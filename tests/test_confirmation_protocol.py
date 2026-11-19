"""Reference, freshness and information-flow checks for the new confirmation."""

from collections import Counter
import copy
import json
from pathlib import Path
import unittest

from calculator_protocol import SYSTEM
from experiments.confirmation_pilot import protocol
from experiments.communication_pilot.protocol import build_messages as selected_messages
from multi_agent_protocol import evaluate_response


def answer(task, round_index, agent_id, arm):
    raw = {"message": {"content": json.dumps({"explanation": "Set up the arithmetic.", "expression": "1/2"})}}
    return {"question_id": task["id"], "round": round_index, "agent_id": agent_id, "arm": arm,
            "response": evaluate_response(raw, task["probability"])}


class ConfirmationProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tasks = protocol.load_tasks()
        cls.positions = protocol.call_positions(cls.tasks)
        cls.plan = {"tasks_snapshot": cls.tasks, "call_positions": cls.positions}

    def test_twelve_unused_numeric_cases_with_four_new_structures(self):
        self.assertEqual([task["id"] for task in self.tasks], protocol.TASK_IDS)
        self.assertEqual(Counter(task["family"] for task in self.tasks), {family: 3 for family in protocol.FAMILIES})
        self.assertTrue(all(task["split"] == "development" for task in self.tasks))
        metadata = protocol.cohort_metadata(self.tasks)
        self.assertEqual(metadata["structural_groups"], 8)
        self.assertEqual(len(metadata["new_structural_groups"]), 4)
        self.assertEqual(metadata["cohort_questions"], {"seen_structure_new_numbers": 4, "new_structure": 8})

    def test_exact_840_budget_and_shared_initial_panel(self):
        self.assertEqual(len(self.positions), 840)
        self.assertEqual(Counter(row["arm"] for row in self.positions),
                         {"shared_initial": 120, "communication": 360, "self_revision": 360})
        self.assertEqual([row["round"] for row in self.positions[:120]], [0] * 120)
        for index in range(120, 840, 2):
            left, right = self.positions[index:index + 2]
            self.assertEqual(left["seed"], right["seed"])
            self.assertEqual({left["arm"], right["arm"]}, set(protocol.ARMS))
            self.assertEqual((left["question_id"], left["round"], left["agent_id"]),
                             (right["question_id"], right["round"], right["agent_id"]))

    def test_initial_request_uses_selected_original_prompt_and_no_labels(self):
        plan = copy.deepcopy(self.plan)
        plan["tasks_snapshot"][0]["gold_fraction"] = "SECRET_GOLD"
        plan["tasks_snapshot"][0]["parameters"] = {"secret": "SECRET_PARAMETERS"}
        call = protocol.build_call(plan, 0, [])
        self.assertEqual(call["messages"][0], {"role": "system", "content": SYSTEM})
        self.assertEqual(call["messages"][1]["content"], self.tasks[0]["prompt"])
        self.assertNotIn("SECRET", json.dumps(call["messages"]))
        self.assertEqual(call["format"], protocol.STRICT_SCHEMA)

    def test_revision_requests_preserve_selected_prompt_and_peer_policy(self):
        task = self.tasks[0]
        initial = [answer(task, 0, agent, "shared_initial") for agent in range(10)]
        for index in (120, 121):
            call = protocol.build_call(self.plan, index, initial)
            self.assertEqual(call["messages"], selected_messages(task, 1, 0, call["arm"], initial))
        left, right = [protocol.build_call(self.plan, index, initial) for index in (120, 121)]
        comm = next(row for row in (left, right) if row["arm"] == "communication")
        self_revision = next(row for row in (left, right) if row["arm"] == "self_revision")
        payload = json.loads(comm["messages"][1]["content"])
        self.assertEqual(len(payload.pop("peers")), 9)
        self.assertEqual(payload, json.loads(self_revision["messages"][1]["content"]))

    def test_complete_preceding_branch_snapshot_required(self):
        task = self.tasks[0]
        previous = [answer(task, 1, agent, "communication") for agent in range(10)]
        index = next(i for i, row in enumerate(self.positions)
                     if row["question_id"] == task["id"] and row["round"] == 2 and row["arm"] == "communication")
        call = protocol.build_call(self.plan, index, previous)
        self.assertEqual(json.loads(call["messages"][1]["content"])["previous_round"], 1)
        with self.assertRaisesRegex(ValueError, "complete"):
            protocol.build_call(self.plan, index, previous[:9])
        wrong_arm = [{**row, "arm": "self_revision"} for row in previous]
        with self.assertRaisesRegex(ValueError, "complete"):
            protocol.build_call(self.plan, index, wrong_arm)

    def test_configuration_and_prospective_failure_policy_are_frozen(self):
        actual = json.loads((Path(protocol.ROOT) / "config/confirmation_pilot.json").read_text(encoding="utf-8"))
        self.assertEqual(actual, protocol.EXPECTED_CONFIG)
        self.assertFalse(actual["protocol"]["online_early_stopping"])
        self.assertEqual(actual["protocol"]["policy_protocol"]["voting_rules"],
                         ["plurality", "initial_anchored", "agent_history"])
        self.assertEqual(actual["protocol"]["policy_protocol"]["new_stopping_rules"],
                         ["high_agreement_8", "stable_majority_6"])
        self.assertEqual(protocol.FAILURE_POLICY["scope"], "prospectively_frozen_before_confirmation_inference")


if __name__ == "__main__":
    unittest.main()
