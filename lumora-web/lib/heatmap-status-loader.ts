// lib/heatmap-status-loader.ts
// Server-only loader for heatmap data status (latest + history freshness).
//
// Uses the same Supabase REST pattern as heatmap-live-loader.ts — raw fetch,
// no @supabase/supabase-js, service-role key from process.env, never exposed
// to client. Returns null on any failure so the heatmap API is never broken.

const SUPABASE_TIMEOUT_MS = 2500;
const FRESH_THRESHOLD_S = 60;

export interface HeatmapDataStatus {
  latest_found: boolean;
  history_found: boolean;
  latest_updated_at: string | null;
  history_latest_frame_ts: string | null;
  history_row_count: number;
  latest_age_seconds: number | null;
  history_age_seconds: number | null;
  latest_fresh: boolean;
  history_fresh: boolean;
  data_mode: "live" | "stale" | "missing";
  status_label: string;
}

interface SupabaseEnv {
  url: string;
  key: string;
}

function readSupabaseEnv(): SupabaseEnv | null {
  const url = process.env.SUPABASE_URL;
  const key =
    process.env.SUPABASE_SERVICE_ROLE_KEY ??
    process.env.SUPABASE_ANON_KEY ??
    null;
  if (!url || !key) return null;
  return { url: url.trim().replace(/\/+$/, "").replace(/\/rest\/v1$/, ""), key };
}

async function querySupabase(
  env: SupabaseEnv,
  table: string,
  params: URLSearchParams,
): Promise<unknown[] | null> {
  const url = `${env.url}/rest/v1/${table}?${params.toString()}`;
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
    const data = await res.json();
    return Array.isArray(data) ? data : null;
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

function ageSeconds(isoTs: string | null | undefined): number | null {
  if (!isoTs) return null;
  const parsed = Date.parse(isoTs);
  if (Number.isNaN(parsed)) return null;
  return Math.max(0, Math.round((Date.now() - parsed) / 1000));
}

export async function loadHeatmapDataStatus(
  symbol: string,
  timeframe: string,
  exchange: string = "binance_spot",
): Promise<HeatmapDataStatus | null> {
  const env = readSupabaseEnv();
  if (!env) return null;

  const safeSymbol = symbol.replace(/[^A-Za-z0-9]/g, "").toUpperCase();
  const safeTf = timeframe.replace(/[^A-Za-z0-9]/g, "").toLowerCase();
  const safeExchange = exchange.replace(/[^A-Za-z0-9_]/g, "");
  if (!safeSymbol || !safeTf) return null;

  const [latestRows, historyRows] = await Promise.all([
    querySupabase(env, "heatmap_latest_payloads", new URLSearchParams({
      symbol: `eq.${safeSymbol}`,
      exchange: `eq.${safeExchange}`,
      timeframe: `eq.${safeTf}`,
      select: "live_updated_at,updated_at",
      order: "live_updated_at.desc",
      limit: "1",
    })),
    querySupabase(env, "heatmap_frame_history", new URLSearchParams({
      symbol: `eq.${safeSymbol}`,
      exchange: `eq.${safeExchange}`,
      timeframe: `eq.${safeTf}`,
      select: "frame_ts",
      order: "frame_ts.desc",
      limit: "1",
    })),
  ]);

  const latestRow = latestRows?.[0] as Record<string, unknown> | undefined;
  const historyRow = historyRows?.[0] as Record<string, unknown> | undefined;

  const latestTs = (latestRow?.live_updated_at ?? latestRow?.updated_at ?? null) as string | null;
  const historyTs = (historyRow?.frame_ts ?? null) as string | null;

  // Get history row count with a separate lightweight query
  let historyCount = 0;
  if (historyRow) {
    const countRows = await querySupabase(env, "heatmap_frame_history", new URLSearchParams({
      symbol: `eq.${safeSymbol}`,
      exchange: `eq.${safeExchange}`,
      timeframe: `eq.${safeTf}`,
      select: "frame_ts",
      limit: "10000",
    }));
    historyCount = countRows?.length ?? 0;
  }

  const latestAge = ageSeconds(latestTs);
  const historyAge = ageSeconds(historyTs);
  const latestFresh = latestAge !== null && latestAge <= FRESH_THRESHOLD_S;
  const historyFresh = historyAge !== null && historyAge <= FRESH_THRESHOLD_S;
  const latestFound = latestRow != null;
  const historyFound = historyRow != null;

  let dataMode: "live" | "stale" | "missing";
  let statusLabel: string;
  if (latestFound && latestFresh) {
    dataMode = "live";
    statusLabel = "Live data flowing";
  } else if (latestFound) {
    dataMode = "stale";
    statusLabel = `Latest data ${latestAge}s old`;
  } else {
    dataMode = "missing";
    statusLabel = "No data in Supabase";
  }

  return {
    latest_found: latestFound,
    history_found: historyFound,
    latest_updated_at: latestTs,
    history_latest_frame_ts: historyTs,
    history_row_count: historyCount,
    latest_age_seconds: latestAge,
    history_age_seconds: historyAge,
    latest_fresh: latestFresh,
    history_fresh: historyFresh,
    data_mode: dataMode,
    status_label: statusLabel,
  };
}
