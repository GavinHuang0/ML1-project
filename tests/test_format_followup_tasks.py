"""Checks for the development-only follow-up bank and independent references."""

from contextlib import redirect_stderr, redirect_stdout
import copy
from fractions import Fraction
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import build_format_followup_tasks as bank
from multi_agent_protocol import build_messages, read_tasks


class FormatFollowupTasksTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads(bank.DEFAULT_PATH.read_text(encoding="utf-8"))

    def test_frozen_bytes_and_development_only_semantic_pairing(self):
        self.assertEqual(bank.manifest_bytes(bank.generate_manifest()), bank.DEFAULT_PATH.read_bytes())
        tasks, _ = read_tasks(bank.DEFAULT_PATH)
        self.assertEqual(len(tasks), 16)
        self.assertEqual({task["split"] for task in tasks}, {"development"})
        self.assertEqual(len({task["group_id"] for task in tasks}), 8)
        for old, new in zip(tasks[:8], tasks[8:]):
            self.assertEqual(old["group_id"], new["group_id"])
            self.assertNotEqual(old["prompt"], new["prompt"])
            self.assertNotEqual(bank.numeric_key(old), bank.numeric_key(new))
        self.assertIn("not a structural holdout", self.manifest["source"]["semantic_group_policy"])

    def test_reference_checks_reject_wrong_gold_even_if_witness_changes(self):
        for family in bank.FAMILIES:
            manifest = copy.deepcopy(self.manifest)
            task = next(task for task in manifest["tasks"][8:] if task["family"] == family)
            task["gold_fraction"] = str(Fraction(task["gold_fraction"]) + Fraction(1, 100))
            task["parameters"]["reference_expression"] = task["gold_fraction"]
            with self.subTest(family=family), self.assertRaises(ValueError):
                bank.validate_manifest(manifest)

    def test_allocations_and_regression_evidence_cannot_silently_change(self):
        altered = copy.deepcopy(self.manifest)
        altered["tasks"][8]["split"] = "validation"
        with self.assertRaises(ValueError):
            bank.validate_manifest(altered)
        altered = copy.deepcopy(self.manifest)
        altered["tasks"][0]["prompt"] += " Additional hint."
        with self.assertRaisesRegex(ValueError, "Regression task changed"):
            bank.validate_manifest(altered)
        altered = copy.deepcopy(self.manifest)
        altered["screening_task_ids"] = altered["regression_task_ids"]
        with self.assertRaisesRegex(ValueError, "allocation differs"):
            bank.validate_manifest(altered)

    def test_private_references_and_group_metadata_never_enter_prompts(self):
        for task in self.manifest["tasks"]:
            altered = {**task, "gold_fraction": "PRIVATE_GOLD", "parameters": {"secret": "PRIVATE_PARAMETERS"},
                       "group_id": "PRIVATE_GROUP"}
            self.assertNotIn("PRIVATE_", json.dumps(build_messages(altered, 0, 0)))

    def test_cli_is_read_only_and_output_refuses_overwrite(self):
        before = bank.DEFAULT_PATH.read_bytes()
        with redirect_stdout(io.StringIO()):
            self.assertEqual(bank.main(["--check"]), 0)
        self.assertEqual(bank.DEFAULT_PATH.read_bytes(), before)
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "tasks.json"
            with redirect_stdout(io.StringIO()):
                self.assertEqual(bank.main(["--output", str(target)]), 0)
            self.assertEqual(target.read_bytes(), before)
            with redirect_stderr(io.StringIO()):
                self.assertEqual(bank.main(["--output", str(target)]), 1)
            target.write_text("changed", encoding="utf-8")
            with patch.object(bank, "DEFAULT_PATH", target), redirect_stderr(io.StringIO()):
                self.assertEqual(bank.main(["--check"]), 1)


if __name__ == "__main__":
    unittest.main()
