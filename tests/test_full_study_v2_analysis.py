"""Phase isolation, exact voting, grouped uncertainty and frozen selection."""

from collections import Counter
import copy
import csv
from fractions import Fraction
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from experiments.full_study_v2 import analysis


ROOT = Path(__file__).resolve().parents[1]


def fixture(phase="development", initial_correct=True, communication_correct=True, self_correct=True):
    bank = json.loads((ROOT / "config/full_benchmark.json").read_text(encoding="utf-8"))
    tasks = [copy.deepcopy(task) for task in bank["tasks"] if task["split"] == phase]

    def record(task, index, agent, arm, correct):
        value = task["gold_fraction"] if correct else "1" if Fraction(task["gold_fraction"]) == 0 else "0"
        return {"question_id": task["id"], "round": index, "agent_id": agent, "arm": arm,
                "elapsed_seconds": 1.25,
                "raw": {"prompt_eval_count": 200, "eval_count": 50, "load_duration": 250_000_000,
                        "done_reason": "stop"},
                "response": {"eligible": True, "json_valid": True, "required_fields_valid": True,
                             "calculator_success": True, "computed_fraction": value,
                             "within_explanation_bound": True, "calculator_error": None,
                             "probability_in_range": True if task["probability"] else None}}

    initial = [record(task, 0, agent, "shared_initial", initial_correct)
               for task in tasks for agent in range(5)]
    revisions = [record(task, index, agent, arm,
                        communication_correct if arm == "communication" else self_correct)
                 for task in tasks for index in range(1, 4) for agent in range(5) for arm in analysis.ARMS]
    manifest = {"study_id": analysis.STUDY_ID, "tasks_snapshot": tasks,
                "configuration_snapshot": {"num_agents": 5}}
    return manifest, initial, revisions


class FullStudyV2AnalysisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest, cls.initial, cls.revisions = fixture()
        cls.development = analysis.summarize_phase(cls.manifest, cls.initial, cls.revisions, "development")
        cls.calibration = analysis.create_calibration(cls.development, cls.manifest["tasks_snapshot"])

    def summarize(self, phase="validation", initial_correct=False,
                  communication_correct=True, self_correct=False, selection=None):
        manifest, initial, revisions = fixture(phase, initial_correct, communication_correct, self_correct)
        with patch.object(analysis, "BOOTSTRAP_DRAWS", 25):
            summary = analysis.summarize_phase(manifest, initial, revisions, phase,
                                               self.calibration, selection)
        return summary

    def test_development_full_budget_costs_and_initial_controls(self):
        result = self.development
        self.assertEqual((result["questions"], result["semantic_groups"]), (20, 12))
        self.assertEqual((result["comparison_rows"], result["per_question_rows"]), (8, 160))
        self.assertEqual(result["source_generation_cost_including_initial_once"]["unique_calls"], 700)
        self.assertEqual(result["source_generation_cost_including_initial_once"]["total_tokens"], 700 * 250)
        self.assertEqual([row["unique_calls"] for row in result["joint_round_costs"]], [100, 300, 500, 700])
        for name in ("single_agent_0", "oracle_any_initial_eligible_correct", "five_agent_plurality"):
            self.assertEqual(result["initial_controls"][name]["correct_questions"], 20)
        self.assertIsNone(result["primary_round"])
        self.assertFalse(result["test_round_selection_performed"])

    def test_calibration_is_positive_revision_only_family_balanced_r1(self):
        calibration = self.calibration
        self.assertEqual(calibration["references"], {"token_reference": 1250.0,
                                                    "request_seconds_reference": 6.25})
        self.assertEqual(calibration["time_metric"], "summed_model_request_seconds")
        self.assertEqual(calibration["cost_scope"], "communication_revisions_only_excluding_initial")
        self.assertEqual(calibration["source_summary_sha256"], analysis.artifact_hash(self.development))
        self.assertEqual(len(calibration["source_question_ids"]), 20)
        self.assertEqual(len(calibration["source_group_ids"]), 12)
        # A family's mean has equal weight even when its question count differs.
        self.assertEqual(analysis._family_mean([{"family": "a", "cost": 10},
                                               {"family": "b", "cost": 20},
                                               {"family": "b", "cost": 20}], "cost"), 15)

    def test_validation_selects_one_global_round_with_frozen_objective(self):
        summary = self.summarize()
        selection = analysis.choose_round(summary, self.calibration)
        self.assertEqual(selection["primary_round"], 1)
        self.assertEqual(selection["self_revision_primary_round"], 1)
        self.assertFalse(selection["test_feedback_used"])
        self.assertEqual([row["objective"] for row in selection["candidates"]], [1, 0.02, 0.04, 0.06])
        self.assertEqual(selection["calibration_sha256"], analysis.artifact_hash(self.calibration))
        self.assertEqual(len(selection["source_question_ids"]), 40)
        self.assertEqual(len(selection["source_group_ids"]), 20)
        # Changing only control outcomes cannot change the communication selection.
        other = self.summarize(self_correct=True)
        self.assertEqual(analysis.choose_round(other, self.calibration)["candidates"], selection["candidates"])

    def test_r0_available_and_exact_objective_tie_prefers_fewer_rounds(self):
        all_correct = self.summarize(initial_correct=True, self_correct=True)
        self.assertEqual(analysis.choose_round(all_correct, self.calibration)["primary_round"], 0)
        # Explicit zero-error equal-cost candidate values make the tie exact.
        changed = copy.deepcopy(all_correct)
        for row in changed["per_question"]:
            row["revision_total_tokens"] = 0
            row["revision_request_seconds"] = 0
        selected = analysis.choose_round(changed, self.calibration)
        self.assertEqual([row["objective"] for row in selected["candidates"]], [0, 0, 0, 0])
        self.assertEqual(selected["primary_round"], 0)

    def test_test_applies_validation_choice_even_when_another_test_round_is_better(self):
        selection = analysis.choose_round(self.summarize(), self.calibration)
        result = self.summarize("test", initial_correct=True, communication_correct=False,
                                self_correct=True, selection=selection)
        self.assertEqual(result["primary_round"], 1)
        self.assertEqual(result["primary_comparison"]["communication"]["correct_questions"], 0)
        self.assertEqual(result["primary_comparison"]["self_revision"]["correct_questions"], 40)
        self.assertEqual(result["primary_comparison"]["paired"]["correct_question_losses"], 40)
        self.assertEqual(result["comparisons"][0]["correct_questions"], 40)
        self.assertEqual(result["source_generation_cost_including_initial_once"]["unique_calls"], 1400)
        self.assertEqual(result["semantic_groups"], 20)
        self.assertFalse(result["test_round_selection_performed"])
        with self.assertRaisesRegex(ValueError, "validation"):
            analysis.choose_round(result, self.calibration)
        manifest, initial, revisions = fixture("test")
        with self.assertRaises(ValueError):
            analysis.summarize_phase(manifest, initial, revisions, "test")

    def test_exact_plurality_ties_abstain_and_oracle_is_only_diagnostic(self):
        manifest, initial, revisions = fixture()
        first = manifest["tasks_snapshot"][0]
        chosen = [row for row in initial if row["question_id"] == first["id"]]
        gold = Fraction(first["gold_fraction"])
        wrong = Fraction(1) if gold == 0 else Fraction(0)
        third = Fraction(1, 2) if gold != Fraction(1, 2) else Fraction(1, 3)
        for index, row in enumerate(chosen):
            row["response"]["computed_fraction"] = str(gold) if index in (1, 2) else str(wrong) if index in (0, 3) else str(third)
        with patch.object(analysis, "BOOTSTRAP_DRAWS", 15):
            result = analysis.summarize_phase(manifest, initial, revisions, "development")
        case = next(row for row in result["per_question"] if row["question_id"] == first["id"]
                    and row["arm"] == "communication" and row["round"] == 0)
        self.assertFalse(case["answered"])
        self.assertFalse(case["correct"])
        self.assertEqual(case["abstention_reason"], "tied_plurality")
        controls = result["initial_controls"]
        self.assertEqual(controls["single_agent_0"]["correct_questions"], 19)
        self.assertEqual(controls["oracle_any_initial_eligible_correct"]["correct_questions"], 20)
        self.assertEqual(controls["five_agent_plurality"]["correct_questions"], 19)

    def test_bootstrap_keeps_whole_groups_and_family_pairing(self):
        tasks = self.manifest["tasks_snapshot"]
        draws = analysis._bootstrap_indices(tasks)
        self.assertEqual(len(draws), 2000)
        self.assertGreater(len({len(draw) for draw in draws}), 1)
        for draw in draws[:75]:
            counts = Counter(draw)
            groups = {}
            for index, task in enumerate(tasks):
                groups.setdefault((task["family"], task["group_id"]), []).append(index)
            for members in groups.values():
                self.assertEqual(len({counts[index] for index in members}), 1)
            for family in analysis.FAMILIES:
                representatives = [members[0] for (f, _), members in groups.items() if f == family]
                self.assertEqual(sum(counts[index] for index in representatives), 3)
        for paired in self.development["cross_arm_comparisons"]:
            self.assertEqual(paired["metrics"]["family_balanced_accuracy_difference"]["interval_95"], [0, 0])

    def test_artifacts_reject_wrong_phase_nonpositive_or_unknown_cost_and_overlapping_groups(self):
        validation = self.summarize()
        with self.assertRaises(ValueError):
            analysis.create_calibration(validation)
        with self.assertRaises(ValueError):
            analysis.choose_round(self.development, self.calibration)
        for value in (None, -1, float("nan")):
            changed = copy.deepcopy(self.development)
            for row in changed["per_question"]:
                if row["arm"] == "communication" and row["round"] == 1:
                    row["revision_request_seconds"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                analysis.create_calibration(changed)
        bad_calibration = copy.deepcopy(self.calibration)
        bad_calibration["references"]["token_reference"] = 0
        with self.assertRaises(ValueError):
            analysis.choose_round(validation, bad_calibration)
        bad_calibration = copy.deepcopy(self.calibration)
        bad_calibration["source_group_ids"].append(validation["group_ids"][0])
        with self.assertRaisesRegex(ValueError, "overlap"):
            analysis.choose_round(validation, bad_calibration)

    def test_phase_record_identity_and_frozen_test_dependency_checks(self):
        with self.assertRaises(ValueError):
            analysis.summarize_phase(self.manifest, self.initial[:-1], self.revisions, "development")
        with self.assertRaises(ValueError):
            analysis.summarize_phase(self.manifest, self.initial, self.revisions[:-1], "development")
        with self.assertRaises(ValueError):
            analysis.summarize_phase(self.manifest, self.initial, self.revisions, "validation")
        wrong = copy.deepcopy(self.manifest)
        wrong["configuration_snapshot"]["num_agents"] = 10
        with self.assertRaises(ValueError):
            analysis.summarize_phase(wrong, self.initial, self.revisions, "development")
        selection = analysis.choose_round(self.summarize(), self.calibration)
        selection["calibration_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            self.summarize("test", selection=selection)
        selection = analysis.choose_round(self.summarize(), self.calibration)
        selection["primary_round"] = 3
        with self.assertRaisesRegex(ValueError, "objective"):
            self.summarize("test", selection=selection)

    def test_portable_reports_have_complete_rows_and_are_deterministic(self):
        reports = analysis.report_bytes(self.development)
        self.assertEqual(reports, analysis.report_bytes(copy.deepcopy(self.development)))
        self.assertEqual(set(reports), {"summary.json", "comparisons.csv", "per_question.csv"})
        self.assertEqual(len(list(csv.DictReader(io.StringIO(reports["comparisons.csv"].decode())))), 8)
        self.assertEqual(len(list(csv.DictReader(io.StringIO(reports["per_question.csv"].decode())))), 160)


if __name__ == "__main__":
    unittest.main()
