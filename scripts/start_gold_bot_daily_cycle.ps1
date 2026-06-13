# start_gold_bot_daily_cycle.ps1
# -------------------------------
# LM92A - launcher for the Gold Bot daily cycle orchestrator.
# DEFAULT = plan / dry-run. Runs NOTHING, makes NO demo trades, sends NO Discord.
#
# Trading happens only with BOTH -Execute AND -ConfirmDemoSession (and even then
# the existing session runner + safety supervisor + risk gate still gate every
# order). Discord sends only with -SendDiscord. No secrets handled here.
#
# Usage:
#   .\scripts\start_gold_bot_daily_cycle.ps1                                         # plan only
#   .\scripts\start_gold_bot_daily_cycle.ps1 -Execute -IncludeRealTrades             # safe offline steps (no trades)
#   .\scripts\start_gold_bot_daily_cycle.ps1 -Execute -ConfirmDemoSession -DurationMinutes 5 -MaxTrades 3 -RiskMode scalp -UseLearningModifiers -IncludeRealTrades
param(
    [switch]$Execute,
    [switch]$ConfirmDemoSession,
    [double]$DurationMinutes = 5,
    [int]$MaxTrades = 3,
    [string]$RiskMode = "scalp",
    [switch]$UseLearningModifiers,
    [switch]$IncludeRealTrades,
    [switch]$SendDiscord,
    [switch]$ContinueOnError
)
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$cmd = @("scripts/run_gold_bot_daily_cycle.py",
         "--duration-minutes", $DurationMinutes,
         "--max-trades", $MaxTrades,
         "--risk-mode", $RiskMode)
if ($Execute)              { $cmd += "--execute" }
if ($ConfirmDemoSession)   { $cmd += "--confirm-demo-session" }
if ($UseLearningModifiers) { $cmd += "--use-learning-modifiers" }
if ($IncludeRealTrades)    { $cmd += "--include-real-trades" }
if ($SendDiscord)          { $cmd += "--send-discord" }
if ($ContinueOnError)      { $cmd += "--continue-on-error" }

Write-Host "================================================================"
Write-Host " Lumora Gold Bot  -  DAILY CYCLE  ($(if ($Execute) {'EXECUTE'} else {'PLAN / dry-run'}))"
Write-Host " MT5 DEMO ONLY  |  NEVER LIVE  |  trades only with -Execute -ConfirmDemoSession"
Write-Host " repo: $RepoRoot"
Write-Host "================================================================"

python @cmd
exit $LASTEXITCODE
