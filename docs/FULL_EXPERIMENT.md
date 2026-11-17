# Full experiment: communication rounds and computational cost

This document describes the prepared full-study template `ml1-full-study-v1`. The configuration is [full_experiment.json](../config/full_experiment.json); generation settings remain those of [the original multi-agent protocol](MULTI_AGENT_PROTOCOL.md). Reference checks, dry runs, and offline fixtures cover the prepared setup, including portable call checkpoints; integrated verification precedes the next real run. **The full study remains gated on the follow-up development pilot. No full-study inference has been performed.** The completed four-question pilot is separate development evidence.

## What the pilot established

The [portable pilot summary](PILOT_RESULTS_V1.json) records 160 calls on four previously inspected questions. Independent offline reanalysis reproduced the saved results and checked raw responses, prompts, seeds, snapshots, and evidence hashes.

| Communication round | Collective accuracy | Eligible agent outputs | Cumulative tokens/question | Cumulative seconds/question |
| --- | --- | --- | --- | --- |
| 0 | 50% | 57.5% | 2,919 | 84.1 |
| 1 | 75% | 70% | 16,614 | 213.0 |
| 2 | 75% | 80% | 31,191 | 348.3 |
| 3 | 50% | 75% | 45,913 | 487.0 |

These changes do not establish improved mathematical reasoning. Algebra became collectively correct in round 1 because **one of ten** responses was eligible; round 2 had three eligible responses, and round 3 had none. Across its forty generations, 33 algebra expressions contained an unsupported assignment. A correct rearrangement written as `x = ...` still fails the frozen calculator grammar. No expression is repaired or extracted from explanation text.

Sensor answers illustrate harmful convergence: nine agents selected `1/2` in round 3, against the exact reference `18/19`. Overall, 113/160 responses were eligible, 46 failed calculator execution, and one probability result was out of range. All responses passed JSON/required-field checks; there were zero output-length stops. Model loading consumed about 35% of measured wall time.

The pilot confirms technical feasibility, logging, and scoring behavior. It does not select a validation-optimal round. Its one-question-per-family bootstrap intervals are degenerate. The failed earlier attempt remains preserved separately and is excluded from the completed-run accuracy summary; its partial evidence and incurred execution cost are not erased.

## Follow-up pilot before the full study

Use eight preregistered new development questions: two per family from eight distinct structural groups, selected before responses are inspected. Include a one-source sensor question and a three- or four-source question. Validation/test data remain untouched. The [Windows run guide](WINDOWS_RUN_GUIDE.md) covers setup and hardware verification. Run both formats on the same Windows 11 hardware/runtime; comparing the old Mac baseline against a new PC intervention would confound format and hardware. GPU identity and Windows throughput must be measured, not inferred from a product label.

**Phase A: output-format check, 160 calls.** Compare the original JSON transport with one structured-JSON-schema intervention that constrains the expression format. Keep prompts, seeds, model settings, references, and scoring identical; change only the response-format constraint. Offline preflight validates the requested schema and profile; it cannot prove that the installed runtime enforces every pattern constraint without generation. Returned strict-format outputs are checked for conformance. A nonconforming strict response is preserved as raw evidence and stops the pilot, so unsupported or ignored constraints cannot silently count as a successful intervention.

The dedicated [Stage-A runner](../run_followup_pilot.py) and [configuration](../config/followup_pilot.json) are available now. Preview its 160-call plan with `python run_followup_pilot.py --dry-run`, then follow the Windows guide to run it on the verified PC. Its `summary.json` contains a development screening/adoption recommendation; it does not launch communication rounds or the full study.

Each format generates ten independent answers per question, for eighty outputs. Proposed technical acceptance is at least **72/80 eligible outputs (90%)** and at most **4/80 calculator rejections (5%)**, conservatively covering unsupported expressions. These are aspirational development screens, not guaranteed outcomes. Also require the candidate's collective round-0 correct-question count to be no more than one below baseline. Report paired question wins/losses and group-bootstrap uncertainty; eighty correlated agent outputs are not eighty independent accuracy observations.

Freeze this selection rule before running: choose the constrained format if it passes those screens and baseline fails the technical screens, or both pass and the candidate has more eligible outputs. Otherwise retain baseline only if baseline passes. Baseline wins ties. If neither qualifies, stop and preregister a new protocol; never relax numerical tolerance or repair expressions after observing results.

**Phase B: communication check, scheduled after inspecting Stage A and freezing a chosen profile.** The planned next pilot runs that profile on the same eight questions through rounds 0–3, comparing all-to-all with self-revision using an identical initial panel. This represents 560 unique calls including that panel. If compatibility and provenance checks permit reuse of the chosen Phase-A panel, **480 additional calls, 640 total across both phases** would be needed; without audited reuse, the total is 720. These are planned budgets. Strict-schema communication is not implemented by the Stage-A runner, and the prepared full-study baseline cannot automatically switch to that format. Adopt any intervention through a newly versioned generation protocol before Stage B or the full study.

Do not run the full format-by-communication factorial. Diagnose the easy sensor case separately: if no eligible initial answer is correct, pause rather than assuming discussion will supply missing capability. A future, separately versioned Bayes scaffold would test scaffolding, not establish a communication benefit.

Eight questions support technical screening and exploratory paired comparisons. They do not establish a reliable accuracy improvement. Freeze any selected protocol change in a new version before validation or test; preserve v1 and its results.

## Fresh benchmark and comparison conditions

The [benchmark](../config/full_benchmark.json) contains 100 new questions across urn probability, sensor posteriors, algebra, and unit/rate problems.

| Partition | Questions | Structural groups | New model calls |
| --- | --- | --- | --- |
| Development/calibration | 20 | 12 | 1,400 |
| Validation | 40 | 20 | 2,800 |
| Held-out test | 40 | 20 | 2,800 |

Every partition is balanced across the four families. The 52 structural problem groups are disjoint across partitions; numerical variants stay together. Validation and test each contain twenty groups with two variants per group. This provides structural holdout rather than only changing numbers in an otherwise reused problem. Exact rational references receive independent enumerative, symbolic, or dimensional verification, as appropriate:

```sh
python3 build_full_benchmark.py --check
```

The primary condition uses ten independent initial generations followed by three synchronous all-to-all revision rounds: forty calls per question. Self-revision uses the **same ten initial raw responses**, then thirty new calls in which each agent sees only its own previous response. Both conditions therefore represent forty-generation trajectories, with seventy unique calls per question and **7,000 total new calls**.

This comparison matches generation counts and initial evidence. It is **not token-matched**: self-revision has shorter prompts. Additional independent samples under a matched token budget remain a future control and an explicit limitation. The predeclared single-agent control is initial agent 0; compare it with round-0 plurality over ten agents. “Any initial eligible agent was correct” is an oracle diagnostic using references, not an operational aggregation method.

## Frozen generation, scoring, and selection

Both conditions retain `llama3.2:3b`, temperature `0.7`, 1,024 output tokens, a 16,384-token context, sequential execution, and `keep_alive=0`. Revision prompts use only the preceding completed round. All-to-all agents receive the original question, their own response, and anonymized, reproducibly ordered peers' explanations, expressions, calculator results, and failure statuses. No reference or correctness feedback enters prompts.

Strict delivery requires the required string fields, successful calculator execution, and a probability in range where applicable. Exact-rational plurality selects a unique winning value; ties or no eligible outputs abstain and count incorrect. Correctness uses exact equality. Explanation quality is not graded; expression grammar, delivery validity, and numerical success remain separate diagnostics. The original v1 scorer and historical results are preserved.

Development primary round-1 costs define positive, family-balanced token/time calibration references. The same frozen references apply to both conditions. Select one global primary round on validation by minimizing family-balanced error plus `0.02 × [0.5 × normalized communication tokens + 0.5 × normalized communication wall time]`. Communication costs cover rounds `1..R`; report initial and total costs separately. Objective ties prefer fewer rounds.

Freeze that selected round before test inference and evaluate both conditions there. All rounds remain recorded for descriptive curves; neither test results nor the control's preferred round retune the primary choice. Report actual tokens, measured wall time, loading, failures, vote coverage, and consensus errors alongside accuracy.

## Uncertainty and execution

Intervals use 2,000 deterministic, family-stratified whole-group bootstrap draws. The same sampled groups are shared across variants, rounds, and conditions, preserving pairing. Held-out uncertainty has **twenty clusters, not forty independent questions**. This is an exploratory scale, not evidence of power to detect a two-percentage-point gain. One fixed-seed trajectory per question supports reproducibility; deterministic reruns are not sampling replicates.

The driver binds source/configuration hashes, host identity, CPU, memory, OS, available GPU/driver identity, model digest, and Ollama version. Changing these requires a separate study. Loading remains part of the frozen operating procedure. The earlier machine's pilot suggests approximately **20–30 hours** for both full-study conditions; this is not a measured Windows GPU runtime, and new difficulty can change it substantially.

The commands below show the prepared full-study workflow after the follow-up pilot passes and the final protocol is frozen. A chosen format intervention requires its newly versioned runner/configuration first. Portable locks and completed-call checkpoints support Windows 11; see the [Windows run guide](WINDOWS_RUN_GUIDE.md) and [README](../README.md). Commands use `python`; Windows installations may use `py -3`, and Unix installations may use `python3`:

```sh
python run_full_experiment.py --dry-run --phase all
python run_full_experiment.py --output-dir results/full-experiment/study-v1 --phase development
python run_full_experiment.py --output-dir results/full-experiment/study-v1 --phase validation --resume
python run_full_experiment.py --output-dir results/full-experiment/study-v1 --phase test --resume
```

Configure the execution machine to stay awake during runs; macOS users can optionally prefix commands with `caffeinate -i`. After the pilot decision, `--phase all` can execute the ordered full-study phases. Reports are saved under `reports/{phase}.json`; calibration and selection are frozen under `artifacts/`. Per-question child directories retain raw journals and manifests. They contain absolute provenance paths: keep the study directory in place unless relocation support is added.

Every completed call is durably journaled. The first `Ctrl+C` requests a cooperative pause: wait for the current call to finish and be saved, then for the runner to report `paused` and exit with code `2`. A second `Ctrl+C` forces interruption and can lose an in-flight reply; already durable outputs remain saved. From another terminal, the same request can be made with:

```sh
python run_full_experiment.py --pause --output-dir results/full-experiment/study-v1
```

Resume in the **same folder** with `--resume`, the same phase, and unchanged source/configuration, hardware, model, and runtime. The engine audits saved evidence and continues at the next pending call rather than restarting a completed question. Human pause time is excluded from active wall-time measurements. Failures require an explicit resume; they do not trigger automatic retries. Portable file locks prevent two writers from resuming the same study concurrently. Earlier partial attempts and overhead remain auditable.

After the follow-up pilot selects a protocol, full-study phase progression depends on technical completeness, intact provenance, and complete cost measurements. Review development floor/ceiling behavior descriptively; do not add outcome-dependent advancement thresholds. Any design change needs a new protocol before validation/test, while preserving existing evidence; unfavorable outcomes do not justify retrofitting the scorer or replacing questions.
