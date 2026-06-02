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