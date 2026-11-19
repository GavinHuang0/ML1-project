"""Mocked durable integration for both separate architecture experiments."""

from contextlib import ExitStack, redirect_stderr, redirect_stdout
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from experiments.architecture_pilots import runner
from experiment_runtime import FileLock
from tests.test_confirmation_runner import FixtureClient, response


class ArchitectureRunnerTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.base = Path(self.stack.enter_context(tempfile.TemporaryDirectory())).resolve()
        self.roots = {name: self.base / name for name in runner.EXPECTED_CONFIGS}
        self.directories = {name: root / "fixture-v1" for name, root in self.roots.items()}
        self.clients = {name: FixtureClient(path) for name, path in self.directories.items()}
        self.reference_file = self.base / "profile-reference.txt"
        self.reference_file.write_bytes(b"immutable selected profile fixture\n")
        self.hardware = {"fixture": "same-driver"}
        self.reference = {
            "directory": str(self.base), "evidence_sha256": {
                str(self.reference_file): runner.digest(self.reference_file.read_bytes())},
            "audit": "fixture-audited", "profile": "strict_schema", "reused_answers": 0,
            "model_digest": "fixture-model-digest", "ollama_version": "fixture-runtime",
            "hardware_snapshot": copy.deepcopy(self.hardware), "source_sha256": {},
        }
        self.environment = {"environment_id": "fixture-current-driver", "hardware_snapshot": copy.deepcopy(self.hardware)}
        self.active_preset = "five_agent"
        self.stack.enter_context(patch.object(runner, "OUTPUT_ROOTS", self.roots))
        self.stack.enter_context(patch.object(runner, "INFERENCE_LOCK", self.base / "inference.lock"))
        self.stack.enter_context(patch.object(runner, "load_reference", side_effect=lambda: copy.deepcopy(self.reference)))
        self.stack.enter_context(patch.object(runner, "load_environment", side_effect=lambda reference: copy.deepcopy(self.environment)))
        self.stack.enter_context(patch.object(runner, "hardware_identity", side_effect=lambda: copy.deepcopy(self.hardware)))
        self.stack.enter_context(patch.object(runner, "PilotClient", side_effect=lambda **options: self.clients[self.active_preset]))

    def invoke(self, preset="five_agent", *arguments, directory=None):
        self.active_preset = preset
        output, error = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(error):
            code = runner.main(["--output-dir", str(directory or self.directories[preset]), *arguments], preset=preset)
        self.last_output, self.last_error = output.getvalue(), error.getvalue()
        return code

    def manifest(self, preset="five_agent"):
        return json.loads((self.directories[preset] / "run-manifest.json").read_text(encoding="utf-8"))

    def records(self, name, preset="five_agent"):
        return runner.journal_records(self.directories[preset] / name)[0]

    def pause_after(self, count=1, preset="five_agent"):
        self.clients[preset].stop_after = count
        self.assertEqual(self.invoke(preset), 2, self.last_error)
        manifest = self.manifest(preset)
        self.assertEqual(manifest["status"], "paused")
        self.assertEqual(manifest["calls_completed"], count)
        return manifest

    def test_both_full_mock_runs_resume_without_repetition_and_reproduce_actual_reports(self):
        for preset, total, initial, degree in (("five_agent", 420, 60, 4), ("sparse_peer", 840, 120, 2)):
            with self.subTest(preset=preset):
                self.pause_after(3, preset)
                prefix = (self.directories[preset] / "generations.jsonl").read_bytes()
                self.clients[preset].stop_after = None
                self.assertEqual(self.invoke(preset, "--resume"), 0, self.last_error)
                self.assertEqual(len(self.clients[preset].calls), total)
                manifest = self.manifest(preset)
                self.assertEqual(manifest["status"], "complete")
                self.assertEqual((manifest["generations_saved"], manifest["calls_completed"]), (total, total))
                self.assertTrue((self.directories[preset] / "generations.jsonl").read_bytes().startswith(prefix))
                records = self.records("answers.jsonl", preset)
                self.assertEqual(sum(row["round"] == 0 for row in records), initial)
                for record in records:
                    if record["arm"] == "communication":
                        payload = json.loads(record["messages"][1]["content"])
                        self.assertEqual(len(payload["peers"]), degree)
                        self.assertEqual(len(record["peer_ids"]), degree)
                    elif record["arm"] == "self_revision":
                        self.assertNotIn("peers", json.loads(record["messages"][1]["content"]))
                summary = json.loads((self.directories[preset] / "summary.json").read_text(encoding="utf-8"))
                self.assertEqual(len(summary["comparisons"]), 8)
                self.assertEqual(len(summary["per_question"]), 96)
                audit = runner.analyze_run(self.directories[preset], preset)
                self.assertTrue(audit["summary_reproduced"])
                self.assertEqual(audit["analysis_model_calls"], 0)
                self.assertEqual(self.invoke(preset, "--resume"), 1)
                self.assertIn("already complete", self.last_error)
                self.assertEqual(len(self.clients[preset].calls), total)
        path = self.directories["five_agent"] / "comparisons.csv"
        path.write_bytes(path.read_bytes() + b"tamper\n")
        with self.assertRaisesRegex(ValueError, "Saved report differs"):
            runner.analyze_run(self.directories["five_agent"], "five_agent")

    def test_sparse_routing_and_payload_tamper_rejected_after_rehash(self):
        preset = "sparse_peer"
        # All120 initial, one self revision, then the first communication call.
        manifest = self.pause_after(122, preset)
        for name in runner.JOURNALS:
            records = self.records(name, preset)
            target = records[-1]
            self.assertEqual(target["arm"], "communication")
            target["peer_ids"] = list(reversed(target["peer_ids"]))
            payload = json.loads(target["messages"][1]["content"])
            payload["peers"] = list(reversed(payload["peers"]))
            target["messages"][1]["content"] = json.dumps(payload)
            (self.directories[preset] / name).write_text(
                "".join(json.dumps(row) + "\n" for row in records), encoding="utf-8", newline="\n")
        runner.checkpoint(self.directories[preset], manifest)
        self.assertEqual(self.invoke(preset, "--resume"), 1)
        self.assertIn("canonical prompt/position/routing", self.last_error)
        self.assertEqual(len(self.clients[preset].calls), 122)

    def test_cross_preset_resume_cannot_adopt_other_experiment_evidence(self):
        manifest = self.pause_after()
        other = runner.load_plan("sparse_peer")
        with self.assertRaisesRegex(ValueError, "Resume snapshot/protocol differs"):
            runner.audit_resume(self.directories["five_agent"], manifest, other)
        with self.assertRaisesRegex(ValueError, "Output must be"):
            runner.analyze_run(self.directories["five_agent"], "sparse_peer")
        self.assertEqual(len(self.clients["five_agent"].calls), 1)
        self.assertEqual(self.clients["sparse_peer"].calls, [])

    def test_global_lock_prevents_interleaved_inference_between_presets(self):
        with FileLock(runner.INFERENCE_LOCK):
            for preset in self.clients:
                self.assertEqual(self.invoke(preset), 1)
                self.assertIn("Another process holds", self.last_error)
                self.assertFalse(self.directories[preset].exists())
                self.assertEqual(self.clients[preset].calls, [])

    def test_durable_raw_orphan_is_evaluated_without_regeneration(self):
        manifest = self.pause_after()
        prefix = (self.directories["five_agent"] / "generations.jsonl").read_bytes()
        (self.directories["five_agent"] / "answers.jsonl").write_bytes(b"")
        manifest["status"] = "interrupted"
        runner.checkpoint(self.directories["five_agent"], manifest)
        self.clients["five_agent"].stop_after = 2
        self.assertEqual(self.invoke("five_agent", "--resume"), 2, self.last_error)
        self.assertEqual(len(self.clients["five_agent"].calls), 2)
        self.assertEqual(len(self.records("answers.jsonl")), 2)
        self.assertTrue((self.directories["five_agent"] / "generations.jsonl").read_bytes().startswith(prefix))

    def test_truncated_initial_is_ineligible_without_retry_other_schema_failure_stays_fatal(self):
        client = self.clients["five_agent"]
        client.next_response = response('{"explanation":"unfinished', truncated=True)
        self.pause_after()
        record = self.records("answers.jsonl")[0]
        self.assertTrue(record["output_truncation_failure"])
        self.assertFalse(record["response"]["eligible"])
        self.assertEqual(record["arm"], "shared_initial")
        client.stop_after = None
        client.next_response = response('{"explanation":"Bad schema","expression":"x=2"}')
        self.assertEqual(self.invoke("five_agent", "--resume"), 1)
        self.assertEqual(self.manifest()["status"], "failed")
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(self.manifest()["generations_saved"], 2)
        self.assertEqual(self.manifest()["calls_completed"], 1)
        self.assertEqual(self.invoke("five_agent", "--resume"), 1)
        self.assertEqual(len(client.calls), 2)

    def test_source_drift_blocks_resume_before_new_generation(self):
        self.pause_after()
        original = (self.directories["five_agent"] / "generations.jsonl").read_bytes()
        self.reference_file.write_bytes(b"changed profile evidence\n")
        self.assertEqual(self.invoke("five_agent", "--resume"), 1)
        self.assertIn("source_sha256", self.last_error)
        self.assertEqual(len(self.clients["five_agent"].calls), 1)
        self.assertEqual((self.directories["five_agent"] / "generations.jsonl").read_bytes(), original)

    def test_model_driver_and_runtime_drift_block_inference(self):
        client = self.clients["five_agent"]
        for attribute, bad, good in (("digest", "new-model", client.digest),
                                     ("version", "new-runtime", client.version)):
            setattr(client, attribute, bad)
            self.assertEqual(self.invoke(), 1)
            self.assertFalse(self.directories["five_agent"].exists())
            self.assertEqual(client.calls, [])
            setattr(client, attribute, good)
        self.pause_after()
        with patch.object(runner, "hardware_identity", return_value={"fixture": "updated-driver"}):
            self.assertEqual(self.invoke("five_agent", "--resume"), 1)
        self.assertIn("Hardware differs", self.last_error)
        self.assertEqual(len(client.calls), 1)

    def test_both_previews_do_not_contact_service_or_create_run(self):
        with patch.object(runner, "PilotClient", side_effect=AssertionError("No service in dry run")):
            for preset, calls in (("five_agent", 420), ("sparse_peer", 840)):
                self.assertEqual(self.invoke(preset, "--dry-run"), 0, self.last_error)
                preview = json.loads(self.last_output)
                self.assertEqual(preview["planned_new_calls"], calls)
                self.assertFalse(preview["service_contacted"])
                self.assertFalse(self.directories[preset].exists())


if __name__ == "__main__":
    unittest.main()
