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