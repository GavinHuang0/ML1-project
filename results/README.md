# Reviewed pilot artifacts

These artifacts preserve the two completed Qwen pilots, their analyses, and the single-agent urn follow-up appended to the second pilot. The original raw outputs are unchanged. New files under `results/` remain ignored unless explicitly selected for versioning.

| Pilot | Raw output | Derived artifacts |
| --- | --- | --- |
| 256 tokens | [JSONL](experiment1-qwen-seed42.jsonl) | [Summary](experiment1-qwen-seed42.summary.json), [failure record](experiment1-qwen-seed42.failure.json) |
| 512 tokens | [JSONL](experiment1-qwen-seed42-max512.jsonl) | [Summary](experiment1-qwen-seed42-max512.summary.json), [comparison](experiment1-qwen-seed42-max512.comparison.json), [run manifest](experiment1-qwen-seed42-max512.run.json), [console log](experiment1-qwen-seed42-max512.run.log) |
| Second pilot urn appendix at 1024 tokens | [Four single-call responses](experiment1-qwen-seed42-max512-urn-check1024.jsonl) | [Summary](experiment1-qwen-seed42-max512-urn-check1024.summary.json); original prompt 0/2, math-checking prompt 1/2 |
| Second pilot diagnostic sequence at 1024 tokens | [Sixteen single-call responses](experiment1-qwen-seed42-max512-diagnostic1024.jsonl) | [Summary and manual review](experiment1-qwen-seed42-max512-diagnostic1024.summary.json); arithmetic, expression construction, full solving, algebra, and units |

Both runs used `qwen2.5:3b`, four questions, three agents, seed 42, and temperature 0.7. The intentional generation-setting change was the output limit. The first run had 12/60 invalid responses, all truncated at 256 tokens. The follow-up had 0/60 invalid responses, but every method still missed both urn questions and scored 2/4 overall.

The later urn appendix used one agent per call, the two original urn questions, matched first-agent sampling seeds, and a 1024-token cap. It compared the original and explicit math-checking prompts without tools or revision calls. Its four responses are stored separately from the historical 60-call files and are not inputs for the full-panel analyzer below. The outcomes and exact prompts are documented as a section of the [second pilot report](../PILOT_512_RESULTS.md#single-agent-urn-follow-up-at-1024-tokens).

The next diagnostic used two fresh urn cases across three stages plus two non-probability math items, with baseline and checking prompts. It remains a [section of the second pilot](../PILOT_512_RESULTS.md#single-agent-diagnostic-sequence-and-transfer-check), with separate numeric and expression scoring rather than the historical full-panel analyzer. Its related stages are not independent trials.

See the [original interpretation](../PILOT_RESULTS.md), [512 token comparison](../PILOT_512_RESULTS.md), and [next experiment plan](../NEXT_STEPS.md). Their scores are descriptive pilot results, with correlated calls and only four underlying questions per run.

The summaries contain raw-file SHA256 hashes. The 512-token manifest also records inference-source hashes, model/runtime information through the linked raw metadata, and the executed command. Its calendar timestamps span a different interval from its monotonic/request timers; the cause is unverified. The original 256-token generation did not record its code revision or hardware.

From the repository root, validate either run without making model calls. Use a new output filename:

```sh
python3 analyze_results.py results/experiment1-qwen-seed42.jsonl --output results/experiment1-qwen-seed42.recheck.json
python3 analyze_results.py results/experiment1-qwen-seed42-max512.jsonl --output results/experiment1-qwen-seed42-max512.recheck.json
```
