"""Confirmation replay, paired clusters, accounting, and stopping failures."""

from collections import Counter
import copy
import csv
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from experiments.confirmation_pilot import analysis
from experiments.confirmation_pilot.protocol import TASK_IDS


ROOT = Path(__file__).resolve().parents[1]


def fixture():
    bank = json.loads((ROOT / "config/full_benchmark.json").read_text(encoding="utf-8"))
    by_id = {task["id"]: task for task in bank["tasks"]}
    tasks = [copy.deepcopy(by_id[question_id]) for question_id in TASK_IDS]

    def record(task, index, agent, arm, value=None):
        value = task["gold_fraction"] if value is None else value
        return {"question_id": task["id"], "round": index, "agent_id": agent,
                "arm": arm, "elapsed_seconds": 1.5,
                "raw": {"prompt_eval_count": 200, "eval_count": 50, "done_reason": "stop"},
                "response": {"eligible": True, "json_valid": True,
                             "required_fields_valid": True, "calculator_success": True,
                             "probability_in_range": None, "computed_fraction": value,
                             "within_explanation_bound": True, "calculator_error": None}}

    initial = [record(task, 0, agent, "shared_initial") for task in tasks for agent in range(10)]
    revisions = [record(task, index, agent, arm)
                 for task in tasks for index in range(1, 4)
                 for agent in range(10) for arm in analysis.ARMS]
    return {"experiment_id": analysis.EXPERIMENT_ID, "tasks_snapshot": tasks}, initial, revisions


class ConfirmationAnalysisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest, cls.initial, cls.revisions = fixture()
        cls.result = analysis.summarize(cls.manifest, cls.initial, cls.revisions)

    def row(self, stopping, voter="plurality", arm="communication", result=None):
        return next(row for row in (result or self.result)["comparisons"]
                    if (row["arm"], row["voting_rule"], row["stopping_rule"]) == (arm, voter, stopping))

    def test_complete_prespecified_grid_and_cohort_sizes(self):
        self.assertEqual(self.result["comparison_rows"], 36)
        self.assertEqual(self.result["per_question_rows"], 432)
        self.assertEqual(self.result["round_prediction_rows"], 288)
        self.assertEqual(self.result["cohorts"]["new_structure"]["questions"], 8)
        self.assertEqual(self.result["cohorts"]["new_structure"]["groups"], 4)
        self.assertEqual(self.result["cohorts"]["seen_structure_new_numbers"]["questions"], 4)
        self.assertEqual(self.result["semantic_groups"], 8)
        self.assertEqual(len(self.result["diagnostics"]), 96)
        self.assertEqual(self.result["additional_policy_model_calls"], 0)
        self.assertFalse(self.result["selection"]["performed"])
        self.assertIsNone(self.result["selection"]["winner"])

    def test_full_round_costs_and_unique_initial_accounting(self):
        expected = {"fixed_round_3": 480, "high_agreement_8": 120, "stable_majority_6": 240}
        for stopping, calls in expected.items():
            row = self.row(stopping)
            self.assertEqual(row["consumed_logical_calls"], calls)
            self.assertEqual(row["total_tokens"], calls * 250)
            self.assertEqual(row["correct_questions"], 12)
            self.assertEqual(row["by_cohort"]["new_structure"]["correct_questions"], 8)
        self.assertEqual(self.result["source_generation_cost_including_initial_once"]["unique_calls"], 840)
        for stopping, calls in (("fixed_round_3", 840), ("high_agreement_8", 120), ("stable_majority_6", 360)):
            joint = next(row for row in self.result["joint_policy_costs"]
                         if row["voting_rule"] == "plurality" and row["stopping_rule"] == stopping)
            self.assertEqual(joint["unique_calls"], calls)
            self.assertEqual(joint["total_tokens"], calls * 250)
            self.assertEqual(joint["shared_initial_calls_counted_once"], 120)

    def test_bootstrap_samples_whole_groups_and_preserves_family_strata(self):
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
                group_copies = []
                for indices in groups.values():
                    self.assertEqual(len({counts[index] for index in indices}), 1)
                    group_copies.append(counts[indices[0]])
                self.assertEqual(sum(group_copies), 2)
        meta = self.result["bootstrap"]
        self.assertEqual(meta["groups"], 8)
        self.assertTrue(meta["variants_resampled_together"])
        self.assertTrue(meta["same_draws_across_all_policies_and_arms"])
        paired = next(row for row in self.result["cross_arm_comparisons"]
                      if row["voting_rule"] == "plurality" and row["stopping_rule"] == "fixed_round_3")
        self.assertEqual(paired["metrics"]["family_balanced_accuracy_difference"]["interval_95"], [0.0, 0.0])

    def test_bootstrap_family_balance_is_recomputed_with_unequal_draw_sizes(self):
        cases = [copy.deepcopy(row) for row in self.result["per_question"]
                 if row["arm"] == "communication" and row["voting_rule"] == "plurality"
                 and row["stopping_rule"] == "fixed_round_3"]
        # Resampled families need not contain equal question counts.
        indices = [0, 0] + [4, 5, 4, 5] + [7, 8, 7, 8] + [10, 11, 10, 11]
        for row in cases:
            row["correct"] = row["family"] == "reasoning"
        stats = analysis._statistics(cases, indices)
        self.assertEqual(stats["family_balanced_accuracy"], 0.25)
        self.assertAlmostEqual(stats["accuracy"], 2 / 14)

    def test_wrong_early_stops_later_recoveries_and_correct_answers_lost(self):
        manifest, initial, revisions = fixture()
        first, second = [task["id"] for task in manifest["tasks_snapshot"][:2]]
        for row in initial:
            if row["question_id"] == first and row["agent_id"] < 8:
                row["response"]["computed_fraction"] = "999"
        for row in revisions:
            if row["question_id"] == second and row["agent_id"] < 8:
                row["response"]["computed_fraction"] = "999"
        with patch.object(analysis, "BOOTSTRAP_DRAWS", 20):
            result = analysis.summarize(manifest, initial, revisions)
        high = self.row("high_agreement_8", result=result)
        self.assertEqual(high["wrong_early_stops"], 1)
        self.assertEqual(high["early_stop_missed_later_recoveries"], 1)
        self.assertEqual(high["early_stop_correct_later_losses"], 1)
        cases = {row["question_id"]: row for row in result["per_question"]
                 if row["arm"] == "communication" and row["voting_rule"] == "plurality"
                 and row["stopping_rule"] == "high_agreement_8"}
        self.assertEqual(cases[first]["stopping_round"], 0)
        self.assertEqual(cases[first]["answer"], "999")
        self.assertEqual(cases[first]["later_correct_rounds"], [1, 2, 3])
        self.assertEqual(cases[second]["later_incorrect_rounds"], [1, 2, 3])

    def test_future_and_gold_do_not_change_operational_decisions(self):
        manifest, initial, revisions = fixture()
        for task in manifest["tasks_snapshot"]:
            task["gold_fraction"] = "999"
        for row in revisions:
            row["response"]["computed_fraction"] = "999"
        with patch.object(analysis, "BOOTSTRAP_DRAWS", 10):
            result = analysis.summarize(manifest, initial, revisions)
        for before, after in zip(self.result["per_question"], result["per_question"]):
            if before["stopping_rule"] == "high_agreement_8":
                self.assertEqual(before["stopping_round"], after["stopping_round"])
                self.assertEqual(before["answer"], after["answer"])
                self.assertFalse(after["correct"])

    def test_reports_are_deterministic_and_csv_matches_full_grid(self):
        payloads = analysis.report_bytes(self.result)
        self.assertEqual(payloads, analysis.report_bytes(copy.deepcopy(self.result)))
        self.assertEqual(set(payloads), {"summary.json", "comparisons.csv", "per_question.csv"})
        self.assertEqual(json.loads(payloads["summary.json"])["questions"], 12)
        self.assertEqual(len(list(csv.DictReader(io.StringIO(payloads["comparisons.csv"].decode())))), 36)
        self.assertEqual(len(list(csv.DictReader(io.StringIO(payloads["per_question.csv"].decode())))), 432)

    def test_partial_duplicate_and_wrong_split_evidence_are_rejected(self):
        for changed in (self.initial[:-1], [*self.initial[:-1], self.initial[0]]):
            with self.assertRaises(ValueError):
                analysis.summarize(self.manifest, changed, self.revisions)
        with self.assertRaises(ValueError):
            analysis.summarize(self.manifest, self.initial, self.revisions[:-1])
        manifest = copy.deepcopy(self.manifest)
        manifest["tasks_snapshot"][0]["split"] = "validation"
        with self.assertRaises(ValueError):
            analysis.summarize(manifest, self.initial, self.revisions)


if __name__ == "__main__":
    unittest.main()
