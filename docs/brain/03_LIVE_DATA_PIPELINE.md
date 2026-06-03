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