# start_gold_bot_first_run_preflight.ps1
# ---------------------------------------
# LM92B - launcher for the first market-open demo run PREFLIGHT.
# READ-ONLY GO / NO-GO. Places NO orders, sends NO Discord, prints NO secrets.
#
# Usage:
#   .\scripts\start_gold_bot_first_run_preflight.ps1                      # market-open preflight
#   .\scripts\start_gold_bot_first_run_preflight.ps1 -SkipMt5 -SkipSafety # weekend/offline prep
#   .\scripts\start_gold_bot_first_run_preflight.ps1 -UseLearningModifiers -IncludeRealTrades -Write
param(
    [switch]$SkipMt5,
    [switch]$SkipSafety,
    [double]$DurationMinutes = 5,
    [int]$MaxTrades = 3,
    [string]$RiskMode = "scalp",
    [switch]$UseLearningModifiers,
    [switch]$IncludeRealTrades,
    [switch]$SendDiscord,
    [switch]$CheckDiscordEnv,
    [switch]$Write
)
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$cmd = @("scripts/run_gold_bot_first_run_preflight.py",
         "--duration-minutes", $DurationMinutes,
         "--max-trades", $MaxTrades,
         "--risk-mode", $RiskMode)
if ($SkipMt5)              { $cmd += "--skip-mt5" }
if ($SkipSafety)           { $cmd += "--skip-safety" }
if ($UseLearningModifiers) { $cmd += "--use-learning-modifiers" }
if ($IncludeRealTrades)    { $cmd += "--include-real-trades" }
if ($SendDiscord)          { $cmd += "--send-discord" }
if ($CheckDiscordEnv)      { $cmd += "--check-discord-env" }
if ($Write)                { $cmd += "--write" }

Write-Host "================================================================"
Write-Host " Lumora Gold Bot  -  FIRST MARKET-OPEN PREFLIGHT (read-only)"
Write-Host " MT5 DEMO ONLY  |  NEVER LIVE  |  no orders, no Discord send"
Write-Host "================================================================"

python @cmd
exit $LASTEXITCODE
