"use client";

import { useState } from "react";
import { GlassCard } from "@/components/ui/GlassCard";
import { Badge } from "@/components/ui/Badge";
import { mockLiquidityZones } from "@/lib/mock-data";
import { clsx } from "clsx";

const ALL_PRICES = [68500, 68000, 67500, 67200, 67000, 66800, 66500, 66000, 65800, 65500];
const TIME_COLS = ["T-60m", "T-45m", "T-30m", "T-15m", "T-5m", "Now"];

const RANGE_PRESETS = [
  { label: "65.5k – 68.5k", min: 65500, max: 68500 },
  { label: "66k – 68k", min: 66000, max: 68000 },
  { label: "66.5k – 67.5k", min: 66500, max: 67500 },
];

function intensityToColor(v: number): string {
  if (v > 85) return "bg-purple-500/70 shadow-[inset_0_0_6px_rgba(139,92,246,0.4)]";
  if (v > 65) return "bg-purple-500/45";
  if (v > 45) return "bg-purple-500/22";
  if (v > 25) return "bg-purple-500/10";
  return "bg-lumora-border/15";
}

function mockCell(price: number, col: number): number {
  const base = Math.abs(Math.sin(price * 0.01 + col * 0.5)) * 100;
  const zone = mockLiquidityZones.find((z) => Math.abs(z.price - price) < 300);
  const boost = zone ? zone.intensity * (1 - col * 0.08) : 0;
  return Math.min(100, base * 0.3 + boost * 0.7);
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
          <p className="text-sm text-lumora-muted mt-0.5">Bookmap-style depth heatmap — BTC/USDT</p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant="cyan">BTCUSDT</Badge>
          <Badge variant="muted">{filtered.length} levels</Badge>
        </div>
      </div>

      {/* Controls */}
      <GlassCard className="p-3 flex flex-wrap items-center gap-3">
        <span className="text-xs text-lumora-muted uppercase tracking-wide font-medium">Price Range</span>
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

        {/* Legend inline */}
        <div className="ml-auto flex items-center gap-3 flex-wrap">
          <span className="text-[10px] text-lumora-muted uppercase tracking-wide">Intensity →</span>
          {[
            { label: "Low", cls: "bg-lumora-border/20" },
            { label: "Med", cls: "bg-purple-500/22" },
            { label: "High", cls: "bg-purple-500/45" },
            { label: "Critical", cls: "bg-purple-500/70" },
          ].map(({ label, cls }) => (
            <div key={label} className="flex items-center gap-1">
              <div className={clsx("h-3 w-5 rounded-sm", cls)} />
              <span className="text-[10px] text-lumora-text-dim">{label}</span>
            </div>
          ))}
        </div>
      </GlassCard>

      {/* Heatmap */}
      <GlassCard className="overflow-x-auto p-4">
        <table className="w-full text-xs num border-separate border-spacing-1 min-w-[520px]">
          <thead>
            <tr>
              <th className="text-left text-lumora-muted px-2 pb-2 w-20 text-[11px] uppercase tracking-wider">
                Price
              </th>
              {TIME_COLS.map((t) => (
                <th
                  key={t}
                  className={clsx(
                    "text-center pb-2 px-1 text-[11px] uppercase tracking-wider",
                    t === "Now" ? "text-lumora-cyan" : "text-lumora-muted"
                  )}
                >
                  {t}
                </th>
              ))}
              <th className="text-left text-lumora-muted px-2 pb-2 text-[11px] uppercase tracking-wider">
                Zone
              </th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((price) => {
              const zone = mockLiquidityZones.find((z) => Math.abs(z.price - price) < 300);
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
                          className={clsx(
                            "h-7 rounded transition-all duration-200 group-hover:opacity-90",
                            intensityToColor(v)
                          )}
                          title={`${price.toLocaleString()} · ${TIME_COLS[ci]} · ${v.toFixed(0)}%`}
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

      {/* Zone summary below map */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {mockLiquidityZones.slice(0, 3).map((z) => (
          <GlassCard key={z.price} className="p-3 flex items-center gap-3">
            <div
              className="shrink-0 w-1.5 h-8 rounded-full"
              style={{
                background:
                  z.intensity > 80
                    ? "linear-gradient(180deg,#c084fc,#8b5cf6)"
                    : "linear-gradient(180deg,#22d3ee,#0891b2)",
              }}
            />
            <div className="flex-1 min-w-0">
              <p className="num text-sm font-semibold text-lumora-text">${z.price.toLocaleString()}</p>
              <p className="text-xs text-lumora-muted">{z.label}</p>
            </div>
            <div className="text-right space-y-0.5">
              <Badge variant={z.side === "ASK" ? "red" : "green"}>{z.side}</Badge>
              <p className="num text-[10px] text-lumora-text-dim">{z.intensity}% intensity</p>
            </div>
          </GlassCard>
        ))}
      </div>
    </div>
  );
}
