# Gold Bot — Windows Task Scheduler (offline maintenance)

**LM96A.** A Windows scheduling helper that runs the Gold Bot **offline maintenance
cycle** on a schedule. It is a thin wrapper around the existing LM94A gateway — it
adds no trading logic, no UI, and no API.

## What this does

Schedules a task that runs exactly one whitelisted gateway action:

```
python scripts/run_gold_bot_command_gateway.py --action daily_cycle_offline --execute --include-real-trades --write-log
```

That offline cycle: syncs trade outcomes → runs the learning cycle → builds the
session review → **previews** the Discord digest (never sends) → writes redacted
command logs.

## What it does NOT do

- **No demo trading scheduled by default** — no demo session, no `--confirm-*` flags.
- **No live trading** — there is no environment/live knob anywhere in these scripts.
- **No Discord send** — preview only; the webhook is never read or stored.
- **No secrets** stored in the task. **No admin** required (current-user, limited).
- Does not bypass the gateway, safety supervisor, or risk gate (no order path is
  even reached — this is offline maintenance).

## Safe default command

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder"
.\scripts\start_gold_bot_offline_cycle.ps1
```

Optional: write a transcript to `data/gold_bot/task_logs/` (gitignored):

```powershell
.\scripts\start_gold_bot_offline_cycle.ps1 -LogTranscript
```

## Plan the scheduled task (dry-run, default)

Nothing is registered without `-Register`:

```powershell
.\scripts\create_gold_bot_offline_task.ps1 -WhatIfPlan
```

## Register an hourly task

```powershell
.\scripts\create_gold_bot_offline_task.ps1 -Register -Frequency Hourly -EveryHours 1
```

## Register a daily task

```powershell
.\scripts\create_gold_bot_offline_task.ps1 -Register -Frequency Daily -At "09:00"
```

Replace an existing task with `-Force`. The task runs as the current user at a
limited run level (no admin prompt).

## Disable / delete the task

```powershell
Disable-ScheduledTask  -TaskName "LumoraGoldBotOfflineCycle"
Unregister-ScheduledTask -TaskName "LumoraGoldBotOfflineCycle" -Confirm:$false
```

## Where logs go

- Gateway run logs: `data/gold_bot/commands/command_*.json` / `.jsonl` (LM94A, gitignored).
- Daily-cycle run logs: `data/gold_bot/runs/run_*.json` / `.jsonl` (gitignored).
- Optional task transcripts: `data/gold_bot/task_logs/offline_cycle_*.log` (gitignored).

## Check the latest status in the UI

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder\lumora-web"
npm run dev
# open http://localhost:3000/gold-bot  (read-only OBSERVE strip + REPORT review)
```

## Sample XML

A generic Task Scheduler export is provided as a template only:
`docs/gold_bot/templates/gold_bot_offline_task.xml.sample`. Replace `<REPO_ROOT>`
and `<USER>` before importing. Machine-specific XML is never committed.

## Warnings

- **No demo trading is scheduled by default.** Starting a guarded demo session is a
  separate, explicit, interactive action (run it yourself from the UI or CLI).
- **Do not store the Discord webhook in the task.** The scheduled cycle previews
  only. If you later want to send a review to Discord, do it as a separate **manual**
  flow with the env var set for that one run — never bake it into a scheduled task.
