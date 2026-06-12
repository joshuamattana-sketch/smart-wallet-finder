# start_gold_bot_observe.ps1
# ---------------------------
# LM82A - convenience launcher for the Gold Bot worker in OBSERVE mode.
# MT5 DEMO ONLY. No live trading. Sends NO orders (observe only).
#
# Run from repo root, or directly from the scripts folder:
#   .\scripts\start_gold_bot_observe.ps1
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

Write-Host "================================================================"
Write-Host " Lumora Gold Bot  -  OBSERVE (balanced)"
Write-Host " MT5 DEMO ONLY  |  NO LIVE TRADING  |  orders: DISABLED (observe)"
Write-Host " repo: $RepoRoot"
Write-Host "================================================================"
Write-Host " Stop with Ctrl+C."
Write-Host ""

python scripts/run_gold_bot_worker.py --mode observe --risk-mode balanced --interval-seconds 5
exit $LASTEXITCODE
