"""Frozen paired complete-expression instruction follow-up on development data.

The first Ctrl+C pauses after a durable response; --resume audits and continues
the saved prefix. Both profiles use the same strict schema; only one appended
expression-completion instruction changes. Regression and screening stay separate.
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
import random
import sys
import time

from calculator_protocol import SYSTEM
from build_format_followup_tasks import generate_manifest
from experiment_runtime import FileLock, PauseController, hardware_identity
from local_llm import OllamaClient, OllamaError, validate_model_tag
from multi_agent_analysis import summarize_round
from multi_agent_protocol import agent_seed, evaluate_response, read_tasks


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config/format_followup.json"
EXPERIMENT_ID = "development-complete-expression-pilot-v2"
EXPRESSION_PATTERN = r"^[0-9.()+*/ -]{1,1000}$"
STRICT_SCHEMA = {
    "type": "object",
    "properties": {"explanation": {"type": "string"},
                   "expression": {"type": "string", "pattern": EXPRESSION_PATTERN}},
    "required": ["explanation", "expression"],
    "additionalProperties": False,
}
COMPLETE_EXPRESSION_INSTRUCTION = (
    "Before returning JSON, make expression a complete, finite arithmetic expression consistent with your explanation. "
    "Write every multiplication with *. Do not use assignments, ellipses, implicit multiplication, or unfinished operators. "
    "Check balanced parentheses and include an operand on both sides of every binary operator."
)
PROFILES = {"strict_schema": STRICT_SCHEMA, "complete_expression": STRICT_SCHEMA}
SYSTEM_PROMPTS = {"strict_schema": SYSTEM,
                  "complete_expression": SYSTEM + "\n" + COMPLETE_EXPRESSION_INSTRUCTION}
FAMILIES = ("reasoning", "evidence", "algebra", "units")
REGRESSION_TASK_IDS = [f"full-v1-{family}-development-{index:02d}" for family in FAMILIES for index in (1, 2)]
SCREENING_TASK_IDS = [f"format-v2-{family}-development-{index:02d}" for family in FAMILIES for index in (1, 2)]
TASK_IDS = REGRESSION_TASK_IDS + SCREENING_TASK_IDS
PLANNED_CALLS = 320
PILOT_PROTOCOL = {
    "model": "llama3.2:3b", "num_agents": 10, "round": 0, "temperature": 0.7,
    "max_tokens": 1024, "context_tokens": 16384, "keep_alive": 0,
    "transport": "nonstreaming_local_ollama", "execution_mode": "sequential_alternating_pairs",
    "pair_order": "strict_schema_first_when_question_index_plus_agent_id_is_even",
    "seed_policy": "agent_seed(question_id,0,agent_id)",
    "prompt_policy": "same_strict_schema_and_original_question_only_candidate_appends_complete_expression_instruction",
    "scoring": "exact_rational_plurality_ties_abstain_exact_equality",
    "explanation_word_limit": 60, "explanation_bound_is_correctness_gate": False,
    "repairs": False, "technical_min_eligible": 72, "technical_max_calculator_errors": 4,
    "maximum_collective_accuracy_loss_questions": 1,
    "decision_set": "screening",
    "regression_role": "descriptive_only_no_selection_or_retuning",
    "adoption_policy": "recommendation_only_new_full_protocol_requires_review",
}
EXPECTED_CONFIG = {
    "schema_version": 1, "experiment_id": EXPERIMENT_ID,
    "task_manifest": "format_followup_tasks.json", "task_ids": TASK_IDS,
    "evaluation_sets": {"regression": REGRESSION_TASK_IDS, "screening": SCREENING_TASK_IDS},
    "protocol": PILOT_PROTOCOL, "profiles": PROFILES, "system_prompts": SYSTEM_PROMPTS,
}
SOURCE_FILES = ("run_format_followup.py", "run_format_followup.ps1", "build_format_followup_tasks.py", "build_full_benchmark.py", "config/full_benchmark.json", "experiment_runtime.py", "run_multi_agent.py",
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
        raise ValueError("Configuration differs from the frozen complete-expression follow-up")
    tasks_path = (config_path.parent / config["task_manifest"]).resolve()
    all_tasks, tasks_hash = read_tasks(tasks_path)
    by_id = {task["id"]: task for task in all_tasks}
    if set(by_id) != set(TASK_IDS):
        raise ValueError("Manifest must contain exactly the sixteen frozen development tasks")
    task_manifest = strict_json(tasks_path.read_text(encoding="utf-8"))
    if canonical(task_manifest) != canonical(generate_manifest()):
        raise ValueError("Task manifest differs from independently audited deterministic development generation")
    if (task_manifest.get("regression_task_ids") != REGRESSION_TASK_IDS
            or task_manifest.get("screening_task_ids") != SCREENING_TASK_IDS):
        raise ValueError("Manifest evaluation-set membership differs from the frozen plan")
    tasks = [by_id[task_id] for task_id in TASK_IDS]
    for evaluation_set, task_ids in EXPECTED_CONFIG["evaluation_sets"].items():
        selected = [by_id[task_id] for task_id in task_ids]
        if (any(task["split"] != "development" for task in selected)
                or Counter(task["family"] for task in selected) != Counter({family: 2 for family in FAMILIES})
                or len({task["group_id"] for task in selected}) != 8):
            raise ValueError(f"{evaluation_set} needs eight development questions from eight distinct groups")
        evidence = [task for task in selected if task["family"] == "evidence"]
        if [task["template_id"] for task in evidence] != ["one_positive", "three_majority_positive"]:
            raise ValueError("Evidence pilot must contain the frozen easy and three-source structures")
    # Numeric variants are deliberately grouped with their inspected structures.
    if any(by_id[reg]["group_id"] != by_id[new]["group_id"]
           for reg, new in zip(REGRESSION_TASK_IDS, SCREENING_TASK_IDS)):
        raise ValueError("Fresh numeric variants must retain their original structural groups")
    hashes = {name: digest((ROOT / name).read_bytes()) for name in SOURCE_FILES}
    hashes[str(config_path)] = digest(config_bytes)
    hashes[str(tasks_path)] = tasks_hash
    calls = []
    for question_index, task in enumerate(tasks):
        evaluation_set = "regression" if task["id"] in REGRESSION_TASK_IDS else "screening"
        for agent_id in range(10):
            profiles = ("strict_schema", "complete_expression") if (question_index + agent_id) % 2 == 0 else ("complete_expression", "strict_schema")
            for profile in profiles:
                messages = [{"role": "system", "content": SYSTEM_PROMPTS[profile]},
                            {"role": "user", "content": task["prompt"]}]
                if sum(len(message["content"].encode("utf-8")) for message in messages) + 1024 >= 16384:
                    raise ValueError("Conservative UTF-8 context admission failed")
                calls.append({"call_index": len(calls), "question_id": task["id"],
                              "evaluation_set": evaluation_set,
                              "family": task["family"], "split": task["split"], "group_id": task["group_id"],
                              "round": 0, "agent_id": agent_id, "profile": profile,
                              "seed": agent_seed(task["id"], 0, agent_id), "messages": messages,
                              "format": copy.deepcopy(PROFILES[profile])})
    seeds = [agent_seed(task_id, 0, agent_id) for task_id in TASK_IDS for agent_id in range(10)]
    if len(seeds) != len(set(seeds)):
        raise ValueError("Per-agent seed collision across distinct question-agent positions")
    return {"experiment_id": EXPERIMENT_ID, "planned_calls": PLANNED_CALLS,
            "configuration_path": str(config_path), "task_manifest_path": str(tasks_path),
            "configuration_snapshot": config, "tasks_snapshot": tasks,
            "configuration_sha256": digest(config_bytes), "task_manifest_sha256": tasks_hash,
            "schema_sha256": snapshot_hash(STRICT_SCHEMA), "protocol_sha256": snapshot_hash(PILOT_PROTOCOL),
            "source_sha256": hashes, "calls": calls,
            "notes": ["Eight paired screening questions, not eighty independent observations per profile.",
                      "The eight regression questions are descriptive; only fresh development screening controls selection.",
                      "Screening uses fresh numerical variants of inspected structures, not structural holdout.",
                      "The schema restricts characters; it does not guarantee executable or correct mathematics.",
                      "Both profiles use the identical schema; only the candidate completion instruction changes.",
                      "No response repair, reference feedback, mathematical scaffold, or scoring-tolerance change."]}


class PilotClient(OllamaClient):
    def chat(self, model, messages, *, seed, temperature, max_tokens, format_value):
        validate_model_tag(model)
        if (type(seed) is not int or temperature != 0.7 or type(max_tokens) is not int or max_tokens != 1024
                or model != "llama3.2:3b" or canonical(format_value) != canonical(STRICT_SCHEMA)
                or not isinstance(messages, list) or len(messages) != 2
                or messages[0] not in [{"role": "system", "content": value} for value in SYSTEM_PROMPTS.values()]
                or messages[1].get("role") != "user" or not isinstance(messages[1].get("content"), str)):
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
    if generation["profile"] not in PROFILES:
        raise ValueError("Unknown frozen instruction profile")
    conforms = schema_conforms(raw)
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
    if len(generations) > plan["planned_calls"] or len(answers) > len(generations) or len(generations) - len(answers) > 1:
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


def paired_intervals(tasks, collective, per_question):
    """Descriptive paired intervals over eight whole question/structural groups."""
    rng = random.Random(20261118)
    families = {family: [task["id"] for task in tasks if task["family"] == family] for family in FAMILIES}
    draws = {"collective_accuracy_difference": [], "eligibility_rate_difference": [],
             "individual_accuracy_difference": []}
    for _ in range(2000):
        selected = [rng.choice(ids) for ids in families.values() for _ in ids]
        draws["collective_accuracy_difference"].append(sum(
            int(collective["complete_expression"][task_id]) - int(collective["strict_schema"][task_id])
            for task_id in selected) / 8)
        for metric, key in (("eligibility_rate_difference", "valid_agents"),
                            ("individual_accuracy_difference", "exact_agent_correct")):
            draws[metric].append(sum(per_question["complete_expression"][task_id][key]
                                     - per_question["strict_schema"][task_id][key]
                                     for task_id in selected) / 80)
    return {"method": "paired_family_stratified_whole_question_group_percentile_bootstrap",
            "draws": 2000, "seed": 20261118, "groups": 8,
            "contrast": "complete_expression_minus_strict_schema",
            "intervals_95": {key: [sorted(values)[49], sorted(values)[1949]] for key, values in draws.items()},
            "note": "Descriptive development intervals from eight groups; degenerate intervals do not prove equivalence."}


def summarize_set(tasks, answers, evaluation_set):
    profiles, collective = {}, {}
    per_question = {}
    for profile in PROFILES:
        records = [record for record in answers if record["profile"] == profile]
        rounds = [summarize_round(task, [r for r in records if r["question_id"] == task["id"]],
                                  sum(r["elapsed_seconds"] for r in records if r["question_id"] == task["id"]), [])
                  for task in tasks]
        eligible = sum(record["response"]["eligible"] for record in records)
        errors = sum(record["response"]["calculator_error"] is not None for record in records)
        correct = sum(row["aggregate_correct"] for row in rounds)
        exact_agent_correct = sum(sum(row["agent_correct"].values()) for row in rounds)
        profiles[profile] = {
            "calls": len(records), "questions": 8, "eligible": eligible,
            "json_valid": sum(record["response"]["json_valid"] for record in records),
            "required_fields_valid": sum(record["response"]["required_fields_valid"] for record in records),
            "calculator_errors": errors, "calculator_success": sum(record["response"]["calculator_success"] for record in records),
            "collective_correct": correct, "collective_accuracy": correct / 8,
            "exact_agent_correct": exact_agent_correct, "individual_accuracy": exact_agent_correct / 80,
            "collective_abstentions": sum(row["aggregate_abstained"] for row in rounds),
            "probability_out_of_range": sum(record["response"]["status"] == "probability_out_of_range" for record in records),
            "calculator_error_counts": dict(Counter(record["response"]["calculator_error"] for record in records
                                                     if record["response"]["calculator_error"] is not None)),
            "length_stops": sum(record["raw"].get("done_reason") == "length" for record in records),
            "explanation_over_limit": sum(not record["response"]["within_explanation_bound"] for record in records),
            "technical_pass": eligible >= 72 and errors <= 4,
            "input_tokens": known_token_sum(records, "prompt_eval_count"),
            "output_tokens": known_token_sum(records, "eval_count"),
            "call_elapsed_seconds": sum(record["elapsed_seconds"] for record in records),
            "ceiling_observed": correct == 8, "floor_observed": correct == 0,
            "question_round0": rounds,
        }
        collective[profile] = {row["question_id"]: row["aggregate_correct"] for row in rounds}
        per_question[profile] = {row["question_id"]: {"valid_agents": row["valid_agents"],
                                                    "exact_agent_correct": sum(row["agent_correct"].values())}
                                 for row in rounds}
    control, candidate = profiles["strict_schema"], profiles["complete_expression"]
    losses = sum(collective["strict_schema"][task["id"]] and not collective["complete_expression"][task["id"]] for task in tasks)
    gains = sum(not collective["strict_schema"][task["id"]] and collective["complete_expression"][task["id"]] for task in tasks)
    accuracy_screen = candidate["collective_correct"] >= control["collective_correct"] - 1
    if evaluation_set == "regression":
        recommendation = "descriptive_only"
    elif candidate["technical_pass"] and accuracy_screen and (not control["technical_pass"] or candidate["eligible"] > control["eligible"]):
        recommendation = "complete_expression_for_review"
    elif control["technical_pass"]:
        recommendation = "strict_schema"
    else:
        recommendation = "stop_and_review_neither_passes"
    return {
        "evaluation_set": evaluation_set, "selection_eligible": evaluation_set == "screening", "profiles": profiles,
        "paired_questions": 8, "paired_collective_gains": gains, "paired_collective_losses": losses,
        "candidate_accuracy_screen_pass": accuracy_screen,
        "uncertainty": paired_intervals(tasks, collective, per_question),
        "recommendation": recommendation,
        "total_call_elapsed_seconds": sum(record["elapsed_seconds"] for record in answers),
    }


def summarize(manifest, answers):
    if len(answers) != PLANNED_CALLS:
        raise ValueError(f"A screening recommendation needs all {PLANNED_CALLS} paired calls")
    sets = {}
    for evaluation_set, task_ids in EXPECTED_CONFIG["evaluation_sets"].items():
        tasks = [task for task in manifest["tasks_snapshot"] if task["id"] in task_ids]
        selected = [record for record in answers if record["question_id"] in task_ids]
        if len(tasks) != 8 or len(selected) != 160:
            raise ValueError("Both evaluation sets need their complete 160-call paired evidence")
        sets[evaluation_set] = summarize_set(tasks, selected, evaluation_set)
    return {
        "schema_version": 1, "experiment_id": EXPERIMENT_ID, "sets": sets,
        "decision_set": "screening", "recommendation": sets["screening"]["recommendation"],
        "total_calls": len(answers), "total_call_elapsed_seconds": sum(record["elapsed_seconds"] for record in answers),
        "notes": ["Development screening only: eight paired screening questions, not eighty independent samples per profile.",
                  "Regression results are descriptive and cannot change the frozen screening rule or candidate.",
                  "Regression and screening share eight semantic groups; fresh numeric variants are not structural holdout.",
                  "Call time sums exclude operator pause intervals and the other profile's intervening calls.",
                  "The one-question accuracy-loss screen is descriptive; it is not a statistical noninferiority test.",
                  "Selection is a recommendation only; adoption requires review and a new versioned full protocol.",
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
                print(f"Saved {len(answers)}/{PLANNED_CALLS}: {call['evaluation_set']} {call['question_id']} agent {call['agent_id']} {call['profile']}", flush=True)
                if pause.requested():
                    manifest["status"], code = "paused", 2
                    break
        if len(answers) == PLANNED_CALLS:
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
    print(f"{manifest['status']}: {len(answers)}/{PLANNED_CALLS} saved in {directory}")
    return code


def analyze_run(directory):
    """Audit evidence without locks, service calls, hardware reads, or writes."""
    directory = Path(directory).resolve()
    manifest = strict_json((directory / "run-manifest.json").read_text(encoding="utf-8"))
    if manifest.get("experiment_id") != EXPERIMENT_ID:
        raise ValueError("Analysis requires a complete-expression follow-up run")
    if manifest.get("status") in {"running", "initializing"}:
        raise ValueError("Pause the active writer before offline analysis")
    plan = load_plan(Path(manifest["configuration_path"]))
    generations, answers = audit_resume(directory, manifest, plan)
    result = {"offline_audit": "passed", "status": manifest["status"],
              "calls_completed": len(answers), "generations_saved": len(generations),
              "summary_reproduced": None}
    if manifest.get("status") == "complete":
        if len(generations) != PLANNED_CALLS or len(answers) != PLANNED_CALLS:
            raise ValueError("Completed run has incomplete evidence")
        summary_path = directory / "summary.json"
        if digest(summary_path.read_bytes()) != manifest.get("summary_sha256"):
            raise ValueError("Summary evidence hash mismatch")
        summary = summarize(manifest, answers)
        if strict_json(summary_path.read_text(encoding="utf-8")) != summary:
            raise ValueError("Saved summary disagrees with recomputed evidence")
        result.update(summary_reproduced=True, summary=summary)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--timeout", type=float, default=600)
    parser.add_argument("--dry-run", action="store_true")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--resume", action="store_true")
    action.add_argument("--pause", action="store_true")
    action.add_argument("--analyze-run", type=Path, help="Audit a saved run offline without inference or writes")
    args = parser.parse_args(argv)
    try:
        if args.analyze_run is not None:
            if args.dry_run or args.config or args.output_dir:
                raise ValueError("--analyze-run accepts only a saved run directory")
            print(json.dumps(analyze_run(args.analyze_run), indent=2, allow_nan=False))
            return 0
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
        directory = (args.output_dir or ROOT / "results/format-followup" /
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
