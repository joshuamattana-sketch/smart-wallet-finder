/**
 * lumora-web/lib/chart-whale-events.ts
 * -------------------------------------
 * LM68D — pure helpers turning real whale alerts (from /api/whale-alerts)
 * into Intelligence Chart whale markers.
 *
 * No fetching here — `useWhaleChartEvents` owns transport. These functions
 * are deterministic and defensive: malformed rows are dropped, never thrown.
 */

import type {
  ChartCandle,
  ViewMode,
  WhaleChartEvent,
} from "@/components/charts/mock-intelligence-chart-data";

// ── Types ─────────────────────────────────────────────────────────────────────

/** A real whale event parsed into chart-friendly primitives. */
export interface RawChartWhaleEvent {
  id: string;
  symbol: string;            // uppercase, e.g. "BTCUSDT"
  side: "BUY" | "SELL";
  notionalUsd: number;
  risk: "LOW" | "MEDIUM" | "HIGH";
  severity: string;          // raw bucket, e.g. "high" / "notable"
  confidence: number;        // 0–100
  timeSec: number;           // unix seconds (from event_ts)
  sourceType?: string;
}

// Marker caps per density — keep the chart readable, never spammy.
const MAX_MARKERS_ASSISTED = 6;
const MAX_MARKERS_FULL = 12;
const DEFAULT_BAR_SECONDS = 300;

// ── Formatting ────────────────────────────────────────────────────────────────

/** Short marker label: $4.2M · $940K · $1.8B. */
export function fmtShortNotional(n: number): string {
  if (!Number.isFinite(n) || n <= 0) return "$0";
  if (n >= 1_000_000_000) return `$${(n / 1_000_000_000).toFixed(1)}B`;
  if (n >= 1_000_000)     return `$${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000)         return `$${Math.round(n / 1_000)}K`;
  return `$${Math.round(n)}`;
}

// ── Parsing /api/whale-alerts rows ───────────────────────────────────────────

/**
 * Parse the API's `alerts` array into raw chart events. Rows without a
 * usable `event_ts` or `notional_usd` (e.g. mock alerts) are skipped —
 * the caller treats an empty result as "no real whale data".
 */
export function parseWhaleAlertRows(rows: unknown): RawChartWhaleEvent[] {
  if (!Array.isArray(rows)) return [];
  const out: RawChartWhaleEvent[] = [];
  for (let i = 0; i < rows.length; i++) {
    const row = rows[i];
    if (!row || typeof row !== "object") continue;
    const r = row as Record<string, unknown>;

    const symbol = typeof r.symbol === "string" ? r.symbol.toUpperCase() : "";
    if (!symbol) continue;

    const ts = typeof r.event_ts === "string" ? Date.parse(r.event_ts) : NaN;
    if (!Number.isFinite(ts)) continue;

    const notional = typeof r.notional_usd === "number" ? r.notional_usd : NaN;
    if (!Number.isFinite(notional) || notional <= 0) continue;

    const side = r.side === "SELL" ? "SELL" : "BUY";
    const risk =
      r.risk === "HIGH" ? "HIGH" : r.risk === "MEDIUM" ? "MEDIUM" : "LOW";
    const confidence =
      typeof r.confidence === "number" && Number.isFinite(r.confidence)
        ? Math.max(0, Math.min(100, Math.round(r.confidence)))
        : 0;

    out.push({
      id: String(r.id ?? `whale-${i}`),
      symbol,
      side,
      notionalUsd: notional,
      risk,
      severity: typeof r.severity === "string" ? r.severity : "",
      confidence,
      timeSec: Math.floor(ts / 1000),
      sourceType: typeof r.source_type === "string" ? r.source_type : undefined,
    });
  }
  return out;
}

// ── Mapping events → chart markers ───────────────────────────────────────────

/**
 * Map real whale events onto the displayed candle range.
 *
 * - Only events for `symbol` whose timestamp falls inside (or within two
 *   bars past the end of) the candle range are kept.
 * - Event times are snapped to the owning candle bucket; marker price is
 *   that candle's close.
 * - One marker per (bucket, side) — the strongest notional wins, so bursts
 *   never stack labels on a single candle.
 * - Density caps: Assisted keeps the strongest 6 (HIGH risk always
 *   qualifies), Full Intel keeps the strongest 12.
 * - Result is sorted ascending by time (required by `setMarkers`).
 */
export function mapWhaleEventsToChartMarkers(
  events: RawChartWhaleEvent[],
  candles: ChartCandle[],
  symbol: string,
  density: ViewMode,
): WhaleChartEvent[] {
  if (events.length === 0 || candles.length === 0) return [];

  const barSec =
    candles.length >= 2
      ? Math.max(1, candles[1].time - candles[0].time)
      : DEFAULT_BAR_SECONDS;
  const firstTime = candles[0].time;
  const lastTime = candles[candles.length - 1].time;
  const sym = symbol.toUpperCase();

  // Snap each in-range event to its candle; keep the strongest per (bucket, side).
  const byBucket = new Map<string, RawChartWhaleEvent & { bucketIdx: number }>();
  for (const ev of events) {
    if (ev.symbol !== sym) continue;
    if (ev.timeSec < firstTime || ev.timeSec >= lastTime + 2 * barSec) continue;

    const bucketIdx = Math.min(
      candles.length - 1,
      Math.max(0, Math.floor((ev.timeSec - firstTime) / barSec)),
    );
    const key = `${bucketIdx}:${ev.side}`;
    const prev = byBucket.get(key);
    if (!prev || ev.notionalUsd > prev.notionalUsd) {
      byBucket.set(key, { ...ev, bucketIdx });
    }
  }
  if (byBucket.size === 0) return [];

  // Strongest first, then cap by density.
  const cap = density === "full" ? MAX_MARKERS_FULL : MAX_MARKERS_ASSISTED;
  const strongest = Array.from(byBucket.values())
    .sort((a, b) => b.notionalUsd - a.notionalUsd)
    .slice(0, cap);

  return strongest
    .sort((a, b) => a.bucketIdx - b.bucketIdx || (a.side < b.side ? -1 : 1))
    .map((ev) => {
      const candle = candles[ev.bucketIdx];
      return {
        id: ev.id,
        time: candle.time,
        price: candle.close,
        side: ev.side,
        notionalUsd: ev.notionalUsd,
        risk: ev.risk,
        label: fmtShortNotional(ev.notionalUsd),
      };
    });
}
