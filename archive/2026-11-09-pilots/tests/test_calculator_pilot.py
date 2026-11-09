"""Offline integration checks for the one-call planning/calculator pilot."""

from contextlib import redirect_stderr, redirect_stdout
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from calculator import evaluate_expression
from experiment_config import MAX_TOKENS, MODEL
from local_llm import OllamaError
import run_calculator_pilot as runner


def read_rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


class FixtureClient:
    """A fixed method fixture, independent of every question and reference answer."""

    instances = []

    def __init__(self, **kwargs):
        self.options, self.calls, self.responses, self.health_calls = kwargs, [], [], 0
        FixtureClient.instances.append(self)

    def health(self):
        self.health_calls += 1
        return {"version": "fixture-runtime", "models": [
            {"name": MODEL, "model": MODEL, "digest": "fixture-llama-digest"}]}

    def chat(self, model, messages, **kwargs):
        self.calls.append({"model": model, "messages": copy.deepcopy(messages), **kwargs})
        raw = {"model": model, "message": {"role": "assistant", "content": json.dumps({
            "explanation": "Fixture method only.", "expression": "(1/2)"})},
            "done": True, "done_reason": "stop", "prompt_eval_count": 20,
            "eval_count": 8, "eval_duration": 1000000}
        self.responses.append(copy.deepcopy(raw))
        return raw


class CalculatorPilotTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads(runner.CONFIG_PATH.read_text(encoding="utf-8"))
        FixtureClient.instances = []

    def invoke(self, arguments, client_class=FixtureClient):
        output, errors = io.StringIO(), io.StringIO()
        with patch.object(runner, "OllamaClient", client_class), \
                redirect_stdout(output), redirect_stderr(errors):
            result = runner.main(arguments)
        return result, output.getvalue(), errors.getvalue()

    def test_dry_run_plans_eight_calls_without_service_or_output(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "dry"
            with patch.object(runner, "OllamaClient", side_effect=AssertionError("No service")), \
                    redirect_stdout(io.StringIO()) as output:
                self.assertEqual(runner.main(["--dry-run", "--output-dir", str(destination)]), 0)
            plan = json.loads(output.getvalue())
            self.assertEqual(plan["model"], MODEL)
            self.assertEqual(plan["max_tokens"], MAX_TOKENS)
            self.assertEqual(plan["planned_calls"], 8)
            self.assertFalse(destination.exists())

    def test_complete_run_preserves_methods_and_keeps_references_out_of_requests(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "complete"
            with patch("calculator_protocol.evaluate_expression", wraps=evaluate_expression) as calculate:
                result, _, errors = self.invoke(["--output-dir", str(destination)])
            self.assertEqual(result, 0, errors)
            self.assertEqual(calculate.call_count, 8)
            self.assertTrue(all(call.args == ("(1/2)",) and not call.kwargs
                                for call in calculate.call_args_list))
            self.assertEqual(len(FixtureClient.instances), 1)
            client = FixtureClient.instances[0]
            self.assertEqual(len(client.calls), 8)
            for request, task in zip(client.calls, self.config["tasks"]):
                self.assertEqual(request["model"], MODEL)
                self.assertEqual(request["max_tokens"], MAX_TOKENS)
                self.assertEqual(request["temperature"], 0.7)
                self.assertEqual(request["seed"], task["seed"])
                self.assertEqual(len(request["messages"]), 2)
                self.assertEqual(request["messages"][0]["role"], "system")
                self.assertEqual(request["messages"][1], {"role": "user", "content": task["prompt"]})
                sent = json.dumps(request["messages"])
                for key in ("gold_probability", "gold_state", "gold_fraction", "source_task_id"):
                    self.assertNotIn(key, sent)
            rows = read_rows(destination / "answers.jsonl")
            self.assertEqual(rows[0]["model_metadata"]["digest"], "fixture-llama-digest")
            self.assertEqual(rows[-1], {"type": "complete", "calls_completed": 8,
                                        "calculator_evaluations_attempted": 8})
            self.assertEqual([row["raw"] for row in rows[1:-1]], client.responses)
            self.assertEqual([row["messages"] for row in rows[1:-1]], [call["messages"] for call in client.calls])
            for row in rows[1:-1]:
                self.assertTrue(row["score"]["calculator_attempted"])
                self.assertTrue(row["score"]["calculator_success"])
                self.assertEqual(row["score"]["computed_fraction"], "1/2")
                self.assertEqual(row["calculated_answer"],
                                 {"fraction": "1/2", "decimal": 0.5, "origin": "calculator"})
            summary = json.loads((destination / "summary.json").read_text())
            self.assertEqual(summary["overall"]["model_budget"]["calls"], 8)
            self.assertEqual(summary["overall"]["calculator_success"], 8)
            manifest = json.loads((destination / "run-manifest.json").read_text())
            self.assertEqual(manifest["status"], "complete")
            self.assertEqual(manifest["calls_completed"], 8)
            self.assertEqual(manifest["calculator_evaluations_attempted"], 8)
            self.assertTrue(manifest["generation_sources_unchanged"])

    def test_invalid_expression_is_recorded_without_retry_and_run_completes(self):
        class InvalidExpressionClient(FixtureClient):
            def chat(self, *args, **kwargs):
                raw = super().chat(*args, **kwargs)
                raw["message"]["content"] = json.dumps({"explanation": "Fixture only.", "expression": "abs(-2)"})
                return raw

        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "invalid"
            result, _, errors = self.invoke(["--output-dir", str(destination)], InvalidExpressionClient)
            self.assertEqual(result, 0, errors)
            self.assertEqual(sum(len(client.calls) for client in FixtureClient.instances), 8)
            rows = read_rows(destination / "answers.jsonl")
            self.assertEqual(len(rows[1:-1]), 8)
            self.assertEqual(rows[-1]["type"], "complete")
            self.assertTrue(all("abs(-2)" in row["raw"]["message"]["content"] for row in rows[1:-1]))
            for row in rows[1:-1]:
                self.assertTrue(row["score"]["calculator_attempted"])
                self.assertFalse(row["score"]["calculator_success"])
                self.assertIsNone(row["calculated_answer"]["fraction"])
                self.assertIsNotNone(row["score"]["calculator_error"])
            summary = json.loads((destination / "summary.json").read_text())
            self.assertEqual(summary["overall"]["calculator_attempted"], 8)
            self.assertEqual(summary["overall"]["calculator_success"], 0)
            self.assertEqual(summary["overall"]["correct"], 0)

    def test_existing_output_is_refused_before_client_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "existing"
            destination.mkdir()
            sentinel = destination / "keep.txt"
            sentinel.write_text("Keep existing results.")
            result, _, errors = self.invoke(["--output-dir", str(destination)])
            self.assertEqual(result, 1)
            self.assertIn("already exists", errors)
            self.assertEqual(FixtureClient.instances, [])
            self.assertEqual(sentinel.read_text(), "Keep existing results.")
            self.assertEqual(list(destination.iterdir()), [sentinel])

    def test_failed_generation_preserves_two_answers_without_completion_or_summary(self):
        class FailedClient(FixtureClient):
            def chat(self, *args, **kwargs):
                if len(self.calls) == 2:
                    raise OllamaError("Fixture request failure")
                return super().chat(*args, **kwargs)

        self.assert_partial(FailedClient, 1, "failed")

    def test_interrupted_generation_preserves_two_answers_and_returns_130(self):
        class InterruptedClient(FixtureClient):
            def chat(self, *args, **kwargs):
                if len(self.calls) == 2:
                    raise KeyboardInterrupt
                return super().chat(*args, **kwargs)

        self.assert_partial(InterruptedClient, 130, "interrupted")

    def assert_partial(self, client_class, code, status):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "partial"
            result, _, _ = self.invoke(["--output-dir", str(destination)], client_class)
            self.assertEqual(result, code)
            self.assertEqual([row["type"] for row in read_rows(destination / "answers.jsonl")],
                             ["metadata", "answer", "answer"])
            self.assertFalse((destination / "summary.json").exists())
            manifest = json.loads((destination / "run-manifest.json").read_text())
            self.assertEqual(manifest["status"], status)
            self.assertEqual(manifest["calls_completed"], 2)

    def test_runtime_drift_stops_before_the_next_generation(self):
        class ChangedRuntimeClient(FixtureClient):
            def health(self):
                health = super().health()
                if self.calls:
                    health["version"] = "changed-runtime"
                return health

        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "runtime-drift"
            result, _, _ = self.invoke(["--output-dir", str(destination)], ChangedRuntimeClient)
            self.assertEqual(result, 1)
            self.assertEqual(sum(len(client.calls) for client in FixtureClient.instances), 1)
            self.assertNotIn("complete", [row["type"] for row in read_rows(destination / "answers.jsonl")])
            self.assertFalse((destination / "summary.json").exists())

    def test_source_drift_stops_before_the_next_generation(self):
        digest = {"value": "frozen"}

        class ChangedSourceClient(FixtureClient):
            def chat(self, *args, **kwargs):
                raw = super().chat(*args, **kwargs)
                digest["value"] = "changed"
                return raw

        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "source-drift"
            with patch.object(runner, "source_hashes", side_effect=lambda: {"fixture.py": digest["value"]}):
                result, _, _ = self.invoke(["--output-dir", str(destination)], ChangedSourceClient)
            self.assertEqual(result, 1)
            self.assertEqual(sum(len(client.calls) for client in FixtureClient.instances), 1)
            manifest = json.loads((destination / "run-manifest.json").read_text())
            self.assertEqual(manifest["status"], "failed")
            self.assertFalse(manifest["generation_sources_unchanged"])
            self.assertFalse((destination / "summary.json").exists())


if __name__ == "__main__":
    unittest.main()
