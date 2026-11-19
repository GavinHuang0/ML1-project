"""Offline checks for explicitly amended, no-retry continuation after truncation."""

from contextlib import redirect_stderr, redirect_stdout
import copy
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from experiments.communication_pilot import protocol
from experiments.communication_pilot import runner as original
from experiments.communication_pilot import recovery as pilot
from experiments.communication_pilot import recovery_analysis
from local_llm import OllamaError
from run_format_followup import SchemaViolation
from tests.test_communication_pilot import answer, fixture_tasks, raw


def truncated_raw(**updates):
    value = raw("1")
    value["message"]["content"] = '{"explanation":"' + "Repeat the setup. " * 10
    value.update(done_reason="length", eval_count=1024)
    value.update(updates)
    return value


def generation(task, raw_value=None):
    return {"type": "generation", "question_id": task["id"], "arm": "self_revision",
            "profile": "strict_schema", "round": 2, "agent_id": 2,
            "raw": raw_value or truncated_raw(), "elapsed_seconds": 0.2}


class TruncationEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.task = fixture_tasks()[2]

    def test_only_output_cap_invalid_json_becomes_one_ineligible_outcome_without_calculator(self):
        source = generation(self.task)
        unchanged = copy.deepcopy(source)
        with patch("multi_agent_protocol.evaluate_expression", side_effect=AssertionError("No calculation")):
            result = pilot.evaluate_generation(source, self.task)
        self.assertEqual(source, unchanged)
        self.assertTrue(result["output_truncation_failure"])
        self.assertFalse(result["schema_conforms"])
        self.assertEqual(result["response"]["status"], "invalid_json")
        self.assertFalse(result["response"]["eligible"])
        self.assertFalse(result["response"]["calculator_attempted"])
        for field in ("explanation", "expression", "computed_fraction"):
            self.assertIsNone(result["response"][field])
        self.assertEqual(result["raw"], source["raw"])

    def test_nonlength_missing_cap_and_wrong_cap_do_not_relax_schema_enforcement(self):
        cases = [truncated_raw(done_reason="stop"), truncated_raw(eval_count=1023),
                 truncated_raw(eval_count=1025), truncated_raw(eval_count=1024.0)]
        missing = truncated_raw()
        missing.pop("eval_count")
        cases.append(missing)
        for value in cases:
            with self.subTest(reason=value.get("done_reason"), count=value.get("eval_count")):
                with self.assertRaises(SchemaViolation):
                    pilot.evaluate_generation(generation(self.task, value), self.task)

    def test_valid_json_schema_violation_remains_fatal_even_at_cap(self):
        for content in ('{"explanation":"setup","expression":"x=1"}',
                        '{"explanation":"setup","expression":"1","extra":true}',
                        '{"explanation":"setup"}',
                        '{"explanation":"setup","expression":"1","expression":"2"}'):
            value = truncated_raw()
            value["message"]["content"] = content
            with self.subTest(content=content), self.assertRaises(SchemaViolation):
                pilot.evaluate_generation(generation(self.task, value), self.task)

    def test_existing_valid_response_evaluation_is_exactly_unchanged(self):
        source = generation(self.task, raw(self.task["parameters"]["reference_expression"]))
        self.assertEqual(pilot.evaluate_generation(source, self.task),
                         original.evaluate_generation(source, self.task))
        self.assertNotIn("output_truncation_failure", pilot.evaluate_generation(source, self.task))

    def test_source_dependency_drift_is_rejected_before_even_service_health(self):
        class NoService:
            def health(self):
                raise AssertionError("Source drift must stop before service access")
        with tempfile.TemporaryDirectory() as temporary:
            dependency = Path(temporary) / "pinned-input.txt"
            dependency.write_bytes(b"frozen input")
            manifest = {"source_sha256": {str(dependency): original.digest(dependency.read_bytes())}}
            dependency.write_bytes(b"changed input")
            with self.assertRaisesRegex(ValueError, "Frozen source/input changed"):
                pilot.verify_runtime(NoService(), manifest)


class FixtureClient:
    calls = []
    tasks = {}
    pause_after = None
    pause_path = None

    def __init__(self, **options):
        self.options = options

    def health(self):
        return {"version": "fixture-runtime", "models": [
            {"name": "llama3.2:3b", "digest": "fixture-digest"}]}

    def chat(self, model, messages, **options):
        payload = json.loads(messages[1]["content"])
        task = self.tasks[payload["original_question"]]
        self.calls.append({"model": model, "messages": copy.deepcopy(messages), **copy.deepcopy(options)})
        if self.pause_after is not None and len(self.calls) >= self.pause_after:
            self.pause_path.touch()
        return raw(task["parameters"]["reference_expression"])


class RecoveryRunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        cls.parent = cls.root / "parent"
        cls.parent.mkdir()
        cls.source = cls.root / "failed-v1"
        cls.source.mkdir()
        cls.tasks = fixture_tasks()
        cls.initial = [answer(task, 0, agent) for task in cls.tasks for agent in range(10)]
        tasks = {task["id"]: task for task in cls.tasks}
        for record in cls.initial:
            record.update(evaluation_set="screening", format=copy.deepcopy(protocol.STRICT_SCHEMA),
                          seed=protocol.agent_seed(record["question_id"], 0, record["agent_id"]),
                          messages=[{"role": "system", "content": original.parent_pilot.SYSTEM},
                                    {"role": "user", "content": tasks[record["question_id"]]["prompt"]}])
        cls.parent_manifest = {"experiment_id": "fixture-format-parent", "tasks_snapshot": cls.tasks,
                               "model_digest": "fixture-digest", "ollama_version": "fixture-runtime",
                               "hardware_snapshot": {"fixture": "same-machine"}}
        for name in original.PARENT_FILES:
            value = cls.parent_manifest if name == "run-manifest.json" else {}
            (cls.parent / name).write_text(json.dumps(value) + "\n", encoding="utf-8", newline="\n")
        with patch.object(original, "load_parent", side_effect=cls.parent_loader):
            cls.old_plan = original.load_plan(original.CONFIG_PATH, cls.parent)
        cls.generations, cls.answers = [], []
        for index in range(146):
            call = original.build_call(cls.old_plan, index, cls.answers)
            value = truncated_raw() if index == 145 else raw(tasks[call["question_id"]]["parameters"]["reference_expression"])
            saved = {**copy.deepcopy(call), "type": "generation", "raw": value, "elapsed_seconds": 0.2}
            cls.generations.append(saved)
            if index < 145:
                cls.answers.append(original.evaluate_generation(saved, tasks[saved["question_id"]]))
        cls.write_rows(cls.source / "initial_panel.jsonl", cls.initial)
        cls.write_rows(cls.source / "generations.jsonl", cls.generations)
        cls.write_rows(cls.source / "answers.jsonl", cls.answers)
        cls.source_manifest = {key: value for key, value in cls.old_plan.items() if key != "first_revision_calls"}
        cls.source_manifest.update(status="failed", started_at="2026-11-17T00:00:00+00:00",
                                   model_digest="fixture-digest", ollama_version="fixture-runtime",
                                   hardware_snapshot={"fixture": "same-machine"},
                                   calls_completed=145, generations_saved=146,
                                   schema_support_check="failed_or_truncated",
                                   error="Strict schema violation: check runtime support or output truncation; raw preserved",
                                   active_call={key: cls.generations[-1][key] for key in
                                                ("call_index", "question_id", "round", "agent_id", "arm")})
        cls.source_manifest["snapshot_sha256"] = original.snapshot_hash(
            {key: cls.source_manifest[key] for key in original.SNAPSHOT_FIELDS})
        with patch("os.fsync"):
            original.checkpoint(cls.source, cls.source_manifest)
        FixtureClient.tasks = {task["prompt"]: task for task in cls.tasks}
        FixtureClient.calls = []
        FixtureClient.pause_after = None
        cls.completed = cls.root / "continued"
        code, output, error = cls.invoke(["--source-run", str(cls.source), "--output-dir", str(cls.completed)])
        if code != 0:
            cls.temporary.cleanup()
            raise AssertionError(output + error)
        cls.completed_calls = copy.deepcopy(FixtureClient.calls)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    @staticmethod
    def write_rows(path, records):
        path.write_text("".join(json.dumps(record, allow_nan=False) + "\n" for record in records),
                        encoding="utf-8", newline="\n")

    @classmethod
    def parent_loader(cls, directory):
        snapshot = {"directory": str(cls.parent), "experiment_id": cls.parent_manifest["experiment_id"],
                    "evidence_sha256": original.parent_hashes(cls.parent), "selected_profile": "strict_schema",
                    "model_digest": "fixture-digest", "ollama_version": "fixture-runtime",
                    "hardware_snapshot": {"fixture": "same-machine"},
                    "initial_panel_sha256": original.snapshot_hash(cls.initial),
                    "selection": {"fixture": "selected"}}
        return copy.deepcopy(cls.parent_manifest), copy.deepcopy(cls.initial), snapshot

    @classmethod
    def invoke(cls, arguments, client=FixtureClient, hardware=None):
        output, errors = io.StringIO(), io.StringIO()
        with patch.object(pilot, "PilotClient", client), \
                patch.object(original, "load_parent", side_effect=cls.parent_loader), \
                patch.object(pilot, "hardware_identity", return_value=hardware or {"fixture": "same-machine"}), \
                patch("os.fsync"), redirect_stdout(output), redirect_stderr(errors):
            code = pilot.main(arguments)
        return code, output.getvalue(), errors.getvalue()

    def setUp(self):
        FixtureClient.calls = []
        FixtureClient.pause_after = None
        FixtureClient.pause_path = None

    def target(self, suffix):
        return self.root / (self.id().split(".")[-1] + "-" + suffix)

    def test_complete_continuation_imports_exact_bytes_and_generates_only_334_pending_calls(self):
        self.assertEqual(len(self.completed_calls), 334)
        for name in ("initial_panel.jsonl", "generations.jsonl", "answers.jsonl"):
            self.assertTrue((self.completed / name).read_bytes().startswith((self.source / name).read_bytes()))
        self.assertEqual((self.completed / "initial_panel.jsonl").read_bytes(),
                         (self.source / "initial_panel.jsonl").read_bytes())
        answers = [json.loads(line) for line in (self.completed / "answers.jsonl").read_text().splitlines()]
        self.assertEqual(len(answers), 480)
        self.assertEqual(answers[:145], self.answers)
        self.assertTrue(answers[145]["output_truncation_failure"])
        self.assertEqual(self.completed_calls[0]["seed"], protocol.call_positions(self.tasks)[146]["seed"])
        summary = json.loads((self.completed / "summary.json").read_text())
        self.assertEqual(summary["total_revision_calls"], 480)
        self.assertEqual(summary["new_calls"], 334)
        self.assertEqual(summary["imported_revision_calls"], 146)
        self.assertEqual(summary["new_generation_cost"]["calls"], 334)
        self.assertEqual(summary["imported_revision_generation_cost"]["calls"], 146)
        self.assertEqual(summary["all_revision_generation_cost"]["calls"], 480)
        self.assertEqual(summary["execution_cost_including_initial_once"]["calls"], 560)
        self.assertEqual(summary["output_truncation_failures"]["imported"], 1)
        self.assertTrue(summary["protocol_amendment"]["post_failure"])
        for arm in protocol.ARMS:
            self.assertEqual(summary["arms"][arm]["new_generation_cost"]["calls"], 167)
            self.assertEqual(summary["arms"][arm]["imported_revision_generation_cost"]["calls"], 73)

    def test_dry_run_has_no_model_hardware_or_writes_and_reports_334_not_480_new_calls(self):
        target = self.target("dry")
        with patch.object(pilot, "PilotClient", side_effect=AssertionError("No service")), \
                patch.object(pilot, "hardware_identity", side_effect=AssertionError("No hardware")), \
                patch.object(original, "load_parent", side_effect=self.parent_loader), \
                redirect_stdout(io.StringIO()) as output:
            self.assertEqual(pilot.main(["--dry-run", "--source-run", str(self.source), "--output-dir", str(target)]), 0)
        plan = json.loads(output.getvalue())
        self.assertEqual(plan["planned_new_calls"], 334)
        self.assertEqual(plan["imported_revision_calls"], 146)
        self.assertEqual(plan["planned_revision_calls"], 480)
        self.assertFalse(target.exists())

    def test_hardware_or_runtime_change_is_rejected_before_inference_or_destination_creation(self):
        target = self.target("hardware")
        self.assertEqual(self.invoke(["--source-run", str(self.source), "--output-dir", str(target)],
                                     hardware={"fixture": "changed"})[0], 1)
        self.assertFalse(target.exists())
        class ChangedRuntime(FixtureClient):
            def health(self):
                return {"version": "changed", "models": [{"name": "llama3.2:3b", "digest": "fixture-digest"}]}
        self.assertEqual(self.invoke(["--source-run", str(self.source), "--output-dir", str(target)], client=ChangedRuntime)[0], 1)
        self.assertFalse(target.exists())
        self.assertEqual(FixtureClient.calls, [])

    def test_pause_resume_skips_imported_146_and_already_completed_new_calls(self):
        target = self.target("pause")
        FixtureClient.pause_path, FixtureClient.pause_after = target / ".pause-request", 2
        self.assertEqual(self.invoke(["--source-run", str(self.source), "--output-dir", str(target)])[0], 2)
        prefix = (target / "answers.jsonl").read_bytes()
        self.assertEqual(len(prefix.splitlines()), 148)
        FixtureClient.pause_after = 3
        self.assertEqual(self.invoke(["--resume", "--output-dir", str(target)])[0], 2)
        self.assertEqual(len(FixtureClient.calls), 3)
        self.assertTrue((target / "answers.jsonl").read_bytes().startswith(prefix))

    def test_returned_new_raw_orphan_is_evaluated_locally_without_a_second_model_request(self):
        target = self.target("orphan")
        implementation = pilot.evaluate_generation
        interrupted = False
        def interrupt_one_new_call(saved, task):
            nonlocal interrupted
            if saved.get("call_index") == 146 and not interrupted:
                interrupted = True
                raise KeyboardInterrupt
            return implementation(saved, task)
        with patch.object(pilot, "evaluate_generation", side_effect=interrupt_one_new_call):
            self.assertEqual(self.invoke(["--source-run", str(self.source), "--output-dir", str(target)])[0], 130)
        self.assertEqual(len(FixtureClient.calls), 1)
        self.assertEqual(len((target / "answers.jsonl").read_bytes().splitlines()), 146)
        FixtureClient.pause_path, FixtureClient.pause_after = target / ".pause-request", 2
        self.assertEqual(self.invoke(["--resume", "--output-dir", str(target)])[0], 2)
        self.assertEqual(len(FixtureClient.calls), 2)
        self.assertEqual(len((target / "answers.jsonl").read_bytes().splitlines()), 148)

    def test_complete_offline_reanalysis_is_read_only_and_reproduces_summary_without_live_runtime(self):
        before = {path.name: path.read_bytes() for path in self.completed.iterdir() if path.is_file()}
        with patch.object(pilot, "PilotClient", side_effect=AssertionError("No service")), \
                patch.object(pilot, "hardware_identity", side_effect=AssertionError("No hardware")), \
                patch.object(original, "load_parent", side_effect=self.parent_loader), \
                redirect_stdout(io.StringIO()) as output:
            self.assertEqual(pilot.main(["--analyze-run", str(self.completed)]), 0)
        self.assertTrue(json.loads(output.getvalue())["summary_reproduced"])
        self.assertEqual(before, {path.name: path.read_bytes() for path in self.completed.iterdir() if path.is_file()})
        self.assertEqual(FixtureClient.calls, [])

    def test_imported_prefix_tampering_and_rehashed_canonical_prompt_tampering_are_rejected(self):
        target = self.target("tamper")
        shutil.copytree(self.completed, target)
        path = target / "answers.jsonl"
        path.write_bytes(path.read_bytes().replace(b'"eligible": true', b'"eligible": false', 1))
        self.assertEqual(self.invoke(["--analyze-run", str(target)])[0], 1)
        shutil.copyfile(self.completed / "answers.jsonl", path)
        for name in ("generations.jsonl", "answers.jsonl"):
            path = target / name
            records = [json.loads(line) for line in path.read_text().splitlines()]
            records[146]["messages"][1]["content"] += " changed"
            self.write_rows(path, records)
        manifest_path = target / "run-manifest.json"
        manifest = json.loads(manifest_path.read_text())
        for name in ("generations.jsonl", "answers.jsonl"):
            manifest["evidence_checkpoint"][name]["sha256"] = original.digest((target / name).read_bytes())
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        code, _, error = self.invoke(["--analyze-run", str(target)])
        self.assertEqual(code, 1)
        self.assertIn("canonical", error.lower())
        self.assertEqual(FixtureClient.calls, [])

    def test_changed_frozen_configuration_and_existing_destination_do_not_overwrite_evidence(self):
        target = self.target("changed-config.json")
        config = copy.deepcopy(pilot.EXPECTED_CONFIG)
        config["protocol"]["max_tokens"] = 2048
        target.write_text(json.dumps(config), encoding="utf-8")
        self.assertEqual(self.invoke(["--dry-run", "--config", str(target), "--source-run", str(self.source)])[0], 1)
        before = (self.completed / "answers.jsonl").read_bytes()
        self.assertEqual(self.invoke(["--source-run", str(self.source), "--output-dir", str(self.completed)])[0], 1)
        self.assertEqual((self.completed / "answers.jsonl").read_bytes(), before)
        self.assertEqual(FixtureClient.calls, [])


if __name__ == "__main__":
    unittest.main()
