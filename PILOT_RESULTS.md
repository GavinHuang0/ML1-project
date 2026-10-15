# Experiment 1 pilot results

The four-question `qwen2.5:3b` pilot completed on October 14, 2026. Communication did not improve panel accuracy over independent voting in this run. Every method missed both urn questions. All 12 invalid responses were truncated at the 256-token limit, which accounts for the measured correction and corruption transitions. These results identify arithmetic and output-length problems to address before a larger evaluation.

## Saved run and settings

The original [raw JSONL](results/experiment1-qwen-seed42.jsonl) contains metadata, four question records, and a final completion marker. The [derived JSON summary](results/experiment1-qwen-seed42.summary.json) includes per-question and per-family metrics, transition counts, budgets, and provenance. These reviewed pilot artifacts are versioned in Git; new run outputs remain ignored by default. The [artifact index](results/README.md) lists both pilots.

| Setting | Recorded value |
| --- | --- |
| Model | `qwen2.5:3b`, 3.1B parameters, `Q4_K_M` |
| Ollama version | `0.40.4` |
| Run start | October 14, 2026 at 01:04:08 EDT, or 05:04:08 UTC |
| Questions and agents | 4 questions, 3 agents per panel |
| Seed and temperature | 42 and 0.7 |
| Output limit | 256 tokens per call |
| Observed work | 60 calls, 24,784 input tokens, 10,533 output tokens |
| Summed request time | 478.96 seconds, approximately 7 minutes 59 seconds |

The summary retains the full model digest. The run did not record a Git revision; the summary identifies the source revision and file hashes used for analysis. The current source reproduces the saved tasks, parsing, scores, and budgets, but this does not establish the exact source revision used during generation.

The raw file is 97,600 bytes. Its SHA256 is:

```text
5f34df5b85c2fb8513e420d0536bd6015040012444104eec025647350ed30548
```

## Accuracy and response validity

| Method | Overall panel accuracy | Urn questions | Sensor decisions | Individual correct | Invalid outputs |
| --- | --- | --- | --- | --- | --- |
| Single answer | 1/4 = 25% | 0/2 | 1/2 | 1/4 | 1/4 |
| Independent voting | 2/4 = 50% | 0/2 | 2/2 | 4/12 | 2/12 |
| Self revision | 2/4 = 50% | 0/2 | 2/2 | 4/12 | 2/12 |
| Answers only | 2/4 = 50% | 0/2 | 2/2 | 4/12 | 2/12 |
| Justifications | 2/4 = 50% | 0/2 | 2/2 | 5/12 | 1/12 |
| Source deduplication | 1/4 = 25% | 0/2 | 1/2 | 1/12 | 5/12 |

Urn answers use the documented absolute tolerance of 0.001. Sensor accuracy checks whether the probability is on the correct side of 0.5, relative to the sampled hidden state. It does not check the accuracy of the posterior. Invalid answers count as individual failures and abstain from panel voting. The single-answer baseline uses the first initial agent; it is part of the same panel.

All 30 urn responses were valid JSON but mathematically incorrect. Every valid sensor response predicted state 0, which was the hidden state on both sensor questions. An always-zero sensor classifier would also score 2/2 on these two cases. On question `0003`, source deduplication's correct panel decision came from one valid vote with two invalid abstentions.

## Correction and corruption

G counts wrong-to-correct transitions and H counts correct-to-wrong transitions, each divided by all 12 paired agent slots. Invalid answers count as wrong under the frozen scoring rule.

| Revision condition | Corrections | Corruptions | G | H | Net individual change |
| --- | --- | --- | --- | --- | --- |
| Self revision | 0 | 0 | 0% | 0% | 0 percentage points |
| Answers only | 1 | 1 | 8.33% | 8.33% | 0 percentage points |
| Justifications | 1 | 0 | 8.33% | 0% | +8.33 percentage points |
| Source deduplication | 0 | 3 | 0% | 25% | -25 percentage points |

Both measured corrections were invalid-to-valid recoveries on sensor tasks. All four measured corruptions were correct sensor decisions becoming invalid JSON. No transition changed a valid, incorrect task answer into a correct one or a valid, correct task answer into a valid, incorrect one. The justifications gain therefore reflects format recovery. Source deduplication lost one previously correct panel decision when all three revised responses on question `0001` were truncated.

Across the actual run, 12/60 responses were invalid, all on sensor tasks. Every one ended with `done_reason: "length"`, used exactly 256 generated tokens, and left an unfinished JSON string. Source deduplication truncated 5/6 sensor revisions. This supports investigating the output limit before interpreting its lower score as an effect on reasoning. Visible answer fragments inside incomplete JSON were not rescued for headline scoring.

## Errors visible in the responses

On question `0000`, all three initial agents returned `0.4666666666666667` while writing the correct expression `(12/15) * (11/14)`. That expression actually equals `22/35`, approximately `0.628571`. All four revision branches left every agent wrong. Agreement across these agents repeated a shared arithmetic mistake.

Question `0002` required the conditional probability `7/11`, approximately `0.636364`. Initial answers were `0.75`, `0.75`, and `0.6667`; no revision reached the reference. Self revision changed answers to `0.5`, `0.25`, and `0.5`, showing that revising an answer can change its value without fixing it.

On sensor question `0001`, the correct posterior was `1/82`, approximately `0.012195`. Valid outputs ranged from `0.25` to approximately `0.272727`. They chose the correct state but gave substantially incorrect probabilities. Some explanations incorrectly treated distinct source IDs as the same information or substituted the wrong reliabilities.

On sensor question `0003`, the posterior was `2/2189`, approximately `0.000914`. Many valid answers were `0.0032` or `0.0033`, with explanations that omitted normalization or misapplied likelihoods. One truncated source-deduplication explanation called the observations dependent because they were repeated, despite the distinct source IDs. This is a useful qualitative error example; its official prediction remains invalid.

## Sensor probability quality

These means use valid individual sensor responses only. The reference is the exact posterior; Brier score uses the sampled hidden state. Lower values are better for both measures.

| Method | Valid sensor responses | Mean absolute posterior error | Mean Brier score |
| --- | --- | --- | --- |
| Single answer | 1/2 | 0.237805 | 0.062500 |
| Independent voting | 4/6 | 0.125777 | 0.034225 |
| Self revision | 4/6 | 0.125227 | 0.034223 |
| Answers only | 4/6 | 0.125754 | 0.034222 |
| Justifications | 5/6 | 0.101059 | 0.027382 |
| Source deduplication | 1/6 | 0.002286 | 0.000010 |

Source deduplication's low means describe its one surviving response on question `0003`. The five invalid responses are absent from these means, so these numbers cannot establish that it improves probability estimates. The other conditions also have differing valid subsets. Two sensor questions cannot support calibration claims.

## Calls and tokens

These costs cover each method across all four questions, including its initial calls. Each revision method uses 24 calls versus 12 for independent voting. Input lengths also differ substantially.

| Method | Calls | Input tokens | Output tokens |
| --- | --- | --- | --- |
| Single answer | 4 | 590 | 709 |
| Independent voting | 12 | 1,770 | 1,991 |
| Self revision | 24 | 5,833 | 4,113 |
| Answers only | 24 | 6,141 | 3,874 |
| Justifications | 24 | 9,077 | 4,077 |
| Source deduplication | 24 | 9,043 | 4,442 |

These rows overlap because they reuse the same initial answers. The actual run used 60 calls; summing the method rows would count shared work repeatedly. Communication used more calls and tokens without improving panel accuracy over independent voting in this pilot. No budget-matched extra-sampling condition was run.

## Why the 256 token pilot was insufficient

The [failure record](results/experiment1-qwen-seed42.failure.json) lists all 12 invalid responses by question, branch, agent, JSONL line, stop reason, token count, and parser error.

The run completed operationally and saved all 60 calls, but 12/60 responses reached the 256-token limit with unfinished JSON. This affected 5/6 source-deduplication sensor revisions. The measured G/H changes all involved invalid responses becoming valid or valid responses becoming invalid, so they do not establish correction or corruption of mathematical reasoning. Separately, all 30 urn responses were valid but wrong; fixing output length alone does not address those errors.

Four questions, with hidden state 0 on both sensor questions, also cannot reliably rank the methods. The 512-token follow-up tests whether a higher output limit reduces truncation under the same settings. It does not resolve the small sample, unbalanced sensor states, or unequal method budgets.

## Next experiment

A separate follow-up completed with `--max-tokens 512`, keeping the same model, four questions, three agents, seed 42, and temperature 0.7. All 60 responses were valid, while every method still missed both urn questions. See the [512 token comparison](PILOT_512_RESULTS.md) for results and remaining reasoning errors. The original run's raw responses, scores, and settings are preserved.

After resolving truncation, use a larger development pilot to select and freeze settings. The eventual held-out evaluation should include both hidden states, varied posterior strengths, several seeds, and additional independent sampling at the communication budget. Analyze uncertainty by question, keeping each question's agents and branches together. The source-deduplication prompt also changes verification instructions and table repetition, so isolating deduplication requires a controlled comparison.

Four questions from one model and seed cannot rank the methods reliably. The useful findings here are shared arithmetic errors, incorrect sensor posteriors despite correct decisions, and a substantial truncation problem.

## Reproduce the summary

Run the analyzer from the project directory, choosing a new output filename if the default summary already exists:

```sh
python3 analyze_results.py results/experiment1-qwen-seed42.jsonl --output results/experiment1-qwen-seed42.recheck.json
```

The analyzer makes no model calls. It checks completion, task generation, raw-response parsing, stored scores, and budgets before saving. It refuses to overwrite an existing output. Analysis timestamps and the recorded source revision may differ on a later run; the recorded task metrics should agree.
