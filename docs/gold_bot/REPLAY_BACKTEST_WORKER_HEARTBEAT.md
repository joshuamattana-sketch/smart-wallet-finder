# Gold Bot — Replay / Backtest Worker Heartbeat (LM98B)

Upgrades the LM98A reporter into an **offline worker**: while the market is closed it
actually RUNS new no-lookahead replay/backtest jobs (LM85A) across a timeframe / risk
/ horizon plan, refreshes the LM86A scorecard after each job, and reports the
replay-data **growth** (files/rows/trades deltas) + performance via Discord every N
minutes. It calls the existing `run_replay` service directly — no subprocess, no shell.

- Service: `services/gold_bot_replay_backtest_worker_heartbeat.py`
- CLI: `scripts/run_gold_bot_replay_backtest_worker_heartbeat.py`
- PowerShell: `scripts/start_gold_bot_replay_backtest_worker_heartbeat.ps1`
- Artifacts (gitignored): `data/gold_bot/replay_worker/worker_*.json|.md`, `worker_events.jsonl`, `worker_latest.*`

## Each cycle

1. Pick the next job from the plan (`timeframes × risk-modes × horizons`, all `max-bars`).
2. Run that replay job offline (`run_replay`, demo decision engine, no MT5, no orders).
3. Refresh the scorecard (global, all replay files) at the job's horizon.
4. Read active modifiers + real demo-outcome count.
5. Build a growth report (before → after deltas) and preview / send Discord.
6. Persist `worker_*.json/.md` + append `worker_events.jsonl`.

A job that can't run (e.g. missing history for a timeframe) is **skipped** with a clear
warning — the worker keeps going and never crashes.

## Safety (hard-coded)

environment **replay/offline worker** · broker orders **disabled** · live **locked**.
No MT5 order senders, no demo session, no `--confirm-demo-session`, no
`--allow-live-trading`, no arbitrary shell. No network unless `--send-discord` with a
**valid** `LUMORA_GOLD_DISCORD_WEBHOOK_URL` (a bad URL fails safely, no traceback). The
webhook value is never printed or logged.

## Commands

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder"

# show the job plan (runs nothing)
python scripts/run_gold_bot_replay_backtest_worker_heartbeat.py --dry-run-plan

# one job + one heartbeat (preview)
python scripts/run_gold_bot_replay_backtest_worker_heartbeat.py --once --timeframes M1 --risk-modes scalp --horizons 15 --max-bars 1000

# short loop (preview)
python scripts/run_gold_bot_replay_backtest_worker_heartbeat.py --duration-minutes 5 --report-every-minutes 1 --job-every-minutes 1 --timeframes M1 --risk-modes scalp --horizons 15 --max-bars 1000

# normal loop (preview)
python scripts/run_gold_bot_replay_backtest_worker_heartbeat.py --duration-minutes 240 --report-every-minutes 15 --job-every-minutes 15 --timeframes M1,M5 --risk-modes balanced,scalp --horizons 15,30 --max-bars 1000

# send to Discord (valid env webhook required; never commit it)
$env:LUMORA_GOLD_DISCORD_WEBHOOK_URL="YOUR_WEBHOOK_URL"
python scripts/run_gold_bot_replay_backtest_worker_heartbeat.py --duration-minutes 240 --report-every-minutes 15 --job-every-minutes 15 --send-discord
Remove-Item Env:LUMORA_GOLD_DISCORD_WEBHOOK_URL

# PowerShell helper
.\scripts\start_gold_bot_replay_backtest_worker_heartbeat.ps1 -DurationMinutes 240 -ReportEveryMinutes 15 -JobEveryMinutes 15 -Timeframes "M1,M5" -RiskModes "balanced,scalp" -Horizons "15,30" -MaxBars 1000

# tests (offline; injected job runner / clock / sender)
python -m pytest tests/test_gold_bot_replay_backtest_worker_heartbeat.py -q
```

## Sample report

```
**Lumora Replay Worker · 15m Update**
Mode: replay/offline worker | Current job: M1 / scalp / h15 / 1000 bars
Job: 3 | Elapsed: 30m | Remaining: 30m

Replay growth:
Files 36 -> 38 (+2)
Rows 17,700 -> 18,900 (+1,200)
Trades 11,776 -> 12,540 (+764)
No-trade 5,924 -> 6,360 (+436)

Performance:
Winrate 27% | Expectancy -43.2pt | Status avoid

Best tactics:
1. liquidity_sweep_reclaim +15.4pt / 790 trades
2. breakout_retest -24.9pt / 1,020 trades
3. momentum -48.1pt / 4,500 trades
Weak/Avoid: breakout_retest, fvg_retest, momentum
Learning: replay-dominant | real demo trades 0
Active modifiers: breakout_retest -8, fvg_retest -8, momentum -8

Replay worker only. No MT5 orders, no demo session, live locked.
```

## Notes

- Needs local history (`scripts/run_gold_bot_history_backfill.py --timeframes M1,M5`).
  Jobs for a timeframe with no history are skipped with a warning, not a crash.
- In this version a job + a heartbeat run together each cycle; the cadence is
  `min(report-every, job-every)` minutes.
- Never store the webhook in a scheduled task — sending stays explicit + env-gated.
