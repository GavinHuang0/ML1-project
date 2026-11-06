# Current experiment results

This directory is reserved for new runs of the active `llama3.2:3b` workflow with a 1024-token output limit. See the [current instructions](../README.md) for commands and the sensor posterior scoring rule. A completed raw run must have its final completion marker before it is interpreted as a complete experiment.

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

## Recording policy

New outputs are ignored by Git by default. Preserve raw responses and their generation settings; select artifacts for versioning only after review. Keep model weights outside the repository.

All earlier Qwen and Llama runs, reports, code, and scoring contracts are preserved in the [legacy archive](../archive/2026-10-24-legacy/README.md). Those historical sensor correctness scores used the decision-v1 state classification rule and are not scores under the current posterior-based rule.
