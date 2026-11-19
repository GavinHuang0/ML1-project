"""Prespecified voting/stopping replay for the twelve-case confirmation.

Policies inspect completed prefixes only. References enter after decisions.
Intervals resample whole structural groups, carrying all numerical variants.
Prefix costs are counterfactual; full trajectories are deliberately collected.
"""

from collections import Counter
import copy
import csv
import io
import json
from fractions import Fraction
import math
import random

from experiments.offline_policies.protocol import (
    ARMS, BOOTSTRAP_DRAWS, BOOTSTRAP_SEED, FAMILIES, MAX_ROUND, NUM_AGENTS,
    STOPPING_RULES, VOTING_RULES,
    choose_stop, vote_prediction,
)
from experiments.communication_pilot.analysis import _diagnostics
from .protocol import EXPERIMENT_ID, TASK_IDS, POLICY_PROTOCOL as POLICY_DEFINITIONS


def _sum_known(values):
    values = list(values)
    return sum(values) if all(value is not None for value in values) else None


def _cost(records):
    tokens = {}
    for field, name in (("prompt_eval_count", "input_tokens"), ("eval_count", "output_tokens")):
        values = [record["raw"].get(field) for record in records]
        tokens[name] = sum(values) if all(type(value) is int and value >= 0 for value in values) else None
    durations = [record.get("elapsed_seconds") for record in records]
    if any(type(value) not in (int, float) or not math.isfinite(value) or value < 0 for value in durations):
        raise ValueError("Recorded model-request durations must be finite and nonnegative")
    return {"logical_calls": len(records), **tokens,
            "total_tokens": _sum_known(tokens.values()),
            "request_seconds": sum(durations)}


def _cohort(task):
    return "seen_structure_new_numbers" if task["id"].endswith("-03") else "new_structure"


def _validate(tasks, initial_panel, answers):
    if (not isinstance(tasks, list) or len(tasks) != 12
            or [task["id"] for task in tasks] != list(TASK_IDS)
            or len({task["group_id"] for task in tasks}) != 8
            or Counter(task["family"] for task in tasks) != Counter({family: 3 for family in FAMILIES})
            or any(task["split"] != "development" for task in tasks)):
        raise ValueError("Confirmation requires the frozen twelve unused development questions")
    groups = {}
    for task in tasks:
        groups.setdefault(task["group_id"], []).append(task)
    if (sorted(map(len, groups.values())) != [1] * 4 + [2] * 4
            or any(len({task["family"] for task in members}) != 1 for members in groups.values())
            or any(len({task["group_id"] for task in tasks if task["family"] == family}) != 2
                   for family in FAMILIES)):
        raise ValueError("Confirmation groups must preserve paired numerical variants within family")
    if len(initial_panel) != 120 or len(answers) != 720:
        raise ValueError("Complete confirmation needs 120 shared initial and 720 revision records")
    initial_positions = [(record.get("question_id"), record.get("round"), record.get("agent_id"))
                         for record in initial_panel]
    expected_initial = {(task["id"], 0, agent) for task in tasks for agent in range(NUM_AGENTS)}
    if len(set(initial_positions)) != 120 or set(initial_positions) != expected_initial:
        raise ValueError("Shared initial records must cover all unique question-agent positions")
    positions = [(record.get("arm"), record.get("question_id"), record.get("round"), record.get("agent_id"))
                 for record in answers]
    expected = {(arm, task["id"], index, agent) for arm in ARMS for task in tasks
                for index in range(1, MAX_ROUND + 1) for agent in range(NUM_AGENTS)}
    if len(set(positions)) != 720 or set(positions) != expected:
        raise ValueError("Revisions must cover every unique arm/question/round/agent position")


def _statistics(rows, indices=None):
    chosen = rows if indices is None else [rows[index] for index in indices]
    count = len(chosen)
    if not count:
        raise ValueError("Cannot summarize an empty policy cohort")
    correct = sum(row["correct"] for row in chosen)
    answered = sum(row["answered"] for row in chosen)
    return {
        "questions": count, "correct_questions": correct, "answered_questions": answered,
        "abstentions": count - answered, "incorrect_delivered_answers": answered - correct,
        "accuracy": correct / count, "coverage": answered / count,
        "family_balanced_accuracy": sum(
            sum(row["correct"] for row in chosen if row["family"] == family)
            / sum(row["family"] == family for row in chosen)
            for family in sorted({row["family"] for row in chosen}))
            / len({row["family"] for row in chosen}),
        "accuracy_among_answered": correct / answered if answered else None,
        "mean_stopping_round": sum(row["stopping_round"] for row in chosen) / count,
        "consumed_logical_calls": sum(row["consumed_logical_calls"] for row in chosen),
        "input_tokens": _sum_known(row["input_tokens"] for row in chosen),
        "output_tokens": _sum_known(row["output_tokens"] for row in chosen),
        "total_tokens": _sum_known(row["total_tokens"] for row in chosen),
        "request_seconds": sum(row["request_seconds"] for row in chosen),
        "stopped_before_maximum": sum(row["stopping_round"] < MAX_ROUND for row in chosen),
        "correct_early_stops": sum(row["early_stop"] and row["correct"] for row in chosen),
        "wrong_early_stops": sum(row["early_stop"] and row["answered"] and not row["correct"] for row in chosen),
        "missed_later_recoveries": sum(row["missed_later_recovery"] for row in chosen),
        "early_stop_missed_later_recoveries": sum(row["early_stop_missed_later_recovery"] for row in chosen),
        "correct_before_later_losses": sum(row["correct_before_later_loss"] for row in chosen),
        "early_stop_correct_later_losses": sum(row["early_stop_correct_later_loss"] for row in chosen),
    }


def _percentile(values, probability):
    values = sorted(values)
    position = (len(values) - 1) * probability
    lower, upper = math.floor(position), math.ceil(position)
    return values[lower] + (values[upper] - values[lower]) * (position - lower)


def _interval(point, values):
    valid = [value for value in values if value is not None]
    return {"estimate": point,
            "interval_95": [_percentile(valid, 0.025), _percentile(valid, 0.975)]
                if point is not None and valid else None,
            "valid_bootstrap_draws": len(valid) if point is not None else 0,
            "total_bootstrap_draws": BOOTSTRAP_DRAWS}


def _difference(policy, reference):
    def difference(key):
        return policy[key] - reference[key] if policy[key] is not None and reference[key] is not None else None
    tokens_saved = -difference("total_tokens") if difference("total_tokens") is not None else None
    time_saved = reference["request_seconds"] - policy["request_seconds"]
    return {
        "accuracy_difference": difference("accuracy"),
        "family_balanced_accuracy_difference": difference("family_balanced_accuracy"),
        "coverage_difference": difference("coverage"),
        "accuracy_among_answered_difference": difference("accuracy_among_answered"),
        "mean_stopping_round_difference": difference("mean_stopping_round"),
        "logical_calls_saved": reference["consumed_logical_calls"] - policy["consumed_logical_calls"],
        "tokens_saved": tokens_saved,
        "token_savings_fraction": tokens_saved / reference["total_tokens"]
            if tokens_saved is not None and reference["total_tokens"] else None,
        "request_seconds_saved": time_saved,
        "request_time_savings_fraction": time_saved / reference["request_seconds"]
            if reference["request_seconds"] else None,
    }


def _paired_contrast(cases, reference_cases, points, reference_points, draws, reference_draws):
    point = _difference(points, reference_points)
    distributions = {key: [] for key in point}
    for policy_draw, reference_draw in zip(draws, reference_draws):
        for key, value in _difference(policy_draw, reference_draw).items():
            distributions[key].append(value)
    return {
        "correct_question_gains": sum(row["correct"] and not previous["correct"]
                                      for row, previous in zip(cases, reference_cases)),
        "correct_question_losses": sum(not row["correct"] and previous["correct"]
                                       for row, previous in zip(cases, reference_cases)),
        "metrics": {key: _interval(value, distributions[key]) for key, value in point.items()},
    }


def _bootstrap_indices(tasks):
    """Resample groups within each family, keeping all variants together.

    Four family strata each have two structural clusters, one with one case
    and one with two. Draw sizes therefore vary; family-balanced accuracy is
    recomputed within every draw, never pooled as independent question trials.
    """
    families = {}
    for family in FAMILIES:
        families[family] = {}
        for index, task in enumerate(tasks):
            if task["family"] == family:
                families[family].setdefault(task["group_id"], []).append(index)
    randomizer = random.Random(BOOTSTRAP_SEED)
    draws = []
    for _ in range(BOOTSTRAP_DRAWS):
        indices = []
        for groups in families.values():
            group_ids = sorted(groups)
            for _ in group_ids:
                indices.extend(groups[randomizer.choice(group_ids)])
        draws.append(indices)
    return draws


def summarize(manifest, initial_panel, answers):
    """Return the complete prespecified grid, with no automatic policy selection."""
    tasks = manifest["tasks_snapshot"]
    _validate(tasks, initial_panel, answers)
    panels, predictions = {}, {}
    round_predictions, per_question, cases_by_key = [], [], {}
    for arm in ARMS:
        for task in tasks:
            key = arm, task["id"]
            panels[key] = []
            for round_index in range(MAX_ROUND + 1):
                selected = [record for record in (initial_panel if round_index == 0 else answers)
                            if record["question_id"] == task["id"] and record["round"] == round_index
                            and (round_index == 0 or record["arm"] == arm)]
                panels[key].append(sorted(selected, key=lambda record: record["agent_id"]))
            prefixes = [sum(panels[key][:round_index + 1], []) for round_index in range(MAX_ROUND + 1)]
            costs = [_cost(prefix) for prefix in prefixes]
            for voting_rule in VOTING_RULES:
                observed = [vote_prediction(panels[key][:round_index + 1], voting_rule)
                            for round_index in range(MAX_ROUND + 1)]
                predictions[(arm, task["id"], voting_rule)] = observed
                round_predictions.extend({"arm": arm, "question_id": task["id"],
                                          "family": task["family"], "group_id": task["group_id"], **prediction}
                                         for prediction in observed)
                for stopping_rule in STOPPING_RULES:
                    decision = choose_stop(observed, stopping_rule)
                    round_index = decision["stopping_round"]
                    prediction = decision["prediction"]
                    # Gold appears only after the fully label-free decision above.
                    predicted = prediction["answer"]
                    gold = Fraction(task["gold_fraction"])
                    answered = predicted is not None
                    row = {
                        "policy_id": f"{voting_rule}__{stopping_rule}", "arm": arm,
                        "voting_rule": voting_rule, "stopping_rule": stopping_rule,
                        "question_id": task["id"], "family": task["family"], "group_id": task["group_id"],
                        "cohort": _cohort(task),
                        "stopping_round": round_index, "stop_reason": decision["stop_reason"],
                        "stop_triggered": decision["triggered"],
                        "early_stop": decision["triggered"] and round_index < MAX_ROUND,
                        "answer": predicted, "answered": answered,
                        "correct": answered and Fraction(predicted) == gold,
                        "gold_fraction": str(gold),
                        "current_support": prediction["current_support"],
                        "current_eligible_agents": prediction["current_eligible_agents"],
                        "agreement_denominator": NUM_AGENTS,
                        "consumed_logical_calls": costs[round_index]["logical_calls"],
                        "revision_calls": round_index * NUM_AGENTS, "initial_calls": NUM_AGENTS,
                        **{name: value for name, value in costs[round_index].items() if name != "logical_calls"},
                        "vote_details": copy.deepcopy(prediction),
                    }
                    later_correct = [item["round"] for item in observed[round_index + 1:]
                                     if item["answer"] is not None and Fraction(item["answer"]) == gold]
                    later_wrong = [item["round"] for item in observed[round_index + 1:]
                                   if item["answer"] is None or Fraction(item["answer"]) != gold]
                    row.update(
                        later_correct_rounds=later_correct, later_incorrect_rounds=later_wrong,
                        missed_later_recovery=not row["correct"] and bool(later_correct),
                        early_stop_missed_later_recovery=row["early_stop"] and not row["correct"] and bool(later_correct),
                        correct_before_later_loss=row["correct"] and bool(later_wrong),
                        early_stop_correct_later_loss=row["early_stop"] and row["correct"] and bool(later_wrong),
                    )
                    per_question.append(row)
                    cases_by_key.setdefault((arm, voting_rule, stopping_rule), []).append(row)

    # The same paired draw is reused across all policies/arms; both numerical
    # variants travel together every time their structural group is sampled.
    sampled = _bootstrap_indices(tasks)
    points = {key: _statistics(rows) for key, rows in cases_by_key.items()}
    bootstrap = {key: [_statistics(rows, indices) for indices in sampled]
                 for key, rows in cases_by_key.items()}
    comparisons = []
    for arm in ARMS:
        for voting_rule in VOTING_RULES:
            for stopping_rule in STOPPING_RULES:
                key = arm, voting_rule, stopping_rule
                cases = cases_by_key[key]
                same_voter = arm, voting_rule, "fixed_round_3"
                primary = arm, "plurality", "fixed_round_3"
                row = {"policy_id": f"{voting_rule}__{stopping_rule}", "arm": arm,
                       "voting_rule": voting_rule, "stopping_rule": stopping_rule, **points[key],
                       "family_balanced_accuracy": sum(
                           _statistics([case for case in cases if case["family"] == family])["accuracy"]
                           for family in FAMILIES) / len(FAMILIES),
                       "stop_round_distribution": {str(index): sum(case["stopping_round"] == index for case in cases)
                                                   for index in range(MAX_ROUND + 1)},
                       "by_family": {family: _statistics([case for case in cases if case["family"] == family])
                                     for family in FAMILIES},
                       "by_group": {group: _statistics([case for case in cases if case["group_id"] == group])
                                    for group in sorted({case["group_id"] for case in cases})},
                       "by_cohort": {cohort: _statistics([case for case in cases if case["cohort"] == cohort])
                                     for cohort in ("seen_structure_new_numbers", "new_structure")},
                       "uncertainty": {metric: _interval(points[key][metric], [draw[metric] for draw in bootstrap[key]])
                                       for metric in ("accuracy", "family_balanced_accuracy", "coverage", "accuracy_among_answered",
                                                      "mean_stopping_round", "total_tokens", "request_seconds")},
                       "versus_same_voter_fixed_round_3": _paired_contrast(
                           cases, cases_by_key[same_voter], points[key], points[same_voter],
                           bootstrap[key], bootstrap[same_voter]),
                       "versus_primary_plurality_fixed_round_3": _paired_contrast(
                           cases, cases_by_key[primary], points[key], points[primary],
                           bootstrap[key], bootstrap[primary])}
                comparisons.append(row)

    cross_arm_comparisons, joint_policy_costs = [], []
    initial_cost = _cost(initial_panel)
    actual_source_cost = _cost(initial_panel + answers)
    for voting_rule in VOTING_RULES:
        for stopping_rule in STOPPING_RULES:
            communication = "communication", voting_rule, stopping_rule
            self_revision = "self_revision", voting_rule, stopping_rule
            contrast = _paired_contrast(cases_by_key[communication], cases_by_key[self_revision],
                                       points[communication], points[self_revision],
                                       bootstrap[communication], bootstrap[self_revision])
            cross_arm_comparisons.append({"policy_id": f"{voting_rule}__{stopping_rule}",
                                          "voting_rule": voting_rule, "stopping_rule": stopping_rule,
                                          "contrast": "communication_minus_self_revision",
                                          "cost_contrast_note": "Savings fields use self-revision as the reference; negative savings mean communication costs more.",
                                          **contrast})
            joint = {"policy_id": f"{voting_rule}__{stopping_rule}",
                     "voting_rule": voting_rule, "stopping_rule": stopping_rule,
                     "unique_calls": points[communication]["consumed_logical_calls"]
                        + points[self_revision]["consumed_logical_calls"] - initial_cost["logical_calls"]}
            for metric in ("input_tokens", "output_tokens", "total_tokens", "request_seconds"):
                left, right, shared = points[communication][metric], points[self_revision][metric], initial_cost[metric]
                joint[metric] = left + right - shared if all(value is not None for value in (left, right, shared)) else None
            joint["shared_initial_calls_counted_once"] = initial_cost["logical_calls"]
            joint_policy_costs.append(joint)

    return {
        "schema_version": 1, "experiment_id": EXPERIMENT_ID,
        "source_experiment_id": manifest.get("experiment_id"),
        "scope": "prespecified_development_confirmation_not_held_out_test",
        "additional_policy_model_calls": 0, "planned_unique_generation_calls": 840,
        "selection_performed": False, "recommendation": None,
        "questions": len(tasks), "semantic_groups": len({task["group_id"] for task in tasks}),
        "voting_rules": list(VOTING_RULES), "stopping_rules": list(STOPPING_RULES),
        "comparison_rows": len(comparisons), "per_question_rows": len(per_question),
        "round_prediction_rows": len(round_predictions),
        "policy_definitions": copy.deepcopy(POLICY_DEFINITIONS),
        "generation_protocol": copy.deepcopy(manifest.get("protocol_snapshot")),
        "execution_environment": copy.deepcopy(manifest.get("execution_environment")),
        "hardware_snapshot": copy.deepcopy(manifest.get("hardware_snapshot")),
        "selection": {"performed": False, "winner": None, "ranking": None,
                      "reason": "Development confirmation reports all frozen candidates; no automatic winner or validation/test selection."},
        "source_generation_cost_including_initial_once": {"unique_calls": actual_source_cost["logical_calls"],
                                                           **{key: value for key, value in actual_source_cost.items() if key != "logical_calls"}},
        "bootstrap": {"method": "paired_family_stratified_whole_semantic_group_percentile_bootstrap",
                      "draws": BOOTSTRAP_DRAWS, "seed": BOOTSTRAP_SEED, "groups": len({task["group_id"] for task in tasks}),
                      "clusters_per_family": 2,
                      "variants_resampled_together": True,
                      "accuracy_estimand": "question-weighted within each family, then equally weighted across four families",
                      "draw_question_counts_may_vary": True,
                      "same_draws_across_all_policies_and_arms": True,
                      "undefined_conditional_accuracy": "null; invalid bootstrap draws are excluded and their valid count is reported",
                      "inference": "Limited development confirmation; eight structural clusters, no multiplicity adjustment or automatic winner selection."},
        "cohorts": {cohort: {"questions": sum(_cohort(task) == cohort for task in tasks),
                              "groups": len({task["group_id"] for task in tasks if _cohort(task) == cohort}),
                              "task_ids": [task["id"] for task in tasks if _cohort(task) == cohort]}
                    for cohort in ("seen_structure_new_numbers", "new_structure")},
        "diagnostics": [{"arm": arm, "question_id": task["id"], "family": task["family"],
                         "group_id": task["group_id"], "round": index,
                         **_diagnostics(task, panels[(arm, task["id"])][index])}
                        for arm in ARMS for task in tasks for index in range(MAX_ROUND + 1)],
        "comparisons": comparisons, "per_question": per_question,
        "round_predictions": round_predictions,
        "cross_arm_comparisons": cross_arm_comparisons,
        "joint_policy_costs": joint_policy_costs,
        "notes": [
            "All three voters and both new stopping rules are compared in both arms; fixed rounds zero through three are retained as controls.",
            "Agreement thresholds are actual current support among the original ten agents, not weighted/history scores or a fraction of eligible answers.",
            "Whole completed rounds are charged, including initialization; no future correctness, reference answer, or future round enters a decision.",
            "Gold values are used only to score an already chosen terminal answer. Ties and no eligible score abstain and count incorrect.",
            "Accuracy among answered questions is separate from coverage and full-question accuracy; no answered cases yields null, not perfect accuracy.",
            "Costs are counterfactual saved-prefix accounting on already generated trajectories. Recorded request seconds are not newly measured deployment latency or total active process time.",
            "Both-arm joint costs subtract the shared initial panel once. Saved budget is not reinvested into extra model calls.",
            "The existing aggregate was not supplied to model prompts; this replay supports terminal aggregation and whole-question stopping only.",
            "Changing peer populations, prompts, feedback, confidence fields, or judge models requires new generation and cannot be inferred from this replay.",
            "Twelve unused numerical cases span eight structural clusters: four inspected structures and four new structures; validation/test stay untouched.",
            "Plurality at round three remains the primary development comparator; no response, calculator result, or score is repaired.",
            "Later-correction and later-loss fields are retrospective diagnostics, never operational stopping features.",
            "The confirmation environment records its pre-inference driver amendment; paired arms share the new frozen baseline. Earlier-driver costs are not a hardware-held-constant comparison.",
            "Correct-before-later-loss means at least one later round is wrong or abstains; missed-later-recovery means at least one later round is correct.",
        ],
    }


def _csv_bytes(rows):
    columns = list(dict.fromkeys(key for row in rows for key in row))
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: "" if value is None else json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
                         if isinstance(value, (dict, list, bool)) else value
                         for key, value in row.items()})
    return output.getvalue().encode("utf-8")


def report_bytes(summary):
    """Deterministic portable reports used both on completion and read-only audit."""
    return {
        "summary.json": (json.dumps(summary, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8"),
        "comparisons.csv": _csv_bytes(summary["comparisons"]),
        "per_question.csv": _csv_bytes(summary["per_question"]),
    }
