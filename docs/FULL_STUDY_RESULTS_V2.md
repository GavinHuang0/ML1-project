# Completed five-agent full study: verification and results

**Verification passed.** All 3,500 planned generations and evaluations are saved, all three phase reports reproduce, and there are no pending artifact recoveries. The prespecified validation procedure selected **round 0: five initial answers with plurality, without revision**. Its held-out test accuracy is **12/40 (30%)**. This is the primary result; later-round findings remain secondary.

The conclusion is more nuanced than saying communication is always worse. Later test rounds show a possible collective benefit over repeated self-revision and a clearer individual-answer improvement. However, those findings do not replace the frozen endpoint or demonstrate a general communication advantage.

## Completion and integrity

The [operational study](../results/full-experiment/study-v2/study-manifest.json) is complete under `ml1-five-agent-full-study-v2`:

| Phase | Questions | Structural groups | Saved generations | Status |
| --- | ---: | ---: | ---: | --- |
| Development | 20 | 12 | 700 | Complete, reproduced |
| Validation | 40 | 20 | 1,400 | Complete, reproduced |
| Held-out test | 40 | 20 | 1,400 | Complete, reproduced |
| Total | 100 | 52 disjoint groups | **3,500** | **Complete** |

There are 500 shared initial calls, 1,500 communication revisions and 1,500 self-revisions. All three phases completed in one segment each, with no recorded pause or failed segment. The read-only audit verified source/configuration/model/environment identities, canonical phase-local requests, seeds and peer order, immediately preceding branch snapshots, raw-response evaluation, checkpoints, artifact dependencies, and deterministic report bytes. It made zero model calls.

Technical completion does not mean every answer was eligible: **3,301/3,500 outputs were eligible (94.3%)**. Six output-cap invalid-JSON responses were retained as single ineligible outcomes under the prospective policy, without repair or retry: three development, one validation and two test. These are included in diagnostics and costs. No schema/scoring rule was changed after inspecting the run.

The [immutable full-study archive](../archive/2026-11-19-full-study-v2/README.md) preserves operational evidence, frozen artifacts and the new source/configuration snapshot, with verified references to prior dependencies. Interpretation is maintained here; frozen source, raw answers and scores remain unchanged.

## Phase separation and frozen selection

The saved chronology is consistent with the required gates. All times below are November 18, 2026, America/New_York:

| Event | Time |
| --- | --- |
| Development completed | 21:31:12 |
| Calibration written | 21:31:14 |
| Validation began | 21:31:16 |
| Validation completed | 22:36:40 |
| Selection written | 22:36:46 |
| Test began | 22:36:52 |
| Test completed | 23:40:59 |
| Whole study finalized | 23:41:08 |

The test manifest embeds the exact calibration and selection snapshots and hashes. They match the saved files and independently reproduce from development/validation reports. The frozen selection names validation as its source, records no test feedback, and sets both test branches to the same round 0. Verification was performed on November 19.

Development communication R1 supplied the positive normalization references: **5,425.15 revision tokens/question** and **13.5653 request seconds/question**, family-balanced. The selection objective was frozen before validation:

```text
1 - family-balanced communication accuracy
+ 0.02 * (0.5 * normalized revision tokens
          + 0.5 * normalized revision request seconds)
```

Initialization is excluded only from the revision penalty, not from total cost. Validation chose:

| Candidate round | Validation correct | Accuracy | Cost penalty | Total objective, lower is better |
| --- | ---: | ---: | ---: | ---: |
| **R0** | **13/40** | **32.5%** | **0** | **0.67500** |
| R1 | 12/40 | 30.0% | 0.01986 | 0.71986 |
| R2 | 13/40 | 32.5% | 0.04028 | 0.71528 |
| R3 | 14/40 | 35.0% | 0.06108 | 0.71108 |

Three rounds added one correct validation question, a 2.5-percentage-point accuracy gain over R0. Their approximately 6.11-point penalty outweighed that gain under the specified utility. R0 therefore won without changing weights or rules after observing test.

This is a validation-policy decision, not proof that no revision could ever help. The validation sample has forty questions in twenty groups; a selected endpoint need not be optimal on another sample. Indeed, test R1 outcomes are better than test R0. We retain R0 as primary rather than tuning the rule to those test outcomes.

## Primary held-out result

The locked policy answers **12/40 test questions correctly: 30%**, with a paired family-stratified whole-group bootstrap accuracy interval of **15–47.5%**. It answers 23 questions, delivering eleven wrong answers and abstaining on seventeen. Abstentions remain incorrect in the forty-question denominator.

At R0 the two named branches reuse exactly the same initial panel, so their answers and accuracy are **identical by construction**. The zero accuracy difference and [0, 0] paired interval are structural, not evidence that communication and self-revision are generally equivalent. The primary finding is that the validation objective selected no revision, followed by the held-out performance of that policy.

R0 is not free: its test panel contains **200 unique initial generations**, **66,171 tokens**, and **519.5 summed request seconds**. It has zero revision cost. All later rounds were nevertheless generated as planned for the secondary curves; those full-study costs have already been incurred and are reported separately below.

## Prespecified secondary test curves

| Round | Communication correct | Self-revision correct | Communication minus self-revision | Exploratory paired 95% interval |
| --- | ---: | ---: | ---: | --- |
| R0, locked primary | 12/40 (30.0%) | 12/40 (30.0%) | 0 points, structural | [0, 0] |
| R1 | 15/40 (37.5%) | 16/40 (40.0%) | −2.5 points | [−12.5, +10] |
| R2 | 13/40 (32.5%) | 12/40 (30.0%) | +2.5 points | [−10, +17.5] |
| R3 | 14/40 (35.0%) | 10/40 (25.0%) | **+10 points** | **[−2.5, +22.5]** |

Communication does better than self-revision at R3 on seven questions and worse on three. The interval includes no difference. These are paired group intervals over twenty test clusters, with all variants together and one seed panel per question. Later rounds and multiple diagnostics are secondary; they do not constitute a new search for a replacement primary endpoint.

The highest observed test point is self-revision R1 at 16/40. Calling it the newly selected policy now would use test outcomes for selection. Likewise, the positive R3 communication contrast cannot replace the validation-selected R0 result.

The test curves also clarify what late communication improves relative to: R3 communication has four question gains and two losses versus initial plurality, a net gain of two. R3 self-revision has three gains and five losses, a net loss of two. Thus the late communication-versus-self advantage partly reflects self-revision deterioration. It is not a uniform improvement from more discussion.

For transparency, applying the unchanged utility formula descriptively to test communication gives R0 0.7000, R1 0.6451, R2 0.7152 and R3 0.7101. R1 would look better on these test observations. This calculation is explicitly post hoc diagnosis of selection variability, not a new selection or a claim that R0 is test-optimal.

## Family effects and delivered errors

At R3 the collective result is strongly uneven:

| Test family | Communication | Self-revision |
| --- | ---: | ---: |
| Urn reasoning | 3/10 | 5/10 |
| Sensor evidence | 2/10 | 0/10 |
| Algebra | 1/10 | 2/10 |
| Units/rates | **8/10** | **3/10** |

The units/rates advantage contributes five of the net four extra correct questions. Broad claims across all mathematical families would obscure these differences.

Communication's additional coverage is not purely beneficial:

| Test endpoint | Correct | Answered | Wrong delivered | Abstentions |
| --- | ---: | ---: | ---: | ---: |
| Shared R0 | 12 | 23 | 11 | 17 |
| Communication R1 | 15 | 36 | 21 | 4 |
| Self-revision R1 | 16 | 23 | 7 | 17 |
| Communication R3 | 14 | 34 | **20** | 6 |
| Self-revision R3 | 10 | 15 | **5** | 25 |

At R3 communication is more accurate overall than self-revision, but delivers many more wrong answers. Answered-only accuracy is about 41.2% versus 66.7%, and their coverage differs substantially. The primary score penalizes abstentions, so these conditional percentages must not replace the full-question accuracy comparison.

## Individual answers and representative cases

Communication's individually correct test responses rise **50→59→67→70 out of 200**; self-revision gives **50→51→50→44**. The final individual difference is +13 percentage points, with descriptive paired group interval [+5.5, +21.5]. This secondary advantage does not automatically become a reliable collective gain.

Examples show both useful exchange and harmful revision:

- Three-color urn `reasoning-test-06`: one initially correct agent spreads to five of five correct by R1.
- Sensor `evidence-test-02`: communication grows correct support 2→3→4→5, while self-revision loses the initially correct answer after R0.
- Staged pump `units-test-09`: no agent is initially correct, but communication produces correct calculated answers from four agents by R2/R3.
- Divided-unknown algebra `algebra-test-01`: four of five agents start correct, but the panel becomes tied at R2 and wrong at R3, with only one correct agent remaining.
- Area conversion `units-test-01`: communication retains five of five correct, while self-revision falls to one correct agent and a wrong final answer.
- The sole unanimous wrong test panel is communication R3 on `reasoning-test-08`, predicting `2/33` instead of `5/9`.

There is still a supply limitation. At least one initial eligible agent is correct on **18/40** questions, but initial plurality solves only twelve. On the twenty-two questions with no correct initial agent, communication R3 solves one and self-revision R3 solves two. The reference-based oracle is a capability diagnostic, not an available aggregation method or correctness signal.

The prespecified single-agent-0 control gets **10/40**, versus initial plurality's 12/40. Their paired gain is +5 points, interval [−5, +17.5]. This is insufficient to establish that five samples always justify their additional cost over one.

## Delivery versus mathematical correctness

Final test communication has **197/200 eligible outputs**: seventy correct, 127 executable wrong, two malformed expressions and one out-of-range probability. Self-revision has **186/200 eligible**: forty-four correct, 142 executable wrong, one truncated invalid JSON, five malformed expressions and eight out-of-range probabilities.

The final failures are therefore predominantly delivered mathematical/formulation errors rather than JSON delivery failure. Exact arithmetic removes calculator rounding uncertainty for supported expressions, but a wrong executable expression may arise from conceptual reasoning, transcription or an explanation–expression mismatch. Explanations were not automatically graded, so the study does not fully separate those causes.

## Costs and runtime

| Test endpoint | Communication tokens | Self-revision tokens | Communication request seconds | Self-revision request seconds |
| --- | ---: | ---: | ---: | ---: |
| Shared R0 | 66,171 | 66,171 | 519.5 | 519.5 |
| R1 | 280,130 | 175,325 | 1,072.8 | 1,048.4 |
| R2 | 502,246 | 286,348 | 1,611.5 | 1,575.9 |
| R3 | **720,720** | **398,567** | **2,143.5** | **2,111.3** |

R3 communication uses **1.81 times total trajectory tokens**, or **1.97 times revision-only tokens**: 654,549 versus 332,396. Its measured request time is only about 1.5% greater. Fixed unloading/loading helps explain why token cost and time do not scale together.

Whole-study physical expenditure counts every shared initial response once:

- **3,500 saved generations** and **2,638,253 input/output tokens**.
- **9,434.15 request seconds**, about 2h37m14.
- **6,531.30 loading seconds**, 69.2% of measured request time.
- **2h42m06 elapsed time** from study initialization through finalization.

Request time excludes health checks, prompt construction, evaluation, journaling and other overhead. These figures describe this frozen `keep_alive=0` operating procedure, not an API bill or a new deployment benchmark. The selected R0 prefix cost is counterfactual operational expenditure within this completed full-trajectory study; it does not erase the costs already incurred generating later rounds.

## Interpretation and next steps

The valid primary conclusion is: **under the frozen validation accuracy/cost objective, the chosen policy uses five initial answers and no revision; its held-out accuracy is 30%.** The primary comparison cannot establish an effect of peer exchange because neither branch revises at the selected endpoint.

Secondary evidence suggests communication sometimes spreads useful information, preserves it better than repeated self-revision, and improves individual correctness. It also propagates mistakes and increases delivered errors. Collective gains are uncertain and family-dependent. The held-out observations are more mixed than the small development pilots; they do not support a universal claim that communication helps or hurts.

The experiment is complete. Preserve the selected endpoint, all phase curves, failed outputs and evidence. Do not alter the cost weight, adopt test R1, or promote test R3 to primary after inspection. Write up the result and its limitations: one model/profile, one architecture and seed panel, forty test questions in twenty structural clusters, and the specified cost objective.

If pursuing a follow-up, frame a separately versioned hypothesis such as preserving correct earlier work or improving the selection of correct minority answers. Retaining conversation history remains an untested intervention. Validation/test outcomes from this study are now inspected data; a new confirmatory claim needs fresh held-out evidence. No further inference is required to finish this experiment.

## Reproduce completion verification

```powershell
Set-Location D:\ML1-project
.\run_full_experiment.ps1 -AnalyzeRun results/full-experiment/study-v2
```

Expected audit: complete, 3,500 generations and answers, all three phases reproduced, no pending recovery, primary round 0, zero analysis model calls.
