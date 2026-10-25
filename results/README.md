# Current experiment results

This directory is reserved for new runs of the active `llama3.2:3b` workflow with a 1024-token output limit. See the [current instructions](../README.md) for commands and the sensor posterior scoring rule. A completed raw run must have its final completion marker before it is interpreted as a complete experiment.

New outputs are ignored by Git by default. Preserve raw responses and their generation settings; select artifacts for versioning only after review. Keep model weights outside the repository.

All earlier Qwen and Llama runs, reports, code, and scoring contracts are preserved in the [legacy archive](../archive/2026-10-24-legacy/README.md). Those historical sensor correctness scores used the decision-v1 state classification rule and are not scores under the current posterior-based rule.
