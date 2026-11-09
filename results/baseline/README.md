# Calculator-baseline records

This is the sole active result namespace. From the repository root:

```sh
python3 run_baseline.py --dry-run
python3 run_baseline.py
```

Each real execution creates a new `<UTC>-calculator-baseline-v1/` directory with `answers.jsonl`, `summary.json`, and `run-manifest.json`. A complete run has sixteen answers, a completion marker, and manifest status `complete`; partial data remains available after failures or interruptions. New run directories stay local until reviewed and deliberately selected for versioning.

[HISTORICAL_REFERENCE.json](HISTORICAL_REFERENCE.json) selects the original-prompt records from the archived November 6 comparison. Its 7/16 correct and 11/16 executable results are historical evidence, not a new run of this wrapper. The [selection report](../../docs/BASELINE_RESULTS.md) explains the mapping, scoring, and limitations. No real-model generation was performed during consolidation.
