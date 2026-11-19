"""Frozen full-study partitioning, budgets and revision information flow."""

from collections import Counter
import copy
import json
import unittest

from experiments.full_study_v2 import protocol
from experiments.architecture_pilots.protocol import generation_seed as pilot_seed
from multi_agent_protocol import evaluate_response


def answer(task, round_index, agent, arm):
    raw = {"message": {"content": json.dumps({"explanation": f"Agent {agent} arithmetic.",
                                              "expression": "1/2"})}}
    return {"question_id": task["id"], "round": round_index, "agent_id": agent,
            "phase": task["split"], "arm": arm, "correctness_secret": "DO_NOT_FORWARD",
            "response": evaluate_response(raw, task["probability"])}


class FullStudyProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tasks = protocol.load_tasks()
        cls.plans = {}
        for phase in protocol.PHASES:
            tasks = protocol.phase_tasks(cls.tasks, phase)
            cls.plans[phase] = {"configuration_snapshot": protocol.EXPECTED_CONFIG,
                                "tasks_snapshot": tasks,
                                "call_positions": protocol.call_positions(tasks, phase)}

    def test_configuration_and_request_time_amendment_are_frozen(self):
        actual = json.loads(protocol.CONFIG_PATH.read_text(encoding="utf-8"))
        self.assertEqual(actual, protocol.EXPECTED_CONFIG)
        self.assertEqual(actual["num_agents"], 5)
        self.assertEqual(actual["protocol"]["planned_calls"],
                         {"development": 700, "validation": 1400, "test": 1400, "total": 3500})
        objective = actual["protocol"]["selection_objective"]
        self.assertIn("request_seconds", objective["formula"])
        self.assertEqual(objective["cost_weight"], 0.02)
        self.assertEqual(objective["tie_break"], "prefer_fewer_rounds")
        self.assertFalse(actual["protocol"]["online_early_stopping"])
        self.assertEqual(actual["protocol"]["reused_pilot_answers"], 0)

    def test_benchmark_has_disjoint_structural_groups_and_balanced_phases(self):
        self.assertEqual(len(self.tasks), 100)
        self.assertEqual(len({task["group_id"] for task in self.tasks}), 52)
        group_sets = []
        for phase in protocol.PHASES:
            selected = self.plans[phase]["tasks_snapshot"]
            self.assertEqual(len(selected), protocol.PHASE_QUESTIONS[phase])
            self.assertEqual(Counter(task["family"] for task in selected),
                             {family: len(selected) // 4 for family in protocol.FAMILIES})
            group_sets.append({task["group_id"] for task in selected})
        for i, groups in enumerate(group_sets):
            for other in group_sets[i + 1:]:
                self.assertFalse(groups & other)

    def test_phase_budgets_paired_seeds_and_new_namespace(self):
        all_unique = []
        for phase, planned in (("development", 700), ("validation", 1400), ("test", 1400)):
            plan = self.plans[phase]
            positions = plan["call_positions"]
            initial_count = 5 * len(plan["tasks_snapshot"])
            self.assertEqual(len(positions), planned)
            self.assertEqual({row["phase"] for row in positions}, {phase})
            self.assertEqual({row["round"] for row in positions[:initial_count]}, {0})
            self.assertEqual(Counter(row["arm"] for row in positions),
                             {"shared_initial": initial_count, "communication": 3 * initial_count,
                              "self_revision": 3 * initial_count})
            for index in range(initial_count, planned, 2):
                left, right = positions[index:index + 2]
                self.assertEqual({left["arm"], right["arm"]}, set(protocol.ARMS))
                for field in ("seed", "question_id", "round", "agent_id"):
                    self.assertEqual(left[field], right[field])
            independent = [row for row in positions if row["round"] == 0 or row["arm"] == "communication"]
            all_unique.extend(row["seed"] for row in independent)
            for row in independent:
                self.assertNotEqual(row["seed"], pilot_seed(row["question_id"], row["round"], row["agent_id"]))
        self.assertEqual(len(all_unique), len(set(all_unique)))

    def test_phase_schedule_rejects_cross_phase_or_duplicate_tasks(self):
        tasks = self.plans["development"]["tasks_snapshot"]
        with self.assertRaisesRegex(ValueError, "own partition"):
            protocol.call_positions([*tasks, self.plans["test"]["tasks_snapshot"][0]], "development")
        with self.assertRaisesRegex(ValueError, "duplicate"):
            protocol.call_positions([tasks[0], tasks[0]], "development")
        with self.assertRaisesRegex(ValueError, "Unknown"):
            protocol.phase_tasks(self.tasks, "invalid")

    def test_initial_and_revision_requests_hide_reference_and_forward_only_previous_round(self):
        plan = copy.deepcopy(self.plans["development"])
        task = plan["tasks_snapshot"][0]
        task["gold_fraction"] = "DO_NOT_FORWARD"
        task["parameters"] = {"secret": "DO_NOT_FORWARD"}
        initial = [answer(task, 0, agent, "shared_initial") for agent in range(5)]
        initial_request = protocol.build_call(plan, 0, [])
        self.assertEqual(initial_request["messages"][0]["content"], protocol.SYSTEM)
        self.assertEqual(initial_request["messages"][1]["content"], task["prompt"])
        indices = [index for index, row in enumerate(plan["call_positions"])
                   if row["question_id"] == task["id"] and row["round"] == 1 and row["agent_id"] == 0]
        comm, own = sorted([protocol.build_call(plan, i, initial) for i in indices], key=lambda row: row["arm"])
        comm_payload = json.loads(comm["messages"][1]["content"])
        peers = comm_payload.pop("peers")
        self.assertEqual(len(peers), 4)
        self.assertEqual(comm_payload, json.loads(own["messages"][1]["content"]))
        self.assertEqual(comm["messages"][0], own["messages"][0])
        self.assertNotIn("DO_NOT_FORWARD", json.dumps([initial_request, comm, own]))
        self.assertEqual(set(comm["peer_ids"]), {1, 2, 3, 4})

    def test_incomplete_previous_snapshot_and_routing_tampering_are_rejected(self):
        plan = copy.deepcopy(self.plans["validation"])
        task = plan["tasks_snapshot"][0]
        initial = [answer(task, 0, agent, "shared_initial") for agent in range(5)]
        index = next(i for i, row in enumerate(plan["call_positions"])
                     if row["question_id"] == task["id"] and row["round"] == 1 and row["arm"] == "communication")
        with self.assertRaisesRegex(ValueError, "complete"):
            protocol.build_call(plan, index, initial[:4])
        plan["call_positions"][index]["peer_ids"] = [1, 1, 2, 3]
        with self.assertRaisesRegex(ValueError, "routing"):
            protocol.build_call(plan, index, initial)


if __name__ == "__main__":
    unittest.main()
