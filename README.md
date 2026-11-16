# ML1 Project: multi-agent communication

How many rounds of communication improve a multi-agent LLM system's collective accuracy enough to justify their token and time costs? We adopt the [experimental design discussed on November 15, 2026](https://chatgpt.com/s/t_6afa1956baec8191b2c6d69d0c30935d) as the project framework, with the remaining choices below to be frozen before the main experiment.

## Experimental design

| Component | Planned procedure |
| --- | --- |
| Agent panel | Ten separate generations from the same `llama3.2:3b` model; their errors may be correlated. |
| Round 0 | Each agent independently returns a brief `explanation` and arithmetic `expression`; the existing exact-rational calculator evaluates the expression. |
| Communication | Each agent receives the original question, its own previous response, and all nine peers' previous explanations, expressions, and calculator results or failure statuses, then produces a revised response. |
| Synchronous updates | Every prompt for round `t` uses the same completed round `t-1` snapshot. Calls may execute sequentially or concurrently under a fixed runtime policy. |
| Answer evaluation | Score the collective numerical result against a private reference; do not judge explanation quality or expose references/correctness feedback to agents. Preserve invalid outputs without repair. |

Collect every round through a prespecified maximum, even if answers stabilize, so all candidate stopping points can be evaluated offline. The primary objective selects **one globally fixed communication-round count**, with agent population and communication structure held fixed:

$$
R^* = \arg\min_{R \in \{0,\ldots,R_{\max}\}}
\left[L(R) + \lambda_T\,\widetilde C_T(R) + \lambda_W\,\widetilde C_W(R)\right],
\qquad \lambda_T,\lambda_W \ge 0.
$$

Here `L(R)` is one minus family-balanced accuracy. The cost terms are family-balanced means of cumulative input/output tokens and cumulative measured wall-clock time over communication rounds `1..R`, each normalized by a fixed calibration reference; report total costs including round 0 separately. Freeze cost references on development/calibration data, select `R*` on validation data under prespecified penalties, and evaluate on held-out questions without retuning. Report accuracy by round/family, invalid and abstention rates, beneficial/harmful revisions, cost curves, penalty sensitivity, and question-level uncertainty.

Use fresh evaluation questions, initially building on urn probability, sensor posteriors, algebra, and unit/rate problems. The existing sixteen inspected cases remain development/regression data; related question variants must stay in the same split. Round 0 provides the ten-independent-agent comparison. Self-revision and budget-matched independent sampling are recommended additional controls; adaptive learned stopping is a later extension.

**Choices still to freeze:** aggregation and ties, numerical tolerance and output eligibility, maximum rounds, benchmark size/family mix/splits, peer ordering/history/context and runtime policies, and cost normalization/penalties. Current proposals are exact-rational plurality with ties/no eligible answers abstaining (counted incorrect), exact rational equality, previous-round-only history, and at most three communication rounds. These remain provisional rather than finalized settings.

**Implementation status:** the multi-agent runner is planned. Implement it with a separate versioned configuration and result directory, saving per-agent prompts, seeds, raw responses, calculator outcomes, tokens/time, round summaries, and runtime provenance. The runnable code below is the existing single-agent control; its historical scoring and results are preserved.

## Current implementation: calculator baseline

This repository now has one active baseline: **Llama constructs a mathematical expression, a calculator evaluates it, and scoring checks the computed result.** All future experiments should start from this procedure and declare their changes explicitly.

The baseline uses the **original calculator prompt**, not the longer syntax clarification. It is the most useful starting point among the approaches tested so far, with known expression-format and reasoning weaknesses. Historical performance is **7/16 correct** on inspected development questions; this is not a validated general accuracy estimate. [Selection and results](docs/BASELINE_RESULTS.md)

## Install, preview, and run

Use Python 3.10 or newer and install [Ollama](https://ollama.com/download). Open Ollama or run `ollama serve`, then run these commands from the repository root:

```sh
python3 setup_models.py
python3 setup_models.py --check
python3 run_baseline.py --dry-run
python3 run_baseline.py
```

Only `llama3.2:3b` is installed and tested. The code uses the Python standard library; no Python packages are needed. On Windows, replace `python3` with `py -3`.

`--dry-run` previews all sixteen exact requests without contacting Ollama or writing results. The final command runs **one model call per question**, followed by at most one calculator attempt for that response. The sixteen fixed questions cover four urn, four sensor, four algebra, and four units problems. All have been inspected previously; they are development/regression cases, not a held-out test set.

New runs go to a unique `results/baseline/<UTC>-calculator-baseline-v1/` directory. An existing directory is never overwritten. For a named run or a slower computer:

```sh
python3 run_baseline.py --output-dir results/baseline/my-run --timeout 600
```

An optional `python3 setup_models.py --check --smoke` makes one additional calculator-baseline model call as an installation check. It is separate from experimental results.

## What happens for each question

1. **Ask Llama to set up the mathematics.** Send the system prompt below and the original question. Reference answers and scoring metadata stay local.
2. **Read its explicit expression.** The model returns JSON with string fields `explanation` and `expression`.
3. **Run the calculator once.** Pass only the expression string to the calculator. It has no access to the question or reference answer.
4. **Score the computed value.** Compare it with the reference after calculation. Preserve format, execution, and mathematical failures separately.
5. **Save the original evidence.** Record the exact request, unchanged model response, expression, calculator result/error, scores, and generation settings.

For example, for 90 kilometres per hour over 14 minutes, the intended model output could be:

```json
{"explanation":"Convert minutes to hours, then multiply by speed.","expression":"90*(14/60)"}
```

The calculator returns the exact value `21`. It does not decide whether the formula is appropriate. A wrong formula is faithfully evaluated; unsupported syntax is recorded as a failure. This example explains the procedure and is not inserted into model requests.

There is **no model revision, peer discussion, answer retry, expression repair, or extraction from explanation text** in the baseline. A wrong or malformed model answer is recorded once and the next question proceeds. A service failure or interruption preserves partial records and stops the run.

## Exact model prompt

Every question uses this unchanged system instruction from [calculator_protocol.py](calculator_protocol.py):

> Solve the user's problem by constructing one arithmetic expression. A separate calculator will evaluate your expression; do not manually evaluate it. Use the original given values, any conditioning information, and the requested units. Use standard unit-conversion constants when needed. Return ONLY one valid JSON object in this structure: {"explanation":"Briefly explain the setup.","expression":"Unevaluated arithmetic expression"}. Both fields must be strings. Keep explanation to at most 60 words. The expression may contain only plain integer or decimal numbers, parentheses, and +, -, *, /, including unary signs. Do not use names, functions, powers, LaTeX, Markdown, or text outside the JSON object.

The user message is exactly the task's `prompt` in [config/baseline.json](config/baseline.json). There are no answer options, worked examples, reference answers, or task-specific system hints in the actual requests.

| Setting | Baseline value |
| --- | --- |
| Active wrapper | `calculator-baseline-v1` |
| Planning/execution contract | `planner-calculator-v1` |
| Model | `llama3.2:3b` |
| Maximum output tokens per call | 1024 |
| Temperature | 0.7 |
| Context requested | 4096 tokens |
| Sampling seed | Fixed per question in the configuration |
| Response transport | JSON, non-streaming, model unloaded after each request |
| Explanation instruction | At most 60 words; compliance reported separately |

## Calculator rules

The [calculator](calculator.py) supports plain integer/decimal literals, parentheses, `+`, `-`, `*`, `/`, and unary signs. Fractions are written as division, such as `3/7`. Every multiplication needs `*`.

| Accepted | Rejected |
| --- | --- |
| `(21+11)/4` | `x = (21+11)/4` |
| `(8/10)*(7/9)` | `8x`, `2(3+4)`, or Unicode `×`/`∗` |
| `0.1+0.2` | Variables, functions, powers, units, scientific notation, or prose |

The calculator uses exact rational arithmetic: `0.1+0.2` gives `3/10`. An approximate decimal is saved for display where representable. It never executes Python programs or uses `eval`/`exec`. Limits are 1000 expression characters, 200 AST nodes, depth 40, 64 characters per numeric literal, literal magnitude at most 1,000,000, and 4096 bits per intermediate numerator/denominator. Division by zero and unsupported/oversized expressions produce recorded errors.

Only the explicit expression is evaluated, at most once. Assignments are not stripped, Unicode is not normalized, variables are not solved automatically, and no fallback expression is taken from the explanation.

## What counts as correct

A **strictly correct delivered answer** requires both required string fields, successful expression execution, and a computed value within **absolute error 0.001** of the reference. Probability answers must also lie between zero and one. This inherited tolerance applies to every family. Sensor correctness uses the numerical posterior, with no state decision at a 0.5 threshold.

The report distinguishes:

- JSON and required-field validity;
- calculator attempts and successful execution;
- numerical correctness of the computed result;
- strict delivered correctness;
- explanation length, exact two-key compliance, and arithmetic-operation presence;
- model calls, input/output tokens, calculator attempts, and time.

If explanation is missing but an explicit expression is available, calculation can still succeed; the response fails strict delivery. Word-limit violations, extra keys, and literal-only answers are secondary flags, not additional correctness gates. Correct values in explanation text never replace the expression field.

**Numerical success does not prove correct reasoning.** A literal answer can pass without demonstrating a formulation. The inherited sensor reference `2/2189` is smaller than 0.001, so even zero lies within tolerance. Keep this limitation visible and inspect methods separately; tightening the rule would require a separately versioned comparison.

## Results and reproducibility

Each completed run saves `answers.jsonl`, `summary.json`, and `run-manifest.json`. They contain the frozen configuration, exact messages, raw responses, calculated answers labeled `origin: "calculator"`, separate scores, source hashes, model digest, Ollama version, sampling settings, and completion/failure status. The runner checks source and model/runtime identity before calls and after the final call.

A complete run has sixteen answer records, a final completion marker, and manifest status `complete`. Failed/interrupted runs retain partial records. New raw runs stay ignored until deliberately selected for versioning. [Result locations](results/README.md)

The [historical reference](results/baseline/HISTORICAL_REFERENCE.json) selects the sixteen original-prompt records from the preserved November 6 comparison: 11/16 executable methods and 7/16 correct. **It is not a newly generated run.** The November 9 consolidation preserves the prompt, calculator, scorer, mathematical questions, and seeds; it prepares a clearer entry point without claiming a new model result.

## Rules for future experiments

Use this baseline as the control. Freeze each new design and questions before inference, use fresh evaluation questions for generalization, and record every intentional difference. Keep the model, token cap, calculator grammar, parser, numerical scoring, and failure policy identical across comparison arms unless one is the declared experimental variable. Do not silently improve old outputs or replace historical scores.

For future self-revision and peer comparisons, reuse the same initial calculator-enabled plans/results in every branch. If peers receive computed values, self revision also receives its own computed value. Do not provide reference-answer feedback. Report and control model-call, token, and calculator budgets separately. These revision/peer branches are not implemented in the active baseline yet.

## Active files and archived experiments

| Location | Purpose |
| --- | --- |
| [run_baseline.py](run_baseline.py) | Sole active experiment entry point |
| [config/baseline.json](config/baseline.json) | Original prompt, sixteen questions, seeds, and execution policy |
| [calculator_protocol.py](calculator_protocol.py) | Prompt, parsing, one-shot calculation, and scoring |
| [calculator.py](calculator.py) | Exact restricted arithmetic |
| [experiment_config.py](experiment_config.py) | Shared model/settings and provenance |
| [local_llm.py](local_llm.py), [setup_models.py](setup_models.py) | Local inference and model setup |
| [docs/BASELINE_RESULTS.md](docs/BASELINE_RESULTS.md) | Why this baseline was chosen and its limitations |
| [archive/2026-11-09-pilots/](archive/2026-11-09-pilots/README.md) | Preserved unassisted, template, syntax, multiple-choice, and earlier calculator pilots |
| [archive/2026-10-24-legacy/](archive/2026-10-24-legacy/README.md) | Earlier Qwen/Llama experiments and original scores |

Old experiment commands, configurations, reports, tests, and outputs are archived with their original bytes and SHA256 inventories. Historical provenance strings retain their original paths; the archive index explains how to resolve them. The other approaches remain available for reference but are not active defaults.

Run the active offline tests with:

```sh
python3 -m unittest discover -s tests -v
```

Tests use simulated model responses and a temporary loopback HTTP fixture. They do not download weights or measure model accuracy.
