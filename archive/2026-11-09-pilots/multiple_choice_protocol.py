"""Independent exact-choice protocol: render options and score a selected label.

Fraction arithmetic is used only to validate the authored question bank. Model
responses are never evaluated as expressions or converted into numeric answers.
"""

from collections import Counter
from fractions import Fraction
import json
import math
import re

from experiment_config import MAX_TOKENS, MODEL


EXPERIMENT_ID = "mc-exact-v1"
LABELS = tuple("ABCDEFGHIJKLMNO")
COHORTS = {"syntax_reuse", "pilot_reuse"}
FAMILIES = {"reasoning", "evidence", "algebra", "units"}


def _canonical_fraction(text):
    if not isinstance(text, str) or not re.fullmatch(r"-?[0-9]{1,32}/[0-9]{1,32}", text):
        raise ValueError("Every authored value must be a reduced numerator/denominator fraction")
    try:
        value = Fraction(text)
    except (ValueError, ZeroDivisionError) as exc:
        raise ValueError("Invalid authored fraction") from exc
    if text != f"{value.numerator}/{value.denominator}":
        raise ValueError("Authored fractions must be reduced, with a positive denominator")
    return value


def validate_config(config):
    """Validate the independent, fixed sixteen-question design before inference."""
    if (not isinstance(config, dict)
            or type(config.get("schema_version")) is not int or config["schema_version"] != 1
            or config.get("experiment_id") != EXPERIMENT_ID
            or config.get("model") != MODEL or config.get("max_tokens") != MAX_TOKENS
            or config.get("temperature") != 0.7 or config.get("context_tokens") != 4096
            or config.get("explanation_word_limit") != 60 or config.get("option_count") != 15
            or not isinstance(config.get("system_prompt"), str) or not config["system_prompt"].strip()
            or not isinstance(config.get("tasks"), list) or len(config["tasks"]) != 16):
        raise ValueError("Unexpected fixed multiple-choice settings")
    ids, sources, counts, correct_positions = set(), set(), Counter(), Counter()
    for task in config["tasks"]:
        if (not isinstance(task, dict) or not isinstance(task.get("id"), str) or not task["id"]
                or task["id"] in ids or not isinstance(task.get("source_task_id"), str)
                or not task["source_task_id"] or task["source_task_id"] in sources
                or task["id"] != "mc-" + task["source_task_id"]
                or task.get("cohort") not in COHORTS or task.get("family") not in FAMILIES
                or type(task.get("seed")) is not int or type(task.get("probability")) is not bool
                or task["probability"] != (task["family"] in {"reasoning", "evidence"})
                or not isinstance(task.get("question"), str) or not task["question"].strip()
                or not isinstance(task.get("options"), list) or len(task["options"]) != len(LABELS)
                or task.get("correct_choice") not in LABELS):
            raise ValueError("Invalid or duplicate multiple-choice question")
        gold = _canonical_fraction(task.get("gold_fraction"))
        values = set()
        for expected_label, option in zip(LABELS, task["options"]):
            if (not isinstance(option, dict) or option.get("label") != expected_label
                    or not isinstance(option.get("rationale"), str) or not option["rationale"].strip()):
                raise ValueError("Options must have ordered labels A-O and author-facing rationales")
            value = _canonical_fraction(option.get("value"))
            if value in values:
                raise ValueError("Each option must have a mathematically distinct value")
            if task["probability"] and not 0 < value < 1:
                raise ValueError("This probability bank must use options strictly between zero and one")
            if not task["probability"] and value <= 0:
                raise ValueError("This bank's nonprobability options must be positive")
            if (option["label"] == task["correct_choice"]) != (value == gold):
                raise ValueError("Exactly the keyed option must match the exact reference")
            values.add(value)
        ids.add(task["id"])
        sources.add(task["source_task_id"])
        counts[(task["cohort"], task["family"])] += 1
        correct_positions[task["correct_choice"]] += 1
    if counts != Counter({(cohort, family): 2 for cohort in COHORTS for family in FAMILIES}):
        raise ValueError("Each reused cohort must have two questions per family")
    if set(correct_positions) != set(LABELS) or sorted(correct_positions.values()) != [1] * 14 + [2]:
        raise ValueError("Correct-answer positions must be balanced across the sixteen questions")


def build_messages(config, task):
    """Whitelist model-visible content; answer keys and author notes stay local."""
    options = "\n".join(f"{option['label']}. {option['value']}" for option in task["options"])
    question = task["question"] + "\n\nOptions (exact values):\n" + options
    question += "\n\nSelect exactly one option."
    return [{"role": "system", "content": config["system_prompt"]},
            {"role": "user", "content": question}]


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(text):
    raise ValueError(f"Nonfinite JSON value: {text}")


def _finite_float(text):
    value = float(text)
    if not math.isfinite(value):
        raise ValueError("Nonfinite JSON number")
    return value


def process_response(raw, task, max_explanation_words=60):
    """Score the original JSON choice without normalization, repairs, or tools.

    choice_correct records a valid, keyed selection independently of explanation
    delivery. Headline correct also requires both string fields. Extra fields
    and the explanation word limit are reported as secondary compliance flags.
    Explanations are retained for review; they are not automatically judged.
    """
    if type(max_explanation_words) is not int or max_explanation_words < 0:
        raise ValueError("max_explanation_words must be a nonnegative integer")
    result = {"json_valid": False, "required_fields_valid": False, "choice_valid": False,
              "choice_correct": False, "correct": False, "exact_two_fields": False,
              "within_explanation_bound": False, "explanation_word_count": None,
              "choice": None, "selected_fraction": None, "prediction": None, "parse_error": None}
    try:
        content = raw["message"]["content"]
        if not isinstance(content, str):
            raise ValueError("Model content must be a string")
        parsed = json.loads(content, object_pairs_hook=_unique_object,
                            parse_constant=_reject_constant, parse_float=_finite_float)
        if not isinstance(parsed, dict):
            raise ValueError("Prediction must be a JSON object")
    except (KeyError, TypeError, ValueError, RecursionError) as exc:
        result["parse_error"] = str(exc)
        return result
    result.update(json_valid=True, prediction=parsed,
                  exact_two_fields=set(parsed) == {"explanation", "choice"})
    explanation, choice = parsed.get("explanation"), parsed.get("choice")
    errors = []
    if isinstance(explanation, str):
        count = len(explanation.split())
        result.update(explanation_word_count=count, within_explanation_bound=count <= max_explanation_words)
    else:
        errors.append("Prediction needs a string explanation")
    if isinstance(choice, str):
        result["choice"] = choice
    else:
        errors.append("Prediction needs a string choice")
    result["required_fields_valid"] = isinstance(explanation, str) and isinstance(choice, str)
    options = {option["label"]: option["value"] for option in task["options"]}
    if isinstance(choice, str) and choice in options:
        result.update(choice_valid=True, selected_fraction=options[choice],
                      choice_correct=choice == task["correct_choice"])
    else:
        errors.append("Choice must be exactly one uppercase letter A-O")
    result["correct"] = result["required_fields_valid"] and result["choice_correct"]
    result["parse_error"] = "; ".join(errors) or None
    return result
