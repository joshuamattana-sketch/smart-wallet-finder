# start_gold_bot_replay_backtest_heartbeat.ps1
# ---------------------------------------------
# LM98A - launcher for the Gold Bot REPLAY / BACKTEST heartbeat.
# DEFAULT = preview (prints Discord-style updates, sends NOTHING). Sending needs
# BOTH -SendDiscord AND the env LUMORA_GOLD_DISCORD_WEBHOOK_URL. Replay/offline
# only: no MT5 orders, no demo session, no live, no secrets handled here.
#
# Usage:
#   .\scripts\start_gold_bot_replay_backtest_heartbeat.ps1 -Once
#   .\scripts\start_gold_bot_replay_backtest_heartbeat.ps1 -DurationMinutes 60 -ReportEveryMinutes 15
#   $env:LUMORA_GOLD_DISCORD_WEBHOOK_URL = "YOUR_WEBHOOK_URL"
#   .\scripts\start_gold_bot_replay_backtest_heartbeat.ps1 -DurationMinutes 60 -ReportEveryMinutes 15 -SendDiscord
#   Remove-Item Env:LUMORA_GOLD_DISCORD_WEBHOOK_URL
param(
    [int]$DurationMinutes = 60,
    [int]$ReportEveryMinutes = 15,
    [string]$RiskMode = "balanced",
    [string]$TimeFrame = "M1",
    [int]$Horizon = 15,
    [switch]$SendDiscord,
    [switch]$Once
)
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$cmd = @("scripts/run_gold_bot_replay_backtest_heartbeat.py",
         "--duration-minutes", $DurationMinutes,
         "--report-every-minutes", $ReportEveryMinutes,
         "--risk-mode", $RiskMode,
         "--timeframe", $TimeFrame,
         "--horizon", $Horizon)
if ($Once)        { $cmd += "--once" }
if ($SendDiscord) { $cmd += "--send-discord" }

Write-Host "================================================================"
Write-Host " Lumora Gold Bot  -  REPLAY BACKTEST HEARTBEAT  ($(if ($SendDiscord) {'SEND'} else {'PREVIEW'}))"
Write-Host " REPLAY/OFFLINE ONLY: no MT5 orders, no demo session, no live"
Write-Host " repo: $RepoRoot"
Write-Host "================================================================"

python @cmd
exit $LASTEXITCODE
