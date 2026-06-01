"use client";

import { useState, useEffect, useCallback } from "react";
import { GlassCard } from "@/components/ui/GlassCard";
import { Badge } from "@/components/ui/Badge";
import { clsx } from "clsx";
import { RefreshCw, ChevronDown, AlertCircle } from "lucide-react";
import type { HeatmapApiPayload } from "@/lib/heatmap-types";
import { HeatmapCanvas } from "@/components/liquidity/HeatmapCanvas";
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

const SYMBOLS    = MARKET_SOURCES.map(m => m.symbol);
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
            ? <span className="text-[8px] text-lumora-muted leading-none">{l}</span>
            : <span className="text-[8px] leading-none opacity-0">·</span>
          }
        </div>
      ))}
    </div>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────────
export default function LiquidityMapPage() {
  const [symbol,    setSymbol]    = useState("BTCUSDT");
  const [exchange,  setExchange]  = useState("Binance Spot");
  const [timeframe, setTimeframe] = useState<string>("15m");
  const [dataSource, setDataSource] = useState<"mock" | "fixture">("mock");
  const [autoRefresh, setAutoRefresh] = useState(true);

  const [payload,  setPayload]  = useState<HeatmapApiPayload | null>(null);
  const [loading,  setLoading]  = useState(false);
  const [apiError, setApiError] = useState<string | null>(null);
  const [lastFetchedAt, setLastFetchedAt] = useState<string | null>(null);

  // `silent` skips the loading overlay so the 2s auto-refresh poll does not
  // flicker the chart. On failure we keep the previous payload and surface the
  // error — the next poll can recover on its own.
  const fetchPayload = useCallback(async (opts?: { silent?: boolean }) => {
    const silent = opts?.silent ?? false;
    if (!silent) setLoading(true);
    try {
      const tf  = timeframe.toLowerCase();
      const exSlug = exchangeToApiSlug(exchange);
      const params = new URLSearchParams({ symbol, exchange: exSlug, timeframe: tf });
      // Fixture mode opts into locally exported payloads; the API falls back to
      // mock automatically when no fixture file exists.
      if (dataSource === "fixture") params.set("source", "fixture");
      const res = await fetch(`/api/heatmap?${params.toString()}`, { cache: "no-store" });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        setApiError((body as { message?: string }).message ?? `API error ${res.status}`);
        return;
      }
      const data: HeatmapApiPayload = await res.json();
      setPayload(data);
      setApiError(null);
      setLastFetchedAt(new Date().toISOString());
    } catch (err) {
      setApiError(err instanceof Error ? err.message : "Network error");
    } finally {
      if (!silent) setLoading(false);
    }
  }, [symbol, exchange, timeframe, dataSource]);

  // Initial load + reload whenever symbol/exchange/timeframe/source changes.
  useEffect(() => { fetchPayload(); }, [fetchPayload]);

  // Auto-refresh: poll every 2s while in fixture mode with auto-refresh on.
  // The interval resets (cleanup runs) when symbol/timeframe/source change, on
  // unmount, or when the toggle flips — so there are no leaked timers.
  useEffect(() => {
    if (dataSource !== "fixture" || !autoRefresh) return;
    const id = setInterval(() => { fetchPayload({ silent: true }); }, 2000);
    return () => clearInterval(id);
  }, [dataSource, autoRefresh, fetchPayload]);

  // Derive display values — fall back to static defaults when payload not loaded yet
  const isDemo        = payload?.meta.isDemo ?? true;
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
  const statusVariant: "green" | "yellow" | "purple" =
    marketStatus === "supported" ? "green" : marketStatus === "demo" ? "purple" : "yellow";

  // Key zones — use payload walls if available, otherwise static fallback
  const apiWalls = payload?.walls ?? [];
  const showApiWalls = apiWalls.length > 0;

  return (
    <div className="space-y-4 animate-[fadeIn_0.4s_ease-out]">

      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-lumora-text">Liquidity Map</h1>
          <p className="text-sm text-lumora-muted mt-0.5">
            Spot orderbook depth over time{isDemo ? " — demo data" : ""}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant={statusVariant}>{statusLabel}</Badge>
          {isDemo && <Badge variant="yellow">Demo Data</Badge>}
        </div>
      </div>

      {/* Controls */}
      <GlassCard className="p-2.5 flex flex-wrap items-center gap-2">
        {/* Symbol */}
        <div className="relative">
          <select value={symbol} onChange={e => setSymbol(e.target.value)}
            className="appearance-none bg-lumora-bg border border-lumora-border text-lumora-text text-xs rounded-md px-2.5 py-1.5 pr-6 focus:outline-none focus:border-lumora-purple num cursor-pointer">
            {SYMBOLS.map(s => (
              <option key={s} value={s}>
                {getMarketSource(s)?.displayName ?? s}
              </option>
            ))}
          </select>
          <ChevronDown className="absolute right-1.5 top-2 h-3 w-3 text-lumora-muted pointer-events-none" />
        </div>
        {/* Exchange */}
        <div className="relative">
          <select value={exchange} onChange={e => setExchange(e.target.value)}
            className="appearance-none bg-lumora-bg border border-lumora-border text-lumora-text text-xs rounded-md px-2.5 py-1.5 pr-6 focus:outline-none focus:border-lumora-purple cursor-pointer">
            {EXCHANGES.map(ex => <option key={ex} value={ex}>{ex}</option>)}
          </select>
          <ChevronDown className="absolute right-1.5 top-2 h-3 w-3 text-lumora-muted pointer-events-none" />
        </div>
        <div className="h-4 w-px bg-lumora-border hidden sm:block" />
        {/* Timeframes */}
        <div className="flex rounded-md border border-lumora-border overflow-hidden">
          {TIMEFRAMES.map(tf => (
            <button key={tf} onClick={() => setTimeframe(tf)}
              className={clsx("px-2.5 py-1.5 text-xs font-medium transition-colors",
                timeframe === tf
                  ? "bg-lumora-purple text-white"
                  : "text-lumora-muted hover:text-lumora-text bg-lumora-card")}>
              {tf}
            </button>
          ))}
        </div>
        <div className="h-4 w-px bg-lumora-border hidden sm:block" />
        {/* Data source toggle — Mock vs locally exported Fixture */}
        <div className="flex rounded-md border border-lumora-border overflow-hidden" title="Heatmap data source">
          {(["mock", "fixture"] as const).map(src => (
            <button key={src} onClick={() => setDataSource(src)}
              className={clsx("px-2.5 py-1.5 text-xs font-medium capitalize transition-colors",
                dataSource === src
                  ? "bg-lumora-purple text-white"
                  : "text-lumora-muted hover:text-lumora-text bg-lumora-card")}>
              {src}
            </button>
          ))}
        </div>
        {/* Auto-refresh toggle — drives the 2s fixture poll */}
        <button
          onClick={() => setAutoRefresh(v => !v)}
          title="Auto refresh (2s) in fixture mode"
          className={clsx(
            "px-2.5 py-1.5 text-xs font-medium rounded-md border transition-colors",
            autoRefresh
              ? "border-lumora-purple bg-lumora-purple/15 text-lumora-text"
              : "border-lumora-border bg-lumora-card text-lumora-muted hover:text-lumora-text"
          )}
        >
          Auto {autoRefresh ? "On" : "Off"}
        </button>
        {/* Refresh */}
        <button onClick={() => fetchPayload()} title="Refresh"
          disabled={loading}
          className="p-1.5 rounded-md border border-lumora-border bg-lumora-card text-lumora-muted hover:text-lumora-text transition-colors disabled:opacity-50">
          <RefreshCw className={clsx("h-3.5 w-3.5", loading && "animate-spin")} />
        </button>
        {/* Legend */}
        <div className="ml-auto flex items-center gap-3">
          <HeatLegend />
          <div className="h-4 w-px bg-lumora-border hidden md:block" />
          <span className="flex items-center gap-1.5 text-[10px] text-lumora-muted">
            <span className="inline-block w-5 h-[1.5px] bg-white/60 rounded" />Price
          </span>
          <span className="flex items-center gap-1.5 text-[10px] text-lumora-cyan">
            <span className="inline-block w-2 h-2 rounded-full bg-lumora-cyan shadow-[0_0_6px_rgba(34,211,238,0.9)]" />Now
          </span>
        </div>
      </GlassCard>

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
              ? "border border-lumora-border bg-lumora-card text-lumora-muted"
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
        <GlassCard className="overflow-hidden p-0">
          <div className="px-3 py-1.5 border-b border-lumora-border flex items-center justify-between gap-3">
            <span className="text-[11px] text-lumora-muted uppercase tracking-wide font-medium">
              Liquidity Heatmap
            </span>
            <span className="text-[10px] text-lumora-muted num">
              {payload
                ? `${payload.timeBuckets.length} frames · ${payload.meta.cellCount} cells · ${payload.meta.wallCount} walls`
                : "—"}
            </span>
          </div>

          <div className="relative" style={{ height: CHART_H, background: "#05030f" }}>
            {/* Loading overlay — silent auto-refresh polls do not trigger this */}
            {loading && (
              <div className="absolute inset-0 z-40 flex items-center justify-center bg-black/30 backdrop-blur-[1px]">
                <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-lumora-card/80 border border-lumora-border text-lumora-muted text-xs">
                  <RefreshCw className="h-3 w-3 animate-spin" />
                  Loading…
                </div>
              </div>
            )}

            {/* Error card inside the chart area when there is nothing to show */}
            {apiError && !payload && (
              <div className="absolute inset-0 z-30 flex items-center justify-center p-4">
                <div className="flex items-center gap-2 px-3 py-2 rounded-lg border border-red-500/30 bg-red-500/10 text-red-300 text-xs">
                  <AlertCircle className="h-3.5 w-3.5 shrink-0" />
                  <span>{apiError}</span>
                </div>
              </div>
            )}

            {payload ? (
              <HeatmapCanvas payload={payload} height={CHART_H} showDebug />
            ) : (
              !apiError && (
                <div className="absolute inset-0 flex items-center justify-center text-xs text-lumora-muted">
                  {loading ? "Loading heatmap…" : "Waiting for data…"}
                </div>
              )
            )}
          </div>
        </GlassCard>

        {/* Depth rail (compact) */}
        <GlassCard className="overflow-hidden p-0">
          <div className="px-2.5 py-1.5 border-b border-lumora-border flex items-center justify-between">
            <span className="text-[10px] text-lumora-muted uppercase tracking-wide font-medium">Depth</span>
            <span className="text-[10px] text-lumora-cyan font-medium">Now</span>
          </div>
          <div className="px-1.5 py-1.5 overflow-y-auto" style={{ maxHeight: CHART_H - 60 }}>
            <DepthProfile />
          </div>
          <div className="px-2.5 py-1.5 border-t border-lumora-border flex flex-col gap-1">
            <div className="flex items-center gap-1.5 text-[10px] text-lumora-muted">
              <div className="w-3.5 h-2 rounded-sm shrink-0" style={{ background: iColor(85) }} />Asks
            </div>
            <div className="flex items-center gap-1.5 text-[10px] text-lumora-muted">
              <div className="w-3.5 h-2 rounded-sm shrink-0" style={{ background: iColor(75) }} />Bids
            </div>
          </div>
        </GlassCard>

      </div>

      {/* Key zone cards — API walls when available, static fallback otherwise */}
      <div>
        <h2 className="text-xs font-semibold uppercase tracking-widest text-lumora-muted mb-2">Key Zones</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {showApiWalls
            ? apiWalls.slice(0, 4).map(w => {
                const isAsk = w.side === "ask";
                const badge = w.intensity >= 85 ? "WALL" : isAsk ? "RES" : "SUP";
                return (
                  <GlassCard key={`${w.price_bucket}-${w.side}`} className="p-3 flex items-start gap-2.5">
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
                        <p className="num text-sm font-semibold text-lumora-text">
                          ${w.price_bucket.toLocaleString()}
                        </p>
                        <Badge variant={isAsk ? "red" : "green"} className="text-[9px] px-1 py-0">
                          {badge}
                        </Badge>
                        <span className="num text-[10px] text-lumora-muted ml-auto">
                          {Math.round(w.intensity)}%
                        </span>
                      </div>
                      <p className="text-xs font-medium text-lumora-text-dim">{w.label}</p>
                      <p className="text-[11px] text-lumora-muted mt-0.5 leading-snug">
                        ${(w.total_usd / 1_000_000).toFixed(2)}M liquidity
                      </p>
                    </div>
                  </GlassCard>
                );
              })
            : ZONES.slice(0, 4).map(z => (
                <GlassCard key={z.price} className="p-3 flex items-start gap-2.5">
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
                      <p className="num text-sm font-semibold text-lumora-text">${z.price.toLocaleString()}</p>
                      <Badge variant={z.side === "ASK" ? "red" : "green"} className="text-[9px] px-1 py-0">
                        {z.badge}
                      </Badge>
                      <span className="num text-[10px] text-lumora-muted ml-auto">{z.intensity}%</span>
                    </div>
                    <p className="text-xs font-medium text-lumora-text-dim">{z.label}</p>
                    <p className="text-[11px] text-lumora-muted mt-0.5 leading-snug">{z.desc}</p>
                  </div>
                </GlassCard>
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
          <GlassCard key={label} className="p-3">
            <p className="text-[11px] text-lumora-muted uppercase tracking-wide mb-1.5">{label}</p>
            <p className={clsx("num text-sm font-semibold", color)}>{value}</p>
            <p className="text-[11px] text-lumora-muted mt-1 leading-snug">{sub}</p>
          </GlassCard>
        ))}
      </div>

      {/* API Status Panel */}
      <GlassCard className="p-3">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          {/* Title + status dot */}
          <div className="flex items-center gap-1.5 shrink-0">
            <span className="text-[10px] font-semibold uppercase tracking-widest text-lumora-muted">
              API Status
            </span>
            <span
              className={clsx(
                "inline-block w-1.5 h-1.5 rounded-full",
                loading   ? "bg-yellow-400 animate-pulse" :
                apiError  ? "bg-red-400" :
                payload   ? "bg-emerald-400" :
                            "bg-lumora-muted"
              )}
            />
            <span
              className={clsx(
                "text-[10px] font-medium",
                loading   ? "text-yellow-400" :
                apiError  ? "text-red-400" :
                payload   ? "text-emerald-400" :
                            "text-lumora-muted"
              )}
            >
              {loading ? "Loading" : apiError ? "Error" : payload ? "Connected" : "—"}
            </span>
          </div>

          <div className="h-3 w-px bg-lumora-border hidden sm:block" />

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
            // Requested data source (toggle) and what meta actually reports —
            // reveals a fixture→mock fallback when no fixture file exists.
            { k: "Source",      v: dataSource },
            { k: "Meta Src",    v: payload?.meta.source ?? payload?.meta.dataSource ?? "—" },
            { k: "Auto",        v: dataSource === "fixture" ? (autoRefresh ? "On (2s)" : "Off") : "—" },
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
              <span className="text-[9px] uppercase tracking-wide text-lumora-muted">{k}</span>
              <span className="num text-[10px] text-lumora-text font-medium">{v}</span>
            </div>
          ))}

          {/* Error detail */}
          {apiError && (
            <>
              <div className="h-3 w-px bg-lumora-border hidden sm:block" />
              <span className="flex items-center gap-1 text-[10px] text-red-400">
                <AlertCircle className="h-3 w-3 shrink-0" />
                {apiError}
              </span>
            </>
          )}
        </div>
      </GlassCard>

    </div>
  );
}
