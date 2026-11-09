"""Score answer completeness separately from arithmetic in the template pilot."""

from fractions import Fraction
import json

from local_llm import OllamaError, _decode_json, parse_prediction
from pilot_scoring import score_response as score_diagnostic_response


def score_response(raw, task, max_explanation_words=60):
    """Score the explicit final answer without recovering answers from prose.

    The primary format contract matches the diagnostic pilot: two required
    string fields and the task's numeric or restricted-expression grammar.
    Exact keys and explanation length are recorded as secondary compliance
    flags, so those prompt additions do not change the comparison's scoring.
    """
    if (isinstance(max_explanation_words, bool)
            or not isinstance(max_explanation_words, int) or max_explanation_words < 0):
        raise ValueError("max_explanation_words must be a nonnegative integer")
    result = {
        "json_valid": False, "required_fields_valid": False,
        "final_answer_valid": False, "numeric_correct": False,
        "format_valid": False, "correct": False,
        "explanation_words": None, "within_explanation_bound": False,
        "exact_two_fields": False, "prediction": None,
        "value": None, "absolute_error": None, "probability_in_range": None, "error": None,
    }
    try:
        parsed = _decode_json(raw["message"]["content"])
        if not isinstance(parsed, dict):
            raise ValueError("Prediction must be a JSON object")
    except (KeyError, TypeError, ValueError) as exc:
        result["error"] = str(exc)
        return result

    result.update(json_valid=True, prediction=parsed,
                  exact_two_fields=set(parsed) == {"final_answer", "explanation"})
    if isinstance(parsed.get("explanation"), str):
        words = len(parsed["explanation"].split())
        result.update(explanation_words=words,
                      within_explanation_bound=words <= max_explanation_words)
    try:
        parse_prediction(raw)
        result["required_fields_valid"] = True
    except OllamaError as exc:
        result["error"] = str(exc)

    # Supply only the scorer's required explanation field. This lets a correct
    # explicit final_answer count numerically even if the model omitted its
    # explanation; the original output still fails the primary format contract.
    final_only_raw = {"message": {"content": json.dumps({
        "final_answer": parsed.get("final_answer"), "explanation": "",
    }, allow_nan=False)}}
    final_score = score_diagnostic_response(final_only_raw, task, "diagnostic")
    final_valid = final_score["format_valid"]
    probability_in_range = None
    if final_valid and (task.get("probability") is True or task.get("family") == "reasoning"):
        probability_in_range = 0 <= Fraction(final_score["value"]) <= 1
    result.update(final_answer_valid=final_valid,
                  numeric_correct=final_valid and final_score["correct"] and probability_in_range is not False,
                  probability_in_range=probability_in_range,
                  value=final_score["value"], absolute_error=final_score["absolute_error"])
    result["format_valid"] = result["required_fields_valid"] and final_valid
    result["correct"] = result["format_valid"] and result["numeric_correct"]
    if result["error"] is None:
        result["error"] = final_score["error"]
    return result
