# Completed five-agent and sparse ten-agent pilots

Recommend **five agents with all four peers versus matched five-agent self-revision** for the primary full research experiment. This is a pragmatic reduction in full-trajectory budget, not a validated optimal architecture or a demonstrated communication advantage. Preserve plurality and validation-based global round selection. Sparse ten-agent communication has a promising early-round result and is not uniformly inferior after considering endpoint costs.

For a practical system based only on these observations, five-agent self-revision is the more economical default: it achieves the same final correct count as five-agent communication while delivering fewer wrong answers. The research experiment should still compare both branches.

## Audit and comparability

Both completed runs independently reproduce their raw generations, calculator evaluations, canonical requests, seeds, peer routing, source/configuration hashes and JSON/CSV reports:

| Run | Unique generations | Branch/round summaries | Question/round rows |
| --- | ---: | ---: | ---: |
| [Five agents, four peers](../results/five-agent-pilot/windows-v1/summary.json) | 420 | 8 | 96 |
| [Ten agents, two peers](../results/sparse-peer-pilot/windows-v1/summary.json) | 840 | 8 | 96 |

Each run completed in one segment, using the same Llama3.2 digest, Ollama 0.40.16 and driver 621.24. Neither had an output-length stop. This interpretation adds no model generations and performs no declined counterfactual subset screen.

The common seed design produced exactly matching evidence here: the sixty common initial responses and 180 common self-revision responses have identical generation seeds, prompts, raw response text and evaluated responses across the two runs. Thus the five-agent initialization and self-revision trajectories actually are nested within the ten-agent evidence. Timing and other transport metadata are separate measurements; matching response text is not a claim that two executions are independent replicates.

All twelve questions and eight structural groups were previously inspected development data. There is one new seed panel per question, with related common-agent seeds across the two experiments. Validation/test remain untouched. The thirty-six rows in earlier policy grids were never independent experiments; here too, twelve questions and 1,260 calls do not create 1,260 independent accuracy observations. The two communication packages change both panel size and peer degree, so their difference cannot be attributed to either factor alone. Architecture choice is a development decision requiring held-out evaluation.

The [combined immutable archive](../archive/2026-11-18-architecture-pilots-v1/README.md) preserves both runs, their new sources/configurations, and verified references to earlier frozen dependencies. [Exact generation and routing definitions](ARCHITECTURE_PILOTS.md) remain unchanged.

## Collective trajectories

Current-round exact-rational plurality, with abstentions counted incorrect:

| Round | Five-agent communication | Five-agent self-revision | Sparse ten-agent communication | Ten-agent self-revision |
| --- | ---: | ---: | ---: | ---: |
| R0 | 0/12 | 0/12 | 1/12 | 1/12 |
| R1 | 2/12 | 1/12 | 3/12 | 1/12 |
| R2 | 2/12 | 0/12 | 3/12 | 1/12 |
| R3, pilot primary endpoint | **3/12** | **3/12** | **2/12** | **3/12** |

Five-agent communication and self-revision solve exactly the same final questions: rectangle `algebra-03`, tank `units-03`, and average speed `units-05`. There are zero paired gains or losses at R3. Its paired accuracy interval [0, 0] follows from identical observed correct-question outcomes; it does not prove equivalence on new questions.

Sparse communication at R3 has one exclusive success, average speed `units-05`, but loses the three-color urn `reasoning-04` and rectangle `algebra-03` that its self-revision control solves. The family-balanced communication-minus-self difference is −8.33 percentage points, with exploratory paired eight-group bootstrap interval [−33.33, +8.33] points. Sparse R1/R2 instead show a +16.67-point difference, with interval [0, +25]. These intervals summarize the inspected development groups, with numerical variants resampled together; they do not select a test-optimal architecture or round.

Five-agent self-revision abstains on all twelve questions at R2 even though six individual responses are correct. Odd panel size does not eliminate plurality ties among multiple mathematical values, particularly with ineligible responses. Its R2 zero collective accuracy is not zero individual mathematical success.

## What communication changed

Five-agent communication quickly spreads correct information on two cases. The tank starts with one correct agent and reaches five of five correct at R1; average speed starts with two correct agents and also reaches five of five at R1. Self-revision eventually catches up collectively at R3.

The same mechanism also concentrates errors: both three-color urn variants become five of five wrong in communication R1 and remain wrong. Smaller ensembles therefore do not eliminate harmful agreement. At R3 there are two unanimous all-agent wrong panels and six wrong strict-majority panels in five-agent communication. Its self-revision branch has neither pattern at that round.

Sparse communication avoids a ten-of-ten wrong consensus in this run, but that is not a size-controlled comparison with the five-agent unanimity count. Ensemble size and peer connectivity both differ. It strengthens the correct average-speed answer to eight of ten agents by R3, while the control's two correct votes do not produce a unique winner.

The sparse mixture case `algebra-04` illustrates a later loss. It is correct at R1 and R2 through a unique two-vote plurality. At R3 both previously correct agents change to wrong answers; a different agent becomes correct, leaving one correct vote and a collective tie. Continuing discussion can erase an earlier success even with only two peers per recipient.

Every sensor question still has zero correct individual answers in every round in all four branch trajectories. These runs do not show that changing panel size or connectivity supplies the missing sensor formulation capability.

## Coverage and delivered errors

R3 outcomes need both accuracy and coverage:

| Branch | Correct | Answered | Wrong delivered | Abstentions |
| --- | ---: | ---: | ---: | ---: |
| Five-agent communication | 3 | 11 | **8** | 1 |
| Five-agent self-revision | 3 | 3 | **0** | 9 |
| Sparse ten-agent communication | 2 | 9 | **7** | 3 |
| Ten-agent self-revision | 3 | 6 | **3** | 6 |

Five-agent communication's equal final accuracy conceals substantially more delivered errors. Its self-revision control answers only three questions, all correctly on this sample. Three answered questions do not establish reliable conditional accuracy generally, and nine abstentions remain unsuccessful under the primary score.

Final individual correctness is five-agent communication 13/60 versus self-revision 10/60; sparse communication 17/120 versus self-revision 19/120. Communication's extra individually correct answers in the five-agent run do not yield an extra solved question.

Final five-agent communication has 56/60 eligible outputs: 13 correct, 43 executable wrong and four out-of-range probabilities. Sparse communication has 110/120 eligible: 17 correct, 93 executable wrong, one division by zero and nine out-of-range probabilities. Delivery eligibility is substantially higher than mathematical accuracy. These diagnostics score expressions, not the conceptual correctness of explanation text.

## Resource comparison

Tokens include input and output. Branch totals include initialization; physical experiment totals count the shared initial panel once.

| Full R0–R3 resource | Five-agent setup | Sparse ten-agent setup |
| --- | ---: | ---: |
| Communication tokens | 221,415 | 363,589 |
| Self-revision tokens | 123,227 | 252,901 |
| Communication / self token ratio | 1.80 | 1.44 |
| Physical paired experiment calls | **420** | **840** |
| Physical paired experiment tokens | **323,987** | **574,336** |
| Physical summed request seconds | 1,149.3 | 2,289.4 |

Five agents halve full-trajectory calls and use **43.59% fewer measured paired tokens**. Its communication branch uses 39.10% fewer tokens than sparse ten-agent communication. Within the five-agent run, self-revision uses **44.35% fewer branch tokens** than communication for the same final correct count.

Communication request time is only about 0.5% above its five-agent control and 0.9% above its ten-agent control. Loading accounts for about 69% of physical request time under `keep_alive=0`. These are summed model-request durations, not full study wall time, API prices, or equal-token-budget comparisons. Both architectures read twenty directed peer records per question/communication round, but the ten-agent setup makes twice as many generations and repeats the original question more often.

## Important endpoint caveat

Five agents are not uniformly better after selecting a round:

| Observed endpoint | Correct communication answers | Communication tokens | Communication request seconds |
| --- | ---: | ---: | ---: |
| Sparse ten agents, R1 | 3/12 | **146,151** | 652.5 |
| Five agents, R3 | 3/12 | 221,415 | 659.8 |

Both communication prefixes represent 240 logical calls, and they solve different question sets: sparse R1 solves the mixture instead of the five-agent R3 rectangle. Sparse R1's entire paired prefix is 360 physical calls and 215,456 tokens; five-agent R3's paired trajectories are 420 calls and 323,987 tokens. Thus the cheaper full-trajectory five-agent experiment is not a proven best deployment accuracy/cost frontier.

Five-agent self-revision R3 reaches three correct at 123,227 branch tokens, lower than either communication endpoint above, but with much lower coverage. Retain the round curves and use the held-out validation procedure. Do not declare sparse R1 or five-agent R3 the optimal endpoint from these inspected rows.

## Recommended full-study configuration

Use the following primary research comparison as an explicitly documented pre-validation amendment to the original ten-agent design:

- Five agents with all four peers in communication, versus five-agent self-revision with no peers.
- Identical shared initialization, matched agent seeds, identical generic revision instruction, paired synchronous scheduling and preceding-round history.
- The selected Llama model/digest, original calculator instruction, strict schema, exact scoring, explicit truncation policy and current environment.
- Current-round plurality; collect R0–R3 and select **one global round on validation** using a frozen accuracy/cost objective, then lock it before test and compare both branches at that round.

The reason for choosing five is lower full-trajectory experimental cost under uncertainty, combined with no observed final accuracy penalty relative to the sparse alternative. It is not proof that five agents maximize accuracy, that communication beats self-revision, or that an early sparse endpoint is inferior. Preserve the original ten-agent design and all completed evidence. Sparse ten-agent R1 remains a useful descriptive or separately prespecified secondary candidate; it should not silently replace the primary after viewing test results.

For the planned 100-question study, five agents require **3,500 unique full-trajectory calls** from scratch: 700 development, 1,400 validation and 1,400 test, compared with the original ten-agent 7,000-call design. An audited import of the 420 existing five-agent development calls could leave eight additional development trajectories (280 calls), then the validation/test calls. Such reuse is conditional on exact protocol, prompts, seeds, routing, environment and timing compatibility; it is not implemented by the current full-study runner.

Before inference, create a newly versioned full-study implementation. The old full-study runner still uses plain JSON, different revision prompts/scheduling and full-round wall-time cost calibration. These pilots use strict schema, generic matched revision instructions, paired scheduling and request-time measurements. Freeze a consistent timing objective/calibration before validation, rather than silently substituting request time for wall time. A negative communication result remains a valid outcome.

No additional pilot is required simply to obtain a favorable communication result. The deferred conversation-history idea remains deferred; the recommended study retains the tested immediately preceding-round history. None of these twelve-case development results is held-out validation of architecture selection.

## Reproduce the audits

```powershell
Set-Location D:\ML1-project
.\run_five_agent_pilot.ps1 -AnalyzeRun results/five-agent-pilot/windows-v1
.\run_sparse_peer_pilot.ps1 -AnalyzeRun results/sparse-peer-pilot/windows-v1
```

These commands make no model generations.
