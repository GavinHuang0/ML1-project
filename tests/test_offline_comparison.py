"""Exact, prefix-only voting/stopping and read-only comparison checks."""

from contextlib import redirect_stderr, redirect_stdout
import copy
from fractions import Fraction
import io
import json
import hashlib
import csv
import shutil
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from experiments.offline_policies import protocol
from tests.test_communication_pilot import answer, fixture_tasks
from experiments.communication_pilot.protocol import call_positions


ROOT = Path(__file__).resolve().parents[1]


def panel(values, round_index=0):
    return [{"agent_id": index, "round": round_index,
             "response": {"eligible": value is not None,
                          "json_valid": True, "required_fields_valid": True,
                          "calculator_success": value is not None,
                          "probability_in_range": None,
                          "computed_fraction": str(value) if value is not None else None}}
            for index, value in enumerate(values)]


def predictions(panels, voter="plurality"):
    return [protocol.vote_prediction(panels[:index + 1], voter)
            for index in range(len(panels))]


def complete_fixture():
    tasks = fixture_tasks()
    by_id = {task["id"]: task for task in tasks}
    initial = [answer(task, 0, agent) for task in tasks for agent in range(10)]
    revisions = [{**answer(by_id[position["question_id"]], position["round"],
                           position["agent_id"], position["arm"]), **position}
                 for position in call_positions(tasks)]
    manifest = {"experiment_id": "strict-schema-communication-self-revision-pilot-recovery-v2",
                "status": "complete", "tasks_snapshot": tasks}
    return manifest, initial, revisions


class VotingAndStoppingTests(unittest.TestCase):
    def test_equivalent_rationals_are_one_exact_value_and_ties_abstain(self):
        value = protocol.vote_prediction([panel(["1/2", "2/4", "3/6", "0.5"] + ["1/3"] * 3 + [None] * 3)], "plurality")
        self.assertEqual(value["answer"], "1/2")
        self.assertEqual(value["scores"], {"1/3": "3", "1/2": "4"})
        self.assertEqual(value["current_support"], 4)
        self.assertEqual(value["current_eligible_agents"], 7)
        tied = protocol.vote_prediction([panel(["1/2"] * 5 + ["1/3"] * 5)], "plurality")
        self.assertIsNone(tied["answer"])
        self.assertEqual(tied["abstention_reason"], "tied_scores")
        self.assertEqual(tied["current_support"], 0)
        empty = protocol.vote_prediction([panel([None] * 10)], "plurality")
        self.assertIsNone(empty["answer"])
        self.assertEqual(empty["abstention_reason"], "no_eligible_scores")

    def test_initial_anchor_counts_round_zero_once_and_adds_only_current_round(self):
        prefix = [panel(["1"] * 6 + ["2"] * 4)]
        first = protocol.vote_prediction(prefix, "initial_anchored")
        self.assertEqual(first["total_score_weight"], "10")
        prefix.append(panel(["1"] * 4 + ["2"] * 6, 1))
        tied = protocol.vote_prediction(prefix, "initial_anchored")
        self.assertEqual(tied["scores"], {"1": "10", "2": "10"})
        self.assertIsNone(tied["answer"])
        prefix.append(panel(["1"] * 8 + ["2"] * 2, 2))
        later = protocol.vote_prediction(prefix, "initial_anchored")
        self.assertEqual(later["scores"], {"1": "14", "2": "6"})
        self.assertEqual(later["total_score_weight"], "20")

    def test_agent_history_has_one_unit_per_agent_and_deduplicates_exact_values(self):
        prefix = [panel(["1/2", "1/2", "1/3"] + [None] * 7),
                  panel(["1/3", "2/4", None] + [None] * 7, 1)]
        value = protocol.vote_prediction(prefix, "agent_history")
        self.assertEqual(value["scores"], {"1/3": "3/2", "1/2": "3/2"})
        self.assertEqual(value["total_score_weight"], "3")
        self.assertIsNone(value["answer"])
        prefix.append(panel(["1/3", "3/6", None] + [None] * 7, 2))
        repeated = protocol.vote_prediction(prefix, "agent_history")
        self.assertEqual(repeated["scores"], value["scores"])
        self.assertEqual(repeated["total_score_weight"], "3")

    def test_gating_uses_original_ten_agents_and_never_weighted_scores(self):
        scarce = [panel(["1"] * 2 + [None] * 8, r) for r in range(4)]
        decision = protocol.choose_stop(predictions(scarce), "high_agreement_8")
        self.assertEqual(decision["stopping_round"], 3)
        self.assertFalse(decision["triggered"])
        prefix = [panel(["1"] * 6 + ["2"] * 4)]
        prefix += [panel(["1"] * 3 + ["2"] * 7, r) for r in range(1, 4)]
        anchored = predictions(prefix, "initial_anchored")
        self.assertEqual(anchored[1]["scores"]["2"], "11")
        self.assertEqual(anchored[1]["current_support"], 7)
        self.assertFalse(protocol.choose_stop(anchored, "high_agreement_8")["triggered"])
        history = predictions(prefix, "agent_history")
        self.assertEqual(history[1]["scores"]["2"], "11/2")
        self.assertEqual(protocol.choose_stop(history, "stable_majority_6")["stopping_round"], 2)

    def test_stable_majority_requires_same_unique_answer_and_six_in_each_panel(self):
        # A five-vote plurality followed by six is not a confirmed majority.
        panels = [panel(["1"] * 5 + ["2"] * 3 + ["3"] * 2),
                  panel(["1"] * 6 + ["2"] * 4, 1),
                  panel(["1"] * 6 + ["2"] * 4, 2),
                  panel(["1"] * 6 + ["2"] * 4, 3)]
        chosen = protocol.choose_stop(predictions(panels), "stable_majority_6")
        self.assertEqual(chosen["stopping_round"], 2)
        switched = [panel(["1"] * 6 + ["2"] * 4),
                    panel(["1"] * 4 + ["2"] * 6, 1),
                    panel(["1"] * 5 + ["2"] * 5, 2),
                    panel(["1"] * 4 + ["2"] * 6, 3)]
        chosen = protocol.choose_stop(predictions(switched), "stable_majority_6")
        self.assertFalse(chosen["triggered"])
        self.assertEqual(chosen["stopping_round"], 3)

    def test_policy_decisions_ignore_reference_labels_and_future_outcomes(self):
        panels = [panel(["1"] * 8 + ["2"] * 2, r) for r in range(4)]
        original = copy.deepcopy(panels)
        observed = protocol.choose_stop(predictions(panels), "high_agreement_8")
        self.assertEqual(observed["stopping_round"], 0)
        for r, current in enumerate(panels):
            for row in current:
                row.update(gold_fraction="SECRET_REFERENCE", correct=False,
                           agent_correct={"secret": True}, future_correct=True)
                if r:
                    row["response"]["computed_fraction"] = "3"
        changed = protocol.choose_stop(predictions(panels), "high_agreement_8")
        self.assertEqual(changed["stopping_round"], observed["stopping_round"])
        self.assertEqual(changed["prediction"]["answer"], observed["prediction"]["answer"])
        for voter in protocol.VOTING_RULES:
            self.assertEqual(protocol.vote_prediction([panels[0]], voter),
                             protocol.vote_prediction([original[0]], voter))

    def test_fixed_round_controls_use_selected_voter_and_full_declared_round(self):
        panels = [panel([str(r + 1)] * 10, r) for r in range(4)]
        observed = predictions(panels)
        for r in range(4):
            chosen = protocol.choose_stop(observed, f"fixed_round_{r}")
            self.assertEqual(chosen["stopping_round"], r)
            self.assertEqual(chosen["prediction"]["answer"], str(r + 1))
            self.assertFalse(chosen["triggered"])

    def test_malformed_panels_and_unknown_policies_are_rejected(self):
        good = panel(["1"] * 10)
        for bad in (good[:9], [*good[:9], good[0]], panel(["1"] * 10, 1)):
            with self.subTest(size=len(bad)), self.assertRaises(ValueError):
                protocol.vote_prediction([bad], "plurality")
        with self.assertRaises(ValueError):
            protocol.vote_prediction([good], "unfrozen_voter")
        with self.assertRaises(ValueError):
            protocol.choose_stop(predictions([panel(["1"] * 10, r) for r in range(4)]), "unfrozen_stop")


class AnalysisGridTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from experiments.offline_policies import analysis
        cls.analysis = analysis
        cls.manifest, cls.initial, cls.revisions = complete_fixture()
        cls.result = analysis.analyze(cls.manifest, cls.initial, cls.revisions)

    def row(self, stop, voter="plurality", arm="communication"):
        return next(row for row in self.result["comparisons"] if
                    (row["arm"], row["voting_rule"], row["stopping_rule"]) == (arm, voter, stop))

    def test_complete_grid_has_all_controls_policies_and_no_winner(self):
        self.assertEqual(len(self.result["comparisons"]), 36)
        self.assertEqual(len(self.result["per_question"]), 288)
        self.assertEqual(len(self.result["round_predictions"]), 192)
        self.assertEqual(len(self.result["cross_arm_comparisons"]), 18)
        self.assertEqual(len(self.result["joint_policy_costs"]), 18)
        expected = {(arm, vote, stop) for arm in protocol.ARMS for vote in protocol.VOTING_RULES
                    for stop in protocol.STOPPING_RULES}
        observed = {(row["arm"], row["voting_rule"], row["stopping_rule"])
                    for row in self.result["comparisons"]}
        self.assertEqual(observed, expected)
        self.assertFalse(self.result["selection"]["performed"])
        self.assertIsNone(self.result["selection"]["winner"])
        self.assertIsNone(self.result["selection"]["ranking"])
        self.assertEqual(self.result["additional_model_calls"], 0)

    def test_whole_completed_round_costs_and_shared_initial_count_once(self):
        expected = {"fixed_round_3": (320, 80000), "high_agreement_8": (80, 20000),
                    "stable_majority_6": (160, 40000)}
        for voter in protocol.VOTING_RULES:
            for stop, (calls, tokens) in expected.items():
                with self.subTest(voter=voter, stopping=stop):
                    value = self.row(stop, voter)
                    self.assertEqual(value["consumed_logical_calls"], calls)
                    self.assertEqual(value["total_tokens"], tokens)
                    self.assertEqual(value["correct_questions"], 8)
        self.assertEqual(self.result["source_generation_cost_including_initial_once"]["unique_calls"], 560)
        for stop, calls, tokens in (("fixed_round_3", 560, 140000),
                                   ("high_agreement_8", 80, 20000),
                                   ("stable_majority_6", 240, 60000)):
            joint = next(row for row in self.result["joint_policy_costs"]
                         if row["voting_rule"] == "plurality" and row["stopping_rule"] == stop)
            self.assertEqual(joint["unique_calls"], calls)
            self.assertEqual(joint["total_tokens"], tokens)
            self.assertEqual(joint["shared_initial_calls_counted_once"], 80)

    def test_paired_group_intervals_preserve_pairing_and_known_savings(self):
        metadata = self.result["bootstrap"]
        self.assertEqual(metadata["groups"], 8)
        self.assertEqual(metadata["draws"], 2000)
        self.assertEqual(metadata["seed"], 20261118)
        self.assertTrue(metadata["same_draws_across_all_policies_and_arms"])
        reference = self.row("fixed_round_3")["versus_primary_plurality_fixed_round_3"]
        self.assertEqual(reference["metrics"]["accuracy_difference"]["interval_95"], [0.0, 0.0])
        saved = self.row("high_agreement_8")["versus_same_voter_fixed_round_3"]
        self.assertEqual(saved["correct_question_gains"], 0)
        self.assertEqual(saved["correct_question_losses"], 0)
        self.assertEqual(saved["metrics"]["token_savings_fraction"]["estimate"], 0.75)
        self.assertEqual(saved["metrics"]["token_savings_fraction"]["interval_95"], [0.75, 0.75])

    def test_gold_and_future_rounds_do_not_change_early_decision_or_consumed_cost(self):
        altered_manifest, initial, revisions = copy.deepcopy((self.manifest, self.initial, self.revisions))
        for task in altered_manifest["tasks_snapshot"]:
            task["gold_fraction"] = "1/123" if task["probability"] else "0"
        for record in revisions:
            record["response"]["computed_fraction"] = "0"
            record["raw"]["prompt_eval_count"] = 999
            record["elapsed_seconds"] = 999
            record["future_correct"] = True
        altered = self.analysis.analyze(altered_manifest, initial, revisions)
        before = [row for row in self.result["per_question"] if row["stopping_rule"] == "high_agreement_8"]
        after = [row for row in altered["per_question"] if row["stopping_rule"] == "high_agreement_8"]
        for old, new in zip(before, after):
            for field in ("answer", "stopping_round", "stop_reason", "consumed_logical_calls",
                          "total_tokens", "request_seconds"):
                self.assertEqual(old[field], new[field])
        self.assertTrue(all(row["correct"] for row in before))
        self.assertTrue(all(not row["correct"] for row in after))

    def test_no_answer_means_zero_accuracy_coverage_and_null_conditional_accuracy(self):
        initial, revisions = copy.deepcopy((self.initial, self.revisions))
        for record in initial + revisions:
            record["response"]["computed_fraction"] = "1/4" if record["agent_id"] < 5 else "3/4"
        result = self.analysis.analyze(self.manifest, initial, revisions)
        for row in result["comparisons"]:
            self.assertEqual(row["correct_questions"], 0)
            self.assertEqual(row["accuracy"], 0)
            self.assertEqual(row["coverage"], 0)
            self.assertIsNone(row["accuracy_among_answered"])
            interval = row["uncertainty"]["accuracy_among_answered"]
            self.assertIsNone(interval["interval_95"])
            self.assertEqual(interval["valid_bootstrap_draws"], 0)


class OfflineRunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from experiments.offline_policies import runner
        cls.runner = runner
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        cls.source = cls.root / "source"
        cls.source.mkdir()
        cls.parent = cls.root / "parent"
        cls.parent.mkdir()
        cls.failed = cls.root / "failed-prefix"
        cls.failed.mkdir()
        (cls.parent / "evidence.json").write_text('{"parent":"fixture"}', encoding="utf-8")
        (cls.failed / "evidence.json").write_text('{"prefix":"fixture"}', encoding="utf-8")
        cls.generation_config = cls.root / "generation.json"
        cls.generation_config.write_text('{"generation":"fixture"}', encoding="utf-8")
        manifest, initial, revisions = complete_fixture()
        cls.initial, cls.revisions = initial, revisions
        manifest.update(configuration_path=str(cls.generation_config),
                        source_sha256={str(cls.generation_config): runner.digest(cls.generation_config.read_bytes())},
                        parent_snapshot={"directory": str(cls.parent), "evidence_sha256": {
                            "evidence.json": runner.digest((cls.parent / "evidence.json").read_bytes())}},
                        source_run_snapshot={"directory": str(cls.failed), "evidence_sha256": {
                            "evidence.json": runner.digest((cls.failed / "evidence.json").read_bytes())}},
                        model_digest="fixture-model", ollama_version="fixture-runtime",
                        protocol_snapshot={"failure_policy": "fixture"})
        cls.manifest = manifest
        cls.write_rows(cls.source / "initial_panel.jsonl", initial)
        cls.write_rows(cls.source / "answers.jsonl", revisions)
        generations = [{**{key: value for key, value in row.items()
                            if key not in ("response", "schema_conforms")}, "type": "generation"}
                       for row in revisions]
        cls.write_rows(cls.source / "generations.jsonl", generations)
        (cls.source / "summary.json").write_text('{"fixture":"audited"}', encoding="utf-8")
        (cls.source / "run-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        cls.completed = cls.root / "complete"
        code, output, error = cls.invoke(["--source-run", str(cls.source), "--output-dir", str(cls.completed)])
        if code != 0:
            cls.temporary.cleanup()
            raise AssertionError(output + error)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    @staticmethod
    def write_rows(path, records):
        path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8", newline="\n")

    @staticmethod
    def audit_result():
        return {"offline_audit": "passed", "status": "complete", "summary_reproduced": True,
                "calls_completed": 480, "generations_saved": 480}

    @classmethod
    def invoke(cls, arguments, audit=None):
        output, errors = io.StringIO(), io.StringIO()
        with patch.object(cls.runner.recovery, "analyze_run", side_effect=audit or (lambda _: cls.audit_result())), \
                patch.object(cls.runner.recovery, "PilotClient", side_effect=AssertionError("No model service")), \
                patch.object(cls.runner.recovery, "hardware_identity", side_effect=AssertionError("No hardware")), \
                patch("socket.create_connection", side_effect=AssertionError("No sockets")), \
                patch("subprocess.run", side_effect=AssertionError("No external process")), \
                redirect_stdout(output), redirect_stderr(errors):
            code = cls.runner.main(arguments)
        return code, output.getvalue(), errors.getvalue()

    def target(self, suffix):
        return self.root / (self.id().split(".")[-1] + "-" + suffix)

    @staticmethod
    def file_bytes(directory):
        return {path.name: path.read_bytes() for path in directory.iterdir() if path.is_file()}

    def test_dry_run_has_exact_grid_no_source_mutation_or_output_creation(self):
        target = self.target("dry")
        before = self.file_bytes(self.source)
        with patch.object(Path, "mkdir", side_effect=AssertionError("Dry run creates no directory")), \
                patch.object(Path, "write_bytes", side_effect=AssertionError("Dry run writes nothing")), \
                patch.object(Path, "write_text", side_effect=AssertionError("Dry run writes nothing")):
            code, output, error = self.invoke(["--dry-run", "--source-run", str(self.source), "--output-dir", str(target)])
        self.assertEqual(code, 0, output + error)
        plan = json.loads(output)
        self.assertEqual(plan["planned_comparison_rows"], 36)
        self.assertEqual(plan["planned_question_rows"], 288)
        self.assertEqual(plan["planned_round_predictions"], 192)
        self.assertEqual(plan["additional_model_calls"], 0)
        self.assertFalse(target.exists())
        self.assertEqual(self.file_bytes(self.source), before)

    def test_complete_report_and_csv_grid_preserve_source_and_no_selection(self):
        summary = json.loads((self.completed / "summary.json").read_text())
        manifest = json.loads((self.completed / "run-manifest.json").read_text())
        self.assertEqual(manifest["status"], "complete")
        self.assertEqual(len(summary["comparisons"]), 36)
        self.assertFalse(summary["selection_performed"])
        self.assertIsNone(summary["recommendation"])
        self.assertEqual(summary["additional_model_calls"], 0)
        for name, count in (("comparisons.csv", 36), ("per_question.csv", 288)):
            with (self.completed / name).open(encoding="utf-8", newline="") as source:
                self.assertEqual(len(list(csv.DictReader(source))), count)
        for name in self.runner.REPORT_FILES:
            self.assertEqual(self.runner.digest((self.completed / name).read_bytes()), manifest["output_sha256"][name])

    def test_read_only_reanalysis_reproduces_all_reports_and_refuses_tampering(self):
        before = self.file_bytes(self.completed)
        source_before = self.file_bytes(self.source)
        with patch.object(Path, "write_bytes", side_effect=AssertionError("Reanalysis writes nothing")), \
                patch.object(Path, "write_text", side_effect=AssertionError("Reanalysis writes nothing")):
            code, output, error = self.invoke(["--analyze-run", str(self.completed)])
        self.assertEqual(code, 0, output + error)
        self.assertTrue(json.loads(output)["summary_reproduced"])
        self.assertEqual(self.file_bytes(self.completed), before)
        self.assertEqual(self.file_bytes(self.source), source_before)
        target = self.target("tampered")
        shutil.copytree(self.completed, target)
        with (target / "comparisons.csv").open("ab") as changed:
            changed.write(b"modified\n")
        code, _, error = self.invoke(["--analyze-run", str(target)])
        self.assertEqual(code, 1)
        self.assertIn("recomputation", error)

    def test_repeated_analysis_is_deterministic_without_overwriting_existing_output(self):
        target = self.target("second")
        code, output, error = self.invoke(["--source-run", str(self.source), "--output-dir", str(target)])
        self.assertEqual(code, 0, output + error)
        for name in self.runner.REPORT_FILES:
            self.assertEqual((target / name).read_bytes(), (self.completed / name).read_bytes())
        before = self.file_bytes(target)
        self.assertEqual(self.invoke(["--source-run", str(self.source), "--output-dir", str(target)])[0], 1)
        self.assertEqual(self.file_bytes(target), before)

    def test_invalid_source_audit_or_frozen_configuration_stops_before_publication(self):
        target = self.target("bad-audit")
        invalid = lambda _: {**self.audit_result(), "summary_reproduced": False}
        self.assertEqual(self.invoke(["--source-run", str(self.source), "--output-dir", str(target)], audit=invalid)[0], 1)
        self.assertFalse(target.exists())
        config = copy.deepcopy(self.runner.EXPECTED_CONFIG)
        config["protocol"]["num_agents"] = 9
        path = self.target("config.json")
        path.write_text(json.dumps(config), encoding="utf-8")
        code, _, error = self.invoke(["--config", str(path), "--source-run", str(self.source), "--output-dir", str(target)])
        self.assertEqual(code, 1)
        self.assertIn("frozen", error)
        self.assertFalse(target.exists())

    def test_input_drift_during_audit_and_after_analysis_cannot_publish(self):
        original = self.generation_config.read_bytes()
        target = self.target("drift")
        def changed_audit(_):
            self.generation_config.write_bytes(b"changed during audit")
            return self.audit_result()
        try:
            code, _, error = self.invoke(["--source-run", str(self.source), "--output-dir", str(target)], audit=changed_audit)
            self.assertEqual(code, 1)
            self.assertIn("changed", error)
            self.assertFalse(target.exists())
        finally:
            self.generation_config.write_bytes(original)
        original_analysis = self.runner.analysis.analyze
        def changed_after_analysis(*args, **kwargs):
            result = original_analysis(*args, **kwargs)
            self.generation_config.write_bytes(b"changed after analysis")
            return result
        try:
            with patch.object(self.runner.analysis, "analyze", side_effect=changed_after_analysis):
                code, _, error = self.invoke(["--source-run", str(self.source), "--output-dir", str(target)])
            self.assertEqual(code, 1)
            self.assertIn("changed", error)
            self.assertFalse(target.exists())
        finally:
            self.generation_config.write_bytes(original)

    def test_changed_code_dependency_is_rejected_by_frozen_analysis_guard(self):
        with patch.object(self.runner.recovery, "analyze_run", return_value=self.audit_result()):
            plan = self.runner.load_plan(self.runner.CONFIG_PATH, self.source)
        dependency = self.target("analysis-dependency.py")
        dependency.write_bytes(b"frozen code")
        plan["source_sha256"][str(dependency)] = self.runner.digest(dependency.read_bytes())
        dependency.write_bytes(b"changed code")
        with self.assertRaisesRegex(ValueError, "changed"):
            self.runner.verify_plan(plan)

    def test_output_must_not_overlap_inputs_history_or_symlink_ancestors(self):
        with patch.object(self.runner.recovery, "analyze_run", return_value=self.audit_result()):
            plan = self.runner.load_plan(self.runner.CONFIG_PATH, self.source)
        for target in (self.source / "new", self.parent / "new", self.failed / "new",
                       self.runner.ROOT / "archive/new-comparison", self.source.parent):
            with self.subTest(target=target), self.assertRaises(ValueError):
                self.runner.validate_output(target, plan, require_new=False)
        real = self.target("real-directory")
        real.mkdir()
        link = self.target("symlink")
        try:
            link.symlink_to(real, target_is_directory=True)
        except OSError as exc:
            if getattr(exc, "winerror", None) == 1314:
                return
            raise
        with self.assertRaisesRegex(ValueError, "symlink|reparse"):
            self.runner.validate_output(link / "nested", plan)


if __name__ == "__main__":
    unittest.main()
