"""Offline paired checks for the calculator-syntax prompt comparison."""

from contextlib import redirect_stderr, redirect_stdout
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from calculator_protocol import SYSTEM
from experiment_config import MAX_TOKENS, MODEL
from local_llm import OllamaError
import run_calculator_syntax_experiment as runner


def read_rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


class FixtureClient:
    instances = []
    tasks = {}

    def __init__(self, **kwargs):
        self.options, self.calls, self.health_calls = kwargs, [], 0
        FixtureClient.instances.append(self)

    def health(self):
        self.health_calls += 1
        return {"version": "fixture-runtime", "models": [{"name": MODEL, "model": MODEL,
                                                             "digest": "fixture-llama-digest"}]}

    def chat(self, model, messages, **kwargs):
        self.calls.append({"model": model, "messages": copy.deepcopy(messages), **kwargs})
        task = self.tasks[messages[-1]["content"]]
        return {"model": model, "message": {"role": "assistant", "content": json.dumps({
            "explanation": "Fixture only.", "expression": f"({task['gold_fraction']}) * 1"})},
                "done": True, "done_reason": "stop", "prompt_eval_count": 20,
                "eval_count": 8, "eval_duration": 1000000}


class CalculatorSyntaxExperimentTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads(runner.CONFIG_PATH.read_text(encoding="utf-8"))
        FixtureClient.instances = []
        FixtureClient.tasks = {task["prompt"]: task for task in self.config["tasks"]}

    def invoke(self, arguments, client_class=FixtureClient):
        output, errors = io.StringIO(), io.StringIO()
        with patch.object(runner, "OllamaClient", client_class), redirect_stdout(output), redirect_stderr(errors):
            result = runner.main(arguments)
        return result, output.getvalue(), errors.getvalue()

    def test_dry_run_freezes_32_calls_and_unchanged_execution_without_service_or_files(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "dry"
            with patch.object(runner, "OllamaClient", side_effect=AssertionError("No service")), \
                    redirect_stdout(io.StringIO()) as output:
                self.assertEqual(runner.main(["--dry-run", "--output-dir", str(destination)]), 0)
            plan = json.loads(output.getvalue())
            self.assertEqual(plan["planned_calls"], 32)
            self.assertEqual(plan["model"], MODEL)
            self.assertEqual(plan["max_tokens"], MAX_TOKENS)
            self.assertEqual(plan["config"], self.config)
            self.assertEqual(plan["config"]["prompts"]["baseline"], SYSTEM)
            self.assertTrue(plan["config"]["prompts"]["syntax_clear"].startswith(SYSTEM))
            self.assertEqual(plan["settings"]["num_ctx"], 4096)
            self.assertEqual(plan["settings"]["explanation_word_limit"], 60)
            self.assertTrue(plan["protocol"]["execution_and_scoring_unchanged"])
            for source in ("calculator.py", "calculator_protocol.py", "run_calculator_pilot.py",
                           "run_calculator_syntax_experiment.py", "config/calculator_syntax_experiment.json"):
                self.assertIn(source, plan["source_sha256"])
            self.assertFalse(destination.exists())

    def test_complete_32_calls_use_exact_messages_same_paired_seeds_and_never_send_gold(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "complete"
            result, _, errors = self.invoke(["--output-dir", str(destination)])
            self.assertEqual(result, 0, errors)
            client = FixtureClient.instances[0]
            self.assertEqual(client.options["timeout"], 300)
            self.assertEqual(len(client.calls), 32)
            tasks = {task["id"]: task for task in self.config["tasks"]}
            for request, cell in zip(client.calls, self.config["call_order"]):
                task = tasks[cell["task_id"]]
                self.assertEqual(request, {"model": MODEL, "seed": task["seed"], "temperature": 0.7,
                                          "max_tokens": MAX_TOKENS, "messages": [
                                              {"role": "system", "content": self.config["prompts"][cell["condition"]]},
                                              {"role": "user", "content": task["prompt"]}]})
            for index in range(0, 32, 2):
                self.assertEqual(client.calls[index]["seed"], client.calls[index + 1]["seed"])
            rows = read_rows(destination / "answers.jsonl")
            self.assertEqual(rows[0]["config"], self.config)
            self.assertEqual(rows[0]["model_metadata"]["digest"], "fixture-llama-digest")
            self.assertEqual(rows[-1], {"type": "complete", "calls_completed": 32,
                                        "calculator_evaluations_attempted": 32})
            for row, request in zip(rows[1:-1], client.calls):
                self.assertEqual(row["messages"], request["messages"])
                self.assertTrue(row["score"]["correct"])
                self.assertEqual(row["calculated_answer"]["fraction"], row["score"]["computed_fraction"])
                self.assertEqual(row["calculated_answer"]["origin"], "calculator")
            summary = json.loads((destination / "summary.json").read_text())
            self.assertEqual(summary["overall"]["model_budget"]["calls"], 32)
            self.assertEqual(summary["overall"]["correct"], 32)
            for split in ("fresh", "regression"):
                self.assertEqual(summary["paired"][split]["executable_transitions"], {"1->1": 8})
                self.assertEqual(summary["paired"][split]["strict_transitions"], {"1->1": 8})
                self.assertEqual(summary["paired"][split]["joint_method_valid"]["items"], 8)
                for condition in runner.CONDITIONS:
                    self.assertEqual(summary["split_condition"][split][condition]["items"], 8)
                    self.assertEqual(set(summary["groups"][split][condition]), runner.FAMILIES)
                    self.assertTrue(all(group["items"] == 2 for group in summary["groups"][split][condition].values()))
            manifest = json.loads((destination / "run-manifest.json").read_text())
            self.assertEqual(manifest["status"], "complete")
            self.assertEqual(manifest["calls_completed"], 32)
            self.assertTrue(manifest["generation_sources_unchanged"])

    def test_summary_distinguishes_syntax_repair_from_math_regression(self):
        class MixedClient(FixtureClient):
            def chat(self, *args, **kwargs):
                raw = super().chat(*args, **kwargs)
                parsed = json.loads(raw["message"]["content"])
                if len(self.calls) == 1:
                    parsed["expression"] = "x / 2"
                elif len(self.calls) == 3:
                    parsed["expression"] = "0 * 1"
                raw["message"]["content"] = json.dumps(parsed)
                return raw

        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "mixed"
            result, _, errors = self.invoke(["--output-dir", str(destination)], MixedClient)
            self.assertEqual(result, 0, errors)
            summary = json.loads((destination / "summary.json").read_text())
            first_id, second_id = (self.config["call_order"][i]["task_id"] for i in (0, 2))
            paired = {task["task_id"]: task for split in summary["paired"].values() for task in split["tasks"]}
            first, second = paired[first_id], paired[second_id]
            self.assertEqual(first["executable_transition"], "0->1")
            self.assertEqual(first["strict_transition"], "0->1")
            self.assertFalse(first["joint_method_valid"])
            self.assertEqual(second["executable_transition"], "1->1")
            self.assertEqual(second["strict_transition"], "1->0")
            self.assertTrue(second["joint_method_valid"])
            self.assertEqual(summary["overall"]["calculator_success"], 31)
            self.assertEqual(summary["overall"]["correct"], 30)
            self.assertEqual(summary["overall"]["calculator_success_but_numeric_incorrect"], 1)
            self.assertEqual(sum(summary["overall"]["errors"]["calculator_error"].values()), 1)

    def test_existing_directory_is_refused_before_health_or_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "existing"
            destination.mkdir()
            sentinel = destination / "keep.txt"
            sentinel.write_text("Preserve this experiment.")
            result, _, errors = self.invoke(["--output-dir", str(destination)])
            self.assertEqual(result, 1)
            self.assertIn("already exists", errors)
            self.assertEqual(FixtureClient.instances, [])
            self.assertEqual(sentinel.read_text(), "Preserve this experiment.")

    def test_failed_call_flushes_partial_answers_and_stops_without_retry(self):
        class FailedClient(FixtureClient):
            def chat(self, *args, **kwargs):
                if len(self.calls) == 2:
                    raise OllamaError("Fixture request failure")
                return super().chat(*args, **kwargs)

        self.assert_partial(FailedClient, 1, "failed")

    def test_interrupted_call_preserves_partial_and_returns_130(self):
        class InterruptedClient(FixtureClient):
            def chat(self, *args, **kwargs):
                if len(self.calls) == 2:
                    raise KeyboardInterrupt
                return super().chat(*args, **kwargs)

        self.assert_partial(InterruptedClient, 130, "interrupted")

    def assert_partial(self, client_class, expected_code, status):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "partial"
            result, _, _ = self.invoke(["--output-dir", str(destination)], client_class)
            self.assertEqual(result, expected_code)
            self.assertEqual([row["type"] for row in read_rows(destination / "answers.jsonl")],
                             ["metadata", "answer", "answer"])
            self.assertFalse((destination / "summary.json").exists())
            self.assertEqual(sum(len(client.calls) for client in FixtureClient.instances), 2)
            manifest = json.loads((destination / "run-manifest.json").read_text())
            self.assertEqual(manifest["status"], status)
            self.assertEqual(manifest["calls_completed"], 2)
            self.assertEqual(manifest["calculator_evaluations_attempted"], 2)

    def test_runtime_drift_after_32_answers_prevents_complete_marker_and_summary(self):
        class ChangedClient(FixtureClient):
            def health(self):
                health = super().health()
                if self.health_calls == 34:
                    health["version"] = "changed-runtime"
                return health

        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "runtime"
            result, _, errors = self.invoke(["--output-dir", str(destination)], ChangedClient)
            self.assertEqual(result, 1)
            self.assertIn("digest or runtime changed", errors)
            rows = read_rows(destination / "answers.jsonl")
            self.assertEqual(sum(r["type"] == "answer" for r in rows), 32)
            self.assertNotIn("complete", [r["type"] for r in rows])
            self.assertFalse((destination / "summary.json").exists())

    def test_config_source_drift_stops_before_first_generation(self):
        calls = 0

        def changed_hashes():
            nonlocal calls
            calls += 1
            return {"config/calculator_syntax_experiment.json": "frozen" if calls <= 2 else "changed"}

        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "changed"
            with patch.object(runner, "source_hashes", side_effect=changed_hashes):
                result, _, errors = self.invoke(["--output-dir", str(destination)])
            self.assertEqual(result, 1)
            self.assertIn("Generation sources changed", errors)
            self.assertEqual(sum(len(client.calls) for client in FixtureClient.instances), 0)
            manifest = json.loads((destination / "run-manifest.json").read_text())
            self.assertEqual(manifest["status"], "failed")
            self.assertFalse(manifest["generation_sources_unchanged"])

    def test_invalid_pairing_seeds_balance_and_fixed_settings_fail_without_service(self):
        changes = {
            "duplicate_task": lambda c: c["tasks"][1].update(id=c["tasks"][0]["id"]),
            "boolean_seed": lambda c: c["tasks"][0].update(seed=True),
            "family_balance": lambda c: c["tasks"][0].update(family="evidence"),
            "unpaired": lambda c: c["call_order"][1].update(task_id=c["call_order"][2]["task_id"]),
            "condition_order": lambda c: c["call_order"][0].update(condition="syntax_clear"),
            "baseline_drift": lambda c: c["prompts"].update(baseline="Different baseline"),
            "other_model": lambda c: c.update(model="qwen2.5:3b"),
            "other_cap": lambda c: c.update(max_tokens=512),
        }
        with tempfile.TemporaryDirectory() as directory:
            for name, change in changes.items():
                with self.subTest(name=name):
                    config = copy.deepcopy(self.config)
                    change(config)
                    path = Path(directory) / (name + ".json")
                    path.write_text(json.dumps(config))
                    with patch.object(runner, "CONFIG_PATH", path):
                        result, _, _ = self.invoke(["--dry-run"])
                    self.assertEqual(result, 1)
            self.assertEqual(FixtureClient.instances, [])

    def test_summary_rejects_unpaired_partial_records(self):
        task = self.config["tasks"][0]
        with tempfile.TemporaryDirectory() as directory:
            raw_path = Path(directory) / "answers.jsonl"
            raw_path.write_text("{}\n")
            with self.assertRaisesRegex(ValueError, "incomplete paired"):
                runner.summarize([{"task": task, "condition": "baseline"}], raw_path)


if __name__ == "__main__":
    unittest.main()
