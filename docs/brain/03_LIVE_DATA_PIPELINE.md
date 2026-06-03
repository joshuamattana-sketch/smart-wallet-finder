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