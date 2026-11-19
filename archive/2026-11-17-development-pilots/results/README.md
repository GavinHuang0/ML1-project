# Experiment results

The next development pilot uses `run_followup_pilot.py` and `results/followup-pilot/<run>/`. It compares JSON versus constrained schema on eight questions (160 calls), writes a screening `summary.json`, and supports pause/resume without repeating durable completed calls. [Windows guide](../docs/WINDOWS_RUN_GUIDE.md) · [Pilot design](../docs/FOLLOWUP_PILOT.md)

The prepared full study uses `run_full_experiment.py` and `results/full-experiment/<study>/`. Its study manifest indexes question/condition journals, shared initial evidence, development calibration, validation selection, and per-phase reports. Explicit `--resume` audits saved prefixes and continues at the pending model call; returned raw responses can be recovered without inference. Human pause time is excluded and uncertain failed-call costs remain explicitly recorded. Launch this study only after reviewing the development pilots. See the [full design](../docs/FULL_EXPERIMENT.md).

New multi-agent runs use `run_multi_agent.py` and unique directories under `results/multi-agent/`. The default four-question inspected development pilot requires 160 calls. Raw generations, evaluated answers, round summaries, manifests, and complete-run analysis/calibration artifacts stay local and ignored until deliberately selected for versioning. See the [frozen protocol](../docs/MULTI_AGENT_PROTOCOL.md) for the schema and development → validation → test workflow.

Single-agent control runs belong under [baseline/](baseline/README.md), using the original `calculator-baseline-v1` entry point. See the [README](../README.md) for its procedure.

The [historical reference selection](baseline/HISTORICAL_REFERENCE.json) reports the preserved original-prompt condition: 7/16 correct and 11/16 executable. It is explicitly not a new inference run. No real-model run of the reorganized wrapper has been made during the November 9 consolidation.

All previous raw runs, manifests, summaries, checks, and interpretations are preserved in [the November 9 archive](../archive/2026-11-09-pilots/README.md). Earlier Qwen/Llama artifacts remain in [the October 24 archive](../archive/2026-10-24-legacy/README.md). Their original bytes, protocols, paths inside provenance metadata, and scores are unchanged.
