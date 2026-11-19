[CmdletBinding()]
param(
    [switch]$DryRun,
    [switch]$Resume,
    [switch]$Pause,
    [string]$AnalyzeRun,
    [string]$SourceRun,
    [string]$OutputDir,
    [ValidateRange(1, 86400)]
    [int]$Timeout = 600,
    [string]$Python
)

$ErrorActionPreference = 'Stop'
$candidates = [System.Collections.Generic.List[object]]::new()
if ($Python) {
    $candidates.Add(@{ Executable = $Python; Prefix = @() })
} else {
    $launcher = Get-Command py -ErrorAction SilentlyContinue
    if ($launcher) { $candidates.Add(@{ Executable = $launcher.Source; Prefix = @('-3') }) }
    foreach ($name in @('python3', 'python')) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if ($command -and $command.Source -notlike '*\Microsoft\WindowsApps\*') {
            $candidates.Add(@{ Executable = $command.Source; Prefix = @() })
        }
    }
    $nodeCommand = Get-Command node -ErrorAction SilentlyContinue
    if ($nodeCommand) {
        $bundledPython = Join-Path (Split-Path $nodeCommand.Source -Parent) '..\..\python\python.exe'
        if (Test-Path -LiteralPath $bundledPython -PathType Leaf) {
            $candidates.Add(@{ Executable = $bundledPython; Prefix = @() })
        }
    }
    try {
        $packages = Get-AppxPackage -Name 'OpenAI.CodexPrimaryRuntime*' -ErrorAction Stop
        foreach ($package in $packages) {
            $bundledPython = Join-Path $package.InstallLocation 'dependencies\python\python.exe'
            if (Test-Path -LiteralPath $bundledPython -PathType Leaf) {
                $candidates.Add(@{ Executable = $bundledPython; Prefix = @() })
            }
        }
    } catch { }
}

$selected = $null
foreach ($candidate in $candidates) {
    try {
        $prefixArguments = @($candidate.Prefix)
        & $candidate.Executable @prefixArguments -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' *> $null
        if ($LASTEXITCODE -eq 0) { $selected = $candidate; break }
    } catch { }
}
if (-not $selected) {
    throw 'Python 3.10 or newer was not found. Pass -Python C:\path\to\python.exe or install Python, then rerun.'
}

$runnerArguments = @((Join-Path $PSScriptRoot 'run_communication_recovery.py'))
if ($AnalyzeRun) {
    if ($DryRun -or $Resume -or $Pause -or $OutputDir -or $SourceRun) {
        throw '-AnalyzeRun cannot be combined with run, pause, output, or source options.'
    }
    $runnerArguments += @('--analyze-run', $AnalyzeRun)
} else {
    if (-not $OutputDir) { $OutputDir = Join-Path $PSScriptRoot 'results\communication-pilot\windows-v2' }
    $runnerArguments += @('--output-dir', $OutputDir)
    if ($SourceRun) { $runnerArguments += @('--source-run', $SourceRun) }
    if ($DryRun) { $runnerArguments += '--dry-run' }
    if ($Resume) { $runnerArguments += '--resume' }
    if ($Pause) { $runnerArguments += '--pause' }
    if (-not $Pause) { $runnerArguments += @('--timeout', $Timeout.ToString()) }
}
$prefixArguments = @($selected.Prefix)
& $selected.Executable @prefixArguments @runnerArguments
exit $LASTEXITCODE
