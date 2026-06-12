# start_gold_bot_macro_scalp.ps1
# ------------------------------
# LM82A - convenience launcher for the Gold Bot worker in SCALP OBSERVE mode
# with the LM77A sample macro/news event context (event lockout windows).
# MT5 DEMO ONLY. No live trading. Sends NO orders (observe only).
#
# Run from repo root, or directly from the scripts folder:
#   .\scripts\start_gold_bot_macro_scalp.ps1
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

Write-Host "================================================================"
Write-Host " Lumora Gold Bot  -  SCALP OBSERVE + MACRO CONTEXT"
Write-Host " MT5 DEMO ONLY  |  NO LIVE TRADING  |  orders: DISABLED (observe)"
Write-Host " macro events: data/gold_bot/macro_events.sample.json"
Write-Host " repo: $RepoRoot"
Write-Host "================================================================"
Write-Host " Stop with Ctrl+C."
Write-Host ""

python scripts/run_gold_bot_worker.py --mode observe --risk-mode scalp --macro-events-file data/gold_bot/macro_events.sample.json --interval-seconds 5
exit $LASTEXITCODE
