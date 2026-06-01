// lib/mock-heatmap-api.ts
// Synthetic heatmap payload — no network calls, no database.
// Shape mirrors services/heatmap_api_payload.py build_heatmap_api_payload output.

export type {
  HeatmapCell,
  HeatmapWall,
  HeatmapSummary,
  HeatmapMeta,
  HeatmapApiPayload,
  HeatmapApiError,
  HeatmapTimeframe,
} from "@/lib/heatmap-types";

import type {
  HeatmapCell,
  HeatmapWall,
  HeatmapSummary,
  HeatmapApiPayload,
} from "@/lib/heatmap-types";

// ── Synthetic data generation ─────────────────────────────────────────────────

const PRICE_STEP = 10;
const BASE_PRICE = 67_000;
const TOP_PRICE  = 68_000;

function isoOffset(baseIso: string, offsetMinutes: number): string {
  const d = new Date(baseIso);
  d.setMinutes(d.getMinutes() + offsetMinutes);
  return d.toISOString();
}

/** Deterministic intensity between 0–100 for a price/time pair. */
function mockIntensity(price: number, tIdx: number, side: "bid" | "ask"): number {
  // Create a believable gradient — heavier near walls, lighter elsewhere
  const bidWall  = 67_420;
  const askWall  = 67_560;
  const ref      = side === "bid" ? bidWall : askWall;
  const dist     = Math.abs(price - ref);
  const base     = Math.max(0, 80 - dist * 0.25 + tIdx * 2);
  return Math.min(100, Math.round(base));
}

export function buildMockHeatmapPayload(
  symbol: string,
  exchange: string,
  timeframe: string,
): HeatmapApiPayload {
  const now     = new Date().toISOString();
  const offsets = [0, 5, 10]; // 3 time buckets
  const timeBuckets = offsets.map(o => isoOffset(now, -o).replace(/\.\d+Z$/, "Z")).reverse();

  const priceAxis: number[] = [];
  for (let p = BASE_PRICE; p <= TOP_PRICE; p += PRICE_STEP) priceAxis.push(p);

  const cells: HeatmapCell[] = [];

  for (let pIdx = 0; pIdx < priceAxis.length; pIdx++) {
    const price = priceAxis[pIdx];
    for (let tIdx = 0; tIdx < timeBuckets.length; tIdx++) {
      const isBidZone = price <= 67_490;
      const isAskZone = price >= 67_500;

      const bid   = isBidZone ? mockIntensity(price, tIdx, "bid") : 0;
      const ask   = isAskZone ? mockIntensity(price, tIdx, "ask") : 0;
      const total = Math.max(bid, ask);

      if (total > 0) {
        cells.push({ p: pIdx, t: tIdx, bid, ask, total });
      }
    }
  }

  const walls: HeatmapWall[] = [
    {
      price_bucket: 67_420,
      side:        "bid",
      total_usd:   1_850_000,
      intensity:   92,
      label:       "Major Bid Wall",
    },
    {
      price_bucket: 67_560,
      side:        "ask",
      total_usd:   1_650_000,
      intensity:   87,
      label:       "Major Ask Wall",
    },
  ];

  const summary: HeatmapSummary = {
    symbol,
    frame_count:         timeBuckets.length,
    price_min:           BASE_PRICE,
    price_max:           TOP_PRICE,
    time_start:          timeBuckets[0],
    time_end:            timeBuckets[timeBuckets.length - 1],
    max_bid_intensity:   92,
    max_ask_intensity:   87,
    max_total_intensity: 92,
    wall_count:          walls.length,
  };

  return {
    symbol,
    exchange,
    timeframe,
    priceMin:    BASE_PRICE,
    priceMax:    TOP_PRICE,
    priceStep:   PRICE_STEP,
    timeBuckets,
    cells,
    walls,
    summary,
    meta: {
      schemaVersion: "1.0",
      generatedAt:   now,
      cellCount:     cells.length,
      wallCount:     walls.length,
      isDemo:        true,
    },
  };
}
