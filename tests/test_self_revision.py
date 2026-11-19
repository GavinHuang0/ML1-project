"""Offline checks for the shared-panel, self-only revision control."""

from contextlib import redirect_stderr, redirect_stdout
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from local_llm import OllamaError
import run_multi_agent as primary
from experiments.full_study_v1 import run_self_revision as control


class FixtureClient:
    instances = []
    label = "PRIMARY"

    def __init__(self, **options):
        self.calls, self.responses = [], []
        self.options = options
        FixtureClient.instances.append(self)

    def health(self):
        return {"version": "fixture-runtime", "models": [
            {"name": "llama3.2:3b", "digest": "fixture-digest"}]}

    def chat(self, model, messages, **options):
        index = len(self.calls)
        self.calls.append({"model": model, "messages": copy.deepcopy(messages), **options})
        raw = {"model": model, "done": True, "done_reason": "stop",
               "message": {"role": "assistant", "content": json.dumps({
                   "explanation": f"{self.label}_R{index // 10}_A{index % 10}",
                   "expression": "1/2", "private_score": "NEVER_SHARE_MODEL_METADATA"})},
               "prompt_eval_count": 20, "eval_count": 10}
        self.responses.append(raw)
        return raw


class ControlClient(FixtureClient):
    label = "CONTROL"


class SelfRevisionTests(unittest.TestCase):
    def setUp(self):
        FixtureClient.instances = []

    def invoke(self, module, arguments, client=FixtureClient):
        output, errors = io.StringIO(), io.StringIO()
        with patch.object(module, "OllamaClient", client), redirect_stdout(output), redirect_stderr(errors):
            code = module.main(arguments)
        return code, output.getvalue(), errors.getvalue()

    def parent(self, root, multiple=False):
        bank = json.loads((primary.ROOT / "config" / "multi_agent_pilot.json").read_text())
        if not multiple:
            bank["tasks"] = bank["tasks"][:1]
        bank["source"]["private_note"] = "MANIFEST_PRIVATE_METADATA"
        for task in bank["tasks"]:
            task["private_note"] = "TASK_PRIVATE_METADATA"
        path = Path(root) / "tasks.json"
        path.write_text(json.dumps(bank), encoding="utf-8")
        parent = Path(root) / "primary"
        code, _, error = self.invoke(primary, ["--tasks", str(path), "--output-dir", str(parent)])
        self.assertEqual(code, 0, error)
        return parent

    def complete_control(self, root, parent, extra=(), client=ControlClient):
        destination = Path(root) / "control"
        code, output, error = self.invoke(control, ["--parent-run", str(parent), "--output-dir", str(destination), *extra], client)
        self.assertEqual(code, 0, output + error)
        return destination, FixtureClient.instances[-1]

    def test_shared_panel_and_cost_are_exact_with_only_thirty_new_calls(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = self.parent(directory)
            destination, client = self.complete_control(directory, parent)
            self.assertEqual(len(client.calls), 30)
            base_records = [row for row in primary.jsonl(parent / "answers.jsonl") if row.get("type") == "answer"]
            records = [row for row in primary.jsonl(destination / "answers.jsonl") if row.get("type") == "answer"]
            self.assertEqual(len(records), 40)
            initial = [row for row in records if row["round"] == 0]
            for row, original in zip(initial, base_records[:10]):
                self.assertTrue(row["reused_round_zero"])
                self.assertEqual({key: row[key] for key in original}, original)
            for row, original in zip(records[10:], base_records[10:]):
                self.assertEqual(row["seed"], original["seed"])
                self.assertFalse(row["reused_round_zero"])
            rounds = primary.jsonl(destination / "rounds.jsonl")
            self.assertEqual(rounds[0], primary.jsonl(parent / "rounds.jsonl")[0])
            self.assertEqual(rounds[-1]["cumulative_total_tokens"], 1200)
            self.assertEqual(rounds[-1]["communication_total_tokens"], 900)
            self.assertAlmostEqual(rounds[-1]["cumulative_wall_seconds"], sum(r["round_wall_seconds"] for r in rounds))
            manifest = json.loads((destination / "run-manifest.json").read_text())
            self.assertEqual(manifest["status"], "complete")
            self.assertEqual(manifest["planned_new_calls"], 30)
            self.assertEqual(manifest["new_calls_completed"], 30)
            self.assertEqual(manifest["calls_completed"], 40)
            summary = json.loads((destination / "summary.json").read_text())
            self.assertEqual(summary["experiment_id"], "self-revision-calculator-v1")
            self.assertEqual(summary["selected_rounds"], {})
            self.assertIsNone(summary["calibration"])
            self.assertEqual(summary["new_generation_cost"]["input_tokens"], 600)
            self.assertEqual(summary["new_generation_cost"]["output_tokens"], 300)
            self.assertFalse((destination / "selection.json").exists())
            self.assertFalse((destination / "calibration.json").exists())

    def test_prompts_contain_only_own_preceding_response(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = self.parent(directory)
            destination, client = self.complete_control(directory, parent)
            for index, call in enumerate(client.calls):
                payload = json.loads(call["messages"][1]["content"])
                self.assertEqual(set(payload), {"original_question", "previous_round", "self_previous"})
                agent = index % 10
                expected = f"PRIMARY_R0_A{agent}" if index < 10 else f"CONTROL_R{index // 10 - 1}_A{agent}"
                self.assertEqual(payload["self_previous"]["explanation"], expected)
                self.assertEqual(set(payload["self_previous"]), {"explanation", "expression", "computed_fraction", "status"})
                text = json.dumps(call["messages"])
                for private in ("peers", "gold_fraction", "numeric_correct", "NEVER_SHARE_MODEL_METADATA",
                                "MANIFEST_PRIVATE_METADATA", "TASK_PRIVATE_METADATA", "private_score"):
                    self.assertNotIn(private, text)
            self.assertTrue((destination / "summary.json").exists())

    def test_dry_run_audits_parent_but_does_not_contact_ollama_or_write(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = self.parent(directory)
            destination = Path(directory) / "preview"
            with patch.object(control, "OllamaClient", side_effect=AssertionError("Offline preview")), \
                    redirect_stdout(io.StringIO()) as output:
                code = control.main(["--parent-run", str(parent), "--output-dir", str(destination), "--dry-run"])
            self.assertEqual(code, 0)
            plan = json.loads(output.getvalue())
            self.assertEqual(plan["planned_new_calls"], 30)
            self.assertEqual(plan["reused_round_zero_calls"], 10)
            self.assertEqual(len(plan["first_revision_calls"]), 10)
            self.assertFalse(destination.exists())

    def test_multiple_question_parent_reuses_all_initial_panels(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = self.parent(directory, multiple=True)
            destination, client = self.complete_control(directory, parent)
            self.assertEqual(len(client.calls), 120)
            manifest = json.loads((destination / "run-manifest.json").read_text())
            self.assertEqual(manifest["calls_completed"], 160)
            self.assertEqual(manifest["new_calls_completed"], 120)
            self.assertEqual(manifest["rounds_completed"], 16)

    def test_transport_failure_preserves_reused_panel_and_partial_new_calls(self):
        class FailingClient(ControlClient):
            def chat(self, *args, **kwargs):
                if len(self.calls) == 3:
                    raise OllamaError("Fixture failure")
                return super().chat(*args, **kwargs)
        with tempfile.TemporaryDirectory() as directory:
            parent = self.parent(directory)
            destination = Path(directory) / "partial"
            code, _, _ = self.invoke(control, ["--parent-run", str(parent), "--output-dir", str(destination)], FailingClient)
            self.assertEqual(code, 1)
            manifest = json.loads((destination / "run-manifest.json").read_text())
            self.assertEqual(manifest["status"], "failed")
            self.assertEqual(manifest["new_calls_completed"], 3)
            self.assertEqual(manifest["new_calls_attempted"], 4)
            self.assertEqual(manifest["calls_completed"], 13)
            self.assertEqual(len(primary.jsonl(destination / "answers.jsonl")), 13)
            self.assertFalse((destination / "summary.json").exists())
            with self.assertRaisesRegex(ValueError, "complete"):
                control.analyze_run(destination)

    def test_interruption_has_no_false_completion_marker(self):
        class InterruptedClient(ControlClient):
            def chat(self, *args, **kwargs):
                if self.calls:
                    raise KeyboardInterrupt
                return super().chat(*args, **kwargs)
        with tempfile.TemporaryDirectory() as directory:
            parent = self.parent(directory)
            destination = Path(directory) / "interrupted"
            code, _, _ = self.invoke(control, ["--parent-run", str(parent), "--output-dir", str(destination)], InterruptedClient)
            self.assertEqual(code, 130)
            manifest = json.loads((destination / "run-manifest.json").read_text())
            self.assertEqual(manifest["status"], "interrupted")
            self.assertFalse(any(row.get("type") == "complete" for row in primary.jsonl(destination / "answers.jsonl")))

    def test_offline_analysis_independently_audits_raw_data_and_shared_panel(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = self.parent(directory)
            destination, _ = self.complete_control(directory, parent)
            report = Path(directory) / "report.json"
            with patch.object(control, "OllamaClient", side_effect=AssertionError("Offline only")), \
                    redirect_stdout(io.StringIO()):
                code = control.main(["--analyze-run", str(destination), "--analysis-output", str(report)])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(report.read_text())["new_calls_completed"], 30)
            events = primary.jsonl(destination / "answers.jsonl")
            events[0]["raw"]["message"]["content"] = "changed initial response"
            (destination / "answers.jsonl").write_text("".join(json.dumps(r) + "\n" for r in events))
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                control.analyze_run(destination)

    def test_runtime_mismatch_and_existing_output_are_refused_before_generation(self):
        class DifferentRuntimeClient(ControlClient):
            def health(self):
                result = super().health()
                result["version"] = "changed-runtime"
                return result
        with tempfile.TemporaryDirectory() as directory:
            parent = self.parent(directory)
            destination = Path(directory) / "different-runtime"
            code, _, error = self.invoke(control, ["--parent-run", str(parent), "--output-dir", str(destination)], DifferentRuntimeClient)
            self.assertEqual(code, 1)
            self.assertIn("runtime", error)
            self.assertFalse(destination.exists())
            self.assertFalse(FixtureClient.instances[-1].calls)
            destination.mkdir()
            code, _, error = self.invoke(control, ["--parent-run", str(parent), "--output-dir", str(destination)])
            self.assertEqual(code, 1)
            self.assertIn("already exists", error)

    def test_calibration_shares_primary_references_and_is_not_refit_on_control(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = self.parent(directory)
            calibration = parent / "calibration.json"
            destination, _ = self.complete_control(directory, parent, extra=("--calibration", str(calibration)))
            artifact = json.loads(calibration.read_text())
            summary = control.analyze_run(destination)
            self.assertEqual(summary["calibration"], artifact["references"])
            self.assertEqual(summary["calibration_origin"], "shared_frozen_primary_reference")
            self.assertFalse(summary["selected_rounds"])
            with patch.object(control, "OllamaClient", side_effect=AssertionError("Offline only")), \
                    redirect_stdout(io.StringIO()):
                self.assertEqual(control.main(["--analyze-run", str(destination), "--calibration", str(calibration)]), 0)


if __name__ == "__main__":
    unittest.main()
