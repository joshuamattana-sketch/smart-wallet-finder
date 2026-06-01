# Production Live Heatmap — Architecture & Plan

**Status:** Planning only. No production-live code is implemented by this
document — it describes the path from the current local/demo modes to a real
online live Liquidity Map.

**Related docs:**
- [`HEATMAP_API_CONTRACT.md`](./HEATMAP_API_CONTRACT.md) — current `/api/heatmap` contract.
- [`LIQUIDITY_MAP_ARCHITECTURE.md`](./LIQUIDITY_MAP_ARCHITECTURE.md) — current pipeline overview.

---

## 1. Current state (what exists today)

The heatmap pipeline already runs end-to-end, but only against local/synthetic
data. The pieces in place:

| Capability | Where | Notes |
|------------|-------|-------|
| **Mock data** | `lumora-web/lib/mock-heatmap-api.ts` | Synthetic payload generated per request. Default mode. `meta.isDemo = true`. |
| **Fixture data** | `lumora-web/lib/heatmap-fixture-loader.ts` + `?source=fixture` | Serves a local exported JSON from `lumora-web/fixtures/heatmap/{SYMBOL}_{timeframe}.json`; falls back to mock when missing. |
| **Real export (one-shot)** | `scripts/export_real_heatmap_payload.py`, `scripts/export_real_heatmap_history.py` | Pull real Binance Spot depth and run the existing pipeline; write a JSON payload to disk. |
| **Local live writer** | `scripts/run_local_heatmap_live.py` | Loops N samples, keeps a rolling `--max-frames` window, atomically rewrites the fixture file every `--interval` seconds. `meta.source = "local_live_fixture"`, `meta.liveUpdatedAt` stamped. |
| **Price path overlay** | `pricePath` in payload + `HeatmapCanvas.tsx` | Mid-price line drawn over the heatmap. Optional; absent payloads render no line. |
| **Auto refresh** | `liquidity-map/page.tsx` | In fixture mode, the UI polls `/api/heatmap?source=fixture&…` every 2s (silent, no flicker), with a visible Auto On/Off toggle. |

**Shared pipeline (already reused everywhere):**

```
fetch_depth_snapshot            (services/connectors/binance_depth_collector.py)
  → build_heatmap_cells         (services/orderbook_depth_bucketer.py)
  → build_heatmap_matrix        (services/heatmap_matrix_builder.py)
  → build_heatmap_api_payload   (services/heatmap_api_payload.py)
```

**Net:** the *data shape* and *renderer* are production-ready. What's missing is
a hosted process that keeps producing payloads and a storage/serving layer the
deployed `/api/heatmap` can read.

---

## 2. Target picture — production live

```
┌────────────┐   depth     ┌─────────────────────┐   payload   ┌───────────┐
│  Binance   │  snapshots  │   Live Worker       │   writes    │  Storage  │
│  Spot REST │ ──────────▶ │  (Python pipeline)  │ ──────────▶ │  Layer    │
└────────────┘             │  bucket→matrix→     │             └─────┬─────┘
                           │  payload + pricePath│                   │ reads latest/history
                           └─────────────────────┘                   ▼
                                                              ┌───────────────┐
                                                              │ /api/heatmap  │  (Next.js route, server-side)
                                                              │ source=live   │
                                                              └──────┬────────┘
                                                                     │ JSON
                                                                     ▼
                                                              ┌───────────────┐
                                                              │  Liquidity    │  poll (2s) → later WS
                                                              │  Map (Canvas) │
                                                              └───────────────┘
```

Responsibilities:

1. **Worker** — runs continuously off-platform (not in a serverless request).
   Collects Binance depth on an interval, runs the existing pipeline, produces a
   `latest` payload (+ optionally appends history), stamps `liveUpdatedAt`.
2. **Storage layer** — durable place the worker writes and the API reads.
3. **`/api/heatmap`** — gains a `source=live` mode that reads the latest (or
   historical) payload from storage instead of generating mock data. The
   contract (cells/walls/timeBuckets/pricePath/meta) is unchanged.
4. **Frontend** — same auto-refresh poll it already has, just pointed at
   `source=live`. WebSocket push is a later optimization, not a requirement.

The key architectural insight: **the worker reuses the exact same pipeline as
the local live writer** — `run_local_heatmap_live.py` is essentially the worker
minus the deployment target and storage backend. Going to production is mostly a
*storage + hosting* problem, not a *data* problem.

---

## 3. Architecture options

### Option A — Supabase Postgres storage
- Worker writes snapshots/frames/latest payloads into Postgres tables.
- `/api/heatmap` queries Supabase (server-side, service role key) and assembles
  or returns the stored payload.
- **Pros:** queryable history, multi-symbol scaling, row-level metadata, fits an
  existing Supabase footprint, easy retention policies.
- **Cons:** more moving parts; need to keep the JSON shape in sync with rows (or
  store the assembled payload as JSONB to avoid re-assembly cost).

### Option B — Object storage JSON payloads
- Worker writes `latest.json` (and timestamped history objects) to an object
  store (S3 / R2 / Supabase Storage).
- `/api/heatmap` fetches the object server-side and returns it verbatim.
- **Pros:** dead simple, cheap, payload is already the exact response body, great
  cache/CDN story.
- **Cons:** weak querying (history = list/scan objects), no relational metadata,
  per-symbol/per-timeframe key sprawl.

### Option C — Lightweight hosted worker writing latest JSON
- A small always-on host (Fly.io / Railway / Render / a tiny VPS / cron box)
  runs the live writer and pushes `latest` to storage (A or B).
- This is **how the worker is deployed**, orthogonal to where data lives.
- **Pros:** the local live writer ports almost 1:1; cheapest path to "real".
- **Cons:** another deploy target to operate; needs health/restart supervision.

### Option D — WebSocket push (later)
- Replace/augment polling with a WS channel (Supabase Realtime, or the worker
  publishing to a pub/sub the frontend subscribes to).
- **Pros:** lower latency, less redundant fetching at scale.
- **Cons:** premature now — 2s polling is sufficient for an MVP and far simpler.

**Recommended combination for MVP:** **Option C worker + Option B object storage
(`latest.json`)**, then graduate history/multi-symbol to **Option A (Supabase)**
when querying needs grow. Defer **Option D**.

---

## 4. Recommended MVP order

1. ✅ **Local live** — done (`run_local_heatmap_live.py` + fixture auto-refresh).
2. **Hosted worker** — deploy the live writer to an always-on host (Option C).
3. **Latest payload endpoint** — `/api/heatmap?source=live` reads `latest` from
   storage; falls back to fixture/mock on miss (same defensive pattern as today).
4. **Frontend polling** — point the existing fixture poll at `source=live`
   (add `live` to the data-source toggle). No new polling machinery needed.
5. **History storage** — persist rolling frames/snapshots for time-range queries.
6. **Multi-symbol support** — worker fans out over the market registry
   (`lib/market-sources.ts`); storage keyed by symbol + timeframe + exchange.
7. **Alert integration** — wire wall/imbalance events into the existing alert
   engine (`services/whale_alert_engine.py`).

Each step is independently shippable and keeps the app green between steps.

---

## 5. Rough data model

Storage-agnostic; maps to Postgres tables (Option A) or object keys (Option B).

### `heatmap_snapshots`
Raw normalized depth snapshots (optional to persist; useful for replay/audit).
```
id, symbol, exchange, captured_at (ISO),
best_bid, best_ask, mid_price,
bids (jsonb/levels), asks (jsonb/levels),
last_update_id
```

### `heatmap_frames`
Per-snapshot bucketed result (one frame = one time bucket).
```
id, symbol, exchange, timeframe, captured_at,
price_step, buckets (jsonb), walls (jsonb)
```

### `heatmap_latest_payloads`
The assembled, ready-to-serve payload per (symbol, timeframe, exchange).
```
symbol, exchange, timeframe,           -- composite key
payload (jsonb),                       -- exact /api/heatmap body, incl. pricePath
live_updated_at, sample_count, max_frames,
updated_at
```
> Storing the assembled payload (not just frames) lets `/api/heatmap` return it
> with zero re-assembly — the cheapest hot path.

### `symbol_source_metadata`
Mirrors `lib/market-sources.ts` (status, defaultExchange, sourceNote) so the
server can validate symbols and report `marketStatus` without the frontend
registry.
```
symbol, display_name, base, quote,
default_exchange, supported_exchanges,
status (supported|demo|planned|unsupported), source_note
```

History queries select frames by `(symbol, timeframe, captured_at BETWEEN …)`;
live reads hit `heatmap_latest_payloads` by composite key.

---

## 6. API design

Endpoint stays **`GET /api/heatmap`**; the contract body is unchanged. New axis
is the `source` parameter.

| Param | Values | Meaning |
|-------|--------|---------|
| `source` | `mock` (default) \| `fixture` \| `live` | Where the payload comes from. |
| `symbol` | e.g. `BTCUSDT` | Validated against the market registry. |
| `timeframe` | `5m \| 15m \| 1h \| 4h \| 1d` | Candle label. |
| `exchange` | slug, e.g. `binance_spot` | Resolved source. |
| `range` *(future)* | `latest` (default) \| `history` | Latest payload vs a time window. |
| `from` / `to` *(future)* | ISO timestamps | History window bounds. |

Behavior:
- `source=live` → read `heatmap_latest_payloads` (or `latest.json`). On miss or
  staleness, **fall back** to fixture → mock (mirrors the existing fixture
  fallback so the UI never breaks).
- `range=history` → assemble from `heatmap_frames`; `latest` returns the stored
  payload directly.
- **Errors:** keep current shape `{ "error", "message" }`. `400` for unknown
  symbol / invalid timeframe; `503` (new) when `source=live` storage is
  unreachable *and* no fallback is permitted.
- Every payload keeps `meta.source`, `meta.dataSource`, and `meta.liveUpdatedAt`
  so the UI can show provenance and staleness.

---

## 7. Operational concerns

- **Binance rate limits** — `/api/v3/depth` has weight cost scaling with
  `limit`. One worker on a sane interval (≥1–2s, `limit≤1000`) is well within
  limits; multi-symbol must budget combined weight and stagger requests.
- **Retries / backoff** — transient HTTP/`429` errors: exponential backoff, skip
  the tick, keep the previous `latest` payload (the local writer already
  continues on per-tick failure). Never let one bad fetch blank the map.
- **Stale data detection** — `meta.liveUpdatedAt` is the source of truth. The API
  can flag staleness (e.g. `meta.stale = now - liveUpdatedAt > N×interval`); the
  UI already surfaces `liveUpdatedAt` / `Fetched` and can show a "stale" badge.
- **Health checks** — worker exposes a heartbeat (last successful write time);
  alert if it stops advancing. Atomic writes (`.tmp` → `os.replace`) already
  prevent half-written payloads being served.
- **Cost / risk** — object storage + a tiny worker is cents/month. Main risk is
  worker liveness; mitigate with auto-restart + heartbeat alerting. Reads are
  cacheable (short TTL, e.g. 1–2s) to absorb traffic spikes.

---

## 8. Security

- **No secrets in the frontend.** Binance is a public endpoint (no key needed
  for depth); any Supabase/object-store credentials live **only** server-side.
- **Server-side env vars** — service-role / write keys belong to the worker and
  the Next.js server runtime, never `NEXT_PUBLIC_*`. The browser only ever talks
  to `/api/heatmap`.
- **Vercel limitations** — serverless/edge functions are request-scoped and time
  out; they **cannot** host a long-running collector loop. The worker must run
  off-Vercel (Option C). Vercel only runs the read-only `/api/heatmap` route.
- **Worker deployment options** — Fly.io / Railway / Render worker, a small VPS
  with a process supervisor, or a scheduled container. Whichever is chosen, it
  writes to the shared storage the API reads; it accepts no inbound user traffic.

---

## 9. Next implementation milestones

| Milestone | Scope | Touches |
|-----------|-------|---------|
| **LM25** | Hosted worker: package `run_local_heatmap_live` as a deployable long-running service writing `latest` to chosen storage (no UI/API change yet). | scripts / deploy config |
| **LM26** | `source=live` read path in `/api/heatmap` (storage adapter + fallback to fixture/mock); add `live` to the UI data-source toggle. | `app/api/heatmap/route.ts`, a storage lib, `liquidity-map/page.tsx` |
| **LM27** | Staleness handling: `meta.stale` + UI badge driven by `liveUpdatedAt`; health heartbeat for the worker. | API meta, page status panel, worker |
| **LM28** | History storage + `range=history` query and a time-range selector. | data model, API, UI |
| **LM29** | Multi-symbol worker fan-out over the market registry; per-symbol keys. | worker, storage, registry |
| **LM30** | Alert integration (wall/imbalance → alert engine). | `services/whale_alert_engine.py`, worker |
| **LM31+** | Optional WebSocket / Realtime push (Option D) replacing polling. | API, worker, frontend |

---

### Most important architectural decision

**Keep the response contract fixed and make `source` the only axis of change.**
Mock, fixture, and live all return the identical `/api/heatmap` payload shape, so
the renderer and frontend never change as the backend graduates from local files
to a hosted worker + storage. Production-live becomes a *storage + hosting*
problem layered behind an unchanged API — start with a lightweight hosted worker
writing a `latest` payload to object storage, and add Supabase/history/WebSocket
only when real demand appears.
