"""Run a separate single-agent planning-plus-calculator development pilot."""

import argparse
from collections import defaultdict
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import sys
import time

from calculator_protocol import SYSTEM, process_response
from experiment_config import (MODEL, MAX_TOKENS, PROBABILITY_TOLERANCE,
                               generation_metadata, source_hashes as common_source_hashes)
from local_llm import OllamaClient, OllamaError
from run_experiment import budget


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config" / "calculator_pilot.json"
EXPERIMENT_ID = "planner-calculator-v1"
FLAGS = ("json_valid", "required_fields_valid", "method_format_valid", "calculator_attempted",
         "calculator_success", "numeric_correct", "correct", "within_explanation_bound",
         "exact_two_fields", "has_arithmetic_operation")


def read_config():
    data = CONFIG_PATH.read_bytes()
    config = json.loads(data)
    if (config.get("schema_version") != 1 or config.get("experiment_id") != EXPERIMENT_ID
            or config.get("model") != MODEL or config.get("max_tokens") != MAX_TOKENS
            or config.get("temperature") != 0.7 or config.get("context_tokens") != 4096
            or config.get("explanation_word_limit") != 60 or len(config["tasks"]) != 8):
        raise ValueError("Unexpected fixed calculator-pilot settings")
    ids = set()
    for task in config["tasks"]:
        if (not isinstance(task["id"], str) or not task["id"] or task["id"] in ids
                or task.get("split") != "inspected_development"
                or type(task["seed"]) is not int or type(task["probability"]) is not bool
                or not isinstance(task["prompt"], str) or not task["prompt"].strip()
                or not isinstance(task["family"], str) or not task["family"]
                or task.get("answer_kind") != "expression"):
            raise ValueError("Invalid or duplicate calculator-pilot task")
        gold = Fraction(task["gold_fraction"])
        if task["probability"] and not 0 <= gold <= 1:
            raise ValueError("Probability reference must lie between zero and one")
        ids.add(task["id"])
    policy = config["calculator_policy"]
    if (policy.get("model_calls_per_item") != 1
            or policy.get("calculator_calls_per_valid_expression") != 1
            or policy.get("reference_free") is not True
            or any(policy.get(key) is not False for key in ("feedback_to_model", "repairs", "retries"))):
        raise ValueError("Unexpected calculator execution policy")
    return config, hashlib.sha256(data).hexdigest()


def source_hashes():
    hashes = common_source_hashes()
    for name in ("calculator.py", "calculator_protocol.py", "run_calculator_pilot.py"):
        hashes[name] = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
    hashes["config/calculator_pilot.json"] = hashlib.sha256(CONFIG_PATH.read_bytes()).hexdigest()
    return hashes


def protocol_metadata():
    return {"version": EXPERIMENT_ID, "model": MODEL, "max_tokens": MAX_TOKENS,
            "model_output_fields": ["explanation", "expression"],
            "answer_origin": "deterministic_calculator",
            "calculator": "restricted_exact_rational_arithmetic_v1",
            "probability_tolerance": PROBABILITY_TOLERANCE,
            "reference_free_execution": True, "model_feedback": False,
            "strict_correctness_requires_complete_method": True}


def installed_model(client):
    health = client.health()
    model = next((m for m in health["models"]
                  if m.get("name") == MODEL or m.get("model") == MODEL), None)
    if model is None:
        raise OllamaError(f"Model {MODEL} is missing. Run: python3 setup_models.py")
    if not isinstance(model.get("digest"), str) or not model["digest"]:
        raise OllamaError("Ollama did not return the model digest")
    return health, model


def write_json(path, value, exclusive=False):
    with Path(path).open("x" if exclusive else "w", encoding="utf-8") as output:
        json.dump(value, output, indent=2, allow_nan=False)
        output.write("\n")


def summarize(records, path):
    def totals(items):
        return {"items": len(items), **{flag: sum(bool(r["score"][flag]) for r in items) for flag in FLAGS},
                "length_stops": sum(r["raw"].get("done_reason") == "length" for r in items),
                "model_budget": budget(items)}
    groups = defaultdict(list)
    for record in records:
        groups[record["task"]["family"]].append(record)
    return {"experiment_id": EXPERIMENT_ID, "protocol": protocol_metadata(),
            "raw": str(path), "raw_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "overall": totals(records), "families": {key: totals(value) for key, value in groups.items()},
            "notes": ["Calculator input contains only the model's explicit expression, never references.",
                      "Numerical equivalence is not proof of correct formulation.",
                      "Known development cases; no new held-out accuracy or isolated calculator-effect claim.",
                      "Literal answers, original-givens usage, exact keys, and word limits require separate compliance review."]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--dry-run", action="store_true", help="Print the plan without Ollama calls or file writes")
    args = parser.parse_args(argv)
    try:
        if not math.isfinite(args.timeout) or args.timeout <= 0:
            raise ValueError("timeout must be positive and finite")
        config, digest = read_config()
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        directory = args.output_dir or ROOT / "results" / "runs" / ("calculator-pilot-" + stamp)
        plan = {"experiment_id": EXPERIMENT_ID, "model": MODEL, "max_tokens": MAX_TOKENS,
                "protocol": protocol_metadata(), "planned_calls": len(config["tasks"]),
                "planned_calculator_evaluations_max": len(config["tasks"]),
                "output_dir": str(directory), "configuration": str(CONFIG_PATH),
                "configuration_sha256": digest, "source_sha256": source_hashes(),
                "settings": {"temperature": 0.7, "max_tokens": MAX_TOKENS, "num_ctx": 4096,
                             "format": "json", "keep_alive": 0, "request_timeout": args.timeout,
                             "explanation_word_limit": 60},
                "system_prompt": SYSTEM, "tasks": config["tasks"]}
        if args.dry_run:
            print(json.dumps(plan, indent=2))
            return 0
        if directory.exists():
            raise ValueError(f"Output directory already exists: {directory}")
        client = OllamaClient(timeout=args.timeout)
        health, model = installed_model(client)
        if source_hashes() != plan["source_sha256"]:
            raise ValueError("Generation source changed during preflight")
        generation = {**generation_metadata(), "source_sha256": plan["source_sha256"],
                      "cwd": str(Path.cwd()), "request_timeout": args.timeout}
        directory.mkdir(parents=True, exist_ok=False)
    except (OllamaError, OSError, ValueError, KeyError, TypeError, ZeroDivisionError) as exc:
        print(f"Calculator pilot setup failed: {exc}", file=sys.stderr)
        return 1
    manifest = {**plan, "status": "running", "started_at": datetime.now(timezone.utc).isoformat(),
                "generation": generation, "model_metadata": model, "ollama_version": health["version"],
                "calls_completed": 0, "calculator_evaluations_attempted": 0}
    manifest_path = directory / "run-manifest.json"
    write_json(manifest_path, manifest, exclusive=True)
    raw_path = directory / "answers.jsonl"
    records, code = [], 0
    try:
        with raw_path.open("x", encoding="utf-8") as output:
            output.write(json.dumps({"type": "metadata", **manifest}, allow_nan=False) + "\n")
            output.flush()
            for index, task in enumerate(config["tasks"]):
                if source_hashes() != plan["source_sha256"]:
                    raise ValueError("Generation source changed during the pilot")
                current_health, current_model = installed_model(client)
                if current_health["version"] != health["version"] or current_model["digest"] != model["digest"]:
                    raise OllamaError("Model digest or runtime changed during the pilot")
                messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": task["prompt"]}]
                manifest["active_task"] = task["id"]
                write_json(manifest_path, manifest)
                started = time.perf_counter()
                raw = client.chat(MODEL, messages, seed=task["seed"], temperature=0.7, max_tokens=MAX_TOKENS)
                elapsed = time.perf_counter() - started
                score = process_response(raw, task, max_explanation_words=60)
                record = {"type": "answer", "index": index, "task": task, "seed": task["seed"],
                          "messages": messages, "raw": raw, "score": score,
                          "elapsed_seconds": elapsed,
                          "calculated_answer": {"fraction": score["computed_fraction"],
                                                "decimal": score["computed_decimal"], "origin": "calculator"}}
                records.append(record)
                output.write(json.dumps(record, allow_nan=False) + "\n")
                output.flush()
                manifest["calls_completed"] = len(records)
                manifest["calculator_evaluations_attempted"] += int(score["calculator_attempted"])
                write_json(manifest_path, manifest)
                print(f"Completed {len(records)}/{len(config['tasks'])}: {task['id']}", flush=True)
            final_health, final_model = installed_model(client)
            if final_health["version"] != health["version"] or final_model["digest"] != model["digest"]:
                raise OllamaError("Model digest or runtime changed during the pilot")
            if source_hashes() != plan["source_sha256"]:
                raise ValueError("Generation source changed during the pilot")
            output.write(json.dumps({"type": "complete", "calls_completed": len(records),
                                     "calculator_evaluations_attempted": manifest["calculator_evaluations_attempted"]}) + "\n")
        write_json(directory / "summary.json", summarize(records, raw_path), exclusive=True)
        manifest["status"] = "complete"
        manifest.pop("active_task", None)
    except KeyboardInterrupt:
        manifest.update(status="interrupted", error="Interrupted by user")
        code = 130
    except (OllamaError, OSError, ValueError, KeyError, TypeError, ZeroDivisionError) as exc:
        manifest.update(status="failed", error=str(exc))
        print(f"Calculator pilot failed: {exc}", file=sys.stderr)
        code = 1
    finally:
        manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
        try:
            manifest["source_sha256_after"] = source_hashes()
            manifest["generation_sources_unchanged"] = manifest["source_sha256_after"] == plan["source_sha256"]
        except OSError:
            manifest.update(source_sha256_after=None, generation_sources_unchanged=False)
        if not manifest["generation_sources_unchanged"]:
            manifest.update(status="failed", error="Generation source changed during the pilot")
            code = 1
        write_json(manifest_path, manifest)
    print(f"{manifest['status']}: results saved under {directory}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
