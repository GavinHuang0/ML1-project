# ML1 Project: communication versus self-revision

Does access to peers improve a multi-agent LLM system beyond giving each agent another attempt, and enough to justify the extra tokens and time?

The latest completed experiment is the **100-question five-agent full study**, comparing communication with all four peers against matched self-revision. It uses the selected **original calculator instruction + strict JSON schema**, shared initial panels and full round-0-through-3 trajectories. The underlying model is `llama3.2:3b`; no weights are trained or changed.

**Completed result:** validation selected **R0, no revision**, under the frozen accuracy/cost objective. That policy solves **12/40 held-out test questions (30%)**. Its two branch labels are identical by shared initialization. Secondary R3 gives communication 14/40 versus self-revision 10/40, an uncertain +10-point difference with interval [−2.5, +22.5]. The result does not establish that communication is always better or worse. [Full verification and interpretation](docs/FULL_STUDY_RESULTS_V2.md)

[Original-design comparison, completed work and follow-up priorities](docs/DESIGN_RECONCILIATION.md) · [Repository layout and relocated commands](docs/REPOSITORY_LAYOUT.md)

## Verify the completed five-agent full study

All **3,500 calls** are saved and audited: 700 development, 1,400 validation and 1,400 test. Canonical prompts, raw evaluations, source identities, frozen phase dependencies and report bytes reproduce. No recovery is pending. The complete run took about 2h42m elapsed and used 2,638,253 tokens.

```powershell
Set-Location D:\ML1-project
.\run_full_experiment.ps1 -AnalyzeRun results/full-experiment/study-v2
```

The audit is read-only and needs no Ollama service. The evidence remains in `results/full-experiment/study-v2` with an [immutable archive](archive/2026-11-19-full-study-v2/README.md). [All 100 questions](docs/FULL_STUDY_QUESTIONS.md), [question-only JSON](docs/FULL_STUDY_QUESTIONS.json), and the [frozen procedure](docs/FULL_EXPERIMENT.md) remain available. The experiment needs no further inference; test outcomes must not retune its selected endpoint.

Version 2 calibrated revision cost using summed model-request seconds instead of the old full-round wall-time scope. It imported no pilot answers. The original ten-agent runner/configuration are preserved as [v1 compatibility code](experiments/full_study_v1/runner.py) and [historical design](docs/FULL_EXPERIMENT_V1.md); earlier results and their archives remain unchanged.

## Inspect the completed architecture pilots

Both runs are complete and audited: **420** five-agent generations and **840** sparse ten-agent generations, with eight branch/round summaries and 96 question rows each. The actual common initialization and self-revision outputs match across runs. No offline subset screen preceded inference. Evidence and frozen sources are archived.

Reproduce either read-only audit without Ollama:

```powershell
Set-Location D:\ML1-project
.\run_five_agent_pilot.ps1 -AnalyzeRun results/five-agent-pilot/windows-v1
```

```powershell
.\run_sparse_peer_pilot.ps1 -AnalyzeRun results/sparse-peer-pilot/windows-v1
```

For the sparse condition, each receiving agent samples two distinct peers uniformly from the other nine for each question and round. Seeds and peer IDs are recorded; pairs are re-sampled each round, with repeats across rounds allowed. [Frozen procedures and routing policy](docs/ARCHITECTURE_PILOTS.md). The five-agent full-study implementation above incorporates the selected profile and a consistent pre-validation cost calibration.

## Inspect the completed confirmation pilot

The completed **12-question confirmation** uses the selected strict-schema profile and full communication/self-revision trajectories through round 3: **840 unique model calls**, eight structural groups, four newly tested. Plurality gives communication **1/12** versus self-revision **4/12** at R3. Alternative voters show no consistent benefit. High-agreement/stable-majority stopping saves communication 10.92%/4.26% of total tokens, but every early stop is wrong; each final answer matches R3, with no additional observed accuracy loss. Self-revision never stops early. [Results and full-study decision](docs/CONFIRMATION_RESULTS_V1.md)

In PowerShell:

```powershell
Set-Location D:\ML1-project
.\run_confirmation_pilot.ps1 -AnalyzeRun results/confirmation-pilot/windows-v1
```

This read-only audit requires no Ollama service. The default run is complete; no further policy pilot is required. The new full-study runner keeps plurality/global-round selection primary. [Frozen confirmation procedure](docs/CONFIRMATION_PILOT.md)

The initial preflight stopped before inference because the GPU driver changed from 617.42 to 621.24 on the same PC. The [confirmation environment](config/confirmation_environment.json) records this driver-only amendment. Both completed branches share the new pinned baseline; earlier evidence is unchanged.

## Inspect earlier development evidence

The earlier offline comparison covers **three voting rules and two stopping rules**, with fixed-round controls. High-agreement stopping saves about 25–26% of total tokens on those easier traces; stable-majority stopping saves about 17–18%. Both stop only the same three easy questions and preserve round-3 answers. Its recommended confirmation is now complete above. [Earlier results](docs/OFFLINE_POLICY_RESULTS_V1.md)

Reproduce its read-only audit, with no model calls:

```powershell
Set-Location D:\ML1-project
.\run_offline_comparison.ps1 -AnalyzeRun results/offline-comparison/pilot-v1
```

Reports are preserved in `results/offline-comparison/pilot-v1` and a byte-verified archive. [Exact definitions, command options, outputs, and limitations](docs/OFFLINE_POLICY_COMPARISON.md)

Offline reanalysis needs no model service. In PowerShell:

```powershell
Set-Location D:\ML1-project
.\run_communication_recovery.ps1 -AnalyzeRun results/communication-pilot/windows-v2
```

The launcher finds Python 3.10+ automatically. Reanalysis audits the format-pilot parent, original failed-v1 prefix, all 480 revision records and exact scores, and reproduces the saved summary. The completed evidence is under `results/communication-pilot/windows-v2`, with a separate immutable archive. The original v1 stopped on one output-truncated invalid-JSON response; the explicitly amended recovery preserved it as ineligible and generated the remaining 334 responses without replaying the earlier 146.

The selected schema and truncation policy are incorporated in the versioned five-agent full study. The historical v1 implementation retains its plain-JSON profile. A negative communication result remains a legitimate study outcome; do not require a pilot gain or change the questions/scorer to obtain one.

[Original generation design](docs/COMMUNICATION_PILOT.md) · [Current recovery procedure and commands](docs/COMMUNICATION_RECOVERY.md)

## Selected procedure

| Component | Procedure |
| --- | --- |
| Model and sampling | Llama3.2 3B, five separate generations in full-study v2; temperature 0.7, output cap 1024, context 16384, `keep_alive=0` |
| Initial panel | Five fresh responses per question, shared exactly between branches; no pilot outputs are imported into v2 |
| Communication | Each agent sees the question, its own previous response, and all four anonymous peers' previous responses |
| Self-revision | Each agent sees the question and only its own previous response |
| Shared information | Explanation, expression, exact calculator result, and execution status; references and correctness stay local |
| Updates | Both branches use completed preceding-round snapshots; every round through 3 is collected |
| Calculation | Evaluate the explicit expression once with the bounded exact-rational calculator; preserve failures without repair |
| Collective answer | Unique exact-rational plurality among eligible responses; ties/no eligible values abstain and count incorrect |
| Reporting | One validation-selected global round is frozen before test; all round/family curves, paired group intervals, revisions, failures and costs remain reported |

Generation counts match, but peer prompts are longer, so token and time costs are reported separately. Pilots do not choose a validated optimal global round or establish general accuracy. The active full study has 100 questions and 3,500 calls; the earlier ten-agent/7,000-call design remains historical.

## Why this profile

The 320-call format follow-up compared the original prompt with one added expression-completeness instruction, both using the same strict schema. On the eight fresh numerical screening questions, the original prompt produced **79/80 eligible outputs, one division-by-zero rejection, 33/80 individually correct answers, and 4/8 collectively correct questions**. The extra instruction produced 72 eligible outputs, six calculator failures, and the same 4/8 collective accuracy while using about 27% more tokens. The prespecified rule selected `strict_schema`.

The extra instruction helped inspected regression cases but did not transfer reliably to fresh numbers. Those regression outcomes remain descriptive. The schema constrains characters, not complete arithmetic or mathematical correctness. Explanations are not graded, and a wrong executable expression may reflect reasoning, transcription, or explanation-expression inconsistency.

[Format follow-up protocol](docs/FORMAT_FOLLOWUP.md) · [All experiment outcomes](docs/EXPERIMENT_CATALOG.md) · [Tested models and weight availability](docs/MODEL_REGISTRY.md)

## Repository map

| Location | Role |
| --- | --- |
| `run_full_experiment.ps1`, `run_full_experiment.py` | Active five-agent v2 full-study entry points with ETA, pause/resume and phase audit |
| [experiments/full_study_v2/](experiments/full_study_v2/) | Selected-profile protocol, durable three-phase runner, cost selection and paired analysis |
| [docs/FULL_STUDY_QUESTIONS.md](docs/FULL_STUDY_QUESTIONS.md) | All 100 exact question prompts for inspection, without reference answers |
| [experiments/full_study_v1/](experiments/full_study_v1/) | Historical ten-agent runner compatibility; original configuration remains preserved |
| [experiments/baseline/](experiments/baseline/) | Historical single-agent baseline runner, now invoked as `python -m experiments.baseline.runner` |
| [tools/](tools/README.md) | Archive verification, model setup and Windows checkout maintenance; invoke with `python -m tools.<name>` |
| `run_five_agent_pilot.ps1`, `run_sparse_peer_pilot.ps1` | Completed architecture experiments and read-only analyzers |
| [experiments/architecture_pilots/](experiments/architecture_pilots/) | New versioned routing, variable-panel protocol, durable runner and analysis |
| `run_confirmation_pilot.ps1`, `run_confirmation_pilot.py` | Completed twelve-question confirmation and read-only analyzer; 840 calls, all voting/stopping rules replayed offline |
| [experiments/confirmation_pilot/](experiments/confirmation_pilot/) | New versioned protocol, durable runner, and paired policy analysis |
| `run_offline_comparison.ps1`, `run_offline_comparison.py` | Current offline voting/stopping comparison; zero new generations |
| [experiments/offline_policies/](experiments/offline_policies/) | Versioned policy definitions, prefix replay, and report provenance |
| `run_communication_recovery.ps1`, `run_communication_recovery.py` | Preserved completed recovery runner and offline source analyzer |
| [experiments/communication_pilot/](experiments/communication_pilot/) | Preserved completed-pilot protocol, checkpointing runner, and paired analysis |
| [config/communication_recovery.json](config/communication_recovery.json) | Completed recovery's failure-policy amendment and unchanged generation protocol |
| [docs/](docs/) | Current pilot guide, experiment catalog, model registry, and preserved designs |
| [archive/](archive/README.md) | Immutable historical source/configuration/result snapshots and model artifact inventory |
| [results/](results/README.md) | Operational evidence and new runs; raw active results remain local until deliberately archived |
| `calculator.py`, `calculator_protocol.py`, `multi_agent_*.py`, `local_llm.py` | Shared exact calculator, scoring, prompt, and transport dependencies |
| Other root Python files | Frozen completed-pilot entry points and their import dependencies; their original paths are required by recorded audits |
| [tests/](tests/) | Offline protocol, analysis, archive, and durable-checkpoint tests |

The October and November historical archives retain their original bytes. The November 17 archive preserves both Windows pilots, their raw evidence and exact source snapshots. Some older raw Mac artifacts are unavailable on this PC; their portable metrics and recorded evidence hashes are preserved and cataloged. Completed-run source/configuration files and operational parent results remain in their original paths because historical audits and panel imports depend on those paths. The fresh full-study runner reads its selected-profile identity from the versioned archive, without following ignored operational parent paths.

Maintenance and unfrozen legacy modules have moved out of the root. The remaining root modules retain their bytes and paths for historical replay; new implementation belongs under `experiments/` or `tools/`. See the [layout guide](docs/REPOSITORY_LAYOUT.md) for all moved commands and the compatibility boundary.

The locally available Llama weights are backed up with verified content hashes under `archive/model-artifacts/`; large blob backups are ignored by Git, while manifests and inventories can be versioned. Qwen's historical experiments remain archived; its weights are not installed here. [Archive index and verification](archive/README.md)

## Offline checks and other designs

The project uses the Python standard library. With a working Python command:

```powershell
py -3 -B -m unittest discover -s tests -q
py -3 -m tools.archive_project_history --check
```

The suite uses mocked model responses and a temporary localhost server, without real inference. Environments that block local sockets must allow the existing client tests to access their temporary loopback server. The PowerShell pilot launcher also accepts `-Python C:\path\to\python.exe`.

The preserved single-agent control is documented in [BASELINE_RESULTS.md](docs/BASELINE_RESULTS.md), including its historical 0.001 tolerance. Current multi-agent experiments use exact equality. The old [v1 communication protocol](docs/MULTI_AGENT_PROTOCOL.md) and [v1 full-study design](docs/FULL_EXPERIMENT_V1.md) remain historical reference material. The active [five-agent full study](docs/FULL_EXPERIMENT.md) uses the selected strict schema. Windows installation guidance is in [WINDOWS_RUN_GUIDE.md](docs/WINDOWS_RUN_GUIDE.md).
