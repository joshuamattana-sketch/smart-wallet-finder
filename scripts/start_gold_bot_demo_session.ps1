# start_gold_bot_demo_session.ps1
# --------------------------------
# LM88A - launcher for a bounded Gold Bot DEMO auto-session.
# MT5 DEMO ONLY. NEVER live trading. SAFETY SUPERVISOR ALWAYS ON.
#
# DEFAULT: observe-only session. SENDS NO ORDERS.
# Demo orders are ONLY armed when you explicitly opt in with -ConfirmDemoSession.
# Even then it is MT5 demo only and still passes through the worker demo flags,
# the LM75 risk gate, the macro lockout and the LM87A safety supervisor.
#
# Usage:
#   .\scripts\start_gold_bot_demo_session.ps1                                   # observe only
#   .\scripts\start_gold_bot_demo_session.ps1 -ConfirmDemoSession -DurationMinutes 5 -MaxTrades 3
param(
    [switch]$ConfirmDemoSession,
    [double]$DurationMinutes = 30,
    [int]$MaxTrades = 10,
    [string]$RiskMode = "scalp",
    [double]$IntervalSeconds = 5
)
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

Write-Host "================================================================"
Write-Host " Lumora Gold Bot  -  DEMO AUTO-SESSION ($RiskMode)"
Write-Host " MT5 DEMO ONLY  |  NEVER LIVE  |  SAFETY SUPERVISOR ALWAYS ON"

if (-not $ConfirmDemoSession) {
    Write-Host " orders: DISABLED (observe-only session)"
    Write-Host " duration: $DurationMinutes min   repo: $RepoRoot"
    Write-Host "================================================================"
    Write-Host " A demo session that SENDS ORDERS requires explicit -ConfirmDemoSession."
    Write-Host " To arm an MT5 demo session re-run, e.g.:"
    Write-Host "   .\scripts\start_gold_bot_demo_session.ps1 -ConfirmDemoSession -DurationMinutes 5 -MaxTrades 3"
    Write-Host " Stop with Ctrl+C."
    Write-Host ""
    python scripts/run_gold_bot_demo_session.py --risk-mode $RiskMode --duration-minutes $DurationMinutes --max-trades $MaxTrades --interval-seconds $IntervalSeconds --use-learning-modifiers
    exit $LASTEXITCODE
}

Write-Host " orders: ARMED (demo session) -- MT5 DEMO ONLY"
Write-Host " duration: $DurationMinutes min   max-trades: $MaxTrades   repo: $RepoRoot"
Write-Host "================================================================"
Write-Host " Demo orders may be sent on a verified DEMO account if the worker demo"
Write-Host " flags + risk gate + safety supervisor allow it. Session stops on its"
Write-Host " duration / max-trades / drawdown / safety limits. Never live."
Write-Host " Stop with Ctrl+C."
Write-Host ""

python scripts/run_gold_bot_demo_session.py --confirm-demo-session --risk-mode $RiskMode --duration-minutes $DurationMinutes --max-trades $MaxTrades --interval-seconds $IntervalSeconds --use-learning-modifiers
exit $LASTEXITCODE
