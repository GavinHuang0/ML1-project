# Offline comparison of voting and stopping rules

**Completed:** `results/offline-comparison/pilot-v1` has been audited and archived. Read the [results and recommendation](OFFLINE_POLICY_RESULTS_V1.md). To verify that report, use `-AnalyzeRun` below; the default creation command refuses its already-existing destination.

This analysis reuses the completed communication/self-revision recovery traces. It makes **zero model calls**, requires no Ollama service, and never changes saved generations, evaluations, scores, or generation protocols. Its purpose is to prepare a comparison for later interpretation, not select a policy or automatically authorize another pilot.

The eight questions are inspected development data from eight structural groups. All candidates were specified after collecting those traces. Results are therefore **post-hoc exploratory**, not validation of a new voting rule or stopping policy.

## Run the comparison

In PowerShell:

```powershell
Set-Location D:\ML1-project
.\run_offline_comparison.ps1
```

The launcher finds Python 3.10+ automatically; the program uses the standard library. Its default source is `results/communication-pilot/windows-v2`. It first audits that completed run, its source/parent evidence, canonical model requests, evaluated responses, and reproduced summary. Default new output is `results/offline-comparison/pilot-v1`, which must not already exist.

Optional read-only preflight:

```powershell
.\run_offline_comparison.ps1 -DryRun
```

To choose a different report directory, preserving previous outputs:

```powershell
.\run_offline_comparison.ps1 -OutputDir results/offline-comparison/my-run
```

Equivalent direct Python command, if your `py` launcher works:

```powershell
py -3 run_offline_comparison.py --source-run results/communication-pilot/windows-v2 --output-dir results/offline-comparison/pilot-v1
```

The comparison is a short batch analysis with no inference to pause or resume. Existing destinations and protected input/archive paths are refused. Offline verification of a completed report:

```powershell
.\run_offline_comparison.ps1 -AnalyzeRun results/offline-comparison/pilot-v1
```

## Three voting rules

All rules use only eligible exact-rational calculator values. Equivalent fractions are the same value. Ineligible current responses cast no current vote. Scores use exact fractions, and tied highest scores abstain. No reference answer enters the voting rule.

| ID | Definition |
| --- | --- |
| `plurality` | One vote for each eligible agent's current-round value. Unique highest count wins. |
| `initial_anchored` | Score each value by its round-0 count plus its current-round count. Round 0 itself is counted once, not twice. The two panels have equal weight; this is not 20 independent pieces of evidence. |
| `agent_history` | For each agent, collect the distinct eligible exact values it produced from round 0 through the current round. That agent contributes a total weight of one, divided equally among those values. An agent with no eligible history contributes zero. Repeating one value does not add extra weight; a previously valid value can remain a candidate after a later invalid response. |

Anchoring may preserve useful initial evidence or retain an initial mistake. History pooling may reduce repeated-vote amplification or dilute a legitimate correction. These are hypotheses for comparison, not assumed improvements. Neither heuristic makes communicating agents statistically independent or certifies mathematical correctness.

## Two stopping rules and fixed-round controls

For each voting rule, the program computes the candidate answer using **only the observed prefix** through each completed round. Thresholds always count actual current agent votes out of the original panel of **ten**, not votes among only eligible agents and not pooled/history scores.

| ID | Decision |
| --- | --- |
| `high_agreement_8` | Stop at the first completed round, including round 0, where the selected voting rule has a unique answer and at least eight current agents support that answer. Otherwise continue through round 3. |
| `stable_majority_6` | Starting at round 1, stop when the selected voting rule returns the same unique answer in two consecutive completed rounds and that answer has at least six actual agent votes in each of those rounds. Otherwise continue through round 3. |

If no early stopping condition is met, return the selected voting rule's answer at round 3, including abstention when tied. A pooled candidate that differs from current strong consensus cannot use that consensus as evidence for stopping on the pooled answer. Agreement thresholds are heuristics, not probabilities of correctness.

Controls are `fixed_round_0`, `fixed_round_1`, `fixed_round_2`, and `fixed_round_3`. All three voting rules are evaluated with all six stopping/round policies in both branches:

**3 voters × (2 new stopping rules + 4 fixed-round controls) × 2 branches = 36 comparison rows.** There are 288 per-question policy decisions and 192 voting-rule/round predictions. Cross-branch and joint-cost summaries are descriptive; no row is designated the winner.

## What the outputs measure

| File | Contents |
| --- | --- |
| `summary.json` | Complete candidate definitions, all comparisons, per-question decisions/prefix predictions, paired uncertainty, cost contrasts and limitations |
| `comparisons.csv` | The 36 branch/voting/stopping summaries for convenient comparison |
| `per_question.csv` | The 288 decisions, including selected round, stop reason, answer, correctness, support and consumed costs |
| `run-manifest.json` | Frozen analysis/configuration identity, source/input/code hashes, source-audit status, output hashes and completion status |

Overall accuracy counts abstentions as incorrect, with all eight questions in the denominator. Coverage is the fraction receiving a non-abstaining answer. Answered-only accuracy is correct answers divided by answered questions, or undefined when none are answered. Report all three: selective abstention cannot create an overall accuracy gain by removing difficult questions from the denominator.

Comparisons include changes from the same voter's fixed-round-3 procedure and from the original plurality/fixed-round-3 control. They retain correct-question gains/losses, stop-round distribution, incorrect early stops, and initial-versus-revision resource use. References are used only after each decision is fixed to score correctness. No future-round information is used to choose a stopping point.

The `early_stop` and correct/wrong early-stop fields refer specifically to an adaptive rule that triggered before round 3. Fixed-round controls have no adaptive trigger; their earlier endpoints are represented by `stopped_before_maximum` and the stop-round distribution. Cross-branch contrasts compare the same voting/stopping policy in the two branches. Joint-cost rows count the shared initial panel once.

Intervals use 2000 deterministic paired, family-stratified whole-group resamples. The same sampled groups are shared across policies and branches. Eight groups are not 80 independent agents; narrow or degenerate intervals do not establish reliability. Where answered-only accuracy is undefined in a bootstrap draw, that is kept explicit rather than replaced by perfect accuracy.

## Counterfactual cost interpretation

Stopping is evaluated only after a complete ten-agent round. Every call in that round is charged. Costs include the shared initial panel and the observed prefix through the selected stopping round. The comparison does not assume partial-round savings, model-token early termination, or reinvestment of saved compute into other questions.

The full pilot has already been generated. These are **counterfactual prefix costs**, not newly realized savings. Recorded token counts identify the prefix's token use; summed historical model-request seconds estimate its request time, not a new latency benchmark or end-to-end wall time. They exclude human pauses and intervening calls of the other branch. Missing measurements remain unknown.

Each branch trajectory includes initial costs. Joint physical-cost summaries count that shared initial panel once rather than adding it twice. The source experiment has 80 shared initial generations and 480 revisions, or 560 unique generations. Creating this offline report adds zero generations.

## Scope of a valid replay

The saved prompts never received the collective voting result. Consequently terminal reaggregation and stopping the whole question after a completed round can be evaluated from these fixed traces. This analysis does not claim to evaluate changing the peer graph, pruning agents, adding judge calls, asking for confidence, feeding a new winner back to agents, or changing prompts. Those interventions would change future generations and require a new experiment.

The original primary plurality/global-round design remains unchanged. Use this report to inspect a bounded candidate set and decide later whether to prepare a separately versioned development pilot. Selection and claims of generalization must use new development/validation evidence and untouched test groups; the current eight cases do not establish a winner.

Implementation: [policy engine](../experiments/offline_policies/analysis.py), [frozen definitions](../experiments/offline_policies/protocol.py), [runner](../experiments/offline_policies/runner.py), and [configuration](../config/offline_policy_comparison.json). [Source pilot interpretation](COMMUNICATION_RESULTS_V2.md)
