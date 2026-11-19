"""Preserved evidence and local model backup verification; no inference."""

from contextlib import redirect_stderr, redirect_stdout
import csv
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import archive_project_history as history


class ProjectArchiveTests(unittest.TestCase):
    def test_experiment_snapshots_match_every_recorded_byte(self):
        reports = [history.check_inventory(history.ROOT / name) for name in history.EXPERIMENT_ARCHIVES]
        self.assertEqual([item["files_verified"] for item in reports], [39, 74, 69, 27, 33, 12, 15, 22])

    def test_completed_architecture_runs_preserve_every_call_route_and_frozen_input(self):
        archive = history.ROOT / "archive/2026-11-18-architecture-pilots-v1"
        inventory = json.loads((archive / "SHA256_INVENTORY.json").read_text(encoding="utf-8"))
        self.assertEqual((inventory["file_count"], inventory["total_bytes"]), (22, 12841694))
        self.assertEqual((inventory["unique_generations"], inventory["shared_initial_generations"],
                          inventory["revision_generations"]), (1260, 180, 1080))
        self.assertEqual((len(inventory["source_inputs"]), len(inventory["referenced_sources"])), (52, 42))
        inputs = {entry["original_absolute_path"]: entry for entry in inventory["source_inputs"]}
        for run_name, agents, peers, calls in (("five-agent-pilot", 5, 4, 420),
                                             ("sparse-peer-pilot", 10, 2, 840)):
            run = archive / "results" / run_name / "windows-v1"
            manifest = json.loads((run / "run-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "complete")
            self.assertEqual((manifest["calls_completed"], manifest["generations_saved"]), (calls, calls))
            self.assertEqual(manifest["configuration_snapshot"]["num_agents"], agents)
            self.assertEqual(manifest["configuration_snapshot"]["peer_count"], peers)
            self.assertEqual(set(inputs), set(manifest["source_sha256"]))
            for original, digest in manifest["source_sha256"].items():
                self.assertEqual(inputs[original]["sha256"], digest)
                preserved = history.safe_member(history.ROOT, inputs[original]["workspace_archive_path"])
                self.assertEqual(history.sha256(preserved), digest)
            for filename, checkpoint in manifest["evidence_checkpoint"].items():
                self.assertEqual(history.sha256(run / filename), checkpoint["sha256"])
                self.assertEqual(len((run / filename).read_bytes().splitlines()), checkpoint["records"])
            answers = [json.loads(line) for line in (run / "answers.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(sum(row["arm"] == "shared_initial" for row in answers), 12 * agents)
            self.assertEqual(sum(row["arm"] == "communication" for row in answers), 36 * agents)
            self.assertEqual(sum(row["arm"] == "self_revision" for row in answers), 36 * agents)
            for answer, position in zip(answers, manifest["call_positions"]):
                self.assertEqual(answer["peer_ids"], position["peer_ids"])
                self.assertEqual(answer["routing_seed"], position["routing_seed"])
                if answer["arm"] == "communication":
                    self.assertEqual(len(set(answer["peer_ids"])), peers)
                    self.assertNotIn(answer["agent_id"], answer["peer_ids"])
            for filename, digest in manifest["output_sha256"].items():
                self.assertEqual(history.sha256(run / filename), digest)
            for filename, count in (("comparisons.csv", 8), ("per_question.csv", 96)):
                with (run / filename).open(encoding="utf-8", newline="") as stream:
                    self.assertEqual(len(list(csv.DictReader(stream))), count)
            summary = json.loads((run / "summary.json").read_text(encoding="utf-8"))
            self.assertFalse(summary["selection_performed"])
            self.assertEqual(summary["source_generation_cost_including_initial_once"]["unique_calls"], calls)
            self.assertEqual(summary["semantic_groups"], 8)

    def test_completed_confirmation_preserves_raw_evidence_and_all_frozen_source_inputs(self):
        archive = history.ROOT / "archive/2026-11-18-confirmation-pilot-v1"
        run = archive / "results/confirmation-pilot/windows-v1"
        manifest = json.loads((run / "run-manifest.json").read_text(encoding="utf-8"))
        inventory = json.loads((archive / "SHA256_INVENTORY.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["status"], "complete")
        self.assertEqual((manifest["generations_saved"], manifest["calls_completed"]), (840, 840))
        self.assertEqual(len(manifest["source_sha256"]), 43)
        self.assertEqual((inventory["file_count"], len(inventory["referenced_sources"])), (15, 34))
        inputs = {entry["original_absolute_path"]: entry for entry in inventory["source_inputs"]}
        self.assertEqual(set(inputs), set(manifest["source_sha256"]))
        for original, digest in manifest["source_sha256"].items():
            self.assertEqual(inputs[original]["sha256"], digest)
            preserved = history.safe_member(history.ROOT, inputs[original]["workspace_archive_path"])
            self.assertEqual(history.sha256(preserved), digest)
        for name, checkpoint in manifest["evidence_checkpoint"].items():
            self.assertEqual(history.sha256(run / name), checkpoint["sha256"])
            self.assertEqual(len((run / name).read_bytes().splitlines()), checkpoint["records"])
        answers = [json.loads(line) for line in (run / "answers.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(sum(row["arm"] == "shared_initial" for row in answers), 120)
        self.assertEqual(sum(row["arm"] == "communication" for row in answers), 360)
        self.assertEqual(sum(row["arm"] == "self_revision" for row in answers), 360)
        self.assertEqual(manifest["hardware_snapshot"], manifest["execution_environment"]["hardware_snapshot"])
        self.assertIn("621.24", manifest["hardware_snapshot"]["nvidia_gpu_and_driver"])
        self.assertTrue(manifest["execution_environment"]["amendment"]["declared_before_confirmation_inference"])
        for name, digest in manifest["output_sha256"].items():
            self.assertEqual(history.sha256(run / name), digest)
        for name, count in (("comparisons.csv", 36), ("per_question.csv", 432)):
            with (run / name).open(encoding="utf-8", newline="") as stream:
                self.assertEqual(len(list(csv.DictReader(stream))), count)
        summary = json.loads((run / "summary.json").read_text(encoding="utf-8"))
        self.assertFalse(summary["selection_performed"])
        self.assertEqual(summary["questions"], 12)
        self.assertEqual(summary["semantic_groups"], 8)

    def test_completed_offline_snapshot_keeps_reports_and_exact_frozen_sources(self):
        archive = history.ROOT / "archive/2026-11-18-offline-policies-v1"
        run = archive / "results/offline-comparison/pilot-v1"
        manifest = json.loads((run / "run-manifest.json").read_text(encoding="utf-8"))
        inventory = json.loads((archive / "SHA256_INVENTORY.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["status"], "complete")
        self.assertEqual(manifest["additional_model_calls"], 0)
        self.assertEqual(manifest["analysis_scope"], "post_hoc_exploratory_eight_development_groups")
        self.assertFalse(manifest["selection_performed"])
        self.assertEqual(len(manifest["source_sha256"]), 8)
        copies = {item["original_absolute_path"]: item for item in inventory["files"]}
        for original, digest in manifest["source_sha256"].items():
            self.assertEqual(copies[original]["sha256"], digest)
            self.assertEqual(history.sha256(archive / copies[original]["archive_path"]), digest)
        for name, digest in manifest["output_sha256"].items():
            self.assertEqual(history.sha256(run / name), digest)
        for name, count in (("comparisons.csv", 36), ("per_question.csv", 288)):
            with (run / name).open(encoding="utf-8", newline="") as stream:
                self.assertEqual(len(list(csv.DictReader(stream))), count)

    def test_completed_recovery_keeps_every_revision_and_the_failed_prefix(self):
        run = history.ROOT / "archive/2026-11-17-communication-recovery-v2/results/communication-pilot/windows-v2"
        failed = history.ROOT / "archive/2026-11-17-communication-pilot-v1-failed/results/communication-pilot/windows-v1"
        manifest = json.loads((run / "run-manifest.json").read_text(encoding="utf-8"))
        summary = json.loads((run / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["status"], "complete")
        self.assertEqual(summary["imported_revision_calls"], 146)
        self.assertEqual(summary["new_calls"], 334)
        self.assertEqual(summary["total_revision_calls"], 480)
        self.assertEqual(summary["physical_unique_model_calls_including_initial"], 560)
        self.assertTrue(summary["protocol_amendment"]["post_failure"])
        self.assertFalse(summary["protocol_amendment"]["generation_protocol_changed"])
        self.assertEqual((run / "initial_panel.jsonl").read_bytes(), (failed / "initial_panel.jsonl").read_bytes())
        for name in ("generations.jsonl", "answers.jsonl"):
            self.assertTrue((run / name).read_bytes().startswith((failed / name).read_bytes()))
            self.assertEqual(len((run / name).read_bytes().splitlines()), 480)
            self.assertEqual(history.sha256(run / name), manifest["evidence_checkpoint"][name]["sha256"])
        answers = [json.loads(line) for line in (run / "answers.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertTrue(answers[145]["output_truncation_failure"])
        self.assertFalse(answers[145]["response"]["eligible"])
        self.assertEqual(answers[145]["response"]["status"], "invalid_json")
        self.assertEqual(history.sha256(run / "summary.json"), manifest["summary_sha256"])
        self.assertEqual(summary["primary_comparison_round"], 3)
        self.assertEqual(summary["primary_comparison"]["metrics"]["collective_accuracy"]["difference"], -0.125)

    def test_failed_snapshot_keeps_truncated_raw_without_inventing_an_answer(self):
        run = history.ROOT / "archive/2026-11-17-communication-pilot-v1-failed/results/communication-pilot/windows-v1"
        manifest = json.loads((run / "run-manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["status"], "failed")
        records = {}
        for name, count in (("initial_panel.jsonl", 80), ("generations.jsonl", 146), ("answers.jsonl", 145)):
            path = run / name
            records[name] = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(records[name]), count)
            self.assertEqual(manifest["evidence_checkpoint"][name]["records"], count)
            self.assertEqual(history.sha256(path), manifest["evidence_checkpoint"][name]["sha256"])
        failed = records["generations.jsonl"][-1]
        self.assertEqual(failed["call_index"], 145)
        self.assertEqual(failed["raw"]["done_reason"], "length")
        self.assertEqual(failed["raw"]["eval_count"], 1024)
        with self.assertRaises(json.JSONDecodeError):
            json.loads(failed["raw"]["message"]["content"])
        self.assertEqual(records["answers.jsonl"][-1]["call_index"], 144)
        self.assertFalse((run / "summary.json").exists())

    def test_available_local_model_blobs_match_manifest_and_tested_metadata(self):
        model = history.ROOT / history.MODEL_ARCHIVE
        inventory = json.loads((model / "SHA256_INVENTORY.json").read_text())
        if not all((model / item["archive_path"]).is_file() for item in inventory["files"]):
            self.skipTest("Optional local model blobs are not included in an ordinary Git clone")
        reports = history.check_all()
        self.assertEqual(reports[-1]["files_verified"], 8)
        self.assertEqual(reports[-1]["bytes_verified"], 2019395363)

    def test_checker_rejects_tampering_missing_members_and_path_traversal(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact = root / "raw.jsonl"
            artifact.write_bytes(b"original\n")
            inventory = {"files": [{"archive_path": "raw.jsonl", "bytes": 9,
                                    "sha256": history.sha256(artifact)}]}
            (root / "SHA256_INVENTORY.json").write_text(json.dumps(inventory))
            self.assertEqual(history.check_inventory(root)["files_verified"], 1)
            artifact.write_bytes(b"modified\n")
            with self.assertRaisesRegex(ValueError, "differs"):
                history.check_inventory(root)
            artifact.unlink()
            with self.assertRaisesRegex(ValueError, "differs"):
                history.check_inventory(root)
            for path in ("../outside", "/absolute", "C:/outside", "a/../b", "a\\b", ".", ""):
                with self.subTest(path=path), self.assertRaises(ValueError):
                    history.safe_member(root, path)

    def test_checker_rejects_tampered_or_escaping_referenced_sources(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            snapshot = root / "archive/new"
            snapshot.mkdir(parents=True)
            raw = snapshot / "raw.jsonl"
            raw.write_bytes(b"original\n")
            dependency = root / "archive/prior/source.py"
            dependency.parent.mkdir()
            dependency.write_bytes(b"source\n")
            reference = {"workspace_archive_path": "archive/prior/source.py", "bytes": 7,
                         "sha256": history.sha256(dependency)}
            inventory = {"files": [{"archive_path": "raw.jsonl", "bytes": 9,
                                     "sha256": history.sha256(raw)}],
                         "referenced_sources": [reference]}
            inventory_path = snapshot / "SHA256_INVENTORY.json"
            inventory_path.write_text(json.dumps(inventory))
            dependency.write_bytes(b"changed\n")
            with patch.object(history, "EXPERIMENT_ARCHIVES", ("archive/new",)):
                with self.assertRaisesRegex(ValueError, "Referenced preserved source differs"):
                    history.check_all(root)
                for relative in ("outside.py", "archive/../outside.py"):
                    reference["workspace_archive_path"] = relative
                    inventory_path.write_text(json.dumps(inventory))
                    with self.subTest(relative=relative), self.assertRaises(ValueError):
                        history.check_all(root)

    def test_check_cli_is_read_only_and_reports_failure_without_writes(self):
        with patch.object(history, "check_all", return_value=[{"files_verified": 69}]), \
                patch.object(Path, "write_bytes", side_effect=AssertionError("No writes")), \
                patch.object(Path, "write_text", side_effect=AssertionError("No writes")), \
                redirect_stdout(io.StringIO()) as output:
            self.assertEqual(history.main(["--check"]), 0)
        self.assertEqual(json.loads(output.getvalue())["status"], "verified")
        with patch.object(history, "check_all", side_effect=ValueError("Changed evidence")), \
                redirect_stderr(io.StringIO()) as errors:
            self.assertEqual(history.main(["--check"]), 1)
        self.assertIn("Changed evidence", errors.getvalue())

    def test_registry_distinguishes_available_weights_from_historical_metadata(self):
        registry = json.loads((history.ROOT / "archive/model-artifacts/registry.json").read_text())
        models = {item["tag"]: item for item in registry["models"]}
        self.assertEqual(set(models), {"llama3.2:3b", "qwen2.5:3b"})
        self.assertTrue(all(item["tested"] for item in models.values()))
        self.assertTrue(models["llama3.2:3b"]["physical_backup"]["available"])
        self.assertFalse(models["qwen2.5:3b"]["physical_backup"]["available"])
        self.assertNotIn("directory", models["qwen2.5:3b"]["physical_backup"])
        self.assertFalse(models["llama3.2:3b"]["physical_backup"]["large_blobs_versioned"])


if __name__ == "__main__":
    unittest.main()
