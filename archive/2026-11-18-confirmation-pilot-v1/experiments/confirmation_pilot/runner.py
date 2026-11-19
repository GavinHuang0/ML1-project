"""Durable prospective confirmation on twelve unused development questions."""

import argparse
import copy
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import sys
import time

from calculator_protocol import SYSTEM
from experiment_runtime import FileLock, PauseController, hardware_identity
from local_llm import OllamaClient, OllamaError, validate_model_tag
from run_format_followup import (atomic_json, append_record, canonical, digest,
                                 installed_model, journal_records, snapshot_hash,
                                 strict_json, SchemaViolation)
from experiments.communication_pilot import recovery as selected
from experiments.communication_pilot.protocol import STRICT_SCHEMA, REVISION_SYSTEM, context_budget
from .protocol import (EXPERIMENT_ID, EXPECTED_CONFIG, PROTOCOL, NEW_CALLS,
                       load_tasks, cohort_metadata, call_positions, build_call)
from .environment import load_environment


ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "config/confirmation_pilot.json"
OUTPUT_ROOT = ROOT / "results/confirmation-pilot"
DEFAULT_OUTPUT = OUTPUT_ROOT / "windows-v1"
PROFILE_REFERENCE = ROOT / "results/communication-pilot/windows-v2"
JOURNALS = ("generations.jsonl", "answers.jsonl")
REPORT_FILES = ("summary.json", "comparisons.csv", "per_question.csv")
SOURCE_FILES = (
    "run_confirmation_pilot.py", "run_confirmation_pilot.ps1",
    "experiments/confirmation_pilot/__init__.py", "experiments/confirmation_pilot/protocol.py",
    "experiments/confirmation_pilot/runner.py", "experiments/confirmation_pilot/analysis.py",
    "experiments/confirmation_pilot/environment.py", "config/confirmation_environment.json",
    "experiments/offline_policies/protocol.py", "experiments/offline_policies/analysis.py",
    "experiments/offline_policies/runner.py", "config/offline_policy_comparison.json",
    "config/full_benchmark.json", "config/format_followup_tasks.json",
    *selected.SOURCE_FILES, *selected.v1.SOURCE_FILES,
)
PLAN_FIELDS = ("experiment_id", "configuration_path", "configuration_sha256",
               "configuration_snapshot", "protocol_snapshot", "protocol_sha256",
               "schema_sha256", "tasks_snapshot", "cohort", "profile_reference", "execution_environment",
               "source_sha256", "call_positions", "planned_new_calls",
               "planned_initial_calls", "planned_revision_calls")
SNAPSHOT_FIELDS = (*PLAN_FIELDS, "hardware_snapshot", "model_digest", "ollama_version")
ERRORS = selected.ERRORS


def now():
    return datetime.now(timezone.utc).isoformat()


def load_reference():
    """Audit the selected profile without importing any old answer as new evidence."""
    names = ("run-manifest.json", "summary.json")
    before = {str(PROFILE_REFERENCE / name): digest((PROFILE_REFERENCE / name).read_bytes())
              for name in names}
    audit = selected.analyze_run(PROFILE_REFERENCE)
    if audit.get("status") != "complete" or audit.get("summary_reproduced") is not True:
        raise ValueError("Selected-profile reference must be complete and independently reproduced")
    manifest = strict_json((PROFILE_REFERENCE / "run-manifest.json").read_text(encoding="utf-8"))
    for name, value in before.items():
        if digest(Path(name).read_bytes()) != value:
            raise ValueError("Selected-profile evidence changed during audit")
    return {"directory": str(PROFILE_REFERENCE), "evidence_sha256": before,
            "audit": "complete_summary_reproduced",
            "model_digest": manifest["model_digest"], "ollama_version": manifest["ollama_version"],
            "hardware_snapshot": copy.deepcopy(manifest["hardware_snapshot"]),
            "profile": "strict_schema", "reused_answers": 0,
            "source_sha256": copy.deepcopy(manifest["source_sha256"])}


def source_hashes(config_path, reference):
    paths = {str(ROOT / name) for name in SOURCE_FILES}
    paths.add(str(Path(config_path).resolve()))
    paths.update(reference["source_sha256"])
    paths.update(reference["evidence_sha256"])
    return {name: digest(Path(name).read_bytes()) for name in sorted(paths)}


def verify_sources(manifest):
    for name, expected in manifest["source_sha256"].items():
        if digest(Path(name).read_bytes()) != expected:
            raise ValueError(f"Frozen source/input changed: {name}")


def load_plan(config_path=CONFIG_PATH):
    config_path = Path(config_path).resolve()
    data = config_path.read_bytes()
    config = strict_json(data.decode("utf-8"))
    if canonical(config) != canonical(EXPECTED_CONFIG):
        raise ValueError("Configuration differs from the frozen confirmation pilot")
    tasks = load_tasks()
    reference = load_reference()
    environment = load_environment(reference)
    positions = call_positions(tasks)
    if len(positions) != NEW_CALLS or sum(row["round"] == 0 for row in positions) != 120:
        raise ValueError("Confirmation requires 120 shared initial and 720 revision calls")
    return {"experiment_id": EXPERIMENT_ID, "configuration_path": str(config_path),
            "configuration_sha256": digest(data), "configuration_snapshot": config,
            "protocol_snapshot": copy.deepcopy(PROTOCOL), "protocol_sha256": snapshot_hash(PROTOCOL),
            "schema_sha256": snapshot_hash(STRICT_SCHEMA), "tasks_snapshot": tasks,
            "cohort": cohort_metadata(tasks), "profile_reference": reference, "execution_environment": environment,
            "source_sha256": source_hashes(config_path, reference), "call_positions": positions,
            "planned_new_calls": NEW_CALLS, "planned_initial_calls": 120,
            "planned_revision_calls": 720}


class PilotClient(OllamaClient):
    def chat(self, model, messages, *, seed, temperature, max_tokens, format_value):
        validate_model_tag(model)
        if (model != "llama3.2:3b" or type(seed) is not int or temperature != 0.7
                or type(max_tokens) is not int or max_tokens != 1024
                or canonical(format_value) != canonical(STRICT_SCHEMA)
                or not isinstance(messages, list) or len(messages) != 2
                or messages[0] not in ({"role": "system", "content": SYSTEM},
                                      {"role": "system", "content": REVISION_SYSTEM})
                or messages[1].get("role") != "user" or not isinstance(messages[1].get("content"), str)):
            raise ValueError("Selected-profile request settings drifted")
        context_budget(messages)
        return self._request("/api/chat", {
            "model": model, "messages": messages, "stream": False, "format": format_value,
            "keep_alive": 0, "options": {"seed": seed, "temperature": 0.7,
                                          "num_predict": 1024, "num_ctx": 16384},
        })


def evaluate_generation(generation, task):
    # Use precisely the selected strict-schema evaluator and narrow truncation
    # admission, prospectively for initial as well as revised responses.
    if generation.get("arm") == "shared_initial" and generation.get("round") == 0:
        normalized = {**generation, "arm": "self_revision"}
        evaluated = selected.evaluate_generation(normalized, task)
        return {**evaluated, "arm": "shared_initial"}
    if generation.get("round") not in (1, 2, 3):
        raise ValueError("Unexpected initial/revision record identity")
    return selected.evaluate_generation(generation, task)


def verify_runtime(client, manifest, check_hardware=False):
    verify_sources(manifest)
    health, model = installed_model(client)
    if health["version"] != manifest["ollama_version"] or model["digest"] != manifest["model_digest"]:
        raise ValueError("Model digest or Ollama version differs from the frozen selected profile")
    if check_hardware:
        verify_hardware(manifest["hardware_snapshot"])


def verify_hardware(expected):
    current = hardware_identity()
    changes = {key: {"expected": expected.get(key), "observed": current.get(key)}
               for key in set(expected) | set(current) if expected.get(key) != current.get(key)}
    if changes:
        raise ValueError("Hardware identity differs from the frozen confirmation environment: "
                         + json.dumps(changes, sort_keys=True))


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
    if manifest.get("experiment_id") != EXPERIMENT_ID:
        raise ValueError("Destination is not this versioned confirmation pilot")
    for field in PLAN_FIELDS:
        if canonical(manifest.get(field)) != canonical(plan.get(field)):
            raise ValueError(f"Resume snapshot/protocol differs: {field}")
    if manifest.get("snapshot_sha256") != snapshot_hash({name: manifest[name] for name in SNAPSHOT_FIELDS}):
        raise ValueError("Run snapshot hash mismatch")
    reference = plan["profile_reference"]
    for field in ("model_digest", "ollama_version"):
        if manifest[field] != reference[field]:
            raise ValueError(f"Selected-profile identity differs: {field}")
    if manifest["hardware_snapshot"] != plan["execution_environment"]["hardware_snapshot"]:
        raise ValueError("Saved hardware differs from the frozen confirmation environment")
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
    if len(generations) > NEW_CALLS or not 0 <= len(generations) - len(answers) <= 1:
        raise ValueError("Journals do not form a durable canonical call prefix")
    tasks = {task["id"]: task for task in plan["tasks_snapshot"]}
    checked = []
    for index, generation in enumerate(generations):
        if generation.get("type") != "generation":
            raise ValueError("Unexpected raw journal record type")
        expected = build_call(plan, index, checked)
        for name, value in expected.items():
            if canonical(generation.get(name)) != canonical(value):
                raise ValueError(f"Saved call violates canonical prompt/position: {name}")
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
    initial = [record for record in answers if record["round"] == 0]
    revisions = [record for record in answers if record["round"] > 0]
    return analyze(manifest, initial, revisions)


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
    tasks = {task["id"]: task for task in plan["tasks_snapshot"]}
    manifest.update(status="running", last_started_at=now())
    manifest.pop("error", None)
    manifest.setdefault("segments", []).append({"started_at": now(), "calls_before": len(answers)})
    checkpoint(directory, manifest)
    code = 0
    try:
        with (directory / JOURNALS[0]).open("ab") as raw_output, (directory / JOURNALS[1]).open("ab") as answer_output:
            if len(generations) > len(answers):
                # A raw reply returned before a crash is evaluated locally;
                # the model is never called again for that durable position.
                generation = generations[-1]
                answer = evaluate_generation(generation, tasks[generation["question_id"]])
                append_record(answer_output, answer)
                answers.append(answer)
                checkpoint(directory, manifest)
            for index in range(len(generations), NEW_CALLS):
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
                print(f"Saved {len(answers)}/{NEW_CALLS}: {call['question_id']} round {call['round']} "
                      f"agent {call['agent_id']} {call['arm']}", flush=True)
                if pause.requested():
                    manifest["status"], code = "paused", 2
                    break
        if len(answers) == NEW_CALLS:
            verify_runtime(client, manifest, check_hardware=True)
            finish_reports(directory, manifest, answers)
            manifest["status"], code = "complete", 0
    except KeyboardInterrupt:
        manifest.update(status="interrupted", error="Forced interruption; durable replies recover on resume")
        code = 130
    except ERRORS as exc:
        manifest.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        print(f"Confirmation pilot stopped: {exc}", file=sys.stderr)
        code = 1
    finally:
        manifest["segments"][-1].update(finished_at=now(), calls_after=len(answers), status=manifest["status"])
        manifest["updated_at"] = now()
        checkpoint(directory, manifest)
    print(f"{manifest['status']}: {len(answers)}/{NEW_CALLS} calls saved in {directory}")
    return code


def validate_output(path):
    candidate = Path(path).absolute()
    directory = candidate.resolve()
    root = OUTPUT_ROOT.resolve()
    if directory != candidate or root != OUTPUT_ROOT.absolute():
        raise ValueError("Output must use a direct canonical path without links or junctions")
    if directory == root or not directory.is_relative_to(root):
        raise ValueError(f"Output must be a run folder beneath {root}")
    return directory


def analyze_run(directory):
    directory = validate_output(directory)
    with FileLock(directory / ".pilot.lock"):
        manifest = strict_json((directory / "run-manifest.json").read_text(encoding="utf-8"))
        if manifest.get("status") in {"running", "initializing"}:
            raise ValueError("Pause the active writer before offline analysis")
        plan = load_plan(Path(manifest["configuration_path"]))
        generations, answers = audit_resume(directory, manifest, plan)
        result = {"offline_audit": "passed", "status": manifest["status"],
                  "generations_saved": len(generations), "calls_completed": len(answers),
                  "summary_reproduced": None, "analysis_model_calls": 0}
        if manifest.get("status") == "complete":
            if len(generations) != NEW_CALLS or len(answers) != NEW_CALLS:
                raise ValueError("Completed run has incomplete evidence")
            from .analysis import report_bytes
            payloads = report_bytes(summarize(manifest, answers))
            if set(manifest.get("output_sha256", {})) != set(REPORT_FILES):
                raise ValueError("Completed output inventory differs")
            for name, expected in payloads.items():
                actual = (directory / name).read_bytes()
                if actual != expected or digest(actual) != manifest["output_sha256"][name]:
                    raise ValueError(f"Saved report differs from deterministic recomputation: {name}")
            result.update(summary_reproduced=True, comparison_rows=36, question_rows=432,
                          selection_performed=False)
        verify_sources(manifest)
        return result


def main(argv=None):
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
        if args.analyze_run:
            if args.config or args.output_dir or args.dry_run:
                raise ValueError("--analyze-run accepts only a saved run directory")
            print(json.dumps(analyze_run(args.analyze_run), indent=2, allow_nan=False))
            return 0
        directory = validate_output(args.output_dir or DEFAULT_OUTPUT)
        if args.pause:
            if args.config or args.dry_run:
                raise ValueError("--pause accepts only the run destination")
            saved = strict_json((directory / "run-manifest.json").read_text(encoding="utf-8"))
            if saved.get("experiment_id") != EXPERIMENT_ID or saved.get("status") == "complete":
                raise ValueError("No incomplete confirmation pilot at this destination")
            (directory / ".pause-request").touch(exist_ok=True)
            print("Pause requested; the active call will be saved before stopping.")
            return 0
        if not math.isfinite(args.timeout) or args.timeout <= 0:
            raise ValueError("timeout must be positive and finite")
        if args.resume and args.dry_run:
            raise ValueError("--resume cannot be a dry run")
        if directory.exists() and not args.resume:
            raise ValueError("Output already exists; use --resume for the same saved pilot")
        old = strict_json((directory / "run-manifest.json").read_text(encoding="utf-8")) if args.resume else None
        config_path = args.config or (Path(old["configuration_path"]) if old else CONFIG_PATH)
        plan = load_plan(config_path)
        if args.dry_run:
            reference = plan["profile_reference"]
            verify_hardware(plan["execution_environment"]["hardware_snapshot"])
            print(json.dumps({"experiment_id": EXPERIMENT_ID, "output_dir": str(directory),
                              "cohort": plan["cohort"], "task_ids": [t["id"] for t in plan["tasks_snapshot"]],
                              "planned_new_calls": NEW_CALLS, "shared_initial_calls": 120,
                              "revision_calls": 720, "comparison_rows": 36, "question_decisions": 432,
                              "maximum_round": 3, "selected_profile": "strict_schema",
                              "model": "llama3.2:3b", "model_digest": reference["model_digest"],
                              "ollama_version": reference["ollama_version"],
                              "execution_environment": plan["execution_environment"], "hardware_check": "passed",
                              "policy_selection": False, "service_contacted": False,
                              "notes": ["Full trajectories once; policies replayed without additional calls.",
                                        "Validation/test excluded; no automatic retries or repairs.",
                                        "Output-cap invalid JSON is one ineligible response; other schema failures stop."]},
                             indent=2, allow_nan=False))
            return 0
        client = PilotClient(timeout=args.timeout)
        reference = plan["profile_reference"]
        execution_hardware = plan["execution_environment"]["hardware_snapshot"]
        if not args.resume:
            identity = {**plan, **{key: reference[key] for key in ("model_digest", "ollama_version")},
                        "hardware_snapshot": execution_hardware}
            verify_runtime(client, identity, check_hardware=True)
            directory.mkdir(parents=True, exist_ok=False)
        with FileLock(directory / ".pilot.lock"), PauseController(directory / ".pause-request") as pause:
            if args.resume:
                manifest = strict_json((directory / "run-manifest.json").read_text(encoding="utf-8"))
                if manifest.get("status") == "complete":
                    raise ValueError("Pilot already complete; no inference will be replayed")
                generations, answers = audit_resume(directory, manifest, plan)
                verify_runtime(client, manifest, check_hardware=True)
            else:
                for name in JOURNALS:
                    (directory / name).touch(exist_ok=False)
                manifest = {**plan, "status": "initializing", "started_at": now(),
                            **{key: copy.deepcopy(reference[key]) for key in ("model_digest", "ollama_version")},
                            "hardware_snapshot": copy.deepcopy(execution_hardware),
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
        print(f"Confirmation setup/resume failed: {exc}", file=sys.stderr)
        return 1
