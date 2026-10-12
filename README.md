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

## What the starter runs

The initial pilot uses fresh, independent responses from three or five instances of one selected model. It reuses that initial panel across a single self-revision round and three communication branches: answers only, answers with justifications, and source accounting. These are separate calls with the same starting answers, not a continuing conversation across branches. The single-answer and independent-panel outcomes provide initial baselines.

All agents initially see the same unique clues, so discussion supplies no new observations. The justifications branch repeats each peer's source list; the source-accounting branch refers back to the original unique observation table alongside the same peer answers and explanations. Sweeps over repetition counts and private evidence subsets are planned extensions. This pilot compares a combined source-accounting prompt with ordinary communication; it does not isolate deduplication from the other wording changes. Interpret the two task families separately.

Results include raw responses, parsed answers, correctness, generation timing and counts, individual G/H rates across paired agents, and ensemble G/H relative to the initial independent-panel decision. Evidence panels use majority binary voting; probability/counting panels use a plurality of probabilities rounded to three decimals, scored using the median original probability in the winning group. A tied panel abstains and counts as incorrect. Invalid answers count as individual failures and abstain from panel voting. Missing token counts are recorded as unknown. This is a runnable pilot, not a completed research framework or evidence that any branch performs better.

## Run on your own computer

This is a traditional GitHub repository. Each teammate clones the code and installs models on their own computer. GitHub stores code and documentation; model weights and experiment outputs stay local. No Codespaces, cloud model service, API key, or Python package installation is required.

You need:

- Python **3.10 or newer** and Git.
- [Ollama](https://ollama.com/download), installed and running locally.
- Approximately **2 GB of download/storage per default model**, plus runtime memory and temporary space. Sizes can change with model tags. **8 GB RAM** is a reasonable minimum for small, sequential pilots; **16 GB** is preferable. CPU execution can be slow; a compatible GPU is optional.

Install Ollama using its official Windows or macOS installer. On Linux, follow the [official instructions](https://ollama.com/download/linux); the documented installer command is `curl -fsSL https://ollama.com/install.sh | sh`. Review the official installation options before running it. The Python setup helper downloads models through an existing Ollama installation; it does not install Ollama itself.

```sh
git clone https://github.com/GavinHuang0/ML1-project.git
cd ML1-project
python --version
ollama --version
```

On Windows, `py` may replace `python`; on macOS/Linux, use `python3` if needed. If Ollama is not already running, start its desktop application or run `ollama serve` in a separate terminal.

Download the two starting models and run a short readiness check:

```sh
python setup_models.py --smoke
python setup_models.py --check
```

The defaults are **`qwen2.5:3b`** and **`llama3.2:3b`**. Start by evaluating them in separate runs; the starter is not a mixed-model debate. These are manageable local baselines, not guaranteed to solve every task. Model tags and licenses are maintained upstream. Downloading weights needs internet access; after installation, inference runs locally without hosted inference fees. Custom models via `--models`/`--model` must also be downloaded local weights. Obvious cloud tags are rejected; a renamed cloud alias cannot be identified from its name. Your computer still supplies the compute and electricity.

Run a tiny pilot:

```sh
python run_experiment.py --model qwen2.5:3b --questions 4 --agents 3 --output results/pilot.jsonl
```

Then run the other model using a separate output file:

```sh
python run_experiment.py --model llama3.2:3b --questions 4 --agents 3 --output results/llama-pilot.jsonl
```

Calls run sequentially, unloading the model after each request to keep memory use manageable. Reloading adds overhead; the four-question, three-agent pilot makes 60 calls. Use `--questions 2` for a shorter first run, or increase `--timeout` for a slow CPU. The context limit is 4096 tokens and `--max-tokens` defaults to 256. Model configuration, context length, and generated tokens affect cost; the same agent count does not imply the same compute budget. Output files are never overwritten; use a new filename for each run, or omit `--output` for a timestamped filename. A finished JSONL file ends with a `complete` record; a partial run has no such marker.

Check task generation and output handling without downloading or calling models:

```sh
python run_experiment.py --dry-run --questions 4
python -m unittest discover -s tests -v
```

Dry-run output contains generated tasks and reference answers, not model predictions. The tests use simulated inference and a local test HTTP server; real model inference must be checked on a computer with Ollama installed. Begin with small real pilots before increasing the number of questions. Retain raw responses, inspect answer parsing, and treat missing or malformed answers as failures rather than silently removing them.

## Teammate workflow

Clone this repository, install Ollama, and run the setup commands on each computer. Commit code and reviewed documentation through normal Git branches and pull requests. Keep model weights and generated results out of Git; share chosen experiment artifacts separately when the team needs to review them. Pin the model and experiment settings before comparing runs across machines.

No results are claimed yet. The first milestone is a reproducible pilot that establishes which local models can follow the task format and whether the paired comparisons reveal useful correction and corruption patterns.
