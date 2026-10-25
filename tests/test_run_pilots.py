"""Checks for the fixed Llama/1024 protocol; no Ollama or real inference."""

from contextlib import redirect_stderr, redirect_stdout
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import analyze_results
from experiment_config import MAX_TOKENS, MODEL, protocol_metadata
from local_llm import OllamaError
import run_pilots


ROOT = Path(__file__).resolve().parents[1]


def read_rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def reference_rows(pilot):
    return json.loads((ROOT / "config" / "pilots.json").read_text())["profiles"][pilot]["cases"]


class FixtureClient:
    """Record API requests and return fixtures, never model predictions."""

    instances = []

    def __init__(self, **kwargs):
        self.options = kwargs
        self.calls = []
        self.health_calls = 0
        type(self).instances.append(self)

    def health(self):
        self.health_calls += 1
        return {"version": "fixture-runtime", "models": [
            {"name": MODEL, "model": MODEL, "digest": "fixture-llama-digest"},
            {"name": "qwen2.5:3b", "digest": "fixture-qwen-digest"},
        ]}

    def chat(self, model, messages, **kwargs):
        self.calls.append({"model": model, "messages": copy.deepcopy(messages), **kwargs})
        return {"model": model, "message": {"role": "assistant", "content":
                '{"explanation":"Fixture only.","final_answer":"1/2"}'},
                "done": True, "done_reason": "stop", "prompt_eval_count": 20,
                "eval_count": 8, "eval_duration": 1000000}


class PilotReplayTests(unittest.TestCase):
    def setUp(self):
        FixtureClient.instances = []

    def invoke(self, arguments, client_class=FixtureClient):
        output, errors = io.StringIO(), io.StringIO()
        with patch.object(run_pilots, "OllamaClient", client_class), \
                patch.object(run_pilots.experiment, "OllamaClient", client_class), \
                redirect_stdout(output), redirect_stderr(errors):
            result = run_pilots.main(arguments)
        return result, output.getvalue(), errors.getvalue()

    def test_dry_run_all_plans_80_calls_without_service_or_output(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "dry-run"
            with patch.object(run_pilots, "OllamaClient", side_effect=AssertionError("No service in dry run")), \
                    patch.object(run_pilots.experiment, "OllamaClient", side_effect=AssertionError("No service in dry run")), \
                    redirect_stdout(io.StringIO()) as output:
                self.assertEqual(run_pilots.main(["--dry-run", "--output-dir", str(destination)]), 0)
            plan = json.loads(output.getvalue())
            self.assertEqual(plan["planned_calls"], 80)
            self.assertEqual(len(plan["jobs"]), 3)
            self.assertEqual([job["pilot"] for job in plan["jobs"]], ["full", "urn-check", "diagnostic"])
            self.assertTrue(all(job["max_tokens"] == MAX_TOKENS for job in plan["jobs"]))
            self.assertEqual(plan["protocol"], protocol_metadata())
            self.assertFalse(destination.exists())

    def test_inconsistent_config_messages_are_rejected_before_client_or_output(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "results"
            config = json.loads(run_pilots.CONFIG_PATH.read_text())
            config["profiles"]["diagnostic"]["cases"][0]["messages"][0]["content"] = "Changed prompt"
            config_path = Path(directory) / "pilots.json"
            config_path.write_text(json.dumps(config))
            output, errors = io.StringIO(), io.StringIO()
            with patch.object(run_pilots, "CONFIG_PATH", config_path), \
                    patch.object(run_pilots, "OllamaClient", side_effect=AssertionError("No service before config validation")), \
                    redirect_stdout(output), redirect_stderr(errors):
                result = run_pilots.main(["--pilot", "diagnostic", "--dry-run", "--output-dir", str(destination)])
            self.assertEqual(result, 1)
            self.assertIn("inconsistent active prompt/seed/cell", errors.getvalue().lower())
            self.assertFalse(destination.exists())

    def test_active_plan_does_not_depend_on_archived_outputs_or_source_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            config = json.loads(run_pilots.CONFIG_PATH.read_text())
            for profile in config["profiles"].values():
                profile["source"] = {"archive_file": "/missing/archived-result.jsonl", "sha256": "0" * 64}
            config_path = Path(directory) / "pilots.json"
            config_path.write_text(json.dumps(config))
            with patch.object(run_pilots, "CONFIG_PATH", config_path):
                result, output, errors = self.invoke(["--dry-run", "--output-dir", str(Path(directory) / "new")])
            self.assertEqual(result, 0, errors)
            self.assertEqual(json.loads(output)["planned_calls"], 80)
            self.assertEqual(FixtureClient.instances, [])

    def test_frozen_cases_preserve_all_twenty_archived_messages_tasks_and_seeds(self):
        config, _ = run_pilots.read_protocol()
        archived = ROOT / "archive" / "2026-10-24-legacy" / "results"
        for name, profile in config["profiles"].items():
            rows = read_rows(archived / f"experiment1-qwen-seed42-max512-{name}1024.jsonl")
            self.assertEqual(profile["prompts"], rows[0]["prompts"])
            expected = [{"condition": row["condition"], "task": row["task"],
                         "messages": row["messages"], "seed": row.get("seed", row["task"].get("seed"))}
                        for row in rows[1:-1]]
            self.assertEqual(profile["cases"], expected)

    def test_old_models_token_limits_and_profiles_are_rejected_without_service(self):
        for arguments in (["--model", "qwen2.5:3b"], ["--max-tokens", "512"],
                          ["--max-tokens", "256"], ["--pilot", "256"], ["--pilot", "512"]):
            with self.subTest(arguments=arguments), redirect_stderr(io.StringIO()), \
                    self.assertRaises(SystemExit) as raised:
                self.invoke(arguments)
            self.assertEqual(raised.exception.code, 2)
        self.assertEqual(FixtureClient.instances, [])

    def test_urn_check_replays_configured_messages_and_seeds(self):
        expected = reference_rows("urn-check")
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "llama"
            result, _, errors = self.invoke(["--pilot", "urn-check", "--output-dir", str(destination)])
            self.assertEqual(result, 0, errors)
            calls = [call for client in FixtureClient.instances for call in client.calls]
            self.assertEqual(len(calls), 4)
            for actual, saved in zip(calls, expected):
                self.assertEqual(actual["model"], MODEL)
                self.assertEqual(actual["messages"], saved["messages"])
                self.assertEqual(actual["seed"], saved["seed"])
                self.assertEqual(actual["max_tokens"], 1024)
                self.assertEqual(actual["temperature"], 0.7)
            rows = read_rows(destination / "urn-check1024.jsonl")
            self.assertEqual(rows[0]["model"], MODEL)
            self.assertEqual(rows[0]["model_metadata"]["digest"], "fixture-llama-digest")
            self.assertEqual(rows[0]["ollama_version"], "fixture-runtime")
            self.assertEqual(rows[0]["protocol"], protocol_metadata())
            self.assertEqual(rows[-1]["type"], "complete")
            self.assertEqual(sum(row["type"] == "answer" for row in rows), 4)
            summary = json.loads((destination / "urn-check1024.summary.json").read_text())
            self.assertEqual(summary["budget"]["calls"], 4)
            self.assertEqual(set(summary["groups"]), {"original", "math_check"})
            self.assertEqual(json.loads((destination / "run-manifest.json").read_text())["status"], "complete")

    def test_diagnostic_replays_sixteen_calls_and_records_summary(self):
        expected = reference_rows("diagnostic")
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "llama"
            result, _, errors = self.invoke(["--model", MODEL, "--pilot", "diagnostic", "--output-dir", str(destination)])
            self.assertEqual(result, 0, errors)
            calls = [call for client in FixtureClient.instances for call in client.calls]
            self.assertEqual(len(calls), 16)
            for actual, saved in zip(calls, expected):
                self.assertEqual(actual["messages"], saved["messages"])
                self.assertEqual(actual["seed"], saved["task"]["seed"])
                self.assertEqual(actual["max_tokens"], 1024)
                self.assertEqual(actual["model"], MODEL)
            rows = read_rows(destination / "diagnostic1024.jsonl")
            self.assertEqual(rows[-1]["type"], "complete")
            self.assertEqual(sum(row["type"] == "answer" for row in rows), 16)
            summary = json.loads((destination / "diagnostic1024.summary.json").read_text())
            self.assertEqual(summary["budget"]["calls"], 16)
            self.assertEqual(summary["length_stops"], 0)
            self.assertEqual(set(summary["groups"]), {"baseline", "checking"})
            for groups in summary["groups"].values():
                self.assertEqual(set(groups), {"arithmetic", "construction", "full_solution", "transfer"})

    def test_existing_output_directory_is_refused_before_health(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "existing"
            destination.mkdir()
            sentinel = destination / "saved.txt"
            sentinel.write_text("Keep this result.")
            result, _, _ = self.invoke(["--pilot", "urn-check", "--output-dir", str(destination)])
            self.assertNotEqual(result, 0)
            self.assertTrue(all(client.health_calls == 0 for client in FixtureClient.instances))
            self.assertEqual(sentinel.read_text(), "Keep this result.")
            self.assertEqual(list(destination.iterdir()), [sentinel])

    def test_source_change_stops_before_generation_and_marks_run_failed(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "changed"
            with patch.object(run_pilots, "source_hashes", return_value={"changed.py": "changed"}):
                result, _, errors = self.invoke(["--pilot", "urn-check", "--output-dir", str(destination)])
            self.assertEqual(result, 1)
            self.assertIn("Generation source changed", errors)
            self.assertFalse((destination / "urn-check1024.jsonl").exists())
            self.assertEqual(sum(len(client.calls) for client in FixtureClient.instances), 0)
            manifest = json.loads((destination / "run-manifest.json").read_text())
            self.assertEqual(manifest["status"], "failed")
            self.assertFalse(manifest["generation_sources_unchanged"])

    def test_interrupted_generation_keeps_partial_run_without_summary(self):
        class InterruptedClient(FixtureClient):
            def chat(self, *args, **kwargs):
                if len(self.calls) == 2:
                    raise KeyboardInterrupt
                return super().chat(*args, **kwargs)

        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "partial"
            result, _, _ = self.invoke(["--pilot", "urn-check", "--output-dir", str(destination)], InterruptedClient)
            self.assertNotEqual(result, 0)
            rows = read_rows(destination / "urn-check1024.jsonl")
            self.assertEqual(sum(row["type"] == "answer" for row in rows), 2)
            self.assertNotIn("complete", [row["type"] for row in rows])
            self.assertFalse((destination / "urn-check1024.summary.json").exists())
            manifest = json.loads((destination / "run-manifest.json").read_text())
            self.assertEqual(manifest["status"], "interrupted")
            self.assertEqual(result, 130)

    def test_failed_generation_keeps_partial_run_and_failure_manifest(self):
        class FailedClient(FixtureClient):
            def chat(self, *args, **kwargs):
                if len(self.calls) == 2:
                    raise OllamaError("Fixture inference failure")
                return super().chat(*args, **kwargs)

        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "partial"
            result, _, _ = self.invoke(["--pilot", "urn-check", "--output-dir", str(destination)], FailedClient)
            self.assertEqual(result, 1)
            rows = read_rows(destination / "urn-check1024.jsonl")
            self.assertEqual(sum(row["type"] == "answer" for row in rows), 2)
            self.assertNotIn("complete", [row["type"] for row in rows])
            self.assertFalse((destination / "urn-check1024.summary.json").exists())
            manifest = json.loads((destination / "run-manifest.json").read_text())
            self.assertEqual(manifest["status"], "failed")
            self.assertIn("Fixture inference failure", manifest["error"])

    def test_full_1024_pilot_uses_existing_runner_and_validates_all_sixty_calls(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "full"
            result, _, errors = self.invoke(["--pilot", "full", "--output-dir", str(destination)])
            self.assertEqual(result, 0, errors)
            calls = [call for client in FixtureClient.instances for call in client.calls]
            self.assertEqual(len(calls), 60)
            self.assertTrue(all(call["model"] == MODEL and call["max_tokens"] == MAX_TOKENS for call in calls))
            raw = destination / "full1024.jsonl"
            rows = read_rows(raw)
            self.assertEqual([row["type"] for row in rows], ["metadata", "question", "question", "question", "question", "complete"])
            self.assertEqual(rows[0]["model_metadata"]["digest"], "fixture-llama-digest")
            self.assertEqual(rows[0]["protocol"], protocol_metadata())
            summary = json.loads((destination / "full1024.summary.json").read_text())
            self.assertEqual(summary["actual_run"]["calls"], 60)
            self.assertEqual(analyze_results.analyze(raw)["actual_run"]["calls"], 60)


if __name__ == "__main__":
    unittest.main()
