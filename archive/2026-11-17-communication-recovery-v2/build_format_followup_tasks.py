"""Build/check development-only regression cases and fresh format-screen variants.

No inference or downloads. Existing files are never overwritten. New numerical
variants retain the inspected cases' structural groups and are not a holdout.
"""

import argparse
from collections import Counter
import copy
import hashlib
import json
from pathlib import Path
import random
import sys

from build_full_benchmark import BUILDERS, FAMILIES, METHODS, TEMPLATES, verify_reference
from multi_agent_protocol import validate_tasks


ROOT = Path(__file__).resolve().parent
DEFAULT_PATH = ROOT / "config/format_followup_tasks.json"
BENCHMARK_PATH = ROOT / "config/full_benchmark.json"
GENERATOR_VERSION = "targeted-format-development-tasks-v2"
SEED = 20261118
REGRESSION_IDS = [f"full-v1-{family}-development-{index:02d}"
                  for family in FAMILIES for index in (1, 2)]
SCREENING_IDS = [f"format-v2-{family}-development-{index:02d}"
                 for family in FAMILIES for index in (1, 2)]


def numeric_key(task):
    """Ignore only the calculator witness when detecting reused numeric cases."""
    parameters = {key: value for key, value in task["parameters"].items()
                  if key != "reference_expression"}
    return task["family"], task["template_index"], json.dumps(parameters, sort_keys=True)


def generate_manifest():
    source_bytes = BENCHMARK_PATH.read_bytes()
    existing = json.loads(source_bytes)["tasks"]
    by_id = {task["id"]: task for task in existing}
    regression = [copy.deepcopy(by_id[task_id]) for task_id in REGRESSION_IDS]
    rng = random.Random(SEED)
    prompts = {task["prompt"] for task in existing}
    numeric_cases = {numeric_key(task) for task in existing}
    screening = []
    for original, task_id in zip(regression, SCREENING_IDS):
        family, index = original["family"], original["template_index"]
        if original["split"] != "development" or index not in (0, 5):
            raise ValueError("Expected the eight inspected development structures")
        for _ in range(1000):
            prompt, parameters, gold, expression = BUILDERS[family](index, rng)
            candidate = {"family": family, "template_index": index, "parameters": parameters}
            if prompt not in prompts and numeric_key(candidate) not in numeric_cases:
                break
        else:
            raise ValueError("Could not produce a fresh numerical variant")
        prompts.add(prompt)
        numeric_cases.add(numeric_key(candidate))
        parameters["reference_expression"] = expression
        screening.append({"id": task_id, "group_id": original["group_id"],
                          "template_id": TEMPLATES[family][index][0], "template_index": index,
                          "split": "development", "family": family, "prompt": prompt,
                          "probability": family in ("reasoning", "evidence"),
                          "gold_fraction": str(gold), "parameters": parameters,
                          "difficulty": original["difficulty"], "reference_method": METHODS[family]})
    manifest = {
        "schema_version": 1,
        "manifest_id": "targeted-format-development-tasks-v2",
        "source": {
            "generator": "build_format_followup_tasks.py",
            "generator_version": GENERATOR_VERSION,
            "seed": SEED,
            "benchmark": "config/full_benchmark.json",
            "benchmark_sha256": hashlib.sha256(source_bytes).hexdigest(),
            "kind": "Eight inspected regression tasks and eight new deterministic numerical variants; no model inference.",
            "selection_policy": "Keep the same eight development structures, two per family, selected before v2 inference; generate fresh numbers with seed 20261118 and reject reused prompts/parameters.",
            "split_policy": "All sixteen tasks are development data. Validation/test questions and structural groups are excluded.",
            "semantic_group_policy": "Each screening variant retains its regression case's group_id; these are fresh numbers on inspected structures, not a structural holdout.",
            "reference_policy": "Exact rational references independently audited by enumeration, affine substitution or dimensional conservation; no references enter model prompts.",
            "screening_policy": "Only the eight screening_task_ids determine the v2 acceptance screen; regression results remain descriptive.",
            "uncertainty_unit": "Eight semantic groups across both sets; numerical variants and ten agents per question are correlated development observations.",
        },
        "regression_task_ids": REGRESSION_IDS,
        "screening_task_ids": SCREENING_IDS,
        "tasks": regression + screening,
    }
    validate_manifest(manifest, existing)
    return manifest


def validate_manifest(manifest, benchmark_tasks=None):
    tasks = manifest["tasks"]
    validate_tasks(tasks)
    if manifest.get("regression_task_ids") != REGRESSION_IDS or manifest.get("screening_task_ids") != SCREENING_IDS:
        raise ValueError("Regression/screening allocation differs from frozen IDs")
    if [task["id"] for task in tasks] != REGRESSION_IDS + SCREENING_IDS:
        raise ValueError("Manifest needs the sixteen tasks in frozen order")
    if any(task["split"] != "development" for task in tasks):
        raise ValueError("Format follow-up must not contain validation/test questions")
    if len({task["prompt"] for task in tasks}) != 16:
        raise ValueError("Format follow-up prompts must be unique")
    for start in (0, 8):
        if Counter(task["family"] for task in tasks[start:start + 8]) != Counter({family: 2 for family in FAMILIES}):
            raise ValueError("Each set needs two questions from each family")
    for regression, screening in zip(tasks[:8], tasks[8:]):
        for field in ("family", "group_id", "template_id", "template_index", "probability", "split"):
            if regression[field] != screening[field]:
                raise ValueError("Fresh variants must preserve semantic group and family")
        if numeric_key(regression) == numeric_key(screening):
            raise ValueError("Screening variant repeats its regression parameters")
    if len({task["group_id"] for task in tasks}) != 8:
        raise ValueError("Expected eight shared regression/screening semantic groups")
    if benchmark_tasks is None:
        benchmark_tasks = json.loads(BENCHMARK_PATH.read_text(encoding="utf-8"))["tasks"]
    by_id = {task["id"]: task for task in benchmark_tasks}
    benchmark_prompts = {task["prompt"] for task in benchmark_tasks}
    benchmark_numeric = {numeric_key(task) for task in benchmark_tasks}
    for task in tasks[:8]:
        if task != by_id[task["id"]]:
            raise ValueError("Regression task changed from the inspected benchmark")
    for task in tasks[8:]:
        if task["prompt"] in benchmark_prompts or numeric_key(task) in benchmark_numeric:
            raise ValueError("Screening task repeats a full-benchmark question or numeric case")
    for task in tasks:
        verify_reference(task)
    return manifest


def manifest_bytes(manifest):
    return (json.dumps(manifest, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="Audit references and compare frozen bytes without writes")
    mode.add_argument("--output", type=Path, help="Write a new manifest, never overwrite an existing file")
    args = parser.parse_args(argv)
    try:
        data = manifest_bytes(generate_manifest())
        if args.check:
            if DEFAULT_PATH.read_bytes() != data:
                raise ValueError("Frozen format tasks differ from deterministic generation")
            print("Format tasks verified: 8 regression + 8 fresh numerical development variants, 8 shared semantic groups; exact references audited.")
        else:
            with args.output.open("xb") as output:
                output.write(data)
            print(f"Wrote {args.output}: 16 development tasks; no inference performed.")
        return 0
    except (OSError, ValueError, KeyError, TypeError, ZeroDivisionError) as exc:
        print(f"Format task generation/check failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
