"""Run the preregistered study with portable, durable per-call checkpoints."""

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import sys

import run_multi_agent as primary
from multi_agent_protocol import read_config, read_tasks
from experiment_runtime import FileLock, PauseController, hardware_identity
import study_trajectory


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config" / "full_experiment.json"
STUDY_ID = "ml1-full-study-v1"
PHASES = ("development", "validation", "test")
CONDITIONS = ("all_to_all", "self_revision")
FROZEN_DESIGN = {
    "base_protocol_sha256": "c201800643b4ab420da0c20a90a0bfe8e52906c741cf91cca7b4e430d81a7066",
    "conditions": list(CONDITIONS), "shared_initial_panel": True,
    "sampling_replicates": 1, "development_questions": 20,
    "validation_questions": 40, "test_questions": 40,
    "families": ["algebra", "evidence", "reasoning", "units"],
    "groups_per_family": 13, "questions_per_family": 25,
    "development_groups_per_family": 3, "validation_groups_per_family": 5, "test_groups_per_family": 5,
    "round_selection_condition": "all_to_all",
    "uncertainty_unit": "structural_problem_group",
    "execution_order": "development_then_validation_then_test",
    "checkpoint_unit": "durable_completed_model_call",
    "failed_question_policy": "stop_then_explicit_resume_at_next_pending_call",
    "hardware_policy": "same_machine_os_cpu_memory_model_digest_and_ollama_version",
    "matching": "equal_generation_counts_shared_round_zero_not_equal_token_budgets",
}
EXTRA_SOURCES = ("run_full_experiment.py", "run_self_revision.py", "full_experiment_analysis.py",
                 "build_full_benchmark.py", "experiment_runtime.py", "study_trajectory.py")


class StudyPaused(Exception):
    pass


def read_study(path):
    path = Path(path).resolve()
    data = path.read_bytes()
    config = primary.strict_json(data.decode("utf-8"))
    if (set(config) != {"schema_version", "study_id", "base_config", "task_manifest", "design"}
            or type(config["schema_version"]) is not int or config["schema_version"] != 1
            or config["study_id"] != STUDY_ID
            or primary.snapshot_hash(config["design"]) != primary.snapshot_hash(FROZEN_DESIGN)):
        raise ValueError("Study configuration differs from the frozen full experiment design")
    base_path = (path.parent / config["base_config"]).resolve()
    tasks_path = (path.parent / config["task_manifest"]).resolve()
    _, base_hash = read_config(base_path)
    if primary.protocol_hash() != FROZEN_DESIGN["base_protocol_sha256"]:
        raise ValueError("The original multi-agent protocol changed")
    tasks, task_hash = read_tasks(tasks_path)
    validate_benchmark(tasks)
    return config, primary.digest_bytes(data), base_path, tasks_path, tasks, task_hash, base_hash


def validate_benchmark(tasks):
    counts = Counter((t["split"], t["family"]) for t in tasks)
    expected = {(split, family): FROZEN_DESIGN[split + "_questions"] // 4
                for split in PHASES for family in FROZEN_DESIGN["families"]}
    if counts != expected:
        raise ValueError("Full benchmark requires 20 development, 40 validation, 40 test questions balanced by family")
    groups = {}
    for task in tasks:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}", task["id"]):
            raise ValueError("Question IDs must be safe single filesystem components")
        group = task.get("group_id")
        if not isinstance(group, str) or not group:
            raise ValueError("Every full-study question requires a structural group_id")
        identity = (task["family"], task["split"])
        if group in groups and groups[group] != identity:
            raise ValueError("A structural problem group crosses family or split")
        groups[group] = identity
    if Counter(family for family, _ in groups.values()) != Counter(
            {family: FROZEN_DESIGN["groups_per_family"] for family in FROZEN_DESIGN["families"]}):
        raise ValueError("Expected thirteen structural groups per family")
    if Counter((split, family) for family, split in groups.values()) != Counter({
            (split, family): FROZEN_DESIGN[split + "_groups_per_family"]
            for split in PHASES for family in FROZEN_DESIGN["families"]}):
        raise ValueError("Each family needs three development, five validation, and five test groups")


def sources(config_path, base_path, tasks_path):
    paths = {ROOT / name for name in (*primary.SOURCE_FILES, *EXTRA_SOURCES)}
    paths.update({Path(config_path), Path(base_path), Path(tasks_path)})
    return {str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path):
            primary.digest_bytes(path.read_bytes()) for path in sorted(paths)}


def verify_input_hashes(config_path, config_hash, base_path, base_hash, tasks_path, task_hash, source_map):
    for path, expected in ((config_path, config_hash), (base_path, base_hash), (tasks_path, task_hash)):
        path = Path(path).resolve()
        key = str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)
        if source_map.get(key) != expected or primary.digest_bytes(path.read_bytes()) != expected:
            raise ValueError("A study configuration or benchmark changed after its snapshot was read")


def planned_schedule(tasks):
    phases = {}
    for split in PHASES:
        selected = [t for t in tasks if t["split"] == split]
        phases[split] = {"questions": len(selected), "structural_groups": len({t["group_id"] for t in selected}),
                         "primary_new_calls": 40 * len(selected), "control_new_calls": 30 * len(selected),
                         "total_new_calls": 70 * len(selected)}
    return {"study_id": STUDY_ID, "phases": phases, "total_new_calls": 70 * len(tasks),
            "primary_trajectory_hours_at_pilot_rate": len(tasks) * 486.9677960932022 / 3600,
            "estimated_total_hours_including_self_revision": [20, 30],
            "notes": ["Estimate uses the completed four-question development pilot; new task difficulty can change runtime.",
                      "Each condition evaluates forty generations per question; ten initial responses are shared.",
                      "Self-revision matches generation counts, not communication tokens.",
                      "Repeated fixed-seed runs are reproducibility checks, not independent replicates."]}


def verify_frozen(manifest, config_path, base_path, tasks_path):
    if sources(config_path, base_path, tasks_path) != manifest["source_sha256"]:
        raise ValueError("Study sources or frozen inputs changed; create a separately versioned study")
    if hardware_identity() != manifest["hardware"]:
        raise ValueError("Execution hardware or operating system changed; do not mix time measurements")


def check_runtime(manifest, timeout):
    client = primary.OllamaClient(timeout=timeout)
    health, model = primary.installed_model(client)
    identity = {"model_digest": model["digest"], "ollama_version": health["version"]}
    if manifest.get("runtime") is not None and identity != manifest["runtime"]:
        raise ValueError("Ollama version or model digest changed since the study began")
    manifest["runtime"] = identity


def load_control():
    import run_self_revision
    return run_self_revision


def child_data(directory, condition):
    directory = Path(directory)
    if condition == "all_to_all":
        primary.analyze_run(directory)
    else:
        load_control().analyze_run(directory)
    records = [r for r in primary.jsonl(directory / "answers.jsonl") if r.get("type") == "answer"]
    rounds = primary.jsonl(directory / "rounds.jsonl")
    manifest = primary.strict_json((directory / "run-manifest.json").read_text())
    return manifest, records, rounds


def completed_child(manifest, task, condition):
    attempts = manifest["children"].get(task["id"], {}).get(condition, [])
    for attempt in attempts:
        path = Path(attempt["directory"])
        state_path = path / "run-manifest.json"
        if not state_path.exists():
            continue
        state = primary.strict_json(state_path.read_text())
        if state.get("status") != "complete":
            continue
        _, records, _ = child_data(path, condition)
        if len(records) != 40 or {r["question_id"] for r in records} != {task["id"]}:
            raise ValueError("Completed checkpoint does not match its scheduled question")
        if condition == "all_to_all" and state["tasks_snapshot"] != [task]:
            raise ValueError("Completed question checkpoint has changed references or metadata")
        if attempt.get("manifest_sha256") and attempt["manifest_sha256"] != primary.digest_bytes(state_path.read_bytes()):
            raise ValueError("A completed checkpoint manifest changed")
        if state.get("ollama_version") != manifest["runtime"]["ollama_version"]:
            raise ValueError("Completed checkpoint Ollama runtime differs from this study")
        digest = state.get("model_metadata", {}).get("digest")
        if digest is not None and digest != manifest["runtime"]["model_digest"]:
            raise ValueError("Completed checkpoint model differs from this study")
        return path
    return None


def attempt_overhead(manifest, split=None):
    """Keep discarded attempts visible as actual expenditure, not scored evidence."""
    failed, uncertain_calls = [], []
    task_splits = {t["id"]: t["split"] for t in manifest["tasks_snapshot"]}
    for question_id, conditions in manifest["children"].items():
        if split is not None and task_splits[question_id] != split:
            continue
        for condition, attempts in conditions.items():
            for attempt in attempts:
                path = Path(attempt["directory"])
                state = path / "run-manifest.json"
                if state.exists():
                    child_state = primary.strict_json(state.read_text())
                    for item in child_state.get("attempts", []):
                        if item.get("status") != "complete":
                            uncertain_calls.append({"question_id": question_id, "condition": condition,
                                "directory": str(path), **item})
                    if child_state.get("status") == "complete":
                        continue
                rows = []
                journal = path / "generations.jsonl"
                if journal.exists():
                    for line in journal.read_text().splitlines():
                        try:
                            row = primary.strict_json(line)
                        except (ValueError, TypeError):
                            continue
                        if not row.get("reused_round_zero"):
                            rows.append(row)
                def tokens(field):
                    values = [r.get("raw", {}).get(field) for r in rows]
                    return sum(values) if all(type(v) is int and v >= 0 for v in values) else None
                failed.append({"question_id": question_id, "condition": condition, "directory": str(path),
                               "completed_generations": len(rows), "input_tokens": tokens("prompt_eval_count"),
                               "output_tokens": tokens("eval_count"),
                               "recorded_call_seconds": sum(r.get("elapsed_seconds", 0) for r in rows),
                               "note": "Discarded attempt; failed calls without a returned generation can add unmeasured cost."})
    return {"discarded_attempts": failed, "completed_generations": sum(x["completed_generations"] for x in failed),
            "uncertain_call_attempts": uncertain_calls,
            "note": "Returned-generation budgets exclude unknown token costs of calls without a response; active wall timing records attempted work and excludes human pauses."}


def save_manifest(root, manifest):
    primary.write_json(root / "study-manifest.json", manifest)


def question_input(root, task, manifest):
    path = root / "inputs" / (task["id"] + ".json")
    expected = {"schema_version": 1,
                "source": {"study_id": STUDY_ID, "benchmark_sha256": manifest["benchmark_sha256"],
                           "scope": "One whole question; references remain local."},
                "tasks": [task]}
    if path.exists():
        if primary.strict_json(path.read_text()) != expected:
            raise ValueError("A checkpoint question input changed")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        primary.write_json(path, expected, exclusive=True)
    return path


def run_question(root, manifest, task, condition, base_path, timeout, calibration_path, selection_path, pause=None):
    ready = completed_child(manifest, task, condition)
    if ready is not None:
        print(f"Reuse complete {condition}: {task['id']}", flush=True)
        return ready
    attempts = manifest["children"].setdefault(task["id"], {}).setdefault(condition, [])
    if attempts:
        attempt = attempts[-1]
        path = Path(attempt["directory"])
        resume_child = (path / "run-manifest.json").exists()
        if path.exists() and not resume_child:
            raise ValueError("Incomplete child setup without a checkpoint; preserve it for inspection")
    else:
        path = root / "questions" / task["split"] / task["id"] / condition / "attempt-001"
        if path.exists():
            raise ValueError("Unexpected existing attempt directory; inspect the study manifest")
        attempt = {"directory": str(path), "status": "running", "started_at": primary.now()}
        attempts.append(attempt)
        resume_child = False
    manifest["active_question"] = {"question_id": task["id"], "condition": condition}
    attempt.update(status="running", last_started_at=primary.now())
    save_manifest(root, manifest)
    print(f"Run {condition}: {task['id']} ({task['split']})", flush=True)
    parent = completed_child(manifest, task, "all_to_all") if condition == "self_revision" else None
    if condition == "self_revision" and parent is None:
        raise ValueError("Self-revision requires its completed primary initial panel")
    code = study_trajectory.run_question(config_path=base_path, tasks_path=question_input(root, task, manifest),
        output_dir=path, condition=condition, parent_run=parent, calibration=calibration_path,
        selection=selection_path, timeout=timeout, resume=resume_child,
        pause_requested=pause.requested if pause else None)
    attempt["finished_at"] = primary.now()
    if code == 2:
        attempt["status"] = "paused"
        save_manifest(root, manifest)
        raise StudyPaused
    if code != 0:
        attempt["status"] = "interrupted" if code == 130 else "failed"
        save_manifest(root, manifest)
        if code == 130:
            raise KeyboardInterrupt
        raise RuntimeError(f"{condition} stopped for {task['id']}; resume explicitly at the next pending call")
    child_data(path, condition)
    attempt.update(status="complete", manifest_sha256=primary.digest_bytes((path / "run-manifest.json").read_bytes()))
    save_manifest(root, manifest)
    return path


def collect_phase(manifest, tasks, split):
    data = {condition: {"records": [], "rounds": []} for condition in CONDITIONS}
    for task in tasks:
        if task["split"] != split:
            continue
        for condition in CONDITIONS:
            path = completed_child(manifest, task, condition)
            if path is None:
                raise ValueError(f"Phase {split} has an incomplete question/condition")
            _, records, rounds = child_data(path, condition)
            data[condition]["records"].extend(records)
            data[condition]["rounds"].extend(rounds)
    return data


def freeze_artifact(path, value):
    if path.exists():
        if primary.strict_json(path.read_text()) != value:
            raise ValueError("A frozen calibration/selection artifact would change")
    else:
        primary.write_json(path, value, exclusive=True)
    return primary.digest_bytes(path.read_bytes())


def finalize_phase(root, manifest, tasks, split, calibration_path, selection_path):
    from full_experiment_analysis import summarize_study
    chosen = [task for task in tasks if task["split"] == split]
    data = collect_phase(manifest, tasks, split)
    references = primary.read_calibration(calibration_path)[0]["references"] if calibration_path else None
    selection = primary.read_selection(selection_path)[0]["primary_round"] if selection_path else None
    report = summarize_study(chosen, data["all_to_all"]["records"], data["all_to_all"]["rounds"],
                             data["self_revision"]["records"], data["self_revision"]["rounds"],
                             calibration=references, selected_round=selection)
    report["study_id"] = STUDY_ID
    report["hardware"] = manifest["hardware"]
    report["runtime"] = manifest["runtime"]
    report["execution_overhead"] = attempt_overhead(manifest, split)
    report_path = root / "reports" / (split + ".json")
    if report_path.exists():
        if primary.strict_json(report_path.read_text()) != report:
            raise ValueError("A completed phase report changed")
    else:
        primary.write_json(report_path, report, exclusive=True)
    runtime = manifest["runtime"]
    if split == "development":
        refs = report["primary"]["calibration"]
        if refs is None:
            raise ValueError("Complete development token and time measurements are required before validation")
        refs["source_group_ids"] = sorted({t["group_id"] for t in chosen})
        calibration = {"schema_version": 1, "experiment_id": primary.EXPERIMENT_ID,
                       "protocol_sha256": primary.protocol_hash(), **runtime,
                       "references": refs, "source_run": str(root),
                       "study_id": STUDY_ID, "hardware": manifest["hardware"],
                       "development_report_sha256": primary.digest_bytes(report_path.read_bytes())}
        path = root / "artifacts" / "calibration.json"
        manifest["calibration_sha256"] = freeze_artifact(path, calibration)
    elif split == "validation":
        selected = report["primary"]["selected_rounds"]["validation"]["primary"]["selected_round"]
        if type(selected) is not int:
            raise ValueError("Validation costs are incomplete; a primary round cannot be selected")
        selection = {"schema_version": 1, "experiment_id": primary.EXPERIMENT_ID,
                     "protocol_sha256": primary.protocol_hash(), **runtime,
                     "primary_round": selected, "primary_delta": primary.FROZEN_PROTOCOL["primary_delta"],
                     "primary_omega": primary.FROZEN_PROTOCOL["primary_omega"],
                     "calibration_sha256": manifest["calibration_sha256"],
                     "validation_question_ids": [t["id"] for t in chosen],
                     "validation_group_ids": sorted({t["group_id"] for t in chosen}),
                     "source_run": str(root), "study_id": STUDY_ID,
                     "validation_report_sha256": primary.digest_bytes(report_path.read_bytes())}
        manifest["selection_sha256"] = freeze_artifact(root / "artifacts" / "selection.json", selection)
    manifest["phases"][split] = {"status": "complete", "report": str(report_path),
                                "report_sha256": primary.digest_bytes(report_path.read_bytes())}
    save_manifest(root, manifest)
    return report


def check_phase_dependencies(root, manifest, split):
    calibration, selection = root / "artifacts" / "calibration.json", root / "artifacts" / "selection.json"
    index = PHASES.index(split)
    existing = manifest["phases"].get(split)
    if existing is not None:
        if primary.digest_bytes(Path(existing["report"]).read_bytes()) != existing["report_sha256"]:
            raise ValueError("The completed phase report changed")
        if split == "development" and primary.digest_bytes(calibration.read_bytes()) != manifest["calibration_sha256"]:
            raise ValueError("Frozen development calibration changed")
        if split == "validation" and primary.digest_bytes(selection.read_bytes()) != manifest["selection_sha256"]:
            raise ValueError("Frozen validation selection changed")
    for prerequisite in PHASES[:index]:
        phase = manifest["phases"].get(prerequisite, {})
        if phase.get("status") != "complete":
            raise ValueError(f"Complete the {prerequisite} phase before {split}")
        if primary.digest_bytes(Path(phase["report"]).read_bytes()) != phase["report_sha256"]:
            raise ValueError("A prerequisite phase report changed")
    if index >= 1:
        if primary.digest_bytes(calibration.read_bytes()) != manifest["calibration_sha256"]:
            raise ValueError("Frozen development calibration changed")
        if primary.read_calibration(calibration)[0].get("hardware") != manifest["hardware"]:
            raise ValueError("Calibration execution hardware changed")
    if index == 2 and primary.digest_bytes(selection.read_bytes()) != manifest["selection_sha256"]:
        raise ValueError("Frozen validation selection changed")
    return (calibration if index >= 1 else None, selection if index == 2 else None)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--phase", choices=(*PHASES, "all"), default="development")
    parser.add_argument("--timeout", type=float, default=600)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--pause", action="store_true", help="Request a cooperative pause in another running process")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    root, manifest, study_lock, writable_manifest, pause = None, None, None, False, None
    try:
        if args.pause:
            if args.output_dir is None or not (args.output_dir / "study-manifest.json").exists():
                raise ValueError("--pause requires an existing study --output-dir")
            (args.output_dir / ".pause-request").touch(exist_ok=True)
            print("Pause requested; wait for the current model call to be saved and the runner to report paused.")
            return 0
        if not math.isfinite(args.timeout) or args.timeout <= 0:
            raise ValueError("timeout must be positive and finite")
        config_path = args.config.resolve()
        config, config_hash, base_path, tasks_path, tasks, benchmark_hash, base_hash = read_study(config_path)
        schedule = planned_schedule(tasks)
        if args.dry_run:
            print(json.dumps({**schedule, "requested_phase": args.phase, "configuration_sha256": config_hash,
                              "benchmark_sha256": benchmark_hash, "configuration_snapshot": config,
                              "dry_run": "No Ollama calls, directories, or result files created."}, indent=2))
            return 0
        if args.resume and args.output_dir is None:
            raise ValueError("--resume requires the original --output-dir")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        root = (args.output_dir or ROOT / "results" / "full-experiment" / (stamp + "-" + STUDY_ID)).resolve()
        if args.resume:
            study_lock = FileLock(root / ".study.lock").acquire()
            manifest = primary.strict_json((root / "study-manifest.json").read_text())
            if (manifest.get("study_id") != STUDY_ID or manifest.get("configuration_sha256") != config_hash
                    or manifest.get("benchmark_sha256") != benchmark_hash
                    or primary.snapshot_hash(manifest["configuration_snapshot"]) != primary.snapshot_hash(config)
                    or primary.snapshot_hash(manifest["tasks_snapshot"]) != primary.snapshot_hash(tasks)):
                raise ValueError("The checkpoint does not match this frozen study and benchmark")
            verify_frozen(manifest, config_path, base_path, tasks_path)
            verify_input_hashes(config_path, config_hash, base_path, base_hash, tasks_path, benchmark_hash,
                                manifest["source_sha256"])
            check_runtime(manifest, args.timeout)
            writable_manifest = True
        else:
            primary.validate_output_directory(root)
            manifest = {"schema_version": 1, "study_id": STUDY_ID, "status": "prepared",
                        "configuration_sha256": config_hash, "configuration_snapshot": config,
                        "benchmark_sha256": benchmark_hash, "tasks_snapshot": tasks,
                        "source_sha256": sources(config_path, base_path, tasks_path),
                        "hardware": hardware_identity(), "runtime": None,
                        "schedule": schedule, "phases": {}, "children": {}, "started_at": primary.now(),
                        "request_timeout": args.timeout, "git_revision": primary.git_output("rev-parse", "HEAD")}
            verify_input_hashes(config_path, config_hash, base_path, base_hash, tasks_path, benchmark_hash,
                                manifest["source_sha256"])
            check_runtime(manifest, args.timeout)
            root.mkdir(parents=True, exist_ok=False)
            study_lock = FileLock(root / ".study.lock").acquire()
            for name in ("reports", "artifacts"):
                (root / name).mkdir()
            save_manifest(root, manifest)
            writable_manifest = True
        manifest["status"] = "running"
        manifest["last_started_at"] = primary.now()
        save_manifest(root, manifest)
        pause = PauseController(root / ".pause-request")
        pause.clear_request()
        pause.__enter__()
        selected_phases = PHASES if args.phase == "all" else (args.phase,)
        for split in selected_phases:
            verify_frozen(manifest, config_path, base_path, tasks_path)
            calibration_path, selection_path = check_phase_dependencies(root, manifest, split)
            for task in tasks:
                if task["split"] != split:
                    continue
                for condition in CONDITIONS:
                    if pause.requested():
                        raise StudyPaused
                    verify_frozen(manifest, config_path, base_path, tasks_path)
                    run_question(root, manifest, task, condition, base_path, args.timeout,
                                 calibration_path, selection_path, pause)
            finalize_phase(root, manifest, tasks, split, calibration_path, selection_path)
            print(f"Phase complete: {split}. Report: {root / 'reports' / (split + '.json')}", flush=True)
        manifest["status"] = "complete" if all(p in manifest["phases"] for p in PHASES) else "ready_for_next_phase"
        manifest.pop("active_question", None)
        manifest["last_finished_at"] = primary.now()
        manifest.pop("error", None)
        save_manifest(root, manifest)
        pause.close()
        study_lock.close()
        return 0
    except StudyPaused:
        manifest.update(status="paused", last_paused_at=primary.now())
        save_manifest(root, manifest)
        pause.close()
        study_lock.close()
        print("Paused safely. Completed calls are saved; resume with --resume and the same output directory.")
        return 2
    except KeyboardInterrupt:
        error, code = "Interrupted by user", 130
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, ZeroDivisionError, RecursionError) as exc:
        error, code = str(exc), 1
    if writable_manifest and root is not None and manifest is not None and (root / "study-manifest.json").exists():
        manifest.update(status="interrupted" if code == 130 else "failed", error=error, last_finished_at=primary.now())
        save_manifest(root, manifest)
    if study_lock is not None:
        study_lock.close()
    if pause is not None:
        pause.close()
    print(f"Full study stopped: {error}", file=sys.stderr)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
