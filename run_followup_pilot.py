"""Paired development-only JSON versus lexical-schema screening pilot.

The first Ctrl+C pauses after a durable response; --resume audits and continues
the saved prefix. The intervention changes only the transport format field.
"""

import argparse
from collections import Counter, defaultdict
import copy
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import time

from calculator_protocol import SYSTEM
from experiment_runtime import FileLock, PauseController, hardware_identity
from local_llm import OllamaClient, OllamaError, validate_model_tag
from multi_agent_analysis import summarize_round
from multi_agent_protocol import agent_seed, evaluate_response, read_tasks


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config/followup_pilot.json"
EXPERIMENT_ID = "development-format-pilot-v1"
EXPRESSION_PATTERN = r"^[0-9.()+*/ -]{1,1000}$"
STRICT_SCHEMA = {
    "type": "object",
    "properties": {"explanation": {"type": "string"},
                   "expression": {"type": "string", "pattern": EXPRESSION_PATTERN}},
    "required": ["explanation", "expression"],
    "additionalProperties": False,
}
PROFILES = {"baseline_json": "json", "strict_schema": STRICT_SCHEMA}
FAMILIES = ("reasoning", "evidence", "algebra", "units")
TASK_IDS = [f"full-v1-{family}-development-{index:02d}" for family in FAMILIES for index in (1, 2)]
PILOT_PROTOCOL = {
    "model": "llama3.2:3b", "num_agents": 10, "round": 0, "temperature": 0.7,
    "max_tokens": 1024, "context_tokens": 16384, "keep_alive": 0,
    "transport": "nonstreaming_local_ollama", "execution_mode": "sequential_alternating_pairs",
    "pair_order": "baseline_first_when_question_index_plus_agent_id_is_even",
    "seed_policy": "agent_seed(question_id,0,agent_id)",
    "prompt_policy": "unchanged_baseline_SYSTEM_and_original_question",
    "scoring": "exact_rational_plurality_ties_abstain_exact_equality",
    "explanation_word_limit": 60, "explanation_bound_is_correctness_gate": False,
    "repairs": False, "technical_min_eligible": 72, "technical_max_calculator_errors": 4,
    "maximum_collective_accuracy_loss_questions": 1,
    "adoption_policy": "recommendation_only_new_full_protocol_requires_review",
}
EXPECTED_CONFIG = {
    "schema_version": 1, "experiment_id": EXPERIMENT_ID,
    "task_manifest": "full_benchmark.json", "task_ids": TASK_IDS,
    "protocol": PILOT_PROTOCOL, "profiles": PROFILES,
}
SOURCE_FILES = ("run_followup_pilot.py", "experiment_runtime.py", "run_multi_agent.py",
                "multi_agent_protocol.py", "multi_agent_analysis.py", "calculator.py",
                "calculator_protocol.py", "local_llm.py", "experiment_config.py")
JOURNALS = ("generations.jsonl", "answers.jsonl")


class SchemaViolation(ValueError):
    """The returned strict response did not satisfy the declared schema."""


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def snapshot_hash(value):
    return digest(canonical(value).encode("utf-8"))


def now():
    return datetime.now(timezone.utc).isoformat()


def strict_json(text):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result
    def reject(value):
        raise ValueError(f"Nonfinite JSON constant: {value}")
    result = json.loads(text, object_pairs_hook=pairs, parse_constant=reject)
    canonical(result)
    return result


def atomic_json(path, value):
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as output:
        output.write(json.dumps(value, indent=2, allow_nan=False) + "\n")
        output.flush()
        os.fsync(output.fileno())
    temporary.replace(path)


def append_record(output, record):
    output.write((json.dumps(record, allow_nan=False) + "\n").encode("utf-8"))
    output.flush()
    os.fsync(output.fileno())


def load_plan(config_path):
    config_path = Path(config_path).resolve()
    config_bytes = config_path.read_bytes()
    config = strict_json(config_bytes.decode("utf-8"))
    if canonical(config) != canonical(EXPECTED_CONFIG):
        raise ValueError("Configuration differs from the frozen format pilot")
    tasks_path = (config_path.parent / config["task_manifest"]).resolve()
    all_tasks, tasks_hash = read_tasks(tasks_path)
    by_id = {task["id"]: task for task in all_tasks}
    tasks = [by_id[task_id] for task_id in TASK_IDS]
    if (len(tasks) != 8 or any(task["split"] != "development" for task in tasks)
            or Counter(task["family"] for task in tasks) != Counter({family: 2 for family in FAMILIES})
            or len({task["group_id"] for task in tasks}) != 8):
        raise ValueError("Pilot needs eight development questions from eight distinct groups")
    evidence = [task for task in tasks if task["family"] == "evidence"]
    if [task["template_id"] for task in evidence] != ["one_positive", "three_majority_positive"]:
        raise ValueError("Evidence pilot must contain the predeclared easy and three-source structures")
    hashes = {name: digest((ROOT / name).read_bytes()) for name in SOURCE_FILES}
    hashes[str(config_path)] = digest(config_bytes)
    hashes[str(tasks_path)] = tasks_hash
    calls = []
    for question_index, task in enumerate(tasks):
        messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": task["prompt"]}]
        for agent_id in range(10):
            profiles = ("baseline_json", "strict_schema") if (question_index + agent_id) % 2 == 0 else ("strict_schema", "baseline_json")
            for profile in profiles:
                calls.append({"call_index": len(calls), "question_id": task["id"],
                              "family": task["family"], "split": task["split"], "group_id": task["group_id"],
                              "round": 0, "agent_id": agent_id, "profile": profile,
                              "seed": agent_seed(task["id"], 0, agent_id), "messages": messages,
                              "format": copy.deepcopy(PROFILES[profile])})
    return {"experiment_id": EXPERIMENT_ID, "planned_calls": 160,
            "configuration_path": str(config_path), "task_manifest_path": str(tasks_path),
            "configuration_snapshot": config, "tasks_snapshot": tasks,
            "configuration_sha256": digest(config_bytes), "task_manifest_sha256": tasks_hash,
            "schema_sha256": snapshot_hash(STRICT_SCHEMA), "protocol_sha256": snapshot_hash(PILOT_PROTOCOL),
            "source_sha256": hashes, "calls": calls,
            "notes": ["Eight paired questions, not eighty independent observations per profile.",
                      "The schema restricts characters; it does not guarantee executable or correct mathematics.",
                      "Only the transport format field changes; no prompt scaffolding, repair, or tolerance change."]}


class PilotClient(OllamaClient):
    def chat(self, model, messages, *, seed, temperature, max_tokens, format_value):
        validate_model_tag(model)
        if (type(seed) is not int or temperature != 0.7 or type(max_tokens) is not int or max_tokens != 1024
                or canonical(format_value) not in {canonical(value) for value in PROFILES.values()}):
            raise ValueError("Pilot generation settings or transport format drifted")
        return self._request("/api/chat", {
            "model": model, "messages": messages, "stream": False, "format": format_value,
            "keep_alive": 0, "options": {"seed": seed, "temperature": temperature,
                                          "num_predict": max_tokens, "num_ctx": 16384},
        })


def installed_model(client):
    health = client.health()
    model = next((item for item in health["models"] if item.get("name") == "llama3.2:3b"
                  or item.get("model") == "llama3.2:3b"), None)
    if model is None or not isinstance(model.get("digest"), str) or not model["digest"]:
        raise OllamaError("Installed llama3.2:3b with an identifiable digest is required")
    return health, model


def verify_sources(manifest):
    for name, expected in manifest["source_sha256"].items():
        path = Path(name) if Path(name).is_absolute() else ROOT / name
        if digest(path.read_bytes()) != expected:
            raise ValueError(f"Frozen source/input changed: {name}")


def verify_runtime(client, manifest):
    verify_sources(manifest)
    health, model = installed_model(client)
    if health["version"] != manifest["ollama_version"] or model["digest"] != manifest["model_digest"]:
        raise ValueError("Pilot model digest or Ollama runtime changed")


def schema_conforms(raw):
    try:
        value = strict_json(raw["message"]["content"])
    except (KeyError, TypeError, ValueError):
        return False
    return (isinstance(value, dict) and set(value) == {"explanation", "expression"}
            and isinstance(value["explanation"], str) and isinstance(value["expression"], str)
            and re.fullmatch(EXPRESSION_PATTERN, value["expression"]) is not None)


def evaluate_generation(generation, task):
    raw = generation["raw"]
    if (not isinstance(raw, dict) or raw.get("done") is not True
            or raw.get("model", "llama3.2:3b") != "llama3.2:3b"
            or not isinstance(raw.get("message"), dict) or not isinstance(raw["message"].get("content"), str)):
        raise OllamaError("Incomplete or malformed Ollama response; unmodified raw response preserved")
    counts = raw.get("prompt_eval_count"), raw.get("eval_count")
    if all(type(count) is int for count in counts) and sum(counts) >= 16384:
        raise OllamaError("Observed context saturation; response preserved")
    conforms = schema_conforms(raw) if generation["profile"] == "strict_schema" else None
    if conforms is False:
        raise SchemaViolation("Strict schema violation: check runtime support or output truncation; raw preserved")
    return {**generation, "type": "answer", "schema_conforms": conforms,
            "response": evaluate_response(raw, task["probability"])}


def journal_records(path):
    data = path.read_bytes()
    lines = data.splitlines(keepends=True)
    if lines and not lines[-1].endswith(b"\n"):
        raise ValueError(f"Incomplete journal line in {path.name}; preserve evidence for inspection")
    return [strict_json(line.decode("utf-8")) for line in lines], lines


def checkpoint(directory, manifest, generations, answers):
    # Count the durable files, including a response saved immediately before a
    # forced interruption could update the in-memory lists.
    evidence = {}
    for name in JOURNALS:
        data = (directory / name).read_bytes()
        lines = data.splitlines(keepends=True)
        evidence[name] = {"records": len(lines), "sha256": digest(data)}
    manifest["calls_completed"] = evidence["answers.jsonl"]["records"]
    manifest["generations_saved"] = evidence["generations.jsonl"]["records"]
    manifest["evidence_checkpoint"] = evidence
    atomic_json(directory / "run-manifest.json", manifest)


def audit_resume(directory, manifest, plan):
    for field in ("experiment_id", "configuration_sha256", "task_manifest_sha256", "schema_sha256",
                  "protocol_sha256", "source_sha256", "configuration_snapshot", "tasks_snapshot", "calls"):
        if canonical(manifest.get(field)) != canonical(plan.get(field)):
            raise ValueError(f"Resume snapshot/protocol differs: {field}")
    if manifest.get("snapshot_sha256") != snapshot_hash({key: manifest[key] for key in
            ("configuration_snapshot", "tasks_snapshot", "calls", "hardware_snapshot", "model_digest", "ollama_version")}):
        raise ValueError("Resume snapshot hash mismatch")
    verify_sources(manifest)
    parsed = []
    for name in JOURNALS:
        records, lines = journal_records(directory / name)
        saved = manifest["evidence_checkpoint"][name]
        count = saved["records"]
        if (type(count) is not int or count < 0 or len(records) < count or len(records) > count + 1
                or digest(b"".join(lines[:count])) != saved["sha256"]):
            raise ValueError(f"Resume evidence prefix hash/count mismatch: {name}")
        parsed.append(records)
    generations, answers = parsed
    if len(generations) > 160 or len(answers) > len(generations) or len(generations) - len(answers) > 1:
        raise ValueError("Resume journals do not form a durable call prefix")
    tasks = {task["id"]: task for task in plan["tasks_snapshot"]}
    for index, generation in enumerate(generations):
        if generation.get("type") != "generation":
            raise ValueError("Unexpected raw journal record type")
        for field, expected in plan["calls"][index].items():
            if canonical(generation.get(field)) != canonical(expected):
                raise ValueError(f"Saved generation violates canonical call position: {field}")
        seconds = generation.get("elapsed_seconds")
        if type(seconds) not in (int, float) or not math.isfinite(seconds) or seconds < 0:
            raise ValueError("Saved call time is invalid")
        evaluated = evaluate_generation(generation, tasks[generation["question_id"]])
        if index < len(answers) and evaluated != answers[index]:
            raise ValueError("Saved answer disagrees with raw evaluation")
    return generations, answers


def known_token_sum(records, key):
    values = [record["raw"].get(key) for record in records]
    return sum(values) if all(type(value) is int and value >= 0 for value in values) else None


def summarize(manifest, answers):
    if len(answers) != 160:
        raise ValueError("A screening recommendation needs all 160 paired calls")
    tasks = manifest["tasks_snapshot"]
    profiles, collective = {}, {}
    for profile in PROFILES:
        records = [record for record in answers if record["profile"] == profile]
        rounds = [summarize_round(task, [r for r in records if r["question_id"] == task["id"]],
                                  sum(r["elapsed_seconds"] for r in records if r["question_id"] == task["id"]), [])
                  for task in tasks]
        eligible = sum(record["response"]["eligible"] for record in records)
        errors = sum(record["response"]["calculator_error"] is not None for record in records)
        correct = sum(row["aggregate_correct"] for row in rounds)
        profiles[profile] = {
            "calls": len(records), "questions": 8, "eligible": eligible,
            "json_valid": sum(record["response"]["json_valid"] for record in records),
            "required_fields_valid": sum(record["response"]["required_fields_valid"] for record in records),
            "calculator_errors": errors, "calculator_success": sum(record["response"]["calculator_success"] for record in records),
            "collective_correct": correct, "collective_accuracy": correct / 8,
            "technical_pass": eligible >= 72 and errors <= 4,
            "input_tokens": known_token_sum(records, "prompt_eval_count"),
            "output_tokens": known_token_sum(records, "eval_count"),
            "call_elapsed_seconds": sum(record["elapsed_seconds"] for record in records),
            "ceiling_observed": correct == 8, "floor_observed": correct == 0,
            "question_round0": rounds,
        }
        collective[profile] = {row["question_id"]: row["aggregate_correct"] for row in rounds}
    base, strict = profiles["baseline_json"], profiles["strict_schema"]
    losses = sum(collective["baseline_json"][task["id"]] and not collective["strict_schema"][task["id"]] for task in tasks)
    gains = sum(not collective["baseline_json"][task["id"]] and collective["strict_schema"][task["id"]] for task in tasks)
    noninferiority = strict["collective_correct"] >= base["collective_correct"] - 1
    if strict["technical_pass"] and noninferiority and (not base["technical_pass"] or strict["eligible"] > base["eligible"]):
        recommendation = "strict_schema_for_review"
    elif base["technical_pass"]:
        recommendation = "baseline_json"
    else:
        recommendation = "stop_and_review_neither_passes"
    return {
        "schema_version": 1, "experiment_id": EXPERIMENT_ID, "profiles": profiles,
        "paired_questions": 8, "paired_collective_gains": gains, "paired_collective_losses": losses,
        "strict_noninferiority_screen_pass": noninferiority,
        "recommendation": recommendation,
        "total_call_elapsed_seconds": sum(record["elapsed_seconds"] for record in answers),
        "notes": ["Development screening only: eight paired questions, not eighty independent samples per profile.",
                  "Call time sums exclude operator pause intervals and the other profile's intervening calls.",
                  "The one-question accuracy-loss screen is descriptive; it is not a statistical noninferiority test.",
                  "Strict selection is a recommendation only; adoption requires review and a new versioned full protocol.",
                  "Do not use test data or repair expressions to improve this screening outcome."],
    }


def execute(directory, plan, client, manifest, generations, answers, pause, timeout):
    tasks = {task["id"]: task for task in plan["tasks_snapshot"]}
    code = 0
    manifest.update(status="running", request_timeout=timeout, last_started_at=now())
    manifest.pop("error", None)
    manifest.setdefault("segments", []).append({"started_at": now(), "calls_before": len(answers)})
    try:
        with (directory / "generations.jsonl").open("ab") as raw_output, (directory / "answers.jsonl").open("ab") as answer_output:
            # A returned response durably saved before force-interruption is evaluated locally.
            if len(generations) > len(answers):
                orphan = generations[-1]
                answer = evaluate_generation(orphan, tasks[orphan["question_id"]])
                append_record(answer_output, answer)
                answers.append(answer)
                checkpoint(directory, manifest, generations, answers)
            for call in plan["calls"][len(generations):]:
                if pause.requested():
                    manifest["status"], code = "paused", 2
                    break
                verify_runtime(client, manifest)
                manifest["active_call"] = {key: call[key] for key in ("call_index", "question_id", "agent_id", "profile")}
                checkpoint(directory, manifest, generations, answers)
                started = time.perf_counter()
                raw = client.chat("llama3.2:3b", call["messages"], seed=call["seed"], temperature=0.7,
                                  max_tokens=1024, format_value=call["format"])
                generation = {**copy.deepcopy(call), "type": "generation", "raw": raw,
                              "elapsed_seconds": time.perf_counter() - started}
                append_record(raw_output, generation)
                generations.append(generation)
                checkpoint(directory, manifest, generations, answers)
                answer = evaluate_generation(generation, tasks[call["question_id"]])
                append_record(answer_output, answer)
                answers.append(answer)
                manifest.pop("active_call", None)
                checkpoint(directory, manifest, generations, answers)
                print(f"Saved {len(answers)}/160: {call['question_id']} agent {call['agent_id']} {call['profile']}", flush=True)
                if pause.requested():
                    manifest["status"], code = "paused", 2
                    break
        if len(answers) == 160:
            verify_runtime(client, manifest)
            summary = summarize(manifest, answers)
            summary_path = directory / "summary.json"
            if summary_path.exists():
                if strict_json(summary_path.read_text(encoding="utf-8")) != summary:
                    raise ValueError("Existing summary differs from completed evidence; refusing overwrite")
            else:
                atomic_json(summary_path, summary)
            manifest.update(status="complete", summary_sha256=digest(summary_path.read_bytes()))
            code = 0
    except KeyboardInterrupt:
        manifest.update(status="interrupted", error="Forced interruption; resume audits durable returned responses")
        code = 130
    except SchemaViolation as exc:
        manifest.update(status="failed", error=str(exc), schema_support_check="failed_or_truncated",
                        schema_failure_call=manifest.get("active_call"))
        print(f"Pilot stopped: {exc}", file=sys.stderr)
        code = 1
    except (OllamaError, OSError, ValueError, KeyError, TypeError, RuntimeError, ZeroDivisionError, OverflowError) as exc:
        manifest.update(status="failed", error=str(exc))
        print(f"Pilot stopped: {exc}", file=sys.stderr)
        code = 1
    finally:
        manifest["segments"][-1].update(finished_at=now(), calls_after=len(answers), status=manifest["status"])
        manifest["updated_at"] = now()
        checkpoint(directory, manifest, generations, answers)
    print(f"{manifest['status']}: {len(answers)}/160 saved in {directory}")
    return code


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--timeout", type=float, default=600)
    parser.add_argument("--dry-run", action="store_true")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--resume", action="store_true")
    action.add_argument("--pause", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.pause:
            if args.dry_run or args.config or args.output_dir is None:
                raise ValueError("--pause requires only an existing --output-dir")
            directory = args.output_dir.resolve()
            manifest = strict_json((directory / "run-manifest.json").read_text(encoding="utf-8"))
            if manifest.get("experiment_id") != EXPERIMENT_ID or manifest.get("status") == "complete":
                raise ValueError("No incomplete format pilot exists at this destination")
            (directory / ".pause-request").touch(exist_ok=True)
            print("Pause requested; the active call will be saved before stopping.")
            return 0
        if args.resume and (args.output_dir is None or args.dry_run):
            raise ValueError("--resume requires an existing --output-dir and cannot be a dry run")
        if not math.isfinite(args.timeout) or args.timeout <= 0:
            raise ValueError("timeout must be positive and finite")
        directory = (args.output_dir or ROOT / "results/followup-pilot" /
                     datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")).resolve()
        old = strict_json((directory / "run-manifest.json").read_text(encoding="utf-8")) if args.resume else None
        config_path = args.config or (Path(old["configuration_path"]) if old else CONFIG_PATH)
        plan = load_plan(config_path)
        if args.dry_run:
            print(json.dumps({**plan, "output_dir": str(directory)}, indent=2, allow_nan=False))
            return 0
        if not args.resume:
            if directory.exists():
                raise ValueError("Output directory already exists; use --resume for the same saved pilot")
            if directory.is_relative_to(ROOT / "archive") or directory.is_relative_to(ROOT / "results/baseline"):
                raise ValueError("Pilot output must stay outside historical namespaces")
            # Installation/service checks do not create an empty, unresumable run.
            client = PilotClient(timeout=args.timeout)
            health, model = installed_model(client)
            initial_hardware = hardware_identity()
            directory.mkdir(parents=True, exist_ok=False)
        with FileLock(directory / ".pilot.lock"), PauseController(directory / ".pause-request") as pause:
            if args.resume:
                # Re-read after acquiring the lock; another active process may have just checkpointed.
                old = strict_json((directory / "run-manifest.json").read_text(encoding="utf-8"))
                if old.get("status") == "complete":
                    raise ValueError("Pilot already complete; no inference will be replayed")
                generations, answers = audit_resume(directory, old, plan)
                if hardware_identity() != old["hardware_snapshot"]:
                    raise ValueError("Resume hardware identity differs from the original pilot")
                manifest = old
            else:
                generations, answers = [], []
                for name in JOURNALS:
                    (directory / name).touch(exist_ok=False)
                manifest = {**plan, "status": "initializing", "started_at": now(), "calls_completed": 0,
                            "generations_saved": 0, "hardware_snapshot": initial_hardware}
            if args.resume:
                client = PilotClient(timeout=args.timeout)
                verify_runtime(client, manifest)
            else:
                manifest.update(model_digest=model["digest"], model_metadata=model, ollama_version=health["version"])
                manifest["snapshot_sha256"] = snapshot_hash({key: manifest[key] for key in
                    ("configuration_snapshot", "tasks_snapshot", "calls", "hardware_snapshot", "model_digest", "ollama_version")})
                checkpoint(directory, manifest, generations, answers)
            pause.clear_request()
            return execute(directory, plan, client, manifest, generations, answers, pause, args.timeout)
    except KeyboardInterrupt:
        print("Pilot setup interrupted; saved evidence remains available.", file=sys.stderr)
        return 130
    except (OllamaError, OSError, ValueError, KeyError, TypeError, RuntimeError, ZeroDivisionError, OverflowError) as exc:
        print(f"Pilot setup/resume failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
