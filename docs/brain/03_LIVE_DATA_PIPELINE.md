# Live Data Pipeline

## Local Live
Binance Spot REST depth snapshots
→ `services/connectors/binance_depth_collector.py`
→ `services/orderbook_depth_bucketer.py`
→ `services/heatmap_matrix_builder.py`
→ `services/heatmap_api_payload.py`
→ `scripts/run_local_heatmap_live.py`
→ `lumora-web/fixtures/live/*.json`

## API
GET `/api/heatmap`

Sources:
- `mock`
- `fixture`
- `live`

Expected fallback chain:
Supabase live
→ local live file
→ fixture
→ mock

## Important Payload Fields
- `symbol`
- `exchange`
- `timeframe`
- `cells`
- `walls`
- `pricePath`
- `meta.requestedSource`
- `meta.resolvedSource`
- `meta.dataSource`
- `meta.isFallback`
- `meta.stale`
- `meta.liveUpdatedAt`

## Production Live Goal
Hosted worker or local writer with Supabase target
→ `heatmap_latest_payloads` table
→ Vercel API `source=live` reads Supabase
→ Website online live.

## WebSocket Collector MVP (LM42A)
Additive — does NOT replace the REST writer.
- Script: `scripts/run_binance_ws_heatmap_live.py`
- Stream: `wss://stream.binance.com:9443/ws/{symbol}@bookTicker`
- Bootstraps cells from one REST depth snapshot; refreshes every
  `--depth-refresh` seconds (default 30s).
- bookTicker drives sub-second best bid/ask + mid → `pricePath`.
- Writes a HeatmapApiPayload to the same table every `--write-interval`
  seconds (default 1s). One row per (symbol, exchange, timeframe).
- Meta tags: `source=dataSource=binance_ws_live_writer`,
  `collector=binance_websocket`, `resolvedSource=live`,
  `writeIntervalSeconds=<configured>`.
- Optional dep: `websocket-client` (lazy-imported; install only when
  running the script — not required for tests / `--help`).
- Recommended hosted command:
  `python scripts/run_binance_ws_heatmap_live.py --symbol BTCUSDT \
      --timeframes 5m,15m,1h --write-interval 1 --max-frames 1200 \
      --target supabase --forever`

## Price Range Presets (LM43)
Analysis-grade y-axis context for the heatmap. Both writers expose:
`--range-mode tight|standard|wide|macro` (default: standard),
`--price-range-abs <usd>` (override, ±USD half-range),
`--price-range-percent <fraction>` (override, ±fraction of mid).

Per-symbol USD half-range presets (around current mid):

| Symbol  | tight | standard | wide  | macro  |
|---------|-------|----------|-------|--------|
| BTCUSDT | ±1000 | ±3000    | ±7500 | ±15000 |
| ETHUSDT | ±100  | ±300     | ±750  | ±1500  |
| SOLUSDT | ±10   | ±30      | ±75   | ±150   |

Unknown symbols fall back to ±%: tight 1%, standard 3%, wide 7%, macro 15%.

Implementation notes:
- Bucketer filters bid/ask levels to the requested range before bucketing,
  and reports raw snapshot extremes via `meta.availableDepthMin/Max`.
- Auto-scales `price_step` only for `wide`/`macro` modes (target 600
  buckets/row, snapped to 1/2/5 × 10^n). `tight`/`standard` keep the
  user's explicit `--price-step` exactly — fully backward compatible.
- HeatmapCanvas reads `meta.priceRangeMin/Max` and uses them as the
  rendered y-axis bounds so the user sees the full requested context,
  even where Binance depth doesn't reach.
- New meta fields: `priceRangeMode`, `priceRangeMin`, `priceRangeMax`,
  `priceRangeAbs`, `priceRangePercent`, `priceRangeRequestedMin/Max`,
  `availableDepthMin/Max`.

## LM50 — Signal Journal Foundation
Pure-Python, dependency-light layer that turns LM49 standardized signal
dicts into "journal entry" dicts. No I/O, no Supabase, no file writes —
this is the in-memory contract that future persistence layers will read.

**Module**: `services/signal_journal.py`

**Public entry points**:
- `create_signal_journal_entry(signal, *, created_at=None) → dict | None`
- `create_signal_journal_entries(signals, *, created_at=None) → list[dict]`
- `update_signal_outcome(entry, outcome) → dict` (returns a NEW entry; input never mutated)
- `summarize_signal_journal(entries) → dict`

**Outcome statuses**:
| Status         | Meaning |
|----------------|---------|
| `pending`      | actionable signal awaiting price action |
| `target_hit`   | at least one target reached |
| `invalidated`  | invalidation price hit before any target |
| `expired`      | neither hit nor invalidated within the watch window |
| `no_trade`     | informational entry (LM49 no_trade or neutral direction) |
| `unknown`      | explicit "we can't tell" (e.g. data gap) |

**Initial outcome_status**: `no_trade` for `signal_level=="no_trade"` or
`direction=="neutral"`; otherwise `pending`.

**`update_signal_outcome` rules**:
- Returns a fresh dict (immutable-style merge); never mutates the input.
- Unknown keys are silently ignored — safe forward-compatibility.
- Invalid `outcome_status` values are rejected (status untouched).
- `no_trade` entries cannot be promoted to `target_hit`/`invalidated`,
  but excursion fields and `notes` are still mergeable.

**Summary returns** (zero-filled for known keys so callers never KeyError):
`total_entries`, `by_direction`, `by_signal_level`, `by_outcome_status`,
`by_setup_type`, `by_symbol`, `actionable_count`, `resolution_rate`.
`actionable_count` = entries with level `setup`/`strong_setup` AND
outcome not `no_trade`. `resolution_rate` = (resolved /
pending+resolved), where resolved means `target_hit`, `invalidated`,
or `expired`.

**Deterministic `journal_id`**: `journal_{sha1(signal_id)[:12]}` —
sticky to the underlying signal regardless of `created_at`. A signal
level change creates a new `signal_id` and therefore a new
`journal_id`.

**Journal entry fields** (28 total):
`journal_id, signal_id, symbol, exchange, timeframe, created_at,
signal_ts, setup_type, direction, signal_level, score, confidence,
entry_zone_low/high/mid, invalidation_price, targets, reasons,
risks, action_hint, status, outcome_status, outcome_checked_at,
outcome_5m, outcome_15m, outcome_1h,
max_favorable_excursion_pct, max_adverse_excursion_pct,
notes, metadata`.

**Next milestones can build on this**:
- **LM51 (persistence)** — append journal entries to a `signal_journal`
  Supabase table (LM45 pattern: append-only with optional upsert-by-
  `journal_id`, RLS, service-role-only). Reload on restart.
- **LM52 (outcome tracker)** — watcher that compares `current_price`
  against `invalidation_price` / `targets` over rolling windows and
  calls `update_signal_outcome` with `target_hit` / `invalidated` /
  `expired` + `max_favorable_excursion_pct` / `max_adverse_excursion_pct`.
- **UI surface** — "Live Signals + Outcomes" panel in the Dashboard or
  Terminal, reading from the persisted table.

## LM49 — Signal Object Builder v1
Pure deterministic builder. Sits one level above LM48 — consumes setup
candidates and emits standardized signal dicts ready for UI / alerts.
No I/O, no Supabase, no UI, no API changes.

**Module**: `services/signal_builder.py`
- Public entry: `build_signals(setups, *, options=None)`.
- One signal per valid setup (including `no_trade` setups, so callers
  can record that a market was inspected and decided against).
- Output sorted by `(symbol, timeframe, setup_type, direction, entry_zone_mid)`.
- Tolerant of `None` / malformed inputs — never raises.

**Signal levels** (derived from setup score + confidence):
| Level          | Trigger |
|----------------|---------|
| `no_trade`     | score < `watch_score` OR confidence < `min_confidence` |
| `watch`        | `watch_score` ≤ score < `setup_score` |
| `setup`        | `setup_score` ≤ score < `strong_setup_score` |
| `strong_setup` | score ≥ `strong_setup_score` |

**Statuses**: `active` (actionable level, non-neutral, not invalidated)
| `waiting` (watch level or neutral direction) | `invalidated` (passed
through from setup) | `no_trade`.

**Action hints** (human-readable, constrained):
`wait_for_confirmation`, `wait_for_retest` (for strong defended/rejected
walls — best entered on a retest), `monitor_only`, `avoid_trade`.

**Geometry** (for directional signals only):
- Long: `invalidation = price_zone_low − price_zone_mid × invalidation_buffer_pct / 100`;
  R = `mid − invalidation`; targets = `[mid + R·r1, mid + R·r2]`.
- Short: mirror — `invalidation > zone_high`, targets below mid.
- Neutral / no_trade: `invalidation_price=None`, `targets=[]`.

**Configurable thresholds** (`SignalBuilderOptions`):
- `watch_score` (30.0), `setup_score` (50.0), `strong_setup_score` (70.0)
- `min_confidence` (0.40)
- `target_r_multiple_1` (1.5), `target_r_multiple_2` (3.0)
- `invalidation_buffer_pct` (0.20)

**Deterministic `signal_id`**: `sig_{sha1(setup_id|signal_level|direction)[:12]}` — stable for the same setup at the same level.

**Per-signal fields**:
`signal_id, symbol, exchange, timeframe, signal_ts, setup_id, setup_type,
direction, signal_level, score, confidence, entry_zone_low/high/mid,
invalidation_price, targets, reasons, risks, action_hint, status, metadata`.

**Next milestones can build on this**:
- Persist signals to a `trading_signals` Supabase table (LM45 pattern).
- Surface a "Live Signals" panel in the Dashboard or Terminal.
- Wire `active` signals into the whale-alerts pipeline as a new source.
- Track signal lifecycle (`waiting` → `active` → `invalidated`/`hit_target`).

## LM48 — Setup Classifier v1
Pure deterministic classifier. Sits one level above LM47 — consumes
wall persistence features and emits trading setup candidates. No I/O,
no Supabase, no UI, no API changes.

**Module**: `services/setup_classifier.py`
- Public entry: `classify_setups(features, *, options=None)`.
- Returns a list of setup dicts sorted by
  `(symbol, timeframe, setup_type, direction, price_zone_mid)`.
- Tolerant of `None` / empty / malformed inputs — never raises.

**Setup types**:
| Setup type            | Trigger |
|-----------------------|---------|
| `long_absorption`     | strong defended/active **bid** wall (price floor) |
| `short_rejection`     | strong defended/active **ask** wall (price ceiling) |
| `breakout_pressure`   | strong wall now `broken`/`pulled`/`weakening` — direction inferred from side |
| `liquidity_trap_risk` | A: broken/pulled wall AFTER ≥2 prior touches/defenses, OR B: balanced bid + ask walls (within `conflict_strength_pct`) |
| `no_trade`            | features present but none meet thresholds (per market) |

**Directions**: `long` / `short` / `neutral`.
**Statuses**: `candidate` / `confirmed` / `invalidated` / `no_trade`.

**Configurable thresholds** (`SetupClassifierOptions`):
- `min_confidence`        (0.40) — feature confidence floor
- `min_score`             (35.0) — drop setups below this score
- `strong_wall_strength`  (60.0) — required current/max strength
- `min_persistence_seconds` (30) — wall lifespan required
- `near_price_distance_pct` (0.50) — informational; affects risks
- `conflict_strength_pct`   (30.0) — bid vs ask strength delta for trap B
- `trap_min_history_count`  (2)    — touches+defenses needed for trap A

**Score formula** (0–100):
`base = 0.40·confidence + 0.30·persistence_factor + 0.30·strength_factor`
then setup-type-specific bonuses (defenses ↑, weakens ↓, broken/pulled ↑,
balanced-wall bonus, etc.). Setup confidence is `0.7·(score/100) +
0.3·wall_confidence`, clipped to [0, 1].

**Deterministic `setup_id`**: `setup_{sha1(symbol|exchange|timeframe|setup_type|primary_wall_id)[:12]}`.

**Per-setup fields**:
`setup_id, symbol, exchange, timeframe, setup_ts, setup_type, direction,
score, confidence, price_zone_low/high/mid, primary_wall_id,
related_wall_ids, reasons, risks, status, metadata`.

**Next milestones can build on this**:
- Persist setups to a `trading_setups` Supabase table (mirroring LM45
  pattern: append-only or upsert-by-setup_id; service-role-only RLS).
- Surface a "Live Setups" panel in the Dashboard or Liquidity Map.
- Track `candidate` → `confirmed`/`invalidated` transitions for alerting.
- Add machine-learned scoring as v2 (LM48 is rule-based foundation).

## LM47 — Wall Persistence Feature Engine
Pure deterministic aggregator. Sits one level above LM46 — consumes
LM46 wall events and emits per-wall feature rows. No I/O, no Supabase,
no UI, no API changes.

**Module**: `services/wall_persistence_features.py`
- Public entry: `compute_wall_features(events, *, options=None)`.
- Returns a list of feature dicts sorted by
  `(symbol, timeframe, side, price_mid)`.
- Tolerant of `None`, empty iterables, malformed event dicts — never raises.

**Grouping rule** (sequential, deterministic):
Same `(symbol, exchange, timeframe, side)` AND band overlap OR mid within
`zone_merge_pct`% of group centerline → merged. Group band expands as new
events arrive.

**Statuses** (from last event + counts):
| Status     | Trigger |
|------------|---------|
| `broken`   | last event is `wall_broken` |
| `pulled`   | last event is `wall_pulled` |
| `defended` | last event is `wall_defended`, or defenses > touches |
| `weakening`| last event is `wall_weakened`, or weakens > strengthens |
| `active`   | default |

**Configurable options** (`WallFeatureOptions`):
- `zone_merge_pct` (0.10) — merge tolerance as % of centerline
- `min_persistence_seconds` (0) — drop walls shorter than this
- `min_confidence` (0) — drop events below this confidence before grouping
- `max_reasons` (5) — last-N event reasons kept on the feature

**Feature fields** (per wall):
`wall_id, symbol, exchange, timeframe, side, price_low, price_high,
price_mid, first_seen_ts, last_seen_ts, persistence_seconds,
touch_count, defense_count, break_count, pull_count, strengthen_count,
weaken_count, current_strength, max_strength, min_strength,
strength_delta_pct, avg_distance_to_price_pct, last_event_type,
confidence, status, reasons, metadata`.

**Deterministic `wall_id`**: `wall_{sha1(symbol|exchange|timeframe|side|rounded_centroid)[:12]}`. Stable across runs and small price drift.

**Next milestones can build on this**:
- Persist features to a new `wall_persistence_features` Supabase table
  (append-only, mirrored after LM45 pattern).
- Surface a "active walls" sidebar in the Liquidity Map (read-only).
- Use status transitions ("active" → "broken") as alert triggers.

## LM46 — Liquidity Wall Event Detector (Foundation)
Pure deterministic service. No I/O, no Supabase, no UI, no API changes.

**Module**: `services/liquidity_wall_events.py`
- Public entry: `detect_wall_events(previous_walls, current_walls,
  symbol, exchange, timeframe, current_price, event_ts, thresholds)`.
- Returns a list of event dicts sorted by `(event_type, side, price_mid)`.
- Tolerant of `None` / partial / malformed input — never raises.

**Event types**:
| Type                | Trigger |
|---------------------|---------|
| `wall_created`      | new wall in `current_walls`, none/weak match in previous |
| `wall_strengthened` | matched wall; strength ↑ ≥ `strengthened_delta_pct` |
| `wall_weakened`     | matched wall; strength ↓ ≥ `weakened_delta_pct` |
| `wall_pulled`       | wall in previous, gone in current, no price break |
| `wall_touched`      | price inside band; strength steady/down |
| `wall_defended`     | price inside band AND strength ↑ ≥ threshold (subsumes `strengthened`) |
| `wall_broken`       | price past band by ≥ `broken_distance_pct` AND wall vanished/weakened (subsumes `weakened`) |

**Configurable thresholds** (`WallEventThresholds`):
- `min_strength` (30) — walls below this are ignored
- `created_strength_threshold` (50) — new walls must reach this
- `strengthened_delta_pct` / `weakened_delta_pct` (15 each) — % strength delta
- `touch_distance_pct` (0.50) — % of price away from wall mid
- `broken_distance_pct` (0.50) — % past band edge

**Event fields**: `symbol, exchange, timeframe, event_ts, event_type, side,
price_low, price_high, price_mid, strength, previous_strength,
strength_delta_pct, distance_to_price_pct, confidence, reason, metadata`.

**Helper**: `normalize_wall(w)` accepts LM44 keyZones (camelCase), LM45
liquidity_wall_history rows (snake_case), and LM44 single-bucket walls
(`price_bucket`).

**Next milestones can build on this**:
- Consume events into a future `liquidity_wall_events` Supabase table.
- Surface a "recent events" feed in the UI (Liquidity Map sidebar or Terminal).
- Add sweep/absorption/imbalance-flip detection as additional event types.

## LM45 — Heatmap History & Wall Persistence Foundation
Append-only history alongside the existing `heatmap_latest_payloads`
(which is untouched). Two new Supabase tables, off by default in the
collector, so deployment is safe.

**SQL**: `supabase/heatmap_history.sql`
- `heatmap_frame_history` — one compact snapshot row per
  (symbol, exchange, timeframe, frame_ts)
- `liquidity_wall_history` — top-N zones per frame for trend analysis
- RLS enabled, no policies → service-role only (matches latest-payloads)

**Helper module**: `services/heatmap_history.py` (LM45 section appended
alongside the pre-existing in-memory `HeatmapHistoryStore` — both live in
the same module)
- `build_compact_history_payload(payload, max_cells=300, max_walls=50)`
  → trims cells (top-N by `total`), walls (top-N by `total_usd`), drops
  the full pricePath, keeps only the last point. Stamps
  `meta.historyTag = "heatmap_history_v1"`.
- `build_history_frame_row(payload, ...)` → one row for
  `heatmap_frame_history`.
- `build_wall_history_rows(payload, ...)` → up to N rows from `keyZones`
  (fallback `zones`), ordered by `strengthScore` desc with `wall_rank`.
- `append_history_frame(cfg, row)` / `append_wall_history_rows(cfg, rows)`
  → stdlib urllib POST to PostgREST, raises `HistoryWriteError` on HTTP
  / network failure. Callers catch and keep running.

**WS collector** (`scripts/run_binance_ws_heatmap_live.py`):
- New CLI flags: `--history-target none|supabase` (default none),
  `--history-interval` (default 10s), `--history-max-cells` (300),
  `--history-max-walls` (50).
- History runs on a separate cadence — NEVER every `--write-interval`.
- Per-symbol throttle via `state["last_history_at"]`.
- History failures caught and counted; latest-payload pipeline
  continues unaffected.
- Return dict adds `history_writes`, `history_failures`,
  `history_per_symbol`.

**Recommended command (history ON)**:
```
python scripts/run_binance_ws_heatmap_live.py \
    --symbols BTCUSDT,ETHUSDT,SOLUSDT --timeframes 5m,15m,1h \
    --write-interval 1 --max-frames 1200 \
    --target supabase --forever --range-mode wide \
    --history-target supabase --history-interval 10
```

## LM42B — Multi-Symbol WebSocket Collector
The WS collector now supports many symbols on one socket.

- `--symbols BTCUSDT,ETHUSDT,SOLUSDT` switches to Binance's combined
  `/stream?streams=…` endpoint. Multiplexes every bookTicker over a
  single TCP connection.
- `--symbol BTCUSDT` still works unchanged (uses the original
  `/ws/{sym}@bookTicker` endpoint for byte-for-byte LM42A compat).
- `is_valid_binance_symbol` rejects garbage CLI input (`A-Z0-9`, 3–12
  chars) before opening a stream that would 404.
- Per-symbol state isolation: `bestBid/Ask`, `mid`, `frames`,
  `price_path`, `range_meta`, `last_depth_refresh`, `last_write` are
  all keyed by symbol. One symbol's depth-fetch or upsert error never
  wipes another symbol's data.
- Depth refresh is per-symbol; each symbol respects its own
  `last_depth_refresh` and uses `depth_refresh_seconds` independently.
- Write cadence is per-symbol — each symbol writes at most once per
  `write_interval` window. `--samples` caps **total** writes across
  symbols (e.g. `samples=4` with 2 symbols → 4 writes total).
- Return shape: `{writes, messages, per_symbol: {sym: writes}}`.
- Recommended hosted command:
  `python scripts/run_binance_ws_heatmap_live.py \
      --symbols BTCUSDT,ETHUSDT,SOLUSDT --timeframes 5m,15m,1h \
      --write-interval 1 --max-frames 1200 \
      --target supabase --forever --range-mode wide`

## LM44 — Trader-Grade Liquidity Aggregation
Layered on top of cells/walls; fully additive.

**Zones** — `aggregate_liquidity_zones` groups same-side buckets into
trader-facing bands. Bid and ask never merge into one zone. Group breaks
when the next same-side bucket is more than `max_gap_buckets × price_step`
away. Mode-aware gap defaults:

| Mode      | max_gap_buckets |
|-----------|-----------------|
| tight     | 0  (only strictly adjacent) |
| standard  | 2  |
| wide      | 5  |
| macro     | 10 |

Each zone carries: `side`, `priceMin/Max`, `centerPrice` (USD-weighted),
`totalUsd`, `maxIntensity`, `bucketCount`, `label`, `strengthScore`,
`zoneWidth`, `liquidityDensity`, and `distancePctFromPrice` (when the
writer knows the current mid).

**Scoring** — `score_zones` / `score_walls`:
log-normalized USD percentile (0–90) + proximity boost (0–10) for items
within ±5% of current price. Walls get `wallRank` (1 = strongest).
`meta.wallScoreVersion = "2"` tags payloads built under this model.

**Key zones** — `keyZones` = top-N by strengthScore (default 8).

**Payload additions** (all optional, older consumers ignore):
- `payload.zones` (sorted by centerPrice)
- `payload.keyZones`
- `payload.meta.zoneCount`
- `payload.meta.aggregationMode`
- `payload.meta.bucketAggregation`
- `payload.meta.wallScoreVersion`

**Canvas** — HeatmapCanvas adds a zone-band layer between cells and walls.
Bands span priceMin..priceMax with a 3px minimum height so even hairline
zones stay visible; alpha scales with `strengthScore`. Payloads without
`zones` skip the layer (backward compatible).

## LM43C — Smart Viewport
LM43B made the wide y-axis render, but for `macro` mode (±15000 USD) all
real liquidity got compressed into a thin strip in the middle of a mostly
empty axis. LM43C separates **collection** from **viewport**:
- The writer still collects/stamps the wide requested range in meta.
- The canvas computes the visible y-axis from where data actually exists
  (cells/walls → fallback to `availableDepthMin/Max` → fallback to the
  requested range) plus padding (20% for wide context, 8% otherwise) plus
  the current price line.
- The requested `priceRangeMin/Max` is used as an outer **ceiling** for
  that viewport, never as a forced bound.
- A small `View: Auto · Range: <mode>` chip in the canvas corner shows
  the operator that auto-viewport is active.
- Fallback: when no range meta exists, the original auto-tighten behavior
  applies — fully backward compatible.

## LM43B — Make Wide Range Actually Visible
Fixes for "wide/macro looks narrow" after LM43:
- **Per-cell absolute price**: `compress_heatmap_matrix` now emits
  `cell.price_bucket` so the canvas can place each cell at its real price.
  The legacy `priceMin + p × step` formula broke for sparse axes (common
  for wide/macro), squishing cells into the wrong rows.
- **Canvas honors meta range**: HeatmapCanvas uses `meta.priceRangeMin/Max`
  as the rendered y-axis bounds whenever present, and treats them as a
  valid axis even when the snapshot is empty (so the wider frame still
  draws with empty space above/below the observed liquidity).
- **Deeper book for wide/macro**: both writers auto-bump the Binance depth
  API limit to 5000 (from 1000) for `--range-mode wide|macro`. Explicit
  `--limit` / `--depth-limit` always wins. This populates more of the
  wider y-axis with real far-from-mid levels.