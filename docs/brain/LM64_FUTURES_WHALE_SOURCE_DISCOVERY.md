# LM64 — Futures / Leverage Context for Whale Events (Discovery)

Research-only doc. No code changes. Defines how Lumora should add futures and
leverage context to existing whale events without making claims it cannot
actually verify from public exchange data.

---

## 1. Current limitation

Lumora's whale pipeline (LM63B–LM63J) streams **Binance Spot `@aggTrade`** and
emits whale events with these fields (`services/whale_alert_engine.py`,
`detect_whale_events`):

```
source_type, symbol, exchange, chain, side, amount, price,
notional_usd, wallet, tx_hash, severity, confidence, reason, metadata
```

Two structural truths the spot feed forces on us:

1. **Leverage is invisible.** Binance Spot aggTrade carries:
   - `a` agg trade id
   - `p` price, `q` quantity
   - `T` trade time, `m` buyer-is-maker flag

   The only side information is "taker hit bid" vs "taker lifted ask"
   (`m == true` / `false`). There is **no leverage field**, no account
   identifier, no position info. The current
   `normalize_agg_trade_to_whale_input` fills `leverage = None` and
   `wallet = "agg:{aggId}"` — both are honest placeholders.

2. **Per-symbol notional thresholds (LM63D)** treat every fill as a spot
   notional. A $250k BTC fill is "notable"; we have no way to tell whether
   that came from a desk hedging cash flow or a 10x-leveraged momentum
   chase. The `whale_alert_engine.MarketContext` dataclass already has
   `funding_rate`, `oi_change_pct`, `near_breakout`, `liquidity_score`
   slots — but nothing in the spot path populates them.

The cost of staying spot-only is that Lumora can describe **flow** (size,
side, severity) but not **conviction** (is this leveraged? is the book
crowded? is a squeeze brewing?). Futures data is where that conviction
signal lives.

---

## 2. Candidate Binance futures data sources

USD-M perpetuals on `fstream.binance.com`. All are public and require **no
API key**. Same WebSocket transport pattern as LM63B
(`scripts/run_binance_ws_heatmap_live.py`'s lazy `websocket-client` +
reconnect backoff already applies).

### 2.1 Futures `@aggTrade` stream

- WS: `wss://fstream.binance.com/ws/{symbol}@aggTrade`
- Combined: `wss://fstream.binance.com/stream?streams=btcusdt@aggTrade/ethusdt@aggTrade`
- Payload mirrors spot exactly (same `a/s/p/q/T/m` fields) plus `X` (event type) and `o` not present.
- Side mapping identical: `m == true` → SELL aggressor, `m == false` → BUY aggressor.
- **What we learn:** real-time **taker imbalance** on the perpetual itself —
  the side most leveraged actors are paying up to enter/exit.
- **Reuse:** the existing `parse_agg_trade_message` and
  `normalize_agg_trade_to_whale_input` would only need a venue tag
  (`exchange = "binance_futures"`) and a new `source_type =
  "futures_trade"`. No new parsing logic.

### 2.2 Open Interest (REST + history)

- Latest: `GET https://fapi.binance.com/fapi/v1/openInterest?symbol=BTCUSDT`
- Historical (preferred): `GET https://fapi.binance.com/futures/data/openInterestHist?symbol=BTCUSDT&period=5m&limit=30`
  - Returns 30 datapoints of `sumOpenInterest` (base) and `sumOpenInterestValue` (USD-ish).
- **Cadence to poll:** 1 minute is comfortably under Binance public-endpoint rate limits.
- **What we learn:**
  - **Δ OI over 5m / 15m / 1h** → expansion vs contraction.
  - Rising OI + rising price → fresh longs.
  - Rising OI + falling price → fresh shorts.
  - Falling OI + falling price → longs unwinding.
  - Falling OI + rising price → shorts covering.

### 2.3 Funding rate (REST + WS premium index)

- REST: `GET https://fapi.binance.com/fapi/v1/premiumIndex?symbol=BTCUSDT`
  returns `lastFundingRate`, `nextFundingTime`, `markPrice`,
  `indexPrice`, `estimatedSettlePrice`.
- WS stream: `{symbol}@markPrice@1s` or `!markPrice@arr@1s` — pushes
  mark/index/funding once per second (a cheap, sub-millisecond signal).
- **What we learn:**
  - Persistently positive funding → longs paying shorts → crowded longs →
    asymmetric squeeze risk.
  - Funding rate magnitude is more useful than absolute sign once you
    track it over time (Lumora can compute a rolling z-score or simple
    sigma threshold).
  - Premium index = (markPrice − indexPrice) / indexPrice. Large positive
    premium often precedes a funding spike.

### 2.4 Liquidation stream (`@forceOrder`)

- Per-symbol WS: `wss://fstream.binance.com/ws/{symbol}@forceOrder`
- All-symbol firehose: `wss://fstream.binance.com/ws/!forceOrder@arr`
- Payload (per liquidation):
  ```json
  {"e":"forceOrder","E":1685000000000,
   "o":{"s":"BTCUSDT","S":"SELL","o":"LIMIT","f":"IOC",
        "q":"0.014","p":"30000","ap":"30000","X":"FILLED",
        "l":"0.014","z":"0.014","T":1685000000000}}
  ```
- Side `S` = the side **being liquidated**:
  - `SELL` → a long got force-closed (long liquidation).
  - `BUY`  → a short got force-closed (short liquidation).
- **What we learn:**
  - Real-time liquidation **notional** (`ap * z`) per symbol.
  - Direction of pain (long vs short cascades).
  - Note: Binance throttles `@forceOrder` to ~1 update per second per
    symbol; the displayed flow is a sample, not the full book.

### 2.5 Mark price / premium index (WS)

Same stream as funding (`@markPrice@1s`). One subscription gives us mark
price + funding + estimated settle, which we'd otherwise have to fetch via
two REST calls per minute. Worth using as the primary stream for both
"futures heat" and "spot vs futures bias".

---

## 3. Derived signals Lumora can compute safely

Each signal is a *score* in `[0, 1]` (or a small enum) built from public
streams. None of them require knowing any individual account's leverage.

### 3.1 `futures_flow_pressure` (per symbol, rolling window)

- Inputs: futures `@aggTrade` taker-buy vs taker-sell volume over the last
  N seconds (suggested 30s / 5m / 15m windows).
- Definition: `bid_volume_usd / (bid_volume_usd + ask_volume_usd)` clamped
  to `[0, 1]`.
- Reading: > 0.6 = buyer-led; < 0.4 = seller-led; near 0.5 = balanced.

### 3.2 `oi_expansion` (per symbol, rolling)

- Inputs: open interest history, 5m or 15m bars.
- Definition: percent change in `sumOpenInterestValue` over the last
  window, normalised to a rolling sigma (e.g. last 24h).
- Reading: > +2σ in 5m = aggressive position build (fresh leverage
  entering); < −2σ = de-risking / unwind.

### 3.3 `liquidation_risk` (per symbol, rolling)

- Inputs: `@forceOrder` notional aggregated over 1m / 5m / 15m windows,
  split by side liquidated.
- Definition: total liquidation USD in the window, normalised against a
  rolling baseline. Plus a directional component (long_liq − short_liq).
- Reading:
  - Spike with `long_liq >> short_liq` → ongoing long-squeeze (downside).
  - Spike with `short_liq >> long_liq` → ongoing short-squeeze (upside).

### 3.4 `leverage_heat` (per symbol, composite)

- A single `[0, 1]` score that combines:
  - `oi_expansion` magnitude
  - `|funding_rate|` z-score (crowded = hot)
  - 5m liquidation flow size (cascades = hot)
- Use a weighted sum with conservative weights so any one input can't
  dominate (e.g. 0.4 · OI + 0.4 · funding + 0.2 · liq).
- Reading: > 0.7 = leverage tension high; < 0.3 = calm.

### 3.5 `spot_vs_futures_bias`

- Inputs: matching spot price (already collected) + futures `markPrice` /
  `indexPrice`.
- Definition: `(markPrice − spotPrice) / spotPrice`.
- Plus: 5m taker-buy ratio on **spot** minus the same ratio on **futures**.
- Reading: Positive premium + futures-led buying = derivatives
  front-running spot. Negative premium + spot-led buying = real-money
  accumulation.

---

## 4. What Lumora may say safely

The whole point of these derived signals is to enrich whale-event
narratives **without falsifying claims about individual accounts**.

### Safe phrasings

- "Leverage pressure rising" / "leverage tension elevated" — backed by
  `leverage_heat`.
- "Fresh longs entering" — backed by rising OI + rising price + futures-led
  bid taker-buys.
- "Possible long squeeze setup" — backed by high OI + positive funding +
  recent long liquidations.
- "Spot-led move" / "derivatives-led move" — backed by
  `spot_vs_futures_bias`.
- "Funding crowded long" / "crowded short" — backed by absolute funding
  rate magnitude.

### Phrasings to avoid

- "This wallet used 20x leverage." — **Not knowable.** Spot aggTrade has
  no account, no leverage. Futures aggTrade has no account. Force-order
  events do not carry account ids either.
- "Trader X opened a $5M long at 10x." — **Not knowable.** Aggregate flow
  cannot be attributed to one trader from public WS.
- "Liquidation imminent at $66,300." — **Not knowable** without per-account
  margin data. Lumora can only describe **aggregate** liquidation flow
  that has already happened, plus directional pressure, never a forecast
  about a named trader.
- "Whale is short with X% margin used." — **Not knowable.**

The line is consistent: Lumora can describe the **state of the market**
(crowdedness, taker imbalance, funding stress, liquidation flow), but
never the **state of an individual account**. The same wallet/tx
constraint already in the spot path applies here.

---

## 5. Existing pieces Lumora already has that map cleanly to futures

- `services/whale_alert_engine.MarketContext` already accepts
  `imbalance`, `liquidity_score`, `funding_rate`, `oi_change_pct`,
  `near_breakout`, `near_support`, `near_resistance` and uses them in
  risk and importance scoring. **Populating these from futures data is
  the win** — the engine has been written for it from day one but the
  spot pipeline never had data to fill them.
- `services/whale_symbol_thresholds.py` already separates `notable /
  high / extreme` notionals per symbol. The same shape can be reused for
  futures-specific thresholds (futures BTC whales differ from spot BTC
  whales).
- `scripts/run_binance_ws_heatmap_live.py` and
  `scripts/run_binance_trade_stream_smoke.py` already use the same
  `websocket-client` lazy import + reconnect backoff pattern — the
  futures WS collectors can reuse the helper unchanged.
- `services/whale_event_journal.py` and
  `services/whale_event_supabase_writer.py` already accept arbitrary
  `event` dicts. A `source_type = "futures_trade"` event lands in the
  same journal / table with no schema change. The LM63G Supabase schema
  has `payload jsonb` precisely for forward-compatible columns like
  `funding_rate`, `oi_change_pct`, `leverage_heat`.

---

## 6. Recommended patch sequence

Three small, independent patches that each ship a usable signal. Each
mirrors the LM63B/C/D/E structure so the work plan is already proven.

### LM64B — Binance Futures aggTrade collector

New module: `services/connectors/binance_futures_trade_stream.py` (or
extend `binance_trade_stream.py` with a `venue` parameter — to be decided
in the patch).

- WS URL builder for `wss://fstream.binance.com/ws/{symbol}@aggTrade` (and
  combined stream).
- Parse / normalize → whale-engine v2 input dicts with
  `source_type = "futures_trade"` and `exchange = "binance_futures"`.
- Reuses `parse_agg_trade_message` byte-for-byte (same payload shape).
- New `iter_binance_futures_aggtrades(symbols, message_iter=None)`.
- Smoke runner CLI: extend
  `scripts/run_binance_trade_stream_smoke.py` with a `--venue` flag
  (`spot` default, `futures`, or `both`) so existing spot behavior stays
  intact.
- Tests mirror LM63B: URL builder, parser, normalization, iterator,
  symbol filter, round-trip into `detect_whale_events`.
- No Supabase schema change.

Scope guard: this is the *plumbing* patch only — we get futures trades
in, but no funding / OI / liquidation context yet.

### LM64C — Funding rate + Open Interest poller

New module: `services/connectors/binance_futures_context.py`.

- REST poller (1 min cadence) for:
  - `/fapi/v1/premiumIndex` → `funding_rate`, `mark_price`, `index_price`
  - `/futures/data/openInterestHist?period=5m` → derive `oi_expansion`
- Plus optional WS `@markPrice@1s` stream subscription for sub-second
  funding/mark price.
- Exposes `get_futures_context_for_symbol(sym)` returning a dict shaped
  for `MarketContext` (i.e. `funding_rate`, `oi_change_pct`, derived
  signal scores).
- New service `services/whale_futures_context_cache.py` keeps a small
  in-memory rolling buffer per symbol (no Supabase yet).
- Smoke runner picks up `MarketContext` per event so `detect_smart_whale_event`
  (the richer path) starts producing real reasons/warnings instead of
  empty context.
- Tests: REST mocked via injected `requester`, sigma/normalisation math
  verified deterministically.
- No Supabase schema change.

Scope guard: read-only, in-memory. Persistence (Supabase
`futures_context` table) is a later concern.

### LM64D — Liquidation stream + leverage heat composite

New module: `services/connectors/binance_force_order_stream.py`.

- WS subscriber for `wss://fstream.binance.com/ws/!forceOrder@arr`
  (single all-symbol firehose).
- Normalize liquidation events: `{symbol, side_liquidated, notional_usd,
  event_ts}`.
- New `services/whale_leverage_heat.py`:
  - Maintains rolling liquidation windows.
  - Combines `oi_expansion` (from LM64C), `|funding_rate|` z-score, and
    liquidation flow into a `leverage_heat ∈ [0, 1]` score per symbol.
- Whale event enrichment:
  - When a spot or futures whale event fires, attach `metadata.futures =
    {funding_rate, oi_change_pct, leverage_heat, liquidation_risk}`.
  - The whale event's `reason` / `action` (already produced by
    `_derive_action` in `whale_alert_engine.py`) gain real
    `MarketContext` signals to work with.
- Tests: deterministic windows, weight sanity, no-throw on partial data.
- Optional follow-up: extend `supabase/whale_events.sql` (LM64E) with a
  jsonb column for futures context — but only after LM64D proves the
  shape on the journal side first.

### Out of scope (for LM64 series)

- Per-account leverage attribution — not knowable from public WS, full stop.
- A Lumora-side "open interest by venue" cross-exchange aggregator —
  belongs to a later LM65 series once Bybit/OKX collectors exist.
- Liquidation forecasting via leverage tier maps — Binance does publish
  liquidation price tiers for some products, but treating them as
  predictive crosses into "we said the wallet was 20x" territory we are
  explicitly avoiding.

---

## 7. Decision summary

| Question | Answer |
|---|---|
| Can Lumora know any individual trader's leverage from public data? | **No.** |
| Can Lumora know aggregate leverage pressure on a symbol? | **Yes** — via funding, OI change, and liquidation flow. |
| Do we need new Supabase tables for LM64? | **No** for B/C/D. Maybe later (LM64E or LM65) if we promote `metadata.futures` into first-class columns. |
| Do we need new env vars? | **No** — futures REST + WS are public, same endpoints just on `fstream.binance.com` / `fapi.binance.com`. |
| Do we need new frontend work? | **No** in this series. The whale-alerts page already reads enriched event payloads; new keys land in `metadata` and surface in the existing card UI without page edits. |
| Risk of misleading users? | Only if we forget the rules in §4. The patches must keep the wording strictly aggregate. |

---

## 8. Recommended next patch

**`LM64B_BINANCE_FUTURES_AGGTRADE_COLLECTOR`**

The smallest standalone step that:
- proves the futures WS endpoint works inside the existing collector pattern,
- gives us a `source_type = "futures_trade"` lane in the journal,
- unblocks LM64C/D without touching any of them yet,
- requires no Supabase changes, no env-var changes, no frontend changes.

Once LM64B is green, LM64C (funding/OI poller) adds *context* and LM64D
(force-order stream + composite) closes the loop with `leverage_heat`.
