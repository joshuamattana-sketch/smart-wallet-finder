# LM74 — Gold Bot Core Engine Blueprint

Status: **blueprint only — no implementation in this patch.**
No MT5 connection, no broker keys, no live trading, no real orders. The Gold Bot
UI (`lumora-web/app/(app)/gold-bot/`) already stages this architecture visually;
this document defines what gets built behind it.

Product: a private Jarvis-like XAUUSD daytrading assistant — paper/demo first,
risk-engine-governed, journal-driven self-learning, funded-account-aware later.

---

## 0. Module layout (proposed)

All engine code lives in pure-Python `services/goldbot/`, mirroring the existing
repo style (pure engines in `services/`, transports in `services/connectors/`,
deterministic tests in `tests/`, no network in tests):

```
services/goldbot/
  sources/            # Source Intelligence Layer (adapters)
  memory/             # Historical Memory Layer (backfill + snapshots)
  replay/             # Replay Learning Engine
  strategies/         # Strategy Engine (one module per family)
  risk/               # Risk Engine (final authority)
  manager/            # Trade Manager + Exit Engine
  execution/          # Execution adapters (paper engine, MT5 demo)
  journal/            # Journal + Learning Layer
  review/             # Discord Review Layer
  config.py           # Safety flags, risk modes, profiles
```

Data contracts are frozen dataclasses passed down a single pipeline:

```
MarketContext → StrategySignal → RiskDecision → TradeIdea → OrderResult
             → PositionUpdate* → ExitRecord → JournalEntry → ReviewReport
```

Nothing executes unless a `RiskDecision.approved == True` object exists for it.

---

## 1. Source Intelligence Layer (`sources/`)

One adapter interface, many planned implementations. Every adapter returns
normalized dataclasses with UTC timestamps and a `source` tag; every adapter
must work in `offline` mode (fixtures) for tests.

| Adapter                  | Provides                                  | First implementation |
|--------------------------|-------------------------------------------|----------------------|
| `xauusd_candles`         | M1/M5/H1 candles + ticks                  | MT5 demo terminal data (later); CSV/fixture backfill first |
| `dxy`                    | DXY index candles                         | fixture/CSV; provider TBD |
| `us_yields`              | 2y/10y yields                             | fixture/CSV; provider TBD |
| `economic_calendar`      | scheduled events, impact rating, actual/forecast/previous | static JSON calendar first |
| `news_high_impact`       | CPI/NFP/FOMC/Fed speech flags + windows   | derived from calendar |
| `news_geopolitical`      | unscheduled risk flags                    | manual/owner-entered first |
| `mt5_account`            | account info, positions, order history    | MT5 demo only (section 7) |
| `journal_reader`         | the bot's own past decisions              | JSONL journal (section 8) |

`MarketContext` is the merged snapshot the rest of the engine consumes:
session (Asia/London/NY), price state, zone inventory, news window state,
macro lean (DXY/yields direction), spread/volatility readings.

## 2. Historical Memory Layer (`memory/`)

The bot must not start from zero. Backfill jobs build a local store
(JSONL/Parquet under `data/goldbot/`, same local-first pattern as the whale
journal) containing:

- **Candle history** — multi-year XAUUSD M5/H1/D1 backfill (CSV import first,
  MT5 history pull once the demo adapter exists).
- **Event history** — CPI / NFP / FOMC / Fed speeches with timestamps,
  surprise direction, impact rating.
- **Reaction snapshots** — for each event: XAUUSD/DXY/yields path ±N minutes
  around release (pre-range, spike, retrace, close).
- **Setup outcomes** — every historical setup the detectors find when run over
  the candle history: setup type, context, would-be entry/SL/TP, outcome in R.
- **Market day snapshots** — one compact record per trading day: sessions,
  ranges, sweeps, news, regime label.

Memory is append-only and versioned (`schema_version` field per record) so
re-backfills never corrupt learned statistics.

## 3. Replay Learning Engine (`replay/`)

Replays any stored market day bar-by-bar with **no lookahead**: at each step
the engine sees only data up to that bar.

Replay run output per day:
1. what the bot would have *seen* (context timeline),
2. which setups detectors would have flagged (with timestamps),
3. trade or skip — through the same Strategy + Risk pipeline as live,
4. simulated outcome (entry/SL/TP walked forward against real candles),
5. a stored `ReplayLesson`: setup type, decision, outcome R, mistake class,
   score, and the rule/threshold that drove the decision.

Replay results feed the same journal/analytics as paper trading — one learning
loop, two data sources (replayed past + live paper). Determinism rule: same
day + same config ⇒ identical replay output (seeded, no wall-clock reads).

## 4. Strategy Engine (`strategies/`)

First strategy families (one module each, registered in a strategy registry):

1. `sweep_reclaim` — liquidity sweep + reclaim (the flagship setup)
2. `fvg_retest` — fair value gap retest after displacement
3. `session_sweep` — session high/low sweep (Asia range, London open traps)
4. `breakout_retest` — level break + successful retest
5. `trend_continuation` — pullback continuation with session bias
6. `stop_hunt_reversal` — reversal after stop hunt into HTF level
7. `news_no_trade` — explicit no-trade strategy that asserts flat during news
   windows (a strategy, so the journal records *why* flat was chosen)

Every strategy consumes `MarketContext` and emits a `StrategySignal`:

```python
@dataclass(frozen=True)
class StrategySignal:
    strategy: str                  # registry id
    direction: Literal["long", "short", "no_trade"]
    confidence: float              # 0–100
    entry_idea: float | None       # price or zone midpoint
    invalidation: float            # thesis-dead level
    stop_loss_idea: float | None
    take_profit_idea: float | None
    reason: str                    # one sentence, journal-ready
    confirmations_required: list[str]   # e.g. ["fvg_touch", "m1_reclaim"]
    confirmations_met: list[str]
```

Signals are ideas, never orders. Multiple signals may coexist; the Risk Engine
arbitrates.

## 5. Risk Engine (`risk/`) — final authority

Single entry point: `evaluate(signal, context, account_state) -> RiskDecision`.
**Nothing reaches execution without an approved RiskDecision. No module may
bypass it. No risk mode may bypass hard rules.**

Hard rules (non-negotiable, identical in every mode):
- **-7% max daily loss = hard stop.** Reached ⇒ flat, trading disabled until
  next session day.
- **+10% daily target is aspirational only** — a benchmark for review, never a
  reason to take an extra trade. No overtrading to chase it.
- Max trades per day (default 3).
- Cooldown after a loss (default 45 min).
- No martingale (size never increases after a loss).
- No revenge trading (same-direction re-entry within cooldown after stop-out is rejected).
- Spread/volatility filter (reject when spread > threshold or vol regime is disorderly).
- News lockout (no entries inside high-impact windows; default ±30 min).
- **Kill switch** — one flag flattens everything and halts the engine.

Risk modes (`Safe | Balanced | Aggressive`) only tune *soft* parameters:
minimum confidence to act, allowed setup classes, risk-per-trade within the
cap, partial-take behavior. Aggressive may allow riskier demo ideas — it can
never raise the -7% stop, the trade cap, or pierce news lockout.

Funded-account guardrails (section 10) load as an *additional* rule layer on
top — profiles can only tighten, never loosen.

## 6. Trade Manager + Exit Engine (`manager/`)

Owns the full life of an approved idea:

- **Open**: place buy/sell via the active execution adapter with SL/TP
  attached at open (never naked).
- **Monitor**: track position state on a fixed cadence; every transition
  journaled as a `PositionUpdate`.
- **Break-even**: move SL to BE when the configured R-multiple is reached and
  the rule allows.
- **Partial close**: planned (config-gated, off by default).
- **Close on invalidation**: thesis level broken ⇒ close, regardless of PnL.
- **Close before news**: rule-required flattening N minutes before high-impact
  events.
- **Session-end close**: optional flat-at-session-close config.
- **Emergency close**: risk breach or kill switch ⇒ immediate flatten via a
  path that does not depend on the strategy layer.

Every exit writes an `ExitRecord` (reason enum: tp / sl / invalidation / news /
session_end / emergency / manual).

## 7. MT5 Demo Execution Layer (`execution/mt5_demo.py`) — first real execution path

Planned integration via the official `MetaTrader5` Python package, demo only:

1. **Account type check first.** On connect, read account info; anything that
   is not a demo account ⇒ refuse to initialize.
2. **Symbol discovery** — resolve the broker's XAUUSD symbol name
   (XAUUSD / GOLD / XAUUSD.x variants), verify trade permissions and contract specs.
3. **`order_check` before `order_send`** — every order is pre-validated; a
   failed check is journaled and dropped.
4. **`order_send` only with an approved `RiskDecision`** attached to the request.
5. **Position monitoring** — poll positions/orders, emit `PositionUpdate`s.
6. **History import** — pull demo trade history into the journal (also serves
   the memory layer).
7. **Reject/error handling** — every retcode mapped; transient errors retried
   bounded; persistent errors flip the engine to watch-only and journal a RISK event.

Safety flags (config defaults, all checked at adapter init *and* per order):

```
MT5_DEMO_ONLY=true
LIVE_TRADING_ENABLED=false
ALLOW_REAL_ORDERS=false
KILL_SWITCH=true
```

Live accounts are blocked by default; enabling live trading would require
deliberate, multi-flag changes plus the account-type check — out of scope and
not planned in this series. Until MT5 lands, `execution/paper.py` (Lumora
Paper Engine: simulated fills against the candle feed) is the only adapter.

## 8. Journal + Learning Layer (`journal/`)

Append-only JSONL journal (same pattern as the whale event journal). Every
pipeline stage writes — decisions are journaled even when nothing is traded.

Stored per entry (superset; stages fill their slice):
market context · event context · strategy signal · risk decision · trade idea ·
order result · position updates · exit reason · PnL (R and %) · mistake class ·
lesson · score (0–10) · suggested strategy change.

**Self-learning contract:** learning = journal + analytics + scoring +
**owner-approved suggestions**. Analytics may *propose* threshold/rule changes
(as `suggested_change` records with evidence); the bot **never silently
rewrites its own rules** — every change requires explicit owner approval and
is itself journaled.

## 9. Discord Review Layer (`review/`)

Daily report built from the journal, formatted by a pure formatter (reuse the
`discord_webhook_sender.py` transport pattern when wired — not wired yet):

session summary · paper PnL · trades taken · trades skipped (with reasons) ·
why taken/skipped · best setup · worst setup · mistakes detected · lessons
learned · tomorrow's watchlist · **risk warning when behavior was poor**
(e.g. cooldown violations attempted, near-miss on daily stop).

The review never flatters the engine — skipped valid setups and rule frictions
are reported as prominently as wins.

## 10. Future Funded Account Mode (`config.py` profiles)

Funded profiles are declarative rule packs layered onto the Risk Engine.
Planned profiles: **FTMO · The5ers · Alpha Capital · Custom**.

Each profile defines: daily drawdown limit · max total drawdown · consistency
rules (max share of profit from one day) · news restrictions (some firms ban
news trading outright) · max open risk · max lot/risk per trade · no
martingale · no revenge trading (both already hard rules — profiles restate
them as firm requirements).

Profile rules can only **tighten** the base Risk Engine, never loosen it. No
prop-firm logic is implemented in this series — profiles exist as schema +
staged copy until paper results justify them.

---

## Implementation sequence (recommended)

1. **LM74B** — contracts + config: dataclasses (`MarketContext`,
   `StrategySignal`, `RiskDecision`, `TradeIdea`, `ExitRecord`,
   `JournalEntry`), safety flags, risk-mode config, deterministic tests.
2. **LM74C** — Risk Engine v1 (hard rules + modes) with full test matrix.
3. **LM74D** — `sweep_reclaim` + `news_no_trade` strategies over fixture candles.
4. **LM74E** — Paper engine + Trade Manager v1 (simulated fills, BE rule, invalidation exit).
5. **LM74F** — Journal layer + first analytics (setup win-rate by session).
6. **LM74G** — Historical backfill (CSV candles + static event calendar) + memory store.
7. **LM74H** — Replay engine v1 over backfilled days.
8. **LM74I** — Gold Bot UI wiring (page reads journal/paper state instead of staged data).
9. **LM75x** — MT5 demo adapter (account check, symbol discovery, order_check/send), Discord review sender, funded profiles.

## Current truth (unchanged by this patch)

- No live trading. No MT5 connection. No broker keys. No real orders.
- Gold Bot page is staged data only; paper engine not yet implemented.
- This document is the contract future patches implement against.
