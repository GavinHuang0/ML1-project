"""Offline checks for the frozen paired template experiment; no model inference."""

from contextlib import redirect_stderr, redirect_stdout
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from experiment_config import MAX_TOKENS, MODEL
from local_llm import OllamaError
import run_template_experiment as runner


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
        answer = task["gold_fraction"]
        if task["answer_kind"] == "expression":
            answer = f"({answer}) * 1"
        return {"model": model, "message": {"role": "assistant", "content": json.dumps({
            "explanation": "Fixture only.", "final_answer": answer})},
                "done": True, "done_reason": "stop", "prompt_eval_count": 20,
                "eval_count": 8, "eval_duration": 1000000}


class TemplateExperimentTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads(runner.CONFIG_PATH.read_text(encoding="utf-8"))
        FixtureClient.instances = []
        FixtureClient.tasks = {task["prompt"]: task for task in self.config["tasks"]}

    def invoke(self, arguments, client_class=FixtureClient):
        output, errors = io.StringIO(), io.StringIO()
        with patch.object(runner, "OllamaClient", client_class), redirect_stdout(output), redirect_stderr(errors):
            result = runner.main(arguments)
        return result, output.getvalue(), errors.getvalue()

    def test_dry_run_pins_forty_calls_without_service_or_files(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "dry"
            with patch.object(runner, "OllamaClient", side_effect=AssertionError("No service")), \
                    redirect_stdout(io.StringIO()) as output:
                self.assertEqual(runner.main(["--dry-run", "--output-dir", str(destination)]), 0)
            plan = json.loads(output.getvalue())
            self.assertEqual(plan["model"], MODEL)
            self.assertEqual(plan["max_tokens"], MAX_TOKENS)
            self.assertEqual(plan["planned_calls"], 40)
            self.assertEqual(plan["config"], self.config)
            self.assertEqual(plan["settings"]["num_ctx"], 4096)
            self.assertIn("run_template_experiment.py", plan["source_sha256"])
            self.assertIn("template_scoring.py", plan["source_sha256"])
            self.assertIn("config/template_experiment.json", plan["source_sha256"])
            self.assertFalse(destination.exists())

    def test_complete_run_uses_exact_frozen_pairing_and_never_sends_gold_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "complete"
            result, _, errors = self.invoke(["--output-dir", str(destination)])
            self.assertEqual(result, 0, errors)
            client = FixtureClient.instances[0]
            self.assertEqual(len(client.calls), 40)
            tasks = {task["id"]: task for task in self.config["tasks"]}
            for request, cell in zip(client.calls, self.config["call_order"]):
                task = tasks[cell["task_id"]]
                self.assertEqual(request, {"model": MODEL, "seed": task["seed"], "temperature": 0.7,
                                          "max_tokens": MAX_TOKENS, "messages": [
                                              {"role": "system", "content": self.config["prompts"][cell["condition"]]},
                                              {"role": "user", "content": task["prompt"]}]})
            rows = read_rows(destination / "answers.jsonl")
            self.assertEqual(rows[0]["config"], self.config)
            self.assertEqual(rows[0]["model_metadata"]["digest"], "fixture-llama-digest")
            self.assertEqual(rows[-1], {"type": "complete", "calls_completed": 40})
            self.assertEqual([r["messages"] for r in rows[1:-1]], [r["messages"] for r in client.calls])
            self.assertTrue(all(row["score"]["correct"] for row in rows[1:-1]))
            summary = json.loads((destination / "summary.json").read_text())
            self.assertEqual(summary["overall"]["budget"]["calls"], 40)
            self.assertEqual(summary["overall"]["correct"], 40)
            for split, size in (("fresh", 12), ("regression", 8)):
                self.assertEqual(summary["paired"][split]["strict_transitions"], {"1->1": size})
                self.assertEqual(summary["paired"][split]["joint_format_valid"]["items"], size)
                self.assertEqual(summary["split_condition"][split]["baseline"]["items"], size)
            manifest = json.loads((destination / "run-manifest.json").read_text())
            self.assertEqual(manifest["status"], "complete")
            self.assertEqual(manifest["calls_completed"], 40)
            self.assertTrue(manifest["generation_sources_unchanged"])

    def test_summary_separates_format_repair_from_numeric_improvement(self):
        class MissingExplanationClient(FixtureClient):
            def chat(self, *args, **kwargs):
                first = not self.calls
                raw = super().chat(*args, **kwargs)
                if first:
                    parsed = json.loads(raw["message"]["content"])
                    raw["message"]["content"] = json.dumps({"final_answer": parsed["final_answer"]})
                return raw

        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "format"
            result, _, errors = self.invoke(["--output-dir", str(destination)], MissingExplanationClient)
            self.assertEqual(result, 0, errors)
            summary = json.loads((destination / "summary.json").read_text())
            first_id = self.config["call_order"][0]["task_id"]
            first_task = next(t for t in self.config["tasks"] if t["id"] == first_id)
            paired = summary["paired"][first_task["split"]]
            item = next(item for item in paired["tasks"] if item["task_id"] == first_id)
            self.assertEqual(item["strict_transition"], "0->1")
            self.assertEqual(item["numeric_transition"], "1->1")
            self.assertFalse(item["joint_format_valid"])
            self.assertEqual(summary["overall"]["numeric_correct"], 40)
            self.assertEqual(summary["overall"]["correct"], 39)
            self.assertEqual(summary["overall"]["numeric_correct_with_invalid_format"], 1)

    def test_existing_directory_is_refused_before_service_or_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "existing"
            destination.mkdir()
            sentinel = destination / "keep.txt"
            sentinel.write_text("Preserve this result.")
            result, _, errors = self.invoke(["--output-dir", str(destination)])
            self.assertEqual(result, 1)
            self.assertIn("already exists", errors)
            self.assertEqual(FixtureClient.instances, [])
            self.assertEqual(sentinel.read_text(), "Preserve this result.")

    def test_failed_call_keeps_two_flushed_answers_and_no_complete_or_summary(self):
        class FailedClient(FixtureClient):
            def chat(self, *args, **kwargs):
                if len(self.calls) == 2:
                    raise OllamaError("Fixture request failure")
                return super().chat(*args, **kwargs)

        self.assert_partial(FailedClient, 1, "failed")

    def test_interrupted_call_keeps_partial_answers_and_returns_130(self):
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
            rows = read_rows(destination / "answers.jsonl")
            self.assertEqual([row["type"] for row in rows], ["metadata", "answer", "answer"])
            self.assertFalse((destination / "summary.json").exists())
            self.assertEqual(sum(len(c.calls) for c in FixtureClient.instances), 2)
            manifest = json.loads((destination / "run-manifest.json").read_text())
            self.assertEqual(manifest["status"], status)
            self.assertEqual(manifest["calls_completed"], 2)

    def test_runtime_change_stops_before_next_generation(self):
        class ChangedClient(FixtureClient):
            def health(self):
                health = super().health()
                if self.health_calls >= 3:
                    health["models"][0]["digest"] = "changed"
                return health

        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "changed"
            result, _, errors = self.invoke(["--output-dir", str(destination)], ChangedClient)
            self.assertEqual(result, 1)
            self.assertIn("digest or Ollama version changed", errors)
            self.assertEqual(sum(len(c.calls) for c in FixtureClient.instances), 1)
            self.assertNotIn("complete", [r["type"] for r in read_rows(destination / "answers.jsonl")])

    def test_source_change_stops_before_first_generation(self):
        calls = 0

        def changed_hashes():
            nonlocal calls
            calls += 1
            return {"source.py": "frozen" if calls <= 2 else "changed"}

        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "changed"
            with patch.object(runner, "source_hashes", side_effect=changed_hashes):
                result, _, errors = self.invoke(["--output-dir", str(destination)])
            self.assertEqual(result, 1)
            self.assertIn("Generation sources changed", errors)
            self.assertEqual(sum(len(c.calls) for c in FixtureClient.instances), 0)
            manifest = json.loads((destination / "run-manifest.json").read_text())
            self.assertFalse(manifest["generation_sources_unchanged"])
            self.assertEqual(manifest["status"], "failed")

    def test_invalid_or_unbalanced_configuration_is_rejected_without_service(self):
        changes = {
            "duplicate_task": lambda c: c["tasks"][1].update(id=c["tasks"][0]["id"]),
            "boolean_seed": lambda c: c["tasks"][0].update(seed=True),
            "unpaired": lambda c: c["call_order"][1].update(task_id=c["call_order"][2]["task_id"]),
            "condition_order": lambda c: c["call_order"][0].update(condition="template_bounded"),
            "other_model": lambda c: c.update(model="qwen2.5:3b"),
            "other_cap": lambda c: c.update(max_tokens=512),
        }
        with tempfile.TemporaryDirectory() as directory:
            for name, mutate in changes.items():
                with self.subTest(name=name):
                    config = copy.deepcopy(self.config)
                    mutate(config)
                    path = Path(directory) / (name + ".json")
                    path.write_text(json.dumps(config))
                    with patch.object(runner, "CONFIG_PATH", path):
                        result, _, _ = self.invoke(["--dry-run"])
                    self.assertEqual(result, 1)
            self.assertEqual(FixtureClient.instances, [])


if __name__ == "__main__":
    unittest.main()
