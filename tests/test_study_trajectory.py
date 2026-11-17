"""Offline per-call resume, pause, and interruption recovery checks."""

from contextlib import redirect_stderr, redirect_stdout
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from local_llm import OllamaError
import run_multi_agent as primary
import study_trajectory as engine


class FixtureClient:
    calls = []
    instances = []

    def __init__(self, **options):
        self.local_calls = []
        FixtureClient.instances.append(self)

    def health(self):
        return {"version": "fixture-runtime", "models": [
            {"name": "llama3.2:3b", "digest": "fixture-digest"}]}

    def chat(self, model, messages, **options):
        call = {"model": model, "messages": copy.deepcopy(messages), **options}
        self.local_calls.append(call)
        FixtureClient.calls.append(call)
        return {"model": model, "done": True, "done_reason": "stop", "prompt_eval_count": 20,
                "eval_count": 10, "message": {"role": "assistant", "content":
                '{"explanation":"Fixture response.","expression":"1/2"}'}}


class Clock:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        self.value += 0.01
        return self.value


class TrajectoryTests(unittest.TestCase):
    def setUp(self):
        FixtureClient.calls, FixtureClient.instances = [], []

    def inputs(self, root):
        manifest = json.loads((primary.ROOT / "config/multi_agent_pilot.json").read_text())
        manifest["tasks"] = manifest["tasks"][:1]
        path = Path(root) / "question.json"
        path.write_text(json.dumps(manifest), encoding="utf-8")
        return {"config_path": primary.CONFIG_PATH, "tasks_path": path,
                "output_dir": Path(root) / "primary"}

    def invoke(self, options, client=FixtureClient):
        output, errors = io.StringIO(), io.StringIO()
        with patch.object(engine, "OllamaClient", client), redirect_stdout(output), redirect_stderr(errors):
            code = engine.run_question(**options)
        return code, output.getvalue(), errors.getvalue()

    def assert_complete(self, path, condition="all_to_all"):
        manifest = json.loads((path / "run-manifest.json").read_text())
        self.assertEqual(manifest["status"], "complete")
        records = [r for r in primary.jsonl(path / "answers.jsonl") if r.get("type") == "answer"]
        self.assertEqual(len(records), 40)
        self.assertEqual(len({(r["round"], r["agent_id"]) for r in records}), 40)
        with patch.object(engine, "OllamaClient", side_effect=AssertionError("Offline audit only")):
            engine.analyze_run(path, condition)
        return manifest, records

    def test_primary_pause_after_three_calls_resumes_only_remaining_thirty_seven(self):
        with tempfile.TemporaryDirectory() as directory:
            options = self.inputs(directory)
            code, _, error = self.invoke({**options, "pause_requested": lambda: len(FixtureClient.calls) >= 3})
            self.assertEqual(code, 2, error)
            self.assertEqual(len(FixtureClient.calls), 3)
            manifest = json.loads((options["output_dir"] / "run-manifest.json").read_text())
            self.assertEqual(manifest["status"], "paused")
            self.assertEqual(manifest["calls_completed"], 3)
            before = (options["output_dir"] / "answers.jsonl").read_bytes()
            code, _, error = self.invoke({**options, "resume": True})
            self.assertEqual(code, 0, error)
            self.assertEqual(len(FixtureClient.calls), 40)
            self.assertEqual(len(FixtureClient.instances[-1].local_calls), 37)
            self.assertTrue((options["output_dir"] / "answers.jsonl").read_bytes().startswith(before))
            self.assert_complete(options["output_dir"])

    def test_self_revision_reuses_ten_initial_calls_and_resumes_remaining_twenty_eight(self):
        with tempfile.TemporaryDirectory() as directory:
            options = self.inputs(directory)
            self.assertEqual(self.invoke(options)[0], 0)
            FixtureClient.calls = []
            control_options = {**options, "output_dir": Path(directory) / "control", "condition": "self_revision",
                               "parent_run": options["output_dir"]}
            code, _, error = self.invoke({**control_options, "pause_requested": lambda: len(FixtureClient.calls) >= 2})
            self.assertEqual(code, 2, error)
            self.assertEqual(len(FixtureClient.calls), 2)
            code, _, error = self.invoke({**control_options, "resume": True})
            self.assertEqual(code, 0, error)
            self.assertEqual(len(FixtureClient.calls), 30)
            self.assertEqual(len(FixtureClient.instances[-1].local_calls), 28)
            manifest, records = self.assert_complete(control_options["output_dir"], "self_revision")
            self.assertEqual(manifest["new_calls_completed"], 30)
            self.assertTrue(all(record["reused_round_zero"] for record in records[:10]))

    def test_paused_idle_time_is_excluded_from_accumulated_round_wall(self):
        with tempfile.TemporaryDirectory() as directory:
            options = self.inputs(directory)
            clock = Clock()
            with patch.object(engine.time, "perf_counter", clock):
                self.assertEqual(self.invoke({**options, "pause_requested": lambda: len(FixtureClient.calls) >= 3})[0], 2)
                first = json.loads((options["output_dir"] / "run-manifest.json").read_text())
                elapsed = next(iter(first["round_timing"].values()))["active_seconds"]
                clock.value += 100000
                code, _, error = self.invoke({**options, "resume": True})
            self.assertEqual(code, 0, error)
            rounds = primary.jsonl(options["output_dir"] / "rounds.jsonl")
            self.assertGreaterEqual(rounds[0]["round_wall_seconds"], elapsed)
            self.assertLess(sum(row["round_wall_seconds"] for row in rounds), 100)

    def test_returned_raw_without_answer_is_recovered_without_requery(self):
        with tempfile.TemporaryDirectory() as directory:
            options = self.inputs(directory)
            with patch.object(engine, "evaluate_response", side_effect=KeyboardInterrupt):
                code, _, _ = self.invoke(options)
            self.assertEqual(code, 130)
            self.assertEqual(len(FixtureClient.calls), 1)
            self.assertEqual(len(primary.jsonl(options["output_dir"] / "generations.jsonl")), 1)
            self.assertFalse(primary.jsonl(options["output_dir"] / "answers.jsonl"))
            code, _, error = self.invoke({**options, "resume": True})
            self.assertEqual(code, 0, error)
            self.assertEqual(len(FixtureClient.calls), 40)
            self.assertEqual(len(FixtureClient.instances[-1].local_calls), 39)
            manifest, _ = self.assert_complete(options["output_dir"])
            self.assertEqual(manifest["attempts"][0]["status"], "recovered_from_raw")

    def test_ten_answers_without_round_summary_are_completed_locally(self):
        with tempfile.TemporaryDirectory() as directory:
            options = self.inputs(directory)
            with patch.object(engine.primary, "summarize_round", side_effect=KeyboardInterrupt):
                code, _, _ = self.invoke(options)
            self.assertEqual(code, 130)
            self.assertEqual(len(FixtureClient.calls), 10)
            self.assertFalse(primary.jsonl(options["output_dir"] / "rounds.jsonl"))
            code, _, error = self.invoke({**options, "resume": True})
            self.assertEqual(code, 0, error)
            self.assertEqual(len(FixtureClient.instances[-1].local_calls), 30)
            self.assert_complete(options["output_dir"])

    def test_completion_marker_before_final_manifest_is_recovered_without_model_calls(self):
        with tempfile.TemporaryDirectory() as directory:
            options = self.inputs(directory)
            with patch.object(engine, "_finish_artifacts", side_effect=KeyboardInterrupt):
                code, _, _ = self.invoke(options)
            self.assertEqual(code, 130)
            self.assertEqual(len(FixtureClient.calls), 40)
            code, _, error = self.invoke({**options, "resume": True})
            self.assertEqual(code, 0, error)
            self.assertFalse(FixtureClient.instances[-1].local_calls)
            self.assertEqual(len(primary.jsonl(options["output_dir"] / "answers.jsonl")), 41)
            self.assert_complete(options["output_dir"])

    def test_resume_rejects_tampered_or_truncated_evidence_before_append(self):
        for mode in ("tamper", "truncated"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                FixtureClient.calls = []
                options = self.inputs(directory)
                self.assertEqual(self.invoke({**options, "pause_requested": lambda: len(FixtureClient.calls) >= 3})[0], 2)
                path = options["output_dir"] / "answers.jsonl"
                if mode == "tamper":
                    path.write_text(path.read_text().replace("Fixture response.", "Changed evidence."))
                else:
                    with path.open("ab") as output:
                        output.write(b'{"unfinished"')
                before = {name: (options["output_dir"] / name).read_bytes()
                          for name in (*engine.JOURNALS, "run-manifest.json")}
                calls = len(FixtureClient.calls)
                code, _, _ = self.invoke({**options, "resume": True})
                self.assertEqual(code, 1)
                self.assertEqual(len(FixtureClient.calls), calls)
                for name, data in before.items():
                    self.assertEqual((options["output_dir"] / name).read_bytes(), data)

    def test_runtime_and_input_drift_refuse_resume_without_changing_checkpoint(self):
        class DifferentRuntimeClient(FixtureClient):
            def health(self):
                result = super().health()
                result["version"] = "changed-runtime"
                return result
        with tempfile.TemporaryDirectory() as directory:
            options = self.inputs(directory)
            self.assertEqual(self.invoke({**options, "pause_requested": lambda: len(FixtureClient.calls) >= 3})[0], 2)
            manifest = options["output_dir"] / "run-manifest.json"
            before = manifest.read_bytes()
            code, _, _ = self.invoke({**options, "resume": True}, DifferentRuntimeClient)
            self.assertEqual(code, 1)
            self.assertEqual(manifest.read_bytes(), before)
            bank = json.loads(options["tasks_path"].read_text())
            bank["tasks"][0]["private_note"] = "changed input"
            options["tasks_path"].write_text(json.dumps(bank))
            code, _, _ = self.invoke({**options, "resume": True})
            self.assertEqual(code, 1)
            self.assertEqual(manifest.read_bytes(), before)
            self.assertEqual(len(FixtureClient.calls), 3)

    def test_explicit_resume_after_transport_failure_preserves_completed_calls_and_unknown_attempt_cost(self):
        class FailingClient(FixtureClient):
            def chat(self, *args, **kwargs):
                if len(FixtureClient.calls) == 3:
                    raise OllamaError("Transport ended before a raw response was returned")
                return super().chat(*args, **kwargs)
        with tempfile.TemporaryDirectory() as directory:
            options = self.inputs(directory)
            code, _, _ = self.invoke(options, FailingClient)
            self.assertEqual(code, 1)
            manifest = json.loads((options["output_dir"] / "run-manifest.json").read_text())
            self.assertEqual(manifest["status"], "failed")
            self.assertEqual(manifest["calls_completed"], 3)
            self.assertIsNone(manifest["attempts"][-1]["input_tokens"])
            self.assertIsNone(manifest["attempts"][-1]["output_tokens"])
            self.assertEqual(manifest["attempts"][-1]["status"], "uncertain_no_returned_raw")
            code, _, error = self.invoke({**options, "resume": True})
            self.assertEqual(code, 0, error)
            self.assertEqual(len(FixtureClient.calls), 40)
            self.assertEqual(len(FixtureClient.instances[-1].local_calls), 37)
            manifest, _ = self.assert_complete(options["output_dir"])
            self.assertEqual(len(manifest["attempts"]), 41)
            self.assertEqual(len(manifest["error_history"]), 1)

    def test_changed_checkpoint_timing_is_rejected_without_touching_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            options = self.inputs(directory)
            self.assertEqual(self.invoke({**options, "pause_requested": lambda: len(FixtureClient.calls) >= 3})[0], 2)
            path = options["output_dir"] / "run-manifest.json"
            manifest = json.loads(path.read_text())
            next(iter(manifest["round_timing"].values()))["active_seconds"] += 1000000
            path.write_text(json.dumps(manifest))
            before = path.read_bytes()
            raw = (options["output_dir"] / "generations.jsonl").read_bytes()
            code, _, error = self.invoke({**options, "resume": True})
            self.assertEqual(code, 1)
            self.assertIn("timing", error)
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual((options["output_dir"] / "generations.jsonl").read_bytes(), raw)
            self.assertEqual(len(FixtureClient.calls), 3)


if __name__ == "__main__":
    unittest.main()
