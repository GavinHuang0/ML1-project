# Failed communication pilot preserved on November 17, 2026

This immutable snapshot contains **27 files totaling 2,853,346 bytes**: the four original evidence files and all 23 source/configuration files named in the run's frozen `source_sha256`. Every original and copied file was SHA256-checked before and after copying. Operational files were left unchanged. The [inventory](SHA256_INVENTORY.json) maps original absolute and repository-relative paths to archived paths.

| Evidence | Preserved state |
| --- | --- |
| [Run manifest](results/communication-pilot/windows-v1/run-manifest.json) | `failed`; 145 evaluated answers, 146 saved raw responses |
| [Initial panel](results/communication-pilot/windows-v1/initial_panel.jsonl) | All 80 imported strict-schema screening answers unchanged |
| [Raw generations](results/communication-pilot/windows-v1/generations.jsonl) | All 146 responses, including the unmodified truncated response |
| [Evaluated answers](results/communication-pilot/windows-v1/answers.jsonl) | The 145 answers evaluated before the frozen schema stop |
| [Configuration](config/communication_pilot.json) | Original strict-schema v1 generation and stop policy |
| [Versioned implementation](experiments/communication_pilot/) | Original protocol, runner, and analysis used by this attempt |

The final saved response is call index 145 (the 146th call): easy sensor question `format-v2-evidence-development-01`, round 2, agent 2, `self_revision`. The model repeated its explanation until the **1024-token output cap**, with `done_reason="length"` and `eval_count=1024`. Its JSON string never closed and no expression was delivered. The prompt used 440 reported input tokens, so this was output truncation rather than context saturation or a calculator rejection.

The original v1 schema guard correctly stopped before creating an evaluated record for that response. A plain v1 resume would reevaluate the same saved invalid response and stop again. There is no complete v1 summary, and this snapshot must not be presented as a completed 480-call comparison or used to select a favorable communication result.

The separately versioned recovery design preserves this failed attempt and changes only the treatment of a known length-terminated invalid-JSON response: count it as one ineligible answer, without repair or retry. It can audit and import all 146 saved generations, evaluate the truncated response locally, and leave **334 new calls**. The output cap, prompts, sampling, calculator, and exact scoring remain unchanged. This is a post-failure protocol amendment for exploratory continuation, not a retroactive claim that v1 completed.

The parent Windows format-pilot evidence is already preserved in [the development-pilot archive](../2026-11-17-development-pilots/README.md). Its original operational folder remains available for provenance audit. Parent records are not duplicated here; the failed run's manifest retains their original paths and hashes. Earlier archives and the model backup remain unchanged.

The README and inventory are new archive documentation; the 27 inventoried files retain their exact original bytes. Lockfiles, bytecode, and the new recovery implementation are excluded. Verify this snapshot with the root `archive_project_history.py --check`; it checks archived contents without inference or evidence mutation.
