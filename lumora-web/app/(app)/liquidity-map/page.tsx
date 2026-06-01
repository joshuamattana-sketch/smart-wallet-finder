"use client";

import { useState } from "react";
import { GlassCard } from "@/components/ui/GlassCard";
import { Badge } from "@/components/ui/Badge";
import { mockLiquidityZones } from "@/lib/mock-data";
import { clsx } from "clsx";

const ALL_PRICES = [68500, 68000, 67500, 67350, 67200, 67000, 66800, 66500, 66200, 65800];
const TIME_COLS = ["T-60m", "T-45m", "T-30m", "T-15m", "T-5m", "Now"];

const RANGE_PRESETS = [
  { label: "Full view", min: 65800, max: 68500 },
  { label: "66k – 68k",  min: 66000, max: 68000 },
  { label: "Tight ±1%",  min: 66800, max: 68000 },
];

const LEGEND = [
  { label: "Thin / No liquidity", cls: "bg-lumora-border/15" },
  { label: "Light cluster",       cls: "bg-purple-500/20"    },
  { label: "Heavy cluster",       cls: "bg-purple-500/45"    },
  { label: "Wall / Critical",     cls: "bg-purple-500/75 shadow-[inset_0_0_6px_rgba(139,92,246,0.4)]" },
];

function intensityToColor(v: number): string {
  if (v > 80) return "bg-purple-500/75 shadow-[inset_0_0_6px_rgba(139,92,246,0.4)]";
  if (v > 60) return "bg-purple-500/45";
  if (v > 35) return "bg-purple-500/20";
  if (v > 15) return "bg-purple-500/10";
  return "bg-lumora-border/15";
}

function mockCell(price: number, col: number): number {
  const base = Math.abs(Math.sin(price * 0.013 + col * 0.6)) * 100;
  const zone = mockLiquidityZones.find((z) => Math.abs(z.price - price) < 250);
  const boost = zone ? zone.intensity * (1 - col * 0.07) : 0;
  return Math.min(100, base * 0.25 + boost * 0.75);
}

export default function LiquidityMapPage() {
  const [presetIdx, setPresetIdx] = useState(0);
  const { min, max } = RANGE_PRESETS[presetIdx];
  const filtered = ALL_PRICES.filter((p) => p >= min && p <= max);

  return (
    <div className="space-y-4 animate-[fadeIn_0.4s_ease-out]">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-lumora-text">Liquidity Map</h1>
          <p className="text-sm text-lumora-muted mt-0.5">Bookmap-style depth heatmap — demo data, BTC/USDT</p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant="cyan">BTCUSDT</Badge>
          <Badge variant="muted">{filtered.length} levels</Badge>
        </div>
      </div>

      {/* Controls + legend in one bar */}
      <GlassCard className="p-3 flex flex-wrap items-center gap-3">
        <span className="text-xs text-lumora-muted uppercase tracking-wide font-medium shrink-0">Range</span>
        <div className="flex rounded-lg border border-lumora-border overflow-hidden">
          {RANGE_PRESETS.map((p, i) => (
            <button
              key={p.label}
              onClick={() => setPresetIdx(i)}
              className={clsx(
                "px-3 py-1.5 text-xs font-medium transition-colors num",
                presetIdx === i
                  ? "bg-lumora-purple text-white"
                  : "text-lumora-muted hover:text-lumora-text bg-lumora-card"
              )}
            >
              {p.label}
            </button>
          ))}
        </div>

        <div className="h-4 w-px bg-lumora-border hidden sm:block" />

        <span className="text-[10px] text-lumora-muted uppercase tracking-wide shrink-0">Intensity →</span>
        <div className="flex items-center gap-3 flex-wrap">
          {LEGEND.map(({ label, cls }) => (
            <div key={label} className="flex items-center gap-1.5">
              <div className={clsx("h-3 w-5 rounded-sm shrink-0", cls)} />
              <span className="text-[10px] text-lumora-text-dim">{label}</span>
            </div>
          ))}
        </div>
      </GlassCard>

      {/* Heatmap */}
      <GlassCard className="overflow-x-auto p-4">
        <table className="w-full text-xs num border-separate border-spacing-1 min-w-[560px]">
          <thead>
            <tr>
              <th className="text-left text-lumora-muted px-2 pb-2.5 w-24 text-[11px] uppercase tracking-wider">Price</th>
              {TIME_COLS.map((t) => (
                <th
                  key={t}
                  className={clsx(
                    "text-center pb-2.5 px-1 text-[11px] uppercase tracking-wider",
                    t === "Now" ? "text-lumora-cyan" : "text-lumora-muted"
                  )}
                >
                  {t}
                </th>
              ))}
              <th className="text-left text-lumora-muted px-2 pb-2.5 text-[11px] uppercase tracking-wider">Zone</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((price) => {
              const zone = mockLiquidityZones.find((z) => Math.abs(z.price - price) < 250);
              return (
                <tr key={price} className="group">
                  <td
                    className={clsx(
                      "px-2 py-0.5 font-semibold text-xs",
                      zone ? "text-lumora-purple-bright" : "text-lumora-text-dim"
                    )}
                  >
                    {price.toLocaleString()}
                  </td>
                  {TIME_COLS.map((_, ci) => {
                    const v = mockCell(price, ci);
                    return (
                      <td key={ci} className="px-0.5 py-0.5">
                        <div
                          className={clsx("h-7 rounded transition-opacity duration-200 group-hover:opacity-80", intensityToColor(v))}
                          title={`$${price.toLocaleString()} · ${TIME_COLS[ci]} · ${v.toFixed(0)}% intensity`}
                        />
                      </td>
                    );
                  })}
                  <td className="px-2 py-0.5">
                    {zone ? (
                      <div className="flex items-center gap-1.5">
                        <Badge variant={zone.side === "ASK" ? "red" : "green"}>{zone.side}</Badge>
                        <span className="text-[11px] text-lumora-muted">{zone.label}</span>
                      </div>
                    ) : (
                      <span className="text-[11px] text-lumora-border">—</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </GlassCard>

      {/* Zone detail cards */}
      <div>
        <h2 className="text-xs font-semibold uppercase tracking-widest text-lumora-muted mb-2">Key Zones</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {mockLiquidityZones.slice(0, 6).map((z) => (
            <GlassCard key={z.price} className="p-3 flex items-start gap-3">
              <div
                className="shrink-0 w-1.5 h-full min-h-[36px] rounded-full mt-0.5"
                style={{
                  background:
                    z.intensity > 80
                      ? "linear-gradient(180deg,#c084fc,#8b5cf6)"
                      : "linear-gradient(180deg,#22d3ee,#0891b2)",
                }}
              />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-0.5">
                  <p className="num text-sm font-semibold text-lumora-text">${z.price.toLocaleString()}</p>
                  <Badge variant={z.side === "ASK" ? "red" : "green"}>{z.side}</Badge>
                  <span className="num text-[10px] text-lumora-muted ml-auto">{z.intensity}%</span>
                </div>
                <p className="text-xs font-medium text-lumora-text-dim">{z.label}</p>
                <p className="text-[11px] text-lumora-muted mt-0.5 leading-snug">{z.desc}</p>
              </div>
            </GlassCard>
          ))}
        </div>
      </div>
    </div>
  );
}
