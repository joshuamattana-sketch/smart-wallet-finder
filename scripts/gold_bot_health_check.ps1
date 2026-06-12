# gold_bot_health_check.ps1
# --------------------------
# LM82A - one-shot Gold Bot health check. READ-ONLY / dry-run. Sends NO orders.
# Runs the MT5 demo connector probe (account/symbol/candles/history) then the
# decision probe (dry-run) so you can confirm the stack is wired before looping.
#
# Run from repo root, or directly from the scripts folder:
#   .\scripts\gold_bot_health_check.ps1
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

Write-Host "================================================================"
Write-Host " Lumora Gold Bot  -  HEALTH CHECK (read-only / dry-run)"
Write-Host " MT5 DEMO ONLY  |  NO LIVE TRADING  |  orders: DISABLED"
Write-Host " repo: $RepoRoot"
Write-Host "================================================================"

Write-Host ""
Write-Host "[1/2] MT5 demo connector probe (read-only) ..."
python scripts/run_mt5_demo_connector_probe.py --bars 10 --history-debug
$probeExit = $LASTEXITCODE

Write-Host ""
Write-Host "[2/2] Decision engine probe (balanced, dry-run) ..."
python scripts/run_gold_bot_decision_probe.py --risk-mode balanced --dry-run
$decisionExit = $LASTEXITCODE

Write-Host ""
Write-Host "Health check done. connector exit=$probeExit  decision exit=$decisionExit"
if ($probeExit -ne 0 -or $decisionExit -ne 0) { exit 1 } else { exit 0 }
