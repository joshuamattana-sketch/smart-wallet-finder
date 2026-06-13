# Gold Bot — First Market-Open Demo Run

**MT5 DEMO ONLY. NEVER LIVE.** This runbook turns the whole LM86–LM92 loop into one
safe, guided first run. Every order still passes the existing session runner +
safety supervisor + risk gate + macro lockout + kill switch — this procedure adds
**no** new trading logic and the preflight places **no** orders.

The preflight is read-only and prints **GO** or **NO-GO** plus the exact next command.

---

## 1. Weekend / market-closed prep (offline)

When the market is closed you can still validate everything except the live tick:

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder"
python scripts/run_gold_bot_first_run_preflight.py --skip-mt5 --skip-safety
# or the PowerShell wrapper:
.\scripts\start_gold_bot_first_run_preflight.ps1 -SkipMt5 -SkipSafety
```

`--skip-mt5` marks the tick check **SKIP** (not FAIL) so weekend prep can reach GO.
Use this to confirm scripts, the daily-cycle plan, the kill switch and local
artifacts are all healthy before the market opens. You can also dry-run the loop:

```powershell
python scripts/run_gold_bot_daily_cycle.py            # plan only, runs nothing
```

## 2. Market-open preflight

When XAUUSD is trading and MT5 demo is logged in:

```powershell
python scripts/run_gold_bot_first_run_preflight.py
# add --write to save data/gold_bot/preflight/preflight_latest.json
# add --use-learning-modifiers --include-real-trades to shape the GO command
```

Checks: repo root · required scripts · daily-cycle plan · MT5 demo + fresh tick ·
safety probe (no active cooldown) · kill switch off · macro lockout · local
artifacts · Discord (optional). Status levels: **PASS / WARN / FAIL / SKIP**.
`WARN`/`SKIP` never block GO; a `FAIL` on any blocking check → **NO-GO**.

## 3. GO command

If the preflight says **GO**, it prints the exact conservative command, e.g.:

```powershell
.\scripts\start_gold_bot_daily_cycle.ps1 -Execute -ConfirmDemoSession -DurationMinutes 5 -MaxTrades 3 -RiskMode scalp -UseLearningModifiers -IncludeRealTrades
# equivalently:
python scripts/run_gold_bot_daily_cycle.py --execute --confirm-demo-session --duration-minutes 5 --max-trades 3 --risk-mode scalp --use-learning-modifiers --include-real-trades
```

Trading requires **both** `--execute` and `--confirm-demo-session`. Even then the
supervisor blocks on stale tick / spread / open position / loss-streak / drawdown /
kill switch / macro lockout, and the risk gate sizes + vetoes every order.

## 4. NO-GO troubleshooting

If **NO-GO**, the preflight lists the failing reasons and prints safe read-only
commands to investigate:

```powershell
python scripts/run_mt5_demo_connector_probe.py --bars 10 --history-debug   # MT5 / tick / account
python scripts/run_gold_bot_safety_probe.py                                # cooldown / contract
python scripts/run_gold_bot_daily_cycle.py                                 # plan sanity
```

| NO-GO reason | Fix |
|---|---|
| required script missing | re-pull the repo |
| MT5 unavailable / not demo / no candles | start MT5, log into the **demo** account, make XAUUSD visible |
| stale tick / market closed | wait for the session to open (London 07–16 / NY 12–21 UTC) |
| safety cooldown active | wait for the loss-streak cooldown to expire (see safety probe) |
| kill switch active | unset `GOLD_BOT_KILL_SWITCH` (it is a safety brake, not a bug) |
| macro lockout active | wait out the high-impact event window |
| daily cycle plan failed | run the plan command above and read the error |

## 5. Send the Discord review after a run (optional, manual)

Discord is never required and never sent by default. To send after a run:

```powershell
$env:LUMORA_GOLD_DISCORD_WEBHOOK_URL = "YOUR_WEBHOOK_URL"   # never commit this
python scripts/run_gold_bot_session_review.py               # build the digest
python scripts/run_gold_bot_discord_review.py --send-discord
Remove-Item Env:LUMORA_GOLD_DISCORD_WEBHOOK_URL
```

`python scripts/run_gold_bot_discord_review.py` (no flag) previews without sending.
The webhook URL is read only from the env and is never printed (redacted in logs).

## 6. Inspect UI status (read-only)

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder\lumora-web"
npm run dev
# open http://localhost:3000/gold-bot   (read-only status panel; no trading controls)
# raw JSON: http://localhost:3000/api/gold-bot/status
```

## 7. Stop / close manually if needed

- **Stop the worker/session**: press `Ctrl+C` in the terminal running the cycle —
  the session ends cleanly and writes its report.
- **Kill switch** (block all orders immediately): set the env brake before/while running:
  ```powershell
  $env:GOLD_BOT_KILL_SWITCH = "true"
  ```
- **Close an open demo position** (guarded, demo-only — explicit ticket required):
  ```powershell
  python scripts/run_mt5_demo_trade_loop.py --list-positions
  python scripts/run_mt5_demo_trade_loop.py --close-position TICKET --confirm-demo-order
  ```

## 8. Files / logs created

| Path (all gitignored) | By |
|---|---|
| `data/gold_bot/preflight/preflight_latest.json` | preflight `--write` |
| `data/gold_bot/sessions/session_latest.json` + `.jsonl` | demo session |
| `data/gold_bot/trade_outcomes/outcomes_latest.json` | outcome sync |
| `data/gold_bot/learning/active_demo_modifiers.json`, cycles/, real_trade_* | learning cycle |
| `data/gold_bot/reviews/session_review_latest.md` + `.json` | session review |
| `data/gold_bot/safety/safety_state.json` + `safety_events.jsonl` | safety supervisor |
| `data/gold_bot/runs/run_latest.json` + `.jsonl` | daily cycle run log |

## 9. Warning

This is a **DEMO-ONLY** procedure. It never enables live trading, never sends real
orders, and never bypasses the risk gate, macro lockout, kill switch, or safety
supervisor. The aspirational `+10%/day` is a target only; the hard `-7%/day` stop
and every other guard always have final authority.
