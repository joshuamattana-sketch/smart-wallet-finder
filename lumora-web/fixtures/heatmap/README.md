# Heatmap fixtures

Optional, **local-only** exported heatmap payloads that the web API can serve
instead of the synthetic mock. This is a demo/testing convenience — it is **not
production live data** and is never fetched over the network.

## How to add a fixture

Use the Python export script to produce a real Binance Spot snapshot payload,
then drop the JSON here:

```bash
# from the repo root
python scripts/export_real_heatmap_payload.py \
  --symbol BTCUSDT --timeframe 5m \
  --output lumora-web/fixtures/heatmap/BTCUSDT_5m.json
```

## Naming convention

```
{SYMBOL}_{timeframe}.json
```

- `SYMBOL` — upper-case, e.g. `BTCUSDT`
- `timeframe` — lower-case, e.g. `5m`, `15m`, `1h`, `4h`, `1d`

Examples:

```
fixtures/heatmap/BTCUSDT_5m.json
fixtures/heatmap/ETHUSDT_1h.json
```

## How it is used

Request the heatmap API with `source=fixture`:

```
GET /api/heatmap?symbol=BTCUSDT&timeframe=5m&source=fixture
```

- If a matching fixture file exists and is valid → it is returned with
  `meta.source = "fixture"`.
- If no fixture exists (or it is invalid) → the API falls back to the
  synthetic mock with `meta.source = "mock"`.
- Without `source=fixture`, the API behaves exactly as before (mock data).

Fixtures are git-ignorable demo artifacts: feel free to keep them locally
without committing real exported data.
