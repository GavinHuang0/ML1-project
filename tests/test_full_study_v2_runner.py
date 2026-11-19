"""Mocked durable three-phase integration; no model service is contacted."""

from contextlib import ExitStack, redirect_stderr, redirect_stdout
from collections import Counter
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from experiments.full_study_v2 import runner, protocol
from experiment_runtime import FileLock


def raw_response(expression="0", *, truncated=False):
    content = json.dumps({"explanation": "Use the original quantities in this expression.",
                          "expression": expression})
    return {"model": "llama3.2:3b", "done": True,
            "done_reason": "length" if truncated else "stop",
            "message": {"role": "assistant", "content": '{"explanation":"unfinished' if truncated else content},
            "prompt_eval_count": 100, "eval_count": 1024 if truncated else 30,
            "load_duration": 1000000, "total_duration": 10000000}


class FixtureClient:
    def __init__(self, owner):
        self.owner = owner
        self.calls = []
        self.version = "fixture-runtime"
        self.digest = "fixture-model-digest"
        self.pause_after = None
        self.next_response = None
        self.phase_gate_observations = []

    def health(self):
        return {"version": self.version,
                "models": [{"name": "llama3.2:3b", "digest": self.digest}]}

    def chat(self, model, messages, **options):
        initial = messages[0]["content"] == protocol.SYSTEM
        question = messages[1]["content"] if initial else json.loads(messages[1]["content"])["original_question"]
        task = self.owner.by_prompt[question]
        phase = task["split"]
        if phase in ("validation", "test"):
            calibration = self.owner.directory / "artifacts/calibration.json"
            if not calibration.exists():
                raise AssertionError("Validation generation occurred before calibration was frozen")
        if phase == "test":
            selection = self.owner.directory / "artifacts/selection.json"
            if not selection.exists():
                raise AssertionError("Test generation occurred before validation selection was frozen")
            chosen = json.loads(selection.read_text(encoding="utf-8"))
            self.phase_gate_observations.append(chosen["primary_round"])
        self.calls.append({"phase": phase, "messages": copy.deepcopy(messages), **copy.deepcopy(options)})
        value = self.next_response
        self.next_response = None
        if self.pause_after == len(self.calls):
            (self.owner.directory / ".pause-request").touch()
        return value if value is not None else raw_response("0" if initial else task["parameters"]["reference_expression"])


class FullStudyV2RunnerTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.base = Path(self.stack.enter_context(tempfile.TemporaryDirectory())).resolve()
        self.output_root = self.base / "full-experiment"
        self.directory = self.output_root / "study-v2"
        self.hardware = {"fixture": "same-pc-driver"}
        self.reference_file = self.base / "profile-reference.txt"
        self.reference_file.write_bytes(b"immutable selected profile fixture\n")
        self.reference = {"directory": str(self.base), "evidence_sha256": {
            str(self.reference_file): runner.digest(self.reference_file.read_bytes())},
            "profile": "strict_schema", "audit": "fixture-audited", "reused_answers": 0,
            "model_digest": "fixture-model-digest", "ollama_version": "fixture-runtime",
            "hardware_snapshot": copy.deepcopy(self.hardware), "source_sha256": {}}
        self.environment = {"environment_id": "fixture-driver", "hardware_snapshot": copy.deepcopy(self.hardware)}
        all_tasks = protocol.load_tasks()
        self.tasks = [next(task for task in all_tasks if task["split"] == phase and task["family"] == family)
                      for phase in protocol.PHASES for family in protocol.FAMILIES]
        self.by_prompt = {task["prompt"]: task for task in self.tasks}
        self.client = FixtureClient(self)
        self.stack.enter_context(patch.object(runner, "OUTPUT_ROOT", self.output_root))
        self.stack.enter_context(patch.object(runner, "INFERENCE_LOCK", self.base / "inference.lock"))
        self.stack.enter_context(patch.object(runner, "load_reference", side_effect=lambda: copy.deepcopy(self.reference)))
        self.stack.enter_context(patch.object(runner, "load_environment", side_effect=lambda ref: copy.deepcopy(self.environment)))
        self.stack.enter_context(patch.object(runner, "hardware_identity", side_effect=lambda: copy.deepcopy(self.hardware)))
        self.stack.enter_context(patch.object(runner, "PilotClient", return_value=self.client))
        self.original_load_plan = runner.load_plan
        self.stack.enter_context(patch.object(runner, "load_plan", side_effect=self.fixture_plan))

    def fixture_plan(self, *args, **kwargs):
        plan = self.original_load_plan(*args, **kwargs)
        plan["tasks_snapshot"] = copy.deepcopy(self.tasks)
        plan["cohort"] = protocol.cohort_metadata(self.tasks)
        plan["planned_calls"] = {phase: 140 for phase in protocol.PHASES}
        plan["planned_calls"]["total"] = 420
        return plan

    def invoke(self, *arguments):
        output, error = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(error):
            code = runner.main(["--output-dir", str(self.directory), *arguments])
        self.last_output, self.last_error = output.getvalue(), error.getvalue()
        return code

    def phase_directory(self, phase="development"):
        return self.directory / "phases" / phase

    def phase_manifest(self, phase="development"):
        return json.loads((self.phase_directory(phase) / "run-manifest.json").read_text(encoding="utf-8"))

    def phase_records(self, name, phase="development"):
        return runner.journal_records(self.phase_directory(phase) / name)[0]

    def test_three_phase_lifecycle_pause_resume_freezes_artifacts_and_reproduces_reports(self):
        self.client.pause_after = 3
        self.assertEqual(self.invoke("--phase", "all"), 2, self.last_error)
        prefix = (self.phase_directory() / "generations.jsonl").read_bytes()
        self.assertEqual(len(self.client.calls), 3)
        self.client.pause_after = None
        self.assertEqual(self.invoke("--phase", "all", "--resume"), 0, self.last_error)
        self.assertEqual(len(self.client.calls), 420)
        self.assertEqual(Counter(row["phase"] for row in self.client.calls),
                         {phase: 140 for phase in protocol.PHASES})
        self.assertTrue((self.phase_directory() / "generations.jsonl").read_bytes().startswith(prefix))
        self.assertIn("ETA", self.last_output)
        calibration = json.loads((self.directory / "artifacts/calibration.json").read_text(encoding="utf-8"))
        selection = json.loads((self.directory / "artifacts/selection.json").read_text(encoding="utf-8"))
        self.assertEqual(calibration["source_phase"], "development")
        self.assertEqual(selection["source_phase"], "validation")
        self.assertEqual(selection["primary_round"], 1)
        self.assertEqual(set(self.client.phase_gate_observations), {1})
        for phase in protocol.PHASES:
            summary = json.loads((self.phase_directory(phase) / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["comparison_rows"], 8)
            self.assertEqual(summary["per_question_rows"], 32)
            self.assertEqual(summary["source_generation_cost_including_initial_once"]["unique_calls"], 140)
        test_summary = json.loads((self.phase_directory("test") / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(test_summary["primary_round"], 1)
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(runner.main(["--analyze-run", str(self.directory)]), 0)
        self.assertEqual(len(self.client.calls), 420)

    def test_later_phases_cannot_generate_without_prior_frozen_artifacts(self):
        for phase in ("validation", "test"):
            self.assertEqual(self.invoke("--phase", phase), 1)
            self.assertEqual(self.client.calls, [])

    def test_calibration_tamper_blocks_validation_without_more_calls(self):
        self.assertEqual(self.invoke("--phase", "development"), 0, self.last_error)
        path = self.directory / "artifacts/calibration.json"
        artifact = json.loads(path.read_text(encoding="utf-8"))
        artifact["references"]["token_reference"] += 1
        path.write_text(json.dumps(artifact) + "\n", encoding="utf-8")
        self.assertEqual(self.invoke("--phase", "validation", "--resume"), 1)
        self.assertEqual(len(self.client.calls), 140)

    def test_selection_tamper_blocks_test_without_more_calls(self):
        self.assertEqual(self.invoke("--phase", "development"), 0, self.last_error)
        self.assertEqual(self.invoke("--phase", "validation", "--resume"), 0, self.last_error)
        path = self.directory / "artifacts/selection.json"
        artifact = json.loads(path.read_text(encoding="utf-8"))
        artifact["primary_round"] = 3
        path.write_text(json.dumps(artifact) + "\n", encoding="utf-8")
        self.assertEqual(self.invoke("--phase", "test", "--resume"), 1)
        self.assertEqual(len(self.client.calls), 280)

    def test_missing_calibration_recovery_is_deterministic_but_audit_stays_read_only(self):
        self.assertEqual(self.invoke("--phase", "development"), 0, self.last_error)
        path = self.directory / "artifacts/calibration.json"
        original = path.read_bytes()
        path.unlink()
        # Simulate a crash after phase completion but before the parent
        # checkpoint records/installs its deterministic derived artifact.
        state = json.loads((self.directory / "study-manifest.json").read_text(encoding="utf-8"))
        state["artifact_sha256"].pop("calibration.json")
        runner.save_study(self.directory, state)
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(runner.main(["--analyze-run", str(self.directory)]), 0)
        self.assertFalse(path.exists(), "Read-only analysis must not recreate missing artifacts")
        self.assertEqual(self.invoke("--phase", "development", "--resume"), 0, self.last_error)
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(len(self.client.calls), 140)

    def test_preview_is_offline_and_refuses_legacy_study_folder(self):
        with patch.object(runner, "PilotClient", side_effect=AssertionError("No service in dry run")):
            self.assertEqual(self.invoke("--dry-run", "--phase", "all"), 0, self.last_error)
        self.assertFalse(self.directory.exists())
        self.assertEqual(self.client.calls, [])
        self.directory.mkdir(parents=True)
        (self.directory / "study-manifest.json").write_text(json.dumps({"study_id": "ml1-full-study-v1"}))
        self.assertEqual(self.invoke("--resume", "--phase", "all"), 1)
        self.assertEqual(self.client.calls, [])

    def test_runtime_and_hardware_drift_block_new_inference(self):
        for attribute, bad in (("digest", "new-model"), ("version", "new-runtime")):
            original = getattr(self.client, attribute)
            setattr(self.client, attribute, bad)
            self.assertEqual(self.invoke("--phase", "development"), 1)
            self.assertEqual(self.client.calls, [])
            setattr(self.client, attribute, original)
        self.client.pause_after = 1
        self.assertEqual(self.invoke("--phase", "development"), 2, self.last_error)
        with patch.object(runner, "hardware_identity", return_value={"fixture": "different-driver"}):
            self.assertEqual(self.invoke("--phase", "development", "--resume"), 1)
        self.assertEqual(len(self.client.calls), 1)

    def test_output_source_drift_and_global_lock_are_rejected(self):
        with FileLock(runner.INFERENCE_LOCK):
            self.assertEqual(self.invoke("--phase", "development"), 1)
            self.assertEqual(self.client.calls, [])
        self.client.pause_after = 1
        self.assertEqual(self.invoke("--phase", "development"), 2, self.last_error)
        self.reference_file.write_bytes(b"changed selected-profile evidence\n")
        self.assertEqual(self.invoke("--phase", "development", "--resume"), 1)
        self.assertEqual(len(self.client.calls), 1)

    def test_durable_phase_raw_orphan_is_evaluated_without_regeneration(self):
        self.client.pause_after = 1
        self.assertEqual(self.invoke("--phase", "development"), 2, self.last_error)
        phase_directory = self.phase_directory()
        raw_prefix = (phase_directory / "generations.jsonl").read_bytes()
        (phase_directory / "answers.jsonl").write_bytes(b"")
        phase_state = self.phase_manifest()
        phase_state["status"] = "interrupted"
        runner.checkpoint(phase_directory, phase_state)
        study_state = json.loads((self.directory / "study-manifest.json").read_text(encoding="utf-8"))
        runner.sync_phase(self.directory, study_state, "development", phase_directory, phase_state)
        self.client.pause_after = 2
        self.assertEqual(self.invoke("--phase", "development", "--resume"), 2, self.last_error)
        self.assertEqual(len(self.client.calls), 2)
        self.assertEqual(len(self.phase_records("answers.jsonl")), 2)
        self.assertTrue((phase_directory / "generations.jsonl").read_bytes().startswith(raw_prefix))

    def test_initial_cap_failure_is_admitted_and_other_schema_failure_preserves_raw_without_retry(self):
        self.client.pause_after = 1
        self.client.next_response = raw_response(truncated=True)
        self.assertEqual(self.invoke("--phase", "development"), 2, self.last_error)
        row = self.phase_records("answers.jsonl")[0]
        self.assertTrue(row["output_truncation_failure"])
        self.assertEqual(row["arm"], "shared_initial")
        self.assertFalse(row["response"]["eligible"])
        self.client.pause_after = None
        self.client.next_response = raw_response("x=2")
        self.assertEqual(self.invoke("--phase", "development", "--resume"), 1)
        phase_state = self.phase_manifest()
        self.assertEqual((phase_state["generations_saved"], phase_state["calls_completed"]), (2, 1))
        original = (self.phase_directory() / "generations.jsonl").read_bytes()
        self.assertEqual(self.invoke("--phase", "development", "--resume"), 1)
        self.assertEqual(len(self.client.calls), 2)
        self.assertEqual((self.phase_directory() / "generations.jsonl").read_bytes(), original)

    def test_premature_artifact_hash_cannot_be_recorded_before_its_source_phase(self):
        self.client.pause_after = 1
        self.assertEqual(self.invoke("--phase", "development"), 2, self.last_error)
        state = json.loads((self.directory / "study-manifest.json").read_text(encoding="utf-8"))
        state["artifact_sha256"]["calibration.json"] = "0" * 64
        runner.save_study(self.directory, state)
        self.client.pause_after = 2
        self.assertEqual(self.invoke("--phase", "development", "--resume"), 1)
        self.assertIn("artifact", self.last_error.lower())
        self.assertEqual(len(self.client.calls), 1)


if __name__ == "__main__":
    unittest.main()
