# Twelve-question confirmation: completed results and full-study decision

The confirmation is technically complete. It supports retaining current-round plurality and moving toward the original held-out communication versus self-revision study. It does not support replacing plurality with either alternative voter or treating agreement as confidence in correctness. No additional candidate-screening pilot is needed to seek a favorable communication result. A selected-profile full-study implementation and consistent cost calibration remain prerequisites to launching validation/test.

## Evidence and audit

The completed run is [results/confirmation-pilot/windows-v1](../results/confirmation-pilot/windows-v1/summary.json). Independent read-only analysis passed: all **840 raw generations and evaluations**, canonical requests/seeds/preceding-round snapshots, source/configuration hashes, model/runtime identity, and all three reports reproduce. The report contains **36 comparisons, 432 question decisions and 288 voter/round predictions**. No model calls were made during this interpretation.

There are 120 freshly generated shared initial responses and 720 revisions. These are twelve previously unrun numerical development cases across eight structural groups: four new numbers on inspected moderate structures and eight cases from four new hard structures. Variants within a structural group are correlated. The 36 policy rows are not 36 independent experiments. All thresholds and voters were fixed before these responses were collected; this remains development evidence, with no automatic policy selection and no validation/test inference.

The run completed in one segment. The selected model, original calculator instruction, strict schema, paired scheduling and exact scoring were retained. The [environment amendment](../config/confirmation_environment.json) records the pre-inference NVIDIA driver change from 617.42 to 621.24. Both branches in this run use the same new baseline. Earlier-driver timing is not a hardware-held-constant comparison.

The [immutable archive](../archive/2026-11-18-confirmation-pilot-v1/README.md) preserves the completed evidence and frozen implementation. See the [protocol](CONFIRMATION_PILOT.md) for exact generation, voting and stopping definitions.

## Communication versus self-revision

Current-round plurality gives:

| Completed round | Communication correct questions | Self-revision correct questions | Communication correct agents | Self-revision correct agents |
| --- | ---: | ---: | ---: | ---: |
| R0, shared initialization | 0/12 | 0/12 | 5/120 | 5/120 |
| R1 | 1/12 | 3/12 | 6/120 | 15/120 |
| R2 | 1/12 | 4/12 | 6/120 | 16/120 |
| R3, primary reference | **1/12** | **4/12** | **11/120** | **17/120** |

At R3, communication solves only the second average-speed-with-pause case, `units-05`. Self-revision also solves that case, plus the rectangle `algebra-03`, mixture `algebra-05`, and tank `units-03`. There are three self-revision-only wins and no communication-only win. Communication answers eleven questions, ten incorrectly; self-revision answers eight, four incorrectly.

The communication-minus-self-revision family-balanced accuracy difference is **−25 percentage points**, with an exploratory paired whole-group bootstrap interval of **[−50, −12.5] points**. The point estimate equals the ordinary question accuracy difference because the original sample has three questions per family. Bootstrap family sizes vary when one- and two-variant groups are resampled, so its family-balanced interval differs from the raw pooled-question interval [−44.44, −13.33]. Preserve that distinction. These are 2,000 resamples of eight observed development groups, not a general proof of superiority or a held-out test result.

Both branches fail all three urn and all three sensor questions collectively. All sensor cases have zero correct individual responses in every round of either branch. Previously inspected structures give communication 0/4 versus self-revision 2/4; new hard structures give 1/8 versus 2/8. The result is therefore not solely an effect of new structures. The low absolute success rate limits what this model/benchmark can reveal about useful mathematical communication, and must be reported rather than removed by changing questions after inspection.

## Three voters

R3 results, with abstention counted incorrect over all twelve questions:

| Voter | Communication correct / answered | Communication wrong delivered | Self-revision correct / answered | Self-revision wrong delivered |
| --- | ---: | ---: | ---: | ---: |
| Current-round plurality | **1 / 11** | 10 | **4 / 8** | 4 |
| Initial-anchored | 1 / 11 | 10 | 4 / 10 | 6 |
| Agent-history | 1 / 12 | 11 | 3 / 9 | 6 |

Initial anchoring has no net self-revision accuracy gain: it recovers mixture `-04` by combining one current correct vote with one initial correct vote, but loses mixture `-05` because initial errors turn its correct two-vote plurality into a pooled tie. It additionally delivers wrong answers on two sensor cases. History also loses the correct mixture `-05` answer and does not recover `-04`. For communication, history's extra answered question is wrong.

The earlier post-hoc self-revision R2 gain did not transfer: current-round plurality and anchoring now both solve 4/12 at R2, while history solves 3/12. At R1 plurality solves 3/12 versus 2/12 for each alternative. There is no consistent accuracy benefit supporting either replacement. Retain plurality as the default; the other voters can remain frozen secondary analyses.

## Two stopping rules

All three voters choose the same stopping rounds on this sample. Costs include initial generation, input/output tokens, and complete rounds through the selected endpoint.

| Policy | Communication early stops | Wrong early stops | Communication tokens | Saving versus own R3 | Self-revision saving |
| --- | ---: | ---: | ---: | ---: | ---: |
| Fixed R3 | 0 | 0 | 748,411 | — | — |
| High agreement, at least 8/10 | 3 | **3** | 666,704 | **10.92%** | **0%** |
| Stable majority, at least 6/10 in consecutive rounds | 2 | **2** | 716,557 | **4.26%** | **0%** |

High agreement stops all three urn cases early: `-03` at R2 with 9/10 support, `-04` at R2 with 8/10, and `-05` at R1 with 8/10. All are wrong. Stable majority stops urn `-05` at R2 with **10/10 wrong votes**, and tank `units-03` at R2 with 6/10 wrong votes. The two hard urn variants share a structural group. Neither stopper triggers early in self-revision.

Every adaptive final answer is exactly its own voter's R3 answer. No early-stopped question later recovers, so **there is no additional observed accuracy loss or missed later recovery relative to completing R3**. The savings come from ending persistently wrong trajectories earlier. Distinguish that potential efficiency benefit from recognizing correct answers: high agreement and temporal stability are not reliable correctness signals on these cases.

High agreement again saves more than stability, but savings are smaller than in the earlier easy-case replay. These numbers are counterfactual saved-prefix costs: all 840 calls were deliberately generated, allowing the audit of later outcomes. They do not measure deployed early-stopping latency. Neither rule has been certified safe on new questions; neither warrants becoming the primary procedure on this evidence alone. Retain them as prespecified efficiency secondaries, without retuning thresholds against these results.

Fixed-round controls are competitive. Communication R1 already solves the same one question as R3 at 266,407 rather than 748,411 tokens, a 64.40% reduction. Self-revision R2 and R3 each solve four questions, at 180,842 versus 250,047 tokens, a 27.68% reduction; their correct sets differ, with average-speed `units-04` lost and mixture `algebra-05` gained by R3. These are development observations; select a global round on validation rather than adopting a post-hoc endpoint.

## Delivery and resource checks

Communication R3 is **120/120 eligible**, with 11 correct and **109 executable wrong expressions**. Self-revision R3 is 114/120 eligible, with 17 correct, 97 executable wrong, one malformed expression, one division by zero, and four out-of-range probabilities. The final communication failure is predominantly delivered mathematical/formulation error, not formatting rejection. Explanation correctness is not automatically graded; executable wrong expressions can reflect conceptual reasoning, transcription, or inconsistency between explanation and expression.

One fresh communication response, `algebra-03`, R2 agent 1, exhausted the 1024-token output cap and produced incomplete JSON. The prospectively frozen admission preserved it as one ineligible response without repair or retry. The complete audit reproduced that decision. It is included in costs and diagnostics.

| Resource | Communication | Self-revision |
| --- | ---: | ---: |
| Full trajectory tokens, including initialization | 748,411 | 250,047 |
| Revision-only tokens | 706,218 | 207,854 |
| Full trajectory model-request seconds | 1,421.8 | 1,344.8 |

Communication uses **2.99 times the total trajectory tokens**, or **3.40 times revision-only tokens**, and 5.7% more summed request time. Across both arms, shared initialization counts once: **840 generations, 956,265 tokens, and 2,392.9 request seconds**. Loading contributes about 1,600.0 seconds under `keep_alive=0`. Request time excludes prompt construction, health checks, evaluation, journaling and other process overhead; it is not total study wall time.

## Full-study decision

The development screening is sufficient to move to a frozen held-out comparison. Another exploratory voting/stopping pilot is not required by these results. A negative communication result is an admissible research outcome. Keep the difficult cases, exact scorer, and selected model/profile unchanged within this study; a stronger model or scaffold would be a separate intervention.

Before launching:

1. Version the full-study runner with the selected strict schema, original initial instruction, identical generic revision instruction in both branches, explicit output-cap failure policy, paired scheduling, durable checkpoints and pinned driver 621.24. The existing plain-JSON full-study runner uses different prompts/scheduling and does not implement the confirmed procedure.
2. Preserve **plurality plus one global communication round selected on validation** as primary, using the specified error/cost objective and tie rule. Freeze that round before test, compare both arms at it, and retain R0/fixed-round curves. Report the three voters and two stoppers as a frozen secondary grid; do not substitute the best test row for the primary result.
3. Make development calibration and cost units explicit. The twelve confirmed trajectories could be imported only through a new audited compatibility path. Completing all twenty development trajectories would then require eight further cases ×70 =560 generations on the same new baseline; those eight are regression cases already numerically inspected, not fresh holdout. Reuse is conditional, not implemented by the current full runner.
4. Resolve the timing-scope difference before validation. The old full-study objective uses full-round active wall time, while this confirmation records request time. These cannot be silently interchanged. Either collect compatible calibration for the original wall-time objective or freeze a documented request-time amendment before validation; report other overhead separately where measured.
5. Keep the forty validation and forty test questions/groups untouched until the corresponding stage. Development data, including these twelve outcomes, may inform the frozen setup. Validation performs the predeclared selection, and test evaluates the locked procedure. The current setup must not automatically launch the old full-study command.

This means **ready for full-study implementation/freeze, with no further policy pilot needed**, while the present full-study executable still requires integration and calibration work before inference.

## Reproduce this run's audit

```powershell
Set-Location D:\ML1-project
.\run_confirmation_pilot.ps1 -AnalyzeRun results/confirmation-pilot/windows-v1
```

This is read-only analysis, requires no model service, and adds no generations.
