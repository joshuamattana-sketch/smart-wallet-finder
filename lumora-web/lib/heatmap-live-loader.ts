// lib/heatmap-live-loader.ts
// Server-only loader for production "live" heatmap payloads.
//
// Resolution order:
//   1. Supabase `heatmap_latest_payloads` table (when env vars are present),
//      stamped as resolvedSource="live", dataSource="supabase_live".
//   2. Local `fixtures/live/{SYMBOL}_{timeframe}.json` (writer skeleton).
// A null result lets the API route fall back to fixture → mock.
//
// No new dependencies (Node fs/path + global fetch). Never throws: any problem
// (missing env, network error, bad JSON, wrong shape) resolves to null and
// degrades gracefully. The service-role key is read from process.env on the
// server and is never exposed to the client.

import fs from "node:fs";
import path from "node:path";
import type { HeatmapApiPayload } from "@/lib/heatmap-types";

const LIVE_DIR = path.join(process.cwd(), "fixtures", "live");
const SUPABASE_TABLE = "heatmap_latest_payloads";
const SUPABASE_TIMEOUT_MS = 2500; // keep API responses snappy on Supabase hiccups

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

interface SupabaseEnv {
  url: string;
  key: string;
}

function readSupabaseEnv(): SupabaseEnv | null {
  const url = process.env.SUPABASE_URL;
  // Service-role is preferred (server-only), but a publishable/anon key with
  // a read-policy in place is acceptable. The browser never sees either.
  const key =
    process.env.SUPABASE_SERVICE_ROLE_KEY ??
    process.env.SUPABASE_ANON_KEY ??
    null;
  if (!url || !key) return null;
  return { url: url.replace(/\/+$/, ""), key };
}

/**
 * Try to read the latest payload from Supabase via PostgREST. Returns the
 * stored payload (as written by the live writer) or null on any failure.
 */
async function loadFromSupabase(
  env: SupabaseEnv,
  symbol: string,
  timeframe: string,
  exchange: string,
): Promise<HeatmapApiPayload | null> {
  const params = new URLSearchParams({
    symbol: `eq.${symbol}`,
    exchange: `eq.${exchange}`,
    timeframe: `eq.${timeframe}`,
    select: "payload,live_updated_at",
    limit: "1",
  });
  const url = `${env.url}/rest/v1/${SUPABASE_TABLE}?${params.toString()}`;

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), SUPABASE_TIMEOUT_MS);
  try {
    const res = await fetch(url, {
      method: "GET",
      headers: {
        apikey: env.key,
        Authorization: `Bearer ${env.key}`,
        Accept: "application/json",
      },
      cache: "no-store",
      signal: controller.signal,
    });
    if (!res.ok) return null;
    const rows = (await res.json()) as Array<{ payload?: unknown }>;
    if (!Array.isArray(rows) || rows.length === 0) return null;
    const payload = rows[0]?.payload;
    if (!looksLikePayload(payload)) return null;
    return payload;
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Load a production live heatmap payload for the given symbol/timeframe.
 *
 * Tries Supabase first (when env vars are present), then falls back to a local
 * file under `fixtures/live/`. Stamps a couple of live-source meta hints so the
 * API route can carry them through; the route still computes the final
 * resolvedSource / isFallback / stale fields.
 *
 * Returns the payload, or null when nothing is available. A null result lets
 * the route fall back to fixture → mock.
 */
export async function loadHeatmapLivePayload(
  symbol: string,
  timeframe: string,
  exchange: string = "binance_spot",
): Promise<HeatmapApiPayload | null> {
  const safeSymbol = sanitize(symbol, true);
  const safeTf = sanitize(timeframe, false);
  const safeExchange = exchange.replace(/[^A-Za-z0-9_]/g, "");
  if (!safeSymbol || !safeTf) return null;

  // 1) Supabase — first choice when configured.
  const env = readSupabaseEnv();
  if (env) {
    const sb = await loadFromSupabase(env, safeSymbol, safeTf, safeExchange || "binance_spot");
    if (sb) {
      // Tag origin so the route preserves it on dataSource.
      sb.meta = {
        ...sb.meta,
        source: sb.meta?.source ?? "supabase_live",
        dataSource: "supabase_live",
      };
      return sb;
    }
  }

  // 2) Local file fallback (writer skeleton).
  try {
    const filePath = path.join(LIVE_DIR, `${safeSymbol}_${safeTf}.json`);
    if (!fs.existsSync(filePath)) return null;
    const raw = fs.readFileSync(filePath, "utf-8");
    const data: unknown = JSON.parse(raw);
    if (!looksLikePayload(data)) return null;
    return data;
  } catch {
    return null;
  }
}
