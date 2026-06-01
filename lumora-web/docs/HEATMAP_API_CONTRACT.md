# Heatmap API Contract

**Endpoint:** `GET /api/heatmap`  
**Status:** Demo — synthetic data only (`meta.isDemo: true`).  
**Schema version:** `1.0`

---

## Query parameters

| Parameter  | Type   | Default         | Notes                                         |
|------------|--------|-----------------|-----------------------------------------------|
| `symbol`   | string | `BTCUSDT`       | Normalised to uppercase. E.g. `ETHUSDT`.      |
| `exchange` | string | `binance_spot`  | Snake-case slug. E.g. `bybit_spot`.           |
| `timeframe`| string | `5m`            | Must be one of the allowed values (see below).|

### Allowed timeframes

`5m` · `15m` · `1h` · `4h` · `1d`

Any other value returns HTTP 400.

---

## Success response — HTTP 200

```json
{
  "symbol": "BTCUSDT",
  "exchange": "binance_spot",
  "timeframe": "5m",
  "priceMin": 67000,
  "priceMax": 68000,
  "priceStep": 10,
  "timeBuckets": [
    "2026-06-01T11:50:00Z",
    "2026-06-01T11:55:00Z",
    "2026-06-01T12:00:00Z"
  ],
  "cells": [
    { "p": 42, "t": 0, "bid": 72, "ask": 0,  "total": 72 },
    { "p": 56, "t": 1, "bid": 0,  "ask": 87, "total": 87 }
  ],
  "walls": [
    {
      "price_bucket": 67420,
      "side": "bid",
      "total_usd": 1850000,
      "intensity": 92,
      "label": "Major Bid Wall"
    },
    {
      "price_bucket": 67560,
      "side": "ask",
      "total_usd": 1650000,
      "intensity": 87,
      "label": "Major Ask Wall"
    }
  ],
  "summary": {
    "symbol": "BTCUSDT",
    "frame_count": 3,
    "price_min": 67000,
    "price_max": 68000,
    "time_start": "2026-06-01T11:50:00Z",
    "time_end": "2026-06-01T12:00:00Z",
    "max_bid_intensity": 92,
    "max_ask_intensity": 87,
    "max_total_intensity": 92,
    "wall_count": 2
  },
  "meta": {
    "schemaVersion": "1.0",
    "generatedAt": "2026-06-01T12:00:00.000Z",
    "cellCount": 201,
    "wallCount": 2,
    "isDemo": true
  }
}
```

---

## Error response — HTTP 400

```json
{
  "error": "Invalid timeframe",
  "message": "'3m' is not supported. Valid values: 5m, 15m, 1h, 4h, 1d."
}
```

---

## Field reference

### Top-level

| Field         | Type              | Description                                                    |
|---------------|-------------------|----------------------------------------------------------------|
| `symbol`      | string            | Trading pair, uppercase.                                       |
| `exchange`    | string            | Exchange slug passed through from the request.                 |
| `timeframe`   | string            | Candle timeframe label passed through from the request.        |
| `priceMin`    | number \| null    | Lowest price bucket in the response (inclusive).               |
| `priceMax`    | number \| null    | Highest price bucket in the response (inclusive).              |
| `priceStep`   | number            | Width of each price bucket in USD (e.g. 10 → $10 buckets).    |
| `timeBuckets` | string[]          | ISO 8601 timestamps of each captured snapshot, ascending.      |
| `cells`       | HeatmapCell[]     | Sparse list — only non-zero cells are included.                |
| `walls`       | HeatmapWall[]     | Detected liquidity concentrations, sorted by total_usd desc.   |
| `summary`     | HeatmapSummary    | Aggregate stats across the full matrix.                        |
| `meta`        | HeatmapMeta       | Schema version, generation timestamp, counts, demo flag.       |

---

### `cells[].p` and `cells[].t` — index semantics

Cells use integer indices rather than raw prices / timestamps to keep the
payload compact.

- `p` — zero-based index into the **implicit price axis**.  
  Price axis = `[priceMin, priceMin + priceStep, ..., priceMax]` (ascending).  
  Reconstruct: `price = priceMin + p * priceStep`

- `t` — zero-based index into `timeBuckets` (ascending order).  
  Reconstruct: `timestamp = timeBuckets[t]`

### `cells[].bid`, `cells[].ask`, `cells[].total` — intensity values

All intensity values are **log-scaled floats in [0, 100]**.

- `bid` — intensity of resting bid liquidity at this price/time cell.  
  `0` means no bid orders were present in this bucket.
- `ask` — intensity of resting ask liquidity at this price/time cell.  
  `0` means no ask orders were present in this bucket.
- `total` — combined intensity (`max(bid, ask)` in practice).

Log scaling is applied so that extreme walls (e.g. 50× the average) do not
compress all other levels to near-zero. A value of `100` represents the
single highest-liquidity bucket in the snapshot window.

---

### `walls[].side`

| Value     | Meaning                                          |
|-----------|--------------------------------------------------|
| `"bid"`   | Bucket contains only bid liquidity.              |
| `"ask"`   | Bucket contains only ask liquidity.              |
| `"mixed"` | Bucket straddles the spread — both sides present.|

### `walls[].label`

| Label              | Side    |
|--------------------|---------|
| `"Major Bid Wall"` | `bid`   |
| `"Major Ask Wall"` | `ask`   |
| `"Liquidity Wall"` | `mixed` |

---

### `meta.isDemo`

`true` while the endpoint returns synthetic data generated by
`lib/mock-heatmap-api.ts`.

When real exchange data is connected (Binance depth snapshots → Python
pipeline → Supabase → this endpoint), `isDemo` will be set to `false` and
the UI Demo badge will be hidden automatically.

---

## TypeScript types

All types are defined in [`lib/heatmap-types.ts`](../lib/heatmap-types.ts):

```ts
HeatmapTimeframe   // "5m" | "15m" | "1h" | "4h" | "1d"
HeatmapCell
HeatmapWall
HeatmapSummary
HeatmapMeta
HeatmapApiPayload
HeatmapApiError
```

---

## Notes for live data integration

When replacing demo data with real exchange data:

1. The Python pipeline (`services/heatmap_api_payload.py → build_heatmap_api_payload`)
   already produces the exact same JSON shape. No frontend changes needed.
2. Set `meta.isDemo = false` in the Python payload builder.
3. Wire `route.ts` to call the Python service (HTTP, Supabase, or direct import
   via a Python edge function) instead of `buildMockHeatmapPayload`.
4. The `priceMin` / `priceMax` values will vary per symbol — the frontend
   already handles dynamic ranges.
5. `timeBuckets` length will equal the number of depth snapshots aggregated
   into the matrix (controlled by `frame_count` in `summary`).
