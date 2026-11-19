"""Independent reference and isolation checks for the sole active baseline."""

import ast
from collections import Counter
import copy
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "archive" / "2026-11-09-pilots"
SOURCE = ARCHIVE / "config" / "calculator_syntax_experiment.json"
BANK = ROOT / "config" / "baseline.json"


def derive_reference(task):
    """Derive exact answers from question text without any experiment scorer."""
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
            raise AssertionError("Missing sensor prior")
        prior = Fraction(prior_match.group(1))
        observations = {}
        for source, value, reliability in re.findall(
                r"(S\d+): observation=([01]), reliability=([0-9.]+)", prompt):
            reading = (int(value), Fraction(reliability))
            if source in observations and observations[source] != reading:
                raise AssertionError("Conflicting repeated sensor ID")
            observations[source] = reading
        if not observations:
            raise AssertionError("Missing sensor observations")
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
            raise AssertionError("Unrecognized speed/time question")
        speed, minutes = map(int, match.groups())
        return Fraction(speed * minutes, 60)
    raise AssertionError("Unexpected baseline question family")


class BaselineBankTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = json.loads(SOURCE.read_text(encoding="utf-8"))
        cls.bank = json.loads(BANK.read_text(encoding="utf-8"))

    def test_original_prompt_and_fixed_execution_settings_are_preserved(self):
        self.assertEqual(self.bank["experiment_id"], "calculator-baseline-v1")
        self.assertEqual(self.bank["execution_protocol"], "planner-calculator-v1")
        self.assertEqual(self.bank["system_prompt"], self.source["prompts"]["baseline"])
        self.assertEqual(self.bank["source"]["path"], SOURCE.relative_to(ROOT).as_posix())
        self.assertEqual(self.bank["source"]["sha256"], hashlib.sha256(SOURCE.read_bytes()).hexdigest())
        self.assertEqual(self.bank["source"]["condition"], "baseline")
        for key, expected in {"model": "llama3.2:3b", "max_tokens": 1024,
                              "temperature": 0.7, "context_tokens": 4096,
                              "explanation_word_limit": 60}.items():
            with self.subTest(setting=key):
                self.assertEqual(self.bank[key], expected)
                self.assertEqual(self.bank[key], self.source[key])
        self.assertNotIn("prompts", self.bank)
        self.assertNotIn("call_order", self.bank)

    def test_sixteen_original_tasks_and_metadata_survive_consolidation_in_order(self):
        tasks = self.bank["tasks"]
        self.assertEqual(len(tasks), 16)
        self.assertEqual(len({task["id"] for task in tasks}), 16)
        self.assertEqual(len({task["source_task_id"] for task in tasks}), 16)
        for index, (task, source) in enumerate(zip(tasks, self.source["tasks"]), start=1):
            with self.subTest(task=task["id"]):
                expected = copy.deepcopy(source)
                expected["id"] = f"baseline-{index:02d}"
                expected["split"] = "inspected_development"
                if "source_task_id" in source:
                    expected["original_source_task_id"] = source["source_task_id"]
                expected["source_task_id"] = source["id"]
                expected["cohort"] = "syntax_reuse" if source["split"] == "fresh" else "pilot_reuse"
                self.assertEqual(task, expected)

    def test_references_match_independent_combinatorial_likelihood_algebra_and_unit_calculations(self):
        for task in self.bank["tasks"]:
            with self.subTest(task=task["id"]):
                reference = derive_reference(task)
                self.assertEqual(reference, Fraction(task["gold_fraction"]))
                if "gold_probability" in task:
                    self.assertAlmostEqual(float(reference), task["gold_probability"], places=14)
                if task["probability"]:
                    self.assertGreaterEqual(reference, 0)
                    self.assertLessEqual(reference, 1)

    def test_family_cohort_and_development_labels_are_explicit(self):
        tasks = self.bank["tasks"]
        self.assertEqual(Counter(task["family"] for task in tasks),
                         {"reasoning": 4, "evidence": 4, "algebra": 4, "units": 4})
        self.assertEqual(Counter(task["cohort"] for task in tasks), {"syntax_reuse": 8, "pilot_reuse": 8})
        self.assertEqual(Counter((task["cohort"], task["family"]) for task in tasks),
                         {(cohort, family): 2 for cohort in ("syntax_reuse", "pilot_reuse")
                          for family in ("reasoning", "evidence", "algebra", "units")})
        self.assertTrue(all(task["split"] == "inspected_development" for task in tasks))
        self.assertTrue(all(task["answer_kind"] == "expression" for task in tasks))

    def test_baseline_policy_allows_one_reference_free_execution_without_repairs(self):
        self.assertEqual(self.bank["calculator_policy"], {
            "model_calls_per_item": 1, "calculator_calls_per_valid_expression": 1,
            "reference_free": True, "feedback_to_model": False,
            "repairs": False, "retries": False, "scoring_tolerance": "0.001",
        })

    def test_historical_reference_selects_original_records_without_claiming_a_new_run(self):
        reference = json.loads((ROOT / "results" / "baseline" / "HISTORICAL_REFERENCE.json")
                               .read_text(encoding="utf-8"))
        self.assertEqual(reference["record_type"], "historical_reference_selection")
        self.assertIs(reference["model_inference_performed_for_consolidation"], False)
        self.assertEqual(reference["baseline_protocol"], self.bank["experiment_id"])
        self.assertEqual(reference["execution_protocol"], self.bank["execution_protocol"])
        self.assertEqual(reference["configuration_sha256"], hashlib.sha256(BANK.read_bytes()).hexdigest())
        self.assertEqual(reference["source"]["condition"], "baseline")
        raw_path = ROOT / reference["source"]["raw"]
        self.assertTrue(raw_path.resolve().is_relative_to(ARCHIVE.resolve()))
        data = raw_path.read_bytes()
        self.assertEqual(reference["source"]["raw_sha256"], hashlib.sha256(data).hexdigest())
        rows = [json.loads(line) for line in data.decode("utf-8").splitlines()]
        self.assertEqual(rows[0]["experiment_id"], reference["source"]["original_experiment_id"])
        self.assertEqual(rows[-1]["type"], "complete")
        baseline = [row for row in rows[1:-1] if row["condition"] == "baseline"]
        self.assertEqual(len(baseline), 16)
        by_source = {row["task"]["id"]: row for row in baseline}
        self.assertEqual(set(by_source), {task["source_task_id"] for task in self.bank["tasks"]})
        self.assertEqual(len(reference["cases"]), 16)
        family_counts = {}
        for case, task in zip(reference["cases"], self.bank["tasks"]):
            with self.subTest(task=task["id"]):
                original = by_source[task["source_task_id"]]
                score = original["score"]
                self.assertEqual(original["messages"], [
                    {"role": "system", "content": self.bank["system_prompt"]},
                    {"role": "user", "content": task["prompt"]},
                ])
                self.assertEqual(case, {
                    "baseline_task_id": task["id"], "source_task_id": task["source_task_id"],
                    "seed": original["seed"], "expression": score["expression"],
                    "computed_fraction": score["computed_fraction"],
                    "calculator_success": score["calculator_success"], "correct": score["correct"],
                })
                self.assertEqual(case["seed"], task["seed"])
                group = family_counts.setdefault(task["family"], {"items": 0, "calculator_success": 0, "correct": 0})
                group["items"] += 1
                group["calculator_success"] += score["calculator_success"]
                group["correct"] += score["correct"]
        overall = {key: sum(group[key] for group in family_counts.values())
                   for key in ("items", "calculator_success", "correct")}
        self.assertEqual(overall, {"items": 16, "calculator_success": 11, "correct": 7})
        self.assertEqual(reference["overall"], overall)
        self.assertEqual(reference["families"], family_counts)


class ActiveSeparationTests(unittest.TestCase):
    def test_only_declared_current_and_provenance_pinned_commands_and_banks_exist(self):
        self.assertEqual({path.name for path in ROOT.glob("run_*.py")},
                         {"run_multi_agent.py", "run_full_experiment.py",
                          "run_followup_pilot.py", "run_format_followup.py", "run_communication_pilot.py",
                          "run_communication_recovery.py", "run_offline_comparison.py",
                          "run_confirmation_pilot.py", "run_five_agent_pilot.py", "run_sparse_peer_pilot.py"})
        self.assertEqual({path.name for path in (ROOT / "config").glob("*.json")},
                         {"baseline.json", "models.json", "multi_agent.json", "multi_agent_pilot.json",
                          "full_benchmark.json", "full_experiment.json", "followup_pilot.json",
                          "format_followup.json", "format_followup_tasks.json", "communication_pilot.json",
                          "communication_recovery.json", "offline_policy_comparison.json",
                          "confirmation_pilot.json", "confirmation_environment.json",
                          "five_agent_pilot.json", "sparse_peer_pilot.json", "full_study_v2.json"})

    def test_active_modules_do_not_import_archived_or_retired_approaches(self):
        active_paths = [*ROOT.glob("*.py"), *(ROOT / "experiments").rglob("*.py"),
                        *(ROOT / "tools").rglob("*.py")]
        active = {path.stem for path in active_paths}
        retired = {path.stem for path in ARCHIVE.glob("*.py")} - active
        self.assertTrue((ROOT / "experiments/baseline/runner.py").is_file())
        self.assertTrue(retired)
        for path in active_paths:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            imports = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports.append(node.module)
            for name in imports:
                with self.subTest(module=path.name, imported=name):
                    first = name.split(".", 1)[0]
                    self.assertNotEqual(first, "archive")
                    self.assertNotIn(first, retired)


if __name__ == "__main__":
    unittest.main()
