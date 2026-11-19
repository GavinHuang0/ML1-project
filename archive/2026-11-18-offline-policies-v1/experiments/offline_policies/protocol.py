"""Fixed post-hoc comparison definitions; reference answers are never features."""

from collections import Counter
import copy
from fractions import Fraction


EXPERIMENT_ID = "offline-voting-stopping-comparison-v1"
ARMS = ("communication", "self_revision")
FAMILIES = ("reasoning", "evidence", "algebra", "units")
NUM_AGENTS = 10
MAX_ROUND = 3
VOTING_RULES = ("plurality", "initial_anchored", "agent_history")
NEW_STOPPING_RULES = ("high_agreement_8", "stable_majority_6")
STOPPING_RULES = tuple(f"fixed_round_{index}" for index in range(4)) + NEW_STOPPING_RULES
BOOTSTRAP_DRAWS = 2000
BOOTSTRAP_SEED = 20261118
PROTOCOL = {
    "scope": "post_hoc_exploratory_saved_development_traces_no_policy_selection",
    "arms": list(ARMS), "num_agents": NUM_AGENTS, "max_round": MAX_ROUND,
    "voting_rules": list(VOTING_RULES), "stopping_rules": list(STOPPING_RULES),
    "new_stopping_rules": list(NEW_STOPPING_RULES),
    "voting_definitions": {
        "plurality": "Unique largest eligible exact-rational current-round vote count; ties abstain.",
        "initial_anchored": "Round-zero votes plus current-round votes; round zero is counted once when r=0; tied exact scores abstain.",
        "agent_history": "Each agent contributes total weight one, equally divided over its DISTINCT eligible exact-rational answers observed from round zero through r; no eligible history contributes zero; tied exact scores abstain.",
    },
    "stopping_definitions": {
        "high_agreement_8": "First completed round 0..3 where the selected voter has a unique answer and at least eight of the ORIGINAL ten current agents support that answer; otherwise use the selected voter at round three.",
        "stable_majority_6": "First completed round r>=1 where the selected voter has the same unique answer at r-1 and r and at least six of the ORIGINAL ten agents support that answer in EACH current panel; otherwise use the selected voter at round three.",
        "fixed_rounds": "Controls stop after the specified full round 0, 1, 2, or 3 and use the selected voter at that round.",
    },
    "agreement_denominator": "original_ten_agents_not_eligible_count_or_weighted_scores",
    "answer_policy": "unique_exact_score_winner_else_abstain",
    "abstention_counts_incorrect": True,
    "score_arithmetic": "exact_Fraction_weights_and_rational_answers",
    "reference_policy": "reference_used_only_after_terminal_decision_not_in_voting_or_stopping",
    "history_policy": "observed_prefix_only_no_future_round_features",
    "cost_policy": "charge_every_call_in_each_completed_round_through_stop_including_round_zero",
    "counterfactual_scope": "terminal_aggregation_and_whole_question_stopping_only_no_feedback_or_changed_generation",
    "cost_interpretation": "saved_prefix_token_counts_and_request_durations_not_realized_new_inference_or_latency_benchmarks",
    "bootstrap_draws": BOOTSTRAP_DRAWS, "bootstrap_seed": BOOTSTRAP_SEED,
    "bootstrap_unit": "paired_family_stratified_whole_semantic_group",
    "selection": "none_no_winner_ranking_or_validation_claim",
    "additional_model_calls": 0,
}
EXPECTED_CONFIG = {
    "schema_version": 1, "experiment_id": EXPERIMENT_ID,
    "source_run": "results/communication-pilot/windows-v2",
    "protocol": PROTOCOL,
}


def _eligible_value(record):
    response = record.get("response")
    if not isinstance(response, dict):
        raise ValueError("Panel records require an evaluated response")
    if not (response.get("eligible") is True and response.get("json_valid") is True
            and response.get("required_fields_valid") is True
            and response.get("calculator_success") is True
            and response.get("probability_in_range") is not False):
        return None
    value = response.get("computed_fraction")
    if not isinstance(value, str):
        raise ValueError("Eligible responses require an exact fraction string")
    try:
        return Fraction(value)
    except (ValueError, ZeroDivisionError) as exc:
        raise ValueError("Eligible answer is not an exact rational value") from exc


def _panel_values(panel, round_index):
    if not isinstance(panel, list) or len(panel) != NUM_AGENTS:
        raise ValueError("Each completed panel needs exactly ten agents")
    values = {}
    for record in panel:
        agent = record.get("agent_id")
        if (type(agent) is not int or not 0 <= agent < NUM_AGENTS or agent in values
                or ("round" in record and record["round"] != round_index)):
            raise ValueError("Panel agent/round identities are inconsistent")
        values[agent] = _eligible_value(record)
    return values


def vote_prediction(prefix, voting_rule):
    """Predict from observed panels only, ignoring gold/correctness metadata.

    ``prefix`` is a list of completed panels, each containing ten records with
    ``agent_id`` and evaluated ``response``. Optional round identities must match.
    Exact scores are serialized as rational strings rather than rounded floats.
    """
    if voting_rule not in VOTING_RULES:
        raise ValueError("Unknown frozen voting rule")
    if not isinstance(prefix, list) or not 1 <= len(prefix) <= MAX_ROUND + 1:
        raise ValueError("Voting needs an observed prefix of one through four panels")
    panels = [_panel_values(panel, index) for index, panel in enumerate(prefix)]
    current = Counter(value for value in panels[-1].values() if value is not None)
    scores = Counter()
    if voting_rule == "plurality":
        scores.update(current)
    elif voting_rule == "initial_anchored":
        scores.update(value for value in panels[0].values() if value is not None)
        if len(panels) > 1:
            scores.update(current)
    else:
        for agent in range(NUM_AGENTS):
            distinct = {panel[agent] for panel in panels if panel[agent] is not None}
            for value in distinct:
                scores[value] += Fraction(1, len(distinct))
    largest = max(scores.values(), default=0)
    winners = sorted(value for value, weight in scores.items() if weight == largest)
    answer = winners[0] if len(winners) == 1 else None
    return {
        "round": len(prefix) - 1, "voting_rule": voting_rule,
        "answer": str(answer) if answer is not None else None,
        "abstained": answer is None,
        "abstention_reason": ("no_eligible_scores" if not scores else "tied_scores") if answer is None else None,
        "scores": {str(value): str(Fraction(scores[value])) for value in sorted(scores)},
        "total_score_weight": str(sum((Fraction(score) for score in scores.values()), Fraction(0))),
        "tied_winners": [str(value) for value in winners] if len(winners) > 1 else [],
        "current_votes": {str(value): current[value] for value in sorted(current)},
        "current_eligible_agents": sum(current.values()),
        "current_support": current.get(answer, 0) if answer is not None else 0,
        "agreement_denominator": NUM_AGENTS,
    }


def choose_stop(predictions, stopping_rule):
    """Use only observable predictions up to the first admitted stop.

    Adaptive policies fall back to round three. Gold labels, future correctness,
    and token/time savings do not enter the decision. A complete round is paid.
    """
    if stopping_rule not in STOPPING_RULES:
        raise ValueError("Unknown frozen stopping rule")
    if (not isinstance(predictions, list) or len(predictions) != MAX_ROUND + 1
            or any(item.get("round") != index for index, item in enumerate(predictions))):
        raise ValueError("Stopping comparison requires predictions for rounds zero through three")
    if stopping_rule.startswith("fixed_round_"):
        index = int(stopping_rule.rsplit("_", 1)[1])
        return {"stopping_round": index, "stop_reason": "fixed_round_control",
                "triggered": False, "prediction": copy.deepcopy(predictions[index])}
    for index, prediction in enumerate(predictions):
        if prediction["answer"] is None:
            continue
        if stopping_rule == "high_agreement_8" and prediction["current_support"] >= 8:
            return {"stopping_round": index, "stop_reason": "eight_of_original_ten",
                    "triggered": True, "prediction": copy.deepcopy(prediction)}
        if stopping_rule == "stable_majority_6" and index >= 1:
            previous = predictions[index - 1]
            if (prediction["answer"] == previous["answer"]
                    and prediction["current_support"] >= 6 and previous["current_support"] >= 6):
                return {"stopping_round": index, "stop_reason": "same_six_vote_majority_in_two_completed_rounds",
                        "triggered": True, "prediction": copy.deepcopy(prediction)}
    return {"stopping_round": MAX_ROUND, "stop_reason": "maximum_round_fallback",
            "triggered": False, "prediction": copy.deepcopy(predictions[-1])}
