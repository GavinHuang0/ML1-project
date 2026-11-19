# Tested models and artifact availability

Model weights and experimental profiles are distinct. The repository has evidence for **two tested model families**; no fine-tuned checkpoints were produced. The current selected delivery profile is the original calculator instruction plus strict schema on Llama3.2:3b.

| Model | Tested artifact | Current role | Available preservation |
| --- | --- | --- | --- |
| `llama3.2:3b` | 3.2B GGUF, `Q4_K_M`; recorded digest `a80c4f17acd55265feec403c7aef86be0c25983ab279d83f3bcd3abbcb5b8b72` | Retained; selected model for the current pilot | Original installed store retained. Independent [manifest and seven-blob backup](../archive/model-artifacts/llama3.2-3b-a80c4f17/README.md), raw generations/settings and model metadata archived |
| `qwen2.5:3b` | 3.1B GGUF, `Q4_K_M`; recorded digest `357c53fb659c5076de1d65ccb0b397446227b71a42be9d1603d46168015c9e4b` | Previously tested, superseded in the active workflow; not a conclusion of general model inferiority | [Original metadata, raw generations and historical settings](../archive/2026-10-24-legacy/results/experiment1-qwen-seed42.summary.json) preserved. Its weights/installed manifest are absent from this Windows machine; no physical weight backup is claimed |

The archived Llama backup contains **2,019,395,363 bytes** in eight files, including its manifest. Each copied blob was streamed through SHA256 verification against the manifest digest. Its main GGUF blob is 2,019,377,376 bytes. The installed model was neither moved nor changed. Blob files remain local and ignored by Git; ordinary clones preserve the versioned metadata, not 2 GB of model contents.

The recorded experimental Llama digest is also the digest of the original 1,005-byte manifest blob. The currently installed 1,169-byte manifest wraps that original as a layer; its file hash is `a52a4a87c5affc63e344f4974f75bcc5b478b40e641df57d0f40941dfc406c94`. The registry records both instead of confusing the wrapper hash with the experimental identity.

Historical Qwen/Llama runs recorded Ollama `0.40.4`; the completed Windows format pilots recorded `0.40.16`. Runtime differences and scoring changes prevent naive cross-run rankings. New runs bind the exact installed digest/runtime/hardware rather than relying only on a mutable model tag.

Discarded prompt/format alternatives are preserved with their code and configurations: numerical final-answer output, internal checking prompts, bounded templates, longer syntax instructions, multiple choice, plain JSON transport, and the latest `complete_expression` instruction. They are **not additional model weights**. The original prompt, strict schema and exact calculator remain selected; the old plain-JSON full-study template is prepared historical implementation, not a silently updated current protocol.

The machine-readable [registry](../archive/model-artifacts/registry.json) links the evidence and backup inventory. Verify all available archived artifacts with `archive_project_history.py --check`. Qwen cannot be reconstructed byte-for-byte from the metadata alone. No model was downloaded, uninstalled, or deleted during this organization.
