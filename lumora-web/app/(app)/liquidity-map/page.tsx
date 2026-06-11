"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import { Panel } from "@/components/ui/Panel";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { PageTransition } from "@/components/ui/PageTransition";
import { WatchlistPriorityPicker } from "@/components/ui/WatchlistPriorityPicker";
import { useWatchlist } from "@/lib/watchlist";
import { clsx } from "clsx";
import { RefreshCw, ChevronDown, AlertCircle } from "lucide-react";
import type { HeatmapApiPayload, HeatmapDataStatus } from "@/lib/heatmap-types";
import { heatmapResolvedStatus } from "@/lib/heatmap-types";
import { HeatmapCanvas } from "@/components/liquidity/HeatmapCanvas";
import { IntelligenceChartPanel } from "@/components/charts/IntelligenceChartPanel";
import {
  MARKET_SOURCES,
  getMarketSource,
  getMarketStatusLabel,
  getMarketSourceNote,
} from "@/lib/market-sources";

// ── Layout constants ───────────────────────────────────────────────────────────
const CHART_H   = 560;
// Price band used only by the compact depth-profile rail (synthetic backdrop).
const MIN_PRICE = 65_000;
const MAX_PRICE = 69_500;
const CURRENT_PRICE = 67_420;

const ALL_SYMBOLS = MARKET_SOURCES.map(m => m.symbol);
const EXCHANGES  = ["Binance Spot", "Bybit Spot", "OKX Spot"];
const TIMEFRAMES = ["5m", "15m", "1h", "4h", "1D"] as const;

// ── Helpers ────────────────────────────────────────────────────────────────────
function exchangeToApiSlug(ex: string): string {
  return ex.toLowerCase().replace(/\s+/g, "_");
}

/** CoinGlass-style color ramp: navy → blue → cyan → green → yellow → red */
function iColor(v: number): string {
  if (v <  5) return "rgba(6,8,24,0)";
  if (v < 14) return "rgba(10,18,85,0.55)";
  if (v < 27) return "rgba(12,48,160,0.70)";
  if (v < 40) return "rgba(8,95,215,0.78)";
  if (v < 53) return "rgba(0,158,215,0.84)";
  if (v < 66) return "rgba(0,195,145,0.88)";
  if (v < 78) return "rgba(35,215,55,0.91)";
  if (v < 87) return "rgba(195,225,0,0.93)";
  if (v < 93) return "rgba(255,145,0,0.96)";
  return             "rgba(255,50,18,0.98)";
}

// ── Static wall zones (visual backdrop — unchanged) ────────────────────────────
const ZONES = [
  { price: 68_000, side: "ASK" as const, intensity: 95, label: "Major Ask Wall", badge: "WALL", desc: "Large resting sell orders. Hard resistance, two rejections today." },
  { price: 67_800, side: "ASK" as const, intensity: 72, label: "Spot Sell Wall",  badge: "RES",  desc: "Multiple sellers clustered. Watch for rejection on retest." },
  { price: 67_500, side: "ASK" as const, intensity: 60, label: "Ask Resistance",  badge: "RES",  desc: "Lighter asks stacking above current price." },
  { price: 67_350, side: "BID" as const, intensity: 88, label: "Major Bid Wall",  badge: "WALL", desc: "Held twice in the last hour — strong demand zone." },
  { price: 67_000, side: "BID" as const, intensity: 80, label: "Spot Buy Wall",   badge: "SUP",  desc: "Aligns with daily structure. Key invalidation level." },
  { price: 66_500, side: "BID" as const, intensity: 61, label: "Demand Zone",     badge: "DMZ",  desc: "Lighter bids. Could be swept before reversal." },
  { price: 66_200, side: "BID" as const, intensity: 55, label: "Sweep Zone",      badge: "SWP",  desc: "Likely liquidation magnet on a downside flush." },
  { price: 65_800, side: "BID" as const, intensity: 79, label: "Liquidity Gap",   badge: "GAP",  desc: "Thin orderbook. Fast price movement expected here." },
];

// ── Depth profile sidebar ──────────────────────────────────────────────────────
function DepthBar({ price, intensity, maxI }: { price: number; intensity: number; maxI: number }) {
  const isAsk = price > CURRENT_PRICE;
  const isCur = price === CURRENT_PRICE;
  const w     = (intensity / maxI) * 96;
  const bg    = isCur
    ? "rgba(34,211,238,0.55)"
    : isAsk
    ? iColor(intensity * 0.88).replace(/[\d.]+\)$/, "0.75)")
    : iColor(intensity).replace(/[\d.]+\)$/, "0.70)");

  return (
    <div className="relative h-[18px] flex items-center overflow-hidden">
      <div className="absolute inset-y-0 left-0 rounded-r-sm" style={{ width: `${w}%`, background: bg }} />
      <span
        className={clsx(
          "absolute right-1 num text-[9px] leading-none select-none z-10",
          isCur ? "text-lumora-cyan font-bold" : intensity > 60 ? "text-white/80" : "text-white/40"
        )}
      >
        {isCur ? "▶" : ""}{(price / 1000).toFixed(1)}k
      </span>
    </div>
  );
}

function DepthProfile() {
  const STEP = 50;
  const rows: Array<{ price: number; intensity: number }> = [];

  for (let p = MAX_PRICE - STEP; p >= MIN_PRICE + STEP; p -= STEP) {
    const near = ZONES.reduce((b, z) =>
      Math.abs(z.price - p) < Math.abs(b.price - p) ? z : b
    );
    const dist = Math.abs(near.price - p);
    const raw  = Math.max(0, (1 - dist / 450) * near.intensity * 0.88);
    const n    = Math.abs(Math.sin(p * 0.0091 + 3.1)) * 14;
    const intensity = Math.min(100, raw + n * 0.3);
    if (intensity < 3) continue;
    rows.push({ price: p, intensity });
  }

  const maxI = Math.max(...rows.map(r => r.intensity), 1);

  return (
    <div className="flex flex-col gap-px py-1">
      {rows.map(r => (
        <DepthBar key={r.price} price={r.price} intensity={r.intensity} maxI={maxI} />
      ))}
    </div>
  );
}

// ── Legend ─────────────────────────────────────────────────────────────────────
const LEGEND = [
  { v:  3, l: "" }, { v: 10, l: "Low" }, { v: 22, l: "" },
  { v: 35, l: "Med" }, { v: 50, l: "" }, { v: 63, l: "High" },
  { v: 76, l: "" }, { v: 86, l: "Wall" }, { v: 94, l: "" }, { v: 97, l: "Crit" },
];
function HeatLegend() {
  return (
    <div className="hidden md:flex items-end gap-0.5">
      {LEGEND.map(({ v, l }) => (
        <div key={v} className="flex flex-col items-center gap-0.5">
          <div className="h-3 w-5 rounded-sm" style={{ background: iColor(v) || "#0a0818" }} />
          {l
            ? <span className="text-[8px] text-lm-muted leading-none">{l}</span>
            : <span className="text-[8px] leading-none opacity-0">·</span>
          }
        </div>
      ))}
    </div>
  );
}

// ── Last-good payload cache ──────────────────────────────────────────────────────
// Module-level so the last successfully loaded payload survives component
// remounts (e.g. navigating away to another app tab and back). Keyed by the
// exact selection so we never show one market's data under another.
const payloadCache = new Map<string, HeatmapApiPayload>();

function cacheKey(symbol: string, timeframe: string, dataSource: string): string {
  return `${symbol}|${timeframe.toLowerCase()}|${dataSource}`;
}

/** Minimal shape check so we never replace a good chart with junk. */
function isValidPayload(data: unknown): data is HeatmapApiPayload {
  if (typeof data !== "object" || data === null) return false;
  const p = data as Record<string, unknown>;
  return (
    Array.isArray(p.cells) &&
    Array.isArray(p.timeBuckets) &&
    typeof p.meta === "object" &&
    p.meta !== null
  );
}

type DataSource = "mock" | "fixture" | "live";
const INITIAL_KEY = cacheKey("BTCUSDT", "15m", "live");

// ── LM60B: Data Status Panel ──────────────────────────────────────────────────
function DataStatusPanel({ dataStatus, dataSource }: { dataStatus: HeatmapDataStatus | null; dataSource: string }) {
  if (!dataStatus) {
    if (dataSource !== "live") return null;
    return (
      <Panel flush className="p-3">
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-semibold uppercase tracking-widest text-lm-muted">Data Status</span>
          <span className="text-[10px] text-lm-muted">Supabase not configured</span>
        </div>
      </Panel>
    );
  }

  const modeColor = dataStatus.data_mode === "live" ? "text-emerald-400"
    : dataStatus.data_mode === "stale" ? "text-amber-400" : "text-red-400";
  const modeDot = dataStatus.data_mode === "live" ? "bg-emerald-400"
    : dataStatus.data_mode === "stale" ? "bg-amber-400" : "bg-red-400";

  const latestLabel = dataStatus.latest_found
    ? (dataStatus.latest_fresh ? "Fresh" : `Stale (${dataStatus.latest_age_seconds}s)`)
    : "Missing";
  const latestColor = dataStatus.latest_found
    ? (dataStatus.latest_fresh ? "text-emerald-400" : "text-amber-400")
    : "text-red-400";

  const historyLabel = dataStatus.history_found
    ? (dataStatus.history_fresh ? "Fresh" : `Stale (${dataStatus.history_age_seconds}s)`)
    : "Missing";
  const historyColor = dataStatus.history_found
    ? (dataStatus.history_fresh ? "text-emerald-400" : "text-amber-400")
    : "text-red-400";

  const fmtTime = (iso: string | null) => {
    if (!iso) return "—";
    try { return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }); }
    catch { return "—"; }
  };

  return (
    <Panel flush className="p-3">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <div className="flex items-center gap-1.5 shrink-0">
          <span className="text-[10px] font-semibold uppercase tracking-widest text-lm-muted">Data Status</span>
          <span className={clsx("inline-block w-1.5 h-1.5 rounded-full", modeDot)} />
          <span className={clsx("text-[10px] font-medium", modeColor)}>{dataStatus.status_label}</span>
        </div>
        <div className="h-3 w-px bg-lm-border hidden sm:block" />
        {[
          { k: "Latest", v: latestLabel, c: latestColor },
          { k: "Updated", v: fmtTime(dataStatus.latest_updated_at) },
          { k: "History", v: historyLabel, c: historyColor },
          { k: "History Ts", v: fmtTime(dataStatus.history_latest_frame_ts) },
          { k: "History Rows", v: String(dataStatus.history_row_count) },
        ].map(({ k, v, c }) => (
          <div key={k} className="flex items-center gap-1">
            <span className="text-[9px] uppercase tracking-wide text-lm-muted">{k}</span>
            <span className={clsx("num text-[10px] font-medium", c ?? "text-lm-text")}>{v}</span>
          </div>
        ))}
      </div>
    </Panel>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────────
export default function LiquidityMapPage() {
  const { list: watchlist } = useWatchlist();
  const [symbol,    setSymbol]    = useState("BTCUSDT");
  const [exchange,  setExchange]  = useState("Binance Spot");
  const [timeframe, setTimeframe] = useState<string>("15m");
  const [dataSource, setDataSource] = useState<DataSource>("live");
  const [autoRefresh, setAutoRefresh] = useState(true);
  // LM68B: optional Intelligence Chart preview (mock) — collapsed by default.
  const [showChartPreview, setShowChartPreview] = useState(false);

  // Symbol options: watchlist entries (in priority order) first, then the rest
  // of the supported MARKET_SOURCES. The currently-selected symbol always
  // remains a valid option even if it's not in either group.
  const orderedSymbols = useMemo<string[]>(() => {
    const all: string[] = [...ALL_SYMBOLS];
    const inWatch = watchlist.filter((s) => all.includes(s));
    const inWatchSet = new Set<string>(inWatch);
    const rest = all.filter((s) => !inWatchSet.has(s));
    const merged = [...inWatch, ...rest];
    return merged.includes(symbol) ? merged : [symbol, ...merged];
  }, [watchlist, symbol]);
  const watchSet = useMemo(() => new Set<string>(watchlist), [watchlist]);

  // Initialise from the last-good cache so a remount (app tab switch) shows the
  // previous chart immediately instead of an empty frame.
  const [payload, setPayload] = useState<HeatmapApiPayload | null>(
    () => payloadCache.get(INITIAL_KEY) ?? null,
  );
  const [refreshing, setRefreshing] = useState(false); // any fetch in flight
  const [apiError, setApiError]     = useState<string | null>(null);
  const [fixtureFallback, setFixtureFallback] = useState(false);
  const [lastFetchedAt, setLastFetchedAt] = useState<string | null>(null);

  // Same proven fetch pattern as Terminal/Dashboard: hit /api/heatmap with a
  // cache-buster, accept the JSON payload, and ALWAYS settle the in-flight flag
  // in `finally`. Every fetch ends by setting either a payload or an error, so
  // the loading state (derived as `!payload && !apiError`) can never get stuck.
  const fetchPayload = useCallback(async () => {
    const tf = timeframe.toLowerCase();
    const key = cacheKey(symbol, timeframe, dataSource);
    setRefreshing(true);
    try {
      const exSlug = exchangeToApiSlug(exchange);
      const params = new URLSearchParams({
        symbol,                   // real symbol e.g. BTCUSDT — never a display label
        exchange: exSlug,
        timeframe: tf,            // 5m / 15m / 1h / 4h / 1d
        source: dataSource,       // mock | fixture | live — route does the fallback chain
        _ts: String(Date.now()),  // cache buster so each poll is fresh
      });

      const res = await fetch(`/api/heatmap?${params.toString()}`, { cache: "no-store" });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        // Keep the last good payload on screen; just surface the error.
        setApiError((body as { message?: string }).message ?? `API error ${res.status}`);
        return;
      }

      const data: unknown = await res.json();
      if (!isValidPayload(data)) {
        setApiError("Received an invalid heatmap payload");
        return;
      }

      // Accept the payload as-is (empty cells → empty state, never a perpetual
      // spinner). Flag a fallback when the route served a different source than
      // requested. Replace the last good payload and cache it for remounts.
      setFixtureFallback(Boolean(data.meta?.isFallback));
      payloadCache.set(key, data);
      setPayload(data);
      setApiError(null);
      setLastFetchedAt(new Date().toISOString());
    } catch (err) {
      setApiError(err instanceof Error ? err.message : "Network error");
    } finally {
      setRefreshing(false); // always — the UI is never left stuck on loading
    }
  }, [symbol, exchange, timeframe, dataSource]);

  // Initial load + reload whenever symbol/exchange/timeframe/source changes.
  useEffect(() => { fetchPayload(); }, [fetchPayload]);

  // Auto-refresh every 2s while the toggle is on (cleaned up on change/unmount).
  // lastFetchedAt advances every tick even if the writer's liveUpdatedAt lags.
  useEffect(() => {
    if (!autoRefresh) return;
    const id = setInterval(() => { fetchPayload(); }, 2000);
    return () => clearInterval(id);
  }, [autoRefresh, fetchPayload]);

  // Refresh immediately when the browser tab becomes visible again — the last
  // good payload stays on screen while the refresh runs.
  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState === "visible") fetchPayload();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => document.removeEventListener("visibilitychange", onVisible);
  }, [fetchPayload]);

  // Derive display values — fall back to static defaults when payload not loaded yet
  const summaryData   = payload?.summary;
  const topBidWall    = payload?.walls.find(w => w.side === "bid");
  const topAskWall    = payload?.walls.find(w => w.side === "ask");

  const bidWallLabel  = topBidWall
    ? `$${topBidWall.price_bucket.toLocaleString()}`
    : "$67,350";
  const askWallLabel  = topAskWall
    ? `$${topAskWall.price_bucket.toLocaleString()}`
    : "$68,000";
  const bidWallSub    = topBidWall
    ? `${Math.round(topBidWall.intensity)}% intensity · ${topBidWall.label}`
    : "88% intensity · held 40m";
  const askWallSub    = topAskWall
    ? `${Math.round(topAskWall.intensity)}% intensity · ${topAskWall.label}`
    : "95% intensity · major wall";
  const priceRangeLabel = summaryData
    ? `$${summaryData.price_min.toLocaleString()}–$${summaryData.price_max.toLocaleString()}`
    : "$65,800";
  const frameCountSub   = summaryData
    ? `${summaryData.frame_count} frames · step $${payload?.priceStep ?? 10}`
    : "Thin below $66,200";
  const maxBidI = summaryData ? `${Math.round(summaryData.max_bid_intensity)}% bid` : "+0.42 imbal";
  const maxAskI = summaryData ? `${Math.round(summaryData.max_ask_intensity)}% ask max` : "Break → flush to $66,500";

  // Market source metadata — driven by the registry so it shows immediately on
  // selection, with the payload's note preferred once loaded.
  const sourceNote   = payload?.meta.sourceNote ?? getMarketSourceNote(symbol);
  const statusLabel  = getMarketStatusLabel(symbol);
  const marketStatus = payload?.meta.marketStatus ?? getMarketSource(symbol)?.status ?? "unsupported";
  const statusVariant: "live" | "neutral" | "warning" =
    marketStatus === "supported" ? "live" : marketStatus === "demo" ? "neutral" : "warning";

  // Key zones — use payload walls if available, otherwise static fallback
  const apiWalls = payload?.walls ?? [];
  const showApiWalls = apiWalls.length > 0;

  // Does the displayed payload match the current selection? When it doesn't and
  // a fetch is in flight, we're loading a new selection while keeping old data.
  const tfLower = timeframe.toLowerCase();
  const payloadMatchesSelection =
    payload != null &&
    payload.symbol === symbol &&
    String(payload.timeframe).toLowerCase() === tfLower;
  const selectionLoading = refreshing && payload != null && !payloadMatchesSelection;
  // Resolved source status (Live / Fixture Fallback / Demo Fallback) + stale.
  const resolvedStatus = heatmapResolvedStatus(payload);
  // Map the heatmap colour variant onto the strict StatusBadge variants.
  const resolvedBadgeVariant =
    resolvedStatus.variant === "green" ? "live" :
    resolvedStatus.variant === "red"   ? "error" :
    resolvedStatus.variant === "muted" ? "neutral" : "stale";

  // Status indicator — never implies "empty" while a payload is on screen.
  const statusInfo =
    !payload && !apiError    ? { text: "Loading",                  dot: "bg-yellow-400 animate-pulse", txt: "text-yellow-400" } :
    !payload && apiError     ? { text: "Error",                    dot: "bg-red-400",                  txt: "text-red-400" } :
    selectionLoading         ? { text: "Loading new selection",    dot: "bg-cyan-400 animate-pulse",   txt: "text-lumora-cyan" } :
    apiError                 ? { text: "Connected · refresh failed", dot: "bg-amber-400",              txt: "text-amber-400" } :
    refreshing && payload    ? { text: "Refreshing",               dot: "bg-cyan-400 animate-pulse",   txt: "text-lumora-cyan" } :
    payload                  ? { text: "Connected",                dot: "bg-emerald-400",              txt: "text-emerald-400" } :
                               { text: "—",                        dot: "bg-lm-muted",             txt: "text-lm-muted" };

  return (
    <PageTransition className="space-y-4">

      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-lm-text">Liquidity Map</h1>
          <p className="text-sm text-lm-muted mt-0.5">
            Spot orderbook depth over time{resolvedStatus.resolved === "mock" ? " — demo data" : ""}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <StatusBadge variant={statusVariant} dot={statusVariant === "live"}>{statusLabel}</StatusBadge>
          {payload && <StatusBadge variant={resolvedBadgeVariant} dot={resolvedBadgeVariant === "live"}>{resolvedStatus.label}</StatusBadge>}
          {payload && resolvedStatus.stale && (
            <StatusBadge variant="stale">Stale</StatusBadge>
          )}
        </div>
      </div>

      {/* Controls */}
      <Panel flush className="p-2.5 flex flex-wrap items-center gap-2">
        {/* Symbol — watchlist entries appear first, marked with a star */}
        <div className="relative">
          <select value={symbol} onChange={e => setSymbol(e.target.value)}
            className="appearance-none bg-lm-bg border border-lm-border text-lm-text text-xs rounded-md px-2.5 py-1.5 pr-6 focus:outline-none focus:border-lumora-purple num cursor-pointer">
            {orderedSymbols.map(s => {
              const inWatch = watchSet.has(s);
              const label = getMarketSource(s)?.displayName ?? s;
              return (
                <option key={s} value={s}>
                  {inWatch ? "★ " : ""}{label}
                </option>
              );
            })}
          </select>
          <ChevronDown className="absolute right-1.5 top-2 h-3 w-3 text-lm-muted pointer-events-none" />
        </div>
        <WatchlistPriorityPicker />
        {/* Exchange */}
        <div className="relative">
          <select value={exchange} onChange={e => setExchange(e.target.value)}
            className="appearance-none bg-lm-bg border border-lm-border text-lm-text text-xs rounded-md px-2.5 py-1.5 pr-6 focus:outline-none focus:border-lumora-purple cursor-pointer">
            {EXCHANGES.map(ex => <option key={ex} value={ex}>{ex}</option>)}
          </select>
          <ChevronDown className="absolute right-1.5 top-2 h-3 w-3 text-lm-muted pointer-events-none" />
        </div>
        <div className="h-4 w-px bg-lm-border hidden sm:block" />
        {/* Timeframes */}
        <div className="flex rounded-md border border-lm-border overflow-hidden">
          {TIMEFRAMES.map(tf => (
            <button key={tf} onClick={() => setTimeframe(tf)}
              className={clsx("lm-segment-btn px-2.5 py-1.5 text-xs font-medium",
                timeframe === tf
                  ? "lm-segment-active"
                  : "text-lm-muted bg-lm-surface")}>
              {tf}
            </button>
          ))}
        </div>
        <div className="h-4 w-px bg-lm-border hidden sm:block" />
        {/* Data source toggle — Live (default) → Fixture → Mock. The API falls
            back live → fixture → mock server-side. */}
        <div className="flex rounded-md border border-lm-border overflow-hidden" title="Heatmap data source">
          {(["live", "fixture", "mock"] as const).map(src => (
            <button key={src} onClick={() => setDataSource(src)}
              className={clsx("lm-segment-btn px-2.5 py-1.5 text-xs font-medium capitalize",
                dataSource === src
                  ? "lm-segment-active"
                  : "text-lm-muted bg-lm-surface")}>
              {src}
            </button>
          ))}
        </div>
        {/* Auto-refresh toggle — drives the 2s poll */}
        <button
          onClick={() => setAutoRefresh(v => !v)}
          title="Auto refresh (2s)"
          className={clsx(
            "lm-segment-btn px-2.5 py-1.5 text-xs font-medium rounded-md border",
            autoRefresh
              ? "lm-toggle-active"
              : "border-lm-border bg-lm-surface text-lm-muted"
          )}
        >
          Auto {autoRefresh ? "On" : "Off"}
        </button>
        {/* Refresh */}
        <button onClick={() => fetchPayload()} title="Refresh"
          disabled={refreshing}
          className="lm-segment-btn p-1.5 rounded-md border border-lm-border bg-lm-surface text-lm-muted disabled:opacity-50">
          <RefreshCw className={clsx("h-3.5 w-3.5", refreshing && "animate-spin")} />
        </button>
        {/* Legend */}
        <div className="ml-auto flex items-center gap-3">
          <HeatLegend />
          <div className="h-4 w-px bg-lm-border hidden md:block" />
          <span className="flex items-center gap-1.5 text-[10px] text-lm-muted">
            <span className="inline-block w-5 h-[1.5px] bg-white/60 rounded" />Price
          </span>
          <span className="flex items-center gap-1.5 text-[10px] text-lumora-cyan">
            <span className="lm-now-dot inline-block w-2 h-2 rounded-full bg-lumora-cyan" />Now
          </span>
        </div>
      </Panel>

      {/* API error banner — only when stale data is still on screen; a fresh
          error with no payload renders inside the chart area instead. */}
      {apiError && payload && (
        <div className="flex items-center gap-2 px-3 py-2.5 rounded-lg border border-red-500/30 bg-red-500/10 text-red-300 text-xs">
          <AlertCircle className="h-3.5 w-3.5 shrink-0" />
          <span>{apiError}</span>
        </div>
      )}

      {/* Market source hint — muted for supported markets, highlighted for
          demo/planned (e.g. XMR has no Binance Spot depth). */}
      {sourceNote && (
        <div
          className={clsx(
            "flex items-center gap-2 px-3 py-2 rounded-lg text-xs",
            marketStatus === "supported"
              ? "border border-lm-border bg-lm-surface text-lm-muted"
              : "border border-yellow-500/30 bg-yellow-500/10 text-yellow-300"
          )}
        >
          <AlertCircle className="h-3.5 w-3.5 shrink-0" />
          <span>{sourceNote}</span>
        </div>
      )}

      {/* Main: Canvas heatmap (with price overlay) as the single primary chart
          + compact depth rail. */}
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_140px] gap-3 items-start">

        {/* Primary liquidity heatmap (Canvas) */}
        <Panel flush className="overflow-hidden p-0">
          <div className="px-3 py-1.5 border-b border-lm-border flex items-center justify-between gap-3">
            <span className="text-[11px] text-lm-muted uppercase tracking-wide font-medium">
              Liquidity Heatmap
            </span>
            <div className="flex items-center gap-2">
              {(selectionLoading || (refreshing && payload)) && (
                <span className="flex items-center gap-1 text-[9px] text-lumora-cyan">
                  <RefreshCw className="h-2.5 w-2.5 animate-spin" />
                  {selectionLoading ? "new selection" : "refreshing"}
                </span>
              )}
              <span className="text-[10px] text-lm-muted num">
                {payload
                  ? `${payload.timeBuckets.length} frames · ${payload.meta.cellCount} cells · ${payload.meta.wallCount} walls`
                  : "—"}
              </span>
            </div>
          </div>

          <div className="lm-chart-frame relative" style={{ height: CHART_H, background: "#0a0a0c" }}>
            {/* Initial loading — shown only before the first payload/error.
                Cannot be infinite: every fetch ends by setting one of them. */}
            {!payload && !apiError && (
              <div className="absolute inset-0 z-40 flex items-center justify-center bg-black/30 backdrop-blur-[1px]">
                <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-lm-surface/80 border border-lm-border text-lm-muted text-xs">
                  <RefreshCw className="h-3 w-3 animate-spin" />
                  Loading…
                </div>
              </div>
            )}

            {/* Error card when there is no last-good payload to keep showing */}
            {apiError && !payload && (
              <div className="absolute inset-0 z-30 flex items-center justify-center p-4">
                <div className="flex items-center gap-2 px-3 py-2 rounded-lg border border-red-500/30 bg-red-500/10 text-red-300 text-xs">
                  <AlertCircle className="h-3.5 w-3.5 shrink-0" />
                  <span>{apiError}</span>
                </div>
              </div>
            )}

            {/* Valid but empty payload → explicit empty state, never a spinner */}
            {payload && payload.cells.length === 0 && (
              <div className="absolute inset-0 z-20 flex items-center justify-center text-xs text-lm-muted pointer-events-none">
                No liquidity data in this window
              </div>
            )}

            {payload && <HeatmapCanvas payload={payload} height={CHART_H} showDebug />}
          </div>
        </Panel>

        {/* Depth rail (compact) */}
        <Panel flush className="overflow-hidden p-0">
          <div className="px-2.5 py-1.5 border-b border-lm-border flex items-center justify-between">
            <span className="text-[10px] text-lm-muted uppercase tracking-wide font-medium">Depth</span>
            <span className="text-[10px] text-lumora-cyan font-medium">Now</span>
          </div>
          <div className="px-1.5 py-1.5 overflow-y-auto" style={{ maxHeight: CHART_H - 60 }}>
            <DepthProfile />
          </div>
          <div className="px-2.5 py-1.5 border-t border-lm-border flex flex-col gap-1">
            <div className="flex items-center gap-1.5 text-[10px] text-lm-muted">
              <div className="w-3.5 h-2 rounded-sm shrink-0" style={{ background: iColor(85) }} />Asks
            </div>
            <div className="flex items-center gap-1.5 text-[10px] text-lm-muted">
              <div className="w-3.5 h-2 rounded-sm shrink-0" style={{ background: iColor(75) }} />Bids
            </div>
          </div>
        </Panel>

      </div>

      {/* LM68B: Intelligence Chart preview (mock) — optional candle view with
          Lumora overlays. Collapsed by default so the heatmap stays primary. */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <h2 className="text-xs font-semibold uppercase tracking-widest text-lm-muted flex items-center gap-2">
            Intelligence Chart · Preview
            <StatusBadge variant="warning" size="sm">Demo</StatusBadge>
          </h2>
          <button
            onClick={() => setShowChartPreview((v) => !v)}
            className="lm-segment-btn flex items-center gap-1.5 rounded-md border border-lm-border bg-lm-surface px-2.5 py-1 text-[11px] text-lm-muted"
          >
            {showChartPreview ? "Hide preview" : "Show preview"}
            <ChevronDown
              className={clsx("h-3 w-3 transition-transform", showChartPreview && "rotate-180")}
            />
          </button>
        </div>
        {showChartPreview && <IntelligenceChartPanel height={400} />}
      </div>

      {/* Key zone cards — API walls when available, static fallback otherwise */}
      <div>
        <h2 className="text-xs font-semibold uppercase tracking-widest text-lm-muted mb-2">Key Zones</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {showApiWalls
            ? apiWalls.slice(0, 4).map(w => {
                const isAsk = w.side === "ask";
                const badge = w.intensity >= 85 ? "WALL" : isAsk ? "RES" : "SUP";
                return (
                  <Panel flush hover key={`${w.price_bucket}-${w.side}`} className="p-3 flex items-start gap-2.5">
                    <div
                      className="shrink-0 w-1.5 rounded-full self-stretch mt-0.5"
                      style={{
                        background: isAsk
                          ? "linear-gradient(180deg,#f87171,#ef4444)"
                          : w.intensity > 80
                          ? "linear-gradient(180deg,#c084fc,#8b5cf6)"
                          : "linear-gradient(180deg,#22d3ee,#0891b2)",
                      }}
                    />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-1.5 mb-0.5 flex-wrap">
                        <p className="num text-sm font-semibold text-lm-text">
                          ${w.price_bucket.toLocaleString()}
                        </p>
                        <StatusBadge variant={isAsk ? "ask" : "bid"} size="sm">
                          {badge}
                        </StatusBadge>
                        <span className="num text-[10px] text-lm-muted ml-auto">
                          {Math.round(w.intensity)}%
                        </span>
                      </div>
                      <p className="text-xs font-medium text-lm-text-dim">{w.label}</p>
                      <p className="text-[11px] text-lm-muted mt-0.5 leading-snug">
                        ${(w.total_usd / 1_000_000).toFixed(2)}M liquidity
                      </p>
                    </div>
                  </Panel>
                );
              })
            : ZONES.slice(0, 4).map(z => (
                <Panel flush hover key={z.price} className="p-3 flex items-start gap-2.5">
                  <div
                    className="shrink-0 w-1.5 rounded-full self-stretch mt-0.5"
                    style={{
                      background: z.side === "ASK"
                        ? "linear-gradient(180deg,#f87171,#ef4444)"
                        : z.intensity > 80
                        ? "linear-gradient(180deg,#c084fc,#8b5cf6)"
                        : "linear-gradient(180deg,#22d3ee,#0891b2)",
                    }}
                  />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1.5 mb-0.5 flex-wrap">
                      <p className="num text-sm font-semibold text-lm-text">${z.price.toLocaleString()}</p>
                      <StatusBadge variant={z.side === "ASK" ? "ask" : "bid"} size="sm">
                        {z.badge}
                      </StatusBadge>
                      <span className="num text-[10px] text-lm-muted ml-auto">{z.intensity}%</span>
                    </div>
                    <p className="text-xs font-medium text-lm-text-dim">{z.label}</p>
                    <p className="text-[11px] text-lm-muted mt-0.5 leading-snug">{z.desc}</p>
                  </div>
                </Panel>
              ))
          }
        </div>
      </div>

      {/* Summary stat cards — values from API payload */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        {[
          { label: "Strongest Bid",  value: bidWallLabel,                   sub: bidWallSub,   color: "text-lumora-green"         },
          { label: "Strongest Ask",  value: askWallLabel,                   sub: askWallSub,   color: "text-lumora-red"           },
          { label: "Price Range",    value: priceRangeLabel,                sub: frameCountSub, color: "text-yellow-400"          },
          { label: "Max Bid Intens", value: `${Math.round(summaryData?.max_bid_intensity ?? 88)}%`, sub: maxBidI, color: "text-lumora-purple-bright" },
          { label: "Max Ask Intens", value: `${Math.round(summaryData?.max_ask_intensity ?? 95)}%`, sub: maxAskI, color: "text-lumora-cyan"           },
        ].map(({ label, value, sub, color }) => (
          <Panel flush key={label} className="p-3">
            <p className="text-[11px] text-lm-muted uppercase tracking-wide mb-1.5">{label}</p>
            <p className={clsx("num text-sm font-semibold", color)}>{value}</p>
            <p className="text-[11px] text-lm-muted mt-1 leading-snug">{sub}</p>
          </Panel>
        ))}
      </div>

      {/* API Status Panel */}
      <Panel flush className="p-3">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          {/* Title + status dot */}
          <div className="flex items-center gap-1.5 shrink-0">
            <span className="text-[10px] font-semibold uppercase tracking-widest text-lm-muted">
              API Status
            </span>
            <span className={clsx("inline-block w-1.5 h-1.5 rounded-full", statusInfo.dot)} />
            <span className={clsx("text-[10px] font-medium", statusInfo.txt)}>
              {statusInfo.text}
            </span>
          </div>

          <div className="h-3 w-px bg-lm-border hidden sm:block" />

          {/* Key/value pairs */}
          {[
            { k: "Symbol",      v: payload?.symbol      ?? symbol },
            { k: "Exchange",    v: payload?.exchange     ?? exchangeToApiSlug(exchange) },
            { k: "Timeframe",   v: payload?.timeframe    ?? timeframe },
            { k: "Cells",       v: payload ? String(payload.meta.cellCount)  : "—" },
            { k: "Walls",       v: payload ? String(payload.meta.wallCount)  : "—" },
            {
              k: "Generated",
              v: payload
                ? new Date(payload.meta.generatedAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })
                : "—",
            },
            { k: "Demo",        v: payload ? (payload.meta.isDemo ? "Yes" : "No") : "—" },
            // Requested source (toggle) vs what the route actually resolved to
            // after the live → fixture → mock fallback chain.
            { k: "Requested",   v: dataSource },
            { k: "Resolved",    v: payload?.meta.resolvedSource ?? payload?.meta.source ?? payload?.meta.dataSource ?? "—" },
            { k: "Stale",       v: payload ? (resolvedStatus.stale ? "Yes" : "No") : "—" },
            { k: "Auto",        v: autoRefresh ? "On (2s)" : "Off" },
            {
              k: "Live Upd",
              v: payload?.meta.liveUpdatedAt
                ? new Date(payload.meta.liveUpdatedAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })
                : "—",
            },
            {
              k: "Fetched",
              v: lastFetchedAt
                ? new Date(lastFetchedAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })
                : "—",
            },
          ].map(({ k, v }) => (
            <div key={k} className="flex items-center gap-1">
              <span className="text-[9px] uppercase tracking-wide text-lm-muted">{k}</span>
              <span className="num text-[10px] text-lm-text font-medium">{v}</span>
            </div>
          ))}

          {/* Fallback notice — requested source wasn't available, served a
              lower-tier source. Last good payload (if any) stays on screen. */}
          {fixtureFallback && payload && (
            <>
              <div className="h-3 w-px bg-lm-border hidden sm:block" />
              <span className="flex items-center gap-1 text-[10px] text-amber-400">
                <AlertCircle className="h-3 w-3 shrink-0" />
                Fallback → {resolvedStatus.label}
              </span>
            </>
          )}

          {/* Error detail — chart keeps the last good payload visible. */}
          {apiError && (
            <>
              <div className="h-3 w-px bg-lm-border hidden sm:block" />
              <span className="flex items-center gap-1 text-[10px] text-red-400">
                <AlertCircle className="h-3 w-3 shrink-0" />
                {apiError}
              </span>
            </>
          )}
        </div>
      </Panel>

      {/* LM60B: Data Status Panel */}
      <DataStatusPanel dataStatus={payload?.dataStatus ?? null} dataSource={dataSource} />

    </PageTransition>
  );
}
