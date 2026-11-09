"""Offline checks for exact label scoring, never numerical-expression execution."""

import copy
import json
from pathlib import Path
import unittest

from multiple_choice_protocol import build_messages, process_response, validate_config


CONFIG = Path(__file__).resolve().parents[1] / "config" / "multiple_choice_experiment.json"


class MultipleChoiceProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = json.loads(CONFIG.read_text(encoding="utf-8"))
        cls.task = cls.config["tasks"][0]

    def score(self, payload):
        return process_response({"message": {"content": json.dumps(payload)}}, self.task)

    def test_correct_selection_requires_explanation_delivery_but_does_not_judge_its_reasoning(self):
        right = self.task["correct_choice"]
        score = self.score({"explanation": "This explanation is not automatically evaluated.", "choice": right})
        self.assertTrue(score["correct"])
        self.assertTrue(score["choice_correct"])
        self.assertEqual(score["selected_fraction"], self.task["gold_fraction"])
        missing = self.score({"choice": right})
        self.assertTrue(missing["choice_correct"])
        self.assertFalse(missing["required_fields_valid"])
        self.assertFalse(missing["correct"])

    def test_every_other_option_is_wrong_even_when_numerically_near_the_correct_one(self):
        for task in self.config["tasks"]:
            for option in task["options"]:
                with self.subTest(task=task["id"], choice=option["label"]):
                    raw = {"message": {"content": json.dumps({"explanation": "Selection.", "choice": option["label"]})}}
                    score = process_response(raw, task)
                    self.assertTrue(score["choice_valid"])
                    self.assertEqual(score["correct"], option["label"] == task["correct_choice"])
                    self.assertEqual(score["selected_fraction"], option["value"])

    def test_choice_is_not_normalized_or_replaced_by_a_number_in_explanation(self):
        right = self.task["correct_choice"]
        for invalid in (right.lower(), " " + right, right + " ", right + ".", "Answer: " + right,
                        self.task["gold_fraction"], [right], 1, None, "", "P", right + ", A"):
            with self.subTest(choice=invalid):
                score = self.score({"explanation": self.task["gold_fraction"], "choice": invalid})
                self.assertFalse(score["choice_valid"])
                self.assertFalse(score["correct"])
                self.assertIsNone(score["selected_fraction"])

    def test_word_bound_and_extra_keys_are_secondary(self):
        score = self.score({"explanation": " ".join(["word"] * 61),
                            "choice": self.task["correct_choice"], "extra": "retained"})
        self.assertTrue(score["correct"])
        self.assertFalse(score["exact_two_fields"])
        self.assertFalse(score["within_explanation_bound"])
        self.assertEqual(score["explanation_word_count"], 61)

    def test_strict_json_rejects_duplicate_keys_nonfinite_values_and_surrounding_prose(self):
        right = self.task["correct_choice"]
        texts = ["[]", "null", "```json\n{}\n```", 'prefix {"choice":"' + right + '"}',
                 '{"choice":"A","choice":"' + right + '","explanation":"x"}',
                 '{"choice":"' + right + '","explanation":"x","extra":NaN}',
                 '{"choice":"' + right + '","explanation":"x","extra":1e9999}']
        for text in texts:
            with self.subTest(text=text):
                score = process_response({"message": {"content": text}}, self.task)
                self.assertFalse(score["json_valid"])
                self.assertFalse(score["correct"])
                self.assertIsNotNone(score["parse_error"])

    def test_missing_transport_fields_and_nonstrings_are_invalid(self):
        for raw in ({}, {"message": {}}, {"message": None}, {"message": {"content": {}}}):
            self.assertFalse(process_response(raw, self.task)["correct"])
        for limit in (True, -1, 1.5):
            with self.assertRaises(ValueError):
                process_response({}, self.task, max_explanation_words=limit)

    def test_renderer_uses_only_prompt_question_and_option_labels_values(self):
        task = copy.deepcopy(self.task)
        task["author_secret"] = "DO NOT SEND THIS KEY"
        task["correct_choice"] = "DO NOT SEND THIS ANSWER KEY"
        task["gold_fraction"] = "DO NOT SEND THIS REFERENCE"
        for option in task["options"]:
            option["rationale"] = "DO NOT SEND THIS DISTRACTOR EXPLANATION"
        messages = build_messages(self.config, task)
        expected = task["question"] + "\n\nOptions (exact values):\n"
        expected += "\n".join(f"{o['label']}. {o['value']}" for o in task["options"])
        expected += "\n\nSelect exactly one option."
        self.assertEqual(messages, [{"role": "system", "content": self.config["system_prompt"]},
                                    {"role": "user", "content": expected}])
        self.assertNotIn("DO NOT SEND", json.dumps(messages))

    def test_validation_rejects_ambiguous_options_inconsistent_key_and_wrong_settings(self):
        mutations = {
            "duplicate_value": lambda c: c["tasks"][0]["options"][1].update(value=c["tasks"][0]["options"][0]["value"]),
            "nonreduced": lambda c: c["tasks"][0]["options"][0].update(value="2/4"),
            "zero_denominator": lambda c: c["tasks"][0]["options"][0].update(value="1/0"),
            "wrong_key": lambda c: c["tasks"][0].update(correct_choice="P"),
            "wrong_reference": lambda c: c["tasks"][0].update(gold_fraction="1/100000"),
            "bad_label": lambda c: c["tasks"][0]["options"][0].update(label="Z"),
            "duplicate_id": lambda c: c["tasks"][1].update(id=c["tasks"][0]["id"]),
            "bad_seed": lambda c: c["tasks"][0].update(seed=True),
            "other_model": lambda c: c.update(model="qwen2.5:3b"),
            "other_cap": lambda c: c.update(max_tokens=512),
            "other_protocol": lambda c: c.update(experiment_id="planner-calculator-v1"),
        }
        validate_config(self.config)
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                changed = copy.deepcopy(self.config)
                mutate(changed)
                with self.assertRaises(ValueError):
                    validate_config(changed)
        with self.assertRaises(ValueError):
            validate_config([])


if __name__ == "__main__":
    unittest.main()
