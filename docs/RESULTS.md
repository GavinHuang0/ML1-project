# Llama pilot results under posterior scoring

On November 6, 2026, the active Llama suite completed all 80 calls under `llama-1024-posterior-v2`. Every method scored 0/4 on the full probability pilot. The single-agent math-check prompt again solved both original urn questions, but the broader diagnostic still failed to deliver reliable structured answers. The run establishes the new scoring baseline; it does not demonstrate a general benefit from checking or discussion.

## Run and validation

The [run manifest](../results/runs/llama3.2-3b-pilots-20261106T191224204871Z/run-manifest.json) records `llama3.2:3b`, a 1024-token output cap, temperature 0.7, the frozen sampling seeds, and Ollama `0.40.4`. The model digest is `a80c4f17acd55265feec403c7aef86be0c25983ab279d83f3bcd3abbcb5b8b72`. Generation began from clean revision `02cf4376bef11b9364aa04d47b2aad5b3bca48ab`, and all recorded source hashes stayed unchanged and match the current generation code. The requested context was 4096 tokens.

Independent analysis reproduced the full-pilot tasks, raw parsing, scores, transition counts, and budgets; all 20 single-agent answers also rescored exactly as saved. Raw hashes match their summaries, and sent single-agent messages, tasks, and seeds match the active configuration. Every profile and the manifest have completion markers. The [verified interpretation](../results/runs/llama3.2-3b-pilots-20261106T191224204871Z/interpretation.verified.json) records the checks, raw hashes, metrics, historical response comparisons, and manual qualifications. Original responses and scores are unchanged. Analysis made no new model calls.

## Full probability pilot

| Method | Panel correct | Individual correct | Invalid responses | Mean sensor posterior absolute error | Valid sensor responses |
| --- | --- | --- | --- | --- | --- |
| Single answer | 0/4 | 0/4 | 0/4 | 0.555946 | 2/2 |
| Independent aggregation | 0/4 | 0/12 | 0/12 | 0.536501 | 6/6 |
| Self revision | 0/4 | 0/12 | 0/12 | 0.611154 | 6/6 |
| Answers only | 0/4 | 0/12 | 2/12 | 0.444183 | 4/6 |
| Justifications | 0/4 | 0/12 | 0/12 | 0.658029 | 6/6 |
| Source deduplication | 0/4 | 0/12 | 0/12 | 0.501779 | 6/6 |

The single and independent baselines reuse initial calls; do not sum their rows as separate experiments. Across the actual 60 calls there were 58 valid answers, all wrong: 30 urn answers and 28 sensor answers. The closest valid answer was still about 0.093629 away from its reference, so the zero scores are not a numerical boundary effect of the 0.001 tolerance.

Both urn questions show correct formulas followed by incorrect arithmetic or inconsistent final answers. For example, an initial response writes `(12/15)*(11/14)` but returns `11/60` instead of `22/35`. Revisions do not repair any urn answer.

For sensor question `0001`, the exact posterior is `1/82`, approximately 0.012195. The initial answers are 0.625, 0.8, and 0.75, producing a median of 0.75. For question `0003`, the reference is `2/2189`, approximately 0.000914; the initial median is `1/3`. These estimates are far from the required probabilities. Explanations reverse likelihoods, use incorrect normalization, or treat different source IDs as repeated observations. The stricter posterior headline exposes errors that a state-decision score could conceal.

All four revision branches have **G = H = 0**. This is a correctness floor: no initial answer was correct, and no revision became correct. In particular, zero H cannot establish resistance to corruption because there were no correct initial answers to corrupt. Continuous errors still change: self revision and justifications increase mean sensor error relative to the initial panel. Source deduplication lowers it modestly, but never reaches tolerance. Answers-only has the lowest valid-only mean, yet excludes two failed sensor answers, so it cannot be cleanly ranked as an improvement.

Two answers-only responses to sensor question `0001` hit the 1024-token cap and leave unfinished JSON strings. They repeatedly attempt inconsistent recalculations around the model's own claimed “expected” answers. Those numbers were not supplied reference answers. Extra output space extended these loops without completing the response. Thus 1024 tokens removed neither all truncation nor the underlying mathematical failures.

## Original urn prompt comparison

| Question | Reference | Original prompt | Math-check prompt |
| --- | --- | --- | --- |
| 12 red, 3 blue; draw two red | `22/35` | `11/60`, wrong | `22/35`, correct |
| 8 red, 2 blue; both red given at least one red | `7/11` | `1/3`, wrong | `7/11`, correct |

The math-check condition scores **2/2**, compared with **0/2** for the original prompt. Both checked derivations are mathematically sound. This is a narrow success on these two inspected questions. The instruction bundle also requests explanation-first ordering, so the experiment does not isolate checking from field order. Neither checked response includes the requested literal `Math check` label.

## Diagnostic questions and answer delivery

| Item | Baseline | Checking |
| --- | --- | --- |
| Supplied unconditional expression | Wrong `5/22`; missing explanation | Wrong `0.58333333333` |
| Unconditional expression construction | Correct `(7/12)*(6/11)` | Same correct expression |
| Full unconditional urn | Wrong `0.305555...` | Correct `7/22` in explanation; missing final answer |
| Supplied conditional expression | Correct `5/13` in explanation; missing final answer | Correct `5/13` |
| Conditional expression construction | Correct `15/39` numerically | Wrong `6C2/(6C2+4C2)` and unsupported syntax |
| Full conditional urn | Incomplete; missing final answer | Wrong `5/11` |
| Algebra | Correct `7` in explanation; missing final answer | Correct `35/5` derivation; missing final answer |
| Unit conversion | Correct `30` in explanation; missing final answer | Correct `30` |

Under the unchanged answer contract, baseline scores **2/8** and checking **3/8**. Both full urn questions remain official failures in each condition, but the checked unconditional failure is an answer-field omission despite correct mathematics. It should not be described as a wrong calculation.

Eight of the 16 responses fail their answer contracts: six omit `final_answer`, one omits `explanation`, and one uses unsupported expression notation. All 16 are syntactically valid JSON objects. At least five invalid responses contain a correct conclusion or equivalent derivation in the explanation; they remain official failures. The two baseline-to-checking score gains are supplied conditional arithmetic and units, where checking delivers an answer that was already correct in baseline prose. Conditional construction regresses from a correct numerical expression to an invalid, mathematically wrong one. The net 2/8 to 3/8 gain therefore does not demonstrate a general improvement in calculation.

Construction also requires qualification: baseline `15/39` is accepted numerically, although it evaluates counts despite requesting an unevaluated expression. The checked `6C2/(6C2+4C2)` violates the syntax and equals `5/7`, rather than the correct `5/13`. Manual mathematical findings are separate from official scores.

All 20 single-agent responses stopped normally, with a maximum of 293 output tokens. None of the ten checking-condition responses across the two profiles includes its requested checking label. These failures do not call for a higher token cap, and the results do not establish that a consistent checking procedure was followed.

## Reproduction of earlier behavior

All **20 single-agent response texts and their reported input/output token counts are identical** to the archived October 16 Llama results. The model digest, runtime, prompts, seeds, and effective generation settings match. This adds evidence that those cases reproduce under the same inputs, not fresh question coverage or independent sampling evidence.

In the full pilot, 57/60 response texts exactly match the archived 512-token run. The two continuing truncations extend the same old truncated text as exact prefixes. The remaining changed response, a source-deduplication answer to the conditional urn, now finishes at 756 tokens but remains wrong at `1/3`.

Historical sensor accuracy used a state decision and state-label voting; the current run uses posterior tolerance and numerical median aggregation. An apparent change from an old nonzero score to current zero is not evidence that the model regressed. Archived scores have not been rewritten.

## Budget and next step

| Profile | Calls | Input tokens | Output tokens | Summed request seconds |
| --- | --- | --- | --- | --- |
| Full | 60 | 30,085 | 13,768 | 671.71 |
| Original urn comparison | 4 | 588 | 668 | 33.87 |
| Diagnostic | 16 | 2,512 | 1,911 | 104.50 |
| Total | 80 | 33,185 | 16,347 | 810.09 |

The calendar interval was about 13 minutes 31 seconds. Related question variants, reused initial answers, and revision branches are dependent; these counts are not 80 independent benchmark questions.

The subsequent [40-call template comparison](TEMPLATE_EXPERIMENT.md#results-on-november-6-2026) tests the proposed prompt change on a frozen fresh/regression split. It improves fresh answer-contract validity from 3/12 to 11/12 and strict correctness from 1/12 to 5/12, while retaining important mathematical failures and regressions. Its record and interpretation are separate from this original baseline run.

This baseline motivated a compact two-field response template with a bounded explanation against the frozen prompt, keeping Llama, 1024 tokens, one agent, one call per item, no calculator, and no retries. The linked follow-up has now completed that comparison. It evaluates field completion, numerical correctness, and agreement with explanations separately on fresh development and existing regression cases. Once single-agent correctness and answer delivery are reliable enough to avoid the present floor, return to communication comparisons with comparable budgets.
