"use client";

import { useState, useEffect, useCallback } from "react";
import { Panel } from "@/components/ui/Panel";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { PageTransition } from "@/components/ui/PageTransition";
import { Skeleton } from "@/components/ui/Skeleton";
import { clsx } from "clsx";
import { mockSetups, mockWhaleAlerts } from "@/lib/mock-data";
import { TrendingUp, Zap, RefreshCw } from "lucide-react";
import type { HeatmapApiPayload } from "@/lib/heatmap-types";
import {
  heatmapCurrentPrice,
  heatmapStrongestWall,
  heatmapResolvedStatus,
} from "@/lib/heatmap-types";

const DASH_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"] as const;

// Active/primary market refreshes fast; the rest poll slowly in the background.
const ACTIVE_SYMBOL = "BTCUSDT";
const BACKGROUND_SYMBOLS = DASH_SYMBOLS.filter((s) => s !== ACTIVE_SYMBOL);
const ACTIVE_REFRESH_MS = 2000;
const BACKGROUND_REFRESH_MS = 9000;

interface MarketState {
  payload: HeatmapApiPayload | null;
  error: string | null;
  lastFetchedAt: string | null;
}

const EMPTY_MARKET: MarketState = { payload: null, error: null, lastFetchedAt: null };

// Status badge driven by the route's resolvedSource (live → fixture → mock).
type BadgeVariant = "live" | "stale" | "error" | "neutral";

function marketStatus(
  m: MarketState,
): { label: string; variant: BadgeVariant; isFallback: boolean; stale: boolean } {
  if (m.error && !m.payload) return { label: "Error", variant: "error", isFallback: false, stale: false };
  if (!m.payload) return { label: "—", variant: "neutral", isFallback: false, stale: false };
  const s = heatmapResolvedStatus(m.payload);
  const variant: BadgeVariant =
    s.variant === "green" ? "live" :
    s.variant === "red"   ? "error" :
    s.variant === "muted" ? "neutral" : "stale";
  return { label: s.label, variant, isFallback: s.isFallback, stale: s.stale };
}

function fmtTime(iso?: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? "—"
    : d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export default function DashboardPage() {
  const [markets, setMarkets] = useState<Record<string, MarketState>>({});
  const [lastFetchedAt, setLastFetchedAt] = useState<string | null>(null);

  // Fetch one market from the shared /api/heatmap live source. The route falls
  // back live → fixture → mock server-side and reports what it served via
  // meta.resolvedSource. On error the last good payload is kept.
  const fetchSymbol = useCallback(async (sym: string) => {
    try {
      const res = await fetch(
        `/api/heatmap?source=live&symbol=${sym}&exchange=binance_spot&timeframe=5m&_ts=${Date.now()}`,
        { cache: "no-store" },
      );
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        const message = (body as { message?: string }).message ?? `API error ${res.status}`;
        setMarkets((prev) => ({
          ...prev,
          [sym]: { ...(prev[sym] ?? EMPTY_MARKET), error: message },
        }));
        return;
      }
      const payload: HeatmapApiPayload = await res.json();
      const now = new Date().toISOString();
      setMarkets((prev) => ({
        ...prev,
        [sym]: { payload, error: null, lastFetchedAt: now },
      }));
      setLastFetchedAt(now);
    } catch (err) {
      setMarkets((prev) => ({
        ...prev,
        [sym]: {
          ...(prev[sym] ?? EMPTY_MARKET),
          error: err instanceof Error ? err.message : "Network error",
        },
      }));
    }
  }, []);

  // Tiered auto-refresh: the active market polls fast, background markets slow.
  // Both intervals (and the initial load) are cleaned up on unmount.
  // On visibility restore, an immediate fetch fires so the user never sees
  // stale numbers after switching back from another tab.
  useEffect(() => {
    DASH_SYMBOLS.forEach((sym) => { fetchSymbol(sym); });
    const activeId = setInterval(() => fetchSymbol(ACTIVE_SYMBOL), ACTIVE_REFRESH_MS);
    const backgroundId = setInterval(
      () => { BACKGROUND_SYMBOLS.forEach((sym) => fetchSymbol(sym)); },
      BACKGROUND_REFRESH_MS,
    );
    const onVisible = () => {
      if (document.visibilityState === "visible") {
        DASH_SYMBOLS.forEach((sym) => { fetchSymbol(sym); });
      }
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      clearInterval(activeId);
      clearInterval(backgroundId);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [fetchSymbol]);

  // Overall header status derived from the active (primary) market.
  const headerStatus = heatmapResolvedStatus(markets[ACTIVE_SYMBOL]?.payload ?? null);
  const headerDot =
    headerStatus.resolved === "live" ? "bg-green-400" :
    headerStatus.resolved == null ? "bg-lm-muted" : "bg-yellow-400";

  return (
    <PageTransition className="space-y-4">
      {/* Header */}
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-semibold text-lm-text leading-tight">Market Dashboard</h1>
          <p className="text-[11px] text-lm-muted mt-0.5">
            Live markets · top setups · whale intelligence
          </p>
        </div>
        <div className="flex items-center gap-2 text-[11px] text-lm-text-dim num uppercase tracking-wide">
          <span className={clsx("h-1.5 w-1.5 rounded-full inline-block", headerDot, headerStatus.resolved === "live" && "lm-live-dot text-emerald-400")} />
          {headerStatus.resolved ? headerStatus.label : "Connecting…"}
        </div>
      </div>

      {/* ── PRIMARY · Live Markets ──────────────────────────────────────────── */}
      <section>
        <div className="flex items-center justify-between mb-2">
          <span className="lm-section-title">
            Live Markets
            <span className="text-lm-border">·</span>
            <span className="text-lm-muted normal-case tracking-normal num text-[10px]">
              auto · 2s
            </span>
          </span>
          <span className="flex items-center gap-1.5 text-[10px] text-lm-muted num">
            <RefreshCw className="h-3 w-3" />
            {lastFetchedAt ? `updated ${fmtTime(lastFetchedAt)}` : "loading…"}
          </span>
        </div>
        {/* Command-center split: primary card spans 2/3, compacts stacked in 1/3 */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">

          {/* ── Primary focal card (BTCUSDT) ─────────────────────────────── */}
          {(() => {
            const sym = ACTIVE_SYMBOL;
            const m = markets[sym] ?? EMPTY_MARKET;
            const status = marketStatus(m);
            const p = m.payload;
            const price = p ? heatmapCurrentPrice(p) : null;
            const bidWall = p ? heatmapStrongestWall(p, "bid") : null;
            const askWall = p ? heatmapStrongestWall(p, "ask") : null;
            return (
              <Panel flush hover className="lg:col-span-2 lm-accent-top-cyan lm-card-primary p-4">
                {/* Header */}
                <div className="flex items-center justify-between flex-wrap gap-2">
                  <div className="flex items-center gap-2">
                    <span className="num text-[13px] font-semibold uppercase tracking-widest text-lm-text">
                      {sym}
                    </span>
                    <span className="num text-[9px] uppercase tracking-widest text-lm-cyan">
                      PRIMARY · FAST
                    </span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    {(status.isFallback || status.stale) && (
                      <StatusBadge variant="stale" size="sm">
                        {status.stale ? "Stale" : "Fallback"}
                      </StatusBadge>
                    )}
                    <StatusBadge variant={status.variant} dot={status.variant === "live"}>
                      {status.label}
                    </StatusBadge>
                  </div>
                </div>

                {!p ? (
                  <div className="mt-3 grid grid-cols-1 sm:grid-cols-[1fr_1fr] gap-4">
                    <div className="space-y-2">
                      <Skeleton variant="line" height="h-10" width="w-3/4" />
                      <Skeleton variant="line" width="w-1/2" />
                    </div>
                    <div className="space-y-2">
                      <Skeleton variant="line" width="w-2/3" />
                      <Skeleton variant="line" width="w-1/2" />
                      <Skeleton variant="line" width="w-3/4" />
                    </div>
                    {m.error && (
                      <p className="text-[10px] text-red-400/80 truncate sm:col-span-2">last error: {m.error}</p>
                    )}
                  </div>
                ) : (
                  <div className="mt-3 grid grid-cols-1 sm:grid-cols-[1fr_1fr] gap-4">
                    {/* Price column */}
                    <div>
                      <p className="text-[10px] uppercase tracking-widest text-lm-muted">Last Price</p>
                      <p className="lm-price text-4xl text-lm-text leading-none mt-1">
                        {price !== null
                          ? `$${price.toLocaleString(undefined, { maximumFractionDigits: 2 })}`
                          : "—"}
                      </p>
                      <p className="num text-[10px] text-lm-muted mt-2">
                        {p.meta.liveUpdatedAt ? `live ${fmtTime(p.meta.liveUpdatedAt)}` : "no live timestamp"}
                        {" · "}fetched {fmtTime(m.lastFetchedAt)}
                      </p>
                    </div>

                    {/* Bid / Ask + KPIs column */}
                    <div className="space-y-2.5">
                      {bidWall && (
                        <div className="lm-rail-bid relative pl-3 flex items-center gap-2 text-[12px]">
                          <span className="text-[9px] uppercase tracking-widest text-lm-muted w-7">Bid</span>
                          <span className="num text-lm-text">${bidWall.price_bucket.toLocaleString()}</span>
                          <span className="num text-lm-muted ml-auto">
                            ${(bidWall.total_usd / 1_000_000).toFixed(2)}M
                          </span>
                        </div>
                      )}
                      {askWall && (
                        <div className="lm-rail-ask relative pl-3 flex items-center gap-2 text-[12px]">
                          <span className="text-[9px] uppercase tracking-widest text-lm-muted w-7">Ask</span>
                          <span className="num text-lm-text">${askWall.price_bucket.toLocaleString()}</span>
                          <span className="num text-lm-muted ml-auto">
                            ${(askWall.total_usd / 1_000_000).toFixed(2)}M
                          </span>
                        </div>
                      )}
                      <div className="lm-section-rule" />
                      <div className="grid grid-cols-3 gap-2 text-[10px]">
                        <div>
                          <p className="text-lm-muted uppercase tracking-wide">Cells</p>
                          <p className="num text-lm-text">{p.meta.cellCount}</p>
                        </div>
                        <div>
                          <p className="text-lm-muted uppercase tracking-wide">Walls</p>
                          <p className="num text-lm-text">{p.meta.wallCount}</p>
                        </div>
                        <div>
                          <p className="text-lm-muted uppercase tracking-wide">Source</p>
                          <p className="num text-lm-text truncate">
                            {p.meta.resolvedSource ?? p.meta.source ?? p.meta.dataSource ?? "—"}
                          </p>
                        </div>
                      </div>
                    </div>
                  </div>
                )}
              </Panel>
            );
          })()}

          {/* ── Compact secondary cards (ETH, SOL) ─────────────────────── */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-1 gap-3">
            {BACKGROUND_SYMBOLS.map((sym) => {
              const m = markets[sym] ?? EMPTY_MARKET;
              const status = marketStatus(m);
              const p = m.payload;
              const price = p ? heatmapCurrentPrice(p) : null;
              const bidWall = p ? heatmapStrongestWall(p, "bid") : null;
              const askWall = p ? heatmapStrongestWall(p, "ask") : null;
              return (
                <Panel flush hover key={sym} className="p-3">
                  <div className="flex items-center justify-between">
                    <span className="num text-[11px] font-semibold uppercase tracking-widest text-lm-text">
                      {sym}
                    </span>
                    <StatusBadge variant={status.variant} size="sm" dot={status.variant === "live"}>
                      {status.label}
                    </StatusBadge>
                  </div>

                  {!p ? (
                    <div className="mt-1.5 space-y-1.5">
                      <Skeleton variant="line" height="h-5" width="w-1/2" />
                      <Skeleton variant="line" width="w-3/4" />
                    </div>
                  ) : (
                    <>
                      <p className="lm-price text-xl text-lm-text leading-none mt-1">
                        {price !== null
                          ? `$${price.toLocaleString(undefined, { maximumFractionDigits: 2 })}`
                          : "—"}
                      </p>
                      <div className="mt-1.5 flex items-center gap-3 text-[10px] num">
                        {bidWall && (
                          <span className="lm-rail-bid relative pl-2 text-emerald-400">
                            ${bidWall.price_bucket.toLocaleString()}
                          </span>
                        )}
                        {askWall && (
                          <span className="lm-rail-ask relative pl-2 text-red-400 ml-auto">
                            ${askWall.price_bucket.toLocaleString()}
                          </span>
                        )}
                      </div>
                      <p className="text-[10px] text-lm-muted mt-1.5 num truncate">
                        {p.meta.wallCount}w · {fmtTime(m.lastFetchedAt)}
                      </p>
                    </>
                  )}
                </Panel>
              );
            })}
          </div>
        </div>
      </section>

      {/* ── SECONDARY · Setups | Whale Intel ────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 items-start">

        {/* Left column */}
        <div className="lg:col-span-2 space-y-3">
          {/* Top Setups */}
          <section>
            <div className="flex items-center justify-between mb-2">
              <span className="lm-section-title">
                Top Market Setups
                <TrendingUp className="h-3 w-3 text-lm-purple" />
              </span>
              <StatusBadge variant="warning" size="sm">Demo</StatusBadge>
            </div>
            <Panel flush className="divide-y divide-lm-border/60">
              {mockSetups.map((s) => (
                <div key={s.symbol} className="lm-row px-3 py-2.5 flex flex-col gap-2 sm:grid sm:grid-cols-[80px_1fr_136px_56px] sm:gap-3 sm:items-center">
                  {/* Symbol + bias */}
                  <div className="min-w-0">
                    <p className="num text-[13px] font-semibold text-lm-text leading-tight">{s.symbol}</p>
                    <StatusBadge
                      variant={s.bias === "LONG" ? "bid" : s.bias === "SHORT" ? "ask" : "neutral"}
                      size="sm"
                      className="mt-1"
                    >
                      {s.bias}
                    </StatusBadge>
                  </div>

                  {/* Reason + tags */}
                  <div className="min-w-0">
                    <p className="text-[11.5px] text-lm-text-dim leading-snug line-clamp-2">{s.reason}</p>
                    <div className="flex flex-wrap gap-1 mt-1.5">
                      {s.tags.map((tag) => (
                        <span
                          key={tag}
                          className="text-[9px] uppercase tracking-wide px-1.5 py-0.5 rounded bg-lm-surface-muted text-lm-muted border border-lm-border/60"
                        >
                          {tag}
                        </span>
                      ))}
                    </div>
                  </div>

                  {/* Levels — aligned label/value columns */}
                  <div className="grid grid-cols-[auto_1fr] gap-x-2 gap-y-0.5 text-[11px] num">
                    <span className="text-[9px] uppercase tracking-wide text-lm-muted self-center">Entry</span>
                    <span className="text-right text-lm-text">{s.entry}</span>
                    <span className="text-[9px] uppercase tracking-wide text-lm-muted self-center">Target</span>
                    <span className="text-right text-emerald-400">{s.target}</span>
                    <span className="text-[9px] uppercase tracking-wide text-lm-muted self-center">Stop</span>
                    <span className="text-right text-red-400">{s.stop}</span>
                  </div>

                  {/* Confidence */}
                  <div className="text-right">
                    <div className="h-1 rounded-full bg-lm-border overflow-hidden">
                      <div
                        className="h-full rounded-full bg-lm-cyan/80"
                        style={{ width: `${s.confidence}%` }}
                      />
                    </div>
                    <p className="num text-[10px] text-lm-text-dim mt-1">{s.confidence}%</p>
                  </div>
                </div>
              ))}
            </Panel>
          </section>

        </div>

        {/* Right column — Whale intel feed (compact) */}
        <aside className="space-y-3">
          <Panel flush className="overflow-hidden">
            <div className="px-3 py-2 border-b border-lm-border flex items-center justify-between">
              <span className="lm-section-title">
                Whale Intel
                <Zap className="h-3 w-3 text-lm-cyan" />
              </span>
              <div className="flex items-center gap-1.5">
                <StatusBadge variant="warning" size="sm">Demo</StatusBadge>
                <StatusBadge variant="neutral" size="sm">{mockWhaleAlerts.length}</StatusBadge>
              </div>
            </div>
            <div className="overflow-y-auto max-h-[340px] divide-y divide-lm-border/60">
              {mockWhaleAlerts.map((a) => (
                <div key={a.id} className="lm-row px-3 py-2">
                  {/* Top line: side · symbol · type · size */}
                  <div className="flex items-center gap-2">
                    <StatusBadge variant={a.side === "BUY" ? "bid" : "ask"} size="sm" className="w-9 justify-center shrink-0">
                      {a.side}
                    </StatusBadge>
                    <span className="num text-[12px] font-semibold text-lm-text">{a.symbol}</span>
                    <span className="text-[10px] text-lm-muted uppercase tracking-wide">{a.type}</span>
                    <span className="ml-auto num text-[12px] font-semibold text-lm-text">{a.size}</span>
                  </div>
                  {/* Reason — full width, tight */}
                  <p className="text-[11px] text-lm-text-dim leading-snug mt-1 pl-11">{a.reason}</p>
                  {/* Meta strip */}
                  <div className="flex items-center gap-1.5 mt-1 pl-11">
                    <span className="text-[9px] uppercase tracking-wide text-lm-muted">{a.exchange}</span>
                    <span className="text-lm-border">·</span>
                    <StatusBadge
                      variant={a.risk === "HIGH" ? "error" : a.risk === "MEDIUM" ? "warning" : "neutral"}
                      size="sm"
                    >
                      {a.risk}
                    </StatusBadge>
                    <span className="num text-[10px] text-lm-muted ml-auto">{a.time}</span>
                  </div>
                </div>
              ))}
            </div>
          </Panel>

          <p className="text-[10px] text-lm-muted px-1 leading-snug">
            Live per-symbol liquidity walls are shown in the Live Markets cards above
            and on the Liquidity Map.
          </p>
        </aside>
      </div>
    </PageTransition>
  );
}
