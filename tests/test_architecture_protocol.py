"""Architecture budgets, sparse routing, seeded pairing and information flow."""

from collections import Counter
import copy
import json
import unittest

from experiments.architecture_pilots import protocol
from multi_agent_protocol import agent_seed as old_seed, evaluate_response


def answer(task, round_index, agent, arm):
    raw = {"message": {"content": json.dumps({"explanation": f"Setup from agent {agent}.",
                                              "expression": str(agent + 1)})}}
    return {"question_id": task["id"], "round": round_index, "agent_id": agent, "arm": arm,
            "reference_secret": "DO_NOT_FORWARD", "correct": True,
            "response": evaluate_response(raw, task["probability"])}


class ArchitectureProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tasks = protocol.load_tasks()
        cls.plans = {}
        for name, config in protocol.EXPECTED_CONFIGS.items():
            cls.plans[name] = {"tasks_snapshot": cls.tasks, "configuration_snapshot": config,
                               "call_positions": protocol.call_positions(cls.tasks, config)}

    def test_frozen_configs_and_seen_development_cohort(self):
        for name, path in protocol.CONFIG_PATHS.items():
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), protocol.EXPECTED_CONFIGS[name])
            self.assertEqual(protocol.EXPECTED_CONFIGS[name]["protocol"]["adaptive_stopping_rules"], [])
            self.assertEqual(protocol.EXPECTED_CONFIGS[name]["protocol"]["alternative_voters"], [])
        cohort = protocol.cohort_metadata(self.tasks)
        self.assertEqual((cohort["questions"], cohort["structural_groups"]), (12, 8))
        self.assertIn("previously_inspected", cohort["freshness"])
        self.assertTrue(all(task["split"] == "development" for task in self.tasks))
        self.assertFalse(cohort["validation_test_inference"])

    def test_exact_budgets_and_shared_initialization(self):
        for name, size, calls in (("five_agent", 5, 420), ("sparse_peer", 10, 840)):
            plan = self.plans[name]
            positions = plan["call_positions"]
            self.assertEqual(len(positions), calls)
            self.assertEqual(Counter(row["arm"] for row in positions),
                             {"shared_initial": 12 * size, "communication": 36 * size,
                              "self_revision": 36 * size})
            self.assertEqual({row["round"] for row in positions[:12 * size]}, {0})
            for index in range(12 * size, calls, 2):
                left, right = positions[index:index + 2]
                for key in ("seed", "question_id", "round", "agent_id"):
                    self.assertEqual(left[key], right[key])
                self.assertEqual({left["arm"], right["arm"]}, set(protocol.ARMS))

    def test_nested_panel_seeds_are_new_and_paired_across_architectures(self):
        maps = {name: {(row["question_id"], row["round"], row["agent_id"], row["arm"]): row["seed"]
                       for row in plan["call_positions"]} for name, plan in self.plans.items()}
        self.assertEqual(self.plans["five_agent"]["configuration_snapshot"]["agent_ids"], list(range(5)))
        for position, seed in maps["five_agent"].items():
            self.assertEqual(seed, maps["sparse_peer"][position])
            self.assertNotEqual(seed, old_seed(*position[:3]))

    def test_peer_choices_have_fixed_degree_exclude_self_and_are_reproducible(self):
        for name, degree in (("five_agent", 4), ("sparse_peer", 2)):
            plan = self.plans[name]
            self.assertEqual(plan["call_positions"], protocol.call_positions(self.tasks, plan["configuration_snapshot"]))
            for row in plan["call_positions"]:
                if row["arm"] == "communication":
                    self.assertEqual(len(row["peer_ids"]), degree)
                    self.assertEqual(len(set(row["peer_ids"])), degree)
                    self.assertNotIn(row["agent_id"], row["peer_ids"])
                    self.assertTrue(set(row["peer_ids"]).issubset(set(plan["configuration_snapshot"]["agent_ids"])))
                    self.assertIsInstance(row["routing_seed"], int)
                else:
                    self.assertEqual(row["peer_ids"], [])
                    self.assertIsNone(row["routing_seed"])

    def test_sparse_routing_resamples_and_allows_repeat_peers_across_rounds(self):
        rows = [row for row in self.plans["sparse_peer"]["call_positions"] if row["arm"] == "communication"]
        by_position = {(row["question_id"], row["round"], row["agent_id"]): row for row in rows}
        changed, repeats = 0, 0
        for row in rows:
            if row["round"] == 1:
                later = by_position[row["question_id"], 2, row["agent_id"]]
                changed += row["peer_ids"] != later["peer_ids"]
                repeats += bool(set(row["peer_ids"]) & set(later["peer_ids"]))
                self.assertNotEqual(row["routing_seed"], later["routing_seed"])
        self.assertGreater(changed, 0)
        self.assertGreater(repeats, 0)

    def test_initial_and_revision_prompts_keep_labels_private_and_forward_only_selected_peers(self):
        for name, plan in self.plans.items():
            task = self.tasks[0]
            initial = [answer(task, 0, agent, "shared_initial")
                       for agent in plan["configuration_snapshot"]["agent_ids"]]
            changed = copy.deepcopy(plan)
            changed["tasks_snapshot"][0]["gold_fraction"] = "DO_NOT_FORWARD"
            changed["tasks_snapshot"][0]["parameters"] = {"secret": "DO_NOT_FORWARD"}
            call = protocol.build_call(changed, 0, [])
            self.assertEqual(call["messages"], [{"role": "system", "content": protocol.SYSTEM},
                                               {"role": "user", "content": task["prompt"]}])
            first_revision = 12 * plan["configuration_snapshot"]["num_agents"]
            both = [protocol.build_call(changed, index, initial)
                    for index in (first_revision, first_revision + 1)]
            comm = next(row for row in both if row["arm"] == "communication")
            self_revision = next(row for row in both if row["arm"] == "self_revision")
            payload = json.loads(comm["messages"][1]["content"])
            peers = payload.pop("peers")
            self.assertEqual(payload, json.loads(self_revision["messages"][1]["content"]))
            self.assertEqual(comm["messages"][0], self_revision["messages"][0])
            self.assertEqual(comm["messages"][0]["content"], protocol.REVISION_SYSTEM)
            self.assertEqual([peer["explanation"] for peer in peers],
                             [initial[agent]["response"]["explanation"] for agent in comm["peer_ids"]])
            for peer in peers:
                self.assertEqual(set(peer), {"label", "explanation", "expression", "computed_fraction", "status"})
            self.assertNotIn("DO_NOT_FORWARD", json.dumps(both))

    def test_ineligible_peers_are_not_filtered_out_of_sparse_routing(self):
        plan = self.plans["sparse_peer"]
        task = self.tasks[0]
        first = next(i for i, row in enumerate(plan["call_positions"]) if row["arm"] == "communication")
        initial = [answer(task, 0, agent, "shared_initial") for agent in range(10)]
        chosen = plan["call_positions"][first]["peer_ids"][0]
        initial[chosen]["response"].update(explanation=None, expression=None, computed_fraction=None,
                                            status="invalid_json", eligible=False)
        call = protocol.build_call(plan, first, initial)
        peer = json.loads(call["messages"][1]["content"])["peers"][0]
        self.assertEqual(peer["status"], "invalid_json")
        self.assertIsNone(peer["expression"])
        self.assertEqual(call["peer_ids"][0], chosen)

    def test_missing_previous_branch_and_routing_tampering_are_rejected(self):
        plan = self.plans["five_agent"]
        task = self.tasks[0]
        index = next(i for i, row in enumerate(plan["call_positions"])
                     if row["question_id"] == task["id"] and row["arm"] == "communication" and row["round"] == 2)
        previous = [answer(task, 1, agent, "communication") for agent in range(5)]
        with self.assertRaisesRegex(ValueError, "complete"):
            protocol.build_call(plan, index, previous[:-1])
        with self.assertRaisesRegex(ValueError, "complete"):
            protocol.build_call(plan, index, [{**record, "arm": "self_revision"} for record in previous])
        changed = copy.deepcopy(plan)
        changed["call_positions"][index]["peer_ids"] = [0, 0, 0, 0]
        with self.assertRaisesRegex(ValueError, "routing"):
            protocol.build_call(changed, index, previous)


if __name__ == "__main__":
    unittest.main()
