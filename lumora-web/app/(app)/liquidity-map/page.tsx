"use client";

import { useState } from "react";
import { GlassCard } from "@/components/ui/GlassCard";
import { Badge } from "@/components/ui/Badge";
import { clsx } from "clsx";
import { RefreshCw, ChevronDown } from "lucide-react";

// ─── Static config ────────────────────────────────────────────────────────────

const CURRENT_PRICE = 67_420;

/** Price rows — high to low, current price included as its own row */
const PRICE_LEVELS = [
  68_500, 68_200, 68_000, 67_800, 67_600,
  67_500, CURRENT_PRICE, 67_350, 67_200,
  67_000, 66_800, 66_500, 66_200, 65_800, 65_500,
];

/** Time columns — oldest left, newest right */
const TIME_COLS = [
  "−60m", "−55m", "−50m", "−45m", "−40m", "−35m",
  "−30m", "−25m", "−20m", "−15m", "−10m", "−5m", "−2m", "Now",
];

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
  { price: 67_500, side: "ASK", intensity: 72, badge: "RES",  label: "Ask Resistance",  desc: "Multiple sellers clustered. Watch for rejection on retest." },
  { price: 67_350, side: "BID", intensity: 88, badge: "WALL", label: "Major Bid Wall",  desc: "Held twice in the last hour — strong demand zone." },
  { price: 67_000, side: "BID", intensity: 80, badge: "SUP",  label: "Support Floor",   desc: "Aligns with daily structure. Key invalidation level." },
  { price: 66_500, side: "BID", intensity: 61, badge: "DMZ",  label: "Demand Zone",     desc: "Lighter bids. Could be swept before reversal." },
  { price: 66_200, side: "BID", intensity: 55, badge: "SWP",  label: "Sweep Zone",      desc: "Likely liquidation magnet on a downside flush." },
  { price: 65_800, side: "BID", intensity: 79, badge: "GAP",  label: "Liquidity Gap",   desc: "Thin orderbook. Fast price movement expected here." },
];

/** Mock price path: price value at each TIME_COL index */
const PRICE_PATH: number[] = [
  67_200, 67_190, 67_270, 67_340, 67_350, 67_395,
  67_370, 67_405, 67_360, 67_415, 67_435, 67_410, 67_428, 67_420,
];

// ─── Color & intensity helpers ────────────────────────────────────────────────

/**
 * Professional liquidity heatmap palette — Bookmap/CoinGlass inspired,
 * tuned to Lumora's dark background:
 *
 *  0–4  %  empty          near-black / deep purple bg
 *  5–14 %  low            dark navy blue
 * 15–27 %  low-med        medium blue
 * 28–41 %  medium         bright blue → cyan
 * 42–54 %  med-high       teal / cyan
 * 55–67 %  high           green
 * 68–79 %  strong         lime green
 * 80–89 %  very strong    yellow-green / yellow
 * 90–94 %  near-critical  orange
 * 95+  %  critical wall   bright red-orange / near-white edge
 */
function heatBg(v: number): string {
  if (v <  5) return "rgba(10,8,22,0.60)";           // empty — near-black
  if (v < 15) return "rgba(14,24,72,0.78)";           // low — dark navy
  if (v < 28) return "rgba(18,56,140,0.84)";          // low-med — medium blue
  if (v < 42) return "rgba(10,100,190,0.87)";         // medium — bright blue
  if (v < 55) return "rgba(0,150,180,0.89)";          // med-high — cyan
  if (v < 68) return "rgba(0,170,100,0.91)";          // high — teal-green
  if (v < 80) return "rgba(50,190,40,0.93)";          // strong — green
  if (v < 90) return "rgba(200,200,0,0.95)";          // very strong — yellow
  if (v < 95) return "rgba(240,120,0,0.96)";          // near-critical — orange
  return      "rgba(255,60,30,0.98)";                 // critical wall — red-orange
}

/** Per-cell intensity: walls are persistent; background has noise + spill */
function cellIntensity(price: number, ci: number): number {
  const wall = ZONES.find((z) => z.price === price);
  if (wall) {
    const noise   = Math.sin(price * 0.0007 + ci * 0.38) * 5;
    const buildUp = ci < 5 ? ci * 0.7 : 0;
    const decay   = (TIME_COLS.length - 1 - ci) * 0.35;
    return Math.min(100, Math.max(wall.intensity * 0.68, wall.intensity + noise + buildUp - decay));
  }
  const nearest = ZONES.reduce((best, z) =>
    Math.abs(z.price - price) < Math.abs(best.price - price) ? z : best
  );
  const dist   = Math.abs(nearest.price - price);
  const spill  = Math.max(0, 1 - dist / 360) * nearest.intensity * 0.28;
  const noise  = Math.abs(Math.sin(price * 0.019 + ci * 0.57)) * 17;
  return Math.min(100, spill + noise);
}

/** True if this cell falls on the mock price path (within one row-step) */
function onPricePath(price: number, ci: number): boolean {
  return ci < PRICE_PATH.length && Math.abs(PRICE_PATH[ci] - price) < 115;
}

// ─── Depth Profile sidebar ────────────────────────────────────────────────────

function DepthProfile() {
  const lastCol = TIME_COLS.length - 1;
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
      {rows.map(({ price, intensity, zone, isCurrent, isAsk, isBid }) => {
        const barPct = (intensity / maxI) * 100;
        return (
          <div
            key={price}
            className={clsx(
              "relative h-[30px] flex items-center px-2 rounded-sm overflow-hidden",
              isCurrent && "ring-1 ring-lumora-cyan/50 bg-cyan-500/8"
            )}
          >
            {/* depth bar */}
            <div
              className={clsx(
                "absolute inset-y-0 left-0 rounded-sm",
                isAsk ? "bg-red-500/35" : isBid ? "bg-green-500/30" : "bg-cyan-500/25"
              )}
              style={{ width: `${barPct}%` }}
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
        );
      })}
    </div>
  );
}

// ─── Legend gradient ──────────────────────────────────────────────────────────

const LEGEND_STEPS = [
  { v:  2, label: "Empty"    },
  { v: 10, label: "Low"      },
  { v: 22, label: ""         },
  { v: 35, label: "Medium"   },
  { v: 48, label: ""         },
  { v: 62, label: "High"     },
  { v: 75, label: ""         },
  { v: 85, label: "Strong"   },
  { v: 92, label: "Critical" },
  { v: 97, label: "Wall"     },
];

function HeatLegend() {
  return (
    <div className="hidden md:flex items-center gap-0.5">
      {LEGEND_STEPS.map(({ v, label }) => (
        <div key={v} className="flex flex-col items-center gap-0.5" title={`~${v}% intensity`}>
          <div
            className="h-3 w-5 rounded-sm"
            style={{ background: heatBg(v) }}
          />
          {label && (
            <span className="text-[8px] text-lumora-muted leading-none">{label}</span>
          )}
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

      {/* ── Controls bar ── */}
      <GlassCard className="p-2.5 flex flex-wrap items-center gap-2">
        {/* Symbol */}
        <div className="relative">
          <select
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            className="appearance-none bg-lumora-bg border border-lumora-border text-lumora-text text-xs rounded-md px-2.5 py-1.5 pr-6 focus:outline-none focus:border-lumora-purple num cursor-pointer"
          >
            {SYMBOLS.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <ChevronDown className="absolute right-1.5 top-2 h-3 w-3 text-lumora-muted pointer-events-none" />
        </div>

        {/* Exchange */}
        <div className="relative">
          <select
            value={exchange}
            onChange={(e) => setExchange(e.target.value)}
            className="appearance-none bg-lumora-bg border border-lumora-border text-lumora-text text-xs rounded-md px-2.5 py-1.5 pr-6 focus:outline-none focus:border-lumora-purple cursor-pointer"
          >
            {EXCHANGES.map((ex) => <option key={ex} value={ex}>{ex}</option>)}
          </select>
          <ChevronDown className="absolute right-1.5 top-2 h-3 w-3 text-lumora-muted pointer-events-none" />
        </div>

        <div className="h-4 w-px bg-lumora-border hidden sm:block" />

        {/* Timeframe */}
        <div className="flex rounded-md border border-lumora-border overflow-hidden">
          {TIMEFRAMES.map((tf) => (
            <button
              key={tf}
              onClick={() => setTimeframe(tf)}
              className={clsx(
                "px-2.5 py-1.5 text-xs font-medium transition-colors",
                timeframe === tf
                  ? "bg-lumora-purple text-white"
                  : "text-lumora-muted hover:text-lumora-text bg-lumora-card"
              )}
            >
              {tf}
            </button>
          ))}
        </div>

        {/* Refresh mock */}
        <button
          onClick={() => {}}
          className="p-1.5 rounded-md border border-lumora-border bg-lumora-card text-lumora-muted hover:text-lumora-text transition-colors"
          title="Refresh (demo)"
        >
          <RefreshCw className="h-3.5 w-3.5" />
        </button>

        <div className="ml-auto flex items-center gap-3">
          <HeatLegend />
          <div className="h-4 w-px bg-lumora-border hidden md:block" />
          <div className="flex items-center gap-1.5 text-[10px] text-lumora-muted">
            <span className="h-2 w-2 rounded-full bg-white/70 inline-block" />
            Price path
          </div>
          <div className="flex items-center gap-1.5 text-[10px] text-lumora-muted">
            <span className="h-2 w-2 rounded-full bg-lumora-cyan shadow-[0_0_4px_rgba(34,211,238,0.8)] inline-block" />
            Now
          </div>
        </div>
      </GlassCard>

      {/* ── Main area: heatmap + depth profile ── */}
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_148px] gap-3 items-start">

        {/* Heatmap */}
        <GlassCard className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full border-collapse" style={{ minWidth: "640px" }}>
              <thead>
                <tr className="border-b border-lumora-border/50">
                  {/* Price axis header */}
                  <th className="w-20 px-2 py-2 text-left text-[10px] text-lumora-muted uppercase tracking-wider sticky left-0 bg-lumora-card z-10">
                    Price
                  </th>
                  {TIME_COLS.map((t) => (
                    <th
                      key={t}
                      className={clsx(
                        "px-px py-2 text-center text-[9px] uppercase tracking-wide font-medium",
                        t === "Now" ? "text-lumora-cyan" : "text-lumora-muted"
                      )}
                    >
                      {t}
                    </th>
                  ))}
                  <th className="px-2 py-2 text-left text-[10px] text-lumora-muted uppercase tracking-wider min-w-[148px]">
                    Zone
                  </th>
                </tr>
              </thead>

              <tbody>
                {PRICE_LEVELS.map((price) => {
                  const zone      = ZONES.find((z) => z.price === price);
                  const isCurrent = price === CURRENT_PRICE;

                  return (
                    <tr
                      key={price}
                      className={clsx("group", isCurrent && "bg-cyan-500/[0.04]")}
                    >
                      {/* Price label */}
                      <td
                        className={clsx(
                          "px-2 py-0 num text-xs font-semibold sticky left-0 z-10 h-[34px] align-middle",
                          isCurrent
                            ? "text-lumora-cyan bg-cyan-500/[0.10]"
                            : zone
                            ? "text-lumora-purple-bright bg-lumora-card"
                            : "text-lumora-text-dim bg-lumora-card"
                        )}
                      >
                        {isCurrent ? (
                          <span className="flex items-center gap-1.5">
                            <span className="h-1.5 w-1.5 rounded-full bg-lumora-cyan shrink-0 shadow-[0_0_4px_rgba(34,211,238,0.8)]" />
                            {price.toLocaleString()}
                          </span>
                        ) : (
                          price.toLocaleString()
                        )}
                      </td>

                      {/* Heat cells */}
                      {TIME_COLS.map((_, ci) => {
                        const v      = cellIntensity(price, ci);
                        const onPath = onPricePath(price, ci);
                        const isNow  = ci === TIME_COLS.length - 1;

                        return (
                          <td
                            key={ci}
                            className="px-px py-px"
                            title={`$${price.toLocaleString()} · ${TIME_COLS[ci]} · ${v.toFixed(0)}% intensity`}
                          >
                            <div
                              className={clsx(
                                "relative h-[34px] rounded-[2px] transition-opacity duration-100 group-hover:opacity-80",
                                isNow && "ring-1 ring-inset ring-white/10"
                              )}
                              style={{ background: heatBg(v) }}
                            >
                              {onPath && (
                                <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                                  <div
                                    className={clsx(
                                      "rounded-full transition-all",
                                      isCurrent
                                        ? "w-2 h-2 bg-lumora-cyan shadow-[0_0_8px_rgba(34,211,238,1)]"
                                        : "w-1.5 h-1.5 bg-white/75 shadow-[0_0_4px_rgba(255,255,255,0.75)]"
                                    )}
                                  />
                                </div>
                              )}
                            </div>
                          </td>
                        );
                      })}

                      {/* Zone label */}
                      <td className="px-2 py-0 align-middle">
                        {zone ? (
                          <div className="flex items-center gap-1.5">
                            <Badge
                              variant={zone.side === "ASK" ? "red" : "green"}
                              className="text-[9px] px-1 py-0 shrink-0"
                            >
                              {zone.badge}
                            </Badge>
                            <span
                              className={clsx(
                                "text-[11px] hidden sm:block truncate max-w-[90px]",
                                zone.intensity > 80 ? "text-lumora-text" : "text-lumora-muted"
                              )}
                            >
                              {zone.label}
                            </span>
                          </div>
                        ) : isCurrent ? (
                          <Badge variant="cyan" className="text-[9px] px-1 py-0">PRICE</Badge>
                        ) : (
                          <span className="text-[11px] text-lumora-border/50">—</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Time axis footer */}
          <div className="px-4 py-2 border-t border-lumora-border/40 flex items-center gap-2">
            <span className="text-[10px] text-lumora-muted">← Older</span>
            <div className="flex-1 h-px bg-gradient-to-r from-lumora-border/20 to-lumora-cyan/40" />
            <span className="text-[10px] text-lumora-cyan font-medium">Now →</span>
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
              <div className="w-3 h-2 rounded-sm bg-red-500/40 shrink-0" />
              Asks (sell-side)
            </div>
            <div className="flex items-center gap-1.5 text-[10px] text-lumora-muted">
              <div className="w-3 h-2 rounded-sm bg-green-500/35 shrink-0" />
              Bids (buy-side)
            </div>
            <div className="flex items-center gap-1.5 text-[10px] text-lumora-muted">
              <div className="w-3 h-2 rounded-sm bg-cyan-500/30 shrink-0" />
              Current price
            </div>
          </div>
        </GlassCard>
      </div>

      {/* ── Zone detail cards ── */}
      <div>
        <h2 className="text-xs font-semibold uppercase tracking-widest text-lumora-muted mb-2">
          Key Zones
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {ZONES.slice(0, 4).map((z) => (
            <GlassCard key={z.price} className="p-3 flex items-start gap-2.5">
              <div
                className="shrink-0 w-1.5 rounded-full self-stretch mt-0.5"
                style={{
                  background:
                    z.side === "ASK"
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
          {
            label: "Strongest Bid Zone",
            value: "$67,350",
            sub: "88% intensity · held 40m",
            color: "text-lumora-green",
          },
          {
            label: "Strongest Ask Zone",
            value: "$68,000",
            sub: "95% intensity · major wall",
            color: "text-lumora-red",
          },
          {
            label: "Liquidity Gap",
            value: "$65,800",
            sub: "Thin below $66,200",
            color: "text-yellow-400",
          },
          {
            label: "Current Bias",
            value: "BULLISH",
            sub: "Bid dominant · +0.42 imbal",
            color: "text-lumora-purple-bright",
          },
          {
            label: "Watch Action",
            value: "Hold $67,350",
            sub: "Break → flush to $66,500",
            color: "text-lumora-cyan",
          },
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
