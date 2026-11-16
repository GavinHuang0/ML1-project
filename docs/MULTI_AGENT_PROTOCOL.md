# Frozen multi-agent calculator protocol

`multi-agent-calculator-v1` implements the [adopted experimental framework](https://chatgpt.com/s/t_6afa1956baec8191b2c6d69d0c30935d). [The configuration](../config/multi_agent.json) freezes the procedure; the question manifest can change. The supplied four-question pilot tests feasibility using inspected development cases. It does not fix the final benchmark size or establish general accuracy.

## Generation and communication

| Setting | Frozen value |
| --- | --- |
| Model and panel | `llama3.2:3b`; ten separate generations from the same model |
| Rounds | `0..3`: independent initialization, then three communication rounds |
| Sampling | Temperature `0.7`; maximum output `1024` tokens; base seed `20261116` |
| Runtime | Sequential, JSON, non-streaming, `keep_alive=0` |
| Context | `16384` tokens; no automatic prompt shortening |
| History | Original question plus immediately preceding round only |
| Peer order | Deterministically shuffled, anonymous labels per receiving agent/round |

Round 0 uses the unchanged baseline system prompt and original question. Subsequent requests contain the agent's own previous response and all nine peers' previous responses. Only `explanation`, `expression`, `computed_fraction`, and `status` are forwarded. Peer text is explicitly untrusted data. References, correctness, arbitrary model keys, and older-round history are excluded. Every request in a round is constructed from the same completed previous-round snapshot before generation begins. All four rounds are collected regardless of apparent consensus.

The new context differs from the preserved baseline's `4096`. Ten ordinary 60-word explanations plus expressions produce synthetic revision requests around 7,800–8,200 UTF-8 bytes. The admission guard counts content bytes plus a 256-token template reserve and the full 1024-token output allowance. This is a conservative byte budget, not proof from the model's actual tokenizer. Oversized requests and observed context saturation stop the run; text is never silently shortened. Returned token counts and termination reasons remain available for inspection.

## Scoring and stopping-round selection

The calculator evaluates explicit expressions once using exact rational arithmetic, without repairs. Eligibility requires valid JSON, string `explanation`, nonempty string `expression`, successful calculation, and a result in `[0,1]` for probability tasks. Explanation mathematics is not graded; the 60-word bound is secondary. Extra keys do not affect eligibility and are never forwarded. Missing explanation can permit calculation but prevents voting eligibility.

Exact rational plurality selects the unique most frequent eligible value. Ties and no eligible values produce abstentions, counted incorrect. Correctness requires exact equality with the private rational reference. Historical baseline tolerance and results remain preserved.

Select one global round count on validation data, minimizing

`J(R) = L(R) + delta * [omega * normalized_tokens(R) + (1-omega) * normalized_wall(R)]`,

with smaller rounds winning objective ties. `L` is one minus family-balanced accuracy. Costs accumulate communication rounds `1..R`; report round 0 and total costs separately. Wall time includes prompt construction, health checks, generation, parsing, calculator execution, and journaling, excluding offline scoring. Reference costs are family-balanced mean first-communication-round costs from development/calibration data, frozen before validation.

The primary preference is `delta=0.02`, `omega=0.5`: approximately two accuracy percentage points per reference-cost unit, with equal token/time weighting. This is an operating preference, not an estimate from observed accuracy. Sensitivity grids are `delta=[0,0.01,0.02,0.05,0.1]` and `omega=[0,0.5,1]`. Missing token measurements stay unknown.

Uncertainty uses a seeded, paired, family-stratified question bootstrap: 2,000 replicates and 95% percentile intervals. Questions, rather than agents or rounds, are the sampling units. One question per family makes the pilot's bootstrap variability degenerate; its intervals cannot establish precision.

## Commands and evaluation lifecycle

Preview the default 160 calls without Ollama access or result writes, then run the development pilot:

```sh
python3 run_multi_agent.py --dry-run
python3 run_multi_agent.py --output-dir results/multi-agent/pilot-v1
```

Create a new JSON manifest with `schema_version: 1`, a nonempty `source` object, and a nonempty `tasks` list. Every task requires unique nonempty `id`, `family`, `prompt`, recognized `split`, boolean `probability`, and exact integer/fraction string `gold_fraction`. Supply `group_id` for every related variant and preserve that identifier across manifests. References remain local. Recognized splits are `inspected_development`, `development`, `calibration`, `validation`, and `test`.

Use `--tasks` and `--split` to select a partition. Run development/calibration, validation, and test separately. Validation consumes frozen development costs and emits `selection.json`; held-out evaluation requires that selection and the same original development calibration file:

```sh
python3 run_multi_agent.py --tasks config/benchmark.json --split validation --calibration results/multi-agent/pilot-v1/calibration.json --output-dir results/multi-agent/validation-v1
python3 run_multi_agent.py --tasks config/benchmark.json --split test --calibration results/multi-agent/pilot-v1/calibration.json --selection results/multi-agent/validation-v1/selection.json --output-dir results/multi-agent/test-v1
```

These benchmark paths are examples; create and verify the new questions before inference. Cross-run question/group overlap is rejected.

Runs save raw `generations.jsonl`, evaluated `answers.jsonl`, `rounds.jsonl`, `summary.json`, and a provenance/completion manifest. Development can emit `calibration.json`; validation can emit `selection.json` when measurements support selection. Model/runtime/source drift stops inference. Failures preserve partial evidence; partial runs cannot be analyzed as complete. There are no retries or resume, and existing destinations are refused.

Recompute a complete run offline into a new external report:

```sh
python3 run_multi_agent.py --analyze-run results/multi-agent/pilot-v1 --analysis-output /tmp/pilot-v1-analysis.json
```

Replay checks completion, evidence hashes, frozen inputs, prompts, seeds, and evaluated results. Self-revision and budget-matched independent-sampling controls remain recommended additions; they are not implemented comparison arms yet.
