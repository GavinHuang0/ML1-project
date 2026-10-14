# Experiment: <name>

## Objective and status

State the concrete research question and whether this protocol is prospective or reconstructed from existing artifacts.

## Models and run matrix

Record exact model tags/digests, questions per model, agents per question, repeated runs, question seeds, response sampling seeds, temperature, output/context limits, timeout, and expected generation/token budget. Distinguish models, agents, questions, and trials.

## Question selection

Describe generators/datasets, exact reference answers, inclusion/exclusion rules, duplicates and grouped variants, pilot/development/evaluation splits, and the frozen manifests under `question-selection/`.

## Procedure and prompts

Give full prompts or immutable references, call sequencing, branches and baselines, shared inputs, information each agent sees, seed matching, and the executable path.

## Scoring and comparisons

Define every metric and denominator, invalid-answer handling, aggregation and ties, paired comparisons, family-specific analysis, uncertainty estimation, and budget controls.

## Collection and artifact contract

Provide exact commands. Save original pilot and evaluation generations in `pilot/raw/` and `results/raw/`; retain metadata, completion markers, code/protocol provenance, and checksums. Track artifact indexes and reviewed summaries in each stage's `summaries/`. State retention/backups for ignored raw files.

## Interpretation and limitations

Link `interpretation.md`. State supported claims, unresolved confounds, deviations, and which decisions will be made from pilot versus evaluation data.
