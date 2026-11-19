# Original design, completed study, and follow-up priorities

Reviewed November 19, 2026 against the [shared experimental and mathematical specification](https://chatgpt.com/s/t_6afa1956baec8191b2c6d69d0c30935d), dated November 15, 2026. The shared page was accessible in the browser, although the web reader could not fetch it. Its distinction between agreed decisions, proposals and unresolved choices matters: not every extension mentioned there was a commitment for the first full study.

The [completed-study report](FULL_STUDY_RESULTS_V2.md), [frozen v2 procedure](FULL_EXPERIMENT.md), [original implementation protocol](MULTI_AGENT_PROTOCOL.md) and [experiment catalog](EXPERIMENT_CATALOG.md) supply the implementation and result evidence below. This review changes no experimental artifact, scoring rule or selected endpoint.

## What stayed consistent

The core question remains how many communication rounds justify their additional cost. We evaluated every fixed endpoint R0 through R3, calibrated costs on development data, selected one global endpoint on validation, and froze it before test. We did not learn a question-specific stopping policy or train model weights.

| Design component | Completed implementation | Status |
| --- | --- | --- |
| Planner plus deterministic calculator | Llama formulates explanation/expression; the calculator evaluates the explicit expression exactly once | Preserved; no expression repair or reference feedback |
| One underlying model with multiple sampled agents | Same pinned Llama3.2:3b artifact, temperature 0.7 and 1,024-token output cap | Preserved; these are correlated sampled trajectories, not independently trained models |
| Independent initialization and synchronous revision | All R0–R3 collected; each revision uses a completed preceding-round snapshot | Preserved; sequential physical execution does not create asynchronous information flow |
| Full communication content | Own preceding response plus peers' explanations, expressions, calculator values and failure statuses | Preserved; private answers/correctness never enter model prompts |
| Bounded history | Original question and immediately preceding round only | Adopted the proposed short-history policy; older history remains saved for analysis |
| Numerical answer determines correctness | Exact rational equality after delivery/eligibility checks; explanation mathematics ungraded | Finalized an originally unresolved scoring choice |
| Collective aggregation | Unique current-round exact-value plurality; ties/no eligible values abstain and count incorrect | Adopted after development comparisons |
| Shared initialization for controls | Communication and self-revision share the exact initial panel, with matched later seed positions | Implemented the recommended self-revision control |
| Cost-aware global selection | Family-balanced error plus 0.02 times an equally weighted normalized token/time penalty; ties prefer fewer rounds | Preference frozen before validation; initial cost excluded only from revision penalty |
| Separate evaluation stages | 20 development, 40 validation, 40 held-out test questions; 52 disjoint structural groups overall | Completed, with related numerical variants kept together |
| Reproducible evidence and uncertainty | Raw requests/replies, exact evaluations, identities, frozen artifacts, costs and paired family-stratified whole-group intervals | Completed; group resampling respects related variants |

The selected policy was **R0**. Validation communication accuracy was 13/40 at R0 and 14/40 at R3; R3's cost penalty outweighed that one-question gain. Locked test accuracy was 12/40. Equality between the two R0 branch labels is structural shared initialization, not proof that communication has zero effect. Secondary test R1–R3 results remain available and do not replace the primary.

## Choices that changed or became more specific

| Earlier design or open choice | Final choice | Reason and limit |
| --- | --- | --- |
| Ten agents as intended main configuration | Five agents, each receiving all four peers | Architecture pilots supported a pragmatic lower-budget choice, not proof five agents are optimal; full-study budget fell from the prepared ten-agent 7,000 calls to 3,500 |
| Plain JSON in the historical baseline | Strict JSON schema with the original calculator instruction | Format screening reduced delivery problems; the added expression-completeness instruction was tested and not adopted |
| Baseline context of 4,096 tokens | Multi-agent context frozen at 16,384 | Development admission checks accommodated peer messages; historical baseline settings/results were preserved |
| Tolerance and aggregation unresolved | Exact equality, required explanation/expression fields, unique plurality with abstention | Exact arithmetic makes tolerance unnecessary for this rational benchmark; missing/malformed delivery is distinct from an incorrect explanation |
| Execution time proposed as complete round elapsed time | Summed model-request seconds in v2 selection | Explicit pre-validation amendment: includes loading but excludes prompt construction, health checks, calculation and journaling; whole-study elapsed time reported separately |
| Penalty numbers proposed, not originally approved | Primary delta 0.02 and omega 0.5 frozen | An operating preference, not a statistically learned universally optimal resource valuation |
| Benchmark size/fifth family/splits unresolved | 100 questions across the original four families, split 20/40/40 | Expanded structures and numerical variants without adding a fifth category; forty test questions form twenty resampling clusters |
| General format/infrastructure failure handling | Narrow output-cap invalid-JSON exception kept as one ineligible response without repair/retry | Prospectively versioned recovery policy; other schema failures remain fatal and raw evidence is retained |

Model/runtime/hardware identities were pinned within each run. The earlier NVIDIA driver change was documented through a prospective environment amendment before the later experiments; it was not silently ignored. Earlier Mac/Windows results with different operating conditions remain separate development evidence.

## Extra options we tested during development

1. **Delivery and wording:** plain JSON versus lexical strict schema, then the original strict-schema instruction versus an added completeness instruction. We selected strict schema with the original instruction.
2. **Revision control and recovery:** communication versus own-response self-revision, including an explicitly versioned recovery from one truncated response. Saved replies were retained rather than regenerated.
3. **Three voters:** current plurality, initial-anchored voting, and per-agent distinct-answer history voting. These were first replayed on saved traces, then checked prospectively on twelve previously unused numerical development questions.
4. **Two adaptive heuristics:** stop on eight-of-ten current agreement, or on the same six-of-ten majority across two rounds. They were evaluated with all three voters and fixed-round controls. These are agreement heuristics, not learned stopping models. Consensus could be wrong, and alternative voting benefits did not transfer reliably.
5. **Architecture:** five agents/all four peers and ten agents/two randomly selected peers, each against matched self-revision. Sparse peers were sampled without replacement within a recipient's pair, using recorded seeds; pairs could repeat across rounds. The smaller all-to-all panel was selected for the full study.

These stages informed a frozen procedure before validation/test. They are not a held-out leaderboard of every model, voter, stopping rule and graph we tried. In particular, development screening does not establish the globally best architecture.

## Completed versus remaining

| Work item | Current status |
| --- | --- |
| Versioned model, calculator, schema, reference bank and scoring | Complete |
| Format/profile screening, recovery, voter/stopper confirmation and architecture pilots | Complete as development evidence |
| Fresh full-study development calibration, validation selection and held-out evaluation | Complete: all 3,500 calls and all three reports independently reproduce |
| Raw-evidence/source archive and results report | Complete; preserved in the [full-study archive](../archive/2026-11-19-full-study-v2/README.md) |
| Original ten-agent held-out full study | Superseded before inference; not a completed ten-agent held-out comparison |
| All three voters and both adaptive rules on final held-out data | Not included in frozen v2; completed only in development comparisons. An earlier confirmation recommendation mentioned a secondary grid, but the final v2 protocol retained only plurality and global round selection |
| Penalty sensitivity, break-even values and Pareto summary | Not supplied by the completed v2 report; useful remaining supplementary analysis of saved data |
| Mean numerical-error summaries | Not included in v2's accuracy/coverage diagnostics; could be supplemental with an explicit denominator/abstention convention |
| Answer-only communication ablation | Proposed in the original design, not run |
| Extra independent samples at a matched token budget | Strongly recommended original control, not run; equal call counts do not answer this efficiency question |
| Full-history communication/self-revision | Deferred and untested; see [history note](DEFERRED_CONVERSATION_HISTORY.md) |
| Learned adaptive stopping | Future extension, not part of the completed core study; requires separate training/evaluation design |
| Multiple random seed panels and model generalization | Not established by one panel per question and one final-study model |
| Final course paper/presentation | Results and methods are documented; a course submission still needs synthesis into the required format |

There is **no remaining model inference needed to complete frozen full-study v2**. Missing proposed controls and supplementary analyses should be reported honestly, without describing them as requirements that were secretly satisfied by other pilots.

## Recommended sequence from here

**First finish the analysis and write-up using saved evidence.** Add a clearly labeled supplementary validation sensitivity table over the originally recorded delta grid `[0, 0.01, 0.02, 0.05, 0.1]` and omega grid `[0, 0.5, 1]`, plus Pareto/break-even descriptions. Keep the frozen primary 0.02/0.5 selection untouched. We now know test outcomes, so any new test-policy analysis is exploratory rather than a newly prespecified endpoint. Include accuracy, abstentions and wrong delivered answers together: higher agreement or coverage alone is insufficient.

**Then audit a defined sample of explanations and revisions.** With a fixed annotation rubric, distinguish delivery rejection, wrong mathematical setup, expression transcription, explanation–expression inconsistency, loss of an initially correct answer, and correct-minority adoption. This needs no new model generation. The calculator already separates execution from formulation; manual annotation can sharpen the unresolved formulation categories. It does not retroactively change numerical scoring.

**For the next efficiency experiment, prioritize independent sampling at a matched token budget.** The current control isolates access to peers at matched generation counts. It does not show that discussion is preferable to spending its longer prompts' token budget on additional independent answers. Freeze a budget, allocation/overshoot rule and terminal voter before collecting new outcomes, count initialization once, and report actual budget use. This is the most direct missing control for a cost-efficiency claim.

In that new study, distinguish a fixed nonzero-round comparison of peer exposure from the validation-selected operating policy. Selecting R0 is a valid outcome of utility optimization, but its primary endpoint contains no peer exposure. Predeclaring these two questions separately would keep the next mechanism comparison informative even if its preferred operating policy again stops at initialization.

**For a mechanism follow-up, choose one intervention.** Answer-only versus explanation/expression/result communication is closest to the original proposed ablation and tests whether longer explanations earn their token cost. Alternatively, test short versus retained history at fixed five-agent routing, crossed with communication/self-revision. The latter is motivated by observed correct-to-wrong revisions, but must match message roles and define retained peer snapshots and context overflow prospectively. Do not change model, voter, graph and history simultaneously.

Use existing questions for development or stochastic-stability work only. All current validation/test outcomes are now inspected. A new confirmatory claim needs fresh held-out structural groups; extra seeds on existing questions measure stability conditional on those structures rather than fresh structural generalization. A stronger model, task scaffold or learned stopping policy can be a separate later study if the course goals justify it.
