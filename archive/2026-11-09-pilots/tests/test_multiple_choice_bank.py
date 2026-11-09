"""Independent exact-reference and public-text checks for the frozen MC bank.

These tests read JSON only; runner tests separately inspect actual model requests.
"""

from collections import Counter
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = ROOT / "config" / "calculator_syntax_experiment.json"
BANK_PATH = ROOT / "config" / "multiple_choice_experiment.json"
LABELS = list("ABCDEFGHIJKLMNO")
LEGACY_SUFFIXES = (
    " Return an unevaluated arithmetic expression for x in expression.",
    " Return an unevaluated arithmetic expression for the distance in kilometres in expression.",
)


def derive_reference(task):
    """Derive the answer from mathematical question text, never stored gold."""
    prompt = task["prompt"]
    if task["family"] == "reasoning":
        match = re.search(r"An urn has (\d+) red and (\d+) blue balls\.", prompt)
        if match is None:
            raise AssertionError("Unrecognized urn question")
        red, blue = map(int, match.groups())
        denominator = math.comb(red + blue, 2)
        if "Given that at least one ball is red" in prompt:
            denominator -= math.comb(blue, 2)
        return Fraction(math.comb(red, 2), denominator)
    if task["family"] == "evidence":
        prior_match = re.search(r"prior probability ([0-9]+(?:\.[0-9]+)?)", prompt)
        if prior_match is None:
            raise AssertionError("Missing stated sensor prior")
        prior = Fraction(prior_match.group(1))
        observations = {}
        for source, value, reliability in re.findall(
                r"(S\d+): observation=([01]), reliability=([0-9.]+)", prompt):
            reading = (int(value), Fraction(reliability))
            if source in observations and observations[source] != reading:
                raise AssertionError("Conflicting repeated sensor ID")
            observations[source] = reading
        if not observations:
            raise AssertionError("No sensor observations")
        joint_one, joint_zero = prior, 1 - prior
        for value, reliability in observations.values():
            joint_one *= reliability if value == 1 else 1 - reliability
            joint_zero *= reliability if value == 0 else 1 - reliability
        return joint_one / (joint_one + joint_zero)
    if task["family"] == "algebra":
        match = re.search(r"Solve (.+?) = (.+?) for x\.", prompt)
        if match is None:
            raise AssertionError("Unrecognized linear equation")

        def linear_side(text):
            text = text.replace(" ", "")
            if re.fullmatch(r"[+-]?\d+", text):
                return 0, int(text)
            term = re.fullmatch(r"([+-]?\d+)\*x([+-]\d+)?", text)
            if term is None:
                raise AssertionError("Unrecognized linear expression")
            return int(term.group(1)), int(term.group(2) or "0")

        left_x, left_constant = linear_side(match.group(1))
        right_x, right_constant = linear_side(match.group(2))
        return Fraction(right_constant - left_constant, left_x - right_x)
    if task["family"] == "units":
        match = re.search(r"constant speed of (\d+) kilometres per hour for (\d+) minutes", prompt)
        if match is None:
            raise AssertionError("Unrecognized speed and time question")
        speed, minutes = map(int, match.groups())
        return Fraction(speed * minutes, 60)
    raise AssertionError("Unexpected question family")


def mathematical_question(prompt):
    for suffix in LEGACY_SUFFIXES:
        if prompt.endswith(suffix):
            return prompt[:-len(suffix)]
    return prompt


class MultipleChoiceBankTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = json.loads(SOURCE_PATH.read_text(encoding="utf-8"))
        cls.bank = json.loads(BANK_PATH.read_text(encoding="utf-8"))
        cls.sources = {task["id"]: task for task in cls.source["tasks"]}

    def test_all_sixteen_source_references_match_independent_question_calculations(self):
        self.assertEqual(len(self.sources), 16)
        self.assertEqual(Counter(task["family"] for task in self.sources.values()),
                         {"reasoning": 4, "evidence": 4, "algebra": 4, "units": 4})
        for task in self.sources.values():
            with self.subTest(task=task["id"]):
                self.assertEqual(derive_reference(task), Fraction(task["gold_fraction"]))

    def test_bank_covers_each_source_once_and_records_the_frozen_source_hash(self):
        tasks = self.bank["tasks"]
        self.assertEqual(len(tasks), 16)
        self.assertEqual(len({task["id"] for task in tasks}), 16)
        self.assertEqual(Counter(task["source_task_id"] for task in tasks), Counter(self.sources.keys()))
        self.assertEqual(self.bank["source"]["sha256"], hashlib.sha256(SOURCE_PATH.read_bytes()).hexdigest())
        self.assertEqual(self.bank["source"]["path"], str(SOURCE_PATH.relative_to(ROOT)))
        self.assertEqual(self.bank["model"], "llama3.2:3b")
        self.assertEqual(self.bank["max_tokens"], 1024)
        self.assertEqual(self.bank["option_count"], 15)

    def test_mathematical_questions_and_sampling_seeds_are_preserved(self):
        for task in self.bank["tasks"]:
            with self.subTest(task=task["id"]):
                source = self.sources[task["source_task_id"]]
                self.assertEqual(task["id"], "mc-" + source["id"])
                self.assertEqual(task["question"], mathematical_question(source["prompt"]))
                self.assertEqual(task["family"], source["family"])
                self.assertIs(task["probability"], source["probability"])
                self.assertEqual(task["seed"], source["seed"])
                self.assertIs(type(task["seed"]), int)
                self.assertEqual(task["cohort"], "syntax_reuse" if source["split"] == "fresh" else "pilot_reuse")
        self.assertEqual(Counter(task["cohort"] for task in self.bank["tasks"]),
                         {"syntax_reuse": 8, "pilot_reuse": 8})

    def test_each_option_list_has_fifteen_distinct_canonical_fractions(self):
        for task in self.bank["tasks"]:
            with self.subTest(task=task["id"]):
                self.assertEqual([option["label"] for option in task["options"]], LABELS)
                values = []
                for option in task["options"]:
                    value = option["value"]
                    self.assertRegex(value, r"^-?(?:0|[1-9][0-9]*)/[1-9][0-9]*$")
                    rational = Fraction(value)
                    self.assertEqual(value, f"{rational.numerator}/{rational.denominator}")
                    self.assertIsInstance(option["rationale"], str)
                    self.assertTrue(option["rationale"].strip())
                    values.append(rational)
                self.assertEqual(len(values), 15)
                self.assertEqual(len(set(values)), 15)

    def test_exactly_one_option_matches_independent_reference_and_correct_label(self):
        for task in self.bank["tasks"]:
            with self.subTest(task=task["id"]):
                reference = derive_reference(self.sources[task["source_task_id"]])
                self.assertEqual(task["gold_fraction"], f"{reference.numerator}/{reference.denominator}")
                matches = [option["label"] for option in task["options"] if Fraction(option["value"]) == reference]
                self.assertEqual(matches, [task["correct_choice"]])

    def test_every_probability_option_is_in_the_probability_range(self):
        for task in self.bank["tasks"]:
            if task["probability"]:
                with self.subTest(task=task["id"]):
                    for option in task["options"]:
                        self.assertGreaterEqual(Fraction(option["value"]), 0)
                        self.assertLessEqual(Fraction(option["value"]), 1)

    def test_correct_positions_are_balanced_and_options_are_not_magnitude_sorted(self):
        counts = Counter(task["correct_choice"] for task in self.bank["tasks"])
        self.assertEqual(set(counts), set(LABELS))
        self.assertEqual(sorted(counts.values()), [1] * 14 + [2])
        for task in self.bank["tasks"]:
            with self.subTest(task=task["id"]):
                values = [Fraction(option["value"]) for option in task["options"]]
                self.assertNotEqual(values, sorted(values))
                self.assertNotEqual(values, sorted(values, reverse=True))

    def test_model_facing_question_and_template_text_has_no_author_only_metadata(self):
        template = self.bank["system_prompt"]
        self.assertIsInstance(template, str)
        private_keys = ("correct_choice", "gold_fraction", "rationale", "source_task_id", "cohort")
        for task in self.bank["tasks"]:
            with self.subTest(task=task["id"]):
                # Actual rendering is tested by the runner owner. Here the JSON
                # fields available for display must contain only public text.
                public_text = template + "\n" + task["question"] + "\n" + "\n".join(
                    f"{option['label']}: {option['value']}" for option in task["options"])
                for key in private_keys:
                    self.assertNotIn(key, public_text)
                self.assertNotIn(task["id"], public_text)
                self.assertNotIn(task["source_task_id"], public_text)
                for option in task["options"]:
                    if option["rationale"] != "correct":
                        self.assertNotIn(option["rationale"], public_text)


if __name__ == "__main__":
    unittest.main()
