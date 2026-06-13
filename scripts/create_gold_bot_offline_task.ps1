# create_gold_bot_offline_task.ps1
# ---------------------------------
# LM96A - create (or plan) a Windows Scheduled Task that runs the Gold Bot OFFLINE
# maintenance cycle on a schedule. It only ever launches:
#   scripts/start_gold_bot_offline_cycle.ps1
# which runs the whitelisted gateway action `daily_cycle_offline` (no demo session,
# no broker orders, no live, Discord preview only). This task runs offline
# maintenance only. It does not start demo sessions or live trading.
#
# DEFAULT = plan only (WhatIf). Nothing is registered unless you pass -Register.
# Runs in the CURRENT USER context at a limited run level - no admin required.
# No Discord webhook or any secret is stored in the task.
#
# Usage:
#   .\scripts\create_gold_bot_offline_task.ps1 -WhatIfPlan
#   .\scripts\create_gold_bot_offline_task.ps1 -Register -Frequency Hourly -EveryHours 1
#   .\scripts\create_gold_bot_offline_task.ps1 -Register -Frequency Daily -At "09:00"
#   .\scripts\create_gold_bot_offline_task.ps1 -Register -Force        # replace existing
param(
    [string]$TaskName = "LumoraGoldBotOfflineCycle",
    [ValidateSet("Hourly", "Daily")] [string]$Frequency = "Hourly",
    [string]$At = "09:00",
    [int]$EveryHours = 1,
    [switch]$WhatIfPlan,
    [switch]$Register,
    [switch]$Force,
    [string]$RepoRoot
)
$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $RepoRoot = Split-Path -Parent $PSScriptRoot
}
$startScript = Join-Path $RepoRoot "scripts\start_gold_bot_offline_cycle.ps1"
$exe = "powershell.exe"
$psArgs = "-NoProfile -ExecutionPolicy Bypass -File `"$startScript`""
$fullCommand = "$exe $psArgs"

# What the scheduled run ultimately executes (offline gateway action only).
$effectivePython = "python scripts/run_gold_bot_command_gateway.py --action daily_cycle_offline --execute --include-real-trades --write-log"

# -WhatIfPlan forces plan even if -Register is also passed; default (no -Register) is plan.
$doRegister = $Register -and -not $WhatIfPlan

$triggerDesc = if ($Frequency -eq "Daily") { "Daily at $At" } else { "Every $EveryHours hour(s)" }

Write-Host "================================================================"
Write-Host " Lumora Gold Bot  -  OFFLINE TASK $([string]::Format('{0}', $(if ($doRegister) {'REGISTER'} else {'PLAN / dry-run'})))"
Write-Host "================================================================"
Write-Host " Task name        : $TaskName"
Write-Host " Schedule         : $triggerDesc"
Write-Host " Working dir      : $RepoRoot"
Write-Host " Run as           : $([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) (limited, no admin)"
Write-Host " Action command   : $fullCommand"
Write-Host " Scheduled run    : $effectivePython"
Write-Host " ----------------------------------------------------------------"
Write-Host " This task runs offline maintenance only. It does not start demo"
Write-Host " sessions or live trading. No Discord is sent and no secret/webhook"
Write-Host " is stored in the task."
Write-Host "================================================================"

if (-not $doRegister) {
    Write-Host " DRY-RUN (plan only) - nothing was registered."
    Write-Host " Re-run with -Register to create the task, e.g.:"
    Write-Host "   .\scripts\create_gold_bot_offline_task.ps1 -Register -Frequency $Frequency"
    exit 0
}

# ---- registration path (current user, no admin) -------------------------------
$action = New-ScheduledTaskAction -Execute $exe -Argument $psArgs -WorkingDirectory $RepoRoot

if ($Frequency -eq "Daily") {
    $trigger = New-ScheduledTaskTrigger -Daily -At $At
}
else {
    # Hourly: fire once, then repeat every N hours (re-register to extend the window).
    $trigger = New-ScheduledTaskTrigger -Once -At (Get-Date "00:00") `
        -RepetitionInterval (New-TimeSpan -Hours $EveryHours) `
        -RepetitionDuration (New-TimeSpan -Days 365)
}

$userId = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal = New-ScheduledTaskPrincipal -UserId $userId -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing -and -not $Force) {
    Write-Error "Task '$TaskName' already exists. Re-run with -Force to replace it."
    exit 2
}
if ($existing -and $Force) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Principal $principal -Settings $settings `
    -Description "Lumora Gold Bot offline maintenance cycle (gateway daily_cycle_offline). No demo trading, no live, no Discord send, no secrets." | Out-Null

Write-Host " Registered scheduled task '$TaskName'."
Write-Host " Verify : Get-ScheduledTask -TaskName '$TaskName'"
Write-Host " Disable: Disable-ScheduledTask -TaskName '$TaskName'"
Write-Host " Delete : Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false"
exit 0
