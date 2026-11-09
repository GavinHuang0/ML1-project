# Calculator pilot results

The eight-case `planner-calculator-v1` development run completed on November 6, 2026. Every model response supplied both required fields, five expressions were executable, and three computed answers were correct. The calculator performed arithmetic correctly on supported inputs; the remaining failures expose expression-interface and problem-formulation errors. This is a known-case readiness check, not evidence of a general calculator benefit.

## Protocol and verified record

Each item received one `llama3.2:3b` generation at 1024 output tokens, temperature 0.7, and a requested 4096-token context, with seeds 8201–8208. Llama returned `explanation` and `expression`. The calculator received only that explicit expression, once, without task references or feedback. The final numerical answer came from exact arithmetic, then was scored against the reference with absolute tolerance 0.001. The [protocol](CALCULATOR_PROTOCOL.md) defines these stages and their separate metrics.

The existing [run manifest](../results/runs/calculator-pilot-20261106T205135473899Z/run-manifest.json) and [raw responses](../results/runs/calculator-pilot-20261106T205135473899Z/answers.jsonl) were found complete and were not rerun for this interpretation. The [summary](../results/runs/calculator-pilot-20261106T205135473899Z/summary.json) and [independent verification](../results/runs/calculator-pilot-20261106T205135473899Z/verification.json) agree on all eight scores and calculated answers. Sent messages match the frozen system instruction and question text, without gold fields. Re-evaluation confirmed that the calculator receives only the original expression. Raw responses, failed expressions, and original scores remain unchanged.

Generation source hashes match the current files and stayed unchanged during the run. Configuration SHA256 is `1c009e2c9dd183aa095f549c99fdb4b8db639bc3305d19e2392abe9608f1187d`. The model digest is `a80c4f17acd55265feec403c7aef86be0c25983ab279d83f3bcd3abbcb5b8b72`, with Ollama `0.40.4`. Generation used a dirty working tree based on revision `b8487754ffabb314aaf5e388bb3f0c13a384a88c`; source hashes identify the actual calculator implementation. All 109 offline tests passed before this publication.

## Outcomes

| Measure | Result |
| --- | --- |
| Completed model calls | 8/8 |
| Valid JSON and both required string fields | 8/8 |
| Exactly the requested two keys | 8/8 |
| Calculator evaluations attempted | 8 |
| Executable expressions | 5/8 |
| Correct computed and strictly delivered answers | 3/8 |
| Explanations within 60 words | 4/8 |
| Truncated responses | 0/8 |

| Case | Model expression or failure | Computed result | Reference | Interpretation |
| --- | --- | --- | --- | --- |
| Unconditional urn: 12 red, 3 blue | `(12/15)*(11/14)` | `22/35` | `22/35` | Correct setup and execution |
| Sensor question 0001 | Symmetric sums of reliability/complement terms | `1/2` | `1/82` | Executable but wrong Bayesian formulation |
| Conditional urn: 8 red, 2 blue | `(8/10)*(7/9)/((8/10)+(7/9))` | `28/71` | `7/11` | Wrong conditioning denominator |
| Sensor question 0003 | Unicode `∗` and implicit multiplication | Rejected | `2/2189` | Unsupported syntax, with duplicated factors and missing proper normalization |
| `4*x - 11 = 21` | `x = (21 + 11) / 4` | Rejected | `8` | Correct numeric right-hand side, but forbidden assignment syntax |
| `3*x + 5 = 2*x + 14` | `3*x + 5 - 2*x - 5` | Rejected | `9` | Contains an unresolved variable and omits the right-hand value |
| 84 km/h for 35 minutes | `(35/60)*84` | `49` | `49` | Correct setup and execution |
| 96 km/h for 18 minutes | `(96*18)/60` | `144/5` | `144/5` | Correct setup and execution |

By family, urn answers score **1/2**, sensors **0/2**, algebra **0/2**, and units **2/2**. These eight inspected questions are not a representative accuracy estimate.

## What the separation reveals

All five supported expressions were evaluated faithfully. Two are mathematically inappropriate methods for their questions: the conditional urn divides by a sum that is not the probability of at least one red, and the sensor expression uses symmetric additive terms instead of the required joint likelihoods and normalization. These are formulation failures, not incorrect calculator arithmetic.

Three expressions are rejected by the declared interface. The first algebra case has a correct numerical expression after its `x =` prefix, so the failure is avoidable interface friction. The second algebra case is not merely bad notation: its expression does not supply a numeric solution. The rejected sensor expression also has substantive probability errors beyond its unsupported operators. No prefixes were stripped, operators normalized, variables solved, expressions extracted, or failed answers retried. Doing so would define a different protocol and must not alter this run's scores.

The operation-presence flag is true for six outputs; its two false values come from expressions that could not be parsed, not from observed literal-only answers. The tiny-posterior sensor case remains a rejected expression. Because `2/2189` is below 0.001, some incorrect near-zero formulas could pass numerical tolerance if accepted; numerical success alone cannot establish sound formulation. No literal-zero success occurred here, and the invalid sensor expression was not repaired or rescored.

All explanations for the four probability questions exceed the requested 60-word limit; the four transfer explanations satisfy it. The longest generated response used 257 tokens, so neither the syntax errors nor the wrong formulations can be attributed to exhausting the 1024-token cap.

## Limits and next step

The pilot changes the prompt, output representation, sampling seeds, and execution pipeline compared with earlier unassisted runs. Its 3/8 score cannot be treated as a causal calculator improvement or regression against the earlier 5/12 template result. The two rate problems illustrate the intended arithmetic handoff, while the algebra and sensor failures show that constructing an executable, appropriate method remains part of the agent's task.

Keep this result as a frozen readiness baseline. The next controlled change should address numeric-expression delivery explicitly and test on new cases, preserving unsupported outputs as failures rather than silently repairing historical records. For any later self-revision versus peer comparison, every arm must share the same calculator-enabled initial plans/results, grammar, execution policy, reference-free feedback policy, and model budget rules. Sensor formulation should be reported separately, with posterior errors and method inspection alongside tolerance-based correctness.

The run used **8 model calls**, **8 calculator attempts**, **1,753 input tokens**, **961 output tokens**, and **67.98 seconds** of summed model request time. Its calendar duration was **68.66 seconds**. Independent validation re-executed expressions only for verification; it made no new model calls or corrective attempts.

The subsequent [paired syntax-prompt comparison](CALCULATOR_SYNTAX_EXPERIMENT.md) keeps this calculator and scorer fixed. It tests the original questions as regression cases alongside eight fresh questions and reports syntax gains, new failures, and mathematical changes separately.
