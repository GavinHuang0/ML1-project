"""Preserve existing completed runs and index their settings without model calls."""

import argparse
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import tempfile


EXPERIMENT_DIR = Path(__file__).resolve().parents[1] / "experiments" / "communication_pilot"
METHODS = ("single", "independent_voting", "self_revision", "answers_only",
           "justifications", "source_dedup")


def reject_constant(value):
    raise ValueError(f"Nonfinite JSON value: {value}")


def finite(value):
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("Nonfinite number in run data")
    if isinstance(value, dict):
        for item in value.values():
            finite(item)
    elif isinstance(value, list):
        for item in value:
            finite(item)


def read_json(text):
    value = json.loads(text, parse_constant=reject_constant)
    finite(value)
    return value


def describe(data, filename, stage):
    rows = [read_json(line) for line in data.decode("utf-8").splitlines()]
    if len(rows) < 3 or any(not isinstance(row, dict) for row in rows):
        raise ValueError("Expected metadata, question records, and a completion marker")
    metadata, complete = rows[0], rows[-1]
    questions = rows[1:-1]
    if metadata.get("type") != "metadata" or complete.get("type") != "complete":
        raise ValueError("Metadata must be first and the completion marker must be last")
    if any(row.get("type") != "question" for row in questions):
        raise ValueError("Only question records may occur between metadata and completion")
    settings = metadata.get("settings")
    expected = settings.get("questions") if isinstance(settings, dict) else None
    completed = complete.get("questions_completed")
    if (type(expected) is not int or expected < 1 or type(completed) is not int
            or expected != len(questions) or completed != len(questions)):
        raise ValueError("Question count does not match settings and completion marker")
    if not isinstance(metadata.get("model"), str) or not metadata["model"].strip():
        raise ValueError("Metadata must identify the model tag")
    if not isinstance(metadata.get("created_at"), str) or not metadata["created_at"]:
        raise ValueError("Metadata must include created_at")
    model_metadata = metadata.get("model_metadata", {})
    if not isinstance(model_metadata, dict):
        raise ValueError("model_metadata must be an object")
    agents = settings.get("agents")
    if type(agents) is not int or agents < 1:
        raise ValueError("Metadata must identify the number of agents")
    ids, families, scores = set(), Counter(), {method: [] for method in METHODS}
    for row in questions:
        task = row.get("task")
        if not isinstance(task, dict):
            raise ValueError("Each question must contain its original task")
        task_id, family = task.get("id"), task.get("family")
        if not isinstance(task_id, str) or not task_id or task_id in ids:
            raise ValueError("Question task IDs must be nonempty and unique")
        if not isinstance(family, str) or not family:
            raise ValueError("Each task must identify its family")
        ids.add(task_id)
        families[family] += 1
        if not isinstance(row.get("initial"), list) or len(row["initial"]) != agents:
            raise ValueError("Initial response count does not match settings")
        for method in METHODS:
            if method in METHODS[:2]:
                metrics = row.get(method)
            else:
                conditions = row.get("conditions")
                branch = conditions.get(method) if isinstance(conditions, dict) else None
                if (not isinstance(branch, dict) or not isinstance(branch.get("revised"), list)
                        or len(branch["revised"]) != agents):
                    raise ValueError(f"Revision response count does not match settings for {method}")
                metrics = branch.get("metrics")
            ensemble = metrics.get("ensemble") if isinstance(metrics, dict) else None
            correct = ensemble.get("correct") if isinstance(ensemble, dict) else None
            if type(correct) is not bool:
                raise ValueError(f"Missing boolean ensemble correctness for {method}")
            scores[method].append(correct)
    protocol = {key: value for key, value in metadata.items() if "protocol" in key.lower()}
    return {
        "raw_path": (Path(stage) / "raw" / filename).as_posix(),
        "sha256": hashlib.sha256(data).hexdigest(),
        "question_set_sha256": hashlib.sha256(json.dumps(
            [row["task"] for row in questions], sort_keys=True,
            separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest(),
        "source_filename": filename,
        "model": metadata["model"], "model_digest": model_metadata.get("digest"),
        "questions": len(questions), "family_counts": dict(families),
        "settings": settings, "created_at": metadata["created_at"],
        "experiment_id": metadata.get("experiment_id"),
        "ollama_version": metadata.get("ollama_version"),
        "protocol_provenance": {"status": "recorded" if protocol else "unknown", "fields": protocol},
        "ensemble_accuracy": {method: sum(values) / len(values) for method, values in scores.items()},
    }


def register(data, entry, stage):
    raw = EXPERIMENT_DIR / entry["raw_path"]
    summaries = EXPERIMENT_DIR / stage / "summaries"
    raw.parent.mkdir(parents=True, exist_ok=True)
    summaries.mkdir(parents=True, exist_ok=True)
    index_path = summaries / "runs.json"
    lock_path = summaries / "runs.json.lock"
    try:
        lock = lock_path.open("x", encoding="utf-8")
    except FileExistsError as exc:
        raise ValueError(f"Registration is locked: {lock_path}") from exc
    temporary = None
    try:
        with lock:
            index = read_json(index_path.read_text(encoding="utf-8")) if index_path.exists() else {
                "schema_version": 1, "runs": []}
            if (not isinstance(index, dict) or index.get("schema_version") != 1
                    or not isinstance(index.get("runs"), list)):
                raise ValueError("Unrecognized existing run index; refusing to replace it")
            paths = set()
            for old in index["runs"]:
                if (not isinstance(old, dict) or not isinstance(old.get("raw_path"), str)
                        or old["raw_path"] in paths or not isinstance(old.get("sha256"), str)):
                    raise ValueError("Malformed existing run index; refusing to replace it")
                paths.add(old["raw_path"])
            old = next((run for run in index["runs"] if run["raw_path"] == entry["raw_path"]), None)
            if old is not None and old["sha256"] != entry["sha256"]:
                raise ValueError(f"Indexed filename has different contents: {raw.name}")
            if raw.exists():
                if raw.read_bytes() != data:
                    raise ValueError(f"Raw filename has different contents: {raw.name}")
            else:
                with raw.open("xb") as output:
                    output.write(data)
            if old is not None:
                return
            index["runs"].append(entry)
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=summaries,
                                             prefix=".runs-", suffix=".json", delete=False) as output:
                temporary = Path(output.name)
                json.dump(index, output, indent=2, allow_nan=False)
                output.write("\n")
            os.replace(temporary, index_path)
            temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        lock_path.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+", type=Path, metavar="FILE")
    parser.add_argument("--stage", choices=("pilot", "results"), default="pilot")
    args = parser.parse_args(argv)
    try:
        prepared = []
        for source in args.files:
            data = source.read_bytes()
            prepared.append((data, describe(data, source.name, args.stage)))
        for data, entry in prepared:
            register(data, entry, args.stage)
            print(f"Registered {entry['source_filename']} -> {entry['raw_path']}")
        return 0
    except (OSError, ValueError, AttributeError, TypeError) as exc:
        print(f"Registration failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
