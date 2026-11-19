"""Verified line-ending repair must preserve contents and original evidence."""

from contextlib import redirect_stderr, redirect_stdout
import io
from pathlib import Path
import tempfile
import unittest

import fix_windows_checkout as repair


ROOT = Path(__file__).resolve().parents[1]


class WindowsCheckoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.baseline_bytes = (ROOT / "config/baseline.json").read_bytes().replace(b"\r\n", b"\n")
        cls.benchmark_bytes = repair.manifest_bytes(repair.generate_manifest())

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / "config").mkdir()
        (self.root / "results/baseline").mkdir(parents=True)
        (self.root / "results/baseline/HISTORICAL_REFERENCE.json").write_bytes(
            (ROOT / "results/baseline/HISTORICAL_REFERENCE.json").read_bytes())
        self.baseline = self.root / "config/baseline.json"
        self.benchmark = self.root / "config/full_benchmark.json"
        self.baseline.write_bytes(self.baseline_bytes)
        self.benchmark.write_bytes(self.benchmark_bytes)

    def invoke(self, *args):
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return repair.main(["--root", str(self.root), *args])

    def backups(self):
        return list((self.root / "results").glob("windows-checkout-backup-*"))

    def test_correct_files_are_unchanged_and_need_no_backup(self):
        before = [(path.read_bytes(), path.stat().st_mtime_ns) for path in (self.baseline, self.benchmark)]
        self.assertEqual(self.invoke(), 0)
        self.assertEqual(before, [(path.read_bytes(), path.stat().st_mtime_ns)
                                 for path in (self.baseline, self.benchmark)])
        self.assertEqual(self.backups(), [])

    def test_crlf_repair_preserves_originals_and_is_idempotent(self):
        originals = {}
        for path in (self.baseline, self.benchmark):
            originals[path] = path.read_bytes().replace(b"\n", b"\r\n")
            path.write_bytes(originals[path])
        self.assertEqual(self.invoke(), 0)
        self.assertEqual(self.baseline.read_bytes(), self.baseline_bytes)
        self.assertEqual(self.benchmark.read_bytes(), self.benchmark_bytes)
        backups = self.backups()
        self.assertEqual(len(backups), 1)
        for path, original in originals.items():
            self.assertEqual((backups[0] / path.relative_to(self.root)).read_bytes(), original)
        self.assertEqual(self.invoke(), 0)
        self.assertEqual(self.backups(), backups)

    def test_check_reports_crlf_without_writing(self):
        original = self.baseline_bytes.replace(b"\n", b"\r\n")
        self.baseline.write_bytes(original)
        self.assertEqual(self.invoke("--check"), 1)
        self.assertEqual(self.baseline.read_bytes(), original)
        self.assertEqual(self.backups(), [])

    def test_content_difference_in_either_file_blocks_all_repairs(self):
        for changed_path in (self.baseline, self.benchmark):
            with self.subTest(file=changed_path.name):
                self.baseline.write_bytes(self.baseline_bytes.replace(b"\n", b"\r\n"))
                self.benchmark.write_bytes(self.benchmark_bytes.replace(b"\n", b"\r\n"))
                changed_path.write_bytes(changed_path.read_bytes() + b" ")
                before = {path: path.read_bytes() for path in (self.baseline, self.benchmark)}
                self.assertEqual(self.invoke(), 1)
                for path, original in before.items():
                    self.assertEqual(path.read_bytes(), original)
                self.assertEqual(self.backups(), [])


if __name__ == "__main__":
    unittest.main()
