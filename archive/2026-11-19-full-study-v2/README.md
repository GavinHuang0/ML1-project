# Completed full-study v2 preserved on November 19, 2026

This immutable snapshot preserves **29 original files totaling 36,486,082 bytes**: the completed study manifest, both frozen selection/calibration artifacts, eighteen phase evidence/report files, and eight new frozen v2 source/configuration/launcher files. Every original and copy was SHA256-checked before and after copying. Operational paths, raw model replies, evaluations and earlier archives remain unchanged.

The [inventory](SHA256_INVENTORY.json) maps every one of the study's **49 frozen source/input files**. Eight new files are copied here, while **41 byte-identical dependencies** reference verified earlier archives. This includes the earlier versioned identity manifest and inventory; their historical absolute path fields are preserved as data rather than rewritten. Model weights and earlier raw evidence are not duplicated.

| Preserved evidence | Scope |
| --- | --- |
| [Study manifest](results/full-experiment/study-v2/study-manifest.json) | Complete status, 3,500 durable generations/evaluations, immutable study protocol and phase bindings |
| [Development](results/full-experiment/study-v2/phases/development/summary.json) | Twenty inspected development cases, twelve groups, 700 calls; raw and evaluated journals plus all three reports and the phase manifest |
| [Validation](results/full-experiment/study-v2/phases/validation/summary.json) | Forty validation cases, twenty groups, 1,400 calls; complete raw/evaluated evidence and reports |
| [Test](results/full-experiment/study-v2/phases/test/summary.json) | Forty held-out test cases, twenty groups, 1,400 calls; complete raw/evaluated evidence and reports at the locked primary round |
| [Calibration](results/full-experiment/study-v2/artifacts/calibration.json) | Positive development R1 communication revision-token/request-time normalization references, bound to the development report |
| [Selection](results/full-experiment/study-v2/artifacts/selection.json) | All four validation objectives, development calibration identity and **primary round 0**, frozen before test inference |
| [New full-study implementation](experiments/full_study_v2/), [configuration](config/full_study_v2.json), and root launchers | Exact v2 bytes used for generation, progress/ETA, phase gating, analysis and selection |

The operational read-only replay audit passed: all **3,500 raw generations and evaluated answers**, canonical prompts, paired seeds, four-peer routing, source/input identities, phase dependencies and deterministic report bytes reproduce. All three phases completed, with no pending artifact recovery. Audit adds zero model generations. Initialization counts once in physical cost: **500 initial generations and 3,000 revisions**.

Five agents use the selected original calculator instruction and strict schema. Communication receives all four peers' completed immediately preceding response snapshots; self-revision receives its own preceding response only. The branches share each initial panel exactly and use matched seeds with paired synchronous scheduling. Exact-rational plurality abstains on ties, and exact scoring is unchanged. The model/runtime/hardware baseline remains pinned, including driver 621.24. No response or expression was repaired during archiving.

Development supplies cost calibration. Validation selects one global round using the frozen accuracy/cost objective; test does not select or retune it. The selected round is **R0**, so the primary test comparison uses the same initial records in both branches: **12/40 correct each**. This structural equality is not evidence that later communication and self-revision are generally equivalent. The complete R1–R3 curves remain available as secondary results. See the [full interpretation](../../docs/FULL_STUDY_RESULTS_V2.md) and [preserved procedure](../../docs/FULL_EXPERIMENT.md).

This is the completed 100-question study, with twenty development, forty validation and forty test cases across 52 disjoint structural groups. Development definitions were inspected in earlier work; validation/test generation belongs to this full study rather than the preceding pilots. One seed panel per question and related numerical variants remain explicit limits on inference.

Runtime lock files are excluded because they are not model evidence. This generated README and inventory are excluded from the 29-original-file count. Use the operational analyzer for canonical replay; saved manifests bind their original paths. The read-only root command `archive_project_history.py --check` verifies all nine dated snapshots, referenced preserved inputs and the separate local model backup.
