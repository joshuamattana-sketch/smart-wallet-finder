"use client";

import { useState, useEffect, useCallback } from "react";
import { GlassCard } from "@/components/ui/GlassCard";
import { Badge } from "@/components/ui/Badge";
import { clsx } from "clsx";
import { RefreshCw, ChevronDown, AlertCircle } from "lucide-react";
import type { HeatmapApiPayload } from "@/lib/heatmap-types";
import { HeatmapCanvas } from "@/components/liquidity/HeatmapCanvas";

// ── Layout constants ───────────────────────────────────────────────────────────
const CHART_H   = 560;
const MIN_PRICE = 65_000;
const MAX_PRICE = 69_500;
const PRICE_RNG = MAX_PRICE - MIN_PRICE;
const CURRENT_PRICE = 67_420;

const SYMBOLS    = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "HYPEUSDT", "XMRUSDT"];
const EXCHANGES  = ["Binance Spot", "Bybit Spot", "OKX Spot"];
const TIMEFRAMES = ["5m", "15m", "1h", "4h", "1D"] as const;

// ── Helpers ────────────────────────────────────────────────────────────────────
function py(price: number) {
  return ((MAX_PRICE - price) / PRICE_RNG) * 100;
}
function pyPx(price: number) {
  return ((MAX_PRICE - price) / PRICE_RNG) * CHART_H;
}

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

// ── Band generation ────────────────────────────────────────────────────────────
interface LiqBand {
  topPct:   number;
  leftPct:  number;
  heightPx: number;
  color:    string;
  shadow?:  string;
}

function buildBands(): LiqBand[] {
  const out: LiqBand[] = [];
  const STEP = 25;

  for (let price = MIN_PRICE + STEP; price < MAX_PRICE; price += STEP) {
    const near = ZONES.reduce((b, z) =>
      Math.abs(z.price - price) < Math.abs(b.price - price) ? z : b
    );
    const dist  = Math.abs(near.price - price);
    const spill = Math.max(0, (1 - dist / 420) * near.intensity);
    const n1    = Math.abs(Math.sin(price * 0.00917 + 2.14)) * 22;
    const n2    = Math.abs(Math.sin(price * 0.02311 + 0.87)) * 9;
    const base  = Math.min(100, spill * 0.82 + n1 * 0.35 + n2 * 0.25);

    if (base < 6) continue;

    const layers = base > 78 ? 5 : base > 55 ? 4 : base > 32 ? 3 : 2;

    for (let b = 0; b < layers; b++) {
      const s1 = Math.sin(price * 0.00413 + b * 2.31);
      const s2 = Math.cos(price * 0.00831 + b * 1.74);
      const leftPct  = Math.max(0, Math.min(72, Math.abs(s1) * 60 + b * 5));
      const bandI    = Math.min(100, base * (0.72 + Math.abs(s2) * 0.32));
      const heightPx = bandI > 84 ? 7 : bandI > 62 ? 5 : bandI > 38 ? 3 : 2;
      const color    = iColor(bandI);

      let shadow: string | undefined;
      if (bandI > 82) {
        shadow = near.side === "ASK"
          ? "0 0 10px rgba(255,90,30,0.45), 0 0 20px rgba(255,90,30,0.20)"
          : "0 0 10px rgba(30,220,80,0.40), 0 0 20px rgba(30,220,80,0.18)";
      } else if (bandI > 65) {
        shadow = "0 0 6px rgba(0,180,220,0.30)";
      }

      out.push({ topPct: py(price), leftPct, heightPx, color, shadow });
    }
  }

  return out;
}

const BANDS = buildBands();

// ── Price path ─────────────────────────────────────────────────────────────────
const RAW_PATH = [
  67_180, 67_200, 67_175, 67_230, 67_270, 67_310, 67_340, 67_355,
  67_390, 67_370, 67_405, 67_380, 67_415, 67_400, 67_360, 67_385,
  67_410, 67_430, 67_420, 67_435, 67_445, 67_415, 67_428, 67_438,
  67_420, 67_425, 67_418, 67_420,
];
const N_PTS = RAW_PATH.length;

const Y_TICKS = [69_000, 68_500, 68_000, 67_500, 67_000, 66_500, 66_000, 65_500];

const TIME_AXIS: Array<{ label: string; pct: number }> = [
  { label: "−60m", pct:  0 },
  { label: "−45m", pct: 25 },
  { label: "−30m", pct: 50 },
  { label: "−15m", pct: 75 },
  { label: " −5m", pct: 90 },
  { label:  "Now", pct: 100 },
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

  const [payload,  setPayload]  = useState<HeatmapApiPayload | null>(null);
  const [loading,  setLoading]  = useState(false);
  const [apiError, setApiError] = useState<string | null>(null);

  const fetchPayload = useCallback(async () => {
    setLoading(true);
    setApiError(null);
    try {
      const tf  = timeframe.toLowerCase();
      const exSlug = exchangeToApiSlug(exchange);
      const res = await fetch(
        `/api/heatmap?symbol=${encodeURIComponent(symbol)}&exchange=${encodeURIComponent(exSlug)}&timeframe=${encodeURIComponent(tf)}`
      );
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        setApiError((body as { message?: string }).message ?? `API error ${res.status}`);
        return;
      }
      const data: HeatmapApiPayload = await res.json();
      setPayload(data);
    } catch (err) {
      setApiError(err instanceof Error ? err.message : "Network error");
    } finally {
      setLoading(false);
    }
  }, [symbol, exchange, timeframe]);

  useEffect(() => { fetchPayload(); }, [fetchPayload]);

  const curY   = pyPx(CURRENT_PRICE);
  const svgLine = RAW_PATH.map((p, i) => `${i},${pyPx(p).toFixed(1)}`).join(" ");

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

  // Unsupported-source note — driven by the payload when present, with a
  // symbol-based fallback so the hint appears immediately on selection.
  const sourceNote =
    payload?.meta.sourceNote ??
    (symbol === "XMRUSDT"
      ? "XMR source planned. Binance Spot depth unavailable for Monero."
      : null);

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
        {isDemo && <Badge variant="yellow">Demo Data</Badge>}
      </div>

      {/* Controls */}
      <GlassCard className="p-2.5 flex flex-wrap items-center gap-2">
        {/* Symbol */}
        <div className="relative">
          <select value={symbol} onChange={e => setSymbol(e.target.value)}
            className="appearance-none bg-lumora-bg border border-lumora-border text-lumora-text text-xs rounded-md px-2.5 py-1.5 pr-6 focus:outline-none focus:border-lumora-purple num cursor-pointer">
            {SYMBOLS.map(s => <option key={s} value={s}>{s}</option>)}
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
        {/* Refresh */}
        <button onClick={fetchPayload} title="Refresh"
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

      {/* API error banner */}
      {apiError && (
        <div className="flex items-center gap-2 px-3 py-2.5 rounded-lg border border-red-500/30 bg-red-500/10 text-red-300 text-xs">
          <AlertCircle className="h-3.5 w-3.5 shrink-0" />
          <span>{apiError}</span>
        </div>
      )}

      {/* Unsupported-source note (e.g. XMR planned, no Binance Spot depth) */}
      {sourceNote && (
        <div className="flex items-center gap-2 px-3 py-2 rounded-lg border border-yellow-500/30 bg-yellow-500/10 text-yellow-300 text-xs">
          <AlertCircle className="h-3.5 w-3.5 shrink-0" />
          <span>{sourceNote}</span>
        </div>
      )}

      {/* Main: chart + depth sidebar */}
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_160px] gap-3 items-start">

        {/* Chart card */}
        <GlassCard className="overflow-hidden p-0">
          <div className="overflow-x-auto">
            <div style={{ minWidth: 560 }}>

              {/* Y-axis + chart body */}
              <div className="flex">

                {/* Y-axis */}
                <div
                  className="relative shrink-0 border-r border-lumora-border/25"
                  style={{ width: 62, height: CHART_H }}
                >
                  {Y_TICKS.map(p => (
                    <div key={p}
                      className="absolute right-2 num text-[10px] text-lumora-muted select-none -translate-y-1/2"
                      style={{ top: pyPx(p) }}>
                      {(p / 1000).toFixed(1)}k
                    </div>
                  ))}
                  <div
                    className="absolute right-1 num text-[10px] text-lumora-cyan font-semibold select-none -translate-y-1/2 leading-none"
                    style={{ top: curY }}>
                    {(CURRENT_PRICE / 1000).toFixed(2)}k
                  </div>
                </div>

                {/* Chart body */}
                <div
                  className="relative flex-1 overflow-hidden"
                  style={{ height: CHART_H, background: "#05030f" }}
                >
                  {/* Loading overlay — no layout jump */}
                  {loading && (
                    <div className="absolute inset-0 z-40 flex items-center justify-center bg-black/30 backdrop-blur-[1px]">
                      <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-lumora-card/80 border border-lumora-border text-lumora-muted text-xs">
                        <RefreshCw className="h-3 w-3 animate-spin" />
                        Loading…
                      </div>
                    </div>
                  )}

                  {Y_TICKS.map(p => (
                    <div key={p} className="absolute left-0 right-0 h-px bg-white/[0.035] pointer-events-none"
                      style={{ top: pyPx(p) }} />
                  ))}
                  <div className="absolute inset-y-0 right-0 w-px bg-lumora-cyan/25 pointer-events-none" />

                  {/* Liquidity bands */}
                  {BANDS.map((band, idx) => (
                    <div
                      key={idx}
                      className="absolute pointer-events-none"
                      style={{
                        top:       `${band.topPct}%`,
                        left:      `${band.leftPct}%`,
                        right:     0,
                        height:    band.heightPx,
                        background: band.color,
                        transform: "translateY(-50%)",
                        boxShadow: band.shadow,
                        borderRadius: "1px 0 0 1px",
                      }}
                    />
                  ))}

                  {/* SVG price line */}
                  <svg
                    className="absolute inset-0 w-full pointer-events-none"
                    style={{ height: CHART_H, zIndex: 20 }}
                    viewBox={`0 0 ${N_PTS - 1} ${CHART_H}`}
                    preserveAspectRatio="none"
                  >
                    <defs>
                      <filter id="priceglow">
                        <feGaussianBlur stdDeviation="1.5" result="blur" />
                        <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
                      </filter>
                    </defs>
                    <polyline
                      points={svgLine}
                      fill="none"
                      stroke="rgba(255,255,255,0.80)"
                      strokeWidth="1.5"
                      strokeLinejoin="round"
                      strokeLinecap="round"
                      filter="url(#priceglow)"
                    />
                    {RAW_PATH.slice(0, -1).map((p, i) => {
                      if (RAW_PATH[i + 1] >= p) return null;
                      return (
                        <line key={i}
                          x1={i} y1={pyPx(p).toFixed(1)}
                          x2={i + 1} y2={pyPx(RAW_PATH[i + 1]).toFixed(1)}
                          stroke="rgba(248,113,113,0.85)" strokeWidth="1.8"
                          strokeLinecap="round" />
                      );
                    })}
                  </svg>

                  {/* "Now" price dot */}
                  <div
                    className="absolute pointer-events-none"
                    style={{
                      right: 2, top: curY, width: 10, height: 10,
                      borderRadius: "50%", transform: "translate(0, -50%)",
                      background: "#22d3ee",
                      boxShadow: "0 0 8px rgba(34,211,238,1), 0 0 20px rgba(34,211,238,0.55)",
                      zIndex: 30,
                    }}
                  />
                  {/* Current price line */}
                  <div
                    className="absolute left-0 right-0 pointer-events-none"
                    style={{
                      top: curY, height: 1.5,
                      background: "rgba(34,211,238,0.85)",
                      boxShadow: "0 0 8px rgba(34,211,238,0.7), 0 0 24px rgba(34,211,238,0.25)",
                      zIndex: 22,
                    }}
                  />
                  <div
                    className="absolute right-3 num text-[10px] font-bold text-lumora-cyan pointer-events-none select-none -translate-y-full"
                    style={{ top: curY - 2, zIndex: 23 }}>
                    ▶ {CURRENT_PRICE.toLocaleString()}
                  </div>

                  {/* Zone overlay badges */}
                  {ZONES.map(z => {
                    const y      = pyPx(z.price);
                    const isAsk  = z.side === "ASK";
                    const yAdj   = Math.abs(y - curY) < 18 ? (y < curY ? y - 14 : y + 5) : y;
                    return (
                      <div key={z.price}
                        className="absolute left-2 flex items-center gap-1 pointer-events-none"
                        style={{ top: yAdj - 9, zIndex: 18 }}>
                        <span className={clsx(
                          "text-[9px] font-bold px-1.5 py-0.5 rounded leading-none",
                          isAsk
                            ? "bg-red-500/80 text-white"
                            : z.intensity >= 80
                            ? "bg-emerald-500/80 text-white"
                            : "bg-emerald-600/55 text-emerald-200"
                        )}>
                          {z.badge}
                        </span>
                        <span className={clsx(
                          "text-[10px] font-medium hidden sm:block",
                          isAsk ? "text-red-300/85" : "text-emerald-300/80"
                        )}>
                          {z.label}
                        </span>
                      </div>
                    );
                  })}

                </div>{/* end chart body */}
              </div>

              {/* Time X-axis */}
              <div className="relative border-t border-lumora-border/25" style={{ marginLeft: 62, height: 24 }}>
                {TIME_AXIS.map(({ label, pct }) => (
                  <span
                    key={label}
                    className={clsx(
                      "absolute -translate-x-1/2 top-1.5 num text-[9px] uppercase tracking-wide select-none",
                      pct === 100 ? "text-lumora-cyan font-semibold" : "text-lumora-muted"
                    )}
                    style={{ left: `${pct}%` }}
                  >
                    {label.trim()}
                  </span>
                ))}
              </div>

            </div>
          </div>
        </GlassCard>

        {/* Depth sidebar */}
        <GlassCard className="overflow-hidden p-0">
          <div className="px-3 py-2 border-b border-lumora-border flex items-center justify-between">
            <span className="text-[11px] text-lumora-muted uppercase tracking-wide font-medium">Depth Profile</span>
            <span className="text-[10px] text-lumora-cyan font-medium">Now</span>
          </div>
          <div className="px-1.5 py-1.5 overflow-y-auto" style={{ maxHeight: CHART_H }}>
            <DepthProfile />
          </div>
          <div className="px-3 py-2 border-t border-lumora-border flex flex-col gap-1.5">
            <div className="flex items-center gap-1.5 text-[10px] text-lumora-muted">
              <div className="w-4 h-2.5 rounded-sm shrink-0" style={{ background: iColor(85) }} />Asks
            </div>
            <div className="flex items-center gap-1.5 text-[10px] text-lumora-muted">
              <div className="w-4 h-2.5 rounded-sm shrink-0" style={{ background: iColor(75) }} />Bids
            </div>
            <div className="flex items-center gap-1.5 text-[10px] text-lumora-muted">
              <div className="w-4 h-1.5 rounded-sm shrink-0 bg-lumora-cyan/60" />Price
            </div>
          </div>
        </GlassCard>

      </div>

      {/* Canvas Renderer v1 — renders the live /api/heatmap payload on an HTML
          canvas. The legacy DOM map above stays unchanged; this is the new
          technical foundation. */}
      <GlassCard className="overflow-hidden p-0">
        <div className="px-3 py-2 border-b border-lumora-border flex items-center justify-between">
          <span className="text-[11px] text-lumora-muted uppercase tracking-wide font-medium">
            Canvas Renderer v1
          </span>
          <span className="text-[10px] text-lumora-muted">
            {payload ? `${payload.meta.cellCount} cells · ${payload.meta.wallCount} walls` : "—"}
          </span>
        </div>
        <div className="relative">
          {payload ? (
            <HeatmapCanvas
              payload={payload}
              height={CHART_H}
              currentPrice={CURRENT_PRICE}
              showDebug
            />
          ) : (
            <div
              className="flex items-center justify-center text-xs text-lumora-muted"
              style={{ height: CHART_H, background: "#05030f" }}
            >
              {loading ? "Loading heatmap…" : apiError ? "No payload" : "Waiting for data…"}
            </div>
          )}
        </div>
      </GlassCard>

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
