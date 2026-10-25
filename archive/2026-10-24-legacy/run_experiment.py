"""Paired, single-round local LLM pilot. No external datasets or hosted APIs."""

import argparse
import datetime
import json
import random
import sys
import time
from pathlib import Path

from benchmark import clue_table, correct, ensemble, make_tasks, probability
from local_llm import OllamaClient, OllamaError, parse_prediction, validate_model_tag


SYSTEM = ("Solve the user's probability problem. Return ONLY a JSON object with "
          "final_answer (a string containing a fraction or decimal probability between 0 and 1) "
          "and explanation (a concise, auditable calculation, citing source IDs when given). "
          "Do not write extra text outside JSON.")
CONDITIONS = ("self_revision", "answers_only", "justifications", "source_dedup")


def call(client, model, messages, seed, temperature, max_tokens):
    started = time.perf_counter()
    raw = client.chat(model, messages, seed=seed, temperature=temperature, max_tokens=max_tokens)
    record = {"raw": raw, "elapsed_seconds": time.perf_counter() - started}
    try:
        prediction = parse_prediction(raw)
        value = probability(prediction["final_answer"])
        if value is None:
            raise OllamaError("final_answer must be a fraction or decimal between 0 and 1")
        record.update(prediction=prediction, probability=value, parse_error=None)
    except OllamaError as exc:
        record.update(prediction=None, probability=None, parse_error=str(exc))
    return record


def revision_prompt(task, initial, agent, condition, order_seed):
    text = "Check your previous calculation and revise only if warranted.\n"
    if condition == "self_revision":
        return text + "You have no peer messages."
    peers = [i for i in range(len(initial)) if i != agent]
    random.Random(order_seed).shuffle(peers)
    # Anonymous labels describe display order, never an identity or correctness.
    for position, index in enumerate(peers):
        prediction = initial[index]["prediction"]
        if prediction is None:
            text += f"\nPeer {position + 1}: no valid structured answer.\n"
            continue
        text += f"\nPeer {position + 1} answer: {prediction['final_answer']}\n"
        if condition != "answers_only":
            text += f"Explanation: {prediction['explanation']}\n"
        if condition == "justifications" and task["family"] == "evidence":
            text += "This peer had these source observations:\n" + clue_table(task["clues"]) + "\n"
    if condition == "source_dedup":
        text += ("\nAgreement and repeated reports are not new observations. Before changing "
                 "your answer, identify a specific calculation or assumption that was wrong. ")
        if task["family"] == "evidence":
            text += ("Use each source ID exactly once from the UNIQUE observation "
                     "table in the original problem. Everyone saw that same table.")
    return text


def evaluate(task, records, initial=None):
    outcomes = [correct(task, r["probability"]) for r in records]
    result = {"individual_correct": outcomes,
              "invalid_answers": sum(r["probability"] is None for r in records),
              "ensemble": ensemble(task, [r["probability"] for r in records])}
    if task["family"] == "evidence":
        result["brier_scores"] = [None if r["probability"] is None else
                                  (r["probability"] - task["gold_state"]) ** 2 for r in records]
        result["posterior_absolute_errors"] = [None if r["probability"] is None else
                                               abs(r["probability"] - task["gold_probability"])
                                               for r in records]
    if initial is not None:
        before = [correct(task, r["probability"]) for r in initial]
        n = len(records)
        result["G"] = sum(not a and b for a, b in zip(before, outcomes)) / n
        result["H"] = sum(a and not b for a, b in zip(before, outcomes)) / n
        before_vote = ensemble(task, [r["probability"] for r in initial])["correct"]
        after_vote = result["ensemble"]["correct"]
        result["ensemble_G"] = int(not before_vote and after_vote)
        result["ensemble_H"] = int(before_vote and not after_vote)
    return result


def budget(records):
    def tokens(field):
        counts = [r["raw"].get(field) for r in records]
        return sum(counts) if all(isinstance(count, int) and count >= 0 for count in counts) else None
    return {"calls": len(records),
            "input_tokens": tokens("prompt_eval_count"),
            "output_tokens": tokens("eval_count"),
            "elapsed_seconds": sum(r["elapsed_seconds"] for r in records)}


def run_question(client, task, model, args, index):
    seed = args.seed + index * 100
    base = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": task["prompt"]}]
    initial = [call(client, model, base, seed + agent, args.temperature, args.max_tokens)
               for agent in range(args.agents)]
    result = {"task": task, "initial": initial,
              "single": evaluate(task, initial[:1]),
              "independent_voting": evaluate(task, initial),
              "initial_budget": budget(initial), "conditions": {}}
    for condition in CONDITIONS:
        revised = []
        for agent in range(args.agents):
            content = revision_prompt(task, initial, agent, condition, seed + agent)
            messages = base + [{"role": "assistant", "content": initial[agent]["raw"]["message"]["content"]},
                               {"role": "user", "content": content}]
            revised.append(call(client, model, messages, seed + 50 + agent,
                                args.temperature, args.max_tokens))
        result["conditions"][condition] = {"revised": revised,
                                           "metrics": evaluate(task, revised, initial),
                                           "total_budget": budget(initial + revised)}
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="qwen2.5:3b")
    parser.add_argument("--questions", type=int, default=4)
    parser.add_argument("--agents", type=int, choices=(3, 5), default=3)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--max-tokens", type=int, default=256)
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--dry-run", action="store_true", help="Inspect generated tasks without Ollama")
    args = parser.parse_args(argv)
    try:
        args.model = validate_model_tag(args.model)
    except ValueError as exc:
        parser.error(str(exc))
    if args.questions < 1 or args.max_tokens < 1 or args.timeout <= 0:
        parser.error("questions, max-tokens, and timeout must be positive")
    if not 0 <= args.temperature <= 2:
        parser.error("temperature must be between 0 and 2")
    tasks = make_tasks(args.questions, args.seed)
    if args.dry_run:
        print(json.dumps({"questions": len(tasks), "calls_per_question": args.agents * 5,
                          "conditions": CONDITIONS, "tasks": tasks}, indent=2))
        return 0
    path = args.output or Path("results") / (
        "pilot-" + datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ".jsonl")
    client = OllamaClient(timeout=args.timeout)
    try:
        health = client.health()
        tags = health["models"]
        requested = args.model if ":" in args.model.rsplit("/", 1)[-1] else args.model + ":latest"
        metadata = next((m for m in tags if m.get("name") == requested or m.get("model") == requested), None)
        if metadata is None:
            raise OllamaError(f"Model {args.model} is missing. Run: python setup_models.py --models {args.model}")
        path.parent.mkdir(parents=True, exist_ok=True)
        summary = {name: [] for name in ("single", "independent_voting", *CONDITIONS)}
        with path.open("x", encoding="utf-8") as output:
            output.write(json.dumps({"type": "metadata", "model": args.model,
                                     "model_metadata": metadata, "ollama_version": health["version"],
                                     "settings": {k: v for k, v in vars(args).items() if k != "output"},
                                     "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat()}) + "\n")
            output.flush()
            for index, task in enumerate(tasks):
                result = run_question(client, task, args.model, args, index)
                output.write(json.dumps({"type": "question", **result}, allow_nan=False) + "\n")
                output.flush()
                for name in ("single", "independent_voting"):
                    summary[name].append(result[name]["ensemble"]["correct"])
                for name in CONDITIONS:
                    summary[name].append(result["conditions"][name]["metrics"]["ensemble"]["correct"])
                print(f"Completed {index + 1}/{len(tasks)}: {task['id']}", flush=True)
            output.write(json.dumps({"type": "complete", "questions_completed": len(tasks)}) + "\n")
        print(json.dumps({"output": str(path), "ensemble_accuracy":
                          {name: sum(scores) / len(scores) for name, scores in summary.items()}}, indent=2))
        return 0
    except (OllamaError, OSError, ValueError) as exc:
        print(f"Experiment failed: {exc}", file=sys.stderr)
        print("Any partial output lacks a complete marker; do not treat it as a finished run.", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Experiment interrupted. Partial output must not be treated as a finished run.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
