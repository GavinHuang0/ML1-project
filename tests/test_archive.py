"""Verify preserved pilot snapshots without importing archived experiment code."""

import hashlib
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
ARCHIVES = {"2026-10-24-legacy": 39, "2026-11-09-pilots": 74}


class ArchiveTests(unittest.TestCase):
    def test_both_snapshot_inventories_match_every_archived_byte(self):
        for name, expected_count in ARCHIVES.items():
            archive = ROOT / "archive" / name
            inventory = json.loads((archive / "SHA256_INVENTORY.json").read_text(encoding="utf-8"))
            entries = inventory["files"]
            with self.subTest(archive=name):
                self.assertEqual(len(entries), expected_count)
                self.assertEqual(len({entry["original_path"] for entry in entries}), expected_count)
                self.assertEqual(len({entry["archive_path"] for entry in entries}), expected_count)
                if "file_count" in inventory:
                    self.assertEqual(inventory["file_count"], expected_count)
                if "total_bytes" in inventory:
                    self.assertEqual(inventory["total_bytes"], sum(entry["bytes"] for entry in entries))
            for entry in entries:
                with self.subTest(archive=name, file=entry["archive_path"]):
                    relative = Path(entry["archive_path"])
                    self.assertFalse(relative.is_absolute())
                    path = archive / relative
                    self.assertTrue(path.resolve().is_relative_to(archive.resolve()))
                    self.assertTrue(path.is_file())
                    data = path.read_bytes()
                    self.assertEqual(len(data), entry["bytes"])
                    self.assertEqual(hashlib.sha256(data).hexdigest(), entry["sha256"])

    def test_active_calculator_and_execution_protocol_are_unchanged_from_snapshot(self):
        archive = ROOT / "archive" / "2026-11-09-pilots"
        inventory = json.loads((archive / "SHA256_INVENTORY.json").read_text(encoding="utf-8"))
        entries = {entry["original_path"]: entry for entry in inventory["files"]}
        for name in ("calculator.py", "calculator_protocol.py"):
            with self.subTest(file=name):
                expected = entries[name]
                active = (ROOT / name).read_bytes()
                snapshot = (archive / expected["archive_path"]).read_bytes()
                self.assertEqual(active, snapshot)
                self.assertEqual(len(active), expected["bytes"])
                self.assertEqual(hashlib.sha256(active).hexdigest(), expected["sha256"])


if __name__ == "__main__":
    unittest.main()
