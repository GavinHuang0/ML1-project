"""Offline tests for the original-prompt, one-call baseline runner."""

from contextlib import redirect_stderr, redirect_stdout
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from calculator import evaluate_expression
from calculator_protocol import SYSTEM
from local_llm import OllamaError
import run_baseline as runner


class FixtureClient:
    instances = []

    def __init__(self, **options):
        self.options, self.calls, self.responses, self.health_calls, self.attempts = options, [], [], 0, 0
        FixtureClient.instances.append(self)

    def health(self):
        self.health_calls += 1
        return {"version": "fixture-runtime", "models": [{"name": runner.MODEL, "digest": "fixture-digest"}]}

    def chat(self, model, messages, **options):
        self.attempts += 1
        self.calls.append({"model": model, "messages": copy.deepcopy(messages), **options})
        raw = {"model": model, "message": {"role": "assistant", "content":
               '{"explanation":"Fixture only.","expression":"1/2"}'},
               "done": True, "done_reason": "stop", "prompt_eval_count": 20, "eval_count": 10}
        self.responses.append(raw)
        return raw


def rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


class BaselineRunnerTests(unittest.TestCase):
    def setUp(self):
        FixtureClient.instances = []
        self.config = json.loads(runner.CONFIG_PATH.read_text(encoding="utf-8"))

    def invoke(self, arguments, client=FixtureClient):
        output, errors = io.StringIO(), io.StringIO()
        with patch.object(runner, "OllamaClient", client), redirect_stdout(output), redirect_stderr(errors):
            code = runner.main(arguments)
        return code, output.getvalue(), errors.getvalue()

    def test_dry_run_is_offline_and_previews_original_messages_and_config_snapshot(self):
        with patch.object(runner, "OllamaClient", side_effect=AssertionError("No service access")), \
                redirect_stdout(io.StringIO()) as output:
            self.assertEqual(runner.main(["--dry-run"]), 0)
        plan = json.loads(output.getvalue())
        destination = Path(plan["output_dir"])
        self.assertFalse(destination.exists())
        self.assertEqual(destination.parent, runner.ROOT / "results" / "baseline")
        self.assertTrue(destination.name.endswith("-calculator-baseline-v1"))
        self.assertEqual(plan["planned_calls"], 16)
        self.assertEqual(plan["planned_calculator_evaluations_max"], 16)
        self.assertEqual(plan["configuration_snapshot"], self.config)
        self.assertEqual(set(plan["source_sha256"]), {*runner.SOURCE_FILES, "config/baseline.json"})
        for call, task in zip(plan["calls"], self.config["tasks"]):
            self.assertEqual(call["messages"], [{"role": "system", "content": SYSTEM},
                                                {"role": "user", "content": task["prompt"]}])

    def test_complete_run_preserves_raw_and_invokes_reference_free_calculator_once(self):
        with tempfile.TemporaryDirectory() as directory:
            config = copy.deepcopy(self.config)
            config["source"]["private_note"] = "AUTHOR_METADATA_CANARY_NEVER_SEND"
            for task in config["tasks"]:
                task["private_note"] = "TASK_GOLD_METADATA_CANARY_NEVER_SEND"
            config_path = Path(directory) / "bank.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            destination = Path(directory) / "run"
            with patch.object(runner, "CONFIG_PATH", config_path), \
                    patch("calculator_protocol.evaluate_expression", wraps=evaluate_expression) as calculate:
                code, _, error = self.invoke(["--output-dir", str(destination), "--timeout", "432"])
            self.assertEqual(code, 0, error)
            self.assertEqual(calculate.call_count, 16)
            self.assertTrue(all(call.args == ("1/2",) and not call.kwargs for call in calculate.call_args_list))
            client = FixtureClient.instances[0]
            self.assertEqual(len(client.calls), 16)
            self.assertEqual(client.options["timeout"], 432)
            for call, task in zip(client.calls, config["tasks"]):
                self.assertEqual(call["model"], "llama3.2:3b")
                self.assertEqual(call["max_tokens"], 1024)
                self.assertEqual(call["temperature"], 0.7)
                self.assertEqual(call["seed"], task["seed"])
                self.assertEqual(call["messages"], runner.build_messages(config, task))
                sent = json.dumps(call["messages"])
                for hidden in ("AUTHOR_METADATA_CANARY_NEVER_SEND", "TASK_GOLD_METADATA_CANARY_NEVER_SEND",
                               "gold_fraction", "gold_probability", "cohort", "source_task_id"):
                    self.assertNotIn(hidden, sent)
            raw = rows(destination / "answers.jsonl")
            self.assertEqual(len(raw), 18)
            self.assertEqual(raw[-1], {"type": "complete", "calls_completed": 16,
                                        "calculator_evaluations_attempted": 16})
            for record, response in zip(raw[1:-1], client.responses):
                self.assertEqual(record["raw"], response)
                self.assertEqual(record["calculated_answer"],
                                 {"fraction": "1/2", "decimal": 0.5, "origin": "calculator"})
            summary = json.loads((destination / "summary.json").read_text())
            self.assertEqual(summary["overall"]["items"], 16)
            self.assertEqual(summary["overall"]["calculator_success"], 16)
            self.assertEqual(summary["overall"]["model_budget"]["input_tokens"], 320)
            self.assertEqual(set(summary["cohorts"]), {"syntax_reuse", "pilot_reuse"})
            self.assertEqual(set(summary["families"]), {"reasoning", "evidence", "algebra", "units"})
            manifest = json.loads((destination / "run-manifest.json").read_text())
            self.assertEqual(manifest["status"], "complete")
            self.assertTrue(manifest["generation_sources_unchanged"])
            self.assertEqual(manifest["configuration_snapshot"], config)
            self.assertEqual(manifest["settings"]["request_timeout"], 432)

    def test_bad_content_and_unsupported_expressions_continue_without_retry(self):
        class InvalidClient(FixtureClient):
            def chat(self, *arguments, **options):
                raw = super().chat(*arguments, **options)
                raw["message"]["content"] = ("{unfinished" if len(self.calls) % 2 else
                    '{"explanation":"Fixture only.","expression":"x=1/2"}')
                return raw
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "invalid"
            with patch("calculator_protocol.evaluate_expression", wraps=evaluate_expression) as calculate:
                code, _, error = self.invoke(["--output-dir", str(destination)], InvalidClient)
            self.assertEqual(code, 0, error)
            self.assertEqual(FixtureClient.instances[0].attempts, 16)
            self.assertEqual(calculate.call_count, 8)
            summary = json.loads((destination / "summary.json").read_text())
            self.assertEqual(summary["overall"]["json_valid"], 8)
            self.assertEqual(summary["overall"]["calculator_attempted"], 8)
            self.assertEqual(summary["overall"]["calculator_success"], 0)
            self.assertEqual(summary["overall"]["correct"], 0)

    def test_transport_failure_stops_without_retry_and_preserves_partial_answers(self):
        class FailingClient(FixtureClient):
            def chat(self, *arguments, **options):
                if len(self.calls) == 3:
                    self.attempts += 1
                    raise OllamaError("Fixture unavailable")
                return super().chat(*arguments, **options)
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "partial"
            code, _, _ = self.invoke(["--output-dir", str(destination)], FailingClient)
            self.assertEqual(code, 1)
            self.assertEqual(FixtureClient.instances[0].attempts, 4)
            self.assertEqual(len(rows(destination / "answers.jsonl")), 4)
            self.assertFalse((destination / "summary.json").exists())
            manifest = json.loads((destination / "run-manifest.json").read_text())
            self.assertEqual(manifest["status"], "failed")
            self.assertEqual(manifest["calls_completed"], 3)

    def test_interruption_keeps_partial_run(self):
        class InterruptedClient(FixtureClient):
            def chat(self, *arguments, **options):
                if len(self.calls) == 2:
                    raise KeyboardInterrupt
                return super().chat(*arguments, **options)
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "interrupted"
            code, _, _ = self.invoke(["--output-dir", str(destination)], InterruptedClient)
            self.assertEqual(code, 130)
            raw = rows(destination / "answers.jsonl")
            self.assertEqual(len(raw), 3)
            self.assertFalse(any(record["type"] == "complete" for record in raw))
            self.assertEqual(json.loads((destination / "run-manifest.json").read_text())["status"], "interrupted")

    def test_existing_output_is_refused_before_health(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "existing"
            destination.mkdir()
            sentinel = destination / "keep.txt"
            sentinel.write_text("Keep this data.", encoding="utf-8")
            code, _, error = self.invoke(["--output-dir", str(destination)])
            self.assertEqual(code, 1)
            self.assertIn("already exists", error)
            self.assertEqual(FixtureClient.instances, [])
            self.assertEqual(list(destination.iterdir()), [sentinel])

    def test_historical_namespaces_are_protected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "archive").mkdir()
            with patch.object(runner, "ROOT", root):
                for target in (root / "archive/new", root / "results/runs/new",
                               root / "results/multiple-choice/new"):
                    with self.subTest(target=target), self.assertRaisesRegex(ValueError, "historical"):
                        runner.validate_output_directory(target)

    def test_symlink_alias_of_historical_namespace_is_protected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "archive").mkdir()
            alias = root / "alias"
            try:
                alias.symlink_to(root / "archive", target_is_directory=True)
            except OSError as error:
                if getattr(error, "winerror", None) == 1314:
                    self.skipTest("Windows does not grant this account permission to create symlinks")
                raise
            with patch.object(runner, "ROOT", root):
                with self.assertRaisesRegex(ValueError, "historical"):
                    runner.validate_output_directory(alias / "new")

    def test_runtime_drift_stops_after_first_answer(self):
        class DriftingClient(FixtureClient):
            def health(self):
                health = super().health()
                if self.health_calls >= 3:
                    health["models"][0]["digest"] = "changed-digest"
                return health
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "drift"
            code, _, _ = self.invoke(["--output-dir", str(destination)], DriftingClient)
            self.assertEqual(code, 1)
            self.assertEqual(len(FixtureClient.instances[0].calls), 1)
            self.assertFalse((destination / "summary.json").exists())
            self.assertEqual(json.loads((destination / "run-manifest.json").read_text())["status"], "failed")

    def test_source_drift_stops_after_first_answer(self):
        original, count = runner.source_hashes(), 0
        def changing_hashes():
            nonlocal count
            count += 1
            return original if count < 4 else {**original, "changed": "fixture"}
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "source-drift"
            with patch.object(runner, "source_hashes", side_effect=changing_hashes):
                code, _, _ = self.invoke(["--output-dir", str(destination)])
            self.assertEqual(code, 1)
            self.assertEqual(len(FixtureClient.instances[0].calls), 1)
            manifest = json.loads((destination / "run-manifest.json").read_text())
            self.assertFalse(manifest["generation_sources_unchanged"])
            self.assertEqual(manifest["status"], "failed")

    def test_final_runtime_check_prevents_completion_marker(self):
        class FinalDriftClient(FixtureClient):
            def health(self):
                health = super().health()
                if self.health_calls == 18:
                    health["version"] = "changed-runtime"
                return health
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "final-drift"
            code, _, _ = self.invoke(["--output-dir", str(destination)], FinalDriftClient)
            self.assertEqual(code, 1)
            self.assertEqual(len(FixtureClient.instances[0].calls), 16)
            self.assertFalse(any(record["type"] == "complete" for record in rows(destination / "answers.jsonl")))
            self.assertFalse((destination / "summary.json").exists())

    def test_config_read_hash_race_is_refused_offline(self):
        hashes = runner.source_hashes()
        hashes[runner._config_source_name()] = "changed-configuration"
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "changed"
            with patch.object(runner, "source_hashes", return_value=hashes):
                code, _, error = self.invoke(["--dry-run", "--output-dir", str(destination)])
            self.assertEqual(code, 1)
            self.assertIn("Configuration changed after it was read", error)
            self.assertFalse(destination.exists())
            self.assertEqual(FixtureClient.instances, [])

    def test_invalid_timeout_duplicate_config_and_changed_prompt_are_refused(self):
        for value in ("0", "-1", "nan", "inf"):
            with self.subTest(timeout=value):
                code, _, _ = self.invoke(["--timeout", value, "--dry-run"])
                self.assertEqual(code, 1)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate.json"
            path.write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")
            with patch.object(runner, "CONFIG_PATH", path):
                code, _, error = self.invoke(["--dry-run"])
            self.assertEqual(code, 1)
            self.assertIn("Duplicate configuration key", error)
        changed = copy.deepcopy(self.config)
        changed["system_prompt"] += " New instruction."
        with self.assertRaisesRegex(ValueError, "original system prompt"):
            runner.validate_config(changed)
        self.assertEqual(FixtureClient.instances, [])

    def test_unknown_token_counts_remain_unknown(self):
        budget = runner.model_budget([{"raw": {}, "elapsed_seconds": 1}])
        self.assertIsNone(budget["input_tokens"])
        self.assertIsNone(budget["output_tokens"])


if __name__ == "__main__":
    unittest.main()
