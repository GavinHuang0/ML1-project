"""Durable per-call study execution, with cooperative pause and in-place resume.

Completed outputs retain the original primary/control schemas. This scheduler
adds checkpoints and operational attempt diagnostics without changing prompts,
sampling, voting, or the experiment's model settings.
"""

from collections import defaultdict
import copy
import json
import math
from pathlib import Path
import sys
import time

from local_llm import OllamaError
from multi_agent_protocol import FROZEN_PROTOCOL, agent_seed
import run_multi_agent as primary
from experiments.full_study_v1 import run_self_revision as control


SCHEDULER_PROFILE = "durable-call-checkpoint-v1"
OllamaClient = primary.OllamaClient
evaluate_response = primary.evaluate_response
JOURNALS = ("generations.jsonl", "answers.jsonl", "rounds.jsonl")
CHECKPOINT_FIELDS = ("round_timing", "attempts", "calls_completed", "new_calls_completed",
                     "rounds_completed", "journal_prefixes")
ERRORS = (OllamaError, OSError, ValueError, KeyError, TypeError, RuntimeError,
          ZeroDivisionError, OverflowError, RecursionError)


def analyze_run(path, condition="all_to_all"):
    if condition == "all_to_all":
        return primary.analyze_run(path)
    if condition == "self_revision":
        return control.analyze_run(path)
    raise ValueError("Unknown study condition")


def _sources(config_path, tasks_path, condition, parent_run, calibration, selection):
    if condition == "all_to_all":
        result = primary.source_hashes(config_path, tasks_path, calibration, selection)
    else:
        result = control.source_hashes(parent_run, calibration)
        for path in (config_path, tasks_path, selection):
            if path is not None:
                result[str(Path(path).resolve())] = primary.digest_bytes(Path(path).read_bytes())
    result[str(Path(__file__).resolve())] = primary.digest_bytes(Path(__file__).read_bytes())
    return result


def _prefixes(directory):
    result = {}
    for name in JOURNALS:
        path = directory / name
        data = path.read_bytes() if path.exists() else b""
        result[name] = {"bytes": len(data), "sha256": primary.digest_bytes(data)}
    return result


def _save(directory, manifest):
    manifest["journal_prefixes"] = _prefixes(directory)
    manifest["checkpoint_state_sha256"] = primary.snapshot_hash({key: manifest.get(key) for key in CHECKPOINT_FIELDS})
    primary.write_json(directory / "run-manifest.json", manifest)


def _check_state(manifest):
    if manifest.get("checkpoint_state_sha256") != primary.snapshot_hash({key: manifest.get(key) for key in CHECKPOINT_FIELDS}):
        raise ValueError("Checkpoint timing, attempt metadata, or journal prefixes changed")


def _read_journal(path):
    if not path.exists():
        return []
    data = path.read_bytes()
    if data and not data.endswith(b"\n"):
        raise ValueError(f"Truncated trailing JSON journal; preserve it for inspection: {path.name}")
    return [primary.strict_json(line) for line in data.decode("utf-8").splitlines() if line.strip()]


def _key(record):
    return record["question_id"], record["round"], record["agent_id"]


def _round_key(question_id, round_index):
    return json.dumps([question_id, round_index], separators=(",", ":"))


def _wrapper(raw):
    if (not isinstance(raw, dict) or not isinstance(raw.get("message"), dict)
            or not isinstance(raw["message"].get("content"), str)
            or raw.get("done") is not True
            or raw.get("model", FROZEN_PROTOCOL["model"]) != FROZEN_PROTOCOL["model"]):
        raise OllamaError("Returned Ollama wrapper is invalid/incomplete; raw evidence is preserved and cannot be re-queried")
    counts = raw.get("prompt_eval_count"), raw.get("eval_count")
    if all(type(value) is int for value in counts) and sum(counts) >= FROZEN_PROTOCOL["context_tokens"]:
        raise OllamaError("Observed context saturation; raw evidence preserved")


def _generation(record):
    return {**{key: value for key, value in record.items()
               if key not in {"response", "postprocessing_seconds"}}, "type": "generation"}


def _messages(task, round_index, agent, previous, condition):
    if condition == "all_to_all":
        return primary.build_messages(task, round_index, agent, previous if round_index else None)
    return control.build_messages(task, round_index, agent, previous[agent])


def _plan(config_path, tasks_path, output_dir, condition, parent_run, calibration, selection, timeout):
    config, config_hash = primary.read_config(config_path)
    tasks, tasks_hash = primary.read_tasks(tasks_path)
    if condition == "all_to_all":
        artifact, calibration_hash = primary.read_calibration(calibration) if calibration else (None, None)
        chosen, selection_hash = primary.read_selection(selection) if selection else (None, None)
        primary.validate_evaluation_inputs(tasks, artifact, chosen, calibration_hash)
        plan = primary.build_plan(config, config_hash, tasks, tasks_hash, config_path, tasks_path,
                                  output_dir, timeout, artifact, calibration, chosen, selection)
        if calibration:
            plan.update(calibration_sha256=calibration_hash, calibration_path=str(calibration))
        if selection:
            plan.update(selection_sha256=selection_hash, selection_path=str(selection))
        plan["snapshot_sha256"] = {key: primary.snapshot_hash(plan.get(key)) for key in (
            "configuration_snapshot", "tasks_snapshot", "calibration_snapshot", "selection_snapshot")}
        plan["planned_new_calls"] = plan["planned_calls"]
        parent_records, parent_rounds = [], []
    else:
        if parent_run is None:
            raise ValueError("Self revision requires its completed primary parent_run")
        parent_manifest, parent_records, parent_rounds, snapshot = control.read_parent(parent_run)
        if tasks != parent_manifest["tasks_snapshot"]:
            raise ValueError("Self-revision task input differs from the shared primary parent")
        plan = control.build_plan(parent_run, parent_manifest, parent_records, parent_rounds,
                                  snapshot, output_dir, timeout, calibration)
        plan.update(configuration=str(config_path), configuration_sha256=config_hash,
                    configuration_snapshot=config, task_manifest=str(tasks_path),
                    task_manifest_sha256=tasks_hash)
        plan["snapshot_sha256"]["configuration_snapshot"] = primary.snapshot_hash(config)
        if selection is not None:
            chosen, digest = primary.read_selection(selection)
            if chosen != parent_manifest.get("selection_snapshot") or digest != parent_manifest.get("selection_sha256"):
                raise ValueError("Control selection must match the parent primary selection")
    plan.update(scheduler_profile=SCHEDULER_PROFILE, condition=condition, engine_sha256=
                primary.digest_bytes(Path(__file__).read_bytes()))
    plan["source_sha256"] = _sources(config_path, tasks_path, condition, parent_run, calibration, selection)
    if primary.digest_bytes(config_path.read_bytes()) != config_hash or primary.digest_bytes(tasks_path.read_bytes()) != tasks_hash:
        raise ValueError("Configuration or task input changed after being read")
    return plan, parent_records, parent_rounds


def _validate_prefixes(directory, manifest):
    if set(manifest.get("journal_prefixes", {})) != set(JOURNALS):
        raise ValueError("Checkpoint is missing its durable journal prefixes")
    for name, prefix in manifest.get("journal_prefixes", {}).items():
        if name not in JOURNALS or type(prefix.get("bytes")) is not int or prefix["bytes"] < 0:
            raise ValueError("Invalid checkpoint journal prefix")
        data = (directory / name).read_bytes()
        if len(data) < prefix["bytes"] or primary.digest_bytes(data[:prefix["bytes"]]) != prefix["sha256"]:
            raise ValueError(f"Checkpoint evidence changed: {name}")


def _audit(directory, manifest, plan, condition, parent_records, parent_rounds):
    _check_state(manifest)
    if (manifest.get("scheduler_profile") != SCHEDULER_PROFILE or manifest.get("condition") != condition
            or manifest.get("source_sha256") != plan["source_sha256"]
            or manifest.get("engine_sha256") != plan["engine_sha256"]):
        raise ValueError("Resume sources, frozen inputs, or scheduler profile differ")
    if manifest.get("snapshot_sha256") != plan.get("snapshot_sha256"):
        raise ValueError("Resume frozen snapshot identities differ")
    for key, digest in manifest.get("snapshot_sha256", {}).items():
        if primary.snapshot_hash(manifest.get(key)) != digest or primary.snapshot_hash(plan.get(key)) != digest:
            raise ValueError(f"Resume frozen snapshot mismatch: {key}")
    for key in ("experiment_id", "protocol_sha256", "calibration_sha256", "selection_sha256",
                "configuration_sha256", "task_manifest_sha256"):
        if manifest.get(key) != plan.get(key):
            raise ValueError(f"Resume frozen identity mismatch: {key}")
    _validate_prefixes(directory, manifest)
    generations, answers, rounds = [_read_journal(directory / name) for name in JOURNALS]
    had_marker = bool(answers and answers[-1].get("type") == "complete")
    if had_marker:
        marker = {"type": "complete", "calls_completed": len(plan["tasks_snapshot"]) * 40,
                  "rounds_completed": len(plan["tasks_snapshot"]) * 4}
        if condition == "self_revision":
            marker["new_calls_completed"] = len(plan["tasks_snapshot"]) * 30
        if answers[-1] != marker or len(answers) != marker["calls_completed"] + 1:
            raise ValueError("Invalid completion marker in checkpoint")
        answers = answers[:-1]
    if any(record.get("type") != "answer" for record in answers):
        raise ValueError("Partial checkpoint contains an unexpected completion/event record")
    expected = [(task["id"], index, agent) for task in plan["tasks_snapshot"]
                for index in range(4) for agent in range(10)]
    if (len(generations) not in {len(answers), len(answers) + 1}
            or len(generations) > len(expected)
            or [_key(record) for record in generations] != expected[:len(generations)]
            or [_key(record) for record in answers] != expected[:len(answers)]):
        raise ValueError("Checkpoint journals contain duplicate, missing, or out-of-order calls")
    tasks = {task["id"]: task for task in plan["tasks_snapshot"]}
    parent_initial = {_key(r): r for r in parent_records if r["round"] == 0}
    snapshots = defaultdict(list)
    for index, generation in enumerate(generations):
        key = _key(generation)
        task = tasks[key[0]]
        if generation.get("type") != "generation":
            raise ValueError("Invalid raw checkpoint event")
        if condition == "self_revision" and key[1] == 0:
            expected_answer = control._reuse(parent_initial[key], plan["parent_snapshot"])
            if generation != _generation(expected_answer):
                raise ValueError("Checkpoint common initial panel differs from the primary")
        else:
            previous = snapshots[(key[0], key[1] - 1)] if key[1] else None
            messages = _messages(task, key[1], key[2], previous, condition)
            if (generation.get("messages") != messages
                    or generation.get("seed") != agent_seed(*key)
                    or generation.get("context_budget") != primary.context_budget(messages)):
                raise ValueError("Checkpoint prompt, seed, or context differs from the frozen protocol")
            _wrapper(generation["raw"])
            response = primary.evaluate_response(generation["raw"], task["probability"])
            if index < len(answers):
                expected_answer = {**generation, "type": "answer", "response": response,
                                   "postprocessing_seconds": answers[index]["postprocessing_seconds"]}
            else:
                expected_answer = None
        if index < len(answers):
            if answers[index] != expected_answer:
                raise ValueError("Checkpoint answer does not match independently audited raw evidence")
            snapshots[(key[0], key[1])].append(answers[index])
    expected_rounds = []
    histories = defaultdict(list)
    parent_first = {r["question_id"]: r for r in parent_rounds if r["round"] == 0}
    for task in plan["tasks_snapshot"]:
        for index in range(4):
            if len(snapshots[(task["id"], index)]) != 10:
                break
            if len(expected_rounds) >= len(rounds):
                break
            saved = rounds[len(expected_rounds)]
            recomputed = primary.summarize_round(task, snapshots[(task["id"], index)],
                                                 saved["round_wall_seconds"], histories[task["id"]])
            if any(saved.get(name) != value for name, value in recomputed.items()):
                raise ValueError("Checkpoint round summary disagrees with the agent records")
            if condition == "self_revision" and index == 0 and saved != parent_first[task["id"]]:
                raise ValueError("Shared initial timing differs from its parent")
            histories[task["id"]].append(saved)
            expected_rounds.append(saved)
    if len(expected_rounds) != len(rounds):
        raise ValueError("Checkpoint contains unexpected round summaries")
    return generations, answers, rounds, had_marker


def _identity(client, manifest, current_sources):
    if current_sources() != manifest["source_sha256"]:
        raise ValueError("Frozen sources or inputs changed during the trajectory")
    health, model = primary.installed_model(client)
    if (model["digest"] != manifest["model_metadata"]["digest"]
            or health["version"] != manifest["ollama_version"]):
        raise OllamaError("Model digest/runtime differs from this trajectory checkpoint")


def _finish_artifacts(directory, manifest, records, rounds, condition):
    summary = (primary.make_summary(manifest, records, rounds, directory) if condition == "all_to_all"
               else control.make_summary(manifest, records, rounds, directory))
    summary["scheduler_profile"] = SCHEDULER_PROFILE
    summary["operational_attempts"] = manifest["attempts"]
    summary["operational_attempt_note"] = "Unknown costs of attempts without returned raw responses remain unknown; paused time is excluded."
    primary.write_json(directory / "summary.json", summary, exclusive=not (directory / "summary.json").exists())
    if condition == "all_to_all":
        if summary.get("calibration") is not None and manifest.get("calibration_snapshot") is None:
            artifact = {"schema_version": 1, "experiment_id": primary.EXPERIMENT_ID,
                        "protocol_sha256": primary.protocol_hash(), "model_digest": manifest["model_metadata"]["digest"],
                        "ollama_version": manifest["ollama_version"], "references": summary["calibration"],
                        "source_run": str(directory), "evidence_sha256": summary["evidence_sha256"]}
            if not (directory / "calibration.json").exists():
                primary.write_json(directory / "calibration.json", artifact, exclusive=True)
        chosen = summary["selected_rounds"].get("validation", {}).get("primary", {}).get("selected_round")
        if chosen is not None:
            artifact = {"schema_version": 1, "experiment_id": primary.EXPERIMENT_ID,
                        "protocol_sha256": primary.protocol_hash(), "model_digest": manifest["model_metadata"]["digest"],
                        "ollama_version": manifest["ollama_version"], "source_run": str(directory),
                        "calibration_sha256": manifest["calibration_sha256"], "primary_round": chosen,
                        "primary_delta": FROZEN_PROTOCOL["primary_delta"], "primary_omega": FROZEN_PROTOCOL["primary_omega"],
                        "validation_question_ids": [task["id"] for task in manifest["tasks_snapshot"]],
                        "validation_group_ids": sorted({task["group_id"] for task in manifest["tasks_snapshot"] if "group_id" in task}),
                        "evidence_sha256": summary["evidence_sha256"]}
            if not (directory / "selection.json").exists():
                primary.write_json(directory / "selection.json", artifact, exclusive=True)
    manifest.update(status="complete", evidence_sha256=summary["evidence_sha256"],
                    generation_sources_unchanged=True, finished_at=primary.now())
    manifest.pop("active_call", None)
    manifest.pop("active_round", None)
    _save(directory, manifest)


def run_question(*, config_path, tasks_path, output_dir, condition="all_to_all", parent_run=None,
                 calibration=None, selection=None, timeout=600, resume=False, pause_requested=None):
    """Return 0 complete, 2 safely paused, 1 failed, or 130 force-interrupted."""
    directory, manifest, ready = Path(output_dir).resolve(), None, False
    active, attempt = None, None
    pause_requested = pause_requested or (lambda: False)
    try:
        if condition not in {"all_to_all", "self_revision"} or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("Valid condition and positive finite timeout are required")
        config_path, tasks_path = Path(config_path).resolve(), Path(tasks_path).resolve()
        parent_run = Path(parent_run).resolve() if parent_run is not None else None
        calibration = Path(calibration).resolve() if calibration is not None else None
        selection = Path(selection).resolve() if selection is not None else None
        current_sources = lambda: _sources(config_path, tasks_path, condition, parent_run, calibration, selection)
        plan, parent_records, parent_rounds = _plan(config_path, tasks_path, directory, condition,
                                                  parent_run, calibration, selection, timeout)
        if resume:
            manifest = primary.strict_json((directory / "run-manifest.json").read_text())
            if manifest.get("status") == "complete":
                _check_state(manifest)
                if manifest.get("source_sha256") != plan["source_sha256"]:
                    raise ValueError("Completed trajectory sources or inputs differ")
                analyze_run(directory, condition)
                return 0
            generations, records, rounds, had_marker = _audit(directory, manifest, plan, condition, parent_records, parent_rounds)
        else:
            primary.validate_output_directory(directory)
            generations, records, rounds, had_marker = [], [], [], False
            manifest = {**plan, "status": "running", "started_at": primary.now(), "calls_completed": 0,
                        "new_calls_completed": 0, "rounds_completed": 0, "attempts": [], "error_history": [],
                        "round_timing": {}, "resume_count": 0, "generation_sources_unchanged": True}
        client = OllamaClient(timeout=timeout)
        health, model = primary.installed_model(client)
        if resume:
            _identity(client, manifest, current_sources)
        else:
            if condition == "self_revision" and (model["digest"] != plan["parent_snapshot"]["model_digest"]
                                                  or health["version"] != plan["parent_snapshot"]["ollama_version"]):
                raise OllamaError("Control model/runtime differs from its shared primary panel")
            inherited = plan.get("calibration_snapshot")
            if inherited and (inherited["model_digest"] != model["digest"] or inherited["ollama_version"] != health["version"]):
                raise OllamaError("Calibration model/runtime differs from current Ollama")
            manifest.update(model_metadata=model, ollama_version=health["version"])
            if current_sources() != manifest["source_sha256"]:
                raise ValueError("Sources changed during scheduler preflight")
            directory.mkdir(parents=True, exist_ok=False)
            for name in JOURNALS:
                (directory / name).touch(exist_ok=False)
        ready = True
        manifest.update(status="running", last_started_at=primary.now(), resume_count=manifest["resume_count"] + int(resume))
        _save(directory, manifest)
        with (directory / "generations.jsonl").open("a", encoding="utf-8") as raw_output, \
                (directory / "answers.jsonl").open("a", encoding="utf-8") as answer_output, \
                (directory / "rounds.jsonl").open("a", encoding="utf-8") as round_output:
            tasks = {task["id"]: task for task in manifest["tasks_snapshot"]}
            # A returned response may have reached disk immediately before forced interruption.
            if len(generations) == len(records) + 1:
                generation = generations[-1]
                task = tasks[generation["question_id"]]
                started = time.perf_counter()
                if condition == "self_revision" and generation["round"] == 0:
                    original = next(r for r in parent_records if _key(r) == _key(generation))
                    record = control._reuse(original, manifest["parent_snapshot"])
                else:
                    response = evaluate_response(generation["raw"], task["probability"])
                    record = {**generation, "type": "answer", "response": response,
                              "postprocessing_seconds": time.perf_counter() - started}
                primary.append_record(answer_output, record)
                records.append(record)
                if not (condition == "self_revision" and generation["round"] == 0):
                    elapsed = time.perf_counter() - started
                    timing = manifest["round_timing"].setdefault(
                        _round_key(generation["question_id"], generation["round"]),
                        {"active_seconds": 0.0, "segments": []})
                    timing["active_seconds"] = max(timing["active_seconds"], generation.get("round_active_seconds", 0)) + elapsed
                    timing["segments"].append({"elapsed_seconds": elapsed, "reason": "recover_returned_raw"})
                for item in manifest["attempts"]:
                    if tuple(item["call"]) == _key(record) and item.get("status") in {"inflight", "raw_received"}:
                        item["status"] = "recovered_from_raw"
            for item in manifest["attempts"]:
                if item.get("status") == "inflight":
                    item.update(status="uncertain_no_returned_raw", input_tokens=None, output_tokens=None)
            manifest["calls_completed"] = len(records)
            manifest["new_calls_completed"] = sum(not r.get("reused_round_zero", False) for r in records)
            _save(directory, manifest)
            parent_initial = {_key(r): r for r in parent_records if r["round"] == 0}
            parent_first = {r["question_id"]: r for r in parent_rounds if r["round"] == 0}
            lookup = {_key(r): r for r in records}
            saved_rounds = {(r["question_id"], r["round"]): r for r in rounds}
            def save_counts():
                manifest.update(calls_completed=len(records), rounds_completed=len(rounds),
                                new_calls_completed=sum(not r.get("reused_round_zero", False) for r in records))
                _save(directory, manifest)
            def close_segment(reason):
                nonlocal active
                if active is not None:
                    timing, started, baseline = active
                    elapsed = time.perf_counter() - started
                    timing["active_seconds"] = baseline + elapsed
                    timing["segments"].append({"elapsed_seconds": elapsed, "reason": reason})
                    active = None
            def pause():
                close_segment("pause")
                manifest.update(status="paused", last_paused_at=primary.now())
                save_counts()
                return 2
            for task in manifest["tasks_snapshot"]:
                history, previous = [], None
                for index in range(4):
                    identity = (task["id"], index)
                    if identity in saved_rounds:
                        history.append(saved_rounds[identity])
                        previous = [lookup[(task["id"], index, agent)] for agent in range(10)]
                        continue
                    current = [lookup[(task["id"], index, agent)] for agent in range(10)
                               if (task["id"], index, agent) in lookup]
                    if condition == "self_revision" and index == 0:
                        for agent in range(len(current), 10):
                            record = control._reuse(parent_initial[(task["id"], 0, agent)], manifest["parent_snapshot"])
                            primary.append_record(raw_output, _generation(record))
                            primary.append_record(answer_output, record)
                            generations.append(_generation(record)); records.append(record); current.append(record)
                            lookup[_key(record)] = record
                            save_counts()
                        row = copy.deepcopy(parent_first[task["id"]])
                    else:
                        if pause_requested():
                            return pause()
                        timing = manifest["round_timing"].setdefault(_round_key(*identity), {"active_seconds": 0.0, "segments": []})
                        measured = [r.get("round_active_seconds", 0) + r.get("postprocessing_seconds", 0) for r in current]
                        timing["active_seconds"] = max([timing["active_seconds"], *measured])
                        baseline = timing["active_seconds"]
                        started_round = time.perf_counter()
                        active = timing, started_round, baseline
                        manifest["active_round"] = {"question_id": task["id"], "round": index}
                        prompts = [_messages(task, index, agent, previous, condition) for agent in range(10)]
                        budgets = [primary.context_budget(messages) for messages in prompts]
                        for agent in range(len(current), 10):
                            if pause_requested():
                                return pause()
                            _identity(client, manifest, current_sources)
                            key = task["id"], index, agent
                            manifest["active_call"] = {"question_id": key[0], "round": key[1], "agent_id": key[2]}
                            attempt = {"call": list(key), "status": "inflight", "started_at": primary.now(),
                                       "input_tokens": None, "output_tokens": None, "elapsed_seconds": None}
                            manifest["attempts"].append(attempt)
                            _save(directory, manifest)
                            started_call = time.perf_counter()
                            raw = client.chat(FROZEN_PROTOCOL["model"], prompts[agent], seed=agent_seed(*key),
                                              temperature=FROZEN_PROTOCOL["temperature"], max_tokens=FROZEN_PROTOCOL["max_tokens"])
                            elapsed = time.perf_counter() - started_call
                            generation = {"type": "generation", "question_id": key[0], "family": task["family"],
                                          "split": task["split"], "round": index, "agent_id": agent,
                                          "seed": agent_seed(*key), "messages": prompts[agent], "raw": raw,
                                          "elapsed_seconds": elapsed, "context_budget": budgets[agent],
                                          "round_active_seconds": baseline + time.perf_counter() - started_round}
                            if condition == "self_revision":
                                generation["reused_round_zero"] = False
                            primary.append_record(raw_output, generation)
                            generations.append(generation)
                            attempt.update(status="raw_received", elapsed_seconds=elapsed,
                                           input_tokens=raw.get("prompt_eval_count") if isinstance(raw, dict) else None,
                                           output_tokens=raw.get("eval_count") if isinstance(raw, dict) else None)
                            _wrapper(raw)
                            started_post = time.perf_counter()
                            response = evaluate_response(raw, task["probability"])
                            record = {**generation, "type": "answer", "response": response,
                                      "postprocessing_seconds": time.perf_counter() - started_post}
                            primary.append_record(answer_output, record)
                            records.append(record); current.append(record); lookup[key] = record
                            attempt["status"] = "complete"
                            attempt = None
                            timing["active_seconds"] = baseline + time.perf_counter() - started_round
                            save_counts()
                            if len(current) < 10 and pause_requested():
                                return pause()
                        close_segment("round_complete")
                        row = primary.summarize_round(task, current, timing["active_seconds"], history)
                    primary.append_record(round_output, row)
                    rounds.append(row); saved_rounds[identity] = row
                    previous, history = current, [*history, row]
                    manifest.pop("active_call", None)
                    save_counts()
                    if pause_requested():
                        return pause()
            _identity(client, manifest, current_sources)
            marker = {"type": "complete", "calls_completed": len(records), "rounds_completed": len(rounds)}
            if condition == "self_revision":
                marker["new_calls_completed"] = manifest["new_calls_completed"]
            if not had_marker:
                primary.append_record(answer_output, marker)
        _finish_artifacts(directory, manifest, records, rounds, condition)
        return 0
    except KeyboardInterrupt:
        error, code = "Force-interrupted; an in-flight call may have unknown cost", 130
    except ERRORS as exc:
        error, code = str(exc), 1
    if ready and manifest is not None:
        if active is not None:
            timing, started, baseline = active
            elapsed = time.perf_counter() - started
            timing["active_seconds"] = baseline + elapsed
            timing["segments"].append({"elapsed_seconds": elapsed, "reason": "interrupted" if code == 130 else "error"})
        if attempt is not None:
            if attempt.get("elapsed_seconds") is None and "started_call" in locals():
                attempt["elapsed_seconds"] = time.perf_counter() - started_call
            attempt["status"] = "raw_received" if attempt.get("status") == "raw_received" else "uncertain_no_returned_raw"
        manifest.update(status="interrupted" if code == 130 else "failed", error=error, last_stopped_at=primary.now())
        manifest["error_history"].append({"time": primary.now(), "error": error, "exit_code": code})
        manifest["calls_completed"] = len(records)
        manifest["new_calls_completed"] = sum(not r.get("reused_round_zero", False) for r in records)
        manifest["rounds_completed"] = len(rounds)
        try:
            manifest["generation_sources_unchanged"] = current_sources() == manifest["source_sha256"]
        except OSError:
            manifest["generation_sources_unchanged"] = False
        _save(directory, manifest)
    print(f"Trajectory stopped: {error}", file=sys.stderr)
    return code
