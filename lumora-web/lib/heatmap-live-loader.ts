// lib/heatmap-live-loader.ts
// Server-only loader for production "live" heatmap payloads.
//
// SKELETON: for now this just reads an optional local JSON file under
// fixtures/live/. Later this is where a real production live source (object
// storage `latest.json`, Supabase, a hosted worker feed, …) gets wired in —
// see docs/PRODUCTION_LIVE_HEATMAP_PLAN.md. The route's fallback chain
// (live → fixture → mock) means a missing live source degrades gracefully.
//
// No new dependencies (Node's built-in fs/path only). Never throws: any
// problem (missing file, bad JSON, wrong shape) resolves to null.

import fs from "node:fs";
import path from "node:path";
import type { HeatmapApiPayload } from "@/lib/heatmap-types";

const LIVE_DIR = path.join(process.cwd(), "fixtures", "live");

/** Strip anything that isn't safe for a filename to prevent path traversal. */
function sanitize(part: string, upper: boolean): string {
  const cleaned = part.replace(/[^A-Za-z0-9]/g, "");
  return upper ? cleaned.toUpperCase() : cleaned.toLowerCase();
}

/** Minimal structural check — same shape used by the fixture loader. */
function looksLikePayload(data: unknown): data is HeatmapApiPayload {
  if (typeof data !== "object" || data === null) return false;
  const p = data as Record<string, unknown>;
  return (
    typeof p.symbol === "string" &&
    Array.isArray(p.cells) &&
    Array.isArray(p.timeBuckets) &&
    Array.isArray(p.walls) &&
    typeof p.meta === "object" &&
    p.meta !== null
  );
}

/**
 * Load a production live heatmap payload for the given symbol/timeframe.
 *
 * Looks for: fixtures/live/{SYMBOL}_{timeframe}.json
 * Example:   fixtures/live/BTCUSDT_5m.json
 *
 * Returns the parsed payload, or null when the file is missing, unreadable,
 * not valid JSON, or does not look like a heatmap payload. A null result lets
 * the route fall back to fixture → mock.
 */
export function loadHeatmapLivePayload(
  symbol: string,
  timeframe: string,
): HeatmapApiPayload | null {
  try {
    const safeSymbol = sanitize(symbol, true);
    const safeTf = sanitize(timeframe, false);
    if (!safeSymbol || !safeTf) return null;

    const filePath = path.join(LIVE_DIR, `${safeSymbol}_${safeTf}.json`);
    if (!fs.existsSync(filePath)) return null;

    const raw = fs.readFileSync(filePath, "utf-8");
    const data: unknown = JSON.parse(raw);
    if (!looksLikePayload(data)) return null;

    return data;
  } catch {
    // Any error (fs, JSON.parse, …) → safe null. Never crash the route.
    return null;
  }
}
