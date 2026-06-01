"use client";

import { useState, useEffect, useCallback } from "react";
import { KpiCard } from "@/components/ui/KpiCard";
import { GlassCard } from "@/components/ui/GlassCard";
import { Badge } from "@/components/ui/Badge";
import { mockKpis, mockSetups, mockWhaleAlerts, mockLiquidityZones } from "@/lib/mock-data";
import { clsx } from "clsx";
import { TrendingUp, TrendingDown, Minus, Activity, Zap, RefreshCw } from "lucide-react";
import type { HeatmapApiPayload } from "@/lib/heatmap-types";
import {
  heatmapCurrentPrice,
  heatmapStrongestWall,
  heatmapIsStale,
} from "@/lib/heatmap-types";

const DASH_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"] as const;

interface MarketState {
  payload: HeatmapApiPayload | null;
  error: string | null;
}

function marketStatus(
  m: MarketState,
): { label: string; variant: "green" | "yellow" | "red" | "muted" } {
  if (m.error) return { label: "Error", variant: "red" };
  if (!m.payload) return { label: "—", variant: "muted" };
  if (heatmapIsStale(m.payload)) return { label: "Stale", variant: "yellow" };
  const src = m.payload.meta.source ?? m.payload.meta.dataSource;
  if (src === "fixture" || src === "local_live_fixture") {
    return { label: "Live Fixture", variant: "green" };
  }
  return { label: "Mock", variant: "muted" };
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

  // Pull each market from the shared /api/heatmap fixture source (the route
  // falls back to mock server-side when no fixture exists).
  const fetchMarkets = useCallback(async () => {
    const entries = await Promise.all(
      DASH_SYMBOLS.map(async (sym) => {
        try {
          const res = await fetch(
            `/api/heatmap?source=fixture&symbol=${sym}&timeframe=5m`,
            { cache: "no-store" },
          );
          if (!res.ok) {
            const body = await res.json().catch(() => ({}));
            const message = (body as { message?: string }).message ?? `API error ${res.status}`;
            return [sym, { payload: null, error: message }] as const;
          }
          const payload: HeatmapApiPayload = await res.json();
          return [sym, { payload, error: null }] as const;
        } catch (err) {
          return [sym, { payload: null, error: err instanceof Error ? err.message : "Network error" }] as const;
        }
      }),
    );
    setMarkets(Object.fromEntries(entries));
    setLastFetchedAt(new Date().toISOString());
  }, []);

  // Auto-refresh every 5s; interval cleaned up on unmount.
  useEffect(() => {
    fetchMarkets();
    const id = setInterval(fetchMarkets, 5000);
    return () => clearInterval(id);
  }, [fetchMarkets]);

  return (
    <div className="space-y-5 animate-[fadeIn_0.4s_ease-out]">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-lumora-text">Market Dashboard</h1>
          <p className="text-sm text-lumora-muted mt-0.5">Demo data — live integrations coming soon</p>
        </div>
        <div className="flex items-center gap-2 text-xs text-lumora-green">
          <span className="h-1.5 w-1.5 rounded-full bg-green-400 animate-pulse inline-block" />
          Demo Mode
        </div>
      </div>

      {/* Live Markets — shared /api/heatmap fixture source, auto-refresh 5s */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <h2 className="text-xs font-semibold uppercase tracking-widest text-lumora-muted flex items-center gap-2">
            <Activity className="h-3.5 w-3.5 text-lumora-cyan" /> Live Markets
          </h2>
          <span className="flex items-center gap-1.5 text-[10px] text-lumora-muted">
            <RefreshCw className="h-3 w-3" />
            {lastFetchedAt ? `updated ${fmtTime(lastFetchedAt)}` : "loading…"}
          </span>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          {DASH_SYMBOLS.map((sym) => {
            const m = markets[sym] ?? { payload: null, error: null };
            const status = marketStatus(m);
            const p = m.payload;
            const price = p ? heatmapCurrentPrice(p) : null;
            const bidWall = p ? heatmapStrongestWall(p, "bid") : null;
            const askWall = p ? heatmapStrongestWall(p, "ask") : null;
            return (
              <GlassCard key={sym} className="p-3">
                <div className="flex items-center justify-between mb-1.5">
                  <span className="num text-sm font-semibold text-lumora-text">{sym}</span>
                  <Badge variant={status.variant}>{status.label}</Badge>
                </div>

                {m.error ? (
                  <p className="text-[11px] text-red-400">{m.error}</p>
                ) : !p ? (
                  <p className="text-[11px] text-lumora-muted">Loading…</p>
                ) : (
                  <>
                    <p className="num text-lg font-bold text-neon-cyan leading-tight">
                      {price !== null
                        ? `$${price.toLocaleString(undefined, { maximumFractionDigits: 2 })}`
                        : "—"}
                    </p>
                    <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 mt-2 text-[11px]">
                      <span className="text-lumora-muted">Cells</span>
                      <span className="num text-right text-lumora-text">{p.meta.cellCount}</span>
                      <span className="text-lumora-muted">Walls</span>
                      <span className="num text-right text-lumora-text">{p.meta.wallCount}</span>
                      <span className="text-lumora-muted">Source</span>
                      <span className="num text-right text-lumora-text">
                        {p.meta.source ?? p.meta.dataSource ?? "—"}
                      </span>
                    </div>
                    <div className="mt-2 space-y-1">
                      {bidWall && (
                        <div className="flex items-center gap-2 text-[11px]">
                          <Badge variant="green" className="text-[9px] px-1 py-0">BID</Badge>
                          <span className="num text-lumora-text">${bidWall.price_bucket.toLocaleString()}</span>
                          <span className="num text-lumora-muted ml-auto">
                            ${(bidWall.total_usd / 1_000_000).toFixed(2)}M
                          </span>
                        </div>
                      )}
                      {askWall && (
                        <div className="flex items-center gap-2 text-[11px]">
                          <Badge variant="red" className="text-[9px] px-1 py-0">ASK</Badge>
                          <span className="num text-lumora-text">${askWall.price_bucket.toLocaleString()}</span>
                          <span className="num text-lumora-muted ml-auto">
                            ${(askWall.total_usd / 1_000_000).toFixed(2)}M
                          </span>
                        </div>
                      )}
                    </div>
                    <p className="text-[10px] text-lumora-muted mt-2">
                      {p.meta.liveUpdatedAt ? `live ${fmtTime(p.meta.liveUpdatedAt)}` : "no live timestamp"}
                    </p>
                  </>
                )}
              </GlassCard>
            );
          })}
        </div>
      </div>

      {/* KPI strip */}
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3">
        {mockKpis.map((kpi) => (
          <KpiCard key={kpi.label} {...kpi} />
        ))}
      </div>

      {/* 2-col: setups + bias | right panel */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5 items-start">

        {/* Left column */}
        <div className="lg:col-span-2 space-y-5">
          {/* Top Setups */}
          <div>
            <h2 className="text-xs font-semibold uppercase tracking-widest text-lumora-muted flex items-center gap-2 mb-2">
              <TrendingUp className="h-3.5 w-3.5 text-lumora-purple" /> Top Market Setups
            </h2>
            <div className="space-y-2">
              {mockSetups.map((s) => (
                <GlassCard key={s.symbol} className="p-3">
                  <div className="flex items-start gap-4">
                    {/* Symbol + bias */}
                    <div className="shrink-0 w-28">
                      <p className="num text-sm font-semibold text-lumora-text">{s.symbol}</p>
                      <Badge
                        variant={s.bias === "LONG" ? "green" : s.bias === "SHORT" ? "red" : "muted"}
                        className="mt-1"
                      >
                        {s.bias}
                      </Badge>
                    </div>

                    {/* Reason + tags */}
                    <div className="flex-1 min-w-0">
                      <p className="text-xs text-lumora-text-dim leading-relaxed">{s.reason}</p>
                      <div className="flex flex-wrap gap-1 mt-1.5">
                        {s.tags.map((tag) => (
                          <span
                            key={tag}
                            className="text-[10px] px-1.5 py-0.5 rounded bg-lumora-border/50 text-lumora-muted"
                          >
                            {tag}
                          </span>
                        ))}
                      </div>
                    </div>

                    {/* Levels */}
                    <div className="shrink-0 grid grid-cols-2 gap-x-3 gap-y-0.5 text-xs num text-right">
                      <span className="text-lumora-muted">Entry</span>
                      <span className="text-lumora-text">{s.entry}</span>
                      <span className="text-lumora-muted">Target</span>
                      <span className="text-lumora-green">{s.target}</span>
                      <span className="text-lumora-muted">Stop</span>
                      <span className="text-lumora-red">{s.stop}</span>
                    </div>

                    {/* Confidence bar */}
                    <div className="shrink-0 w-12 text-right">
                      <div className="h-1.5 rounded-full bg-lumora-border overflow-hidden">
                        <div
                          className="h-full rounded-full bg-gradient-to-r from-lumora-purple to-lumora-cyan"
                          style={{ width: `${s.confidence}%` }}
                        />
                      </div>
                      <p className="num text-[11px] text-lumora-text-dim mt-1">{s.confidence}%</p>
                    </div>
                  </div>
                </GlassCard>
              ))}
            </div>
          </div>

          {/* Market Bias */}
          <div>
            <h2 className="text-xs font-semibold uppercase tracking-widest text-lumora-muted mb-2">Market Bias</h2>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {[
                { symbol: "BTC",  bias: "BULLISH",  strength: 84, icon: TrendingUp,  color: "text-lumora-green" },
                { symbol: "ETH",  bias: "BEARISH",  strength: 68, icon: TrendingDown, color: "text-lumora-red"   },
                { symbol: "SOL",  bias: "NEUTRAL",  strength: 55, icon: Minus,        color: "text-lumora-muted" },
                { symbol: "HYPE", bias: "BULLISH",  strength: 71, icon: TrendingUp,  color: "text-lumora-green" },
              ].map(({ symbol, bias, strength, icon: Icon, color }) => (
                <GlassCard key={symbol} className="p-3 flex items-center gap-3">
                  <Icon className={clsx("h-4 w-4 shrink-0", color)} />
                  <div className="flex-1 min-w-0">
                    <p className="num text-sm font-semibold text-lumora-text">{symbol}</p>
                    <p className={clsx("text-[11px] font-medium", color)}>{bias}</p>
                  </div>
                  <div className="shrink-0 w-10">
                    <div className="h-1 rounded-full bg-lumora-border overflow-hidden">
                      <div className="h-full rounded-full bg-lumora-purple" style={{ width: `${strength}%` }} />
                    </div>
                    <p className="num text-[10px] text-lumora-muted text-right mt-0.5">{strength}%</p>
                  </div>
                </GlassCard>
              ))}
            </div>
          </div>
        </div>

        {/* Right panel */}
        <div className="space-y-4">
          {/* Whale Alerts */}
          <GlassCard className="overflow-hidden">
            <div className="px-3 py-2.5 border-b border-lumora-border flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-widest text-lumora-muted flex items-center gap-1.5">
                <Zap className="h-3 w-3 text-lumora-cyan" /> Whale Alerts
              </span>
              <Badge variant="cyan">{mockWhaleAlerts.length}</Badge>
            </div>
            <div className="overflow-y-auto max-h-[272px] divide-y divide-lumora-border/40">
              {mockWhaleAlerts.map((a) => (
                <div key={a.id} className="px-3 py-2.5 hover:bg-lumora-surface/30 transition-colors">
                  <div className="flex items-center gap-2 mb-1">
                    <Badge variant={a.side === "BUY" ? "green" : "red"} className="w-10 justify-center shrink-0">
                      {a.side}
                    </Badge>
                    <span className="num text-xs font-semibold text-lumora-text">{a.symbol}</span>
                    <span className="text-[11px] text-lumora-muted">{a.type}</span>
                    <span className="ml-auto num text-xs font-semibold text-lumora-text">{a.size}</span>
                  </div>
                  <p className="text-[11px] text-lumora-muted leading-snug pl-12">{a.reason}</p>
                  <div className="flex items-center gap-1.5 mt-1 pl-12">
                    <Badge variant="muted" className="text-[10px]">{a.exchange}</Badge>
                    <Badge variant={a.risk === "HIGH" ? "red" : a.risk === "MEDIUM" ? "yellow" : "muted"} className="text-[10px]">
                      {a.risk}
                    </Badge>
                    <span className="num text-[10px] text-lumora-muted ml-auto">{a.time}</span>
                  </div>
                </div>
              ))}
            </div>
          </GlassCard>

          {/* Liquidity Walls */}
          <GlassCard className="overflow-hidden">
            <div className="px-3 py-2.5 border-b border-lumora-border flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-widest text-lumora-muted flex items-center gap-1.5">
                <Activity className="h-3 w-3 text-lumora-purple" /> Liquidity Walls
              </span>
              <Badge variant="purple">BTC</Badge>
            </div>
            <div className="divide-y divide-lumora-border/40">
              {mockLiquidityZones.slice(0, 5).map((z) => (
                <div key={z.price} className="px-3 py-2.5 flex items-center gap-2.5 hover:bg-lumora-surface/30 transition-colors">
                  <div
                    className="shrink-0 w-1.5 h-7 rounded-full"
                    style={{
                      background:
                        z.intensity > 80
                          ? "linear-gradient(180deg,#c084fc,#8b5cf6)"
                          : "linear-gradient(180deg,#22d3ee,#0891b2)",
                    }}
                  />
                  <div className="flex-1 min-w-0">
                    <p className="num text-xs font-medium text-lumora-text">${z.price.toLocaleString()}</p>
                    <p className="text-[11px] text-lumora-muted">{z.label}</p>
                  </div>
                  <div className="shrink-0 text-right space-y-0.5">
                    <Badge variant={z.side === "ASK" ? "red" : "green"}>{z.side}</Badge>
                    <p className="num text-[10px] text-lumora-text-dim">{z.intensity}%</p>
                  </div>
                </div>
              ))}
            </div>
          </GlassCard>
        </div>
      </div>
    </div>
  );
}
