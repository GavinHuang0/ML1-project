"""Variable-size plurality, grouped uncertainty and cost accounting checks."""

from collections import Counter
import copy
import csv
from fractions import Fraction
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from experiments.architecture_pilots import analysis


ROOT = Path(__file__).resolve().parents[1]


def fixture(count=5):
    bank = json.loads((ROOT / "config/full_benchmark.json").read_text(encoding="utf-8"))
    by_id = {task["id"]: task for task in bank["tasks"]}
    tasks = [copy.deepcopy(by_id[question_id]) for question_id in analysis.TASK_IDS]

    def record(task, index, agent, arm):
        return {"question_id": task["id"], "round": index, "agent_id": agent,
                "arm": arm, "elapsed_seconds": 1.25,
                "raw": {"prompt_eval_count": 200, "eval_count": 50, "load_duration": 250_000_000,
                        "done_reason": "stop"},
                "response": {"eligible": True, "json_valid": True,
                             "required_fields_valid": True, "calculator_success": True,
                             "probability_in_range": True if task["probability"] else None,
                             "computed_fraction": task["gold_fraction"],
                             "within_explanation_bound": True, "calculator_error": None}}

    peers = 4 if count == 5 else 2
    initial = [record(task, 0, agent, "shared_initial") for task in tasks for agent in range(count)]
    revisions = [record(task, index, agent, arm) for task in tasks for index in range(1, 4)
                 for agent in range(count) for arm in analysis.ARMS]
    positions = [{"question_id": row["question_id"], "round": row["round"], "agent_id": row["agent_id"],
                  "arm": row["arm"], "peer_ids":
                      [agent for agent in range(count) if agent != row["agent_id"]][:peers]
                      if row["arm"] == "communication" else []} for row in revisions]
    return {"experiment_id": "fixture-architecture", "tasks_snapshot": tasks,
            "configuration_snapshot": {"num_agents": count, "peer_count": peers},
            "call_positions": positions}, initial, revisions


class ArchitectureAnalysisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest, cls.initial, cls.revisions = fixture()
        cls.summary = analysis.summarize(cls.manifest, cls.initial, cls.revisions)

    def row(self, arm="communication", index=3, summary=None):
        return next(row for row in (summary or self.summary)["comparisons"]
                    if (row["arm"], row["round"]) == (arm, index))

    def test_variable_panel_counts_and_physical_initial_cost_once(self):
        self.assertEqual(self.summary["comparison_rows"], 8)
        self.assertEqual(self.summary["per_question_rows"], 96)
        self.assertEqual(len(self.summary["cross_arm_comparisons"]), 4)
        self.assertEqual(self.summary["source_generation_cost_including_initial_once"]["unique_calls"], 420)
        self.assertEqual(self.summary["source_generation_cost_including_initial_once"]["total_tokens"], 420 * 250)
        self.assertEqual(self.row()["cumulative_calls"], 240)
        self.assertEqual(self.row()["revision_calls"], 180)
        self.assertEqual(self.row()["correct_agent_outputs"], 60)
        self.assertEqual(self.row()["correct_questions"], 12)
        self.assertEqual([row["unique_calls"] for row in self.summary["joint_round_costs"]], [60, 180, 300, 420])
        manifest, initial, revisions = fixture(10)
        with patch.object(analysis, "BOOTSTRAP_DRAWS", 10):
            summary = analysis.summarize(manifest, initial, revisions)
        self.assertEqual(summary["source_generation_cost_including_initial_once"]["unique_calls"], 840)
        self.assertEqual(self.row(summary=summary)["correct_agent_outputs"], 120)
        self.assertEqual(self.row(summary=summary)["cumulative_calls"], 480)
        self.assertEqual(summary["architecture"], {"num_agents": 10, "peer_count": 2, "agent_ids": list(range(10)),
                                                  "communication": "two_seeded_random_distinct_peers_per_agent_per_round"})
        self.assertFalse(summary["selection_performed"])

    def test_exact_fraction_plurality_and_ties_for_odd_panel(self):
        manifest, initial, revisions = fixture()
        task = manifest["tasks_snapshot"][0]
        chosen = [row for row in initial if row["question_id"] == task["id"]]
        gold = Fraction(task["gold_fraction"])
        for agent, row in enumerate(chosen):
            if agent < 3:
                row["response"]["computed_fraction"] = f"{gold.numerator * 2}/{gold.denominator * 2}"
            else:
                row["response"]["computed_fraction"] = "0"
        with patch.object(analysis, "BOOTSTRAP_DRAWS", 10):
            summary = analysis.summarize(manifest, initial, revisions)
        case = next(row for row in summary["per_question"] if row["arm"] == "communication"
                    and row["round"] == 0 and row["question_id"] == task["id"])
        self.assertEqual(case["answer"], str(gold))
        self.assertEqual(case["winning_support"], 3)
        # Five agents can tie across multiple mathematical answers: 2:2:1.
        for agent, row in enumerate(chosen):
            row["response"]["computed_fraction"] = str(gold) if agent < 2 else "0" if agent < 4 else "1"
        with patch.object(analysis, "BOOTSTRAP_DRAWS", 10):
            summary = analysis.summarize(manifest, initial, revisions)
        case = next(row for row in summary["per_question"] if row["arm"] == "communication"
                    and row["round"] == 0 and row["question_id"] == task["id"])
        self.assertFalse(case["answered"])
        self.assertFalse(case["correct"])
        self.assertEqual(case["abstention_reason"], "tied_plurality")

    def test_eligibility_and_correct_minority_loss_diagnostics(self):
        manifest, initial, revisions = fixture()
        question = manifest["tasks_snapshot"][0]["id"]
        for row in revisions:
            if row["question_id"] == question and row["arm"] == "communication":
                row["response"]["computed_fraction"] = "0"
        bad = next(row for row in revisions if row["question_id"] == question
                   and row["arm"] == "self_revision" and row["round"] == 1)
        bad["response"].update(eligible=False, calculator_success=False,
                               computed_fraction=None, calculator_error="Division by zero")
        with patch.object(analysis, "BOOTSTRAP_DRAWS", 10):
            summary = analysis.summarize(manifest, initial, revisions)
        comm = self.row(index=1, summary=summary)
        self.assertEqual(comm["correct_questions"], 11)
        self.assertEqual(comm["all_agent_wrong_consensus_panels"], 1)
        self.assertEqual(comm["harmful_collective_revisions"], 1)
        self.assertEqual(comm["harmful_agent_revisions"], 5)
        self.assertEqual(comm["correct_agent_outputs"], 55)
        self_row = self.row("self_revision", 1, summary)
        self.assertEqual(self_row["eligible_outputs"], 59)
        self.assertEqual(self_row["diagnostic_counts"]["undefined_division_by_zero"], 1)
        paired = next(row for row in summary["cross_arm_comparisons"] if row["round"] == 1)
        self.assertEqual(paired["correct_question_losses"], 1)
        self.assertEqual(paired["correct_question_gains"], 0)
        self.assertAlmostEqual(paired["metrics"]["family_balanced_accuracy_difference"]["estimate"], -1 / 12)

    def test_group_bootstrap_keeps_variants_paired_and_family_balance(self):
        tasks = self.manifest["tasks_snapshot"]
        draws = analysis._bootstrap_indices(tasks)
        self.assertEqual(len(draws), 2000)
        self.assertEqual(draws, analysis._bootstrap_indices(tasks))
        self.assertGreater(len({len(draw) for draw in draws}), 1)
        for draw in draws[:100]:
            counts = Counter(draw)
            for family in analysis.FAMILIES:
                groups = {}
                for index, task in enumerate(tasks):
                    if task["family"] == family:
                        groups.setdefault(task["group_id"], []).append(index)
                copies = []
                for members in groups.values():
                    self.assertEqual(len({counts[index] for index in members}), 1)
                    copies.append(counts[members[0]])
                self.assertEqual(sum(copies), 2)
        cases = [copy.deepcopy(row) for row in self.summary["per_question"]
                 if row["arm"] == "communication" and row["round"] == 3]
        for row in cases:
            row["correct"] = row["family"] == "reasoning"
        chosen = [0, 0] + [4, 5, 4, 5] + [7, 8, 7, 8] + [10, 11, 10, 11]
        stats = analysis._statistics(cases, chosen)
        self.assertEqual(stats["family_balanced_accuracy"], 0.25)
        self.assertAlmostEqual(stats["accuracy"], 2 / 14)
        for contrast in self.summary["cross_arm_comparisons"]:
            self.assertEqual(contrast["metrics"]["family_balanced_accuracy_difference"]["interval_95"], [0.0, 0.0])

    def test_report_bytes_and_routing_counts(self):
        reports = analysis.report_bytes(self.summary)
        self.assertEqual(reports, analysis.report_bytes(copy.deepcopy(self.summary)))
        self.assertEqual(set(reports), {"summary.json", "comparisons.csv", "per_question.csv"})
        self.assertEqual(len(list(csv.DictReader(io.StringIO(reports["comparisons.csv"].decode())))), 8)
        self.assertEqual(len(list(csv.DictReader(io.StringIO(reports["per_question.csv"].decode())))), 96)
        route = self.summary["routing"]
        self.assertEqual(route["communication_calls"], 180)
        self.assertEqual(route["directed_peer_references"], 720)
        self.assertEqual(route["directed_peer_references_per_question_round"], 20)
        self.assertEqual(len(route["snapshots"]), 36)
        self.assertTrue(all(row["min_inbound"] == row["max_inbound"] == 4 for row in route["snapshots"]))

    def test_no_eligible_answers_keep_conditional_accuracy_undefined(self):
        manifest, initial, revisions = fixture()
        for row in initial + revisions:
            row["response"].update(eligible=False, calculator_success=False,
                                   computed_fraction=None, calculator_error="Division by zero")
        with patch.object(analysis, "BOOTSTRAP_DRAWS", 10):
            summary = analysis.summarize(manifest, initial, revisions)
        r = self.row(summary=summary)
        self.assertEqual(r["accuracy"], 0)
        self.assertEqual(r["coverage"], 0)
        self.assertIsNone(r["accuracy_among_answered"])
        self.assertIsNone(r["uncertainty"]["accuracy_among_answered"]["interval_95"])
        self.assertEqual(r["uncertainty"]["accuracy_among_answered"]["valid_bootstrap_draws"], 0)

    def test_reject_partial_duplicate_wrong_split_and_bad_routing(self):
        with self.assertRaises(ValueError):
            analysis.summarize(self.manifest, self.initial[:-1], self.revisions)
        with self.assertRaises(ValueError):
            analysis.summarize(self.manifest, self.initial, [*self.revisions[:-1], self.revisions[0]])
        manifest = copy.deepcopy(self.manifest)
        manifest["tasks_snapshot"][0]["split"] = "test"
        with self.assertRaises(ValueError):
            analysis.summarize(manifest, self.initial, self.revisions)
        manifest = copy.deepcopy(self.manifest)
        manifest["call_positions"][0]["peer_ids"] = [0, 1, 2, 3]
        with patch.object(analysis, "BOOTSTRAP_DRAWS", 5), self.assertRaisesRegex(ValueError, "peer IDs"):
            analysis.summarize(manifest, self.initial, self.revisions)


if __name__ == "__main__":
    unittest.main()
