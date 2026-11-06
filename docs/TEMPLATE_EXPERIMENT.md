# Explicit template and bounded explanation experiment

This experiment compares the frozen diagnostic baseline prompt with an explicit two-field JSON template and a 60-word explanation limit. It tests whether the change improves answer delivery and scored correctness separately. The intervention bundles the template and explanation bound, so it cannot identify their individual effects.

## Frozen design

The question manifest, exact prompts, sampling seeds, and counterbalanced call order are in [config/template_experiment.json](../config/template_experiment.json). They were fixed before inference. Its SHA256 is `fa398ee8a67f74fc5a66b5a2aeec50c9e7c7430b681b939aef684ea98c272815`.

Use only `llama3.2:3b`, 1024 output tokens, temperature 0.7, and a requested 4096-token context. Each item receives one fresh call per prompt condition with the same sampling seed. There are no peers, earlier answers, calculator tools, retries, gold feedback, response repairs, or prompt changes after results are observed. Call order alternates which condition goes first for each successive item; each condition goes first on ten items. The explanation limit is an instruction to the model, not an automatic truncation of its response.

There are **12 fresh numeric questions** and **8 inspected regression items**, each under two prompts, for **40 calls**. Fresh questions contain three unconditional urns, three conditional urns, three algebra problems, and three rate/unit problems. Regression items preserve the earlier eight diagnostic user messages and seeds. The three stages sharing an urn are related items, not independent underlying questions. Report fresh and regression results separately; the latter cannot establish transfer.

| Fresh family | Questions | Exact references used only after generation |
| --- | --- | --- |
| Unconditional urn | 9 red/6 blue; 4 red/9 blue; 10 red/7 blue; draw two red without replacement | `12/35`, `1/13`, `45/136` |
| Conditional urn | 5 red/7 blue; 9 red/3 blue; 3 red/8 blue; both red given at least one red | `2/9`, `4/7`, `1/9` |
| Algebra | `7*x+8=50`; `4*x-11=21`; `3*x+5=2*x+14` | `6`, `8`, `9` |
| Units | 84 km/h for 35 minutes; 54 km/h for 40 minutes; 96 km/h for 18 minutes | `49`, `36`, `144/5` kilometres |

The manifest includes reference values and parameters for post-generation scoring and auditing. Only each task's user prompt and the applicable system instruction are sent to the model.

## Prompt conditions

Both conditions use this existing baseline:

> Solve the user's problem. Return ONLY one valid JSON object with explanation (a concise derivation) and final_answer (a string in the format requested by the question). Put explanation before final_answer. Do not use LaTeX, Markdown, or text outside JSON.

The `template_bounded` condition appends exactly:

> Use exactly the two string fields in this JSON template, replacing both placeholders with your own content: {"explanation":"BRIEF CALCULATION","final_answer":"ANSWER IN THE FORMAT REQUESTED BY THE QUESTION"}. Keep explanation to at most 60 words. Include both fields and finish the JSON object.

Both already request explanation-first ordering. The new condition adds no mathematical checking instruction, worked example, or correct answer. The final-answer placeholder permits the expression format required by the two regression construction items.

## Outcomes fixed before inference

Report counts with denominators for all items, by split and condition, and by question family. Primary outcomes are required-field completion, answer-contract validity, and strict correctness. The contract remains the diagnostic contract: a string explanation, a nonempty string final answer, and a parsable number/fraction or permitted arithmetic expression for that task. Exact two-key compliance and the explanation bound are secondary outcomes, not extra correctness gates applied only to treatment.

Also report final-answer numerical correctness independently of whether the explanation field exists. This still requires valid JSON and a correctly typed and parsable `final_answer`; never recover an answer from explanation text. Probability answers must lie in 0 to 1 for numerical correctness. Compare numerical values against exact references with the existing absolute tolerance of 0.001. A missing final answer fails both strict and final-only correctness.

Count explanation words with `len(explanation.split())`. A missing/non-string explanation has no word count and does not satisfy the bound. Record exact-key compliance, truncation, input/output tokens, and request times for both conditions.

Use paired counts of strict-correct and final-only-correct improvements and regressions. Numerical accuracy on the subset where both answers satisfy the format contract is a secondary diagnostic: that selected subset can itself be affected by the intervention and is not a general causal measure of mathematical ability. A gain solely from delivering previously missing fields should be described as a delivery gain. With one seed per question and small family groups, treat results as descriptive development evidence; do not infer universal effectiveness or tune the prompt on these outcomes and call the same questions held-out tests.

## Running and records

The dedicated runner preserves exact prompts, tasks, messages, raw responses, source/configuration hashes, model/runtime identity, paired scores, and complete/failed/interrupted status in a new directory under `results/runs/`. It refuses existing output directories and stops on failure without answer retries. It leaves the original three-profile suite and all historical scores intact.

```sh
python3 run_template_experiment.py --dry-run
python3 run_template_experiment.py
```

## Results on November 6 2026

The frozen run completed **40/40 calls**, with all responses ending normally and none truncated. The [run manifest](../results/runs/template-bounded-20261106T195732100566Z/run-manifest.json), [raw responses](../results/runs/template-bounded-20261106T195732100566Z/answers.jsonl), [paired summary](../results/runs/template-bounded-20261106T195732100566Z/summary.json), and [independent verification](../results/runs/template-bounded-20261106T195732100566Z/verification.json) preserve the record. Configuration SHA256 stayed equal to the value registered above. All source hashes, model digest, and Ollama version stayed unchanged.

The model digest was `a80c4f17acd55265feec403c7aef86be0c25983ab279d83f3bcd3abbcb5b8b72`, with Ollama `0.40.4`. The code ran from a dirty working tree based on revision `02cf4376bef11b9364aa04d47b2aad5b3bca48ab`; generation-source hashes identify the actual new experiment code. Before inference, all 75 offline tests passed and independent enumeration, algebra substitution, and rate calculations verified the fresh references. Afterward, all 40 stored scores, the summary, sent messages, tasks, and seeds matched independent recomputation. No prompt was retuned, no answer retried, and no score rescued by reading a number from prose.

### Fresh questions

| Outcome | Baseline | Explicit template and bound |
| --- | --- | --- |
| Valid JSON object | 12/12 | 12/12 |
| Required string fields complete | 3/12 | 11/12 |
| Valid answer contract | 3/12 | 11/12 |
| Correct explicit final answer | 1/12 | 5/12 |
| Strict correct answer | 1/12 | 5/12 |
| Explanation within 60 words | 5/12 | 6/12 |
| Exactly the two requested keys | 3/12 | 11/12 |

Delivered accuracy increased from **8.3% to 41.7%**, with four wrong/invalid-to-correct paired changes, no correct-to-wrong official changes, one answer correct under both prompts, and seven failures under both prompts. Format failures fell from nine to one. These are descriptive results on twelve questions with one sampling seed each.

| Fresh family | Baseline strict correct | Template strict correct |
| --- | --- | --- |
| Unconditional urn | 0/3 | 1/3 |
| Conditional urn | 0/3 | 1/3 |
| Algebra | 0/3 | 2/3 |
| Units | 1/3 | 1/3 |

Three of the four gains primarily complete answers whose baseline derivations were already correct: the 9-red/6-blue urn (`12/35`), algebra with `4*x - 11 = 21` (baseline correctly reaches `4*x=32` and division by four), and algebra with `3*x + 5 = 2*x + 14` (`9`). The remaining gain is a clear numerical correction with both outputs valid: the 5-red/7-blue conditional urn changes from wrong `5/11` to correct `2/9`, with a sound conditional calculation.

Mathematical behavior is not uniformly better. Two baseline explanations correctly derive `45/136` and `1/9` but omit final answers; the template delivers wrong values near 0.117647 and `1/3`. Because baseline format already failed, those prose-level regressions are invisible in the official paired loss count. They are recorded as manual qualifications without changing scores. The remaining template field failure solves `7*x+8=50` as `x=6` in its explanation but still omits `final_answer`.

Only three fresh pairs are format-valid in both conditions. Within that selected subset, numerical correctness changes from 1/3 to 2/3. This is consistent with one mathematical repair, but is too small and selected by output validity to estimate a general reasoning effect. A correct final answer also does not guarantee a consistent explanation: the correct `12/35` response says to multiply a probability “by itself” while actually writing the correct different factors `9/15` and `8/14`.

### Regression questions

| Outcome | Baseline | Explicit template and bound |
| --- | --- | --- |
| Required fields and valid answer contract | 3/8 | 8/8 |
| Correct explicit final answer | 2/8 | 5/8 |
| Strict correct answer | 2/8 | 5/8 |
| Explanation within 60 words | 2/8 | 6/8 |

There are four paired correct-answer gains and one loss. Supplied unconditional arithmetic changes from wrong `5/22` to correct `7/22`, improving both mathematics and field completion. Conditional arithmetic, algebra, and units deliver correct final answers that were previously present only in baseline explanations. The loss is conditional expression construction: correct `15/39` becomes `(6*5)/(10*9 + 6*5)`, which uses permitted syntax but evaluates to wrong `1/4` rather than `5/13`.

Both regression full urn solutions remain wrong. On the three pairs valid in both conditions, numerical accuracy falls from 2/3 to 1/3. All eight baseline response texts exactly reproduce the earlier diagnostic baseline, so the regression section supplies a new prompt comparison rather than new baseline question coverage. Baseline `15/39` also evaluates counts despite the instruction to leave the expression unevaluated; that style requirement is outside primary numerical scoring.

### Explanation length and tokens

Only **12/20 template responses** meet the requested 60-word limit. Only 11/20 meet both the full answer contract and the bound. The correct fresh conditional repair uses 192 words, so that success cannot be attributed to actually following the length limit. The length instruction is partly followed; this run does not identify whether the template or the bound caused the delivery improvement. Bounds and exact-key compliance remain secondary, as registered before inference.

| Work across both splits | Baseline | Template and bound |
| --- | --- | --- |
| Calls | 20 | 20 |
| Input tokens | 2,396 | 3,636 |
| Output tokens | 2,385 | 2,051 |
| Total tokens | 4,781 | 5,687 |
| Median explanation words, among present explanations | 62 (17 explanations) | 54 (20 explanations) |

The template reduces generated tokens but increases total tokens by about 19% because its instructions are longer. The full run used 10,468 tokens and 259.69 summed request seconds; the calendar interval was about 4 minutes 21 seconds. These timings are not a controlled speed comparison. The longest answer used 293 tokens, well below the fixed 1024-token cap.

### Interpretation and next step

The strongest evidence is **better answer delivery**, with more correct usable outputs on these fresh questions. Mathematics remains mixed: the intervention has one clear fresh numerical repair, substantial recoveries of missing final answers, continued errors, and some mathematical regressions. Keep this as a promising prompt candidate rather than a general accuracy fix. Replicate the frozen candidate on another small new development set before adopting it for broader communication experiments. Separate fresh and known regression evidence, keep the model and 1024-token cap fixed, and retain the original prompts and scores for comparison. The original three-profile suite is unchanged by this experiment.
