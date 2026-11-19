"""Five-agent phase analysis and frozen development/validation artifacts.

Exact plurality is label-free. References score completed decisions only.
Calibration uses development R1 revision costs; validation alone chooses the
one common primary round. Test reports apply that frozen choice unchanged.
"""

from collections import Counter
import copy
import hashlib
import json
import math
import random

from experiments.architecture_pilots.analysis import (
    _cost, _round, _statistics, _difference, _csv_bytes,
)
from .protocol import STUDY_ID, PHASES, ARMS, NUM_AGENTS, MAX_ROUNDS, FAMILIES


BOOTSTRAP_DRAWS = 2000
BOOTSTRAP_SEED = 20261118
COST_WEIGHT = 0.02
CALIBRATION_ID = "five-agent-full-study-v2-development-calibration"
SELECTION_ID = "five-agent-full-study-v2-validation-selection"
TIME_METRIC = "summed_model_request_seconds"
COST_SCOPE = "communication_revisions_only_excluding_initial"


def artifact_hash(value):
    data = json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _validate(manifest, initial_panel, revisions, phase):
    if phase not in PHASES:
        raise ValueError("Unknown full-study phase")
    tasks = manifest["tasks_snapshot"]
    if (not isinstance(tasks, list) or not tasks
            or len({task["id"] for task in tasks}) != len(tasks)
            or any(task["split"] != phase or task["family"] not in FAMILIES for task in tasks)):
        raise ValueError("Phase analysis requires unique questions exclusively from its scheduled split")
    groups = {}
    for task in tasks:
        group = task.get("group_id")
        if not isinstance(group, str) or not group:
            raise ValueError("Every question needs a structural group")
        identity = task["family"], task["split"]
        if group in groups and groups[group] != identity:
            raise ValueError("A structural group cannot cross families or phases")
        groups[group] = identity
    count = manifest.get("configuration_snapshot", {}).get("num_agents", NUM_AGENTS)
    if type(count) is not int or count != NUM_AGENTS:
        raise ValueError("The full study requires exactly five agents")
    if any(type(row.get("agent_id")) is not int or type(row.get("round")) is not int
           for row in initial_panel + revisions):
        raise ValueError("Round and agent identities must be integers")
    expected_initial = {(task["id"], 0, agent, "shared_initial")
                        for task in tasks for agent in range(NUM_AGENTS)}
    actual_initial = [(row.get("question_id"), row.get("round"), row.get("agent_id"), row.get("arm"))
                      for row in initial_panel]
    if len(actual_initial) != len(expected_initial) or set(actual_initial) != expected_initial:
        raise ValueError("Initial evidence must cover every shared question-agent position once")
    expected = {(task["id"], index, agent, arm) for task in tasks
                for index in range(1, MAX_ROUNDS + 1) for agent in range(NUM_AGENTS) for arm in ARMS}
    actual = [(row.get("question_id"), row.get("round"), row.get("agent_id"), row.get("arm"))
              for row in revisions]
    if len(actual) != len(expected) or set(actual) != expected:
        raise ValueError("Revisions must cover every branch/question/round/agent position once")
    return tasks


def _bootstrap_indices(tasks):
    families = {}
    for task_index, task in enumerate(tasks):
        families.setdefault(task["family"], {}).setdefault(task["group_id"], []).append(task_index)
    rng = random.Random(BOOTSTRAP_SEED)
    sampled = []
    for _ in range(BOOTSTRAP_DRAWS):
        indices = []
        for family in sorted(families):
            groups = families[family]
            names = sorted(groups)
            for _ in names:
                indices.extend(groups[rng.choice(names)])
        sampled.append(indices)
    return sampled


def _percentile(values, probability):
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    left, right = math.floor(position), math.ceil(position)
    return ordered[left] + (ordered[right] - ordered[left]) * (position - left)


def _interval(point, values):
    valid = [value for value in values if value is not None]
    return {"estimate": point, "interval_95": [_percentile(valid, 0.025), _percentile(valid, 0.975)]
            if point is not None and valid else None,
            "valid_bootstrap_draws": len(valid) if point is not None else 0,
            "total_bootstrap_draws": BOOTSTRAP_DRAWS}


def _accuracy(rows, indices=None):
    selected = rows if indices is None else [rows[index] for index in indices]
    families = sorted({row["family"] for row in selected})
    return {"accuracy": sum(row["correct"] for row in selected) / len(selected),
            "family_balanced_accuracy": sum(
                sum(row["correct"] for row in selected if row["family"] == family)
                / sum(row["family"] == family for row in selected) for family in families) / len(families)}


def _initial_controls(tasks, round_zero_rows, sampled):
    cases = {"single_agent_0": [], "oracle_any_initial_eligible_correct": [], "five_agent_plurality": []}
    for task, row in zip(tasks, round_zero_rows):
        for name, correct in (("single_agent_0", row["agent_correct"]["0"]),
                              ("oracle_any_initial_eligible_correct", bool(row["correct_agents"])),
                              ("five_agent_plurality", row["correct"])):
            cases[name].append({"question_id": task["id"], "group_id": task["group_id"],
                                "family": task["family"], "correct": correct})
    result = {}
    distributions = {}
    for name, rows in cases.items():
        point = _accuracy(rows)
        draws = [_accuracy(rows, indices) for indices in sampled]
        distributions[name] = draws
        result[name] = {"correct_questions": sum(row["correct"] for row in rows), "questions": len(rows),
                        **point, "per_question": rows,
                        "uncertainty": {metric: _interval(value, [draw[metric] for draw in draws])
                                        for metric, value in point.items()}}
    result["panel_minus_single_agent_0"] = {
        metric + "_difference": _interval(result["five_agent_plurality"][metric] - result["single_agent_0"][metric],
            [panel[metric] - agent[metric] for panel, agent in zip(distributions["five_agent_plurality"],
                                                                  distributions["single_agent_0"])])
        for metric in ("accuracy", "family_balanced_accuracy")}
    result["oracle_note"] = "Reference-based capability diagnostic only; not an operational voter or stopping rule."
    return result


def _validate_calibration(calibration):
    if (not isinstance(calibration, dict) or calibration.get("artifact_id") != CALIBRATION_ID
            or calibration.get("study_id") != STUDY_ID or calibration.get("source_phase") != "development"
            or calibration.get("cost_scope") != COST_SCOPE or calibration.get("time_metric") != TIME_METRIC):
        raise ValueError("Calibration must be the frozen development-only request-time artifact")
    for key in ("token_reference", "request_seconds_reference"):
        value = calibration.get("references", {}).get(key)
        if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
            raise ValueError("Calibration references must be finite and strictly positive")
    return calibration


def _validate_selection(selection, calibration, tasks):
    _validate_calibration(calibration)
    if (not isinstance(selection, dict) or selection.get("artifact_id") != SELECTION_ID
            or selection.get("study_id") != STUDY_ID or selection.get("source_phase") != "validation"
            or type(selection.get("primary_round")) is not int
            or selection["primary_round"] not in range(MAX_ROUNDS + 1)
            or selection.get("calibration_sha256") != artifact_hash(calibration)
            or selection.get("cost_scope") != COST_SCOPE or selection.get("time_metric") != TIME_METRIC):
        raise ValueError("Primary round must come from the frozen validation selection")
    candidates = selection.get("candidates")
    if (not isinstance(candidates, list) or [row.get("round") for row in candidates] != list(range(MAX_ROUNDS + 1))
            or any(type(row.get("objective")) not in (int, float)
                   or not math.isfinite(row["objective"]) for row in candidates)
            or min(candidates, key=lambda row: (row["objective"], row["round"]))["round"] != selection["primary_round"]
            or selection.get("self_revision_primary_round") != selection["primary_round"]
            or selection.get("test_feedback_used") is not False):
        raise ValueError("Locked primary round differs from its validation objective candidates")
    if set(selection.get("source_question_ids", [])) & {task["id"] for task in tasks}:
        raise ValueError("Selection data must be disjoint from evaluated test questions")
    if set(selection.get("source_group_ids", [])) & {task["group_id"] for task in tasks}:
        raise ValueError("Selection groups must be disjoint from evaluated test groups")


def summarize_phase(manifest, initial_panel, revisions, phase, calibration=None, selection=None):
    tasks = _validate(manifest, initial_panel, revisions, phase)
    if calibration is not None:
        _validate_calibration(calibration)
    if phase == "test":
        _validate_selection(selection, calibration, tasks)
    elif selection is not None:
        raise ValueError("Write raw development/validation reports before creating selection artifacts")
    cases, by_key = [], {}
    for arm in ARMS:
        for task in tasks:
            history, prefix = [], []
            for index in range(MAX_ROUNDS + 1):
                source = initial_panel if index == 0 else revisions
                panel = sorted([row for row in source if row["question_id"] == task["id"]
                                and row["round"] == index and (index == 0 or row["arm"] == arm)],
                               key=lambda row: row["agent_id"])
                prefix.extend(panel)
                row = _round(task, panel, history[-1] if history else None, history[0] if history else None,
                             arm, index, prefix)
                row.pop("prior_confirmation_stratum", None)
                row["phase"] = phase
                row["planned_difficulty"] = task.get("difficulty")
                cases.append(row)
                by_key.setdefault((arm, index), []).append(row)
                history.append(row)
    sampled = _bootstrap_indices(tasks)
    points = {key: _statistics(rows) for key, rows in by_key.items()}
    draws = {key: [_statistics(rows, indices) for indices in sampled] for key, rows in by_key.items()}
    metrics = ("accuracy", "family_balanced_accuracy", "coverage", "accuracy_among_answered",
               "individual_accuracy", "family_balanced_individual_accuracy",
               "cumulative_total_tokens", "cumulative_request_seconds")
    families = sorted({task["family"] for task in tasks})
    comparisons = []
    for arm in ARMS:
        for index in range(MAX_ROUNDS + 1):
            key = arm, index
            comparisons.append({"arm": arm, "round": index, "num_agents": NUM_AGENTS,
                                "voting_rule": "plurality", "endpoint": f"fixed_round_{index}", **points[key],
                                "by_family": {family: _statistics([row for row in by_key[key] if row["family"] == family])
                                              for family in families},
                                "uncertainty": {metric: _interval(points[key][metric], [draw[metric] for draw in draws[key]])
                                                for metric in metrics}})
    paired, joint = [], []
    initial_cost = _cost(initial_panel)
    for index in range(MAX_ROUNDS + 1):
        left, right = ("communication", index), ("self_revision", index)
        point = _difference(points[left], points[right])
        distribution = [_difference(a, b) for a, b in zip(draws[left], draws[right])]
        paired.append({"round": index, "contrast": "communication_minus_self_revision",
                       "correct_question_gains": sum(a["correct"] and not b["correct"]
                                                     for a, b in zip(by_key[left], by_key[right])),
                       "correct_question_losses": sum(not a["correct"] and b["correct"]
                                                      for a, b in zip(by_key[left], by_key[right])),
                       "metrics": {metric: _interval(value, [draw[metric] for draw in distribution])
                                   for metric, value in point.items()}})
        cost = {"round": index, "unique_calls": points[left]["cumulative_calls"]
                + points[right]["cumulative_calls"] - initial_cost["calls"]}
        for metric in ("input_tokens", "output_tokens", "total_tokens", "request_seconds", "loading_seconds"):
            a, b, shared = points[left][f"cumulative_{metric}"], points[right][f"cumulative_{metric}"], initial_cost[metric]
            cost[metric] = a + b - shared if all(value is not None for value in (a, b, shared)) else None
        joint.append(cost)
    group_counts = {family: len({task["group_id"] for task in tasks if task["family"] == family})
                    for family in families}
    physical = _cost(initial_panel + revisions)
    primary_round = selection["primary_round"] if selection is not None else None
    return {
        "schema_version": 1, "study_id": STUDY_ID, "phase": phase,
        "scope": "descriptive_inspected_development" if phase == "development" else
                 "held_out_validation_for_prespecified_round_selection" if phase == "validation" else
                 "held_out_test_at_locked_validation_selected_round",
        "questions": len(tasks), "semantic_groups": len({task["group_id"] for task in tasks}),
        "task_ids": [task["id"] for task in tasks], "group_ids": sorted({task["group_id"] for task in tasks}),
        "architecture": {"num_agents": NUM_AGENTS, "peer_count": NUM_AGENTS - 1},
        "comparison_rows": len(comparisons), "per_question_rows": len(cases),
        "comparisons": comparisons, "per_question": cases, "cross_arm_comparisons": paired,
        "initial_controls": _initial_controls(tasks, by_key[("communication", 0)], sampled),
        "source_generation_cost_including_initial_once": {"unique_calls": physical["calls"],
                                                          **{key: value for key, value in physical.items() if key != "calls"}},
        "initial_generation_cost": initial_cost, "joint_round_costs": joint,
        "generation_protocol": copy.deepcopy(manifest.get("protocol_snapshot")),
        "execution_environment": copy.deepcopy(manifest.get("execution_environment")),
        "hardware_snapshot": copy.deepcopy(manifest.get("hardware_snapshot")),
        "bootstrap": {"method": "paired_family_stratified_whole_semantic_group_percentile_bootstrap",
                      "draws": BOOTSTRAP_DRAWS, "seed": BOOTSTRAP_SEED,
                      "groups": len({task["group_id"] for task in tasks}), "clusters_per_family": group_counts,
                      "variants_resampled_together": True, "same_draws_across_rounds_and_arms": True,
                      "accuracy_estimand": "question-weighted within family, then equally weighted across families",
                      "draw_question_counts_may_vary": True,
                      "inference": "Paired structural-group uncertainty; one generation seed panel per question, not independent agents."},
        "calibration": copy.deepcopy(calibration), "selection": copy.deepcopy(selection),
        "primary_round": primary_round,
        "primary_comparison": {
            "round": primary_round,
            "communication": next(row for row in comparisons if row["arm"] == "communication" and row["round"] == primary_round),
            "self_revision": next(row for row in comparisons if row["arm"] == "self_revision" and row["round"] == primary_round),
            "paired": next(row for row in paired if row["round"] == primary_round),
            "selection_source": "validation_only_locked_before_test",
        } if primary_round is not None else None,
        "test_round_selection_performed": False,
        "notes": [
            "Five-agent current-round exact-rational plurality; tied or empty eligible panels abstain and count incorrect.",
            "The same initial raw records are used in both branch trajectories and charged once in physical costs.",
            "Both arms use five matched generations per round; tokens and request time are not matched budgets.",
            "Reference values score completed decisions only and are never forwarded into model prompts.",
            "Development calibrates positive family-balanced R1 communication revision token/request-time references.",
            "Validation alone selects one global primary round; both test branches are evaluated at that locked round.",
            "All other test round curves are descriptive and cannot retune the primary selection.",
            "Request time includes model loading but excludes health checks, prompt construction, evaluation, journaling and pauses.",
            "The request-time calibration is a pre-validation amendment to the historical full-round-wall-time objective.",
        ],
    }


def _family_mean(rows, field):
    families = sorted({row["family"] for row in rows})
    if not rows:
        raise ValueError("Cost calibration requires question-level rows")
    for row in rows:
        value = row.get(field)
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ValueError("Cost measurements must be known, finite and nonnegative")
    return sum(sum(row[field] for row in rows if row["family"] == family)
               / sum(row["family"] == family for row in rows) for family in families) / len(families)


def create_calibration(summary, tasks=None):
    if summary.get("study_id") != STUDY_ID or summary.get("phase") != "development":
        raise ValueError("Only development can calibrate cost references")
    rows = [row for row in summary["per_question"] if row["arm"] == "communication" and row["round"] == 1]
    if any(row.get("split") != "development" for row in rows):
        raise ValueError("Calibration rows must come exclusively from development")
    token_reference = _family_mean(rows, "revision_total_tokens")
    request_reference = _family_mean(rows, "revision_request_seconds")
    if token_reference <= 0 or request_reference <= 0:
        raise ValueError("R1 development cost references must be strictly positive")
    if tasks is not None and ([task["id"] for task in tasks] != summary["task_ids"]
                              or any(task["split"] != "development" for task in tasks)):
        raise ValueError("Calibration task identity differs from the development report")
    return {"schema_version": 1, "artifact_id": CALIBRATION_ID, "study_id": STUDY_ID,
            "source_phase": "development", "source_summary_sha256": artifact_hash(summary),
            "source_question_ids": list(summary["task_ids"]), "source_group_ids": list(summary["group_ids"]),
            "cost_scope": COST_SCOPE, "time_metric": TIME_METRIC,
            "reference_definition": "family_balanced_mean_per_question_communication_round_1_revision_cost",
            "references": {"token_reference": token_reference, "request_seconds_reference": request_reference},
            "objective": {"cost_weight": COST_WEIGHT, "token_weight": 0.5, "request_time_weight": 0.5,
                          "error": "one_minus_family_balanced_communication_accuracy", "tie_rule": "fewer_rounds"}}


def choose_round(validation_summary, calibration):
    _validate_calibration(calibration)
    if validation_summary.get("study_id") != STUDY_ID or validation_summary.get("phase") != "validation":
        raise ValueError("Only held-out validation can choose the primary round")
    if set(validation_summary["group_ids"]) & set(calibration["source_group_ids"]):
        raise ValueError("Validation selection groups overlap development calibration groups")
    if set(validation_summary["task_ids"]) & set(calibration["source_question_ids"]):
        raise ValueError("Validation selection questions overlap development calibration questions")
    candidates = []
    for index in range(MAX_ROUNDS + 1):
        point = next(row for row in validation_summary["comparisons"]
                     if row["arm"] == "communication" and row["round"] == index)
        cases = [row for row in validation_summary["per_question"]
                 if row["arm"] == "communication" and row["round"] == index]
        if any(row.get("split") != "validation" for row in cases):
            raise ValueError("Selection rows must come exclusively from validation")
        tokens = _family_mean(cases, "revision_total_tokens")
        seconds = _family_mean(cases, "revision_request_seconds")
        normalized_tokens = tokens / calibration["references"]["token_reference"]
        normalized_time = seconds / calibration["references"]["request_seconds_reference"]
        error = 1 - point["family_balanced_accuracy"]
        if not math.isfinite(error) or not 0 <= error <= 1:
            raise ValueError("Validation accuracy is invalid")
        candidates.append({"round": index, "family_balanced_error": error,
                           "family_balanced_revision_tokens_per_question": tokens,
                           "family_balanced_revision_request_seconds_per_question": seconds,
                           "normalized_tokens": normalized_tokens, "normalized_request_time": normalized_time,
                           "objective": error + COST_WEIGHT * (0.5 * normalized_tokens + 0.5 * normalized_time)})
    best = min(candidates, key=lambda row: (row["objective"], row["round"]))
    return {"schema_version": 1, "artifact_id": SELECTION_ID, "study_id": STUDY_ID,
            "source_phase": "validation", "source_summary_sha256": artifact_hash(validation_summary),
            "source_question_ids": list(validation_summary["task_ids"]),
            "source_group_ids": list(validation_summary["group_ids"]),
            "calibration_sha256": artifact_hash(calibration), "primary_round": best["round"],
            "cost_scope": COST_SCOPE, "time_metric": TIME_METRIC,
            "objective": "family_balanced_error_plus_0.02_times_half_normalized_revision_tokens_and_half_normalized_revision_request_time",
            "tie_rule": "fewer_rounds", "candidates": candidates,
            "self_revision_primary_round": best["round"],
            "test_feedback_used": False}


def report_bytes(summary):
    return {"summary.json": (json.dumps(summary, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8"),
            "comparisons.csv": _csv_bytes(summary["comparisons"]),
            "per_question.csv": _csv_bytes(summary["per_question"])}
