"""Post-generation scoring for the two frozen single-agent pilot appendices."""

import ast
from fractions import Fraction
import math

from benchmark import correct, probability
from local_llm import OllamaError, parse_prediction


def _expression_value(text):
    """Interpret the diagnostic's restricted arithmetic grammar without execution."""
    tree = ast.parse(text.strip(), mode="eval")
    if len(list(ast.walk(tree))) > 200 or not any(
            isinstance(node, ast.BinOp) for node in ast.walk(tree)):
        raise ValueError("Expected a short unevaluated arithmetic expression")

    def visit(node, depth=0):
        if depth > 40:
            raise ValueError("Expression nesting too deep")
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            if not math.isfinite(node.value) or abs(node.value) > 1000000:
                raise ValueError("Invalid or oversized number")
            return Fraction(str(node.value))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = visit(node.operand, depth + 1)
            return -value if isinstance(node.op, ast.USub) else value
        if isinstance(node, ast.BinOp):
            left, right = visit(node.left, depth + 1), visit(node.right, depth + 1)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                return left / right
        raise ValueError("Only arithmetic numbers and + - * / are accepted")

    return visit(tree.body)


def score_response(raw, task, pilot):
    """Score without inference; preserve each appendix's original answer contract.

    ``urn-check`` returns a float value and clears invalid predictions.
    ``diagnostic`` returns an exact fraction string and retains a parsed prediction
    when its answer violates the requested numeric or expression grammar.
    """
    if pilot not in ("urn-check", "diagnostic"):
        raise ValueError("pilot must be 'urn-check' or 'diagnostic'")
    result = {"prediction": None, "value": None, "format_valid": False,
              "correct": False, "absolute_error": None, "error": None,
              "check_label": False}
    if pilot == "urn-check":
        try:
            parsed = parse_prediction(raw)
            value = probability(parsed["final_answer"])
            if value is None:
                raise OllamaError("final_answer must be a fraction or decimal between 0 and 1")
            result.update(prediction=parsed, value=value, format_valid=True,
                          correct=correct(task, value),
                          absolute_error=abs(value - task["gold_probability"]),
                          check_label="math check" in parsed["explanation"].lower())
        except OllamaError as exc:
            result["error"] = str(exc)
        return result

    try:
        parsed = parse_prediction(raw)
        result["prediction"] = parsed
        result["check_label"] = "check:" in parsed["explanation"].lower()
        value = (_expression_value(parsed["final_answer"])
                 if task["answer_kind"] == "expression"
                 else Fraction(parsed["final_answer"].strip()))
        error = abs(value - Fraction(task["gold_fraction"]))
        result.update(value=str(value), format_valid=True,
                      correct=error <= Fraction(1, 1000), absolute_error=float(error))
    except (OllamaError, ValueError, SyntaxError, TypeError, ZeroDivisionError, OverflowError) as exc:
        result["error"] = str(exc)
    return result
