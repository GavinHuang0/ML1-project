# Next experiment steps

The active setup is fixed to `llama3.2:3b`, 1024 output tokens, and `posterior-v2` sensor correctness at absolute tolerance 0.001. The October 24 migration changes configuration, sensor scoring, and sensor panel aggregation; it does not run a new inference experiment. Historical results and their interpretations are in [the legacy archive](../archive/2026-10-24-legacy/README.md).

First run the frozen diagnostic or the full current suite to establish a result under the new protocol. Report required-field validity separately from numerical correctness. Llama's earlier diagnostic had eight answer-contract failures, at least five with a correct mathematical conclusion or equivalent derivation in the explanation. Those old official scores remain unchanged.

The proposed next prompt experiment remains a fixed two-field response template against the existing prompt, with one agent, one generation per item, matched seeds, and no calculator or retries. That template has not been implemented by this configuration/scoring revision. Check it on a small new set of urn, algebra, and unit questions before scaling. Evaluate consistency between explanations and final answers separately; never extract a number from prose to rescue historical scores.

For sensors, headline correctness must use the exact posterior tolerance rather than agreement with a hidden-state decision. Before a larger evaluation, build a balanced development set with varied posterior strengths and both hidden states, then freeze prompts and evaluate on separate held-out questions. Related variants must stay in the same split. Any later communication comparison needs an independent-answer baseline with comparable call budgets and separate input/output token accounting.
