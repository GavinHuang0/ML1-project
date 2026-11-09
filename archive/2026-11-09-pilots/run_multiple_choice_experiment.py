"""Run the isolated mc-exact-v1 question bank without tools, repairs, or retries."""

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import time

from experiment_config import MAX_TOKENS, MODEL
from local_llm import OllamaClient, OllamaError
from multiple_choice_protocol import build_messages, process_response, validate_config


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config" / "multiple_choice_experiment.json"
EXPERIMENT_ID = "mc-exact-v1"
SOURCE_FILES = ("run_multiple_choice_experiment.py", "multiple_choice_protocol.py",
                "local_llm.py", "experiment_config.py")
FLAGS = ("json_valid", "required_fields_valid", "choice_valid", "choice_correct",
         "correct", "exact_two_fields", "within_explanation_bound")


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


def read_config():
    data = CONFIG_PATH.read_bytes()
    config = json.loads(data.decode("utf-8"), object_pairs_hook=_unique_object,
                        parse_constant=_reject_constant, parse_float=_finite_float)
    validate_config(config)
    return config, hashlib.sha256(data).hexdigest()


def source_hashes():
    hashes = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
              for name in SOURCE_FILES}
    name = CONFIG_PATH.relative_to(ROOT).as_posix() if CONFIG_PATH.is_relative_to(ROOT) else str(CONFIG_PATH)
    hashes[name] = hashlib.sha256(CONFIG_PATH.read_bytes()).hexdigest()
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


def protocol_metadata():
    return {"version": EXPERIMENT_ID, "model": MODEL, "max_tokens": MAX_TOKENS,
            "model_output_fields": ["explanation", "choice"], "option_count": 15,
            "scoring": "exact_selected_label", "strict_correctness_requires_both_string_fields": True,
            "word_bound_and_extra_fields_are_secondary": True,
            "external_tools": False, "repairs": False, "retries": False}


def validate_output_directory(directory):
    directory = Path(directory).resolve()
    if any(directory.is_relative_to(path.resolve())
           for path in (ROOT / "archive", ROOT / "results" / "runs")):
        raise ValueError("Choose an output directory outside archive/ and historical results/runs/")
    if directory.exists():
        raise ValueError(f"Output directory already exists: {directory}")
    return directory


def build_plan(config, config_hash, directory, timeout=300):
    hashes = source_hashes()
    config_name = CONFIG_PATH.relative_to(ROOT).as_posix() if CONFIG_PATH.is_relative_to(ROOT) else str(CONFIG_PATH)
    if hashes[config_name] != config_hash:
        raise ValueError("Configuration changed after it was read")
    return {"experiment_id": EXPERIMENT_ID, "protocol": protocol_metadata(),
            "config": config,
            "planned_calls": len(config["tasks"]), "output_dir": str(directory),
            "configuration": str(CONFIG_PATH), "configuration_sha256": config_hash,
            "source_sha256": hashes,
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
        raise OllamaError(f"Model {MODEL} is missing. Run: python3 setup_models.py")
    if not isinstance(model.get("digest"), str) or not model["digest"]:
        raise OllamaError("Ollama did not return the model digest")
    return health, model


def write_json(path, value, exclusive=False):
    with Path(path).open("x" if exclusive else "w", encoding="utf-8") as output:
        json.dump(value, output, indent=2, allow_nan=False)
        output.write("\n")


def model_budget(records):
    def tokens(field):
        counts = [record["raw"].get(field) for record in records]
        return sum(counts) if all(type(count) is int and count >= 0 for count in counts) else None
    return {"calls": len(records), "input_tokens": tokens("prompt_eval_count"),
            "output_tokens": tokens("eval_count"),
            "elapsed_seconds": sum(record["elapsed_seconds"] for record in records)}


def _distractor_rationale(task, score):
    if not score["choice_valid"] or score["choice"] == task["correct_choice"]:
        return None
    return next(option["rationale"] for option in task["options"] if option["label"] == score["choice"])


def totals(records):
    return {"items": len(records), **{flag: sum(bool(r["score"][flag]) for r in records) for flag in FLAGS},
            "strict_accuracy": sum(r["score"]["correct"] for r in records) / len(records) if records else None,
            "choice_accuracy": sum(r["score"]["choice_correct"] for r in records) / len(records) if records else None,
            "choice_correct_with_invalid_required_fields": sum(
                r["score"]["choice_correct"] and not r["score"]["required_fields_valid"] for r in records),
            "answer_letter_distribution": dict(Counter(
                r["score"]["choice"] if r["score"]["choice_valid"] else "invalid" for r in records)),
            "selected_distractor_rationale_counts": dict(Counter(
                r["selected_distractor_rationale"] for r in records if r["selected_distractor_rationale"])),
            "parse_errors": dict(Counter(r["score"]["parse_error"] for r in records if r["score"]["parse_error"])),
            "done_reasons": dict(Counter(r["raw"].get("done_reason") for r in records)),
            "length_stops": sum(r["raw"].get("done_reason") == "length" for r in records),
            "model_budget": model_budget(records),
            "scoring_seconds": sum(r["scoring_seconds"] for r in records)}


def summarize(records, path):
    if len(records) != 16 or len({record["task"]["id"] for record in records}) != 16:
        raise ValueError("Cannot summarize an incomplete or duplicate multiple-choice run")
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
            "answers": [{"task_id": r["task"]["id"], "source_task_id": r["task"]["source_task_id"],
                         "cohort": r["task"]["cohort"], "family": r["task"]["family"],
                         "seed": r["seed"], "score": r["score"],
                         "selected_distractor_rationale": r["selected_distractor_rationale"]}
                        for r in records],
            "notes": ["Headline correctness requires both string fields and the exact keyed option label.",
                      "Choices are not normalized or interpreted as numerical answers.",
                      "Option rationales and answer keys are local author metadata, never model inputs.",
                      "A selected distractor does not prove its authored misconception caused the answer.",
                      "These are reused inspected cases and one frozen option order, not held-out evidence."]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--dry-run", action="store_true", help="Preview all exact requests without service access or writes")
    args = parser.parse_args(argv)
    try:
        if not math.isfinite(args.timeout) or args.timeout <= 0:
            raise ValueError("timeout must be positive and finite")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        directory = validate_output_directory(args.output_dir or ROOT / "results" / "multiple-choice" /
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
    except (OllamaError, OSError, ValueError, KeyError, TypeError, RecursionError) as exc:
        print(f"Multiple-choice setup failed: {exc}", file=sys.stderr)
        return 1

    manifest = {**plan, "status": "running", "started_at": datetime.now(timezone.utc).isoformat(),
                "generation": generation, "model_metadata": model, "ollama_version": health["version"],
                "calls_completed": 0}
    manifest_path = directory / "run-manifest.json"
    raw_path, records, code = directory / "answers.jsonl", [], 0
    write_json(manifest_path, manifest, exclusive=True)
    try:
        with raw_path.open("x", encoding="utf-8") as output:
            output.write(json.dumps({"type": "metadata", **manifest}, allow_nan=False) + "\n")
            output.flush()
            for index, task in enumerate(config["tasks"]):
                if source_hashes() != plan["source_sha256"]:
                    raise ValueError("Generation sources changed during the experiment")
                current_health, current_model = installed_model(client)
                if current_health["version"] != health["version"] or current_model["digest"] != model["digest"]:
                    raise OllamaError("Model digest or runtime changed during the experiment")
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
                          "scoring_seconds": time.perf_counter() - score_started,
                          "selected_distractor_rationale": _distractor_rationale(task, score)}
                records.append(record)
                output.write(json.dumps(record, allow_nan=False) + "\n")
                output.flush()
                manifest["calls_completed"] = len(records)
                write_json(manifest_path, manifest)
                print(f"Completed {len(records)}/16: {task['id']}", flush=True)
            final_health, final_model = installed_model(client)
            if final_health["version"] != health["version"] or final_model["digest"] != model["digest"]:
                raise OllamaError("Model digest or runtime changed during the experiment")
            if source_hashes() != plan["source_sha256"]:
                raise ValueError("Generation sources changed during the experiment")
            output.write(json.dumps({"type": "complete", "calls_completed": len(records)}) + "\n")
        write_json(directory / "summary.json", summarize(records, raw_path), exclusive=True)
        manifest["status"] = "complete"
        manifest.pop("active_call", None)
    except KeyboardInterrupt:
        manifest.update(status="interrupted", error="Interrupted by user")
        code = 130
    except (OllamaError, OSError, ValueError, KeyError, TypeError, RecursionError) as exc:
        manifest.update(status="failed", error=str(exc))
        print(f"Multiple-choice experiment failed: {exc}", file=sys.stderr)
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
