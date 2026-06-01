"use client";

import { useState } from "react";
import { GlassCard } from "@/components/ui/GlassCard";
import { Badge } from "@/components/ui/Badge";
import { mockLiquidityZones } from "@/lib/mock-data";
import { clsx } from "clsx";

const PRICE_LEVELS = [68500, 68000, 67500, 67200, 67000, 66800, 66500, 66000, 65800, 65500];
const TIME_COLS = ["T-60m", "T-45m", "T-30m", "T-15m", "T-5m", "Now"];

function intensityToColor(v: number): string {
  if (v > 85) return "bg-purple-500/70 shadow-[inset_0_0_6px_rgba(139,92,246,0.5)]";
  if (v > 65) return "bg-purple-500/40";
  if (v > 45) return "bg-purple-500/20";
  if (v > 25) return "bg-purple-500/10";
  return "bg-lumora-border/20";
}

function mockCell(price: number, col: number): number {
  const base = Math.abs(Math.sin(price * 0.01 + col * 0.5)) * 100;
  const zone = mockLiquidityZones.find((z) => Math.abs(z.price - price) < 300);
  const boost = zone ? (zone.intensity * (1 - col * 0.08)) : 0;
  return Math.min(100, base * 0.3 + boost * 0.7);
}

export default function LiquidityMapPage() {
  const [rangeMin, setRangeMin] = useState(65500);
  const [rangeMax, setRangeMax] = useState(68500);

  const filtered = PRICE_LEVELS.filter((p) => p >= rangeMin && p <= rangeMax);

  return (
    <div className="space-y-5 animate-[fadeIn_0.4s_ease-out]">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-lumora-text">Liquidity Map</h1>
          <p className="text-sm text-lumora-muted mt-0.5">Bookmap-style heatmap — BTC/USDT</p>
        </div>
        <Badge variant="cyan">BTCUSDT</Badge>
      </div>

      {/* Range controls */}
      <GlassCard className="p-4 flex flex-wrap items-center gap-4">
        <div className="flex items-center gap-2">
          <label className="text-xs text-lumora-muted uppercase tracking-wide">Min</label>
          <input
            type="number"
            value={rangeMin}
            onChange={(e) => setRangeMin(Number(e.target.value))}
            className="num w-24 bg-lumora-bg border border-lumora-border rounded px-2 py-1 text-sm text-lumora-text focus:outline-none focus:border-lumora-purple"
          />
        </div>
        <div className="flex items-center gap-2">
          <label className="text-xs text-lumora-muted uppercase tracking-wide">Max</label>
          <input
            type="number"
            value={rangeMax}
            onChange={(e) => setRangeMax(Number(e.target.value))}
            className="num w-24 bg-lumora-bg border border-lumora-border rounded px-2 py-1 text-sm text-lumora-text focus:outline-none focus:border-lumora-purple"
          />
        </div>
        <div className="ml-auto flex items-center gap-4 text-xs text-lumora-muted">
          <span>Showing {filtered.length} levels</span>
        </div>
      </GlassCard>

      {/* Heatmap grid */}
      <GlassCard className="overflow-x-auto p-4">
        <table className="w-full text-xs num border-separate border-spacing-1 min-w-[500px]">
          <thead>
            <tr>
              <th className="text-left text-lumora-muted px-2 pb-2 w-24">Price</th>
              {TIME_COLS.map((t) => (
                <th key={t} className="text-center text-lumora-muted pb-2 px-1">{t}</th>
              ))}
              <th className="text-left text-lumora-muted px-2 pb-2">Zone</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((price) => {
              const zone = mockLiquidityZones.find((z) => Math.abs(z.price - price) < 300);
              return (
                <tr key={price} className="group">
                  <td className={clsx("px-2 py-1 font-semibold", zone ? "text-lumora-purple-bright" : "text-lumora-text-dim")}>
                    {price.toLocaleString()}
                  </td>
                  {TIME_COLS.map((_, ci) => {
                    const v = mockCell(price, ci);
                    return (
                      <td key={ci} className="px-1 py-0.5">
                        <div
                          className={clsx("h-7 rounded transition-all duration-200 group-hover:scale-y-110", intensityToColor(v))}
                          title={`Intensity: ${v.toFixed(0)}%`}
                        />
                      </td>
                    );
                  })}
                  <td className="px-2">
                    {zone && (
                      <span className="flex items-center gap-1">
                        <Badge variant={zone.side === "ASK" ? "red" : "green"}>{zone.side}</Badge>
                        <span className="text-lumora-muted ml-1">{zone.label}</span>
                      </span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </GlassCard>

      {/* Legend */}
      <GlassCard className="p-4 flex flex-wrap items-center gap-6">
        <span className="text-xs text-lumora-muted uppercase tracking-wide font-medium">Wall Intensity</span>
        {[
          { label: "Critical (>85%)", cls: "bg-purple-500/70" },
          { label: "High (>65%)", cls: "bg-purple-500/40" },
          { label: "Medium (>45%)", cls: "bg-purple-500/20" },
          { label: "Low (<45%)", cls: "bg-lumora-border/20" },
        ].map(({ label, cls }) => (
          <div key={label} className="flex items-center gap-2">
            <div className={clsx("h-4 w-8 rounded", cls)} />
            <span className="text-xs text-lumora-text-dim">{label}</span>
          </div>
        ))}
      </GlassCard>
    </div>
  );
}
