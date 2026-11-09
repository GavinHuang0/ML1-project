# Calculator expression syntax experiment

This experiment tests whether a clearer numeric-expression prompt improves calculator executability while preserving numerical correctness. The comparison keeps the existing calculator, scoring rules, model, and generation settings fixed. It does not repair rejected expressions or change historical scores.

## Frozen design

[config/calculator_syntax_experiment.json](../config/calculator_syntax_experiment.json) fixes both prompts, sixteen tasks, sampling seeds, and a counterbalanced thirty-two-call order before inference. Configuration SHA256 is `f35c71d3c5db19223ac292826dd9413c9d2b45d7bd6cb059e707fd7bf478612c`.

There are eight fresh development questions: one unconditional urn, one conditional urn, two sensor posteriors, two algebra equations, and two rates/unit conversions. The eight previous calculator-pilot questions are a separate inspected regression set. Each task receives one call per condition with the same seed. Condition order alternates between adjacent task pairs, with each condition first on eight tasks. The prior eight seeds and question texts are preserved in the regression set.

All calls use `llama3.2:3b`, 1024 output tokens, temperature 0.7, and a 4096-token context. There are no peers, calculator feedback to the model, input repairs, answer retries, reference feedback, or prompt changes after outcomes are observed. The 60-word explanation instruction remains the same in both conditions and is a secondary compliance measure.

| Fresh family | Questions | Exact references, used only after generation |
| --- | --- | --- |
| Urns | Both red from 6 red/9 blue; both red given at least one red from 7 red/4 blue | `1/7`, `3/7` |
| Sensors | Unique observations `(1,0.75),(0,0.6),(1,0.9)`; `(0,0.75),(1,0.6),(0,0.6)`, with equal state priors | `18/19`, `1/4` |
| Algebra | `5*x + 7 = 42`; `6*x - 4 = 2*x + 20` | `7`, `6` |
| Units | 90 km/h for 14 minutes; 66 km/h for 45 minutes | `21`, `99/2` kilometres |

The fresh sensor values are far enough from zero that a literal zero cannot pass the 0.001 tolerance. All tasks are still small development examples, not a held-out benchmark. The manifest includes reference values for scoring; only the system prompt and question text are sent to Llama.

## Prompt comparison

`baseline` is the exact original `calculator_protocol.SYSTEM` instruction. `syntax_clear` appends this contract without changing the JSON field names or calculator grammar:

> Expression-format contract: expression must be one NUMERIC expression, not an equation or an intermediate symbolic rearrangement. For algebra, finish isolating the requested unknown in your setup, then put only a numeric right-hand-side expression for its value in expression. Never put variable names or an equals sign in expression. Use only ASCII digits 0-9, decimal points, spaces, parentheses, and the operators +, -, *, /. Write ASCII '*' for EVERY multiplication and '/' for division. Do not use Unicode operators, implicit multiplication, scientific notation, functions, units, or prose in expression. These are syntax examples only, unrelated to your question. VALID: '(2+3)*4'; '2*(3+4)'; '(7-1)/(5+2)'. INVALID: 'x = (2+3)*4'; '3*y+5'; '2×3'; '2∗3'; '2(3+4)'. Before sending, check that expression has balanced parentheses, no letters or '=', and an explicit ASCII operator between multiplied quantities. Return the original two-field JSON object; do not manually evaluate the expression.

The examples are generic syntax examples, not worked solutions to the test questions. The addition bundles explicit restrictions, examples, and a pre-send check; their individual contributions are not identified. The algebra-isolation reminder can also affect formulation, so any numerical changes are not purely lexical effects.

## Outcomes fixed before inference

Report the fresh and regression sets separately. Primary outcomes are executable expressions (`calculator_success`) and complete executable methods (`method_format_valid`), each divided by all model calls in that condition. This is an executability measure rather than a pure character-syntax test: undefined arithmetic such as division by zero can also fail, so report calculator error categories alongside the counts.

Secondary measures are JSON/required-field validity, numerical correctness, strict delivered correctness, word-bound and exact-key compliance, arithmetic-operation presence, and input/output token budgets. The unchanged [calculator protocol](CALCULATOR_PROTOCOL.md) controls these definitions. No output is normalized, repaired, or rescored under a looser grammar. A syntactically executable expression may still represent the wrong probability or equation, and a correct literal value does not prove correct setup.

Use matched per-task changes in executability and strict correctness. Numerical correctness on the subset where both methods are executable is a selected secondary diagnostic, not a causal measure of mathematical ability. A syntax gain with unchanged or reduced correctness must not be described as a general reasoning improvement. With two fresh questions per family and one seed per item, conclusions remain descriptive.

## Running and records

```sh
python3 run_calculator_syntax_experiment.py --dry-run
python3 run_calculator_syntax_experiment.py
```

The runner uses a new `results/runs/calculator-syntax-.../` directory, preserving frozen configuration, original model responses, exact requests, reference-free calculator outputs, paired scores, source hashes, model/runtime identity, and complete/failed/interrupted status. It refuses existing output directories and stops on model/API failure or source/runtime drift. Model-content failures are recorded once and the experiment continues without retries.

## Results on November 6 2026

All **32 calls completed** using the frozen configuration and unchanged evaluator/scorer. Every response was a valid JSON object with the two required string fields, and none truncated. Independent verification reproduced all scores, calculator results, and the full summary; source/configuration hashes stayed unchanged. The eight regression baseline texts exactly match the previous calculator pilot. All **119 offline tests passed** before inference.

The [run manifest](../results/runs/calculator-syntax-20261106T211825622487Z/run-manifest.json), [raw responses](../results/runs/calculator-syntax-20261106T211825622487Z/answers.jsonl), [paired summary](../results/runs/calculator-syntax-20261106T211825622487Z/summary.json), and [verification](../results/runs/calculator-syntax-20261106T211825622487Z/verification.json) preserve the comparison. The model digest and Ollama version match the earlier pilot (`a80c4f17acd55265feec403c7aef86be0c25983ab279d83f3bcd3abbcb5b8b72`, `0.40.4`). The new experiment code ran in a dirty working tree based on revision `31237783a203e2631b54da4036ff660a15d4e334`; recorded source hashes identify the actual files.

### Primary executability and secondary correctness

| Question set | Baseline executable methods | Clearer prompt executable methods | Baseline correct | Clearer prompt correct |
| --- | --- | --- | --- | --- |
| Fresh 8 | 6/8 | 7/8 | 4/8 | 4/8 |
| Regression 8 | 5/8 | 5/8 | 3/8 | 4/8 |

Method-format validity equals executability in this run because all required fields are present. On fresh questions there are two recoveries and one new execution failure, a net gain of one. On regression questions there are two recoveries and two new failures, leaving the total unchanged. The clarification therefore does **not reliably eliminate expression errors**.

The fresh correctness count also stays unchanged: one gain is offset by one loss. On the five fresh pairs executable in both conditions, numerical correctness changes from 4/5 to 3/5. On the three regression pairs executable in both conditions, both prompts score 3/3. These selected subsets exclude changing failures and are secondary diagnostics, not broad reasoning estimates.

| Fresh family | Baseline correct | Clearer prompt correct |
| --- | --- | --- |
| Urns | 2/2 | 1/2 |
| Sensors | 0/2 | 0/2 |
| Algebra | 0/2 | 1/2 |
| Units | 2/2 | 2/2 |

### What changed on fresh questions

Both algebra assignments become executable, but only one becomes correct. For `5*x+7=42`, baseline uses the unsupported but mathematically correct right-hand side in `x = (42-7)/5`. The clarified response has a correct explanation yielding seven, but writes `42-7/5`, which the calculator correctly evaluates as `203/5`, or 40.6. This is a grouping/expression-construction failure, not faulty calculator arithmetic.

For `6*x-4=2*x+20`, baseline produces unsupported `x = (24/4)+4`, inconsistent with its explanation. The new response produces executable `24/4`, yielding the correct six. That is the one fresh strict-correctness gain, combining interface and expression-value recovery.

The fresh conditional urn loses a correct answer. Baseline's `21/49` equals `3/7`. The clarified explanation still derives the appropriate conditional ratio, but its explicit expression is only `(7/11)*(6/10)`, which equals `21/55` and omits the conditioning denominator. Correct reasoning in explanation text does not rescue an inconsistent submitted expression.

The new execution failure is a sensor expression containing forbidden `^` powers. Both sensor questions remain wrong under both prompts, with incorrect additive likelihood combinations or normalization. The unconditional urn and both unit answers remain correct.

### What changed on inspected regression questions

The clarification fixes two original rejection types: the Unicode/implicit-multiplication sensor expression becomes executable, and the assignment-prefixed algebra answer becomes executable. It simultaneously introduces forbidden `^` powers on a previously executable sensor answer and `C` combination notation on a previously executable conditional urn. The other algebra expression still contains unresolved `x`. Thus the error forms shift without an overall regression-set execution-rate gain.

The only regression correctness gain is `8*1` for `4*x-11=21`. Its value is correct and remains an official success, but it is an already calculated answer wrapped in an identity multiplication, not an unevaluated setup from the original givens. An arithmetic-operation flag alone cannot establish that the calculator performed the problem's calculation. The repaired sensor expression evaluates to wrong `9/22`; it is not a near-zero tolerance success.

Across the clarified outputs, all four rejected expressions contain either `^` powers, combination notation, or an unresolved variable. No expressions were rewritten or re-evaluated under relaxed syntax. All original and new scores are preserved.

### Compliance, budget, and interpretation

The explanation bound is met by 6/8 to 5/8 fresh responses and 4/8 to 5/8 regression responses: 10/16 under each prompt overall. The longest response uses 325 output tokens, well below 1024, so the failures are not output truncation. No bare literal-only expression occurs, but `8*1` illustrates a manually evaluated shortcut.

| Budget across both splits | Baseline | Clearer prompt |
| --- | --- | --- |
| Model calls | 16 | 16 |
| Calculator attempts | 16 | 16 |
| Input tokens | 3,480 | 7,160 |
| Output tokens | 1,779 | 1,811 |
| Total tokens | 5,259 | 8,971 |

The longer clarification increases total tokens by about 70.6%, with little net executability improvement. The full run uses 14,230 tokens, 227.33 seconds of summed model request timers, and about 228.23 seconds of calendar time. These are not controlled speed estimates or evidence of an efficiency improvement.

The outcome is mixed: the prompt helps several algebra/interface cases, but creates other syntax failures and no fresh overall correctness gain. Keep the original calculator prompt as the frozen baseline; preserve this clarification as a tested candidate rather than promoting it as a universal fix. Further variants need new development questions and explicit accounting of regressions. A separate syntax-enforcement or bounded correction policy could be studied later, but it would change the protocol and budget rules and must apply equally to every comparison arm. No such repair mechanism is introduced here.
