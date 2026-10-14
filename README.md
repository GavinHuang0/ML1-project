# When More Agents Do Not Mean More Evidence

Redundancy and error propagation in local LLM debate. We compare independent answers, self-revision, and communication using automatically checked probability and noisy-evidence tasks.

## Start here

| What you need | Where to look |
| --- | --- |
| Research question and proposed study | [Project proposal](docs/proposal.md) |
| Install Python/Ollama and download local models | [Local setup](docs/local-setup.md) |
| Experiments and their current status | [Experiment index](experiments/README.md) |
| Full communication-pilot design, settings, and comparisons | [Pilot protocol](experiments/communication_pilot/protocol.md) |
| How questions are selected and saved | [Question selection](experiments/communication_pilot/question-selection/README.md) |
| Already-generated pilot outputs and how to register them | [Pilot artifacts](experiments/communication_pilot/pilot/README.md) |
| Evaluation results and summaries | [Results](experiments/communication_pilot/results/README.md) |
| Findings, limitations, and decisions | [Interpretation](experiments/communication_pilot/interpretation.md) |

The pilot has been completed according to the experiment owner. Its files are not present in this checkout, so the exact three Qwen tags, run counts, and numerical findings await registration from those files. This repository's older download defaults are not a record of that completed pilot.

## Repository layout

```text
llm_debate/                      shared question generation, scoring, Ollama client
scripts/                         model setup and offline results registration
experiments/
  README.md                      experiment index and conventions
  _template/                     starting protocol and interpretation for a new experiment
  communication_pilot/
    run.py                       this experiment's executable
    protocol.md                  full procedure, settings, metrics, comparison limits
    question-selection/          selection rules and frozen question artifacts
    pilot/
      raw/                       original pilot JSONL outputs (ignored)
      summaries/                 tracked run index and reviewed summaries
    results/
      raw/                       later evaluation JSONL outputs (ignored)
      summaries/                 tracked run index and reviewed summaries
    interpretation.md            conclusions supported by registered results
config/models.json               legacy model-download defaults
docs/                           project proposal and common local setup
tests/                          offline software checks
```

## Commands

Run commands from the repository root. On Windows, use `py -3` in place of `python3`.

```sh
# Preview the tutorial question set; no model calls.
python3 -m experiments.communication_pilot.run --dry-run --questions 4 --seed 42

# Register an existing pilot; no model calls and no rerun.
python3 -m scripts.register_results /path/to/completed-pilot.jsonl --stage pilot

# Run offline software tests.
python3 -m unittest discover -s tests -v
```

Existing commands such as `python3 run_experiment.py` and `python3 setup_models.py` continue to work through compatibility entry points. The executable implementations are in the directories above. New runs default to `experiments/communication_pilot/pilot/raw/`; use `--stage results` for later evaluation or `--output` for a specific path.

## What belongs in Git

Track code, protocols, question-selection rules, frozen synthetic question sets, artifact indexes, reviewed summaries, and interpretation. Full model-response logs under either `raw/` directory, model weights, and the legacy root `results/` directory are ignored. Back up raw logs separately; Git does not preserve ignored files. A tracked index contains paths, checksums, settings, and summaries so collaborators know which original artifacts support a result.

Preserve existing pilot files. Registration copies them without modifying their contents and records settings from their metadata. It does not retroactively apply today's protocol to an older run.
