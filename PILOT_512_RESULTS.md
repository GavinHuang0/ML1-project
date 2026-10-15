# Pilot comparison at 256 and 512 tokens

The 512-token Qwen pilot completed all four questions and 60 calls on October 14, 2026. All 60 responses were valid JSON, compared with 48/60 in the 256-token run. Every method now scores 2/4 at the panel level. The larger limit resolved the observed formatting failures on these questions; shared arithmetic mistakes and incorrect posterior calculations remain.

## Why the previous pilot was insufficient

The 256-token run completed successfully, but 12 responses exhausted the output allowance before closing their JSON explanations. Source deduplication lost 5/6 sensor responses. Invalid answers count as failures, so every measured correction or corruption in that run reflected a change in output validity. These transitions could not establish whether communication repaired or corrupted a valid answer. The [original report](PILOT_RESULTS.md#why-the-256-token-pilot-was-insufficient) and [failure record](results/experiment1-qwen-seed42.failure.json) preserve the diagnosis and exact failure locations.

Formatting was only one limitation. All 30 urn responses were valid but wrong, and correct sensor decisions often concealed incorrect probabilities. Four questions, with hidden state 0 on both sensor tasks, cannot rank the methods reliably. Raising the output limit addresses the observed truncation problem while leaving these other limitations in place.

## Settings and comparison scope

The new run used `qwen2.5:3b`, the same installed model digest, Ollama `0.40.4`, four questions, three agents, seed 42, temperature 0.7, a 300-second request timeout, and a 4096-token context. The only intentional generation-setting change was `max_tokens: 256 → 512`. The runner, prompt templates, task generator, and scoring were unchanged in this follow-up.

The [run manifest](results/experiment1-qwen-seed42-max512.run.json) records the command, timestamps, Python version, Git revision, and inference-source hashes before and after generation. Inference files matched revision `8d87e38dc75331a237e5472cfeb99d3383384244` and stayed unchanged during the run. Their hashes also match the source used to analyze the earlier run. The earlier generation did not record its code revision or hardware, so that provenance cannot be established retrospectively.

Longer or newly valid initial answers change the actual revision histories and peer messages. This comparison therefore measures the whole experiment's sensitivity to the output limit. It does not isolate the effect of extra tokens on otherwise identical revision inputs. G and H are paired within each run against that run's own initial panel.

```sh
python3 run_experiment.py --model qwen2.5:3b --questions 4 --agents 3 --seed 42 --temperature 0.7 --max-tokens 512 --timeout 300 --output results/experiment1-qwen-seed42-max512.jsonl
```

The completed output is preserved; another run must use a new filename.

## Accuracy and validity

| Method | Panel correct at 256 | Panel correct at 512 | Individual correct at 512 | Invalid at 256 | Invalid at 512 |
| --- | --- | --- | --- | --- | --- |
| Single answer | 1/4 | 2/4 | 2/4 | 1/4 | 0/4 |
| Independent voting | 2/4 | 2/4 | 6/12 | 2/12 | 0/12 |
| Self revision | 2/4 | 2/4 | 6/12 | 2/12 | 0/12 |
| Answers only | 2/4 | 2/4 | 6/12 | 2/12 | 0/12 |
| Justifications | 2/4 | 2/4 | 6/12 | 1/12 | 0/12 |
| Source deduplication | 1/4 | 2/4 | 6/12 | 5/12 | 0/12 |

Every method gets 0/2 urn questions and 2/2 sensor decisions. All four revision conditions have G = H = 0 across their 12 paired agent slots at 512 tokens. No revision fixes an urn answer or changes a correct sensor decision into an incorrect one. The apparent justifications advantage and source-deduplication penalty in the earlier transition counts disappear once output validity is restored.

All 12 previously invalid call positions have valid responses in the new run, with no new invalid positions. Across the 60 aligned calls, 38 output texts are identical. All new responses end with `done_reason: "stop"`; the longest is 483 tokens, and 15 exceed 256 tokens. One 477-token initial sensor response begins with the exact text previously truncated at 256 tokens and now closes its JSON. This directly supports the prior output-limit diagnosis. It does not guarantee that 512 tokens will suffice for longer tasks.

## Errors that remain at 512 tokens

Both urn tasks reproduce the earlier wrong answers across all 30 calls. For question `0000`, every initial agent writes `(12/15) * (11/14)` but returns approximately `0.466667`; the correct value is `22/35`, approximately `0.628571`. Question `0002` requires `7/11`, approximately `0.636364`, and no branch reaches it.

On sensor question `0001`, probabilities remain approximately `0.2222–0.2727` against the reference `1/82`, approximately `0.012195`. Answers-only revisions converge to `0.25`, showing agreement on an incorrect posterior. All these probabilities still select state 0 and therefore pass the binary decision score.

On sensor question `0003`, the reference is `2/2189`, approximately `0.000914`. The first initial answer is now valid at `0.065`, despite its explanation ending a different calculation near `0.000416`. Source deduplication's first agent also returns `0.065`, incorrectly attributes that answer to a peer, and displays inconsistent arithmetic. Answers-only and justifications converge to `0.0033`. The self-revised third agent reaches `0.0012`, close to the reference, but correct binary decisions alone do not establish reliable posterior computation.

| Method at 512 tokens | Valid sensor responses | Mean absolute posterior error | Mean Brier score |
| --- | --- | --- | --- |
| Single answer | 2/2 | 0.150946 | 0.033363 |
| Independent voting | 6/6 | 0.129533 | 0.031750 |
| Self revision | 6/6 | 0.128750 | 0.031695 |
| Answers only | 6/6 | 0.120096 | 0.031255 |
| Justifications | 6/6 | 0.123879 | 0.033233 |
| Source deduplication | 6/6 | 0.137933 | 0.035915 |

These scores summarize individual predictions, not panel probabilities. Lower is better. All sensor responses now contribute to their method's mean. The earlier valid-only means used different subsets, including just one surviving source-deduplication response, so comparing those means directly would mix probability changes with selection effects. Two sensor questions do not support calibration or method-superiority claims.

## Tokens and timings

| Actual work counted once | 256-token run | 512-token run |
| --- | --- | --- |
| Generation calls | 60 | 60 |
| Input tokens | 24,784 | 29,082 |
| Output tokens | 10,533 | 12,550 |
| Total tokens | 35,317 | 41,632 |
| Summed request timers | 478.96 seconds | 668.45 seconds |

Total tokens increased by 6,315, approximately 17.9%. Input use also grew because longer and newly valid initial answers expanded revision contexts. Methods still use unequal budgets, and their standalone costs overlap through shared initial answers. The new manifest retains both calendar timestamps and a monotonic run timer; their elapsed intervals differ substantially, so the request totals are not treated as calendar wall time or a controlled speed comparison.

## Saved artifacts and next step

The new [raw JSONL](results/experiment1-qwen-seed42-max512.jsonl), [validated summary](results/experiment1-qwen-seed42-max512.summary.json), [structured comparison](results/experiment1-qwen-seed42-max512.comparison.json), [run manifest](results/experiment1-qwen-seed42-max512.run.json), and [console log](results/experiment1-qwen-seed42-max512.run.log) are versioned as reviewed pilot artifacts. New run outputs remain ignored by default. The manifest and summaries include SHA256 hashes. The original raw file is unchanged.

The analyzer verified completion, all seeded tasks, parsed predictions, stored scores, and budgets for the new run. Recompute its summary with a new filename:

```sh
python3 analyze_results.py results/experiment1-qwen-seed42-max512.jsonl --output results/experiment1-qwen-seed42-max512.recheck.json
```

Use 512 tokens as a provisional setting for the next development pilot, while continuing to monitor completion. The [next experiment plan](NEXT_STEPS.md) prioritizes checking calculations, then improving task balance and budget comparisons. Preserve these four questions as diagnostic examples of correlated arithmetic and Bayesian errors. This follow-up passed the output-format check on the tested cases; it did not establish a benefit from communication.
