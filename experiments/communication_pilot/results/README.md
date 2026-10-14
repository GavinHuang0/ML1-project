# Experiment results

Use this stage for later evaluation after selecting and recording settings through the pilot. The runner has no implemented development/held-out split, so choosing `--stage results` only changes the default artifact directory; it does not create or certify a held-out set.

## Artifact locations

- `raw/`: full original evaluation JSONL logs, ignored by Git and backed up separately.
- `summaries/runs.json`: tracked metadata/checksum index generated when completed runs are registered.
- `summaries/`: reviewed tables, plots, and analysis notes with references to the source runs.
- [Interpretation](../interpretation.md): empirical conclusions, uncertainty, limitations, and decisions.

Register an existing completed evaluation file without rerunning inference:

```sh
python3 -m scripts.register_results /path/to/evaluation.jsonl --stage results
```

For future collection, `python3 -m experiments.communication_pilot.run --stage results` saves new generations here by default. Supply all agreed model, question-count, seed, agent, and sampling settings from the [protocol](../protocol.md). An explicit `--output` overrides the default location.

## Comparisons

Compare the six methods within each model using the same questions and initial panel. Compare models only after verifying the full task objects match (the index records `question_set_sha256`) and other settings are aligned. Report question counts, agents per question, repeated runs, invalid answers, and cost alongside accuracy. Registered indexes provide combined panel accuracies; substantive analysis should also separate task families and include G/H and evidence probability errors.

There are no imported evaluation results in this checkout yet. No ranking of the three Qwen models is asserted here. Add findings only with links to registered original artifacts and their checksums.

Files with identical source checksums are copies, not independent repeats. A protocol checksum identifies the protocol text; retain the matching Git code revision alongside collection notes to reconstruct the exact prompt implementation.
