"""Offline, paired development analysis for the strict-schema Stage-B pilot.

The analysis scores delivered expressions and voting, not explanation quality or
hidden reasoning. Initial calls are counted once in execution cost and shown in
both hypothetical trajectories. Call durations exclude human pause intervals.
"""

from collections import Counter, defaultdict
from fractions import Fraction
import math
import random

from multi_agent_analysis import summarize_round


ARMS = ("communication", "self_revision")
FAMILIES = ("reasoning", "evidence", "algebra", "units")
BOOTSTRAP_REPLICATES = 2000
BOOTSTRAP_SEED = 20261117


def _sum_known(values):
    values = list(values)
    return sum(values) if all(value is not None for value in values) else None


def _tokens(records, field):
    values = [record["raw"].get(field) for record in records]
    return sum(values) if all(type(value) is int and value >= 0 for value in values) else None


def _cost(records):
    inputs = _tokens(records, "prompt_eval_count")
    outputs = _tokens(records, "eval_count")
    durations = [record["elapsed_seconds"] for record in records]
    if any(type(value) not in (int, float) or not math.isfinite(value) or value < 0 for value in durations):
        raise ValueError("Call elapsed seconds must be finite and nonnegative")
    return {"calls": len(records), "input_tokens": inputs, "output_tokens": outputs,
            "total_tokens": _sum_known((inputs, outputs)), "call_elapsed_seconds": sum(durations)}


def _diagnostics(task, records):
    gold = Fraction(task["gold_fraction"])
    counts = Counter()
    error_messages = Counter()
    for record in records:
        response = record["response"]
        error = response.get("calculator_error")
        if not response.get("json_valid"):
            category = "invalid_json"
        elif not response.get("required_fields_valid"):
            category = "invalid_fields"
        elif error is not None:
            error_messages[error] += 1
            if error == "Division by zero":
                category = "undefined_division_by_zero"
            elif "limit" in error.lower() or "exceeds" in error.lower():
                category = "calculator_resource_limit"
            else:
                category = "unsupported_or_malformed_expression"
        elif response.get("probability_in_range") is False:
            category = "probability_out_of_range"
        elif response.get("eligible"):
            category = "eligible_correct" if Fraction(response["computed_fraction"]) == gold else "eligible_wrong"
        else:
            category = "other_ineligible"
        counts[category] += 1
    categories = ("invalid_json", "invalid_fields", "unsupported_or_malformed_expression",
                  "undefined_division_by_zero", "calculator_resource_limit", "probability_out_of_range",
                  "eligible_correct", "eligible_wrong", "other_ineligible")
    return {"counts": {key: counts[key] for key in categories},
            "calculator_error_messages": dict(sorted(error_messages.items())),
            "explanation_over_limit": sum(not record["response"].get("within_explanation_bound") for record in records),
            "length_stops": sum(record["raw"].get("done_reason") == "length" for record in records)}


def _metrics(rows):
    if not rows:
        raise ValueError("Cannot summarize empty round")
    count = len(rows)
    families = defaultdict(list)
    for row in rows:
        families[row["family"]].append(row)
    family_accuracy = {family: sum(row["aggregate_correct"] for row in selected) / len(selected)
                       for family, selected in families.items()}
    keys = list(rows[0]["diagnostics"]["counts"])
    return {"questions": count,
            "collective_correct": sum(row["aggregate_correct"] for row in rows),
            "collective_accuracy": sum(row["aggregate_correct"] for row in rows) / count,
            "family_balanced_accuracy": sum(family_accuracy.values()) / len(family_accuracy),
            "eligible_outputs": sum(row["valid_agents"] for row in rows),
            "eligibility_rate": sum(row["valid_agents"] for row in rows) / (10 * count),
            "exact_agent_correct": sum(sum(row["agent_correct"].values()) for row in rows),
            "individual_accuracy": sum(sum(row["agent_correct"].values()) for row in rows) / (10 * count),
            "collective_abstentions": sum(row["aggregate_abstained"] for row in rows),
            "collective_abstention_rate": sum(row["aggregate_abstained"] for row in rows) / count,
            "beneficial_collective_revisions": sum(row["beneficial_revision"] is True for row in rows),
            "harmful_collective_revisions": sum(row["harmful_revision"] is True for row in rows),
            "beneficial_agent_revisions": sum(row["agent_beneficial_revisions"] or 0 for row in rows),
            "harmful_agent_revisions": sum(row["agent_harmful_revisions"] or 0 for row in rows),
            "unanimous_eligible_wrong_panels": sum(row["unanimous_eligible_wrong"] for row in rows),
            "ten_agent_wrong_consensus_panels": sum(row["ten_agent_wrong_consensus"] for row in rows),
            "panels_with_correct_available_but_collective_wrong": sum(row["correct_available_but_collective_wrong"] for row in rows),
            "initial_zero_correct_panels_now_correct": sum(row["initial_correct_agents"] == 0 and row["aggregate_correct"] for row in rows),
            "diagnostic_counts": {key: sum(row["diagnostics"]["counts"][key] for row in rows) for key in keys},
            "round_input_tokens": _sum_known(row["round_input_tokens"] for row in rows),
            "round_output_tokens": _sum_known(row["round_output_tokens"] for row in rows),
            "round_total_tokens": _sum_known(row["round_total_tokens"] for row in rows),
            "cumulative_total_tokens": _sum_known(row["cumulative_total_tokens"] for row in rows),
            "revision_total_tokens": _sum_known(row["communication_total_tokens"] for row in rows),
            "round_call_elapsed_seconds": sum(row["round_wall_seconds"] for row in rows),
            "cumulative_call_elapsed_seconds": sum(row["cumulative_wall_seconds"] for row in rows),
            "revision_call_elapsed_seconds": sum(row["communication_wall_seconds"] for row in rows)}


def _paired(tasks, rows):
    """One paired, family-stratified group resample shared by every round."""
    by_position = {(arm, row["question_id"], row["round"]): row
                   for arm in ARMS for row in rows[arm]}
    families = {family: [task["id"] for task in tasks if task["family"] == family] for family in FAMILIES}
    rng = random.Random(BOOTSTRAP_SEED)
    draws = [[rng.choice(ids) for ids in families.values() for _ in ids]
             for _ in range(BOOTSTRAP_REPLICATES)]
    result = []
    for round_index in range(4):
        differences = {}
        gains = losses = 0
        for task in tasks:
            qid = task["id"]
            communication = by_position[("communication", qid, round_index)]
            revision = by_position[("self_revision", qid, round_index)]
            gains += communication["aggregate_correct"] and not revision["aggregate_correct"]
            losses += not communication["aggregate_correct"] and revision["aggregate_correct"]
            differences[qid] = {
                "collective_accuracy": int(communication["aggregate_correct"]) - int(revision["aggregate_correct"]),
                "individual_accuracy": (sum(communication["agent_correct"].values()) - sum(revision["agent_correct"].values())) / 10,
                "eligibility_rate": (communication["valid_agents"] - revision["valid_agents"]) / 10,
                "cumulative_tokens_per_question": (communication["cumulative_total_tokens"] - revision["cumulative_total_tokens"])
                    if communication["cumulative_total_tokens"] is not None and revision["cumulative_total_tokens"] is not None else None,
                "cumulative_call_seconds_per_question": communication["cumulative_wall_seconds"] - revision["cumulative_wall_seconds"],
            }
        metrics = {}
        for key in next(iter(differences.values())):
            if any(value[key] is None for value in differences.values()):
                metrics[key] = {"difference": None, "interval_95": None}
                continue
            values = sorted(sum(differences[qid][key] for qid in draw) / len(draw) for draw in draws)
            metrics[key] = {"difference": sum(value[key] for value in differences.values()) / len(tasks),
                            "interval_95": [values[49], values[1949]]}
        result.append({"round": round_index, "communication_question_wins": gains,
                       "self_revision_question_wins": losses, "metrics": metrics})
    return {"contrast": "communication_minus_self_revision", "by_round": result,
            "method": "paired_family_stratified_whole_semantic_group_percentile_bootstrap",
            "replicates": BOOTSTRAP_REPLICATES, "seed": BOOTSTRAP_SEED,
            "groups": len({task["group_id"] for task in tasks}),
            "note": "Eight development groups; intervals are exploratory, and degenerate intervals do not establish equivalence."}


def summarize(manifest, initial_panel, answers):
    """Recompute complete Stage-B curves without model calls or evidence writes."""
    tasks = manifest["tasks_snapshot"]
    if (len(tasks) != 8 or len(initial_panel) != 80 or len(answers) != 480
            or len({task["id"] for task in tasks}) != 8
            or len({task["group_id"] for task in tasks}) != 8
            or Counter(task["family"] for task in tasks) != Counter({family: 2 for family in FAMILIES})
            or any(task["split"] != "development" for task in tasks)):
        raise ValueError("Complete analysis requires eight development groups, 80 shared initial answers and 480 revision answers")
    positions = [(record.get("arm"), record.get("question_id"), record.get("round"), record.get("agent_id")) for record in answers]
    expected = {(arm, task["id"], round_index, agent_id) for arm in ARMS for task in tasks
                for round_index in (1, 2, 3) for agent_id in range(10)}
    if len(set(positions)) != len(answers) or set(positions) != expected:
        raise ValueError("Revision answers do not cover the complete unique branch/round positions")
    rows, arms = {}, {}
    for arm in ARMS:
        rows[arm] = []
        for task in tasks:
            history = []
            initial_correct = None
            for round_index in range(4):
                selected = [record for record in (initial_panel if round_index == 0 else answers)
                            if record["question_id"] == task["id"] and record["round"] == round_index
                            and (round_index == 0 or record["arm"] == arm)]
                row = summarize_round(task, selected, sum(record["elapsed_seconds"] for record in selected), history)
                if round_index == 0:
                    initial_correct = sum(row["agent_correct"].values())
                row.update(arm=arm, initial_correct_agents=initial_correct,
                           initial_any_correct=initial_correct > 0,
                           correct_available_but_collective_wrong=any(row["agent_correct"].values()) and not row["aggregate_correct"],
                           unanimous_eligible_wrong=row["valid_agents"] >= 2 and row["distinct_answers"] == 1 and not row["aggregate_correct"],
                           ten_agent_wrong_consensus=row["valid_agents"] == 10 and row["distinct_answers"] == 1 and not row["aggregate_correct"],
                           diagnostics=_diagnostics(task, selected))
                history.append(row)
                rows[arm].append(row)
        arm_answers = [record for record in answers if record["arm"] == arm]
        by_round = []
        for round_index in range(4):
            selected = [row for row in rows[arm] if row["round"] == round_index]
            by_round.append({"round": round_index, **_metrics(selected),
                             "by_family": {family: _metrics([row for row in selected if row["family"] == family])
                                           for family in FAMILIES}})
        arms[arm] = {"new_generation_cost": _cost(arm_answers), "by_round": by_round,
                     "question_rounds": rows[arm]}
    paired = _paired(tasks, rows)
    return {"schema_version": 1, "experiment_id": manifest["experiment_id"],
            "selected_profile": "strict_schema", "questions": 8, "semantic_groups": 8,
            "primary_comparison_round": 3,
            "primary_comparison": paired["by_round"][3],
            "shared_initial_calls": 80, "new_calls": 480,
            "initial_generation_cost": _cost(initial_panel),
            "new_generation_cost": _cost(answers),
            "execution_cost_including_initial_once": _cost(initial_panel + answers),
            "arms": arms, "paired_comparison": paired,
            "notes": ["Exploratory development pilot; no validation/test evaluation or globally optimal round is selected.",
                      "Round 3 is the prespecified primary communication-minus-self-revision comparison; all other rounds are descriptive.",
                      "Both branch trajectories include exactly the same initial evidence and historical call cost; execution cost counts it once.",
                      "Reported call seconds are sums of measured model-request durations, excluding human pauses and intervening calls of the other branch; they are not end-to-end study wall time.",
                      "Branches match generation counts, not input-token or time budgets. Missing token measurements remain unknown.",
                      "Division by zero is an undefined model expression, not evidence of incorrect calculator arithmetic.",
                      "Eligible wrong expressions measure delivered mathematical errors; explanations and hidden reasoning are not graded."]}
