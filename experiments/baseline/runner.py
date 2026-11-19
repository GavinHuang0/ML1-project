"""Run the original single-agent planner/calculator baseline on its frozen bank."""

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import time

from calculator_protocol import SYSTEM, process_response
from experiment_config import MAX_TOKENS, MODEL, PROBABILITY_TOLERANCE, protocol_metadata
from local_llm import OllamaClient, OllamaError


ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "config" / "baseline.json"
EXPERIMENT_ID = "calculator-baseline-v1"
EXECUTION_PROTOCOL = "planner-calculator-v1"
SOURCE_FILES = ("experiments/baseline/runner.py", "calculator.py", "calculator_protocol.py",
                "local_llm.py", "experiment_config.py", "tools/setup_models.py", "config/models.json")
COHORTS = {"syntax_reuse", "pilot_reuse"}
FAMILIES = {"reasoning", "evidence", "algebra", "units"}
FLAGS = ("json_valid", "required_fields_valid", "method_format_valid", "calculator_attempted",
         "calculator_success", "numeric_correct", "correct", "exact_two_fields",
         "within_explanation_bound", "has_arithmetic_operation")
ERROR_FIELDS = ("parse_error", "calculator_error", "scoring_error")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate configuration key: {key}")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError(f"Nonfinite configuration value: {value}")


def _finite_float(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("Nonfinite configuration number")
    return number


def validate_config(config):
    if (not isinstance(config, dict) or type(config.get("schema_version")) is not int
            or config["schema_version"] != 1 or config.get("experiment_id") != EXPERIMENT_ID
            or config.get("execution_protocol") != EXECUTION_PROTOCOL
            or config.get("model") != MODEL or type(config.get("max_tokens")) is not int
            or config["max_tokens"] != MAX_TOKENS or config.get("temperature") != 0.7
            or config.get("context_tokens") != 4096 or config.get("explanation_word_limit") != 60
            or config.get("system_prompt") != SYSTEM
            or not isinstance(config.get("tasks"), list) or len(config["tasks"]) != 16
            or not isinstance(config.get("source"), dict) or not isinstance(config.get("analysis_plan"), dict)):
        raise ValueError("Unexpected fixed baseline settings or original system prompt")
    ids, sources, counts = set(), set(), Counter()
    for index, task in enumerate(config["tasks"]):
        if (not isinstance(task, dict) or task.get("id") != f"baseline-{index + 1:02d}"
                or task["id"] in ids or not isinstance(task.get("source_task_id"), str)
                or not task["source_task_id"] or task["source_task_id"] in sources
                or task.get("cohort") not in COHORTS or task.get("family") not in FAMILIES
                or task.get("split") != "inspected_development" or type(task.get("seed")) is not int
                or type(task.get("probability")) is not bool
                or task["probability"] != (task["family"] in {"reasoning", "evidence"})
                or not isinstance(task.get("prompt"), str) or not task["prompt"].strip()
                or not isinstance(task.get("gold_fraction"), str)):
            raise ValueError("Invalid, duplicate, or out-of-order baseline task")
        gold = Fraction(task["gold_fraction"])
        if task["probability"] and not 0 <= gold <= 1:
            raise ValueError("Probability reference must lie between zero and one")
        ids.add(task["id"])
        sources.add(task["source_task_id"])
        counts[(task["cohort"], task["family"])] += 1
    if counts != Counter({(cohort, family): 2 for cohort in COHORTS for family in FAMILIES}):
        raise ValueError("Each cohort must contain two tasks per family")
    policy = config.get("calculator_policy")
    if (not isinstance(policy, dict) or type(policy.get("model_calls_per_item")) is not int
            or policy["model_calls_per_item"] != 1
            or type(policy.get("calculator_calls_per_valid_expression")) is not int
            or policy["calculator_calls_per_valid_expression"] != 1
            or policy.get("reference_free") is not True
            or any(policy.get(key) is not False for key in ("feedback_to_model", "repairs", "retries"))):
        raise ValueError("Unexpected original calculator execution policy")
    if Fraction(str(policy.get("scoring_tolerance"))) != Fraction(str(PROBABILITY_TOLERANCE)):
        raise ValueError("Baseline scoring must retain the original numerical tolerance")


def read_config():
    data = CONFIG_PATH.read_bytes()
    config = json.loads(data.decode("utf-8"), object_pairs_hook=_unique_object,
                        parse_constant=_reject_constant, parse_float=_finite_float)
    validate_config(config)
    return config, hashlib.sha256(data).hexdigest()


def build_messages(config, task):
    return [{"role": "system", "content": config["system_prompt"]},
            {"role": "user", "content": task["prompt"]}]


def _config_source_name():
    return CONFIG_PATH.relative_to(ROOT).as_posix() if CONFIG_PATH.is_relative_to(ROOT) else str(CONFIG_PATH)


def source_hashes():
    hashes = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in SOURCE_FILES}
    hashes[_config_source_name()] = hashlib.sha256(CONFIG_PATH.read_bytes()).hexdigest()
    return hashes


def _git_output(*arguments):
    try:
        result = subprocess.run(["git", *arguments], cwd=ROOT, capture_output=True,
                                text=True, check=False)
    except OSError:
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def generation_metadata(hashes, timeout):
    status = _git_output("status", "--porcelain")
    return {"git_revision": _git_output("rev-parse", "HEAD"),
            "git_dirty": bool(status) if status is not None else None,
            "source_sha256": hashes, "python_version": sys.version,
            "cwd": str(Path.cwd()), "request_timeout": timeout}


def validate_output_directory(directory):
    directory = Path(directory).resolve()
    protected = (ROOT / "archive", ROOT / "results" / "runs", ROOT / "results" / "multiple-choice")
    if any(directory.is_relative_to(path.resolve()) for path in protected):
        raise ValueError("Choose a new output directory outside archives and historical result namespaces")
    if directory.exists():
        raise ValueError(f"Output directory already exists: {directory}")
    return directory


def build_plan(config, config_hash, directory, timeout=300):
    hashes = source_hashes()
    if hashes[_config_source_name()] != config_hash:
        raise ValueError("Configuration changed after it was read")
    return {"experiment_id": EXPERIMENT_ID, "execution_protocol": EXECUTION_PROTOCOL,
            "protocol": protocol_metadata(), "planned_calls": 16,
            "planned_calculator_evaluations_max": 16, "output_dir": str(directory),
            "configuration": str(CONFIG_PATH), "configuration_sha256": config_hash,
            "configuration_snapshot": config, "source_sha256": hashes,
            "settings": {"model": MODEL, "max_tokens": MAX_TOKENS, "temperature": 0.7,
                         "num_ctx": 4096, "format": "json", "keep_alive": 0,
                         "request_timeout": timeout, "explanation_word_limit": 60},
            "calls": [{"index": index, "task_id": task["id"], "seed": task["seed"],
                       "messages": build_messages(config, task)}
                      for index, task in enumerate(config["tasks"])]}


def installed_model(client):
    health = client.health()
    model = next((entry for entry in health["models"]
                  if entry.get("name") == MODEL or entry.get("model") == MODEL), None)
    if model is None:
        raise OllamaError(f"Model {MODEL} is missing. Run: python -m tools.setup_models")
    if not isinstance(model.get("digest"), str) or not model["digest"]:
        raise OllamaError("Ollama did not return the model digest")
    return health, model


def write_json(path, value, exclusive=False):
    with Path(path).open("x" if exclusive else "w", encoding="utf-8") as output:
        json.dump(value, output, indent=2, allow_nan=False)
        output.write("\n")


def model_budget(records):
    def tokens(field):
        values = [record["raw"].get(field) for record in records]
        return sum(values) if all(type(value) is int and value >= 0 for value in values) else None
    return {"calls": len(records), "input_tokens": tokens("prompt_eval_count"),
            "output_tokens": tokens("eval_count"),
            "elapsed_seconds": sum(record["elapsed_seconds"] for record in records)}


def totals(records):
    return {"items": len(records), **{flag: sum(bool(record["score"][flag]) for record in records) for flag in FLAGS},
            "length_stops": sum(record["raw"].get("done_reason") == "length" for record in records),
            "done_reasons": dict(Counter(record["raw"].get("done_reason") for record in records)),
            "errors": {field: dict(Counter(record["score"][field] for record in records if record["score"][field]))
                       for field in ERROR_FIELDS},
            "numeric_correct_with_invalid_method": sum(record["score"]["numeric_correct"]
                and not record["score"]["method_format_valid"] for record in records),
            "calculator_success_but_numeric_incorrect": sum(record["score"]["calculator_success"]
                and not record["score"]["numeric_correct"] for record in records),
            "model_budget": model_budget(records),
            "postprocessing_seconds": sum(record["postprocessing_seconds"] for record in records)}


def summarize(records, path):
    if len(records) != 16 or len({record["task"]["id"] for record in records}) != 16:
        raise ValueError("Cannot summarize an incomplete or duplicate baseline run")
    cohorts, families, groups = defaultdict(list), defaultdict(list), defaultdict(lambda: defaultdict(list))
    for record in records:
        task = record["task"]
        cohorts[task["cohort"]].append(record)
        families[task["family"]].append(record)
        groups[task["cohort"]][task["family"]].append(record)
    return {"experiment_id": EXPERIMENT_ID, "protocol": protocol_metadata(),
            "raw": str(path), "raw_sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
            "overall": totals(records), "cohorts": {key: totals(value) for key, value in cohorts.items()},
            "families": {key: totals(value) for key, value in families.items()},
            "groups": {cohort: {family: totals(value) for family, value in group.items()}
                       for cohort, group in groups.items()},
            "answers": [{"task_id": record["task"]["id"], "source_task_id": record["task"]["source_task_id"],
                         "cohort": record["task"]["cohort"], "family": record["task"]["family"],
                         "seed": record["seed"], "score": record["score"]} for record in records],
            "notes": ["The original planner-calculator-v1 prompt, parser, evaluator, and scoring are unchanged.",
                      "Only the explicit model expression is executed once; references are used after execution.",
                      "Numeric correctness is separate from complete-method delivery and secondary compliance flags.",
                      "These are inspected reused development cases, not a fresh or held-out benchmark."]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--dry-run", action="store_true", help="Preview all requests without service access or file writes")
    args = parser.parse_args(argv)
    try:
        if not math.isfinite(args.timeout) or args.timeout <= 0:
            raise ValueError("timeout must be positive and finite")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        directory = validate_output_directory(args.output_dir or ROOT / "results" / "baseline" /
                                              (stamp + "-" + EXPERIMENT_ID))
        config, digest = read_config()
        plan = build_plan(config, digest, directory, args.timeout)
        if args.dry_run:
            print(json.dumps(plan, indent=2))
            return 0
        client = OllamaClient(timeout=args.timeout)
        health, model = installed_model(client)
        if source_hashes() != plan["source_sha256"]:
            raise ValueError("Generation sources changed during preflight")
        generation = generation_metadata(plan["source_sha256"], args.timeout)
        directory.mkdir(parents=True, exist_ok=False)
    except (OllamaError, OSError, ValueError, KeyError, TypeError, ZeroDivisionError, RecursionError) as exc:
        print(f"Baseline setup failed: {exc}", file=sys.stderr)
        return 1

    manifest = {**plan, "status": "running", "started_at": datetime.now(timezone.utc).isoformat(),
                "generation": generation, "model_metadata": model, "ollama_version": health["version"],
                "calls_completed": 0, "calculator_evaluations_attempted": 0}
    manifest_path = directory / "run-manifest.json"
    raw_path, records, code = directory / "answers.jsonl", [], 0
    write_json(manifest_path, manifest, exclusive=True)
    try:
        with raw_path.open("x", encoding="utf-8") as output:
            output.write(json.dumps({"type": "metadata", **manifest}, allow_nan=False) + "\n")
            output.flush()
            for index, task in enumerate(config["tasks"]):
                if source_hashes() != plan["source_sha256"]:
                    raise ValueError("Generation sources changed during the baseline")
                current_health, current_model = installed_model(client)
                if current_health["version"] != health["version"] or current_model["digest"] != model["digest"]:
                    raise OllamaError("Model digest or runtime changed during the baseline")
                messages = plan["calls"][index]["messages"]
                manifest["active_call"] = {"index": index, "task_id": task["id"]}
                write_json(manifest_path, manifest)
                started = time.perf_counter()
                raw = client.chat(MODEL, messages, seed=task["seed"], temperature=0.7, max_tokens=MAX_TOKENS)
                elapsed = time.perf_counter() - started
                score_started = time.perf_counter()
                score = process_response(raw, task, max_explanation_words=60)
                record = {"type": "answer", "index": index, "task": task, "seed": task["seed"],
                          "messages": messages, "raw": raw, "score": score, "elapsed_seconds": elapsed,
                          "postprocessing_seconds": time.perf_counter() - score_started,
                          "calculated_answer": {"fraction": score["computed_fraction"],
                                                "decimal": score["computed_decimal"], "origin": "calculator"}}
                records.append(record)
                output.write(json.dumps(record, allow_nan=False) + "\n")
                output.flush()
                manifest["calls_completed"] = len(records)
                manifest["calculator_evaluations_attempted"] += int(score["calculator_attempted"])
                write_json(manifest_path, manifest)
                print(f"Completed {len(records)}/16: {task['id']}", flush=True)
            final_health, final_model = installed_model(client)
            if final_health["version"] != health["version"] or final_model["digest"] != model["digest"]:
                raise OllamaError("Model digest or runtime changed during the baseline")
            if source_hashes() != plan["source_sha256"]:
                raise ValueError("Generation sources changed during the baseline")
            output.write(json.dumps({"type": "complete", "calls_completed": len(records),
                                     "calculator_evaluations_attempted": manifest["calculator_evaluations_attempted"]}) + "\n")
        write_json(directory / "summary.json", summarize(records, raw_path), exclusive=True)
        manifest["status"] = "complete"
        manifest.pop("active_call", None)
    except KeyboardInterrupt:
        manifest.update(status="interrupted", error="Interrupted by user")
        code = 130
    except (OllamaError, OSError, ValueError, KeyError, TypeError, ZeroDivisionError, RecursionError) as exc:
        manifest.update(status="failed", error=str(exc))
        print(f"Baseline failed: {exc}", file=sys.stderr)
        code = 1
    finally:
        manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
        try:
            manifest["source_sha256_after"] = source_hashes()
            manifest["generation_sources_unchanged"] = manifest["source_sha256_after"] == plan["source_sha256"]
        except OSError:
            manifest.update(source_sha256_after=None, generation_sources_unchanged=False)
        if not manifest["generation_sources_unchanged"]:
            manifest.update(status="failed", error="Generation sources changed during the baseline")
            code = 1
        write_json(manifest_path, manifest)
    print(f"{manifest['status']}: results saved under {directory}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
