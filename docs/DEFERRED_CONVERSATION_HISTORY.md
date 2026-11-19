# Deferred idea: conversation-history preservation

Recorded on November 18, 2026. **Status: deferred discussion only.** Continue with the currently prepared experiments and their frozen procedures. This note does not change any model, prompt, configuration, runner, voting rule, stopping rule, or result. No history-preservation pilot or full experiment is being implemented or launched now.

## Question to investigate later

Does retaining an agent's earlier conversation improve collective accuracy or stability enough to justify its additional context cost, compared with supplying only the immediately preceding round?

The current [architecture pilots](ARCHITECTURE_PILOTS.md) use the original question and the agent's immediately preceding response. Communication also supplies the selected peers' immediately preceding responses. Older rounds are not directly retained. Keep that procedure unchanged for the present work.

## What preserving a conversation means

Every new response still requires model inference. A continuing conversation is represented by the history available to the model, not by a separate learning process in which its weights absorb previous turns.

For the local Ollama chat interface, the application supplies history through the `messages` array. Keeping the same chat object or leaving the model loaded is not an additional conversational-memory mechanism. If two implementations provide the same ordered, role-tagged messages and settings, they provide the same conversational context; a persistent conversation identifier alone should not be assumed to improve reasoning.

There can nevertheless be a substantive difference between faithfully retained user/assistant messages and a new user message containing pasted or paraphrased earlier responses. Roles, ordering, formatting, omissions, and summaries can affect the input. Do not attribute such a combined change solely to memory length. See the [Ollama chat API](https://docs.ollama.com/api/chat) for the history and keep-alive fields.

## Recommended later comparison

Preserve each agent's actual message history in code and explicitly provide the retained history to its next request. Avoid manually paraphrasing its earlier answers. Use the same message-role format in the two history conditions:

| Condition | Information available at round r |
| --- | --- |
| Short history | Original question and immediately preceding interaction |
| Full history | Original question and all preceding interactions through round r-1 |

For self-revision, a full interaction history would retain the agent's own earlier responses and calculator feedback. For communication, preserving the actual conversation would also retain the peer-response snapshots that the agent saw in earlier rounds. That is different from retaining only its own history plus the latest peers; if that alternative is wanted, define it as a separate condition before inference.

The current implementation places a structured preceding-round snapshot in a user message. If the later experiment adopts a native user/assistant message sequence, provide a matched short-history baseline in that same format. A direct comparison between the old snapshot format and a new full conversation would change both history amount and presentation.

## Expected benefits and risks to measure

Retained history might help agents preserve earlier correct reasoning, notice inconsistent revisions, or recover a useful answer that disappeared from the latest round. It might also reinforce earlier mistakes, repeat correlated peer evidence, distract from the original question, or make correction harder. These are hypotheses, not demonstrated benefits.

Full history increases input tokens and may exceed the current context admission budget. Define the history contents, message roles, context limit, and overflow policy prospectively. Do not silently truncate or summarize history. If a larger context setting is necessary, use the same setting for both history conditions and record the new operating profile. Keep loading/cache policies comparable and distinguish their timing effects from changes in answer quality.

## Experimental recommendations

- Test history policy while holding panel size, peer routing, model artifact, sampling, calculator, scoring, and aggregation fixed. Evaluate conversation history separately from the five-agent versus ten-agent or sparse-peer architecture comparisons.
- Use identical initial evidence between matched conditions where compatible, branch-specific histories, and synchronous preceding-round snapshots. Preserve references and correctness labels for local analysis only.
- Record exact requests, raw outputs, calculator outcomes, history lengths, context admission, seeds, tokens, request time, and loading time. Follow the established prospective truncation/failure policy.
- Measure collective and individual accuracy, beneficial/harmful revisions, preservation or loss of correct minority answers, vote concentration, and accuracy versus resource cost. History is not automatically useful merely because answers become more consistent.
- This input-changing intervention requires new revision generations. Existing saved trajectories can motivate the design, but cannot establish what a model would have generated with a different history. Reuse any initialization only after prompt/provenance compatibility checks.
- Treat a later pilot as development evidence. Freeze its definitions before running it, and use separate validation/test evidence for policy selection and any full-study conclusions. Do not alter completed experiments or retune their scores.

The earlier recommendation was to assess smaller-panel/sparse-peer communication first, then consider a history-preservation pilot at a fixed architecture. The present decision is to **defer the history idea and continue the current work**. Revisit this note before designing that later pilot or a potential full experiment.
