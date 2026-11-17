"""Offline paired-format, durable-resume, and recommendation checks."""

from contextlib import redirect_stderr, redirect_stdout
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from calculator_protocol import SYSTEM
from local_llm import OllamaError
import run_followup_pilot as pilot


class FixtureClient:
    instances = []
    all_calls = []
    pause_path = None

    def __init__(self, **options):
        self.options, self.calls = options, []
        FixtureClient.instances.append(self)
        plan = pilot.load_plan(pilot.CONFIG_PATH)
        self.tasks = {task["prompt"]: task for task in plan["tasks_snapshot"]}

    def health(self):
        return {"version": "fixture-runtime", "models": [{"name": "llama3.2:3b", "digest": "fixture-digest"}]}

    def chat(self, model, messages, **options):
        call = {"model": model, "messages": copy.deepcopy(messages), **copy.deepcopy(options)}
        self.calls.append(call)
        FixtureClient.all_calls.append(call)
        task = self.tasks[messages[1]["content"]]
        content = json.dumps({"explanation": "Use the stated quantities.",
                              "expression": task["parameters"]["reference_expression"]})
        return {"model": model, "message": {"content": content}, "done": True,
                "done_reason": "stop", "prompt_eval_count": 200, "eval_count": 50}


def rows(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines()]


class FollowupPilotTests(unittest.TestCase):
    def setUp(self):
        FixtureClient.instances, FixtureClient.all_calls, FixtureClient.pause_path = [], [], None

    def invoke(self, arguments, client=FixtureClient):
        output, errors = io.StringIO(), io.StringIO()
        with patch.object(pilot, "PilotClient", client), patch.object(pilot, "hardware_identity", return_value={"fixture": "same-machine"}), \
                redirect_stdout(output), redirect_stderr(errors):
            code = pilot.main(arguments)
        return code, output.getvalue(), errors.getvalue()

    def complete(self, destination, client=FixtureClient):
        code, output, error = self.invoke(["--output-dir", str(destination)], client)
        self.assertEqual(code, 0, output + error)
        return json.loads((destination / "summary.json").read_text())

    def test_dry_run_is_exactly_160_paired_development_calls_without_service_or_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "dry"
            with patch.object(pilot, "PilotClient", side_effect=AssertionError("No Ollama")), \
                    patch.object(pilot, "hardware_identity", side_effect=AssertionError("No hardware calls")), \
                    redirect_stdout(io.StringIO()) as output:
                code = pilot.main(["--dry-run", "--output-dir", str(target)])
            self.assertEqual(code, 0)
            plan = json.loads(output.getvalue())
            self.assertEqual(plan["planned_calls"], 160)
            self.assertEqual(len(plan["tasks_snapshot"]), 8)
            self.assertEqual({task["split"] for task in plan["tasks_snapshot"]}, {"development"})
            self.assertEqual(len({task["group_id"] for task in plan["tasks_snapshot"]}), 8)
            self.assertFalse(target.exists())
            for question_index in range(8):
                for agent in range(10):
                    pair = plan["calls"][question_index * 20 + agent * 2:question_index * 20 + agent * 2 + 2]
                    self.assertEqual(pair[0]["seed"], pair[1]["seed"])
                    self.assertEqual(pair[0]["messages"], pair[1]["messages"])
                    self.assertEqual(pair[0]["messages"][0], {"role": "system", "content": SYSTEM})
                    self.assertEqual(pair[0]["profile"], "baseline_json" if (question_index + agent) % 2 == 0 else "strict_schema")
                    self.assertEqual({call["profile"] for call in pair}, {"baseline_json", "strict_schema"})

    def test_complete_profiles_preserve_raw_and_baseline_wins_ties(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "complete"
            summary = self.complete(target)
            self.assertEqual(summary["recommendation"], "baseline_json")
            self.assertEqual(summary["paired_questions"], 8)
            self.assertEqual(len(rows(target / "generations.jsonl")), 160)
            answers = rows(target / "answers.jsonl")
            self.assertEqual(len(answers), 160)
            for profile, expected in pilot.PROFILES.items():
                selected = [record for record in answers if record["profile"] == profile]
                self.assertEqual(len(selected), 80)
                self.assertTrue(all(record["format"] == expected for record in selected))
                self.assertEqual(summary["profiles"][profile]["eligible"], 80)
                self.assertEqual(summary["profiles"][profile]["collective_correct"], 8)
                self.assertTrue(summary["profiles"][profile]["ceiling_observed"])
            self.assertTrue(all(record["elapsed_seconds"] >= 0 for record in answers))
            manifest = json.loads((target / "run-manifest.json").read_text())
            self.assertEqual(manifest["status"], "complete")
            self.assertEqual(manifest["calls_completed"], 160)
            self.assertEqual(manifest["hardware_snapshot"], {"fixture": "same-machine"})
            self.assertEqual(manifest["schema_sha256"], pilot.snapshot_hash(pilot.STRICT_SCHEMA))

    def test_schema_intervention_is_lexical_and_calculator_remains_final_gate(self):
        for expression in ("1/0", "1**2", "2(3+4)", "1..2"):
            raw = {"message": {"content": json.dumps({"explanation": "A setup", "expression": expression})}, "done": True}
            self.assertTrue(pilot.schema_conforms(raw))
            generation = {"raw": raw, "profile": "strict_schema"}
            self.assertFalse(pilot.evaluate_generation(generation, {"probability": False})["response"]["eligible"])
        for expression in ("x=(1+2)", "1^2", "sqrt(4)", "1e3", "1\n+2"):
            raw = {"message": {"content": json.dumps({"explanation": "A setup", "expression": expression})}}
            self.assertFalse(pilot.schema_conforms(raw))
        self.assertFalse(pilot.schema_conforms({"message": {"content": '{"explanation":"ok","expression":"1","extra":true}'}}))

    def test_transport_posts_schema_object_and_retains_all_other_generation_settings(self):
        client = pilot.PilotClient(timeout=600)
        raw = {"message": {"content": "{}"}, "done": True}
        messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": "Question"}]
        with patch.object(client, "_request", return_value=raw) as request:
            result = client.chat("llama3.2:3b", messages, seed=5, temperature=0.7, max_tokens=1024,
                                 format_value=pilot.STRICT_SCHEMA)
        self.assertEqual(result, raw)
        path, payload = request.call_args.args
        self.assertEqual(path, "/api/chat")
        self.assertIsInstance(payload["format"], dict)
        self.assertEqual(payload["format"], pilot.STRICT_SCHEMA)
        self.assertEqual(payload["messages"], messages)
        self.assertEqual(payload["options"], {"seed": 5, "temperature": 0.7, "num_predict": 1024, "num_ctx": 16384})
        self.assertEqual(payload["keep_alive"], 0)

    def test_strict_better_eligibility_is_a_recommendation_not_automatic_adoption(self):
        class FormatFailureClient(FixtureClient):
            def chat(self, *arguments, **options):
                raw = super().chat(*arguments, **options)
                if options["format_value"] == "json":
                    raw["message"]["content"] = '{"explanation":"Correct steps.","expression":"x = 7"}'
                return raw
        with tempfile.TemporaryDirectory() as directory:
            summary = self.complete(Path(directory) / "strict", FormatFailureClient)
            self.assertEqual(summary["recommendation"], "strict_schema_for_review")
            self.assertEqual(summary["profiles"]["baseline_json"]["eligible"], 0)
            self.assertTrue(summary["profiles"]["baseline_json"]["floor_observed"])
            self.assertEqual(summary["profiles"]["strict_schema"]["eligible"], 80)
            self.assertIn("adoption requires review", " ".join(summary["notes"]))

    def test_neither_profile_passes_stops_and_missing_tokens_stay_unknown(self):
        class ArithmeticFailureClient(FixtureClient):
            def chat(self, *arguments, **options):
                raw = super().chat(*arguments, **options)
                raw["message"]["content"] = '{"explanation":"Setup","expression":"1/0"}'
                raw.pop("prompt_eval_count")
                return raw
        with tempfile.TemporaryDirectory() as directory:
            summary = self.complete(Path(directory) / "stop", ArithmeticFailureClient)
            self.assertEqual(summary["recommendation"], "stop_and_review_neither_passes")
            for profile in summary["profiles"].values():
                self.assertIsNone(profile["input_tokens"])
                self.assertEqual(profile["calculator_errors"], 80)

    def test_collective_accuracy_loss_screen_has_a_one_question_boundary(self):
        class AccuracyTradeoffClient(FixtureClient):
            losses = 1
            def chat(self, model, messages, **options):
                raw = super().chat(model, messages, **options)
                task = self.tasks[messages[1]["content"]]
                if options["format_value"] == "json" and len(self.calls) == 1:
                    raw["message"]["content"] = '{"explanation":"Setup","expression":"x=1"}'
                elif isinstance(options["format_value"], dict) and task["id"] in pilot.TASK_IDS[:self.losses]:
                    raw["message"]["content"] = '{"explanation":"Wrong arithmetic setup","expression":"0"}'
                return raw
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            AccuracyTradeoffClient.losses = 1
            summary = self.complete(target / "one-loss", AccuracyTradeoffClient)
            self.assertTrue(summary["strict_noninferiority_screen_pass"])
            self.assertEqual(summary["recommendation"], "strict_schema_for_review")
            AccuracyTradeoffClient.losses = 2
            summary = self.complete(target / "two-losses", AccuracyTradeoffClient)
            self.assertFalse(summary["strict_noninferiority_screen_pass"])
            self.assertEqual(summary["recommendation"], "baseline_json")

    def test_strict_schema_violation_stops_after_preserving_unmodified_raw(self):
        class UnsupportedSchemaClient(FixtureClient):
            def chat(self, *arguments, **options):
                raw = super().chat(*arguments, **options)
                if isinstance(options["format_value"], dict):
                    raw["message"]["content"] = '{"explanation":"Setup","expression":"x=7"}'
                return raw
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "unsupported"
            code, _, error = self.invoke(["--output-dir", str(target)], UnsupportedSchemaClient)
            self.assertEqual(code, 1)
            self.assertIn("Strict schema violation", error)
            self.assertEqual(len(rows(target / "generations.jsonl")), 2)
            self.assertEqual(len(rows(target / "answers.jsonl")), 1)
            self.assertIn("x=7", rows(target / "generations.jsonl")[-1]["raw"]["message"]["content"])
            self.assertEqual(json.loads((target / "run-manifest.json").read_text())["schema_support_check"], "failed_or_truncated")
            self.assertFalse((target / "summary.json").exists())

    def test_cooperative_pause_and_resume_do_not_replay_completed_pairs(self):
        class PausingClient(FixtureClient):
            def chat(self, *arguments, **options):
                raw = super().chat(*arguments, **options)
                if len(FixtureClient.all_calls) == 3:
                    FixtureClient.pause_path.touch()
                return raw
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "paused"
            FixtureClient.pause_path = target / ".pause-request"
            code, _, _ = self.invoke(["--output-dir", str(target)], PausingClient)
            self.assertEqual(code, 2)
            self.assertEqual(len(rows(target / "answers.jsonl")), 3)
            prefix_raw = (target / "generations.jsonl").read_bytes()
            prefix_answers = (target / "answers.jsonl").read_bytes()
            code, output, error = self.invoke(["--resume", "--output-dir", str(target)])
            self.assertEqual(code, 0, output + error)
            self.assertEqual(len(FixtureClient.all_calls), 160)
            self.assertTrue((target / "generations.jsonl").read_bytes().startswith(prefix_raw))
            self.assertTrue((target / "answers.jsonl").read_bytes().startswith(prefix_answers))
            self.assertEqual(json.loads((target / "run-manifest.json").read_text())["status"], "complete")
            self.assertFalse(FixtureClient.pause_path.exists())

    def test_force_interruption_recovers_durable_raw_without_an_extra_model_call(self):
        original = pilot.evaluate_generation
        interrupted = False
        def force_once(generation, task):
            nonlocal interrupted
            if not interrupted:
                interrupted = True
                raise KeyboardInterrupt
            return original(generation, task)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "forced"
            with patch.object(pilot, "evaluate_generation", side_effect=force_once):
                code, _, _ = self.invoke(["--output-dir", str(target)])
            self.assertEqual(code, 130)
            self.assertEqual(len(rows(target / "generations.jsonl")), 1)
            self.assertEqual(len(rows(target / "answers.jsonl")), 0)
            code, output, error = self.invoke(["--resume", "--output-dir", str(target)])
            self.assertEqual(code, 0, output + error)
            self.assertEqual(len(FixtureClient.all_calls), 160)
            self.assertEqual(len(rows(target / "answers.jsonl")), 160)

    def test_transport_failure_resumes_at_failed_position_without_overwriting(self):
        class FailingClient(FixtureClient):
            def chat(self, *arguments, **options):
                if len(self.calls) == 4:
                    raise OllamaError("Fixture transport failure")
                return super().chat(*arguments, **options)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "failed"
            code, _, _ = self.invoke(["--output-dir", str(target)], FailingClient)
            self.assertEqual(code, 1)
            self.assertEqual(len(rows(target / "answers.jsonl")), 4)
            before = (target / "answers.jsonl").read_bytes()
            code, _, _ = self.invoke(["--output-dir", str(target)])
            self.assertEqual(code, 1)
            self.assertEqual(before, (target / "answers.jsonl").read_bytes())
            code, output, error = self.invoke(["--resume", "--output-dir", str(target)])
            self.assertEqual(code, 0, output + error)
            self.assertEqual(len(FixtureClient.all_calls), 160)

    def test_resume_rejects_changed_evidence_and_hardware_before_inference(self):
        class PausingClient(FixtureClient):
            def chat(self, *arguments, **options):
                raw = super().chat(*arguments, **options)
                FixtureClient.pause_path.touch()
                return raw
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "tamper"
            FixtureClient.pause_path = target / ".pause-request"
            self.assertEqual(self.invoke(["--output-dir", str(target)], PausingClient)[0], 2)
            path = target / "answers.jsonl"
            evidence = path.read_bytes()
            path.write_bytes(evidence.replace(b'"eligible": true', b'"eligible": false'))
            calls_before = len(FixtureClient.all_calls)
            self.assertEqual(self.invoke(["--resume", "--output-dir", str(target)])[0], 1)
            self.assertEqual(len(FixtureClient.all_calls), calls_before)
            path.write_bytes(evidence)
            with patch.object(pilot, "PilotClient", side_effect=AssertionError("No inference")), \
                    patch.object(pilot, "hardware_identity", return_value={"fixture": "different-machine"}), \
                    redirect_stderr(io.StringIO()):
                self.assertEqual(pilot.main(["--resume", "--output-dir", str(target)]), 1)

    def test_pause_command_only_requests_an_existing_incomplete_run(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "missing"
            self.assertEqual(self.invoke(["--pause", "--output-dir", str(target)])[0], 1)
            self.assertFalse(target.exists())
            target.mkdir()
            (target / "run-manifest.json").write_text(json.dumps({"experiment_id": pilot.EXPERIMENT_ID, "status": "running"}))
            with patch.object(pilot, "PilotClient", side_effect=AssertionError("No Ollama")), redirect_stdout(io.StringIO()):
                self.assertEqual(pilot.main(["--pause", "--output-dir", str(target)]), 0)
            self.assertTrue((target / ".pause-request").exists())

    def test_failed_service_check_leaves_no_empty_unresumable_output_directory(self):
        class UnavailableClient(FixtureClient):
            def health(self):
                raise OllamaError("Fixture service unavailable")
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "not-started"
            self.assertEqual(self.invoke(["--output-dir", str(target)], UnavailableClient)[0], 1)
            self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
