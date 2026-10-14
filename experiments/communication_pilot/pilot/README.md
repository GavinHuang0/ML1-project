# Pilot testing and existing pilot artifacts

**Status:** the experiment owner reports that the pilot has already been generated for three Qwen models. Its original outputs are not present in this checkout. Exact model tags, question counts, repeated-trial counts, settings, and findings await metadata from those outputs.

The [protocol](../protocol.md) records the implemented design and separates default settings from actual completed-run settings. Preserve the existing outputs; they do not need to be generated again for this reorganization.

## Register a completed pilot

Run from the repository root, substituting each original output path:

```sh
python3 -m scripts.register_results /path/to/completed-pilot.jsonl --stage pilot
```

You may pass several JSONL paths in one command. On Windows, replace `python3` with `py -3` and quote paths containing spaces.

The command validates metadata, unique task IDs, question counts, and the final completion marker. It copies the original bytes into `pilot/raw/`, leaves the source unchanged, and updates `pilot/summaries/runs.json` with model tags/digests, settings, family counts, SHA-256 checksums, a question-set checksum, and the six combined panel accuracies. Identical re-registration is safe; a filename collision with different contents is rejected. Legacy logs without protocol fields retain unknown protocol provenance. A recorded protocol path without a hash does not establish the exact protocol version.

For old outputs still in the root `results/` directory, pass those paths directly. That directory stays ignored for compatibility. Check the copied artifacts and back them up before making any separate decision about the original files.

## Record pilot decisions

Keep full generations in `raw/` (ignored). Keep indexes, reviewed aggregate tables, and prompt/model/settings decisions in `summaries/` (tracked). Add supported conclusions and decisions to [interpretation.md](../interpretation.md).

Check parsing failures, difficulty, runtime, token use, and whether initial answers include enough successes and failures to study correction and corruption. The pilot helps choose settings; it does not establish a held-out performance claim. A roughly 50-question pilot is the proposed scale, not a confirmed count for existing runs.

Once actual metadata is available, reconcile the protocol's model roster and counts with the registered records. Do not silently replace old settings or label tutorial defaults as the settings used in the completed pilot.

Compare `question_set_sha256` to verify the same ordered task objects across models. Two files with the same source `sha256` are copies of one run, even if their filenames differ; do not count them as independent repeated trials.
