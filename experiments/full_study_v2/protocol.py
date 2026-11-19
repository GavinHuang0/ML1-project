"""Frozen five-agent full-study design; references never enter model requests."""

from collections import Counter
import copy
import hashlib
import json
from pathlib import Path
import random

from build_full_benchmark import generate_manifest, validate_manifest
from calculator_protocol import SYSTEM
from experiments.communication_pilot.protocol import (
    ARMS, MAX_ROUNDS, REVISION_SYSTEM, STRICT_SCHEMA, shared_response, context_budget,
    PROTOCOL as SELECTED_GENERATION_PROTOCOL,
)
from experiments.confirmation_pilot.protocol import FAILURE_POLICY as SELECTED_FAILURE_POLICY
from run_format_followup import canonical, strict_json


ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "config/full_study_v2.json"
STUDY_ID = "ml1-five-agent-full-study-v2"
EXPERIMENT_ID = STUDY_ID
PHASES = ("development", "validation", "test")
FAMILIES = ("reasoning", "evidence", "algebra", "units")
NUM_AGENTS = 5
AGENT_IDS = tuple(range(NUM_AGENTS))
SEED_NAMESPACE = "full-study-v2"
TASK_SOURCE_FILES = ("build_full_benchmark.py", "config/full_benchmark.json")
PHASE_QUESTIONS = {"development": 20, "validation": 40, "test": 40}
PHASE_GROUPS = {"development": 12, "validation": 20, "test": 20}

GENERATION_PROTOCOL = copy.deepcopy(SELECTED_GENERATION_PROTOCOL)
GENERATION_PROTOCOL.update({
    "num_agents": NUM_AGENTS, "peer_count": 4, "initial_system": SYSTEM,
    "round_zero": "fresh_five_agent_panel_generated_once_then_shared_exactly_between_arms",
    "execution_mode": "phase_local_all_initial_panels_then_question_major_synchronous_paired_revisions",
    "seed_policy": "sha256_full_study_v2_question_round_agent_generation_identical_between_arms",
    "peer_order": "all_four_other_agents_in_question_round_recipient_seeded_random_order",
    "study_role": "development_calibration_then_validation_selection_then_locked_test_evaluation",
    "bootstrap_seed": 20261118,
})
FAILURE_POLICY = copy.deepcopy(SELECTED_FAILURE_POLICY)
FAILURE_POLICY["scope"] = "prospectively_frozen_before_full_study_v2_inference"
SELECTION_OBJECTIVE = {
    "condition": "communication", "candidate_rounds": [0, 1, 2, 3],
    "formula": "1-family_balanced_accuracy + 0.02*(0.5*normalized_revision_tokens + 0.5*normalized_revision_request_seconds)",
    "cost_weight": 0.02, "token_weight": 0.5, "request_time_weight": 0.5,
    "cost_scope": "communication_revision_rounds_1_through_candidate_round_excluding_shared_initialization",
    "cost_aggregation": "question_weighted_within_family_then_equal_mean_across_four_families",
    "calibration": "positive_family_balanced_development_communication_round_1_token_and_request_second_means",
    "round_zero_revision_cost": 0,
    "timing_amendment": "request_seconds_including_loading_replaces_legacy_full_round_wall_time_before_validation",
    "tie_break": "prefer_fewer_rounds",
    "test_comparison": "both_branches_at_the_same_validation_selected_communication_round",
    "lock": "calibration_frozen_before_validation_and_selection_frozen_before_test",
}
PROTOCOL = {
    "generation_protocol": GENERATION_PROTOCOL, "failure_policy": FAILURE_POLICY,
    "num_agents": NUM_AGENTS, "agent_ids": list(AGENT_IDS), "arms": list(ARMS),
    "phases": list(PHASES), "phase_questions": PHASE_QUESTIONS, "phase_structural_groups": PHASE_GROUPS,
    "task_manifest": "full_benchmark.json", "seed_namespace": SEED_NAMESPACE,
    "phase_isolation": "no_request_from_a_later_phase_before_its_frozen_dependencies_exist",
    "schedule": "all_phase_initial_calls_then_each_question_round1_to3_with_alternating_paired_arms",
    "history": "original_question_and_immediately_preceding_completed_branch_snapshot_only",
    "peer_selection": "all_four_other_agents_no_correctness_or_eligibility_filter",
    "peer_presentation": "anonymous_Peer_1_through_Peer_4_in_seeded_order",
    "shared_fields": ["explanation", "expression", "computed_fraction", "status"],
    "voting": "unique_eligible_exact_rational_current_round_plurality_ties_abstain",
    "scoring": "exact_equality_abstentions_count_incorrect",
    "full_trajectory_collection": True, "online_early_stopping": False,
    "alternative_voters": [], "adaptive_stopping_rules": [],
    "reference_policy": "local_scoring_only_no_references_or_correctness_or_collective_feedback_in_prompts",
    "initial_control": "single_initial_agent_0_with_round_zero_plurality_and_oracle_diagnostic",
    "reused_pilot_answers": 0, "initialization": "fresh_all_3500_calls_no_pilot_import",
    "planned_calls": {"development": 700, "validation": 1400, "test": 1400, "total": 3500},
    "environment_manifest": "confirmation_environment.json",
    "selection_objective": SELECTION_OBJECTIVE,
    "uncertainty": {"draws": 2000, "seed": 20261118,
                    "method": "paired_family_stratified_whole_structural_group_bootstrap_all_variants_together"},
    "design_amendments": [
        "Five agents replace the historical ten-agent primary design before validation/test.",
        "The selected strict schema, matched generic revision instruction and paired scheduling replace the legacy plain-JSON full-study implementation.",
        "Consistent measured model-request time, including loading, replaces legacy round-wall-time cost calibration before validation.",
        "Full history remains deferred; immediately preceding snapshots are retained.",
    ],
}
EXPECTED_CONFIG = {
    "schema_version": 2, "study_id": STUDY_ID, "experiment_id": EXPERIMENT_ID,
    "task_manifest": "full_benchmark.json", "num_agents": NUM_AGENTS,
    "peer_count": 4, "agent_ids": list(AGENT_IDS), "selected_profile": "strict_schema",
    "arms": list(ARMS), "protocol": PROTOCOL,
}


def load_tasks():
    manifest = strict_json((ROOT / "config/full_benchmark.json").read_text(encoding="utf-8"))
    if canonical(manifest) != canonical(generate_manifest()):
        raise ValueError("Full benchmark differs from independently audited deterministic generation")
    validate_manifest(manifest)
    tasks = copy.deepcopy(manifest["tasks"])
    if len(tasks) != 100 or len({task["group_id"] for task in tasks}) != 52:
        raise ValueError("Full study requires 100 questions and 52 disjoint structural groups")
    for phase in PHASES:
        selected = phase_tasks(tasks, phase)
        if (len(selected) != PHASE_QUESTIONS[phase]
                or len({task["group_id"] for task in selected}) != PHASE_GROUPS[phase]
                or Counter(task["family"] for task in selected) !=
                   Counter({family: PHASE_QUESTIONS[phase] // 4 for family in FAMILIES})):
            raise ValueError("Benchmark phase balance differs from the frozen full study")
    group_phases = {}
    for task in tasks:
        prior = group_phases.setdefault(task["group_id"], (task["split"], task["family"]))
        if prior != (task["split"], task["family"]):
            raise ValueError("Structural group crosses a family or phase")
    return tasks


def phase_tasks(tasks, phase):
    if phase not in PHASES:
        raise ValueError("Unknown full-study phase")
    if any(task.get("split") not in PHASES for task in tasks):
        raise ValueError("Unexpected benchmark partition")
    return [copy.deepcopy(task) for task in tasks if task["split"] == phase]


def cohort_metadata(tasks):
    return {
        "questions": len(tasks), "structural_groups": len({task["group_id"] for task in tasks}),
        "phase_questions": {phase: sum(task["split"] == phase for task in tasks) for phase in PHASES},
        "phase_groups": {phase: len({task["group_id"] for task in tasks if task["split"] == phase})
                         for phase in PHASES},
        "development": "previously_inspected_case_definitions_fresh_generation_calibration_not_holdout",
        "validation_test": "structurally_disjoint_partitions_not_used_in_development_inference",
        "reused_answers": 0,
    }


def _seed(question_id, round_index, agent_id, purpose):
    value = json.dumps([SEED_NAMESPACE, question_id, round_index, agent_id, purpose],
                       separators=(",", ":")).encode("utf-8")
    return int.from_bytes(hashlib.sha256(value).digest()[:4], "big") & 0x7fffffff


def generation_seed(question_id, round_index, agent_id):
    return _seed(question_id, round_index, agent_id, "generation")


def routing_seed(question_id, round_index, agent_id):
    return _seed(question_id, round_index, agent_id, "routing")


def choose_peers(question_id, round_index, agent_id):
    if type(round_index) is not int or not 1 <= round_index <= MAX_ROUNDS or agent_id not in AGENT_IDS:
        raise ValueError("Invalid full-study peer routing position")
    others = [agent for agent in AGENT_IDS if agent != agent_id]
    return random.Random(routing_seed(question_id, round_index, agent_id)).sample(others, NUM_AGENTS - 1)


def call_positions(tasks, phase):
    if phase not in PHASES or not tasks or any(task.get("split") != phase for task in tasks):
        raise ValueError("A phase schedule may contain only questions from its own partition")
    if len({task["id"] for task in tasks}) != len(tasks):
        raise ValueError("Phase schedule contains duplicate questions")
    positions = []

    def add(task, round_index, agent, arm):
        communicates = arm == "communication" and round_index > 0
        positions.append({"call_index": len(positions), "phase": phase,
                          "question_id": task["id"], "family": task["family"],
                          "split": phase, "group_id": task["group_id"],
                          "evaluation_set": "full_study_v2", "round": round_index,
                          "agent_id": agent, "arm": arm, "profile": "strict_schema",
                          "seed": generation_seed(task["id"], round_index, agent),
                          "routing_seed": routing_seed(task["id"], round_index, agent) if communicates else None,
                          "peer_ids": choose_peers(task["id"], round_index, agent) if communicates else []})

    for task in tasks:
        for agent in AGENT_IDS:
            add(task, 0, agent, "shared_initial")
    for question_index, task in enumerate(tasks):
        for round_index in range(1, MAX_ROUNDS + 1):
            for agent in AGENT_IDS:
                arms = ARMS if (question_index + round_index + agent) % 2 == 0 else tuple(reversed(ARMS))
                for arm in arms:
                    add(task, round_index, agent, arm)
    unique_seeds = [row["seed"] for row in positions if row["round"] == 0 or row["arm"] == ARMS[0]]
    if len(set(unique_seeds)) != len(unique_seeds):
        raise ValueError("Generation seed collision between distinct positions")
    if len(positions) != len(tasks) * 35:
        raise ValueError("Full-study phase call budget differs from 35 per question")
    return positions


def build_call(plan, index, answers):
    if canonical(plan["configuration_snapshot"]) != canonical(EXPECTED_CONFIG):
        raise ValueError("Configuration differs from the frozen full-study protocol")
    position = plan["call_positions"][index]
    task = next(task for task in plan["tasks_snapshot"] if task["id"] == position["question_id"])
    if position["phase"] != task["split"] or position["split"] != task["split"]:
        raise ValueError("Call position crosses its phase boundary")
    index_round = position["round"]
    if index_round == 0:
        if position["arm"] != "shared_initial" or position["peer_ids"] or position["routing_seed"] is not None:
            raise ValueError("Initial panel cannot contain communication routing")
        messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": task["prompt"]}]
    else:
        if position["arm"] not in ARMS or not 1 <= index_round <= MAX_ROUNDS:
            raise ValueError("Unexpected full-study revision identity")
        prior = [record for record in answers if record["question_id"] == task["id"]
                 and record["round"] == index_round - 1
                 and record.get("arm") == ("shared_initial" if index_round == 1 else position["arm"])]
        if len(prior) != NUM_AGENTS:
            raise ValueError("Revision requires the complete preceding branch snapshot")
        by_agent = {}
        for row in prior:
            agent = row.get("agent_id")
            if type(agent) is not int or agent not in AGENT_IDS or agent in by_agent:
                raise ValueError("Previous snapshot has inconsistent agent identities")
            if row.get("phase", task["split"]) != task["split"]:
                raise ValueError("Previous snapshot crosses its phase boundary")
            by_agent[agent] = shared_response(row)
        peers = choose_peers(task["id"], index_round, position["agent_id"]) if position["arm"] == "communication" else []
        route = routing_seed(task["id"], index_round, position["agent_id"]) if peers else None
        if position["peer_ids"] != peers or position["routing_seed"] != route:
            raise ValueError("Saved routing differs from the frozen full-study policy")
        payload = {"original_question": task["prompt"], "previous_round": index_round - 1,
                   "self_previous": by_agent[position["agent_id"]]}
        if peers:
            payload["peers"] = [{"label": f"Peer {i + 1}", **by_agent[agent]}
                                for i, agent in enumerate(peers)]
        messages = [{"role": "system", "content": REVISION_SYSTEM},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False, allow_nan=False)}]
    context_budget(messages)
    return {**copy.deepcopy(position), "format": copy.deepcopy(STRICT_SCHEMA), "messages": messages}
