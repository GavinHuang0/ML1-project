"""Offline separation of model setup, calculator execution, and delivered answers."""

import copy
from fractions import Fraction
import json
import unittest
from unittest.mock import patch

from calculator import evaluate_expression
from calculator_protocol import SYSTEM, process_response


def response(expression=None, explanation="Use the given values.", **extra):
    parsed = {"explanation": explanation, **extra}
    if expression is not None:
        parsed["expression"] = expression
    return {"message": {"content": json.dumps(parsed)}}


class CalculatorProtocolTests(unittest.TestCase):
    def test_correct_unconditional_conditional_sensor_and_units_expressions(self):
        cases = (
            ("(12/15)*(11/14)", {"family": "reasoning", "gold_fraction": "22/35"}, "22/35"),
            ("(8*7)/(10*9-2*1)", {"probability": True, "gold_fraction": "7/11"}, "7/11"),
            ("(0.5*0.8*(1-0.75))/(0.5*0.8*(1-0.75)+0.5*(1-0.8)*0.75)",
             {"family": "evidence", "gold_fraction": "4/7", "gold_state": 0}, "4/7"),
            ("(26+9)/5", {"family": "algebra", "gold_fraction": "7"}, "7"),
            ("72*(25/60)", {"family": "units", "gold_fraction": "30"}, "30"),
        )
        for expression, task, expected in cases:
            with self.subTest(expression=expression):
                result = process_response(response(expression), task)
                self.assertTrue(result["required_fields_valid"])
                self.assertTrue(result["method_format_valid"])
                self.assertTrue(result["calculator_success"])
                self.assertTrue(result["numeric_correct"])
                self.assertTrue(result["correct"])
                self.assertTrue(result["has_arithmetic_operation"])
                self.assertEqual(result["computed_fraction"], expected)
                self.assertIsNone(result["error"])

    def test_correct_execution_of_wrong_setup_does_not_count_as_correct_answer(self):
        result = process_response(response("(8/10)*(7/9)"),
                                  {"probability": True, "gold_fraction": "7/11"})
        self.assertTrue(result["calculator_success"])
        self.assertTrue(result["method_format_valid"])
        self.assertEqual(result["computed_fraction"], "28/45")
        self.assertFalse(result["numeric_correct"])
        self.assertFalse(result["correct"])
        self.assertGreater(result["absolute_error"], 0.001)

    def test_missing_explanation_preserves_numeric_success_but_fails_delivery(self):
        raw = {"message": {"content": '{"expression":"1/2"}'}}
        original = copy.deepcopy(raw)
        result = process_response(raw, {"gold_fraction": "1/2", "probability": True})
        self.assertTrue(result["json_valid"])
        self.assertTrue(result["calculator_attempted"])
        self.assertTrue(result["calculator_success"])
        self.assertTrue(result["numeric_correct"])
        self.assertFalse(result["required_fields_valid"])
        self.assertFalse(result["method_format_valid"])
        self.assertFalse(result["correct"])
        self.assertIn("explanation", result["parse_error"])
        self.assertIsNone(result["calculator_error"])
        self.assertEqual(raw, original)

    def test_no_expression_is_recovered_from_explanation_or_other_fields(self):
        for parsed in (
                {"explanation": "Compute 1/2; the answer is 0.5."},
                {"explanation": "Half.", "final_answer": "1/2"},
                {"explanation": "Half.", "expression": 0.5},
                {"explanation": "Half.", "expression": "   "}):
            with self.subTest(parsed=parsed), \
                    patch("calculator_protocol.evaluate_expression", side_effect=AssertionError("No expression provided")):
                result = process_response({"message": {"content": json.dumps(parsed)}}, {"gold_fraction": "1/2"})
            self.assertFalse(result["calculator_attempted"])
            self.assertFalse(result["calculator_success"])
            self.assertFalse(result["numeric_correct"])
            self.assertFalse(result["correct"])
            self.assertIsNotNone(result["parse_error"])

    def test_calculator_receives_only_the_original_expression(self):
        expression = "72 * (25 / 60)"
        task = {"prompt": "Do not pass this task to the calculator", "gold_fraction": "30",
                "secret_gold": "Never pass gold", "family": "units"}
        with patch("calculator_protocol.evaluate_expression", wraps=evaluate_expression) as calculate:
            result = process_response(response(expression), task)
        calculate.assert_called_once_with(expression)
        self.assertTrue(result["correct"])

    def test_malicious_or_unsupported_expressions_fail_without_execution_or_repairs(self):
        for expression in ('__import__("os").system("echo unsafe")', "1 ** 2", "1 // 2", "x + 1", "1/0"):
            with self.subTest(expression=expression), \
                    patch("builtins.eval", side_effect=AssertionError("No evaluation of code")), \
                    patch("calculator_protocol.evaluate_expression", wraps=evaluate_expression) as calculate:
                result = process_response(response(expression), {"gold_fraction": "1"})
            calculate.assert_called_once_with(expression)
            self.assertTrue(result["json_valid"])
            self.assertTrue(result["required_fields_valid"])
            self.assertTrue(result["calculator_attempted"])
            self.assertFalse(result["calculator_success"])
            self.assertFalse(result["method_format_valid"])
            self.assertFalse(result["correct"])
            self.assertIsNone(result["parse_error"])
            self.assertIsNotNone(result["calculator_error"])

    def test_invalid_prediction_json_never_reaches_calculator(self):
        for raw in ({}, {"message": {"content": "Not JSON"}},
                    {"message": {"content": "[]"}}, {"message": {"content": '{"expression":NaN}'}}):
            with self.subTest(raw=raw), \
                    patch("calculator_protocol.evaluate_expression", side_effect=AssertionError("No valid JSON")):
                result = process_response(raw, {"gold_fraction": "1/2"})
            self.assertFalse(result["json_valid"])
            self.assertFalse(result["calculator_attempted"])
            self.assertIsNotNone(result["parse_error"])
            self.assertIsNone(result["calculator_error"])

    def test_word_bound_and_exact_keys_are_secondary(self):
        result = process_response(response("1/2", " ".join(["word"] * 61), extra="allowed but flagged"),
                                  {"gold_fraction": "1/2"})
        self.assertEqual(result["explanation_words"], 61)
        self.assertFalse(result["within_explanation_bound"])
        self.assertFalse(result["exact_two_fields"])
        self.assertTrue(result["method_format_valid"])
        self.assertTrue(result["correct"])

    def test_literal_is_allowed_but_does_not_claim_arithmetic_setup(self):
        for expression, gold in (("0.5", "1/2"), ("-2", "-2")):
            with self.subTest(expression=expression):
                result = process_response(response(expression), {"gold_fraction": gold})
                self.assertTrue(result["calculator_success"])
                self.assertTrue(result["correct"])
                self.assertFalse(result["has_arithmetic_operation"])

    def test_probability_range_is_a_numeric_correctness_gate(self):
        for marker in ({"probability": True}, {"family": "reasoning"}, {"family": "evidence"}):
            with self.subTest(marker=marker):
                result = process_response(response("1.0005"), {**marker, "gold_fraction": "1"})
                self.assertTrue(result["method_format_valid"])
                self.assertTrue(result["calculator_success"])
                self.assertFalse(result["probability_in_range"])
                self.assertFalse(result["numeric_correct"])
                self.assertFalse(result["correct"])

    def test_exact_fraction_tolerance_and_float_gold_roundoff(self):
        exact = process_response(response("0.501"), {"gold_fraction": "1/2"})
        outside = process_response(response("0.50100001"), {"gold_fraction": "1/2"})
        fallback = process_response(response("0.501"), {"gold_probability": 0.5})
        preferred = process_response(response("1/2"), {"gold_fraction": "1/2", "gold_probability": 0.1})
        self.assertTrue(exact["correct"])
        self.assertFalse(outside["correct"])
        self.assertTrue(fallback["correct"])
        self.assertTrue(preferred["correct"])

    def test_decimal_overflow_does_not_discard_authoritative_exact_fraction(self):
        value = Fraction(10) ** 400
        with patch("calculator_protocol.evaluate_expression", return_value=value):
            result = process_response(response("1 * 1"), {"gold_fraction": str(value)})
        self.assertTrue(result["calculator_success"])
        self.assertEqual(result["computed_fraction"], str(value))
        self.assertIsNone(result["computed_decimal"])
        self.assertTrue(result["numeric_correct"])
        self.assertTrue(result["correct"])

    def test_scoring_reference_error_is_separate_from_calculation_failure(self):
        result = process_response(response("1/2"), {})
        self.assertTrue(result["calculator_success"])
        self.assertIsNone(result["parse_error"])
        self.assertIsNone(result["calculator_error"])
        self.assertIsNotNone(result["scoring_error"])
        self.assertFalse(result["correct"])

    def test_prompt_is_generic_and_scoring_never_calls_a_model(self):
        self.assertIn('"expression"', SYSTEM)
        self.assertIn("separate calculator", SYSTEM)
        self.assertNotIn("gold", SYSTEM.lower())
        self.assertNotIn("22/35", SYSTEM)
        with patch("local_llm.OllamaClient.chat", side_effect=AssertionError("No model inference")), \
                patch("local_llm.OllamaClient.health", side_effect=AssertionError("No model service")):
            result = process_response(response("1/2"), {"gold_fraction": "1/2"})
        self.assertTrue(result["correct"])


if __name__ == "__main__":
    unittest.main()
