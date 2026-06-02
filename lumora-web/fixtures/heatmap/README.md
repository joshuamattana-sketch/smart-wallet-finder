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

## Local live mode (multi-symbol / multi-timeframe)

`scripts/run_local_heatmap_live.py` continuously rewrites these fixtures from
real Binance depth. It supports several symbols and timeframes at once and
writes one file per pair using the naming convention above:

```bash
# from the repo root — writes BTCUSDT/ETHUSDT/SOLUSDT × 5m/15m/1h fixtures
python scripts/run_local_heatmap_live.py \
  --symbols BTCUSDT,ETHUSDT,SOLUSDT --timeframes 5m,15m,1h \
  --samples 120 --interval 2 --max-frames 60
```

- Single-symbol form (`--symbol` / `--timeframe` / `--output`) still works.
- Price step defaults per symbol: BTCUSDT `10`, ETHUSDT `5`, SOLUSDT `0.5`,
  otherwise `1`. Override globally with `--price-step`, or per symbol with
  `--price-steps BTCUSDT:10,ETHUSDT:5,SOLUSDT:0.5`.
- Files default to `--output-dir` (this directory). The UI can then load the
  matching fixture as the symbol/timeframe selection changes.

### Active market fast mode

Update the symbol you're actively analysing on a fast cadence while the others
refresh slowly in the background (fewer REST requests, livelier active chart):

```bash
python scripts/run_local_heatmap_live.py \
  --symbols BTCUSDT,ETHUSDT,SOLUSDT --active-symbol BTCUSDT \
  --timeframes 5m,15m,1h \
  --active-interval 2 --background-interval 10 \
  --samples 999999 --max-frames 900
```

- The active symbol updates every `--active-interval` seconds; background
  symbols every `--background-interval` seconds.
- Each payload's `meta` carries `activeSymbol`, `updateMode`
  (`active_fast` / `standard`), `effectiveIntervalSeconds`, and `isActiveSymbol`.
- Without `--active-symbol` the writer behaves exactly as before (every symbol
  every `--interval`).

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
