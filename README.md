# When More Agents Do Not Mean More Evidence

**Redundancy and Error Propagation in LLM Debate** — an initial ML course project proposal and a small, local experiment scaffold.

## Proposal

**Research question:** When does communication between local LLM agents improve answers, and when does it amplify shared mistakes or count repeated evidence more than once?

More agreeing agents do not necessarily provide more independent evidence. We will study communication under controlled conditions, compare it with simpler baselines, and test a modest source-accounting intervention. The project aims for defensible comparisons; it does not assume that debate helps or claim a new method before running the experiments.

The study has three connected parts:

- **Communication versus simpler baselines:** compare a single answer, self-revision, independent answers, and one round of communication. Later work will add additional independent sampling and targeted critique under matched budgets.
- **Paired error propagation:** replay the same initial answers in each branch. Measure correction, **G** (initially wrong → finally correct), and corruption, **H** (initially correct → finally wrong). The net change is **Δ = G − H**, using the same denominator for both rates. Report transitions alongside overall accuracy.
- **Evidence accounting:** give agents noisy binary clues with explicit source IDs. Compare discussion of repeated evidence with a prompt that accounts for each authoritative source once. Repeated mentions of a clue are not new observations.

### Tasks and evaluation

1. **Probability and counting:** generated questions with exact answers and automatic checking. The starter accepts a numerical probability within 0.001 of the answer; the eventual study should freeze and justify this tolerance.
2. **Noisy binary clues:** a hidden binary state, a specified prior, and conditionally independent clues from identifiable sources. Given known clue reliability, the reference posterior is computed analytically: posterior log odds equal prior log odds plus the likelihood contribution of each **unique** clue. Agents report a probability; we measure binary decision accuracy, Brier score, and absolute deviation from the exact posterior. Calibration analysis follows once enough trials are available.

Use roughly 50 questions to debug prompts and choose settings, then freeze a development set and evaluate on several hundred held-out questions. Keep variants of one underlying question in the same split. Quantify uncertainty at the question level; agents and prompt variants for one question are not independent samples. Record model versions, prompts, sampling settings, runtimes, and token counts where available.

Useful comparisons must account for compute as well as accuracy. Communication uses extra calls and longer contexts, so this starter's branches have different budgets. Budget-matched additional sampling, repeated trials, stronger statistical analysis, and a complete held-out evaluation remain follow-up work.

## Experiment 1: one-round communication pilot

**Question:** Starting from the same independent answers, does one revision round repair errors or cause agents to abandon correct answers? This first runnable experiment combines the proposal's baseline comparison, paired answer-transition analysis, and noisy-clue task. It uses one already-trained local model; it does not train or fine-tune anything.

An **agent** is a separate call to the same model with its own conversation history and sampling seed. Three agents do not require three model downloads or three Ollama servers. They receive the same task and instructions, initially without any peer messages. Their errors can still be correlated.

### What happens for each question

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

### Exactly which tasks are generated

Tasks alternate between two families. Odd positions are urn questions with randomly chosen red/blue counts; they alternate between an unconditional and conditional probability calculation. Even positions are four noisy sensor observations about a hidden binary state. Each clue has a unique ID and reliability selected from 0.6, 0.75, or 0.9. The prior probability of either state is 0.5, and unique observations are conditionally independent given that state.

With `--questions 4 --seed 42`, the references are:

| Position / task ID suffix | Task | Reference answer |
| --- | --- | --- |
| 1 / `0000` | 12 red, 3 blue; draw two without replacement; probability both are red | `22/35` ≈ 0.628571 |
| 2 / `0001` | Sensors S1=(0, 0.9), S2=(0, 0.6), S3=(1, 0.6), S4=(0, 0.9); pairs mean (observation, reliability) | P(Y=1)=`1/82` ≈ 0.012195; sampled hidden state is 0 |
| 3 / `0002` | 8 red, 2 blue; probability both are red given at least one is red | `7/11` ≈ 0.636364 |
| 4 / `0003` | S1=(0, 0.6), S2=S3=S4=(0, 0.9); those three IDs are distinct sources | P(Y=1)=`2/2189` ≈ 0.000914; sampled hidden state is 0 |

All agents see the same unique clues initially. Communication adds **no new observations**. Repeating S1 is not independent evidence, while distinct S2/S3/S4 remain independent even if their values agree. The reference posterior adds each unique clue's log-likelihood contribution once. These four questions test wiring and output format; both evidence questions happen to have state 0, so they are not a balanced evaluation.

### Scoring and what to compare

- **Reasoning accuracy:** a parsed probability is correct when its absolute error from the reference is at most 0.001. Fractions and decimal strings are accepted.
- **Evidence decision accuracy:** classify Y as 1 when the reported probability is at least 0.5, otherwise 0, then compare with the sampled hidden state. This is distinct from reproducing the posterior. For example, 0.1 and 1/82 both predict state 0 on task 2, but their posterior errors differ.
- **Evidence probability quality:** save each agent's Brier score `(p - hidden_state)^2` and absolute posterior error `abs(p - reference_posterior)`. Lower is better.
- **Panel decisions:** evidence tasks use binary majority voting. Reasoning tasks group probabilities rounded to three decimals, take the largest group, and score the median of that group's original probabilities. A tied vote or all-invalid panel abstains and counts as incorrect. Invalid individual answers count as failures and abstain from voting; they are not silently dropped from accuracy denominators.
- **Correction G and corruption H:** for each branch/question, G is the number of wrong→correct agent transitions divided by **all three agents**; H is correct→wrong divided by **all three agents**. Thus revised individual accuracy minus initial individual accuracy equals G−H. These are not conditional rates divided only by initial mistakes or successes. `ensemble_G` and `ensemble_H` are analogous 0/1 transitions relative to the initial panel decision.

Compare communication with `independent_voting` and `self_revision`, inspect G/H, and check token use alongside accuracy. Analyze the two task families separately. The console reports combined panel accuracy only; per-family summaries, aggregate G/H, confidence intervals, and calibration curves are not computed automatically.

The `source_dedup` intervention changes both the repeated-table presentation and verification instructions. It therefore tests that combined prompt, not an isolated causal effect of deduplication. Private evidence subsets, controlled repetition sweeps, matched budgets, and multi-round debate are planned extensions. Four questions cannot establish that a method wins.

## Run Experiment 1 locally, step by step

Each teammate installs the model on their own computer. GitHub stores the code; model weights and experiment outputs remain local. No Codespaces, hosted inference account, API key, Python package installation, or virtual environment is required for this standard-library starter.

### 1. Install the prerequisites and start Ollama

- Install [Python](https://www.python.org/downloads/) **3.10 or newer** and [Git](https://git-scm.com/downloads).
- Install [Ollama](https://ollama.com/download) using the Windows/macOS installer. For Linux, follow the [official Linux instructions](https://ollama.com/download/linux).
- Open the Ollama application. If it is not already serving requests, run `ollama serve` in a separate terminal and leave that terminal open. If the port is already in use by Ollama, keep the existing service; a second server is unnecessary.

The scripts connect to **your own computer** at `http://127.0.0.1:11434`. Allow approximately 2 GB of model storage for Qwen, plus runtime and temporary space. 8 GB RAM is a reasonable starting point for these small sequential runs; 16 GB is preferable. A GPU is optional, but CPU runs can be slow. The setup helper installs model weights through Ollama, not the Ollama application itself.

### 2. Get the code and verify your tools

In Terminal on macOS/Linux or PowerShell on Windows:

```sh
git clone https://github.com/GavinHuang0/ML1-project.git
cd ML1-project
ollama --version
```

If you already cloned the repository, enter that folder and run `git pull --ff-only` instead of cloning again. Run all following commands from the `ML1-project` folder.

On **macOS/Linux**, check `python3 --version`. On **Windows**, check `py -3 --version`. Confirm Python is at least 3.10. If your installation uses `python` instead, substitute that working command throughout.

### 3. Download Qwen and make one smoke-test request

For the first experiment, only **`qwen2.5:3b`** is needed. The first download needs internet access; once installed, these local models can run offline.

macOS/Linux:

```sh
python3 setup_models.py --models qwen2.5:3b --smoke
python3 setup_models.py --models qwen2.5:3b --check
```

Windows:

```powershell
py -3 setup_models.py --models qwen2.5:3b --smoke
py -3 setup_models.py --models qwen2.5:3b --check
```

The first command downloads the model, confirms it is installed, and asks "What is 2 + 2?". It prints a structured answer and explanation. Inspect that answer yourself: the smoke check validates response format, not mathematical accuracy. The `--check` command does not download or generate anything. You can also run `ollama list` to see the installed tag. Leave Ollama running for the experiment.

### 4. Preview the questions, then run the pilot

macOS/Linux:

```sh
python3 run_experiment.py --dry-run --questions 4 --seed 42
python3 run_experiment.py --model qwen2.5:3b --questions 4 --agents 3 --seed 42 --output results/experiment1-qwen-seed42.jsonl
```

Windows:

```powershell
py -3 run_experiment.py --dry-run --questions 4 --seed 42
py -3 run_experiment.py --model qwen2.5:3b --questions 4 --agents 3 --seed 42 --output results/experiment1-qwen-seed42.jsonl
```

The dry run prints the generated tasks and reference answers, makes **zero model calls**, and writes no results file. The second command performs the **60 real generations**. Expect a `Completed 1/4: ...` message only after all 15 calls for the first question finish, then progress for the remaining questions. Calls run sequentially and unload the model after each request, so reloading adds latency. Runtime depends on hardware; there is no fixed minutes-to-completion promise.

| Setting | Default / tutorial value | Meaning |
| --- | --- | --- |
| `--model` | `qwen2.5:3b` | One local model for all agents in this run |
| `--questions` | 4 | Total questions across both alternating families |
| `--agents` | 3 | Choose 3 or 5; more agents mean more calls |
| `--seed` | 42 | Task generation and deterministic per-question sampling seeds |
| `--temperature` | 0.7 | Stochastic answer generation |
| `--max-tokens` | 256 | Maximum generated tokens per call, including the JSON answer and explanation |
| `--timeout` | 300 | Seconds allowed per experiment HTTP request, not the entire run |
| Context size | 4096 | Fixed in the client; no CLI flag |
| `--output` | Path shown above | New JSONL file; its parent directory is created automatically |

Revision seeds are matched across branches for each agent, and the same seed reproduces the task set. Identical model responses across different hardware or Ollama/model versions are not guaranteed.

### 5. Read the result and confirm completion

After finishing, the console prints the output path and `ensemble_accuracy` for all six methods. Accuracy 0.75 means three of these four questions had correct panel decisions; it is not a statistically reliable performance estimate.

Open `results/experiment1-qwen-seed42.jsonl` in a text editor. Each line is a JSON object. A complete four-question run has **six lines**:

1. `type: "metadata"`: model tag and installed model metadata/digest, Ollama version, run settings, and time.
2. Four `type: "question"` records: original task and references, `initial` responses, `single` and `independent_voting` metrics, `initial_budget`, and each `conditions` branch's `revised`, `metrics`, and `total_budget`.
3. `type: "complete"` with `questions_completed: 4`.

For example, inspect `conditions.justifications.metrics.G`, `.H`, `.ensemble.correct`, and, on evidence questions, `.brier_scores` and `.posterior_absolute_errors`. `initial` and `revised` entries retain `raw` model responses, parsed predictions, `parse_error`, and elapsed request time. Original task prompts are saved; revision prompts are constructed by the versioned code from those tasks and initial answers.

Each branch's `total_budget` includes the three initial and three revised calls. **Do not sum these branch budgets to estimate actual run cost**, because that counts the shared initial panel four times. Input/output tokens come from Ollama's reported counts; missing counts are `null`. Elapsed request time includes model loading and generation.

The file must end with the `complete` record before being treated as a completed run. A timeout, connection error, or interruption leaves partial output without that marker. Malformed prediction content inside a valid Ollama response is recorded as an answer failure and the experiment continues; malformed API responses stop the run. Output files are never overwritten: choose a new filename for another run, or omit `--output` to get a unique timestamped file under `results/`.

### Optional: compare Llama or scale the pilot

To compare **`llama3.2:3b`**, download it and run the same questions/settings in a separate file (on Windows, replace `python3` with `py -3`):

```sh
python3 setup_models.py --models llama3.2:3b --smoke
python3 run_experiment.py --model llama3.2:3b --questions 4 --agents 3 --seed 42 --output results/experiment1-llama-seed42.jsonl
```

This remains a same-model panel within each run, not a mixed-model debate. Running `setup_models.py --smoke` without `--models` downloads **both** defaults from `config/models.json`. Custom tags must refer to downloaded local weights; obvious cloud tags are rejected, but renamed cloud aliases cannot be identified from their names.

After inspecting the tiny pilot's raw answers, use `--questions 50` for a larger pilot: that makes **750 generation calls** with three agents. Use a new result file and retain comparable settings across models. A smaller `--questions 2` run makes 30 calls. Development/held-out splits and their uncertainty analysis still need to be implemented before drawing research conclusions.

### Troubleshooting and offline checks

| Symptom | Action |
| --- | --- |
| Python/Ollama command not found | Install the prerequisite, open a new terminal, and verify the command; use the Python invocation appropriate to your OS. |
| Cannot reach local Ollama | Open the Ollama app or start `ollama serve`; the required endpoint is local port 11434. |
| Model missing | Run the setup command with the exact tag passed to `--model`. |
| Existing output file | Choose another filename or omit `--output`; do not overwrite earlier results. |
| Slow CPU or timeout | Begin with two questions; increase the experiment's `--timeout`, e.g. `--timeout 600`. Setup smoke requests have a separate 180-second timeout. |
| Many invalid/truncated answers | Inspect raw responses and parsing errors; try `--max-tokens 512` in a new pilot and keep that setting consistent across comparisons. |

To run the offline tests, use `python3 -m unittest discover -s tests -v` on macOS/Linux or `py -3 -m unittest discover -s tests -v` on Windows. They use simulated inference and a local test HTTP server, so they do not install models or establish real-model accuracy.

## Teammate workflow

Clone this repository, install Ollama, and run the setup commands on each computer. Commit code and reviewed documentation through normal Git branches and pull requests. Keep model weights and generated results out of Git; share chosen experiment artifacts separately when the team needs to review them. Pin the model and experiment settings before comparing runs across machines.

No results are claimed yet. The first milestone is a reproducible pilot that establishes which local models can follow the task format and whether the paired comparisons reveal useful correction and corruption patterns.
