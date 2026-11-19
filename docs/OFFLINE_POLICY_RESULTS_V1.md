# Offline voting and stopping comparison: completed results

The replay supports one bounded confirmation on unused development data before validation/test. The stopping rules saved tokens on these traces, but only by recognizing three already-easy cases. The alternative voters had mixed effects. Neither a new voter nor a stopping rule has been validated for adoption.

## Evidence and scope

The completed report is [results/offline-comparison/pilot-v1](../results/offline-comparison/pilot-v1/summary.json). Read-only audit reproduced the JSON summary and both CSV reports, verified source/configuration hashes and the completed recovery evidence, and confirmed **zero additional model calls**. There are 36 policy/branch summaries and 288 question decisions, all based on the same eight inspected development groups. These are correlated, post-hoc comparisons, not 36 independent experiments.

[Exact frozen definitions](OFFLINE_POLICY_COMPARISON.md) and the [immutable source/report snapshot](../archive/2026-11-18-offline-policies-v1/README.md) preserve the analysis. The source experiment remains unchanged; its [interpretation](COMMUNICATION_RESULTS_V2.md) still applies. The report performs no policy selection.

## Stopping rules: useful savings, limited evidence

Both rules preserve every voter's round-3 correctness, coverage, and actual final answers on these trajectories. They stop exactly the same three questions in both branches: the simple urn, affine equation, and cyclist problem. All three are correct early stops; the other five questions continue through round 3.

| Endpoint policy | Early stopping behavior | Communication tokens | Saving versus R3 | Self-revision tokens | Saving versus R3 |
| --- | --- | ---: | ---: | ---: | ---: |
| Fixed round 3 | All eight complete R3 | 410,034 | — | 150,364 | — |
| High agreement, at least 8/10 | Three stop at R0; five at R3 | 302,042 | **26.34%** | 112,591 | **25.12%** |
| Stable majority, at least 6/10 in two consecutive rounds | Three stop at R1; five at R3 | 337,732 | **17.63%** | 125,004 | **16.87%** |

Tokens include input and output, initial generation, and every call through the selected completed round. All three voters happen to choose the same stop rounds, so their costs are identical here. These are counterfactual costs reconstructed from saved prefixes; the full trajectories were already generated. Summed historical request times also fall, but are not a newly measured latency benchmark.

High agreement is the stronger cost-saving candidate on this sample. Stable majority spends one extra round on the same three cases without changing their answers. That does not establish that high agreement is generally safer or that checking stability is useless. There were only **three distinct early-stopped groups**; the two branches and three voters do not create independent safety observations. No difficult case exercised either early-stop rule.

The stored paired accuracy-difference intervals against each voter's R3 baseline are [0, 0] because the observed question outcomes are identical. Resampling these eight groups cannot reveal an unobserved failure mode; this is not proof of noninferiority on new questions. The saved exploratory token-saving intervals are also broad: high agreement 6.43–49.28% for communication and 7.04–45.56% for self-revision.

## Voting rules: no consistent replacement for plurality

At round 3, all answers are scored over eight questions, with abstention counted incorrect. The same correct/answered counts hold under either adaptive stopping rule.

| Voter | Communication correct / answered | Self-revision correct / answered |
| --- | ---: | ---: |
| Current-round plurality | **4 / 5** | **5 / 6** |
| Initial-anchored | 4 / 7 | 4 / 5 |
| Agent-history | 4 / 8 | 5 / 6 |

Communication's increased coverage under the new voters is entirely additional wrong answers. Initial anchoring replaces two plurality abstentions with errors; history replaces three. Answering more questions is not an accuracy improvement here. For self-revision, anchoring loses the correct tank answer by tying it with an initially popular wrong answer. History matches the original round-3 correctness and coverage.

The promising result is **self-revision at round 2**: both new voters solve 6/8, compared with 4/8 under same-round plurality. They correctly resolve plurality ties on the conditional urn and easy sensor by retaining earlier evidence. Each correct answer has only two current votes out of ten. The exploratory paired gain is +25 percentage points, with an eight-group bootstrap interval of [0, 50] points, before accounting for searching across policies.

This improvement is temporary. At round 3 the conditional urn has no correct current votes; anchoring abstains and history selects a wrong historical answer. Anchoring additionally loses the tank. The resulting totals fall to 4/8 for anchoring and 5/8 for history. Neither stopping rule captures the round-2 gains because two current supporting agents do not meet either threshold. Thus **the proposed combinations do not deliver the best observed 6/8 result**.

Keep the fixed-round controls, especially R1 and R2. Communication at R1 solves 5/8 under all three voters. A simpler globally selected round remains a meaningful alternative to adaptive stopping. Selecting the best row after inspecting this grid would overfit the development evidence.

## Communication versus self-revision

The primary plurality/R3 comparison remains communication **4/8** versus self-revision **5/8**, a difference of −12.5 percentage points with exploratory paired interval [−25, 0]. The adaptive rules preserve that comparison. They reduce cost in both branches; they do not establish a communication benefit.

At R2, both alternative voters instead give communication 4/8 versus self-revision 6/8. This is a descriptive contrast among inspected alternatives, not an independently confirmed advantage for self-revision. The central finding remains that retaining and aggregating correct minority answers matters, while more correct individual communication responses do not reliably become more collectively solved questions.

## Recommended next stage

Run one development confirmation using the selected strict-schema profile, before validation/test. Freeze the current three voters, the two thresholds, the four fixed-round controls, and the analysis before generating responses. Collect each communication and self-revision trajectory through R3 once, with a shared initial ten-agent panel, then replay every policy on those traces. Voters and stopping decisions are not fed into the prompts, so six combinations do **not** require six generation experiments. Full trajectories are needed to detect later corrections that an early stop would miss.

Use the **twelve unused development questions**, `full-v1-{family}-development-03/-04/-05`: three per family, **840 unique calls** at seventy per question. They span eight structural groups, only four of which are structurally new. Each family's `-03` is a new numerical instance of an inspected moderate structure; `-04/-05` are two variants of one new hard structure. The four new structures are the three-color urn, four-source sensor querying state zero, algebraic mixture, and average travel speed with a pause. No exact prompt/parameter matches were found against the format-followup tasks.

This is fresh numerical confirmation with limited structural expansion, and it emphasizes moderate/hard cases. It is useful for detecting missed recoveries or confidently wrong answers; its aggregate stopping rate need not match the easier eight-case pilot. Report the new versus previously inspected structures separately, alongside all twelve cases.

The existing twenty-question development bank also contains eight numerically inspected regression questions; it must not be described as twenty untouched cases. If collecting standardized full development coverage immediately, generate all twenty for **1,400 unique calls** and distinguish the eight regression cases from the twelve fresh cases in the report. Prefer making this confirmation part of that versioned development stage, with any reuse explicitly audited, rather than adding repeated pilots. Validation and test remain untouched.

Report paired gains/losses, overall accuracy, coverage, wrong delivered answers, incorrect early stops, correct early answers later lost, incorrect early answers later corrected, stop rounds, tokens, request time, and results by family/group. Compare each adaptive policy with both its same-voter R3 baseline and fixed-round alternatives. More seeds can assess variability on a structure but do not add independent structural groups.

Keep original plurality/global-round selection as the primary design. Treat new voting/stopping policies as prespecified secondary candidates unless a separately versioned selection procedure is frozen before validation. If choosing among these candidates on validation, specify the candidate set, cost objective, tie rule, and control comparator first; lock the choice before test. Do not train a learned stopper, alter thresholds against these eight cases, require communication to win before advancing, or add another format/model intervention to this confirmation.

After this bounded confirmation, proceed to validation/test if the implementation, evidence and cost measurements are complete. An unfavorable communication outcome is a valid result. The existing full-study runner still uses an older plain-JSON profile and requires a newly versioned implementation of the selected schema, revision prompts and explicit truncation policy before it can run this study.

## Reproduce the audit

```powershell
Set-Location D:\ML1-project
.\run_offline_comparison.ps1 -AnalyzeRun results/offline-comparison/pilot-v1
```

The audit requires no Ollama service. It verifies existing evidence and makes no new generations.
