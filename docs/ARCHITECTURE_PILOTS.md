# Smaller-panel and sparse-peer architecture pilots

**Completed and audited:** five-agent communication/self-revision solve the same 3/12 final questions; sparse ten-agent communication solves 2/12 versus self-revision 3/12. Both raw runs and reports reproduce. Read the [results and full-study configuration recommendation](ARCHITECTURE_RESULTS_V1.md). The creation commands below preserve the original procedure; the completed default destinations now require the audit commands at the end.

Two separate development experiments compare communication with matched self-revision using the selected **original calculator instruction + strict JSON schema**. Both have completed. No offline subset screen preceded these experiments.

| Experiment | Communication branch | Self-revision control | Fresh model calls |
| --- | --- | --- | ---: |
| Five-agent pilot | Five agents, each seeing all four other agents | Five agents, each seeing only its own previous response | **420** |
| Sparse-peer pilot | Ten agents, each seeing two sampled peers | Ten agents, each seeing only its own previous response | **840** |

Each experiment generates initialization afresh, shares that exact initial panel between its two branches, and collects every round R0–R3. The experiments have separate configurations, manifests and output folders. They do not import earlier answers or require one another to complete. Running both requires **1,260 fresh generations**. Run them sequentially on the same Ollama service and machine.

## Commands

With Ollama running and the selected `llama3.2:3b` installed, run the five-agent experiment:

```powershell
Set-Location D:\ML1-project
.\run_five_agent_pilot.ps1
```

After that process exits, run the ten-agent sparse-peer experiment separately:

```powershell
.\run_sparse_peer_pilot.ps1
```

Default destinations are `results/five-agent-pilot/windows-v1` and `results/sparse-peer-pilot/windows-v1`. Fresh runs refuse an existing destination. Optional `-DryRun` prints the frozen plan without inference; it is a software preflight, not an offline comparison of saved outcomes. Both launchers find Python 3.10+ automatically and accept `-Python C:\path\to\python.exe`, `-Timeout`, and `-OutputDir` within the corresponding run namespace.

## Which two peers?

For **each question, communication round, and receiving agent**, sample **two distinct IDs uniformly without replacement from the other nine agents**. The receiving agent is excluded. Re-sample the pair independently for the next round; a peer used in an earlier round may be selected again. Sampling without replacement applies within the two-peer pair, not across all three rounds.

Routing uses a fixed, separate deterministic seed derived from the question ID, receiving agent ID and round. The chosen peer IDs and routing seed are recorded, so pause/resume and offline audit reproduce the same choices. The sampled order is also the presentation order. Peer labels in the prompt are anonymous; recorded IDs are for local audit.

Selection never uses the reference answer, correctness, eligibility, apparent confidence, explanation quality, or future responses. A sampled ineligible response is forwarded with its mechanical execution status rather than replaced. Different receiving agents can select overlapping peers. Links need not be reciprocal, and each agent need not be selected equally often: every receiver has exactly two incoming peer records, while the number of times an agent is selected can vary. This simple random routing policy is fixed before generation.

The five-agent condition uses IDs 0–4 and all four peers. The sparse-peer condition uses IDs 0–9. Those IDs are fixed without consulting outcomes. Generation seeds use a new shared architecture-pilot namespace: corresponding question/round/agent positions match between communication and self-revision, and the first five IDs are nested across the two experiments. The seed namespace differs from the completed confirmation. Fresh calls in separate experiments are retained as separate evidence; matching seeds are not a claim that independent runs are new structural observations or necessarily byte-identical.

## Questions and information flow

Both experiments use the same twelve development questions as the completed confirmation: `full-v1-{family}-development-03/-04/-05`, for reasoning, evidence, algebra and units. These are **already inspected questions**, now used for an architecture replication with fresh seed panels. They span eight structural groups; all eight have already been tested. They are not fresh questions or structural holdout. Validation/test remain excluded.

Initial calls are collected first, followed by question-major synchronous revision rounds with paired alternating branches. At each revision, both branches receive the original question, the same generic reconsideration instruction, and their own immediately preceding explanation, expression, exact calculator result and status. Communication additionally receives either all four peers or the two sampled peers from that branch's completed preceding round. No current-round response, reference answer, correctness flag, collective winner or future-round information enters prompts. Earlier history is not retained beyond the preceding response.

The selected model, temperature 0.7, output cap 1024, context 16384 and `keep_alive=0` remain fixed. Source/configuration hashes, model digest, Ollama version and the confirmation's driver-621.24 environment are bound and verified. The original prompt/profile and completed evidence remain unchanged.

The prospectively fixed truncation policy applies to initial and revision responses: a proven output-cap invalid-JSON response is one ineligible outcome with retained cost and no repair/retry. Other schema violations preserve raw evidence and stop. Supported expressions are evaluated once by the bounded exact-rational calculator; probability range gates remain unchanged.

## Outcomes and costs

Use **current-round exact-rational plurality**, with a unique leader required; ties/no eligible responses abstain and count incorrect. The experiments retain fixed rounds 0, 1, 2 and 3. They do not introduce new voters, adaptive stopping thresholds, judges or confidence fields. This isolates architecture changes from voting/stopping changes.

For five agents there are 60 shared initial generations and 360 revisions: **420 unique calls**. For ten agents there are 120 shared initial generations and 720 revisions: **840 unique calls**. Every complete trajectory represents (7N) unique calls per question across both branches, counting shared initialization once. Both architectures expose twenty directed peer records per communication round in total: five receivers ×four peers, or ten receivers ×two peers. This does not make their total tokens or number of generations equal.

Reports cover collective accuracy, coverage, individual correctness, eligible and failed outputs, vote concentration, changes over rounds, request times and tokens. Paired uncertainty resamples whole structural groups within families, keeping numerical variants together. Eight groups and one seed panel per question support exploratory comparisons rather than a validated architecture choice. No automatic winner is selected. Earlier ten-agent all-to-all results remain a separately recorded reference; conclusions about architecture must account for fresh seed panels and the different amounts of generated compute.

Each completed run produces `summary.json`, `comparisons.csv`, and `per_question.csv` beside its raw `generations.jsonl`, evaluated `answers.jsonl`, and `run-manifest.json`. Initial records have `arm="shared_initial"`; revisions identify their branch. Preserve the complete run folder.

## Pause, resume and audit

Press Ctrl+C once and wait for the active reply to be durably saved and the runner to report `paused`. Continue the same experiment and folder with:

```powershell
.\run_five_agent_pilot.ps1 -Resume
```

or:

```powershell
.\run_sparse_peer_pilot.ps1 -Resume
```

For a custom destination, pass the same `-OutputDir` when resuming. `-Pause` requests a cooperative pause from another terminal. A second Ctrl+C forces interruption and can lose an in-flight reply; durable returned replies are evaluated locally without regeneration. Source, model, environment and route changes are rejected on resume.

After each experiment completes, audit its saved evidence without Ollama:

```powershell
.\run_five_agent_pilot.ps1 -AnalyzeRun results/five-agent-pilot/windows-v1
.\run_sparse_peer_pilot.ps1 -AnalyzeRun results/sparse-peer-pilot/windows-v1
```

These commands verify completed evidence; they do not generate new responses or perform the declined offline subset screen. The [combined completed-run archive](../archive/2026-11-18-architecture-pilots-v1/README.md) preserves both runs, their new frozen sources and verified references to earlier dependencies.

Implementation: [protocol](../experiments/architecture_pilots/protocol.py), [runner](../experiments/architecture_pilots/runner.py), [analysis](../experiments/architecture_pilots/analysis.py), [five-agent configuration](../config/five_agent_pilot.json), and [sparse-peer configuration](../config/sparse_peer_pilot.json).
