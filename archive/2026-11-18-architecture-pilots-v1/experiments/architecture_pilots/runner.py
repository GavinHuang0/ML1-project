"""Separate durable smaller-ensemble and sparse-communication experiments."""

import argparse
import copy
import json
import math
import os
from pathlib import Path
import sys
import time

from experiment_runtime import FileLock, PauseController, hardware_identity
from run_format_followup import (atomic_json, append_record, canonical, digest,
                                 installed_model, journal_records, snapshot_hash, strict_json)
from experiments.confirmation_pilot import runner as confirmed
from .protocol import (EXPECTED_CONFIGS, CONFIG_PATHS, PROTOCOLS, load_tasks,
                       cohort_metadata, call_positions, build_call)


ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOTS = {"five_agent": ROOT / "results/five-agent-pilot",
                "sparse_peer": ROOT / "results/sparse-peer-pilot"}
INFERENCE_LOCK = ROOT / "results/.architecture-inference.lock"
JOURNALS = ("generations.jsonl", "answers.jsonl")
REPORT_FILES = ("summary.json", "comparisons.csv", "per_question.csv")
SOURCE_FILES = (
    "run_five_agent_pilot.py", "run_five_agent_pilot.ps1",
    "run_sparse_peer_pilot.py", "run_sparse_peer_pilot.ps1",
    "config/five_agent_pilot.json", "config/sparse_peer_pilot.json",
    "experiments/architecture_pilots/__init__.py", "experiments/architecture_pilots/protocol.py",
    "experiments/architecture_pilots/runner.py", "experiments/architecture_pilots/analysis.py",
    "experiments/confirmation_pilot/runner.py", *confirmed.SOURCE_FILES,
)
PLAN_FIELDS = ("preset", "experiment_id", "configuration_path", "configuration_sha256",
               "configuration_snapshot", "protocol_snapshot", "protocol_sha256", "schema_sha256",
               "tasks_snapshot", "cohort", "profile_reference", "execution_environment",
               "source_sha256", "call_positions", "planned_new_calls", "planned_initial_calls",
               "planned_revision_calls")
SNAPSHOT_FIELDS = (*PLAN_FIELDS, "hardware_snapshot", "model_digest", "ollama_version")
ERRORS = confirmed.ERRORS
PilotClient = confirmed.PilotClient
evaluate_generation = confirmed.evaluate_generation
load_reference = confirmed.load_reference
load_environment = confirmed.load_environment
verify_sources = confirmed.verify_sources
now = confirmed.now


def source_hashes(config_path, reference):
    paths = {str(ROOT / name) for name in SOURCE_FILES}
    paths.add(str(Path(config_path).resolve()))
    paths.update(reference["source_sha256"])
    paths.update(reference["evidence_sha256"])
    return {name: digest(Path(name).read_bytes()) for name in sorted(paths)}


def load_plan(preset="five_agent", config_path=None):
    if preset not in EXPECTED_CONFIGS:
        raise ValueError("Unknown architecture experiment")
    path = Path(config_path or CONFIG_PATHS[preset]).resolve()
    data = path.read_bytes()
    config = strict_json(data.decode("utf-8"))
    if canonical(config) != canonical(EXPECTED_CONFIGS[preset]):
        raise ValueError("Configuration differs from the frozen architecture experiment")
    tasks = load_tasks()
    reference = load_reference()
    environment = load_environment(reference)
    positions = call_positions(tasks, config)
    initial = len(tasks) * config["num_agents"]
    total = initial * 7
    if (len(positions) != total or sum(row["round"] == 0 for row in positions) != initial
            or any(row["split"] != "development" for row in positions)):
        raise ValueError("Call schedule differs from the matched full-trajectory design")
    return {"preset": preset, "experiment_id": config["experiment_id"],
            "configuration_path": str(path), "configuration_sha256": digest(data),
            "configuration_snapshot": config, "protocol_snapshot": copy.deepcopy(PROTOCOLS[preset]),
            "protocol_sha256": snapshot_hash(PROTOCOLS[preset]),
            "schema_sha256": snapshot_hash(confirmed.STRICT_SCHEMA),
            "tasks_snapshot": tasks, "cohort": cohort_metadata(tasks),
            "profile_reference": reference, "execution_environment": environment,
            "source_sha256": source_hashes(path, reference), "call_positions": positions,
            "planned_new_calls": total, "planned_initial_calls": initial,
            "planned_revision_calls": total - initial}


def verify_hardware(expected):
    current = hardware_identity()
    changes = {key: {"expected": expected.get(key), "observed": current.get(key)}
               for key in set(expected) | set(current) if expected.get(key) != current.get(key)}
    if changes:
        raise ValueError("Hardware differs from the frozen experiment environment: "
                         + json.dumps(changes, sort_keys=True))


def verify_runtime(client, manifest, check_hardware=False):
    verify_sources(manifest)
    health, model = installed_model(client)
    if health["version"] != manifest["ollama_version"] or model["digest"] != manifest["model_digest"]:
        raise ValueError("Model digest or Ollama version differs from the selected profile")
    if check_hardware:
        verify_hardware(manifest["hardware_snapshot"])


def checkpoint(directory, manifest):
    evidence = {}
    for name in JOURNALS:
        data = (directory / name).read_bytes()
        evidence[name] = {"records": len(data.splitlines()), "sha256": digest(data)}
    manifest["evidence_checkpoint"] = evidence
    manifest["calls_completed"] = evidence["answers.jsonl"]["records"]
    manifest["generations_saved"] = evidence["generations.jsonl"]["records"]
    atomic_json(directory / "run-manifest.json", manifest)


def audit_resume(directory, manifest, plan):
    for field in PLAN_FIELDS:
        if canonical(manifest.get(field)) != canonical(plan.get(field)):
            raise ValueError(f"Resume snapshot/protocol differs: {field}")
    if manifest.get("snapshot_sha256") != snapshot_hash({name: manifest[name] for name in SNAPSHOT_FIELDS}):
        raise ValueError("Run snapshot hash mismatch")
    for field in ("model_digest", "ollama_version"):
        if manifest[field] != plan["profile_reference"][field]:
            raise ValueError(f"Selected-profile identity differs: {field}")
    if manifest["hardware_snapshot"] != plan["execution_environment"]["hardware_snapshot"]:
        raise ValueError("Saved hardware differs from the frozen experiment environment")
    verify_sources(manifest)
    parsed = []
    for name in JOURNALS:
        records, lines = journal_records(directory / name)
        saved = manifest["evidence_checkpoint"][name]
        count = saved["records"]
        if (type(count) is not int or count < 0 or len(records) < count or len(records) > count + 1
                or digest(b"".join(lines[:count])) != saved["sha256"]):
            raise ValueError(f"Evidence prefix hash/count mismatch: {name}")
        parsed.append(records)
    if (manifest.get("calls_completed") != manifest["evidence_checkpoint"]["answers.jsonl"]["records"]
            or manifest.get("generations_saved") != manifest["evidence_checkpoint"]["generations.jsonl"]["records"]):
        raise ValueError("Manifest counters disagree with the durable checkpoint")
    generations, answers = parsed
    if len(generations) > plan["planned_new_calls"] or not 0 <= len(generations) - len(answers) <= 1:
        raise ValueError("Journals do not form a durable canonical call prefix")
    tasks = {task["id"]: task for task in plan["tasks_snapshot"]}
    checked = []
    for index, generation in enumerate(generations):
        if generation.get("type") != "generation":
            raise ValueError("Unexpected raw journal record type")
        expected = build_call(plan, index, checked)
        for name, value in expected.items():
            if canonical(generation.get(name)) != canonical(value):
                raise ValueError(f"Saved call violates canonical prompt/position/routing: {name}")
        elapsed = generation.get("elapsed_seconds")
        if type(elapsed) not in (int, float) or not math.isfinite(elapsed) or elapsed < 0:
            raise ValueError("Invalid model-request duration")
        answer = evaluate_generation(generation, tasks[generation["question_id"]])
        if index < len(answers) and answer != answers[index]:
            raise ValueError("Saved answer disagrees with raw calculator evaluation")
        checked.append(answer)
    return generations, answers


def summarize(manifest, answers):
    from .analysis import summarize as analyze
    return analyze(manifest, [row for row in answers if row["round"] == 0],
                   [row for row in answers if row["round"] > 0])


def finish_reports(directory, manifest, answers):
    from .analysis import report_bytes
    payloads = report_bytes(summarize(manifest, answers))
    if set(payloads) != set(REPORT_FILES):
        raise ValueError("Unexpected completed report inventory")
    for name, data in payloads.items():
        path = directory / name
        if path.exists():
            if path.read_bytes() != data:
                raise ValueError(f"Existing report differs; refusing overwrite: {name}")
        else:
            with path.open("xb") as output:
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
    manifest["output_sha256"] = {name: digest(data) for name, data in payloads.items()}


def execute(directory, plan, client, manifest, generations, answers, pause):
    total = plan["planned_new_calls"]
    tasks = {task["id"]: task for task in plan["tasks_snapshot"]}
    manifest.update(status="running", last_started_at=now())
    manifest.pop("error", None)
    manifest.setdefault("segments", []).append({"started_at": now(), "calls_before": len(answers)})
    checkpoint(directory, manifest)
    code = 0
    try:
        with (directory / JOURNALS[0]).open("ab") as raw_output, (directory / JOURNALS[1]).open("ab") as answer_output:
            if len(generations) > len(answers):
                generation = generations[-1]
                answer = evaluate_generation(generation, tasks[generation["question_id"]])
                append_record(answer_output, answer)
                answers.append(answer)
                checkpoint(directory, manifest)
            for index in range(len(generations), total):
                if pause.requested():
                    manifest["status"], code = "paused", 2
                    break
                verify_runtime(client, manifest)
                call = build_call(plan, index, answers)
                manifest["active_call"] = {name: call[name] for name in
                                           ("call_index", "question_id", "round", "agent_id", "arm")}
                checkpoint(directory, manifest)
                started = time.perf_counter()
                raw = client.chat("llama3.2:3b", call["messages"], seed=call["seed"],
                                  temperature=0.7, max_tokens=1024, format_value=call["format"])
                generation = {**copy.deepcopy(call), "type": "generation", "raw": raw,
                              "elapsed_seconds": time.perf_counter() - started}
                append_record(raw_output, generation)
                generations.append(generation)
                checkpoint(directory, manifest)
                answer = evaluate_generation(generation, tasks[call["question_id"]])
                append_record(answer_output, answer)
                answers.append(answer)
                manifest.pop("active_call", None)
                checkpoint(directory, manifest)
                print(f"Saved {len(answers)}/{total}: {call['question_id']} round {call['round']} "
                      f"agent {call['agent_id']} {call['arm']}", flush=True)
                if pause.requested():
                    manifest["status"], code = "paused", 2
                    break
        if len(answers) == total:
            verify_runtime(client, manifest, check_hardware=True)
            finish_reports(directory, manifest, answers)
            manifest["status"], code = "complete", 0
    except KeyboardInterrupt:
        manifest.update(status="interrupted", error="Forced interruption; durable replies recover on resume")
        code = 130
    except ERRORS as exc:
        manifest.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        print(f"Architecture experiment stopped: {exc}", file=sys.stderr)
        code = 1
    finally:
        manifest["segments"][-1].update(finished_at=now(), calls_after=len(answers), status=manifest["status"])
        manifest["updated_at"] = now()
        checkpoint(directory, manifest)
    print(f"{manifest['status']}: {len(answers)}/{total} calls saved in {directory}")
    return code


def validate_output(path, preset):
    candidate = Path(path).absolute()
    directory = candidate.resolve()
    root = OUTPUT_ROOTS[preset].resolve()
    if directory != candidate or root != OUTPUT_ROOTS[preset].absolute():
        raise ValueError("Output must use a direct canonical path without links or junctions")
    if directory == root or not directory.is_relative_to(root):
        raise ValueError(f"Output must be a run folder beneath {root}")
    return directory


def analyze_run(directory, preset="five_agent"):
    directory = validate_output(directory, preset)
    with FileLock(directory / ".pilot.lock"):
        manifest = strict_json((directory / "run-manifest.json").read_text(encoding="utf-8"))
        if manifest.get("status") in {"running", "initializing"}:
            raise ValueError("Pause the active writer before analysis")
        plan = load_plan(preset, Path(manifest["configuration_path"]))
        generations, answers = audit_resume(directory, manifest, plan)
        result = {"offline_audit": "passed", "preset": preset, "status": manifest["status"],
                  "generations_saved": len(generations), "calls_completed": len(answers),
                  "summary_reproduced": None, "analysis_model_calls": 0}
        if manifest.get("status") == "complete":
            if len(generations) != plan["planned_new_calls"] or len(answers) != plan["planned_new_calls"]:
                raise ValueError("Completed run has incomplete evidence")
            from .analysis import report_bytes
            payloads = report_bytes(summarize(manifest, answers))
            if set(manifest.get("output_sha256", {})) != set(REPORT_FILES):
                raise ValueError("Completed output inventory differs")
            for name, expected in payloads.items():
                actual = (directory / name).read_bytes()
                if actual != expected or digest(actual) != manifest["output_sha256"][name]:
                    raise ValueError(f"Saved report differs from deterministic recomputation: {name}")
            result.update(summary_reproduced=True, comparison_rows=8, question_rows=96,
                          selection_performed=False)
        verify_sources(manifest)
        return result


def main(argv=None, *, preset="five_agent"):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--timeout", type=float, default=600)
    parser.add_argument("--dry-run", action="store_true")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--resume", action="store_true")
    mode.add_argument("--pause", action="store_true")
    mode.add_argument("--analyze-run", type=Path)
    args = parser.parse_args(argv)
    try:
        if preset not in EXPECTED_CONFIGS:
            raise ValueError("Unknown architecture experiment")
        if args.analyze_run:
            if args.config or args.output_dir or args.dry_run:
                raise ValueError("--analyze-run accepts only a saved run directory")
            print(json.dumps(analyze_run(args.analyze_run, preset), indent=2, allow_nan=False))
            return 0
        directory = validate_output(args.output_dir or OUTPUT_ROOTS[preset] / "windows-v1", preset)
        if args.pause:
            if args.config or args.dry_run:
                raise ValueError("--pause accepts only the run destination")
            saved = strict_json((directory / "run-manifest.json").read_text(encoding="utf-8"))
            if saved.get("experiment_id") != EXPECTED_CONFIGS[preset]["experiment_id"] or saved.get("status") == "complete":
                raise ValueError("No incomplete matching architecture experiment at this destination")
            (directory / ".pause-request").touch(exist_ok=True)
            print("Pause requested; the active call will be saved before stopping.")
            return 0
        if not math.isfinite(args.timeout) or args.timeout <= 0:
            raise ValueError("timeout must be positive and finite")
        if args.resume and args.dry_run:
            raise ValueError("--resume cannot be a dry run")
        if directory.exists() and not args.resume:
            raise ValueError("Output already exists; use --resume for this saved experiment")
        old = strict_json((directory / "run-manifest.json").read_text(encoding="utf-8")) if args.resume else None
        config_path = args.config or (Path(old["configuration_path"]) if old else CONFIG_PATHS[preset])
        plan = load_plan(preset, config_path)
        reference = plan["profile_reference"]
        execution_hardware = plan["execution_environment"]["hardware_snapshot"]
        if args.dry_run:
            verify_hardware(execution_hardware)
            config = plan["configuration_snapshot"]
            print(json.dumps({"experiment_id": plan["experiment_id"], "preset": preset,
                              "output_dir": str(directory), "cohort": plan["cohort"],
                              "num_agents": config["num_agents"], "peers_per_agent": config["peer_count"],
                              "planned_new_calls": plan["planned_new_calls"],
                              "shared_initial_calls": plan["planned_initial_calls"],
                              "revision_calls": plan["planned_revision_calls"],
                              "comparison_rows": 8, "question_rows": 96, "maximum_round": 3,
                              "voter": "current_round_plurality", "stopping": "fixed_rounds_0_to_3",
                              "model_digest": reference["model_digest"], "ollama_version": reference["ollama_version"],
                              "hardware_check": "passed", "service_contacted": False,
                              "task_ids": [task["id"] for task in plan["tasks_snapshot"]],
                              "routing_preview": [row for row in plan["call_positions"]
                                                  if row["round"] == 1 and row["arm"] == "communication"][:3]},
                             indent=2, allow_nan=False))
            return 0
        client = PilotClient(timeout=args.timeout)
        identity = {**plan, **{key: reference[key] for key in ("model_digest", "ollama_version")},
                    "hardware_snapshot": execution_hardware}
        verify_runtime(client, identity, check_hardware=True)
        # The two experiments run separately against one local model service.
        # This cross-experiment lock prevents their inference from interleaving.
        with FileLock(INFERENCE_LOCK):
            if not args.resume:
                directory.mkdir(parents=True, exist_ok=False)
            with FileLock(directory / ".pilot.lock"), PauseController(directory / ".pause-request") as pause:
                if args.resume:
                    manifest = strict_json((directory / "run-manifest.json").read_text(encoding="utf-8"))
                    if manifest.get("status") == "complete":
                        raise ValueError("Experiment already complete; no inference will be replayed")
                    generations, answers = audit_resume(directory, manifest, plan)
                    verify_runtime(client, manifest, check_hardware=True)
                else:
                    for name in JOURNALS:
                        (directory / name).touch(exist_ok=False)
                    manifest = {**identity, "status": "initializing", "started_at": now(),
                                "request_timeout": args.timeout, "calls_completed": 0, "generations_saved": 0}
                    manifest["snapshot_sha256"] = snapshot_hash({name: manifest[name] for name in SNAPSHOT_FIELDS})
                    generations, answers = [], []
                    checkpoint(directory, manifest)
                pause.clear_request()
                return execute(directory, plan, client, manifest, generations, answers, pause)
    except KeyboardInterrupt:
        print("Setup interrupted; durable evidence remains available.", file=sys.stderr)
        return 130
    except ERRORS as exc:
        print(f"Architecture setup/resume failed: {exc}", file=sys.stderr)
        return 1
