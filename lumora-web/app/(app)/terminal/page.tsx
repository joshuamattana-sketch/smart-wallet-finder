"use client";

import { useState } from "react";
import { GlassCard } from "@/components/ui/GlassCard";
import { Badge } from "@/components/ui/Badge";
import { mockOrderbook } from "@/lib/mock-data";
import { clsx } from "clsx";
import { ChevronDown } from "lucide-react";

const SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"];
const TIMEFRAMES = ["Now", "5m", "1h"];

export default function TerminalPage() {
  const [symbol, setSymbol] = useState("BTCUSDT");
  const [timeframe, setTimeframe] = useState("Now");
  const ob = mockOrderbook;

  const maxAskSize = Math.max(...ob.asks.map((a) => a.size));
  const maxBidSize = Math.max(...ob.bids.map((b) => b.size));
  const totalBidUsd = ob.bids.reduce((s, b) => s + b.usd, 0);
  const totalAskUsd = ob.asks.reduce((s, a) => s + a.usd, 0);
  const bidPct = Math.round((totalBidUsd / (totalBidUsd + totalAskUsd)) * 100);

  return (
    <div className="space-y-5 animate-[fadeIn_0.4s_ease-out]">
      {/* Controls */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="relative">
          <select
            className="appearance-none bg-lumora-card border border-lumora-border text-lumora-text text-sm rounded-lg px-3 py-2 pr-8 focus:outline-none focus:border-lumora-purple num"
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
          >
            {SYMBOLS.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <ChevronDown className="absolute right-2 top-2.5 h-4 w-4 text-lumora-muted pointer-events-none" />
        </div>

        <div className="flex rounded-lg border border-lumora-border overflow-hidden">
          {TIMEFRAMES.map((tf) => (
            <button
              key={tf}
              onClick={() => setTimeframe(tf)}
              className={clsx(
                "px-4 py-2 text-sm font-medium transition-colors",
                timeframe === tf
                  ? "bg-lumora-purple text-white"
                  : "text-lumora-muted hover:text-lumora-text bg-lumora-card"
              )}
            >
              {tf}
            </button>
          ))}
        </div>

        <Badge variant="cyan" className="ml-auto">{symbol}</Badge>
      </div>

      {/* Orderbook */}
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_auto_1fr] gap-4 items-start">
        {/* Asks */}
        <GlassCard className="overflow-hidden">
          <div className="px-4 py-3 border-b border-lumora-border flex items-center justify-between">
            <span className="text-sm font-semibold text-lumora-red">Asks (Sell Wall)</span>
            <span className="num text-xs text-lumora-muted">${(totalAskUsd / 1000).toFixed(1)}K total</span>
          </div>
          <div className="font-mono text-xs">
            <div className="grid grid-cols-3 px-4 py-2 text-lumora-muted text-[11px] uppercase tracking-wider border-b border-lumora-border/50">
              <span>Price</span><span className="text-right">Size</span><span className="text-right">USD</span>
            </div>
            {[...ob.asks].reverse().map((row, i) => (
              <div key={i} className="relative px-4 py-1.5 grid grid-cols-3 hover:bg-lumora-surface/50 transition-colors">
                <div
                  className="absolute inset-0 right-0 bg-red-500/8"
                  style={{ width: `${(row.size / maxAskSize) * 100}%`, marginLeft: "auto" }}
                />
                <span className="relative num text-lumora-red">{row.price.toLocaleString()}</span>
                <span className="relative num text-right text-lumora-text">{row.size.toFixed(2)}</span>
                <span className="relative num text-right text-lumora-muted">${(row.usd / 1000).toFixed(1)}K</span>
              </div>
            ))}
          </div>
        </GlassCard>

        {/* Mid price */}
        <div className="flex flex-col items-center justify-center gap-3 px-2 py-6">
          <div className="text-center">
            <p className="text-xs text-lumora-muted uppercase tracking-widest mb-1">Mid Price</p>
            <p className="num text-2xl font-bold text-neon-cyan">{ob.midPrice.toLocaleString()}</p>
            <p className="text-xs text-lumora-green mt-1">+0.32% (5m)</p>
          </div>
          <div className="w-24">
            <div className="flex justify-between text-[10px] text-lumora-muted mb-1">
              <span>Bids</span><span>Asks</span>
            </div>
            <div className="h-2 rounded-full overflow-hidden flex">
              <div className="bg-green-500" style={{ width: `${bidPct}%` }} />
              <div className="bg-red-500 flex-1" />
            </div>
            <div className="flex justify-between text-[10px] mt-1">
              <span className="text-lumora-green num">{bidPct}%</span>
              <span className="text-lumora-red num">{100 - bidPct}%</span>
            </div>
          </div>
          <Badge variant="green">Bid Pressure Dominant</Badge>
        </div>

        {/* Bids */}
        <GlassCard className="overflow-hidden">
          <div className="px-4 py-3 border-b border-lumora-border flex items-center justify-between">
            <span className="text-sm font-semibold text-lumora-green">Bids (Buy Wall)</span>
            <span className="num text-xs text-lumora-muted">${(totalBidUsd / 1000).toFixed(1)}K total</span>
          </div>
          <div className="font-mono text-xs">
            <div className="grid grid-cols-3 px-4 py-2 text-lumora-muted text-[11px] uppercase tracking-wider border-b border-lumora-border/50">
              <span>Price</span><span className="text-right">Size</span><span className="text-right">USD</span>
            </div>
            {ob.bids.map((row, i) => (
              <div key={i} className="relative px-4 py-1.5 grid grid-cols-3 hover:bg-lumora-surface/50 transition-colors">
                <div
                  className="absolute inset-0 bg-green-500/8"
                  style={{ width: `${(row.size / maxBidSize) * 100}%` }}
                />
                <span className="relative num text-lumora-green">{row.price.toLocaleString()}</span>
                <span className="relative num text-right text-lumora-text">{row.size.toFixed(2)}</span>
                <span className="relative num text-right text-lumora-muted">${(row.usd / 1000).toFixed(1)}K</span>
              </div>
            ))}
          </div>
        </GlassCard>
      </div>

      {/* Pressure Summary */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          { label: "Spread", value: "4 bps", variant: "muted" as const },
          { label: "Bid/Ask Ratio", value: `${bidPct}/${100 - bidPct}`, variant: "green" as const },
          { label: "Largest Ask Wall", value: "$215K @ 67,440", variant: "red" as const },
          { label: "Largest Bid Wall", value: "$276K @ 67,400", variant: "green" as const },
        ].map(({ label, value, variant }) => (
          <GlassCard key={label} className="p-3">
            <p className="text-xs text-lumora-muted mb-1">{label}</p>
            <p className="num text-sm font-semibold text-lumora-text">{value}</p>
          </GlassCard>
        ))}
      </div>
    </div>
  );
}
