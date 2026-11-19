# Communication versus self-revision: completed recovery pilot

The completed pilot does **not support adopting three communication rounds**. At the prespecified round-3 endpoint, communication answered 4/8 questions correctly versus 5/8 for self-revision, with about three times the revision tokens. Communication did increase individual answer correctness; the extra correct answers did not reliably win the collective vote.

## Evidence and audit

The operational run is [results/communication-pilot/windows-v2](../results/communication-pilot/windows-v2/summary.json). Independent offline replay passed: all 480 raw revision records and evaluated answers, canonical prompts/seeds/preceding-round snapshots, original parent/prefix evidence, calculator results, source hashes and the saved summary reproduced. The [immutable archive](../archive/2026-11-17-communication-recovery-v2/README.md) preserves the completed evidence and exact source/configuration snapshot.

The run combines 80 historical initial generations, all 146 revisions from failed v1, and 334 newly generated revisions. All 145 earlier evaluations are unchanged. The one length-truncated invalid-JSON response was evaluated locally as ineligible, with no repair or retry. No additional truncation occurred during the 334-call continuation. This is an explicit post-failure amendment, not completion under v1's original stop policy. The model, prompts, schema, seeds, output cap and exact scoring stayed fixed.

## Collective and individual results

| Round | Communication: correct questions | Self-revision: correct questions | Communication: correct agents | Self-revision: correct agents |
| --- | ---: | ---: | ---: | ---: |
| 0, shared initial panel | 4/8 (50%) | 4/8 (50%) | 33/80 | 33/80 |
| 1 | 5/8 (62.5%) | 4/8 (50%) | 40/80 | 33/80 |
| 2 | 4/8 (50%) | 4/8 (50%) | 43/80 | 31/80 |
| 3, primary comparison | **4/8 (50%)** | **5/8 (62.5%)** | **46/80** | **29/80** |

The primary communication-minus-self-revision collective accuracy difference is **-12.5 percentage points**, with a 95% paired family-stratified eight-group bootstrap interval of **[-25, 0] percentage points**. Self-revision alone solved one additional question, the tank; communication had no exclusive correct question at round 3. Eight inspected development groups and one discordant question do not establish general inferiority or superiority. Agent outputs are correlated; 80 responses are not 80 independent accuracy trials.

Communication's final individual correctness was 57.5% versus 36.25% for self-revision, a difference of +21.25 points (descriptive group interval [+7.5, +35]). This is a secondary outcome and does not replace the collective primary endpoint. Correct responses can become more numerous on already solved questions while correlated wrong answers still prevent other panels from winning.

Round 1 is a promising descriptive candidate, not a validated stopping rule. Its collective advantage over self-revision was +12.5 points with interval [-12.5, +37.5]. Choosing it after examining these curves would not constitute validation of an optimal global round.

## What happened on individual questions

| Case | Communication | Self-revision | Implication |
| --- | --- | --- | --- |
| Conditional urn, reference `1/19` | Correct-agent counts 2→6→4→5. Correct in round 1; wrong `1/7` won round 2; round 3 tied 5:5 and abstained | Incorrect throughout; no correct agent remained by round 3 | Correct information spread, then the collective benefit disappeared |
| Tank, reference `58/3` | Correct agents increased 1→2→3→4, but six agents ultimately agreed on wrong `238/3` | Three correct agents won because the strongest wrong answer had only two votes | More correct agents can still lose when errors concentrate |
| Easy sensor, reference `7/19` | Correct agents increased 2→4→6→7; collective answer remained correct | Correct agents 2→0→2→2; final answer correct by a fragile two-vote plurality | Communication strengthened the correct answer without adding a newly solved question |
| Three-source sensor, reference `9/11` | Zero correct agents throughout; answers concentrated on wrong candidates | Zero correct agents throughout; wrong answers remained diverse | Both conditions had a mathematical capability/formulation problem |
| Rectangle, reference `2` | Zero correct agents throughout; collective answer never correct | One correct agent in round 1 and two in round 3; collective never correct | New correct responses need not become a winning plurality |

There was **no unanimous ten-agent wrong consensus** in either branch. The harmful patterns were wrong majorities and tied candidates. The fixed aggregation rule behaves as specified; no reference-based tie breaking or expression repair was applied.

Across revision transitions, communication had 22 beneficial and nine harmful individual revisions; self-revision had ten beneficial and fourteen harmful revisions. These are correlated transition events, not independent trials. Communication collectively gained the conditional urn in round 1 and lost it in round 2. Self-revision gained the tank, temporarily lost the easy sensor, and later recovered it.

## Formatting versus mathematical errors

All **240/240** communication revisions were eligible. Self-revision had **232/240** eligible: five malformed/unsupported expressions, two out-of-range probabilities, and the inherited truncation. No new truncation occurred. The calculator faithfully evaluated supported expressions; these observations do not indicate arithmetic-engine errors.

In final round 3, communication had 46 correct and 34 executable wrong expressions. Self-revision had 29 correct, 48 eligible wrong, and three ineligible responses. This separates delivery/execution from delivered mathematical correctness. The reports do not automatically grade explanations or distinguish conceptual reasoning from transcription or explanation-expression inconsistencies.

## Resource comparison

Costs below include **all three revision rounds**, including the imported prefix, and exclude the identical initial panel:

| Resource | Communication | Self-revision |
| --- | ---: | ---: |
| Revision calls | 240 | 240 |
| Input tokens | 360,650 | 99,491 |
| Output tokens | 24,659 | 26,148 |
| Total revision tokens | **385,309** | **125,639** |
| Measured model-request seconds | **659.2** | **636.9** |
| Model loading seconds | 472.2 | 470.7 |

Communication used **3.07 times** the revision tokens and 3.5% more measured request time. Loading accounted for 71.6% and 73.9% of those request times under the frozen `keep_alive=0` policy. This helps explain why the longer prompts did not cause a proportional time increase on this machine. Request durations include loading, but exclude health checks, journaling, human pauses, and other process overhead. They are not end-to-end wall times or API prices.

Including the shared initial panel in each trajectory, communication round 1 and self-revision round 3 each solved 5/8 questions. Their costs were respectively 147,634 versus 150,364 tokens and 421.4 versus 841.8 request seconds. This motivates testing a shorter communication option; it does not establish a stopping rule. Communication rounds 2 and 3 matched round 0's 4/8 accuracy at greater cost on this sample.

Across both conditions, initial costs count once: 560 unique generations, 535,673 tokens, and 1,501.0 measured request seconds. Of the 480 revision generations, 146 were historical and 334 were generated during recovery. Both costs are retained.

## Recommended next study

The pilot is technically complete and the delivery profile is suitable for further evaluation. Another format pilot is not required by these results. Three-round communication is not justified as an operational default, and self-revision is not yet proven generally superior.

For the original research objective, the next substantial step is to **version and freeze the full-study implementation with the selected strict schema and explicit output-truncation policy**, then follow the planned development/calibration → validation selection over rounds 0–3 → untouched test procedure. Keep round 0 available, so a finding that communication is not worth its cost is an admissible result. The existing plain-JSON full-study runner must not be launched as if it already implemented this profile.

A smaller, prespecified balanced development replication with additional seed panels is an optional way to check trajectory variability and runtime before committing to the full study. It must not become a rule that advancement requires a favorable communication result. Preserve difficult cases, exact scoring, and the original aggregation rule. Select the global round on validation rather than these eight inspected questions.

Report individual versus collective correctness, correct-minority adoption/loss, vote concentration and token/time curves. A budget-matched additional-independent-sampling control is a useful later comparison. A stronger model, Bayes scaffold, or different voting rule would be a separate intervention, evaluated on new development evidence before validation/test; it should not retroactively change these scores.
