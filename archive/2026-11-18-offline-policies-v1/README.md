# Completed offline policy comparison preserved on November 18, 2026

This immutable snapshot contains **12 original files totaling 1,513,331 bytes**: all four completed-run reports and the eight analysis/configuration files named by the manifest's frozen `source_sha256`. Every original and copied file was SHA256-checked before and after copying. Operational source paths, report bytes, and prior raw evidence remain unchanged. The [inventory](SHA256_INVENTORY.json) maps each original path to its archived copy and records 41 transitive input references to existing archives.

| Preserved artifact | Scope |
| --- | --- |
| [Summary](results/offline-comparison/pilot-v1/summary.json) | Complete policy results, observed prefixes, paired contrasts, costs, and uncertainty on eight inspected development groups |
| [Comparison table](results/offline-comparison/pilot-v1/comparisons.csv) | 36 rows: three voters × six stopping/control policies × two branches |
| [Question decisions](results/offline-comparison/pilot-v1/per_question.csv) | All 288 terminal decisions, stopping rounds, and saved-prefix costs |
| [Manifest](results/offline-comparison/pilot-v1/run-manifest.json) | Complete status, frozen definitions/configuration/source hashes, transitive input hashes, report hashes, and zero additional model calls |
| [Analysis package](experiments/offline_policies/), [configuration](config/offline_policy_comparison.json), and launchers | The exact source/configuration bytes used to generate the reports |

The three voters are defined over eligible exact-rational answers. `plurality` selects the unique largest current-round count; ties abstain. `initial_anchored` adds initial-panel votes to current-panel votes, counting round zero once when evaluating round zero. `agent_history` gives each agent total weight one, divided equally over that agent's distinct eligible answers observed from round zero through the current round. Every voter abstains on an exact score tie.

`high_agreement_8` stops at the first completed round from zero through three when the selected voter has a unique answer supported by at least eight of the original ten current agents. `stable_majority_6` stops at the first round of at least one where the selected voter returns the same unique answer in two consecutive rounds and at least six of the original ten current agents support it in each round. Both fall back to the selected voter at round three. Four fixed-round controls stop after rounds zero, one, two, or three. Agreement counts actual current agents, never weighted voter scores or a reduced eligible denominator. Reference answers are used only to score completed decisions.

This is **post-hoc exploratory replay of eight already inspected development groups**. It generated **zero additional model responses**, performed no policy selection, and established no confirmed winner. Reported savings are counterfactual costs of prefixes within existing traces; no new inference savings or online stopping behavior were measured. The three voters and two adaptive stopping rules remain candidates for fresh confirmation. See the [result interpretation](../../docs/OFFLINE_POLICY_RESULTS_V1.md) and [frozen comparison guide](../../docs/OFFLINE_POLICY_COMPARISON.md).

The [completed recovery archive](../2026-11-17-communication-recovery-v2/README.md), [failed-prefix archive](../2026-11-17-communication-pilot-v1-failed/README.md), and [format-pilot archive](../2026-11-17-development-pilots/README.md) already preserve all 41 transitive inputs referenced by this manifest. Their files were verified against the manifest's recorded hashes and are not recursively duplicated here. The separate model backup remains unchanged.

The original operational directory remains in place because replay audits bind its absolute source and input paths. Use the operational analyzer for canonical replay; this snapshot preserves bytes without silently relocating run provenance. The generated README and inventory are archive documentation and are excluded from the 12-file count. Verify all six dated snapshots and the local model backup with the read-only root command `archive_project_history.py --check`.
