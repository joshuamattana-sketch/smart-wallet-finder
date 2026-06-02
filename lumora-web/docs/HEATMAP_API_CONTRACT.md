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
| `source`   | string | `mock`          | One of `mock` \| `fixture` \| `live`. Any other value returns HTTP 400. Unset = `mock`. |

### Allowed timeframes

`5m` · `15m` · `1h` · `4h` · `1d`

Any other value returns HTTP 400.

### Data sources & fallback chain

The `source` parameter selects where the payload body comes from. Each source
degrades gracefully down the chain, so a missing/not-yet-wired source never
breaks the response:

| Requested  | Chain                       | Looks for |
|------------|-----------------------------|-----------|
| `mock`     | `mock`                      | — (synthetic generator) |
| `fixture`  | `fixture` → `mock`          | `fixtures/heatmap/{SYMBOL}_{timeframe}.json` |
| `live`     | `live` → `fixture` → `mock` | `fixtures/live/{SYMBOL}_{timeframe}.json`, then the fixture path |

- **`source=fixture`** loads a locally exported payload (produced by
  `scripts/export_real_heatmap_payload.py` or the local live writer). Missing or
  invalid → falls back to mock.
- **`source=live`** is the production-live entry point. Today it is a **skeleton**
  (`lib/heatmap-live-loader.ts`) that only reads an optional local file under
  `fixtures/live/`; later it will read a real production live store (object
  storage / Supabase / hosted worker — see `PRODUCTION_LIVE_HEATMAP_PLAN.md`).
  No Supabase or external network call is made from Next.js. Missing → falls back
  to fixture, then mock.

Symbol/timeframe/source validation (and the corresponding 400s) run before any
file lookup. Missing files never crash the route.

### Source resolution & freshness meta

Every 200 response stamps `meta` with what was actually served:

| Field             | Meaning |
|-------------------|---------|
| `requestedSource` | What the caller asked for (`mock`/`fixture`/`live`). |
| `resolvedSource`  | What was actually served after the fallback chain. |
| `source`          | Mirror of `resolvedSource` (origin of the body). |
| `dataSource`      | Preserved producer tag from the loaded file (e.g. `"local_live_fixture"`, `"binance_spot_rest_snapshot"`), else the resolved source. |
| `isFallback`      | `true` when `resolvedSource !== requestedSource`. |
| `stale`           | Freshness flag (see below). |
| `staleReason`     | Present only when `stale` is `true`. |

**Stale detection** uses the payload's freshest timestamp
(`meta.liveUpdatedAt` ?? `meta.generatedAt`):

- Timestamp older than **30 seconds** → `stale: true`,
  `staleReason: "Payload older than 30 seconds"`.
- No usable timestamp → `stale: true`, `staleReason: "Missing live timestamp"`.
- Otherwise → `stale: false`.

Mock payloads are generated on the fly (`generatedAt = now`) so they read as
fresh, but are still clearly marked via `resolvedSource: "mock"` and
`meta.isDemo`.

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

---

### `pricePath` (optional)

Live/history exporters may include a `pricePath` array — one point per time
bucket — so the UI can draw a mid-price line over the heatmap:

```json
"pricePath": [
  { "t": "2026-06-01T12:00:00+00:00", "price": 67495.0, "bestBid": 67490.0, "bestAsk": 67500.0 }
]
```

- `t` matches an entry in `timeBuckets`.
- `price` is the mid price `(bestBid + bestAsk) / 2`.
- When present, the latest mid is also mirrored to `summary.currentPrice` and
  `meta.currentPrice`.

The key is **optional**: the mock endpoint and older fixtures omit it, and the
Canvas renderer simply draws no line when it is absent — nothing crashes.

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

### `meta.sourceAvailable` / `meta.sourceNote`

`sourceAvailable` is `false` for markets that exist in the UI selector but have
no real exchange source wired yet (currently `XMRUSDT` — Monero is not offered
on Binance Spot). For those symbols the endpoint still returns a valid demo
payload (so the renderer never crashes), `isDemo` stays `true`, and
`sourceNote` carries a human-readable explanation the UI surfaces as a small
banner, e.g. `"XMR source planned. Binance Spot depth unavailable for Monero."`

For all supported markets `sourceAvailable` is `true` and `sourceNote` is
`null`.

---

### `meta.marketStatus` / `meta.dataSource`

Resolved from the central market registry in
[`lib/market-sources.ts`](../lib/market-sources.ts):

- `marketStatus` — one of `"supported" | "demo" | "planned" | "unsupported"`.
  BTC/ETH/SOL are `"supported"`, HYPE is `"demo"`, XMR is `"planned"`.
- `dataSource` — the resolved exchange slug backing the market (e.g.
  `"binance_spot"`, `"hyperliquid"`). Falls back to the requested `exchange`
  when the market has no wired default.

The UI uses `marketStatus` for the Supported / Demo / Planned status badge and
`sourceNote` for the small source hint under the controls.

---

### Unsupported symbol error — HTTP 400

A symbol not present in the market registry is rejected:

```json
{
  "error": "Unsupported symbol",
  "message": "'DOGEUSDT' is not a known market. Supported symbols: BTCUSDT, ETHUSDT, SOLUSDT, HYPEUSDT, XMRUSDT."
}
```

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
