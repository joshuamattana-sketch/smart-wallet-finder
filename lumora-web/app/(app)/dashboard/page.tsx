"use client";

import { useState, useEffect, useCallback } from "react";
import { Panel } from "@/components/ui/Panel";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { PageTransition } from "@/components/ui/PageTransition";
import { Skeleton } from "@/components/ui/Skeleton";
import { WatchlistPriorityPicker } from "@/components/ui/WatchlistPriorityPicker";
import { useWatchlist } from "@/lib/watchlist";
import { clsx } from "clsx";
import { mockSetups, mockWhaleAlerts } from "@/lib/mock-data";
import { TrendingUp, Zap, RefreshCw } from "lucide-react";
import type { HeatmapApiPayload } from "@/lib/heatmap-types";
import {
  heatmapCurrentPrice,
  heatmapStrongestWall,
  heatmapResolvedStatus,
  heatmapIntensitySummary,
} from "@/lib/heatmap-types";

// ── Trader-signal derivation ─────────────────────────────────────────────────
// Derives bias/score/confidence/risk/action from the live heatmap payload
// and (when available) the mock setup for this symbol. No new API calls.
type Bias = "LONG" | "SHORT" | "NEUTRAL";
type SetupQuality = "Weak" | "Developing" | "Strong";
interface TraderSignal {
  bias: Bias;
  score: number;       // 0–100, composite of intensity skew + wall strength
  confidence: number;  // 0–100
  quality: SetupQuality;
  risk: "LOW" | "MEDIUM" | "HIGH";
  reason: string;      // one-line "why this read" summary
  action: string;      // short action hint, ≤ ~80 chars
}

function qualityTier(score: number): SetupQuality {
  if (score >= 70) return "Strong";
  if (score >= 40) return "Developing";
  return "Weak";
}
function qualityVariant(q: SetupQuality): "live" | "warning" | "neutral" {
  return q === "Strong" ? "live" : q === "Developing" ? "warning" : "neutral";
}

function deriveSignal(sym: string, payload: HeatmapApiPayload | null): TraderSignal | null {
  if (!payload) return null;
  const intensity = heatmapIntensitySummary(payload);
  const bidWall = heatmapStrongestWall(payload, "bid");
  const askWall = heatmapStrongestWall(payload, "ask");
  const bidPct = intensity?.bidPct ?? 50;

  // Skew: how far from 50/50 the book leans (0–50 → 0–100 magnitude).
  const skew = Math.abs(bidPct - 50);
  const skewScore = Math.min(100, skew * 2);
  // Wall edge: dominant wall side strength.
  const bidI = bidWall?.intensity ?? 0;
  const askI = askWall?.intensity ?? 0;
  const wallEdge = Math.min(100, Math.abs(bidI - askI));

  // Setup lookup (mock — used only when symbol is present in mockSetups).
  const setup = mockSetups.find((s) => s.symbol === sym);

  // Resolve bias: prefer mock setup if it's there (analyst override), else
  // derive from intensity skew.
  let bias: Bias;
  if (setup) {
    bias = setup.bias as Bias;
  } else {
    bias = bidPct >= 55 ? "LONG" : bidPct <= 45 ? "SHORT" : "NEUTRAL";
  }

  // Composite signal score (book-derived).
  const score = Math.round(0.6 * skewScore + 0.4 * wallEdge);
  // Confidence: prefer setup confidence when available; else map score.
  const confidence = setup?.confidence ?? Math.round(40 + score * 0.55);

  // Risk: keep simple — wide spread or extreme wall imbalance → higher risk.
  const wallTotal = (bidWall?.total_usd ?? 0) + (askWall?.total_usd ?? 0);
  const wallImbalance = wallTotal > 0
    ? Math.abs((bidWall?.total_usd ?? 0) - (askWall?.total_usd ?? 0)) / wallTotal
    : 0;
  const risk: TraderSignal["risk"] =
    wallImbalance > 0.75 ? "HIGH" : wallImbalance > 0.45 ? "MEDIUM" : "LOW";

  const quality = qualityTier(score);

  // Reason: prefer the analyst-authored setup reason; otherwise synthesize a
  // short observation from the live book.
  const reason = setup?.reason
    ?? (bias === "LONG"
        ? `Bid intensity ${bidPct.toFixed(0)}% vs ${(100 - bidPct).toFixed(0)}% ask — buyers leading.`
        : bias === "SHORT"
        ? `Ask intensity ${(100 - bidPct).toFixed(0)}% vs ${bidPct.toFixed(0)}% bid — sellers leading.`
        : "Order book balanced near 50/50 — no clean directional edge.");

  // Action hint: weak score always overrides toward monitor. Otherwise per-bias.
  const action = quality === "Weak"
    ? "Monitor — score too weak to commit; wait for confirmation."
    : setup
    ? (bias === "LONG"
        ? `Watch entry ${setup.entry} · invalidates ${setup.stop}`
        : bias === "SHORT"
        ? `Fade into ${setup.entry} · invalidates ${setup.stop}`
        : "Wait for sweep · no clean edge yet")
    : (bias === "LONG"
        ? "Bid-side absorbing · wait for confirmed lift"
        : bias === "SHORT"
        ? "Ask-side dominant · fade rallies"
        : "Book balanced · stand aside");

  return { bias, score, confidence, quality, risk, reason, action };
}

function biasVariant(b: Bias): "bid" | "ask" | "neutral" {
  return b === "LONG" ? "bid" : b === "SHORT" ? "ask" : "neutral";
}
function riskVariant(r: TraderSignal["risk"]): "live" | "warning" | "error" {
  return r === "LOW" ? "live" : r === "MEDIUM" ? "warning" : "error";
}

// Active/primary market refreshes fast; the rest poll slowly in the background.
const ACTIVE_REFRESH_MS = 2000;
const BACKGROUND_REFRESH_MS = 9000;
/** Max number of compact secondary cards shown next to the primary. */
const MAX_SECONDARY = 2;

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
  const { primary, secondaries } = useWatchlist();
  // The primary symbol gets the fast 2s poll. Background symbols cycle on a
  // slower 9s poll. We cap visible secondaries to keep the layout balanced;
  // the full watchlist is still managed via the picker.
  const activeSymbol = primary;
  const backgroundSymbols = secondaries.slice(0, MAX_SECONDARY);
  const dashSymbols = [activeSymbol, ...backgroundSymbols];
  // Stable string for effect dependency (avoids re-runs from new array refs).
  const backgroundKey = backgroundSymbols.join(",");

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
    dashSymbols.forEach((sym) => { fetchSymbol(sym); });
    const activeId = setInterval(() => fetchSymbol(activeSymbol), ACTIVE_REFRESH_MS);
    const backgroundId = setInterval(
      () => { backgroundSymbols.forEach((sym) => fetchSymbol(sym)); },
      BACKGROUND_REFRESH_MS,
    );
    const onVisible = () => {
      if (document.visibilityState === "visible") {
        dashSymbols.forEach((sym) => { fetchSymbol(sym); });
      }
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      clearInterval(activeId);
      clearInterval(backgroundId);
      document.removeEventListener("visibilitychange", onVisible);
    };
    // backgroundKey is the stable signature of backgroundSymbols; dashSymbols
    // is derived from activeSymbol + backgroundSymbols and tracked by both.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fetchSymbol, activeSymbol, backgroundKey]);

  // Overall header status derived from the active (primary) market.
  const headerStatus = heatmapResolvedStatus(markets[activeSymbol]?.payload ?? null);
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
            Current read · live markets · top setups · whale intel
          </p>
        </div>
        <div className="flex items-center gap-2 text-[11px] text-lm-text-dim num uppercase tracking-wide">
          <span className={clsx("h-1.5 w-1.5 rounded-full inline-block", headerDot, headerStatus.resolved === "live" && "lm-live-dot text-emerald-400")} />
          {headerStatus.resolved ? headerStatus.label : "Connecting…"}
        </div>
      </div>

      {/* ── CURRENT READ · primary symbol verdict ──────────────────────────── */}
      {(() => {
        const m = markets[activeSymbol] ?? EMPTY_MARKET;
        const p = m.payload;
        const signal = deriveSignal(activeSymbol, p);
        const status = marketStatus(m);
        return (
          <Panel flush hover className="lm-accent-top-cyan lm-card-primary p-4">
            {/* Header row */}
            <div className="flex items-center justify-between flex-wrap gap-2">
              <div className="flex items-center gap-2">
                <span className="lm-section-title">Current Read</span>
                <span className="num text-[11px] font-semibold uppercase tracking-widest text-lm-text">
                  {activeSymbol}
                </span>
              </div>
              <div className="flex items-center gap-1.5">
                {signal && (
                  <StatusBadge variant={qualityVariant(signal.quality)} size="sm">
                    {signal.quality.toUpperCase()}
                  </StatusBadge>
                )}
                <StatusBadge variant={status.variant} size="sm" dot={status.variant === "live"}>
                  {status.label}
                </StatusBadge>
              </div>
            </div>

            {!signal ? (
              <div className="mt-3 grid grid-cols-1 sm:grid-cols-[180px_1fr] gap-3">
                <Skeleton variant="line" height="h-12" />
                <div className="space-y-2">
                  <Skeleton variant="line" width="w-3/4" />
                  <Skeleton variant="line" width="w-1/2" />
                </div>
              </div>
            ) : (
              <div className="mt-3 grid grid-cols-1 sm:grid-cols-[180px_1fr] gap-3 items-start">
                {/* Big bias verdict */}
                <div>
                  <p className="text-[9px] uppercase tracking-widest text-lm-muted">Bias</p>
                  <p
                    className={clsx(
                      "lm-price text-3xl leading-none mt-0.5",
                      signal.bias === "LONG"
                        ? "text-emerald-400"
                        : signal.bias === "SHORT"
                        ? "text-red-400"
                        : "text-lm-text-dim",
                    )}
                  >
                    {signal.bias}
                  </p>
                  <div className="mt-2 flex items-center gap-3">
                    <div>
                      <p className="text-[9px] uppercase tracking-widest text-lm-muted">Score</p>
                      <p className="num text-[15px] font-semibold text-lm-text leading-none">
                        {signal.score}
                        <span className="text-[10px] text-lm-muted">/100</span>
                      </p>
                    </div>
                    <div>
                      <p className="text-[9px] uppercase tracking-widest text-lm-muted">Conf</p>
                      <p className="num text-[15px] font-semibold text-lm-text leading-none">
                        {signal.confidence}%
                      </p>
                    </div>
                    <div>
                      <p className="text-[9px] uppercase tracking-widest text-lm-muted">Risk</p>
                      <StatusBadge variant={riskVariant(signal.risk)} size="sm">
                        {signal.risk}
                      </StatusBadge>
                    </div>
                  </div>
                </div>

                {/* Reason + action */}
                <div className="space-y-2.5">
                  <div>
                    <p className="text-[9px] uppercase tracking-widest text-lm-muted">Reason</p>
                    <p className="text-[12px] text-lm-text-dim leading-snug mt-0.5">{signal.reason}</p>
                  </div>
                  <div className="lm-verdict-rule">
                    <p className="text-[9px] uppercase tracking-widest text-lm-muted">Action</p>
                    <p className="text-[12.5px] text-lm-text leading-snug mt-0.5 font-medium">
                      {signal.action}
                    </p>
                  </div>
                </div>
              </div>
            )}
          </Panel>
        );
      })()}

      {/* ── PRIMARY · Live Markets ──────────────────────────────────────────── */}
      <section>
        <div className="flex items-center justify-between mb-2 gap-2 flex-wrap">
          <span className="lm-section-title">
            Live Markets
            <span className="text-lm-border">·</span>
            <span className="text-lm-muted normal-case tracking-normal num text-[10px]">
              auto · 2s
            </span>
          </span>
          <div className="flex items-center gap-2">
            <span className="flex items-center gap-1.5 text-[10px] text-lm-muted num">
              <RefreshCw className="h-3 w-3" />
              {lastFetchedAt ? `updated ${fmtTime(lastFetchedAt)}` : "loading…"}
            </span>
            <WatchlistPriorityPicker />
          </div>
        </div>
        {/* Command-center split: primary card spans 2/3, compacts stacked in 1/3 */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">

          {/* ── Primary focal card ─────────────────────────────── */}
          {(() => {
            const sym = activeSymbol;
            const m = markets[sym] ?? EMPTY_MARKET;
            const status = marketStatus(m);
            const p = m.payload;
            const price = p ? heatmapCurrentPrice(p) : null;
            const bidWall = p ? heatmapStrongestWall(p, "bid") : null;
            const askWall = p ? heatmapStrongestWall(p, "ask") : null;
            const signal = deriveSignal(sym, p);
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
                    </div>
                    {m.error && (
                      <p className="text-[10px] text-red-400/80 truncate sm:col-span-2">last error: {m.error}</p>
                    )}
                  </div>
                ) : (
                  <div className="mt-3 grid grid-cols-1 sm:grid-cols-[1fr_1fr] gap-4">
                    {/* Price column — execution focus */}
                    <div>
                      <p className="text-[10px] uppercase tracking-widest text-lm-muted">Last Price</p>
                      <p className="lm-price text-4xl text-lm-text leading-none mt-1">
                        {price !== null
                          ? `$${price.toLocaleString(undefined, { maximumFractionDigits: 2 })}`
                          : "—"}
                      </p>
                      {p.meta.liveUpdatedAt && (
                        <p className="num text-[10px] text-lm-muted mt-2">
                          live {fmtTime(p.meta.liveUpdatedAt)}
                        </p>
                      )}
                    </div>

                    {/* Depth column — top bid/ask only */}
                    <div className="space-y-2">
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
                      {signal && (
                        <p className="text-[10px] text-lm-muted leading-snug pt-1 num">
                          See Current Read above for bias, score and action.
                        </p>
                      )}
                    </div>
                  </div>
                )}
              </Panel>
            );
          })()}

          {/* ── Compact secondary cards (ETH, SOL) ─────────────────────── */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-1 gap-3">
            {backgroundSymbols.length === 0 ? (
              <Panel flush className="p-3 text-center">
                <p className="text-[11px] text-lm-muted leading-snug">
                  Add another symbol to the watchlist to compare side-by-side.
                </p>
              </Panel>
            ) : null}
            {backgroundSymbols.map((sym) => {
              const m = markets[sym] ?? EMPTY_MARKET;
              const status = marketStatus(m);
              const p = m.payload;
              const price = p ? heatmapCurrentPrice(p) : null;
              const signal = deriveSignal(sym, p);
              return (
                <Panel flush hover key={sym} className="p-3">
                  {/* Header: symbol + status */}
                  <div className="flex items-center justify-between">
                    <span className="num text-[11px] font-semibold uppercase tracking-widest text-lm-text">
                      {sym}
                    </span>
                    <StatusBadge variant={status.variant} size="sm" dot={status.variant === "live"}>
                      {status.label}
                    </StatusBadge>
                  </div>

                  {!p || !signal ? (
                    <div className="mt-1.5 space-y-1.5">
                      <Skeleton variant="line" height="h-5" width="w-1/2" />
                      <Skeleton variant="line" width="w-3/4" />
                    </div>
                  ) : (
                    <>
                      {/* Price */}
                      <p className="lm-price text-xl text-lm-text leading-none mt-1">
                        {price !== null
                          ? `$${price.toLocaleString(undefined, { maximumFractionDigits: 2 })}`
                          : "—"}
                      </p>
                      {/* Bias + Score */}
                      <div className="mt-2 flex items-center gap-2">
                        <StatusBadge variant={biasVariant(signal.bias)} size="sm">
                          {signal.bias}
                        </StatusBadge>
                        <span className="num text-[10px] text-lm-muted uppercase tracking-wide">Score</span>
                        <span className="num text-[12px] font-semibold text-lm-text ml-auto">
                          {signal.score}
                          <span className="text-[9px] text-lm-muted">/100</span>
                        </span>
                      </div>
                      {/* Confidence micro-bar */}
                      <div className="mt-1.5 h-[3px] rounded-full bg-lm-border overflow-hidden">
                        <div
                          className="h-full rounded-full bg-lm-cyan/70"
                          style={{ width: `${signal.confidence}%` }}
                        />
                      </div>
                      {/* Freshness */}
                      <p className="text-[10px] text-lm-muted mt-1.5 num truncate">
                        {p.meta.liveUpdatedAt
                          ? `live ${fmtTime(p.meta.liveUpdatedAt)}`
                          : `last ${fmtTime(m.lastFetchedAt)}`}
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
              {mockSetups.map((s) => {
                const biasVar = biasVariant(s.bias as Bias);
                // Setup score = same confidence scale; useful as a leading metric.
                const setupScore = s.confidence;
                return (
                  <div
                    key={s.symbol}
                    className="lm-row px-3 py-2.5 flex flex-col gap-2 sm:grid sm:grid-cols-[88px_1fr_140px_60px] sm:gap-3 sm:items-center"
                  >
                    {/* Symbol + bias */}
                    <div className="min-w-0">
                      <p className="num text-[13px] font-semibold text-lm-text leading-tight">{s.symbol}</p>
                      <StatusBadge variant={biasVar} size="sm" className="mt-1">
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

                    {/* Levels — Entry / Invalidation / Target */}
                    <div className="grid grid-cols-[auto_1fr] gap-x-2 gap-y-0.5 text-[11px] num">
                      <span className="text-[9px] uppercase tracking-wide text-lm-muted self-center">Entry</span>
                      <span className="text-right text-lm-text">{s.entry}</span>
                      <span className="text-[9px] uppercase tracking-wide text-lm-muted self-center">Target</span>
                      <span className="text-right text-emerald-400">{s.target}</span>
                      <span className="text-[9px] uppercase tracking-wide text-lm-muted self-center">Invalid</span>
                      <span className="text-right text-red-400">{s.stop}</span>
                    </div>

                    {/* Setup score + confidence bar */}
                    <div className="text-right">
                      <p className="num text-[14px] font-semibold text-lm-text leading-none">
                        {setupScore}
                        <span className="text-[9px] text-lm-muted">/100</span>
                      </p>
                      <div className="h-1 mt-1 rounded-full bg-lm-border overflow-hidden">
                        <div
                          className="h-full rounded-full bg-lm-cyan/80"
                          style={{ width: `${s.confidence}%` }}
                        />
                      </div>
                      <p className="num text-[9px] text-lm-muted mt-0.5 uppercase tracking-wide">Score</p>
                    </div>
                  </div>
                );
              })}
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
                  {/* Top line: side · symbol · type · notional */}
                  <div className="flex items-center gap-2">
                    <StatusBadge variant={a.side === "BUY" ? "bid" : "ask"} size="sm" className="w-9 justify-center shrink-0">
                      {a.side}
                    </StatusBadge>
                    <span className="num text-[12px] font-semibold text-lm-text">{a.symbol}</span>
                    <span className="text-[10px] text-lm-muted uppercase tracking-wide truncate">{a.type}</span>
                    <span className="ml-auto lm-price text-[13px] text-lm-text">{a.size}</span>
                  </div>
                  {/* Reason — full width, tight */}
                  <p className="text-[11px] text-lm-text-dim leading-snug mt-1 pl-11 line-clamp-2">{a.reason}</p>
                  {/* Meta strip: severity · confidence · time */}
                  <div className="flex items-center gap-1.5 mt-1 pl-11">
                    <StatusBadge
                      variant={a.risk === "HIGH" ? "error" : a.risk === "MEDIUM" ? "warning" : "neutral"}
                      size="sm"
                    >
                      {a.risk}
                    </StatusBadge>
                    <span className="num text-[9px] uppercase tracking-wide text-lm-muted">
                      conf {a.confidence}%
                    </span>
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
