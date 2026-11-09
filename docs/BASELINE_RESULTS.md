# Baseline selection and historical results

The calculator procedure was selected as the active baseline on **November 9, 2026**. This is a consolidation of the existing procedure, not a new accuracy experiment. The active entry point is `run_baseline.py`, identified as `calculator-baseline-v1`; the planning/calculation contract remains `planner-calculator-v1`. The original system prompt and the bytes of `calculator.py` and `calculator_protocol.py` are unchanged.

## Why this procedure

The original prompt separates mathematical setup from deterministic arithmetic without adding answer-to-letter matching. The longer syntax clarification fixed some rejected expressions but introduced others, left fresh development correctness unchanged at 4/8, and increased tokens. Its total 8/16 versus the original 7/16 does not establish a reliable advantage. The multiple-choice format produced 1/16 and several correct-number/wrong-letter failures. We therefore keep the original prompt as the stable control and preserve those alternatives in the archive.

| Same sixteen inspected questions | Original calculator prompt | Longer syntax prompt | Multiple choice |
| --- | --- | --- | --- |
| Urns | 3/4 | 2/4 | 0/4 |
| Sensors | 0/4 | 0/4 | 0/4 |
| Algebra | 0/4 | 2/4 | 1/4 |
| Units | 4/4 | 4/4 | 0/4 |
| Delivered correct | 7/16 | 8/16 | 1/16 |

This is descriptive historical evidence. The calculator runs use numerical tolerance and multiple choice uses exact selected labels; changing representations also changes task information. The inspected cases do not establish general accuracy or a causal benefit from calculator access.

## Baseline reference records

The active [historical reference selection](../results/baseline/HISTORICAL_REFERENCE.json) maps all sixteen active task IDs to the archived original-prompt records, unchanged questions, references, and seeds. It reports 11/16 successful executions and 7/16 strict correct answers. Its record type explicitly marks a historical selection, with no model inference performed for consolidation.

The source is the `baseline` condition in the [November 6 raw comparison](../archive/2026-11-09-pilots/results/runs/calculator-syntax-20261106T211825622487Z/answers.jsonl). The [original report](../archive/2026-11-09-pilots/docs/CALCULATOR_SYNTAX_EXPERIMENT.md) and [verification](../archive/2026-11-09-pilots/results/runs/calculator-syntax-20261106T211825622487Z/verification.json) retain both conditions and their original provenance. The [earlier eight-case calculator report](../archive/2026-11-09-pilots/docs/CALCULATOR_RESULTS.md) records 3/8 correct; it is a smaller, overlapping pilot rather than a separate additional baseline sample. The [multiple-choice report](../archive/2026-11-09-pilots/docs/MULTIPLE_CHOICE_EXPERIMENT.md) preserves that later experiment independently.

## Known weaknesses and future use

Expression syntax can still fail, and supported expressions can represent the wrong probability or equation. Sensor results are 0/4 in the original sixteen-question condition. The scorer's inherited absolute tolerance is 0.001 for every family; for the small sensor reference `2/2189`, zero lies within tolerance. Preserve this rule and historical scores while explicitly reporting method quality and posterior errors.

All sixteen active questions have been inspected, including the cohort formerly called fresh. They are a development/regression bank. Future claims need frozen comparisons on new evaluation questions. The current baseline is a common procedure for further research, not a guarantee of dependable answer accuracy.

See the [README](../README.md) for the complete prompt, calculator grammar and limits, scoring, commands, and fair-comparison rules. The [archive index](../archive/2026-11-09-pilots/README.md) and SHA256 inventory preserve every earlier source, report, and raw artifact without repairs or rescoring.

## Consolidation validation

All **68 active offline tests pass**, including the calculator's arithmetic/syntax checks, reference-free execution, the new runner's failure/drift handling, independent reference calculations, historical-record selection, and both archive inventories. These tests use simulated inference and a temporary local HTTP fixture.

The real CLI dry-run previews all sixteen exact original message pairs and seeds without service access or result writes. Reprocessing the saved original responses with the active task mapping reproduces every original score. The calculator and scorer bytes match the archive, all 74 newly archived files retain their original hashes, and the 39-file October archive is unchanged. The active configuration SHA256 is `eaccc0c5259c9734a1335e122fd76ad01022114f064e34a92a0703f8b90b4c92`.

No new model generation or pilot was run for this repository consolidation.
