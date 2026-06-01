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
}

/** Error body returned by GET /api/heatmap on 4xx. */
export interface HeatmapApiError {
  error: string;
  message: string;
}
