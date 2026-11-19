"""Mocked durable-call integration for the prospective confirmation runner."""

from contextlib import ExitStack, redirect_stderr, redirect_stdout
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from experiments.confirmation_pilot import runner
from experiments.confirmation_pilot.runner import PilotClient
from local_llm import OllamaError


def response(content=None, *, truncated=False):
    return {"model": "llama3.2:3b", "done": True,
            "done_reason": "length" if truncated else "stop",
            "message": {"role": "assistant", "content": content if content is not None else json.dumps({
                "explanation": "Construct the arithmetic expression.", "expression": "1/2"})},
            "prompt_eval_count": 100, "eval_count": 1024 if truncated else 30}


class FixtureClient:
    def __init__(self, directory):
        self.directory = directory
        self.calls = []
        self.stop_after = None
        self.next_response = None
        self.version = "fixture-runtime"
        self.digest = "fixture-model-digest"

    def health(self):
        return {"version": self.version,
                "models": [{"name": "llama3.2:3b", "digest": self.digest}]}

    def chat(self, model, messages, **kwargs):
        self.calls.append({"model": model, "messages": copy.deepcopy(messages), **copy.deepcopy(kwargs)})
        result = self.next_response or response()
        self.next_response = None
        if self.stop_after == len(self.calls):
            (self.directory / ".pause-request").touch()
        return result


class ConfirmationRunnerTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        base = Path(self.stack.enter_context(tempfile.TemporaryDirectory())).resolve()
        self.output_root = base / "confirmation"
        self.directory = self.output_root / "fixture-v1"
        self.reference_file = base / "reference-evidence.txt"
        self.reference_file.write_bytes(b"frozen selected-profile fixture evidence\n")
        self.identity = {"fixture": "same-machine"}
        self.reference = {"directory": str(base), "evidence_sha256": {
            str(self.reference_file): runner.digest(self.reference_file.read_bytes())},
            "audit": "fixture-audited", "model_digest": "fixture-model-digest",
            "ollama_version": "fixture-runtime", "hardware_snapshot": self.identity,
            "profile": "strict_schema", "reused_answers": 0, "source_sha256": {}}
        self.environment = {"hardware_snapshot": copy.deepcopy(self.identity),
                            "reference_hardware_sha256": runner.snapshot_hash(self.identity),
                            "reference_differences": {}, "environment_id": "fixture-env"}
        self.client = FixtureClient(self.directory)
        self.stack.enter_context(patch.object(runner, "OUTPUT_ROOT", self.output_root))
        self.stack.enter_context(patch.object(runner, "load_reference", side_effect=lambda: copy.deepcopy(self.reference)))
        self.stack.enter_context(patch.object(runner, "load_environment",
                                             side_effect=lambda reference: copy.deepcopy(self.environment)))
        self.stack.enter_context(patch.object(runner, "hardware_identity", return_value=copy.deepcopy(self.identity)))
        self.stack.enter_context(patch.object(runner, "PilotClient", return_value=self.client))

    def invoke(self, *arguments):
        output, error = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(error):
            code = runner.main(["--output-dir", str(self.directory), *arguments])
        self.last_output, self.last_error = output.getvalue(), error.getvalue()
        return code

    def manifest(self):
        return json.loads((self.directory / "run-manifest.json").read_text(encoding="utf-8"))

    def records(self, name):
        return runner.journal_records(self.directory / name)[0]

    def pause_after(self, calls=1):
        self.client.stop_after = calls
        self.assertEqual(self.invoke(), 2, self.last_error)
        manifest = self.manifest()
        self.assertEqual(manifest["status"], "paused")
        self.assertEqual(manifest["calls_completed"], calls)
        return manifest

    def test_full_840_mock_run_pause_resume_and_actual_report_reproduction(self):
        self.pause_after(3)
        original_prefix = (self.directory / "generations.jsonl").read_bytes()
        self.client.stop_after = None
        self.assertEqual(self.invoke("--resume"), 0, self.last_error)
        self.assertEqual(len(self.client.calls), 840)
        manifest = self.manifest()
        self.assertEqual(manifest["status"], "complete")
        self.assertEqual(manifest["calls_completed"], 840)
        self.assertEqual(manifest["generations_saved"], 840)
        self.assertTrue((self.directory / "generations.jsonl").read_bytes().startswith(original_prefix))
        saved = self.records("answers.jsonl")
        self.assertEqual(sum(row["round"] == 0 for row in saved), 120)
        summary = json.loads((self.directory / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(len(summary["comparisons"]), 36)
        self.assertEqual(len(summary["per_question"]), 432)
        self.assertEqual(summary["cohorts"]["new_structure"]["groups"], 4)
        audit = runner.analyze_run(self.directory)
        self.assertTrue(audit["summary_reproduced"])
        self.assertEqual(audit["analysis_model_calls"], 0)
        self.assertEqual(len(self.client.calls), 840)
        self.assertEqual(self.invoke("--resume"), 1)
        self.assertIn("already complete", self.last_error)
        self.assertEqual(len(self.client.calls), 840)
        # A completed report cannot be silently accepted after modification.
        with (self.directory / "comparisons.csv").open("ab") as output:
            output.write(b"tamper\n")
        with self.assertRaisesRegex(ValueError, "Saved report differs"):
            runner.analyze_run(self.directory)
        self.assertEqual(len(self.client.calls), 840)

    def test_raw_orphan_is_evaluated_locally_without_regeneration(self):
        manifest = self.pause_after(1)
        raw_prefix = (self.directory / "generations.jsonl").read_bytes()
        # Simulate a crash after durable raw journaling but before evaluation.
        (self.directory / "answers.jsonl").write_bytes(b"")
        manifest["status"] = "interrupted"
        runner.checkpoint(self.directory, manifest)
        self.client.stop_after = 2
        self.assertEqual(self.invoke("--resume"), 2, self.last_error)
        self.assertEqual(len(self.client.calls), 2)
        self.assertEqual(len(self.records("answers.jsonl")), 2)
        self.assertTrue((self.directory / "generations.jsonl").read_bytes().startswith(raw_prefix))
        self.assertEqual(self.records("answers.jsonl")[0]["seed"], self.client.calls[0]["seed"])

    def test_prospective_truncated_initial_response_is_ineligible_and_not_retried(self):
        self.client.next_response = response('{"explanation":"unfinished', truncated=True)
        self.pause_after(1)
        answer = self.records("answers.jsonl")[0]
        self.assertEqual(answer["arm"], "shared_initial")
        self.assertTrue(answer["output_truncation_failure"])
        self.assertFalse(answer["schema_conforms"])
        self.assertFalse(answer["response"]["eligible"])
        self.assertFalse(answer["response"]["calculator_attempted"])
        self.client.stop_after = 2
        self.assertEqual(self.invoke("--resume"), 2, self.last_error)
        self.assertEqual(len(self.client.calls), 2)

    def test_other_schema_violation_stops_and_preserves_unmodified_raw(self):
        malformed = response(json.dumps({"explanation": "Bad schema", "expression": "x=2"}))
        self.client.next_response = malformed
        self.assertEqual(self.invoke(), 1)
        manifest = self.manifest()
        self.assertEqual((manifest["generations_saved"], manifest["calls_completed"]), (1, 0))
        self.assertEqual(manifest["status"], "failed")
        self.assertEqual(self.records("generations.jsonl")[0]["raw"], malformed)
        original = (self.directory / "generations.jsonl").read_bytes()
        self.assertEqual(self.invoke("--resume"), 1)
        self.assertEqual(len(self.client.calls), 1)
        self.assertEqual((self.directory / "generations.jsonl").read_bytes(), original)

    def test_canonical_call_tampering_is_rejected_even_with_updated_evidence_hash(self):
        manifest = self.pause_after(1)
        rows = self.records("generations.jsonl")
        rows[0]["seed"] += 1
        (self.directory / "generations.jsonl").write_text(json.dumps(rows[0]) + "\n", encoding="utf-8")
        runner.checkpoint(self.directory, manifest)
        self.assertEqual(self.invoke("--resume"), 1)
        self.assertIn("canonical prompt/position", self.last_error)
        self.assertEqual(len(self.client.calls), 1)

    def test_reference_source_drift_blocks_resume_before_inference(self):
        self.pause_after(1)
        self.reference_file.write_bytes(b"changed selected-profile evidence\n")
        self.assertEqual(self.invoke("--resume"), 1)
        self.assertIn("source_sha256", self.last_error)
        self.assertEqual(len(self.client.calls), 1)

    def test_runtime_and_hardware_drift_block_before_output_or_inference(self):
        self.client.version = "different-runtime"
        self.assertEqual(self.invoke(), 1)
        self.assertFalse(self.directory.exists())
        self.assertEqual(self.client.calls, [])

        self.client.version = self.reference["ollama_version"]
        self.client.digest = "different-model"
        self.assertEqual(self.invoke(), 1)
        self.assertFalse(self.directory.exists())
        self.assertEqual(self.client.calls, [])
        self.client.digest = self.reference["model_digest"]
        with patch.object(runner, "hardware_identity", return_value={"fixture": "different-machine"}):
            self.assertEqual(self.invoke(), 1)
        self.assertFalse(self.directory.exists())
        self.assertEqual(self.client.calls, [])

    def test_hardware_drift_on_resume_preserves_saved_calls_and_blocks_inference(self):
        manifest = self.pause_after(1)
        original_raw = (self.directory / "generations.jsonl").read_bytes()
        frozen_identity = copy.deepcopy(manifest["hardware_snapshot"])
        with patch.object(runner, "hardware_identity", return_value={"fixture": "changed-driver"}):
            self.assertEqual(self.invoke("--resume"), 1)
        self.assertIn("Hardware", self.last_error)
        self.assertEqual(len(self.client.calls), 1)
        self.assertEqual((self.directory / "generations.jsonl").read_bytes(), original_raw)
        self.assertEqual(self.manifest()["hardware_snapshot"], frozen_identity)

    def test_new_confirmation_baseline_is_distinct_from_historical_reference(self):
        self.reference["hardware_snapshot"] = {"fixture": "historical-driver"}
        self.environment["reference_hardware_sha256"] = runner.snapshot_hash(self.reference["hardware_snapshot"])
        manifest = self.pause_after(1)
        self.assertEqual(manifest["hardware_snapshot"], self.identity)
        self.assertNotEqual(manifest["hardware_snapshot"], manifest["profile_reference"]["hardware_snapshot"])
        self.client.stop_after = 2
        self.assertEqual(self.invoke("--resume"), 2, self.last_error)
        self.assertEqual(len(self.client.calls), 2)
        self.assertEqual(self.manifest()["hardware_snapshot"], self.identity)

    def test_execution_environment_amendment_cannot_change_during_resume(self):
        manifest = self.pause_after(1)
        original_raw = (self.directory / "generations.jsonl").read_bytes()
        self.environment["environment_id"] = "changed-baseline"
        self.assertEqual(self.invoke("--resume"), 1)
        self.assertIn("execution_environment", self.last_error)
        self.assertEqual(len(self.client.calls), 1)
        self.assertEqual((self.directory / "generations.jsonl").read_bytes(), original_raw)
        self.assertEqual(self.manifest()["execution_environment"], manifest["execution_environment"])

    def test_dry_run_does_not_contact_service_or_create_destination(self):
        with patch.object(runner, "PilotClient", side_effect=AssertionError("service contacted")):
            self.assertEqual(self.invoke("--dry-run"), 0, self.last_error)
        summary = json.loads(self.last_output)
        self.assertEqual(summary["planned_new_calls"], 840)
        self.assertFalse(summary["service_contacted"])
        self.assertFalse(self.directory.exists())

    def test_source_drift_check_fails_before_health_or_inference(self):
        plan = runner.load_plan()
        plan.update({key: self.reference[key] for key in ("model_digest", "ollama_version", "hardware_snapshot")})
        plan["source_sha256"][str(self.reference_file)] = "0" * 64
        with patch.object(self.client, "health", side_effect=AssertionError("health must follow source check")):
            with self.assertRaisesRegex(ValueError, "Frozen source/input changed"):
                runner.verify_runtime(self.client, plan)
        self.assertEqual(self.client.calls, [])


class ConfirmationTransportTests(unittest.TestCase):
    def test_initial_and_revision_transport_use_selected_schema_and_fixed_options(self):
        client = PilotClient(timeout=10)
        with patch.object(client, "_request", return_value=response()) as request:
            for system in (runner.SYSTEM, runner.REVISION_SYSTEM):
                messages = [{"role": "system", "content": system}, {"role": "user", "content": "question"}]
                client.chat("llama3.2:3b", messages, seed=19, temperature=0.7,
                            max_tokens=1024, format_value=runner.STRICT_SCHEMA)
                endpoint, payload = request.call_args.args
                self.assertEqual(endpoint, "/api/chat")
                self.assertEqual(payload["messages"], messages)
                self.assertEqual(payload["format"], runner.STRICT_SCHEMA)
                self.assertEqual(payload["options"], {"seed": 19, "temperature": 0.7,
                                                       "num_predict": 1024, "num_ctx": 16384})
                self.assertEqual(payload["keep_alive"], 0)
                self.assertFalse(payload["stream"])
            self.assertEqual(request.call_count, 2)
            with self.assertRaises(ValueError):
                client.chat("llama3.2:3b", messages, seed=19, temperature=0.7,
                            max_tokens=2048, format_value=runner.STRICT_SCHEMA)
            self.assertEqual(request.call_count, 2)
        with patch.object(client, "_request", side_effect=OllamaError("fixture failure")) as request:
            with self.assertRaisesRegex(OllamaError, "fixture failure"):
                client.chat("llama3.2:3b", messages, seed=19, temperature=0.7,
                            max_tokens=1024, format_value=runner.STRICT_SCHEMA)
            self.assertEqual(request.call_count, 1)


if __name__ == "__main__":
    unittest.main()
