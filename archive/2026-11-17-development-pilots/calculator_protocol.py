"""Score a model's explicit plan separately from execution by a local calculator."""

import ast
from fractions import Fraction
import math

from calculator import CalculationError, MAX_TEXT_LENGTH, evaluate_expression
from experiment_config import PROBABILITY_ROUNDOFF, PROBABILITY_TOLERANCE
from local_llm import _decode_json


SYSTEM = (
    "Solve the user's problem by constructing one arithmetic expression. "
    "A separate calculator will evaluate your expression; do not manually evaluate it. "
    "Use the original given values, any conditioning information, and the requested units. "
    "Use standard unit-conversion constants when needed. "
    "Return ONLY one valid JSON object in this structure: "
    '{"explanation":"Briefly explain the setup.","expression":"Unevaluated arithmetic expression"}. '
    "Both fields must be strings. Keep explanation to at most 60 words. "
    "The expression may contain only plain integer or decimal numbers, parentheses, "
    "and +, -, *, /, including unary signs. Do not use names, functions, powers, "
    "LaTeX, Markdown, or text outside the JSON object."
)


def _has_arithmetic_operation(expression):
    """Record a binary arithmetic operation without running model-generated code."""
    if len(expression) > MAX_TEXT_LENGTH:
        return False
    try:
        tree = ast.parse(expression.strip(), mode="eval")
        return any(isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div))
                   for node in ast.walk(tree))
    except (SyntaxError, ValueError, TypeError, RecursionError):
        return False


def _finite_decimal(value):
    try:
        decimal = float(value)
        return decimal if math.isfinite(decimal) else None
    except (OverflowError, ValueError):
        return None


def process_response(raw, task, max_explanation_words=60):
    """Read only the explicit expression and execute it once, without repairs.

    Required strings and a calculator-supported expression define the primary
    method format. Extra keys, the explanation bound, and the presence of a
    binary arithmetic operation are secondary flags. A literal correct answer
    is therefore deliverable, but does not establish correct problem setup.

    Numeric correctness is recorded even when the model omitted explanation.
    The calculator receives only the expression; task gold is used afterward.
    """
    if (isinstance(max_explanation_words, bool) or not isinstance(max_explanation_words, int)
            or max_explanation_words < 0):
        raise ValueError("max_explanation_words must be a nonnegative integer")
    result = {
        "json_valid": False, "required_fields_valid": False, "method_format_valid": False,
        "exact_two_fields": False, "explanation_words": None, "within_explanation_bound": False,
        "prediction": None, "expression": None, "has_arithmetic_operation": False,
        "calculator_attempted": False, "calculator_success": False,
        "computed_fraction": None, "computed_decimal": None, "absolute_error": None,
        "probability_in_range": None, "numeric_correct": False, "correct": False,
        "parse_error": None, "calculator_error": None, "scoring_error": None, "error": None,
    }
    try:
        parsed = _decode_json(raw["message"]["content"])
        if not isinstance(parsed, dict):
            raise ValueError("Prediction must be a JSON object")
    except (KeyError, TypeError, ValueError) as exc:
        result.update(parse_error=str(exc), error=str(exc))
        return result

    result.update(json_valid=True, prediction=parsed,
                  exact_two_fields=set(parsed) == {"explanation", "expression"})
    explanation, expression = parsed.get("explanation"), parsed.get("expression")
    explanation_valid = isinstance(explanation, str)
    expression_valid = isinstance(expression, str) and bool(expression.strip())
    if explanation_valid:
        count = len(explanation.split())
        result.update(explanation_words=count, within_explanation_bound=count <= max_explanation_words)
    if isinstance(expression, str):
        result["expression"] = expression
        result["has_arithmetic_operation"] = _has_arithmetic_operation(expression)
    result["required_fields_valid"] = explanation_valid and expression_valid
    if not explanation_valid:
        result["parse_error"] = "Prediction needs a string explanation"
    if not expression_valid:
        detail = "Prediction needs a nonempty string expression"
        result["parse_error"] = ((result["parse_error"] + "; " + detail) if result["parse_error"] else detail)
        result["error"] = result["parse_error"]
        return result

    result["calculator_attempted"] = True
    try:
        # This is the only calculator invocation. Gold, prompt, and task are not
        # passed to it, and an unsupported expression is never rewritten.
        value = evaluate_expression(expression)
    except CalculationError as exc:
        result.update(calculator_error=str(exc), error=result["parse_error"] or str(exc))
        return result
    result.update(calculator_success=True, method_format_valid=result["required_fields_valid"],
                  computed_fraction=str(value), computed_decimal=_finite_decimal(value))
    is_probability = task.get("probability") is True or task.get("family") in {"reasoning", "evidence"}
    if is_probability:
        result["probability_in_range"] = 0 <= value <= 1
    try:
        if task.get("gold_fraction") is not None:
            error = abs(value - Fraction(task["gold_fraction"]))
            within_tolerance = error <= Fraction(str(PROBABILITY_TOLERANCE))
            result["absolute_error"] = _finite_decimal(error)
        else:
            gold = task["gold_probability"]
            if isinstance(gold, bool) or not isinstance(gold, (int, float)) or not math.isfinite(gold):
                raise ValueError("gold_probability must be finite and numeric")
            decimal = result["computed_decimal"]
            error = abs(decimal - gold) if decimal is not None else None
            within_tolerance = error is not None and error <= PROBABILITY_TOLERANCE + PROBABILITY_ROUNDOFF
            result["absolute_error"] = error
        result["numeric_correct"] = within_tolerance and result["probability_in_range"] is not False
        result["correct"] = result["method_format_valid"] and result["numeric_correct"]
    except (KeyError, ValueError, TypeError, ZeroDivisionError, OverflowError) as exc:
        result["scoring_error"] = str(exc)
    result["error"] = result["parse_error"] or result["calculator_error"] or result["scoring_error"]
    return result
