"""Offline lifecycle checks for the isolated exact-choice runner."""

from contextlib import redirect_stderr, redirect_stdout
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from local_llm import OllamaError
import run_multiple_choice_experiment as runner


class FixtureClient:
    instances = []

    def __init__(self, **options):
        self.options, self.calls, self.health_calls, self.attempts = options, [], 0, 0
        FixtureClient.instances.append(self)

    def health(self):
        self.health_calls += 1
        return {"version": "fixture-runtime", "models": [{"name": runner.MODEL, "digest": "fixture-digest"}]}

    def chat(self, model, messages, **options):
        self.attempts += 1
        self.calls.append({"model": model, "messages": copy.deepcopy(messages), **options})
        return {"model": model, "message": {"content": '{"explanation":"Fixture only.","choice":"A"}'},
                "done": True, "done_reason": "stop", "prompt_eval_count": 20, "eval_count": 10}


def rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


class MultipleChoiceRunnerTests(unittest.TestCase):
    def setUp(self):
        FixtureClient.instances = []
        self.config = json.loads(runner.CONFIG_PATH.read_text(encoding="utf-8"))

    def invoke(self, arguments, client=FixtureClient):
        output, errors = io.StringIO(), io.StringIO()
        with patch.object(runner, "OllamaClient", client), redirect_stdout(output), redirect_stderr(errors):
            code = runner.main(arguments)
        return code, output.getvalue(), errors.getvalue()

    def test_dry_run_previews_all_exact_messages_without_service_or_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "preview"
            with patch.object(runner, "OllamaClient", side_effect=AssertionError("No service access")), \
                    redirect_stdout(io.StringIO()) as output:
                self.assertEqual(runner.main(["--dry-run", "--output-dir", str(destination)]), 0)
            plan = json.loads(output.getvalue())
            self.assertFalse(destination.exists())
            self.assertEqual(plan["planned_calls"], 16)
            self.assertEqual(plan["config"], self.config)
            self.assertEqual(len(plan["calls"]), 16)
            self.assertEqual(set(plan["source_sha256"]), {*runner.SOURCE_FILES, "config/multiple_choice_experiment.json"})
            for call, task in zip(plan["calls"], self.config["tasks"]):
                expected = task["question"] + "\n\nOptions (exact values):\n"
                expected += "\n".join(f"{option['label']}. {option['value']}" for option in task["options"])
                expected += "\n\nSelect exactly one option."
                self.assertEqual(call["messages"], [{"role": "system", "content": self.config["system_prompt"]},
                                                     {"role": "user", "content": expected}])

    def test_complete_run_uses_sixteen_calls_and_keeps_author_notes_local(self):
        with tempfile.TemporaryDirectory() as directory:
            config = copy.deepcopy(self.config)
            for task in config["tasks"]:
                for option in task["options"]:
                    option["rationale"] = "AUTHOR_RATIONALE_CANARY_NEVER_SEND"
            config["source"]["private_note"] = "AUTHOR_METADATA_CANARY_NEVER_SEND"
            config_path = Path(directory) / "bank.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            destination = Path(directory) / "run"
            with patch.object(runner, "CONFIG_PATH", config_path):
                code, _, error = self.invoke(["--output-dir", str(destination), "--timeout", "432"])
            self.assertEqual(code, 0, error)
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
                self.assertNotIn("AUTHOR_RATIONALE_CANARY_NEVER_SEND", sent)
                self.assertNotIn("AUTHOR_METADATA_CANARY_NEVER_SEND", sent)
                for key in ("gold_fraction", "correct_choice", "source_task_id", "cohort"):
                    self.assertNotIn(key, sent)
            raw = rows(destination / "answers.jsonl")
            self.assertEqual(len(raw), 18)
            self.assertEqual(raw[-1], {"type": "complete", "calls_completed": 16})
            self.assertEqual(raw[0]["protocol"]["version"], "mc-exact-v1")
            self.assertEqual(raw[0]["model_metadata"]["digest"], "fixture-digest")
            self.assertEqual(raw[0]["settings"]["request_timeout"], 432)
            self.assertEqual(raw[0]["config"], config)
            summary = json.loads((destination / "summary.json").read_text())
            self.assertEqual(summary["overall"]["items"], 16)
            self.assertEqual(summary["overall"]["answer_letter_distribution"], {"A": 16})
            self.assertEqual(summary["overall"]["model_budget"]["input_tokens"], 320)
            self.assertEqual(set(summary["cohorts"]), {"syntax_reuse", "pilot_reuse"})
            self.assertEqual(set(summary["families"]), {"reasoning", "evidence", "algebra", "units"})
            self.assertTrue(any(answer["selected_distractor_rationale"] for answer in summary["answers"]))
            manifest = json.loads((destination / "run-manifest.json").read_text())
            self.assertEqual(manifest["status"], "complete")
            self.assertEqual(manifest["config"], config)
            self.assertTrue(manifest["generation_sources_unchanged"])

    def test_invalid_choices_are_scored_and_not_retried(self):
        class InvalidClient(FixtureClient):
            def chat(self, *arguments, **options):
                raw = super().chat(*arguments, **options)
                raw["message"]["content"] = '{"explanation":"Fixture only.","choice":"a"}'
                return raw
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "invalid"
            code, _, error = self.invoke(["--output-dir", str(destination)], InvalidClient)
            self.assertEqual(code, 0, error)
            self.assertEqual(FixtureClient.instances[0].attempts, 16)
            summary = json.loads((destination / "summary.json").read_text())
            self.assertEqual(summary["overall"]["choice_valid"], 0)
            self.assertEqual(summary["overall"]["correct"], 0)
            self.assertEqual(summary["overall"]["answer_letter_distribution"], {"invalid": 16})

    def test_failure_preserves_partial_answers_and_stops_without_retry(self):
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
            client = FixtureClient.instances[0]
            self.assertEqual(client.attempts, 4)
            self.assertEqual(len(rows(destination / "answers.jsonl")), 4)
            self.assertFalse((destination / "summary.json").exists())
            manifest = json.loads((destination / "run-manifest.json").read_text())
            self.assertEqual(manifest["status"], "failed")
            self.assertEqual(manifest["calls_completed"], 3)

    def test_interruption_preserves_partial_answers(self):
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
            self.assertFalse(any(row["type"] == "complete" for row in raw))
            self.assertEqual(json.loads((destination / "run-manifest.json").read_text())["status"], "interrupted")

    def test_existing_directory_is_refused_before_service_access(self):
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

    def test_protected_locations_are_rejected_including_symlink_alias(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "archive").mkdir()
            alias = root / "alias"
            alias.symlink_to(root / "archive", target_is_directory=True)
            with patch.object(runner, "ROOT", root):
                for target in (root / "archive" / "new", root / "results/runs/new", alias / "new"):
                    with self.subTest(target=target), self.assertRaisesRegex(ValueError, "historical"):
                        runner.validate_output_directory(target)

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
        original = runner.source_hashes()
        count = 0
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

    def test_invalid_timeout_and_duplicate_configuration_fail_offline(self):
        for value in ("0", "-1", "nan", "inf"):
            with self.subTest(timeout=value):
                code, _, _ = self.invoke(["--timeout", value, "--dry-run"])
                self.assertEqual(code, 1)
        self.assertEqual(FixtureClient.instances, [])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate.json"
            path.write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")
            with patch.object(runner, "CONFIG_PATH", path):
                code, _, error = self.invoke(["--dry-run"])
            self.assertEqual(code, 1)
            self.assertIn("Duplicate configuration key", error)

    def test_unknown_token_counts_remain_unknown(self):
        result = runner.model_budget([{"raw": {}, "elapsed_seconds": 1}])
        self.assertIsNone(result["input_tokens"])
        self.assertIsNone(result["output_tokens"])

    def test_configuration_change_between_parsing_and_hashing_is_refused_offline(self):
        hashes = runner.source_hashes()
        hashes["config/multiple_choice_experiment.json"] = "changed-configuration"
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "changed"
            with patch.object(runner, "source_hashes", return_value=hashes):
                code, _, error = self.invoke(["--dry-run", "--output-dir", str(destination)])
            self.assertEqual(code, 1)
            self.assertIn("Configuration changed after it was read", error)
            self.assertFalse(destination.exists())
            self.assertEqual(FixtureClient.instances, [])


if __name__ == "__main__":
    unittest.main()
