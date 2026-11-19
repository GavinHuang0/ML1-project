"""A bounded, exact arithmetic calculator with no model or task dependencies."""

import ast
from fractions import Fraction
import re


MAX_TEXT_LENGTH = 1000
MAX_AST_NODES = 200
MAX_DEPTH = 40
MAX_LITERAL_LENGTH = 64
MAX_LITERAL_ABSOLUTE_VALUE = 1000000
MAX_FRACTION_BITS = 4096
_LITERAL = re.compile(r"(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)\Z")


class CalculationError(ValueError):
    """An expression is unsupported, undefined, or exceeds a resource bound."""


def _bounded(value):
    if (value.numerator.bit_length() > MAX_FRACTION_BITS
            or value.denominator.bit_length() > MAX_FRACTION_BITS):
        raise CalculationError("Intermediate fraction exceeds the 4096-bit limit")
    return value


def evaluate_expression(text):
    """Evaluate numbers and +, -, *, / exactly, with parentheses and unary signs.

    Decimal values come from their original source spelling rather than Python's
    floating-point AST value. Names, function calls, and other Python syntax are
    never evaluated.
    """
    if not isinstance(text, str):
        raise CalculationError("Expression must be a string")
    if len(text) > MAX_TEXT_LENGTH:
        raise CalculationError("Expression exceeds the 1000-character limit")
    source = text.strip()
    if not re.fullmatch(r"[0-9.\s()+*/-]+", source):
        raise CalculationError("Use only numeric literals, parentheses, and arithmetic signs")
    try:
        tree = ast.parse(source, mode="eval")
    except (SyntaxError, ValueError, TypeError, RecursionError) as exc:
        raise CalculationError("Invalid arithmetic syntax") from exc
    if sum(1 for _ in ast.walk(tree)) > MAX_AST_NODES:
        raise CalculationError("Expression exceeds the 200-node limit")

    def visit(node, depth=0):
        if depth > MAX_DEPTH:
            raise CalculationError("Expression exceeds the depth limit of 40")
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            literal = ast.get_source_segment(source, node)
            if literal is None or len(literal) > MAX_LITERAL_LENGTH:
                raise CalculationError("Numeric literal exceeds the 64-character limit")
            if not _LITERAL.fullmatch(literal):
                raise CalculationError("Use plain integer or decimal literals")
            value = Fraction(literal)
            if abs(value) > MAX_LITERAL_ABSOLUTE_VALUE:
                raise CalculationError("Numeric literal absolute value exceeds 1000000")
            return _bounded(value)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = visit(node.operand, depth + 1)
            return _bounded(-value if isinstance(node.op, ast.USub) else value)
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
            left = visit(node.left, depth + 1)
            right = visit(node.right, depth + 1)
            if isinstance(node.op, ast.Add):
                value = left + right
            elif isinstance(node.op, ast.Sub):
                value = left - right
            elif isinstance(node.op, ast.Mult):
                value = left * right
            else:
                if right == 0:
                    raise CalculationError("Division by zero")
                value = left / right
            return _bounded(value)
        raise CalculationError("Only numeric literals, parentheses, +, -, *, /, and unary signs are supported")

    return visit(tree.body)
