# Experiment 1: one-round communication pilot

**Question:** Starting from the same independent answers, does one revision round repair errors or cause agents to abandon correct answers? This first runnable experiment combines the proposal's baseline comparison, paired answer-transition analysis, and noisy-clue task. Each run uses one already-trained local model for its entire agent panel. Comparing three Qwen models means three separate model runs, not assigning one model to each of the three agents. No model is trained or fine-tuned.

## Record status and actual model roster

The experiment owner reports that the pilot has already been generated using three Qwen models. The completed logs are not available in this checkout. Their exact tags, question counts, repeated-trial counts, and realized settings must be recovered from the existing JSONL metadata before describing the numerical comparison.

This file documents the implementation available in this checkout and its defaults. It is a retrospective organization of the protocol, not evidence of preregistration. If an existing run used different code or settings, record that difference with its artifacts rather than relabeling it as conforming to this file.

| Item | Known record | Source or next step |
| --- | --- | --- |
| Model roster used in completed pilot | Three Qwen models, exact tags awaiting artifacts | Experiment owner; import logs into `pilot/` |
| Questions and repeated runs per model | Awaiting artifacts | Metadata `settings.questions`, separate completed files |
| Completed pilot status | Reported complete; files absent from checkout | [Pilot artifact record](pilot/README.md) |
| Current runner's default tag | `qwen2.5:3b` | `run.py` |
| Legacy download defaults | `qwen2.5:3b`, `llama3.2:3b` | `../../config/models.json`; not a completed-run roster |

Register each original pilot file with `python3 -m scripts.register_results FILE --stage pilot`. The tracked `pilot/summaries/runs.json` then records exact model tags, settings, completed question counts, source checksums, and panel accuracies. Aggregate multiple files per model only after checking that their question sets and settings are comparable. Count questions separately from agents and generation calls.

An **agent** is a separate call to the same model with its own conversation history and sampling seed. Three agents do not require three model downloads or three Ollama servers. They receive the same task and instructions, initially without any peer messages. Their errors can still be correlated.

## What happens for each question

The procedure and table below use the default three-agent panel. With five agents, the same branches run for all five agents.

1. Generate a synthetic task and compute its reference answer in Python. Ground truth is retained for evaluation and is not sent to the agents.
2. Ask three agents for independent initial answers. Each must return JSON such as `{"final_answer":"22/35","explanation":"12/15 times 11/14."}`. The first agent supplies the single-response baseline; the panel supplies the independent-voting baseline.
3. Replay that **same initial panel** under four separate revision conditions below. Each agent sees the original problem, its own original response, and the condition's revision prompt. Peers are anonymized and shown in a shuffled order that is held fixed across conditions for that agent.
4. Score every initial and revised answer, aggregate the panel decisions, and save responses, errors, token counts, and timings.

Each revision is based only on the **initial** responses. Agents never see another agent's revised response, and one branch never consumes another branch's results. Calls execute sequentially, but this is a single synchronous revision round, not a sequential conversation that accumulates revisions.

| Result key | What is used or shown | Generation calls per question for this method, with 3 agents |
| --- | --- | --- |
| `single` | First agent's initial answer | 1; already part of the initial panel |
| `independent_voting` | Aggregate all three initial answers; no communication | 3 |
| `self_revision` | Each agent checks its own answer with no peers; aggregate the three revisions | 6: 3 initial + 3 revised |
| `answers_only` | Each agent sees the other two initial final answers, without their explanations | 6 |
| `justifications` | Each agent sees the other two initial answers and explanations; on clue tasks, each peer's same source table is repeated | 6 |
| `source_dedup` | Same peer answers and explanations, without extra source tables; instructions say agreement is not new evidence, identify an error before changing, and count each source ID once | 6 |

The executable shares the initial panel, so the actual run uses **3 + 4 × 3 = 15 generations per question**, or **60 for four questions**. The baselines do not trigger additional calls. With five agents, it uses 25 generations per question. Branches have different input lengths; these are **not token-budget-matched comparisons**. Additional independent sampling at the debate budget remains future work.

## Exactly which tasks are generated

Tasks alternate between two families. Odd positions are urn questions with randomly chosen red/blue counts; they alternate between an unconditional and conditional probability calculation. Even positions are four noisy sensor observations about a hidden binary state. Each clue has a unique ID and reliability selected from 0.6, 0.75, or 0.9. The prior probability of either state is 0.5, and unique observations are conditionally independent given that state.

With `--questions 4 --seed 42`, the references are:

| Position / task ID suffix | Task | Reference answer |
| --- | --- | --- |
| 1 / `0000` | 12 red, 3 blue; draw two without replacement; probability both are red | `22/35` ≈ 0.628571 |
| 2 / `0001` | Sensors S1=(0, 0.9), S2=(0, 0.6), S3=(1, 0.6), S4=(0, 0.9); pairs mean (observation, reliability) | P(Y=1)=`1/82` ≈ 0.012195; sampled hidden state is 0 |
| 3 / `0002` | 8 red, 2 blue; probability both are red given at least one is red | `7/11` ≈ 0.636364 |
| 4 / `0003` | S1=(0, 0.6), S2=S3=S4=(0, 0.9); those three IDs are distinct sources | P(Y=1)=`2/2189` ≈ 0.000914; sampled hidden state is 0 |

All agents see the same unique clues initially. Communication adds **no new observations**. Repeating S1 is not independent evidence, while distinct S2/S3/S4 remain independent even if their values agree. The reference posterior adds each unique clue's log-likelihood contribution once. These four questions test wiring and output format; both evidence questions happen to have state 0, so they are not a balanced evaluation.

## Scoring and what to compare

- **Reasoning accuracy:** a parsed probability is correct when its absolute error from the reference is at most 0.001. Fractions and decimal strings are accepted.
- **Evidence decision accuracy:** classify Y as 1 when the reported probability is at least 0.5, otherwise 0, then compare with the sampled hidden state. This is distinct from reproducing the posterior. For example, 0.1 and 1/82 both predict state 0 on task 2, but their posterior errors differ.
- **Evidence probability quality:** save each agent's Brier score `(p - hidden_state)^2` and absolute posterior error `abs(p - reference_posterior)`. Lower is better.
- **Panel decisions:** evidence tasks use binary majority voting. Reasoning tasks group probabilities rounded to three decimals, take the largest group, and score the median of that group's original probabilities. A tied vote or all-invalid panel abstains and counts as incorrect. Invalid individual answers count as failures and abstain from voting; they are not silently dropped from accuracy denominators.
- **Correction G and corruption H:** for each branch/question, G is the number of wrong→correct agent transitions divided by **all agents in the panel**; H is correct→wrong divided by **all agents in the panel** (three by default, or five when selected). Thus revised individual accuracy minus initial individual accuracy equals G−H. These are not conditional rates divided only by initial mistakes or successes. `ensemble_G` and `ensemble_H` are analogous 0/1 transitions relative to the initial panel decision.

Compare communication with `independent_voting` and `self_revision`, inspect G/H, and check token use alongside accuracy. Analyze the two task families separately. The console reports combined panel accuracy only; per-family summaries, aggregate G/H, confidence intervals, and calibration curves are not computed automatically.

The `source_dedup` intervention changes both the repeated-table presentation and verification instructions. It therefore tests that combined prompt, not an isolated causal effect of deduplication. Private evidence subsets, controlled repetition sweeps, matched budgets, and multi-round debate are planned extensions. Four questions cannot establish that a method wins.

## Run settings and sampling

These are executable defaults. Registered metadata is authoritative for an already-generated run.

| Setting | Default | Meaning |
| --- | --- | --- |
| `--model` | `qwen2.5:3b` | Same model for all agents in one run |
| `--questions` | 4 | Total questions, alternating across both families |
| `--agents` | 3 | Separate model calls; allowed panel sizes are 3 and 5 |
| `--seed` | 42 | Shared base for question generation and response sampling |
| `--temperature` | 0.7 | Stochastic response sampling |
| `--max-tokens` | 256 | Output-token limit per response, including explanation |
| `--timeout` | 300 | Seconds per HTTP request |
| Context size | 4096 | Fixed client option |
| Response format | JSON | String `final_answer` and string `explanation` required |
| `--stage` | `pilot` | Default artifact directory; `results` is later evaluation |
| `--output` | Unique timestamped path | Optional explicit destination; never overwritten |

Question generation uses Python's `random.Random(seed)`. For zero-based question index `i` and agent index `a`, initial response seed and peer-order seed are `seed + 100*i + a`; revision seed is `seed + 100*i + 50 + a`. Revision seeds and peer order are matched across conditions. Revisions use different prompts, so matched seeds do not imply identical responses. These seeds support repeatability; identical output across model versions, Ollama versions, or hardware is not guaranteed.

There is one initial panel and one revision per agent per branch per question. There is no automatic loop over repeated full trials. Changing the current `--seed` changes both question instances and response sampling. Therefore changing `--seed` alone does not measure sampling variance on a fixed question set. Separate question and response seeds or a frozen-task input would need to be implemented for that design.

For `Q` questions and `A` agents the physical run makes `5*A*Q` calls. Three models with 50 questions each and three agents would make 2,250 calls in total; that is an illustrative budget, not the confirmed budget of the completed pilot. For unequal runs sum `5*A*Q` across registered files.

## Prompt specification and implementation

The system instruction for all initial and revised calls is:

> Solve the user's probability problem. Return ONLY a JSON object with final_answer (a string containing a fraction or decimal probability between 0 and 1) and explanation (a concise, auditable calculation, citing source IDs when given). Do not write extra text outside JSON.

Each initial conversation contains that instruction and the generated task prompt. Each revision appends the agent's raw original response, followed by a revision request starting with:

> Check your previous calculation and revise only if warranted.

Self-revision adds “You have no peer messages.” Communication branches display other agents with anonymous labels in a shuffled order, preserving final-answer strings and, where specified, explanations. Invalid peer responses are displayed as “no valid structured answer.” `justifications` repeats the original source table once for each valid peer on evidence tasks.

The `source_dedup` branch adds:

> Agreement and repeated reports are not new observations. Before changing your answer, identify a specific calculation or assumption that was wrong.

For evidence tasks it also adds:

> Use each source ID exactly once from the UNIQUE observation table in the original problem. Everyone saw that same table.

The exact templates and sequencing live in [run.py](run.py). Task construction, posterior computation, answer parsing, and voting rules live in [benchmark.py](../../llm_debate/benchmark.py). The [Ollama client](../../llm_debate/local_llm.py) supplies local inference options and retains response metadata. Protocol revisions and code changes are versioned in Git.

## Question selection and stages

[Question selection](question-selection/README.md) specifies the generator, parameter ranges, and how to save a question manifest. Every generated task is included; current code does not filter by model success, deduplicate instances, enforce hidden-state balance, or implement development/held-out splits. Odd counts contain one more reasoning than evidence task.

The default four-question set is a wiring example. A roughly 50-question pilot was proposed for choosing settings; the actual completed counts come from logs. Keep pilot and later evaluation artifacts in separate stage folders. Before evaluating on held-out questions, document and implement the split, grouping variants of the same underlying problem. Increasing the question count with the same seed includes the old prefix, so that alone does not create a held-out set.

## Artifact contract and completion

A valid run has one metadata record first, one question record per task, and one completion record last. For `Q` questions, there are `Q+2` JSONL records. Completion requires `questions_completed`, `settings.questions`, and the number of question records to agree.

Metadata records the model tag, installed model metadata/digest, Ollama version, settings, and UTC creation time. New runs also include the experiment ID, protocol path, and SHA-256 of the protocol bytes. Older logs without protocol fields are marked as having unknown protocol provenance instead of being assigned the current protocol. A recorded path alone does not establish the protocol version; a checksum identifies the protocol text, not the executable code revision. Retain the matching Git code revision in collection notes.

Each question record saves its prompt, reference answers, initial responses, branch revisions, metrics, budgets, timings, and parse errors. Task prompts do not contain ground truth. Revision prompts can be reconstructed from the saved initial responses and matching source code; they are not separately stored in the legacy format.

Malformed prediction content is recorded as a failed answer without retrying. Inference failure, timeout, malformed API response, or interruption stops the run, leaving partial output without completion. Keep those partial files for diagnosis, but do not register them as completed runs. Files are opened exclusively and are never overwritten.

Keep original logs in `pilot/raw/` or `results/raw/` (ignored by Git). Registration copies existing logs byte for byte without deleting originals and creates a tracked index under the corresponding `summaries/`. See [pilot instructions](pilot/README.md) for completed pilot artifacts and [results instructions](results/README.md) for subsequent evaluation.

## Analysis and interpretation plan

Report all six methods for each model, treating model tags, panel size, question count, and number of repeated runs as separate dimensions. Compare branches on the same questions and shared initial panel within a model. Across models, verify the complete task records match, not just the question count; the registration index records `question_set_sha256` for this comparison. Files with the same source `sha256` are copies of one run, not independent repeated trials. Keep reasoning and evidence results separate in substantive analysis; combined accuracy is only a quick run summary.

Inspect invalid responses and abstentions, correction G and corruption H, probability quality on evidence tasks, and input/output tokens and latency. Do not count reused initial calls more than once when estimating physical run cost. The registration index summarizes completed-run panel accuracy; family-specific G/H, aggregate Brier scores, confidence intervals, and calibration curves need further analysis.

Uncertainty analysis should resample at the question level, keeping all agents and branches for a question together. Multiple agents answering one question are not additional independent questions. A repeated-trial design and budget-matched independent sampling are follow-up work. The existing communication conditions change context length and, for source deduplication, both presentation and verification instructions.

Record empirical findings and any setting decisions in [interpretation.md](interpretation.md), with links to the exact supporting run indexes and raw artifact checksums. Do not claim that debate wins or that deduplication alone caused a change from these pilot settings without the necessary analysis and controls.
