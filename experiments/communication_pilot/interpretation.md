# Communication pilot: interpretation

## Evidence status

The experiment owner reports a completed pilot involving three Qwen models. Original pilot files are not available in this checkout, so the exact model roster, realized settings, counts, and numerical results have not been verified here. This record does not infer results from tutorial defaults or simulated software tests.

Register the completed logs into [pilot/summaries](pilot/summaries/README.md). Preserve model digests and artifact checksums and note the original code/protocol version when known. Historical logs without provenance remain explicitly unknown.

## Findings

Awaiting registered artifacts and analysis. For each finding, link its run index, identify the model tag and task family, give question and repeated-run counts, and report the relevant accuracy, G/H, probability error, and budget evidence. Explain uncertainty and whether the comparison used the same questions and settings.

## Limits of the current design

- All agents within a run use the same model, so their errors may be correlated.
- Shared initial panels and matched revision seeds control some between-condition variation; they do not estimate variance across repeated full trials.
- Communication and self-revision use different context lengths. No token-budget matching or additional independent sampling at the debate budget is implemented.
- Source deduplication changes both repeated-table presentation and verification instructions, so its isolated causal effect cannot be identified here.
- Tiny tutorial sets are wiring checks. The generator does not enforce class balance or implement development/held-out splits.
- The registration index summarizes combined panel accuracy. Family-specific transitions, uncertainty intervals, and calibration still require analysis.

## Decisions and follow-up

No model ranking or final settings decision is recorded without the existing artifacts. After registration, record which settings to retain, why the pilot supports those choices, the next evaluation's question selection/split, and any deviations from the [protocol](protocol.md). Keep pilot-driven decisions separate from later held-out conclusions.
