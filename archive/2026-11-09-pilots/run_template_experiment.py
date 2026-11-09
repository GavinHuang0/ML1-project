"""Compare baseline and bounded-template prompts on a frozen 40-call Llama pilot."""

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

from experiment_config import (MAX_TOKENS, MODEL, generation_metadata,
                               protocol_metadata, source_hashes as common_source_hashes)
from local_llm import OllamaClient, OllamaError
from run_experiment import budget
from template_scoring import score_response


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config" / "template_experiment.json"
OUTPUT_ROOT = ROOT / "results" / "runs"
EXPERIMENT_ID = "template-bounded-v1"
CONDITIONS = ("baseline", "template_bounded")
SCORE_FLAGS = ("json_valid", "required_fields_valid", "final_answer_valid", "numeric_correct",
               "format_valid", "correct", "within_explanation_bound", "exact_two_fields")


def read_config():
    """Check the paired design before contacting Ollama or creating output."""
    data = CONFIG_PATH.read_bytes()
    config = json.loads(data)
    if (config.get("schema_version") != 1 or config.get("experiment_id") != EXPERIMENT_ID
            or config.get("model") != MODEL or config.get("max_tokens") != MAX_TOKENS
            or config.get("temperature") != 0.7 or config.get("explanation_word_limit") != 60
            or set(config["prompts"]) != set(CONDITIONS)
            or any(not isinstance(p, str) or not p.strip() for p in config["prompts"].values())):
        raise ValueError("Unexpected fixed template-experiment settings")
    if len(config["tasks"]) != 20 or len(config["call_order"]) != 40:
        raise ValueError("The frozen design requires 20 tasks and 40 calls")
    tasks = {}
    split_counts = defaultdict(int)
    fresh_families = defaultdict(int)
    for task in config["tasks"]:
        if (not isinstance(task["id"], str) or not task["id"] or task["id"] in tasks
                or task["split"] not in {"fresh", "regression"}
                or type(task["seed"]) is not int
                or not isinstance(task["prompt"], str) or not task["prompt"].strip()
                or not isinstance(task["family"], str) or not task["family"]
                or not isinstance(task["stage"], str) or not task["stage"]
                or type(task["probability"]) is not bool
                or not isinstance(task["gold_fraction"], str)
                or task["answer_kind"] not in {"numeric", "expression"}):
            raise ValueError("Invalid or duplicate frozen task")
        gold = Fraction(task["gold_fraction"])
        if task["probability"] and not 0 <= gold <= 1:
            raise ValueError(f"Probability gold is outside [0, 1] for {task['id']}")
        if "gold_probability" in task:
            value = task["gold_probability"]
            if (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
                    or not 0 <= value <= 1 or abs(float(gold) - value) > 1e-12):
                raise ValueError(f"Invalid probability gold for {task['id']}")
        tasks[task["id"]] = task
        split_counts[task["split"]] += 1
        if task["split"] == "fresh":
            fresh_families[task["family"]] += 1
    if dict(split_counts) != {"fresh": 12, "regression": 8} or sorted(fresh_families.values()) != [3, 3, 3, 3]:
        raise ValueError("The design requires 12 fresh tasks (three per family) and eight regressions")
    cells = set()
    for index in range(0, 40, 2):
        pair = config["call_order"][index:index + 2]
        order = CONDITIONS if index // 2 % 2 == 0 else CONDITIONS[::-1]
        if (pair[0]["task_id"] != pair[1]["task_id"]
                or tuple(cell["condition"] for cell in pair) != order):
            raise ValueError("Call order must alternate the two conditions within adjacent task pairs")
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
    for path in (ROOT / "run_template_experiment.py", ROOT / "template_scoring.py", CONFIG_PATH):
        name = str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def build_plan(output_dir, timeout):
    config, config_hash = read_config()
    return {"experiment_id": EXPERIMENT_ID, "model": MODEL, "max_tokens": MAX_TOKENS,
            "planned_calls": len(config["call_order"]), "output_dir": str(output_dir),
            "timeout": timeout, "configuration": str(CONFIG_PATH), "configuration_sha256": config_hash,
            "protocol": protocol_metadata(), "source_sha256": source_hashes(),
            "settings": {"max_tokens": MAX_TOKENS, "temperature": config["temperature"],
                         "num_ctx": 4096, "format": "json", "keep_alive": 0,
                         "explanation_word_limit": config["explanation_word_limit"],
                         "explanation_word_count": "whitespace_split"},
            "raw": str(output_dir / "answers.jsonl"), "summary": str(output_dir / "summary.json")}, config


def installed_model(client):
    health = client.health()
    model = next((item for item in health["models"]
                  if item.get("name") == MODEL or item.get("model") == MODEL), None)
    if model is None:
        raise OllamaError(f"Model {MODEL} is missing. Run: python3 setup_models.py")
    if not isinstance(model.get("digest"), str) or not model["digest"]:
        raise OllamaError("Ollama did not provide a model digest")
    return health, model


def write_json(path, value, exclusive=False):
    with Path(path).open("x" if exclusive else "w", encoding="utf-8") as output:
        json.dump(value, output, indent=2, allow_nan=False)
        output.write("\n")


def group_summary(records):
    counts = {"items": len(records), **{key: sum(bool(r["score"][key]) for r in records) for key in SCORE_FLAGS},
              "length_stops": sum(r["raw"].get("done_reason") == "length" for r in records),
              "budget": budget(records)}
    counts["numeric_correct_among_format_valid"] = sum(r["score"]["format_valid"] and r["score"]["numeric_correct"]
                                                        for r in records)
    counts["numeric_correct_with_invalid_format"] = sum(not r["score"]["format_valid"] and r["score"]["numeric_correct"]
                                                         for r in records)
    return counts


def summarize(records, raw_path):
    groups = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(list))))
    cells = defaultdict(dict)
    for record in records:
        task = record["task"]
        groups[task["split"]][record["condition"]][task["family"]][task["stage"]].append(record)
        cells[task["id"]][record["condition"]] = record
    grouped = {split: {condition: {family: {stage: group_summary(items) for stage, items in stages.items()}
                                  for family, stages in families.items()}
                       for condition, families in conditions.items()}
               for split, conditions in groups.items()}
    split_condition = {split: {condition: group_summary([r for r in records if r["task"]["split"] == split
                                                       and r["condition"] == condition])
                              for condition in CONDITIONS}
                       for split in ("fresh", "regression")}
    paired = {}
    for split in ("fresh", "regression"):
        paired[split] = {"tasks": [], "strict_transitions": defaultdict(int),
                         "numeric_transitions": defaultdict(int),
                         "joint_format_valid": {"items": 0, "baseline_numeric_correct": 0,
                                               "template_bounded_numeric_correct": 0,
                                               "numeric_transitions": defaultdict(int)}}
    for task_id, conditions in cells.items():
        before, after = conditions["baseline"], conditions["template_bounded"]
        task = before["task"]
        strict = f"{int(before['score']['correct'])}->{int(after['score']['correct'])}"
        numeric = f"{int(before['score']['numeric_correct'])}->{int(after['score']['numeric_correct'])}"
        joint = before["score"]["format_valid"] and after["score"]["format_valid"]
        item = {"task_id": task_id, "family": task["family"], "stage": task["stage"],
                "strict_transition": strict, "numeric_transition": numeric, "joint_format_valid": joint,
                "baseline": before["score"], "template_bounded": after["score"]}
        group = paired[task["split"]]
        group["tasks"].append(item)
        group["strict_transitions"][strict] += 1
        group["numeric_transitions"][numeric] += 1
        if joint:
            joint_group = group["joint_format_valid"]
            joint_group["items"] += 1
            joint_group["baseline_numeric_correct"] += before["score"]["numeric_correct"]
            joint_group["template_bounded_numeric_correct"] += after["score"]["numeric_correct"]
            joint_group["numeric_transitions"][numeric] += 1
    return {"experiment_id": EXPERIMENT_ID, "protocol": protocol_metadata(), "raw": str(raw_path),
            "raw_sha256": hashlib.sha256(raw_path.read_bytes()).hexdigest(),
            "overall": group_summary(records), "split_condition": split_condition,
            "groups": grouped, "paired": paired}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--dry-run", action="store_true", help="Inspect the frozen plan without model calls or output writes")
    args = parser.parse_args(argv)
    try:
        if not math.isfinite(args.timeout) or args.timeout <= 0:
            raise ValueError("timeout must be positive and finite")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        output_dir = args.output_dir or OUTPUT_ROOT / ("template-bounded-" + stamp)
        plan, config = build_plan(output_dir, args.timeout)
        if args.dry_run:
            print(json.dumps({**plan, "config": config}, indent=2))
            return 0
        if output_dir.exists():
            raise ValueError(f"Output directory already exists; choose a new one: {output_dir}")
        client = OllamaClient(timeout=args.timeout)
        health, model_metadata = installed_model(client)
        if source_hashes() != plan["source_sha256"]:
            raise ValueError("Generation sources changed during preflight")
        generation = {**generation_metadata(), "source_sha256": plan["source_sha256"],
                      "cwd": str(Path.cwd()), "request_timeout": args.timeout}
        output_dir.mkdir(parents=True, exist_ok=False)
    except (OllamaError, OSError, ValueError, KeyError, TypeError, ZeroDivisionError) as exc:
        print(f"Template experiment setup failed: {exc}", file=sys.stderr)
        return 1
    manifest = {**plan, "status": "running", "started_at": datetime.now(timezone.utc).isoformat(),
                "generation": generation, "model_metadata": model_metadata, "ollama_version": health["version"],
                "calls_completed": 0}
    manifest_path = output_dir / "run-manifest.json"
    write_json(manifest_path, manifest, exclusive=True)
    metadata = {"type": "metadata", "experiment_id": EXPERIMENT_ID, "model": MODEL,
                "created_at": manifest["started_at"], "protocol": protocol_metadata(),
                "model_metadata": model_metadata, "ollama_version": health["version"],
                "configuration": str(CONFIG_PATH), "configuration_sha256": plan["configuration_sha256"],
                "settings": plan["settings"], "config": config, "generation": generation}
    records, code = [], 0
    tasks = {task["id"]: task for task in config["tasks"]}
    try:
        with Path(plan["raw"]).open("x", encoding="utf-8") as output:
            output.write(json.dumps(metadata, allow_nan=False) + "\n")
            output.flush()
            for index, cell in enumerate(config["call_order"]):
                if source_hashes() != plan["source_sha256"]:
                    raise ValueError("Generation sources changed during the experiment")
                current_health, current_model = installed_model(client)
                if current_health["version"] != health["version"] or current_model["digest"] != model_metadata["digest"]:
                    raise OllamaError("Model digest or Ollama version changed during the experiment")
                task, condition = tasks[cell["task_id"]], cell["condition"]
                messages = [{"role": "system", "content": config["prompts"][condition]},
                            {"role": "user", "content": task["prompt"]}]
                manifest["active_call"] = {"index": index, **cell}
                write_json(manifest_path, manifest)
                started = time.perf_counter()
                raw = client.chat(MODEL, messages, seed=task["seed"], temperature=config["temperature"], max_tokens=MAX_TOKENS)
                elapsed = time.perf_counter() - started
                record = {"type": "answer", "index": index, "condition": condition, "task": task,
                          "seed": task["seed"], "messages": messages, "raw": raw, "elapsed_seconds": elapsed,
                          "score": score_response(raw, task, max_explanation_words=config["explanation_word_limit"])}
                records.append(record)
                output.write(json.dumps(record, allow_nan=False) + "\n")
                output.flush()
                manifest["calls_completed"] = len(records)
                write_json(manifest_path, manifest)
                print(f"Completed {len(records)}/40: {task['id']} {condition}", flush=True)
            final_health, final_model = installed_model(client)
            if final_health["version"] != health["version"] or final_model["digest"] != model_metadata["digest"]:
                raise OllamaError("Model digest or Ollama version changed during the experiment")
            if source_hashes() != plan["source_sha256"]:
                raise ValueError("Generation sources changed during the experiment")
            output.write(json.dumps({"type": "complete", "calls_completed": len(records)}) + "\n")
        write_json(plan["summary"], summarize(records, Path(plan["raw"])), exclusive=True)
        manifest.update(status="complete")
        manifest.pop("active_call", None)
    except KeyboardInterrupt:
        manifest.update(status="interrupted", error="Interrupted by user")
        code = 130
    except (OllamaError, OSError, ValueError, KeyError, TypeError, ZeroDivisionError) as exc:
        manifest.update(status="failed", error=str(exc))
        print(f"Template experiment failed: {exc}", file=sys.stderr)
        code = 1
    finally:
        manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
        try:
            manifest["source_sha256_after"] = source_hashes()
            manifest["generation_sources_unchanged"] = manifest["source_sha256_after"] == plan["source_sha256"]
        except OSError as exc:
            manifest.update(source_sha256_after=None, generation_sources_unchanged=False)
            manifest.setdefault("error", str(exc))
        if not manifest["generation_sources_unchanged"]:
            manifest.update(status="failed", error="Generation sources changed during the experiment")
            code = 1
        write_json(manifest_path, manifest)
    print(f"{manifest['status']}: results saved under {output_dir}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
