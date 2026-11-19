"""Offline arithmetic and resource checks for the exact calculator."""

from fractions import Fraction
import unittest
from unittest.mock import patch

from calculator import CalculationError, evaluate_expression


class CalculatorTests(unittest.TestCase):
    def test_fractions_precedence_and_parentheses_are_exact(self):
        cases = {
            "(12/15) * (11/14)": Fraction(22, 35),
            "(6*5) / (10*9 - 4*3)": Fraction(5, 13),
            "1 + 2 * 3": Fraction(7),
            "(1 + 2) * 3": Fraction(9),
            "  7/22 \n": Fraction(7, 22),
        }
        for expression, expected in cases.items():
            with self.subTest(expression=expression):
                self.assertEqual(evaluate_expression(expression), expected)
                self.assertIsInstance(evaluate_expression(expression), Fraction)

    def test_decimals_use_lexical_values_instead_of_binary_float_values(self):
        cases = {
            "0.1 + 0.2": Fraction(3, 10),
            "0.1000000000000000000000000000000000000001":
                Fraction("0.1000000000000000000000000000000000000001"),
            ".5 + 1.": Fraction(3, 2),
            "0.00000000000000000000000000000000000000000000000000000000000001":
                Fraction(1, 10 ** 62),
        }
        for expression, expected in cases.items():
            with self.subTest(expression=expression):
                self.assertEqual(evaluate_expression(expression), expected)

    def test_sensor_likelihood_formula_has_exact_normalization(self):
        expression = "(0.5*0.9*0.75)/(0.5*0.9*0.75 + 0.5*0.1*0.25)"
        self.assertEqual(evaluate_expression(expression), Fraction(27, 28))

    def test_literals_and_unary_signs(self):
        cases = {"0": Fraction(0), "1000000": Fraction(1000000),
                 "-1000000": Fraction(-1000000), "-(-3/4)": Fraction(3, 4),
                 "+2 * -3": Fraction(-6), "1--2": Fraction(3)}
        for expression, expected in cases.items():
            with self.subTest(expression=expression):
                self.assertEqual(evaluate_expression(expression), expected)

    def test_python_constructs_are_rejected_without_eval_or_exec(self):
        invalid = (
            "x + 1", "abs(-2)", "__import__('os').system('echo unsafe')",
            "(1).__class__", "[1, 2][0]", "[x for x in (1, 2)]",
            "True", "False + 1", "1 ** 2", "1 // 2", "1 % 2",
            "1 << 2", "1 and 2", "1 < 2", "1 if True else 2",
            "(1, 2)", "{1: 2}", "'1'", "1j", "lambda: 1", "1 # ignored text",
        )
        with patch("builtins.eval", side_effect=AssertionError("No eval")), \
                patch("builtins.exec", side_effect=AssertionError("No exec")):
            for expression in invalid:
                with self.subTest(expression=expression), self.assertRaises(CalculationError):
                    evaluate_expression(expression)
            self.assertEqual(evaluate_expression("0.1 + 0.2"), Fraction(3, 10))

    def test_nonplain_numeric_notation_is_rejected(self):
        for expression in ("1e3", "1e-30", "1_000", "0x10", "0b10", "0o10", "1e9999"):
            with self.subTest(expression=expression), self.assertRaises(CalculationError):
                evaluate_expression(expression)

    def test_division_by_zero_is_a_controlled_calculation_error(self):
        for expression in ("1/0", "1/(2-2)", "0/0", "1/-0.0"):
            with self.subTest(expression=expression), self.assertRaisesRegex(CalculationError, "Division by zero"):
                evaluate_expression(expression)

    def test_invalid_input_and_syntax_are_controlled_errors(self):
        for expression in (None, 1, True, "", " ", "1 +", "(1+2", "1; 2", "a=1", "1\x00"):
            with self.subTest(expression=expression), self.assertRaises(CalculationError):
                evaluate_expression(expression)

    def test_text_length_limit_counts_original_whitespace(self):
        self.assertEqual(evaluate_expression(" " * 999 + "1"), Fraction(1))
        with self.assertRaisesRegex(CalculationError, "1000-character"):
            evaluate_expression(" " * 1000 + "1")

    def test_literal_length_and_magnitude_limits(self):
        literal = "0." + "0" * 61 + "1"
        self.assertEqual(len(literal), 64)
        self.assertEqual(evaluate_expression(literal), Fraction(1, 10 ** 62))
        for expression, message in ((literal + "1", "64-character"),
                                    ("1000001", "absolute value"),
                                    ("-1000000.1", "absolute value")):
            with self.subTest(expression=expression), self.assertRaisesRegex(CalculationError, message):
                evaluate_expression(expression)

    def test_ast_node_and_depth_limits(self):
        self.assertEqual(evaluate_expression("+" * 40 + "1"), Fraction(1))
        with self.assertRaisesRegex(CalculationError, "depth limit"):
            evaluate_expression("+" * 41 + "1")
        expression = " + ".join(["1"] * 80)
        with self.assertRaisesRegex(CalculationError, "200-node"):
            evaluate_expression(expression)

    def test_intermediate_fraction_size_is_bounded_before_later_cancellation(self):
        # Isolate the fraction bound by relaxing only the separately tested
        # text bound. The final ratio is one, but each product exceeds 4096 bits.
        base = "0." + "0" * 61 + "1"
        product = "*".join([base] * 20)
        expression = "(" + product + ")/(" + product + ")"
        with patch("calculator.MAX_TEXT_LENGTH", 3000):
            with self.assertRaisesRegex(CalculationError, "4096-bit"):
                evaluate_expression(expression)


if __name__ == "__main__":
    unittest.main()
