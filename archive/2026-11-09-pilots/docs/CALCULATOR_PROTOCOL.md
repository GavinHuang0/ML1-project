# Planning and calculator execution protocol

`planner-calculator-v1` separates constructing a mathematical expression from executing arithmetic. Llama produces an explicit plan; a reference-free calculator evaluates it; scoring compares that computed result with the reference only afterward. The unassisted experiments, prompts, raw responses, and scores remain preserved as their own protocols.

## Procedure

Each item uses one `llama3.2:3b` generation with the fixed 1024-token output cap, temperature 0.7, a 4096-token context, and a recorded sampling seed. The model receives one system instruction and the user question. It returns two string fields:

```json
{"explanation":"Briefly explain the setup.","expression":"Unevaluated arithmetic expression"}
```

The system instruction says that a separate calculator will execute the expression, requests original given values and relevant conditioning/units, allows standard conversion constants, and asks for at most 60 explanation words. It permits plain integer/decimal numbers, parentheses, and `+ - * /`, including unary signs. It excludes names, functions, powers, LaTeX, and text outside JSON. The exact instruction is `SYSTEM` in [calculator_protocol.py](../calculator_protocol.py).

The calculator receives **only the explicit expression string**, once. It receives no question, task object, gold value, or model feedback. For example, `(2+3)*4` evaluates to the exact fraction `20`. The computed fraction, an optional approximate finite decimal, and `origin: "calculator"` are recorded as the calculated answer. The original model response is preserved verbatim. There is no second model generation, automatic repair, fallback expression, prose extraction, or retry of a failed answer.

This is an execution stage shared by the protocol, rather than an arithmetic check available only to a favored condition. A wrong formula is faithfully evaluated and can still yield a wrong answer. Introducing this mode changes both the requested answer representation and execution, so it does not isolate the causal effect of calculator access from the prompt change.

## Calculator and limits

[calculator.py](../calculator.py) uses restricted AST interpretation and exact rational arithmetic, including the original decimal literal spelling (`0.1 + 0.2` is exactly `3/10`). It never uses `eval` or `exec`. Supported expressions are bounded to 1000 characters, 200 AST nodes, depth 40, 64 characters per numeric literal, literal magnitude at most 1,000,000, and 4096 bits per intermediate numerator/denominator. Division by zero and unsupported/resource-exceeding expressions produce explicit calculator errors. Function calls and Python programs cannot be executed through this interface.

Exact fractions are authoritative. A decimal is an approximate display value and can be absent for a very large finite rational that cannot be represented as a finite float.

## Separate outcomes

The record distinguishes JSON validity, required field completeness, supported/executable expression validity, calculator attempts and successes, numerical correctness of the computed answer, and strict delivered correctness. Primary method-format validity requires both string fields and successful expression execution. Strict correctness additionally requires the computed answer to meet the reference tolerance and, for probabilities, lie between zero and one.

When a valid explicit expression is present but explanation is missing, the calculator can still run and numerical correctness can be recorded. That response still fails the complete-method delivery requirement. Missing or unsupported expressions remain failures; no expression is reconstructed from prose.

Numerical correctness uses the existing absolute tolerance of 0.001. Sensors are compared with their exact posterior, not a state decision. Word-limit compliance, exact two-key compliance, and whether an expression actually contains an arithmetic operation are secondary flags. A correct literal answer can pass numerical correctness without demonstrating a valid formulation. In particular, the inherited sensor reference `2/2189` is below 0.001, so the constant `0` is within numerical tolerance; that is not evidence of sound reasoning. Evaluating an expression to the right number does not prove that it represents the given event or uses the conditioning correctly. Original-givens usage and explanation/setup consistency need separate method review.

## Development pilot

[config/calculator_pilot.json](../config/calculator_pilot.json) fixes eight previously inspected cases: two original urn questions, two original sensor questions, two algebra problems, and two rate/unit problems. All are labeled `inspected_development`, including cases whose source IDs once described them as fresh. The two inherited sensor questions have the same sampled hidden state; their scores use posterior tolerance regardless. This is a readiness check, not a fresh held-out benchmark.

```sh
python3 run_calculator_pilot.py --dry-run
python3 run_calculator_pilot.py
```

The dry run contacts no model and writes no output. A real run uses eight model calls and at most eight calculator evaluations, saving original model plans, exact sent messages, execution outcomes, scores, model/runtime identity, configuration/source hashes, and complete/failed/interrupted status under a new `results/runs/calculator-pilot-.../` directory. Existing output directories are refused. Invalid model expressions are recorded without retry, and API failures or interruptions preserve partial data and stop the run.

The first [completed calculator pilot](CALCULATOR_RESULTS.md) has now been verified: all eight outputs supplied both fields, five expressions executed, and three computed answers were correct. Its protocol, raw expressions, errors, and original scores are preserved without repairs.

The output representation and protocol are separate from the original numeric-final-answer suite, whose prompts and scores are unchanged. Its analyzer should not be used to relabel these computed answers as unassisted Llama predictions.

## Policy for later revision and peer experiments

Every experimental branch must use the same planner schema, parser, calculator, error policy, model, token cap, and numerical scoring. Save one common set of calculator-enabled initial plans/results and start self revision and peer branches from that same state. Self revision must receive its own computed value just as peer conditions receive their peers' computed values; no branch receives the reference answer or extra automatic retries.

Count model calls, calculator attempts/successes, token use, and failures separately. Shared calculator access does not itself match model-call or token budgets. The self-versus-peer comparison is a future experiment; the prepared runner here is single-agent only.

## Verification status

All **109 offline tests pass**, including exact decimals, restricted syntax/resource bounds, reference-free single invocation, wrong-formula execution, missing-field distinctions, output preservation, failure/interruption handling, and source/runtime drift. The dry run confirms eight Llama/1024 calls and at most eight calculator evaluations without creating an output directory. The [live pilot verification](../results/runs/calculator-pilot-20261106T205135473899Z/verification.json) also reproduces all eight scores and the full summary, confirms exact request/configuration/source matches, and preserves raw responses and failed expressions unchanged.
