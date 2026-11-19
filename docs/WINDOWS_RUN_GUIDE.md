# Windows 11 setup, transfer, pause, and resume

Both Windows format pilots are complete. Communication v1 stopped at an output-truncated response. The current [explicit recovery amendment](COMMUNICATION_RECOVERY.md) reuses its 146 responses and the selected 80 initial answers, leaving **334 new calls**. Launch `.\run_communication_recovery.ps1`; resume with `.\run_communication_recovery.ps1 -Resume`. The setup and GPU guidance below still applies. Later `run_followup_pilot.py` commands document the original Stage-A experiment, whose evidence remains preserved.

## Transfer the project and install the local model

Install Git for Windows, Python 3.10 or newer, and [Ollama for Windows](https://ollama.com/download/windows). Open Ollama. In PowerShell, choose a normal local folder, then run:

```powershell
git clone --config core.autocrlf=false https://github.com/GavinHuang0/ML1-project.git
Set-Location ML1-project
git rev-parse HEAD
py -3 --version
ollama pull llama3.2:3b
ollama --version
py -3 -m tools.setup_models --check
py -3 build_full_benchmark.py --check
py -3 -m unittest discover -s tests -q
```

The repository is private: sign in to GitHub when Git requests authentication. `core.autocrlf=false` preserves the exact committed bytes used by the source and archive checks. No Python packages are required. Use this updated repository version, which contains `run_followup_pilot.py` and portable checkpointing.

Active configuration JSON files also require LF line endings through `.gitattributes`. Earlier Windows checkouts could convert `config/full_benchmark.json` to CRLF, causing `build_full_benchmark.py --check` to report a deterministic-generation mismatch even though the questions were unchanged.

For an existing copy with that error, update the code and run the included helper from the repository root **before starting an experiment**. It checks both `config/baseline.json` against its frozen historical hash and `config/full_benchmark.json` against deterministic generation before changing either file. A content mismatch stops without changes; original bytes are backed up under `results/windows-checkout-backup-*/`. Correct LF files are left untouched.

```powershell
git pull --ff-only origin main
py -3 -m tools.fix_windows_checkout
py -3 build_full_benchmark.py --check
py -3 -m unittest discover -s tests -q
```

Use `py -3 -m tools.fix_windows_checkout --check` for a read-only diagnosis. The helper restores only line endings and does not run a model. The test command's `-q` mode stays quiet until completion, which can take a few minutes on Windows.

The updated tests compare recorded repository paths using `/` on every operating system. The symlink-only protection test skips when Windows reports missing symlink privileges (`WinError 1314`); direct historical-output protections are tested separately and always run. Administrator access is not required for the suite.

Transfer the **code** through GitHub. Start a new experiment directory on Windows; do not resume the Mac run on a different machine or reuse its time-calibration artifact. Hardware, driver, runtime, model, and code are frozen during each experiment. The prior Mac result remains separate historical development evidence.

## Verify the GPU rather than assume a speedup

Check the actual adapter, VRAM, and driver:

```powershell
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv
```

The label “4060 Super” alone is insufficient to infer the exact model or available memory. Keep the PC plugged in and prevent automatic sleep during active computation. Do not change the frozen 16,384-token context or other model settings to force GPU placement without defining a new comparison.

While the pilot is generating, use a second PowerShell window:

```powershell
while ($true) {
    ollama ps
    Start-Sleep -Seconds 2
}
```

Inspect `PROCESSOR` and `CONTEXT`: Ollama reports GPU, CPU, or mixed placement. With `keep_alive=0`, the model unloads after each request, so an empty listing between calls is expected. The pilot records measured time, token counts, and hardware identity; use those results to estimate the full-study runtime. A faster GPU does not guarantee that the entire request is GPU resident. [Ollama Windows requirements](https://docs.ollama.com/windows), [GPU placement](https://docs.ollama.com/faq), [context memory](https://docs.ollama.com/context-length).

## Run the short pilot first

```powershell
py -3 run_followup_pilot.py --dry-run
py -3 run_followup_pilot.py --output-dir results/followup-pilot/windows-v1 --timeout 600
```

Both baseline JSON and schema-constrained output run on this same Windows machine with paired seeds and identical prompts/settings. Comparing the Mac baseline against only a new Windows schema arm would confound the format change with runtime changes.

The pilot uses eight development questions, two per family, and 160 calls. It never reads validation/test outputs. Its schema constrains characters in the expression; the unchanged calculator still rejects malformed arithmetic, and exact reference equality still determines correctness. The report recommends a candidate; it does not automatically change the full-study protocol.

## Pause whenever needed

Press **Ctrl+C once** in the running terminal. The runner waits for the current model response to finish, saves it and its checkpoint, reports `paused`, and exits with code `2`. Code `2` means a requested pause. You can then close the terminal or shut down the PC. A call can take up to the configured timeout, so pausing is cooperative rather than an immediate cancellation.

Alternatively, request a pause from a second PowerShell window in the same repository:

```powershell
py -3 run_followup_pilot.py --pause --output-dir results/followup-pilot/windows-v1
```

Wait for the original terminal to confirm it has paused. A second Ctrl+C forces interruption; an unfinished request may need to be generated again and can have unknown cost. Returned responses already saved to the journal are recovered locally rather than requested again.

Resume with the same output directory:

```powershell
py -3 run_followup_pilot.py --resume --output-dir results/followup-pilot/windows-v1 --timeout 600
```

Completed calls are audited and skipped. Paused hours are excluded from the active timing measurements. Only one process may own the run's file lock. Keep the repository, source files, model, Ollama version, GPU driver, and experiment folder unchanged until the run finishes. Do not `git pull` into a paused experiment or move its folders. Back up the whole project/results folder while paused, and restore it to its original path if needed; results are ignored by Git and are not included in a normal push.

## What to inspect and share next

The report is `results/followup-pilot/windows-v1/summary.json`. It includes each format's eligible outputs, calculator failures, collective accuracy, paired gains/losses, costs, and a development-only recommendation. Preserve the journals and `run-manifest.json`; share the summary for interpretation before proceeding to the communication pilot.

The prepared full-study driver supports the same Ctrl+C/`--pause`/`--resume` workflow and per-call checkpoints. Its profile currently implements the original JSON protocol; a successful schema intervention requires a separately versioned adopted profile before a full-study launch. [Full-study design and conditional later phases](FULL_EXPERIMENT.md)
