"use client";

import { useState } from "react";
import { GlassCard } from "@/components/ui/GlassCard";
import { Badge } from "@/components/ui/Badge";
import { clsx } from "clsx";
import { RefreshCw, ChevronDown } from "lucide-react";

// ─── Layout constants ─────────────────────────────────────────────────────────

const CHART_H   = 520;   // chart body height (px)
const MIN_PRICE = 65_000;
const MAX_PRICE = 69_100;

// ─── Data ─────────────────────────────────────────────────────────────────────

const CURRENT_PRICE = 67_420;

const PRICE_LEVELS = [
  68_500, 68_200, 68_000, 67_800, 67_600,
  67_500, CURRENT_PRICE, 67_350, 67_200,
  67_000, 66_800, 66_500, 66_200, 65_800, 65_500,
];

const TIME_COLS = [
  "−60m", "−55m", "−50m", "−45m", "−40m", "−35m",
  "−30m", "−25m", "−20m", "−15m", "−10m", "−5m", "−2m", "Now",
];
const N_COLS = TIME_COLS.length;

/** Indices where a time-axis label is shown */
const TIME_AXIS_SHOW = new Set([0, 3, 6, 9, 11, N_COLS - 1]);

/** Price ticks on the Y-axis */
const PRICE_TICKS = [68_500, 68_000, 67_500, 67_000, 66_500, 66_000, 65_500];

const SYMBOLS   = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "HYPEUSDT"];
const EXCHANGES = ["Binance Spot", "Bybit Spot", "OKX Spot"];
const TIMEFRAMES = ["5m", "15m", "1h", "4h", "1D"] as const;

// ─── Zone definitions ─────────────────────────────────────────────────────────

interface Zone {
  price: number;
  side: "ASK" | "BID";
  intensity: number;
  label: string;
  badge: string;
  desc: string;
}

const ZONES: Zone[] = [
  { price: 68_000, side: "ASK", intensity: 95, badge: "WALL", label: "Major Ask Wall",  desc: "Large resting sell orders. Hard resistance, two rejections today." },
  { price: 67_500, side: "ASK", intensity: 72, badge: "RES",  label: "Spot Sell Wall",  desc: "Multiple sellers clustered. Watch for rejection on retest." },
  { price: 67_350, side: "BID", intensity: 88, badge: "WALL", label: "Major Bid Wall",  desc: "Held twice in the last hour — strong demand zone." },
  { price: 67_000, side: "BID", intensity: 80, badge: "SUP",  label: "Spot Buy Wall",   desc: "Aligns with daily structure. Key invalidation level." },
  { price: 66_500, side: "BID", intensity: 61, badge: "DMZ",  label: "Demand Zone",     desc: "Lighter bids. Could be swept before reversal." },
  { price: 66_200, side: "BID", intensity: 55, badge: "SWP",  label: "Sweep Zone",      desc: "Likely liquidation magnet on a downside flush." },
  { price: 65_800, side: "BID", intensity: 79, badge: "GAP",  label: "Liquidity Gap",   desc: "Thin orderbook. Fast price movement expected here." },
];

const PRICE_PATH: number[] = [
  67_200, 67_190, 67_270, 67_340, 67_350, 67_395,
  67_370, 67_405, 67_360, 67_415, 67_435, 67_410, 67_428, 67_420,
];

// ─── Pure helpers ─────────────────────────────────────────────────────────────

function priceToY(price: number): number {
  return ((MAX_PRICE - price) / (MAX_PRICE - MIN_PRICE)) * CHART_H;
}

/** Top y of a band — extends to chart top for first row, midpoint otherwise */
function bandTopY(idx: number): number {
  if (idx === 0) return 0;
  return priceToY((PRICE_LEVELS[idx - 1] + PRICE_LEVELS[idx]) / 2);
}

/** Bottom y of a band — extends to chart bottom for last row, midpoint otherwise */
function bandBottomY(idx: number): number {
  if (idx === PRICE_LEVELS.length - 1) return CHART_H;
  return priceToY((PRICE_LEVELS[idx] + PRICE_LEVELS[idx + 1]) / 2);
}

/**
 * Intensity palette — Bookmap/CoinGlass inspired on a dark background:
 *  empty → navy → blue → cyan → teal-green → green → yellow → orange → red-orange (critical wall)
 */
function heatBg(v: number): string {
  if (v <  5) return "rgba(10,8,22,0.60)";
  if (v < 15) return "rgba(14,24,72,0.78)";
  if (v < 28) return "rgba(18,56,140,0.84)";
  if (v < 42) return "rgba(10,100,190,0.87)";
  if (v < 55) return "rgba(0,150,180,0.89)";
  if (v < 68) return "rgba(0,170,100,0.91)";
  if (v < 80) return "rgba(50,190,40,0.93)";
  if (v < 90) return "rgba(200,200,0,0.95)";
  if (v < 95) return "rgba(240,120,0,0.96)";
  return       "rgba(255,60,30,0.98)"; // critical wall — red-orange
}

function cellIntensity(price: number, ci: number): number {
  const wall = ZONES.find((z) => z.price === price);
  if (wall) {
    const noise   = Math.sin(price * 0.0007 + ci * 0.38) * 5;
    const buildUp = ci < 5 ? ci * 0.7 : 0;
    const decay   = (N_COLS - 1 - ci) * 0.35;
    return Math.min(100, Math.max(wall.intensity * 0.68, wall.intensity + noise + buildUp - decay));
  }
  const nearest = ZONES.reduce((best, z) =>
    Math.abs(z.price - price) < Math.abs(best.price - price) ? z : best
  );
  const dist  = Math.abs(nearest.price - price);
  const spill = Math.max(0, 1 - dist / 360) * nearest.intensity * 0.28;
  const noise = Math.abs(Math.sin(price * 0.019 + ci * 0.57)) * 17;
  return Math.min(100, spill + noise);
}

/** CSS linear-gradient encoding intensity at every time column */
function bandGradient(price: number): string {
  const stops = TIME_COLS.map((_, ci) => {
    const v   = cellIntensity(price, ci);
    const pct = (ci / (N_COLS - 1)) * 100;
    return `${heatBg(v)} ${pct.toFixed(1)}%`;
  });
  return `linear-gradient(to right, ${stops.join(", ")})`;
}

// ─── Depth profile sidebar ────────────────────────────────────────────────────

function DepthProfile() {
  const lastCol = N_COLS - 1;
  const rows = PRICE_LEVELS.map((price) => ({
    price,
    intensity: cellIntensity(price, lastCol),
    zone: ZONES.find((z) => z.price === price),
    isCurrent: price === CURRENT_PRICE,
    isAsk: price > CURRENT_PRICE,
    isBid: price < CURRENT_PRICE,
  }));
  const maxI = Math.max(...rows.map((r) => r.intensity), 1);

  return (
    <div className="space-y-px py-1">
      {rows.map(({ price, intensity, zone, isCurrent, isAsk, isBid }) => (
        <div
          key={price}
          className={clsx(
            "relative h-[30px] flex items-center px-2 rounded-sm overflow-hidden",
            isCurrent && "ring-1 ring-lumora-cyan/50 bg-cyan-500/[0.08]"
          )}
        >
          <div
            className={clsx(
              "absolute inset-y-0 left-0 rounded-sm",
              isAsk ? "bg-red-500/35" : isBid ? "bg-green-500/30" : "bg-cyan-500/25"
            )}
            style={{ width: `${(intensity / maxI) * 100}%` }}
          />
          <span
            className={clsx(
              "relative num text-[10px] font-medium w-full text-right z-10 leading-none",
              isCurrent ? "text-lumora-cyan" : zone ? "text-lumora-purple-bright" : "text-lumora-muted"
            )}
          >
            {isCurrent ? `▶ ${price.toLocaleString()}` : price.toLocaleString()}
          </span>
        </div>
      ))}
    </div>
  );
}

// ─── Legend ───────────────────────────────────────────────────────────────────

const LEGEND_STEPS = [
  { v:  2, label: "Empty"  },
  { v: 10, label: ""       },
  { v: 22, label: "Low"    },
  { v: 35, label: ""       },
  { v: 48, label: "Med"    },
  { v: 62, label: ""       },
  { v: 75, label: "High"   },
  { v: 85, label: ""       },
  { v: 92, label: "Wall"   },
  { v: 97, label: "Crit."  },
];

function HeatLegend() {
  return (
    <div className="hidden md:flex items-end gap-0.5">
      {LEGEND_STEPS.map(({ v, label }) => (
        <div key={v} className="flex flex-col items-center gap-0.5" title={`~${v}% intensity`}>
          <div className="h-3 w-5 rounded-sm" style={{ background: heatBg(v) }} />
          {label
            ? <span className="text-[8px] text-lumora-muted leading-none whitespace-nowrap">{label}</span>
            : <span className="text-[8px] leading-none opacity-0">·</span>
          }
        </div>
      ))}
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function LiquidityMapPage() {
  const [symbol,    setSymbol]    = useState("BTCUSDT");
  const [exchange,  setExchange]  = useState("Binance Spot");
  const [timeframe, setTimeframe] = useState<string>("15m");

  const currentY = priceToY(CURRENT_PRICE);

  // SVG price-path points (viewBox 0 0 N_COLS−1 CHART_H, preserveAspectRatio=none)
  const svgPolyline = PRICE_PATH
    .map((p, ci) => `${ci},${priceToY(p).toFixed(2)}`)
    .join(" ");

  // SVG area-fill polygon: path → right-bottom → left-bottom
  const svgPolygon = [
    ...PRICE_PATH.map((p, ci) => `${ci},${priceToY(p).toFixed(2)}`),
    `${N_COLS - 1},${CHART_H}`,
    `0,${CHART_H}`,
  ].join(" ");

  return (
    <div className="space-y-4 animate-[fadeIn_0.4s_ease-out]">

      {/* ── Header ── */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-lumora-text">Liquidity Map</h1>
          <p className="text-sm text-lumora-muted mt-0.5">
            Spot orderbook liquidity over time — demo data, live depth history coming later
          </p>
        </div>
        <Badge variant="yellow">Demo Data</Badge>
      </div>

      {/* ── Controls ── */}
      <GlassCard className="p-2.5 flex flex-wrap items-center gap-2">
        <div className="relative">
          <select value={symbol} onChange={(e) => setSymbol(e.target.value)}
            className="appearance-none bg-lumora-bg border border-lumora-border text-lumora-text text-xs rounded-md px-2.5 py-1.5 pr-6 focus:outline-none focus:border-lumora-purple num cursor-pointer">
            {SYMBOLS.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <ChevronDown className="absolute right-1.5 top-2 h-3 w-3 text-lumora-muted pointer-events-none" />
        </div>
        <div className="relative">
          <select value={exchange} onChange={(e) => setExchange(e.target.value)}
            className="appearance-none bg-lumora-bg border border-lumora-border text-lumora-text text-xs rounded-md px-2.5 py-1.5 pr-6 focus:outline-none focus:border-lumora-purple cursor-pointer">
            {EXCHANGES.map((ex) => <option key={ex} value={ex}>{ex}</option>)}
          </select>
          <ChevronDown className="absolute right-1.5 top-2 h-3 w-3 text-lumora-muted pointer-events-none" />
        </div>
        <div className="h-4 w-px bg-lumora-border hidden sm:block" />
        <div className="flex rounded-md border border-lumora-border overflow-hidden">
          {TIMEFRAMES.map((tf) => (
            <button key={tf} onClick={() => setTimeframe(tf)}
              className={clsx("px-2.5 py-1.5 text-xs font-medium transition-colors",
                timeframe === tf ? "bg-lumora-purple text-white" : "text-lumora-muted hover:text-lumora-text bg-lumora-card")}>
              {tf}
            </button>
          ))}
        </div>
        <button onClick={() => {}} title="Refresh (demo)"
          className="p-1.5 rounded-md border border-lumora-border bg-lumora-card text-lumora-muted hover:text-lumora-text transition-colors">
          <RefreshCw className="h-3.5 w-3.5" />
        </button>
        <div className="ml-auto flex items-center gap-3">
          <HeatLegend />
          <div className="h-4 w-px bg-lumora-border hidden md:block" />
          <div className="flex items-center gap-1.5 text-[10px] text-lumora-muted">
            <span className="inline-block w-6 h-[1.5px] bg-white/65 rounded" />Price path
          </div>
          <div className="flex items-center gap-1.5 text-[10px] text-lumora-muted">
            <span className="inline-block w-2 h-2 rounded-full bg-lumora-cyan shadow-[0_0_5px_rgba(34,211,238,0.9)]" />Now
          </div>
        </div>
      </GlassCard>

      {/* ── Main: chart + depth ── */}
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_148px] gap-3 items-start">

        {/* Chart card */}
        <GlassCard className="overflow-hidden p-0">
          <div className="overflow-x-auto">
            <div style={{ minWidth: 560 }}>

              {/* Price Y-axis + chart body */}
              <div className="flex">

                {/* Y-axis */}
                <div
                  className="relative shrink-0 border-r border-lumora-border/30"
                  style={{ width: 64, height: CHART_H }}
                >
                  {/* Static price ticks */}
                  {PRICE_TICKS.map((p) => (
                    <div
                      key={p}
                      className="absolute right-2 num text-[10px] text-lumora-muted select-none -translate-y-1/2"
                      style={{ top: priceToY(p) }}
                    >
                      {(p / 1000).toFixed(1)}k
                    </div>
                  ))}
                  {/* Current price tick */}
                  <div
                    className="absolute right-0 left-0 flex items-center justify-end pr-2 select-none -translate-y-1/2"
                    style={{ top: currentY }}
                  >
                    <span className="num text-[10px] text-lumora-cyan font-semibold">
                      {CURRENT_PRICE.toLocaleString()}
                    </span>
                  </div>
                  {/* Y-axis horizontal guide lines */}
                  {PRICE_TICKS.map((p) => (
                    <div
                      key={`g-${p}`}
                      className="absolute left-0 right-0 h-px bg-lumora-border/20 pointer-events-none"
                      style={{ top: priceToY(p) }}
                    />
                  ))}
                </div>

                {/* Chart body */}
                <div
                  className="relative flex-1 overflow-hidden"
                  style={{ height: CHART_H, background: "#05030e" }}
                >
                  {/* Subtle horizontal guide lines (match Y-axis ticks) */}
                  {PRICE_TICKS.map((p) => (
                    <div
                      key={`gl-${p}`}
                      className="absolute left-0 right-0 h-px bg-white/[0.04] pointer-events-none"
                      style={{ top: priceToY(p) }}
                    />
                  ))}

                  {/* "Now" right-edge glow */}
                  <div className="absolute inset-y-0 right-0 w-px bg-lumora-cyan/30 pointer-events-none" />

                  {/* ── Liquidity bands ── */}
                  {PRICE_LEVELS.map((price, ri) => {
                    const top    = bandTopY(ri);
                    const height = bandBottomY(ri) - top;
                    const zone   = ZONES.find((z) => z.price === price);
                    const isWall = zone && zone.intensity >= 80;

                    return (
                      <div
                        key={price}
                        style={{
                          position: "absolute",
                          top,
                          left: 0,
                          right: 0,
                          height,
                          background: bandGradient(price),
                          ...(isWall && {
                            boxShadow:
                              zone.side === "ASK"
                                ? "0 0 14px rgba(255,60,30,0.20)"
                                : "0 0 14px rgba(50,200,50,0.18)",
                          }),
                        }}
                      />
                    );
                  })}

                  {/* ── SVG price path (stretches with container, path stays proportional) ── */}
                  <svg
                    className="absolute inset-0 w-full pointer-events-none"
                    style={{ height: CHART_H, zIndex: 18 }}
                    viewBox={`0 0 ${N_COLS - 1} ${CHART_H}`}
                    preserveAspectRatio="none"
                  >
                    <defs>
                      <linearGradient id="areaFill" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%"   stopColor="rgba(255,255,255,0.07)" />
                        <stop offset="100%" stopColor="rgba(255,255,255,0)"    />
                      </linearGradient>
                    </defs>
                    {/* Subtle area fill under path */}
                    <polygon points={svgPolygon} fill="url(#areaFill)" />
                    {/* Price path line */}
                    <polyline
                      points={svgPolyline}
                      fill="none"
                      stroke="rgba(255,255,255,0.72)"
                      strokeWidth="1.6"
                      strokeLinejoin="round"
                      strokeLinecap="round"
                    />
                  </svg>

                  {/* ── Price path dots (CSS — avoids SVG distortion) ── */}
                  {PRICE_PATH.map((p, ci) => {
                    const isNow = ci === N_COLS - 1;
                    return (
                      <div
                        key={ci}
                        className="absolute pointer-events-none"
                        style={{
                          left:      `${(ci / (N_COLS - 1)) * 100}%`,
                          top:       priceToY(p),
                          width:     isNow ? 10 : 5,
                          height:    isNow ? 10 : 5,
                          borderRadius: "50%",
                          transform: "translate(-50%, -50%)",
                          background: isNow ? "#22d3ee" : "rgba(255,255,255,0.70)",
                          boxShadow:  isNow
                            ? "0 0 8px rgba(34,211,238,1), 0 0 18px rgba(34,211,238,0.5)"
                            : "0 0 3px rgba(255,255,255,0.5)",
                          zIndex: 25,
                        }}
                      />
                    );
                  })}

                  {/* ── Current price line ── */}
                  <div
                    className="absolute left-0 right-0 pointer-events-none"
                    style={{
                      top:       currentY,
                      height:    1.5,
                      background: "rgba(34,211,238,0.9)",
                      boxShadow:  "0 0 8px rgba(34,211,238,0.8), 0 0 22px rgba(34,211,238,0.3)",
                      zIndex:    20,
                    }}
                  />
                  {/* Current price label (right edge) */}
                  <div
                    className="absolute right-2 num text-[10px] font-bold text-lumora-cyan pointer-events-none select-none -translate-y-1/2"
                    style={{ top: currentY, zIndex: 21 }}
                  >
                    ▶ {CURRENT_PRICE.toLocaleString()}
                  </div>

                  {/* ── Floating zone badges (left edge) ── */}
                  {ZONES.map((z) => {
                    const y      = priceToY(z.price);
                    const isAsk  = z.side === "ASK";
                    // nudge labels that are too close to the current-price line
                    const tooClose = Math.abs(y - currentY) < 16;
                    const nudgeY   = tooClose ? (y < currentY ? y - 12 : y + 4) : y;

                    return (
                      <div
                        key={z.price}
                        className="absolute left-2 flex items-center gap-1 pointer-events-none"
                        style={{ top: nudgeY - 9, zIndex: 15 }}
                      >
                        <span
                          className={clsx(
                            "text-[9px] font-bold px-1.5 rounded leading-[14px]",
                            isAsk
                              ? "bg-red-500/75 text-white"
                              : z.intensity >= 80
                              ? "bg-green-500/75 text-white"
                              : "bg-green-500/45 text-green-200"
                          )}
                        >
                          {z.badge}
                        </span>
                        <span
                          className={clsx(
                            "text-[10px] font-medium hidden sm:block",
                            isAsk ? "text-red-300/80" : "text-green-300/80"
                          )}
                        >
                          {z.label}
                        </span>
                      </div>
                    );
                  })}
                </div>{/* end chart body */}
              </div>{/* end flex row */}

              {/* ── Time X-axis ── */}
              <div
                className="flex border-t border-lumora-border/30"
                style={{ marginLeft: 64 }}
              >
                {TIME_COLS.map((t, ci) => (
                  <div key={t} className="flex-1 py-1.5 text-center">
                    {TIME_AXIS_SHOW.has(ci) && (
                      <span
                        className={clsx(
                          "text-[9px] uppercase tracking-wide select-none",
                          t === "Now" ? "text-lumora-cyan font-semibold" : "text-lumora-muted"
                        )}
                      >
                        {t}
                      </span>
                    )}
                  </div>
                ))}
              </div>

            </div>
          </div>
        </GlassCard>

        {/* Depth profile */}
        <GlassCard className="overflow-hidden">
          <div className="px-3 py-2.5 border-b border-lumora-border flex items-center justify-between">
            <span className="text-[11px] text-lumora-muted uppercase tracking-wide font-medium">Depth</span>
            <span className="text-[10px] text-lumora-cyan">Now</span>
          </div>
          <div className="px-1.5 py-1.5">
            <DepthProfile />
          </div>
          <div className="px-3 pb-3 pt-1 flex flex-col gap-1">
            <div className="flex items-center gap-1.5 text-[10px] text-lumora-muted">
              <div className="w-3 h-2 rounded-sm bg-red-500/40 shrink-0" />Asks
            </div>
            <div className="flex items-center gap-1.5 text-[10px] text-lumora-muted">
              <div className="w-3 h-2 rounded-sm bg-green-500/35 shrink-0" />Bids
            </div>
            <div className="flex items-center gap-1.5 text-[10px] text-lumora-muted">
              <div className="w-3 h-2 rounded-sm bg-cyan-500/30 shrink-0" />Price
            </div>
          </div>
        </GlassCard>
      </div>

      {/* ── Zone detail cards ── */}
      <div>
        <h2 className="text-xs font-semibold uppercase tracking-widest text-lumora-muted mb-2">Key Zones</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {ZONES.slice(0, 4).map((z) => (
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
          ))}
        </div>
      </div>

      {/* ── Summary cards ── */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        {[
          { label: "Strongest Bid Zone", value: "$67,350", sub: "88% intensity · held 40m",    color: "text-lumora-green" },
          { label: "Strongest Ask Zone", value: "$68,000", sub: "95% intensity · major wall",  color: "text-lumora-red"   },
          { label: "Liquidity Gap",      value: "$65,800", sub: "Thin below $66,200",          color: "text-yellow-400"   },
          { label: "Current Bias",       value: "BULLISH", sub: "Bid dominant · +0.42 imbal",  color: "text-lumora-purple-bright" },
          { label: "Watch Action",       value: "Hold $67,350", sub: "Break → flush to $66,500", color: "text-lumora-cyan" },
        ].map(({ label, value, sub, color }) => (
          <GlassCard key={label} className="p-3">
            <p className="text-[11px] text-lumora-muted uppercase tracking-wide mb-1.5">{label}</p>
            <p className={clsx("num text-sm font-semibold", color)}>{value}</p>
            <p className="text-[11px] text-lumora-muted mt-1 leading-snug">{sub}</p>
          </GlassCard>
        ))}
      </div>

    </div>
  );
}
