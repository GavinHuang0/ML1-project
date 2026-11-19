"""Paired group-level analysis for the full all-to-all/self-revision study.

This layer leaves the original versioned runner and scorer unchanged. It uses
their complete-trajectory validation, then replaces question bootstrap
intervals with resampling of whole related-problem groups within each family.
"""

from collections import defaultdict
import math
import random

from multi_agent_analysis import summarize_experiment
from multi_agent_protocol import FROZEN_PROTOCOL, validate_tasks


ANALYSIS_ID = "full-study-group-bootstrap-v1"
NUM_AGENTS = FROZEN_PROTOCOL["num_agents"]
ROUNDS = range(FROZEN_PROTOCOL["max_rounds"] + 1)
REPLICATES = FROZEN_PROTOCOL["confidence_replicates"]
CONFIDENCE = FROZEN_PROTOCOL["confidence_level"]
SEED = FROZEN_PROTOCOL["bootstrap_seed"]
ACCURACY_METRICS = ("accuracy", "family_balanced_accuracy")
CURVE_METRICS = (*ACCURACY_METRICS, "accuracy_change_from_round0",
                 "family_balanced_accuracy_change_from_round0")
COMPARISON_METRICS = ("accuracy_difference", "family_balanced_accuracy_difference")


def _sum_known(values):
    values = list(values)
    return sum(values) if all(value is not None for value in values) else None


def _mean(values):
    values = list(values)
    return sum(values) / len(values) if values and all(value is not None for value in values) else None


def _ratio(numerator, denominator):
    return numerator / denominator if numerator is not None and denominator is not None and denominator > 0 else None


def _tokens(records, key):
    values = [r.get("raw", {}).get(key) for r in records]
    return sum(values) if all(type(value) is int and value >= 0 for value in values) else None


def _duration(records, key):
    values = [r.get("raw", {}).get(key) for r in records]
    return (sum(values) / 1e9 if all(type(value) in (int, float) and math.isfinite(value)
                                   and value >= 0 for value in values) else None)


def _elapsed(records):
    values = [r.get("elapsed_seconds") for r in records]
    return (sum(values) if all(type(value) in (int, float) and math.isfinite(value)
                              and value >= 0 for value in values) else None)


def _percentile(values, probability):
    values = sorted(values)
    position = (len(values) - 1) * probability
    lower, upper = math.floor(position), math.ceil(position)
    return values[lower] + (values[upper] - values[lower]) * (position - lower)


def _interval(point, values):
    tail = (1 - CONFIDENCE) / 2
    return {"estimate": point, "lower": _percentile(values, tail),
            "upper": _percentile(values, 1 - tail)}


def _cluster_key(task):
    return ("group", task["group_id"]) if "group_id" in task else ("question", task["id"])


def _validate_groups(tasks):
    locations = {}
    for task in tasks:
        key = _cluster_key(task)
        location = (task["split"], task["family"])
        if key in locations and locations[key] != location:
            raise ValueError("A related-problem group cannot cross splits or families")
        locations[key] = location


def _shared_initial(primary_records, control_records):
    def initial(records):
        return {(r["question_id"], r["agent_id"]): r for r in records if r["round"] == 0}
    primary, control = initial(primary_records), initial(control_records)
    if set(primary) != set(control):
        raise ValueError("Control and primary must share every initial agent record")
    for key in primary:
        if any(primary[key].get(field) != control[key].get(field)
               for field in ("raw", "response", "seed", "messages")):
            raise ValueError("Control must reuse the exact primary round-zero raw responses, prompts, and seeds")


def _group_metadata(tasks):
    grouped = defaultdict(lambda: defaultdict(list))
    for task in tasks:
        grouped[task["family"]][_cluster_key(task)].append(task["id"])
    family_groups = [[sorted(questions) for _, questions in sorted(groups.items())]
                     for _, groups in sorted(grouped.items())]
    counts = {family: {"groups": len(groups), "questions": sum(len(qs) for qs in groups.values())}
              for family, groups in sorted(grouped.items())}
    notes = [
        "Resample whole related-problem groups within each family; every draw is shared across rounds, arms, and initial controls.",
        "Point estimates remain question-weighted within each family, with equal weights across families for balanced accuracy.",
        "These intervals describe variation across problem groups, not across generation seeds or independent LLM models.",
        "Fixed-seed reruns reproduce trajectories and are not independent sampling replicates.",
    ]
    singletons = [family for family, values in counts.items() if values["groups"] == 1]
    if singletons:
        notes.append("Families with one group have degenerate bootstrap variability; narrow intervals do not establish precision.")
    if any(task["split"] in {"development", "calibration", "inspected_development"} for task in tasks):
        notes.append("Development intervals are descriptive, not held-out generalization estimates.")
    return family_groups, {
        "method": "family-stratified-paired-whole-group-percentile-bootstrap", "unit": "group_id",
        "analysis_id": ANALYSIS_ID, "confidence_level": CONFIDENCE, "replicates": REPLICATES,
        "seed": SEED, "questions": len(tasks), "groups": sum(len(groups) for groups in grouped.values()),
        "family_counts": counts, "singleton_families": singletons,
        "fallback_question_groups": sum("group_id" not in task for task in tasks), "notes": notes,
    }


def _round_lookup(rounds):
    return {(r["question_id"], r["round"]): r for r in rounds}


def _sample_statistics(sampled_families, trajectories):
    total_questions = sum(len(questions) for questions in sampled_families)
    by_family = [[sum(trajectories[q][r] for q in questions) for r in ROUNDS]
                 for questions in sampled_families]
    ordinary = [sum(counts[r] for counts in by_family) / total_questions for r in ROUNDS]
    balanced = [_mean(counts[r] / len(questions) for questions, counts in zip(sampled_families, by_family))
                for r in ROUNDS]
    return ordinary, balanced


def _point_statistics(tasks, values):
    families = defaultdict(list)
    for task in tasks:
        families[task["family"]].append(values[task["id"]])
    return {"accuracy": _mean(value for group in families.values() for value in group),
            "family_balanced_accuracy": _mean(_mean(group) for group in families.values())}


def _group_bootstrap(tasks, arm_rounds, arm_curves, comparisons, initial_baselines):
    family_groups, metadata = _group_metadata(tasks)
    trajectories = {}
    for arm, rounds in arm_rounds.items():
        lookup = _round_lookup(rounds)
        trajectories[arm] = {task["id"]: [int(lookup[(task["id"], r)]["aggregate_correct"]) for r in ROUNDS]
                             for task in tasks}
    primary_lookup = _round_lookup(arm_rounds["all_to_all"])
    initial_values = {
        "single_agent_0": {t["id"]: int(primary_lookup[(t["id"], 0)]["agent_correct"]["0"]) for t in tasks},
        "oracle_any_initial_eligible_correct": {
            t["id"]: int(any(primary_lookup[(t["id"], 0)]["agent_correct"].values())) for t in tasks},
    }
    distributions = {arm: [{metric: [] for metric in CURVE_METRICS} for _ in ROUNDS] for arm in arm_rounds}
    comparison_distributions = [{metric: [] for metric in COMPARISON_METRICS} for _ in ROUNDS]
    initial_distributions = {name: {metric: [] for metric in ACCURACY_METRICS} for name in initial_values}
    baseline_difference = {metric: [] for metric in COMPARISON_METRICS}
    generator = random.Random(SEED)
    for _ in range(REPLICATES):
        sampled = [[q for _ in groups for q in groups[generator.randrange(len(groups))]] for groups in family_groups]
        sampled_statistics = {}
        for arm, values in trajectories.items():
            ordinary, balanced = _sample_statistics(sampled, values)
            sampled_statistics[arm] = ordinary, balanced
            for r in ROUNDS:
                distribution = distributions[arm][r]
                distribution["accuracy"].append(ordinary[r])
                distribution["family_balanced_accuracy"].append(balanced[r])
                distribution["accuracy_change_from_round0"].append(ordinary[r] - ordinary[0])
                distribution["family_balanced_accuracy_change_from_round0"].append(balanced[r] - balanced[0])
        if "self_revision" in trajectories:
            for r in ROUNDS:
                for metric, p, c in zip(COMPARISON_METRICS, sampled_statistics["all_to_all"],
                                        sampled_statistics["self_revision"]):
                    comparison_distributions[r][metric].append(p[r] - c[r])
        for name, values in initial_values.items():
            repeated = {q: [value] * len(ROUNDS) for q, value in values.items()}
            ordinary, balanced = _sample_statistics(sampled, repeated)
            initial_distributions[name]["accuracy"].append(ordinary[0])
            initial_distributions[name]["family_balanced_accuracy"].append(balanced[0])
            if name == "single_agent_0":
                baseline_difference["accuracy_difference"].append(sampled_statistics["all_to_all"][0][0] - ordinary[0])
                baseline_difference["family_balanced_accuracy_difference"].append(
                    sampled_statistics["all_to_all"][1][0] - balanced[0])
    for arm, curves in arm_curves.items():
        for r, curve in enumerate(curves):
            curve["accuracy_change_from_round0"] = curve["accuracy"] - curves[0]["accuracy"]
            curve["family_balanced_accuracy_change_from_round0"] = (
                curve["family_balanced_accuracy"] - curves[0]["family_balanced_accuracy"])
            curve["confidence_intervals"] = {
                metric: _interval(curve[metric], distributions[arm][r][metric]) for metric in CURVE_METRICS}
    for r, comparison in enumerate(comparisons):
        comparison["confidence_intervals"] = {
            metric: _interval(comparison[metric], comparison_distributions[r][metric]) for metric in COMPARISON_METRICS}
    for name in initial_values:
        initial_baselines[name].update(_point_statistics(tasks, initial_values[name]))
        initial_baselines[name]["confidence_intervals"] = {
            metric: _interval(initial_baselines[name][metric], initial_distributions[name][metric])
            for metric in ACCURACY_METRICS}
    panel = initial_baselines["ten_independent_agents_round0"]
    panel["confidence_intervals"] = {
        metric: dict(arm_curves["all_to_all"][0]["confidence_intervals"][metric]) for metric in ACCURACY_METRICS}
    difference = initial_baselines["panel_minus_single_agent_0"]
    for difference_metric, metric in zip(COMPARISON_METRICS, ACCURACY_METRICS):
        difference[difference_metric] = panel[metric] - initial_baselines["single_agent_0"][metric]
    difference["confidence_intervals"] = {
        metric: _interval(difference[metric], baseline_difference[metric]) for metric in COMPARISON_METRICS}
    return metadata


def _round_diagnostics(records, rounds, shared_initial=False):
    logical_input, logical_output = _tokens(records, "prompt_eval_count"), _tokens(records, "eval_count")
    load, model_duration = _duration(records, "load_duration"), _duration(records, "total_duration")
    wall = sum(row["round_wall_seconds"] for row in rounds)
    eligible = sum(row["valid_agents"] for row in rounds)
    strict = sum(sum(row["agent_correct"].values()) for row in rounds)
    numeric = sum(sum(row["agent_numeric_correct"].values()) for row in rounds)
    size = len(records)
    flags = {name: sum(record["response"].get(name) is True for record in records) / size
             for name in ("json_valid", "required_fields_valid", "calculator_attempted", "calculator_success")}
    return {
        "strict_agent_accuracy": strict / size, "numeric_only_agent_accuracy": numeric / size,
        "numeric_correct_but_ineligible_rate": (numeric - strict) / size,
        "valid_vote_fraction": eligible / size,
        "mean_distinct_eligible_answers": _mean(row["distinct_answers"] for row in rounds),
        "mean_unique_answer_fraction_among_eligible": _mean(
            row["distinct_answers"] / row["valid_agents"] for row in rounds if row["valid_agents"]),
        "mean_plurality_fraction_of_panel": _mean(row["plurality_count"] / NUM_AGENTS for row in rounds),
        "mean_plurality_fraction_among_eligible": _mean(
            row["plurality_count"] / row["valid_agents"] for row in rounds if row["valid_agents"]),
        "json_valid_rate": flags["json_valid"], "required_fields_valid_rate": flags["required_fields_valid"],
        "output_contract_failure_rate": 1 - flags["required_fields_valid"],
        "calculator_attempt_rate": flags["calculator_attempted"],
        "calculator_success_rate": flags["calculator_success"],
        "calculator_execution_failure_rate": flags["calculator_attempted"] - flags["calculator_success"],
        "logical_agent_calls": size, "new_model_calls": 0 if shared_initial else size,
        "shared_initial_records": size if shared_initial else 0,
        "round_input_tokens": logical_input, "round_output_tokens": logical_output,
        "new_execution_input_tokens": 0 if shared_initial else logical_input,
        "new_execution_output_tokens": 0 if shared_initial else logical_output,
        "round_wall_seconds": wall, "new_execution_round_wall_seconds": 0 if shared_initial else wall,
        "model_call_elapsed_seconds": _elapsed(records),
        "model_reported_total_seconds": model_duration, "model_reported_load_seconds": load,
        "load_fraction_of_model_duration": _ratio(load, model_duration),
        "load_fraction_of_round_wall": _ratio(load, wall),
        "new_execution_load_seconds": 0 if shared_initial else load,
        "notes": (["Round-zero evidence is reused; logical standalone-arm costs are shown, and no new calls are charged."]
                  if shared_initial else []),
    }


def _initial_baselines(tasks, records, rounds, primary_curve):
    initial = [r for r in records if r["round"] == 0 and r["agent_id"] == 0]
    lookup = _round_lookup(rounds)
    numeric = {t["id"]: int(lookup[(t["id"], 0)]["agent_numeric_correct"]["0"]) for t in tasks}
    return {
        "single_agent_0": {
            "agent_id": 0, "predeclared": True, "numeric_only_accuracy": _point_statistics(tasks, numeric)["accuracy"],
            "calls": len(initial), "input_tokens": _tokens(initial, "prompt_eval_count"),
            "output_tokens": _tokens(initial, "eval_count"), "model_call_elapsed_seconds": _elapsed(initial),
            "note": "Uses agent zero from the exact shared initial panel, with identical context, scoring, and seeds.",
        },
        "ten_independent_agents_round0": {
            "accuracy": primary_curve["accuracy"], "family_balanced_accuracy": primary_curve["family_balanced_accuracy"],
            "calls": len(tasks) * NUM_AGENTS,
            "note": "Independent generations from one model; plurality aggregates eligible exact calculator results.",
        },
        "oracle_any_initial_eligible_correct": {
            "diagnostic_only": True,
            "note": "Uses references to ask whether any initial eligible answer was correct; it is not a deployable aggregation rule.",
        },
        "panel_minus_single_agent_0": {},
    }


def _comparison(primary, control):
    cost_keys = ("family_balanced_cumulative_total_tokens", "family_balanced_communication_total_tokens",
                 "family_balanced_cumulative_wall_seconds", "family_balanced_communication_wall_seconds")
    return {
        "round": primary["round"], "accuracy_difference": primary["accuracy"] - control["accuracy"],
        "family_balanced_accuracy_difference": primary["family_balanced_accuracy"] - control["family_balanced_accuracy"],
        "cost_differences": {key: primary[key] - control[key]
                             if primary[key] is not None and control[key] is not None else None for key in cost_keys},
        "direction": "all_to_all_minus_self_revision",
        "generation_calls_matched": True, "token_budgets_matched": False,
    }


def _remove_unavailable_control_calibration(control):
    """A control cannot supply its own references when primary calibration failed."""
    control["calibration"] = None
    control["calibration_origin"] = "unavailable_primary_reference"
    for split in control["splits"].values():
        for curve in split["rounds"]:
            curve["normalized_communication_tokens"] = None
            curve["normalized_communication_wall"] = None
            curve["primary_objective"] = None
        for crossover in split["break_even"]:
            crossover.update(additional_normalized_cost=None, break_even_delta=None, status="unknown_cost")


def summarize_study(tasks, primary_records, primary_rounds, control_records=None, control_rounds=None,
                    calibration=None, selected_round=None):
    """Summarize complete primary/control trajectories with shared group uncertainty.

    Inputs may include one partition or the complete study. Only the primary
    validation result can choose a round. A test-only partition must receive the
    already selected primary round explicitly.
    """
    validate_tasks(tasks)
    _validate_groups(tasks)
    if (control_records is None) != (control_rounds is None):
        raise ValueError("Control records and round summaries must be supplied together")
    if selected_round is not None and (type(selected_round) is not int or selected_round not in ROUNDS):
        raise ValueError("selected_round must be a fixed integer from zero through three")
    primary = summarize_experiment(tasks, primary_records, primary_rounds, calibration)
    validation = primary["selected_rounds"].get("validation", {}).get("primary", {}).get("selected_round")
    if selected_round is not None and validation is not None and selected_round != validation:
        raise ValueError("Explicit selected round disagrees with the primary validation selection")
    chosen = selected_round if selected_round is not None else validation
    if "test" in primary["splits"] and chosen is None:
        raise ValueError("Test evaluation requires a round frozen on primary validation")
    control = None
    if control_records is not None:
        _shared_initial(primary_records, control_records)
        control = summarize_experiment(tasks, control_records, control_rounds, primary["calibration"])
        if primary["calibration"] is None:
            _remove_unavailable_control_calibration(control)
        control["selected_rounds"] = {}
        control["notes"].append("Self-revision is evaluated at primary-selected stopping rounds; it is not independently tuned.")
    comparisons, baselines, structures = {}, {}, {}
    for split, primary_split in primary["splits"].items():
        split_tasks = [task for task in tasks if task["split"] == split]
        ids = {task["id"] for task in split_tasks}
        p_records = [r for r in primary_records if r["question_id"] in ids]
        p_rounds = [r for r in primary_rounds if r["question_id"] in ids]
        arm_rounds, arm_curves = {"all_to_all": p_rounds}, {"all_to_all": primary_split["rounds"]}
        comparisons[split] = []
        if control is not None:
            c_records = [r for r in control_records if r["question_id"] in ids]
            c_rounds = [r for r in control_rounds if r["question_id"] in ids]
            control_split = control["splits"][split]
            arm_rounds["self_revision"], arm_curves["self_revision"] = c_rounds, control_split["rounds"]
            comparisons[split] = [_comparison(p, c) for p, c in zip(primary_split["rounds"], control_split["rounds"])]
        baselines[split] = _initial_baselines(split_tasks, p_records, p_rounds, primary_split["rounds"][0])
        metadata = _group_bootstrap(split_tasks, arm_rounds, arm_curves, comparisons[split], baselines[split])
        structures[split] = metadata
        primary_split["uncertainty"] = metadata
        if control is not None:
            control["splits"][split]["uncertainty"] = dict(metadata)
        for r in ROUNDS:
            primary_split["rounds"][r]["diagnostics"] = _round_diagnostics(
                [row for row in p_records if row["round"] == r], [row for row in p_rounds if row["round"] == r])
            if control is not None:
                control["splits"][split]["rounds"][r]["diagnostics"] = _round_diagnostics(
                    [row for row in c_records if row["round"] == r], [row for row in c_rounds if row["round"] == r],
                    shared_initial=r == 0)
    unique_records = list(primary_records) + ([r for r in control_records if r["round"] > 0] if control else [])
    unique_rounds = list(primary_rounds) + ([r for r in control_rounds if r["round"] > 0] if control else [])
    result = {
        "schema_version": 1, "analysis_id": ANALYSIS_ID, "questions": len(tasks),
        "primary": primary, "control": control, "selected_round": chosen,
        "round_selection_source": "explicit_primary_validation_selection" if selected_round is not None else
                                  ("primary_validation" if validation is not None else "not_selected"),
        "calibration": primary["calibration"], "comparisons": comparisons,
        "initial_baselines": baselines, "group_structure": structures,
        "joint_execution_budget": {
            "unique_model_calls": len(unique_records), "input_tokens": _tokens(unique_records, "prompt_eval_count"),
            "output_tokens": _tokens(unique_records, "eval_count"),
            "measured_round_wall_seconds": sum(row["round_wall_seconds"] for row in unique_rounds),
            "model_reported_load_seconds": _duration(unique_records, "load_duration"),
            "model_reported_total_seconds": _duration(unique_records, "total_duration"),
            "shared_initial_model_calls": len(tasks) * NUM_AGENTS if control is not None else 0,
            "note": "Shared round zero is charged once; outer orchestration and final analysis time are excluded.",
        },
        "notes": [
            "All-to-all is compared with self-revision at equal generation-call counts, sharing identical initial responses.",
            "Self-revision has shorter prompts; this is not a token-matched comparison.",
            "Only primary validation selects stopping rounds; held-out evaluation uses that fixed round for both arms.",
            "Uncertainty resamples whole groups within families, paired across questions, rounds, and arms; reruns are not seed replicates.",
            "Initial agent zero is predeclared; oracle-any-correct is a reference-assisted diagnostic only.",
            "Missing token or load-duration measurements stay unknown, never zero.",
        ],
    }
    if "test" in primary["splits"]:
        result["heldout_evaluation"] = {
            "selected_round": chosen, "primary": primary["splits"]["test"]["rounds"][chosen],
            "control": control["splits"]["test"]["rounds"][chosen] if control else None,
            "comparison": comparisons["test"][chosen] if control else None,
        }
    return result
