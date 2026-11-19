# Repository layout and command paths

The completed study is documented in [the results report](FULL_STUDY_RESULTS_V2.md). Its experimental source and configuration remain frozen. Repository organization moves maintenance and unused legacy modules, without moving raw results or changing existing archive bytes.

| Location | Purpose |
| --- | --- |
| `experiments/full_study_v2/` | Completed five-agent study protocol, runner, progress/ETA and analysis |
| `experiments/architecture_pilots/` | Five-agent/all-peer and ten-agent/sparse-peer development experiments |
| `experiments/confirmation_pilot/` | Prospective development voting/stopping confirmation |
| `experiments/offline_policies/` | Saved-trace voting/stopping replay |
| `experiments/communication_pilot/` | Communication/self-revision pilot and versioned recovery |
| `experiments/baseline/` | Historical single-agent baseline wrapper |
| `experiments/full_study_v1/` | Superseded ten-agent study and its self-revision, scheduling and analysis dependencies |
| `tools/` | Model setup, checkout maintenance and archive verification |
| `config/` | Versioned task banks, profiles and experiment definitions |
| `docs/` | Current results/methods, design comparison and historical guides |
| `results/` | Operational evidence at its original provenance paths; most raw runs are ignored by Git |
| `archive/` | Versioned immutable evidence/source snapshots and model metadata; large model blobs remain local |
| `tests/` | Offline protocol, calculator, journal, analysis and provenance tests |

## Relocated Python modules

| Former root path | Current path | Invocation from repository root |
| --- | --- | --- |
| `archive_project_history.py` | `tools/archive_project_history.py` | `python -m tools.archive_project_history --check` |
| `setup_models.py` | `tools/setup_models.py` | `python -m tools.setup_models --check` |
| `fix_windows_checkout.py` | `tools/fix_windows_checkout.py` | `python -m tools.fix_windows_checkout --check` |
| `run_baseline.py` | `experiments/baseline/runner.py` | `python -m experiments.baseline.runner --dry-run` |
| `run_self_revision.py` | `experiments/full_study_v1/run_self_revision.py` | `python -m experiments.full_study_v1.run_self_revision --help` |
| `study_trajectory.py` | `experiments/full_study_v1/study_trajectory.py` | Library used by v1 runner |
| `full_experiment_analysis.py` | `experiments/full_study_v1/full_experiment_analysis.py` | Library used by v1 runner |

Use module invocation rather than running nested files by filename, so imports resolve from the repository root. The superseded full runner remains available as `python -m experiments.full_study_v1.runner --help`; it is historical compatibility code, not the selected current procedure. Historical guide/source copies inside `archive/` describe the paths that existed when those experiments ran.

## Why some Python files still remain at the root

Seven modules were relocated, reducing the root count from 27 to 20. Nineteen remaining modules are bound to completed runs' recorded source hashes and original paths; `multi_agent_llm.py` remains an import dependency of frozen code. They form the existing compatibility surface:

- Calculator and shared protocol/runtime: `calculator.py`, `calculator_protocol.py`, `experiment_config.py`, `experiment_runtime.py`, `local_llm.py`, `multi_agent_protocol.py`, `multi_agent_analysis.py`, `multi_agent_llm.py`.
- Frozen task builders: `build_full_benchmark.py`, `build_format_followup_tasks.py`.
- Frozen entry points: `run_multi_agent.py`, `run_followup_pilot.py`, `run_format_followup.py`, `run_communication_pilot.py`, `run_communication_recovery.py`, `run_offline_comparison.py`, `run_confirmation_pilot.py`, `run_five_agent_pilot.py`, `run_sparse_peer_pilot.py`, `run_full_experiment.py`.

The existing PowerShell launchers remain unchanged. For example, completion verification is still:

```powershell
Set-Location D:\ML1-project
.\run_full_experiment.ps1 -AnalyzeRun results/full-experiment/study-v2
```

Moving or rewriting the remaining files would break the existing canonical replay checks, even if a copy survived elsewhere. A future deeper migration needs explicitly versioned source-path relocation support and cross-platform replay validation. Keeping these paths avoids introducing that machinery merely for cosmetic cleanup. New modules should live in the relevant `experiments/` package or `tools/`.

Ordinary offline tests continue to run from the root:

```powershell
py -3 -B -m unittest discover -s tests -q
py -3 -m tools.archive_project_history --check
```
