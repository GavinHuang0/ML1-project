"""Independent bank checks: semantic groups, exact references, and safe builds."""

from collections import Counter, defaultdict
from contextlib import redirect_stderr, redirect_stdout
import copy
from fractions import Fraction
import io
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

import build_full_benchmark as bank
from calculator import evaluate_expression
from multi_agent_protocol import build_messages, read_tasks


ROOT = Path(__file__).resolve().parents[1]


class FullBenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads(bank.DEFAULT_PATH.read_text(encoding="utf-8"))
        cls.tasks = cls.manifest["tasks"]

    def test_exact_family_partition_and_cluster_counts(self):
        self.assertEqual(len(self.tasks), 100)
        self.assertEqual(Counter(t["family"] for t in self.tasks), Counter({f: 25 for f in bank.FAMILIES}))
        self.assertEqual(Counter(t["split"] for t in self.tasks),
                         Counter(development=20, validation=40, test=40))
        expected = Counter({(f, s): (5 if s == "development" else 10)
                            for f in bank.FAMILIES for s in bank.PARTITIONS})
        self.assertEqual(Counter((t["family"], t["split"]) for t in self.tasks), expected)
        groups = defaultdict(list)
        for task in self.tasks:
            groups[task["group_id"]].append(task)
        self.assertEqual(len(groups), 52)
        group_counts = Counter(next(iter({t["split"] for t in variants})) for variants in groups.values())
        self.assertEqual(group_counts, Counter(development=12, validation=20, test=20))
        for family in bank.FAMILIES:
            for split in bank.PARTITIONS:
                sizes = sorted(len(ts) for ts in groups.values() if ts[0]["family"] == family and ts[0]["split"] == split)
                self.assertEqual(sizes, [1, 2, 2] if split == "development" else [2] * 5)

    def test_structural_templates_and_numeric_variants_do_not_cross_splits(self):
        templates = defaultdict(list)
        for task in self.tasks:
            templates[(task["family"], task["template_id"])].append(task)
        self.assertEqual(len(templates), 52)
        for (family, slug), tasks in templates.items():
            with self.subTest(family=family, template=slug):
                self.assertEqual(len({t["group_id"] for t in tasks}), 1)
                self.assertEqual(len({t["split"] for t in tasks}), 1)
                index = tasks[0]["template_index"]
                self.assertEqual(slug, bank.TEMPLATES[family][index][0])
                split = tasks[0]["split"]
                self.assertIn(index, bank.PARTITIONS[split])
                self.assertEqual(len({t["prompt"] for t in tasks}), len(tasks))
        for family in bank.FAMILIES:
            self.assertEqual({t["template_index"] for t in self.tasks if t["family"] == family}, set(range(13)))

    def test_inventory_describes_actual_groups_and_planned_difficulty(self):
        inventory = self.manifest["source"]["template_inventory"]
        self.assertEqual(len(inventory), 52)
        self.assertEqual(len({item["group_id"] for item in inventory}), 52)
        for item in inventory:
            tasks = [t for t in self.tasks if t["group_id"] == item["group_id"]]
            self.assertEqual(len(tasks), item["variants"])
            for task in tasks:
                self.assertEqual(task["difficulty"], item["planned_difficulty"])
                self.assertEqual(task["split"], item["split"])
                self.assertEqual(task["family"], item["family"])
        self.assertIn("never model outcomes", self.manifest["source"]["difficulty_policy"])
        self.assertIn("20 test clusters", self.manifest["source"]["uncertainty_unit"])

    def test_no_pilot_duplicates_and_all_metadata_stays_out_of_prompts(self):
        baseline = json.loads((ROOT / "config/baseline.json").read_text())
        pilot_prompts = {task["prompt"] for task in baseline["tasks"]}
        self.assertEqual(len({task["id"] for task in self.tasks}), 100)
        self.assertEqual(len({task["prompt"] for task in self.tasks}), 100)
        self.assertFalse(pilot_prompts & {task["prompt"] for task in self.tasks})
        for task in self.tasks:
            self.assertRegex(task["id"], r"^full-v1-(reasoning|evidence|algebra|units)-(development|validation|test)-\d\d$")
            altered = {**task, "parameters": {"secret": "PRIVATE_PARAMETERS_MARKER"},
                       "gold_fraction": "PRIVATE_REFERENCE_MARKER", "group_id": "PRIVATE_GROUP_MARKER"}
            sent = json.dumps(build_messages(altered, 0, 0))
            self.assertNotIn("PRIVATE_", sent)

    def test_manifest_is_protocol_compatible_and_generation_is_byte_exact(self):
        tasks, digest = read_tasks(bank.DEFAULT_PATH)
        self.assertEqual(tasks, self.tasks)
        self.assertEqual(len(digest), 64)
        first = bank.manifest_bytes(bank.generate_manifest())
        second = bank.manifest_bytes(bank.generate_manifest())
        self.assertEqual(first, second)
        self.assertEqual(first, bank.DEFAULT_PATH.read_bytes())

    def test_all_references_are_independently_verified_and_grammar_executable(self):
        for task in self.tasks:
            with self.subTest(task=task["id"]):
                gold = Fraction(task["gold_fraction"])
                self.assertEqual(bank.verify_reference(task), gold)
                self.assertEqual(evaluate_expression(task["parameters"]["reference_expression"]), gold)
                if task["probability"]:
                    self.assertTrue(0 < gold < 1)
                else:
                    self.assertEqual(task["family"] in {"algebra", "units"}, True)
        for family in bank.FAMILIES:
            task = copy.deepcopy(next(t for t in self.tasks if t["family"] == family))
            task["gold_fraction"] = str(Fraction(task["gold_fraction"]) + 1)
            # Changing the witness with the stored answer must not fool the independent check.
            task["parameters"]["reference_expression"] = task["gold_fraction"]
            with self.subTest(family=family), self.assertRaises(ValueError):
                bank.verify_reference(task)

    def test_urn_enumeration_does_not_depend_on_closed_form_combinations(self):
        tasks = [t for t in self.tasks if t["family"] == "reasoning"]
        with patch.object(bank.math, "comb", side_effect=AssertionError("Enumeration must not reuse combinations")):
            for task in tasks:
                self.assertEqual(bank.enumerate_urn(task), Fraction(task["gold_fraction"]))
                p = task["parameters"]
                opening = re.search(r"contains (\d+) red and (\d+) blue balls(?: and (\d+) green balls)?", task["prompt"])
                self.assertIsNotNone(opening)
                self.assertEqual(tuple(int(value or 0) for value in opening.groups()), (p["red"], p["blue"], p["green"]))
                self.assertIn(f"Draw {p['draws']} balls uniformly in order without replacement", task["prompt"])

    def test_sensor_prompt_rederivation_deduplicates_sources_and_handles_prior_odds(self):
        for task in [t for t in self.tasks if t["family"] == "evidence"]:
            prompt, p = task["prompt"], task["parameters"]
            if p["prior_representation"] == "odds":
                a, b = map(int, re.search(r"Prior odds Y=1 to Y=0 are (\d+):(\d+)", prompt).groups())
                prior = Fraction(a, a + b)
            else:
                prior = Fraction(re.search(r"P\(Y=1\) is ([0-9/]+);", prompt).group(1))
            observations = {}
            for source, value, reliability in re.findall(r"(S\d+): observation=([01]), reliability=([0-9/]+)", prompt):
                observation = int(value), Fraction(reliability)
                if source in observations:
                    self.assertEqual(observations[source], observation)
                observations[source] = observation
            self.assertTrue(1 <= len(observations) <= 4)
            masses = [1 - prior, prior]
            for value, reliability in observations.values():
                for state in (0, 1):
                    masses[state] *= reliability if value == state else 1 - reliability
            query = int(re.search(r"What is P\(Y=([01])", prompt).group(1))
            self.assertEqual(masses[query] / sum(masses), Fraction(task["gold_fraction"]))
        duplicates = [t for t in self.tasks if t["family"] == "evidence" and t["template_index"] in (7, 11)]
        self.assertEqual(len(duplicates), 4)
        changed = copy.deepcopy(duplicates[0])
        seen = set()
        for observation in changed["parameters"]["observations"]:
            if observation["source_id"] in seen:
                observation["observation"] = 1 - observation["observation"]
                break
            seen.add(observation["source_id"])
        with self.assertRaisesRegex(ValueError, "Contradictory"):
            bank.enumerate_sensor(changed)

    def test_algebra_references_satisfy_equations_and_include_fractional_answers(self):
        tasks = [t for t in self.tasks if t["family"] == "algebra"]
        self.assertTrue(any(Fraction(t["gold_fraction"]).denominator != 1 for t in tasks))
        for task in tasks:
            p, gold = task["parameters"], Fraction(task["gold_fraction"])
            a, b = bank.affine(p["equation_left"])
            c, d = bank.affine(p["equation_right"])
            self.assertNotEqual(a, c)
            self.assertEqual(a * gold + b, c * gold + d)
            equation = f"Solve {p['equation_left']} = {p['equation_right']} for x"
            if p["equation_visible"]:
                self.assertIn(equation, task["prompt"])
            else:
                self.assertNotIn(equation, task["prompt"])
                self.assertIn("Find x.", task["prompt"])
        for invalid in ("x*x", "1/x", "x**2", "__import__('os')"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                bank.affine(invalid)

    def test_units_dimensions_and_given_quantities_are_visible(self):
        for task in [t for t in self.tasks if t["family"] == "units"]:
            gold = Fraction(task["gold_fraction"])
            self.assertGreater(gold, 0)
            bank.verify_units(task, gold)
            with self.assertRaises(ValueError):
                bank.verify_units(task, gold + 1)
            for key, value in task["parameters"].items():
                if key != "reference_expression":
                    self.assertIn(str(value), task["prompt"])

    def test_cli_check_is_read_only_and_output_refuses_overwrite(self):
        before = bank.DEFAULT_PATH.read_bytes()
        with redirect_stdout(io.StringIO()):
            self.assertEqual(bank.main(["--check"]), 0)
        self.assertEqual(bank.DEFAULT_PATH.read_bytes(), before)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "new-bank.json"
            with redirect_stdout(io.StringIO()):
                self.assertEqual(bank.main(["--output", str(target)]), 0)
            self.assertEqual(target.read_bytes(), before)
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(bank.main(["--output", str(target)]), 1)
            self.assertEqual(target.read_bytes(), before)
            target.write_bytes(b"changed")
            with patch.object(bank, "DEFAULT_PATH", target), redirect_stderr(io.StringIO()):
                self.assertEqual(bank.main(["--check"]), 1)


if __name__ == "__main__":
    unittest.main()
