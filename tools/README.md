# Repository maintenance tools

Run these modules from the repository root. They use the Python standard library.

| Command | Purpose |
| --- | --- |
| `python -m tools.archive_project_history --check` | Read-only byte verification of all dated snapshots, referenced inputs and available local model backup |
| `python -m tools.fix_windows_checkout --check` | Read-only LF/configuration diagnosis |
| `python -m tools.fix_windows_checkout` | Restore verified configuration line endings with original-byte backups; run before an experiment |
| `python -m tools.setup_models --check` | Check the local Ollama model installation |
| `python -m tools.setup_models` | Install the configured model; `--smoke` additionally makes a test generation |

These replaced root-level script paths during repository organization. Existing source snapshots under `archive/` keep their original paths and bytes. See [repository layout](../docs/REPOSITORY_LAYOUT.md) and [Windows setup](../docs/WINDOWS_RUN_GUIDE.md).
