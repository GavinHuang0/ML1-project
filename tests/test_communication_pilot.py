"""Offline checks for selected-schema paired communication and self revision."""

from contextlib import redirect_stderr, redirect_stdout
import copy
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from experiments.communication_pilot import analysis, protocol
from experiments.communication_pilot import runner as pilot
from local_llm import OllamaError
from multi_agent_protocol import evaluate_response


ROOT = Path(__file__).resolve().parents[1]


def fixture_tasks():
    manifest = json.loads((ROOT / "config/format_followup_tasks.json").read_text(encoding="utf-8"))
    return [task for task in manifest["tasks"] if task["id"] in protocol.SCREENING_TASK_IDS]


def raw(expression):
    return {"model": "llama3.2:3b", "done": True, "done_reason": "stop",
            "message": {"role": "assistant", "content": json.dumps({
                "explanation": "Use the original quantities.", "expression": expression})},
            "prompt_eval_count": 200, "eval_count": 50}


def answer(task, round_index, agent, arm=None, expression=None):
    response = raw(expression if expression is not None else task["parameters"]["reference_expression"])
    record = {"type": "answer", "question_id": task["id"], "family": task["family"],
              "split": task["split"], "group_id": task["group_id"], "round": round_index,
              "agent_id": agent, "profile": "strict_schema", "raw": response,
              "elapsed_seconds": 0.1 if round_index == 0 else 0.2,
              "schema_conforms": True, "response": evaluate_response(response, task["probability"])}
    if arm is not None:
        record["arm"] = arm
    return record


def fixtures():
    tasks = fixture_tasks()
    initial = [answer(task, 0, agent) for task in tasks for agent in range(10)]
    revisions = [answer(task, round_index, agent, arm) for task in tasks for round_index in (1, 2, 3)
                 for agent in range(10) for arm in protocol.ARMS]
    return {"experiment_id": protocol.EXPERIMENT_ID, "tasks_snapshot": tasks}, initial, revisions


class CommunicationAnalysisTests(unittest.TestCase):
    def test_shared_initial_cost_is_counted_once_and_branch_curves_match(self):
        manifest, initial, revisions = fixtures()
        untouched = copy.deepcopy((initial, revisions))
        result = analysis.summarize(manifest, initial, revisions)
        self.assertEqual(result["new_calls"], 480)
        self.assertEqual(result["execution_cost_including_initial_once"]["calls"], 560)
        self.assertEqual(result["execution_cost_including_initial_once"]["total_tokens"], 140000)
        self.assertEqual(result["initial_generation_cost"]["total_tokens"], 20000)
        for arm in protocol.ARMS:
            self.assertEqual(result["arms"][arm]["new_generation_cost"]["calls"], 240)
            self.assertEqual([row["collective_correct"] for row in result["arms"][arm]["by_round"]], [8] * 4)
            self.assertEqual(result["arms"][arm]["by_round"][3]["cumulative_total_tokens"], 80000)
        for row in result["paired_comparison"]["by_round"]:
            self.assertEqual(row["metrics"]["collective_accuracy"], {"difference": 0.0, "interval_95": [0.0, 0.0]})
        self.assertEqual((initial, revisions), untouched)
        self.assertNotIn("selected_round", result)
        self.assertEqual(result["primary_comparison_round"], 3)
        self.assertEqual(result["primary_comparison"], result["paired_comparison"]["by_round"][3])

    def test_delivered_errors_are_partitioned_without_claiming_hidden_reasoning(self):
        manifest, initial, revisions = fixtures()
        task = manifest["tasks_snapshot"][0]
        variations = {0: "2*", 1: "1/0", 2: "2", 3: "0"}
        for index, record in enumerate(revisions):
            if record["question_id"] == task["id"] and record["arm"] == "communication" and record["round"] == 1:
                if record["agent_id"] in variations:
                    revisions[index] = answer(task, 1, record["agent_id"], "communication", variations[record["agent_id"]])
        result = analysis.summarize(manifest, initial, revisions)
        row = result["arms"]["communication"]["by_round"][1]
        diagnostics = row["diagnostic_counts"]
        self.assertEqual(diagnostics["unsupported_or_malformed_expression"], 1)
        self.assertEqual(diagnostics["undefined_division_by_zero"], 1)
        self.assertEqual(diagnostics["probability_out_of_range"], 1)
        self.assertEqual(diagnostics["eligible_wrong"], 1)
        self.assertEqual(sum(diagnostics.values()), 80)
        self.assertTrue(any("hidden reasoning" in note for note in result["notes"]))

    def test_minority_correctness_and_harmful_consensus_are_separate_diagnostics(self):
        manifest, initial, revisions = fixtures()
        task = manifest["tasks_snapshot"][0]
        for index, record in enumerate(initial):
            if record["question_id"] == task["id"] and record["agent_id"] >= 2:
                initial[index] = answer(task, 0, record["agent_id"], expression="0")
        for index, record in enumerate(revisions):
            if record["question_id"] == task["id"] and record["arm"] == "self_revision":
                revisions[index] = answer(task, record["round"], record["agent_id"], "self_revision", "0")
        result = analysis.summarize(manifest, initial, revisions)
        self.assertEqual(result["arms"]["communication"]["by_round"][0]["panels_with_correct_available_but_collective_wrong"], 1)
        self.assertEqual(result["arms"]["communication"]["by_round"][1]["beneficial_collective_revisions"], 1)
        self.assertEqual(result["arms"]["self_revision"]["by_round"][1]["ten_agent_wrong_consensus_panels"], 1)
        self.assertEqual(result["arms"]["self_revision"]["by_round"][1]["harmful_agent_revisions"], 2)
        paired = result["paired_comparison"]["by_round"][1]
        self.assertEqual(paired["communication_question_wins"], 1)
        self.assertEqual(paired["metrics"]["collective_accuracy"]["difference"], 0.125)
        self.assertEqual(paired["metrics"]["collective_accuracy"]["interval_95"], [0.0, 0.25])

    def test_missing_measurements_stay_unknown_and_duplicate_positions_are_rejected(self):
        manifest, initial, revisions = fixtures()
        revisions[0]["raw"].pop("eval_count")
        result = analysis.summarize(manifest, initial, revisions)
        self.assertIsNone(result["new_generation_cost"]["output_tokens"])
        self.assertIsNone(result["paired_comparison"]["by_round"][1]["metrics"]["cumulative_tokens_per_question"]["difference"])
        revisions[-1] = copy.deepcopy(revisions[0])
        with self.assertRaisesRegex(ValueError, "unique"):
            analysis.summarize(manifest, initial, revisions)


class CommunicationProtocolTests(unittest.TestCase):
    def test_shared_system_and_only_peer_visibility_differs_without_reference_leakage(self):
        tasks = fixture_tasks()
        task = {**tasks[0], "gold_fraction": "SECRET_GOLD", "parameters": {"secret": "SECRET_PARAMETERS"}}
        previous = [answer(tasks[0], 0, agent) for agent in range(10)]
        for record in previous:
            record["response"]["secret"] = "SECRET_RESPONSE"
            record["secret"] = "SECRET_RECORD"
        communication = protocol.build_messages(task, 1, 0, "communication", previous)
        revision = protocol.build_messages(task, 1, 0, "self_revision", previous)
        self.assertEqual(communication[0], revision[0])
        communication_payload, revision_payload = [json.loads(messages[1]["content"]) for messages in (communication, revision)]
        self.assertEqual(len(communication_payload.pop("peers")), 9)
        self.assertEqual(communication_payload, revision_payload)
        self.assertNotIn("SECRET", json.dumps((communication, revision)))
        self.assertEqual(communication, protocol.build_messages(task, 1, 0, "communication", previous))

    def test_snapshots_are_synchronous_question_specific_and_branch_specific(self):
        task = fixture_tasks()[0]
        previous = [answer(task, 1, agent, "communication") for agent in range(10)]
        self.assertEqual(json.loads(protocol.build_messages(task, 2, 0, "communication", previous)[1]["content"])["previous_round"], 1)
        with self.assertRaisesRegex(ValueError, "inconsistent"):
            protocol.build_messages(task, 2, 0, "self_revision", previous)
        previous[0]["round"] = 2
        with self.assertRaisesRegex(ValueError, "inconsistent"):
            protocol.build_messages(task, 2, 0, "communication", previous)
        with self.assertRaisesRegex(ValueError, "complete"):
            protocol.build_messages(task, 2, 0, "communication", previous[:9])

    def test_all_positions_share_pair_seeds_and_context_is_never_shortened(self):
        positions = protocol.call_positions(fixture_tasks())
        self.assertEqual(len(positions), 480)
        for index in range(0, 480, 2):
            left, right = positions[index:index + 2]
            self.assertEqual(left["seed"], right["seed"])
            self.assertEqual({left["arm"], right["arm"]}, set(protocol.ARMS))
            for key in ("question_id", "round", "agent_id", "profile"):
                self.assertEqual(left[key], right[key])
        with self.assertRaisesRegex(ValueError, "never shortened"):
            protocol.context_budget([{"role": "user", "content": "x" * 16000}])


class FixtureClient:
    all_calls = []
    tasks = {}
    pause_path = None
    pause_after = None
    bad_schema_after = None

    def __init__(self, **options):
        self.options = options

    def health(self):
        return {"version": "fixture-runtime", "models": [{"name": "llama3.2:3b", "digest": "fixture-digest"}]}

    def chat(self, model, messages, **options):
        payload = json.loads(messages[1]["content"])
        task = self.tasks[payload["original_question"]]
        FixtureClient.all_calls.append({"model": model, "messages": copy.deepcopy(messages), **copy.deepcopy(options)})
        if self.pause_after is not None and len(self.all_calls) >= self.pause_after:
            self.pause_path.touch()
        if self.bad_schema_after is not None and len(self.all_calls) >= self.bad_schema_after:
            return raw("x=1")
        return raw(task["parameters"]["reference_expression"])


class CommunicationRunnerTests(unittest.TestCase):
    """Exercise actual call journals; parent audit and model service are fixtures."""

    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        cls.parent = cls.root / "parent"
        cls.parent.mkdir()
        cls.tasks = fixture_tasks()
        cls.initial = [answer(task, 0, agent) for task in cls.tasks for agent in range(10)]
        by_id = {task["id"]: task for task in cls.tasks}
        for record in cls.initial:
            record.update(evaluation_set="screening", format=copy.deepcopy(protocol.STRICT_SCHEMA),
                          seed=protocol.agent_seed(record["question_id"], 0, record["agent_id"]),
                          messages=[{"role": "system", "content": pilot.parent_pilot.SYSTEM},
                                    {"role": "user", "content": by_id[record["question_id"]]["prompt"]}])
        cls.parent_manifest = {"experiment_id": "fixture-format-parent", "tasks_snapshot": cls.tasks,
                               "model_digest": "fixture-digest", "ollama_version": "fixture-runtime",
                               "hardware_snapshot": {"fixture": "same-machine"}}
        (cls.parent / "run-manifest.json").write_text(json.dumps(cls.parent_manifest), encoding="utf-8")
        (cls.parent / "answers.jsonl").write_text("".join(json.dumps(record) + "\n" for record in cls.initial), encoding="utf-8", newline="\n")
        (cls.parent / "generations.jsonl").write_text("{}\n", encoding="utf-8")
        cls.parent_summary = {"recommendation": "strict_schema", "sets": {"screening": {"fixture": "selected"}}}
        (cls.parent / "summary.json").write_text(json.dumps(cls.parent_summary), encoding="utf-8")
        FixtureClient.tasks = {task["prompt"]: task for task in cls.tasks}
        FixtureClient.all_calls = []
        FixtureClient.pause_after = FixtureClient.bad_schema_after = None
        cls.completed = cls.root / "completed"
        code, output, errors = cls.invoke(["--parent-run", str(cls.parent), "--output-dir", str(cls.completed)])
        if code != 0:
            cls.temporary.cleanup()
            raise AssertionError(output + errors)
        cls.completed_calls = copy.deepcopy(FixtureClient.all_calls)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def setUp(self):
        FixtureClient.all_calls = []
        FixtureClient.pause_after = FixtureClient.bad_schema_after = None
        FixtureClient.pause_path = None

    @classmethod
    def parent_audit(cls, directory):
        return {"status": "complete", "summary_reproduced": True,
                "summary": json.loads((Path(directory) / "summary.json").read_text(encoding="utf-8"))}

    @classmethod
    def invoke(cls, arguments, client=FixtureClient, hardware=None):
        output, errors = io.StringIO(), io.StringIO()
        with patch.object(pilot, "PilotClient", client), \
                patch.object(pilot.parent_pilot, "analyze_run", side_effect=cls.parent_audit), \
                patch.object(pilot, "hardware_identity", return_value=hardware or {"fixture": "same-machine"}), \
                patch("os.fsync"), redirect_stdout(output), redirect_stderr(errors):
            code = pilot.main(arguments)
        return code, output.getvalue(), errors.getvalue()

    def new_target(self, label):
        return self.root / (self.id().split(".")[-1] + "-" + label)

    def test_complete_run_has_480_new_calls_exact_shared_panel_and_selected_schema_every_round(self):
        self.assertEqual(len(self.completed_calls), 480)
        saved = [json.loads(line) for line in (self.completed / "initial_panel.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(saved, self.initial)
        summary = json.loads((self.completed / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["new_calls"], 480)
        self.assertEqual(summary["primary_comparison_round"], 3)
        for call in self.completed_calls:
            self.assertEqual(call["format_value"], protocol.STRICT_SCHEMA)
            self.assertEqual(call["messages"][0]["content"], protocol.REVISION_SYSTEM)
            self.assertNotIn("gold_fraction", json.dumps(call["messages"]))
            self.assertNotIn("reference_expression", json.dumps(call["messages"]))
        for index in range(0, 480, 2):
            self.assertEqual(self.completed_calls[index]["seed"], self.completed_calls[index + 1]["seed"])

    def test_dry_run_is_offline_and_does_not_create_destination(self):
        target = self.new_target("dry")
        with patch.object(pilot, "PilotClient", side_effect=AssertionError("No service")), \
                patch.object(pilot, "hardware_identity", side_effect=AssertionError("No hardware")), \
                patch.object(pilot.parent_pilot, "analyze_run", side_effect=self.parent_audit), \
                redirect_stdout(io.StringIO()) as output:
            self.assertEqual(pilot.main(["--dry-run", "--parent-run", str(self.parent), "--output-dir", str(target)]), 0)
        plan = json.loads(output.getvalue())
        self.assertEqual(plan["planned_new_calls"], 480)
        self.assertEqual(plan["reused_round_zero_calls"], 80)
        self.assertEqual(len(plan["first_revision_calls"]), 160)
        self.assertFalse(target.exists())
        self.assertTrue(all(task["split"] == "development" for task in plan["tasks_snapshot"]))

    def test_parent_selection_and_changed_generation_config_rejected_before_inference(self):
        path = self.parent / "summary.json"
        original = path.read_bytes()
        try:
            path.write_text(json.dumps({**self.parent_summary, "recommendation": "complete_expression_for_review"}), encoding="utf-8")
            code, _, error = self.invoke(["--dry-run", "--parent-run", str(self.parent)])
            self.assertEqual(code, 1)
            self.assertIn("selecting strict_schema", error)
        finally:
            path.write_bytes(original)
        config = copy.deepcopy(pilot.EXPECTED_CONFIG)
        config["protocol"]["temperature"] = 0
        changed = self.new_target("changed-config.json")
        changed.write_text(json.dumps(config), encoding="utf-8")
        code, _, error = self.invoke(["--dry-run", "--config", str(changed), "--parent-run", str(self.parent)])
        self.assertEqual(code, 1)
        self.assertEqual(FixtureClient.all_calls, [])

    def test_hardware_and_runtime_change_leave_no_new_run_or_model_calls(self):
        target = self.new_target("hardware")
        self.assertEqual(self.invoke(["--parent-run", str(self.parent), "--output-dir", str(target)], hardware={"fixture": "different"})[0], 1)
        self.assertFalse(target.exists())
        class ChangedRuntime(FixtureClient):
            def health(self):
                return {"version": "different", "models": [{"name": "llama3.2:3b", "digest": "fixture-digest"}]}
        self.assertEqual(self.invoke(["--parent-run", str(self.parent), "--output-dir", str(target)], client=ChangedRuntime)[0], 1)
        self.assertFalse(target.exists())
        self.assertEqual(FixtureClient.all_calls, [])

    def test_pause_resume_preserves_prefix_and_does_not_replay_calls(self):
        target = self.new_target("paused")
        FixtureClient.pause_path, FixtureClient.pause_after = target / ".pause-request", 3
        self.assertEqual(self.invoke(["--parent-run", str(self.parent), "--output-dir", str(target)])[0], 2)
        prefix = (target / "answers.jsonl").read_bytes()
        self.assertEqual(len(prefix.splitlines()), 3)
        FixtureClient.pause_after = 4
        self.assertEqual(self.invoke(["--resume", "--output-dir", str(target)])[0], 2)
        self.assertEqual(len(FixtureClient.all_calls), 4)
        self.assertTrue((target / "answers.jsonl").read_bytes().startswith(prefix))
        self.assertEqual(len((target / "answers.jsonl").read_bytes().splitlines()), 4)

    def test_orphaned_returned_raw_is_recovered_without_repeating_generation(self):
        target = self.new_target("orphan")
        original = pilot.evaluate_generation
        interrupted = False
        def force_once(generation, task):
            nonlocal interrupted
            if not interrupted:
                interrupted = True
                raise KeyboardInterrupt
            return original(generation, task)
        with patch.object(pilot, "evaluate_generation", side_effect=force_once):
            self.assertEqual(self.invoke(["--parent-run", str(self.parent), "--output-dir", str(target)])[0], 130)
        self.assertEqual(len(FixtureClient.all_calls), 1)
        self.assertEqual((target / "answers.jsonl").read_bytes(), b"")
        FixtureClient.pause_path, FixtureClient.pause_after = target / ".pause-request", 2
        self.assertEqual(self.invoke(["--resume", "--output-dir", str(target)])[0], 2)
        self.assertEqual(len(FixtureClient.all_calls), 2)
        self.assertEqual(len((target / "generations.jsonl").read_bytes().splitlines()), 2)
        self.assertEqual(len((target / "answers.jsonl").read_bytes().splitlines()), 2)

    def test_schema_violation_is_preserved_and_resume_does_not_repair_it(self):
        target = self.new_target("bad-schema")
        FixtureClient.bad_schema_after = 1
        code, _, error = self.invoke(["--parent-run", str(self.parent), "--output-dir", str(target)])
        self.assertEqual(code, 1)
        self.assertIn("schema violation", error.lower())
        self.assertIn(b"x=1", (target / "generations.jsonl").read_bytes())
        self.assertEqual((target / "answers.jsonl").read_bytes(), b"")
        self.assertEqual(self.invoke(["--resume", "--output-dir", str(target)])[0], 1)
        self.assertEqual(len(FixtureClient.all_calls), 1)

    def test_offline_analysis_is_read_only_and_recomputes_complete_summary(self):
        before = {path.relative_to(self.completed): path.read_bytes() for path in self.completed.rglob("*") if path.is_file()}
        with patch.object(pilot, "PilotClient", side_effect=AssertionError("No service")), \
                patch.object(pilot, "hardware_identity", side_effect=AssertionError("No hardware")), \
                patch.object(pilot.parent_pilot, "analyze_run", side_effect=self.parent_audit), \
                redirect_stdout(io.StringIO()) as output:
            self.assertEqual(pilot.main(["--analyze-run", str(self.completed)]), 0)
        audit = json.loads(output.getvalue())
        self.assertTrue(audit["summary_reproduced"])
        self.assertEqual(before, {path.relative_to(self.completed): path.read_bytes() for path in self.completed.rglob("*") if path.is_file()})
        self.assertEqual(FixtureClient.all_calls, [])

    def test_changed_evidence_and_canonical_prompt_tampering_are_rejected(self):
        target = self.new_target("tamper")
        shutil.copytree(self.completed, target)
        answers = target / "answers.jsonl"
        answers.write_bytes(answers.read_bytes().replace(b'"eligible": true', b'"eligible": false', 1))
        self.assertEqual(self.invoke(["--analyze-run", str(target)])[0], 1)
        shutil.copyfile(self.completed / "answers.jsonl", answers)
        raw_path, evaluated_path = target / "generations.jsonl", target / "answers.jsonl"
        for path in (raw_path, evaluated_path):
            records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            records[0]["messages"][1]["content"] += " modified"
            path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8", newline="\n")
        manifest_path = target / "run-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for name in pilot.JOURNALS:
            manifest["evidence_checkpoint"][name]["sha256"] = pilot.digest((target / name).read_bytes())
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        code, _, error = self.invoke(["--analyze-run", str(target)])
        self.assertEqual(code, 1)
        self.assertIn("canonical", error)
        self.assertEqual(FixtureClient.all_calls, [])

    def test_existing_completed_destination_and_unavailable_service_are_not_overwritten(self):
        before = (self.completed / "answers.jsonl").read_bytes()
        self.assertEqual(self.invoke(["--parent-run", str(self.parent), "--output-dir", str(self.completed)])[0], 1)
        self.assertEqual(self.invoke(["--resume", "--output-dir", str(self.completed)])[0], 1)
        self.assertEqual((self.completed / "answers.jsonl").read_bytes(), before)
        class Unavailable(FixtureClient):
            def health(self):
                raise OllamaError("Fixture service unavailable")
        target = self.new_target("unavailable")
        self.assertEqual(self.invoke(["--parent-run", str(self.parent), "--output-dir", str(target)], client=Unavailable)[0], 1)
        self.assertFalse(target.exists())
        self.assertEqual(FixtureClient.all_calls, [])


if __name__ == "__main__":
    unittest.main()
