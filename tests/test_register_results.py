"""Existing run registration preserves evidence and refuses invalid artifacts."""

from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import register_results as registration


def records(model="qwen-fixture:3b"):
    metadata = {"type": "metadata", "model": model, "model_metadata": {"digest": "fixture-digest"},
                "ollama_version": "fixture", "created_at": "2026-10-12T00:00:00+00:00",
                "settings": {"questions": 2, "agents": 3, "seed": 73, "temperature": 0.2,
                             "max_tokens": 512, "timeout": 600, "custom_setting": "retained"}}
    rows = [metadata]
    for index, family in enumerate(("reasoning", "evidence")):
        outcomes = {method: {"ensemble": {"correct": index == 0}}
                    for method in registration.METHODS}
        rows.append({"type": "question", "task": {"id": f"task-{index}", "family": family},
                     "initial": [{"raw": {}} for _ in range(3)],
                     "single": outcomes["single"], "independent_voting": outcomes["independent_voting"],
                     "conditions": {method: {"metrics": outcomes[method], "revised": [{"raw": {}}] * 3}
                                    for method in registration.METHODS[2:]}})
    rows.append({"type": "complete", "questions_completed": 2})
    return rows


class RegistrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.experiment = self.directory / "experiment"
        self.patch = patch.object(registration, "EXPERIMENT_DIR", self.experiment)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.addCleanup(self.temporary.cleanup)

    def write_run(self, name="existing-pilot.jsonl", rows=None):
        path = self.directory / name
        data = "\r\n".join(json.dumps(row) + " " for row in (rows if rows is not None else records())) + "\r\n"
        path.write_bytes(data.encode("utf-8"))
        return path

    def run_tool(self, *arguments):
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return registration.main([str(argument) for argument in arguments])

    def index(self, stage="pilot"):
        return json.loads((self.experiment / stage / "summaries" / "runs.json").read_text())

    def test_registers_exact_original_bytes_and_metadata_without_inference(self):
        source = self.write_run()
        original = source.read_bytes()
        self.assertEqual(self.run_tool(source), 0)
        copied = self.experiment / "pilot" / "raw" / source.name
        self.assertEqual(copied.read_bytes(), original)
        self.assertEqual(source.read_bytes(), original)
        entry = self.index()["runs"][0]
        self.assertEqual(entry["raw_path"], "pilot/raw/existing-pilot.jsonl")
        self.assertEqual(entry["sha256"], hashlib.sha256(original).hexdigest())
        self.assertEqual(entry["settings"], records()[0]["settings"])
        self.assertEqual(entry["model_digest"], "fixture-digest")
        self.assertEqual(entry["family_counts"], {"reasoning": 1, "evidence": 1})
        self.assertEqual(entry["questions"], 2)
        self.assertEqual(entry["ensemble_accuracy"], {method: 0.5 for method in registration.METHODS})
        self.assertEqual(entry["protocol_provenance"], {"status": "unknown", "fields": {}})

    def test_records_available_protocol_fields_and_distinct_model_runs(self):
        first = self.write_run("first.jsonl")
        second_rows = records("another-qwen-fixture:7b")
        provenance = {"protocol_path": "experiments/communication_pilot/protocol.md",
                      "protocol_sha256": "fixture-protocol-hash"}
        second_rows[0].update(provenance, experiment_id="communication_pilot")
        second = self.write_run("second.jsonl", second_rows)
        self.assertEqual(self.run_tool(first, second, "--stage", "results"), 0)
        entries = self.index("results")["runs"]
        self.assertEqual([entry["model"] for entry in entries], ["qwen-fixture:3b", "another-qwen-fixture:7b"])
        self.assertEqual(entries[1]["protocol_provenance"], {"status": "recorded", "fields": provenance})
        self.assertEqual(entries[1]["experiment_id"], "communication_pilot")
        self.assertFalse((self.experiment / "pilot").exists())

    def test_identical_registration_is_idempotent_and_preserves_index_bytes(self):
        source = self.write_run()
        self.assertEqual(self.run_tool(source), 0)
        index_path = self.experiment / "pilot" / "summaries" / "runs.json"
        previous = index_path.read_bytes()
        self.assertEqual(self.run_tool(source), 0)
        self.assertEqual(index_path.read_bytes(), previous)
        self.assertEqual(len(self.index()["runs"]), 1)

    def test_question_hash_matches_across_models_and_changes_with_original_tasks(self):
        first = self.write_run("first.jsonl")
        same_tasks = records("another-qwen-fixture:7b")
        for row in same_tasks[1:-1]:
            row["task"] = dict(reversed(list(row["task"].items())))
        second = self.write_run("second.jsonl", same_tasks)
        altered = records("another-qwen-fixture:7b")
        altered[1]["task"]["prompt"] = "An altered original question."
        third = self.write_run("third.jsonl", altered)
        self.assertEqual(self.run_tool(first, second, third), 0)
        hashes = [entry["question_set_sha256"] for entry in self.index()["runs"]]
        self.assertEqual(hashes[0], hashes[1])
        self.assertNotEqual(hashes[0], hashes[2])

    def test_same_filename_different_bytes_preserves_raw_source_and_index(self):
        source = self.write_run()
        self.assertEqual(self.run_tool(source), 0)
        raw = self.experiment / "pilot" / "raw" / source.name
        index_path = self.experiment / "pilot" / "summaries" / "runs.json"
        old_raw, old_index = raw.read_bytes(), index_path.read_bytes()
        modified = records()
        modified[0]["settings"]["temperature"] = 0.9
        self.write_run(rows=modified)
        new_source = source.read_bytes()
        self.assertEqual(self.run_tool(source), 1)
        self.assertEqual(raw.read_bytes(), old_raw)
        self.assertEqual(index_path.read_bytes(), old_index)
        self.assertEqual(source.read_bytes(), new_source)

    def test_unindexed_raw_collision_is_not_overwritten(self):
        source = self.write_run()
        raw = self.experiment / "pilot" / "raw" / source.name
        raw.parent.mkdir(parents=True)
        raw.write_bytes(b"existing original data")
        self.assertEqual(self.run_tool(source), 1)
        self.assertEqual(raw.read_bytes(), b"existing original data")
        self.assertFalse((self.experiment / "pilot" / "summaries" / "runs.json").exists())

    def test_rejects_incomplete_or_malformed_records_before_copying(self):
        base = records()
        invalid = [base[:-1], base[1:]]
        for path, replacement in [((0, "settings", "questions"), 3),
                                  ((3, "questions_completed"), 1),
                                  ((3, "questions_completed"), True),
                                  ((2, "task", "id"), "task-0"),
                                  ((1, "initial"), []),
                                  ((1, "conditions", "answers_only", "revised"), []),
                                  ((1, "single", "ensemble", "correct"), 1)]:
            changed = deepcopy(base)
            node = changed
            for key in path[:-1]:
                node = node[key]
            node[path[-1]] = replacement
            invalid.append(changed)
        invalid.append(base + [{"type": "question"}])
        for index, rows in enumerate(invalid):
            with self.subTest(case=index):
                source = self.write_run(f"bad-{index}.jsonl", rows)
                original = source.read_bytes()
                self.assertEqual(self.run_tool(source), 1)
                self.assertEqual(source.read_bytes(), original)
                self.assertFalse(self.experiment.exists())

    def test_rejects_json_syntax_errors_and_nonfinite_values(self):
        for value in ("not-json", "NaN", "Infinity", "-Infinity", "1e999"):
            with self.subTest(value=value):
                source = self.write_run("bad.jsonl")
                text = source.read_text().replace('"temperature": 0.2', f'"temperature": {value}')
                source.write_text(text)
                self.assertEqual(self.run_tool(source), 1)
                self.assertFalse(self.experiment.exists())

    def test_corrupt_index_is_not_replaced(self):
        source = self.write_run()
        summaries = self.experiment / "pilot" / "summaries"
        summaries.mkdir(parents=True)
        index = summaries / "runs.json"
        index.write_bytes(b'{"schema_version":1,"runs":[{"unrecognized":"entry"}]}')
        original = index.read_bytes()
        self.assertEqual(self.run_tool(source), 1)
        self.assertEqual(index.read_bytes(), original)
        self.assertFalse((self.experiment / "pilot" / "raw" / source.name).exists())
        self.assertFalse((summaries / "runs.json.lock").exists())


if __name__ == "__main__":
    unittest.main()
