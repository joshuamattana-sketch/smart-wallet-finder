# Gold Bot — Replay / Backtest Heartbeat (LM98A)

A long-running **replay/offline** runner that refreshes the learning scorecard and
emits a compact Discord progress report every N minutes (default 15). It is a
reporting loop over the existing LM86A scorecard — it adds no strategy, risk, or
modifier logic.

- Service: `services/gold_bot_replay_backtest_heartbeat.py`
- CLI: `scripts/run_gold_bot_replay_backtest_heartbeat.py`
- PowerShell: `scripts/start_gold_bot_replay_backtest_heartbeat.ps1`
- Artifacts (gitignored): `data/gold_bot/replay_heartbeat/heartbeat_*.json` / `.md` + `heartbeat_latest.*`

## What it does each heartbeat

1. Rebuilds the scorecard from stored replay JSONL (offline, LM86A service — no subprocess, no MT5).
2. Reads `active_demo_modifiers.json` and counts real `demo_trade_outcome` events.
3. Builds a compact Discord message: progress, replay rows/trades, winrate/expectancy/status, best tactics, weak/avoid, confidence buckets, learning mode, active modifiers, and the replay-only safety line.
4. Writes `heartbeat_<ts>.json` + `.md` (and `heartbeat_latest.*`).
5. Previews by default; sends only with `--send-discord` + the env webhook.

## Safety (hard-coded)

- environment **replay/offline** · execution **observe** · broker orders **disabled** · live **locked**.
- No MT5 order senders imported, no demo session runner, no arbitrary commands.
- No network call unless `--send-discord`. The webhook value is never printed or logged (redacted target only).

## Commands

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder"

# one heartbeat, preview only
python scripts/run_gold_bot_replay_backtest_heartbeat.py --once

# fast local loop (preview)
python scripts/run_gold_bot_replay_backtest_heartbeat.py --duration-minutes 1 --report-every-minutes 1

# normal preview (1h, every 15m)
python scripts/run_gold_bot_replay_backtest_heartbeat.py --duration-minutes 60 --report-every-minutes 15

# send to Discord (needs the env webhook; never commit it)
$env:LUMORA_GOLD_DISCORD_WEBHOOK_URL = "YOUR_WEBHOOK_URL"
python scripts/run_gold_bot_replay_backtest_heartbeat.py --duration-minutes 60 --report-every-minutes 15 --send-discord
Remove-Item Env:LUMORA_GOLD_DISCORD_WEBHOOK_URL

# PowerShell helper (preview / send)
.\scripts\start_gold_bot_replay_backtest_heartbeat.ps1 -DurationMinutes 60 -ReportEveryMinutes 15
.\scripts\start_gold_bot_replay_backtest_heartbeat.ps1 -DurationMinutes 60 -ReportEveryMinutes 15 -SendDiscord

# tests (offline; no network, no MT5)
python -m pytest tests/test_gold_bot_replay_backtest_heartbeat.py -q
```

## CLI flags

`--duration-minutes 60` · `--report-every-minutes 15` · `--timeframe M1` ·
`--risk-mode balanced` · `--horizon 15` · `--min-samples 10` ·
`--include-real-trades` / `--no-include-real-trades` (default on) ·
`--real-trade-weight 2.0` · `--min-real-trades 5` · `--max-bars N` ·
`--send-discord` · `--once` · `--sleep-seconds N` (testing) · `--out-dir` · `--json`.

## Sample report

```
**Lumora Replay Backtest · 15m Update**
Mode: replay/offline | Symbol: XAUUSD | TF: M1 | Risk: balanced | h15
Heartbeat: 2 | Elapsed: 15m | Remaining: 45m

Replay: 37 files | 17,900 rows | 11,926 trades | 5,974 no-trade
Performance: winrate 27% | expectancy -45.8pt | status avoid

Best tactics:
1. liquidity_sweep_reclaim +14.9pt / 746 trades
2. breakout_retest -26.2pt / 954 trades
3. momentum -49.0pt / 4,336 trades
Weak/Avoid: breakout_retest, fvg_retest, liquidity_sweep_reclaim, momentum
Learning: replay-dominant | real demo trades 0
Active modifiers: breakout_retest -8, fvg_retest -8, momentum -8

Replay only. No MT5 orders, no demo session, live locked.
```

## Notes

- If there is no replay data yet, the heartbeat says so and points to
  `scripts/run_gold_bot_replay.py` — it never fails or invents numbers.
- `--send-discord` without the env webhook fails safely: nothing is sent and a
  clear warning is printed (the preview is still produced).
- **Never store the webhook in a scheduled task.** Sending is an explicit,
  manual, env-gated action.
