# Experiment and model archives

The most recent completed experiment is the [five-agent full study v2](../docs/FULL_STUDY_RESULTS_V2.md): 3,500 fresh generations over development, validation and test. Validation selected round 0 before test inference. The [architecture pilots](../docs/ARCHITECTURE_RESULTS_V1.md), [twelve-question confirmation](../docs/CONFIRMATION_RESULTS_V1.md), earlier [offline voting/stopping comparison](../docs/OFFLINE_POLICY_RESULTS_V1.md), and [communication-pilot recovery](../docs/COMMUNICATION_RESULTS_V2.md) remain preserved separately. Historical results retain their original scoring rules and original bytes. See the [experiment catalog](../docs/EXPERIMENT_CATALOG.md) and [model registry](../docs/MODEL_REGISTRY.md) for decisions and evidence.

| Archive | Contents |
| --- | --- |
| [2026-10-24 legacy](2026-10-24-legacy/README.md) | Completed Qwen and Llama probability, checking, and diagnostic runs under historical scoring; 39 preserved files |
| [2026-11-09 pilots](2026-11-09-pilots/README.md) | Posterior-scored unassisted, bounded-template, calculator, syntax-instruction, and multiple-choice experiments; 74 preserved files |
| [2026-11-17 development pilots](2026-11-17-development-pilots/README.md) | Both completed Windows format pilots, raw evidence and a pre-Stage-B source/configuration/test/report snapshot; 69 preserved files |
| [2026-11-17 failed communication v1](2026-11-17-communication-pilot-v1-failed/README.md) | All 146 raw responses, 145 evaluated answers, 80 initial records, failure manifest and its exact frozen source/configuration files |
| [2026-11-17 completed recovery v2](2026-11-17-communication-recovery-v2/README.md) | All 480 revision responses and evaluations, shared initial panel, completed summary/manifest and exact frozen sources; 33 preserved files |
| [2026-11-18 offline policies v1](2026-11-18-offline-policies-v1/README.md) | Completed 36-row comparison and 288 question decisions, summary/manifest and all eight frozen analysis/configuration files; 12 preserved files, no new inference or selected winner |
| [2026-11-18 confirmation pilot v1](2026-11-18-confirmation-pilot-v1/README.md) | All 840 raw/evaluated responses, completed reports/manifest and nine new frozen source/config files; 15 preserved originals, with 34 existing archive references covering all 43 frozen inputs |
| [2026-11-18 architecture pilots v1](2026-11-18-architecture-pilots-v1/README.md) | Both completed architecture runs: 1,260 generations, twelve raw/report/manifest files and ten new frozen source/config/launcher files; 22 preserved originals, with 42 verified archive references covering all 52 frozen inputs |
| [2026-11-19 full study v2](2026-11-19-full-study-v2/README.md) | Completed 3,500-call development/validation/test study, frozen calibration and round selection, raw/evaluated evidence and reports; 29 preserved originals, with 41 verified references covering all 49 frozen inputs |
| [Model artifacts](model-artifacts/README.md) | Tested-model registry, exact available Llama manifest, and a separate local backup of its seven content-addressed blobs |

Earlier snapshots are unchanged. New snapshots copy completed evidence rather than moving it: their manifests contain absolute source/result paths, and Stage B imports the selected initial panel from its original location. Root compatibility sources therefore remain available for audit; they are not current recommended experiment commands. No score or model output was repaired during archiving. The offline snapshot references its already archived recovery, failed-prefix, and format inputs rather than recursively duplicating their raw evidence or the separate model backup.

Verify all nine snapshots and the local model backup without inference, downloads, or writes:

```powershell
py -3 -B archive_project_history.py --check
```

Use the same working Python interpreter selected by the pilot launcher if `py -3` is unavailable. Large model blobs are local, ignored by Git, and absent from an ordinary clone. The verifier reports their absence rather than claiming a complete backup. Manifests, checksums, metadata, historical source and raw results are versionable. The archive is not a substitute for an external backup of the working folder and local model artifacts.
