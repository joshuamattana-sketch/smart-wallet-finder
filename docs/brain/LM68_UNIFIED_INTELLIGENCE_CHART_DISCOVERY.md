# LM68 Unified Intelligence Chart — Discovery

Status: discovery only (LM68A). No frontend code in this patch.
Scope: design the Lumora Unified Intelligence Chart — a premium candlestick
chart with optional Lumora intelligence overlays. It evolves "The Lumora
Field" landing hero (LM67) into a real trading interface: same visual
language, but real candles instead of an illustrative price path, and real
heatmap/whale/futures signals instead of staged scene props.

---

## 1. Core idea

The base chart is **clean candles**. Lumora intelligence appears as
**optional overlays** the user can switch on:

- heatmap / liquidity signal bands
- whale buy/sell markers
- futures pressure context
- current read panel
- sweep risk zones
- setup / level annotations

The chart must be usable with everything off. Not everyone wants full
heatmap structures on top of their trading dashboard — overlays are an
opt-in intelligence layer, never a default wall of paint.

What it is **not**: a generic TradingView clone (no drawing-tool zoo, no
indicator marketplace), and not the landing hero verbatim (no staged scene,
no parallax, no marketing glow inside the app — per DESIGN_DIRECTION rule 10).

---

## 2. Proposed UX — three view modes

One segmented control (same `lm-segment-btn` / `lm-segment-active`
primitives the app already has): **Clean · Assisted · Full Intel**.

| Layer | Clean | Assisted | Full Intel |
|---|---|---|---|
| Candles | ✔ | ✔ | ✔ |
| Volume (toggle) | optional | optional | optional |
| Price/time axes | minimal | minimal | minimal |
| Liquidity zones | — | top 2–3 strongest only, quiet bands | full heatmap signal bands (all zones, intensity-graded) |
| Whale markers | — | important only (HIGH risk / ≥ threshold notional) | all markers, with size scaling |
| Current read badge | — | compact chip (bias · score) | full read strip (bias · score · conf · risk) |
| Futures pressure context | — | — | funding/OI/pressure row |
| Sweep risk zones | — | — | hatched amber band(s) |
| Setup/level annotations | — | — | entry/invalidation lines (when a setup exists) |
| Replay annotations | — | — | optional, off by default |

Mode behavior rules:

- Mode is remembered (localStorage, like the watchlist) per user, not per
  symbol. Default for new users: **Assisted** — shows the product without
  drowning the chart.
- Within a mode, individual overlays can still be toggled from an
  "Overlays" popover (checkbox list). The mode is a preset, not a cage;
  changing a checkbox switches the mode label to "Custom".
- Mobile: same three modes; Full Intel drops to Assisted density
  automatically below `sm` (heatmap bands capped at top 3, futures row
  collapses into the read strip).

### Visual language (from The Lumora Field, LM67)

- Dark terminal plane (`#0d0d10`-ish plot on `lm-surface` panel), hairline
  grid, minimal mono axes — exactly the instrument feel of the hero.
- Cyan = price energy: last-price line/label in `lm-cyan`. Candles
  themselves stay classic green/red bodies (muted: `#22c55e` / `#ef4444`
  at ~85% body opacity, slim wicks) — semantic color rules from
  DESIGN_DIRECTION apply.
- Red bands above price = ask/liquidity pressure; green bands below = bid
  support; band opacity = strength (alpha ramp like `HeatmapCanvas`
  zones: `0.06 + strength/100 * 0.25`, capped ~0.35).
- Amber hatched band = sweep risk (the hero's `SWEEP RISK` zone, now data-
  driven).
- Whale markers: small triangles/dots at (time, price) — green up-marker
  for buys below bars, red down-marker for sells above bars, sized by
  notional bucket, with the hero's single quiet ping on arrival (one ring,
  ~1s, only for new events, only when motion is allowed).
- Current read chip: pixel-identical language to the hero/dashboard chip —
  `READ LONG · 72/100 · RISK MED`.
- Micro-labels in JetBrains Mono, uppercase, tracking-wide — `ASK $38M`,
  `SWEEP RISK`, `FUNDING +0.012%`.
- Calm by default: no scan sweep, no particles, no drift field inside the
  app chart. Those are landing-only theater. The only motion: last-price
  pulse dot, whale-arrival ping, smooth crosshair.

---

## 3. Architecture

### Base library: `lightweight-charts` (TradingView OSS)

Recommended. Reasons:

- **Built for exactly this**: canvas-rendered candlesticks + volume with
  pan/zoom/crosshair, ~45 KB gzipped, zero dependencies, tree-shakeable,
  Apache-2.0.
- **Overlay-friendly**: exposes `timeScale().timeToCoordinate()` and
  `series.priceToCoordinate()` plus pan/zoom subscription events — so a
  custom canvas/SVG overlay layer can stay perfectly registered with the
  chart viewport. v4+ also has a plugin/custom-series API (primitives) if
  we later want overlays drawn inside the chart's own render loop.
- **Owns the hard parts** we'd otherwise rebuild on `HeatmapCanvas`:
  time-scale math, kinetic scrolling, crosshair, DPR handling, axis
  formatting.

Why **not a TradingView embed** (widget/iframe):

- The embedded widget is a closed iframe: no API to draw custom shapes from
  our data (heatmap bands, whale pings, sweep zones are impossible).
- No control over visual identity — it looks like TradingView, branding
  included, which kills the "proprietary intelligence layer" feel.
- Charting Library (the licensed full version) allows custom studies but
  requires a license agreement, ships megabytes, and still fights our
  design system. Overkill when we render our own overlays anyway.

Why not extend `HeatmapCanvas` into a candle chart: it would mean
hand-building pan/zoom/crosshair/scale math — months of chart-engine work
with no product differentiation. `HeatmapCanvas` stays as the Liquidity
Map's dedicated renderer; the new chart is a separate component.

### Layered architecture

One component, `components/chart/IntelligenceChart.tsx`, owning a stack of
positioned layers inside a single `Panel`:

```
┌─ 6. UI controls layer (React/DOM) ─────────────────────────┐
│   mode segmented control · overlay popover · symbol/tf     │
│   status badge · current read chip/strip (DOM, top layer)  │
├─ 5. Pressure/read annotation layer (DOM/SVG, absolute) ────┤
│   read strip · futures context row · setup level lines     │
├─ 4. Whale marker layer (lightweight-charts series markers   │
│   or overlay canvas)                                        │
├─ 3. Heatmap overlay layer (absolute <canvas>, redrawn on   │
│   pan/zoom via coordinate APIs)                             │
├─ 2. Volume layer (lightweight-charts histogram series)      │
├─ 1. Base candle layer (lightweight-charts candle series)    │
└─────────────────────────────────────────────────────────────┘
```

- **Layer 1–2** live inside the lightweight-charts instance (candle series
  + volume histogram on a separate price scale).
- **Layer 3 (heatmap zones + sweep zones)**: one absolutely-positioned
  overlay `<canvas>` matching the chart's plot area. It redraws on
  `subscribeVisibleTimeRangeChange` / crosshair pan using
  `priceToCoordinate` for band y-positions. Horizontal bands are cheap:
  a handful of `fillRect`s per frame, not a cell grid. (If we later want
  per-time-bucket heatmap texture, the LM43 offscreen-buffer trick from
  `HeatmapCanvas` ports directly.)
- **Layer 4 (whale markers)**: first implementation uses the built-in
  `series.setMarkers()` (zero custom math). If marker styling proves too
  limited (no rings, no notional sizing), they move to the layer-3 overlay
  canvas with `timeToCoordinate`.
- **Layer 5 (annotations)**: DOM/SVG absolutely positioned — read strip,
  futures context row, setup entry/invalidation as
  `createPriceLine()` (built-in) with mono titles.
- **Layer 6 (controls)**: plain React; toggling overlays flips layer
  visibility/state only — the chart instance and candle data are never
  recreated (see Performance).

### Component layout

```
components/chart/
  IntelligenceChart.tsx     // orchestrator: chart instance, mode state, layers
  useLightweightChart.ts    // create/destroy chart, resize, theme options
  ZoneOverlayCanvas.tsx     // layer 3: liquidity bands + sweep zones
  WhaleMarkers.ts           // layer 4: marker mapping helpers
  ReadStrip.tsx             // layer 5: read / futures context strip
  chart-contracts.ts        // all data contracts below
  chart-mock-data.ts        // LM68B scene data
```

---

## 4. Data contracts (`chart-contracts.ts`)

Deliberately decoupled from source shapes — adapters map existing payloads
into these. All times are unix seconds (lightweight-charts native).

```ts
export type ViewMode = "clean" | "assisted" | "full";

export interface ChartCandle {
  time: number;            // unix seconds, bucket open
  open: number; high: number; low: number; close: number;
  volume?: number;         // base-asset volume for the volume layer
}

export interface LiquidityZone {
  id: string;
  side: "bid" | "ask";
  priceMin: number;        // band bottom
  priceMax: number;        // band top
  strength: number;        // 0–100 → band alpha
  notionalUsd?: number;    // label: "ASK · $38M"
  kind: "zone" | "wall";   // wall = thin line accent, zone = band
  firstSeen?: number;      // unix s — optional band start on time axis
  lastSeen?: number;       // unix s — band end (default: now / right edge)
}

export interface SweepZone {
  id: string;
  priceMin: number;
  priceMax: number;
  severity: "watch" | "elevated";   // hatch opacity
  note?: string;           // "stops clustered below 66,800"
}

export interface WhaleChartEvent {
  id: string;
  time: number;            // unix seconds (snapped to nearest candle)
  price?: number;          // marker y; fallback: candle close
  side: "BUY" | "SELL";
  notionalUsd: number;     // marker size bucket + label
  risk: "LOW" | "MEDIUM" | "HIGH";
  reason?: string;         // tooltip text
}

export interface FuturesContext {
  fundingRatePct?: number;     // +0.012 (already in %)
  oiChangePct?: number;        // +2.4
  pressure?: "long" | "short" | "balanced";
  leverageHeat?: "low" | "medium" | "high";   // derived bucket, never
                                              // per-account claims (LM64)
  asOf?: number;               // unix seconds
}

export interface CurrentRead {
  bias: "LONG" | "SHORT" | "NEUTRAL";
  score: number;           // 0–100
  confidence: number;      // 0–100
  risk: "LOW" | "MEDIUM" | "HIGH";
  reason: string;          // one sentence, descriptive
  action: string;          // watch/wait language — never predictive
  asOf?: number;
}

export interface SetupLevels {
  entry?: number;
  invalidation?: number;
  target?: number;
  note?: string;
}

export interface IntelligenceChartData {
  symbol: string;
  timeframe: string;       // "5m" | "15m" | "1h" | ...
  candles: ChartCandle[];
  zones: LiquidityZone[];
  sweeps: SweepZone[];
  whales: WhaleChartEvent[];
  futures: FuturesContext | null;
  read: CurrentRead | null;
  setup: SetupLevels | null;
  meta: {
    dataSource: "mock" | "fixture" | "live";
    generatedAt: string;   // ISO
    isStale?: boolean;
  };
}
```

Overlay visibility state (layer 6):

```ts
export interface OverlayState {
  mode: ViewMode;          // preset selector
  volume: boolean;
  zones: boolean;
  whales: boolean;
  sweeps: boolean;
  futures: boolean;
  read: boolean;
  setup: boolean;
  replay: boolean;         // Full Intel only, default false
}
// presetFor(mode): OverlayState — Clean/Assisted/Full mappings from §2.
```

---

## 5. Plugging in existing Lumora data (later patches)

| Contract | Source today | Adapter notes |
|---|---|---|
| `candles` | **none yet** — needs a new source. Options: (a) Binance klines REST proxied via a new `/api/candles` route; (b) extend the Python writer to publish a `chart_candles` payload to Supabase. Recommend (a) first: stateless, no schema change, easy mock parity. | new `lib/candles-loader.ts`, 3-tier live → fixture → mock like the heatmap route |
| `zones`, `sweeps` | `heatmap_latest_payloads` via `lib/heatmap-live-loader.ts` — `payload.zones[]` (LM44: priceMin/priceMax/side/strengthScore) map 1:1 to `LiquidityZone`; `payload.walls[]` map to `kind:"wall"`. Sweep zones: derived later (thin-book + stop-cluster heuristic) — mock until then. | pure mapping fn `zonesFromHeatmap(payload)` |
| `whales` | `whale_events` via `lib/whale-alerts-loader.ts` (Supabase → JSONL → mock). Needs `event_ts` → unix s, `notional_usd`, `side`, `severity→risk`; price at event time is *not* stored today — fallback to nearest candle close (good enough visually), optionally add `price` to the whale event schema later. | `whalesFromAlerts(alerts, candles)` |
| `futures` | LM64 `MarketContext` (funding_rate, oi_change_pct, leverage_heat) — pipeline planned, not live yet. Mock until LM64 lands, then read from whatever table it publishes. | direct field mapping |
| `read` | future `market_read_latest` table (planned). Interim: the dashboard's `deriveSignal()` heuristic can compute a read client-side from the heatmap payload — same numbers the dashboard shows. | `readFromHeatmap(payload)` interim, table later |
| `setup` | `mockSetups` today; signal-builder output later. | — |

---

## 6. Implementation sequence

### LM68B — `LM68B_INTELLIGENCE_CHART_MOCK_PANEL` (next patch)

Everything mocked, UX complete:

- `npm i lightweight-charts` (only new dependency).
- `chart-contracts.ts` + `chart-mock-data.ts`: ~120 deterministic mock
  candles (a believable BTC session that interacts with the mock zones —
  rejects at the ask band, holds the bid band, echoing the Field scene),
  3 zones + 1 wall, 1 sweep zone, 4 whale events, futures context, read,
  one setup.
- `IntelligenceChart.tsx` + `useLightweightChart.ts` + `ZoneOverlayCanvas`
  + `ReadStrip` with all three modes, overlay popover, dark theme matched
  to `lm-*` tokens.
- Mount on a new route or inside Terminal page behind a panel — decide in
  LM68B (recommend new `/chart` page first; integrating into Terminal once
  proven).
- Mode presets, localStorage persistence, reduced-motion + mobile rules.

### LM68C — live candles + live zones

- `/api/candles` route (Binance klines proxy, live → fixture → mock) +
  `lib/candles-loader.ts`.
- `zonesFromHeatmap()` adapter on the existing heatmap live source; polling
  cadence shared with dashboard (2s active / slower background).
- Whale markers from `/api/whale-alerts` with candle-close price snapping.

### LM68D — read/futures integration + polish

- Interim client-side read (`deriveSignal` parity) or `market_read_latest`
  when available; LM64 futures context when the pipeline lands.
- Sweep-zone heuristic, setup lines from the signal builder, replay
  annotations (optional), Terminal-page integration, perf audit.

---

## 7. Performance rules

- **No heavy 3D, no giant animation loops.** No three.js. No rAF loop that
  runs unconditionally — overlay canvas redraws only on data change or
  pan/zoom events; the only persistent animations are the CSS price-pulse
  dot and (when allowed) the brief whale-arrival ping.
- **`prefers-reduced-motion`**: ping/pulse off; everything renders static.
  Pan/zoom (user-initiated) is unaffected.
- **Overlay toggles must not rerender the page or rebuild the chart.**
  Chart instance created once per symbol/timeframe in
  `useLightweightChart`; data updates via `series.update()`; overlay
  toggles only show/hide the overlay canvas/DOM and skip their draw work.
  Mode state lives in the chart component, not in a page-level context.
- **Responsive**: ResizeObserver (pattern already proven in
  `HeatmapCanvas`), DPR-aware overlay canvas, chart `autoSize`.
- **Mobile fallback stays readable**: ~320–380px height, Full Intel
  auto-densifies (top-3 zones, collapsed futures row), axis label thinning
  handled by the library, overlay popover becomes a bottom sheet-style
  list. Crosshair tooltip suppressed on coarse pointers in favor of
  last-value labels.
- Bundle: lightweight-charts ~45 KB gz added to app routes that mount the
  chart only (dynamic `import()` / `next/dynamic` with a skeleton, so
  dashboard/landing stay untouched).

---

## 8. Product rules (copy + claims)

- No guaranteed profits, no financial advice, no exact leverage claims
  (aggregate `leverageHeat` buckets only, per LM64).
- **Never imply prediction.** Allowed language: "risk rising", "pressure
  building", "watch", "wait", "possible sweep", "support holding",
  "invalidates below X". Banned: "will happen", "price will", "guaranteed",
  "predicts", "target will be hit".
- Read strip wording mirrors the dashboard: reason = observation, action =
  watch/wait instruction.
- Data-state honesty: the existing `StatusBadge` live/stale/error/demo
  system applies to every overlay source independently (zones can be live
  while read is demo — show per-layer badges in the overlay popover, one
  aggregate badge in the chart header).
- Disclaimer line under the chart panel: "Informational market context
  only — not financial advice."

---

## 9. Recommended next patch

**LM68B_INTELLIGENCE_CHART_MOCK_PANEL** — scope as defined in §6:
lightweight-charts install, contracts + mock scene, `IntelligenceChart`
with Clean/Assisted/Full Intel modes and overlay popover on a new `/chart`
page. No live data, no worker/Python/Supabase changes.
