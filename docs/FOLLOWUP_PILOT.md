# Follow-up development pilot

The Windows Stage-A run is complete: strict-schema eligibility was 71/80 with five calculator failures, and both profiles answered the same 3/8 questions correctly. Neither passed this document's frozen screen. The next prepared experiment is the [targeted expression-instruction follow-up](FORMAT_FOLLOWUP.md); the Stage-A protocol and original runner below remain preserved.

Run this short diagnostic experiment before the full study. The completed Mac pilot had 46 calculator execution failures among 160 outputs; algebra's apparent improvement was a change in formatting eligibility, and sensors reached an incorrect consensus. Preserve those observations and the v1 protocol. The next pilot tests whether one explicit output constraint reduces delivery failures without obscuring mathematical errors.

## Stage A: paired format comparison, 160 calls

The frozen [pilot configuration](../config/followup_pilot.json) selects eight fresh development questions from [the synthetic benchmark](../config/full_benchmark.json): two questions from different structural groups in each family. Sensor cases include an easy single-source problem and a three-source problem. All validation/test questions remain unrun.

Each question receives ten initial answers in each of two profiles:

| Profile | Changed behavior |
| --- | --- |
| `baseline_json` | The existing Ollama `format: "json"` request |
| `strict_schema` | A JSON Schema object requiring the two string fields and constraining expression characters |

The schema uses `^[0-9.()+*/ -]{1,1000}$` for `expression`. Both profiles retain the identical system instruction, question, per-agent seed, `llama3.2:3b`, temperature `0.7`, 1,024-token output limit, 16,384-token context, and `keep_alive=0`. Pair order alternates to reduce simple ordering effects. The only intervention is the transport format. [Ollama structured output API](https://docs.ollama.com/capabilities/structured-outputs).

The constraint blocks letters and assignments. It does not establish balanced syntax, valid operator sequences, nonzero denominators, or correct mathematics. Calculator execution and exact-reference scoring are unchanged. No failed expression is repaired. The installed runtime's returned schema outputs are checked; nonconformance preserves raw evidence and stops the pilot rather than silently accepting an unsupported constraint.

For each profile, report eligible outputs, calculator errors, JSON/field validity, exact numerical correctness, and the unique plurality over each ten-agent initial panel. Report paired question gains/losses and family/group results. Eighty outputs from eight questions are not eighty independent accuracy trials.

## Prespecified screening rule

A profile passes the technical screen with **at least 72/80 eligible outputs** and **at most 4/80 calculator failures**. The schema candidate must also finish with no more than one fewer collectively correct question than baseline. These are development point-estimate screens, not statistical noninferiority guarantees.

Recommend the schema candidate if it clears those screens and either baseline fails the technical screen or the candidate has more eligible outputs. Retain baseline on ties if baseline passes. If neither qualifies, stop for a new, separately specified proposal. Never loosen exact equality or repair old expressions to make the pilot pass.

If format validity improves while the easy sensor question still has no correct initial answer, diagnose model capability separately before the communication study. A proposed reasoning scaffold or stronger model is a distinct intervention and needs a new development comparison. Prefer one controlled change at a time.

## Stage B: communication versus self-revision, after review

After interpreting Stage A, freeze the chosen profile and compare all-to-all communication with self-revision on the same eight development questions through rounds 0–3. Both arms share the exact ten initial outputs. This represents 560 unique calls; audited reuse of the chosen Stage-A panel would leave 480 additional calls, or 640 total across both stages. Without reuse, the total is 720 calls.

Stage B is the next planned experiment, not an automatic action of the Stage-A script. The current prepared full-study profile remains baseline JSON; adopting schema output requires a newly versioned profile and verified panel import first. Freeze those details after the Stage-A result. Do not pick questions because they favor discussion, and do not use held-out results for the decision.

The 100-question full-study template is prepared, with 7,000 calls including the self-revision control. Launch it only after these diagnostics justify a final protocol. Better delivery and stronger evidence are the goals; a benefit from communication remains a hypothesis to test.

## Launch, pause, resume

Follow the [Windows 11 setup guide](WINDOWS_RUN_GUIDE.md). In PowerShell from the repository root:

```powershell
py -3 run_followup_pilot.py --dry-run
py -3 run_followup_pilot.py --output-dir results/followup-pilot/windows-v1 --timeout 600
```

Press Ctrl+C once and wait for `paused` to save the current call. Resume later:

```powershell
py -3 run_followup_pilot.py --resume --output-dir results/followup-pilot/windows-v1 --timeout 600
```

The completed report is `results/followup-pilot/windows-v1/summary.json`. No real follow-up inference was performed while preparing this configuration and runner.
