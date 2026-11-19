# Versioned active experiments

The current prepared analysis is [offline_policies/](offline_policies/), launched with `run_offline_comparison.ps1`. It reuses the completed recovery traces to compare three voters, two stopping rules, and fixed-round controls, with no model calls or automatic policy selection. [Offline comparison guide](../docs/OFFLINE_POLICY_COMPARISON.md)

The current runnable continuation is [communication_pilot/recovery.py](communication_pilot/recovery.py), configured by [communication_recovery.json](../config/communication_recovery.json) and launched through `run_communication_recovery.ps1` or `run_communication_recovery.py` at the repository root. It records an explicit output-truncation failure-policy amendment, preserves the failed v1 unchanged, and reuses all 146 existing revisions before making 334 new requests. [Recovery guide](../docs/COMMUNICATION_RECOVERY.md)

Its protocol, runner, and analysis live together here. Shared calculator/validation dependencies remain at the root. Earlier root runners are retained at their provenance-pinned paths so completed runs remain auditable; the [experiment catalog](../docs/EXPERIMENT_CATALOG.md) distinguishes completed, selected, rejected, and prepared designs.

Immutable source/evidence snapshots live in [archive/](../archive/README.md). New generation evidence belongs under [results/](../results/README.md). No archived runner is the default entry point for a new experiment.
