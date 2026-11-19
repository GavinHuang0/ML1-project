# Selected-profile communication versus self-revision pilot

V1 stopped after 146 raw responses (145 evaluated): a self-revision response hit the 1024-token cap inside unfinished JSON. Its original stop policy and evidence remain unchanged. The [explicit v2 recovery amendment](COMMUNICATION_RECOVERY.md) records the truncated response as ineligible and reuses the entire prefix, leaving 334 new calls. The original generation design below remains the basis for both branches.

This development pilot tests whether access to peers helps beyond another attempt with one's own work. The selected profile is the **unchanged original calculator instruction plus the existing strict JSON schema**. The added completeness instruction is not adopted. Selection came from the frozen screening rule in the completed format follow-up: 79/80 eligible outputs, one calculator rejection, and 4/8 collectively correct questions for `strict_schema`.

## Frozen design

| Item | Procedure |
| --- | --- |
| Questions | Eight `format-v2-*-development-*` screening questions, two per family, from eight structural groups |
| Initial answers | Reuse all 80 original `strict_schema` screening records, copied unchanged from the audited parent run |
| Conditions | `communication` and `self_revision`, sharing the identical initial panel |
| Rounds | Shared round 0, then three new revision rounds per condition; no early stopping on consensus |
| New generation budget | Eight questions times ten agents times three rounds times two conditions = **480 calls** |
| Sampling | `llama3.2:3b`, temperature 0.7, 1024 output tokens, context 16384, `keep_alive=0`, nonstreaming local Ollama |
| Seeds | Same deterministic question/round/agent seed in both branches; errors may still be correlated |
| Order | Alternating paired condition order with synchronous preceding-round snapshots |
| Primary descriptive comparison | Communication minus self-revision collective accuracy at round 3 |
| Other comparisons | All round 0–3 and family curves, revisions, failures, aggregation, and measured resource costs |

These are inspected development data, including fresh numbers on previously inspected structures. They are not a held-out generalization test. Keep all eight, including difficult cases with zero correct initial answers; do not select favorable questions using references. The easy sensor initial panel contains two correct agents, so the earlier zero-correct capability diagnostic does not block this pilot.

## What each agent receives

Both branches use the **same revision system instruction**: the original calculator instruction followed by a request to reconsider the setup using the preceding snapshot. The only condition difference in the request is whether peer responses are present. The schema is identical in every call: string `explanation` and `expression`, no extra properties, and expression pattern `^[0-9.()+*/ -]{1,1000}$`.

For round `r`, a communication agent receives the original question, its own response, and all nine peers' responses from completed round `r-1` in the communication branch. Peers are anonymous and reproducibly shuffled. A self-revision agent receives the original question and only its own preceding response from the self-revision branch. At round 1 both branches use the same imported round 0; rounds 2 and 3 follow branch-specific trajectories.

Only `explanation`, `expression`, `computed_fraction`, and `status` are shared. References, correctness labels, dataset parameters, and unrelated metadata remain local. The instruction treats response text as untrusted data and distinguishes mechanical calculator values from correctness feedback. No call sees another agent's newly generated answer from its own round.

Calls run sequentially; condition order alternates within question/round/agent pairs to reduce simple ordering effects. Prompts are never shortened. UTF-8 content bytes plus a 256-token template reserve and 1024-token output allowance must fit the 16384 context admission budget. Oversized prompts or observed saturation stop and preserve the run.

## Calculator and scoring

Raw generations are saved before validation. Schema nonconformance stops the run with raw evidence preserved. The calculator evaluates the explicit expression once, without repairs, response retries, or extraction from explanation text. A calculator rejection is recorded and remaining planned calls continue. An undefined denominator is a model-produced expression failure, not evidence of arithmetic-engine error.

Eligibility requires valid required fields, successful exact-rational calculation, and a probability in `[0,1]` where relevant. Correctness requires exact equality with the independently checked reference. The unique most frequent eligible rational value is the collective answer; ties/no eligible values abstain and count incorrect. Explanation length is reported separately. Explanation mathematics and agreement with the expression are not automatically graded.

The report separates malformed/unsupported expressions, division by zero, other execution failures, out-of-range probabilities, executable wrong values, and correct values. It also exposes correct minority answers lost by voting, zero-correct initial panels, beneficial/harmful individual and collective revisions, and incorrect consensus. These are observable diagnostics, not direct measurements of hidden reasoning.

## Analysis fixed before inference

The primary descriptive endpoint is the paired collective-accuracy difference at round 3. Report rounds 0–3 regardless of outcome; do not select a favorable round as if it were a validated stopping policy. Intervals use 2000 deterministic paired, family-stratified bootstrap resamples of whole question/structural groups. The same sampled groups are shared across conditions and rounds. There are **eight groups**, not 80 independent agents. Small or degenerate intervals do not establish equivalence or generalization.

Both trajectories include the identical recorded round-0 costs. Physical totals count that imported panel once, identify its costs as historical, and separately report the 480 new calls and their actual tokens and measured generation-call seconds. Call times include loading but exclude human pause intervals; they do not include prompt construction, health checks, parsing, or journaling. Recorded process segments measure active execution intervals separately. Generation counts match; tokens/time do not. A token-budget-matched independent-sampling control remains future work.

If communication improves over self-revision, inspect whether it improves execution, mathematical formulation, or use of correct minority answers. If both improve similarly, extra revision is a plausible explanation. If correct answers disappear into wrong consensus, report harmful convergence. No outcome automatically launches the full study. Freeze the final profile, calibrate on development, select one global round on validation, and evaluate on untouched test questions later.

## Run, pause, resume, and audit

The default parent is `results/format-followup/windows-v2`. Offline preparation audits its complete raw evidence, exact scores, recommendation, source/configuration hashes, and selected panel. A real launch additionally requires the same model digest, Ollama version, and hardware/runtime identity as that parent. A mismatch stops; there is no silent fallback to new initial generations. A fresh-panel design would need a separately frozen 560-call run.

With Ollama running, in PowerShell:

```powershell
Set-Location D:\ML1-project
.\run_communication_pilot.ps1 -DryRun
.\run_communication_pilot.ps1
```

The launcher finds a working Python 3.10+ interpreter without installing packages. Default output is `results/communication-pilot/windows-v1`, which must be new. Explicit paths:

```powershell
.\run_communication_pilot.ps1 -ParentRun results/format-followup/windows-v2 -OutputDir results/communication-pilot/my-run -Timeout 600
```

Equivalent direct Python command:

```powershell
py -3 run_communication_pilot.py --parent-run results/format-followup/windows-v2 --output-dir results/communication-pilot/windows-v1 --timeout 600
```

Press Ctrl+C once and wait for `paused`; the current returned response is saved. Resume with the same options plus `-Resume` (or `--resume` for Python):

```powershell
.\run_communication_pilot.ps1 -Resume
```

Keep source, inputs, parent evidence, hardware, driver, model, runtime, and paths unchanged during the run, including while paused. A lock prevents concurrent writers. Resume audits evidence and reconstructs canonical prompts, continuing at the next pending call. A durably returned raw response is evaluated locally rather than requested again. A second Ctrl+C can lose an in-flight reply. Failed calls are not automatically retried; an explicit resume preserves failure history.

From another terminal, `.\run_communication_pilot.ps1 -Pause` requests cooperative pausing. Offline reanalysis makes no service calls, reads no live hardware, and changes no evidence:

```powershell
.\run_communication_pilot.ps1 -AnalyzeRun results/communication-pilot/windows-v1
```

Evidence includes `initial_panel.jsonl` (80 unchanged imported answers), new-call `generations.jsonl` and `answers.jsonl` (480 each on completion), `run-manifest.json`, and completed `summary.json`. The manifest binds parent evidence, frozen source/configuration, settings, model/runtime/hardware, and checkpoints. The summary contains both branch trajectories and paired comparisons.

Source lives under [experiments/communication_pilot/](../experiments/communication_pilot/), with [configuration](../config/communication_pilot.json) and [entry point](../run_communication_pilot.py). Alternatives and model availability are indexed in the [experiment catalog](EXPERIMENT_CATALOG.md), [model registry](MODEL_REGISTRY.md), and [archive index](../archive/README.md).
