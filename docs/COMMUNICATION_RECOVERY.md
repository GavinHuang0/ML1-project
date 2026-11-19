# Communication pilot: explicit truncation recovery amendment

The recovery is complete and independently reanalyzed: all 480 revision records and the saved summary reproduce. At round 3, communication solved 4/8 questions versus 5/8 for self-revision, with 3.07 times the revision tokens. The inherited truncation was counted ineligible, and no additional truncation occurred. [Full interpretation and next steps](COMMUNICATION_RESULTS_V2.md). The frozen amendment below remains preserved.

The original [communication/self-revision pilot](COMMUNICATION_PILOT.md) stopped after saving 146 raw responses and 145 evaluated answers. Call index 145, the easy sensor question in self-revision round 2 for agent 2, repeated its explanation until `eval_count=1024` and `done_reason="length"`. The JSON string was unfinished and no expression was delivered. The largest admitted context budget in the saved prefix was 8367, below 16384; this was output truncation, not context overflow or a calculator error.

The old schema guard correctly stopped v1. Unchanged `-Resume` would evaluate the same saved malformed response and stop again. V1 is preserved unchanged in its operational directory and in [the failed-run archive](../archive/2026-11-17-communication-pilot-v1-failed/README.md).

## Amendment fixed before continuing

V2 changes only handling of a narrowly identified output truncation:

| Returned response | V2 treatment |
| --- | --- |
| Complete response conforming to the strict schema | Evaluate exactly as v1 |
| Invalid JSON, `done_reason="length"`, and exactly 1024 generated tokens under the unchanged cap | Record one ineligible `invalid_json` answer; no calculator attempt, expression extraction, JSON repair, or regeneration |
| Other schema nonconformance, including parseable JSON that violates the schema | Preserve raw evidence and stop |
| Incomplete transport wrapper or context saturation | Preserve available evidence and stop, as before |

All model requests remain governed by the original frozen generation protocol: same question/round/agent positions, per-position seeds, peer shuffle, common revision system instruction, strict schema, model digest, runtime/hardware identity, temperature 0.7, output cap 1024, context 16384, and `keep_alive=0`. Both branches apply the same amended failure handling. No output limit is increased, and no failed call is retried. Subsequent prompts receive the normal structured invalid status and null unavailable fields; unfinished raw text is not converted into an explanation or expression.

This is an explicit **post-failure protocol amendment**, not completion under v1's original stop-on-schema-failure policy. All pilot conclusions remain exploratory. Retain and report the truncation as an observed system failure, including its incurred tokens/time. Do not select a favorable round or remove difficult questions.

## Audited reuse and budget

V2 independently checks v1's source/configuration/evidence hashes, imported initial panel, canonical prompts built from preceding-round snapshots, and all 145 evaluated answers. The first 146 raw records, first 145 answer records, and 80 initial records are copied byte for byte to a **new output directory**. V2 evaluates response 146 locally as invalid JSON, then resumes generation at call index 146.

| Evidence / work | Count |
| --- | ---: |
| Shared initial answers, retained in both trajectories | 80 |
| Revision responses already generated in v1, all retained | 146 |
| Local evaluation of the truncated response | 1, with no model request |
| Additional model requests needed | **334** |
| Completed revision records across both attempts | 480 |
| Unique model generations including original initialization | 560 |

The original directory is not modified. A source/evidence/model/runtime/hardware mismatch stops continuation rather than silently replacing evidence. The new manifest identifies the amendment, source v1, imported prefix, original format-pilot parent, and both historical and newly incurred costs. Summaries distinguish 146 imported revisions from 334 newly generated revisions, rather than describing all 480 as new calls in this continuation.

## Commands

With Ollama running, in PowerShell:

```powershell
Set-Location D:\ML1-project
.\run_communication_recovery.ps1 -DryRun
.\run_communication_recovery.ps1
```

Default source: `results/communication-pilot/windows-v1`. Default new destination: `results/communication-pilot/windows-v2`, which must not already exist. The launcher selects a working Python 3.10+ interpreter; no additional packages are required.

Explicit equivalent:

```powershell
py -3 run_communication_recovery.py --source-run results/communication-pilot/windows-v1 --output-dir results/communication-pilot/windows-v2 --timeout 600
```

Press Ctrl+C once and wait for `paused`. Resume **v2** with:

```powershell
.\run_communication_recovery.ps1 -Resume
```

Keep old and new evidence, source/configurations, hardware, model, runtime, and paths unchanged while running or paused. Completed responses are audited and skipped; returned raw responses are evaluated locally on recovery. A second Ctrl+C can lose an in-flight response. Schema violations outside the explicit truncation exception remain fatal.

Offline reanalysis:

```powershell
.\run_communication_recovery.ps1 -AnalyzeRun results/communication-pilot/windows-v2
```

The completed `summary.json` reports rounds 0–3 and the prespecified round-3 communication-minus-self-revision comparison, paired eight-group uncertainty, execution/formulation/aggregation diagnostics, output truncations, and cost splits. It does not grade hidden reasoning or choose a validated optimal communication round.

The new [recovery runner](../experiments/communication_pilot/recovery.py), [analysis](../experiments/communication_pilot/recovery_analysis.py), and [configuration](../config/communication_recovery.json) sit alongside the unchanged v1 modules. No original source, recorded response, or score is rewritten to make the failed v1 pass.
