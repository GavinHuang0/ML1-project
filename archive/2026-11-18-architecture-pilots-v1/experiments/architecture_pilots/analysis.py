"""Exact plurality and paired group analysis for the two architecture pilots.

The pilots generate new trajectories on previously inspected development
questions. This module scores those trajectories; it does not subsample old
results, select a winning architecture, or change the generation procedure.
"""

from collections import Counter
import copy
import csv
from fractions import Fraction
import io
import json
import math
import random

from experiments.communication_pilot.analysis import _diagnostics
from .protocol import ARMS, FAMILIES, TASK_IDS, MAX_ROUNDS


BOOTSTRAP_DRAWS = 2000
BOOTSTRAP_SEED = 20261118


def _sum_known(values):
    values = list(values)
    return sum(values) if all(value is not None for value in values) else None


def _cost(records):
    tokens = {}
    for raw_name, name in (("prompt_eval_count", "input_tokens"), ("eval_count", "output_tokens")):
        values = [record["raw"].get(raw_name) for record in records]
        tokens[name] = sum(values) if all(type(value) is int and value >= 0 for value in values) else None
    durations = [record.get("elapsed_seconds") for record in records]
    if any(type(value) not in (int, float) or not math.isfinite(value) or value < 0 for value in durations):
        raise ValueError("Model-request durations must be finite and nonnegative")
    loading = [record["raw"].get("load_duration") for record in records]
    loading_seconds = sum(loading) / 1e9 if all(type(value) is int and value >= 0 for value in loading) else None
    return {"calls": len(records), **tokens, "total_tokens": _sum_known(tokens.values()),
            "request_seconds": sum(durations), "loading_seconds": loading_seconds}


def _validate(manifest, initial_panel, answers):
    config = manifest["configuration_snapshot"]
    count = config["num_agents"]
    peers = config["peer_count"]
    if type(count) is not int or (count, peers) not in ((5, 4), (10, 2)):
        raise ValueError("Analysis requires the five-agent dense or ten-agent two-peer architecture")
    tasks = manifest["tasks_snapshot"]
    if (not isinstance(tasks, list) or [task["id"] for task in tasks] != list(TASK_IDS)
            or len(tasks) != 12 or len({task["group_id"] for task in tasks}) != 8
            or any(task["split"] != "development" for task in tasks)
            or Counter(task["family"] for task in tasks) != Counter({family: 3 for family in FAMILIES})):
        raise ValueError("Architecture pilots require the twelve frozen inspected development cases")
    groups = {}
    for task in tasks:
        groups.setdefault(task["group_id"], []).append(task)
    if (sorted(map(len, groups.values())) != [1] * 4 + [2] * 4
            or any(len({task["family"] for task in members}) != 1 for members in groups.values())
            or any(len({task["group_id"] for task in tasks if task["family"] == family}) != 2
                   for family in FAMILIES)):
        raise ValueError("Structural groups must keep numerical variants together within family")
    expected_initial = {(task["id"], 0, agent, "shared_initial")
                        for task in tasks for agent in range(count)}
    if any(type(r.get("agent_id")) is not int or type(r.get("round")) is not int for r in initial_panel + answers):
        raise ValueError("Round and agent identities must be integers")
    positions = [(r.get("question_id"), r.get("round"), r.get("agent_id"), r.get("arm"))
                 for r in initial_panel]
    if len(positions) != len(expected_initial) or set(positions) != expected_initial:
        raise ValueError("Initial evidence must contain every shared question-agent position exactly once")
    expected_revisions = {(task["id"], index, agent, arm)
                          for task in tasks for index in range(1, MAX_ROUNDS + 1)
                          for agent in range(count) for arm in ARMS}
    positions = [(r.get("question_id"), r.get("round"), r.get("agent_id"), r.get("arm")) for r in answers]
    if len(positions) != len(expected_revisions) or set(positions) != expected_revisions:
        raise ValueError("Revisions must contain every branch/question/round/agent position exactly once")
    return tasks, count, peers


def _value(record, probability):
    response = record["response"]
    if not all(response.get(key) is True for key in
               ("eligible", "json_valid", "required_fields_valid", "calculator_success")):
        return None
    text = response.get("computed_fraction")
    if not isinstance(text, str):
        raise ValueError("Eligible records need an exact rational calculator value")
    try:
        value = Fraction(text)
    except (ValueError, ZeroDivisionError) as exc:
        raise ValueError("Eligible records need a valid exact rational value") from exc
    if probability and not 0 <= value <= 1:
        raise ValueError("Eligible probability records must be in range")
    return value


def _round(task, panel, previous, initial, arm, index, prefix):
    values = {str(record["agent_id"]): _value(record, task["probability"]) for record in panel}
    votes = Counter(value for value in values.values() if value is not None)
    largest = max(votes.values(), default=0)
    winners = sorted(value for value, number in votes.items() if number == largest)
    answer = winners[0] if len(winners) == 1 else None
    # Reference scoring begins only after the label-free exact plurality.
    gold = Fraction(task["gold_fraction"])
    agent_correct = {agent: value == gold if value is not None else False for agent, value in values.items()}
    correct = answer == gold if answer is not None else False
    count = len(panel)
    row = {
        "arm": arm, "question_id": task["id"], "family": task["family"], "split": task["split"],
        "group_id": task["group_id"], "round": index, "num_agents": count,
        "prior_confirmation_stratum": "moderate_structure" if task["id"].endswith("-03") else "hard_structure",
        "aggregation": "current_round_exact_rational_plurality", "answer": str(answer) if answer is not None else None,
        "answered": answer is not None, "correct": correct, "gold_fraction": str(gold),
        "abstention_reason": ("no_eligible_answers" if not votes else "tied_plurality") if answer is None else None,
        "eligible_agents": sum(value is not None for value in values.values()),
        "correct_agents": sum(agent_correct.values()), "agent_correct": agent_correct,
        "votes": {str(value): votes[value] for value in sorted(votes)}, "winning_support": largest,
        "distinct_answers": len(votes), "tied_winners": [str(value) for value in winners] if len(winners) > 1 else [],
        "initial_correct_agents": initial["correct_agents"] if initial is not None else sum(agent_correct.values()),
        "correct_available_but_collective_wrong": bool(sum(agent_correct.values())) and not correct,
        "unanimous_eligible_wrong": bool(votes) and len(votes) == 1 and not correct,
        "all_agent_wrong_consensus": len(votes) == 1 and largest == count and not correct,
        "wrong_strict_majority": answer is not None and not correct and largest > count / 2,
        "beneficial_collective_revision": not previous["correct"] and correct if previous is not None else None,
        "harmful_collective_revision": previous["correct"] and not correct if previous is not None else None,
        "beneficial_agent_revisions": sum(not previous["agent_correct"][agent] and value
                                            for agent, value in agent_correct.items()) if previous is not None else None,
        "harmful_agent_revisions": sum(previous["agent_correct"][agent] and not value
                                         for agent, value in agent_correct.items()) if previous is not None else None,
        "diagnostics": _diagnostics(task, panel),
    }
    for scope, selected in (("round", panel), ("cumulative", prefix),
                            ("revision", [record for record in prefix if record["round"] > 0])):
        row.update({f"{scope}_{key}": value for key, value in _cost(selected).items()})
    return row


def _statistics(rows, indices=None):
    chosen = rows if indices is None else [rows[index] for index in indices]
    if not chosen:
        raise ValueError("Cannot summarize an empty cohort")
    count = len(chosen)
    answered = sum(row["answered"] for row in chosen)
    correct = sum(row["correct"] for row in chosen)
    families = sorted({row["family"] for row in chosen})
    agent_count = sum(row["num_agents"] for row in chosen)
    diagnostic_keys = list(chosen[0]["diagnostics"]["counts"])
    result = {
        "questions": count, "correct_questions": correct, "answered_questions": answered,
        "abstentions": count - answered, "incorrect_delivered_answers": answered - correct,
        "accuracy": correct / count, "coverage": answered / count,
        "accuracy_among_answered": correct / answered if answered else None,
        "family_balanced_accuracy": sum(
            sum(row["correct"] for row in chosen if row["family"] == family)
            / sum(row["family"] == family for row in chosen) for family in families) / len(families),
        "eligible_outputs": sum(row["eligible_agents"] for row in chosen),
        "invalid_outputs": agent_count - sum(row["eligible_agents"] for row in chosen),
        "eligibility_rate": sum(row["eligible_agents"] for row in chosen) / agent_count,
        "correct_agent_outputs": sum(row["correct_agents"] for row in chosen),
        "individual_accuracy": sum(row["correct_agents"] for row in chosen) / agent_count,
        "family_balanced_individual_accuracy": sum(
            sum(row["correct_agents"] for row in chosen if row["family"] == family)
            / sum(row["num_agents"] for row in chosen if row["family"] == family)
            for family in families) / len(families),
        "correct_available_but_collective_wrong_panels": sum(row["correct_available_but_collective_wrong"] for row in chosen),
        "unanimous_eligible_wrong_panels": sum(row["unanimous_eligible_wrong"] for row in chosen),
        "all_agent_wrong_consensus_panels": sum(row["all_agent_wrong_consensus"] for row in chosen),
        "wrong_strict_majority_panels": sum(row["wrong_strict_majority"] for row in chosen),
        "beneficial_collective_revisions": sum(row["beneficial_collective_revision"] is True for row in chosen),
        "harmful_collective_revisions": sum(row["harmful_collective_revision"] is True for row in chosen),
        "beneficial_agent_revisions": sum(row["beneficial_agent_revisions"] or 0 for row in chosen),
        "harmful_agent_revisions": sum(row["harmful_agent_revisions"] or 0 for row in chosen),
        "diagnostic_counts": {key: sum(row["diagnostics"]["counts"][key] for row in chosen) for key in diagnostic_keys},
        "length_stops": sum(row["diagnostics"]["length_stops"] for row in chosen),
    }
    for scope in ("round", "cumulative", "revision"):
        for metric in ("calls", "input_tokens", "output_tokens", "total_tokens", "request_seconds", "loading_seconds"):
            result[f"{scope}_{metric}"] = _sum_known(row[f"{scope}_{metric}"] for row in chosen)
    return result


def _bootstrap_indices(tasks):
    families = {}
    for family in FAMILIES:
        families[family] = {}
        for index, task in enumerate(tasks):
            if task["family"] == family:
                families[family].setdefault(task["group_id"], []).append(index)
    rng = random.Random(BOOTSTRAP_SEED)
    result = []
    for _ in range(BOOTSTRAP_DRAWS):
        indices = []
        for groups in families.values():
            names = sorted(groups)
            for _ in names:
                indices.extend(groups[rng.choice(names)])
        result.append(indices)
    return result


def _percentile(values, probability):
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower, upper = math.floor(position), math.ceil(position)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _interval(point, values):
    valid = [value for value in values if value is not None]
    return {"estimate": point,
            "interval_95": [_percentile(valid, 0.025), _percentile(valid, 0.975)]
            if point is not None and valid else None,
            "valid_bootstrap_draws": len(valid) if point is not None else 0,
            "total_bootstrap_draws": BOOTSTRAP_DRAWS}


def _difference(left, right):
    result = {}
    for key in ("accuracy", "family_balanced_accuracy", "coverage", "accuracy_among_answered",
                "individual_accuracy", "family_balanced_individual_accuracy",
                "cumulative_total_tokens", "cumulative_request_seconds", "revision_total_tokens",
                "revision_request_seconds"):
        result[f"{key}_difference"] = left[key] - right[key] if left[key] is not None and right[key] is not None else None
    for key in ("cumulative_total_tokens", "cumulative_request_seconds", "revision_total_tokens", "revision_request_seconds"):
        result[f"{key}_ratio"] = left[key] / right[key] if left[key] is not None and right[key] else None
    return result


def _routing(manifest, tasks, count, peers):
    positions = manifest.get("call_positions")
    if positions is None:
        return {"recorded_routing_available": False}
    selected = [row for row in positions if row["arm"] == "communication" and row["round"] > 0]
    expected = {(task["id"], index, agent) for task in tasks
                for index in range(1, MAX_ROUNDS + 1) for agent in range(count)}
    keys = [(row["question_id"], row["round"], row["agent_id"]) for row in selected]
    if len(keys) != len(expected) or set(keys) != expected:
        raise ValueError("Recorded routing must cover each communicating revision exactly once")
    snapshots = []
    for task in tasks:
        for index in range(1, MAX_ROUNDS + 1):
            rows = [row for row in selected if row["question_id"] == task["id"] and row["round"] == index]
            inbound = Counter({agent: 0 for agent in range(count)})
            for row in rows:
                ids = row.get("peer_ids")
                if (not isinstance(ids, list) or len(ids) != peers or len(set(ids)) != peers
                        or row["agent_id"] in ids or any(type(agent) is not int or not 0 <= agent < count for agent in ids)):
                    raise ValueError("Recorded peer IDs must be distinct, in-panel and exclude the receiver")
                inbound.update(ids)
            snapshots.append({"question_id": task["id"], "round": index,
                              "directed_peer_references": sum(len(row["peer_ids"]) for row in rows),
                              "inbound_counts": {str(agent): inbound[agent] for agent in range(count)},
                              "min_inbound": min(inbound.values()), "max_inbound": max(inbound.values())})
    return {"recorded_routing_available": True, "communication_calls": len(selected),
            "peer_count_per_call": peers, "directed_peer_references": len(selected) * peers,
            "directed_peer_references_per_question_round": count * peers,
            "snapshots": snapshots,
            "note": "inbound_counts counts how often each agent is selected as a peer by receiving agents; the routing graph is receiver-to-peer. Sparse routing does not force equal selected-peer counts or reciprocal edges."}


def summarize(manifest, initial_panel, revisions):
    tasks, count, peers = _validate(manifest, initial_panel, revisions)
    cases = []
    by_key = {}
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
                cases.append(row)
                by_key.setdefault((arm, index), []).append(row)
                history.append(row)
    sampled = _bootstrap_indices(tasks)
    points = {key: _statistics(rows) for key, rows in by_key.items()}
    draws = {key: [_statistics(rows, indices) for indices in sampled] for key, rows in by_key.items()}
    comparisons = []
    uncertain = ("accuracy", "family_balanced_accuracy", "coverage", "accuracy_among_answered",
                 "individual_accuracy", "family_balanced_individual_accuracy",
                 "cumulative_total_tokens", "cumulative_request_seconds")
    for arm in ARMS:
        for index in range(MAX_ROUNDS + 1):
            key = arm, index
            rows = by_key[key]
            comparisons.append({"arm": arm, "round": index, "num_agents": count,
                                "voting_rule": "plurality", "endpoint": f"fixed_round_{index}", **points[key],
                                "by_family": {family: _statistics([row for row in rows if row["family"] == family])
                                              for family in FAMILIES},
                                "by_prior_confirmation_stratum": {
                                    name: _statistics([row for row in rows if row["prior_confirmation_stratum"] == name])
                                    for name in ("moderate_structure", "hard_structure")},
                                "uncertainty": {metric: _interval(points[key][metric], [draw[metric] for draw in draws[key]])
                                                for metric in uncertain}})
    paired = []
    joint = []
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
    physical_cost = _cost(initial_panel + revisions)
    return {
        "schema_version": 1, "experiment_id": manifest["experiment_id"],
        "scope": "prespecified_architecture_development_replication_previously_inspected_questions",
        "architecture": {"num_agents": count, "peer_count": peers,
                         "agent_ids": list(range(count)),
                         "communication": "all_other_agents" if peers == count - 1 else "two_seeded_random_distinct_peers_per_agent_per_round"},
        "questions": len(tasks), "semantic_groups": len({task["group_id"] for task in tasks}),
        "comparison_rows": len(comparisons), "per_question_rows": len(cases),
        "comparisons": comparisons, "per_question": cases, "cross_arm_comparisons": paired,
        "source_generation_cost_including_initial_once": {"unique_calls": physical_cost["calls"],
                                                          **{key: value for key, value in physical_cost.items() if key != "calls"}},
        "initial_generation_cost": initial_cost, "joint_round_costs": joint,
        "routing": _routing(manifest, tasks, count, peers),
        "generation_protocol": copy.deepcopy(manifest.get("protocol_snapshot")),
        "execution_environment": copy.deepcopy(manifest.get("execution_environment")),
        "hardware_snapshot": copy.deepcopy(manifest.get("hardware_snapshot")),
        "bootstrap": {"method": "paired_family_stratified_whole_semantic_group_percentile_bootstrap",
                      "draws": BOOTSTRAP_DRAWS, "seed": BOOTSTRAP_SEED, "groups": 8, "clusters_per_family": 2,
                      "variants_resampled_together": True, "same_draws_across_rounds_and_arms": True,
                      "accuracy_estimand": "question-weighted within family, then equally weighted across four families",
                      "draw_question_counts_may_vary": True,
                      "inference": "Eight inspected development clusters; intervals do not establish an optimal architecture or generalization."},
        "selection_performed": False, "recommendation": None,
        "notes": [
            "These are fresh generations on the same twelve previously inspected development questions, not a new structural or numerical holdout.",
            "Both branches share the identical initial panel within this experiment. Their generation counts match, but prompt lengths and token budgets differ.",
            "The five-agent and sparse-peer runs share a seed namespace with nested agent IDs; they are related comparisons, not independent seed replicates.",
            "New requests can vary across executions despite shared seeds; cross-run initial panels are not assumed byte-identical without an explicit audit.",
            "Full rounds zero through three are collected. Only current-round exact-rational plurality and fixed-round controls are scored; no stopping-rule threshold or alternative voter is introduced.",
            "All voting is label-free; gold values enter only after a collective answer is fixed. Exact ties and empty eligible panels abstain and count incorrect.",
            "An odd panel size does not remove ties among multiple distinct mathematical answers.",
            "Shared initialization is counted once in physical cost and once within each logical branch trajectory.",
            "Request durations include loading but exclude health checks, prompt construction, calculator work, journaling and other process overhead; they are not total study wall time.",
            "Routing excludes self and samples distinct peers within a request; an earlier-round peer may reappear in a later round. Routing is independent of correctness and execution eligibility.",
            "No validation/test inference, threshold tuning, winner selection or offline subset analysis of prior responses is performed.",
        ],
    }


def _csv_bytes(rows):
    columns = list(dict.fromkeys(key for row in rows for key in row))
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: "" if value is None else json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
                         if isinstance(value, (dict, list, bool)) else value for key, value in row.items()})
    return output.getvalue().encode("utf-8")


def report_bytes(summary):
    return {"summary.json": (json.dumps(summary, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8"),
            "comparisons.csv": _csv_bytes(summary["comparisons"]),
            "per_question.csv": _csv_bytes(summary["per_question"])}
