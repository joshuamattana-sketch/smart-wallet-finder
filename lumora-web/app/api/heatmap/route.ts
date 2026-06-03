import { NextRequest, NextResponse } from "next/server";
import { buildMockHeatmapPayload } from "@/lib/mock-heatmap-api";
import type {
  HeatmapTimeframe,
  HeatmapApiError,
  HeatmapApiPayload,
} from "@/lib/heatmap-types";
import { isKnownSymbol, getMarketSymbols } from "@/lib/market-sources";
import { loadHeatmapFixture } from "@/lib/heatmap-fixture-loader";
import { loadHeatmapLivePayload } from "@/lib/heatmap-live-loader";
import { loadHeatmapDataStatus } from "@/lib/heatmap-status-loader";

// Always render per-request: live payloads must never be served from Next's
// route cache / Vercel data cache, or the UI shows stale numbers until a manual
// page refresh.
export const dynamic = "force-dynamic";
export const revalidate = 0;

const VALID_TIMEFRAMES: HeatmapTimeframe[] = ["5m", "15m", "1h", "4h", "1d"];
const VALID_SOURCES = ["mock", "fixture", "live"] as const;
type HeatmapSource = (typeof VALID_SOURCES)[number];

// No-store headers stamped on every response so no layer caches live data.
const NO_STORE_HEADERS = {
  "Cache-Control": "no-store, no-cache, must-revalidate",
} as const;

// Payload is considered fresh for this long (ms) after its timestamp.
const FRESHNESS_WINDOW_MS = 30_000;

interface Resolution {
  payload: HeatmapApiPayload;
  resolved: HeatmapSource;
  isFallback: boolean;
}

/**
 * Resolve the payload following the fallback chain:
 *   live  → fixture → mock
 *   fixture → mock
 *   mock
 */
async function resolvePayload(
  requested: HeatmapSource,
  symbol: string,
  exchange: string,
  timeframe: string,
): Promise<Resolution> {
  const mock = (): HeatmapApiPayload =>
    buildMockHeatmapPayload(symbol, exchange, timeframe as HeatmapTimeframe);

  if (requested === "live") {
    const live = await loadHeatmapLivePayload(symbol, timeframe);
    if (live) return { payload: live, resolved: "live", isFallback: false };
    const fixture = loadHeatmapFixture(symbol, timeframe);
    if (fixture) return { payload: fixture, resolved: "fixture", isFallback: true };
    return { payload: mock(), resolved: "mock", isFallback: true };
  }

  if (requested === "fixture") {
    const fixture = loadHeatmapFixture(symbol, timeframe);
    if (fixture) return { payload: fixture, resolved: "fixture", isFallback: false };
    return { payload: mock(), resolved: "mock", isFallback: true };
  }

  // requested === "mock"
  return { payload: mock(), resolved: "mock", isFallback: false };
}

/** Stale detection based on the payload's freshest timestamp. */
function detectStale(meta: HeatmapApiPayload["meta"]): { stale: boolean; staleReason?: string } {
  const ts = meta?.liveUpdatedAt ?? meta?.generatedAt;
  if (!ts) return { stale: true, staleReason: "Missing live timestamp" };
  const parsed = Date.parse(ts);
  if (Number.isNaN(parsed)) return { stale: true, staleReason: "Missing live timestamp" };
  if (Date.now() - parsed > FRESHNESS_WINDOW_MS) {
    return { stale: true, staleReason: "Payload older than 30 seconds" };
  }
  return { stale: false };
}

export async function GET(req: NextRequest): Promise<NextResponse> {
  const { searchParams } = req.nextUrl;

  const symbol    = (searchParams.get("symbol")    ?? "BTCUSDT").toUpperCase();
  const exchange  =  searchParams.get("exchange")  ?? "binance_spot";
  const timeframe =  searchParams.get("timeframe") ?? "5m";
  const rawSource =  searchParams.get("source");           // unset → mock
  const requested: HeatmapSource = (rawSource ?? "mock") as HeatmapSource;

  if (rawSource !== null && !(VALID_SOURCES as readonly string[]).includes(rawSource)) {
    const body: HeatmapApiError = {
      error:   "Invalid source",
      message: `'${rawSource}' is not a valid source. Valid values: ${VALID_SOURCES.join(", ")}.`,
    };
    return NextResponse.json(body, { status: 400 });
  }

  if (!isKnownSymbol(symbol)) {
    const body: HeatmapApiError = {
      error:   "Unsupported symbol",
      message: `'${symbol}' is not a known market. Supported symbols: ${getMarketSymbols().join(", ")}.`,
    };
    return NextResponse.json(body, { status: 400 });
  }

  if (!(VALID_TIMEFRAMES as string[]).includes(timeframe)) {
    const body: HeatmapApiError = {
      error:   "Invalid timeframe",
      message: `'${timeframe}' is not supported. Valid values: ${VALID_TIMEFRAMES.join(", ")}.`,
    };
    return NextResponse.json(body, { status: 400 });
  }

  // Resolve the payload through the fallback chain (never throws on missing
  // files — the loaders return null and we degrade gracefully).
  const { payload, resolved, isFallback } = await resolvePayload(
    requested, symbol, exchange, timeframe,
  );

  // Preserve any producer tag the loaded file carried, then stamp source
  // resolution + freshness metadata so the UI can show exactly what was served.
  const producerTag = payload.meta?.dataSource ?? payload.meta?.source ?? resolved;
  const { stale, staleReason } = detectStale(payload.meta);

  payload.meta = {
    ...payload.meta,
    requestedSource: requested,
    resolvedSource: resolved,
    source: resolved,
    dataSource: producerTag,
    isFallback,
    stale,
    ...(staleReason ? { staleReason } : {}),
  };

  // LM60B: attach data status (latest/history freshness) — never blocks or
  // breaks the response; null on any failure.
  try {
    payload.dataStatus = await loadHeatmapDataStatus(symbol, timeframe, exchange);
  } catch {
    payload.dataStatus = null;
  }

  return NextResponse.json(payload, { headers: NO_STORE_HEADERS });
}
