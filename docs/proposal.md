# Project proposal

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


## Experiment records

See [the experiment index](../experiments/README.md) for implementations, protocols, and artifact status.
