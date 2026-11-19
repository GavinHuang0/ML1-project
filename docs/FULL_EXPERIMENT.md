# Five-agent full study: selected profile, validation selection and ETA

**Completed and independently audited on November 19, 2026:** all 3,500 calls and phase reports reproduce, with no pending recovery. Validation selected R0 before test; the locked initial-panel policy scores 12/40 (30%). Later-round comparisons are secondary. Read the [results and interpretation](FULL_STUDY_RESULTS_V2.md). Use the audit command at the end for the completed default directory; the creation commands below document the frozen procedure.

The full-study runner is **ml1-five-agent-full-study-v2**. It compares five agents with all four peers against matched five-agent self-revision, using the selected original calculator instruction and strict JSON schema. This version replaced the root command's older plain-JSON study and has now completed all phases. Its code, configuration and saved evidence remain frozen.

The previous implementation remains available in [experiments/full_study_v1/runner.py](../experiments/full_study_v1/runner.py), with its original [configuration](../config/full_experiment.json), [design guide](FULL_EXPERIMENT_V1.md), historical tests and byte-preserved source in the existing archives. Completed pilots, their scores and immutable evidence remain unchanged. [Why five agents were chosen](ARCHITECTURE_RESULTS_V1.md)

## Run in PowerShell

With Ollama running and the selected `llama3.2:3b` installed, execute all phases in order:

```powershell
Set-Location D:\ML1-project
.\run_full_experiment.ps1 -Phase all
```

The default new directory is `results/full-experiment/study-v2`. It must not already exist for a new study. The launcher finds Python 3.10+ automatically and requires only the standard library. Pass `-Python C:\path\to\python.exe` when needed; `-Timeout` sets a single model request's timeout, default 600 seconds.

To preview the plan without inference:

```powershell
.\run_full_experiment.ps1 -Phase all -DryRun
```

The default command runs development only. A staged workflow, allowing inspection between completed phases, is:

```powershell
.\run_full_experiment.ps1
.\run_full_experiment.ps1 -Phase validation -Resume
.\run_full_experiment.ps1 -Phase test -Resume
```

`-Phase all` performs the same ordered dependencies automatically. Validation cannot start until development and calibration are complete; test cannot start until validation has produced a frozen selection. Progression depends on technical completeness, intact provenance and usable cost measurements, not on communication outperforming self-revision.

## Full question list and budgets

Inspect [all 100 questions](FULL_STUDY_QUESTIONS.md), or the [question-only JSON export](FULL_STUDY_QUESTIONS.json). Prompts reproduce [config/full_benchmark.json](../config/full_benchmark.json) verbatim, with references and generator parameters omitted from the inspection exports. The exact reference answers remain local for scoring and never enter model requests.

| Partition | Questions | Structural groups | New model calls |
| --- | ---: | ---: | ---: |
| Development/calibration | 20 | 12 | 700 |
| Validation | 40 | 20 | 1,400 |
| Held-out test | 40 | 20 | 1,400 |
| Total | 100 | 52 | **3,500** |

The bank is balanced across reasoning/urn probability, sensor evidence, algebra and units/rates. Structural groups are disjoint across partitions; numerical variants stay together. Development cases have already informed pilots. Validation/test model outcomes remain unobserved before their stages. The new study generates **all 3,500 calls freshly**, using its own frozen seed namespace; it does not import the earlier 420-call pilot. This provides consistent protocol and timing calibration for the complete development partition.

Each question costs thirty-five unique calls: five shared initial generations, then fifteen communication and fifteen self-revision calls. Each branch represents twenty-generation trajectories. Shared initialization counts once in physical expenditure and once within each logical branch cost.

## Frozen generation and scoring

| Component | Full-study v2 procedure |
| --- | --- |
| Panel | Five separate seeded trajectories of the same `llama3.2:3b` model; no weight training |
| Model settings | Temperature 0.7, output cap 1024, context 16384, `keep_alive=0` |
| Initial panel | Five fresh original-prompt responses per question, shared exactly across branches |
| Communication | Original question, own preceding response, and all four anonymously ordered peers' preceding responses |
| Self-revision | Original question and own preceding response only |
| Revision instruction | Identical generic reconsideration instruction in both branches |
| History and scheduling | Completed immediately preceding branch round only; paired alternating synchronous updates |
| Delivery | Selected strict schema for explanation and expression; explanation limit remains a prompt instruction |
| Calculation | Execute the explicit expression once using bounded exact-rational arithmetic; probability range gate |
| Collective decision | Unique eligible exact-rational current-round plurality; ties/no eligible votes abstain |
| Scoring | Exact equality; abstention counts incorrect; explanation correctness is not automatically graded |
| Rounds | Record all R0–R3 trajectories; no adaptive consensus stopping |

Both branches use matching seeds for corresponding question/round/agent positions. References, correctness feedback, collective winners and future rounds are never supplied to the model. Generation counts match, but tokens/time do not have to match. An equal-token-budget independent-sampling comparison remains outside this design.

A proven output-cap invalid-JSON response is one ineligible answer, without repair or regeneration. Admission requires the valid unsaturated wrapper, `done_reason="length"`, exactly 1024 generated tokens and invalid JSON syntax. Other schema violations preserve raw evidence and stop the run. Calculator rejection and out-of-range probabilities remain ineligible. No response is extracted from explanation text or silently repaired.

The source/configuration hashes, deterministic benchmark references, model digest, Ollama version and driver-621.24 hardware environment are bound. Source, model, runtime, routes and environment drift are rejected on resume. The selected profile retains the currently tested immediately preceding-round history; the [conversation-history idea](DEFERRED_CONVERSATION_HISTORY.md) remains deferred.

## Calibration and validation selection

Version 2 explicitly changes the old design's timing scope from full-round wall time to **summed model-request seconds**, measured consistently for every new generation. Request time includes loading, but excludes health checks, prompt construction, calculator evaluation, journaling and other process overhead. It is not total study wall time, an API price, or a counterfactual deployment latency benchmark. The timing amendment is frozen before validation and applies to both branches.

Development communication R1 defines positive family-balanced revision-token and revision-request-time references. Initialization is excluded from the selection penalty, while initial and total costs remain reported separately. On validation, evaluate each global communication round R0–R3 with:

```text
objective(R) = 1 - family_balanced_communication_accuracy(R)
             + 0.02 * [0.5 * normalized_revision_tokens(R)
                       + 0.5 * normalized_revision_request_seconds(R)]
```

Normalization uses the frozen development R1 references. R0 has zero revision cost. Objective ties prefer the fewer-round endpoint. Freeze one selected round before test and compare both branches at that same round. Neither the control's best test round nor a promising test subgroup changes the primary selection. Alternative curves remain descriptive; no test result retunes the architecture, objective or scorer.

Whole structural groups are resampled within family strata, with all variants carried together. The same 2,000 paired draws are used across branches/rounds. Test uncertainty has twenty clusters, not forty independent questions or hundreds of independent agent outputs. The reports include coverage, delivered errors, eligibility/failures, individual versus collective accuracy, correct-minority losses/adoptions, tokens, request/loading time and group/family behavior alongside the primary contrast.

## Progress bar, estimated remaining time and pausing

The terminal shows an ASCII progress bar, completed/planned calls and estimated time remaining for the active phase. Estimates learn separate rates for initialization, communication and self-revision, accounting for the remaining mix of call types. ETA begins unknown until enough calls have returned and can change with question difficulty, response length or loading. On resume, saved per-call durations initialize the estimate; human pause hours are not treated as generation time. Noninteractive output uses readable lines instead of assuming a terminal supports in-place updates.

To pause, press **Ctrl+C once**, then wait for the active reply to be saved and for the runner to report `paused`. A second Ctrl+C forces interruption and can lose an in-flight response. Durable returned replies are audited and evaluated locally without regeneration.

Resume the same study and phase:

```powershell
.\run_full_experiment.ps1 -Phase all -Resume
```

For a staged run, substitute the intended `-Phase development`, `validation` or `test`. For a custom `-OutputDir`, repeat that same path. To request a pause from another terminal:

```powershell
.\run_full_experiment.ps1 -Pause
```

A completed phase is reused on resume rather than regenerated. Failed calls without a durable returned reply require an explicit resume; there are no automatic model retries.

The 3,500-call budget and token/request-time summaries count durable returned generations. A failed request with no saved reply can consume unmeasured server work; its token use cannot be reconstructed. Failure segments and the active position remain recorded, and these unknown costs are outside the returned-generation selection metric. Report interruptions separately rather than treating saved request time as the complete cost of failed attempts.

## Evidence, artifacts and audit

The root directory contains `study-manifest.json`. Each `phases/development`, `phases/validation` and `phases/test` directory retains its run manifest, raw `generations.jsonl`, evaluated `answers.jsonl`, `summary.json`, `comparisons.csv` and `per_question.csv`. Initial records are tagged `arm="shared_initial"`.

`artifacts/calibration.json` binds development evidence and positive normalization references. `artifacts/selection.json` binds validation evidence, calibration identity, all four objective values and the chosen global round. The test report identifies the primary comparison at that frozen round. Preserve the complete study folder in place, because provenance binds original paths.

Audit saved evidence and deterministic reports without contacting Ollama:

```powershell
.\run_full_experiment.ps1 -AnalyzeRun results/full-experiment/study-v2
```

Completed phases, their source/configuration snapshots and artifacts must reproduce. Earlier archived experiments and original scores remain intact; new full-study outputs stay under the operational results namespace until deliberately archived.

Implementation: [runner](../experiments/full_study_v2/runner.py), [protocol](../experiments/full_study_v2/protocol.py), [analysis](../experiments/full_study_v2/analysis.py), [progress estimates](../experiments/full_study_v2/progress.py), and [configuration](../config/full_study_v2.json).
