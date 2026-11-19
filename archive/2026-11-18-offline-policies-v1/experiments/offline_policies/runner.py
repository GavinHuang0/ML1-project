"""Audited, inference-free comparison of fixed voting and stopping policies.

All expensive responses already exist. This entry point audits that evidence,
computes deterministic counterfactual reports, and never contacts a model.
"""

import argparse
import copy
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import sys

from experiments.communication_pilot import recovery
from . import analysis
from .protocol import (ARMS, EXPECTED_CONFIG, EXPERIMENT_ID, MAX_ROUND,
                       STOPPING_RULES, VOTING_RULES)


ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "config/offline_policy_comparison.json"
DEFAULT_SOURCE = ROOT / "results/communication-pilot/windows-v2"
DEFAULT_OUTPUT = ROOT / "results/offline-comparison/pilot-v1"
SOURCE_EVIDENCE = ("run-manifest.json", "initial_panel.jsonl", "generations.jsonl",
                   "answers.jsonl", "summary.json")
ANALYSIS_SOURCE_FILES = (
    "run_offline_comparison.py", "run_offline_comparison.ps1", "experiments/__init__.py",
    "experiments/offline_policies/__init__.py", "experiments/offline_policies/protocol.py",
    "experiments/offline_policies/analysis.py", "experiments/offline_policies/runner.py",
)
REPORT_FILES = ("summary.json", "comparisons.csv", "per_question.csv")
PLAN_FIELDS = ("experiment_id", "configuration_path", "configuration_sha256",
               "configuration_snapshot", "source_run_snapshot", "source_sha256",
               "input_sha256", "planned_comparison_rows", "planned_question_rows",
               "planned_round_predictions", "additional_model_calls")
ERRORS = (OSError, ValueError, KeyError, TypeError, RuntimeError, OverflowError,
          ZeroDivisionError, RecursionError)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def snapshot_hash(value):
    return digest(canonical(value).encode("utf-8"))


def strict_json(text):
    return recovery.strict_json(text)


def _file_hashes(paths):
    return {str(Path(path).resolve()): digest(Path(path).read_bytes()) for path in sorted(set(map(str, paths)))}


def _source_paths(directory, manifest):
    paths = {directory / name for name in SOURCE_EVIDENCE}
    for name in manifest["source_sha256"]:
        path = Path(name)
        paths.add(path if path.is_absolute() else ROOT / path)
    paths.add(Path(manifest["configuration_path"]))
    for key in ("parent_snapshot", "source_run_snapshot"):
        snapshot = manifest[key]
        for name in snapshot["evidence_sha256"]:
            paths.add(Path(snapshot["directory"]) / name)
    return paths


def load_source(directory):
    """Independently replay the completed recovery and bind all its inputs."""
    directory = Path(directory).resolve()
    evidence_before = _file_hashes(directory / name for name in SOURCE_EVIDENCE)
    manifest = strict_json((directory / "run-manifest.json").read_text(encoding="utf-8"))
    if manifest.get("experiment_id") != recovery.EXPERIMENT_ID or manifest.get("status") != "complete":
        raise ValueError("Offline comparison requires the complete versioned recovery pilot")
    paths = _source_paths(directory, manifest)
    inputs_before = _file_hashes(paths)
    if any(inputs_before[path] != value for path, value in evidence_before.items()):
        raise ValueError("Source evidence changed while preparing the audit")
    audited = recovery.analyze_run(directory)
    if (audited.get("offline_audit") != "passed" or audited.get("status") != "complete"
            or audited.get("summary_reproduced") is not True
            or audited.get("calls_completed") != 480 or audited.get("generations_saved") != 480):
        raise ValueError("Source must reproduce all 480 outcomes and its saved summary")
    initial, _ = recovery.journal_records(directory / "initial_panel.jsonl")
    answers, _ = recovery.journal_records(directory / "answers.jsonl")
    if len(initial) != 80 or len(answers) != 480:
        raise ValueError("Source needs 80 shared initial answers and 480 revision answers")
    if inputs_before != _file_hashes(paths):
        raise ValueError("Source or transitive input changed during the offline audit")
    snapshot = {
        "directory": str(directory), "experiment_id": manifest["experiment_id"],
        "status": "complete", "offline_audit": "passed", "summary_reproduced": True,
        "evidence_sha256": {name: evidence_before[str(directory / name)] for name in SOURCE_EVIDENCE},
        "input_sha256": inputs_before, "initial_records": 80, "revision_records": 480,
        "questions": len(manifest["tasks_snapshot"]),
        "semantic_groups": len({task["group_id"] for task in manifest["tasks_snapshot"]}),
        "model_digest": manifest["model_digest"], "ollama_version": manifest["ollama_version"],
        "source_failure_policy_amendment": copy.deepcopy(manifest["protocol_snapshot"]),
        "parent_directory": manifest["parent_snapshot"]["directory"],
        "failed_prefix_directory": manifest["source_run_snapshot"]["directory"],
    }
    return manifest, initial, answers, snapshot


def source_hashes(config_path):
    return _file_hashes([ROOT / name for name in ANALYSIS_SOURCE_FILES] + [Path(config_path).resolve()])


def load_plan(config_path=CONFIG_PATH, source_directory=DEFAULT_SOURCE):
    config_path = Path(config_path).resolve()
    config_bytes = config_path.read_bytes()
    config = strict_json(config_bytes.decode("utf-8"))
    if canonical(config) != canonical(EXPECTED_CONFIG):
        raise ValueError("Configuration differs from the frozen offline policy comparison")
    codes_before = source_hashes(config_path)
    manifest, initial, answers, source = load_source(source_directory)
    if codes_before != source_hashes(config_path):
        raise ValueError("Analysis code or configuration changed during source audit")
    policies = len(ARMS) * len(VOTING_RULES) * len(STOPPING_RULES)
    return {
        "experiment_id": EXPERIMENT_ID, "configuration_path": str(config_path),
        "configuration_sha256": digest(config_bytes), "configuration_snapshot": config,
        "source_run_snapshot": source, "source_sha256": codes_before,
        "input_sha256": source["input_sha256"],
        "planned_comparison_rows": policies,
        "planned_question_rows": policies * 8,
        "planned_round_predictions": len(ARMS) * len(VOTING_RULES) * 8 * (MAX_ROUND + 1),
        "additional_model_calls": 0,
        "source_manifest": manifest, "initial_panel": initial, "answers": answers,
    }


def verify_plan(plan):
    for label in ("source_sha256", "input_sha256"):
        for name, expected in plan[label].items():
            if digest(Path(name).read_bytes()) != expected:
                raise ValueError(f"Frozen analysis source/input changed: {name}")


def _plain_output_path(path):
    """Reject symlink/junction ancestors rather than silently resolving escapes."""
    path = Path(path).absolute()
    for current in (path, *path.parents):
        try:
            state = current.lstat()
        except FileNotFoundError:
            continue
        if current.is_symlink() or getattr(state, "st_file_attributes", 0) & 0x400:
            raise ValueError(f"Output path has a symlink or reparse-point component: {current}")
    return path.resolve()


def validate_output(directory, plan, require_new=True):
    directory = _plain_output_path(directory)
    if require_new and directory.exists():
        raise ValueError("Output directory already exists; choose a new comparison directory")
    source = plan["source_run_snapshot"]
    protected = [Path(source[key]).resolve() for key in
                 ("directory", "parent_directory", "failed_prefix_directory")]
    protected += [ROOT / "archive", ROOT / "results/baseline", ROOT / "results/communication-pilot",
                  ROOT / "results/format-followup", ROOT / "results/followup-pilot"]
    for path in protected:
        if directory.is_relative_to(path) or path.is_relative_to(directory):
            raise ValueError(f"Output overlaps a historical or input namespace: {path}")
    for name in plan["input_sha256"]:
        path = Path(name).resolve()
        if directory == path or path.is_relative_to(directory):
            raise ValueError(f"Output would contain an analysis input: {path}")
    return directory


def build_report(plan):
    verify_plan(plan)
    result = analysis.analyze(plan["source_manifest"], plan["initial_panel"], plan["answers"],
                              plan["configuration_snapshot"])
    expected = (("comparisons", "planned_comparison_rows"),
                ("per_question", "planned_question_rows"),
                ("round_predictions", "planned_round_predictions"))
    for name, count in expected:
        if not isinstance(result.get(name), list) or len(result[name]) != plan[count]:
            raise ValueError(f"Analysis did not emit the complete frozen {name} grid")
    result.update(experiment_id=EXPERIMENT_ID, selection_performed=False,
                  recommendation=None, additional_model_calls=0,
                  source_run_snapshot=copy.deepcopy(plan["source_run_snapshot"]),
                  configuration_snapshot=copy.deepcopy(plan["configuration_snapshot"]))
    canonical(result)
    verify_plan(plan)
    return result


def _csv_bytes(rows):
    columns = list(dict.fromkeys(key for row in rows for key in row))
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        formatted = {}
        for key, value in row.items():
            if value is None:
                formatted[key] = ""
            elif isinstance(value, (dict, list, bool)):
                formatted[key] = canonical(value)
            else:
                formatted[key] = value
        writer.writerow(formatted)
    return output.getvalue().encode("utf-8")


def report_bytes(summary):
    return {
        "summary.json": (json.dumps(summary, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8"),
        "comparisons.csv": _csv_bytes(summary["comparisons"]),
        "per_question.csv": _csv_bytes(summary["per_question"]),
    }


def write_reports(directory, plan, summary):
    """Publish only after successful analysis; never overwrite a destination."""
    payloads = report_bytes(summary)
    verify_plan(plan)
    directory = validate_output(directory, plan)
    directory.mkdir(parents=True, exist_ok=False)
    manifest = {name: copy.deepcopy(plan[name]) for name in PLAN_FIELDS}
    manifest.update(status="writing", created_at=datetime.now(timezone.utc).isoformat(),
                    selection_performed=False, recommendation=None,
                    analysis_scope="post_hoc_exploratory_eight_development_groups",
                    cost_interpretation="counterfactual_saved_prefix_costs_not_realized_savings_or_new_latency_benchmark",
                    output_sha256={name: digest(data) for name, data in payloads.items()})
    try:
        recovery.atomic_json(directory / "run-manifest.json", manifest)
        for name, data in payloads.items():
            with (directory / name).open("xb") as output:
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
        verify_plan(plan)
        manifest["status"] = "complete"
        manifest["snapshot_sha256"] = snapshot_hash({name: manifest[name] for name in
            (*PLAN_FIELDS, "selection_performed", "recommendation", "analysis_scope",
             "cost_interpretation", "output_sha256")})
        recovery.atomic_json(directory / "run-manifest.json", manifest)
        verify_plan(plan)
    except BaseException as exc:
        manifest.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        try:
            recovery.atomic_json(directory / "run-manifest.json", manifest)
        except OSError:
            pass
        raise
    return manifest


def analyze_run(directory):
    """Rebuild a completed comparison read-only from its audited source traces."""
    directory = Path(directory).resolve()
    manifest = strict_json((directory / "run-manifest.json").read_text(encoding="utf-8"))
    if manifest.get("experiment_id") != EXPERIMENT_ID or manifest.get("status") != "complete":
        raise ValueError("Reanalysis requires a complete offline policy comparison")
    if (manifest.get("selection_performed") is not False or manifest.get("recommendation") is not None
            or manifest.get("analysis_scope") != "post_hoc_exploratory_eight_development_groups"
            or manifest.get("additional_model_calls") != 0):
        raise ValueError("Offline comparison must remain exploratory without policy selection or inference")
    fields = (*PLAN_FIELDS, "selection_performed", "recommendation", "analysis_scope",
              "cost_interpretation", "output_sha256")
    if manifest.get("snapshot_sha256") != snapshot_hash({name: manifest[name] for name in fields}):
        raise ValueError("Offline comparison manifest snapshot hash differs")
    verify_plan(manifest)
    plan = load_plan(Path(manifest["configuration_path"]),
                     Path(manifest["source_run_snapshot"]["directory"]))
    for name in PLAN_FIELDS:
        if canonical(manifest.get(name)) != canonical(plan.get(name)):
            raise ValueError(f"Saved offline comparison plan differs: {name}")
    summary = build_report(plan)
    payloads = report_bytes(summary)
    if set(manifest["output_sha256"]) != set(REPORT_FILES):
        raise ValueError("Offline comparison output inventory differs")
    for name, expected in payloads.items():
        actual = (directory / name).read_bytes()
        if digest(actual) != manifest["output_sha256"][name] or actual != expected:
            raise ValueError(f"Saved report disagrees with deterministic recomputation: {name}")
    verify_plan(plan)
    return {"offline_audit": "passed", "status": "complete", "summary_reproduced": True,
            "comparison_rows": len(summary["comparisons"]),
            "question_rows": len(summary["per_question"]),
            "additional_model_calls": 0, "selection_performed": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--source-run", type=Path)
    parser.add_argument("--output-dir", type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--analyze-run", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.analyze_run is not None:
            if args.config or args.source_run or args.output_dir:
                raise ValueError("--analyze-run accepts only a saved comparison directory")
            print(json.dumps(analyze_run(args.analyze_run), indent=2, allow_nan=False))
            return 0
        plan = load_plan(args.config or CONFIG_PATH, args.source_run or DEFAULT_SOURCE)
        directory = validate_output(args.output_dir or DEFAULT_OUTPUT, plan, require_new=not args.dry_run)
        if args.dry_run:
            preview = {name: plan[name] for name in PLAN_FIELDS}
            print(json.dumps({**preview, "output_dir": str(directory),
                              "output_exists": directory.exists()}, indent=2, allow_nan=False))
            return 0
        summary = build_report(plan)
        write_reports(directory, plan, summary)
        print(f"complete: {len(summary['comparisons'])} comparisons and {len(summary['per_question'])} question decisions in {directory}; zero model calls; no policy selected")
        return 0
    except ERRORS as exc:
        print(f"Offline comparison failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
