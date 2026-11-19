"""Offline integration checks for checkpointing and the three-phase study lifecycle."""

from contextlib import redirect_stderr, redirect_stdout
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from experiment_runtime import PauseController

from experiments.full_study_v1 import runner as study
import run_multi_agent as primary
from experiments.full_study_v1 import run_self_revision as control, study_trajectory


class FixtureClient:
    calls = []
    failure_at = None

    def __init__(self, **kwargs):
        pass

    def health(self):
        return {"version": "study-fixture", "models": [{"name": primary.MODEL, "digest": "study-digest"}]}

    def chat(self, model, messages, **options):
        if self.failure_at is not None and len(self.calls) == self.failure_at:
            raise primary.OllamaError("Temporary fixture outage")
        self.calls.append((copy.deepcopy(messages), dict(options)))
        return {"model": model, "done": True, "done_reason": "stop", "prompt_eval_count": 80,
                "eval_count": 25, "load_duration": 1000000, "total_duration": 10000000,
                "message": {"content": '{"explanation":"A valid fixture setup.","expression":"1/2"}'}}


class FullStudyRunnerTests(unittest.TestCase):
    def setUp(self):
        FixtureClient.calls, FixtureClient.failure_at = [], None
        self.tasks = [{"id": f"study-{split}", "family": "reasoning", "split": split,
                       "group_id": f"group-{split}", "prompt": "What is one half?",
                       "probability": True, "gold_fraction": "1/2"} for split in study.PHASES]

    def fixture(self, root):
        config = {"schema_version": 1, "study_id": study.STUDY_ID, "design": study.FROZEN_DESIGN,
                  "base_config": "multi_agent.json", "task_manifest": "fixture.json"}
        path = root / "fixture.json"
        path.write_text(json.dumps({"schema_version": 1, "source": {"kind": "test-only"}, "tasks": self.tasks}))
        return config, "config-fixture", primary.CONFIG_PATH, path, self.tasks, "benchmark-fixture", "base-fixture"

    def invoke(self, arguments, inputs):
        output, errors = io.StringIO(), io.StringIO()
        with patch.object(study, "read_study", return_value=inputs), \
                patch.object(study, "sources", return_value={"fixture": "unchanged"}), \
                patch.object(study, "verify_input_hashes"), \
                patch.object(study, "hardware_identity", return_value={"fixture": "same-machine"}), \
                patch.object(primary, "OllamaClient", FixtureClient), \
                patch.object(study_trajectory, "OllamaClient", FixtureClient), \
                patch.object(control, "OllamaClient", FixtureClient), \
                redirect_stdout(output), redirect_stderr(errors):
            code = study.main(arguments)
        return code, output.getvalue(), errors.getvalue()

    def test_dry_run_is_offline_and_plans_shared_initial_calls(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            destination = root / "study"
            inputs = self.fixture(root)
            code, output, errors = self.invoke(["--dry-run", "--phase", "all", "--output-dir", str(destination)], inputs)
            self.assertEqual(code, 0, errors)
            plan = json.loads(output)
            self.assertEqual(plan["total_new_calls"], 210)
            self.assertFalse(destination.exists())
            self.assertEqual(FixtureClient.calls, [])

    def test_full_lifecycle_freezes_global_references_and_reuses_completed_questions(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inputs, destination = self.fixture(root), root / "study"
            code, _, error = self.invoke(["--phase", "all", "--output-dir", str(destination)], inputs)
            self.assertEqual(code, 0, error)
            self.assertEqual(len(FixtureClient.calls), 210)
            state = json.loads((destination / "study-manifest.json").read_text())
            self.assertEqual(state["status"], "complete")
            self.assertEqual(set(state["phases"]), set(study.PHASES))
            calibration = json.loads((destination / "artifacts/calibration.json").read_text())
            self.assertEqual(calibration["references"]["source_question_ids"], ["study-development"])
            self.assertEqual(calibration["references"]["source_group_ids"], ["group-development"])
            selection = json.loads((destination / "artifacts/selection.json").read_text())
            self.assertEqual(selection["validation_question_ids"], ["study-validation"])
            self.assertEqual(selection["primary_round"], 0)
            for split in study.PHASES:
                report = json.loads((destination / "reports" / (split + ".json")).read_text())
                self.assertEqual(report["control"]["selected_rounds"], {})
            code, _, error = self.invoke(["--phase", "all", "--resume", "--output-dir", str(destination)], inputs)
            self.assertEqual(code, 0, error)
            self.assertEqual(len(FixtureClient.calls), 210)

    def test_failed_control_preserves_primary_and_resumes_only_pending_calls(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inputs, destination = self.fixture(root), root / "study"
            FixtureClient.failure_at = 43
            code, _, _ = self.invoke(["--phase", "development", "--output-dir", str(destination)], inputs)
            self.assertEqual(code, 1)
            state = json.loads((destination / "study-manifest.json").read_text())
            attempts = state["children"]["study-development"]
            self.assertEqual(attempts["all_to_all"][0]["status"], "complete")
            self.assertEqual(attempts["self_revision"][0]["status"], "failed")
            FixtureClient.failure_at = None
            code, _, error = self.invoke(["--phase", "development", "--resume", "--output-dir", str(destination)], inputs)
            self.assertEqual(code, 0, error)
            self.assertEqual(len(FixtureClient.calls), 70)
            state = json.loads((destination / "study-manifest.json").read_text())
            self.assertEqual(len(state["children"]["study-development"]["all_to_all"]), 1)
            self.assertEqual(len(state["children"]["study-development"]["self_revision"]), 1)
            report = json.loads((destination / "reports/development.json").read_text())
            self.assertEqual(report["execution_overhead"]["completed_generations"], 0)

    def test_requested_pause_saves_current_call_and_resumes_without_repeating_it(self):
        enabled = True
        class AutoPause(PauseController):
            def requested(self):
                return super().requested() or (enabled and len(FixtureClient.calls) >= 3)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inputs, destination = self.fixture(root), root / "study"
            with patch.object(study, "PauseController", AutoPause):
                code, _, error = self.invoke(["--phase", "development", "--output-dir", str(destination)], inputs)
                self.assertEqual(code, 2, error)
                state = json.loads((destination / "study-manifest.json").read_text())
                self.assertEqual(state["status"], "paused")
                self.assertEqual(len(FixtureClient.calls), 3)
                enabled = False
                code, _, error = self.invoke(["--phase", "development", "--resume", "--output-dir", str(destination)], inputs)
                self.assertEqual(code, 0, error)
            self.assertEqual(len(FixtureClient.calls), 70)

    def test_resume_refuses_hardware_change_without_overwriting_original_manifest(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inputs, destination = self.fixture(root), root / "study"
            code, _, error = self.invoke(["--phase", "development", "--output-dir", str(destination)], inputs)
            self.assertEqual(code, 0, error)
            path = destination / "study-manifest.json"
            before = path.read_bytes()
            with patch.object(study, "verify_frozen", side_effect=ValueError("Hardware changed")):
                code, _, error = self.invoke(["--phase", "validation", "--resume", "--output-dir", str(destination)], inputs)
            self.assertEqual(code, 1)
            self.assertIn("Hardware changed", error)
            self.assertEqual(path.read_bytes(), before)

    def test_validation_cannot_run_before_development_and_existing_root_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inputs, destination = self.fixture(root), root / "study"
            code, _, error = self.invoke(["--phase", "validation", "--output-dir", str(destination)], inputs)
            self.assertEqual(code, 1)
            self.assertIn("development", error)
            self.assertEqual(FixtureClient.calls, [])
            before = (destination / "study-manifest.json").read_bytes()
            code, _, _ = self.invoke(["--phase", "development", "--output-dir", str(destination)], inputs)
            self.assertEqual(code, 1)
            self.assertEqual((destination / "study-manifest.json").read_bytes(), before)

    def test_changed_input_snapshot_and_reformatted_calibration_are_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.json"
            source.write_text('{"version":1}')
            digest = primary.digest_bytes(source.read_bytes())
            mapping = {str(source.resolve()): digest}
            study.verify_input_hashes(source, digest, source, digest, source, digest, mapping)
            source.write_text('{"version":2}')
            with self.assertRaisesRegex(ValueError, "changed"):
                study.verify_input_hashes(source, digest, source, digest, source, digest, mapping)
            inputs, destination = self.fixture(root), root / "study"
            code, _, error = self.invoke(["--phase", "development", "--output-dir", str(destination)], inputs)
            self.assertEqual(code, 0, error)
            path = destination / "artifacts/calibration.json"
            path.write_text(json.dumps(json.loads(path.read_text()), separators=(",", ":")))
            count = len(FixtureClient.calls)
            code, _, error = self.invoke(["--phase", "development", "--resume", "--output-dir", str(destination)], inputs)
            self.assertEqual(code, 1)
            self.assertIn("calibration changed", error)
            self.assertEqual(len(FixtureClient.calls), count)


if __name__ == "__main__":
    unittest.main()
