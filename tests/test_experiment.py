"""Exact benchmark checks and full pilot output tests using simulated inference."""

import argparse
from contextlib import redirect_stdout, redirect_stderr
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from benchmark import correct, ensemble, make_tasks, posterior, probability
from local_llm import OllamaError
import run_experiment as experiment


class BenchmarkTests(unittest.TestCase):
    def test_bayesian_reference_is_duplicate_invariant(self):
        clue = {"id": "A", "value": 1, "reliability": 0.9}
        self.assertAlmostEqual(posterior([clue]), 0.9)
        self.assertAlmostEqual(posterior([clue] * 5), 0.9)
        opposite = {"id": "B", "value": 0, "reliability": 0.9}
        self.assertAlmostEqual(posterior([clue, opposite]), 0.5)
        with self.assertRaises(ValueError):
            posterior([clue, {**clue, "value": 0}])

    def test_generated_reasoning_reference_matches_direct_counting(self):
        import re
        import math
        for task in make_tasks(40):
            if task["family"] != "reasoning":
                continue
            red, blue = map(int, re.findall(r"(\d+) (?:red|blue)", task["prompt"]))
            total_pairs = math.comb(red + blue, 2)
            red_pairs = math.comb(red, 2)
            denominator = total_pairs - math.comb(blue, 2) if "Given" in task["prompt"] else total_pairs
            self.assertAlmostEqual(task["gold_probability"], red_pairs / denominator)
        self.assertEqual(make_tasks(8, 77), make_tasks(8, 77))
        self.assertNotEqual(make_tasks(8, 77), make_tasks(8, 78))

    def test_probability_parsing_and_tied_votes(self):
        self.assertEqual(probability("3/4"), 0.75)
        for value in ["NaN", "Infinity", "0/0", "1.1", "-0.1", "answer is 0.5"]:
            self.assertIsNone(probability(value))
        task = {"family": "reasoning", "gold_probability": 0.75}
        self.assertTrue(ensemble(task, [0.75, 0.75, 0.1])["correct"])
        self.assertTrue(ensemble(task, [0.75, 0.1, None])["abstained"])
        self.assertFalse(correct(task, None))

    def test_correction_corruption_decomposition(self):
        task = {"family": "reasoning", "gold_probability": 0.5}
        before = [{"probability": value} for value in [0.5, 0.1, 0.2]]
        after = [{"probability": value} for value in [0.1, 0.5, 0.5]]
        metrics = experiment.evaluate(task, after, before)
        delta = (sum(metrics["individual_correct"]) - sum(correct(task, r["probability"]) for r in before)) / 3
        self.assertAlmostEqual(metrics["G"] - metrics["H"], delta)
        self.assertAlmostEqual(metrics["G"], 2 / 3)
        self.assertAlmostEqual(metrics["H"], 1 / 3)

    def test_single_vote_uses_original_value_at_tolerance_boundary(self):
        task = {"family": "reasoning", "gold_probability": 1 / 6}
        for value in [0.1676, 0.1656]:
            self.assertEqual(ensemble(task, [value])["correct"], correct(task, value))


class SimulatedClient:
    """Deterministic test service: responses are fixtures, not model predictions."""
    def __init__(self, **kwargs):
        self.calls = []

    def health(self):
        return {"version": "test-fixture", "models": [{"name": "test:local", "digest": "fixture"}]}

    def chat(self, model, messages, **kwargs):
        self.calls.append((messages, kwargs))
        return {"message": {"content": '{"final_answer":"1/2","explanation":"Fixture only."}'},
                "done": True, "prompt_eval_count": 20, "eval_count": 8, "eval_duration": 1000000}


class PilotTests(unittest.TestCase):
    def test_unknown_token_counts_are_not_zero(self):
        counts = experiment.budget([{"raw": {}, "elapsed_seconds": 1}])
        self.assertIsNone(counts["input_tokens"])
        self.assertIsNone(counts["output_tokens"])

    def test_branches_reuse_initial_answers_without_gold_leakage(self):
        client = SimulatedClient()
        task = make_tasks(2)[1]
        args = argparse.Namespace(seed=42, agents=3, temperature=0.7, max_tokens=256)
        result = experiment.run_question(client, task, "test:local", args, 0)
        self.assertEqual(len(client.calls), 15)
        for branch in result["conditions"].values():
            self.assertEqual(branch["total_budget"]["input_tokens"], 120)
            self.assertEqual(branch["total_budget"]["output_tokens"], 48)
        for index, (messages, options) in enumerate(client.calls):
            self.assertNotIn("gold_state", json.dumps(messages))
            self.assertNotIn("gold_probability", json.dumps(messages))
            self.assertEqual(messages[1]["content"], task["prompt"])
            if index >= 3:
                self.assertEqual(messages[2]["content"], result["initial"][(index - 3) % 3]["raw"]["message"]["content"])
        answers = client.calls[6][0][-1]["content"]
        justifications = client.calls[9][0][-1]["content"]
        dedup = client.calls[12][0][-1]["content"]
        self.assertNotIn("Fixture only.", answers)
        self.assertIn("Fixture only.", justifications)
        self.assertEqual(justifications.count("S1:"), 2)
        self.assertEqual(dedup.count("S1:"), 0)
        self.assertIn("Use each source ID exactly once", dedup)

    def test_full_run_writes_metadata_records_and_completion_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "pilot.jsonl"
            args = ["--model", "test:local", "--questions", "2", "--output", str(output)]
            with patch("run_experiment.OllamaClient", SimulatedClient), redirect_stdout(io.StringIO()):
                self.assertEqual(experiment.main(args), 0)
            rows = [json.loads(line) for line in output.read_text().splitlines()]
            self.assertEqual([r["type"] for r in rows], ["metadata", "question", "question", "complete"])
            self.assertEqual(rows[-1]["questions_completed"], 2)
            self.assertEqual(rows[0]["model_metadata"]["digest"], "fixture")
            original = output.read_bytes()
            with patch("run_experiment.OllamaClient", SimulatedClient), redirect_stderr(io.StringIO()):
                self.assertEqual(experiment.main(args), 1)
            self.assertEqual(output.read_bytes(), original)

    def test_failed_inference_does_not_mark_partial_run_complete(self):
        class FailingClient(SimulatedClient):
            def chat(self, *args, **kwargs):
                raise OllamaError("Simulated unavailable model")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "failed.jsonl"
            with patch("run_experiment.OllamaClient", FailingClient), redirect_stderr(io.StringIO()):
                self.assertEqual(experiment.main(["--model", "test:local", "--output", str(output)]), 1)
            self.assertNotIn('"type": "complete"', output.read_text())

    def test_malformed_answer_is_recorded_without_retries(self):
        class MalformedClient(SimulatedClient):
            def chat(self, *args, **kwargs):
                return {"message": {"content": "unstructured answer"}}
        record = experiment.call(MalformedClient(), "test:local", [], 0, 0.7, 256)
        self.assertIsNone(record["probability"])
        self.assertIsNotNone(record["parse_error"])


if __name__ == "__main__":
    unittest.main()
