# Operational experiment evidence

The completed full-study v2 is in `results/full-experiment/study-v2`: 100 questions, 3,500 audited generations and all three phase reports reproduced. Validation selected R0 before test; its held-out accuracy is 12/40 in both shared-initial branches. Secondary R3 gives communication 14/40 versus self-revision 10/40. [Results and interpretation](../docs/FULL_STUDY_RESULTS_V2.md) · [Frozen procedure and audit](../docs/FULL_EXPERIMENT.md) · [Archive](../archive/2026-11-19-full-study-v2/README.md)

The completed and audited architecture runs are `results/five-agent-pilot/windows-v1` (five agents/all four peers, 420 calls) and `results/sparse-peer-pilot/windows-v1` (ten agents/two sampled peers, 840 calls). Each includes a matched self-revision control on the twelve inspected development cases. Five-agent R3 gives 3/12 versus 3/12; sparse R3 gives 2/12 versus 3/12. [Results and full-study decision](../docs/ARCHITECTURE_RESULTS_V1.md) · [Frozen procedures and audit commands](../docs/ARCHITECTURE_PILOTS.md)

The completed and audited confirmation is in `results/confirmation-pilot/windows-v1`: twelve development questions, 840 unique calls with shared initialization, then all three voters and both stopping rules plus fixed-round controls. [Results and full-study decision](../docs/CONFIRMATION_RESULTS_V1.md) · [Frozen procedure and audit command](../docs/CONFIRMATION_PILOT.md)

The completed and audited offline voting/stopping comparison is in `results/offline-comparison/pilot-v1`, with a [byte-preserved archive](../archive/2026-11-18-offline-policies-v1/README.md). It replays the completed recovery traces with zero model calls. [Results and next-stage recommendation](../docs/OFFLINE_POLICY_RESULTS_V1.md) · [Command and candidate definitions](../docs/OFFLINE_POLICY_COMPARISON.md)

The current explicit recovery writes to `results/communication-pilot/windows-v2` by default. It preserves and audits failed v1's 146 raw responses, records its truncated response as ineligible without retry, and makes 334 more calls under the same generation settings. [Current commands and procedure](../docs/COMMUNICATION_RECOVERY.md)

| Location | Status |
| --- | --- |
| `five-agent-pilot/windows-v1/` | Completed and audited: 420 calls, R3 communication 3/12 and self-revision 3/12; eight round summaries, 96 question rows |
| `sparse-peer-pilot/windows-v1/` | Completed and audited: 840 calls, R3 communication 2/12 and self-revision 3/12; eight round summaries, 96 question rows |
| `confirmation-pilot/windows-v1/` | Completed and audited: 840 calls, 36 comparisons, 432 decisions; plurality R3 communication 1/12 versus self-revision 4/12; no policy selected |
| `offline-comparison/pilot-v1/` | Completed and audited exploratory replay: 36 policy/branch rows, 288 question decisions, zero new calls; no winner selected |
| `communication-pilot/windows-v1/` | Failed original pilot: 146 raw responses, 145 evaluated; original evidence remains unchanged |
| `communication-pilot/windows-v2/` | Current explicit recovery: all 146 existing revisions plus 334 new calls, shared initial panel, amended manifest and summary |
| `format-followup/windows-v2/` | Completed 320-call format follow-up; selected parent for the current pilot |
| `followup-pilot/windows-v1/` | Completed 160-call baseline-JSON versus schema comparison |
| [baseline/](baseline/README.md) | Preserved single-agent historical reference, not a newly generated result |
| `windows-checkout-backup-*/` | Original configuration-byte backups from checkout normalization |
| `full-experiment/study-v2/` | Complete and audited: root study manifest, phase journals/reports, frozen calibration and validation selection; all 3,500 fresh calls saved |

Completed Windows runs have immutable copies under [the November 17 archive](../archive/2026-11-17-development-pilots/README.md). Operational originals remain in place because the audit/import manifests retain absolute paths. Do not move, edit, or overwrite parent evidence. Earlier experiments are indexed in [the archive catalog](../archive/README.md); original archives remain unchanged.

New runs remain local and ignored by Git until deliberately archived. Preserve the entire run folder, including raw responses, evaluated records, shared initial evidence, configuration/provenance snapshots, checkpoints, and summaries. Cooperative pause/resume skips durable calls and excludes pause hours. Offline analysis rechecks prompts, hashes, calculator evaluation, and scores without contacting Ollama.
