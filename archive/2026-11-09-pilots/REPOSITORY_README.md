# Llama posterior experiment

All active experiments use **only `llama3.2:3b` with a 1024-token output cap**. The original unassisted and calculator protocols score sensor correctness by absolute posterior error of at most **0.001**, rather than a state decision at 0.5. The unassisted protocol is `llama-1024-posterior-v2`. The separate multiple-choice protocol below uses exact option identity and does not replace those workflows or scores.

Earlier experiments, code, reports, raw responses, and their original scores are preserved in the [legacy archive](archive/2026-10-24-legacy/README.md). The archive includes the latest Llama interpretation and a checksum inventory. It is separate from the active workflow.

## Install and check

Install Python 3.10 or newer and [Ollama](https://ollama.com/download), then open Ollama or run `ollama serve`. This project uses the Python standard library; no Python packages are required. Run these commands from the repository directory. On Windows replace `python3` with `py -3`.

```sh
python3 setup_models.py
python3 setup_models.py --check
```

The installer downloads only Llama 3.2 3B. An optional connectivity/format check is `python3 setup_models.py --check --smoke`; it uses one additional generation at the same 1024-token cap. Model weights stay outside Git.

## Preview and run

```sh
python3 run_pilots.py --dry-run
python3 run_pilots.py
```

The preview does not contact Ollama or write files. The real command runs the following profiles sequentially, all with Llama at 1024 tokens:

| Profile | Setup | Calls |
| --- | --- | --- |
| `full` | Four original probability questions, three agents, four revision branches | 60 |
| `urn-check` | Two original urn questions, original and checking prompts, one agent | 4 |
| `diagnostic` | Eight arithmetic, construction, full-solution, algebra, and units items; two prompts, one agent | 16 |
| `all` (default) | All three profiles | 80 |

For one profile:

```sh
python3 run_pilots.py --pilot diagnostic
python3 run_pilots.py --pilot full
```

New raw JSONL files, summaries, and a run manifest are saved in a unique directory under `results/runs/`. Choose a new directory explicitly with `--output-dir results/runs/my-run`. Existing directories are refused. A failure or interruption preserves partial output and stops the sequence; check the manifest and completion markers before interpreting a run. New outputs remain ignored until deliberately selected for versioning.

`--model llama3.2:3b` and `--max-tokens 1024` are accepted for compatibility; every other model or token limit is rejected before inference. The old token-limit profiles are available only in the archive. Context is 4096 tokens, temperature is 0.7, and the default per-request timeout is 300 seconds. Increase `--timeout` if needed without changing the model or token limit.

## Sensor correctness

An individual sensor probability is correct only when:

```text
abs(predicted_posterior - exact_posterior) <= 0.001
```

Sensor panels use the median valid posterior estimate and apply the same tolerance. There is no conversion to a state label for headline accuracy, corrections, corruptions, or panel correctness. For example, reporting 0.25 is wrong when the exact posterior is approximately 0.012195.

The new rule is recorded as scoring version `posterior-v2` in raw metadata and summaries. Historical decision-based scores have not been relabeled. The [protocol](docs/PROTOCOL.md) specifies aggregation, invalid answers, prompts, settings, and all scoring contracts.

## Inspect and validate results

The first complete run under the current protocol is documented in the [November 6 results](docs/RESULTS.md). It completed 80 calls; the report distinguishes posterior accuracy, answer-format failures, and repeated historical response texts.

Full-profile files can be independently checked without model calls. Use a new output filename:

```sh
python3 analyze_results.py results/runs/YOUR_RUN/full1024.jsonl --output results/runs/YOUR_RUN/full1024.recheck.json
```

The unassisted analyzer requires its matching protocol and rejects historical files. Single-agent summaries are written by the suite using their numeric/expression scorers. Raw answers remain available for manual inspection; correct numbers in explanations do not replace a required final-answer field. In these unassisted profiles, gold answers are used only after generation, and no calculator, retries, or correctness feedback are supplied to the model.

The complete prompts and frozen single-agent cases are in [config/pilots.json](config/pilots.json). Full-pilot prompt construction is in [run_experiment.py](run_experiment.py). To run the unassisted full experiment directly while retaining the fixed model and cap:

```sh
python3 run_experiment.py --questions 4 --agents 3
```

## Template experiment

The separate [template and bounded-explanation experiment](docs/TEMPLATE_EXPERIMENT.md) compares the existing prompt with an explicit JSON template and a 60-word explanation limit. It uses 12 fresh questions and eight regression items, with one matched-seed call per prompt condition: 40 calls in total, all Llama at 1024 tokens. Its scores distinguish required fields, final-answer mathematics, strict correctness, and prompt compliance.

```sh
python3 run_template_experiment.py --dry-run
python3 run_template_experiment.py
```

The completed comparison improved fresh valid answers from 3/12 to 11/12 and strict correctness from 1/12 to 5/12. Mathematical behavior remained mixed, and only 12/20 treatment responses obeyed the 60-word limit. Read the [results and qualifications](docs/TEMPLATE_EXPERIMENT.md#results-on-november-6-2026) before treating the candidate as a general reasoning improvement. The original suite's prompts remain unchanged.

## Calculator-assisted mode

The separate [calculator-assisted protocol](docs/CALCULATOR_PROTOCOL.md) has Llama return an arithmetic expression and uses exact code execution to produce the numerical answer. It retains the same model/token cap and records planning-format, execution, and numeric errors separately. The prepared eight-question development pilot is available with:

```sh
python3 run_calculator_pilot.py --dry-run
python3 run_calculator_pilot.py
```

The [first calculator pilot](docs/CALCULATOR_RESULTS.md) completed eight calls: all responses supplied both fields, five expressions executed, and three computed answers were correct. Its computed answers are labeled separately from the unassisted results. The report distinguishes wrong formulations from unsupported syntax and does not treat this known-case pilot as an isolated calculator-benefit estimate.

The separate [expression-syntax experiment](docs/CALCULATOR_SYNTAX_EXPERIMENT.md) compares that frozen prompt with a clearer numeric-only format contract and generic syntax examples. It uses eight fresh questions and the eight original calculator regression cases, with one matched-seed call per condition, for 32 calls. Calculator execution and scoring are unchanged.

The completed [syntax comparison](docs/CALCULATOR_SYNTAX_EXPERIMENT.md#results-on-november-6-2026) improved fresh executability from 6/8 to 7/8 but left fresh correctness at 4/8; regression executability stayed at 5/8. Some targeted errors disappeared while other unsupported forms appeared. The original calculator prompt remains the baseline.

```sh
python3 run_calculator_syntax_experiment.py --dry-run
python3 run_calculator_syntax_experiment.py
```

## Exact-fraction multiple-choice experiment

The independent [multiple-choice design](docs/MULTIPLE_CHOICE_EXPERIMENT.md) uses the same sixteen questions from the syntax comparison, each with fifteen distinct exact-fraction options. Review the [complete question bank and author answer key](docs/MULTIPLE_CHOICE_QUESTION_BANK.md). One agent returns a brief explanation and an A-O choice, with one call per question and no calculator or revision stage. This is a different answer-selection task, identified as `mc-exact-v1`; all questions are previously inspected, and sensor scoring uses exact choice rather than the earlier tolerance.

```sh
python3 run_multiple_choice_experiment.py --dry-run
python3 run_multiple_choice_experiment.py
```

The first [sixteen-call run](docs/MULTIPLE_CHOICE_EXPERIMENT.md#results-on-november-7-2026) completed with **1/16 correct**, fifteen valid choices, and one truncated response. Several explanations derive the correct number but select the wrong option. Results use the separate `results/multiple-choice/` namespace. The existing suite, template, calculator pilot, and syntax comparison remain available through their own commands.

## Repository layout

| Location | Purpose |
| --- | --- |
| [docs/PROTOCOL.md](docs/PROTOCOL.md) | Current prompts, procedure, posterior correctness, and limitations |
| [docs/NEXT_STEPS.md](docs/NEXT_STEPS.md) | Next proposed experiments |
| [docs/TEMPLATE_EXPERIMENT.md](docs/TEMPLATE_EXPERIMENT.md) | Frozen template comparison design and results |
| [docs/CALCULATOR_PROTOCOL.md](docs/CALCULATOR_PROTOCOL.md) | Planning-plus-calculator procedure, scoring, and future comparison policy |
| [docs/CALCULATOR_RESULTS.md](docs/CALCULATOR_RESULTS.md) | Verified calculator pilot outcomes and failure interpretation |
| [docs/CALCULATOR_SYNTAX_EXPERIMENT.md](docs/CALCULATOR_SYNTAX_EXPERIMENT.md) | Frozen prompt-clarification comparison and results |
| [docs/MULTIPLE_CHOICE_EXPERIMENT.md](docs/MULTIPLE_CHOICE_EXPERIMENT.md) | Separate exact-choice prompt, procedure, and scoring |
| [docs/MULTIPLE_CHOICE_QUESTION_BANK.md](docs/MULTIPLE_CHOICE_QUESTION_BANK.md) | Sixteen reviewable questions with fifteen options each and an author key |
| [config/](config/) | Fixed model and frozen single-agent prompt/task cases |
| [results/](results/README.md) | Current results location and recording policy |
| [archive/2026-10-24-legacy/](archive/2026-10-24-legacy/README.md) | Preserved previous experiments, code, reports, and checksums |
| [tests/](tests/) | Offline tests using simulated inference and a local HTTP fixture |

Run the current offline tests with:

```sh
python3 -m unittest discover -s tests -v
```

The tests do not install models or establish real-model accuracy. These small inspected development cases are not a held-out benchmark; read the protocol limitations before drawing conclusions.
