"""Run the active Llama 3.2 3B pilots at 1024 tokens; no downloads are performed."""

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys
import time

import analyze_results
from experiment_config import (MAX_TOKENS, MODEL, PROTOCOL_VERSION,
                               generation_metadata, protocol_metadata, source_hashes)
from local_llm import OllamaClient, OllamaError
from pilot_scoring import score_response
import run_experiment as experiment


ROOT = Path(__file__).resolve().parent
ARTIFACTS = ROOT / "results" / "runs"
CONFIG_PATH = ROOT / "config" / "pilots.json"
FILENAMES = {"full": "full1024", "urn-check": "urn-check1024", "diagnostic": "diagnostic1024"}
COUNTS = {"full": 60, "urn-check": 4, "diagnostic": 16}


def read_protocol():
    """Validate the active prompt/case configuration without reading old results."""
    data = CONFIG_PATH.read_bytes()
    config = json.loads(data)
    if (config.get("schema_version") != 2 or config.get("protocol_version") != PROTOCOL_VERSION
            or config.get("model") != MODEL or config.get("max_tokens") != MAX_TOKENS
            or set(config["profiles"]) != {"urn-check", "diagnostic"}):
        raise ValueError(f"Unexpected active protocol settings: {CONFIG_PATH}")
    expected_conditions = {"urn-check": {"original", "math_check"},
                           "diagnostic": {"baseline", "checking"}}
    for name, profile in config["profiles"].items():
        if len(profile["cases"]) != COUNTS[name] or set(profile["prompts"]) != expected_conditions[name]:
            raise ValueError(f"Unexpected conditions or case count in {name}")
        cells, tasks, seeds = set(), {}, {}
        for case in profile["cases"]:
            task, condition, seed = case["task"], case["condition"], case["seed"]
            expected = [{"role": "system", "content": profile["prompts"][condition]},
                        {"role": "user", "content": task["prompt"]}]
            cell = (condition, task["id"])
            if (case["messages"] != expected or type(seed) is not int or cell in cells
                    or ("seed" in task and task["seed"] != seed)
                    or (task["id"] in tasks and tasks[task["id"]] != task)
                    or (task["id"] in seeds and seeds[task["id"]] != seed)):
                raise ValueError(f"Inconsistent active prompt/seed/cell in {name}: {task['id']}")
            cells.add(cell)
            tasks[task["id"]], seeds[task["id"]] = task, seed
        if cells != {(condition, task_id) for condition in expected_conditions[name] for task_id in tasks}:
            raise ValueError(f"Unpaired conditions in {name}")
    return config, hashlib.sha256(data).hexdigest()


def build_plan(model, pilot, output_dir, timeout=300):
    if model != MODEL:
        raise ValueError(f"The active protocol only supports {MODEL}")
    _, digest = read_protocol()
    selected = list(COUNTS) if pilot == "all" else [pilot]
    jobs = [{"pilot": name, "planned_calls": COUNTS[name], "max_tokens": MAX_TOKENS,
             "raw": str(output_dir / (FILENAMES[name] + ".jsonl")),
             "summary": str(output_dir / (FILENAMES[name] + ".summary.json")),
             "protocol_file": str(CONFIG_PATH), "protocol_sha256": digest}
            for name in selected]
    return {"model": model, "max_tokens": MAX_TOKENS, "protocol": protocol_metadata(),
            "output_dir": str(output_dir), "timeout": timeout,
            "planned_calls": sum(job["planned_calls"] for job in jobs), "jobs": jobs}


def installed_model(client, model):
    health = client.health()
    metadata = next((item for item in health["models"]
                     if item.get("name") == model or item.get("model") == model), None)
    if metadata is None:
        raise OllamaError(f"Model {model} is missing. Run: python3 setup_models.py")
    return health, metadata


def write_json(path, value, exclusive=False):
    with Path(path).open("x" if exclusive else "w", encoding="utf-8") as output:
        json.dump(value, output, indent=2, allow_nan=False)
        output.write("\n")


def run_single(client, model, job, health, model_metadata, generation):
    config, digest = read_protocol()
    if digest != job["protocol_sha256"]:
        raise ValueError("Active pilot configuration changed after planning")
    profile = config["profiles"][job["pilot"]]
    records = []
    metadata = {"type": "metadata", "pilot": job["pilot"], "model": model,
                "protocol": protocol_metadata(), "model_metadata": model_metadata,
                "ollama_version": health["version"],
                "created_at": datetime.now(timezone.utc).isoformat(),
                "settings": {"max_tokens": MAX_TOKENS, "temperature": 0.7,
                             "timeout": generation["request_timeout"],
                             "sampling_seeds": {c["task"]["id"]: c["seed"] for c in profile["cases"]}},
                "provenance": {"configuration": job["protocol_file"], "sha256": digest,
                               "origin": profile["source"]},
                "generation": generation, "prompts": profile["prompts"],
                "scope": "Independent single-agent calls using the active frozen prompts and seeds"}
    with Path(job["raw"]).open("x", encoding="utf-8") as output:
        output.write(json.dumps(metadata) + "\n")
        output.flush()
        for case in profile["cases"]:
            task, seed = case["task"], case["seed"]
            started = time.perf_counter()
            raw = client.chat(model, case["messages"], seed=seed, temperature=0.7, max_tokens=MAX_TOKENS)
            record = {"type": "answer", "condition": case["condition"], "task": task,
                      "seed": seed, "messages": case["messages"], "raw": raw,
                      "elapsed_seconds": time.perf_counter() - started,
                      "score": score_response(raw, task, job["pilot"])}
            records.append(record)
            output.write(json.dumps(record, allow_nan=False) + "\n")
            output.flush()
            print(f"{job['pilot']}: {len(records)}/{job['planned_calls']} "
                  f"{case['condition']} {task['id']}", flush=True)
        output.write(json.dumps({"type": "complete", "calls_completed": len(records)}) + "\n")
    groups = defaultdict(lambda: defaultdict(lambda: {"items": 0, "correct": 0, "invalid": 0}))
    for record in records:
        group = groups[record["condition"]][record["task"].get("stage", "full_solution")]
        group["items"] += 1
        group["correct"] += record["score"]["correct"]
        group["invalid"] += not record["score"]["format_valid"]
    return {"raw": job["raw"], "raw_sha256": hashlib.sha256(Path(job["raw"]).read_bytes()).hexdigest(),
            "protocol": protocol_metadata(), "groups": groups, "budget": experiment.budget(records),
            "length_stops": sum(r["raw"].get("done_reason") == "length" for r in records),
            "answers": [{"condition": r["condition"], "task_id": r["task"]["id"],
                         "score": r["score"], "output_tokens": r["raw"].get("eval_count")}
                        for r in records]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=(MODEL,), default=MODEL)
    parser.add_argument("--max-tokens", type=int, choices=(MAX_TOKENS,), default=MAX_TOKENS)
    parser.add_argument("--pilot", choices=(*COUNTS, "all"), default="all")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--dry-run", action="store_true", help="Print the plan without Ollama calls or file writes")
    args = parser.parse_args(argv)
    try:
        model = args.model
        if not math.isfinite(args.timeout) or args.timeout <= 0:
            raise ValueError("timeout must be positive and finite")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        output_dir = args.output_dir or ARTIFACTS / ("llama3.2-3b-pilots-" + stamp)
        plan = build_plan(model, args.pilot, output_dir, args.timeout)
        if args.dry_run:
            print(json.dumps(plan, indent=2))
            return 0
        if output_dir.exists():
            raise ValueError(f"Output directory already exists; choose a new one: {output_dir}")
        client = OllamaClient(timeout=args.timeout)
        health, model_metadata = installed_model(client, model)
        output_dir.mkdir(parents=True, exist_ok=False)
    except (OllamaError, OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Pilot setup failed: {exc}", file=sys.stderr)
        return 1
    generation = {**generation_metadata(), "cwd": str(Path.cwd()), "request_timeout": args.timeout}
    manifest = {**plan, "status": "running", "started_at": datetime.now(timezone.utc).isoformat(),
                "generation": generation, "model_metadata": model_metadata,
                "ollama_version": health["version"], "completed_jobs": []}
    manifest_path = output_dir / "run-manifest.json"
    write_json(manifest_path, manifest, exclusive=True)
    code = 0
    try:
        for job in plan["jobs"]:
            if source_hashes() != generation["source_sha256"]:
                raise ValueError("Generation source changed during the run")
            current_health, current_model = installed_model(client, model)
            if (current_model.get("digest") != model_metadata.get("digest")
                    or current_health["version"] != health["version"]):
                raise OllamaError("Model digest or Ollama version changed during this run")
            manifest["active_job"] = job["pilot"]
            write_json(manifest_path, manifest)
            print(f"Starting {job['pilot']}: {job['planned_calls']} planned calls", flush=True)
            if job["pilot"] == "full":
                status = experiment.main(["--model", model, "--questions", "4", "--agents", "3",
                                          "--seed", "42", "--temperature", "0.7", "--max-tokens", str(MAX_TOKENS),
                                          "--timeout", str(args.timeout), "--output", job["raw"]])
                if status == 130:
                    raise KeyboardInterrupt
                if status != 0:
                    raise OllamaError("Full pilot failed; keeping partial output and stopping")
                raw_metadata = json.loads(Path(job["raw"]).read_text().splitlines()[0])
                if (raw_metadata["model_metadata"].get("digest") != model_metadata.get("digest")
                        or raw_metadata["ollama_version"] != health["version"]):
                    raise OllamaError("Full pilot used a different model digest or runtime version")
                summary = analyze_results.analyze(Path(job["raw"]))
            else:
                summary = run_single(client, model, job, health, model_metadata, generation)
            after_health, after_model = installed_model(client, model)
            if (after_model.get("digest") != model_metadata.get("digest")
                    or after_health["version"] != health["version"]):
                raise OllamaError("Model digest or Ollama version changed during the pilot")
            write_json(job["summary"], summary, exclusive=True)
            manifest["completed_jobs"].append(job["pilot"])
            write_json(manifest_path, manifest)
        manifest["status"] = "complete"
        manifest.pop("active_job", None)
    except KeyboardInterrupt:
        manifest.update(status="interrupted", error="Interrupted by user")
        code = 130
    except (OllamaError, OSError, ValueError, KeyError, TypeError) as exc:
        manifest.update(status="failed", error=str(exc))
        print(f"Pilot run failed: {exc}", file=sys.stderr)
        code = 1
    finally:
        manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
        manifest["source_sha256_after"] = source_hashes()
        manifest["generation_sources_unchanged"] = manifest["source_sha256_after"] == generation["source_sha256"]
        if not manifest["generation_sources_unchanged"]:
            manifest.update(status="failed", error="Generation source changed during the run")
            code = 1
        write_json(manifest_path, manifest)
    print(f"{manifest['status']}: results saved under {output_dir}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
