# Gold Bot — Execution Environments

LM93A gives the (currently demo-only) execution stack a clear vocabulary instead of
"demo" scattered everywhere — **without enabling anything unsafe.** Two orthogonal
axes describe every run:

| Axis | Values | Meaning |
|---|---|---|
| **environment** | `paper` · `demo` · `live` | where an order would land |
| **mode** | `observe` · `execute` | whether an order may be *attempted* |

Model: `services/gold_bot_execution_environment.py` (`ExecutionContext`,
`assert_execution_allowed`, `describe_execution_context`, `is_demo_execution`,
`is_live_blocked`).

## Environments

- **paper** — simulated. Never sends broker orders. (`PAPER_NO_BROKER`)
- **demo** — a real MT5 **demo** broker account (e.g. MetaQuotes-Demo). Demo broker
  orders are permitted **by environment policy** only on a verified demo account,
  and only through the existing guarded execution path. (`DEMO_ALLOWED`)
- **live** — **not implemented, hard-locked.** Even with both the env token
  `LUMORA_GOLD_ALLOW_LIVE_TRADING=I_UNDERSTAND_LIVE_RISK` **and** `--allow-live-trading`,
  the gate returns `LIVE_NOT_IMPLEMENTED` and refuses. `--environment live` makes
  every CLI exit with a clear error.

## Modes

- **observe** — reads / analyses only, never sends orders. (`OBSERVE_ONLY`)
- **execute** — may *attempt* a broker order, but **only** if `environment == demo`,
  the account is a verified demo, and **all** existing guards pass.

## The gate is additional, never a replacement

`assert_execution_allowed(context)` is a *second* gate. `DEMO_ALLOWED` does **not**
send anything — a demo order still requires, exactly as before:

1. `--mode demo` + `--auto-execute-demo` + `--confirm-demo-order` (worker), or
   `--confirm-demo-session` (session runner);
2. a connector-verified demo account (`demo_verified`);
3. the **safety supervisor** green (tick fresh, spread ok, no cooldown / drawdown /
   kill switch / macro lockout, no open position);
4. the **risk gate** sizing + approving the order.

Unknown account type → blocked (`UNKNOWN_ACCOUNT`). Live/real account → blocked.

## Context matrix

```
demo   observe  -> OBSERVE_ONLY        allowed=False   (reads only)
demo   execute  -> DEMO_ALLOWED        allowed=True    (guarded broker demo)
paper  execute  -> PAPER_NO_BROKER     allowed=False   (simulated)
live   execute  -> LIVE_NOT_IMPLEMENTED allowed=False  (hard-locked)
```

## Commands to use now

Legacy flags still work and map onto the model:

| Old | Maps to |
|---|---|
| `--mode observe` | environment `demo`, mode `observe` |
| `--mode demo` | environment `demo`, mode `execute` (still needs the confirm flags) |

```powershell
# observe (no orders), default demo environment:
python scripts/run_gold_bot_worker.py --mode observe --risk-mode scalp --use-learning-modifiers --max-iterations 1
# bounded demo session (observe unless --confirm-demo-session):
python scripts/run_gold_bot_demo_session.py --duration-minutes 1 --max-iterations 1
# plan the daily cycle (prints "environ. : demo | execution: plan | live: locked"):
python scripts/run_gold_bot_daily_cycle.py
# guarded demo run (unchanged):
python scripts/run_gold_bot_daily_cycle.py --execute --confirm-demo-session --duration-minutes 5 --max-trades 3 --risk-mode scalp --use-learning-modifiers --include-real-trades
```

New optional flags (display + live refusal): `--environment paper|demo|live`,
`--allow-live-trading` (no-op; live stays locked). `--environment live` is refused
everywhere.

## What would be needed before live could ever be considered

Live is intentionally out of reach. Reaching it would be a separate, deliberate,
heavily-reviewed program — at minimum: a live-capable connector with its own
order path, a hard-money risk engine review, broker/account compliance, an audited
kill-switch + circuit breakers, real-money position limits, and an explicit owner
sign-off flow. None of that exists here. **This build is demo-only; live trading is
never enabled.**
