"use client";

// LM69C — Dashboard: a live command center, not a card grid.
//
// Composition:
//   read strip     — ONE compact line: bias · score/conf · risk · action ·
//                    live price · status. The read stays available without a
//                    giant static card eating the top of the page.
//   watchlist rail — compact secondary symbols + priority picker
//   whale tape     — what changed (demo until live wiring)
//   setups         — what to watch
//
// Mobile order: read → watchlist → whale tape → setups.

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { Panel } from "@/components/ui/Panel";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { PageShell } from "@/components/ui/PageShell";
import { Skeleton } from "@/components/ui/Skeleton";
import { WatchlistPriorityPicker } from "@/components/ui/WatchlistPriorityPicker";
import { SetupCard } from "@/components/dashboard/SetupCard";
import { useWatchlist } from "@/lib/watchlist";
import { clsx } from "clsx";
import { mockSetups, mockWhaleAlerts } from "@/lib/mock-data";
import type { HeatmapApiPayload } from "@/lib/heatmap-types";
import {
  heatmapCurrentPrice,
  heatmapStrongestWall,
  heatmapResolvedStatus,
  heatmapIntensitySummary,
} from "@/lib/heatmap-types";

// ── Dashboard-local visual layer (LM70C) ─────────────────────────────────────
// Command-center accents: a breathing live ring on the read strip, glow-tipped
// score bars, and a faint signal sweep across the read surface. All gated
// behind prefers-reduced-motion; static fallbacks read fine.
const DASH_CSS = `
@media (prefers-reduced-motion: no-preference) {
  .lmdc-sweep { animation: lmdc-sweep 9s ease-in-out infinite; }
  @keyframes lmdc-sweep {
    0%, 100% { transform: translateX(-120%); opacity: 0; }
    40%      { opacity: 1; }
    60%      { transform: translateX(120%); opacity: 0; }
  }
  .lmdc-breathe { animation: lmdc-breathe 3.2s ease-in-out infinite; }
  @keyframes lmdc-breathe {
    0%, 100% { opacity: 0.55; }
    50%      { opacity: 1; }
  }
}
.lmdc-bar-tip { box-shadow: 0 0 6px 0 currentColor; }
.lmdc-module-row { transition: background-color 130ms ease-out, box-shadow 130ms ease-out; }
.lmdc-module-row:hover {
  background-color: rgba(255, 255, 255, 0.025);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.03);
}
`;

// Module header — one shared lead for every intelligence module: section
// title, optional right slot, and a violet→cyan hairline underneath so the
// modules read as parts of one connected system.
function ModuleHeader({
  title,
  right,
}: {
  title: string;
  right?: React.ReactNode;
}) {
  return (
    <div className="relative flex items-center justify-between gap-2 px-3 py-2">
      <span className="lm-section-title">{title}</span>
      {right}
      <span
        aria-hidden
        className="pointer-events-none absolute inset-x-0 bottom-0 h-px bg-gradient-to-r from-violet-500/25 via-white/[0.05] to-transparent"
      />
    </div>
  );
}

// ── Trader-signal derivation ─────────────────────────────────────────────────
// Derives bias/score/confidence/risk/action purely from the live heatmap
// payload — no mock-setup bleed into the live read. No new API calls.
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

function deriveSignal(_sym: string, payload: HeatmapApiPayload | null): TraderSignal | null {
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

  // Bias derived purely from the live order-book skew — no mock-setup bleed
  // into the live read. Curated demo setups live in their own Demo-badged panel.
  const bias: Bias = bidPct >= 55 ? "LONG" : bidPct <= 45 ? "SHORT" : "NEUTRAL";

  // Composite signal score (book-derived).
  const score = Math.round(0.6 * skewScore + 0.4 * wallEdge);
  // Confidence mapped from the book-derived score.
  const confidence = Math.round(40 + score * 0.55);

  // Risk: keep simple — wide spread or extreme wall imbalance → higher risk.
  const wallTotal = (bidWall?.total_usd ?? 0) + (askWall?.total_usd ?? 0);
  const wallImbalance = wallTotal > 0
    ? Math.abs((bidWall?.total_usd ?? 0) - (askWall?.total_usd ?? 0)) / wallTotal
    : 0;
  const risk: TraderSignal["risk"] =
    wallImbalance > 0.75 ? "HIGH" : wallImbalance > 0.45 ? "MEDIUM" : "LOW";

  const quality = qualityTier(score);

  // Reason synthesized from the live book only.
  const reason = bias === "LONG"
    ? `Bid intensity ${bidPct.toFixed(0)}% vs ${(100 - bidPct).toFixed(0)}% ask — buyers leading.`
    : bias === "SHORT"
    ? `Ask intensity ${(100 - bidPct).toFixed(0)}% vs ${bidPct.toFixed(0)}% bid — sellers leading.`
    : "Order book balanced near 50/50 — no clean directional edge.";

  // Action hint — book-derived; weak score overrides toward monitor.
  const action = quality === "Weak"
    ? "Monitor — score too weak to commit; wait for confirmation."
    : bias === "LONG"
    ? "Bid-side absorbing · wait for confirmed lift"
    : bias === "SHORT"
    ? "Ask-side dominant · fade rallies"
    : "Book balanced · stand aside";

  return { bias, score, confidence, quality, risk, reason, action };
}

function biasTone(b: Bias): string {
  return b === "LONG" ? "text-emerald-400" : b === "SHORT" ? "text-red-400" : "text-lm-text-dim";
}
function riskVariant(r: TraderSignal["risk"]): "live" | "warning" | "error" {
  return r === "LOW" ? "live" : r === "MEDIUM" ? "warning" : "error";
}

// Active/primary market refreshes fast; the rest poll slowly in the background.
const ACTIVE_REFRESH_MS = 2000;
const BACKGROUND_REFRESH_MS = 9000;
/** Max number of watchlist rail rows shown next to the command surface. */
const MAX_SECONDARY = 4;

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
  return { label: s.label, variant: variant, isFallback: s.isFallback, stale: s.stale };
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
  // slower 9s poll. We cap visible secondaries to keep the rail balanced;
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

  // Read strip state for the primary symbol.
  const activeMarket = markets[activeSymbol] ?? EMPTY_MARKET;
  const activePayload = activeMarket.payload;
  const activeSignal = deriveSignal(activeSymbol, activePayload);
  const activeStatus = marketStatus(activeMarket);
  const activePrice = activePayload ? heatmapCurrentPrice(activePayload) : null;

  return (
    <PageShell
      title="Dashboard"
      context="The read first · then what changed · then what to watch"
      status={
        <span className="flex items-center gap-2 text-[11px] text-lm-text-dim num uppercase tracking-wide">
          <span className={clsx("h-1.5 w-1.5 rounded-full inline-block", headerDot, headerStatus.resolved === "live" && "lm-live-dot text-emerald-400")} />
          {headerStatus.resolved ? headerStatus.label : "Connecting…"}
        </span>
      }
    >
      <style dangerouslySetInnerHTML={{ __html: DASH_CSS }} />

      {/* ── CURRENT READ — the command surface ─────────────────────────────── */}
      <Panel level="focus" flush className="overflow-hidden">
        <div
          className={clsx(
            "relative flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3",
            // Bias-tinted atmosphere — the surface itself carries the verdict.
            !activeSignal || activeSignal.bias === "NEUTRAL"
              ? "bg-gradient-to-r from-cyan-400/[0.04] via-transparent to-violet-500/[0.03]"
              : activeSignal.bias === "LONG"
                ? "bg-gradient-to-r from-emerald-400/[0.06] via-transparent to-violet-500/[0.03]"
                : "bg-gradient-to-r from-rose-400/[0.06] via-transparent to-violet-500/[0.03]",
          )}
        >
          {/* Signal sweep — a quiet scanner pass across the command surface */}
          <span
            aria-hidden
            className="lmdc-sweep pointer-events-none absolute inset-y-0 w-1/3 bg-gradient-to-r from-transparent via-cyan-300/[0.04] to-transparent"
          />
          {/* bias edge — thicker, glowing verdict rail */}
          <span
            aria-hidden
            className={clsx(
              "absolute inset-y-1.5 left-0 w-[3px] rounded-full",
              !activeSignal
                ? "bg-zinc-600/50"
                : activeSignal.bias === "LONG"
                  ? "bg-emerald-400/80 shadow-[0_0_10px_rgba(52,211,153,0.5)]"
                  : activeSignal.bias === "SHORT"
                    ? "bg-rose-400/80 shadow-[0_0_10px_rgba(251,113,133,0.5)]"
                    : "bg-zinc-500/60",
            )}
          />
          <div className="flex items-baseline gap-2.5">
            <span className="lm-section-title">Current Read</span>
            <span className="num text-[12px] font-semibold uppercase tracking-widest text-lm-text">
              {activeSymbol}
            </span>
          </div>

          {!activeSignal || !activePayload ? (
            <>
              <Skeleton variant="line" width="w-48" height="h-4" />
              {activeMarket.error && (
                <span className="text-[10px] text-red-400/80 truncate">
                  last error: {activeMarket.error}
                </span>
              )}
            </>
          ) : (
            <>
              {/* The verdict — large, glowing, unmistakable */}
              <span
                className={clsx(
                  "num text-[19px] font-bold leading-none tracking-wide",
                  biasTone(activeSignal.bias),
                  activeSignal.bias === "LONG" && "drop-shadow-[0_0_10px_rgba(52,211,153,0.45)]",
                  activeSignal.bias === "SHORT" && "drop-shadow-[0_0_10px_rgba(251,113,133,0.45)]",
                )}
              >
                {activeSignal.bias}
              </span>
              {/* Score capsule — number + micro bar in one unit */}
              <span className="flex items-center gap-2">
                <span className="num text-[11px] text-lm-text-dim">
                  {activeSignal.score}
                  <span className="text-lm-muted">/100</span>
                  <span className="mx-1.5 text-lm-border">·</span>
                  conf {activeSignal.confidence}%
                </span>
                <span className="hidden h-[3px] w-12 overflow-hidden rounded-full bg-black/40 shadow-[inset_0_1px_1px_rgba(0,0,0,0.5)] sm:block">
                  <span
                    className={clsx(
                      "lmdc-bar-tip block h-full rounded-full",
                      activeSignal.bias === "LONG"
                        ? "bg-emerald-400/80 text-emerald-400"
                        : activeSignal.bias === "SHORT"
                          ? "bg-rose-400/80 text-rose-400"
                          : "bg-lm-cyan/70 text-cyan-400",
                    )}
                    style={{ width: `${activeSignal.score}%` }}
                  />
                </span>
              </span>
              <StatusBadge variant={riskVariant(activeSignal.risk)} size="sm">
                {activeSignal.risk}
              </StatusBadge>
              {/* The directive — one line; full reason on hover */}
              <span
                className="hidden min-w-0 flex-1 truncate text-[11.5px] text-lm-text-dim md:inline"
                title={`${activeSignal.reason} — ${activeSignal.action}`}
              >
                {activeSignal.action}
              </span>
            </>
          )}

          <div className="ml-auto flex items-center gap-2.5">
            {/* Live price — breathing halo behind the number */}
            <span className="relative">
              <span
                aria-hidden
                className="lmdc-breathe pointer-events-none absolute -inset-2 rounded-full bg-cyan-400/[0.07] blur-md"
              />
              <span className="lm-price relative text-[16px] leading-none text-lm-cyan drop-shadow-[0_0_8px_rgba(34,211,238,0.35)]">
                {activePrice !== null
                  ? `$${activePrice.toLocaleString(undefined, { maximumFractionDigits: 2 })}`
                  : "—"}
              </span>
            </span>
            <StatusBadge variant={activeStatus.variant} size="sm" dot={activeStatus.variant === "live"}>
              {activeStatus.label}
            </StatusBadge>
            <Link
              href="/terminal"
              className="num rounded border border-white/[0.06] bg-white/[0.02] px-2 py-1 text-[10px] uppercase tracking-wider text-lm-cyan/80 transition-colors duration-150 hover:border-cyan-400/30 hover:text-lm-cyan focus-visible:outline focus-visible:outline-1 focus-visible:outline-offset-2 focus-visible:outline-cyan-400/60"
            >
              Terminal →
            </Link>
          </div>
        </div>
      </Panel>

      {/* ── COMMAND GRID · Setups | Watchlist + Whale Tape ─────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3 items-start">

        {/* Right rail (first on mobile): watchlist priority + what changed */}
        <aside className="space-y-3 lg:order-2">
          {/* Watchlist rail */}
          <Panel level="subtle" flush className="overflow-hidden ring-1 ring-white/[0.05] shadow-[0_8px_24px_-12px_rgba(0,0,0,0.7)]">
            <ModuleHeader title="Watchlist" right={<WatchlistPriorityPicker />} />
            <div className="divide-y divide-lm-border/40">
              {backgroundSymbols.length === 0 && (
                <p className="px-3 py-4 text-[11px] text-lm-muted leading-snug">
                  Add symbols to compare against {activeSymbol}.
                </p>
              )}
              {backgroundSymbols.map((sym) => {
                const m = markets[sym] ?? EMPTY_MARKET;
                const p = m.payload;
                const price = p ? heatmapCurrentPrice(p) : null;
                const signal = deriveSignal(sym, p);
                return (
                  <div key={sym} className="lmdc-module-row px-3 py-2">
                    {!p || !signal ? (
                      <div className="space-y-1.5">
                        <Skeleton variant="line" width="w-1/3" />
                        <Skeleton variant="line" width="w-2/3" />
                      </div>
                    ) : (
                      <>
                        <div className="flex items-baseline gap-2">
                          <span className="num text-[12px] font-semibold tracking-wide text-lm-text">
                            {sym}
                          </span>
                          <span className={clsx("num text-[10px] font-semibold uppercase", biasTone(signal.bias))}>
                            {signal.bias}
                          </span>
                          <span className="lm-price text-[14px] text-lm-text ml-auto">
                            {price !== null
                              ? `$${price.toLocaleString(undefined, { maximumFractionDigits: 2 })}`
                              : "—"}
                          </span>
                        </div>
                        <div className="mt-1.5 flex items-center gap-2">
                          <div className="h-[3px] flex-1 rounded-full bg-black/40 shadow-[inset_0_1px_1px_rgba(0,0,0,0.5)] overflow-hidden">
                            <div
                              className={clsx(
                                "lmdc-bar-tip h-full rounded-full transition-[width] duration-500",
                                signal.bias === "LONG"
                                  ? "bg-emerald-400/70 text-emerald-400"
                                  : signal.bias === "SHORT"
                                    ? "bg-rose-400/70 text-rose-400"
                                    : "bg-lm-cyan/60 text-cyan-400",
                              )}
                              style={{ width: `${signal.confidence}%` }}
                            />
                          </div>
                          <span className="num text-[10px] text-lm-muted">
                            {signal.score}
                            <span className="text-lm-border">/</span>100
                          </span>
                        </div>
                      </>
                    )}
                  </div>
                );
              })}
            </div>
            <p className="num border-t border-lm-border/40 px-3 py-1.5 text-[9.5px] uppercase tracking-wider text-lm-muted">
              {lastFetchedAt ? `updated ${fmtTime(lastFetchedAt)}` : "loading…"} · auto
            </p>
          </Panel>

          {/* Whale tape — what changed */}
          <section>
            <Panel level="subtle" flush className="overflow-hidden ring-1 ring-white/[0.05] shadow-[0_8px_24px_-12px_rgba(0,0,0,0.7)]">
              <ModuleHeader
                title="Whale Tape · What Changed"
                right={<StatusBadge variant="demo" size="sm">Demo</StatusBadge>}
              />
              <div className="overflow-y-auto max-h-[360px] divide-y divide-lm-border/40">
                {mockWhaleAlerts.map((a) => (
                  <div
                    key={a.id}
                    className={clsx(
                      "lmdc-module-row relative px-3 py-2",
                      a.side === "BUY" ? "lm-rail-bid pl-4" : "lm-rail-ask pl-4",
                    )}
                  >
                    {/* Top line: side · symbol · type · notional */}
                    <div className="flex items-baseline gap-2">
                      <span
                        className={clsx(
                          "num text-[10px] font-semibold uppercase w-8 shrink-0",
                          a.side === "BUY" ? "text-emerald-400" : "text-red-400",
                        )}
                      >
                        {a.side}
                      </span>
                      <span className="num text-[12px] font-semibold text-lm-text">{a.symbol}</span>
                      <span className="text-[10px] text-lm-muted uppercase tracking-wide truncate">{a.type}</span>
                      <span className="ml-auto lm-price text-[13px] text-lm-text">{a.size}</span>
                    </div>
                    {/* Bottom line: reason (one line) · risk · time */}
                    <div className="mt-1 flex items-center gap-2">
                      <p className="flex-1 min-w-0 text-[10.5px] text-lm-text-dim leading-snug line-clamp-1">
                        {a.reason}
                      </p>
                      {a.risk !== "LOW" && (
                        <StatusBadge variant={a.risk === "HIGH" ? "error" : "warning"} size="sm">
                          {a.risk}
                        </StatusBadge>
                      )}
                      <span className="num text-[10px] text-lm-muted">{a.time}</span>
                    </div>
                  </div>
                ))}
              </div>
            </Panel>
          </section>
        </aside>

        {/* Setups — what to watch */}
        <section className="lg:order-1 lg:col-span-2">
          <Panel level="subtle" flush className="overflow-hidden ring-1 ring-white/[0.05] shadow-[0_8px_24px_-12px_rgba(0,0,0,0.7)]">
            <ModuleHeader
              title="Setups · What to Watch"
              right={<StatusBadge variant="demo" size="sm">Demo</StatusBadge>}
            />
            <div className="grid grid-cols-1 gap-3 p-3 sm:grid-cols-2">
              {mockSetups.map((s) => (
                <SetupCard key={s.symbol} setup={s} />
              ))}
            </div>
          </Panel>
        </section>
      </div>
    </PageShell>
  );
}
