# Targeted expression-instruction follow-up

This is a new development experiment following the completed Windows format pilot. That pilot improved eligibility from 45/80 to 71/80 with the lexical schema, but both profiles answered the same 3/8 questions correctly. The schema missed the frozen technical screen by one eligible output and one calculator failure. Preserve the original run and decision.

The new comparison tests one appended expression-completeness instruction. It does not test a stronger model, a mathematical scaffold, or communication.

## What changes

| Profile | System instruction | Response format |
| --- | --- | --- |
| `strict_schema` control | Original calculator instruction | Existing lexical JSON schema |
| `complete_expression` candidate | Original instruction plus the paragraph below | Identical lexical JSON schema |

The appended paragraph is:

> Before returning JSON, make expression a complete, finite arithmetic expression consistent with your explanation. Write every multiplication with *. Do not use assignments, ellipses, implicit multiplication, or unfinished operators. Check balanced parentheses and include an operand on both sides of every binary operator.

The control and candidate use the same question, per-agent seed, `llama3.2:3b`, temperature 0.7, 1,024 output tokens, 16,384-token context, and `keep_alive=0`. Pair order alternates. Both use the same schema pattern, `^[0-9.()+*/ -]{1,1000}$`; it still allows malformed arithmetic. The calculator remains the final execution gate. Raw generations are saved before evaluation, with no repair, retry, or extraction from explanation text.

## Fixed questions and budget

Run both sets in the same experiment, with no prompt changes between sets:

| Set | Questions | Calls | Role |
| --- | --- | --- | --- |
| Regression | The eight inspected Stage-A questions | 160 | Descriptive checks on known failure cases |
| Screening | Eight newly generated numerical variants, two per family | 160 | Prespecified profile recommendation |
| Total | 16 | 320 | Two profiles times ten agents per question |

The screening questions use the same eight mathematical structures as the regression questions. Their `group_id` values therefore remain shared. They are fresh numerical variants, not a structural holdout or a generalization test. All tasks are development data; no validation/test question is used for inference. The deterministic builder rejects duplicate prompts/parameter sets and independently checks exact references using enumeration, symbolic substitution, or dimensional balance. Reference answers and metadata never enter model messages.

## Decision fixed before inference

Apply these rules only to the eight screening questions, with 80 outputs per profile:

1. A technical pass requires at least 72 eligible outputs and at most four calculator failures.
2. The candidate must have no more than one fewer collectively correct question than control.
3. Recommend the candidate if it meets both requirements and control fails technically or has fewer eligible outputs. Otherwise retain control if it passes technically. Control wins eligibility ties.
4. If neither qualifies, stop and review a new proposal. Do not adjust thresholds after observing results.

These are development point-estimate screens, not statistical noninferiority tests. Eligibility requires valid fields, successful calculator execution, and a probability in range when relevant. Collective answers use exact-rational plurality; ties/no eligible values abstain and count incorrect. Correctness remains exact equality. Explanation length is reported separately. Regression outcomes cannot replace or be pooled into the screening denominator. Eight related panels are not eighty independent accuracy trials.

The report includes both sets separately, individual and collective correctness, paired question gains/losses, execution and probability failures, abstentions, token counts, and measured call time. A recommendation does not launch or silently change another experiment.

## Windows command

Open Ollama with `llama3.2:3b` installed. From `D:\ML1-project` in PowerShell, preview and then run:

```powershell
.\run_format_followup.ps1 -DryRun
.\run_format_followup.ps1
```

The launcher finds a working Python 3.10+ interpreter, including the installed Codex runtime when available. It does not install packages. Its default destination is `results/format-followup/windows-v2`, which must be new. To select an interpreter or destination explicitly:

```powershell
.\run_format_followup.ps1 -Python C:\path\to\python.exe -OutputDir results/format-followup/my-run
```

With a working Python launcher, the equivalent direct command is:

```powershell
py -3 run_format_followup.py --output-dir results/format-followup/windows-v2 --timeout 600
```

Press Ctrl+C once and wait for `paused`. Resume in the same directory with unchanged code, configuration, hardware, model, and runtime:

```powershell
.\run_format_followup.ps1 -Resume
```

The first interrupt saves the current returned call; completed calls are audited and skipped on resume. Pause hours are excluded from active timings. A second interrupt can lose an in-flight reply. Do not edit the experiment while paused. A second terminal can request a pause with `.\run_format_followup.ps1 -Pause`.

The completed report is `results/format-followup/windows-v2/summary.json`. Offline reanalysis verifies the saved calls, source/input hashes, calculator evaluations, and summary without contacting Ollama or changing evidence:

```powershell
.\run_format_followup.ps1 -AnalyzeRun results/format-followup/windows-v2
```

New files are [runner](../run_format_followup.py), [configuration](../config/format_followup.json), [task manifest](../config/format_followup_tasks.json), and [task builder/auditor](../build_format_followup_tasks.py). No real inference is required to prepare or test them.

## What communication versus self-revision will test later

After choosing and freezing a delivery profile, generate ten initial responses per question once. Copy that identical round-0 panel into two branches:

| Round | Communication branch | Self-revision branch |
| --- | --- | --- |
| 0 | Shared ten initial answers | The same ten initial answers |
| 1 | Each agent sees its own answer and all nine peers' previous explanations, expressions, and calculator results/failures | Each agent sees only its own previous answer and calculator result/failure |
| 2 and 3 | Repeat using the completed previous round in this branch | Repeat using the completed previous round in this branch |

The original question remains visible in every call. Updates are synchronous: all round-2 prompts use round 1, so an agent cannot see another agent's just-generated round-2 answer. Calls can still execute sequentially. No reference answer or correctness feedback enters either branch. These are separate generations of one model, not ten independently trained models.

Use the same aggregation and exact scoring after every round. Compare each branch against round 0 and compare branches at the same round count. If communication outperforms self-revision, that is evidence that access to peers helps beyond another attempt with one's own work. If both improve similarly, extra revision is a plausible explanation. If communication loses correct answers, inspect harmful convergence. A pilot gives exploratory evidence, not a definitive causal or general-accuracy conclusion.

Each question needs ten shared initial calls plus 30 communication and 30 self-revision calls: 70 unique calls, or 560 for eight questions. Audited reuse of a compatible selected screening panel could reduce additional calls to 480. The two branches match generation counts but not token/time budgets: peer prompts are longer, and actual costs must be reported. Additional independent sampling under the same token budget remains a later control.

The targeted format runner implements neither branch. Stage B needs a separately versioned runner with the selected prompt/schema and verified initial-panel import. The full 7,000-call study remains a later step; validation selects a global round count before held-out test evaluation.
