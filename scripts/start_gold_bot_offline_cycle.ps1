# start_gold_bot_offline_cycle.ps1
# ---------------------------------
# LM96A - launcher for the Gold Bot OFFLINE maintenance cycle, via the LM94A gateway.
#
# Runs ONLY the whitelisted offline gateway action:
#   python scripts/run_gold_bot_command_gateway.py --action daily_cycle_offline --execute --include-real-trades --write-log
#
# That means: NO demo session, NO broker orders, NO live trading, Discord PREVIEW
# only (never sent). It syncs trade outcomes, runs the learning cycle, builds the
# session review, and writes redacted command logs. No secrets are read or stored.
# Every order path still passes the safety supervisor + risk gate (none are reached
# here - this is offline maintenance).
#
# Usage:
#   .\scripts\start_gold_bot_offline_cycle.ps1
#   .\scripts\start_gold_bot_offline_cycle.ps1 -LogTranscript
#   .\scripts\start_gold_bot_offline_cycle.ps1 -IncludeRealTrades:$false
param(
    [string]$PythonExe = "python",
    [string]$RepoRoot,
    [bool]$IncludeRealTrades = $true,
    [switch]$LogTranscript
)
$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $RepoRoot = Split-Path -Parent $PSScriptRoot
}
Set-Location $RepoRoot

# Optional transcript -> data/gold_bot/task_logs/offline_cycle_<ts>.log (gitignored)
$transcriptStarted = $false
if ($LogTranscript) {
    $logDir = Join-Path $RepoRoot "data/gold_bot/task_logs"
    if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Force -Path $logDir | Out-Null }
    $logPath = Join-Path $logDir ("offline_cycle_{0}.log" -f (Get-Date -Format "yyyyMMdd_HHmmss"))
    try { Start-Transcript -Path $logPath -Force | Out-Null; $transcriptStarted = $true } catch {}
}

# Fixed, whitelisted offline gateway command. NO demo session, NO discord send.
$cmd = @("scripts/run_gold_bot_command_gateway.py", "--action", "daily_cycle_offline",
         "--execute", "--write-log")
if ($IncludeRealTrades) { $cmd += "--include-real-trades" }

$startTime = Get-Date
Write-Host "================================================================"
Write-Host " Lumora Gold Bot  -  OFFLINE MAINTENANCE CYCLE (gateway)"
Write-Host " OFFLINE ONLY: no demo session, no broker orders, no live, Discord preview only"
Write-Host " repo  : $RepoRoot"
Write-Host " start : $($startTime.ToString('u'))"
Write-Host " run   : $PythonExe $($cmd -join ' ')"
Write-Host "================================================================"

& $PythonExe @cmd
$code = $LASTEXITCODE

$endTime = Get-Date
$elapsed = [int]([TimeSpan]($endTime - $startTime)).TotalSeconds
Write-Host "----------------------------------------------------------------"
Write-Host " end   : $($endTime.ToString('u'))   exit=$code   elapsed=${elapsed}s"
Write-Host " Offline maintenance only. No demo trading, no live, no Discord sent, no secrets."
Write-Host "================================================================"

if ($transcriptStarted) { try { Stop-Transcript | Out-Null } catch {} }
exit $code
