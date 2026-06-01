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

  // Depth / dominance derived purely from the live payload (no mock numbers).
  const bidWall = payload ? heatmapStrongestWall(payload, "bid") : null;
  const askWall = payload ? heatmapStrongestWall(payload, "ask") : null;
  const spread =
    lastPoint?.bestBid != null && lastPoint?.bestAsk != null
      ? lastPoint.bestAsk - lastPoint.bestBid
      : null;
  const bidPctLive = intensity ? intensity.bidPct : null;
  const pressureText = ob.pressureSummary[timeframe];

  return (
    <div className="space-y-4 animate-[fadeIn_0.4s_ease-out]">
      {/* Header + controls */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="mr-2">
          <h1 className="text-xl font-semibold text-lumora-text">Pro Terminal</h1>
          <p className="text-xs text-lumora-muted mt-0.5">Live depth via local fixture · heatmap-derived</p>
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
          <Badge variant={liveStatus.variant}>{liveStatus.label}</Badge>
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

      {/* Order flow & walls — derived from the live payload (no mock depth) */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 items-start">

        {/* Dominance + spread */}
        <GlassCard className="p-4">
          <p className="text-[11px] text-lumora-muted uppercase tracking-widest mb-3">Order Flow Dominance</p>
          {!payload ? (
            <p className="text-xs text-lumora-muted">{apiError ?? "Loading live data…"}</p>
          ) : (
            <>
              <div className="flex justify-between text-[10px] text-lumora-muted mb-1">
                <span>Bids {bidPctLive ?? "—"}%</span>
                <span>{bidPctLive != null ? 100 - bidPctLive : "—"}% Asks</span>
              </div>
              <div className="h-2.5 rounded-full overflow-hidden flex bg-lumora-border">
                <div className="bg-green-500 transition-all" style={{ width: `${bidPctLive ?? 50}%` }} />
                <div className="bg-red-500 flex-1" />
              </div>

              <div className="mt-3 grid grid-cols-3 gap-3 text-center">
                <div>
                  <p className="text-[10px] text-lumora-muted uppercase tracking-wide">Best Bid</p>
                  <p className="num text-sm font-semibold text-lumora-green">
                    {lastPoint?.bestBid != null ? lastPoint.bestBid.toLocaleString() : "—"}
                  </p>
                </div>
                <div>
                  <p className="text-[10px] text-lumora-muted uppercase tracking-wide">Spread</p>
                  <p className="num text-sm font-semibold text-lumora-text">
                    {spread != null ? spread.toLocaleString(undefined, { maximumFractionDigits: 2 }) : "—"}
                  </p>
                </div>
                <div>
                  <p className="text-[10px] text-lumora-muted uppercase tracking-wide">Best Ask</p>
                  <p className="num text-sm font-semibold text-lumora-red">
                    {lastPoint?.bestAsk != null ? lastPoint.bestAsk.toLocaleString() : "—"}
                  </p>
                </div>
              </div>

              <Badge
                variant={(bidPctLive ?? 50) >= 50 ? "green" : "red"}
                className="mt-3 w-full justify-center"
              >
                {(bidPctLive ?? 50) >= 50 ? "Bid Dominant" : "Ask Dominant"}
              </Badge>

              <div className="mt-3 grid grid-cols-2 gap-3 text-center">
                <div>
                  <p className="text-[10px] text-lumora-muted uppercase tracking-wide">Strongest Bid</p>
                  <p className="num text-xs text-lumora-text">
                    {bidWall ? `$${bidWall.price_bucket.toLocaleString()}` : "—"}
                  </p>
                  <p className="num text-[10px] text-lumora-muted">
                    {bidWall ? `$${(bidWall.total_usd / 1_000_000).toFixed(2)}M` : ""}
                  </p>
                </div>
                <div>
                  <p className="text-[10px] text-lumora-muted uppercase tracking-wide">Strongest Ask</p>
                  <p className="num text-xs text-lumora-text">
                    {askWall ? `$${askWall.price_bucket.toLocaleString()}` : "—"}
                  </p>
                  <p className="num text-[10px] text-lumora-muted">
                    {askWall ? `$${(askWall.total_usd / 1_000_000).toFixed(2)}M` : ""}
                  </p>
                </div>
              </div>
            </>
          )}
        </GlassCard>

        {/* Walls list */}
        <GlassCard className="overflow-hidden p-0">
          <div className="px-4 py-2.5 border-b border-lumora-border flex items-center justify-between">
            <span className="text-[11px] text-lumora-muted uppercase tracking-widest">Liquidity Walls</span>
            <span className="num text-[10px] text-lumora-muted">
              {payload ? `${payload.meta.wallCount} walls` : "—"}
            </span>
          </div>
          {!payload ? (
            <div className="px-4 py-3 text-xs text-lumora-muted">{apiError ?? "Loading…"}</div>
          ) : payload.walls.length === 0 ? (
            <div className="px-4 py-3 text-xs text-lumora-muted">No walls detected in current window.</div>
          ) : (
            <div className="divide-y divide-lumora-border/40 max-h-64 overflow-y-auto">
              {[...payload.walls]
                .sort((a, b) => b.total_usd - a.total_usd)
                .slice(0, 8)
                .map((w) => (
                  <div
                    key={`${w.price_bucket}-${w.side}`}
                    className="px-4 py-2 flex items-center gap-2.5 hover:bg-lumora-surface/40 transition-colors"
                  >
                    <Badge
                      variant={w.side === "ask" ? "red" : w.side === "bid" ? "green" : "yellow"}
                      className="text-[9px] px-1 py-0 w-10 justify-center shrink-0"
                    >
                      {w.side.toUpperCase()}
                    </Badge>
                    <span className="num text-xs text-lumora-text">${w.price_bucket.toLocaleString()}</span>
                    <span className="num text-[11px] text-lumora-muted ml-auto">
                      ${(w.total_usd / 1_000_000).toFixed(2)}M
                    </span>
                    <span className="num text-[11px] text-lumora-muted w-10 text-right">
                      {Math.round(w.intensity)}%
                    </span>
                  </div>
                ))}
            </div>
          )}
        </GlassCard>
      </div>
    </div>
  );
}
