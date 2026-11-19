"""Versioned continuation after a token-limited, invalid-JSON response.

V1 evidence and generation rules remain unchanged. The explicit amendment
records only proven output-cap invalid JSON as an ineligible answer, without
repairing or regenerating it. Other schema violations still stop the run.
"""

import argparse
import copy
import json
import math
import os
from pathlib import Path
import time
import sys

from experiment_runtime import FileLock, PauseController, hardware_identity
from local_llm import OllamaError
from multi_agent_protocol import evaluate_response
from run_format_followup import (atomic_json, append_record, canonical, digest,
                                 journal_records, snapshot_hash, strict_json, SchemaViolation)
from . import runner as v1
from .protocol import ARMS, STRICT_SCHEMA, build_call


ROOT = v1.ROOT
CONFIG_PATH = ROOT / "config/communication_recovery.json"
DEFAULT_SOURCE = ROOT / "results/communication-pilot/windows-v1"
EXPERIMENT_ID = "strict-schema-communication-self-revision-pilot-recovery-v2"
IMPORTED_GENERATIONS = 146
IMPORTED_ANSWERS = 145
TOTAL_REVISIONS = 480
NEW_CALLS = TOTAL_REVISIONS - IMPORTED_GENERATIONS
AMENDMENT = {
    "scope": "post_failure_exploratory_continuation_not_an_unchanged_completed_v1",
    "only_change": "output_cap_invalid_json_is_one_ineligible_answer_instead_of_aborting",
    "admission": "done_reason_length_eval_count_exactly_1024_valid_wrapper_unsaturated_context_invalid_JSON_syntax",
    "other_schema_violations": "fatal_including_valid_JSON_that_violates_schema",
    "repair": False, "retry": False, "cap_change": False, "prompt_change": False,
    "source_prefix": {"generations": IMPORTED_GENERATIONS, "answers": IMPORTED_ANSWERS},
}
PROTOCOL = {"generation_protocol": copy.deepcopy(v1.PROTOCOL),
            "generation_protocol_sha256": snapshot_hash(v1.PROTOCOL),
            "failure_policy_amendment": AMENDMENT}
EXPECTED_CONFIG = {
    "schema_version": 1, "experiment_id": EXPERIMENT_ID,
    "source_run": "results/communication-pilot/windows-v1",
    "selected_profile": "strict_schema", "protocol": PROTOCOL,
}
SOURCE_FILES = ("run_communication_recovery.py", "run_communication_recovery.ps1",
                "experiments/communication_pilot/recovery.py",
                "experiments/communication_pilot/recovery_analysis.py")
SOURCE_EVIDENCE = ("run-manifest.json", "initial_panel.jsonl", "generations.jsonl", "answers.jsonl")
JOURNALS = v1.JOURNALS
PLAN_FIELDS = ("experiment_id", "configuration_path", "configuration_sha256", "configuration_snapshot",
               "protocol_snapshot", "protocol_sha256", "generation_protocol_snapshot",
               "generation_protocol_sha256", "schema_sha256", "tasks_snapshot", "initial_panel",
               "parent_snapshot", "source_run_snapshot", "source_sha256", "call_positions",
               "imported_revision_calls", "imported_answer_calls", "planned_new_calls",
               "planned_revision_calls", "reused_round_zero_calls", "planned_unique_calls")
SNAPSHOT_FIELDS = (*PLAN_FIELDS, "hardware_snapshot", "model_digest", "ollama_version")
ERRORS = v1.ERRORS
PilotClient = v1.PilotClient
now = v1.now


def source_run_hashes(directory):
    return {name: digest((Path(directory) / name).read_bytes()) for name in SOURCE_EVIDENCE}


def _output_cap_invalid_json(generation):
    raw = generation["raw"]
    if (raw.get("done_reason") != "length" or raw.get("model") != "llama3.2:3b"
            or type(raw.get("eval_count")) is not int or raw["eval_count"] != 1024
            or type(raw.get("prompt_eval_count")) is not int or raw["prompt_eval_count"] < 0
            or raw["prompt_eval_count"] + raw["eval_count"] >= 16384):
        return False
    try:
        # Structurally valid JSON with wrong fields/pattern is not excused.
        json.loads(raw["message"]["content"])
    except json.JSONDecodeError:
        return True
    return False


def evaluate_generation(generation, task):
    try:
        # Performs all existing wrapper/model/context/profile/schema checks.
        return v1.evaluate_generation(generation, task)
    except SchemaViolation:
        if not _output_cap_invalid_json(generation):
            raise
        response = evaluate_response(generation["raw"], task["probability"])
        if (response["json_valid"] or response["eligible"] or response["calculator_attempted"]
                or response["status"] != "invalid_json"):
            raise ValueError("Output-cap admission must yield an unrepaired invalid-JSON answer")
        return {**generation, "type": "answer", "schema_conforms": False,
                "output_truncation_failure": True, "response": response}


def _check_elapsed(generation):
    elapsed = generation.get("elapsed_seconds")
    if type(elapsed) not in (int, float) or not math.isfinite(elapsed) or elapsed < 0:
        raise ValueError("Invalid recorded call duration")


def load_source(directory):
    """Audit the stopped original run, including its one expected invalid orphan."""
    directory = Path(directory).resolve()
    before = source_run_hashes(directory)
    manifest = strict_json((directory / "run-manifest.json").read_text(encoding="utf-8"))
    if (manifest.get("experiment_id") != v1.EXPERIMENT_ID or manifest.get("status") != "failed"
            or manifest.get("schema_support_check") != "failed_or_truncated"
            or "schema violation" not in str(manifest.get("error", "")).lower()):
        raise ValueError("Recovery source must be the preserved failed v1 schema-stop run")
    plan = v1.load_plan(Path(manifest["configuration_path"]), Path(manifest["parent_snapshot"]["directory"]))
    for field in v1.PLAN_FIELDS:
        if canonical(manifest.get(field)) != canonical(plan.get(field)):
            raise ValueError(f"Original source snapshot/protocol differs: {field}")
    if manifest.get("snapshot_sha256") != snapshot_hash({name: manifest[name] for name in v1.SNAPSHOT_FIELDS}):
        raise ValueError("Original source snapshot hash mismatch")
    parent = plan["parent_snapshot"]
    for name in ("model_digest", "ollama_version", "hardware_snapshot"):
        if manifest.get(name) != parent[name]:
            raise ValueError(f"Original source identity differs: {name}")
    v1.verify_sources(manifest)
    expected_counts = {"initial_panel.jsonl": 80, "generations.jsonl": IMPORTED_GENERATIONS,
                       "answers.jsonl": IMPORTED_ANSWERS}
    parsed = {}
    for name, count in expected_counts.items():
        records, lines = journal_records(directory / name)
        checkpoint = manifest["evidence_checkpoint"][name]
        if (len(records) != count or checkpoint["records"] != count
                or digest(b"".join(lines)) != checkpoint["sha256"]):
            raise ValueError(f"Original source evidence count/hash differs: {name}")
        parsed[name] = records
    if (manifest.get("calls_completed") != IMPORTED_ANSWERS
            or manifest.get("generations_saved") != IMPORTED_GENERATIONS
            or parsed["initial_panel.jsonl"] != plan["initial_panel"]):
        raise ValueError("Original source counters or imported initial panel differ")
    tasks = {task["id"]: task for task in plan["tasks_snapshot"]}
    checked = []
    for index, generation in enumerate(parsed["generations.jsonl"]):
        if generation.get("type") != "generation":
            raise ValueError("Unexpected original raw record type")
        expected = build_call(plan, index, checked)
        for name, value in expected.items():
            if canonical(generation.get(name)) != canonical(value):
                raise ValueError(f"Original source violates canonical preceding-round request: {name}")
        _check_elapsed(generation)
        answer = evaluate_generation(generation, tasks[generation["question_id"]])
        if index < IMPORTED_ANSWERS and answer != parsed["answers.jsonl"][index]:
            raise ValueError("Original answer disagrees with unchanged raw evaluation")
        checked.append(answer)
    if not checked[-1].get("output_truncation_failure"):
        raise ValueError("Original orphan must be the diagnosed output-cap invalid-JSON response")
    active = {name: parsed["generations.jsonl"][-1][name]
              for name in ("call_index", "question_id", "round", "agent_id", "arm")}
    if manifest.get("active_call") != active:
        raise ValueError("Original source failed-call position differs from its saved orphan")
    if source_run_hashes(directory) != before:
        raise ValueError("Original source evidence changed during audit")
    snapshot = {"directory": str(directory), "experiment_id": manifest["experiment_id"],
                "status": "failed", "evidence_sha256": before,
                "generations": IMPORTED_GENERATIONS, "answers": IMPORTED_ANSWERS,
                "model_digest": manifest["model_digest"], "ollama_version": manifest["ollama_version"],
                "hardware_snapshot": copy.deepcopy(manifest["hardware_snapshot"]),
                "generation_protocol_sha256": manifest["protocol_sha256"],
                "failed_call": active, "diagnosis": "output_cap_invalid_json_no_expression",
                "continuation_amendment_declared_after_failure": True}
    return manifest, parsed["generations.jsonl"], parsed["answers.jsonl"], snapshot


def source_hashes(config_path, source_manifest):
    paths = {str(ROOT / name) for name in SOURCE_FILES}
    paths.add(str(Path(config_path).resolve()))
    paths.update(source_manifest["source_sha256"])
    return {name: digest(Path(name).read_bytes()) for name in sorted(paths)}


def load_plan(config_path=CONFIG_PATH, source_directory=DEFAULT_SOURCE):
    config_path = Path(config_path).resolve()
    config_bytes = config_path.read_bytes()
    config = strict_json(config_bytes.decode("utf-8"))
    if canonical(config) != canonical(EXPECTED_CONFIG):
        raise ValueError("Configuration differs from the explicit frozen recovery amendment")
    source, generations, answers, snapshot = load_source(source_directory)
    plan = {"experiment_id": EXPERIMENT_ID, "configuration_path": str(config_path),
            "configuration_sha256": digest(config_bytes), "configuration_snapshot": config,
            "protocol_snapshot": copy.deepcopy(PROTOCOL), "protocol_sha256": snapshot_hash(PROTOCOL),
            "generation_protocol_snapshot": copy.deepcopy(v1.PROTOCOL),
            "generation_protocol_sha256": snapshot_hash(v1.PROTOCOL),
            "schema_sha256": source["schema_sha256"], "tasks_snapshot": copy.deepcopy(source["tasks_snapshot"]),
            "initial_panel": copy.deepcopy(source["initial_panel"]),
            "parent_snapshot": copy.deepcopy(source["parent_snapshot"]), "source_run_snapshot": snapshot,
            "source_sha256": source_hashes(config_path, source),
            "call_positions": copy.deepcopy(source["call_positions"]),
            "imported_revision_calls": IMPORTED_GENERATIONS, "imported_answer_calls": IMPORTED_ANSWERS,
            "planned_new_calls": NEW_CALLS, "planned_revision_calls": TOTAL_REVISIONS,
            "reused_round_zero_calls": 80, "planned_unique_calls": 560,
            "imported_generations": generations, "imported_answers": answers,
            "notes": ["Post-failure protocol amendment; original v1 remains failed and unchanged.",
                      "Reuse all 146 raw calls, including the truncated response; no repair or retry.",
                      "145 saved evaluated answers remain byte-identical; the orphan is evaluated locally as invalid JSON.",
                      "Only known output-cap invalid JSON becomes ineligible instead of aborting; other schema violations remain fatal.",
                      "Original generation prompts, schema, seeds, cap, sampling, scoring, and peer order are unchanged.",
                      "334 additional model calls remain; full trajectories contain 480 revision calls plus 80 initial calls."]}
    evaluated = [*answers, evaluate_generation(generations[-1],
                  next(task for task in plan["tasks_snapshot"] if task["id"] == generations[-1]["question_id"]))]
    plan["next_call"] = build_call(plan, IMPORTED_GENERATIONS, evaluated)
    return plan


def verify_sources(manifest):
    v1.verify_sources(manifest)
    snapshot = manifest["source_run_snapshot"]
    if source_run_hashes(snapshot["directory"]) != snapshot["evidence_sha256"]:
        raise ValueError("Preserved failed v1 evidence changed")


def verify_runtime(client, manifest, check_hardware=False):
    verify_sources(manifest)
    health, model = v1.parent_pilot.installed_model(client)
    if health["version"] != manifest["ollama_version"] or model["digest"] != manifest["model_digest"]:
        raise ValueError("Model digest or Ollama runtime differs from the preserved prefix")
    if check_hardware and hardware_identity() != manifest["hardware_snapshot"]:
        raise ValueError("Hardware identity differs from the preserved prefix")


def checkpoint(directory, manifest):
    v1.checkpoint(directory, manifest)


def audit_resume(directory, manifest, plan):
    for name in PLAN_FIELDS:
        if canonical(manifest.get(name)) != canonical(plan.get(name)):
            raise ValueError(f"Recovery snapshot/protocol differs: {name}")
    if manifest.get("snapshot_sha256") != snapshot_hash({name: manifest[name] for name in SNAPSHOT_FIELDS}):
        raise ValueError("Recovery snapshot hash mismatch")
    for name in ("model_digest", "ollama_version", "hardware_snapshot"):
        if manifest.get(name) != plan["source_run_snapshot"][name]:
            raise ValueError(f"Recovery imported identity differs: {name}")
    verify_sources(manifest)
    for name, counter in (("answers.jsonl", "calls_completed"), ("generations.jsonl", "generations_saved")):
        if manifest.get(counter) != manifest["evidence_checkpoint"][name]["records"]:
            raise ValueError("Recovery counters disagree with durable evidence checkpoint")
    initial, lines = journal_records(directory / "initial_panel.jsonl")
    saved = manifest["evidence_checkpoint"]["initial_panel.jsonl"]
    if initial != plan["initial_panel"] or saved["records"] != 80 or digest(b"".join(lines)) != saved["sha256"]:
        raise ValueError("Recovery initial panel differs from the unchanged import")
    source = Path(plan["source_run_snapshot"]["directory"])
    if (directory / "initial_panel.jsonl").read_bytes() != (source / "initial_panel.jsonl").read_bytes():
        raise ValueError("Recovery initial panel bytes changed")
    parsed = []
    for name in JOURNALS:
        records, lines = journal_records(directory / name)
        saved = manifest["evidence_checkpoint"][name]
        count = saved["records"]
        if (type(count) is not int or count < 0 or len(records) < count or len(records) > count + 1
                or digest(b"".join(lines[:count])) != saved["sha256"]):
            raise ValueError(f"Recovery evidence prefix hash/count differs: {name}")
        if not (directory / name).read_bytes().startswith((source / name).read_bytes()):
            raise ValueError(f"Recovery no longer preserves the original byte prefix: {name}")
        parsed.append(records)
    generations, answers = parsed
    if (len(generations) < IMPORTED_GENERATIONS or len(answers) < IMPORTED_ANSWERS
            or len(generations) > TOTAL_REVISIONS or len(answers) > len(generations)
            or len(generations) - len(answers) > 1):
        raise ValueError("Recovery journals do not form the canonical imported call prefix")
    checked = []
    tasks = {task["id"]: task for task in plan["tasks_snapshot"]}
    for index, generation in enumerate(generations):
        if generation.get("type") != "generation":
            raise ValueError("Unexpected recovery raw record type")
        for name, value in build_call(plan, index, checked).items():
            if canonical(generation.get(name)) != canonical(value):
                raise ValueError(f"Recovery generation violates canonical preceding-round request: {name}")
        _check_elapsed(generation)
        evaluated = evaluate_generation(generation, tasks[generation["question_id"]])
        if index < len(answers) and evaluated != answers[index]:
            raise ValueError("Recovery answer disagrees with unchanged raw evaluation")
        checked.append(evaluated)
    return generations, answers


def summarize(manifest, initial_panel, answers):
    from .recovery_analysis import summarize as summarize_analysis
    return summarize_analysis(manifest, initial_panel, answers)


def execute(directory, plan, client, manifest, generations, answers, pause):
    tasks = {task["id"]: task for task in plan["tasks_snapshot"]}
    manifest.update(status="running", last_started_at=now())
    manifest.pop("error", None)
    manifest.setdefault("segments", []).append({"started_at": now(), "calls_before": len(answers),
                                              "new_calls_before": len(generations) - IMPORTED_GENERATIONS})
    code = 0
    try:
        with (directory / "generations.jsonl").open("ab") as raw_output, (directory / "answers.jsonl").open("ab") as answer_output:
            if len(generations) > len(answers):
                generation = generations[-1]
                answer = evaluate_generation(generation, tasks[generation["question_id"]])
                append_record(answer_output, answer)
                answers.append(answer)
                checkpoint(directory, manifest)
            for index in range(len(generations), TOTAL_REVISIONS):
                if pause.requested():
                    manifest["status"], code = "paused", 2
                    break
                verify_runtime(client, manifest)
                call = build_call(plan, index, answers)
                manifest["active_call"] = {name: call[name] for name in ("call_index", "question_id", "round", "agent_id", "arm")}
                checkpoint(directory, manifest)
                started = time.perf_counter()
                raw = client.chat("llama3.2:3b", call["messages"], seed=call["seed"], temperature=0.7,
                                  max_tokens=1024, format_value=call["format"])
                generation = {**copy.deepcopy(call), "type": "generation", "raw": raw,
                              "elapsed_seconds": time.perf_counter() - started}
                append_record(raw_output, generation)
                generations.append(generation)
                checkpoint(directory, manifest)
                answer = evaluate_generation(generation, tasks[call["question_id"]])
                append_record(answer_output, answer)
                answers.append(answer)
                manifest.pop("active_call", None)
                checkpoint(directory, manifest)
                print(f"Saved {len(answers)}/{TOTAL_REVISIONS}: {call['question_id']} round {call['round']} "
                      f"agent {call['agent_id']} {call['arm']} ({len(generations)-IMPORTED_GENERATIONS}/{NEW_CALLS} new calls)", flush=True)
                if pause.requested():
                    manifest["status"], code = "paused", 2
                    break
        if len(answers) == TOTAL_REVISIONS:
            verify_runtime(client, manifest, check_hardware=True)
            summary = summarize(manifest, plan["initial_panel"], answers)
            summary_path = directory / "summary.json"
            if summary_path.exists():
                if strict_json(summary_path.read_text(encoding="utf-8")) != summary:
                    raise ValueError("Existing recovery summary differs; refusing overwrite")
            else:
                atomic_json(summary_path, summary)
            manifest.update(status="complete", summary_sha256=digest(summary_path.read_bytes()))
    except KeyboardInterrupt:
        manifest.update(status="interrupted", error="Forced interruption; durable raw responses recover without replay")
        code = 130
    except SchemaViolation as exc:
        manifest.update(status="failed", error=str(exc), schema_support_check="non_admitted_schema_violation")
        print(f"Recovery stopped: {exc}", file=sys.stderr)
        code = 1
    except ERRORS as exc:
        manifest.update(status="failed", error=str(exc))
        print(f"Recovery stopped: {exc}", file=sys.stderr)
        code = 1
    finally:
        manifest["segments"][-1].update(finished_at=now(), calls_after=len(answers), status=manifest["status"],
                                      new_calls_after=len(generations)-IMPORTED_GENERATIONS,
                                      error=manifest.get("error"), active_call=copy.deepcopy(manifest.get("active_call")))
        manifest["updated_at"] = now()
        checkpoint(directory, manifest)
    print(f"{manifest['status']}: {len(answers)}/{TOTAL_REVISIONS} revision answers; "
          f"{len(generations)-IMPORTED_GENERATIONS}/{NEW_CALLS} generated here in {directory}")
    return code


def analyze_run(directory):
    directory = Path(directory).resolve()
    manifest = strict_json((directory / "run-manifest.json").read_text(encoding="utf-8"))
    if manifest.get("experiment_id") != EXPERIMENT_ID:
        raise ValueError("Analysis requires the explicitly versioned recovery experiment")
    if manifest.get("status") in {"initializing", "running"}:
        raise ValueError("Pause the active writer before recovery analysis")
    plan = load_plan(Path(manifest["configuration_path"]), Path(manifest["source_run_snapshot"]["directory"]))
    generations, answers = audit_resume(directory, manifest, plan)
    result = {"offline_audit": "passed", "status": manifest["status"], "calls_completed": len(answers),
              "generations_saved": len(generations), "imported_revision_calls": IMPORTED_GENERATIONS,
              "new_calls_completed": len(generations)-IMPORTED_GENERATIONS, "summary_reproduced": None}
    if manifest.get("status") == "complete":
        if len(generations) != TOTAL_REVISIONS or len(answers) != TOTAL_REVISIONS:
            raise ValueError("Completed recovery has incomplete evidence")
        summary_path = directory / "summary.json"
        if digest(summary_path.read_bytes()) != manifest.get("summary_sha256"):
            raise ValueError("Recovery summary evidence hash mismatch")
        summary = summarize(manifest, plan["initial_panel"], answers)
        if strict_json(summary_path.read_text(encoding="utf-8")) != summary:
            raise ValueError("Recovery summary disagrees with recomputed evidence")
        result.update(summary_reproduced=True, summary=summary)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--source-run", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--timeout", type=float, default=600)
    parser.add_argument("--dry-run", action="store_true")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--resume", action="store_true")
    mode.add_argument("--pause", action="store_true")
    mode.add_argument("--analyze-run", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.analyze_run is not None:
            if args.config or args.source_run or args.output_dir or args.dry_run:
                raise ValueError("--analyze-run accepts only a saved recovery directory")
            print(json.dumps(analyze_run(args.analyze_run), indent=2, allow_nan=False))
            return 0
        if args.pause:
            if args.output_dir is None or args.config or args.source_run or args.dry_run:
                raise ValueError("--pause requires only an existing --output-dir")
            directory = args.output_dir.resolve()
            manifest = strict_json((directory / "run-manifest.json").read_text(encoding="utf-8"))
            if manifest.get("experiment_id") != EXPERIMENT_ID or manifest.get("status") == "complete":
                raise ValueError("No incomplete recovery experiment exists at this destination")
            (directory / ".pause-request").touch(exist_ok=True)
            print("Pause requested; the returned response will be saved before stopping.")
            return 0
        if not math.isfinite(args.timeout) or args.timeout <= 0:
            raise ValueError("timeout must be positive and finite")
        if args.resume and (args.output_dir is None or args.dry_run):
            raise ValueError("--resume requires an existing --output-dir and cannot be a dry run")
        directory = (args.output_dir or ROOT / "results/communication-pilot/windows-v2").resolve()
        old = strict_json((directory / "run-manifest.json").read_text(encoding="utf-8")) if args.resume else None
        config_path = args.config or (Path(old["configuration_path"]) if old else CONFIG_PATH)
        source_directory = args.source_run or (Path(old["source_run_snapshot"]["directory"]) if old else DEFAULT_SOURCE)
        plan = load_plan(config_path, source_directory)
        if args.dry_run:
            preview = {key: value for key, value in plan.items() if key not in ("imported_generations", "imported_answers")}
            print(json.dumps({**preview, "output_dir": str(directory)}, indent=2, allow_nan=False))
            return 0
        if not args.resume:
            if directory.exists():
                raise ValueError("Output directory already exists; use --resume for this recovery")
            if (directory.is_relative_to(ROOT / "archive") or directory.is_relative_to(ROOT / "results/baseline")
                    or directory.is_relative_to(Path(plan["source_run_snapshot"]["directory"]))
                    or directory.is_relative_to(Path(plan["parent_snapshot"]["directory"]))):
                raise ValueError("Recovery output must stay outside all historical/parent evidence namespaces")
            client = PilotClient(timeout=args.timeout)
            identity = plan["source_run_snapshot"]
            health, model = v1.parent_pilot.installed_model(client)
            if health["version"] != identity["ollama_version"] or model["digest"] != identity["model_digest"]:
                raise ValueError("Model/runtime changed since the preserved prefix")
            if hardware_identity() != identity["hardware_snapshot"]:
                raise ValueError("Hardware changed since the preserved prefix")
            verify_sources(plan)
            directory.mkdir(parents=True, exist_ok=False)
        with FileLock(directory / ".pilot.lock"), PauseController(directory / ".pause-request") as pause:
            if args.resume:
                old = strict_json((directory / "run-manifest.json").read_text(encoding="utf-8"))
                if old.get("status") == "complete":
                    raise ValueError("Recovery already complete; no inference will be replayed")
                generations, answers = audit_resume(directory, old, plan)
                manifest = old
                client = PilotClient(timeout=args.timeout)
                verify_runtime(client, manifest, check_hardware=True)
            else:
                source = Path(plan["source_run_snapshot"]["directory"])
                for name in ("initial_panel.jsonl", *JOURNALS):
                    with (directory / name).open("xb") as output:
                        output.write((source / name).read_bytes())
                        output.flush()
                        os.fsync(output.fileno())
                identity = plan["source_run_snapshot"]
                persisted = {key: value for key, value in plan.items()
                             if key not in ("imported_generations", "imported_answers", "next_call")}
                manifest = {**persisted, "status": "initializing", "started_at": now(),
                            "hardware_snapshot": copy.deepcopy(identity["hardware_snapshot"]),
                            "model_digest": identity["model_digest"], "ollama_version": identity["ollama_version"],
                            "calls_completed": IMPORTED_ANSWERS, "generations_saved": IMPORTED_GENERATIONS,
                            "request_timeout": args.timeout}
                manifest["snapshot_sha256"] = snapshot_hash({name: manifest[name] for name in SNAPSHOT_FIELDS})
                generations, answers = copy.deepcopy(plan["imported_generations"]), copy.deepcopy(plan["imported_answers"])
                checkpoint(directory, manifest)
            pause.clear_request()
            return execute(directory, plan, client, manifest, generations, answers, pause)
    except KeyboardInterrupt:
        print("Recovery setup interrupted; preserved source evidence is unchanged.", file=sys.stderr)
        return 130
    except ERRORS as exc:
        print(f"Recovery setup/resume failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
