"""Verify preserved experiment/model artifacts without inference or downloads.

The dated snapshot is intentionally separate from the operational source/result
paths referenced by historical manifests. --check never changes either copy.
"""

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys


ROOT = Path(__file__).resolve().parent
EXPERIMENT_ARCHIVES = (
    "archive/2026-10-24-legacy",
    "archive/2026-11-09-pilots",
    "archive/2026-11-17-development-pilots",
    "archive/2026-11-17-communication-pilot-v1-failed",
    "archive/2026-11-17-communication-recovery-v2",
    "archive/2026-11-18-offline-policies-v1",
    "archive/2026-11-18-confirmation-pilot-v1",
    "archive/2026-11-18-architecture-pilots-v1",
)
MODEL_ARCHIVE = "archive/model-artifacts/llama3.2-3b-a80c4f17"


def sha256(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def safe_member(root, relative):
    """Resolve an archive entry without accepting traversal or symlink escapes."""
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise ValueError("Archive member must be a nonempty POSIX relative path")
    parts = PurePosixPath(relative)
    if (not parts.parts or parts.as_posix() != relative or parts.is_absolute()
            or any(part in {"..", "."} or ":" in part for part in parts.parts)):
        raise ValueError(f"Unsafe archive path: {relative}")
    root = Path(root).resolve()
    member = root.joinpath(*parts.parts)
    cursor = root
    for part in parts.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ValueError(f"Archive symlinks are not accepted: {relative}")
    if not member.resolve().is_relative_to(root):
        raise ValueError(f"Archive member escapes its root: {relative}")
    return member


def check_inventory(directory):
    directory = Path(directory)
    if directory.is_symlink():
        raise ValueError("Archive directory must not be a symlink")
    inventory_path = safe_member(directory, "SHA256_INVENTORY.json")
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    files = inventory.get("files")
    if not isinstance(files, list) or not files:
        raise ValueError("Archive inventory must list preserved files")
    seen, total = set(), 0
    for entry in files:
        relative = entry["archive_path"]
        if relative in seen:
            raise ValueError(f"Duplicate archived member: {relative}")
        seen.add(relative)
        member = safe_member(directory, relative)
        if (not member.is_file() or member.stat().st_size != entry["bytes"]
                or sha256(member) != entry["sha256"]):
            raise ValueError(f"Preserved artifact differs: {member}")
        total += entry["bytes"]
    if "file_count" in inventory and inventory["file_count"] != len(files):
        raise ValueError("Archive file count differs from inventory")
    if "total_bytes" in inventory and inventory["total_bytes"] != total:
        raise ValueError("Archive byte count differs from inventory")
    return {"archive": str(directory), "files_verified": len(files), "bytes_verified": total}


def check_all(root=ROOT):
    root = Path(root).resolve()
    reports = [check_inventory(safe_member(root, name)) for name in EXPERIMENT_ARCHIVES]
    for name, report in zip(EXPERIMENT_ARCHIVES, reports):
        inventory = json.loads((safe_member(root, name) / "SHA256_INVENTORY.json").read_text(encoding="utf-8"))
        references = inventory.get("referenced_sources", [])
        if not isinstance(references, list):
            raise ValueError("Referenced source inventory must be a list")
        for entry in references:
            relative = entry["workspace_archive_path"]
            if not relative.startswith("archive/"):
                raise ValueError("Referenced sources must remain in the preserved archive namespace")
            member = safe_member(root, relative)
            if (not member.is_file() or member.stat().st_size != entry["bytes"]
                    or sha256(member) != entry["sha256"]):
                raise ValueError(f"Referenced preserved source differs: {member}")
        if references:
            report["referenced_files_verified"] = len(references)
    model = safe_member(root, MODEL_ARCHIVE)
    reports.append(check_inventory(model))
    inventory = json.loads((model / "SHA256_INVENTORY.json").read_text(encoding="utf-8"))
    manifest = json.loads((model / "ollama-manifest.json").read_text(encoding="utf-8"))
    references = [manifest["config"], *manifest["layers"]]
    expected = {"blobs/" + item["digest"].replace(":", "-"): item for item in references}
    actual = {entry["archive_path"]: entry for entry in inventory["files"]}
    for relative, reference in expected.items():
        entry = actual.get(relative)
        if (entry is None or entry["sha256"] != reference["digest"].removeprefix("sha256:")
                or entry["bytes"] != reference["size"]):
            raise ValueError(f"Model blob does not match its manifest: {relative}")
    registry = json.loads((model.parent / "registry.json").read_text(encoding="utf-8"))
    models = {item["tag"]: item for item in registry["models"]}
    if set(models) != {"llama3.2:3b", "qwen2.5:3b"}:
        raise ValueError("Tested-model registry differs from preserved evidence")
    for item in models.values():
        evidence = json.loads(safe_member(root, item["evidence"]).read_text(encoding="utf-8"))
        if item["tag"] == "qwen2.5:3b":
            metadata = evidence["metadata"]["model_metadata"]
        else:
            metadata = evidence["model_metadata"]
        if metadata != item["model_metadata"] or metadata["digest"] != item["recorded_digest"]:
            raise ValueError(f"Model registry disagrees with original metadata: {item['tag']}")
    if models["llama3.2:3b"]["recorded_digest"] != inventory["recorded_model_digest"]:
        raise ValueError("Llama backup and tested-model identity differ")
    return reports


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", required=True,
                        help="Read-only SHA256 verification of all dated snapshots and model backup")
    args = parser.parse_args(argv)
    try:
        print(json.dumps({"status": "verified", "archives": check_all()}, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Archive verification failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
