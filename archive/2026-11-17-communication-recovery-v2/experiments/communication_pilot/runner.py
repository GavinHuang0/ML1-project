"""Durable selected-profile pilot with audited shared initial evidence."""

import argparse
import copy
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys
import time

from experiment_runtime import FileLock, PauseController, hardware_identity
from local_llm import OllamaClient, OllamaError, validate_model_tag
import run_format_followup as parent_pilot
from run_format_followup import (atomic_json, append_record, canonical, digest, journal_records,
                                 snapshot_hash, strict_json, SchemaViolation)
from .protocol import (ARMS, EXPERIMENT_ID, EXPECTED_CONFIG, MAX_ROUNDS, NEW_CALLS, NUM_AGENTS,
                       PROTOCOL, REVISION_SYSTEM, SCREENING_TASK_IDS, STRICT_SCHEMA,
                       build_call, call_positions, context_budget)


ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "config/communication_pilot.json"
DEFAULT_PARENT = ROOT / "results/format-followup/windows-v2"
SOURCE_FILES = (
    "run_communication_pilot.py", "run_communication_pilot.ps1", "experiments/__init__.py",
    "experiments/communication_pilot/__init__.py", "experiments/communication_pilot/protocol.py",
    "experiments/communication_pilot/runner.py", "experiments/communication_pilot/analysis.py",
    "run_format_followup.py", *parent_pilot.SOURCE_FILES,
)
PARENT_FILES = ("run-manifest.json", "generations.jsonl", "answers.jsonl", "summary.json")
JOURNALS = ("generations.jsonl", "answers.jsonl")
PLAN_FIELDS = ("experiment_id", "configuration_path", "configuration_sha256", "configuration_snapshot",
               "protocol_snapshot", "protocol_sha256", "schema_sha256", "tasks_snapshot",
               "initial_panel", "parent_snapshot", "source_sha256", "call_positions",
               "planned_new_calls", "reused_round_zero_calls", "planned_unique_calls")
SNAPSHOT_FIELDS = (*PLAN_FIELDS, "hardware_snapshot", "model_digest", "ollama_version")
ERRORS = (OllamaError, OSError, ValueError, KeyError, TypeError, RuntimeError, ZeroDivisionError,
          OverflowError, RecursionError)


def now():
    return datetime.now(timezone.utc).isoformat()


def parent_hashes(directory):
    return {name: digest((Path(directory) / name).read_bytes()) for name in PARENT_FILES}


def load_parent(directory):
    directory = Path(directory).resolve()
    before = parent_hashes(directory)
    audited = parent_pilot.analyze_run(directory)
    if (audited.get("status") != "complete" or audited.get("summary_reproduced") is not True
            or audited["summary"]["recommendation"] != "strict_schema"):
        raise ValueError("Parent must be a complete audited format follow-up selecting strict_schema")
    manifest = strict_json((directory / "run-manifest.json").read_text(encoding="utf-8"))
    records, _ = journal_records(directory / "answers.jsonl")
    selected = [record for record in records if record.get("profile") == "strict_schema"
                and record.get("evaluation_set") == "screening"]
    if len(selected) != 80 or any(record.get("round") != 0 for record in selected):
        raise ValueError("Parent must provide exactly eighty selected screening round-zero answers")
    if before != parent_hashes(directory):
        raise ValueError("Parent evidence changed during audit")
    snapshot = {"directory": str(directory), "experiment_id": manifest["experiment_id"],
                "evidence_sha256": before, "selected_profile": "strict_schema",
                "model_digest": manifest["model_digest"], "ollama_version": manifest["ollama_version"],
                "hardware_snapshot": copy.deepcopy(manifest["hardware_snapshot"]),
                "initial_panel_sha256": snapshot_hash(selected),
                "selection": copy.deepcopy(audited["summary"]["sets"]["screening"])}
    return manifest, selected, snapshot


def source_hashes(config_path, parent_manifest=None):
    paths = {str(ROOT / name) for name in SOURCE_FILES}
    paths.add(str(Path(config_path).resolve()))
    for name in (parent_manifest or {}).get("source_sha256", {}):
        path = Path(name)
        paths.add(str(path if path.is_absolute() else ROOT / path))
    return {name: digest(Path(name).read_bytes()) for name in sorted(paths)}


def load_plan(config_path=CONFIG_PATH, parent_directory=DEFAULT_PARENT):
    config_path = Path(config_path).resolve()
    raw_config = config_path.read_bytes()
    config = strict_json(raw_config.decode("utf-8"))
    if canonical(config) != canonical(EXPECTED_CONFIG):
        raise ValueError("Configuration differs from the frozen communication pilot")
    parent_manifest, initial, parent = load_parent(parent_directory)
    by_id = {task["id"]: task for task in parent_manifest["tasks_snapshot"]}
    tasks = [copy.deepcopy(by_id[task_id]) for task_id in SCREENING_TASK_IDS]
    if (len(tasks) != 8 or any(task["split"] != "development" for task in tasks)
            or len({task["group_id"] for task in tasks}) != 8):
        raise ValueError("Pilot needs the eight selected development structural groups")
    ordered = []
    for task in tasks:
        rows = [record for record in initial if record["question_id"] == task["id"]]
        if (len(rows) != NUM_AGENTS or {record["agent_id"] for record in rows} != set(range(NUM_AGENTS))
                or any(record["messages"] != [{"role": "system", "content": parent_pilot.SYSTEM},
                                              {"role": "user", "content": task["prompt"]}]
                       or canonical(record["format"]) != canonical(STRICT_SCHEMA) for record in rows)):
            raise ValueError("Imported panel must use the selected original prompt, schema and all ten agents")
        ordered.extend(sorted(rows, key=lambda record: record["agent_id"]))
    if snapshot_hash(ordered) != parent["initial_panel_sha256"]:
        raise ValueError("Parent initial panel order differs from the frozen screening order")
    positions = call_positions(tasks)
    independent_seeds = [record["seed"] for record in ordered] + [row["seed"] for row in positions[::2]]
    if len(independent_seeds) != len(set(independent_seeds)):
        raise ValueError("Seed collision between initial and revision question/round/agent positions")
    plan = {"experiment_id": EXPERIMENT_ID, "configuration_path": str(config_path),
            "configuration_sha256": digest(raw_config), "configuration_snapshot": config,
            "protocol_snapshot": copy.deepcopy(PROTOCOL), "protocol_sha256": snapshot_hash(PROTOCOL),
            "schema_sha256": snapshot_hash(STRICT_SCHEMA), "tasks_snapshot": tasks,
            "initial_panel": copy.deepcopy(ordered), "parent_snapshot": parent,
            "source_sha256": source_hashes(config_path, parent_manifest), "call_positions": positions,
            "planned_new_calls": NEW_CALLS, "reused_round_zero_calls": 80,
            "planned_unique_calls": 560,
            "notes": ["Eighty audited initial answers are reused identically in both branches.",
                      "480 new calls; 560 unique calls including the imported panel; 640 branch records.",
                      "Both arms use the same revision instruction and strict schema; peer visibility differs.",
                      "Later prompts are built only from each arm's completed immediately preceding round.",
                      "Eight inspected development groups support exploratory comparisons, not validation selection.",
                      "Calls match between arms; actual token/time budgets differ and are reported.",
                      "No repairs, automatic retries, answer feedback, prompt shortening, or early consensus stopping."]}
    plan["first_revision_calls"] = [build_call(plan, index, []) for index, position in
                                    enumerate(plan["call_positions"]) if position["round"] == 1]
    return plan


class PilotClient(OllamaClient):
    def chat(self, model, messages, *, seed, temperature, max_tokens, format_value):
        validate_model_tag(model)
        if (model != "llama3.2:3b" or type(seed) is not int or temperature != 0.7
                or type(max_tokens) is not int or max_tokens != 1024
                or canonical(format_value) != canonical(STRICT_SCHEMA)
                or not isinstance(messages, list) or len(messages) != 2
                or messages[0] != {"role": "system", "content": REVISION_SYSTEM}
                or messages[1].get("role") != "user" or not isinstance(messages[1].get("content"), str)):
            raise ValueError("Selected-profile generation settings or revision instruction drifted")
        context_budget(messages)
        return self._request("/api/chat", {
            "model": model, "messages": messages, "stream": False, "format": format_value,
            "keep_alive": 0, "options": {"seed": seed, "temperature": 0.7,
                                          "num_predict": 1024, "num_ctx": 16384},
        })


def evaluate_generation(generation, task):
    if generation.get("arm") not in ARMS or generation.get("profile") != "strict_schema":
        raise ValueError("Unexpected branch or selected profile")
    return parent_pilot.evaluate_generation(generation, task)


def verify_sources(manifest):
    for name, expected in manifest["source_sha256"].items():
        if digest(Path(name).read_bytes()) != expected:
            raise ValueError(f"Frozen source/input changed: {name}")
    snapshot = manifest["parent_snapshot"]
    if parent_hashes(snapshot["directory"]) != snapshot["evidence_sha256"]:
        raise ValueError("Imported parent evidence changed")


def verify_runtime(client, manifest, check_hardware=False):
    verify_sources(manifest)
    health, model = parent_pilot.installed_model(client)
    if health["version"] != manifest["ollama_version"] or model["digest"] != manifest["model_digest"]:
        raise ValueError("Model digest or Ollama runtime differs from the imported panel")
    if check_hardware and hardware_identity() != manifest["hardware_snapshot"]:
        raise ValueError("Hardware identity differs from the imported panel")


def checkpoint(directory, manifest):
    evidence = {}
    for name in ("initial_panel.jsonl", *JOURNALS):
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
    if (manifest.get("calls_completed") != manifest["evidence_checkpoint"]["answers.jsonl"]["records"]
            or manifest.get("generations_saved") != manifest["evidence_checkpoint"]["generations.jsonl"]["records"]):
        raise ValueError("Manifest counters disagree with the durable evidence checkpoint")
    parent = plan["parent_snapshot"]
    for name in ("model_digest", "ollama_version", "hardware_snapshot"):
        if manifest.get(name) != parent[name]:
            raise ValueError(f"Imported {name} identity differs")
    verify_sources(manifest)
    initial, initial_lines = journal_records(directory / "initial_panel.jsonl")
    saved = manifest["evidence_checkpoint"]["initial_panel.jsonl"]
    if (initial != plan["initial_panel"] or saved["records"] != 80
            or digest(b"".join(initial_lines)) != saved["sha256"]):
        raise ValueError("Shared initial panel differs from audited import")
    parsed = []
    for name in JOURNALS:
        records, lines = journal_records(directory / name)
        saved = manifest["evidence_checkpoint"][name]
        count = saved["records"]
        if (type(count) is not int or count < 0 or len(records) < count or len(records) > count + 1
                or digest(b"".join(lines[:count])) != saved["sha256"]):
            raise ValueError(f"Evidence prefix hash/count mismatch: {name}")
        parsed.append(records)
    generations, answers = parsed
    if (len(generations) > NEW_CALLS or len(answers) > len(generations)
            or len(generations) - len(answers) > 1):
        raise ValueError("Journals do not form a durable canonical call prefix")
    tasks = {task["id"]: task for task in plan["tasks_snapshot"]}
    checked = []
    for index, generation in enumerate(generations):
        if generation.get("type") != "generation":
            raise ValueError("Unexpected raw journal record type")
        expected = build_call(plan, index, checked)
        for name, value in expected.items():
            if canonical(generation.get(name)) != canonical(value):
                raise ValueError(f"Saved generation violates canonical preceding-round prompt/position: {name}")
        elapsed = generation.get("elapsed_seconds")
        if type(elapsed) not in (int, float) or not math.isfinite(elapsed) or elapsed < 0:
            raise ValueError("Invalid recorded call duration")
        evaluated = evaluate_generation(generation, tasks[generation["question_id"]])
        if index < len(answers) and evaluated != answers[index]:
            raise ValueError("Saved answer disagrees with raw calculator evaluation")
        checked.append(evaluated)
    return generations, answers


def summarize(manifest, initial_panel, answers):
    from .analysis import summarize as summarize_analysis
    return summarize_analysis(manifest, initial_panel, answers)


def execute(directory, plan, client, manifest, generations, answers, pause):
    tasks = {task["id"]: task for task in plan["tasks_snapshot"]}
    manifest.update(status="running", last_started_at=now())
    manifest.pop("error", None)
    manifest.setdefault("segments", []).append({"started_at": now(), "calls_before": len(answers)})
    code = 0
    try:
        with (directory / "generations.jsonl").open("ab") as raw_output, (directory / "answers.jsonl").open("ab") as answer_output:
            if len(generations) > len(answers):
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
                manifest["active_call"] = {name: call[name] for name in ("call_index", "question_id", "round", "agent_id", "arm")}
                checkpoint(directory, manifest)
                started = time.perf_counter()
                raw = client.chat("llama3.2:3b", call["messages"], seed=call["seed"], temperature=0.7,
                                  max_tokens=1024, format_value=call["format"])
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
            summary = summarize(manifest, plan["initial_panel"], answers)
            summary_path = directory / "summary.json"
            if summary_path.exists():
                if strict_json(summary_path.read_text(encoding="utf-8")) != summary:
                    raise ValueError("Existing summary differs from completed evidence; refusing overwrite")
            else:
                atomic_json(summary_path, summary)
            manifest.update(status="complete", summary_sha256=digest(summary_path.read_bytes()))
            code = 0
    except KeyboardInterrupt:
        manifest.update(status="interrupted", error="Forced interruption; durable returned responses are recovered on resume")
        code = 130
    except SchemaViolation as exc:
        manifest.update(status="failed", error=str(exc), schema_support_check="failed_or_truncated")
        print(f"Pilot stopped: {exc}", file=sys.stderr)
        code = 1
    except ERRORS as exc:
        manifest.update(status="failed", error=str(exc))
        print(f"Pilot stopped: {exc}", file=sys.stderr)
        code = 1
    finally:
        manifest["segments"][-1].update(finished_at=now(), calls_after=len(answers), status=manifest["status"])
        manifest["updated_at"] = now()
        checkpoint(directory, manifest)
    print(f"{manifest['status']}: {len(answers)}/{NEW_CALLS} new calls saved in {directory}")
    return code


def analyze_run(directory):
    directory = Path(directory).resolve()
    manifest = strict_json((directory / "run-manifest.json").read_text(encoding="utf-8"))
    if manifest.get("experiment_id") != EXPERIMENT_ID:
        raise ValueError("Analysis requires a strict-schema communication pilot")
    if manifest.get("status") in {"initializing", "running"}:
        raise ValueError("Pause the active writer before offline analysis")
    plan = load_plan(Path(manifest["configuration_path"]), Path(manifest["parent_snapshot"]["directory"]))
    generations, answers = audit_resume(directory, manifest, plan)
    result = {"offline_audit": "passed", "status": manifest["status"],
              "calls_completed": len(answers), "generations_saved": len(generations),
              "reused_initial_calls": 80, "summary_reproduced": None}
    if manifest.get("status") == "complete":
        if len(answers) != NEW_CALLS or len(generations) != NEW_CALLS:
            raise ValueError("Completed run has incomplete evidence")
        summary_path = directory / "summary.json"
        if digest(summary_path.read_bytes()) != manifest.get("summary_sha256"):
            raise ValueError("Summary evidence hash mismatch")
        summary = summarize(manifest, plan["initial_panel"], answers)
        if strict_json(summary_path.read_text(encoding="utf-8")) != summary:
            raise ValueError("Saved summary disagrees with recomputed evidence")
        result.update(summary_reproduced=True, summary=summary)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--parent-run", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--timeout", type=float, default=600)
    parser.add_argument("--dry-run", action="store_true")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--resume", action="store_true")
    mode.add_argument("--pause", action="store_true")
    mode.add_argument("--analyze-run", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.analyze_run is not None:
            if args.config or args.parent_run or args.output_dir or args.dry_run:
                raise ValueError("--analyze-run accepts only a saved run directory")
            print(json.dumps(analyze_run(args.analyze_run), indent=2, allow_nan=False))
            return 0
        if args.pause:
            if args.output_dir is None or args.config or args.parent_run or args.dry_run:
                raise ValueError("--pause requires only an existing --output-dir")
            directory = args.output_dir.resolve()
            manifest = strict_json((directory / "run-manifest.json").read_text(encoding="utf-8"))
            if manifest.get("experiment_id") != EXPERIMENT_ID or manifest.get("status") == "complete":
                raise ValueError("No incomplete communication pilot exists at this destination")
            (directory / ".pause-request").touch(exist_ok=True)
            print("Pause requested; the active call will be saved before stopping.")
            return 0
        if not math.isfinite(args.timeout) or args.timeout <= 0:
            raise ValueError("timeout must be positive and finite")
        if args.resume and (args.output_dir is None or args.dry_run):
            raise ValueError("--resume requires an existing --output-dir and cannot be a dry run")
        directory = (args.output_dir or ROOT / "results/communication-pilot" /
                     datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")).resolve()
        old = strict_json((directory / "run-manifest.json").read_text(encoding="utf-8")) if args.resume else None
        config_path = args.config or (Path(old["configuration_path"]) if old else CONFIG_PATH)
        parent_directory = args.parent_run or (Path(old["parent_snapshot"]["directory"]) if old else DEFAULT_PARENT)
        plan = load_plan(config_path, parent_directory)
        if args.dry_run:
            print(json.dumps({**plan, "output_dir": str(directory)}, indent=2, allow_nan=False))
            return 0
        if not args.resume:
            if directory.exists():
                raise ValueError("Output directory already exists; use --resume for the same saved pilot")
            if directory.is_relative_to(ROOT / "archive") or directory.is_relative_to(ROOT / "results/baseline"):
                raise ValueError("Output must stay outside historical namespaces")
            client = PilotClient(timeout=args.timeout)
            parent = plan["parent_snapshot"]
            health, model = parent_pilot.installed_model(client)
            if health["version"] != parent["ollama_version"] or model["digest"] != parent["model_digest"]:
                raise ValueError("Model/runtime changed since the imported panel; a new protocol is required")
            if hardware_identity() != parent["hardware_snapshot"]:
                raise ValueError("Hardware changed since the imported panel; a new protocol is required")
            verify_sources(plan)
            directory.mkdir(parents=True, exist_ok=False)
        with FileLock(directory / ".pilot.lock"), PauseController(directory / ".pause-request") as pause:
            if args.resume:
                old = strict_json((directory / "run-manifest.json").read_text(encoding="utf-8"))
                if old.get("status") == "complete":
                    raise ValueError("Pilot already complete; no inference will be replayed")
                generations, answers = audit_resume(directory, old, plan)
                manifest = old
                client = PilotClient(timeout=args.timeout)
                verify_runtime(client, manifest, check_hardware=True)
            else:
                for name in JOURNALS:
                    (directory / name).touch(exist_ok=False)
                with (directory / "initial_panel.jsonl").open("xb") as output:
                    for record in plan["initial_panel"]:
                        append_record(output, record)
                parent = plan["parent_snapshot"]
                # Preview prompts are reproducible from the frozen plan and
                # are useful in --dry-run, but need not be rewritten in every
                # durable per-call checkpoint.
                persisted_plan = {key: value for key, value in plan.items() if key != "first_revision_calls"}
                manifest = {**persisted_plan, "status": "initializing", "started_at": now(),
                            "hardware_snapshot": copy.deepcopy(parent["hardware_snapshot"]),
                            "model_digest": parent["model_digest"], "ollama_version": parent["ollama_version"],
                            "calls_completed": 0, "generations_saved": 0, "request_timeout": args.timeout}
                manifest["snapshot_sha256"] = snapshot_hash({name: manifest[name] for name in SNAPSHOT_FIELDS})
                generations, answers = [], []
                checkpoint(directory, manifest)
            pause.clear_request()
            return execute(directory, plan, client, manifest, generations, answers, pause)
    except KeyboardInterrupt:
        print("Pilot setup interrupted; saved evidence remains available.", file=sys.stderr)
        return 130
    except ERRORS as exc:
        print(f"Pilot setup/resume failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
