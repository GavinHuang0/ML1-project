# Development pilots preserved on November 17, 2026

This snapshot contains **69 files totaling 4,478,557 bytes**. Files were independently copied and SHA256-checked, without changing the originals. The snapshot precedes the new selected-profile communication/self-revision implementation.

| Preserved material | Location |
| --- | --- |
| Prior repository instructions | [REPOSITORY_README.md](REPOSITORY_README.md) |
| Stage A: JSON versus strict schema, completed 160 calls | [Raw generations](results/followup-pilot/windows-v1/generations.jsonl), [answers](results/followup-pilot/windows-v1/answers.jsonl), [manifest](results/followup-pilot/windows-v1/run-manifest.json), [summary](results/followup-pilot/windows-v1/summary.json) |
| Stage A2: strict schema versus completeness instruction, completed 320 calls | [Raw generations](results/format-followup/windows-v2/generations.jsonl), [answers](results/format-followup/windows-v2/answers.jsonl), [manifest](results/format-followup/windows-v2/run-manifest.json), [summary](results/format-followup/windows-v2/summary.json) |
| Exact generation, parsing, calculator, analysis and checkpoint code | Root Python files and `run_format_followup.ps1` in this snapshot |
| Questions, prompts, model settings and prepared study configuration | [config/](config/) |
| Reports, Windows guide, four-question Mac pilot portable metrics | [docs/](docs/) |
| Offline tests and baseline historical reference | [tests/](tests/), [results/baseline/](results/baseline/) |
| Line-ending repair's original baseline bytes | [Checkout backup](results/windows-checkout-backup-sqgc2n3p/config/baseline.json) |
| Original paths, byte counts, SHA256 hashes | [SHA256_INVENTORY.json](SHA256_INVENTORY.json) |

The generation profiles are preserved separately: Stage A found neither baseline JSON nor strict schema passed its technical screen. Stage A2's **fresh numerical screening set** selected the original prompt plus strict schema: 79/80 eligible, one calculator rejection, and 4/8 collectively correct. The appended completeness instruction had six calculator rejections and the same 4/8 collective score; its improvements on inspected regression cases did not override that screening decision. The prompt is a discarded alternative, not a different model checkpoint.

The earlier [October](../2026-10-24-legacy/README.md) and [November 9](../2026-11-09-pilots/README.md) archives remain separate, unchanged, and are not recursively duplicated here. The model archive is [separate](../model-artifacts/README.md). Lock files, bytecode, environments, Git internals, and unrelated new Stage-B code were excluded.

Original operational sources and `results/` runs remain in place because the saved manifests freeze absolute configuration paths and source hashes. Archived provenance strings are unchanged. Use the operational audited analyzer against the original result directories for full replay; this copy is a byte-preserved evidence backup, not a path-relocated replacement run. `archive_project_history.py --check` checks archived bytes independently.

The Mac run named `results/multi-agent/pilot-v1-restart` is represented here only by its [portable metrics and original evidence hashes](docs/PILOT_RESULTS_V1.json). Its raw journals and the earlier failed Mac attempt are **not present in this Windows checkout**. This snapshot does not claim to back up missing artifacts.

This README and the inventory are new archive documentation; the 69 inventoried entries are the original preserved files. All historical scoring contracts, including the single-agent baseline's tolerance and later exact-equality pilots, remain distinct.
