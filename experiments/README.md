# Experiment index

| Experiment | Question | Protocol | Code | Artifact status |
| --- | --- | --- | --- | --- |
| 1. Communication pilot | Does one revision round repair errors or corrupt correct answers, and how does source accounting change it? | [Full protocol](communication_pilot/protocol.md) | [Runner](communication_pilot/run.py) | Pilot reported complete; original logs and exact three-Qwen roster awaiting registration |

Each experiment owns a folder and a full `protocol.md`. Shared task generation, scoring, and inference are in `llm_debate/`; general commands are in `scripts/`. The top-level README links common installation and the project proposal.

## Standard experiment record

| Step | Required record | Git policy |
| --- | --- | --- |
| Design | `protocol.md`: objective, model roster, counts, parameters, prompts, sequencing, seeds, metrics, comparisons, exclusions, limitations | Track |
| Question selection | `question-selection/`: rules and frozen tasks/manifests, including split assignments when implemented | Track synthetic tasks and rules |
| Pilot testing | `pilot/raw/`: original model logs; `pilot/summaries/`: artifact index, summaries, settings decisions | Ignore raw; track index and reviewed summaries |
| Evaluation | `results/raw/`: evaluation logs; `results/summaries/`: artifact index and analysis outputs | Ignore raw; track index and reviewed summaries |
| Interpretation | `interpretation.md`: findings, evidence links, uncertainty, limitations, follow-up decisions | Track |

Raw logs are ignored because they grow with every generation. They still require separate backups or shared artifact storage. Preserve checksums and references in tracked indexes. Compact reviewed tables and plots belong in `summaries/`; full generations belong in `raw/`. Neither pilot summaries nor the protocol are ignored.

## Adding another experiment

Start from [_template/protocol.md](_template/protocol.md) and [_template/interpretation.md](_template/interpretation.md). Give the experiment a descriptive folder name and add it to the table above. Create the question-selection and stage directories using the layout above; put experiment-specific executable code in that folder. Record the exact models and sample counts before new runs, and retain prior protocol versions in Git when settings change.

For completed historical runs, describe the known original settings from metadata, mark missing details explicitly, and distinguish a retrospective record from a protocol fixed before data collection. Registration of an existing log does not rerun inference or modify it.
