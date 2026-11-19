"""Durable five-agent development, validation-selection and locked-test study."""

import argparse
import copy
import json
import math
import os
from pathlib import Path
import sys
import time

from experiment_runtime import FileLock, PauseController, hardware_identity
from run_format_followup import (atomic_json, append_record, canonical, digest, installed_model,
                                 journal_records, snapshot_hash, strict_json)
from experiments.confirmation_pilot import runner as selected
from .protocol import (STUDY_ID, EXPECTED_CONFIG, PROTOCOL, CONFIG_PATH, PHASES,
                       STRICT_SCHEMA, load_tasks, phase_tasks, cohort_metadata,
                       call_positions, build_call)
from .progress import Progress
from .analysis import summarize_phase, report_bytes, create_calibration, choose_round


ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = ROOT / "results/full-experiment"
DEFAULT_OUTPUT = OUTPUT_ROOT / "study-v2"
INFERENCE_LOCK = ROOT / "results/.architecture-inference.lock"
JOURNALS = ("generations.jsonl", "answers.jsonl")
REPORT_FILES = ("summary.json", "comparisons.csv", "per_question.csv")
SOURCE_FILES = (
    "run_full_experiment.py", "run_full_experiment.ps1", "config/full_study_v2.json",
    "experiments/full_study_v2/__init__.py", "experiments/full_study_v2/protocol.py",
    "experiments/full_study_v2/runner.py", "experiments/full_study_v2/analysis.py",
    "experiments/full_study_v2/progress.py", "experiments/architecture_pilots/analysis.py",
    "experiments/architecture_pilots/protocol.py", "experiments/confirmation_pilot/runner.py",
    *selected.SOURCE_FILES,
)
IDENTITY_ARCHIVE = ROOT / "archive/2026-11-18-architecture-pilots-v1"
IDENTITY_MEMBER = "results/five-agent-pilot/windows-v1/run-manifest.json"
PLAN_FIELDS = ("study_id", "configuration_path", "configuration_sha256", "configuration_snapshot",
               "protocol_snapshot", "protocol_sha256", "schema_sha256", "tasks_snapshot", "cohort",
               "profile_reference", "execution_environment", "source_sha256", "planned_calls")
SNAPSHOT_FIELDS = (*PLAN_FIELDS, "hardware_snapshot", "model_digest", "ollama_version")
PHASE_FIELDS = ("study_id", "phase", "configuration_snapshot", "protocol_snapshot", "tasks_snapshot",
                "call_positions", "planned_new_calls", "source_sha256", "execution_environment",
                "calibration_snapshot", "selection_snapshot", "artifact_dependencies")
PHASE_SNAPSHOT_FIELDS = (*PHASE_FIELDS, "hardware_snapshot", "model_digest", "ollama_version")
ERRORS = selected.ERRORS
PilotClient = selected.PilotClient
evaluate_generation = selected.evaluate_generation
load_environment = selected.load_environment
now = selected.now


def json_bytes(value):
    return (json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def load_reference():
    """Read versioned identity evidence without requiring ignored old run paths.

    Historical absolute paths remain inside the archived evidence, but are
    never followed by this new study. No old model answers are imported.
    """
    inventory_path = IDENTITY_ARCHIVE / "SHA256_INVENTORY.json"
    inventory_raw = inventory_path.read_bytes()
    inventory = strict_json(inventory_raw.decode("utf-8"))
    entries = [entry for entry in inventory["files"] if entry["archive_path"] == IDENTITY_MEMBER]
    if len(entries) != 1:
        raise ValueError("Versioned selected-profile identity is missing from its archive inventory")
    path = IDENTITY_ARCHIVE / IDENTITY_MEMBER
    raw = path.read_bytes()
    if len(raw) != entries[0]["bytes"] or digest(raw) != entries[0]["sha256"]:
        raise ValueError("Versioned selected-profile manifest differs from its preserved bytes")
    record = strict_json(raw.decode("utf-8"))
    config = record["configuration_snapshot"]
    if (record.get("status") != "complete" or config.get("num_agents") != 5
            or config.get("peer_count") != 4 or config.get("selected_profile") != "strict_schema"
            or config["protocol"]["generation_protocol"]["format"] != STRICT_SCHEMA):
        raise ValueError("Archived identity must describe the completed selected five-agent profile")
    reference_hardware = copy.deepcopy(record["profile_reference"]["hardware_snapshot"])
    evidence = {str(path): digest(raw), str(inventory_path): digest(inventory_raw)}
    reference = {"directory": str(IDENTITY_ARCHIVE), "audit": "versioned_manifest_verified_against_archive_inventory",
                 "evidence_sha256": evidence, "source_sha256": {},
                 "model_digest": record["model_digest"], "ollama_version": record["ollama_version"],
                 "hardware_snapshot": reference_hardware,
                 "recorded_execution_hardware": copy.deepcopy(record["hardware_snapshot"]),
                 "profile": "strict_schema", "reused_answers": 0}
    environment = load_environment(reference)
    if environment["hardware_snapshot"] != record["hardware_snapshot"]:
        raise ValueError("Full-study environment differs from the archived selected-profile execution baseline")
    return reference


def source_hashes(config_path, reference):
    paths = {str(ROOT / name) for name in SOURCE_FILES}
    paths.add(str(Path(config_path).resolve()))
    paths.update(reference["source_sha256"])
    paths.update(reference["evidence_sha256"])
    return {name: digest(Path(name).read_bytes()) for name in sorted(paths)}


def load_plan(config_path=CONFIG_PATH):
    path = Path(config_path).resolve()
    raw = path.read_bytes()
    config = strict_json(raw.decode("utf-8"))
    if canonical(config) != canonical(EXPECTED_CONFIG):
        raise ValueError("Configuration differs from the frozen five-agent full study")
    tasks = load_tasks()
    reference = load_reference()
    environment = load_environment(reference)
    budgets = {phase: len(phase_tasks(tasks, phase)) * 35 for phase in PHASES}
    budgets["total"] = sum(budgets.values())
    return {"study_id": STUDY_ID, "configuration_path": str(path),
            "configuration_sha256": digest(raw), "configuration_snapshot": config,
            "protocol_snapshot": copy.deepcopy(PROTOCOL), "protocol_sha256": snapshot_hash(PROTOCOL),
            "schema_sha256": snapshot_hash(STRICT_SCHEMA), "tasks_snapshot": tasks,
            "cohort": cohort_metadata(tasks), "profile_reference": reference,
            "execution_environment": environment, "source_sha256": source_hashes(path, reference),
            "planned_calls": budgets}


def phase_plan(plan, phase, calibration=None, selection=None):
    tasks = phase_tasks(plan["tasks_snapshot"], phase)
    dependencies = {}
    for name, value in (("calibration.json", calibration), ("selection.json", selection)):
        if value is not None:
            dependencies[name] = {"sha256": digest(json_bytes(value)), "snapshot": copy.deepcopy(value)}
    return {"study_id": STUDY_ID, "phase": phase,
            "configuration_snapshot": copy.deepcopy(plan["configuration_snapshot"]),
            "protocol_snapshot": copy.deepcopy(plan["protocol_snapshot"]), "tasks_snapshot": tasks,
            "call_positions": call_positions(tasks, phase), "planned_new_calls": len(tasks) * 35,
            "source_sha256": copy.deepcopy(plan["source_sha256"]),
            "execution_environment": copy.deepcopy(plan["execution_environment"]),
            "calibration_snapshot": copy.deepcopy(calibration), "selection_snapshot": copy.deepcopy(selection),
            "artifact_dependencies": dependencies}


def verify_sources(manifest):
    for name, expected in manifest["source_sha256"].items():
        if digest(Path(name).read_bytes()) != expected:
            raise ValueError(f"Frozen source/input changed: {name}")


def verify_hardware(expected):
    actual = hardware_identity()
    differences = {key: {"expected": expected.get(key), "observed": actual.get(key)}
                   for key in set(expected) | set(actual) if expected.get(key) != actual.get(key)}
    if differences:
        raise ValueError("Hardware differs from the frozen study environment: "
                         + json.dumps(differences, sort_keys=True))


def verify_runtime(client, manifest, check_hardware=False):
    verify_sources(manifest)
    health, model = installed_model(client)
    if health["version"] != manifest["ollama_version"] or model["digest"] != manifest["model_digest"]:
        raise ValueError("Model digest or Ollama runtime differs from the frozen study")
    if check_hardware:
        verify_hardware(manifest["hardware_snapshot"])


def validate_output(path):
    requested = Path(path).absolute()
    directory = requested.resolve()
    root = OUTPUT_ROOT.resolve()
    if requested != directory or root != OUTPUT_ROOT.absolute():
        raise ValueError("Study output must use a direct canonical path without links or junctions")
    if directory == root or not directory.is_relative_to(root):
        raise ValueError(f"Study output must be a run directory beneath {root}")
    return directory


def save_study(directory, manifest):
    state = {key: manifest.get(key) for key in ("status", "phases", "artifact_sha256", "calls_completed",
                                               "generations_saved", "active_phase")}
    manifest["state_sha256"] = snapshot_hash(state)
    atomic_json(directory / "study-manifest.json", manifest)


def checkpoint(directory, manifest):
    inventory = {}
    for name in JOURNALS:
        data = (directory / name).read_bytes()
        inventory[name] = {"records": len(data.splitlines()), "sha256": digest(data)}
    manifest["evidence_checkpoint"] = inventory
    manifest["calls_completed"] = inventory["answers.jsonl"]["records"]
    manifest["generations_saved"] = inventory["generations.jsonl"]["records"]
    atomic_json(directory / "run-manifest.json", manifest)


def verify_dependencies(root, plan):
    for name, record in plan["artifact_dependencies"].items():
        actual = (root / "artifacts" / name).read_bytes()
        if digest(actual) != record["sha256"] or actual != json_bytes(record["snapshot"]):
            raise ValueError(f"Frozen phase dependency changed: {name}")


def audit_phase(directory, manifest, plan, identity):
    for field in PHASE_FIELDS:
        if canonical(manifest.get(field)) != canonical(plan.get(field)):
            raise ValueError(f"Phase snapshot/protocol differs: {field}")
    if manifest.get("snapshot_sha256") != snapshot_hash({name: manifest[name] for name in PHASE_SNAPSHOT_FIELDS}):
        raise ValueError("Phase snapshot hash mismatch")
    for field in ("hardware_snapshot", "model_digest", "ollama_version"):
        if manifest.get(field) != identity[field]:
            raise ValueError(f"Phase execution identity differs: {field}")
    verify_sources(manifest)
    parsed = []
    for name in JOURNALS:
        rows, lines = journal_records(directory / name)
        saved = manifest["evidence_checkpoint"][name]
        count = saved["records"]
        if (type(count) is not int or count < 0 or len(rows) < count or len(rows) > count + 1
                or digest(b"".join(lines[:count])) != saved["sha256"]):
            raise ValueError(f"Durable phase prefix changed: {name}")
        parsed.append(rows)
    generations, answers = parsed
    if (manifest.get("calls_completed") != manifest["evidence_checkpoint"]["answers.jsonl"]["records"]
            or manifest.get("generations_saved") != manifest["evidence_checkpoint"]["generations.jsonl"]["records"]
            or len(generations) > plan["planned_new_calls"]
            or not 0 <= len(generations) - len(answers) <= 1):
        raise ValueError("Phase journals do not form a durable canonical prefix")
    tasks = {task["id"]: task for task in plan["tasks_snapshot"]}
    checked = []
    for index, generation in enumerate(generations):
        if generation.get("type") != "generation":
            raise ValueError("Unexpected raw journal record type")
        expected = build_call(plan, index, checked)
        for field, value in expected.items():
            if canonical(generation.get(field)) != canonical(value):
                raise ValueError(f"Saved call violates canonical prompt/position/routing: {field}")
        elapsed = generation.get("elapsed_seconds")
        if type(elapsed) not in (int, float) or not math.isfinite(elapsed) or elapsed < 0:
            raise ValueError("Invalid measured phase request duration")
        answer = evaluate_generation(generation, tasks[generation["question_id"]])
        if index < len(answers) and answer != answers[index]:
            raise ValueError("Saved answer disagrees with raw calculator evaluation")
        checked.append(answer)
    return generations, answers


def phase_summary(plan, answers):
    return summarize_phase(plan, [row for row in answers if row["round"] == 0],
                           [row for row in answers if row["round"] > 0], plan["phase"],
                           plan["calibration_snapshot"], plan["selection_snapshot"])


def verify_reports(directory, manifest, summary):
    payloads = report_bytes(summary)
    if set(payloads) != set(REPORT_FILES) or set(manifest.get("output_sha256", {})) != set(REPORT_FILES):
        raise ValueError("Completed phase report inventory differs")
    for name, expected in payloads.items():
        actual = (directory / name).read_bytes()
        if actual != expected or digest(actual) != manifest["output_sha256"][name]:
            raise ValueError(f"Saved phase report differs from deterministic recomputation: {name}")


def freeze_file(path, data):
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError(f"Existing frozen artifact/report differs: {path.name}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as output:
        output.write(data)
        output.flush()
        os.fsync(output.fileno())


def audit_study(directory, manifest, plan):
    for field in PLAN_FIELDS:
        if canonical(manifest.get(field)) != canonical(plan.get(field)):
            raise ValueError(f"Study snapshot/protocol differs: {field}")
    if manifest.get("snapshot_sha256") != snapshot_hash({name: manifest[name] for name in SNAPSHOT_FIELDS}):
        raise ValueError("Study snapshot hash mismatch")
    state = {key: manifest.get(key) for key in ("status", "phases", "artifact_sha256", "calls_completed",
                                               "generations_saved", "active_phase")}
    if manifest.get("state_sha256") != snapshot_hash(state):
        raise ValueError("Study state hash mismatch")
    reference = plan["profile_reference"]
    for field in ("model_digest", "ollama_version"):
        if manifest[field] != reference[field]:
            raise ValueError(f"Study selected-profile identity differs: {field}")
    if manifest["hardware_snapshot"] != plan["execution_environment"]["hardware_snapshot"]:
        raise ValueError("Study hardware differs from its frozen environment")
    verify_sources(manifest)
    if set(manifest.get("phases", {})) - set(PHASES):
        raise ValueError("Unexpected phase in the study manifest")
    if set(manifest.get("artifact_sha256", {})) - {"calibration.json", "selection.json"}:
        raise ValueError("Unexpected frozen study artifact")
    found = {}
    calibration = selection = None
    expected_artifacts = {}
    pending = []
    blocked = False
    for phase in PHASES:
        path = directory / "phases" / phase
        recorded = manifest.get("phases", {}).get(phase)
        if not path.exists():
            if recorded is not None:
                raise ValueError("Manifest names a missing phase directory")
            blocked = True
            continue
        if blocked:
            raise ValueError("A later phase exists before its predecessor completed")
        if phase != "development" and calibration is None:
            raise ValueError("Validation/test cannot exist before development calibration")
        if phase == "test" and selection is None:
            raise ValueError("Test cannot exist before frozen validation selection")
        current_plan = phase_plan(plan, phase, calibration if phase != "development" else None,
                                  selection if phase == "test" else None)
        verify_dependencies(directory, current_plan)
        current = strict_json((path / "run-manifest.json").read_text(encoding="utf-8"))
        generations, answers = audit_phase(path, current, current_plan, manifest)
        item = {"manifest": current, "plan": current_plan, "generations": generations,
                "answers": answers, "summary": None}
        found[phase] = item
        if recorded and recorded.get("status") == "complete":
            if current.get("status") != "complete" or recorded.get("manifest_sha256") != digest((path / "run-manifest.json").read_bytes()):
                raise ValueError("Completed phase manifest changed")
        if current.get("status") != "complete":
            blocked = True
            continue
        if len(generations) != current_plan["planned_new_calls"] or len(answers) != current_plan["planned_new_calls"]:
            raise ValueError("Completed phase contains incomplete generation evidence")
        summary = phase_summary(current, answers)
        verify_reports(path, current, summary)
        item["summary"] = summary
        if phase == "development":
            name, expected = "calibration.json", create_calibration(summary, current_plan["tasks_snapshot"])
        elif phase == "validation":
            name, expected = "selection.json", choose_round(summary, calibration)
        else:
            continue
        expected_artifacts[name] = expected
        artifact = directory / "artifacts" / name
        expected_bytes = json_bytes(expected)
        if artifact.exists():
            if artifact.read_bytes() != expected_bytes:
                raise ValueError(f"Frozen artifact differs from its source phase recomputation: {name}")
            expected_hash = digest(expected_bytes)
            if name in manifest["artifact_sha256"] and manifest["artifact_sha256"][name] != expected_hash:
                raise ValueError(f"Study artifact hash differs: {name}")
            if name == "calibration.json":
                calibration = expected
            else:
                selection = expected
        else:
            if name in manifest["artifact_sha256"]:
                raise ValueError(f"Frozen artifact is missing: {name}")
            pending.append(name)
    for name in ("calibration.json", "selection.json"):
        if (directory / "artifacts" / name).exists() and name not in expected_artifacts:
            raise ValueError(f"Artifact exists before its source phase completed: {name}")
    for name in manifest["artifact_sha256"]:
        if name not in expected_artifacts or not (directory / "artifacts" / name).is_file():
            raise ValueError(f"Artifact hash recorded before its source phase or file exists: {name}")
    actual_answers = sum(len(item["answers"]) for item in found.values())
    actual_raw = sum(len(item["generations"]) for item in found.values())
    if (type(manifest.get("calls_completed")) is not int or not 0 <= manifest["calls_completed"] <= actual_answers
            or type(manifest.get("generations_saved")) is not int or not 0 <= manifest["generations_saved"] <= actual_raw):
        raise ValueError("Study counters exceed durable phase evidence")
    if manifest.get("status") == "complete" and (len(found) != len(PHASES) or pending
                                                  or any(item["summary"] is None for item in found.values())):
        raise ValueError("Completed study lacks complete audited phases and frozen artifacts")
    return {"phases": found, "calibration": calibration, "selection": selection,
            "expected_artifacts": expected_artifacts, "pending_artifacts": pending,
            "calls_completed": actual_answers, "generations_saved": actual_raw}


def sync_phase(root, study, phase, directory, current):
    entry = {"status": current["status"], "calls_completed": current["calls_completed"],
             "generations_saved": current["generations_saved"]}
    if current["status"] == "complete":
        entry["manifest_sha256"] = digest((directory / "run-manifest.json").read_bytes())
    study["phases"][phase] = entry
    study["calls_completed"] = sum(value["calls_completed"] for value in study["phases"].values())
    study["generations_saved"] = sum(value["generations_saved"] for value in study["phases"].values())
    study["updated_at"] = now()
    save_study(root, study)


def install_artifacts(root, study, audited):
    for name, value in audited["expected_artifacts"].items():
        path = root / "artifacts" / name
        freeze_file(path, json_bytes(value))
        study["artifact_sha256"][name] = digest(path.read_bytes())
    for phase, item in audited["phases"].items():
        sync_phase(root, study, phase, root / "phases" / phase, item["manifest"])
    save_study(root, study)


def execute_phase(root, study, plan, client, current, generations, answers, pause, progress):
    phase = plan["phase"]
    directory = root / "phases" / phase
    total = plan["planned_new_calls"]
    tasks = {task["id"]: task for task in plan["tasks_snapshot"]}
    current.update(status="running", last_started_at=now())
    current.pop("error", None)
    current.setdefault("segments", []).append({"started_at": now(), "calls_before": len(answers)})
    study.update(status="running", active_phase=phase)
    checkpoint(directory, current)
    sync_phase(root, study, phase, directory, current)
    code = 0

    def save():
        checkpoint(directory, current)
        sync_phase(root, study, phase, directory, current)

    try:
        with (directory / JOURNALS[0]).open("ab") as raw_output, (directory / JOURNALS[1]).open("ab") as answer_output:
            if len(generations) > len(answers):
                generation = generations[-1]
                answer = evaluate_generation(generation, tasks[generation["question_id"]])
                append_record(answer_output, answer)
                answers.append(answer)
                progress.record(answer)
                save()
            progress.display(len(answers), phase=phase)
            for index in range(len(generations), total):
                if pause.requested():
                    current["status"], code = "paused", 2
                    break
                verify_dependencies(root, plan)
                verify_runtime(client, study)
                call = build_call(plan, index, answers)
                current["active_call"] = {key: call[key] for key in
                                           ("call_index", "question_id", "round", "agent_id", "arm", "phase")}
                save()
                started = time.perf_counter()
                raw = client.chat("llama3.2:3b", call["messages"], seed=call["seed"], temperature=0.7,
                                  max_tokens=1024, format_value=call["format"])
                generation = {**copy.deepcopy(call), "type": "generation", "raw": raw,
                              "elapsed_seconds": time.perf_counter() - started}
                append_record(raw_output, generation)
                generations.append(generation)
                save()
                answer = evaluate_generation(generation, tasks[call["question_id"]])
                append_record(answer_output, answer)
                answers.append(answer)
                current.pop("active_call", None)
                progress.record(answer)
                save()
                progress.display(len(answers), phase=phase)
                if pause.requested():
                    current["status"], code = "paused", 2
                    break
        if len(answers) == total:
            verify_dependencies(root, plan)
            verify_runtime(client, study, check_hardware=True)
            payloads = report_bytes(phase_summary(current, answers))
            for name, data in payloads.items():
                freeze_file(directory / name, data)
            current["output_sha256"] = {name: digest(data) for name, data in payloads.items()}
            current["status"], code = "complete", 0
    except KeyboardInterrupt:
        current.update(status="interrupted", error="Forced interruption; durable replies recover without regeneration")
        code = 130
    except ERRORS as exc:
        current.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        print(f"Study phase stopped: {exc}", file=sys.stderr)
        code = 1
    finally:
        current["segments"][-1].update(finished_at=now(), calls_after=len(answers), status=current["status"])
        study["status"] = current["status"] if current["status"] != "complete" else "partial"
        save()
        progress.display(len(answers), phase=phase, final=True)
        progress.close()
    return code


def analyze_run(path):
    root = validate_output(path)
    with FileLock(root / ".study.lock"):
        manifest = strict_json((root / "study-manifest.json").read_text(encoding="utf-8"))
        if manifest.get("status") in {"running", "initializing"}:
            raise ValueError("Pause the active study writer before read-only analysis")
        plan = load_plan(Path(manifest["configuration_path"]))
        audited = audit_study(root, manifest, plan)
        return {"offline_audit": "passed", "study_id": STUDY_ID, "status": manifest["status"],
                "calls_completed": audited["calls_completed"], "generations_saved": audited["generations_saved"],
                "completed_phases": [phase for phase, item in audited["phases"].items() if item["summary"] is not None],
                "summary_reproduced": all(item["summary"] is not None for item in audited["phases"].values()),
                "pending_artifact_recovery": audited["pending_artifacts"],
                "primary_round": audited["selection"]["primary_round"] if audited["selection"] else None,
                "analysis_model_calls": 0}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--phase", choices=(*PHASES, "all"), default="development")
    parser.add_argument("--timeout", type=float, default=600)
    parser.add_argument("--dry-run", action="store_true")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--resume", action="store_true")
    mode.add_argument("--pause", action="store_true")
    mode.add_argument("--analyze-run", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.analyze_run:
            if args.config or args.output_dir or args.dry_run or args.phase != "development":
                raise ValueError("--analyze-run accepts only a saved study directory")
            print(json.dumps(analyze_run(args.analyze_run), indent=2, allow_nan=False))
            return 0
        root = validate_output(args.output_dir or DEFAULT_OUTPUT)
        if args.pause:
            if args.config or args.dry_run:
                raise ValueError("--pause accepts only the study destination")
            state = strict_json((root / "study-manifest.json").read_text(encoding="utf-8"))
            if state.get("study_id") != STUDY_ID or state.get("status") == "complete":
                raise ValueError("No incomplete v2 study at this destination")
            (root / ".pause-request").touch(exist_ok=True)
            print("Pause requested; the active response will be saved before stopping.")
            return 0
        if not math.isfinite(args.timeout) or args.timeout <= 0:
            raise ValueError("timeout must be positive and finite")
        if args.resume and args.dry_run:
            raise ValueError("--resume cannot be a dry run")
        if root.exists() and not args.resume:
            raise ValueError("Study directory exists; use --resume to continue without replay")
        if args.resume and not root.exists():
            raise ValueError("No study exists at this destination to resume")
        old = strict_json((root / "study-manifest.json").read_text(encoding="utf-8")) if args.resume else None
        plan = load_plan(args.config or (Path(old["configuration_path"]) if old else CONFIG_PATH))
        if args.dry_run:
            verify_hardware(plan["execution_environment"]["hardware_snapshot"])
            print(json.dumps({"study_id": STUDY_ID, "output_dir": str(root), "requested_phase": args.phase,
                              "phases": {phase: {"questions": len(phase_tasks(plan["tasks_snapshot"], phase)),
                                                 "new_calls": plan["planned_calls"][phase]} for phase in PHASES},
                              "total_new_calls": plan["planned_calls"]["total"], "num_agents": 5,
                              "peer_count": 4, "profile": "strict_schema", "hardware_check": "passed",
                              "progress": "ASCII bar and measured resume-aware request-time ETA",
                              "cost_time_scope": "model_request_seconds_including_loading",
                              "service_contacted": False, "pilot_answers_imported": 0}, indent=2))
            return 0
        if not args.resume and args.phase not in ("development", "all"):
            raise ValueError("Development must complete and freeze calibration before validation/test")
        reference = plan["profile_reference"]
        identity = {**plan, **{key: copy.deepcopy(reference[key]) for key in ("model_digest", "ollama_version")},
                    "hardware_snapshot": copy.deepcopy(plan["execution_environment"]["hardware_snapshot"])}
        client = None
        with FileLock(INFERENCE_LOCK):
            if not args.resume:
                client = PilotClient(timeout=args.timeout)
                verify_runtime(client, identity, check_hardware=True)
                root.mkdir(parents=True, exist_ok=False)
            with FileLock(root / ".study.lock"), PauseController(root / ".pause-request") as pause:
                if args.resume:
                    study = strict_json((root / "study-manifest.json").read_text(encoding="utf-8"))
                else:
                    study = {**identity, "status": "initializing", "started_at": now(),
                             "phases": {}, "artifact_sha256": {}, "calls_completed": 0,
                             "generations_saved": 0, "active_phase": None, "request_timeout": args.timeout}
                    study["snapshot_sha256"] = snapshot_hash({name: study[name] for name in SNAPSHOT_FIELDS})
                    save_study(root, study)
                audited = audit_study(root, study, plan)
                install_artifacts(root, study, audited)
                pause.clear_request()
                targets = PHASES if args.phase == "all" else (args.phase,)
                for phase in targets:
                    audited = audit_study(root, study, plan)
                    install_artifacts(root, study, audited)
                    if phase != "development" and audited["calibration"] is None:
                        raise ValueError("Development calibration must be complete and frozen before validation/test")
                    if phase == "test" and audited["selection"] is None:
                        raise ValueError("Validation selection must be complete and frozen before test")
                    item = audited["phases"].get(phase)
                    if item and item["summary"] is not None:
                        print(f"{phase}: complete and audited; no calls replayed.")
                        continue
                    if pause.requested():
                        study["status"] = "paused"
                        save_study(root, study)
                        return 2
                    current_plan = phase_plan(plan, phase, audited["calibration"] if phase != "development" else None,
                                              audited["selection"] if phase == "test" else None)
                    verify_dependencies(root, current_plan)
                    if client is None:
                        client = PilotClient(timeout=args.timeout)
                    verify_runtime(client, study, check_hardware=True)
                    directory = root / "phases" / phase
                    if item:
                        current, generations, answers = item["manifest"], item["generations"], item["answers"]
                    else:
                        directory.mkdir(parents=True, exist_ok=False)
                        for name in JOURNALS:
                            (directory / name).touch(exist_ok=False)
                        current = {**current_plan, **{key: copy.deepcopy(study[key]) for key in
                                                     ("model_digest", "ollama_version", "hardware_snapshot")},
                                   "status": "initializing", "started_at": now(), "calls_completed": 0,
                                   "generations_saved": 0}
                        current["snapshot_sha256"] = snapshot_hash({name: current[name] for name in PHASE_SNAPSHOT_FIELDS})
                        generations, answers = [], []
                        checkpoint(directory, current)
                        sync_phase(root, study, phase, directory, current)
                    prior = [answer for previous, state in audited["phases"].items()
                             if previous != phase for answer in state["answers"]] + answers
                    progress = Progress(current_plan["call_positions"], prior_records=prior)
                    code = execute_phase(root, study, current_plan, client, current, generations, answers, pause, progress)
                    if code:
                        return code
                    audited = audit_study(root, study, plan)
                    install_artifacts(root, study, audited)
                study["status"] = "complete" if all(study["phases"].get(phase, {}).get("status") == "complete"
                                                    for phase in PHASES) else "partial"
                study["active_phase"] = None
                save_study(root, study)
                audited = audit_study(root, study, plan)
                print(f"{study['status']}: {audited['calls_completed']}/{plan['planned_calls']['total']} "
                      f"calls saved in {root}")
                if audited["selection"]:
                    print(f"Locked validation-selected primary round: {audited['selection']['primary_round']}")
                return 0
    except KeyboardInterrupt:
        print("Study setup interrupted; durable evidence remains available.", file=sys.stderr)
        return 130
    except ERRORS as exc:
        print(f"Full-study setup/resume failed: {exc}", file=sys.stderr)
        return 1
