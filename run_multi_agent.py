"""Run or independently analyze the frozen synchronous calculator experiment."""

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

from local_llm import OllamaError
from multi_agent_llm import MultiAgentClient as OllamaClient
from multi_agent_protocol import (EXPERIMENT_ID, FROZEN_PROTOCOL, agent_seed, build_messages,
                                  evaluate_response, read_config, read_tasks,
                                  validate_config, validate_tasks)
from multi_agent_analysis import summarize_experiment, summarize_round, validate_calibration


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config" / "multi_agent.json"
MODEL = FROZEN_PROTOCOL["model"]
SOURCE_FILES = ("run_multi_agent.py", "multi_agent_protocol.py", "multi_agent_analysis.py",
                "multi_agent_llm.py", "calculator.py", "calculator_protocol.py", "local_llm.py",
                "experiment_config.py", "config/models.json")


def now():
    return datetime.now(timezone.utc).isoformat()


def digest_bytes(data):
    return hashlib.sha256(data).hexdigest()


def protocol_hash():
    return digest_bytes(json.dumps(FROZEN_PROTOCOL, sort_keys=True, allow_nan=False).encode())


def snapshot_hash(value):
    return digest_bytes(json.dumps(value, sort_keys=True, allow_nan=False).encode())


def strict_json(text):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result
    def reject(value):
        raise ValueError(f"Nonfinite JSON value: {value}")
    result = json.loads(text, object_pairs_hook=pairs, parse_constant=reject)
    # Also rejects finite-looking literals that overflow Python's float parser.
    json.dumps(result, allow_nan=False)
    return result


def write_json(path, value, exclusive=False):
    path = Path(path)
    if exclusive:
        with path.open("x", encoding="utf-8") as output:
            json.dump(value, output, indent=2, allow_nan=False)
            output.write("\n")
        return
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8") as output:
        json.dump(value, output, indent=2, allow_nan=False)
        output.write("\n")
    temporary.replace(path)


def append_record(output, record):
    output.write(json.dumps(record, allow_nan=False) + "\n")
    output.flush()
    os.fsync(output.fileno())


def source_hashes(config_path, tasks_path, calibration_path=None, selection_path=None):
    paths = [ROOT / name for name in SOURCE_FILES] + [Path(config_path), Path(tasks_path)]
    if calibration_path is not None:
        paths.append(Path(calibration_path))
    if selection_path is not None:
        paths.append(Path(selection_path))
    return {(path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else str(path)):
            digest_bytes(path.read_bytes()) for path in paths}


def git_output(*arguments):
    try:
        result = subprocess.run(["git", *arguments], cwd=ROOT, capture_output=True, text=True, check=False)
        return result.stdout.strip() if result.returncode == 0 else None
    except OSError:
        return None


def installed_model(client):
    health = client.health()
    model = next((item for item in health["models"]
                  if item.get("name") == MODEL or item.get("model") == MODEL), None)
    if model is None or not isinstance(model.get("digest"), str) or not model["digest"]:
        raise OllamaError(f"Installed {MODEL} with a model digest is required; run python3 setup_models.py")
    return health, model


def validate_output_directory(directory):
    directory = Path(directory).resolve()
    protected = [ROOT / "archive", ROOT / "results" / "baseline", ROOT / "results" / "runs",
                 ROOT / "results" / "multiple-choice"]
    if any(directory.is_relative_to(path.resolve()) for path in protected):
        raise ValueError("Output must be outside historical result namespaces and archives")
    if directory.exists():
        raise ValueError(f"Output directory already exists: {directory}")
    return directory


def context_budget(messages):
    # Each UTF-8 byte is a conservative upper bound for content tokenization;
    # separately reserve the two-message chat template and the full output cap.
    content_bytes = sum(len(message["content"].encode("utf-8")) for message in messages)
    bound = content_bytes + FROZEN_PROTOCOL["context_template_reserve"]
    budget = {"content_utf8_bytes": content_bytes, "prompt_token_upper_bound": bound,
              "reserved_output_tokens": FROZEN_PROTOCOL["max_tokens"],
              "context_tokens": FROZEN_PROTOCOL["context_tokens"]}
    if bound + FROZEN_PROTOCOL["max_tokens"] > FROZEN_PROTOCOL["context_tokens"]:
        raise ValueError("Context budget exceeded: full peer messages cannot be admitted without shortening; "
                         "preserve this partial run and version a larger context policy")
    return budget


def read_calibration(path):
    data = Path(path).read_bytes()
    artifact = strict_json(data.decode("utf-8"))
    if (not isinstance(artifact, dict) or artifact.get("schema_version") != 1
            or artifact.get("experiment_id") != EXPERIMENT_ID
            or artifact.get("protocol_sha256") != protocol_hash()
            or not isinstance(artifact.get("model_digest"), str)
            or not isinstance(artifact.get("ollama_version"), str)
            or not isinstance(artifact.get("references"), dict)):
        raise ValueError("Calibration artifact must match the frozen protocol and contain runtime identity")
    for key in ("token_reference", "wall_reference"):
        value = artifact["references"].get(key)
        if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
            raise ValueError("Calibration token/time references must be positive and finite")
    validate_calibration(artifact["references"])
    ids = artifact["references"].get("source_question_ids")
    if not isinstance(ids, list) or not ids or any(not isinstance(q, str) or not q for q in ids):
        raise ValueError("Calibration must identify its development questions")
    return artifact, digest_bytes(data)


def read_selection(path):
    data = Path(path).read_bytes()
    artifact = strict_json(data.decode("utf-8"))
    if (not isinstance(artifact, dict) or artifact.get("schema_version") != 1
            or artifact.get("experiment_id") != EXPERIMENT_ID
            or artifact.get("protocol_sha256") != protocol_hash()
            or type(artifact.get("primary_round")) is not int
            or not 0 <= artifact["primary_round"] <= FROZEN_PROTOCOL["max_rounds"]
            or artifact.get("primary_delta") != FROZEN_PROTOCOL["primary_delta"]
            or artifact.get("primary_omega") != FROZEN_PROTOCOL["primary_omega"]
            or not isinstance(artifact.get("validation_question_ids"), list)
            or not artifact["validation_question_ids"]
            or any(not isinstance(q, str) for q in artifact["validation_question_ids"])):
        raise ValueError("Selection must freeze the validation-chosen round under this protocol")
    return artifact, digest_bytes(data)


def validate_evaluation_inputs(tasks, calibration, selection, calibration_hash):
    roles = {("development" if task["split"] in {"development", "calibration", "inspected_development"}
              else task["split"]) for task in tasks}
    if len(roles) != 1:
        raise ValueError("Run development, validation, and test separately; choose --split for a partitioned manifest")
    role = next(iter(roles))
    if role in {"validation", "test"}:
        if calibration is None:
            raise ValueError("Validation/test inference requires --calibration from a completed development run")
        ids = {task["id"] for task in tasks}
        if ids.intersection(calibration["references"].get("source_question_ids", [])):
            raise ValueError("Validation/test questions overlap development calibration questions")
        groups = {task["group_id"] for task in tasks if "group_id" in task}
        if groups.intersection(calibration["references"].get("source_group_ids", [])):
            raise ValueError("Related question groups overlap development calibration questions")
    if role == "test":
        if selection is None:
            raise ValueError("Held-out test inference requires --selection from a completed validation run")
        if selection.get("calibration_sha256") != calibration_hash:
            raise ValueError("Selection and calibration must use the same frozen calibration artifact")
        if (selection.get("model_digest") != calibration["model_digest"]
                or selection.get("ollama_version") != calibration["ollama_version"]):
            raise ValueError("Selection and calibration runtime identities differ")
        if {task["id"] for task in tasks}.intersection(selection["validation_question_ids"]):
            raise ValueError("Held-out test questions overlap validation questions")
        if {task["group_id"] for task in tasks if "group_id" in task}.intersection(
                selection.get("validation_group_ids", [])):
            raise ValueError("Related held-out question groups overlap validation questions")
    elif selection is not None:
        raise ValueError("--selection applies only to held-out test inference")


def build_plan(config, config_hash, tasks, tasks_hash, config_path, tasks_path, directory,
               timeout, calibration_artifact=None, calibration_path=None,
               selection_artifact=None, selection_path=None):
    hashes = source_hashes(config_path, tasks_path, calibration_path, selection_path)
    if digest_bytes(Path(config_path).read_bytes()) != config_hash or digest_bytes(Path(tasks_path).read_bytes()) != tasks_hash:
        raise ValueError("Configuration or task manifest changed after it was read")
    calls, seeds = [], set()
    for task in tasks:
        for round_index in range(FROZEN_PROTOCOL["max_rounds"] + 1):
            for agent_id in range(FROZEN_PROTOCOL["num_agents"]):
                seed = agent_seed(task["id"], round_index, agent_id)
                if seed in seeds:
                    raise ValueError("Generation seed collision in the task manifest")
                seeds.add(seed)
                messages = build_messages(task, 0, agent_id) if round_index == 0 else None
                if messages is not None:
                    context_budget(messages)
                calls.append({"question_id": task["id"], "round": round_index,
                              "agent_id": agent_id, "seed": seed, "messages": messages,
                              "message_source": "original_question" if messages else "completed_previous_round"})
    return {"experiment_id": EXPERIMENT_ID, "protocol_sha256": protocol_hash(),
            "configuration": str(config_path), "configuration_sha256": config_hash,
            "configuration_snapshot": config, "task_manifest": str(tasks_path),
            "task_manifest_sha256": tasks_hash, "tasks_snapshot": tasks,
            "source_sha256": hashes, "settings": dict(FROZEN_PROTOCOL),
            "request_timeout": timeout, "output_dir": str(directory), "calls": calls,
            "planned_calls": len(calls), "planned_calculator_evaluations_max": len(calls),
            "planned_rounds": len(tasks) * (FROZEN_PROTOCOL["max_rounds"] + 1),
            "calibration_snapshot": calibration_artifact,
            "selection_snapshot": selection_artifact,
            "notes": ["Round 0 requests are exact; revision requests depend on observed prior-round responses.",
                      "This default pilot is development data, not held-out accuracy evidence.",
                      "Sequential calls use a frozen previous-round snapshot; no reference feedback."]}


def verify_identity(client, health, model, hashes, config_path, tasks_path, calibration_path, selection_path=None):
    if source_hashes(config_path, tasks_path, calibration_path, selection_path) != hashes:
        raise ValueError("Generation sources or inputs changed during the experiment")
    current_health, current_model = installed_model(client)
    if current_health["version"] != health["version"] or current_model["digest"] != model["digest"]:
        raise OllamaError("Model digest or runtime changed during the experiment")


def make_summary(manifest, records, rounds, directory):
    calibration = manifest.get("calibration_snapshot")
    summary = summarize_experiment(manifest["tasks_snapshot"], records, rounds,
                                   calibration["references"] if calibration else None)
    if summary["calibration_origin"] == "derived_from_development":
        source_ids = set(summary["calibration"]["source_question_ids"])
        summary["calibration"]["source_group_ids"] = sorted({
            t["group_id"] for t in manifest["tasks_snapshot"] if t["id"] in source_ids and "group_id" in t})
    summary.update(experiment_id=EXPERIMENT_ID, protocol_sha256=manifest["protocol_sha256"],
                   configuration_sha256=manifest["configuration_sha256"],
                   task_manifest_sha256=manifest["task_manifest_sha256"],
                   evidence_sha256={name: digest_bytes((directory / name).read_bytes())
                                    for name in ("generations.jsonl", "answers.jsonl", "rounds.jsonl")})
    selection = manifest.get("selection_snapshot")
    if selection is not None:
        selected = selection["primary_round"]
        summary["heldout_evaluation"] = {
            "selected_round": selected, "selection_sha256": manifest["selection_sha256"],
            "metrics": summary["splits"]["test"]["rounds"][selected],
            "note": "Round frozen on validation before test inference; remaining curves are descriptive.",
        }
    return summary


def run(plan, client, health, model, directory, config_path, tasks_path, calibration_path, selection_path=None):
    manifest = {**plan, "status": "running", "started_at": now(), "model_metadata": model,
                "ollama_version": health["version"], "calls_completed": 0, "rounds_completed": 0,
                "generation": {"git_revision": git_output("rev-parse", "HEAD"),
                               "git_status": git_output("status", "--porcelain"),
                               "python_version": sys.version, "platform": platform.platform(),
                               "machine": platform.machine(), "cpu_count": os.cpu_count()}}
    manifest_path = directory / "run-manifest.json"
    records, round_records, code = [], [], 0
    try:
        write_json(manifest_path, manifest, exclusive=True)
        with (directory / "generations.jsonl").open("x", encoding="utf-8") as generations, \
                (directory / "answers.jsonl").open("x", encoding="utf-8") as answers, \
                (directory / "rounds.jsonl").open("x", encoding="utf-8") as round_output:
            for task in plan["tasks_snapshot"]:
                previous, history = None, []
                for round_index in range(FROZEN_PROTOCOL["max_rounds"] + 1):
                    manifest["active_round"] = {"question_id": task["id"], "round": round_index}
                    started_round = time.perf_counter()
                    # Construct ALL requests before any generation in this round.
                    prompts = [build_messages(task, round_index, agent_id, previous)
                               for agent_id in range(FROZEN_PROTOCOL["num_agents"])]
                    budgets = [context_budget(messages) for messages in prompts]
                    current = []
                    for agent_id, messages in enumerate(prompts):
                        manifest["active_call"] = {"question_id": task["id"], "round": round_index,
                                                   "agent_id": agent_id}
                        write_json(manifest_path, manifest)
                        verify_identity(client, health, model, plan["source_sha256"],
                                        config_path, tasks_path, calibration_path, selection_path)
                        seed = agent_seed(task["id"], round_index, agent_id)
                        started = time.perf_counter()
                        raw = client.chat(MODEL, messages, seed=seed,
                                          temperature=FROZEN_PROTOCOL["temperature"],
                                          max_tokens=FROZEN_PROTOCOL["max_tokens"])
                        generation = {"type": "generation", "question_id": task["id"],
                                      "family": task["family"], "split": task["split"],
                                      "round": round_index, "agent_id": agent_id, "seed": seed,
                                      "messages": messages, "raw": raw,
                                      "elapsed_seconds": time.perf_counter() - started,
                                      "context_budget": budgets[agent_id]}
                        # Journal the unmodified response before parsing or any validation.
                        append_record(generations, generation)
                        if (not isinstance(raw.get("message"), dict)
                                or not isinstance(raw["message"].get("content"), str)):
                            raise OllamaError("Ollama wrapper is missing message.content; raw response preserved")
                        if raw.get("done") is not True or raw.get("model", MODEL) != MODEL:
                            raise OllamaError("Incomplete generation or unexpected response model; raw response preserved")
                        input_count, output_count = raw.get("prompt_eval_count"), raw.get("eval_count")
                        if (type(input_count) is int and type(output_count) is int
                                and input_count + output_count >= FROZEN_PROTOCOL["context_tokens"]):
                            raise OllamaError("Observed context saturation; raw response preserved without continuing")
                        started_post = time.perf_counter()
                        response = evaluate_response(raw, task["probability"])
                        record = {**generation, "type": "answer", "response": response,
                                  "postprocessing_seconds": time.perf_counter() - started_post}
                        append_record(answers, record)
                        records.append(record)
                        current.append(record)
                        manifest["calls_completed"] = len(records)
                        write_json(manifest_path, manifest)
                    wall_seconds = time.perf_counter() - started_round
                    # Reference answers enter only this separate, offline scoring step.
                    round_record = summarize_round(task, current, wall_seconds, history)
                    append_record(round_output, round_record)
                    round_records.append(round_record)
                    history.append(round_record)
                    previous = current
                    manifest["rounds_completed"] = len(round_records)
                    manifest.pop("active_call", None)
                    write_json(manifest_path, manifest)
                    print(f"Completed {task['id']} round {round_index}: "
                          f"{len(records)}/{plan['planned_calls']} calls", flush=True)
            verify_identity(client, health, model, plan["source_sha256"],
                            config_path, tasks_path, calibration_path, selection_path)
            append_record(answers, {"type": "complete", "calls_completed": len(records),
                                    "rounds_completed": len(round_records)})
        summary = make_summary(manifest, records, round_records, directory)
        write_json(directory / "summary.json", summary, exclusive=True)
        if summary.get("calibration") is not None and manifest.get("calibration_snapshot") is None:
            artifact = {"schema_version": 1, "experiment_id": EXPERIMENT_ID,
                        "protocol_sha256": protocol_hash(), "model_digest": model["digest"],
                        "ollama_version": health["version"], "references": summary["calibration"],
                        "source_run": str(directory), "evidence_sha256": summary["evidence_sha256"]}
            write_json(directory / "calibration.json", artifact, exclusive=True)
        if "validation" in summary["selected_rounds"]:
            primary = summary["selected_rounds"]["validation"]["primary"]
            if primary["selected_round"] is not None:
                selection = {"schema_version": 1, "experiment_id": EXPERIMENT_ID,
                             "protocol_sha256": protocol_hash(), "model_digest": model["digest"],
                             "ollama_version": health["version"], "source_run": str(directory),
                             "calibration_sha256": plan["calibration_sha256"],
                             "primary_round": primary["selected_round"],
                             "primary_delta": FROZEN_PROTOCOL["primary_delta"],
                             "primary_omega": FROZEN_PROTOCOL["primary_omega"],
                             "validation_question_ids": [t["id"] for t in plan["tasks_snapshot"]],
                             "validation_group_ids": sorted({t["group_id"] for t in plan["tasks_snapshot"] if "group_id" in t}),
                             "evidence_sha256": summary["evidence_sha256"]}
                write_json(directory / "selection.json", selection, exclusive=True)
        manifest.update(status="complete", evidence_sha256=summary["evidence_sha256"])
        manifest.pop("active_call", None)
        manifest.pop("active_round", None)
    except KeyboardInterrupt:
        manifest.update(status="interrupted", error="Interrupted by user")
        code = 130
    except (OllamaError, OSError, ValueError, KeyError, TypeError, ZeroDivisionError, OverflowError, RecursionError) as exc:
        manifest.update(status="failed", error=str(exc))
        print(f"Multi-agent run failed: {exc}", file=sys.stderr)
        code = 1
    finally:
        manifest["finished_at"] = now()
        try:
            after = source_hashes(config_path, tasks_path, calibration_path, selection_path)
            manifest.update(source_sha256_after=after, generation_sources_unchanged=after == plan["source_sha256"])
        except OSError:
            manifest.update(source_sha256_after=None, generation_sources_unchanged=False)
        if not manifest["generation_sources_unchanged"]:
            manifest.update(status="failed", error="Generation sources or inputs changed during the experiment")
            code = 1
        write_json(manifest_path, manifest)
    print(f"{manifest['status']}: results saved under {directory}")
    return code


def jsonl(path):
    return [strict_json(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def analyze_run(directory, calibration_path=None):
    directory = Path(directory).resolve()
    manifest = strict_json((directory / "run-manifest.json").read_text(encoding="utf-8"))
    if (manifest.get("status") != "complete" or manifest.get("experiment_id") != EXPERIMENT_ID
            or manifest.get("protocol_sha256") != protocol_hash()
            or manifest.get("generation_sources_unchanged") is not True):
        raise ValueError("Offline analysis requires a complete run under this frozen protocol")
    for key in ("configuration_snapshot", "tasks_snapshot", "calibration_snapshot", "selection_snapshot"):
        if snapshot_hash(manifest.get(key)) != manifest.get("snapshot_sha256", {}).get(key):
            raise ValueError(f"Frozen input snapshot hash mismatch: {key}")
    validate_config(manifest["configuration_snapshot"])
    validate_tasks(manifest["tasks_snapshot"])
    validate_evaluation_inputs(manifest["tasks_snapshot"], manifest.get("calibration_snapshot"),
                               manifest.get("selection_snapshot"), manifest.get("calibration_sha256"))
    if manifest.get("calibration_snapshot") is not None:
        artifact = manifest["calibration_snapshot"]
        validate_calibration(artifact["references"])
        if (artifact.get("protocol_sha256") != protocol_hash()
                or artifact.get("model_digest") != manifest["model_metadata"]["digest"]
                or artifact.get("ollama_version") != manifest["ollama_version"]):
            raise ValueError("Stored calibration identity does not match the generation runtime")
    if calibration_path is not None:
        artifact, _ = read_calibration(calibration_path)
        if (artifact["model_digest"] != manifest["model_metadata"]["digest"]
                or artifact["ollama_version"] != manifest["ollama_version"]):
            raise ValueError("Calibration runtime does not match this run")
        existing = manifest.get("calibration_snapshot")
        if existing is not None and artifact != existing:
            raise ValueError("Cannot replace the calibration frozen at generation time")
        if any(task["split"] in {"validation", "test"} for task in manifest["tasks_snapshot"]) and existing is None:
            raise ValueError("Validation/test runs must freeze calibration before inference")
        manifest["calibration_snapshot"] = artifact
    for name in ("generations.jsonl", "answers.jsonl", "rounds.jsonl"):
        if digest_bytes((directory / name).read_bytes()) != manifest.get("evidence_sha256", {}).get(name):
            raise ValueError(f"Evidence hash mismatch: {name}")
    events = jsonl(directory / "answers.jsonl")
    expected = len(manifest["tasks_snapshot"]) * FROZEN_PROTOCOL["num_agents"] * (FROZEN_PROTOCOL["max_rounds"] + 1)
    if (not events or events[-1] != {"type": "complete", "calls_completed": expected,
                                    "rounds_completed": len(manifest["tasks_snapshot"]) * 4}
            or len(events) != expected + 1 or any(row.get("type") != "answer" for row in events[:-1])):
        raise ValueError("Missing completion marker or incomplete answer records")
    records = events[:-1]
    generations = jsonl(directory / "generations.jsonl")
    if len(generations) != len(records):
        raise ValueError("Raw journal and evaluated records disagree")
    tasks = {task["id"]: task for task in manifest["tasks_snapshot"]}
    snapshots = defaultdict(list)
    for record, generation in zip(records, generations):
        if {**generation, "type": "answer", "response": record["response"],
                "postprocessing_seconds": record["postprocessing_seconds"]} != record:
            raise ValueError("Raw journal and evaluated record content disagree")
        task = tasks[record["question_id"]]
        if evaluate_response(record["raw"], task["probability"]) != record["response"]:
            raise ValueError("Saved evaluation does not match the independently audited raw response")
        prior = snapshots[(task["id"], record["round"] - 1)] if record["round"] else None
        if (record["seed"] != agent_seed(task["id"], record["round"], record["agent_id"])
                or record["messages"] != build_messages(task, record["round"], record["agent_id"], prior)
                or record["context_budget"] != context_budget(record["messages"])):
            raise ValueError("Saved prompt, seed, or context admission differs from the protocol")
        snapshots[(task["id"], record["round"])].append(record)
    return make_summary(manifest, records, jsonl(directory / "rounds.jsonl"), directory)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--tasks", type=Path, help="New versioned question manifest; protocol knobs stay fixed")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--calibration", type=Path)
    parser.add_argument("--selection", type=Path, help="Validation selection artifact, required before test inference")
    parser.add_argument("--split", choices=sorted({"development", "calibration", "inspected_development", "validation", "test"}))
    parser.add_argument("--analyze-run", type=Path)
    parser.add_argument("--analysis-output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.analyze_run:
            if args.dry_run or args.config or args.tasks or args.output_dir or args.selection or args.split:
                raise ValueError("Offline analysis cannot be combined with generation options")
            summary = analyze_run(args.analyze_run, args.calibration)
            if args.analysis_output:
                write_json(args.analysis_output, summary, exclusive=True)
            else:
                print(json.dumps(summary, indent=2, allow_nan=False))
            return 0
        if args.analysis_output:
            raise ValueError("--analysis-output requires --analyze-run")
        if not math.isfinite(args.timeout) or args.timeout <= 0:
            raise ValueError("timeout must be positive and finite")
        config_path = (args.config or CONFIG_PATH).resolve()
        config, config_hash = read_config(config_path)
        tasks_path = (args.tasks or config_path.parent / config["task_manifest"]).resolve()
        tasks, tasks_hash = read_tasks(tasks_path)
        if args.split:
            tasks = [task for task in tasks if task["split"] == args.split]
            if not tasks:
                raise ValueError("No questions match the requested split")
        calibration, calibration_path = None, args.calibration.resolve() if args.calibration else None
        calibration_hash = None
        if calibration_path:
            calibration, calibration_hash = read_calibration(calibration_path)
        selection, selection_path = None, args.selection.resolve() if args.selection else None
        if selection_path:
            selection, selection_hash = read_selection(selection_path)
        validate_evaluation_inputs(tasks, calibration, selection, calibration_hash)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        directory = validate_output_directory(args.output_dir or ROOT / "results" / "multi-agent" /
                                              (stamp + "-" + EXPERIMENT_ID))
        plan = build_plan(config, config_hash, tasks, tasks_hash, config_path, tasks_path,
                          directory, args.timeout, calibration, calibration_path, selection, selection_path)
        plan["selected_split"] = args.split
        plan["snapshot_sha256"] = {key: snapshot_hash(plan.get(key)) for key in (
            "configuration_snapshot", "tasks_snapshot", "calibration_snapshot", "selection_snapshot")}
        if calibration_path:
            if digest_bytes(calibration_path.read_bytes()) != calibration_hash:
                raise ValueError("Calibration changed after it was read")
            plan["calibration_sha256"] = calibration_hash
            plan["calibration_path"] = str(calibration_path)
        if selection_path:
            if digest_bytes(selection_path.read_bytes()) != selection_hash:
                raise ValueError("Selection changed after it was read")
            plan["selection_sha256"] = selection_hash
            plan["selection_path"] = str(selection_path)
        if args.dry_run:
            print(json.dumps(plan, indent=2, allow_nan=False))
            return 0
        client = OllamaClient(timeout=args.timeout)
        health, model = installed_model(client)
        if calibration and (calibration["model_digest"] != model["digest"] or calibration["ollama_version"] != health["version"]):
            raise ValueError("Calibration model digest/runtime differs from the installed model")
        verify_identity(client, health, model, plan["source_sha256"], config_path, tasks_path, calibration_path, selection_path)
        directory.mkdir(parents=True, exist_ok=False)
    except (OllamaError, OSError, ValueError, KeyError, TypeError, ZeroDivisionError, OverflowError, RecursionError) as exc:
        print(f"Multi-agent setup/analysis failed: {exc}", file=sys.stderr)
        return 1
    return run(plan, client, health, model, directory, config_path, tasks_path, calibration_path, selection_path)


if __name__ == "__main__":
    raise SystemExit(main())
