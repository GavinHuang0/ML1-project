# Multiple-choice results

This namespace contains the separate `mc-exact-v1` answer-selection experiment. Its first sixteen-call run completed on November 7, 2026: **1/16 correct (6.25%)**, with fifteen valid choices and one truncated algebra response. The [design](../../docs/MULTIPLE_CHOICE_EXPERIMENT.md) and [question bank](../../docs/MULTIPLE_CHOICE_QUESTION_BANK.md) document the frozen prompt, sixteen reused questions, fifteen exact-fraction options per question, and exact-choice scoring.

```sh
python3 run_multiple_choice_experiment.py --dry-run
python3 run_multiple_choice_experiment.py
```

Run these commands from the repository root. Each execution creates a unique `<UTC>-mc-exact-v1/` directory here, containing a manifest, raw answers, and a summary after completion. Check the manifest status, sixteen answers, and final completion marker before interpreting a run as complete. A failed or interrupted run retains its partial records. Offline fixture results belong in temporary test directories and are not model results.

New run directories remain ignored until reviewed and deliberately selected for versioning. Previous unassisted and calculator artifacts stay in `results/runs/`; their original scoring is unchanged. Do not combine exact-choice scores with posterior-tolerance results under a shared headline accuracy.

## Reviewed first run

The [results and manual interpretation](../../docs/MULTIPLE_CHOICE_EXPERIMENT.md#results-on-november-7-2026) distinguish arithmetic, probability setup, value-to-option matching, and response delivery failures. Several outputs derive a correct number and then select a different value's letter. No answer was repaired or retried, and earlier calculator scores remain unchanged.

| Artifact | File |
| --- | --- |
| Provenance and frozen configuration | [Manifest](20261107T195716817040Z-mc-exact-v1/run-manifest.json) |
| Original model responses and scores | [Raw answers](20261107T195716817040Z-mc-exact-v1/answers.jsonl) |
| Family/cohort results and budget | [Summary](20261107T195716817040Z-mc-exact-v1/summary.json) |
| Reproduced scores, hashes, and manual review | [Verification](20261107T195716817040Z-mc-exact-v1/verification.json) |
