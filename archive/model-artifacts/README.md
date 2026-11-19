# Model artifacts and local weight backup

Two model families have recorded inference evidence: **Llama3.2:3b** and **Qwen2.5:3b**. [The registry](registry.json) distinguishes tested identity, selected/retired status, and actual weight availability. Prompt profiles such as `complete_expression`, `syntax_clear`, and multiple choice are experiments using the same model, not additional trained weights.

The available Llama model has an independent byte-for-byte backup under [llama3.2-3b-a80c4f17/](llama3.2-3b-a80c4f17/README.md): original Ollama manifest plus all seven referenced blobs, **2,019,395,363 bytes** in eight files. Every blob's streamed SHA256 matched its content-addressed digest. The installed model files were neither moved nor changed.

Qwen's exact tested digest, size, quantization, settings and raw responses are preserved in the [October archive](../2026-10-24-legacy/README.md). Its installed manifest/weights are not present on this machine, so there is **no physical Qwen weight backup** here. No model was downloaded to manufacture one, and no installed model was removed.

Blob files are intentionally ignored by Git because they total about 2 GB. Manifests, registry and checksums remain versionable. Copy the whole `archive/model-artifacts/` directory to external storage to back up the weight files; an ordinary clone contains metadata rather than those local blobs. Verify the backup with `archive_project_history.py --check` using Python 3.10+.
