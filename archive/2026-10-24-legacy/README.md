# Legacy experiments preserved on October 24, 2026

This archive preserves the repository immediately before the active workflow changed to `llama3.2:3b`, a 1024-token limit, and posterior-based sensor correctness. Historical code, raw responses, scores, interpretations, and configuration retain their original bytes. Do not edit those preserved files to reflect the new workflow.

The snapshot contains 39 original files totaling 1,067,617 bytes. Source, configuration, and tests were copied; the three historical root reports and the entire former `results/` tree were moved here. Generated Python bytecode caches were excluded from source copies. Active source files remain at the repository root and may now evolve independently.

## Index

| Preserved material | Location |
| --- | --- |
| Original repository instructions | [REPOSITORY_README.md](REPOSITORY_README.md) |
| First Qwen pilot interpretation | [PILOT_RESULTS.md](PILOT_RESULTS.md) |
| Second pilot, prompt diagnostics, and Llama interpretation | [PILOT_512_RESULTS.md](PILOT_512_RESULTS.md) |
| Historical proposed next steps | [NEXT_STEPS.md](NEXT_STEPS.md) |
| Original result index | [results/README.md](results/README.md) |
| Qwen raw runs and derived artifacts | [results/](results/) |
| Llama replay and verified comparison | [Llama results directory](results/llama3.2-3b-pilots-20261016T193719153075Z/) |
| Frozen source, model configuration, and tests | Root Python files, [config/](config/), and [tests/](tests/) in this directory |
| Original paths, byte counts, and SHA256 checksums | [SHA256_INVENTORY.json](SHA256_INVENTORY.json) |

The inventory records each preserved file's original repository-relative path and its path within this archive. This new index and the inventory itself are archive documentation rather than pre-migration files, so they are not inventory entries. Git attributes disable text conversion for the entire archive to preserve the recorded checksums across checkouts.

## Historical scoring: decision-v1

The old full-panel sensor correctness rule classified a reported probability as state 1 when it was at least 0.5 and state 0 otherwise, then compared that state with the sampled hidden state. Call this historical rule **decision-v1**. It did not require an accurate posterior. For example, a probability of 0.25 could count as correct when the hidden state was 0 even though the exact posterior was close to 0.012195. Both sensor cases in the four-question seed-42 pilot had hidden state 0.

The old full-panel records also retain Brier scores and absolute posterior errors for valid sensor responses. Urn answers used an absolute tolerance of 0.001. Invalid individual answers counted as failures and abstained from panel voting; G and H used all paired agent slots. The separate single-agent diagnostic retained its own numeric and expression answer contracts. The frozen code and reports specify these differences in detail.

All historical correctness, G/H, panel, and summary values remain unchanged. They must not be presented as results under the active posterior-based sensor rule. Raw metadata, source strings, recorded commands, and provenance paths still refer to their original locations. Those strings are historical evidence and have not been rewritten; resolve repository-relative artifact references from this archive directory where applicable. Embedded runner source is data, not a migration script to execute.

## Recompute historical summaries without inference

The archived Python code uses the standard library. Enter this directory so imports and reference files resolve to the frozen snapshot:

```sh
cd archive/2026-10-24-legacy
python3 -B -c "from pathlib import Path; from analyze_results import analyze; print(analyze(Path('results/experiment1-qwen-seed42-max512.jsonl'))['actual_run'])"
python3 -B -c "from pathlib import Path; from analyze_results import analyze; print(analyze(Path('results/llama3.2-3b-pilots-20261016T193719153075Z/pilot512.jsonl'))['actual_run'])"
```

These commands parse and recompute the old scores without Ollama, model downloads, or model calls, and do not write into the archive. On Windows, use `py -3 -B` in place of `python3 -B`. The old analyzer's checked Git revision describes the analysis checkout; generation provenance remains in the original raw records and manifests. To export a recheck with the old CLI, choose a new output path outside this archive.

The [current repository instructions](../../README.md) describe the active experiment. New results belong in the active repository's `results/` directory.
