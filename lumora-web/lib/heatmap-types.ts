// lib/heatmap-types.ts
// Central TypeScript types for the Lumora Liquidity Map heatmap pipeline.
// Mirrors the Python schema defined in services/heatmap_api_payload.py.

/** Allowed candle timeframe values for GET /api/heatmap */
export type HeatmapTimeframe = "5m" | "15m" | "1h" | "4h" | "1d";

/**
 * A single non-zero heatmap cell.
 * p and t are indices into the payload's priceAxis and timeBuckets arrays.
 * bid / ask / total are log-scaled intensities in [0, 100].
 */
export interface HeatmapCell {
  p: number;      // index into price_axis
  t: number;      // index into timeBuckets
  bid: number;    // bid intensity 0–100 (0 when no bid liquidity at this cell)
  ask: number;    // ask intensity 0–100 (0 when no ask liquidity at this cell)
  total: number;  // combined intensity 0–100
}

/** A significant liquidity concentration detected above the wall threshold. */
export interface HeatmapWall {
  price_bucket: number;
  side: "bid" | "ask" | "mixed";
  total_usd: number;
  intensity: number;   // 0–100
  label: string;       // "Major Bid Wall" | "Major Ask Wall" | "Liquidity Wall"
}

/** Aggregated statistics across the full matrix. */
export interface HeatmapSummary {
  symbol: string;
  frame_count: number;
  price_min: number;
  price_max: number;
  time_start: string;   // ISO 8601
  time_end: string;     // ISO 8601
  max_bid_intensity: number;
  max_ask_intensity: number;
  max_total_intensity: number;
  wall_count: number;
  /** Latest mid price, when a price path is available. */
  currentPrice?: number;
}

/**
 * One point on the price path overlay (one per time bucket).
 * `t` matches an entry in the payload's timeBuckets array.
 */
export interface HeatmapPricePoint {
  t: string;          // ISO 8601 timestamp
  price: number;      // mid price = (bestBid + bestAsk) / 2
  bestBid?: number;
  bestAsk?: number;
}

/** Metadata envelope included with every response. */
export interface HeatmapMeta {
  schemaVersion: string;  // semver string, currently "1.0"
  generatedAt: string;    // ISO 8601 server timestamp
  cellCount: number;
  wallCount: number;
  isDemo: boolean;        // true while real exchange data is not yet wired
  /**
   * Whether real exchange depth is available for this symbol/exchange combo.
   * false for planned-but-unwired markets (e.g. XMR on Binance Spot). When
   * false the payload still carries demo cells so the UI does not crash.
   */
  sourceAvailable?: boolean;
  /** Human-readable reason shown when sourceAvailable is false. */
  sourceNote?: string | null;
  /** Market lifecycle status from the market-sources registry. */
  marketStatus?: "supported" | "demo" | "planned" | "unsupported";
  /** Resolved data source slug for this market (e.g. "binance_spot"). */
  dataSource?: string;
  /**
   * Origin of this payload's body for the current request:
   *  - "mock"    — synthetic generator (default)
   *  - "fixture" — loaded from a local exported JSON fixture
   * When a real exported fixture carries its own producer tag (e.g.
   * "binance_spot_rest_snapshot"), the route moves it to `dataSource`.
   */
  source?: string;
  /** ISO timestamp of the last live fixture write (local live mode). */
  liveUpdatedAt?: string;
  /** Number of successful samples collected (export / live scripts). */
  sampleCount?: number;
  /** Seconds between samples (export / live scripts). */
  intervalSeconds?: number;
  /** Rolling frame cap used by the local live writer. */
  maxFrames?: number;
  /** Latest mid price, mirrored from summary.currentPrice when available. */
  currentPrice?: number;
  /**
   * Source resolution metadata (set by the API route). `requestedSource` is
   * what the caller asked for via ?source=; `resolvedSource` is what was
   * actually served after the live → fixture → mock fallback chain.
   */
  requestedSource?: "mock" | "fixture" | "live";
  resolvedSource?: "mock" | "fixture" | "live";
  /** True when the served source differs from the requested source. */
  isFallback?: boolean;
  /** True when the payload's timestamp is older than the freshness window. */
  stale?: boolean;
  /** Human-readable reason set when stale is true. */
  staleReason?: string;
  /** Debug: Supabase env vars were present. */
  supabaseConfigured?: boolean;
  /** Debug: Supabase read was attempted. */
  supabaseAttempted?: boolean;
  /** Debug: safe error string when Supabase read failed (no secrets). */
  supabaseError?: string;
  /** Debug: HTTP status of the Supabase read attempt. */
  supabaseStatus?: number;
  /** LM43: analysis-grade price range preset used (tight | standard | wide | macro). */
  priceRangeMode?: string;
  /** LM43: resolved lower bound of the requested heatmap price range (USD). */
  priceRangeMin?: number;
  /** LM43: resolved upper bound of the requested heatmap price range (USD). */
  priceRangeMax?: number;
  /** LM43: absolute USD half-range that was used (when applicable). */
  priceRangeAbs?: number;
  /** LM43: percent half-range used (when applicable, e.g. 0.05 = ±5%). */
  priceRangePercent?: number;
  /** LM43: requested lower bound before any clamping (equal to priceRangeMin in MVP). */
  priceRangeRequestedMin?: number;
  /** LM43: requested upper bound before any clamping. */
  priceRangeRequestedMax?: number;
  /** LM43: lowest price observed in the raw exchange depth snapshot. */
  availableDepthMin?: number;
  /** LM43: highest price observed in the raw exchange depth snapshot. */
  availableDepthMax?: number;
}

/** Full payload returned by GET /api/heatmap on success. */
export interface HeatmapApiPayload {
  symbol: string;
  exchange: string;
  timeframe: HeatmapTimeframe | string;
  priceMin: number | null;
  priceMax: number | null;
  priceStep: number;
  timeBuckets: string[];   // ISO 8601 timestamps, ascending
  cells: HeatmapCell[];    // sparse — only non-zero cells are included
  walls: HeatmapWall[];
  summary: HeatmapSummary;
  meta: HeatmapMeta;
  /** Optional mid-price path overlay, one point per time bucket. */
  pricePath?: HeatmapPricePoint[];
}

/** Error body returned by GET /api/heatmap on 4xx. */
export interface HeatmapApiError {
  error: string;
  message: string;
}

// ── Derived helpers (pure, no DOM) ──────────────────────────────────────────────
// Small read helpers shared by the Dashboard and Terminal pages so they don't
// duplicate payload-reading logic. No dependencies, safe to import anywhere.

/** Latest known price: summary → meta → last pricePath point, else null. */
export function heatmapCurrentPrice(p: HeatmapApiPayload): number | null {
  if (typeof p.summary?.currentPrice === "number") return p.summary.currentPrice;
  if (typeof p.meta?.currentPrice === "number") return p.meta.currentPrice;
  const last = heatmapLastPricePoint(p);
  return last && typeof last.price === "number" ? last.price : null;
}

/** Last price-path point (best bid/ask/mid), or null when no path is present. */
export function heatmapLastPricePoint(p: HeatmapApiPayload): HeatmapPricePoint | null {
  const path = p.pricePath;
  return path && path.length > 0 ? path[path.length - 1] : null;
}

/** Strongest wall by USD, optionally filtered to a side. Null when none. */
export function heatmapStrongestWall(
  p: HeatmapApiPayload,
  side?: "bid" | "ask",
): HeatmapWall | null {
  const walls = (p.walls ?? []).filter((w) => !side || w.side === side);
  if (walls.length === 0) return null;
  return walls.reduce((best, w) => (w.total_usd > best.total_usd ? w : best));
}

/** Average bid/ask intensity across non-zero cells, plus a bid share %. */
export function heatmapIntensitySummary(
  p: HeatmapApiPayload,
): { bid: number; ask: number; bidPct: number } {
  let bidSum = 0, askSum = 0, bidN = 0, askN = 0;
  for (const c of p.cells ?? []) {
    if (c.bid > 0) { bidSum += c.bid; bidN++; }
    if (c.ask > 0) { askSum += c.ask; askN++; }
  }
  const total = bidSum + askSum;
  return {
    bid: bidN ? Math.round(bidSum / bidN) : 0,
    ask: askN ? Math.round(askSum / askN) : 0,
    bidPct: total > 0 ? Math.round((bidSum / total) * 100) : 50,
  };
}

/**
 * Whether a live payload looks stale. Prefers the route's `meta.stale` flag
 * (computed against the 30s freshness window); otherwise falls back to a local
 * liveUpdatedAt check. Returns false when there is no timestamp at all so
 * mock/fixture payloads without one are not flagged by the local check.
 */
export function heatmapIsStale(p: HeatmapApiPayload, maxAgeMs = 15_000): boolean {
  if (typeof p.meta?.stale === "boolean") return p.meta.stale;
  const t = p.meta?.liveUpdatedAt;
  if (!t) return false;
  const ts = new Date(t).getTime();
  if (Number.isNaN(ts)) return false;
  return Date.now() - ts > maxAgeMs;
}

/**
 * Resolved source status for badges, derived from `meta.resolvedSource` (set by
 * the API route after the live → fixture → mock fallback chain):
 *   live    → "Live"
 *   fixture → "Fixture Fallback"
 *   mock    → "Demo Fallback"
 * Also surfaces `isFallback` and `stale` so the UI can show extra hints.
 */
export function heatmapResolvedStatus(p: HeatmapApiPayload | null): {
  label: string;
  variant: "green" | "yellow" | "red" | "muted";
  resolved: string | null;
  isFallback: boolean;
  stale: boolean;
} {
  if (!p) {
    return { label: "—", variant: "muted", resolved: null, isFallback: false, stale: false };
  }
  const m = p.meta;
  const resolved = m?.resolvedSource ?? m?.source ?? m?.dataSource ?? null;
  const isFallback = m?.isFallback ?? false;
  const stale = heatmapIsStale(p);

  if (resolved === "live") {
    return { label: "Live", variant: "green", resolved, isFallback, stale };
  }
  if (resolved === "fixture" || resolved === "local_live_fixture" || resolved === "local_live_writer") {
    return { label: "Fixture Fallback", variant: "yellow", resolved, isFallback, stale };
  }
  return { label: "Demo Fallback", variant: "muted", resolved, isFallback, stale };
}
