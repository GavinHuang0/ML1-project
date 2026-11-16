"""Offline integration checks for frozen, synchronous multi-agent trajectories."""

from contextlib import redirect_stderr, redirect_stdout
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from calculator_protocol import SYSTEM
from local_llm import OllamaClient as BaselineClient, OllamaError
from multi_agent_llm import MultiAgentClient
import run_multi_agent as runner


class FixtureClient:
    instances = []

    def __init__(self, **options):
        self.options = options
        self.calls, self.responses = [], []
        self.health_calls = self.attempts = 0
        FixtureClient.instances.append(self)

    def health(self):
        self.health_calls += 1
        return {"version": "fixture-runtime", "models": [
            {"name": "llama3.2:3b", "digest": "fixture-digest"}]}

    def chat(self, model, messages, **options):
        self.attempts += 1
        round_index = (len(self.calls) // 10) % 4
        self.calls.append({"model": model, "messages": copy.deepcopy(messages), **options})
        raw = {"model": model, "message": {"role": "assistant", "content": json.dumps({
            "explanation": f"ROUND_{round_index}_ONLY", "expression": "1/2",
            "private_score": "RESPONSE_METADATA_NEVER_FORWARD"})},
            "done": True, "done_reason": "stop", "prompt_eval_count": 20, "eval_count": 10}
        self.responses.append(raw)
        return raw


def rows(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines()]


def answers(path):
    return [row for row in rows(path) if row.get("type") == "answer"]


class MultiAgentRunnerTests(unittest.TestCase):
    def setUp(self):
        FixtureClient.instances = []

    def invoke(self, arguments, client=FixtureClient):
        output, errors = io.StringIO(), io.StringIO()
        with patch.object(runner, "OllamaClient", client), \
                redirect_stdout(output), redirect_stderr(errors):
            code = runner.main(arguments)
        return code, output.getvalue(), errors.getvalue()

    def complete(self, destination, client=FixtureClient, extra=()):
        code, output, error = self.invoke(["--output-dir", str(destination), *extra], client)
        self.assertEqual(code, 0, output + error)
        return FixtureClient.instances[-1]

    def write_bank(self, directory, split, prefix="", filename=None):
        manifest = json.loads((runner.ROOT / "config" / "multi_agent_pilot.json").read_text())
        manifest["manifest_id"] = f"fixture-{split}"
        for task in manifest["tasks"]:
            task["id"] = prefix + task["id"]
            task["split"] = split
        path = Path(directory) / (filename or f"{split}-bank.json")
        path.write_text(json.dumps(manifest), encoding="utf-8")
        return path, manifest

    def validation_selection(self, directory):
        root = Path(directory)
        development = root / "development"
        self.complete(development)
        calibration = development / "calibration.json"
        validation_bank, bank = self.write_bank(root, "validation", "validation-")
        validation = root / "validation"
        self.complete(validation, extra=("--tasks", str(validation_bank), "--calibration", str(calibration)))
        return calibration, validation, validation / "selection.json", bank

    def test_dry_run_has_no_service_access_or_output_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "preview"
            with patch.object(runner, "OllamaClient", side_effect=AssertionError("No service access")), \
                    redirect_stdout(io.StringIO()) as output:
                code = runner.main(["--dry-run", "--output-dir", str(destination)])
            self.assertEqual(code, 0)
            plan = json.loads(output.getvalue())
            self.assertEqual(plan["planned_calls"], 160)
            self.assertEqual(plan["configuration_snapshot"]["protocol"]["num_agents"], 10)
            self.assertEqual(plan["configuration_snapshot"]["protocol"]["max_rounds"], 3)
            self.assertFalse(destination.exists())
            self.assertEqual(FixtureClient.instances, [])

    def test_complete_trajectory_is_synchronous_reproducible_and_reference_free(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "complete"
            manifest = json.loads((runner.ROOT / "config" / "multi_agent_pilot.json").read_text())
            manifest["source"]["private_note"] = "MANIFEST_METADATA_NEVER_SEND"
            for task in manifest["tasks"]:
                task["private_note"] = "TASK_METADATA_NEVER_SEND"
            task_path = Path(directory) / "private-bank.json"
            task_path.write_text(json.dumps(manifest), encoding="utf-8")
            client = self.complete(destination, extra=("--timeout", "432", "--tasks", str(task_path)))
            recorded = answers(destination / "answers.jsonl")
            self.assertEqual(len(recorded), 160)
            self.assertEqual(len(client.calls), 160)
            self.assertEqual(client.options["timeout"], 432)
            self.assertEqual(len({(r["question_id"], r["round"], r["agent_id"]) for r in recorded}), 160)
            self.assertEqual(len({r["seed"] for r in recorded}), 160)
            for record, raw, call in zip(recorded, client.responses, client.calls):
                self.assertEqual(record["raw"], raw)
                self.assertEqual(record["messages"], call["messages"])
                self.assertEqual(record["seed"], call["seed"])
                self.assertEqual(call["model"], "llama3.2:3b")
                self.assertEqual(call["temperature"], 0.7)
                self.assertEqual(call["max_tokens"], 1024)
                self.assertEqual(record["response"]["computed_fraction"], "1/2")
                sent = json.dumps(record["messages"])
                for private in ("gold_fraction", "gold_probability", "numeric_correct",
                                "RESPONSE_METADATA_NEVER_FORWARD", "private_score",
                                "MANIFEST_METADATA_NEVER_SEND", "TASK_METADATA_NEVER_SEND"):
                    self.assertNotIn(private, sent)
                if record["round"] == 0:
                    self.assertEqual(record["messages"][0], {"role": "system", "content": SYSTEM})
                    self.assertNotIn("ROUND_0_ONLY", sent)
                else:
                    self.assertIn(f"ROUND_{record['round'] - 1}_ONLY", sent)
                    for other in range(4):
                        if other != record["round"] - 1:
                            self.assertNotIn(f"ROUND_{other}_ONLY", sent)
            completed_rounds = rows(destination / "rounds.jsonl")
            self.assertEqual(len(completed_rounds), 16)
            self.assertTrue(all(r["round_wall_seconds"] >= 0 for r in completed_rounds))
            manifest = json.loads((destination / "run-manifest.json").read_text())
            self.assertEqual(manifest["status"], "complete")
            self.assertEqual(manifest["calls_completed"], 160)
            self.assertEqual(manifest["rounds_completed"], 16)
            self.assertTrue(any(r.get("type") == "complete" for r in rows(destination / "answers.jsonl")))
            self.assertTrue((destination / "summary.json").exists())
            self.assertTrue((destination / "calibration.json").exists())
            second = Path(directory) / "repeat"
            self.complete(second, extra=("--tasks", str(task_path)))
            self.assertEqual([r["seed"] for r in answers(second / "answers.jsonl")],
                             [r["seed"] for r in recorded])

    def test_model_format_failures_continue_without_repair_or_retry(self):
        class InvalidClient(FixtureClient):
            def chat(self, *arguments, **options):
                raw = super().chat(*arguments, **options)
                raw["message"]["content"] = ("{unfinished" if len(self.calls) % 2 else
                    '{"explanation":"Invalid formula.","expression":"x=1/2"}')
                return raw
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "invalid"
            client = self.complete(destination, InvalidClient)
            recorded = answers(destination / "answers.jsonl")
            self.assertEqual(client.attempts, 160)
            self.assertFalse(any(r["response"]["eligible"] for r in recorded))
            self.assertTrue(all(r["aggregate_abstained"] for r in rows(destination / "rounds.jsonl")))
            self.assertEqual(sum(r["response"]["calculator_attempted"] for r in recorded), 80)

    def test_transport_failure_preserves_partial_evidence_and_stops(self):
        class FailingClient(FixtureClient):
            def chat(self, *arguments, **options):
                if len(self.calls) == 3:
                    self.attempts += 1
                    raise OllamaError("Fixture unavailable")
                return super().chat(*arguments, **options)
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "partial"
            code, _, _ = self.invoke(["--output-dir", str(destination)], FailingClient)
            self.assertEqual(code, 1)
            self.assertEqual(FixtureClient.instances[0].attempts, 4)
            self.assertEqual(len(answers(destination / "answers.jsonl")), 3)
            self.assertFalse((destination / "summary.json").exists())
            manifest = json.loads((destination / "run-manifest.json").read_text())
            self.assertEqual(manifest["status"], "failed")
            self.assertEqual(manifest["calls_completed"], 3)
            self.assertFalse(any(r.get("type") == "complete" for r in rows(destination / "answers.jsonl")))

    def test_malformed_transport_wrapper_is_journaled_before_validation(self):
        class MalformedClient(FixtureClient):
            def chat(self, *arguments, **options):
                raw = super().chat(*arguments, **options)
                raw["message"] = {"role": "assistant", "unexpected_payload": "SAVE_THIS_RAW_EVIDENCE"}
                return raw
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "bad-wrapper"
            code, _, error = self.invoke(["--output-dir", str(destination)], MalformedClient)
            self.assertEqual(code, 1)
            self.assertIn("raw response preserved", error)
            self.assertEqual(len(FixtureClient.instances[0].calls), 1)
            journal = rows(destination / "generations.jsonl")
            self.assertEqual(len(journal), 1)
            self.assertEqual(journal[0]["raw"], FixtureClient.instances[0].responses[0])
            self.assertEqual(journal[0]["raw"]["message"]["unexpected_payload"], "SAVE_THIS_RAW_EVIDENCE")
            self.assertFalse(answers(destination / "answers.jsonl"))
            self.assertFalse((destination / "summary.json").exists())
            self.assertEqual(json.loads((destination / "run-manifest.json").read_text())["status"], "failed")

    def test_missing_token_counts_stay_unknown_instead_of_becoming_zero(self):
        class MissingCountsClient(FixtureClient):
            def chat(self, *arguments, **options):
                raw = super().chat(*arguments, **options)
                raw.pop("prompt_eval_count", None)
                return raw
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "missing-tokens"
            code, _, error = self.invoke(["--output-dir", str(destination)], MissingCountsClient)
            self.assertEqual(code, 0, error)
            for summary in rows(destination / "rounds.jsonl"):
                self.assertIsNone(summary["round_input_tokens"])
                self.assertIsNone(summary["cumulative_total_tokens"])
                self.assertFalse(summary["token_measurements_complete"])
            self.assertFalse((destination / "calibration.json").exists())

    def test_interruption_is_incomplete_and_preserves_saved_answers(self):
        class InterruptedClient(FixtureClient):
            def chat(self, *arguments, **options):
                if len(self.calls) == 2:
                    raise KeyboardInterrupt
                return super().chat(*arguments, **options)
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "interrupted"
            code, _, _ = self.invoke(["--output-dir", str(destination)], InterruptedClient)
            self.assertEqual(code, 130)
            self.assertEqual(len(answers(destination / "answers.jsonl")), 2)
            self.assertEqual(json.loads((destination / "run-manifest.json").read_text())["status"], "interrupted")
            self.assertFalse((destination / "summary.json").exists())

    def test_existing_and_historical_destinations_are_refused_before_service(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "exists"
            destination.mkdir()
            sentinel = destination / "keep.txt"
            sentinel.write_text("Keep this evidence.", encoding="utf-8")
            code, _, error = self.invoke(["--output-dir", str(destination)])
            self.assertEqual(code, 1)
            self.assertIn("already exists", error)
            self.assertEqual(sentinel.read_text(), "Keep this evidence.")
        for target in (runner.ROOT / "archive/new-multi-agent-run",
                       runner.ROOT / "results/baseline/new-multi-agent-run",
                       runner.ROOT / "results/runs/new-multi-agent-run"):
            with self.subTest(target=target):
                code, _, _ = self.invoke(["--output-dir", str(target)])
                self.assertEqual(code, 1)
        self.assertEqual(FixtureClient.instances, [])

    def test_source_and_model_drift_stop_inference(self):
        class DriftClient(FixtureClient):
            def health(self):
                result = super().health()
                if self.calls:
                    result["models"][0]["digest"] = "changed-model"
                return result
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "model-drift"
            code, _, _ = self.invoke(["--output-dir", str(destination)], DriftClient)
            self.assertEqual(code, 1)
            self.assertEqual(len(FixtureClient.instances[0].calls), 1)
            self.assertEqual(json.loads((destination / "run-manifest.json").read_text())["status"], "failed")
        FixtureClient.instances = []
        original = runner.source_hashes
        def changing_hashes(*args, **kwargs):
            value = original(*args, **kwargs)
            return {**value, "fixture_changed": "changed"} if FixtureClient.instances and FixtureClient.instances[0].calls else value
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "source-drift"
            with patch.object(runner, "source_hashes", side_effect=changing_hashes):
                code, _, _ = self.invoke(["--output-dir", str(destination)])
            self.assertEqual(code, 1)
            self.assertEqual(len(FixtureClient.instances[0].calls), 1)
            self.assertFalse((destination / "summary.json").exists())

    def test_final_runtime_check_prevents_false_completion(self):
        class FinalDriftClient(FixtureClient):
            def health(self):
                result = super().health()
                if len(self.calls) == 160:
                    result["version"] = "changed-runtime"
                return result
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "final-drift"
            code, _, _ = self.invoke(["--output-dir", str(destination)], FinalDriftClient)
            self.assertEqual(code, 1)
            self.assertEqual(len(FixtureClient.instances[0].calls), 160)
            self.assertFalse((destination / "summary.json").exists())
            self.assertFalse(any(r.get("type") == "complete" for r in rows(destination / "answers.jsonl")))

    def test_large_peer_payload_is_refused_without_silent_prompt_shortening(self):
        class LongClient(FixtureClient):
            def chat(self, *arguments, **options):
                raw = super().chat(*arguments, **options)
                raw["message"]["content"] = json.dumps({"explanation": "long " * 1000, "expression": "1/2"})
                return raw
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "over-context"
            code, _, error = self.invoke(["--output-dir", str(destination)], LongClient)
            self.assertEqual(code, 1)
            self.assertEqual(len(FixtureClient.instances[0].calls), 10)
            self.assertIn("context", error.lower())
            self.assertFalse((destination / "summary.json").exists())

    def test_offline_analysis_replays_without_service_and_rejects_changed_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "replay"
            self.complete(destination)
            report = Path(directory) / "reanalysis.json"
            with patch.object(runner, "OllamaClient", side_effect=AssertionError("Offline only")), \
                    redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                code = runner.main(["--analyze-run", str(destination), "--analysis-output", str(report)])
            self.assertEqual(code, 0)
            self.assertIsInstance(json.loads(report.read_text()), dict)
            path = destination / "answers.jsonl"
            events = rows(path)
            event = next(r for r in events if r.get("type") == "answer")
            event["response"]["computed_fraction"] = "999"
            path.write_text("".join(json.dumps(r) + "\n" for r in events), encoding="utf-8")
            changed_report = Path(directory) / "must-not-exist.json"
            code, _, _ = self.invoke(["--analyze-run", str(destination), "--analysis-output", str(changed_report)])
            self.assertEqual(code, 1)
            self.assertFalse(changed_report.exists())

    def test_offline_analysis_refuses_partial_manifest(self):
        class InterruptedClient(FixtureClient):
            def chat(self, *arguments, **options):
                if self.calls:
                    raise KeyboardInterrupt
                return super().chat(*arguments, **options)
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "partial-replay"
            self.invoke(["--output-dir", str(destination)], InterruptedClient)
            report = Path(directory) / "must-not-exist.json"
            with patch.object(runner, "OllamaClient", side_effect=AssertionError("Offline only")), \
                    redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                code = runner.main(["--analyze-run", str(destination), "--analysis-output", str(report)])
            self.assertEqual(code, 1)
            self.assertFalse(report.exists())

    def test_invalid_timeouts_fail_without_inference(self):
        for timeout in ("0", "-1", "nan", "inf"):
            with self.subTest(timeout=timeout):
                code, _, _ = self.invoke(["--dry-run", "--timeout", timeout])
                self.assertEqual(code, 1)
        self.assertEqual(FixtureClient.instances, [])

    def test_validation_freezes_selection_and_test_requires_it_before_inference(self):
        with tempfile.TemporaryDirectory() as directory:
            calibration, validation, selection_path, bank = self.validation_selection(directory)
            selection = json.loads(selection_path.read_text())
            self.assertEqual(selection["primary_round"], 0)
            self.assertEqual(selection["primary_delta"], 0.02)
            self.assertEqual(selection["primary_omega"], 0.5)
            self.assertEqual(set(selection["validation_question_ids"]), {t["id"] for t in bank["tasks"]})
            self.assertEqual(selection["model_digest"], "fixture-digest")
            self.assertEqual(selection["ollama_version"], "fixture-runtime")
            self.assertTrue(selection["calibration_sha256"])
            test_bank, _ = self.write_bank(directory, "test", "test-")
            before = len(FixtureClient.instances)
            destination = Path(directory) / "missing-selection"
            code, _, error = self.invoke(["--tasks", str(test_bank), "--calibration", str(calibration),
                                          "--output-dir", str(destination)])
            self.assertEqual(code, 1)
            self.assertIn("selection", error.lower())
            self.assertEqual(len(FixtureClient.instances), before)
            self.assertFalse(destination.exists())
            destination = Path(directory) / "test"
            self.complete(destination, extra=("--tasks", str(test_bank), "--calibration", str(calibration),
                                               "--selection", str(selection_path)))
            manifest = json.loads((destination / "run-manifest.json").read_text())
            self.assertEqual(manifest["selection_snapshot"], selection)
            self.assertEqual({task["split"] for task in manifest["tasks_snapshot"]}, {"test"})
            summary = json.loads((destination / "summary.json").read_text())
            self.assertFalse(summary["selected_rounds"])
            report = Path(directory) / "test-reanalysis.json"
            with patch.object(runner, "OllamaClient", side_effect=AssertionError("Offline only")), \
                    redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                code = runner.main(["--analyze-run", str(destination), "--analysis-output", str(report)])
            self.assertEqual(code, 0)
            self.assertTrue(report.exists())

    def test_selection_rejects_changed_calibration_and_offline_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            calibration, _, selection_path, _ = self.validation_selection(directory)
            changed = json.loads(calibration.read_text())
            changed["references"]["token_reference"] *= 2
            changed_calibration = Path(directory) / "changed-calibration.json"
            changed_calibration.write_text(json.dumps(changed), encoding="utf-8")
            test_bank, _ = self.write_bank(directory, "test", "test-")
            before = len(FixtureClient.instances)
            destination = Path(directory) / "changed-reference"
            code, _, _ = self.invoke(["--tasks", str(test_bank), "--calibration", str(changed_calibration),
                                      "--selection", str(selection_path), "--output-dir", str(destination)])
            self.assertEqual(code, 1)
            self.assertEqual(len(FixtureClient.instances), before)
            self.assertFalse(destination.exists())
            destination = Path(directory) / "test"
            self.complete(destination, extra=("--tasks", str(test_bank), "--calibration", str(calibration),
                                               "--selection", str(selection_path)))
            changed_selection = json.loads(selection_path.read_text())
            changed_selection["primary_round"] = 1
            changed_path = Path(directory) / "changed-selection.json"
            changed_path.write_text(json.dumps(changed_selection), encoding="utf-8")
            report = Path(directory) / "must-not-replace-selection.json"
            with patch.object(runner, "OllamaClient", side_effect=AssertionError("Offline only")), \
                    redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                code = runner.main(["--analyze-run", str(destination), "--selection", str(changed_path),
                                    "--analysis-output", str(report)])
            self.assertEqual(code, 1)
            self.assertFalse(report.exists())
            manifest_path = destination / "run-manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["selection_snapshot"]["primary_round"] = 1
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            report = Path(directory) / "must-not-use-changed-snapshot.json"
            with patch.object(runner, "OllamaClient", side_effect=AssertionError("Offline only")), \
                    redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                code = runner.main(["--analyze-run", str(destination), "--analysis-output", str(report)])
            self.assertEqual(code, 1)
            self.assertFalse(report.exists())

    def test_calibration_blocks_runtime_changes_and_reused_questions(self):
        class DifferentRuntimeClient(FixtureClient):
            def health(self):
                result = super().health()
                result["version"] = "different-runtime"
                return result
        with tempfile.TemporaryDirectory() as directory:
            development = Path(directory) / "development"
            self.complete(development)
            calibration = development / "calibration.json"
            validation_bank, _ = self.write_bank(directory, "validation", "validation-")
            before = len(FixtureClient.instances)
            destination = Path(directory) / "runtime-changed"
            code, _, error = self.invoke(["--tasks", str(validation_bank), "--calibration", str(calibration),
                                          "--output-dir", str(destination)], DifferentRuntimeClient)
            self.assertEqual(code, 1)
            self.assertTrue("runtime" in error.lower() or "identity" in error.lower())
            self.assertTrue(all(not client.calls for client in FixtureClient.instances[before:]))
            reused_bank, _ = self.write_bank(directory, "validation", filename="reused-validation.json")
            before = len(FixtureClient.instances)
            code, _, error = self.invoke(["--tasks", str(reused_bank), "--calibration", str(calibration),
                                          "--output-dir", str(Path(directory) / "reused-questions")])
            self.assertEqual(code, 1)
            self.assertTrue("question" in error.lower() or "overlap" in error.lower())
            self.assertEqual(len(FixtureClient.instances), before)

    def test_calibration_read_to_plan_race_is_refused_before_service(self):
        with tempfile.TemporaryDirectory() as directory:
            development = Path(directory) / "development"
            self.complete(development)
            calibration = development / "calibration.json"
            validation_bank, _ = self.write_bank(directory, "validation", "validation-")
            original = runner.read_calibration
            def changing_calibration(path):
                result = original(path)
                path = Path(path)
                path.write_text(path.read_text() + "\n", encoding="utf-8")
                return result
            before = len(FixtureClient.instances)
            destination = Path(directory) / "changed-calibration"
            with patch.object(runner, "read_calibration", side_effect=changing_calibration):
                code, _, error = self.invoke(["--dry-run", "--tasks", str(validation_bank),
                                              "--calibration", str(calibration), "--output-dir", str(destination)])
            self.assertEqual(code, 1)
            self.assertIn("changed after it was read", error)
            self.assertEqual(len(FixtureClient.instances), before)
            self.assertFalse(destination.exists())

    def test_mixed_roles_require_an_explicit_split_and_filter_selected_tasks(self):
        with tempfile.TemporaryDirectory() as directory:
            development = Path(directory) / "development"
            self.complete(development)
            calibration = development / "calibration.json"
            _, validation_bank = self.write_bank(directory, "validation", "validation-")
            _, test_bank = self.write_bank(directory, "test", "test-")
            mixed = copy.deepcopy(validation_bank)
            mixed["tasks"].extend(test_bank["tasks"])
            mixed_path = Path(directory) / "mixed-bank.json"
            mixed_path.write_text(json.dumps(mixed), encoding="utf-8")
            before = len(FixtureClient.instances)
            code, _, _ = self.invoke(["--tasks", str(mixed_path), "--calibration", str(calibration),
                                      "--output-dir", str(Path(directory) / "mixed")])
            self.assertEqual(code, 1)
            self.assertEqual(len(FixtureClient.instances), before)
            selected = Path(directory) / "selected-validation"
            self.complete(selected, extra=("--tasks", str(mixed_path), "--split", "validation",
                                           "--calibration", str(calibration)))
            manifest = json.loads((selected / "run-manifest.json").read_text())
            self.assertEqual(manifest["selected_split"], "validation")
            expected = {task["id"] for task in validation_bank["tasks"]}
            self.assertEqual({task["id"] for task in manifest["tasks_snapshot"]}, expected)
            self.assertEqual({r["question_id"] for r in answers(selected / "answers.jsonl")}, expected)
            self.assertTrue((selected / "selection.json").exists())


class MultiAgentTransportTests(unittest.TestCase):
    def test_dedicated_transport_uses_frozen_context_without_changing_baseline(self):
        messages = [{"role": "user", "content": "What is 1/2?"}]
        raw = {"message": {"content": '{"explanation":"Fixture.","expression":"1/2"}'}, "done": True}
        client = MultiAgentClient(timeout=1)
        with patch.object(client, "_request", return_value=raw) as request:
            self.assertEqual(client.chat("llama3.2:3b", messages, seed=42), raw)
        path, payload = request.call_args.args
        self.assertEqual(path, "/api/chat")
        self.assertEqual(payload, {
            "model": "llama3.2:3b", "messages": messages, "stream": False, "format": "json", "keep_alive": 0,
            "options": {"seed": 42, "temperature": 0.7, "num_predict": 1024, "num_ctx": 16384}})
        baseline = BaselineClient(timeout=1)
        with patch.object(baseline, "_request", return_value=raw) as baseline_request:
            baseline.chat("llama3.2:3b", messages, seed=42)
        self.assertEqual(baseline_request.call_args.args[1]["options"]["num_ctx"], 4096)

    def test_transport_rejects_setting_drift_before_any_request(self):
        client = MultiAgentClient(timeout=1)
        messages = [{"role": "user", "content": "What is 1/2?"}]
        with patch.object(client, "_request", side_effect=AssertionError("No network")):
            for options in ({"temperature": 0.2}, {"max_tokens": 2048}, {"max_tokens": True}, {"seed": True}):
                with self.subTest(options=options), self.assertRaises(ValueError):
                    client.chat("llama3.2:3b", messages, **options)


if __name__ == "__main__":
    unittest.main()
