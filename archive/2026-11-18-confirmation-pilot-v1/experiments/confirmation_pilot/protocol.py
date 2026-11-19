"""Frozen development confirmation; reference answers never enter requests."""

from collections import Counter
import copy
from pathlib import Path

from build_full_benchmark import generate_manifest as generate_benchmark
from build_format_followup_tasks import generate_manifest as generate_format_tasks, numeric_key
from calculator_protocol import SYSTEM
from multi_agent_protocol import agent_seed
from run_format_followup import canonical, strict_json
from experiments.communication_pilot.protocol import (
    ARMS, NUM_AGENTS, MAX_ROUNDS, REVISION_SYSTEM, STRICT_SCHEMA,
    PROTOCOL as SELECTED_GENERATION_PROTOCOL, build_messages, context_budget,
)
from experiments.offline_policies.protocol import PROTOCOL as OFFLINE_POLICY_PROTOCOL


ROOT = Path(__file__).resolve().parents[2]
EXPERIMENT_ID = "strict-schema-voting-stopping-confirmation-pilot-v1"
FAMILIES = ("reasoning", "evidence", "algebra", "units")
TASK_IDS = [f"full-v1-{family}-development-{index:02d}"
            for family in FAMILIES for index in (3, 4, 5)]
INITIAL_CALLS = len(TASK_IDS) * NUM_AGENTS
REVISION_CALLS = len(TASK_IDS) * NUM_AGENTS * MAX_ROUNDS * len(ARMS)
NEW_CALLS = INITIAL_CALLS + REVISION_CALLS
TASK_SOURCE_FILES = ("build_full_benchmark.py", "build_format_followup_tasks.py",
                     "config/full_benchmark.json", "config/format_followup_tasks.json")

GENERATION_PROTOCOL = copy.deepcopy(SELECTED_GENERATION_PROTOCOL)
GENERATION_PROTOCOL.update({
    "initial_system": SYSTEM,
    "round_zero": "fresh_ten_agent_panel_generated_once_then_shared_exactly_between_arms",
    "execution_mode": "all_initial_panels_then_question_major_synchronous_paired_revisions",
    "peer_order": "unchanged_selected_pilot_sha256_shuffle_using_original_pilot_identity",
    "study_role": "prespecified_development_confirmation_no_validation_test_or_policy_selection",
    "bootstrap_seed": 20261118,
})
FAILURE_POLICY = {
    "scope": "prospectively_frozen_before_confirmation_inference",
    "output_cap_invalid_json": "one_ineligible_answer_without_repair_or_retry",
    "admission": "done_reason_length_eval_count_exactly_1024_valid_wrapper_unsaturated_context_invalid_JSON_syntax",
    "other_schema_violations": "fatal_including_valid_JSON_that_violates_schema",
    "repair": False, "retry": False, "cap_change": False, "prompt_change": False,
}
POLICY_PROTOCOL = copy.deepcopy(OFFLINE_POLICY_PROTOCOL)
POLICY_PROTOCOL.update({
    "scope": "prospectively_prespecified_development_confirmation_no_policy_selection",
    "bootstrap_unit": "paired_family_stratified_whole_semantic_group_with_all_variants",
})
PROTOCOL = {
    "generation_protocol": GENERATION_PROTOCOL,
    "failure_policy": FAILURE_POLICY,
    "policy_protocol": POLICY_PROTOCOL,
    "task_policy": "twelve_unused_numerical_cases_eight_groups_four_previously_unseen_structures",
    "schedule": "all120_initial_calls_then_each_question_round1_to3_with_alternating_paired_arms",
    "full_trajectory_collection": True,
    "online_early_stopping": False,
    "policy_feedback_to_model": False,
    "planned_unique_calls": NEW_CALLS,
    "primary_control": "plurality_fixed_round_3",
    "selection": "none_no_winner_ranking_or_automatic_validation_test_progression",
}
EXPECTED_CONFIG = {
    "schema_version": 1, "experiment_id": EXPERIMENT_ID,
    "task_manifest": "full_benchmark.json", "task_ids": TASK_IDS,
    "selected_profile": "strict_schema", "arms": list(ARMS), "protocol": PROTOCOL,
}


def load_tasks():
    """Audit deterministic references, fixed IDs, and absence from inspected sets."""
    benchmark = strict_json((ROOT / "config/full_benchmark.json").read_text(encoding="utf-8"))
    if canonical(benchmark) != canonical(generate_benchmark()):
        raise ValueError("Full benchmark differs from independently audited deterministic generation")
    inspected = strict_json((ROOT / "config/format_followup_tasks.json").read_text(encoding="utf-8"))
    if canonical(inspected) != canonical(generate_format_tasks()):
        raise ValueError("Inspected format task manifest differs from deterministic generation")
    by_id = {task["id"]: task for task in benchmark["tasks"]}
    tasks = [copy.deepcopy(by_id[task_id]) for task_id in TASK_IDS]
    if (Counter(task["family"] for task in tasks) != Counter({family: 3 for family in FAMILIES})
            or any(task["split"] != "development" for task in tasks)
            or len({task["group_id"] for task in tasks}) != 8):
        raise ValueError("Confirmation requires twelve balanced development cases from eight groups")
    inspected_ids = {task["id"] for task in inspected["tasks"]}
    inspected_prompts = {task["prompt"] for task in inspected["tasks"]}
    inspected_numbers = {numeric_key(task) for task in inspected["tasks"]}
    if any(task["id"] in inspected_ids or task["prompt"] in inspected_prompts
           or numeric_key(task) in inspected_numbers for task in tasks):
        raise ValueError("Confirmation task reuses an inspected numerical case")
    metadata = cohort_metadata(tasks)
    known_groups = {task["group_id"] for task in inspected["tasks"]}
    if (len(set(metadata["new_structural_groups"]) & known_groups)
            or not set(metadata["seen_structural_groups"]).issubset(known_groups)):
        raise ValueError("Confirmation structural freshness differs from the frozen cohort labels")
    return tasks


def cohort_metadata(tasks):
    if [task["id"] for task in tasks] != TASK_IDS:
        raise ValueError("Task IDs/order differ from the twelve frozen development cases")
    task_cohorts = {task["id"]: ("seen_structure_new_numbers" if task["id"].endswith("-03")
                                 else "new_structure") for task in tasks}
    new_groups = sorted({task["group_id"] for task in tasks
                         if task_cohorts[task["id"]] == "new_structure"})
    seen_groups = sorted({task["group_id"] for task in tasks
                          if task_cohorts[task["id"]] == "seen_structure_new_numbers"})
    if len(new_groups) != 4 or len(seen_groups) != 4 or set(new_groups) & set(seen_groups):
        raise ValueError("Confirmation must contain four seen and four new structural groups")
    return {"questions": 12, "structural_groups": 8, "new_structural_groups": new_groups,
            "seen_structural_groups": seen_groups, "task_cohorts": task_cohorts,
            "cohort_questions": {"seen_structure_new_numbers": 4, "new_structure": 8},
            "freshness": "twelve_unrun_numerical_cases_eight_groups_only_four_new_structures",
            "difficulty_scope": "moderate_and_hard_development_cases_not_representative_easy_case_mix"}


def call_positions(tasks):
    cohort_metadata(tasks)
    positions = []

    def add(task, round_index, agent_id, arm):
        positions.append({"call_index": len(positions), "question_id": task["id"],
                          "family": task["family"], "split": task["split"],
                          "group_id": task["group_id"], "evaluation_set": "confirmation",
                          "round": round_index, "agent_id": agent_id, "arm": arm,
                          "profile": "strict_schema", "seed": agent_seed(task["id"], round_index, agent_id)})

    for task in tasks:
        for agent_id in range(NUM_AGENTS):
            add(task, 0, agent_id, "shared_initial")
    for question_index, task in enumerate(tasks):
        for round_index in range(1, MAX_ROUNDS + 1):
            for agent_id in range(NUM_AGENTS):
                arms = ARMS if (question_index + round_index + agent_id) % 2 == 0 else tuple(reversed(ARMS))
                for arm in arms:
                    add(task, round_index, agent_id, arm)
    independent = [row["seed"] for row in positions if row["round"] == 0 or row["arm"] == ARMS[0]]
    if len(independent) != len(set(independent)):
        raise ValueError("Seed collision across distinct question/round/agent positions")
    if len(positions) != NEW_CALLS:
        raise ValueError("Confirmation call budget differs from 840")
    return positions


def build_call(plan, index, answers):
    position = plan["call_positions"][index]
    task = next(task for task in plan["tasks_snapshot"] if task["id"] == position["question_id"])
    round_index = position["round"]
    if round_index == 0:
        messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": task["prompt"]}]
        context_budget(messages)
    else:
        previous = [record for record in answers if record["question_id"] == task["id"]
                    and record["round"] == round_index - 1
                    and record.get("arm") == ("shared_initial" if round_index == 1 else position["arm"])]
        messages = build_messages(task, round_index, position["agent_id"], position["arm"], previous)
    return {**copy.deepcopy(position), "format": copy.deepcopy(STRICT_SCHEMA), "messages": messages}
