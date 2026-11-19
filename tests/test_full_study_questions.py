"""Ensure the inspection exports contain every exact prompt and no answer key."""

from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


class FullStudyQuestionExportTests(unittest.TestCase):
    def test_json_contains_all_hundred_prompts_and_only_public_question_fields(self):
        source = (ROOT / "config/full_benchmark.json").read_bytes()
        tasks = json.loads(source)["tasks"]
        export = json.loads((ROOT / "docs/FULL_STUDY_QUESTIONS.json").read_text(encoding="utf-8"))
        self.assertEqual(export["source_sha256"], hashlib.sha256(source).hexdigest())
        self.assertEqual(len(export["questions"]), 100)
        self.assertEqual({question["id"] for question in export["questions"]}, {task["id"] for task in tasks})
        lookup = {task["id"]: task for task in tasks}
        fields = {"id", "group_id", "family", "split", "probability", "prompt"}
        for question in export["questions"]:
            self.assertEqual(set(question), fields)
            self.assertEqual(question, {key: lookup[question["id"]][key] for key in fields})
        self.assertEqual(Counter(q["split"] for q in export["questions"]),
                         {"development": 20, "validation": 40, "test": 40})
        self.assertEqual(len({q["group_id"] for q in export["questions"]}), 52)

    def test_markdown_has_one_verbatim_prompt_for_every_question(self):
        tasks = json.loads((ROOT / "config/full_benchmark.json").read_text(encoding="utf-8"))["tasks"]
        text = (ROOT / "docs/FULL_STUDY_QUESTIONS.md").read_text(encoding="utf-8")
        records = re.findall(r"#### (\d+)\. ([^\n]+)\n.*?```text\n(.*?)\n```", text, re.S)
        self.assertEqual([int(number) for number, _, _ in records], list(range(1, 101)))
        self.assertEqual({identifier: prompt for _, identifier, prompt in records},
                         {task["id"]: task["prompt"] for task in tasks})


if __name__ == "__main__":
    unittest.main()
