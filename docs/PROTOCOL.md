# Current experiment protocol

Protocol `llama-1024-posterior-v2` became the active setup on October 24, 2026. It uses only `llama3.2:3b` with a 1024-token generated-output cap. The model and limit are enforced by the installer, both runner CLIs, and the local inference client. The shared settings and scoring metadata are defined in [experiment_config.py](../experiment_config.py).

## Generation and recording

The pilot suite uses temperature 0.7, a requested 4096-token context, local Ollama, and a 300-second request timeout by default. The direct full runner defaults to 0.7 but allows a different recorded temperature; the model and output cap remain fixed. Sampling seeds are fixed and matched across prompt conditions. A token cap is a maximum; normally stopped answers can use fewer tokens. There are no calculator tools, answer retries, gold-answer feedback, or automatic prompt repairs. The optional setup smoke check uses temperature 0 and a 1024-token cap and is outside the pilot counts.

The response format remains JSON with a nonempty string `final_answer` and a string `explanation`. JSON mode does not enforce those required fields. Missing fields, unsupported answer notation, or invalid probabilities remain answer-contract failures; numbers in explanations do not rescue a missing final answer. The requested checking labels are recorded, but their presence is not proof of a correct check and their absence is not a separate correctness gate.

Raw JSONL files preserve every task, response, parsed result, seed, and budget. Single-agent records store the exact sent messages; the full-panel messages are reconstructible from the frozen prompts, source hashes, initial answers, and seeded peer order. Metadata includes protocol/scoring version, numerical tolerance, model digest, Ollama version, source/configuration hashes, Git revision and dirty status, and generation settings. The full runner checks that source hashes stayed unchanged. The suite also checks model/runtime identity between profiles and records complete, failed, or interrupted status in its manifest. Partial output is preserved, never silently overwritten or retried.

## Full pilot

`--pilot full` runs four seed-42 questions: the two original urn questions and two sensor posterior questions. It uses three agents and 60 calls. Each question has three independent initial answers and four separate branches of three revision calls. The single baseline reuses initial agent one; independent voting reuses all three initial answers. Each branch starts from the same initial panel, not from another branch's revisions.

The system instruction remains:

> Solve the user's probability problem. Return ONLY a JSON object with final_answer (a string containing a fraction or decimal probability between 0 and 1) and explanation (a concise, auditable calculation, citing source IDs when given). Do not write extra text outside JSON.

Every revision begins “Check your previous calculation and revise only if warranted.” Self revision adds no peers. Answers-only adds two peer final answers. Justifications adds peer explanations and, for sensors, their source tables. Source deduplication includes peer explanations and warns that agreement is not new evidence and each unique source ID must be used once. All agents within a run use the same Llama model. The prompt construction is in [run_experiment.py](../run_experiment.py).

## Single agent profiles

The frozen prompts, tasks, messages, and seeds are in [config/pilots.json](../config/pilots.json). They preserve the previous single-agent questions without loading historical responses during an experiment. The source artifact hashes identify their origin in the archive; those archived files are not runtime dependencies.

| Profile | Items and conditions | Calls |
| --- | --- | --- |
| `urn-check` | Two original urn questions, each with original and math-check prompts | 4 |
| `diagnostic` | Eight items, each with baseline and checking prompts | 16 |

Each cell is one fresh system message plus one user question and one generated answer. Checking happens within that generation. No baseline answer, earlier diagnostic stage, peer response, or computed reference is supplied to the checking condition.

The original urn questions use 12 red/3 blue balls for the unconditional question and 8 red/2 blue balls for the conditional question. Their original condition uses the full-pilot system prompt. The math-check condition appends:

> Before giving final_answer, end your explanation with a Math check: recompute the arithmetic step by step, verify that fractions and decimals agree, and check that your expression answers the stated event using the original ball counts and any conditioning information. Correct any mistake you find before giving final_answer. Put explanation before final_answer in the JSON object.

This changes both checking instructions and field ordering. The diagnostic comparison already requires explanation first in both conditions. Its baseline is:

> Solve the user's problem. Return ONLY one valid JSON object with explanation (a concise derivation) and final_answer (a string in the format requested by the question). Put explanation before final_answer. Do not use LaTeX, Markdown, or text outside JSON.

The diagnostic checking condition appends:

> Before finalizing, end your explanation with a Check: section. Verify that your setup uses the original given values and constraints; recompute each arithmetic step; and verify the result against the original problem using a second check when possible. Correct any inconsistency you find before giving final_answer. Make the check specific rather than merely stating that the answer is correct.

The eight independent diagnostic items are supplied-expression evaluation, expression construction, and full solving for each of the 7 red/5 blue unconditional urn and 6 red/4 blue conditional urn; algebra `5*x - 9 = 26`; and distance at 72 km/h for 25 minutes. The three related stages are diagnostic variants, not a sequential solving pipeline or independent underlying questions. Construction asks for an unevaluated expression using numbers, parentheses, and `+ - * /`.

## Posterior based sensor correctness

Scoring version `posterior-v2` defines an individual sensor answer as correct when its valid probability differs from the exact Bayesian posterior by at most **0.001**, inclusive:

```text
abs(reported_probability - exact_posterior) <= 0.001
```

Floating-point probability comparisons allow roundoff of `1e-15` at the inclusive boundary; this is recorded separately from the 0.001 substantive tolerance. Thus 0.501 against 0.500 passes, while 0.50100001 does not.

The reference combines each unique source exactly once with the question's equal prior. Headline accuracy, individual correctness, corrections G, corruptions H, and panel correctness all use this posterior rule. No reported probability is converted into a state decision at 0.5 for correctness or aggregation.

Sensor panels report the **median of their valid posterior estimates**, and that numerical median is checked against the same tolerance. Invalid estimates are excluded from the median, remain individual failures, and are counted explicitly. A panel with no valid estimates abstains and fails. With two valid estimates, the median is their midpoint. The method key `independent_voting` is retained, but its sensor aggregation is now numerical rather than a state-label vote.

For example, an answer of 0.25 is wrong when the reference is `1/82`, approximately 0.012195, even though both are below 0.5. Conversely, a report of 0.4999 is within tolerance of a reference 0.5002 despite lying on the opposite side of 0.5.

Absolute posterior errors and valid-only means remain secondary summaries, shown with valid denominators. Brier scores against the sampled hidden state are retained as diagnostics, not as the correctness rule. Invalid individual answers count as wrong in G/H; the denominator includes all paired agent slots.

## Other scoring and comparisons

Urn numeric answers retain the same absolute tolerance of 0.001. Urn panel aggregation is unchanged: group valid probabilities rounded to three decimals, abstain on a tied plurality, then score the median original value in the winning group. Algebra and units accept numerical strings outside the probability range. Diagnostic construction evaluates only the restricted arithmetic grammar after generation and compares its numerical value within 0.001; the scorer does not fully enforce the request to leave counts unevaluated or verify explanatory quality.

Old decision-based sensor scores are preserved in [the archive](../archive/2026-10-24-legacy/README.md). The active analyzer requires the current protocol metadata and rejects historical runs rather than silently rescoring them. To reproduce old results, use the archived analyzer in its own directory. No new results under this protocol have been claimed by the migration itself.

These are inspected development cases. Related calls and revision branches are dependent, sensor states are unbalanced in the original four-question pilot, and generation-call counts do not equal token budgets. They do not support a general model ranking or a claim that checking or discussion is universally effective.

## Migration verification

On October 24, 2026, all **54 current offline tests passed**, including fixed model/token rejection before network calls, posterior scoring and G/H, median sensor aggregation, inclusive tolerance boundaries, complete/partial run handling, and refusal to reinterpret historical scoring versions. The dry-run suite planned **80 calls, all Llama at 1024 tokens**, without inference or output writes.

All **39 original archived files** matched the byte lengths and SHA256 checksums recorded before migration. The archived analyzer reproduced the scores, question records, and budgets of all four historical full pilots; the seven archived scoring tests also passed. The migration performed no model installation or real inference, and did not modify any historical score or response.
