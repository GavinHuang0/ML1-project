# Completed communication recovery preserved on November 17, 2026

This immutable snapshot contains **33 files totaling 6,687,905 bytes**: all five completed-run evidence files and every one of the 28 source/configuration files named in the manifest's frozen `source_sha256`. Source and copied bytes were SHA256-checked before and after copying. Original operational paths, source files, responses, and scores remain unchanged. The [inventory](SHA256_INVENTORY.json) maps original paths to archived paths.

| Preserved evidence | State |
| --- | --- |
| [Initial panel](results/communication-pilot/windows-v2/initial_panel.jsonl) | 80 original strict-schema screening responses, shared identically by both branches |
| [Raw generations](results/communication-pilot/windows-v2/generations.jsonl) | All 480 revision responses, including the original truncated response |
| [Evaluated answers](results/communication-pilot/windows-v2/answers.jsonl) | All 480 outcomes, with the truncated response counted as one ineligible invalid-JSON answer |
| [Manifest](results/communication-pilot/windows-v2/run-manifest.json) | Complete; original format-pilot parent, failed v1 source prefix, generation protocol, explicit policy amendment, source hashes and checkpoint hashes retained |
| [Summary](results/communication-pilot/windows-v2/summary.json) | Round/family trajectories, prespecified round-3 comparison, paired group uncertainty, failure/revision/consensus diagnostics, and historical versus new cost accounting |
| [Recovery code](experiments/communication_pilot/) and [configuration](config/communication_recovery.json) | Exact versioned implementation used by the completed continuation, alongside its original frozen dependencies |

V1 stopped after generating 146 revision responses and evaluating 145 because one explanation repeated until the 1024-token output cap, leaving unfinished JSON and no expression. This continuation preserved every earlier raw response and evaluation, evaluated that one response locally as ineligible, and generated **334 additional responses**. Its model requests, sampling, prompts, schema, seeds, calculator, and exact scoring were unchanged. It is an explicit **post-failure policy amendment**, not a completed run under v1's original fatal-schema-stop policy. No response was repaired or regenerated.

There are **480 total revision generations**, plus the 80 shared initial generations: **560 unique generations across the source and continuation**. Historical imported costs are counted rather than erased. The one output truncation was inherited from v1; no new truncation occurred in the 334-call continuation.

| Round | Communication correct questions | Self-revision correct questions |
| --- | ---: | ---: |
| 0 | 4/8 | 4/8 |
| 1 | 5/8 | 4/8 |
| 2 | 4/8 | 4/8 |
| 3, prespecified primary | 4/8 | 5/8 |

The primary collective-accuracy difference, communication minus self-revision, is −12.5 percentage points with a paired eight-group bootstrap interval of [−25, 0]. Communication used 385,309 revision tokens versus 125,639 for self-revision (about 3.07 times as many). These inspected development questions do not establish general accuracy or select an optimal global round; the descriptive round-1 result must not replace the frozen primary comparison. [Full interpretation](../../docs/COMMUNICATION_RESULTS_V2.md)

The [failed v1 archive](../2026-11-17-communication-pilot-v1-failed/README.md) remains separate and unchanged. The [format-pilot archive](../2026-11-17-development-pilots/README.md) preserves the selected initial panel's original experiment. Their raw data are not recursively duplicated here; provenance strings and recorded parent hashes remain intact. The model backup remains separate and unchanged.

The operational original directory remains in place because replay checks bind absolute configuration, parent, and source paths. Use its audited analyzer for full replay; this archive is a byte-preserved evidence backup, not a silently path-relocated run. The generated README and inventory are archive documentation rather than entries in the 33-file snapshot. Verify archived bytes with the root `archive_project_history.py --check`.
