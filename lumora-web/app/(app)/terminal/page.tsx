"use client";

import { useState, useEffect, useCallback } from "react";
import { GlassCard } from "@/components/ui/GlassCard";
import { Badge } from "@/components/ui/Badge";
import { mockOrderbook } from "@/lib/mock-data";
import { clsx } from "clsx";
import { ChevronDown, Info, RefreshCw, AlertCircle } from "lucide-react";
import type { HeatmapApiPayload } from "@/lib/heatmap-types";
import {
  heatmapCurrentPrice,
  heatmapLastPricePoint,
  heatmapStrongestWall,
  heatmapIntensitySummary,
  heatmapIsStale,
} from "@/lib/heatmap-types";

const SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "HYPEUSDT"];
const TIMEFRAMES = ["Now", "5m", "1h"] as const;
type Timeframe = (typeof TIMEFRAMES)[number];

/** Terminal timeframe label → /api/heatmap timeframe ("Now" maps to 5m). */
function apiTimeframe(tf: Timeframe): string {
  return tf === "Now" ? "5m" : tf;
}

function fmtTime(iso?: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? "—"
    : d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export default function TerminalPage() {
  const [symbol, setSymbol] = useState("BTCUSDT");
  const [timeframe, setTimeframe] = useState<Timeframe>("Now");
  const ob = mockOrderbook;

  // ── Live heatmap snapshot (shared /api/heatmap fixture source) ──────────────
  const [payload, setPayload] = useState<HeatmapApiPayload | null>(null);
  const [apiError, setApiError] = useState<string | null>(null);
  const [lastFetchedAt, setLastFetchedAt] = useState<string | null>(null);

  const apiTf = apiTimeframe(timeframe);
  const fetchLive = useCallback(async () => {
    try {
      const res = await fetch(
        `/api/heatmap?source=fixture&symbol=${symbol}&timeframe=${apiTf}`,
        { cache: "no-store" },
      );
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
    }
  }, [symbol, apiTf]);

  // Auto-refresh every 2s; interval resets on symbol/timeframe change and is
  // cleaned up on unmount (no leaked timers).
  useEffect(() => {
    fetchLive();
    const id = setInterval(fetchLive, 2000);
    return () => clearInterval(id);
  }, [fetchLive]);

  const livePrice = payload ? heatmapCurrentPrice(payload) : null;
  const lastPoint = payload ? heatmapLastPricePoint(payload) : null;
  const intensity = payload ? heatmapIntensitySummary(payload) : null;
  const strongestWall = payload ? heatmapStrongestWall(payload) : null;
  const liveSource = payload?.meta.source ?? payload?.meta.dataSource ?? null;
  const liveStale = payload ? heatmapIsStale(payload) : false;
  const liveStatus = apiError
    ? { label: "Error", variant: "red" as const }
    : !payload
      ? { label: "—", variant: "muted" as const }
      : liveStale
        ? { label: "Stale", variant: "yellow" as const }
        : liveSource === "fixture" || liveSource === "local_live_fixture"
          ? { label: "Live Fixture", variant: "green" as const }
          : { label: "Mock", variant: "muted" as const };

  const maxAskSize = Math.max(...ob.asks.map((a) => a.size));
  const maxBidSize = Math.max(...ob.bids.map((b) => b.size));
  const totalBidUsd = ob.bids.reduce((s, b) => s + b.usd, 0);
  const totalAskUsd = ob.asks.reduce((s, a) => s + a.usd, 0);
  const bidPct = Math.round((totalBidUsd / (totalBidUsd + totalAskUsd)) * 100);
  const pressureText = ob.pressureSummary[timeframe];

  return (
    <div className="space-y-4 animate-[fadeIn_0.4s_ease-out]">
      {/* Header + controls */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="mr-2">
          <h1 className="text-xl font-semibold text-lumora-text">Pro Terminal</h1>
          <p className="text-xs text-lumora-muted mt-0.5">Demo orderbook — live data coming soon</p>
        </div>

        <div className="relative">
          <select
            className="appearance-none bg-lumora-card border border-lumora-border text-lumora-text text-sm rounded-lg px-3 py-2 pr-8 focus:outline-none focus:border-lumora-purple num cursor-pointer"
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
          >
            {SYMBOLS.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <ChevronDown className="absolute right-2 top-2.5 h-4 w-4 text-lumora-muted pointer-events-none" />
        </div>

        <div className="flex rounded-lg border border-lumora-border overflow-hidden">
          {TIMEFRAMES.map((tf) => (
            <button
              key={tf}
              onClick={() => setTimeframe(tf)}
              className={clsx(
                "px-4 py-2 text-sm font-medium transition-colors",
                timeframe === tf
                  ? "bg-lumora-purple text-white"
                  : "text-lumora-muted hover:text-lumora-text bg-lumora-card"
              )}
            >
              {tf}
            </button>
          ))}
        </div>

        <div className="ml-auto flex items-center gap-2">
          <span className="h-1.5 w-1.5 rounded-full bg-yellow-400 animate-pulse inline-block" />
          <span className="text-xs text-yellow-400">Demo</span>
        </div>
      </div>

      {/* Pressure context banner */}
      <GlassCard className="px-4 py-2.5 flex items-start gap-2.5">
        <Info className="h-3.5 w-3.5 text-lumora-cyan shrink-0 mt-0.5" />
        <p className="text-xs text-lumora-text-dim leading-relaxed">
          <span className="text-lumora-cyan font-medium">{timeframe} context: </span>
          {pressureText}
        </p>
      </GlassCard>

      {/* Live heatmap snapshot — shared /api/heatmap fixture source, 2s refresh */}
      <GlassCard className="overflow-hidden p-0">
        <div className="px-4 py-2 border-b border-lumora-border flex items-center justify-between gap-3">
          <span className="text-xs font-semibold uppercase tracking-widest text-lumora-muted flex items-center gap-1.5">
            <RefreshCw className="h-3 w-3 text-lumora-cyan" /> Live Heatmap
          </span>
          <div className="flex items-center gap-2">
            <Badge variant={liveStatus.variant}>{liveStatus.label}</Badge>
            <span className="text-[10px] text-lumora-muted num">
              {symbol} · {apiTf}
            </span>
          </div>
        </div>

        {apiError && !payload ? (
          <div className="px-4 py-3 flex items-center gap-2 text-xs text-red-400">
            <AlertCircle className="h-3.5 w-3.5 shrink-0" />
            <span>{apiError}</span>
          </div>
        ) : !payload ? (
          <div className="px-4 py-3 text-xs text-lumora-muted">Loading live data…</div>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-x-4 gap-y-2 px-4 py-3">
            <div>
              <p className="text-[10px] text-lumora-muted uppercase tracking-wide">Current</p>
              <p className="num text-sm font-bold text-neon-cyan">
                {livePrice !== null
                  ? `$${livePrice.toLocaleString(undefined, { maximumFractionDigits: 2 })}`
                  : "—"}
              </p>
            </div>
            <div>
              <p className="text-[10px] text-lumora-muted uppercase tracking-wide">Best Bid</p>
              <p className="num text-sm font-semibold text-lumora-green">
                {lastPoint?.bestBid != null ? lastPoint.bestBid.toLocaleString() : "—"}
              </p>
            </div>
            <div>
              <p className="text-[10px] text-lumora-muted uppercase tracking-wide">Best Ask</p>
              <p className="num text-sm font-semibold text-lumora-red">
                {lastPoint?.bestAsk != null ? lastPoint.bestAsk.toLocaleString() : "—"}
              </p>
            </div>
            <div>
              <p className="text-[10px] text-lumora-muted uppercase tracking-wide">Bid/Ask Intens</p>
              <p className="num text-sm font-semibold text-lumora-text">
                {intensity ? `${intensity.bid}/${intensity.ask}` : "—"}
                <span className="text-[10px] text-lumora-muted ml-1">
                  {intensity ? `(${intensity.bidPct}% bid)` : ""}
                </span>
              </p>
            </div>
            <div>
              <p className="text-[10px] text-lumora-muted uppercase tracking-wide">Walls</p>
              <p className="num text-sm font-semibold text-lumora-text">
                {payload.meta.wallCount}
                {strongestWall && (
                  <span className="text-[10px] text-lumora-muted ml-1">
                    top ${strongestWall.price_bucket.toLocaleString()}
                  </span>
                )}
              </p>
            </div>
            <div>
              <p className="text-[10px] text-lumora-muted uppercase tracking-wide">Live / Fetched</p>
              <p className="num text-[11px] text-lumora-text-dim">
                {fmtTime(payload.meta.liveUpdatedAt)} · {fmtTime(lastFetchedAt)}
              </p>
            </div>
          </div>
        )}
      </GlassCard>

      {/* Orderbook — asks | mid | bids */}
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_156px_1fr] gap-3 items-start">

        {/* Asks */}
        <GlassCard className="overflow-hidden">
          <div className="px-4 py-2.5 border-b border-lumora-border flex items-center justify-between bg-red-500/5">
            <span className="text-sm font-semibold text-lumora-red">Asks</span>
            <span className="num text-xs text-lumora-muted">${(totalAskUsd / 1000).toFixed(1)}K depth</span>
          </div>
          <div className="text-xs num">
            <div className="grid grid-cols-3 px-4 py-1.5 text-lumora-muted text-[10px] uppercase tracking-wider border-b border-lumora-border/40">
              <span>Price</span>
              <span className="text-right">BTC</span>
              <span className="text-right">USD</span>
            </div>
            <div className="overflow-y-auto max-h-64">
              {[...ob.asks].reverse().map((row, i) => (
                <div key={i} className="relative px-4 py-1.5 grid grid-cols-3 hover:bg-lumora-surface/50 transition-colors">
                  <div
                    className="absolute inset-y-0 right-0 bg-red-500/10"
                    style={{ width: `${(row.size / maxAskSize) * 100}%` }}
                  />
                  <span className="relative text-lumora-red">{row.price.toLocaleString()}</span>
                  <span className="relative text-right text-lumora-text">{row.size.toFixed(2)}</span>
                  <span className="relative text-right text-lumora-muted">{(row.usd / 1000).toFixed(1)}K</span>
                </div>
              ))}
            </div>
          </div>
        </GlassCard>

        {/* Mid column */}
        <div className="flex flex-col items-center gap-3 px-2 py-4 lg:py-6">
          <div className="text-center">
            <p className="text-[10px] text-lumora-muted uppercase tracking-widest mb-1">Mid Price</p>
            <p className="num text-xl font-bold text-neon-cyan">{ob.midPrice.toLocaleString()}</p>
            <p className="text-xs text-lumora-green mt-0.5">+0.32% (5m)</p>
          </div>

          <div className="w-full space-y-1">
            <div className="flex justify-between text-[10px] text-lumora-muted">
              <span>Bids {bidPct}%</span>
              <span>{100 - bidPct}% Asks</span>
            </div>
            <div className="h-2 rounded-full overflow-hidden flex">
              <div className="bg-green-500 transition-all" style={{ width: `${bidPct}%` }} />
              <div className="bg-red-500 flex-1" />
            </div>
          </div>

          <Badge variant={bidPct >= 50 ? "green" : "red"} className="text-center w-full justify-center">
            {bidPct >= 50 ? "Bid Dominant" : "Ask Dominant"}
          </Badge>

          <div className="text-center space-y-1">
            <p className="text-[10px] text-lumora-muted">Imbalance</p>
            <p className="num text-xs text-lumora-purple-bright font-semibold">
              {ob.imbalance > 0 ? "+" : ""}{ob.imbalance.toFixed(2)}
            </p>
          </div>

          <div className="text-center">
            <p className="text-[10px] text-lumora-muted">Spread</p>
            <p className="num text-xs text-lumora-text mt-0.5">{ob.spread} bps</p>
            <p className="num text-[10px] text-lumora-muted">{ob.spreadBps}</p>
          </div>
        </div>

        {/* Bids */}
        <GlassCard className="overflow-hidden">
          <div className="px-4 py-2.5 border-b border-lumora-border flex items-center justify-between bg-green-500/5">
            <span className="text-sm font-semibold text-lumora-green">Bids</span>
            <span className="num text-xs text-lumora-muted">${(totalBidUsd / 1000).toFixed(1)}K depth</span>
          </div>
          <div className="text-xs num">
            <div className="grid grid-cols-3 px-4 py-1.5 text-lumora-muted text-[10px] uppercase tracking-wider border-b border-lumora-border/40">
              <span>Price</span>
              <span className="text-right">BTC</span>
              <span className="text-right">USD</span>
            </div>
            <div className="overflow-y-auto max-h-64">
              {ob.bids.map((row, i) => (
                <div key={i} className="relative px-4 py-1.5 grid grid-cols-3 hover:bg-lumora-surface/50 transition-colors">
                  <div
                    className="absolute inset-y-0 left-0 bg-green-500/10"
                    style={{ width: `${(row.size / maxBidSize) * 100}%` }}
                  />
                  <span className="relative text-lumora-green">{row.price.toLocaleString()}</span>
                  <span className="relative text-right text-lumora-text">{row.size.toFixed(2)}</span>
                  <span className="relative text-right text-lumora-muted">{(row.usd / 1000).toFixed(1)}K</span>
                </div>
              ))}
            </div>
          </div>
        </GlassCard>
      </div>

      {/* Pressure Summary */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          { label: "Spread",           value: `${ob.spread} bps`,              sub: ob.spreadBps },
          { label: "Imbalance",        value: `+${ob.imbalance}`,              sub: "Bid-side advantage" },
          { label: "Largest Ask Wall", value: "$216K",                         sub: "@ 67,440" },
          { label: "Largest Bid Wall", value: "$276K",                         sub: "@ 67,400 — held 40m" },
        ].map(({ label, value, sub }) => (
          <GlassCard key={label} className="p-3">
            <p className="text-[11px] text-lumora-muted uppercase tracking-wide mb-1">{label}</p>
            <p className="num text-sm font-semibold text-lumora-text">{value}</p>
            <p className="num text-[11px] text-lumora-muted mt-0.5">{sub}</p>
          </GlassCard>
        ))}
      </div>
    </div>
  );
}
