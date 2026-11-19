# Twelve-question voting and stopping confirmation pilot

**Completed and audited:** all 840 calls and reports reproduce. Communication plurality solves 1/12 versus self-revision 4/12; alternative voters show no consistent gain, and every adaptive early stop is wrong although its final answer matches R3. Read the [results and full-study decision](CONFIRMATION_RESULTS_V1.md). Use the audit command below for the completed default directory; a new creation command will refuse that existing destination.

This versioned development pilot tests the [offline policy candidates](OFFLINE_POLICY_COMPARISON.md) using the selected **original calculator instruction + strict JSON schema**. It generates full communication and self-revision trajectories on twelve unused numerical development cases, then evaluates all policies on those same trajectories. The frozen procedure below is preserved for reproducibility. [Why this confirmation was run](OFFLINE_POLICY_RESULTS_V1.md)

## Run

With Ollama running and the selected `llama3.2:3b` model installed, run in PowerShell:

```powershell
Set-Location D:\ML1-project
.\run_confirmation_pilot.ps1
```

The default new destination is `results/confirmation-pilot/windows-v1`; it must not already exist for a fresh run. The launcher selects Python 3.10+ automatically and requires no additional Python packages. Preview the frozen plan without model calls:

```powershell
.\run_confirmation_pilot.ps1 -DryRun
```

Choose another new directory with `-OutputDir results/confirmation-pilot/my-run`. Pass `-Python C:\path\to\python.exe` if automatic discovery cannot find a working interpreter. The model-request timeout defaults to 600 seconds and can be set with `-Timeout`.

The first setup attempt stopped before creating a run directory or generating any answers because the NVIDIA driver changed from **617.42 to 621.24**. The PC, GPU, GPU memory, CPU, RAM, and OS identity otherwise match the completed recovery. The [confirmation environment](../config/confirmation_environment.json) records this pre-inference amendment and pins driver **621.24** for the new run. Start with the fresh-run command above, without `-Resume` or a trailing backslash after `.ps1`.

## Questions and evidence units

The frozen question IDs are `full-v1-{family}-development-03`, `-04`, and `-05`, for each of `reasoning`, `evidence`, `algebra`, and `units`. They come from the existing [full benchmark](../config/full_benchmark.json). This is **twelve fresh numerical cases**, three per family, spanning **eight structural groups**. Only four groups are structurally new.

| Cases in each family | Freshness | Structural group |
| --- | --- | --- |
| `development-03` | New numbers on a previously inspected moderate structure | One existing group |
| `development-04` and `-05` | Two numerical variants of a previously untested hard structure | One new group, shared by the pair |

The four new structures are three-color urn sampling, four-source sensor evidence querying state zero, an algebraic mixture, and average travel speed with a pause. These cases emphasize moderate/hard problems, so their stopping frequency need not match the easier eight-case pilot. Results distinguish new from previously inspected structures. Neither variants nor ten agent outputs are independent structural observations.

The original eight `development-01/-02` cases were already inspected and are excluded. Validation and test questions and groups are excluded. The confirmation uses references only for offline scoring; no reference answer, correctness flag, or voting/stopping decision enters a model prompt.

## Generation procedure and budget

| Component | Frozen procedure |
| --- | --- |
| Selected profile | Original calculator prompt with the selected lexical strict JSON schema; no expression-completeness intervention |
| Model | `llama3.2:3b`, temperature 0.7, output cap 1024, context 16384, `keep_alive=0` |
| Initial panel | Ten freshly generated round-0 responses per question, shared exactly between both branches |
| Communication | Original question, own preceding response, and nine anonymously ordered peers' preceding responses |
| Self-revision | Original question and own preceding response only |
| Revision instruction | The same revision system instruction in both branches; only peer visibility differs |
| Scheduling | Sequential, paired alternating branches; corresponding question/round/agent seeds match between branches |
| History | Completed immediately preceding round only; synchronous updates |
| Delivery and scoring | Required JSON explanation/expression strings, bounded exact-rational calculator, probability range check, exact equality; no repair |
| Endpoint | Collect every round through R3, then replay terminal policies offline |

There are **120 fresh initial calls + 720 revision calls = 840 unique model calls**. Each branch represents 480 calls including its copy of the shared initialization; counting both copies as physical inference would overstate the total. No initial answer is imported from the earlier pilot.

Voting rules and whole-question stopping are terminal decisions, with no feedback to subsequent model requests. Consequently, all six voter/stopping combinations use the same generated trajectories. They do **not** require six separate generation runs. Completing R3 is deliberate: it reveals whether stopping would miss later corrections or avoid later corruption.

Actual generation completes all 840 calls. Reported adaptive savings are counterfactual prefix costs within these traces, including initial generation and every call in the selected completed round. Historical model-request durations are not a new latency benchmark for an online stopper. Generation counts match between branches; tokens and time need not match.

## Prespecified policy comparisons

All voters use eligible exact-rational values and abstain on an exact highest-score tie:

| Voter | Definition |
| --- | --- |
| `plurality` | One vote per eligible current response; unique largest count wins |
| `initial_anchored` | Initial-panel count plus current-panel count; count R0 once when evaluating R0 |
| `agent_history` | Each agent contributes total weight one, divided equally among its distinct eligible values seen through the current round |

Both stopping rules inspect only observed prefixes and count actual supporting agents out of the original ten:

| Stopper | Definition |
| --- | --- |
| `high_agreement_8` | First completed round, including R0, with a unique selected answer supported by at least eight current agents |
| `stable_majority_6` | First round R1 or later where the selected answer is unchanged across two consecutive rounds and has at least six current supporters in each |

If no trigger occurs, use the selected voter's R3 answer, including abstention. Pooled/history scores do not count as current support. Agreement thresholds are heuristics rather than correctness probabilities.

Fixed rounds 0, 1, 2, and 3 remain controls. The complete report has **3 voters × 6 endpoints × 2 branches = 36 comparison rows**, **432 per-question decisions**, and **288 voter/round predictions**. Retain R1 and R2 controls: the earlier offline comparison's strongest voting gain occurred at R2 and was not captured by either stopping rule.

Report overall accuracy with abstentions counted incorrect, coverage, wrong delivered answers, paired gains/losses, incorrect early stops, later recoveries missed by stopping, correct answers subsequently lost, stop rounds, tokens, request durations, and per-family/freshness behavior. Uncertainty resamples whole structural groups within families, keeping numerical variants together and pairing policies and branches. Eight groups provide exploratory uncertainty rather than a tight safety guarantee.

There is **no automatic winner selection**, threshold tuning, learned stopper, or validation/test inference. Original plurality/R3 remains the reference comparison for this pilot. The full study's primary plurality/global-round selection design remains unchanged; a new policy-selection procedure must be frozen before validation if one is later adopted. Progression must not depend on obtaining a favorable communication result.

## Failure handling fixed before generation

The earlier recovery's narrow output-truncation exception is now specified prospectively for both fresh initial and revision responses. Invalid JSON with a valid, unsaturated transport wrapper, `done_reason="length"`, and exactly 1024 generated tokens is one ineligible answer. Its token/time cost is retained; there is no JSON repair, expression extraction, or retry. Other schema violations, including valid JSON with invalid fields or expression characters, preserve the raw evidence and stop the run. Calculator failures and out-of-range probabilities remain ineligible answers under the existing scorer.

Source/configuration/task hashes and model/runtime/hardware identity are saved and rechecked. The selected model digest and Ollama version still match the completed recovery. The separate [confirmation environment](../config/confirmation_environment.json) freezes the current hardware snapshot and explicitly records the driver-only change from that recovery; it does not permit arbitrary hardware changes. Both branches execute under this one new environment. Resume requires the same evidence paths, frozen implementation, and full confirmation hardware identity, including driver version. A subsequent driver update blocks resume rather than silently mixing environments. Do not edit the selected profile or saved records during a run.

Communication-versus-self-revision token/time comparisons use measurements from this confirmation run under the same driver. Earlier driver-617.42 request times remain historical evidence and are not a hardware-held-constant timing control for this driver-621.24 run. Previous evidence and archives remain unchanged.

## Pause, resume, and audit

Press Ctrl+C once, then wait for the active call to finish, be saved, and the runner to report `paused` with exit code 2. Resume the same directory with:

```powershell
.\run_confirmation_pilot.ps1 -Resume
```

For a custom directory, pass the same `-OutputDir` on resume. To request a pause from another terminal:

```powershell
.\run_confirmation_pilot.ps1 -Pause
```

A second Ctrl+C can interrupt an in-flight request. Durable returned responses are audited and evaluated locally rather than regenerated; a call without a durable returned response cannot be recovered from disk. There are no automatic model retries.

After completion, verify all saved requests, raw evaluations, source hashes, and reproduced reports without Ollama:

```powershell
.\run_confirmation_pilot.ps1 -AnalyzeRun results/confirmation-pilot/windows-v1
```

The output directory retains `run-manifest.json`, raw `generations.jsonl`, evaluated `answers.jsonl`, and the completed `summary.json`, `comparisons.csv`, and `per_question.csv`. Fresh initial records are tagged `arm="shared_initial"` in the journals; revision records identify their branch. Preserve the entire directory. Earlier completed and failed runs remain in place. The [completed confirmation archive](../archive/2026-11-18-confirmation-pilot-v1/README.md) preserves this run, its new frozen sources/configuration and verified references to earlier dependencies.

Implementation: [protocol](../experiments/confirmation_pilot/protocol.py), [runner](../experiments/confirmation_pilot/runner.py), [analysis](../experiments/confirmation_pilot/analysis.py), [configuration](../config/confirmation_pilot.json), and [execution environment](../config/confirmation_environment.json).
