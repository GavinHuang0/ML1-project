"""Offline exact voting, cost calibration, and fixed-round experiment analysis.

References are used only here, after generation. No calculator or model calls
are needed to recompute any score from a saved run.
"""

from collections import Counter, defaultdict
from fractions import Fraction
import math
import random

from multi_agent_protocol import FROZEN_PROTOCOL

NUM_AGENTS = FROZEN_PROTOCOL["num_agents"]
MAX_ROUNDS = FROZEN_PROTOCOL["max_rounds"]
DEVELOPMENT_SPLITS = {"development", "calibration", "inspected_development"}
DELTA_GRID = tuple(FROZEN_PROTOCOL["delta_grid"])
OMEGA_GRID = tuple(FROZEN_PROTOCOL["omega_grid"])
PRIMARY_DELTA = FROZEN_PROTOCOL["primary_delta"]
PRIMARY_OMEGA = FROZEN_PROTOCOL["primary_omega"]
CONFIDENCE_REPLICATES = FROZEN_PROTOCOL["confidence_replicates"]
CONFIDENCE_LEVEL = FROZEN_PROTOCOL["confidence_level"]
BOOTSTRAP_SEED = FROZEN_PROTOCOL["bootstrap_seed"]


def _finite_number(value, name, positive=False):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or (value <= 0 if positive else value < 0)):
        raise ValueError(f"{name} must be {'positive' if positive else 'nonnegative'} and finite")
    return value


def _float(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (OverflowError, ValueError):
        return None


def _sum_known(values):
    values = list(values)
    return sum(values) if all(value is not None for value in values) else None


def _tokens(records, key):
    values = [record.get("raw", {}).get(key) for record in records]
    return sum(values) if all(type(value) is int and value >= 0 for value in values) else None


def _response_value(response, probability):
    value = response.get("computed_fraction")
    if response.get("calculator_success") is not True or not isinstance(value, str):
        return None
    try:
        value = Fraction(value)
    except (ValueError, ZeroDivisionError):
        return None
    return value if not probability or 0 <= value <= 1 else None


def _eligible(response, value):
    return (value is not None and response.get("eligible") is True
            and response.get("json_valid") is True
            and response.get("required_fields_valid") is True
            and response.get("calculator_success") is True)


def summarize_round(task, records, wall_seconds, history):
    """Score one complete synchronous snapshot; keep wall time distinct from call time."""
    _finite_number(wall_seconds, "round wall time")
    if (len(records) != NUM_AGENTS or any(type(r.get("agent_id")) is not int for r in records)
            or {r.get("agent_id") for r in records} != set(range(NUM_AGENTS))):
        raise ValueError("A round needs exactly ten unique agent records")
    round_index = records[0].get("round")
    if type(round_index) is not int or not 0 <= round_index <= MAX_ROUNDS:
        raise ValueError("Invalid round index")
    if any(r.get("round") != round_index or r.get("question_id") != task["id"] for r in records):
        raise ValueError("Round records have inconsistent identities")
    if (len(history) != round_index or any(
            h.get("round") != index or h.get("question_id") != task["id"]
            for index, h in enumerate(history))):
        raise ValueError("Round history must contain the completed preceding snapshots")
    gold = Fraction(task["gold_fraction"])
    values, eligible, numeric, correct = {}, {}, {}, {}
    for record in records:
        agent = str(record["agent_id"])
        response = record["response"]
        value = _response_value(response, task["probability"])
        values[agent] = value
        eligible[agent] = _eligible(response, value)
        numeric[agent] = value is not None and value == gold
        correct[agent] = eligible[agent] and numeric[agent]
    votes = Counter(value for agent, value in values.items() if eligible[agent])
    largest = max(votes.values(), default=0)
    winners = sorted(value for value, count in votes.items() if count == largest)
    winner = winners[0] if len(winners) == 1 else None
    abstained = winner is None
    aggregate_correct = winner == gold if winner is not None else False
    absolute_error = abs(winner - gold) if winner is not None else None
    input_tokens, output_tokens = _tokens(records, "prompt_eval_count"), _tokens(records, "eval_count")
    previous = history[-1] if history else None
    cumulative_input = _sum_known([previous["cumulative_input_tokens"] if previous else 0, input_tokens])
    cumulative_output = _sum_known([previous["cumulative_output_tokens"] if previous else 0, output_tokens])
    communication_input = (_sum_known([previous["communication_input_tokens"], input_tokens])
                           if previous else 0)
    communication_output = (_sum_known([previous["communication_output_tokens"], output_tokens])
                            if previous else 0)
    previous_correct = previous["aggregate_correct"] if previous else None
    return {
        "question_id": task["id"], "family": task["family"], "split": task["split"],
        "round": round_index, "aggregation_method": "exact-rational-plurality-abstain",
        "aggregate_answer": str(winner) if winner is not None else None,
        "aggregate_abstained": abstained,
        "abstention_reason": ("no_eligible_answers" if not votes else "tied_plurality") if abstained else None,
        "aggregate_correct": aggregate_correct,
        "aggregate_absolute_error_fraction": str(absolute_error) if absolute_error is not None else None,
        "aggregate_absolute_error": _float(absolute_error) if absolute_error is not None else None,
        "valid_agents": sum(eligible.values()), "invalid_agents": NUM_AGENTS - sum(eligible.values()),
        "distinct_answers": len(votes),
        "votes": {str(value): votes[value] for value in sorted(votes)},
        "plurality_count": largest, "tied_winners": [str(value) for value in winners] if len(winners) > 1 else [],
        "agent_numeric_correct": numeric, "agent_correct": correct,
        "beneficial_revision": (not previous_correct and aggregate_correct) if previous else None,
        "harmful_revision": (previous_correct and not aggregate_correct) if previous else None,
        "agent_beneficial_revisions": sum(not previous["agent_correct"][agent] and value
                                         for agent, value in correct.items()) if previous else None,
        "agent_harmful_revisions": sum(previous["agent_correct"][agent] and not value
                                      for agent, value in correct.items()) if previous else None,
        "round_input_tokens": input_tokens, "round_output_tokens": output_tokens,
        "round_total_tokens": _sum_known([input_tokens, output_tokens]),
        "cumulative_input_tokens": cumulative_input, "cumulative_output_tokens": cumulative_output,
        "cumulative_total_tokens": _sum_known([cumulative_input, cumulative_output]),
        "communication_input_tokens": communication_input, "communication_output_tokens": communication_output,
        "communication_total_tokens": _sum_known([communication_input, communication_output]),
        "round_wall_seconds": wall_seconds,
        "cumulative_wall_seconds": sum(h["round_wall_seconds"] for h in history) + wall_seconds,
        "communication_wall_seconds": sum(h["round_wall_seconds"] for h in history[1:])
                                      + (wall_seconds if previous else 0),
        "token_measurements_complete": input_tokens is not None and output_tokens is not None,
        "length_stops": sum(r.get("raw", {}).get("done_reason") == "length" for r in records),
    }


def _mean(values):
    values = list(values)
    return sum(values) / len(values) if values and all(v is not None for v in values) else None


def _balanced(rows, key):
    families = defaultdict(list)
    for row in rows:
        families[row["family"]].append(row[key])
    return _mean(_mean(values) for values in families.values())


def build_calibration(rounds):
    """Use first communication rounds from development/calibration questions only."""
    selected = [r for r in rounds if r["round"] == 1 and r["split"] in DEVELOPMENT_SPLITS]
    if not selected:
        return None
    token_reference = _balanced(selected, "round_total_tokens")
    wall_reference = _balanced(selected, "round_wall_seconds")
    if token_reference is None or token_reference <= 0 or wall_reference is None or wall_reference <= 0:
        return None
    return {
        "schema_version": 1, "token_reference": token_reference, "wall_reference": wall_reference,
        "method": "family-balanced-mean-first-communication-round",
        "source_question_ids": sorted(r["question_id"] for r in selected),
        "source_splits": sorted({r["split"] for r in selected}),
        "source_families": sorted({r["family"] for r in selected}),
    }


def _validate_calibration(calibration):
    if not isinstance(calibration, dict):
        raise ValueError("Calibration must be an object")
    _finite_number(calibration.get("token_reference"), "token reference", positive=True)
    _finite_number(calibration.get("wall_reference"), "wall reference", positive=True)
    source_splits = calibration.get("source_splits")
    if (not isinstance(source_splits, list) or not source_splits
            or any(split not in DEVELOPMENT_SPLITS for split in source_splits)):
        raise ValueError("Calibration references must come from development/calibration data")


def validate_calibration(calibration):
    """Validate frozen references before a runner performs inference."""
    _validate_calibration(calibration)
    return calibration


def _round_metrics(rows, calibration):
    families = defaultdict(list)
    for row in rows:
        families[row["family"]].append(row)
    answer_errors = [r["aggregate_absolute_error"] for r in rows if not r["aggregate_abstained"]]
    result = {
        "round": rows[0]["round"], "questions": len(rows),
        "accuracy": _mean(r["aggregate_correct"] for r in rows),
        "family_balanced_accuracy": _balanced(rows, "aggregate_correct"),
        "loss": 1 - _balanced(rows, "aggregate_correct"),
        "abstention_rate": _mean(r["aggregate_abstained"] for r in rows),
        "invalid_agent_rate": _mean(r["invalid_agents"] / NUM_AGENTS for r in rows),
        "agent_accuracy": _mean(sum(r["agent_correct"].values()) / NUM_AGENTS for r in rows),
        "mean_absolute_error_when_answered": _mean(answer_errors),
        "answered_error_count": len(answer_errors),
        "beneficial_revision_rate": _mean(r["beneficial_revision"] for r in rows),
        "harmful_revision_rate": _mean(r["harmful_revision"] for r in rows),
        "family_balanced_beneficial_revision_rate": _balanced(rows, "beneficial_revision"),
        "family_balanced_harmful_revision_rate": _balanced(rows, "harmful_revision"),
        "families": {family: {
            "questions": len(items), "accuracy": _mean(r["aggregate_correct"] for r in items),
            "abstention_rate": _mean(r["aggregate_abstained"] for r in items),
        } for family, items in sorted(families.items())},
        "token_measurements_complete": all(r["token_measurements_complete"] for r in rows),
        "length_stops": sum(r["length_stops"] for r in rows),
    }
    for key in ("round_input_tokens", "round_output_tokens", "round_total_tokens",
                "cumulative_input_tokens", "cumulative_output_tokens", "cumulative_total_tokens",
                "communication_input_tokens", "communication_output_tokens", "communication_total_tokens",
                "round_wall_seconds", "cumulative_wall_seconds", "communication_wall_seconds"):
        result["family_balanced_" + key] = _balanced(rows, key)
    result["normalized_communication_tokens"] = (
        result["family_balanced_communication_total_tokens"] / calibration["token_reference"]
        if calibration is not None and result["family_balanced_communication_total_tokens"] is not None else None)
    result["normalized_communication_wall"] = (
        result["family_balanced_communication_wall_seconds"] / calibration["wall_reference"]
        if calibration is not None else None)
    return result


def _weighted_cost(curve, omega):
    tokens, wall = curve["normalized_communication_tokens"], curve["normalized_communication_wall"]
    if (omega != 0 and tokens is None) or (omega != 1 and wall is None):
        return None
    return (omega * tokens if omega != 0 else 0) + ((1 - omega) * wall if omega != 1 else 0)


def _objective(curve, delta, omega):
    if delta == 0:
        return curve["loss"]
    cost = _weighted_cost(curve, omega)
    return curve["loss"] + delta * cost if cost is not None else None


def _select(curves, delta, omega):
    values = [{"round": c["round"], "objective": _objective(c, delta, omega)} for c in curves]
    selected = min(values, key=lambda v: (v["objective"], v["round"])) if all(
        v["objective"] is not None for v in values) else None
    return {"delta": delta, "omega": omega, "selected_round": selected["round"] if selected else None,
            "objective": selected["objective"] if selected else None, "candidates": values}


def _percentile(values, probability):
    ordered = sorted(values)
    index = (len(ordered) - 1) * probability
    lower, upper = math.floor(index), math.ceil(index)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)


def _bootstrap(rows, curves, split):
    """Resample whole question trajectories within families, pairing all rounds."""
    families = defaultdict(dict)
    for row in rows:
        questions = families[row["family"]]
        questions.setdefault(row["question_id"], [None] * (MAX_ROUNDS + 1))[row["round"]] = int(
            row["aggregate_correct"])
    grouped = [[questions[q] for q in sorted(questions)] for _, questions in sorted(families.items())]
    counts = {family: len(questions) for family, questions in sorted(families.items())}
    question_count, family_count = sum(counts.values()), len(counts)
    distributions = [{key: [] for key in ("accuracy", "family_balanced_accuracy",
                        "accuracy_change_from_round0", "family_balanced_accuracy_change_from_round0")}
                     for _ in range(MAX_ROUNDS + 1)]
    generator = random.Random(BOOTSTRAP_SEED)
    for _ in range(CONFIDENCE_REPLICATES):
        ordinary, balanced = [0.0] * (MAX_ROUNDS + 1), [0.0] * (MAX_ROUNDS + 1)
        for trajectories in grouped:
            sampled = [trajectories[generator.randrange(len(trajectories))] for _ in trajectories]
            correct = [sum(question[index] for question in sampled) for index in range(MAX_ROUNDS + 1)]
            for index, count in enumerate(correct):
                ordinary[index] += count / question_count
                balanced[index] += count / len(trajectories) / family_count
        for index, distribution in enumerate(distributions):
            distribution["accuracy"].append(ordinary[index])
            distribution["family_balanced_accuracy"].append(balanced[index])
            distribution["accuracy_change_from_round0"].append(ordinary[index] - ordinary[0])
            distribution["family_balanced_accuracy_change_from_round0"].append(balanced[index] - balanced[0])
    tail = (1 - CONFIDENCE_LEVEL) / 2
    for curve, distribution in zip(curves, distributions):
        curve["accuracy_change_from_round0"] = curve["accuracy"] - curves[0]["accuracy"]
        curve["family_balanced_accuracy_change_from_round0"] = (
            curve["family_balanced_accuracy"] - curves[0]["family_balanced_accuracy"])
        curve["confidence_intervals"] = {
            metric: {"estimate": curve[metric], "lower": _percentile(samples, tail),
                     "upper": _percentile(samples, 1 - tail)}
            for metric, samples in distribution.items()}
    notes = [
        "Resamples whole questions within each family; all rounds share the same draws for paired changes.",
        "Intervals condition on this benchmark and assume questions are independent within families.",
        "Small samples and shared problem templates can make percentile intervals unreliable.",
    ]
    singleton = [family for family, count in counts.items() if count == 1]
    if singleton:
        notes.append("Families with one question have degenerate bootstrap variability; these intervals do not establish precision.")
    if split in DEVELOPMENT_SPLITS:
        notes.append("Development intervals are descriptive and do not estimate held-out generalization.")
    return {"method": "stratified-paired-question-percentile-bootstrap", "unit": "question",
            "confidence_level": CONFIDENCE_LEVEL, "replicates": CONFIDENCE_REPLICATES,
            "seed": BOOTSTRAP_SEED, "questions": question_count, "family_question_counts": counts,
            "singleton_families": singleton, "notes": notes}


def _pareto_rounds(curves):
    """Return nondominated rounds for prediction loss, tokens, and measured time."""
    points = [(curve["loss"], curve["family_balanced_communication_total_tokens"],
               curve["family_balanced_communication_wall_seconds"]) for curve in curves]
    if any(value is None for point in points for value in point):
        return None
    return [curve["round"] for index, curve in enumerate(curves) if not any(
        all(a <= b for a, b in zip(other, points[index]))
        and any(a < b for a, b in zip(other, points[index]))
        for other_index, other in enumerate(points) if other_index != index)]


def _break_even(curves):
    result = []
    for omega in OMEGA_GRID:
        for index, earlier in enumerate(curves):
            for later in curves[index + 1:]:
                cost_a, cost_b = _weighted_cost(earlier, omega), _weighted_cost(later, omega)
                additional = cost_b - cost_a if cost_a is not None and cost_b is not None else None
                improvement = earlier["loss"] - later["loss"]
                delta = improvement / additional if additional is not None and additional > 0 else None
                if additional is None:
                    status = "unknown_cost"
                elif additional <= 0:
                    status = "no_positive_additional_cost"
                elif improvement < 0:
                    status = "later_round_never_preferred_for_nonnegative_penalty"
                else:
                    status = "pairwise_crossover"
                result.append({"round_a": earlier["round"], "round_b": later["round"], "omega": omega,
                               "loss_improvement": improvement, "additional_normalized_cost": additional,
                               "break_even_delta": delta, "status": status})
    return result


def summarize_experiment(tasks, records, rounds, calibration=None):
    """Analyze a complete trajectory; select stopping rounds using validation only."""
    if not tasks or len({task["id"] for task in tasks}) != len(tasks):
        raise ValueError("Tasks must be nonempty and have unique IDs")
    expected_rounds = {(task["id"], r) for task in tasks for r in range(MAX_ROUNDS + 1)}
    expected_records = {(q, r, a) for q, r in expected_rounds for a in range(NUM_AGENTS)}
    actual_records = [(r.get("question_id"), r.get("round"), r.get("agent_id")) for r in records]
    actual_rounds = [(r.get("question_id"), r.get("round")) for r in rounds]
    if len(actual_records) != len(expected_records) or set(actual_records) != expected_records:
        raise ValueError("Cannot analyze incomplete, duplicate, or unexpected agent records")
    if len(actual_rounds) != len(expected_rounds) or set(actual_rounds) != expected_rounds:
        raise ValueError("Cannot analyze incomplete, duplicate, or unexpected round summaries")
    record_groups, saved_rounds = defaultdict(list), {}
    for record in records:
        record_groups[(record["question_id"], record["round"])].append(record)
    for summary in rounds:
        saved_rounds[(summary["question_id"], summary["round"])] = summary
    # Recompute voting and cumulative costs; saved summary scores are not trusted.
    recomputed = []
    for task in tasks:
        history = []
        for index in range(MAX_ROUNDS + 1):
            key = (task["id"], index)
            summary = summarize_round(task, record_groups[key], saved_rounds[key]["round_wall_seconds"], history)
            if any(saved_rounds[key].get(name) != value for name, value in summary.items()):
                raise ValueError("Saved round summary does not match its agent records")
            recomputed.append(summary)
            history.append(summary)
    if calibration is None:
        calibration = build_calibration(recomputed)
        calibration_origin = "derived_from_development" if calibration else "unavailable"
    else:
        _validate_calibration(calibration)
        calibration = dict(calibration)
        calibration_origin = "external_frozen_reference"
    split_groups = defaultdict(list)
    for row in recomputed:
        split_groups[row["split"]].append(row)
    splits, selected_rounds = {}, {}
    for split, split_rows in sorted(split_groups.items()):
        curves = [_round_metrics([r for r in split_rows if r["round"] == index], calibration)
                  for index in range(MAX_ROUNDS + 1)]
        for curve in curves:
            curve["primary_objective"] = _objective(curve, PRIMARY_DELTA, PRIMARY_OMEGA)
        splits[split] = {"questions": len(split_rows) // (MAX_ROUNDS + 1), "rounds": curves,
                         "uncertainty": _bootstrap(split_rows, curves, split),
                         "pareto_rounds": _pareto_rounds(curves), "break_even": _break_even(curves)}
        if split == "validation":
            selected_rounds[split] = {
                "primary": _select(curves, PRIMARY_DELTA, PRIMARY_OMEGA),
                "sensitivity": [_select(curves, delta, omega) for delta in DELTA_GRID for omega in OMEGA_GRID],
            }
    return {
        "schema_version": 1, "questions": len(tasks), "agent_records": len(records),
        "round_summaries": len(rounds), "calibration": calibration,
        "calibration_origin": calibration_origin, "splits": splits, "selected_rounds": selected_rounds,
        "penalties": {"primary_delta": PRIMARY_DELTA, "primary_omega": PRIMARY_OMEGA,
                      "delta_grid": list(DELTA_GRID), "omega_grid": list(OMEGA_GRID),
                      "objective_tie_break": "smallest_round"},
        "notes": [
            "Exact rational plurality; tied plurality and no eligible answers abstain and count incorrect.",
            "Required string fields, successful calculation, and probability range gate eligibility.",
            "Numerical correctness uses exact rational equality; explanation mathematics is not graded.",
            "Costs and prediction loss use equal family weights; round zero is reported but excluded from penalties.",
            "Round selection uses validation only, never development or held-out test outcomes.",
            "Missing token counts remain unknown; no token-dependent optimum is claimed from incomplete costs.",
        ],
    }
