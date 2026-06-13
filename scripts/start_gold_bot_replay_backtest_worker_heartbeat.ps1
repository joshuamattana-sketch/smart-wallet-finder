# start_gold_bot_replay_backtest_worker_heartbeat.ps1
# ----------------------------------------------------
# LM98B - launcher for the Gold Bot REPLAY/BACKTEST WORKER heartbeat.
# DEFAULT = preview (runs offline replay jobs + prints growth updates, sends NOTHING).
# Sending needs BOTH -SendDiscord AND a valid env LUMORA_GOLD_DISCORD_WEBHOOK_URL.
# Replay/offline only: no MT5 orders, no demo session, no live, no secrets here.
#
# Usage:
#   .\scripts\start_gold_bot_replay_backtest_worker_heartbeat.ps1 -DryRunPlan
#   .\scripts\start_gold_bot_replay_backtest_worker_heartbeat.ps1 -Once -Timeframes "M1" -RiskModes "scalp" -Horizons "15" -MaxBars 1000
#   .\scripts\start_gold_bot_replay_backtest_worker_heartbeat.ps1 -DurationMinutes 240 -ReportEveryMinutes 15 -JobEveryMinutes 15 -Timeframes "M1,M5" -RiskModes "balanced,scalp" -Horizons "15,30" -MaxBars 1000
param(
    [int]$DurationMinutes = 240,
    [int]$ReportEveryMinutes = 15,
    [int]$JobEveryMinutes = 15,
    [string]$Timeframes = "M1,M5",
    [string]$RiskModes = "balanced,scalp",
    [string]$Horizons = "15,30",
    [int]$MaxBars = 1000,
    [switch]$SendDiscord,
    [switch]$Once,
    [switch]$DryRunPlan
)
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$cmd = @("scripts/run_gold_bot_replay_backtest_worker_heartbeat.py",
         "--duration-minutes", $DurationMinutes,
         "--report-every-minutes", $ReportEveryMinutes,
         "--job-every-minutes", $JobEveryMinutes,
         "--timeframes", $Timeframes,
         "--risk-modes", $RiskModes,
         "--horizons", $Horizons,
         "--max-bars", $MaxBars)
if ($Once)       { $cmd += "--once" }
if ($DryRunPlan) { $cmd += "--dry-run-plan" }
if ($SendDiscord){ $cmd += "--send-discord" }

Write-Host "================================================================"
Write-Host " Lumora Gold Bot  -  REPLAY BACKTEST WORKER  ($(if ($SendDiscord) {'SEND'} else {'PREVIEW'}))"
Write-Host " REPLAY/OFFLINE ONLY: runs replay jobs, no MT5 orders, no demo session, no live"
Write-Host " repo: $RepoRoot"
Write-Host "================================================================"

python @cmd
exit $LASTEXITCODE
