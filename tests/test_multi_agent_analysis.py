"""Offline tests for exact voting, cumulative costs, and validation-only selection."""

import copy
import unittest

import multi_agent_analysis as analysis


def task(identifier="q1", family="algebra", split="development", gold="1/2", probability=False):
    return {"id": identifier, "family": family, "split": split, "gold_fraction": gold,
            "probability": probability, "prompt": "Fixture question"}


def response(value="1/2", eligible=True):
    return {"explanation": "Fixture.", "expression": value, "computed_fraction": value,
            "eligible": eligible, "json_valid": True, "required_fields_valid": True,
            "calculator_success": True}


def records(question, index=0, values=None, wall_seconds=None):
    values = values if values is not None else ["1/2"] * 10
    return [{"question_id": question["id"], "round": index, "agent_id": agent,
             "response": response(value), "elapsed_seconds": 1000,
             "raw": {"prompt_eval_count": 20, "eval_count": 10, "done_reason": "stop"}}
            for agent, value in enumerate(values)]


def trajectory(tasks, values_by_question=None):
    all_records, rounds = [], []
    for question in tasks:
        history = []
        for index in range(4):
            values = values_by_question[question["id"]][index] if values_by_question else None
            current = records(question, index, values)
            summary = analysis.summarize_round(question, current, index + 1, history)
            history.append(summary)
            all_records.extend(current)
            rounds.append(summary)
    return all_records, rounds


class ExactVoteTests(unittest.TestCase):
    def test_equivalent_fractions_vote_together_and_wall_time_is_measured(self):
        question = task()
        current = records(question, values=["1/2", "2/4", "0.5", "3/6", "4/8", "5/10", "0", "1", "2", "3"])
        summary = analysis.summarize_round(question, current, 0.25, [])
        self.assertEqual(summary["aggregate_answer"], "1/2")
        self.assertEqual(summary["votes"]["1/2"], 6)
        self.assertTrue(summary["aggregate_correct"])
        self.assertEqual(summary["round_wall_seconds"], 0.25)
        self.assertEqual(summary["cumulative_wall_seconds"], 0.25)
        self.assertEqual(summary["communication_wall_seconds"], 0)
        self.assertEqual(summary["round_total_tokens"], 300)
        self.assertEqual(summary["communication_total_tokens"], 0)

    def test_tie_and_no_eligible_answers_abstain_and_count_incorrect(self):
        question = task()
        current = records(question, values=["1/2"] * 5 + ["1/3"] * 5)
        tied = analysis.summarize_round(question, current, 1, [])
        self.assertTrue(tied["aggregate_abstained"])
        self.assertFalse(tied["aggregate_correct"])
        self.assertEqual(tied["abstention_reason"], "tied_plurality")
        self.assertEqual(tied["tied_winners"], ["1/3", "1/2"])
        for record in current:
            record["response"]["eligible"] = False
        empty = analysis.summarize_round(question, current, 1, [])
        self.assertEqual(empty["abstention_reason"], "no_eligible_answers")
        self.assertEqual(empty["valid_agents"], 0)

    def test_missing_required_field_never_votes_but_numeric_success_is_separate(self):
        question = task()
        current = records(question)
        for record in current:
            record["response"]["required_fields_valid"] = False
        summary = analysis.summarize_round(question, current, 1, [])
        self.assertEqual(summary["valid_agents"], 0)
        self.assertTrue(all(summary["agent_numeric_correct"].values()))
        self.assertFalse(any(summary["agent_correct"].values()))

    def test_tiny_probability_requires_exact_equality_and_range(self):
        question = task(gold="2/2189", probability=True)
        summary = analysis.summarize_round(question, records(question, values=["0"] * 10), 1, [])
        self.assertFalse(summary["aggregate_correct"])
        self.assertEqual(summary["aggregate_absolute_error_fraction"], "2/2189")
        summary = analysis.summarize_round(question, records(question, values=["2"] * 10), 1, [])
        self.assertTrue(summary["aggregate_abstained"])

    def test_transitions_cumulative_costs_and_missing_token_propagation(self):
        question = task()
        first = records(question, values=["0"] * 10)
        first[0]["raw"].pop("prompt_eval_count")
        summary0 = analysis.summarize_round(question, first, 2, [])
        second = records(question, 1)
        summary1 = analysis.summarize_round(question, second, 3, [summary0])
        summary2 = analysis.summarize_round(question, records(question, 2, ["0"] * 10), 4, [summary0, summary1])
        self.assertIsNone(summary1["cumulative_input_tokens"])
        self.assertEqual(summary1["communication_total_tokens"], 300)
        self.assertEqual(summary2["communication_total_tokens"], 600)
        self.assertEqual(summary2["cumulative_wall_seconds"], 9)
        self.assertEqual(summary2["communication_wall_seconds"], 7)
        self.assertTrue(summary1["beneficial_revision"])
        self.assertTrue(summary2["harmful_revision"])
        self.assertEqual(summary1["agent_beneficial_revisions"], 10)

    def test_incomplete_duplicate_or_unsynchronized_round_is_refused(self):
        question = task()
        for current, history in [(records(question)[:-1], []),
                                 (records(question)[:-1] + [records(question)[0]], []),
                                 (records(question, 1), [])]:
            with self.subTest(current=current), self.assertRaises(ValueError):
                analysis.summarize_round(question, current, 1, history)


class ExperimentAnalysisTests(unittest.TestCase):
    def test_family_balance_and_calibration_exclude_validation_and_test(self):
        tasks = [task("a1", family="A"), task("a2", family="A"), task("b1", family="B"),
                 task("v1", split="validation"), task("t1", split="test")]
        values = {q["id"]: [["1/2"] * 10] * 4 for q in tasks}
        values["b1"] = [["0"] * 10] * 4
        current, rounds = trajectory(tasks, values)
        summary = analysis.summarize_experiment(tasks, current, rounds)
        dev = summary["splits"]["development"]["rounds"][0]
        self.assertAlmostEqual(dev["accuracy"], 2 / 3)
        self.assertEqual(dev["family_balanced_accuracy"], 0.5)
        self.assertEqual(summary["calibration"]["source_question_ids"], ["a1", "a2", "b1"])
        self.assertEqual(summary["calibration"]["token_reference"], 300)
        self.assertEqual(summary["calibration"]["wall_reference"], 2)
        self.assertEqual(set(summary["selected_rounds"]), {"validation"})
        self.assertEqual(summary["selected_rounds"]["validation"]["primary"]["selected_round"], 0)

    def test_unknown_tokens_do_not_become_zero_or_claim_primary_optimum(self):
        tasks = [task("v", split="validation")]
        current, rounds = trajectory(tasks)
        current[10]["raw"].pop("eval_count")
        history = []
        for index in range(4):
            history.append(analysis.summarize_round(tasks[0], current[index * 10:(index + 1) * 10], index + 1, history))
        calibration = {"token_reference": 300, "wall_reference": 2, "source_splits": ["development"]}
        summary = analysis.summarize_experiment(tasks, current, history, calibration)
        self.assertIsNone(summary["splits"]["validation"]["rounds"][1]["normalized_communication_tokens"])
        self.assertIsNone(summary["selected_rounds"]["validation"]["primary"]["selected_round"])
        time_only = next(item for item in summary["selected_rounds"]["validation"]["sensitivity"]
                         if item["delta"] == 0.02 and item["omega"] == 0)
        self.assertEqual(time_only["selected_round"], 0)

    def test_nonmonotonic_accuracy_uses_global_minimum_and_smallest_round_tie(self):
        curves = [{"round": index, "loss": loss, "normalized_communication_tokens": index,
                   "normalized_communication_wall": index} for index, loss in enumerate([1, 1, 0, 0])]
        self.assertEqual(analysis._select(curves, 0.02, 0.5)["selected_round"], 2)
        self.assertEqual(analysis._select(curves, 0, 0.5)["selected_round"], 2)
        for curve in curves:
            curve["loss"] = 1
        self.assertEqual(analysis._select(curves, 0, 0.5)["selected_round"], 0)

    def test_heldout_without_calibration_is_scored_without_cost_selection(self):
        tasks = [task(split="test")]
        current, rounds = trajectory(tasks)
        summary = analysis.summarize_experiment(tasks, current, rounds)
        self.assertIsNone(summary["calibration"])
        self.assertEqual(summary["selected_rounds"], {})
        self.assertIsNone(summary["splits"]["test"]["rounds"][1]["primary_objective"])
        self.assertEqual(summary["splits"]["test"]["rounds"][0]["accuracy"], 1)

    def test_invalid_calibration_and_incomplete_duplicate_or_tampered_runs_are_refused(self):
        tasks = [task()]
        current, rounds = trajectory(tasks)
        for invalid in [None, 0, float("nan"), True, -1]:
            with self.subTest(reference=invalid), self.assertRaises(ValueError):
                analysis.summarize_experiment(tasks, current, rounds,
                    {"token_reference": invalid, "wall_reference": 2, "source_splits": ["development"]})
        with self.assertRaises(ValueError):
            analysis.summarize_experiment(tasks, current, rounds,
                {"token_reference": 300, "wall_reference": 2, "source_splits": ["test"]})
        for invalid_records, invalid_rounds in [(current[:-1], rounds),
                (current[:-1] + [current[0]], rounds), (current, rounds[:-1]),
                (current, rounds[:-1] + [rounds[0]])]:
            with self.assertRaises(ValueError):
                analysis.summarize_experiment(tasks, invalid_records, invalid_rounds)
        tampered = copy.deepcopy(rounds)
        tampered[0]["aggregate_correct"] = False
        with self.assertRaisesRegex(ValueError, "does not match"):
            analysis.summarize_experiment(tasks, current, tampered)

    def test_bootstrap_resamples_three_questions_by_family_and_preserves_pairing(self):
        tasks = [task("a1", family="A"), task("a2", family="A"), task("b1", family="B")]
        values = {q["id"]: [["1/2"] * 10] * 4 for q in tasks}
        values["a2"] = [["0"] * 10] * 4
        current, rounds = trajectory(tasks, values)
        report = analysis.summarize_experiment(tasks, current, rounds)
        split = report["splits"]["development"]
        uncertainty = split["uncertainty"]
        self.assertEqual(uncertainty["unit"], "question")
        self.assertEqual(uncertainty["questions"], 3)
        self.assertEqual(uncertainty["family_question_counts"], {"A": 2, "B": 1})
        self.assertEqual(uncertainty["replicates"], 2000)
        self.assertEqual(uncertainty["singleton_families"], ["B"])
        self.assertTrue(any("descriptive" in note for note in uncertainty["notes"]))
        for curve in split["rounds"]:
            intervals = curve["confidence_intervals"]
            self.assertAlmostEqual(intervals["accuracy"]["lower"], 1 / 3)
            self.assertEqual(intervals["accuracy"]["upper"], 1)
            self.assertEqual(intervals["family_balanced_accuracy"]["lower"], 0.5)
            for metric in ("accuracy_change_from_round0", "family_balanced_accuracy_change_from_round0"):
                self.assertEqual(intervals[metric], {"estimate": 0, "lower": 0, "upper": 0})
        reordered = analysis.summarize_experiment(list(reversed(tasks)), list(reversed(current)), list(reversed(rounds)))
        self.assertEqual(reordered["splits"]["development"]["uncertainty"], uncertainty)
        self.assertEqual(reordered["splits"]["development"]["rounds"], split["rounds"])

    def test_pareto_and_pairwise_break_even_cost_accuracy_tradeoff(self):
        curves = [{"round": index, "loss": loss, "normalized_communication_tokens": index,
                   "normalized_communication_wall": index,
                   "family_balanced_communication_total_tokens": index * 300,
                   "family_balanced_communication_wall_seconds": index * 2}
                  for index, loss in enumerate([1, 1, 0, 0])]
        self.assertEqual(analysis._pareto_rounds(curves), [0, 2])
        crossovers = analysis._break_even(curves)
        self.assertEqual(len(crossovers), 18)
        selected = next(row for row in crossovers if row["round_a"] == 0 and row["round_b"] == 2
                        and row["omega"] == 0.5)
        self.assertEqual(selected["break_even_delta"], 0.5)
        self.assertEqual(selected["status"], "pairwise_crossover")
        curves[2]["family_balanced_communication_total_tokens"] = None
        curves[2]["normalized_communication_tokens"] = None
        self.assertIsNone(analysis._pareto_rounds(curves))
        self.assertTrue(any(row["status"] == "unknown_cost" for row in analysis._break_even(curves)))

    def test_public_calibration_validation_is_available_for_preflight(self):
        calibration = {"token_reference": 300, "wall_reference": 2, "source_splits": ["development"]}
        self.assertIs(analysis.validate_calibration(calibration), calibration)
        with self.assertRaises(ValueError):
            analysis.validate_calibration({**calibration, "source_splits": ["validation"]})


if __name__ == "__main__":
    unittest.main()
