"""Offline parity checks against the frozen Qwen appendix records."""

import json
from pathlib import Path
import unittest
from unittest.mock import patch

from pilot_scoring import score_response


ROOT = Path(__file__).resolve().parents[1]
STEM = ROOT / "results" / "experiment1-qwen-seed42-max512"


def saved_answers(suffix):
    path = STEM.with_name(STEM.name + suffix).with_suffix(".jsonl")
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    if rows[-1]["type"] != "complete":
        raise AssertionError(f"Incomplete scoring fixture: {path}")
    return rows[1:-1]


def raw_answer(answer, explanation="Check: fixture."):
    return {"message": {"content": json.dumps({
        "explanation": explanation, "final_answer": answer})}}


class PilotScoringTests(unittest.TestCase):
    def test_all_four_urn_records_retain_original_scores_and_parse_errors(self):
        answers = saved_answers("-urn-check1024")
        self.assertEqual(len(answers), 4)
        for record in answers:
            with self.subTest(condition=record["condition"], task=record["task"]["id"]):
                response = record["response"]
                expected = {
                    "prediction": response["prediction"],
                    "value": response["probability"],
                    "format_valid": response["probability"] is not None,
                    "correct": record["correct"],
                    "absolute_error": record["absolute_error"],
                    "error": response["parse_error"],
                    "check_label": record["math_check_mentioned"],
                }
                self.assertEqual(score_response(response["raw"], record["task"], "urn-check"), expected)

    def test_all_sixteen_diagnostic_records_retain_every_official_score_field(self):
        answers = saved_answers("-diagnostic1024")
        self.assertEqual(len(answers), 16)
        for record in answers:
            with self.subTest(condition=record["condition"], task=record["task"]["id"]):
                self.assertEqual(score_response(record["raw"], record["task"], "diagnostic"),
                                 record["score"])

    def test_out_of_range_numbers_are_valid_only_under_diagnostic_contract(self):
        for answer in ("7", "-2"):
            with self.subTest(answer=answer):
                raw = raw_answer(answer)
                task = {"answer_kind": "numeric", "gold_fraction": answer,
                        "family": "reasoning", "gold_probability": 0.5}
                diagnostic = score_response(raw, task, "diagnostic")
                self.assertTrue(diagnostic["format_valid"])
                self.assertTrue(diagnostic["correct"])
                self.assertEqual(diagnostic["value"], answer)
                urn = score_response(raw, task, "urn-check")
                self.assertFalse(urn["format_valid"])
                self.assertIsNone(urn["prediction"])
                self.assertIsNone(urn["value"])
                self.assertEqual(urn["error"],
                                 "final_answer must be a fraction or decimal between 0 and 1")

    def test_unsupported_ast_is_rejected_without_executing_it(self):
        task = {"answer_kind": "expression", "gold_fraction": "3"}
        expressions = (
            "1 + __import__('builtins').abs(-2)", "1 + sum([1, 1])",
            "(1).__class__ + 2", "[1, 2][0] + 2", "True + 2",
            "1 ** 2", "1 // 2", "'1' + '2'", "1 / 0", "1000001 + 1",
        )
        with patch("builtins.eval", side_effect=AssertionError("Scoring must not execute expressions")):
            for expression in expressions:
                with self.subTest(expression=expression):
                    result = score_response(raw_answer(expression), task, "diagnostic")
                    self.assertFalse(result["format_valid"])
                    self.assertFalse(result["correct"])
                    self.assertIsNotNone(result["prediction"])
                    self.assertIsNotNone(result["error"])

    def test_answer_contract_failures_remain_separate_from_valid_json(self):
        task = {"answer_kind": "expression", "gold_fraction": "7/22"}
        result = score_response(raw_answer("C(7, 2) / C(12, 2)"), task, "diagnostic")
        self.assertIsNotNone(result["prediction"])
        self.assertFalse(result["format_valid"])
        self.assertTrue(result["check_label"])
        numeric = score_response(raw_answer(27), {"answer_kind": "numeric", "gold_fraction": "30"},
                                 "diagnostic")
        self.assertIsNone(numeric["prediction"])
        self.assertFalse(numeric["format_valid"])

    def test_scoring_makes_no_model_calls(self):
        with patch("local_llm.OllamaClient.chat", side_effect=AssertionError("No inference")), \
                patch("local_llm.OllamaClient.health", side_effect=AssertionError("No service access")):
            result = score_response(raw_answer("1/2", "Math check: half."),
                                    {"family": "reasoning", "gold_probability": 0.5}, "urn-check")
        self.assertTrue(result["correct"])
        self.assertTrue(result["check_label"])

    def test_unknown_pilot_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "pilot must be"):
            score_response({}, {}, "other")


if __name__ == "__main__":
    unittest.main()
