# Local setup

Install [Python](https://www.python.org/downloads/) 3.10 or newer, [Git](https://git-scm.com/downloads/), and [Ollama](https://ollama.com/download). This standard-library project needs no Python package installation or hosted inference account.

Start the Ollama application, or run `ollama serve` in a separate terminal if no server is running. The client connects to your computer at `http://127.0.0.1:11434`. Each teammate downloads model weights on their own machine. Models can run offline after installation; weights remain outside Git.

## Get the repository

```sh
git clone https://github.com/GavinHuang0/ML1-project.git
cd ML1-project
ollama --version
python3 --version
```

If you already have the repository, enter it and use `git pull --ff-only`. Run the remaining commands from the repository root. On Windows, replace `python3` with `py -3`.

## Download or check models

Use the exact tags from the experiment's [protocol and registered run metadata](../experiments/communication_pilot/protocol.md). The original tutorial uses `qwen2.5:3b`:

```sh
python3 -m scripts.setup_models --models qwen2.5:3b --smoke
python3 -m scripts.setup_models --models qwen2.5:3b --check
```

`--smoke` asks “What is 2 + 2?” with seed 0, temperature 0, and a 128-token output limit. It checks structured-output parsing; inspect correctness yourself. `--check` only checks installed models. You can pass several tags after `--models`; `ollama list` shows installed tags and `ollama pull TAG` downloads one directly.

Without `--models`, setup uses [config/models.json](../config/models.json), whose legacy defaults are `qwen2.5:3b` and `llama3.2:3b`. They are download conveniences, not the three-Qwen roster reported for the completed pilot. No model weights are stored in this repository.

Allow approximately 2 GB of model storage for the tutorial Qwen tag, plus runtime and temporary space. 8 GB RAM is a starting point for small sequential runs; 16 GB is preferable. Larger tags require more resources. A GPU is optional, and CPU runs can be slow.

## Choose the experiment stage

Read the [full protocol](../experiments/communication_pilot/protocol.md) before generating new runs. For the already-generated pilot, follow [registration instructions](../experiments/communication_pilot/pilot/README.md) instead.

For a fresh tutorial run:

```sh
python3 -m experiments.communication_pilot.run --dry-run --questions 4 --seed 42
python3 -m experiments.communication_pilot.run --model qwen2.5:3b --questions 4 --agents 3 --seed 42 --stage pilot
```

These are tutorial defaults, not asserted settings of the completed pilot. All agents within this run use the one selected model. Compare different models using separate runs with the same question set and settings. A four-question, three-agent run makes 60 generations. A 50-question run makes 750. Calls execute sequentially and unload the model after each request. Progress appears after all 15 calls for a question complete; runtime varies with hardware.

The default output is a unique timestamped JSONL file under the selected stage's `raw/` directory. `--output PATH` selects an explicit filename; existing files are never overwritten. The runner prints the path and combined panel accuracies when finished. Register that file to create the tracked artifact index and summaries.

## Troubleshooting and tests

| Symptom | Action |
| --- | --- |
| Python/Ollama command missing | Install it, open a new terminal, and verify its version. |
| Cannot reach Ollama | Open the app or run `ollama serve`; the endpoint is local port 11434. |
| Model missing | Download the exact tag passed to `--model`. |
| Existing output file | Use another filename or omit `--output` for a unique one. |
| Slow CPU or timeout | Use a small pilot and increase `--timeout`, for example to 600 seconds. Setup smoke requests use a separate 180-second timeout. |
| Invalid/truncated answers | Inspect raw responses and parse errors; evaluate a larger `--max-tokens` value in a new pilot and document the change. |

```sh
python3 -m unittest discover -s tests -v
```

Tests use simulated inference and a local test HTTP server. They do not install models or measure real-model accuracy. The legacy root commands remain usable for teammates with older instructions.
