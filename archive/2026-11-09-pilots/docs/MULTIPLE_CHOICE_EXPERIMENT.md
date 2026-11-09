# Exact-fraction multiple-choice experiment

`mc-exact-v1` is a separate answer-selection experiment. Its first sixteen-call run completed on November 7, 2026, with **1/16 delivered correct answers**. The frozen design below and the results section preserve the experiment separately. The existing unassisted, template, and calculator experiments, commands, prompts, scores, and saved outputs remain available. This experiment does not replace them or run a calculator comparison automatically.

## Questions and choices

The [question bank](MULTIPLE_CHOICE_QUESTION_BANK.md) contains all sixteen mathematical questions from the [calculator syntax comparison](CALCULATOR_SYNTAX_EXPERIMENT.md), each with fifteen exact-value options labeled A through O. It preserves every mathematical given and removes only the terminal expression-output instruction on algebra and units questions. There are four urn, four sensor, four algebra, and four unit-conversion questions.

All sixteen questions and earlier responses have already been inspected. The eight questions formerly called fresh are now the `syntax_reuse` cohort; the eight original calculator-pilot questions are `pilot_reuse`. Neither cohort is fresh or held out in this experiment. The source identifiers, source configuration hash, seeds, choice construction rules, and answer keys are recorded in [the new configuration](../config/multiple_choice_experiment.json).

Every option has the same reduced `n/d` representation, including integers such as `7/1`. There are fifteen mathematically distinct values and exactly one correct option per question. Probability options lie strictly between zero and one. Distractors use errors such as ignoring conditioning, drawing with replacement, omitting Bayesian normalization, moving an algebra term with the wrong sign, or using an incorrect time conversion. Where necessary, algebra items also use explicitly tagged nearby rational alternatives. These author explanations are not model feedback and do not prove the reason for a later wrong selection.

The frozen shuffle seed is `20261107`. Correct-answer positions were shuffled separately from distractors: A is correct twice; each other letter is correct once. Choices are not sorted numerically. This is one fixed ordering per question, so the pilot does not establish robustness to option order. The bank includes an author answer key for review; the key and distractor annotations are excluded from model messages.

## Prompt

Every question uses this same system prompt:

> Choose the one correct exact value for the user's question from options A through O. Preserve the given values, conditioning information, and requested units. Every option is an exact fraction; n/1 represents the integer n. Return ONLY a valid JSON object with exactly two string fields: explanation, briefly explaining your reasoning in at most 60 words; and choice, containing exactly one uppercase letter A through O. Before sending, check that the chosen label matches the value you intend.

The user message consists only of the mathematical question, the fifteen labeled fraction values, and `Select exactly one option.` Each complete user message is shown in [the review bank](MULTIPLE_CHOICE_QUESTION_BANK.md). The renderer explicitly selects only these fields. It does not send source IDs, family/cohort metadata, prior responses, answer keys, or author rationales. The correct numeric value is present among the options, as required by the task.

## Procedure

Run one independent model call per question, in frozen configuration order: **sixteen calls total**. Each call starts with just its system and user message. Use only `llama3.2:3b`, a 1024-token output cap, temperature 0.7, and a 4096-token context. The original question seeds are retained for reproducibility; matching a seed across different prompts does not make this a controlled causal comparison with earlier runs.

The model returns a short explanation and one letter. Local scoring checks that letter against the authored key. There is no calculator invocation, expression construction or execution, agent discussion, revision, repair, retry, or correctness feedback. A malformed model answer is recorded once and the next question proceeds. A transport/service failure, source change, runtime/model change, or interruption stops the run and preserves its partial records.

The same local Ollama client and fixed model/token settings are reused. The new runner, renderer, scorer, configuration, protocol identity, and result namespace are separate from earlier experiment code. Fraction arithmetic is used to validate the authored bank before a run; model responses are never interpreted as mathematical expressions.

## Scoring fixed before inference

The primary delivered-correctness measure is `correct`: a valid JSON object must contain string `explanation` and `choice` fields, and `choice` must be exactly the uppercase label of the correct option. All sixteen calls are in the denominator. A wrong choice, missing field, invalid JSON, lowercase letter, numeric fraction in place of a letter, or label embedded in prose does not satisfy this contract. No normalization or answer extraction is applied. Duplicate JSON keys and nonfinite JSON values are rejected.

Also report `choice_correct` independently of explanation delivery, `choice_valid`, JSON/required-field validity, exact two-field compliance, explanation word count, truncation, per-question selections, selected-value/rationale diagnostics, and input/output token budgets. The 60-word limit and extra-key flag are secondary compliance measures and do not change an otherwise delivered correct answer. Explanation mathematics is retained for manual review and is not automatically scored. A correct letter with a mistaken explanation can therefore count as correct.

Correctness means exact option identity for every family, including sensors. There is **no closest-value rule, posterior tolerance, or hidden-state threshold** in this experiment. The previous posterior-tolerance scores remain unchanged. A distractor numerically close to the correct sensor posterior is still wrong here. Any later exact-value reanalysis of earlier outputs must be separately labeled and must not overwrite historical scores.

Report results overall, by family, by reuse cohort, and by family within cohort. Uniform random choice has accuracy `1/15`, about 6.67%. Fifteen options reduce the guessing baseline, but their quality and the information supplied by the option set affect difficulty. This pilot evaluates answer selection with candidate values available. It can reveal whether avoiding expression generation improves delivered accuracy, but it does not cleanly isolate reasoning from arithmetic or establish improved underlying reasoning. Historical comparisons will be descriptive because task format, answer information, and scoring differ.

## Preview, run, and records

From the repository root, preview the full configuration and all sixteen exact requests without contacting Ollama or writing output:

```sh
python3 run_multiple_choice_experiment.py --dry-run
```

To run the prepared experiment:

```sh
python3 run_multiple_choice_experiment.py
```

New runs are saved under `results/multiple-choice/<UTC>-mc-exact-v1/`, separate from `results/runs/`. An optional `--output-dir results/multiple-choice/my-run` must name a new directory. Historical result/archive destinations are refused. `--timeout` changes only the per-request timeout; model and output-token overrides are not provided.

Each run saves `run-manifest.json`, `answers.jsonl`, and, after completion, `summary.json`. They preserve the frozen configuration, source hashes, exact requests, original responses, original labels and values, scores, model digest, Ollama version, generation settings, timings, token counts, and completion/failure status. Partial outputs are retained and never treated as a complete sixteen-question result. New raw runs remain local until reviewed and explicitly selected for versioning.

The question bank is the reviewable design artifact. Offline tests validate the references independently from the question wording, mathematical option uniqueness, source preservation, strict label scoring, model-message boundaries, and simulated runner behavior. They do not establish model accuracy. The real-model results are recorded separately below.

## Preparation validation on November 7, 2026

All **147 offline tests passed**, including 28 new bank, scoring, and runner tests. The existing HTTP-client checks use a temporary loopback fixture; no real-model inference is involved. Independent calculations from the question wording confirm all sixteen references. All 240 possible authored option selections were checked, with exactly one correct choice per question. The CLI dry-run produces sixteen requests without service access or output writes, and the review bank matches those requests exactly.

Configuration SHA256 is `c4fe818a796604087315d1df9bbfaf1f751e1695bb69b36d3713843390bf566f`. The workflow imports no calculator or previous runner. The recorded calculator-syntax generation-source hashes and verified raw/summary/manifest hashes remain unchanged. These are preparation checks, not multiple-choice accuracy results.

## Results on November 7, 2026

All **sixteen calls completed** once under the frozen design. Exact selected-choice and delivered correctness both score **1/16 (6.25%)**. Fifteen responses contain valid JSON, both required strings, exactly two fields, and a valid uppercase choice. One algebra response reaches the 1024-token cap and leaves incomplete JSON; it remains invalid and incorrect. No failed answer was repaired or retried.

The [manifest](../results/multiple-choice/20261107T195716817040Z-mc-exact-v1/run-manifest.json), [original responses](../results/multiple-choice/20261107T195716817040Z-mc-exact-v1/answers.jsonl), [summary](../results/multiple-choice/20261107T195716817040Z-mc-exact-v1/summary.json), and [independent verification and manual review](../results/multiple-choice/20261107T195716817040Z-mc-exact-v1/verification.json) preserve the complete run. All sixteen scores, exact requests, tasks, seeds, order, budget totals, and the regenerated summary were verified. The configuration and all five generation-source hashes match the independent preflight and final/current files.

| Family | Valid choices | Delivered correct |
| --- | --- | --- |
| Urns | 4/4 | 0/4 |
| Sensors | 4/4 | 0/4 |
| Algebra | 3/4 | 1/4 |
| Units | 4/4 | 0/4 |
| Total | 15/16 | 1/16 |

The `syntax_reuse` cohort scores 0/8, with seven valid responses. The `pilot_reuse` cohort scores 1/8, with all eight valid. Neither is held out. The sole success solves `3*x+5 = 2*x+14` as `x=9` and correctly selects A, `9/1`.

### Correct numerical work can still produce the wrong selection

Four failed responses visibly derive the correct numerical answer but fail to deliver its option:

| Question | Correct value and option | Observed failure |
| --- | --- | --- |
| `5*x+7=42` | K, `7/1` | Derives 7, repeatedly claims it is absent, confuses `7/5` with 7, and loops until the 1024-token cap. Its initial visible letter is A, also wrong; no letter is extracted from incomplete JSON. |
| `6*x-4=2*x+20` | N, `6/1` | Derives 6, claims no option contains 6, and selects A, `22/3`. |
| 66 km/h for 45 minutes | I, `99/2` | Derives `49.5 = 99/2`, selects A, `198/7`, and explicitly calls that fraction incorrect. |
| `4*x-11=21` | A, `8/1` | Derives `8/1` but claims option H represents it; H is actually `9/1`. |

These cases reveal a value-to-option matching and delivery problem in addition to mathematical errors. The correct numbers in the explanations do not rescue the official scores. The malformed algebra response also shows that a shorter intended answer format does not prevent a repetitive explanation from exhausting 1024 tokens. Fourteen of the fifteen normally stopped, valid responses are wrong, so truncation cannot explain the overall result.

### Arithmetic and probability errors remain

The unconditional urn responses start with appropriate setups and then make false fraction equalities. For six red/nine blue, the response obtains `15/105` but asserts it equals the selected `17/35`; it actually equals `1/7`. For twelve red/three blue, the response obtains `132/210` but asserts it equals `6/35`; it actually equals `22/35`.

This matters when interpreting distractor rationales: `17/35` was authored from a matching-colours error, but this response does not demonstrate that misconception. Its text instead shows the correct both-red count followed by incorrect arithmetic. A selected distractor alone cannot identify the model's reason.

The conditional urn responses also mishandle the conditioning event or its arithmetic. One calculates its probability as `121/110`, which is greater than one, and concludes `42/121` while selecting `49/121`. The other uses `2/45` for the all-blue probability instead of `1/45`, concludes `28/43`, falsely reduces it to `28/45`, and selects a different `17/45`. All four sensor selections are wrong. Three sensor explanations assert that Bayes' theorem gives the selected answer without showing likelihood calculations; the fourth incorrectly argues that the posterior remains 0.5 while selecting `2187/2189`.

Unit responses show arithmetic and additional selection inconsistencies. The 90 km/h question treats `14/60` as `7/15`, then resorts to a closest-value argument despite the exact-choice task. The 84 km/h question states the correct multiplication setup but reports `119/60`. The 96 km/h question states `96*(3/10)`, falsely evaluates it as `288/5`, and selects a third value, `432/25`.

### Descriptive historical comparison

| Same sixteen mathematical questions | Original calculator prompt | Clearer calculator prompt | Multiple choice |
| --- | --- | --- | --- |
| Urns | 3/4 | 2/4 | 0/4 |
| Sensors | 0/4 | 0/4 | 0/4 |
| Algebra | 0/4 | 2/4 | 1/4 |
| Units | 4/4 | 4/4 | 0/4 |
| Total delivered correct | 7/16 | 8/16 | 1/16 |

These are the original saved scores, not retroactive rescoring. The calculator conditions use numerical tolerance, while multiple choice uses exact option identity and supplies candidate values. Consequently this is a descriptive comparison between different tasks/protocols, not an isolated causal estimate of format or reasoning ability. None of the earlier correct cases remain correct here; the sole multiple-choice success had an invalid expression under both calculator prompts. The previous approach and its results remain unchanged.

### Compliance, budget, and interpretation

Ten of sixteen responses meet the 60-word bound; five valid responses exceed it and the incomplete response cannot be counted as compliant. The run uses sixteen model calls, 4,543 input tokens, and 2,631 output tokens, totaling 7,174. Summed model-request time is 137.12 seconds, calendar time is 137.60 seconds, and label scoring takes about 0.006 seconds. There are zero calculator calls. These timings are run observations rather than controlled speed measurements.

The model digest is unchanged from the earlier pilots (`a80c4f17acd55265feec403c7aef86be0c25983ab279d83f3bcd3abbcb5b8b72`) and Ollama is 0.40.4. Generation used a dirty working tree based on revision `31237783a203e2631b54da4036ff660a15d4e334`; source hashes identify the actual code and configuration. The prompt, choices, scoring, and settings were not changed after observing answers.

This first fifteen-choice design simplifies execution by removing the calculator interface, but its observed accuracy is poor and option matching introduces a substantial additional failure mode. Exact fractions still require mathematical interpretation, arithmetic, and matching the intended value to a letter. The observed 6.25% is numerically close to uniform guessing's 6.67% expectation; sixteen inspected questions with one ordering and seed each do not establish random behavior or performance below chance. This run provides no support for replacing the retained calculator approach with this prompt as an accuracy baseline.
