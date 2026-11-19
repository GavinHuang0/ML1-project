"""Frozen, separate architecture comparisons; model prompts receive no labels."""

from collections import Counter
import copy
import hashlib
import json
from pathlib import Path
import random

from calculator_protocol import SYSTEM
from experiments.communication_pilot.protocol import (
    ARMS, MAX_ROUNDS, REVISION_SYSTEM, STRICT_SCHEMA, shared_response, context_budget,
    PROTOCOL as SELECTED_GENERATION_PROTOCOL,
)
from experiments.confirmation_pilot.protocol import (
    TASK_IDS, FAMILIES, TASK_SOURCE_FILES, load_tasks as load_confirmed_tasks,
    FAILURE_POLICY as SELECTED_FAILURE_POLICY,
)
from run_format_followup import canonical


ROOT = Path(__file__).resolve().parents[2]
SEED_NAMESPACE = "architecture-pilots-v1"
EXPERIMENT_IDS = {
    "five_agent": "strict-schema-five-agent-all-peer-pilot-v1",
    "sparse_peer": "strict-schema-ten-agent-two-peer-pilot-v1",
}
CONFIG_PATHS = {name: ROOT / "config" / f"{name}_pilot.json" for name in EXPERIMENT_IDS}
PROTOCOLS = {}
EXPECTED_CONFIGS = {}
for _name, _count, _degree in (("five_agent", 5, 4), ("sparse_peer", 10, 2)):
    _generation = copy.deepcopy(SELECTED_GENERATION_PROTOCOL)
    _generation.update({
        "num_agents": _count, "peer_count": _degree, "initial_system": SYSTEM,
        "round_zero": "fresh_panel_generated_once_then_shared_exactly_between_arms",
        "execution_mode": "all_initial_panels_then_question_major_synchronous_paired_revisions",
        "seed_policy": "sha256_architecture_pilots_v1_question_round_agent_generation_shared_across_arms_and_architectures",
        "peer_order": "ordered_sample_without_replacement_using_independent_question_round_agent_routing_seed",
        "study_role": "development_architecture_comparison_on_previously_inspected_questions",
        "bootstrap_seed": 20261118,
    })
    _failure = copy.deepcopy(SELECTED_FAILURE_POLICY)
    _failure["scope"] = "prospectively_frozen_before_architecture_pilot_inference"
    _protocol = {
        "generation_protocol": _generation, "failure_policy": _failure,
        "peer_selection": {
            "method": "uniform_random_sample_without_replacement_from_other_agents",
            "degree": _degree,
            "scope": "independent_question_round_recipient_agent",
            "exclude_self": True, "within_round_duplicate_peers": False,
            "resample_each_round": True, "previous_round_peer_may_recur": True,
            "graph": "directed_recipient_choices_no_reciprocity_or_incoming_degree_constraint",
            "presentation": "sample_order_anonymous_Peer_1_through_Peer_k",
            "eligibility_filter": False, "correctness_filter": False,
            "record": "routing_seed_and_ordered_peer_ids_saved_in_every_call_position",
        },
        "initial_agent_selection": "fixed_ids_zero_through_N_minus_one_before_generation_not_outcome_selected",
        "seed_namespace": SEED_NAMESPACE,
        "cross_architecture_pairing": "same_generation_seed_for_common_question_round_agent_positions_separate_fresh_calls_no_byte_identity_assumption",
        "task_policy": "same_twelve_previously_inspected_development_questions_as_confirmation",
        "schedule": "all_initial_calls_then_each_question_round1_to3_with_alternating_paired_arms",
        "full_trajectory_collection": True, "online_early_stopping": False,
        "policy_feedback_to_model": False,
        "voting": "unique_eligible_exact_rational_current_round_plurality_ties_abstain",
        "scoring": "exact_equality_abstention_counts_incorrect",
        "fixed_round_controls": [0, 1, 2, 3], "primary_comparison_round": 3,
        "alternative_voters": [], "adaptive_stopping_rules": [],
        "planned_initial_calls": len(TASK_IDS) * _count,
        "planned_revision_calls": len(TASK_IDS) * _count * MAX_ROUNDS * len(ARMS),
        "planned_unique_calls": len(TASK_IDS) * _count * (1 + MAX_ROUNDS * len(ARMS)),
        "environment_manifest": "confirmation_environment.json",
        "selection": "none_no_winner_ranking_or_automatic_validation_test_progression",
    }
    PROTOCOLS[_name] = _protocol
    EXPECTED_CONFIGS[_name] = {
        "schema_version": 1, "experiment_id": EXPERIMENT_IDS[_name], "architecture": _name,
        "num_agents": _count, "peer_count": _degree, "agent_ids": list(range(_count)),
        "task_manifest": "full_benchmark.json", "task_ids": list(TASK_IDS),
        "selected_profile": "strict_schema", "arms": list(ARMS), "protocol": _protocol,
    }


def _check_config(config):
    name = config.get("architecture")
    if name not in EXPECTED_CONFIGS or canonical(config) != canonical(EXPECTED_CONFIGS[name]):
        raise ValueError("Configuration differs from a frozen architecture pilot")


def load_tasks():
    """Reuse audited case definitions, without presenting seen cases as holdout."""
    tasks = load_confirmed_tasks()
    cohort_metadata(tasks)
    return tasks


def cohort_metadata(tasks):
    if ([task["id"] for task in tasks] != list(TASK_IDS)
            or Counter(task["family"] for task in tasks) != Counter({family: 3 for family in FAMILIES})
            or any(task["split"] != "development" for task in tasks)
            or len({task["group_id"] for task in tasks}) != 8):
        raise ValueError("Architecture pilots require the twelve fixed development cases and eight groups")
    return {
        "questions": 12, "structural_groups": 8,
        "freshness": "all_twelve_questions_and_all_eight_structures_previously_inspected_development",
        "fresh_generation": True, "reused_answers": 0,
        "task_cohorts": {task["id"]: "previously_inspected_development" for task in tasks},
        "difficulty_scope": "moderate_and_hard_development_cases_not_representative_easy_case_mix",
        "validation_test_inference": False,
    }


def _seed(question_id, round_index, agent_id, purpose):
    value = json.dumps([SEED_NAMESPACE, question_id, round_index, agent_id, purpose],
                       separators=(",", ":")).encode("utf-8")
    return int.from_bytes(hashlib.sha256(value).digest()[:4], "big") & 0x7fffffff


def generation_seed(question_id, round_index, agent_id):
    return _seed(question_id, round_index, agent_id, "generation")


def routing_seed(question_id, round_index, agent_id):
    return _seed(question_id, round_index, agent_id, "routing")


def choose_peers(question_id, round_index, agent_id, agent_ids, degree):
    if (not isinstance(agent_ids, (list, tuple)) or any(type(item) is not int for item in agent_ids)
            or len(set(agent_ids)) != len(agent_ids) or agent_id not in agent_ids
            or type(round_index) is not int or not 1 <= round_index <= MAX_ROUNDS
            or type(degree) is not int or not 1 <= degree < len(agent_ids)):
        raise ValueError("Invalid recipient, round, population or peer degree")
    candidates = sorted(item for item in agent_ids if item != agent_id)
    return random.Random(routing_seed(question_id, round_index, agent_id)).sample(candidates, degree)


def call_positions(tasks, config):
    _check_config(config)
    cohort_metadata(tasks)
    positions = []
    agent_ids = config["agent_ids"]

    def add(task, round_index, agent_id, arm):
        communication = arm == "communication" and round_index > 0
        positions.append({
            "call_index": len(positions), "question_id": task["id"], "family": task["family"],
            "split": task["split"], "group_id": task["group_id"], "evaluation_set": "architecture_development",
            "round": round_index, "agent_id": agent_id, "arm": arm, "profile": "strict_schema",
            "seed": generation_seed(task["id"], round_index, agent_id),
            "routing_seed": routing_seed(task["id"], round_index, agent_id) if communication else None,
            "peer_ids": choose_peers(task["id"], round_index, agent_id, agent_ids, config["peer_count"])
                if communication else [],
        })

    for task in tasks:
        for agent_id in agent_ids:
            add(task, 0, agent_id, "shared_initial")
    for question_index, task in enumerate(tasks):
        for round_index in range(1, MAX_ROUNDS + 1):
            for agent_id in agent_ids:
                arms = ARMS if (question_index + round_index + agent_id) % 2 == 0 else tuple(reversed(ARMS))
                for arm in arms:
                    add(task, round_index, agent_id, arm)
    independent = [row["seed"] for row in positions if row["round"] == 0 or row["arm"] == ARMS[0]]
    if len(independent) != len(set(independent)):
        raise ValueError("Generation seed collision across distinct question/round/agent positions")
    if len(positions) != config["protocol"]["planned_unique_calls"]:
        raise ValueError("Architecture call count differs from the frozen budget")
    return positions


def build_call(plan, index, answers):
    config = plan["configuration_snapshot"]
    _check_config(config)
    position = plan["call_positions"][index]
    task = next(task for task in plan["tasks_snapshot"] if task["id"] == position["question_id"])
    round_index = position["round"]
    if round_index == 0:
        messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": task["prompt"]}]
    else:
        previous = [record for record in answers if record["question_id"] == task["id"]
                    and record["round"] == round_index - 1
                    and record.get("arm") == ("shared_initial" if round_index == 1 else position["arm"])]
        if len(previous) != config["num_agents"]:
            raise ValueError("Revision requires the complete preceding branch snapshot")
        by_id = {}
        for record in previous:
            agent = record.get("agent_id")
            if type(agent) is not int or agent not in config["agent_ids"] or agent in by_id:
                raise ValueError("Previous snapshot has inconsistent agent identities")
            by_id[agent] = shared_response(record)
        expected_peers = choose_peers(task["id"], round_index, position["agent_id"],
                                      config["agent_ids"], config["peer_count"]) if position["arm"] == "communication" else []
        expected_route = routing_seed(task["id"], round_index, position["agent_id"]) if expected_peers else None
        if position["peer_ids"] != expected_peers or position["routing_seed"] != expected_route:
            raise ValueError("Saved routing choice differs from the frozen peer policy")
        payload = {"original_question": task["prompt"], "previous_round": round_index - 1,
                   "self_previous": by_id[position["agent_id"]]}
        if position["arm"] == "communication":
            payload["peers"] = [{"label": f"Peer {i + 1}", **by_id[peer]}
                                for i, peer in enumerate(expected_peers)]
        messages = [{"role": "system", "content": REVISION_SYSTEM},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False, allow_nan=False)}]
    context_budget(messages)
    return {**copy.deepcopy(position), "format": copy.deepcopy(STRICT_SCHEMA), "messages": messages}
