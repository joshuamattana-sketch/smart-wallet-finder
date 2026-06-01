# Liquidity Map — Real Architecture Plan

> Status: Planning · Mock UI exists (LW8–LW12) · Real data pipeline not yet started

---

## 1. Product Goal

A professional orderbook heatmap in the style of Bookmap / CoinGlass:

- **Heatmap background** — spot orderbook depth over time, color-coded by USD size (navy → blue → cyan → green → yellow → red)
- **Price path / candles** — OHLC candlesticks rendered directly over the heatmap
- **Spot buy/sell walls** — prominent horizontal bands where large resting orders cluster
- **Right-side depth profile** — current orderbook snapshot as horizontal bar histogram
- **Timeframes** — 5m, 15m, 1h, 4h, 1D (each changes bucket granularity)
- **Wall labels** — Major Ask Wall, Major Bid Wall, Sweep Zone, etc. detected automatically

---

## 2. Data Sources

### Primary (MVP)
| Source | Method | Data |
|--------|--------|------|
| Binance Spot | WebSocket `depth@100ms` | Full orderbook diffs, top 5000 levels |
| Binance Spot | REST `GET /api/v3/depth` | Snapshot to bootstrap local book |
| Binance Spot | WebSocket `kline_1m` | OHLCV candles for price overlay |

### Later (Pro)
- Binance Futures orderbook + liquidations (`forceOrder` stream)
- Bybit / OKX orderbook for multi-exchange view
- Binance funding rate + open interest streams

### Why WebSocket over polling
Orderbook depth changes every 100–500ms. REST polling at that rate burns rate limits and misses intermediate state. The WebSocket diff stream is the only viable real-time approach.

---

## 3. Backend / Worker Architecture

```
Binance WS ──► Python Worker ──► Aggregator ──► Supabase / TimeSeries DB
                  │                                        │
                  └─ Local order book state                └─ Next.js API reads heatmap tiles
```

### Worker responsibilities
1. Connect to `wss://stream.binance.com/ws/<symbol>@depth@100ms`
2. Receive diff events, apply to in-memory order book (standard Binance diff merge)
3. Every N seconds (configurable per timeframe): snapshot current depth → write time bucket
4. Detect wall changes (new large level / level pulled) → write event
5. Reconnect + re-bootstrap on disconnect

### Worker stack
- Python 3.11+, `websockets` or `aiohttp`, `asyncio`
- Lives in `services/connectors/` (already exists in repo)
- Writes to Supabase via `supabase-py`
- Config per market via environment variables or DB config table

---

## 4. Data Model

### `markets`
```sql
id          uuid primary key
symbol      text        -- 'BTCUSDT'
exchange    text        -- 'binance_spot'
base        text        -- 'BTC'
quote       text        -- 'USDT'
active      boolean
created_at  timestamptz
```

### `orderbook_snapshots`
Raw periodic snapshots. Used to reconstruct history or backfill.
```sql
id            bigserial primary key
market_id     uuid references markets
captured_at   timestamptz
last_update_id bigint
bids          jsonb   -- [["67420.00", "1.234"], ...]  top N levels
asks          jsonb
```
Retention: 24h rolling window (large rows). Aggregate into buckets before discarding.

### `orderbook_depth_buckets`
Pre-aggregated heatmap cells. One row = one (time_bucket, price_bucket) cell.
```sql
id              bigserial primary key
market_id       uuid references markets
time_bucket     timestamptz   -- truncated to bucket size (e.g. 5m)
price_bucket    numeric       -- rounded to price_step (e.g. nearest $10)
bid_usd         numeric       -- total USD depth on bid side in this cell
ask_usd         numeric       -- total USD depth on ask side
max_bid_usd     numeric       -- peak bid depth seen in bucket window
max_ask_usd     numeric       -- peak ask depth seen in bucket window
sample_count    int           -- how many snapshots contributed
```
Index: `(market_id, time_bucket, price_bucket)` — primary query pattern.

### `liquidity_walls`
Detected large persistent levels.
```sql
id              bigserial primary key
market_id       uuid references markets
side            text        -- 'bid' | 'ask'
price           numeric
usd_size        numeric
first_seen_at   timestamptz
last_seen_at    timestamptz
pulled_at       timestamptz  -- null if still present
intensity       numeric      -- 0–100 normalized score
timeframe       text         -- '5m' | '1h' etc.
```

### `price_ticks`
OHLCV data for the candle overlay. Can be sourced from Binance kline stream.
```sql
id          bigserial primary key
market_id   uuid references markets
timeframe   text
open_time   timestamptz
open        numeric
high        numeric
low         numeric
close       numeric
volume      numeric
```

### `heatmap_tiles`
Materialized view / pre-computed output for frontend consumption.
Avoid computing this on every frontend request.
```sql
market_id     uuid
timeframe     text
tile_start    timestamptz
tile_end      timestamptz
price_min     numeric
price_max     numeric
price_step    numeric
time_step     interval
cells         jsonb  -- compressed 2D intensity matrix
generated_at  timestamptz
```

---

## 5. Aggregation Logic

### Price level bucketing
- For BTC: `price_step = 10 USD` (5m), `25 USD` (1h), `50 USD` (4h)
- `price_bucket = FLOOR(price / price_step) * price_step`
- Sum all resting orders within that bucket → `bid_usd` / `ask_usd`

### Time bucketing
- `time_bucket = DATE_TRUNC('5 minutes', captured_at)` etc.
- Average or max across the window (max highlights wall peaks better)

### USD depth calculation
```
usd_depth_at_level = price * quantity
total_bucket_usd   = SUM(usd_depth) for all price levels in [bucket_low, bucket_high]
```

### Intensity scale (0–100)
```
intensity = CLAMP(log10(bucket_usd / min_usd) / log10(max_usd / min_usd) * 100, 0, 100)
```
Log scale is critical — without it, a $50M wall drowns out everything else.
`min_usd` / `max_usd` computed per market over a rolling 24h window.

### Wall detection
A level qualifies as a **wall** when:
- `usd_size > WALL_THRESHOLD` (e.g. $1M for BTC spot)
- Level persists for ≥ 3 consecutive snapshots
- Level has not moved more than `price_step` between snapshots

### Wall persistence
Update `last_seen_at` each snapshot the wall is still present.
Set `pulled_at` when the level drops below threshold — this triggers a "wall pulled" event.

---

## 6. Frontend Rendering

### Why current Tailwind divs are mock-only
- Absolute-positioned `div` per band: works for ~300 static elements
- For a real heatmap: 200 time buckets × 100 price levels = 20,000 cells
- DOM at 20k nodes: layout thrashing, 60fps impossible
- Each `div` has its own paint layer — GPU memory blows up

### Recommended renderer for real data
**Option A: HTML5 Canvas (simpler)**
- `<canvas>` element sized to chart area
- JS renders heatmap cells as `fillRect()` calls
- Price line as `strokePath()`
- 20k cells renders in ~2ms per frame
- Works for up to ~200k cells before needing optimization

**Option B: WebGL (high performance)**
- Required if cells > 200k or animation needed
- Use `regl` or raw WebGL
- Heatmap as a texture upload (1 draw call)
- Suitable for sub-100ms update rates

**Recommended for Lumora MVP:** Canvas 2D. Simple, sufficient for 5m/1h timeframes.

### Layer rendering order
```
1. Background         — solid dark (#04030d)
2. Grid lines         — 1px rgba(255,255,255,0.03)
3. Heatmap tiles      — canvas fillRect per cell, iColor(intensity) fill
4. Major wall glows   — canvas fillRect with wider radius + low opacity
5. Price candles      — canvas strokeRect bodies + lineTo wicks
6. Current price line — canvas strokeStyle cyan, 1px dashed
7. Wall labels        — canvas fillText or DOM overlay
8. Depth profile      — separate canvas or DOM, right side
```

---

## 7. MVP Scope (LM2–LM5)

**What's in:**
- BTCUSDT only
- Binance Spot only
- 5m and 1h timeframes
- Orderbook snapshot every 5 seconds
- 24h of heatmap history
- Price candles from Binance kline API
- No trading, no alerts, no AI explanations

**What's out of MVP:**
- Futures / liquidations
- Multi-exchange
- Real-time push to frontend (polling is fine for MVP)
- Wall alerts

**Frontend data API (Next.js route handler):**
```
GET /api/heatmap?symbol=BTCUSDT&exchange=binance_spot&timeframe=5m&from=<ts>&to=<ts>

Response:
{
  priceMin: 65000,
  priceMax: 69500,
  priceStep: 10,
  timeBuckets: ["2025-06-01T12:00:00Z", ...],
  cells: [[intensity, ...], ...],   // [price_idx][time_idx]
  candles: [{ t, o, h, l, c, v }, ...],
  walls: [{ price, side, intensity, label }, ...]
}
```

---

## 8. Later Pro Features

| Feature | Notes |
|---------|-------|
| Multi-exchange | Normalize orderbooks to USD, merge depth at same price level |
| Futures liquidation overlay | Binance `forceOrder` stream → separate heatmap layer |
| Funding rate / OI overlay | Binance futures REST, per-period bar overlay |
| Wall alerts | Notify when wall appears ≥ threshold, or disappears within 1 bucket |
| Wall pulled detection | `pulled_at` timestamp triggers Supabase webhook → push notification |
| Replay mode | Scrub time axis using pre-computed `heatmap_tiles` |
| AI liquidity explanation | GPT-4o prompt with top-5 walls + price action context |
| Heatmap API (external) | Sell heatmap tile access as API product (already on UI as placeholder) |

---

## 9. Risks and Costs

### WebSocket reliability
- Binance disconnects every 24h → must reconnect + re-bootstrap
- Network blips lose diff events → must detect sequence gap and re-snapshot
- Handle with exponential backoff + sequence validation

### Storage size estimate
- 1 snapshot / 5s × 5000 levels × 16 bytes = ~80KB/snapshot
- Per hour: 720 snapshots = ~57MB raw
- After bucketing to 5m/100-level tiles: ~100KB/hour → 2.4MB/day per symbol
- Manageable with Supabase free tier for MVP

### Rendering performance
- 20k cells at 1fps is trivial on canvas
- At 10fps with smooth scroll/zoom: test on low-end hardware
- WebGL upgrade path exists if needed

### Binance API limits
- WebSocket: 1 connection per stream per IP (no cost)
- REST snapshots: weight 50 per call, limit 1200/min → max 24/min calls fine for 5s intervals (12/min)

### Cost control
- Supabase: 500MB free. At 2.4MB/day per symbol, ~200 days before needing paid plan
- Add TTL cleanup job: delete `orderbook_snapshots` older than 48h
- Keep only bucketed `orderbook_depth_buckets` long-term

---

## 10. Implementation Phases

### LM2 — Collect Binance depth snapshots
- Python worker in `services/connectors/binance_depth_worker.py`
- WebSocket diff stream + REST bootstrap
- Write raw snapshots to `orderbook_snapshots` table
- Deploy as background task (existing worker infrastructure)

### LM3 — Store depth history + bucketing
- Aggregation job: snapshot → `orderbook_depth_buckets`
- Run every minute, buckets 5m and 1h
- Wall detection pass → write `liquidity_walls`
- Add TTL cleanup for raw snapshots

### LM4 — Heatmap matrix API
- Next.js route handler: `GET /api/heatmap`
- Query `orderbook_depth_buckets`, build intensity matrix
- Add candles from `price_ticks`
- Add walls from `liquidity_walls`
- Cache response 30s (Next.js `revalidate`)

### LM5 — Real Canvas renderer in Next.js
- Replace current div-based mock with `<canvas>` renderer
- Implement `drawHeatmap(ctx, tiles)`, `drawCandles(ctx, candles)`, `drawWalls(ctx, walls)`
- Connect to `/api/heatmap` with polling (every 30s for MVP)
- Keep existing controls (symbol, exchange, timeframe, refresh)

### LM6 — Alerts + AI explanations
- Supabase webhook on `liquidity_walls` insert/update
- Push notification via existing alert system
- AI explanation endpoint: summarize top walls + recent price action
