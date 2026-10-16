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

## Single agent urn follow up at 1024 tokens

On October 16, 2026, a small follow-up within this second pilot tested whether a higher output limit and explicit math-checking instructions repair the two urn answers. It used one agent, one generation per question and prompt condition, and no calculator, peer messages, or separate revision call. The original prompt and one engineered prompt were each tested on both urn questions, for four calls total. No prompt was retuned or response retried after seeing an outcome.

The model digest and Ollama version matched the second pilot. Both conditions used `qwen2.5:3b`, temperature 0.7, a 1024-token output limit, and the same 4096-token context. Sampling seeds matched the original first agent: 42 for question `0000` and 242 for question `0002`. The original problem text was unchanged. Reference answers were used only for scoring after generation.

### Current single answer prompt

The original system instruction, followed by the urn problem as the user message, was:

> Solve the user's probability problem. Return ONLY a JSON object with final_answer (a string containing a fraction or decimal probability between 0 and 1) and explanation (a concise, auditable calculation, citing source IDs when given). Do not write extra text outside JSON.

The earlier self-revision instruction belonged to a later generation. It was not part of this original single-answer prompt.

### Math checking prompt addition

The engineered condition used that same system instruction with this addition in the same request:

> Before giving final_answer, end your explanation with a Math check: recompute the arithmetic step by step, verify that fractions and decimals agree, and check that your expression answers the stated event using the original ball counts and any conditioning information. Correct any mistake you find before giving final_answer. Put explanation before final_answer in the JSON object.

Both conditions received one system message and one user problem in a single model call. The addition requested checking inside the generated explanation; no external calculation or feedback was supplied to the model.

### Results

| Urn question | Reference | Original prompt at 512 | Original prompt at 1024 | Math checking prompt at 1024 |
| --- | --- | --- | --- | --- |
| `0000`: two red balls from 12 red and 3 blue | `22/35` ≈ 0.628571 | 0.466667, wrong | 0.466667, wrong | `22/35`, correct |
| `0002`: both red given at least one red, from 8 red and 2 blue | `7/11` ≈ 0.636364 | 0.75, wrong | 0.75, wrong | Invalid answer format; claims `28/31`, also mathematically wrong |

Under the unchanged scoring rule, the original prompt scored **0/2** at 1024 tokens and the math-checking prompt scored **1/2**. The original-prompt response texts were identical to the corresponding first-agent responses at 512 tokens. Raising the limit alone did not change these answers.

All four calls ended with `done_reason: "stop"`, and all four returned syntactically valid JSON. Their generated lengths were 132 and 73 tokens for the original prompt, then 249 and 568 for the math-checking prompt. None reached 1024 tokens. The observed failures in this follow-up therefore were not output truncations. Total reported work was 542 input tokens, 1,022 output tokens, and 43.17 seconds of summed request timers.

On question `0000`, the engineered prompt produced the correct product and simplification: `132/210 = 22/35`. On question `0002`, it still invented a sample space involving six balls, subtracted eight supposed blue-pair cases, and repeated inconsistent repairs after noticing probabilities above one. It ended with `28/(15 + 16) = 28/31`, which is the wrong conditional probability.

The conditional response also put a LaTeX expression in `final_answer` instead of the required plain fraction or decimal. The existing probability parser rejected it, so its official prediction is invalid. Interpreting its displayed expression manually as `28/31` gives approximately 0.903226, still far from `7/11`; this is a mathematical failure as well as an answer-format failure. The result was not rescued or rescored by relaxing the parser.

Neither engineered response included the requested literal “Math check” label, although both put the explanation before the final answer. The instruction was only partly followed. A correct answer on one case does not establish that the model reliably checked its own calculations.

### Interpretation and saved record

This prompt diagnostic improved one of the two known urn cases, while the conditional case remained unresolved. The 1024-token original-prompt control separates the token-cap change from the engineered prompt bundle on these examples. The addition combines arithmetic and event checks with explanation-first ordering, so their individual effects are not isolated. Two previously inspected questions and one sampling seed per question are insufficient to establish reliability on new problems.

The [raw follow-up record](results/experiment1-qwen-seed42-max512-urn-check1024.jsonl) preserves all four responses, exact messages, seeds, model metadata, inference-source hashes, and the runner source. Its [summary](results/experiment1-qwen-seed42-max512-urn-check1024.summary.json) includes the raw SHA256, official scores, token counts, and parsed predictions. This is an appendix to the second pilot; the original 512-token outputs and results are unchanged.

## Single agent diagnostic sequence and transfer check

A further development check on October 16, 2026 separated evaluating a supplied expression, constructing an expression from a word problem, and solving the full word problem. It also included one algebra question and one unit-conversion question to probe transfer beyond probability. This remains a follow-up section of the second pilot, using one agent and one generation per item and prompt condition, with no calculator, peer discussion, retries, or external feedback to the model.

Eight items were fixed before inference: three stages for each of two fresh urn cases, plus the two transfer questions. Each item was run with a baseline prompt and a checking prompt, for 16 calls. The three stages sharing an urn case are dependent diagnostics, not independent benchmark questions. The model digest and Ollama version matched the second pilot. The limit remained 1024 tokens, temperature 0.7, and context size 4096. Seeds were matched across conditions: 1042 for the unconditional case, 1043 for the conditional case, 1044 for algebra, and 1045 for units.

### Prompts and diagnostic tasks

Both conditions used the same general answer contract and field ordering. The baseline system prompt was:

> Solve the user's problem. Return ONLY one valid JSON object with explanation (a concise derivation) and final_answer (a string in the format requested by the question). Put explanation before final_answer. Do not use LaTeX, Markdown, or text outside JSON.

The checking condition appended:

> Before finalizing, end your explanation with a Check: section. Verify that your setup uses the original given values and constraints; recompute each arithmetic step; and verify the result against the original problem using a second check when possible. Correct any inconsistency you find before giving final_answer. Make the check specific rather than merely stating that the answer is correct.

The general answer contract allows values outside 0 to 1 for the algebra and distance questions. It therefore differs from the historical probability-only prompt. Within this diagnostic, the added checking instruction is the only system-prompt difference between conditions.

The unconditional urn has 7 red and 5 blue balls; the reference is `7/22`. The conditional urn has 6 red and 4 blue balls and asks for both red given at least one red; the reference is `5/13`. For each case, the arithmetic stage supplies a correct expression, the construction stage asks for an unevaluated arithmetic expression using only numbers and `+ - * /`, and the full-solution stage asks for the numerical probability. Supplying the expression intentionally removes the formulation task; its result is not unassisted word-problem accuracy. Each call starts independently, without seeing another stage's response.

The transfer items ask for `x` in `5*x - 9 = 26`, with reference `7`, and the distance traveled at 72 kilometres per hour for 25 minutes, with reference 30 kilometres. These are two small mathematical examples outside probability, not a broad test of general reasoning.

### Outcomes by task

| Item | Reference | Baseline | Checking prompt |
| --- | --- | --- | --- |
| Unconditional arithmetic | `7/22` | `7/22`, correct | `7/22`, correct |
| Unconditional expression construction | A correct expression for `7/22` | Malformed factorial expression | `C(7,2)/C(12,2)`: correct setup, outside requested syntax |
| Unconditional full solution | `7/22` ≈ 0.318182 | 0.333333, wrong | 0.363636, wrong |
| Conditional arithmetic | `5/13` | 0.666667, wrong | 0.384615, correct |
| Conditional expression construction | A correct expression for `5/13` | Expression evaluates to `5/11`, wrong | Expression evaluates to `1/234`, wrong |
| Conditional full solution | `5/13` ≈ 0.384615 | 0.25, wrong | 0.2222, wrong |
| Algebra | `7` | `7`, correct | `7`, correct |
| Unit conversion | `30` kilometres | `25`, wrong | JSON number `27`: wrong type and wrong value |

The supplied-expression stage improved from **1/2 to 2/2**, while full urn solving remained **0/2 in both conditions**. Construction scored 0/2 under the fixed arithmetic-only answer contract in both conditions, but this requires qualification: the checked unconditional expression `C(7,2)/C(12,2)` is mathematically appropriate and equals `21/66 = 7/22`. It failed the requested expression syntax, rather than the probability setup. That manual mathematical finding is recorded separately without changing its official format score. The conditional expression is mathematically wrong in both conditions.

Algebra was correct in both conditions, so that case supplies no evidence that checking improved it. The rate calculation remained wrong, and the checked answer additionally used a JSON number instead of the required string. All 16 responses were syntactically valid JSON objects; three failed their answer contracts across the two conditions. All stopped normally, the longest response was 198 tokens, and none approached the 1024-token limit. Reported work was 2,332 input tokens, 2,008 output tokens, and 121.32 seconds of summed request timers.

### What this diagnoses and what can generalize

There are failures in both arithmetic and formulation. Giving a correct expression helped localize one arithmetic error, and adding the checking prompt repaired that supplied-expression answer. It did not repair the corresponding word-problem answers. The checked conditional construction divided a probability by a raw outcome count, mixing incompatible normalizations. Several explanations describe a plausible method but end with an inconsistent number.

All eight checking-condition explanations omitted the requested `Check:` section. Thus this run tests the effect of asking for a check; it does not establish that a consistent checking procedure was executed. More available output tokens did not make the model follow that instruction reliably.

A general checklist can ask whether the given values, constraints, setup, calculations, and result agree, but the actual test depends on the domain. Algebra can use substitution, rates can use units and a reverse calculation, and conditional probability must check the eligible sample space. Factual questions require evidence checks rather than arithmetic alone. These two transfer items do not establish that this prompt works across those domains, and no universal accuracy claim follows from this diagnostic.

The [raw diagnostic record](results/experiment1-qwen-seed42-max512-diagnostic1024.jsonl) stores all prompts, the frozen task manifest, settings, responses, scoring rules, provenance, and runner source. The [summary and manual review](results/experiment1-qwen-seed42-max512-diagnostic1024.summary.json) preserve official results separately from mathematical inspection. Expression evaluation happened only after generation for scoring; no computed values were fed back to the agent. The original pilot and first prompt-check records remain unchanged. Peer-discussion comparisons remain untested in these single-agent follow-ups.
