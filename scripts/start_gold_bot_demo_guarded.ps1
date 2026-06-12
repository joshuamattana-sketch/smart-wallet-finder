# start_gold_bot_demo_guarded.ps1
# -------------------------------
# LM82A - guarded launcher for the Gold Bot worker.
# MT5 DEMO ONLY. NEVER live trading.
#
# DEFAULT: observe / dry-run. SENDS NO ORDERS.
# Demo execution flags (--auto-execute-demo --confirm-demo-order) are ONLY
# passed when you explicitly opt in with -ConfirmDemoExecution. Even then it is
# MT5 demo only and still passes through the LM75 risk gate / macro lockout /
# no-stacking guards in the worker.
#
# Usage:
#   .\scripts\start_gold_bot_demo_guarded.ps1                      # observe only
#   .\scripts\start_gold_bot_demo_guarded.ps1 -ConfirmDemoExecution  # demo orders ARMED
param(
    [switch]$ConfirmDemoExecution,
    [string]$RiskMode = "scalp",
    [int]$IntervalSeconds = 5
)
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

Write-Host "================================================================"
Write-Host " Lumora Gold Bot  -  DEMO GUARDED ($RiskMode)"
Write-Host " MT5 DEMO ONLY  |  NO LIVE TRADING"

if (-not $ConfirmDemoExecution) {
    Write-Host " orders: DISABLED (observe / dry-run)"
    Write-Host " repo: $RepoRoot"
    Write-Host "================================================================"
    Write-Host " Demo execution requires explicit -ConfirmDemoExecution."
    Write-Host " To arm demo orders (MT5 demo only) re-run:"
    Write-Host "   .\scripts\start_gold_bot_demo_guarded.ps1 -ConfirmDemoExecution"
    Write-Host " Stop with Ctrl+C."
    Write-Host ""
    python scripts/run_gold_bot_worker.py --mode observe --risk-mode $RiskMode --interval-seconds $IntervalSeconds
    exit $LASTEXITCODE
}

Write-Host " orders: ARMED (demo execution) -- MT5 DEMO ONLY"
Write-Host " repo: $RepoRoot"
Write-Host "================================================================"
Write-Host " Demo orders may be sent on a verified DEMO account if the risk gate"
Write-Host " approves (no macro lockout, no open XAUUSD position). Never live."
Write-Host " Stop with Ctrl+C."
Write-Host ""

python scripts/run_gold_bot_worker.py --mode demo --risk-mode $RiskMode --auto-execute-demo --confirm-demo-order --interval-seconds $IntervalSeconds
exit $LASTEXITCODE
