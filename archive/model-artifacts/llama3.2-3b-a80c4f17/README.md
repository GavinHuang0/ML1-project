# Llama3.2:3b exact available artifact

The [original Ollama manifest](ollama-manifest.json) and all seven content-addressed files it references were copied independently from the installed store. The [inventory](SHA256_INVENTORY.json) records original locations, archived locations, sizes, media types and SHA256 hashes. Installed files remain unchanged.

The recorded experimental model digest is `a80c4f17acd55265feec403c7aef86be0c25983ab279d83f3bcd3abbcb5b8b72`. The current 1,169-byte installed manifest is a wrapper that includes the original 1,005-byte manifest as a layer. Its own file SHA256 is `a52a4a87c5affc63e344f4974f75bcc5b478b40e641df57d0f40941dfc406c94`. These are different identifiers and are not silently substituted.

The principal GGUF model blob is `sha256-dde5aa3fc5ffc17176b5e8bdc82f587b24b2678c6c66101bf7da77af9f7ccdff`, 2,019,377,376 bytes. The remaining blobs preserve configuration, template, parameters, licenses and original manifest. All eight archived files total **2,019,395,363 bytes**.

Large blobs remain local and ignored by Git. A model tag can change upstream; the recorded digests and these exact bytes establish this tested artifact's identity. This directory is an artifact backup, not a newly trained model or a replacement installation.
