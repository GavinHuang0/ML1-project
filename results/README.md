# Reviewed pilot artifacts

These eight artifacts preserve the two completed Qwen pilots and their analyses. The raw outputs are unchanged. New files under `results/` remain ignored unless explicitly selected for versioning.

| Pilot | Raw output | Derived artifacts |
| --- | --- | --- |
| 256 tokens | [JSONL](experiment1-qwen-seed42.jsonl) | [Summary](experiment1-qwen-seed42.summary.json), [failure record](experiment1-qwen-seed42.failure.json) |
| 512 tokens | [JSONL](experiment1-qwen-seed42-max512.jsonl) | [Summary](experiment1-qwen-seed42-max512.summary.json), [comparison](experiment1-qwen-seed42-max512.comparison.json), [run manifest](experiment1-qwen-seed42-max512.run.json), [console log](experiment1-qwen-seed42-max512.run.log) |

Both runs used `qwen2.5:3b`, four questions, three agents, seed 42, and temperature 0.7. The intentional generation-setting change was the output limit. The first run had 12/60 invalid responses, all truncated at 256 tokens. The follow-up had 0/60 invalid responses, but every method still missed both urn questions and scored 2/4 overall.

See the [original interpretation](../PILOT_RESULTS.md), [512 token comparison](../PILOT_512_RESULTS.md), and [next experiment plan](../NEXT_STEPS.md). Their scores are descriptive pilot results, with correlated calls and only four underlying questions per run.

The summaries contain raw-file SHA256 hashes. The 512-token manifest also records inference-source hashes, model/runtime information through the linked raw metadata, and the executed command. Its calendar timestamps span a different interval from its monotonic/request timers; the cause is unverified. The original 256-token generation did not record its code revision or hardware.

From the repository root, validate either run without making model calls. Use a new output filename:

```sh
python3 analyze_results.py results/experiment1-qwen-seed42.jsonl --output results/experiment1-qwen-seed42.recheck.json
python3 analyze_results.py results/experiment1-qwen-seed42-max512.jsonl --output results/experiment1-qwen-seed42-max512.recheck.json
```
