/**
 * lumora-web/lib/chart-heatmap-zones.ts
 * -------------------------------------
 * LM68F — pure helpers turning a real heatmap payload (from /api/heatmap)
 * into Intelligence Chart liquidity zones.
 *
 * No fetching here — `useHeatmapChartZones` owns transport. These functions
 * are deterministic and defensive: malformed input yields an empty list,
 * never throws.
 *
 * The chart's overlay canvas already knows how to draw `LiquidityZone`
 * (side / priceMin / priceMax / strength / label), so the mapper's only job
 * is: pick the payload's zones, convert to that shape, keep the ones near the
 * visible candle price range, and cap the count so the chart never clutters.
 */

import type { HeatmapApiPayload, HeatmapZone } from "@/lib/heatmap-types";
import type {
  ChartCandle,
  LiquidityZone,
  ViewMode,
} from "@/components/charts/mock-intelligence-chart-data";

// Keep the chart readable — never paint more than this many real zones.
const MAX_ZONES_ASSISTED = 4;
const MAX_ZONES_FULL = 8;
// A real zone is only relevant when its band sits within this fraction of the
// visible price range above/below the candles. Beyond that it's noise.
const NEAR_RANGE_FRACTION = 0.6;
// Assisted mode only surfaces convincing zones.
const KEY_STRENGTH = 60;

/** Short notional label: $4.2M · $940K · $1.8B. */
function fmtZoneNotional(n: number): string {
  if (!Number.isFinite(n) || n <= 0) return "$0";
  if (n >= 1_000_000_000) return `$${(n / 1_000_000_000).toFixed(1)}B`;
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `$${Math.round(n / 1_000)}K`;
  return `$${Math.round(n)}`;
}

/**
 * Pick the usable zones array from a payload. Prefers the explicit `zones`
 * field; older payloads may only carry `keyZones`. Returns [] when neither is
 * present or usable.
 */
export function extractHeatmapZones(payload: HeatmapApiPayload | null): HeatmapZone[] {
  if (!payload) return [];
  const zones = Array.isArray(payload.zones) ? payload.zones : [];
  if (zones.length > 0) return zones;
  return Array.isArray(payload.keyZones) ? payload.keyZones : [];
}

/** True when a payload's heatmap zones describe real (non-demo) liquidity. */
export function hasRealHeatmapZones(payload: HeatmapApiPayload | null): boolean {
  return extractHeatmapZones(payload).some(
    (z) =>
      (z.side === "bid" || z.side === "ask") &&
      Number.isFinite(z.priceMin) &&
      Number.isFinite(z.priceMax) &&
      z.priceMax > 0,
  );
}

/**
 * Map a real heatmap payload's zones onto the displayed candle range.
 *
 * - Only `bid`/`ask` zones with a finite, positive price band are kept.
 * - Zones whose band sits far outside the visible candle range (more than
 *   `NEAR_RANGE_FRACTION` of the range above the highs or below the lows) are
 *   dropped — they'd only force the price scale to zoom out.
 * - Assisted density keeps the strongest few (strength ≥ KEY_STRENGTH); Full
 *   keeps more. Both cap the count so candles stay legible.
 * - Output is the chart's own `LiquidityZone` shape, so the overlay canvas
 *   draws real zones exactly like the demo ones.
 */
export function mapHeatmapZonesToChart(
  payload: HeatmapApiPayload | null,
  candles: ChartCandle[],
  density: ViewMode,
): LiquidityZone[] {
  const zones = extractHeatmapZones(payload);
  if (zones.length === 0 || candles.length === 0) return [];

  let hi = -Infinity;
  let lo = Infinity;
  for (const c of candles) {
    if (c.high > hi) hi = c.high;
    if (c.low < lo) lo = c.low;
  }
  if (!Number.isFinite(hi) || !Number.isFinite(lo)) return [];
  const range = Math.max(hi - lo, hi * 0.002);
  const nearTop = hi + range * NEAR_RANGE_FRACTION;
  const nearBot = lo - range * NEAR_RANGE_FRACTION;

  const minStrength = density === "full" ? 0 : KEY_STRENGTH;
  const cap = density === "full" ? MAX_ZONES_FULL : MAX_ZONES_ASSISTED;

  const usable: Array<{ zone: LiquidityZone; strength: number }> = [];
  for (let i = 0; i < zones.length; i++) {
    const z = zones[i];
    if (z.side !== "bid" && z.side !== "ask") continue;

    const priceMin = Math.min(z.priceMin, z.priceMax);
    const priceMax = Math.max(z.priceMin, z.priceMax);
    if (!Number.isFinite(priceMin) || !Number.isFinite(priceMax) || priceMax <= 0) continue;

    // Drop zones whose band lies entirely outside the near-price window.
    if (priceMax < nearBot || priceMin > nearTop) continue;

    const strength = Number.isFinite(z.strengthScore)
      ? Math.max(0, Math.min(100, Math.round(z.strengthScore)))
      : Math.max(0, Math.min(100, Math.round(z.maxIntensity ?? 0)));
    if (strength < minStrength) continue;

    const notionalUsd = Number.isFinite(z.totalUsd) ? z.totalUsd : 0;
    const sideLabel = z.side === "ask" ? "ASK" : "BID";
    const label =
      typeof z.label === "string" && z.label.trim().length > 0
        ? z.label
        : `${sideLabel} · ${fmtZoneNotional(notionalUsd)}`;

    usable.push({
      strength,
      zone: {
        id: `hz-${z.side}-${Math.round(z.centerPrice ?? (priceMin + priceMax) / 2)}-${i}`,
        side: z.side,
        priceMin,
        priceMax,
        strength,
        notionalUsd,
        label,
      },
    });
  }

  if (usable.length === 0) return [];

  // Strongest first, cap, then restore price order so labels read top-to-bottom.
  return usable
    .sort((a, b) => b.strength - a.strength)
    .slice(0, cap)
    .sort((a, b) => b.zone.priceMax - a.zone.priceMax)
    .map((u) => u.zone);
}
