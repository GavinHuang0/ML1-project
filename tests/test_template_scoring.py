"""Offline checks separating answer mathematics from template compliance."""

import json
import unittest
from unittest.mock import patch

from template_scoring import score_response


NUMERIC_TASK = {"family": "reasoning", "answer_kind": "numeric", "gold_fraction": "7/22"}
EXPRESSION_TASK = {"family": "reasoning", "answer_kind": "expression", "gold_fraction": "7/22"}


def response(fields):
    return {"message": {"content": json.dumps(fields)}}


class TemplateScoringTests(unittest.TestCase):
    def test_complete_correct_numeric_answer_passes_all_contracts(self):
        fields = {"explanation": "Multiply the two conditional probabilities.", "final_answer": "7/22"}
        score = score_response(response(fields), NUMERIC_TASK)
        for key in ("json_valid", "required_fields_valid", "final_answer_valid", "numeric_correct",
                    "format_valid", "correct", "within_explanation_bound", "exact_two_fields"):
            self.assertTrue(score[key], key)
        self.assertEqual(score["value"], "7/22")
        self.assertEqual(score["absolute_error"], 0)
        self.assertEqual(score["prediction"], fields)
        self.assertIsNone(score["error"])

    def test_correct_final_answer_survives_missing_explanation_only_in_numeric_metric(self):
        score = score_response(response({"final_answer": "7/22"}), NUMERIC_TASK)
        self.assertTrue(score["json_valid"])
        self.assertTrue(score["final_answer_valid"])
        self.assertTrue(score["numeric_correct"])
        self.assertFalse(score["required_fields_valid"])
        self.assertFalse(score["format_valid"])
        self.assertFalse(score["correct"])
        self.assertFalse(score["within_explanation_bound"])
        self.assertIsNone(score["explanation_words"])
        self.assertIn("explanation", score["error"])

    def test_missing_final_answer_is_never_recovered_from_correct_prose(self):
        score = score_response(response({"explanation": "The exact answer is 7/22."}), NUMERIC_TASK)
        self.assertTrue(score["json_valid"])
        self.assertFalse(score["final_answer_valid"])
        self.assertFalse(score["numeric_correct"])
        self.assertFalse(score["format_valid"])
        self.assertIsNone(score["value"])
        self.assertIn("final_answer", score["error"])

    def test_valid_format_does_not_make_wrong_arithmetic_correct(self):
        score = score_response(response({"explanation": "A fixture.", "final_answer": "5/22"}), NUMERIC_TASK)
        self.assertTrue(score["required_fields_valid"])
        self.assertTrue(score["final_answer_valid"])
        self.assertTrue(score["format_valid"])
        self.assertFalse(score["numeric_correct"])
        self.assertFalse(score["correct"])
        self.assertIsNone(score["error"])
        self.assertGreater(score["absolute_error"], 0.001)

    def test_nonstring_fields_are_distinct_from_invalid_json(self):
        for fields, numeric_correct in (
            ({"final_answer": "7/22", "explanation": None}, True),
            ({"final_answer": 0.31818181818, "explanation": "A fixture."}, False),
        ):
            with self.subTest(fields=fields):
                score = score_response(response(fields), NUMERIC_TASK)
                self.assertTrue(score["json_valid"])
                self.assertTrue(score["exact_two_fields"])
                self.assertFalse(score["required_fields_valid"])
                self.assertEqual(score["numeric_correct"], numeric_correct)
                self.assertFalse(score["correct"])

    def test_invalid_or_nonobject_json_never_scores(self):
        contents = ("not JSON", "```json\n{}\n```", "[]", "null",
                    '{"final_answer":"7/22","explanation":"ok","extra":NaN}')
        for content in contents:
            with self.subTest(content=content):
                score = score_response({"message": {"content": content}}, NUMERIC_TASK)
                self.assertFalse(score["json_valid"])
                self.assertFalse(score["numeric_correct"])
                self.assertFalse(score["correct"])
                self.assertIsNone(score["prediction"])
                self.assertIsNotNone(score["error"])

    def test_probability_bounds_do_not_restrict_transfer_answers(self):
        for answer in ("-2", "2"):
            with self.subTest(answer=answer):
                raw = response({"explanation": "A fixture.", "final_answer": answer})
                task = {**NUMERIC_TASK, "gold_fraction": answer}
                probability = score_response(raw, task)
                self.assertTrue(probability["required_fields_valid"])
                self.assertTrue(probability["final_answer_valid"])
                self.assertTrue(probability["format_valid"])
                self.assertFalse(probability["numeric_correct"])
                self.assertFalse(probability["probability_in_range"])
                self.assertIsNone(probability["error"])
                transfer = score_response(raw, {**task, "family": "transfer"})
                self.assertTrue(transfer["correct"])
                self.assertIsNone(transfer["probability_in_range"])
        for answer in ("0", "1"):
            with self.subTest(endpoint=answer):
                self.assertTrue(score_response(response({"explanation": "", "final_answer": answer}),
                                               {**NUMERIC_TASK, "gold_fraction": answer})["correct"])

    def test_explicit_probability_marker_handles_custom_family_names(self):
        task = {"family": "unconditional", "probability": True,
                "answer_kind": "numeric", "gold_fraction": "2"}
        score = score_response(response({"explanation": "A fixture.", "final_answer": "2"}), task)
        self.assertTrue(score["format_valid"])
        self.assertFalse(score["probability_in_range"])
        self.assertFalse(score["numeric_correct"])
        self.assertFalse(score["correct"])

    def test_restricted_expression_is_scored_without_executing_code(self):
        with patch("builtins.eval", side_effect=AssertionError("No expression execution")):
            score = score_response(response({"explanation": "A fixture.",
                                              "final_answer": "(7/12) * (6/11)"}), EXPRESSION_TASK)
            self.assertTrue(score["correct"])
            self.assertEqual(score["value"], "7/22")
            for answer in ("C(7, 2)/C(12, 2)", "1/0", "1 + __import__('os').getpid()", "7//22"):
                with self.subTest(answer=answer):
                    invalid = score_response(response({"explanation": "A fixture.", "final_answer": answer}),
                                             EXPRESSION_TASK)
                    self.assertTrue(invalid["required_fields_valid"])
                    self.assertFalse(invalid["final_answer_valid"])
                    self.assertFalse(invalid["correct"])
                    self.assertIsNotNone(invalid["error"])

    def test_expression_numerics_survive_missing_explanation(self):
        score = score_response(response({"final_answer": "(7/12) * (6/11)"}), EXPRESSION_TASK)
        self.assertTrue(score["numeric_correct"])
        self.assertFalse(score["format_valid"])

    def test_length_and_exact_keys_are_secondary_compliance_flags(self):
        raw = response({"explanation": "  one\t two\nthree  ", "final_answer": "7/22", "extra": "ignored"})
        score = score_response(raw, NUMERIC_TASK, max_explanation_words=2)
        self.assertEqual(score["explanation_words"], 3)
        self.assertFalse(score["within_explanation_bound"])
        self.assertFalse(score["exact_two_fields"])
        self.assertTrue(score["format_valid"])
        self.assertTrue(score["correct"])
        self.assertTrue(score_response(raw, NUMERIC_TASK, max_explanation_words=3)["within_explanation_bound"])

    def test_invalid_word_bound_is_rejected_and_scoring_makes_no_model_calls(self):
        for bound in (-1, True, 1.5, None):
            with self.subTest(bound=bound), self.assertRaisesRegex(ValueError, "nonnegative integer"):
                score_response(response({}), NUMERIC_TASK, max_explanation_words=bound)
        with patch("local_llm.OllamaClient.chat", side_effect=AssertionError("No inference")), \
                patch("local_llm.OllamaClient.health", side_effect=AssertionError("No network")):
            score = score_response(response({"explanation": "", "final_answer": "7/22"}), NUMERIC_TASK,
                                   max_explanation_words=0)
            self.assertTrue(score["correct"])
            self.assertTrue(score["within_explanation_bound"])


if __name__ == "__main__":
    unittest.main()
