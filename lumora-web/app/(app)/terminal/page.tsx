"use client";

import { useState, useEffect } from "react";
import { Panel } from "@/components/ui/Panel";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { PageTransition } from "@/components/ui/PageTransition";
import { Skeleton } from "@/components/ui/Skeleton";
import { IntelligenceChartPanel } from "@/components/charts/IntelligenceChartPanel";
import { mockOrderbook } from "@/lib/mock-data";
import { clsx } from "clsx";
import { ChevronDown, Info, RefreshCw, AlertCircle } from "lucide-react";
import type { HeatmapApiPayload } from "@/lib/heatmap-types";
import {
  heatmapCurrentPrice,
  heatmapLastPricePoint,
  heatmapStrongestWall,
  heatmapIntensitySummary,
  heatmapResolvedStatus,
} from "@/lib/heatmap-types";

const SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "HYPEUSDT"];
const TIMEFRAMES = ["Now", "5m", "1h"] as const;
type Timeframe = (typeof TIMEFRAMES)[number];

type LiveVariant = "live" | "stale" | "error" | "neutral";

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

  // ── Live heatmap snapshot (shared /api/heatmap live source) ─────────────────
  const [payload, setPayload] = useState<HeatmapApiPayload | null>(null);
  const [apiError, setApiError] = useState<string | null>(null);
  const [lastFetchedAt, setLastFetchedAt] = useState<string | null>(null);

  const apiTf = apiTimeframe(timeframe);

  // Auto-refresh every 2s with AbortController to prevent race conditions
  // when the user switches symbol/timeframe mid-flight. Visibility restore
  // triggers an immediate fetch so returning to the tab shows fresh data.
  useEffect(() => {
    const controller = new AbortController();

    const fetchLive = async () => {
      try {
        const res = await fetch(
          `/api/heatmap?source=live&symbol=${symbol}&exchange=binance_spot&timeframe=${apiTf}&_ts=${Date.now()}`,
          { cache: "no-store", signal: controller.signal },
        );
        if (controller.signal.aborted) return;
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          setApiError((body as { message?: string }).message ?? `API error ${res.status}`);
          return;
        }
        const data: HeatmapApiPayload = await res.json();
        if (controller.signal.aborted) return;
        setPayload(data);
        setApiError(null);
        setLastFetchedAt(new Date().toISOString());
      } catch (err) {
        if (controller.signal.aborted) return;
        setApiError(err instanceof Error ? err.message : "Network error");
      }
    };

    fetchLive();
    const id = setInterval(fetchLive, 2000);
    const onVisible = () => {
      if (document.visibilityState === "visible") fetchLive();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      controller.abort();
      clearInterval(id);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [symbol, apiTf]);

  const livePrice = payload ? heatmapCurrentPrice(payload) : null;
  const lastPoint = payload ? heatmapLastPricePoint(payload) : null;
  const intensity = payload ? heatmapIntensitySummary(payload) : null;
  const strongestWall = payload ? heatmapStrongestWall(payload) : null;
  // Status from the route's resolvedSource (live → fixture → mock).
  const resolvedStatus = heatmapResolvedStatus(payload);
  const liveStatus: { label: string; variant: LiveVariant } =
    apiError && !payload
      ? { label: "Error", variant: "error" }
      : !payload
        ? { label: "—", variant: "neutral" }
        : {
            label: resolvedStatus.label,
            variant:
              resolvedStatus.variant === "green" ? "live" :
              resolvedStatus.variant === "red"   ? "error" :
              resolvedStatus.variant === "muted" ? "neutral" : "stale",
          };

  // Depth / dominance derived purely from the live payload (no mock numbers).
  const bidWall = payload ? heatmapStrongestWall(payload, "bid") : null;
  const askWall = payload ? heatmapStrongestWall(payload, "ask") : null;
  const spread =
    lastPoint?.bestBid != null && lastPoint?.bestAsk != null
      ? lastPoint.bestAsk - lastPoint.bestBid
      : null;
  const bidPctLive = intensity ? intensity.bidPct : null;
  const askPctLive = bidPctLive != null ? 100 - bidPctLive : null;
  const pressureText = ob.pressureSummary[timeframe];

  return (
    <PageTransition className="space-y-4">
      {/* Header + controls */}
      <div className="flex flex-wrap items-end gap-3">
        <div className="mr-2">
          <h1 className="text-xl font-semibold text-lm-text">Pro Terminal</h1>
          <p className="text-[11px] text-lm-muted mt-0.5">
            Live depth via /api/heatmap (live → fixture → mock)
          </p>
        </div>

        <div className="flex items-center gap-2 ml-auto">
          {/* Symbol */}
          <div className="relative">
            <select
              className="appearance-none bg-lm-bg border border-lm-border text-lm-text text-[12px] rounded-md px-2.5 py-1.5 pr-7 focus:outline-none focus:border-lm-purple num cursor-pointer"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
            >
              {SYMBOLS.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
            <ChevronDown className="absolute right-1.5 top-2 h-3 w-3 text-lm-muted pointer-events-none" />
          </div>

          {/* Timeframe segment */}
          <div className="flex rounded-md border border-lm-border overflow-hidden">
            {TIMEFRAMES.map((tf) => (
              <button
                key={tf}
                onClick={() => setTimeframe(tf)}
                className={clsx(
                  "lm-segment-btn px-2.5 py-1.5 text-[12px] font-medium",
                  timeframe === tf ? "lm-segment-active" : "text-lm-muted bg-lm-surface",
                )}
              >
                {tf}
              </button>
            ))}
          </div>

          <StatusBadge variant={liveStatus.variant} dot={liveStatus.variant === "live"}>
            {liveStatus.label}
          </StatusBadge>
          {payload && resolvedStatus.stale && (
            <StatusBadge variant="stale" size="sm">Stale</StatusBadge>
          )}
        </div>
      </div>

      {/* Top KPI strip — primary operator read */}
      <Panel flush className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 divide-x divide-lm-border/60">
        <div className="px-4 py-2.5">
          <p className="text-[10px] uppercase tracking-widest text-lm-muted">Last</p>
          <p className="lm-price text-2xl text-lm-cyan mt-0.5 leading-none">
            {livePrice !== null
              ? `$${livePrice.toLocaleString(undefined, { maximumFractionDigits: 2 })}`
              : "—"}
          </p>
        </div>
        <div className="px-4 py-2.5">
          <p className="text-[10px] uppercase tracking-widest text-lm-muted">Best Bid</p>
          <p className="lm-price text-lg text-emerald-400 mt-0.5 leading-none">
            {lastPoint?.bestBid != null ? lastPoint.bestBid.toLocaleString() : "—"}
          </p>
        </div>
        <div className="px-4 py-2.5">
          <p className="text-[10px] uppercase tracking-widest text-lm-muted">Best Ask</p>
          <p className="lm-price text-lg text-red-400 mt-0.5 leading-none">
            {lastPoint?.bestAsk != null ? lastPoint.bestAsk.toLocaleString() : "—"}
          </p>
        </div>
        <div className="px-4 py-2.5">
          <p className="text-[10px] uppercase tracking-widest text-lm-muted">Spread</p>
          <p className="lm-price text-lg text-lm-text mt-0.5 leading-none">
            {spread != null ? spread.toLocaleString(undefined, { maximumFractionDigits: 2 }) : "—"}
          </p>
        </div>
        <div className="px-4 py-2.5">
          <p className="text-[10px] uppercase tracking-widest text-lm-muted">Walls</p>
          <p className="lm-price text-lg text-lm-text mt-0.5 leading-none">
            {payload ? payload.meta.wallCount : "—"}
            {strongestWall && (
              <span className="text-[10px] text-lm-muted ml-1.5 font-normal">
                top ${strongestWall.price_bucket.toLocaleString()}
              </span>
            )}
          </p>
        </div>
        <div className="px-4 py-2.5">
          <p className="text-[10px] uppercase tracking-widest text-lm-muted">Live · Fetched</p>
          <p className="num text-[11px] text-lm-text-dim mt-1 leading-none">
            {fmtTime(payload?.meta.liveUpdatedAt)}
          </p>
          <p className="num text-[10px] text-lm-muted mt-0.5 leading-none">
            {fmtTime(lastFetchedAt)}
          </p>
        </div>
      </Panel>

      {/* Pressure context banner */}
      <Panel flush className="px-3 py-2 flex items-start gap-2.5">
        <Info className="h-3.5 w-3.5 text-lm-cyan shrink-0 mt-0.5" />
        <p className="text-[12px] text-lm-text-dim leading-snug">
          <span className="text-lm-cyan font-medium uppercase tracking-wide text-[11px] mr-1.5">
            {timeframe}
          </span>
          {pressureText}
        </p>
      </Panel>

      {/* LM68C: Unified Intelligence Chart — live Binance candles (public
          REST + WS, demo fallback) with demo overlays until LM68D. */}
      <IntelligenceChartPanel height={420} />

      {/* API error banner — only when no payload to display */}
      {apiError && !payload && (
        <div className="flex items-center gap-2 px-3 py-2 rounded-lg border border-red-500/30 bg-red-500/10 text-red-300 text-[11px]">
          <AlertCircle className="h-3.5 w-3.5 shrink-0" />
          <span>{apiError}</span>
        </div>
      )}

      {/* Two-column: Order flow dominance | Walls list */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 items-start">

        {/* Order Flow Dominance */}
        <Panel flush className="p-3">
          <p className="text-[11px] font-semibold uppercase tracking-widest text-lm-muted mb-3">
            Order Flow Dominance
          </p>
          {!payload ? (
            <div className="space-y-2">
              <Skeleton variant="line" height="h-2" />
              <Skeleton variant="line" height="h-14" />
              <div className="grid grid-cols-2 gap-2">
                <Skeleton variant="line" height="h-10" />
                <Skeleton variant="line" height="h-10" />
              </div>
              {apiError && (
                <p className="text-[10px] text-red-400/80 truncate">{apiError}</p>
              )}
            </div>
          ) : (
            <>
              {/* Pressure bar */}
              <div className="flex justify-between text-[10px] text-lm-muted mb-1 num uppercase tracking-wide">
                <span className="text-emerald-400">{bidPctLive ?? "—"}% Bids</span>
                <span className="text-red-400">{askPctLive ?? "—"}% Asks</span>
              </div>
              <div className="h-2 rounded-full overflow-hidden flex bg-lm-surface-muted border border-lm-border">
                <div className="bg-emerald-500/80 transition-all duration-300" style={{ width: `${bidPctLive ?? 50}%` }} />
                <div className="bg-red-500/80 flex-1" />
              </div>

              {/* Best bid / spread / best ask grid */}
              <div className="mt-3 grid grid-cols-3 divide-x divide-lm-border/60 border border-lm-border/60 rounded-md overflow-hidden">
                <div className="px-3 py-2">
                  <p className="text-[10px] text-lm-muted uppercase tracking-wide">Best Bid</p>
                  <p className="lm-price text-[13px] text-emerald-400 mt-0.5 leading-none">
                    {lastPoint?.bestBid != null ? lastPoint.bestBid.toLocaleString() : "—"}
                  </p>
                </div>
                <div className="px-3 py-2">
                  <p className="text-[10px] text-lm-muted uppercase tracking-wide">Spread</p>
                  <p className="lm-price text-[13px] text-lm-text mt-0.5 leading-none">
                    {spread != null ? spread.toLocaleString(undefined, { maximumFractionDigits: 2 }) : "—"}
                  </p>
                </div>
                <div className="px-3 py-2">
                  <p className="text-[10px] text-lm-muted uppercase tracking-wide">Best Ask</p>
                  <p className="lm-price text-[13px] text-red-400 mt-0.5 leading-none">
                    {lastPoint?.bestAsk != null ? lastPoint.bestAsk.toLocaleString() : "—"}
                  </p>
                </div>
              </div>

              {/* Dominance verdict */}
              <StatusBadge
                variant={(bidPctLive ?? 50) >= 50 ? "bid" : "ask"}
                className="mt-3 w-full justify-center"
              >
                {(bidPctLive ?? 50) >= 50 ? "BID DOMINANT" : "ASK DOMINANT"}
              </StatusBadge>

              {/* Strongest bid/ask */}
              <div className="mt-3 grid grid-cols-2 gap-2">
                <div className="lm-rail-bid relative pl-2.5">
                  <p className="text-[10px] text-lm-muted uppercase tracking-wide">Strongest Bid</p>
                  <p className="num text-[12px] text-lm-text mt-0.5">
                    {bidWall ? `$${bidWall.price_bucket.toLocaleString()}` : "—"}
                  </p>
                  <p className="num text-[10px] text-lm-muted">
                    {bidWall ? `$${(bidWall.total_usd / 1_000_000).toFixed(2)}M` : ""}
                  </p>
                </div>
                <div className="lm-rail-ask relative pl-2.5">
                  <p className="text-[10px] text-lm-muted uppercase tracking-wide">Strongest Ask</p>
                  <p className="num text-[12px] text-lm-text mt-0.5">
                    {askWall ? `$${askWall.price_bucket.toLocaleString()}` : "—"}
                  </p>
                  <p className="num text-[10px] text-lm-muted">
                    {askWall ? `$${(askWall.total_usd / 1_000_000).toFixed(2)}M` : ""}
                  </p>
                </div>
              </div>
            </>
          )}
        </Panel>

        {/* Walls list */}
        <Panel flush className="overflow-hidden">
          <div className="px-3 py-2 border-b border-lm-border flex items-center justify-between">
            <span className="text-[11px] font-semibold uppercase tracking-widest text-lm-muted flex items-center gap-1.5">
              <RefreshCw className={clsx("h-3 w-3 text-lm-cyan", payload && "animate-spin")} />
              Liquidity Walls
            </span>
            <span className="num text-[10px] text-lm-muted">
              {payload ? `${payload.meta.wallCount} total` : "—"}
            </span>
          </div>
          {!payload ? (
            <div className="px-3 py-3 space-y-2">
              <Skeleton variant="line" />
              <Skeleton variant="line" width="w-3/4" />
              <Skeleton variant="line" width="w-2/3" />
              {apiError && (
                <p className="text-[10px] text-red-400/80 truncate">{apiError}</p>
              )}
            </div>
          ) : payload.walls.length === 0 ? (
            <div className="px-3 py-3 text-[11px] text-lm-muted">No walls detected in current window.</div>
          ) : (
            <div className="divide-y divide-lm-border/60 max-h-72 overflow-y-auto">
              {[...payload.walls]
                .sort((a, b) => b.total_usd - a.total_usd)
                .slice(0, 8)
                .map((w) => {
                  const isAsk = w.side === "ask";
                  return (
                    <div
                      key={`${w.price_bucket}-${w.side}`}
                      className={clsx(
                        "lm-row relative px-3 py-1.5 grid grid-cols-[36px_1fr_auto_44px] items-center gap-3",
                        isAsk ? "lm-rail-ask pl-4" : w.side === "bid" ? "lm-rail-bid pl-4" : "",
                      )}
                    >
                      <StatusBadge
                        variant={isAsk ? "ask" : w.side === "bid" ? "bid" : "warning"}
                        size="sm"
                        className="w-8 justify-center"
                      >
                        {w.side.toUpperCase()}
                      </StatusBadge>
                      <span className="num text-[12px] text-lm-text">${w.price_bucket.toLocaleString()}</span>
                      <span className="num text-[11px] text-lm-text-dim">
                        ${(w.total_usd / 1_000_000).toFixed(2)}M
                      </span>
                      <span className="num text-[11px] text-lm-muted text-right">
                        {Math.round(w.intensity)}%
                      </span>
                    </div>
                  );
                })}
            </div>
          )}
        </Panel>
      </div>
    </PageTransition>
  );
}
