"""Offline paired-cluster analysis tests; no model or external service is used."""

import copy
import unittest

from full_experiment_analysis import summarize_study
from multi_agent_analysis import summarize_round


def task(identifier, group, family="algebra", split="development"):
    result = {"id": identifier, "family": family, "split": split, "gold_fraction": "1/2",
              "probability": False, "prompt": "Fixture arithmetic question"}
    if group is not None:
        result["group_id"] = group
    return result


def response(correct=True):
    value = "1/2" if correct else "0"
    return {"explanation": "Fixture.", "expression": value, "computed_fraction": value,
            "eligible": True, "json_valid": True, "required_fields_valid": True,
            "calculator_attempted": True, "calculator_success": True}


def trajectory(tasks, correct_by_question=None, token_count=20):
    all_records, all_rounds = [], []
    for question in tasks:
        history = []
        for index in range(4):
            correct = correct_by_question[question["id"]][index] if correct_by_question else True
            records = [{"question_id": question["id"], "round": index, "agent_id": agent,
                        "seed": agent + index * 100, "messages": [{"role": "user", "content": question["prompt"]}],
                        "response": response(correct), "elapsed_seconds": 0.1,
                        "raw": {"message": {"content": "Fixture."}, "prompt_eval_count": token_count,
                                "eval_count": 10, "done_reason": "stop", "load_duration": 100_000_000,
                                "total_duration": 500_000_000}}
                       for agent in range(10)]
            summary = summarize_round(question, records, 10 + index, history)
            history.append(summary)
            all_records.extend(records)
            all_rounds.append(summary)
    return all_records, all_rounds


def control_with_shared_initial(tasks, primary_records, correct_by_question=None, token_count=5):
    records, _ = trajectory(tasks, correct_by_question, token_count)
    initial = {(r["question_id"], r["agent_id"]): r for r in primary_records if r["round"] == 0}
    records = [copy.deepcopy(initial[(r["question_id"], r["agent_id"])]) if r["round"] == 0 else r for r in records]
    return records, recompute_rounds(tasks, records)


def recompute_rounds(tasks, records):
    result = []
    for question in tasks:
        history = []
        for index in range(4):
            current = [r for r in records if r["question_id"] == question["id"] and r["round"] == index]
            summary = summarize_round(question, current, 10 + index, history)
            history.append(summary)
            result.append(summary)
    return result


CALIBRATION = {"token_reference": 300, "wall_reference": 11,
               "source_splits": ["development"], "source_question_ids": ["calibration-fixture"]}


class FullStudyAnalysisTests(unittest.TestCase):
    def test_twenty_groups_preserve_paired_variants_and_shared_initial_cancellation(self):
        tasks = [task(f"q{group:02d}-{variant}", f"g{group:02d}", split="test")
                 for group in range(20) for variant in range(2)]
        values = {q["id"]: [int(q["group_id"][1:]) < 10] * 4 for q in tasks}
        records, rounds = trajectory(tasks, values)
        control_records, control_rounds = control_with_shared_initial(tasks, records, values)
        result = summarize_study(tasks, records, rounds, control_records, control_rounds,
                                 calibration=CALIBRATION, selected_round=1)
        structure = result["group_structure"]["test"]
        self.assertEqual(structure["questions"], 40)
        self.assertEqual(structure["groups"], 20)
        self.assertEqual(structure["family_counts"], {"algebra": {"groups": 20, "questions": 40}})
        self.assertEqual(structure["unit"], "group_id")
        interval = result["primary"]["splits"]["test"]["rounds"][0]["confidence_intervals"]["accuracy"]
        self.assertLess(interval["lower"], 0.5)
        self.assertGreater(interval["upper"], 0.5)
        # Group sampling gives increments of 1/20, not independent-variant increments of 1/40.
        self.assertAlmostEqual(interval["lower"] * 20, round(interval["lower"] * 20))
        self.assertAlmostEqual(interval["upper"] * 20, round(interval["upper"] * 20))
        for comparison in result["comparisons"]["test"]:
            for metric in ("accuracy_difference", "family_balanced_accuracy_difference"):
                self.assertEqual(comparison["confidence_intervals"][metric], {"estimate": 0, "lower": 0, "upper": 0})
        for curve in result["primary"]["splits"]["test"]["rounds"]:
            self.assertEqual(curve["confidence_intervals"]["accuracy_change_from_round0"],
                             {"estimate": 0, "lower": 0, "upper": 0})
        self.assertEqual(result["joint_execution_budget"]["unique_model_calls"], 40 * 70)
        self.assertEqual(result["joint_execution_budget"]["shared_initial_model_calls"], 400)
        self.assertEqual(result["control"]["selected_rounds"], {})

    def test_primary_validation_selects_round_and_test_uses_same_round_for_both_arms(self):
        tasks = [task("d", "gd"), task("v", "gv", split="validation"), task("t", "gt", split="test")]
        values = {"d": [True] * 4, "v": [False, True, True, True], "t": [True, False, False, True]}
        records, rounds = trajectory(tasks, values)
        controls = {"d": [True] * 4, "v": [False, False, True, True], "t": [True, True, False, False]}
        control_records, control_rounds = control_with_shared_initial(tasks, records, controls)
        result = summarize_study(tasks, records, rounds, control_records, control_rounds)
        self.assertEqual(result["selected_round"], 1)
        self.assertEqual(result["primary"]["selected_rounds"]["validation"]["primary"]["selected_round"], 1)
        self.assertEqual(result["control"]["selected_rounds"], {})
        heldout = result["heldout_evaluation"]
        self.assertEqual(heldout["selected_round"], 1)
        self.assertEqual(heldout["primary"]["round"], 1)
        self.assertEqual(heldout["control"]["round"], 1)
        self.assertEqual(heldout["comparison"]["accuracy_difference"], -1)
        self.assertEqual(result["control"]["calibration"], result["primary"]["calibration"])
        with self.assertRaisesRegex(ValueError, "disagrees"):
            summarize_study(tasks, records, rounds, control_records, control_rounds, selected_round=2)

    def test_single_agent_zero_panel_and_oracle_are_predeclared_shared_initial_controls(self):
        tasks = [task("q1", "g1"), task("q2", "g2")]
        records, _ = trajectory(tasks)
        # Agent zero is wrong on q1, but the other nine agents make the panel correct.
        records[0]["response"] = response(False)
        rounds = recompute_rounds(tasks, records)
        result = summarize_study(tasks, records, rounds)
        baseline = result["initial_baselines"]["development"]
        self.assertEqual(baseline["single_agent_0"]["agent_id"], 0)
        self.assertEqual(baseline["single_agent_0"]["accuracy"], 0.5)
        self.assertEqual(baseline["ten_independent_agents_round0"]["accuracy"], 1)
        self.assertEqual(baseline["panel_minus_single_agent_0"]["accuracy_difference"], 0.5)
        self.assertEqual(baseline["oracle_any_initial_eligible_correct"]["accuracy"], 1)
        self.assertTrue(baseline["oracle_any_initial_eligible_correct"]["diagnostic_only"])

    def test_group_weighting_uses_question_means_and_is_deterministic_under_reordering(self):
        tasks = [task("a1", "ga", "A"), task("a2", "ga", "A"), task("a3", "gb", "A"),
                 task("b1", "gc", "B")]
        values = {q["id"]: [q["id"] != "b1"] * 4 for q in tasks}
        records, rounds = trajectory(tasks, values)
        result = summarize_study(tasks, records, rounds)
        curve = result["primary"]["splits"]["development"]["rounds"][0]
        self.assertEqual(curve["accuracy"], 0.75)
        self.assertEqual(curve["family_balanced_accuracy"], 0.5)
        self.assertEqual(result["group_structure"]["development"]["groups"], 3)
        self.assertEqual(result["group_structure"]["development"]["singleton_families"], ["B"])
        reordered = summarize_study(list(reversed(tasks)), list(reversed(records)), list(reversed(rounds)))
        self.assertEqual(reordered["primary"]["splits"]["development"]["rounds"][0]["confidence_intervals"],
                         curve["confidence_intervals"])

    def test_missing_tokens_do_not_fake_costs_or_recalibrate_the_control(self):
        tasks = [task("q", "g")]
        records, _ = trajectory(tasks)
        records[10]["raw"].pop("prompt_eval_count")
        rounds = recompute_rounds(tasks, records)
        control_records, control_rounds = control_with_shared_initial(tasks, records)
        result = summarize_study(tasks, records, rounds, control_records, control_rounds)
        self.assertIsNone(result["calibration"])
        self.assertIsNone(result["control"]["calibration"])
        self.assertIsNone(result["control"]["splits"]["development"]["rounds"][1]["primary_objective"])
        self.assertIsNone(result["joint_execution_budget"]["input_tokens"])
        diagnostics = result["primary"]["splits"]["development"]["rounds"][1]["diagnostics"]
        self.assertIsNone(diagnostics["round_input_tokens"])
        shared = result["control"]["splits"]["development"]["rounds"][0]["diagnostics"]
        self.assertEqual(shared["new_model_calls"], 0)
        self.assertEqual(shared["shared_initial_records"], 10)

    def test_diagnostics_distinguish_numeric_success_format_failure_and_load_time(self):
        tasks = [task("q", None)]
        records, _ = trajectory(tasks)
        records[0]["response"]["eligible"] = False
        records[0]["response"]["required_fields_valid"] = False
        rounds = recompute_rounds(tasks, records)
        result = summarize_study(tasks, records, rounds)
        diagnostic = result["primary"]["splits"]["development"]["rounds"][0]["diagnostics"]
        self.assertEqual(diagnostic["strict_agent_accuracy"], 0.9)
        self.assertEqual(diagnostic["numeric_only_agent_accuracy"], 1)
        self.assertAlmostEqual(diagnostic["numeric_correct_but_ineligible_rate"], 0.1)
        self.assertAlmostEqual(diagnostic["output_contract_failure_rate"], 0.1)
        self.assertEqual(diagnostic["load_fraction_of_model_duration"], 0.2)
        self.assertEqual(diagnostic["load_fraction_of_round_wall"], 0.1)
        self.assertEqual(result["group_structure"]["development"]["fallback_question_groups"], 1)

    def test_missing_load_measurements_remain_unknown(self):
        tasks = [task("q", "g")]
        records, _ = trajectory(tasks)
        records[0]["raw"].pop("load_duration")
        rounds = recompute_rounds(tasks, records)
        result = summarize_study(tasks, records, rounds)
        diagnostic = result["primary"]["splits"]["development"]["rounds"][0]["diagnostics"]
        self.assertIsNone(diagnostic["model_reported_load_seconds"])
        self.assertIsNone(diagnostic["load_fraction_of_model_duration"])
        self.assertIsNone(result["joint_execution_budget"]["model_reported_load_seconds"])

    def test_incomplete_control_altered_initial_group_leakage_and_unfrozen_test_are_refused(self):
        tasks = [task("q", "g")]
        records, rounds = trajectory(tasks)
        control_records, control_rounds = control_with_shared_initial(tasks, records)
        with self.assertRaises(ValueError):
            summarize_study(tasks, records, rounds, control_records[:-1], control_rounds)
        changed = copy.deepcopy(control_records)
        changed[0]["raw"]["message"]["content"] = "Different initial generation"
        with self.assertRaisesRegex(ValueError, "exact primary"):
            summarize_study(tasks, records, rounds, changed, control_rounds)
        leaked = [task("q", "g", "A"), task("q2", "g", "B")]
        records2, rounds2 = trajectory(leaked)
        with self.assertRaisesRegex(ValueError, "cross splits or families"):
            summarize_study(leaked, records2, rounds2)
        test = [task("test-q", "test-g", split="test")]
        test_records, test_rounds = trajectory(test)
        with self.assertRaisesRegex(ValueError, "frozen on primary validation"):
            summarize_study(test, test_records, test_rounds, calibration=CALIBRATION)


if __name__ == "__main__":
    unittest.main()
