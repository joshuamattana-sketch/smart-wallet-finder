# Gold Bot — Local Command Gateway (LM94A)

**MT5 DEMO ONLY. NEVER LIVE. LOCAL ONLY.** The command gateway is the safe
foundation for future one-click website controls. It lets a caller (the CLI today,
a localhost-only API later) trigger a **small, fixed whitelist** of already-existing
Gold Bot scripts — nothing else is runnable. It adds **no** UI, **no** HTTP route,
**no** live trading, and **no** new strategy/trading logic.

- Service: `services/gold_bot_command_gateway.py`
- CLI: `scripts/run_gold_bot_command_gateway.py`
- Tests: `tests/test_gold_bot_command_gateway.py`
- Run logs (gitignored): `data/gold_bot/commands/command_*.json` / `.jsonl` + `command_latest.*`

---

## 1. Whitelisted actions (nothing else exists)

| action | underlying command | notes |
|---|---|---|
| `preflight` | `run_gold_bot_first_run_preflight.py` | read-only GO/NO-GO |
| `daily_cycle_offline` | `run_gold_bot_daily_cycle.py --execute --skip-session` | **no demo trades** |
| `daily_cycle_guarded_demo` | `run_gold_bot_daily_cycle.py --execute --confirm-demo-session --duration-minutes X --max-trades Y --risk-mode Z` | guarded demo, capped |
| `session_review` | `run_gold_bot_session_review.py` | offline digest |
| `discord_preview` | `run_gold_bot_discord_review.py` | no env, no network |
| `discord_send` | `run_gold_bot_discord_review.py --send-discord` | needs allow flag **and** env |

`--use-learning-modifiers` / `--include-real-trades` are appended only when requested.

## 2. Safety model (by construction, not by trust)

- **No free-form shell.** Commands are built from the fixed table above plus
  validated values only (clamped integers, a risk_mode from `{safe, balanced,
  scalp}`). Nothing the caller types is ever interpolated into the argv.
- **No live trading.** There is no `environment` / `--allow-live-trading` knob in
  the request. Guarded demo always routes through the existing
  `daily-cycle → demo session runner → safety supervisor → risk gate → macro
  lockout → kill switch` path. The gateway bypasses none of them.
- **Guarded demo requires explicit confirmation and obeys caps**:
  - `confirm_guarded_demo=True` (else **blocked**)
  - `duration_minutes` ≤ **15** (default 5)
  - `max_trades` ≤ **5** (default 3)
  - `risk_mode` ∈ `{safe, balanced, scalp}` (aggressive/experimental **rejected**)
- **Discord send requires BOTH** `allow_discord_send=True` **and** the env var
  `LUMORA_GOLD_DISCORD_WEBHOOK_URL` being present. The value is **never read** by
  the gateway, **never printed**, **never logged**. Anything webhook-shaped in
  captured subprocess output is redacted before it touches a log.
- **Default is dry-run.** With no `--execute`, the gateway validates and prints the
  planned command and runs **no** subprocess.
- No `MetaTrader5` import, no order placement, no HTTP client in the gateway.

## 3. CLI

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder"

# dry-run (default): validate + show the command, run nothing
python scripts/run_gold_bot_command_gateway.py --action preflight

# preview the guarded demo command (still no execution)
python scripts/run_gold_bot_command_gateway.py --action daily_cycle_guarded_demo --confirm-guarded-demo

# run the safe offline cycle and write a run log
python scripts/run_gold_bot_command_gateway.py --action daily_cycle_offline --execute --include-real-trades --write-log

# run a guarded demo cycle (every order still passes the safety supervisor + risk gate)
python scripts/run_gold_bot_command_gateway.py --action daily_cycle_guarded_demo --execute --confirm-guarded-demo --duration-minutes 5 --max-trades 3 --risk-mode scalp --use-learning-modifiers --include-real-trades --write-log

# send the Discord review INTENTIONALLY (needs the env webhook present)
$env:LUMORA_GOLD_DISCORD_WEBHOOK_URL = "YOUR_WEBHOOK_URL"   # never commit this
python scripts/run_gold_bot_command_gateway.py --action discord_send --execute --allow-discord-send --write-log
Remove-Item Env:LUMORA_GOLD_DISCORD_WEBHOOK_URL
```

Flags: `--action` (required) · `--execute` · `--dry-run` · `--duration-minutes`
· `--max-trades` · `--risk-mode` · `--use-learning-modifiers` ·
`--include-real-trades` · `--confirm-guarded-demo` · `--allow-discord-send` ·
`--timeout-seconds` (default 900, ceiling 3600) · `--requested-by` · `--write-log`
· `--out-dir` · `--json`. `--execute` and `--dry-run` together → exit 2.

Exit codes: planned/success → **0**, failed → **1**, blocked → **2**.

## 4. Run model

`GatewayResult` (written to the run log, JSON + JSONL): `request_id`, `action`,
`accepted`, `status` (`planned|success|failed|blocked`), `reason`, `command`
(readable, redacted), `started_at`, `ended_at`, `exit_code`, `stdout_tail`,
`stderr_tail`, `warnings`, `generated_files`, `redactions_applied`.

- **Dry-run** validates + records the command; writes a plan log only with `--write-log`.
- **Execute** runs `subprocess.run` with `cwd` = repo root, captures + redacts
  output, honours the timeout, and always writes the run log.

## 5. Future local-only web readiness (NOT in this patch)

A future API route may call this service, but **only**:

- bound to **localhost** (never the public internet),
- behind a **CSRF / local token** check,
- restricted to the **action whitelist** above,
- enforcing the same **caps**,
- with **no arbitrary shell** and **no webhook value** ever returned to the client.

The recommended shape is a thin localhost handler that builds a `GatewayRequest`
and returns `GatewayResult.to_dict()` (already secret-free). Default it to dry-run;
require an explicit `execute=true` plus the same `confirm_guarded_demo` /
`allow_discord_send` gates the CLI uses. The next patch (**LM94B**) covers that
web control panel.

## 6. Files / logs created

| Path (all gitignored) | By |
|---|---|
| `data/gold_bot/commands/command_<ts>.json` + `.jsonl` | every executed (or `--write-log`) gateway call |
| `data/gold_bot/commands/command_latest.json` + `.jsonl` | overwritten each call |
| `data/gold_bot/runs/run_latest.json` + `.jsonl` | the underlying daily cycle (offline/guarded) |

## 7. Tests

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder"
python -m pytest tests/test_gold_bot_command_gateway.py -q
python -m compileall services/gold_bot_command_gateway.py scripts/run_gold_bot_command_gateway.py
```

Subprocess and env are mocked; no real commands run, no MT5, no Discord, no
internet. Coverage: unknown action blocked, dry-run runs no subprocess, command
builders, guarded-demo confirm + caps (duration/max_trades/risk_mode), discord
preview needs no env, discord_send blocked without allow flag / without env,
webhook redaction in logs, subprocess success/failure/timeout, no arbitrary
command tokens, no MT5/orders/network/heatmap in source, logs gitignored, safe CLI
defaults.

## 8. Warning

This is a **DEMO-ONLY, LOCAL-ONLY** tool. It never enables live trading, never
sends real orders, never exposes itself to the public internet, never reads or
prints the Discord webhook value, and never bypasses the risk gate, macro lockout,
kill switch, or safety supervisor. The old direct script commands still work
unchanged — the gateway only wraps them with a whitelist, caps, and a dry-run default.
