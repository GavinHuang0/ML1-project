"""Compare calculator syntax instructions with an unchanged planner/calculator pipeline."""

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import sys
import time

from calculator_protocol import SYSTEM, process_response
from experiment_config import (MAX_TOKENS, MODEL, PROBABILITY_TOLERANCE,
                               generation_metadata, source_hashes as common_source_hashes)
from local_llm import OllamaClient, OllamaError
from run_experiment import budget


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config" / "calculator_syntax_experiment.json"
EXPERIMENT_ID = "calculator-syntax-v1"
CONDITIONS = ("baseline", "syntax_clear")
FAMILIES = {"reasoning", "evidence", "algebra", "units"}
FLAGS = ("json_valid", "required_fields_valid", "method_format_valid", "calculator_attempted",
         "calculator_success", "numeric_correct", "correct", "within_explanation_bound",
         "exact_two_fields", "has_arithmetic_operation")
ERROR_FIELDS = ("parse_error", "calculator_error", "scoring_error")


def read_config():
    """Validate the fixed paired design before any model or output activity."""
    data = CONFIG_PATH.read_bytes()
    config = json.loads(data)
    if (config.get("schema_version") != 1 or config.get("experiment_id") != EXPERIMENT_ID
            or config.get("model") != MODEL or config.get("max_tokens") != MAX_TOKENS
            or config.get("temperature") != 0.7 or config.get("context_tokens") != 4096
            or config.get("explanation_word_limit") != 60
            or set(config["prompts"]) != set(CONDITIONS)
            or config["prompts"]["baseline"] != SYSTEM
            or not isinstance(config["prompts"]["syntax_clear"], str)
            or not config["prompts"]["syntax_clear"].startswith(SYSTEM)
            or config["prompts"]["syntax_clear"] == SYSTEM
            or len(config["tasks"]) != 16 or len(config["call_order"]) != 32):
        raise ValueError("Unexpected fixed calculator-syntax settings")
    tasks, counts = {}, Counter()
    for task in config["tasks"]:
        if (not isinstance(task["id"], str) or not task["id"] or task["id"] in tasks
                or task["split"] not in {"fresh", "regression"} or task["family"] not in FAMILIES
                or type(task["seed"]) is not int or type(task["probability"]) is not bool
                or not isinstance(task["prompt"], str) or not task["prompt"].strip()
                or task.get("answer_kind") != "expression" or not isinstance(task["gold_fraction"], str)):
            raise ValueError("Invalid or duplicate calculator-syntax task")
        gold = Fraction(task["gold_fraction"])
        if task["probability"] and not 0 <= gold <= 1:
            raise ValueError("Probability reference must lie between zero and one")
        if task["probability"] != (task["family"] in {"reasoning", "evidence"}):
            raise ValueError("Probability marker must agree with the task family")
        tasks[task["id"]] = task
        counts[(task["split"], task["family"])] += 1
    if counts != Counter({(split, family): 2 for split in ("fresh", "regression") for family in FAMILIES}):
        raise ValueError("Each split must contain two tasks per family")
    cells = set()
    for index in range(0, 32, 2):
        pair = config["call_order"][index:index + 2]
        expected_order = CONDITIONS if index // 2 % 2 == 0 else CONDITIONS[::-1]
        if (pair[0]["task_id"] != pair[1]["task_id"]
                or tuple(cell["condition"] for cell in pair) != expected_order):
            raise ValueError("Call order must alternate conditions within adjacent task pairs")
        for cell in pair:
            key = (cell["task_id"], cell["condition"])
            if cell["task_id"] not in tasks or cell["condition"] not in CONDITIONS or key in cells:
                raise ValueError("Invalid, duplicate, or unbalanced task/condition cell")
            cells.add(key)
    if cells != {(task_id, condition) for task_id in tasks for condition in CONDITIONS}:
        raise ValueError("Each task must receive both conditions exactly once")
    return config, hashlib.sha256(data).hexdigest()


def source_hashes():
    hashes = common_source_hashes()
    for name in ("calculator.py", "calculator_protocol.py", "run_calculator_pilot.py",
                 "config/calculator_pilot.json", "run_calculator_syntax_experiment.py"):
        hashes[name] = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
    config_name = str(CONFIG_PATH.relative_to(ROOT)) if CONFIG_PATH.is_relative_to(ROOT) else str(CONFIG_PATH)
    hashes[config_name] = hashlib.sha256(CONFIG_PATH.read_bytes()).hexdigest()
    return hashes


def protocol_metadata():
    return {"version": EXPERIMENT_ID, "model": MODEL, "max_tokens": MAX_TOKENS,
            "execution_protocol": "planner-calculator-v1", "execution_and_scoring_unchanged": True,
            "conditions": list(CONDITIONS), "model_output_fields": ["explanation", "expression"],
            "answer_origin": "deterministic_calculator", "calculator": "restricted_exact_rational_arithmetic_v1",
            "probability_tolerance": PROBABILITY_TOLERANCE, "reference_free_execution": True,
            "model_feedback": False, "repairs": False, "retries": False,
            "strict_correctness_requires_complete_method": True}


def installed_model(client):
    health = client.health()
    model = next((item for item in health["models"]
                  if item.get("name") == MODEL or item.get("model") == MODEL), None)
    if model is None:
        raise OllamaError(f"Model {MODEL} is missing. Run: python3 setup_models.py")
    if not isinstance(model.get("digest"), str) or not model["digest"]:
        raise OllamaError("Ollama did not return the model digest")
    return health, model


def write_json(path, value, exclusive=False):
    with Path(path).open("x" if exclusive else "w", encoding="utf-8") as output:
        json.dump(value, output, indent=2, allow_nan=False)
        output.write("\n")


def totals(records):
    return {"items": len(records), **{flag: sum(bool(r["score"][flag]) for r in records) for flag in FLAGS},
            "length_stops": sum(r["raw"].get("done_reason") == "length" for r in records),
            "model_budget": budget(records),
            "postprocessing_seconds": sum(r.get("postprocessing_seconds", 0) for r in records),
            "errors": {field: dict(Counter(r["score"][field] for r in records if r["score"][field]))
                       for field in ERROR_FIELDS},
            "numeric_correct_with_invalid_method": sum(r["score"]["numeric_correct"] and not r["score"]["method_format_valid"]
                                                         for r in records),
            "numeric_correct_among_method_valid": sum(r["score"]["numeric_correct"] and r["score"]["method_format_valid"]
                                                        for r in records),
            "calculator_success_but_numeric_incorrect": sum(r["score"]["calculator_success"] and not r["score"]["numeric_correct"]
                                                            for r in records)}


def summarize(records, path):
    """Separate executability, mathematical correctness, and delivered correctness."""
    path = Path(path)
    groups = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    cells = defaultdict(dict)
    for record in records:
        task = record["task"]
        groups[task["split"]][record["condition"]][task["family"]].append(record)
        cells[task["id"]][record["condition"]] = record
    if any(set(conditions) != set(CONDITIONS) for conditions in cells.values()):
        raise ValueError("Cannot summarize an incomplete paired run")
    paired = {split: {"tasks": [], "executable_transitions": Counter(), "strict_transitions": Counter(),
                      "numeric_transitions": Counter(),
                      "joint_method_valid": {"items": 0, "baseline_numeric_correct": 0,
                                             "syntax_clear_numeric_correct": 0, "numeric_transitions": Counter()}}
              for split in ("fresh", "regression")}
    for task_id, conditions in cells.items():
        before, after = conditions["baseline"], conditions["syntax_clear"]
        task = before["task"]
        transition = lambda key: f"{int(before['score'][key])}->{int(after['score'][key])}"
        executable, strict, numeric = (transition(key) for key in ("calculator_success", "correct", "numeric_correct"))
        joint = before["score"]["method_format_valid"] and after["score"]["method_format_valid"]
        group = paired[task["split"]]
        group["tasks"].append({"task_id": task_id, "family": task["family"],
                               "executable_transition": executable, "strict_transition": strict,
                               "numeric_transition": numeric, "joint_method_valid": joint,
                               "baseline": before["score"], "syntax_clear": after["score"]})
        group["executable_transitions"][executable] += 1
        group["strict_transitions"][strict] += 1
        group["numeric_transitions"][numeric] += 1
        if joint:
            group["joint_method_valid"]["items"] += 1
            group["joint_method_valid"]["baseline_numeric_correct"] += before["score"]["numeric_correct"]
            group["joint_method_valid"]["syntax_clear_numeric_correct"] += after["score"]["numeric_correct"]
            group["joint_method_valid"]["numeric_transitions"][numeric] += 1
    return {"experiment_id": EXPERIMENT_ID, "protocol": protocol_metadata(), "raw": str(path),
            "raw_sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "overall": totals(records),
            "split_condition": {split: {condition: totals([r for r in records if r["task"]["split"] == split
                                                           and r["condition"] == condition]) for condition in CONDITIONS}
                                for split in ("fresh", "regression")},
            "groups": {split: {condition: {family: totals(items) for family, items in families.items()}
                                for condition, families in conditions.items()} for split, conditions in groups.items()},
            "paired": paired,
            "notes": ["Only the prompt-clarification bundle differs; execution and scoring are unchanged.",
                      "Calculator input is only the model's explicit expression, never references.",
                      "A successful calculation or numerically matching literal does not prove correct formulation.",
                      "Fresh tasks are analyzed separately from the inspected regression cases.",
                      "Word bound, exact keys, and arithmetic-operation presence are secondary compliance flags."]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--dry-run", action="store_true", help="Inspect the paired plan without Ollama calls or output writes")
    args = parser.parse_args(argv)
    try:
        if not math.isfinite(args.timeout) or args.timeout <= 0:
            raise ValueError("timeout must be positive and finite")
        config, config_hash = read_config()
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        directory = args.output_dir or ROOT / "results" / "runs" / ("calculator-syntax-" + stamp)
        plan = {"experiment_id": EXPERIMENT_ID, "model": MODEL, "max_tokens": MAX_TOKENS,
                "protocol": protocol_metadata(), "planned_calls": 32, "planned_calculator_evaluations_max": 32,
                "output_dir": str(directory), "configuration": str(CONFIG_PATH),
                "configuration_sha256": config_hash, "source_sha256": source_hashes(),
                "settings": {"temperature": 0.7, "max_tokens": MAX_TOKENS, "num_ctx": 4096,
                             "format": "json", "keep_alive": 0, "request_timeout": args.timeout,
                             "explanation_word_limit": 60, "explanation_word_count": "whitespace_split"},
                "config": config}
        if args.dry_run:
            print(json.dumps(plan, indent=2))
            return 0
        if directory.exists():
            raise ValueError(f"Output directory already exists: {directory}")
        client = OllamaClient(timeout=args.timeout)
        health, model = installed_model(client)
        if source_hashes() != plan["source_sha256"]:
            raise ValueError("Generation sources changed during preflight")
        generation = {**generation_metadata(), "source_sha256": plan["source_sha256"],
                      "cwd": str(Path.cwd()), "request_timeout": args.timeout}
        directory.mkdir(parents=True, exist_ok=False)
    except (OllamaError, OSError, ValueError, KeyError, TypeError, ZeroDivisionError) as exc:
        print(f"Calculator syntax setup failed: {exc}", file=sys.stderr)
        return 1
    manifest = {**plan, "status": "running", "started_at": datetime.now(timezone.utc).isoformat(),
                "generation": generation, "model_metadata": model, "ollama_version": health["version"],
                "calls_completed": 0, "calculator_evaluations_attempted": 0}
    manifest_path = directory / "run-manifest.json"
    write_json(manifest_path, manifest, exclusive=True)
    raw_path, records, code = directory / "answers.jsonl", [], 0
    tasks = {task["id"]: task for task in config["tasks"]}
    try:
        with raw_path.open("x", encoding="utf-8") as output:
            output.write(json.dumps({"type": "metadata", **manifest}, allow_nan=False) + "\n")
            output.flush()
            for index, cell in enumerate(config["call_order"]):
                if source_hashes() != plan["source_sha256"]:
                    raise ValueError("Generation sources changed during the experiment")
                current_health, current_model = installed_model(client)
                if current_health["version"] != health["version"] or current_model["digest"] != model["digest"]:
                    raise OllamaError("Model digest or runtime changed during the experiment")
                task, condition = tasks[cell["task_id"]], cell["condition"]
                messages = [{"role": "system", "content": config["prompts"][condition]},
                            {"role": "user", "content": task["prompt"]}]
                manifest["active_call"] = {"index": index, **cell}
                write_json(manifest_path, manifest)
                started = time.perf_counter()
                raw = client.chat(MODEL, messages, seed=task["seed"], temperature=0.7, max_tokens=MAX_TOKENS)
                elapsed = time.perf_counter() - started
                score_started = time.perf_counter()
                score = process_response(raw, task, max_explanation_words=60)
                record = {"type": "answer", "index": index, "condition": condition, "task": task,
                          "seed": task["seed"], "messages": messages, "raw": raw, "score": score,
                          "elapsed_seconds": elapsed, "postprocessing_seconds": time.perf_counter() - score_started,
                          "calculated_answer": {"fraction": score["computed_fraction"],
                                                "decimal": score["computed_decimal"], "origin": "calculator"}}
                records.append(record)
                output.write(json.dumps(record, allow_nan=False) + "\n")
                output.flush()
                manifest["calls_completed"] = len(records)
                manifest["calculator_evaluations_attempted"] += int(score["calculator_attempted"])
                write_json(manifest_path, manifest)
                print(f"Completed {len(records)}/32: {task['id']} {condition}", flush=True)
            final_health, final_model = installed_model(client)
            if final_health["version"] != health["version"] or final_model["digest"] != model["digest"]:
                raise OllamaError("Model digest or runtime changed during the experiment")
            if source_hashes() != plan["source_sha256"]:
                raise ValueError("Generation sources changed during the experiment")
            output.write(json.dumps({"type": "complete", "calls_completed": len(records),
                                     "calculator_evaluations_attempted": manifest["calculator_evaluations_attempted"]}) + "\n")
        write_json(directory / "summary.json", summarize(records, raw_path), exclusive=True)
        manifest["status"] = "complete"
        manifest.pop("active_call", None)
    except KeyboardInterrupt:
        manifest.update(status="interrupted", error="Interrupted by user")
        code = 130
    except (OllamaError, OSError, ValueError, KeyError, TypeError, ZeroDivisionError) as exc:
        manifest.update(status="failed", error=str(exc))
        print(f"Calculator syntax experiment failed: {exc}", file=sys.stderr)
        code = 1
    finally:
        manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
        try:
            manifest["source_sha256_after"] = source_hashes()
            manifest["generation_sources_unchanged"] = manifest["source_sha256_after"] == plan["source_sha256"]
        except OSError:
            manifest.update(source_sha256_after=None, generation_sources_unchanged=False)
        if not manifest["generation_sources_unchanged"]:
            manifest.update(status="failed", error="Generation sources changed during the experiment")
            code = 1
        write_json(manifest_path, manifest)
    print(f"{manifest['status']}: results saved under {directory}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
