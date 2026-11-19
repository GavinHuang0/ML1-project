"""Restore verified LF bytes in the baseline and full benchmark configurations.

Run before starting an experiment. All contents are checked before any file is
changed, and originals are backed up under results/. No model calls are made.
The Windows test fixes are installed separately by updating the Git checkout.
"""

import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile

from build_full_benchmark import generate_manifest, manifest_bytes


ROOT = Path(__file__).resolve().parents[1]


def plan_repairs(root):
    reference = json.loads((root / "results/baseline/HISTORICAL_REFERENCE.json")
                           .read_text(encoding="utf-8"))
    baseline = root / "config/baseline.json"
    benchmark = root / "config/full_benchmark.json"
    changes = []
    for path in (baseline, benchmark):
        original = path.read_bytes()
        normalized = original.replace(b"\r\n", b"\n")
        if path == baseline:
            valid = hashlib.sha256(normalized).hexdigest() == reference["configuration_sha256"]
        else:
            valid = normalized == manifest_bytes(generate_manifest())
        if not valid:
            raise ValueError(f"{path.relative_to(root).as_posix()} has content differences; no files changed")
        if original != normalized:
            changes.append((path, original, normalized))
    return changes


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help="Project directory; defaults to the repository root")
    parser.add_argument("--check", action="store_true", help="Check without writing files")
    args = parser.parse_args(argv)
    backup = None
    try:
        root = args.root.resolve()
        changes = plan_repairs(root)
        if not changes:
            print("Baseline and full benchmark already have verified LF bytes.")
            return 0
        if args.check:
            for path, _, _ in changes:
                print(f"CRLF line endings: {path.relative_to(root).as_posix()}")
            return 1
        backup = Path(tempfile.mkdtemp(prefix="windows-checkout-backup-", dir=root / "results"))
        for path, original, _ in changes:
            destination = backup / path.relative_to(root)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(original)
        for path, _, normalized in changes:
            path.write_bytes(normalized)
            print(f"Restored LF bytes: {path.relative_to(root).as_posix()}")
        print(f"Original files backed up in {backup}")
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"Windows checkout repair stopped: {error}", file=sys.stderr)
        if backup is not None:
            print(f"Original files are preserved in {backup}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
