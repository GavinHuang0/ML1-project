# Current experiment results

This directory is reserved for new runs of the active `llama3.2:3b` workflows with a 1024-token output limit. See the [current instructions](../README.md) for commands and each protocol's scoring rule. A completed raw run must have its final completion marker before it is interpreted as a complete experiment.

## Separate multiple-choice experiment

The [exact-fraction multiple-choice experiment](../docs/MULTIPLE_CHOICE_EXPERIMENT.md#results-on-november-7-2026) completed all sixteen calls on November 7: **1/16 correct**, fifteen valid choices, and one truncated response. Its sixteen reused questions and fifteen options per question are in the [review bank](../docs/MULTIPLE_CHOICE_QUESTION_BANK.md). New `mc-exact-v1` runs use [multiple-choice/](multiple-choice/README.md), a separate namespace from the earlier runs below. Exact choice identity applies to every family, including sensors; this experiment does not use or overwrite the previous numerical-tolerance scores.

## Reviewed current run

The November 6, 2026 suite completed all 80 calls under `posterior-v2`. Read the [interpretation](../docs/RESULTS.md) and [verified checks and manual review](runs/llama3.2-3b-pilots-20261106T191224204871Z/interpretation.verified.json). All full-pilot methods scored 0/4; the original urn comparison scored 0/2 to 2/2, and the diagnostic scored 2/8 to 3/8. Format failures are distinguished from mathematical errors, and historical scores are unchanged.

| Artifact | Files |
| --- | --- |
| Run provenance | [Manifest](runs/llama3.2-3b-pilots-20261106T191224204871Z/run-manifest.json) |
| Full probability pilot | [Raw](runs/llama3.2-3b-pilots-20261106T191224204871Z/full1024.jsonl), [summary](runs/llama3.2-3b-pilots-20261106T191224204871Z/full1024.summary.json) |
| Original urn comparison | [Raw](runs/llama3.2-3b-pilots-20261106T191224204871Z/urn-check1024.jsonl), [summary](runs/llama3.2-3b-pilots-20261106T191224204871Z/urn-check1024.summary.json) |
| Diagnostic | [Raw](runs/llama3.2-3b-pilots-20261106T191224204871Z/diagnostic1024.jsonl), [summary](runs/llama3.2-3b-pilots-20261106T191224204871Z/diagnostic1024.summary.json) |

## Reviewed template comparison

The separate [template experiment](../docs/TEMPLATE_EXPERIMENT.md) completed 40 calls on November 6. Its [manifest](runs/template-bounded-20261106T195732100566Z/run-manifest.json), [raw responses](runs/template-bounded-20261106T195732100566Z/answers.jsonl), [paired summary](runs/template-bounded-20261106T195732100566Z/summary.json), and [verification](runs/template-bounded-20261106T195732100566Z/verification.json) preserve the frozen comparison. Fresh questions improved from 3/12 to 11/12 valid answers and 1/12 to 5/12 strict correct answers. Regression cases are reported separately, and explanation-bound compliance is not an extra correctness gate.

## Reviewed calculator pilot

The first calculator-assisted pilot completed eight known development cases on November 6. See its [interpretation](../docs/CALCULATOR_RESULTS.md), [manifest](runs/calculator-pilot-20261106T205135473899Z/run-manifest.json), [raw plans and computed answers](runs/calculator-pilot-20261106T205135473899Z/answers.jsonl), [summary](runs/calculator-pilot-20261106T205135473899Z/summary.json), and [verification](runs/calculator-pilot-20261106T205135473899Z/verification.json). All eight outputs supplied both fields; five expressions executed and three answers were correct. Invalid syntax and wrong formulas remain distinct failures, with no repairs or retroactive rescoring.

## Reviewed calculator syntax comparison

The [32-call syntax comparison](../docs/CALCULATOR_SYNTAX_EXPERIMENT.md) completed eight fresh and eight regression tasks under two matched prompts. See its [manifest](runs/calculator-syntax-20261106T211825622487Z/run-manifest.json), [raw responses](runs/calculator-syntax-20261106T211825622487Z/answers.jsonl), [paired summary](runs/calculator-syntax-20261106T211825622487Z/summary.json), and [verification](runs/calculator-syntax-20261106T211825622487Z/verification.json). Fresh executable methods change from 6/8 to 7/8 with correctness unchanged at 4/8. Regression executability stays 5/8. Parser/scoring rules and prior scores remain unchanged; no output was repaired.

## Recording policy

New outputs are ignored by Git by default. Preserve raw responses and their generation settings; select artifacts for versioning only after review. Keep model weights outside the repository.

All earlier Qwen and Llama runs, reports, code, and scoring contracts are preserved in the [legacy archive](../archive/2026-10-24-legacy/README.md). Those historical sensor correctness scores used the decision-v1 state classification rule and are not scores under the current posterior-based rule.
