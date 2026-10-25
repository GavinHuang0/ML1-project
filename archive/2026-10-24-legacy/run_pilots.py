"""Repeat the reviewed pilots with another local model; no downloads are performed."""

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import time

import analyze_results
from benchmark import make_tasks
from local_llm import OllamaClient, OllamaError, validate_model_tag
from pilot_scoring import score_response
import run_experiment as experiment


ROOT = Path(__file__).resolve().parent
ARTIFACTS = ROOT / "results"
REFERENCES = {
    "256": "experiment1-qwen-seed42.jsonl",
    "512": "experiment1-qwen-seed42-max512.jsonl",
    "urn-check": "experiment1-qwen-seed42-max512-urn-check1024.jsonl",
    "diagnostic": "experiment1-qwen-seed42-max512-diagnostic1024.jsonl",
}
FILENAMES = {"256": "pilot256", "512": "pilot512",
             "urn-check": "urn-check1024", "diagnostic": "diagnostic1024"}
COUNTS = {"256": 60, "512": 60, "urn-check": 4, "diagnostic": 16}


def read_reference(pilot):
    path = ARTIFACTS / REFERENCES[pilot]
    data = path.read_bytes()
    rows = [json.loads(line) for line in data.decode("utf-8").splitlines()]
    summary = json.loads(path.with_suffix(".summary.json").read_text())
    expected_hash = summary.get("raw_sha256") or summary["source"]["sha256"]
    if hashlib.sha256(data).hexdigest() != expected_hash:
        raise ValueError(f"Reference hash mismatch: {path}")
    if rows[0].get("type") != "metadata" or rows[-1].get("type") != "complete":
        raise ValueError(f"Incomplete reference: {path}")
    if pilot in ("256", "512"):
        if rows[-1].get("questions_completed") != 4 or [r["task"] for r in rows[1:-1]] != make_tasks(4, 42):
            raise ValueError(f"Historical tasks differ from the current generator: {path}")
        manifest = json.loads((ARTIFACTS / "experiment1-qwen-seed42-max512.run.json").read_text())
        for name, digest in manifest["source_sha256"].items():
            if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest:
                raise ValueError(f"Historical inference source changed: {name}")
    else:
        answers = rows[1:-1]
        if (len(answers) != COUNTS[pilot] or rows[-1].get("calls_completed") != COUNTS[pilot]
                or any(r.get("type") != "answer" for r in answers)):
            raise ValueError(f"Unexpected reference call count: {path}")
        settings = rows[0]["settings"]
        if settings.get("max_tokens") != 1024 or settings.get("temperature") != 0.7:
            raise ValueError(f"Unexpected reference sampling settings: {path}")
        cells = set()
        for row in answers:
            task = row["task"]
            seed = row.get("seed", task.get("seed"))
            expected = [{"role": "system", "content": rows[0]["prompts"][row["condition"]]},
                        {"role": "user", "content": task["prompt"]}]
            cell = (row["condition"], task["id"])
            if row["messages"] != expected or not isinstance(seed, int) or cell in cells:
                raise ValueError(f"Inconsistent reference prompt/seed/cell: {path}")
            expected_seed = (settings["sampling_seeds"][task["id"]] if pilot == "urn-check" else task["seed"])
            if seed != expected_seed:
                raise ValueError(f"Reference sampling seed differs from its manifest: {path}")
            cells.add(cell)
        for name, digest in rows[0]["source_sha256"].items():
            if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest:
                raise ValueError(f"Historical inference source changed: {name}")
    return path, rows, expected_hash


def build_plan(model, pilot, output_dir, timeout=300):
    jobs = []
    selected = list(REFERENCES) if pilot == "all" else [pilot]
    for name in selected:
        reference, _, digest = read_reference(name)
        jobs.append({"pilot": name, "planned_calls": COUNTS[name],
                     "max_tokens": int(name) if name in ("256", "512") else 1024,
                     "raw": str(output_dir / (FILENAMES[name] + ".jsonl")),
                     "summary": str(output_dir / (FILENAMES[name] + ".summary.json")),
                     "reference": str(reference), "reference_sha256": digest})
    return {"model": model, "output_dir": str(output_dir), "timeout": timeout,
            "planned_calls": sum(job["planned_calls"] for job in jobs), "jobs": jobs}


def installed_model(client, model):
    health = client.health()
    name = model if ":" in model.rsplit("/", 1)[-1] else model + ":latest"
    metadata = next((item for item in health["models"]
                     if item.get("name") == name or item.get("model") == name), None)
    if metadata is None:
        raise OllamaError(f"Model {model} is missing. Run: python3 setup_models.py --models {model}")
    return health, metadata


def write_json(path, value, exclusive=False):
    with Path(path).open("x" if exclusive else "w", encoding="utf-8") as output:
        json.dump(value, output, indent=2, allow_nan=False)
        output.write("\n")


def source_hashes():
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in ("run_pilots.py", "pilot_scoring.py", "run_experiment.py",
                         "benchmark.py", "local_llm.py", "analyze_results.py")}


def run_single(client, model, job, health, model_metadata, generation):
    _, source_rows, _ = read_reference(job["pilot"])
    source_settings = dict(source_rows[0]["settings"])
    source_settings["timeout"] = generation["request_timeout"]
    records = []
    metadata = {"type": "metadata", "pilot": job["pilot"], "model": model,
                "model_metadata": model_metadata, "ollama_version": health["version"],
                "created_at": datetime.now(timezone.utc).isoformat(),
                "settings": source_settings, "reference": job["reference"],
                "reference_sha256": job["reference_sha256"],
                "generation": generation,
                "prompts": source_rows[0]["prompts"],
                "scope": "Exact replay of archived single-agent messages and seeds with a new model"}
    with Path(job["raw"]).open("x", encoding="utf-8") as output:
        output.write(json.dumps(metadata) + "\n")
        output.flush()
        for source in source_rows[1:-1]:
            task = source["task"]
            seed = source.get("seed", task.get("seed"))
            started = time.perf_counter()
            raw = client.chat(model, source["messages"], seed=seed, temperature=0.7, max_tokens=1024)
            record = {"type": "answer", "condition": source["condition"], "task": task,
                      "seed": seed, "messages": source["messages"], "raw": raw,
                      "elapsed_seconds": time.perf_counter() - started,
                      "score": score_response(raw, task, job["pilot"])}
            records.append(record)
            output.write(json.dumps(record, allow_nan=False) + "\n")
            output.flush()
            print(f"{job['pilot']}: {len(records)}/{job['planned_calls']} "
                  f"{source['condition']} {task['id']}", flush=True)
        output.write(json.dumps({"type": "complete", "calls_completed": len(records)}) + "\n")
    groups = defaultdict(lambda: defaultdict(lambda: {"items": 0, "correct": 0, "invalid": 0}))
    for record in records:
        group = groups[record["condition"]][record["task"].get("stage", "full_solution")]
        group["items"] += 1
        group["correct"] += record["score"]["correct"]
        group["invalid"] += not record["score"]["format_valid"]
    return {"raw": job["raw"], "raw_sha256": hashlib.sha256(Path(job["raw"]).read_bytes()).hexdigest(),
            "groups": groups, "budget": experiment.budget(records),
            "length_stops": sum(r["raw"].get("done_reason") == "length" for r in records),
            "answers": [{"condition": r["condition"], "task_id": r["task"]["id"],
                         "score": r["score"], "output_tokens": r["raw"].get("eval_count")}
                        for r in records]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="llama3.2:3b")
    parser.add_argument("--pilot", choices=(*REFERENCES, "all"), default="all")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--dry-run", action="store_true", help="Print the plan without Ollama calls or file writes")
    args = parser.parse_args(argv)
    try:
        model = validate_model_tag(args.model)
        if not math.isfinite(args.timeout) or args.timeout <= 0:
            raise ValueError("timeout must be positive and finite")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        output_dir = args.output_dir or ARTIFACTS / (re.sub(r"[^a-zA-Z0-9._-]", "-", model) + "-pilots-" + stamp)
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
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                              capture_output=True, text=True, check=False)
    generation = {"git_revision": revision.stdout.strip() if revision.returncode == 0 else None,
                  "source_sha256": source_hashes(), "python_version": sys.version,
                  "cwd": str(Path.cwd()), "request_timeout": args.timeout}
    manifest = {**plan, "status": "running", "started_at": datetime.now(timezone.utc).isoformat(),
                "generation": generation, "model_metadata": model_metadata,
                "ollama_version": health["version"], "completed_jobs": []}
    manifest_path = output_dir / "run-manifest.json"
    write_json(manifest_path, manifest, exclusive=True)
    code = 0
    try:
        for job in plan["jobs"]:
            current_health, current_model = installed_model(client, model)
            if (current_model.get("digest") != model_metadata.get("digest")
                    or current_health["version"] != health["version"]):
                raise OllamaError("Model digest or Ollama version changed during this run")
            manifest["active_job"] = job["pilot"]
            write_json(manifest_path, manifest)
            print(f"Starting {job['pilot']}: {job['planned_calls']} planned calls", flush=True)
            if job["pilot"] in ("256", "512"):
                status = experiment.main(["--model", model, "--questions", "4", "--agents", "3",
                                          "--seed", "42", "--temperature", "0.7", "--max-tokens", str(job["max_tokens"]),
                                          "--timeout", str(args.timeout), "--output", job["raw"]])
                if status == 130:
                    raise KeyboardInterrupt
                if status != 0:
                    raise OllamaError(f"Pilot {job['pilot']} failed; keeping partial output and stopping")
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
