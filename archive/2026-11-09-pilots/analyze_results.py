"""Validate a completed pilot and save descriptive results without model calls."""

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

from benchmark import correct, make_tasks, probability
from local_llm import OllamaError, parse_prediction
from run_experiment import CONDITIONS, budget, evaluate
from experiment_config import (MODEL, MAX_TOKENS, protocol_metadata, source_hashes)


METHODS = ("single", "independent_voting", *CONDITIONS)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def records_for(question, method):
    if method == "single":
        return question["initial"][:1]
    if method == "independent_voting":
        return question["initial"]
    return question["conditions"][method]["revised"]


def metrics_for(question, method):
    initial = question["initial"] if method in CONDITIONS else None
    return evaluate(question["task"], records_for(question, method), initial)


def summarize(questions, method):
    records = []
    cost_records = []
    panel_correct = abstentions = individual_correct = 0
    brier = []
    posterior_errors = []
    transitions = Counter()
    for question in questions:
        revised = records_for(question, method)
        metrics = metrics_for(question, method)
        records.extend(revised)
        cost_records.extend(question["initial"] + revised if method in CONDITIONS else revised)
        panel_correct += metrics["ensemble"]["correct"]
        abstentions += metrics["ensemble"]["abstained"]
        individual_correct += sum(metrics["individual_correct"])
        brier.extend(value for value in metrics.get("brier_scores", []) if value is not None)
        posterior_errors.extend(value for value in metrics.get("posterior_absolute_errors", [])
                                if value is not None)
        if method in CONDITIONS:
            for before, after in zip(question["initial"], revised):
                was_correct = correct(question["task"], before["probability"])
                is_correct = correct(question["task"], after["probability"])
                if not was_correct and is_correct:
                    transitions["wrong_to_correct"] += 1
                    transitions["invalid_to_correct" if before["probability"] is None
                                else "valid_wrong_to_correct"] += 1
                if was_correct and not is_correct:
                    transitions["correct_to_wrong"] += 1
                    transitions["correct_to_invalid" if after["probability"] is None
                                else "correct_to_valid_wrong"] += 1
    result = {
        "questions": len(questions), "panel_correct": panel_correct,
        "panel_accuracy": panel_correct / len(questions), "panel_abstentions": abstentions,
        "individual_responses": len(records), "individual_correct": individual_correct,
        "individual_accuracy": individual_correct / len(records),
        "invalid_answers": sum(record["probability"] is None for record in records),
        "truncated_responses": sum(record["raw"].get("done_reason") == "length" for record in records),
        "evidence_probability_valid_count": len(brier),
        "mean_brier_valid_only": sum(brier) / len(brier) if brier else None,
        "mean_posterior_absolute_error_valid_only": (
            sum(posterior_errors) / len(posterior_errors) if posterior_errors else None),
        "standalone_budget_including_initial": budget(cost_records),
    }
    if method in CONDITIONS:
        keys = ("wrong_to_correct", "correct_to_wrong", "invalid_to_correct",
                "valid_wrong_to_correct", "correct_to_invalid", "correct_to_valid_wrong")
        result["transitions"] = {key: transitions[key] for key in keys}
        result.update(G=transitions["wrong_to_correct"] / len(records),
                      H=transitions["correct_to_wrong"] / len(records),
                      delta=(transitions["wrong_to_correct"] - transitions["correct_to_wrong"]) / len(records))
    return result


def analyze(path):
    source = path.read_bytes()
    rows = [json.loads(line) for line in source.decode("utf-8").splitlines()]
    require(len(rows) >= 3, "Expected metadata, questions, and a completion marker")
    require(rows[0].get("type") == "metadata" and rows[-1].get("type") == "complete",
            "Run is missing metadata or its final completion marker")
    questions = rows[1:-1]
    require(all(question.get("type") == "question" for question in questions),
            "Unexpected record inside the question sequence")
    settings = rows[0]["settings"]
    require(rows[0].get("protocol") == protocol_metadata(),
            "Not an active posterior-v2 run. Use the archived analyzer for historical results.")
    require(rows[0].get("model") == MODEL and settings.get("max_tokens") == MAX_TOKENS,
            "Active results must use llama3.2:3b at 1024 tokens")
    require(rows[-1].get("generation_sources_unchanged") is True,
            "Run did not confirm unchanged generation sources")
    require(rows[0]["generation"]["source_sha256"] == rows[-1].get("source_sha256_after"),
            "Generation source hashes differ before and after the run")
    require(len(questions) == settings["questions"] == rows[-1]["questions_completed"],
            "Question count differs from settings or completion marker")
    require([question["task"] for question in questions] == make_tasks(settings["questions"], settings["seed"]),
            "Saved tasks differ from the current seeded task generator")
    all_calls = []
    question_summaries = []
    for question in questions:
        require(len(question["initial"]) == settings["agents"], "Wrong initial panel size")
        require(set(question["conditions"]) == set(CONDITIONS), "Missing or unknown revision branch")
        calls = list(question["initial"])
        require(question["initial_budget"] == budget(question["initial"]), "Initial budget mismatch")
        for condition in CONDITIONS:
            branch = question["conditions"][condition]
            require(len(branch["revised"]) == settings["agents"], "Wrong revision panel size")
            require(branch["total_budget"] == budget(question["initial"] + branch["revised"]),
                    "Branch budget mismatch")
            calls.extend(branch["revised"])
        for record in calls:
            try:
                parsed = parse_prediction(record["raw"])
                value = probability(parsed["final_answer"])
            except OllamaError:
                parsed = None
                value = None
            if value is None:
                parsed = None
            require(parsed == record["prediction"], "Stored prediction differs from raw response")
            require(value == record["probability"], "Stored prediction differs from raw response")
            require((value is None) == (record["parse_error"] is not None), "Parse failure flag mismatch")
        methods = {}
        for method in METHODS:
            recomputed = metrics_for(question, method)
            stored = (question["conditions"][method]["metrics"] if method in CONDITIONS else question[method])
            require(recomputed == stored, f"Stored metrics disagree for {question['task']['id']} {method}")
            methods[method] = {
                "probabilities": [record["probability"] for record in records_for(question, method)],
                "metrics": recomputed,
            }
        question_summaries.append({"task": question["task"], "methods": methods})
        all_calls.extend(calls)
    root = Path(__file__).resolve().parent
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root,
                              capture_output=True, text=True, check=False)
    families = sorted({question["task"]["family"] for question in questions})
    return {
        "schema_version": 2,
        "protocol": protocol_metadata(),
        "source": {"path": str(path), "bytes": len(source), "sha256": hashlib.sha256(source).hexdigest()},
        "metadata": rows[0],
        "analysis": {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "checked_against_git_revision": revision.stdout.strip() if revision.returncode == 0 else None,
            "run_git_revision": rows[0]["generation"].get("git_revision"),
            "source_sha256": source_hashes(),
            "validation": "Completion, seeded tasks, raw parsing, stored metrics, and budgets all match",
            "notes": [
                "Run provenance includes Git revision, dirty status, and generation source hashes.",
                "Sensor correctness is absolute posterior error <= 0.001; panels use the median valid posterior.",
                "Accuracy includes invalid answers as failures. G and H use all paired agent slots.",
                "Probability means exclude invalid responses; compare alongside their valid counts.",
                "Per-method standalone budgets overlap. actual_run counts each real call once.",
                "Agent slots and revision branches share questions; they are not independent trials.",
            ],
        },
        "actual_run": {
            **budget(all_calls),
            "invalid_answers": sum(record["probability"] is None for record in all_calls),
            "invalid_and_truncated": sum(record["probability"] is None and
                                         record["raw"].get("done_reason") == "length" for record in all_calls),
            "done_reasons": dict(Counter(record["raw"].get("done_reason") for record in all_calls)),
        },
        "methods": {method: {"overall": summarize(questions, method),
                             "families": {family: summarize([question for question in questions
                                                              if question["task"]["family"] == family], method)
                                          for family in families}} for method in METHODS},
        "questions": question_summaries,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or args.input.with_suffix(".summary.json")
    try:
        summary = analyze(args.input)
        with output.open("x", encoding="utf-8") as handle:
            json.dump(summary, handle, indent=2, allow_nan=False)
            handle.write("\n")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(1, f"Analysis failed: {exc}\n")
    print(f"Saved {output}; validated {summary['actual_run']['calls']} calls")


if __name__ == "__main__":
    main()
