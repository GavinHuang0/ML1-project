# Next experiment plan

The next improvement should target calculation quality. The 512-token pilot removed all observed JSON truncation, but all 30 urn responses remained wrong and many sensor probabilities contradicted their explanations. More output space alone did not improve mathematical reasoning. The current single-agent prompt diagnostics use 1024 tokens; the historical 512-token pilot and its baseline prompts remain preserved for comparison.

## First test a calculation check

Add a separately versioned revision prompt that asks each agent to verify its calculation before accepting its own or a peer's answer. For urn tasks, require an explicit event numerator and denominator, an exact fraction, and a consistent decimal. For sensor tasks, require one likelihood contribution per unique source ID, the likelihood under each hidden state, and the normalized posterior `L1 / (L0 + L1)` for the equal prior. Ask for a concise calculation within the existing JSON explanation field.

Test this prompt against the existing self-revision and communication conditions using the same saved initial panel within each question. Include a calculation-checking self-revision control so any improvement can be separated from the effect of peer messages. Keep the model digest, temperature, sampling seeds, 512-token cap, and scoring fixed. Archive the exact prompt text, initial panels, code revision, and all outputs. Do not provide gold answers, corrective examples containing the pilot answers, or a calculator only to the proposed condition.

The existing four questions are debugging cases, already inspected during prompt development. Use them to check format and calculation consistency; improvement on them is not held-out evidence. A format pass means every response parses without reaching the output limit. Mathematical success must be measured separately with the existing urn tolerance and sensor posterior error. Record format regressions and valid wrong-to-correct transitions separately.

## Then build a balanced development pilot

Before a larger run, freeze a new development task manifest of roughly 50 questions with both urn variants, both sensor states in approximately equal numbers, and varied posterior strengths. This needs a versioned generator and analyzer extension: the current CLI does not guarantee balanced hidden states, and the analyzer expects the original seeded generator. Give the new task set its own version and IDs, preserve the four original questions as diagnostics, and keep related variants in the same data split. Preserve the ability to validate the historical runs with their original generation and scoring rules.

Report task families separately. For sensors, make absolute error from the exact posterior a primary probability metric alongside Brier score and binary decision accuracy. Include an always-zero decision baseline so the original state imbalance cannot masquerade as reasoning. Keep invalid answers visible in accuracy and validity counts, and report the valid denominator beside probability averages. Use a fixed set of development seeds to check sensitivity before freezing the final prompts.

## Establish a fair communication comparison

Add six independent answers per question as a baseline against three initial plus three revised answers. This matches generation-call counts, while input/output tokens still need to be measured because contexts differ. Specify tie and abstention handling before looking at the new results. Keep the three initial answers shared across revision branches; count shared calls once when reporting actual run cost.

Only after selecting settings on development data should the project freeze prompts and evaluate on a separate held-out set. Estimate uncertainty at the underlying-question level, keeping its agents, branches, and related variants together. Source deduplication also changes verification instructions and table presentation, so isolating its effect requires varying those factors separately.

The balanced generator, calculation-checking multi-agent comparison, and six-answer baseline remain proposed changes. A simpler single-agent prompt check at 1024 tokens is recorded as an [appendix to the second pilot](PILOT_512_RESULTS.md#single-agent-urn-follow-up-at-1024-tokens): it fixed one original urn answer but left the conditional case wrong. A subsequent [diagnostic sequence and transfer check](PILOT_512_RESULTS.md#single-agent-diagnostic-sequence-and-transfer-check) improved supplied-expression evaluation but left both fresh full urn questions wrong; algebra was already correct, the units item remained wrong, and the requested check sections were omitted. These results do not establish a general self-checking procedure. The [256-token report](PILOT_RESULTS.md) and [second pilot report](PILOT_512_RESULTS.md) preserve the completed results.
