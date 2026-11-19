"""Offline instruction comparison, screening decisions, and durable evidence checks."""

from contextlib import redirect_stderr, redirect_stdout
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from calculator_protocol import SYSTEM
from local_llm import OllamaError
import run_format_followup as pilot


class FixtureClient:
    all_calls = []
    pause_path = None

    def __init__(self, **options):
        self.options, self.calls = options, []
        plan = pilot.load_plan(pilot.CONFIG_PATH)
        self.tasks = {task["prompt"]: task for task in plan["tasks_snapshot"]}

    def health(self):
        return {"version": "fixture-runtime", "models": [
            {"name": "llama3.2:3b", "digest": "fixture-digest"}]}

    def chat(self, model, messages, **options):
        call = {"model": model, "messages": copy.deepcopy(messages),
                **copy.deepcopy(options)}
        self.calls.append(call)
        FixtureClient.all_calls.append(call)
        task = self.tasks[messages[1]["content"]]
        return raw_expression(task["parameters"]["reference_expression"])


def raw_expression(expression):
    return {"model": "llama3.2:3b", "done": True, "done_reason": "stop",
            "message": {"content": json.dumps({
                "explanation": "Use the stated quantities.", "expression": expression})},
            "prompt_eval_count": 200, "eval_count": 50}


def rows(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines()]


class FormatFollowupTests(unittest.TestCase):
    def setUp(self):
        FixtureClient.all_calls, FixtureClient.pause_path = [], None

    def invoke(self, arguments, client=FixtureClient):
        output, errors = io.StringIO(), io.StringIO()
        with patch.object(pilot, "PilotClient", client), \
                patch.object(pilot, "hardware_identity", return_value={"fixture": "same-machine"}), \
                redirect_stdout(output), redirect_stderr(errors):
            code = pilot.main(arguments)
        return code, output.getvalue(), errors.getvalue()

    def complete(self, destination):
        code, output, error = self.invoke(["--output-dir", str(destination)])
        self.assertEqual(code, 0, output + error)
        return json.loads((destination / "summary.json").read_text())

    def synthetic(self):
        plan = pilot.load_plan(pilot.CONFIG_PATH)
        tasks = {task["id"]: task for task in plan["tasks_snapshot"]}
        records = [pilot.evaluate_generation({**copy.deepcopy(call), "type": "generation",
                   "elapsed_seconds": 0.1, "raw": raw_expression(
                       tasks[call["question_id"]]["parameters"]["reference_expression"])},
                   tasks[call["question_id"]]) for call in plan["calls"]]
        return plan, tasks, records

    def change(self, records, tasks, predicate, expression, limit=None):
        changed = 0
        for index, record in enumerate(records):
            if predicate(record) and (limit is None or changed < limit):
                generation = {key: value for key, value in record.items()
                              if key not in ("response", "schema_conforms")}
                generation["type"] = "generation"
                generation["raw"] = raw_expression(expression)
                records[index] = pilot.evaluate_generation(generation, tasks[record["question_id"]])
                changed += 1
        if limit is not None:
            self.assertEqual(changed, limit)

    @staticmethod
    def screening(record, profile="complete_expression"):
        return record["evaluation_set"] == "screening" and record["profile"] == profile

    def test_dry_run_freezes_320_paired_calls_without_service_or_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "dry"
            with patch.object(pilot, "PilotClient", side_effect=AssertionError("No Ollama")), \
                    patch.object(pilot, "hardware_identity", side_effect=AssertionError("No hardware")), \
                    redirect_stdout(io.StringIO()) as output:
                self.assertEqual(pilot.main(["--dry-run", "--output-dir", str(target)]), 0)
            plan = json.loads(output.getvalue())
            self.assertEqual(plan["planned_calls"], 320)
            self.assertEqual(len(plan["tasks_snapshot"]), 16)
            self.assertEqual({task["split"] for task in plan["tasks_snapshot"]}, {"development"})
            self.assertFalse(target.exists())
            for question_index in range(16):
                for agent in range(10):
                    pair = plan["calls"][question_index * 20 + agent * 2:
                                         question_index * 20 + agent * 2 + 2]
                    self.assertEqual(pair[0]["seed"], pair[1]["seed"])
                    self.assertEqual(pair[0]["messages"][1], pair[1]["messages"][1])
                    self.assertEqual(pair[0]["format"], pilot.STRICT_SCHEMA)
                    self.assertEqual(pair[1]["format"], pilot.STRICT_SCHEMA)
                    self.assertEqual({call["profile"] for call in pair},
                                     {"strict_schema", "complete_expression"})
                    self.assertEqual(pair[0]["profile"], "strict_schema" if
                                     (question_index + agent) % 2 == 0 else "complete_expression")
                    for call in pair:
                        prompt = call["messages"][0]["content"]
                        self.assertEqual(len(call["messages"]), 2)
                        if call["profile"] == "strict_schema":
                            self.assertEqual(prompt, SYSTEM)
                        else:
                            self.assertTrue(prompt.startswith(SYSTEM + "\n"))
                            self.assertIn(pilot.COMPLETE_EXPRESSION_INSTRUCTION, prompt)
                        self.assertNotIn("gold_fraction", json.dumps(call["messages"]))
                        self.assertNotIn("reference_expression", json.dumps(call["messages"]))

    def test_screening_variants_are_distinct_prompts_in_shared_structural_groups(self):
        plan = pilot.load_plan(pilot.CONFIG_PATH)
        tasks = {task["id"]: task for task in plan["tasks_snapshot"]}
        regression = [tasks[task_id] for task_id in pilot.REGRESSION_TASK_IDS]
        screening = [tasks[task_id] for task_id in pilot.SCREENING_TASK_IDS]
        self.assertEqual(len(regression), 8)
        self.assertEqual(len(screening), 8)
        self.assertEqual({task["group_id"] for task in regression},
                         {task["group_id"] for task in screening})
        self.assertTrue({task["prompt"] for task in regression}.isdisjoint(
            {task["prompt"] for task in screening}))

    def test_completed_evidence_and_separate_reports_reproduce(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "complete"
            summary = self.complete(target)
            self.assertEqual(summary["recommendation"], "strict_schema")
            self.assertEqual(len(FixtureClient.all_calls), 320)
            self.assertEqual(len(rows(target / "generations.jsonl")), 320)
            self.assertEqual(len(rows(target / "answers.jsonl")), 320)
            for group in ("regression", "screening"):
                for profile in ("strict_schema", "complete_expression"):
                    metrics = summary["sets"][group]["profiles"][profile]
                    self.assertEqual(metrics["calls"], 80)
                    self.assertEqual(metrics["eligible"], 80)
                    self.assertEqual(metrics["collective_correct"], 8)
                    self.assertEqual(metrics["exact_agent_correct"], 80)
            manifest = json.loads((target / "run-manifest.json").read_text())
            self.assertEqual(manifest["status"], "complete")
            self.assertEqual(manifest["calls_completed"], 320)
            self.assertEqual(manifest["hardware_snapshot"], {"fixture": "same-machine"})
            _, records = pilot.audit_resume(target, manifest, pilot.load_plan(pilot.CONFIG_PATH))
            self.assertEqual(pilot.summarize(manifest, records), summary)

    def test_regression_outcomes_cannot_override_screening_selection(self):
        plan, tasks, records = self.synthetic()
        self.change(records, tasks, lambda r: r["evaluation_set"] == "regression" and
                    r["profile"] == "complete_expression", "1/0")
        summary = pilot.summarize(plan, records)
        self.assertEqual(summary["recommendation"], "strict_schema")
        self.assertEqual(summary["sets"]["regression"]["profiles"]["complete_expression"]["eligible"], 0)
        self.assertEqual(summary["sets"]["screening"]["profiles"]["complete_expression"]["eligible"], 80)
        self.change(records, tasks, lambda r: self.screening(r, "strict_schema"), "1/0", limit=5)
        self.assertEqual(pilot.summarize(plan, records)["recommendation"], "complete_expression_for_review")

    def test_technical_screens_have_exact_eligibility_and_error_boundaries(self):
        for errors, out_of_range, expected in ((4, 4, True), (5, 0, False), (4, 5, False)):
            with self.subTest(errors=errors, out_of_range=out_of_range):
                plan, tasks, records = self.synthetic()
                self.change(records, tasks, self.screening, "1/0", limit=errors)
                self.change(records, tasks, lambda r: self.screening(r) and
                            tasks[r["question_id"]]["probability"] and r["response"]["eligible"],
                            "2", limit=out_of_range)
                metrics = pilot.summarize(plan, records)["sets"]["screening"]["profiles"]["complete_expression"]
                self.assertEqual(metrics["eligible"], 80 - errors - out_of_range)
                self.assertEqual(metrics["calculator_errors"], errors)
                self.assertEqual(metrics["technical_pass"], expected)

    def test_both_qualify_prefers_more_eligible_candidate_and_control_on_ties(self):
        plan, tasks, records = self.synthetic()
        self.change(records, tasks, lambda r: self.screening(r, "strict_schema"), "1/0", limit=2)
        self.change(records, tasks, self.screening, "1/0", limit=1)
        self.assertEqual(pilot.summarize(plan, records)["recommendation"], "complete_expression_for_review")
        self.change(records, tasks, lambda r: self.screening(r) and r["response"]["eligible"],
                    "1/0", limit=1)
        self.assertEqual(pilot.summarize(plan, records)["recommendation"], "strict_schema")

    def test_candidate_accuracy_screen_allows_one_question_loss_not_two(self):
        for losses, expected in ((1, True), (2, False)):
            with self.subTest(losses=losses):
                plan, tasks, records = self.synthetic()
                # Control misses the error screen but still has a correct plurality on every question.
                self.change(records, tasks, lambda r: self.screening(r, "strict_schema"), "1/0", limit=5)
                lost_ids = set(pilot.SCREENING_TASK_IDS[:losses])
                self.change(records, tasks, lambda r: self.screening(r) and r["question_id"] in lost_ids, "0")
                summary = pilot.summarize(plan, records)
                self.assertEqual(summary["sets"]["screening"]["candidate_accuracy_screen_pass"], expected)
                self.assertEqual(summary["recommendation"], "complete_expression_for_review" if
                                 expected else "stop_and_review_neither_passes")

    def test_neither_profile_qualifies_and_unknown_token_measurements_remain_unknown(self):
        plan, tasks, records = self.synthetic()
        self.change(records, tasks, lambda r: r["evaluation_set"] == "screening", "1/0")
        for record in records:
            record["raw"].pop("prompt_eval_count")
        summary = pilot.summarize(plan, records)
        self.assertEqual(summary["recommendation"], "stop_and_review_neither_passes")
        for metrics in summary["sets"]["screening"]["profiles"].values():
            self.assertIsNone(metrics["input_tokens"])
            self.assertEqual(metrics["calculator_errors"], 80)

    def test_schema_conformance_is_enforced_for_both_profiles_without_expression_repair(self):
        for profile in ("strict_schema", "complete_expression"):
            with self.subTest(profile=profile):
                for expression in ("2*", "2(3+4)", "1..2", "1/0"):
                    evaluated = pilot.evaluate_generation({"raw": raw_expression(expression),
                                                          "profile": profile}, {"probability": False})
                    self.assertFalse(evaluated["response"]["eligible"])
                    self.assertEqual(evaluated["response"]["expression"], expression)
                with self.assertRaises(pilot.SchemaViolation):
                    pilot.evaluate_generation({"raw": raw_expression("x=7"),
                                               "profile": profile}, {"probability": False})

    def test_transport_preserves_schema_and_generation_settings(self):
        client = pilot.PilotClient(timeout=600)
        messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": "Question"}]
        with patch.object(client, "_request", return_value=raw_expression("1")) as request:
            client.chat("llama3.2:3b", messages, seed=5, temperature=0.7, max_tokens=1024,
                        format_value=pilot.STRICT_SCHEMA)
        path, payload = request.call_args.args
        self.assertEqual(path, "/api/chat")
        self.assertEqual(payload["format"], pilot.STRICT_SCHEMA)
        self.assertEqual(payload["messages"], messages)
        self.assertEqual(payload["options"], {"seed": 5, "temperature": 0.7, "num_predict": 1024, "num_ctx": 16384})
        self.assertEqual(payload["keep_alive"], 0)

    def test_schema_violation_stops_and_preserves_raw_for_either_arm(self):
        class NonconformingClient(FixtureClient):
            bad_prompt = SYSTEM

            def chat(self, model, messages, **options):
                raw = super().chat(model, messages, **options)
                return raw_expression("x=7") if messages[0]["content"] == self.bad_prompt else raw

        for arm in ("strict_schema", "complete_expression"):
            with self.subTest(arm=arm), tempfile.TemporaryDirectory() as directory:
                NonconformingClient.bad_prompt = pilot.SYSTEM_PROMPTS[arm]
                target = Path(directory) / "unsupported"
                code, _, error = self.invoke(["--output-dir", str(target)], NonconformingClient)
                self.assertEqual(code, 1)
                self.assertIn("schema", error.lower())
                generations, answers = rows(target / "generations.jsonl"), rows(target / "answers.jsonl")
                self.assertEqual(len(generations), len(answers) + 1)
                self.assertEqual(generations[-1]["profile"], arm)
                self.assertIn("x=7", generations[-1]["raw"]["message"]["content"])
                self.assertFalse((target / "summary.json").exists())

    def test_pause_and_resume_preserve_prefix_without_replaying_calls(self):
        class PausingClient(FixtureClient):
            def chat(self, *arguments, **options):
                raw = super().chat(*arguments, **options)
                if len(FixtureClient.all_calls) == 3:
                    FixtureClient.pause_path.touch()
                return raw

        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "paused"
            FixtureClient.pause_path = target / ".pause-request"
            self.assertEqual(self.invoke(["--output-dir", str(target)], PausingClient)[0], 2)
            prefix = (target / "answers.jsonl").read_bytes()
            self.assertEqual(len(rows(target / "answers.jsonl")), 3)
            code, output, error = self.invoke(["--resume", "--output-dir", str(target)])
            self.assertEqual(code, 0, output + error)
            self.assertEqual(len(FixtureClient.all_calls), 320)
            self.assertTrue((target / "answers.jsonl").read_bytes().startswith(prefix))
            self.assertFalse(FixtureClient.pause_path.exists())

    def test_force_interruption_recovers_returned_raw_without_an_extra_call(self):
        original, interrupted = pilot.evaluate_generation, False

        def force_once(generation, task):
            nonlocal interrupted
            if not interrupted:
                interrupted = True
                raise KeyboardInterrupt
            return original(generation, task)

        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "forced"
            with patch.object(pilot, "evaluate_generation", side_effect=force_once):
                self.assertEqual(self.invoke(["--output-dir", str(target)])[0], 130)
            self.assertEqual(len(rows(target / "generations.jsonl")), 1)
            self.assertEqual(len(rows(target / "answers.jsonl")), 0)
            code, output, error = self.invoke(["--resume", "--output-dir", str(target)])
            self.assertEqual(code, 0, output + error)
            self.assertEqual(len(FixtureClient.all_calls), 320)

    def test_resume_rejects_evidence_and_hardware_changes_before_inference(self):
        class PausingClient(FixtureClient):
            def chat(self, *arguments, **options):
                raw = super().chat(*arguments, **options)
                FixtureClient.pause_path.touch()
                return raw

        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "tamper"
            FixtureClient.pause_path = target / ".pause-request"
            self.assertEqual(self.invoke(["--output-dir", str(target)], PausingClient)[0], 2)
            path = target / "answers.jsonl"
            evidence = path.read_bytes()
            path.write_bytes(evidence.replace(b'"eligible": true', b'"eligible": false'))
            before = len(FixtureClient.all_calls)
            self.assertEqual(self.invoke(["--resume", "--output-dir", str(target)])[0], 1)
            self.assertEqual(len(FixtureClient.all_calls), before)
            path.write_bytes(evidence)
            with patch.object(pilot, "PilotClient", side_effect=AssertionError("No inference")), \
                    patch.object(pilot, "hardware_identity", return_value={"fixture": "different"}), \
                    redirect_stderr(io.StringIO()):
                self.assertEqual(pilot.main(["--resume", "--output-dir", str(target)]), 1)

    def test_changed_config_is_rejected_during_offline_preflight(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            config = json.loads(pilot.CONFIG_PATH.read_text(encoding="utf-8"))
            config["protocol"]["temperature"] = 0
            config_path = target / "changed.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            with patch.object(pilot, "PilotClient", side_effect=AssertionError("No inference")), \
                    redirect_stderr(io.StringIO()):
                self.assertEqual(pilot.main(["--dry-run", "--config", str(config_path)]), 1)

    def test_offline_analysis_recomputes_without_service_hardware_or_file_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "complete"
            summary = self.complete(target)
            before = {path.relative_to(target): path.read_bytes() for path in target.rglob("*") if path.is_file()}
            with patch.object(pilot, "PilotClient", side_effect=AssertionError("No service")), \
                    patch.object(pilot, "hardware_identity", side_effect=AssertionError("No hardware")), \
                    redirect_stdout(io.StringIO()) as output:
                self.assertEqual(pilot.main(["--analyze-run", str(target)]), 0)
            audit = json.loads(output.getvalue())
            self.assertEqual(audit["offline_audit"], "passed")
            self.assertTrue(audit["summary_reproduced"])
            self.assertEqual(audit["summary"], summary)
            self.assertEqual(before, {path.relative_to(target): path.read_bytes()
                                     for path in target.rglob("*") if path.is_file()})
            summary_path = target / "summary.json"
            summary["recommendation"] = "tampered"
            summary_path.write_text(json.dumps(summary), encoding="utf-8")
            with patch.object(pilot, "PilotClient", side_effect=AssertionError("No service")), \
                    redirect_stderr(io.StringIO()):
                self.assertEqual(pilot.main(["--analyze-run", str(target)]), 1)

    def test_service_failure_does_not_create_empty_run_or_overwrite_completed_run(self):
        class UnavailableClient(FixtureClient):
            def health(self):
                raise OllamaError("Fixture service unavailable")

        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "not-started"
            self.assertEqual(self.invoke(["--output-dir", str(target)], UnavailableClient)[0], 1)
            self.assertFalse(target.exists())
            self.complete(target)
            before = (target / "answers.jsonl").read_bytes()
            self.assertEqual(self.invoke(["--output-dir", str(target)])[0], 1)
            self.assertEqual((target / "answers.jsonl").read_bytes(), before)
            self.assertEqual(self.invoke(["--resume", "--output-dir", str(target)])[0], 1)


if __name__ == "__main__":
    unittest.main()
