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
const SUPABASE_TIMEOUT_MS = 2500;

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

function normalizeSupabaseUrl(raw: string): string {
  let url = raw.trim().replace(/\/+$/, "");
  if (url.endsWith("/rest/v1")) {
    url = url.slice(0, -"/rest/v1".length);
  }
  return url;
}

function readSupabaseEnv(): SupabaseEnv | null {
  const url = process.env.SUPABASE_URL;
  const key =
    process.env.SUPABASE_SERVICE_ROLE_KEY ??
    process.env.SUPABASE_ANON_KEY ??
    null;
  if (!url || !key) return null;
  return { url: normalizeSupabaseUrl(url), key };
}

interface SupabaseRow {
  payload?: unknown;
  live_updated_at?: string;
}

interface SupabaseResult {
  payload: HeatmapApiPayload | null;
  error?: string;
  status?: number;
}

async function loadFromSupabase(
  env: SupabaseEnv,
  symbol: string,
  timeframe: string,
  exchange: string,
): Promise<SupabaseResult> {
  const params = new URLSearchParams({
    symbol: `eq.${symbol}`,
    exchange: `eq.${exchange}`,
    timeframe: `eq.${timeframe}`,
    select: "payload,live_updated_at",
    order: "live_updated_at.desc",
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
    if (!res.ok) {
      return { payload: null, error: `HTTP ${res.status}`, status: res.status };
    }
    const rows = (await res.json()) as SupabaseRow[];
    if (!Array.isArray(rows) || rows.length === 0) {
      return { payload: null, error: "no rows", status: res.status };
    }
    const row = rows[0];
    const payload = row?.payload;
    if (!looksLikePayload(payload)) {
      return { payload: null, error: "invalid payload shape", status: res.status };
    }

    const liveTs = row.live_updated_at ?? payload.meta?.liveUpdatedAt;
    if (liveTs) {
      payload.meta.liveUpdatedAt = liveTs;
      payload.meta.generatedAt = payload.meta.generatedAt ?? liveTs;
    }

    return { payload, status: res.status };
  } catch (err) {
    const msg =
      err instanceof Error ? err.message : "unknown";
    return { payload: null, error: msg };
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Load a production live heatmap payload for the given symbol/timeframe.
 *
 * Tries Supabase first (when env vars are present), then falls back to a local
 * file under `fixtures/live/`. Stamps debug hints (supabaseAttempted,
 * supabaseConfigured, supabaseError) so failures are diagnosable without
 * exposing secrets.
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

  // Track debug state for whichever payload we return.
  let supabaseConfigured = false;
  let supabaseAttempted = false;
  let supabaseError: string | undefined;
  let supabaseStatus: number | undefined;

  // 1) Supabase — first choice when configured.
  const env = readSupabaseEnv();
  if (env) {
    supabaseConfigured = true;
    supabaseAttempted = true;
    const result = await loadFromSupabase(env, safeSymbol, safeTf, safeExchange || "binance_spot");
    if (result.payload) {
      result.payload.meta = {
        ...result.payload.meta,
        source: result.payload.meta?.source ?? "supabase_live",
        dataSource: "supabase_live",
        requestedSource: "live",
        resolvedSource: "live",
        isFallback: false,
        supabaseConfigured: true,
        supabaseAttempted: true,
        ...(result.status !== undefined ? { supabaseStatus: result.status } : {}),
      };
      return result.payload;
    }
    supabaseError = result.error;
    supabaseStatus = result.status;
  }

  // 2) Local file fallback (writer skeleton).
  try {
    const filePath = path.join(LIVE_DIR, `${safeSymbol}_${safeTf}.json`);
    if (!fs.existsSync(filePath)) return null;
    const raw = fs.readFileSync(filePath, "utf-8");
    const data: unknown = JSON.parse(raw);
    if (!looksLikePayload(data)) return null;
    data.meta = {
      ...data.meta,
      supabaseConfigured,
      supabaseAttempted,
      ...(supabaseError ? { supabaseError } : {}),
      ...(supabaseStatus !== undefined ? { supabaseStatus } : {}),
    };
    return data;
  } catch {
    return null;
  }
}
