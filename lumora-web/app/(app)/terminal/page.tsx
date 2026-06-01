"use client";

import { useState } from "react";
import { GlassCard } from "@/components/ui/GlassCard";
import { Badge } from "@/components/ui/Badge";
import { mockOrderbook } from "@/lib/mock-data";
import { clsx } from "clsx";
import { ChevronDown, Activity } from "lucide-react";

const SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"];
const TIMEFRAMES = ["Now", "5m", "1h"] as const;

type Timeframe = (typeof TIMEFRAMES)[number];

const TF_LABEL: Record<Timeframe, string> = {
  Now: "Real-time snapshot",
  "5m": "5-minute depth",
  "1h": "1-hour depth",
};

export default function TerminalPage() {
  const [symbol, setSymbol] = useState("BTCUSDT");
  const [timeframe, setTimeframe] = useState<Timeframe>("Now");
  const ob = mockOrderbook;

  const maxAskSize = Math.max(...ob.asks.map((a) => a.size));
  const maxBidSize = Math.max(...ob.bids.map((b) => b.size));
  const totalBidUsd = ob.bids.reduce((s, b) => s + b.usd, 0);
  const totalAskUsd = ob.asks.reduce((s, a) => s + a.usd, 0);
  const bidPct = Math.round((totalBidUsd / (totalBidUsd + totalAskUsd)) * 100);

  return (
    <div className="space-y-4 animate-[fadeIn_0.4s_ease-out]">
      {/* Header + controls row */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="mr-2">
          <h1 className="text-xl font-semibold text-lumora-text">Pro Terminal</h1>
          <p className="text-xs text-lumora-muted mt-0.5">{TF_LABEL[timeframe]}</p>
        </div>

        {/* Symbol selector */}
        <div className="relative">
          <select
            className="appearance-none bg-lumora-card border border-lumora-border text-lumora-text text-sm rounded-lg px-3 py-2 pr-8 focus:outline-none focus:border-lumora-purple num cursor-pointer"
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
          >
            {SYMBOLS.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <ChevronDown className="absolute right-2 top-2.5 h-4 w-4 text-lumora-muted pointer-events-none" />
        </div>

        {/* Timeframe toggle */}
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

        <div className="ml-auto flex items-center gap-2">
          <span className="h-1.5 w-1.5 rounded-full bg-green-400 animate-pulse inline-block" />
          <span className="text-xs text-lumora-green">Live</span>
        </div>
      </div>

      {/* Orderbook — 3-col: asks | mid | bids */}
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_160px_1fr] gap-3 items-start">

        {/* Asks */}
        <GlassCard className="overflow-hidden">
          <div className="px-4 py-2.5 border-b border-lumora-border flex items-center justify-between bg-red-500/5">
            <span className="text-sm font-semibold text-lumora-red">Asks</span>
            <span className="num text-xs text-lumora-muted">${(totalAskUsd / 1000).toFixed(1)}K</span>
          </div>
          <div className="text-xs num">
            <div className="grid grid-cols-3 px-4 py-1.5 text-lumora-muted text-[10px] uppercase tracking-wider border-b border-lumora-border/40">
              <span>Price</span>
              <span className="text-right">BTC</span>
              <span className="text-right">USD</span>
            </div>
            <div className="overflow-y-auto max-h-64">
              {[...ob.asks].reverse().map((row, i) => (
                <div
                  key={i}
                  className="relative px-4 py-1.5 grid grid-cols-3 hover:bg-lumora-surface/50 transition-colors"
                >
                  <div
                    className="absolute inset-y-0 right-0 bg-red-500/10"
                    style={{ width: `${(row.size / maxAskSize) * 100}%` }}
                  />
                  <span className="relative text-lumora-red">{row.price.toLocaleString()}</span>
                  <span className="relative text-right text-lumora-text">{row.size.toFixed(2)}</span>
                  <span className="relative text-right text-lumora-muted">{(row.usd / 1000).toFixed(1)}K</span>
                </div>
              ))}
            </div>
          </div>
        </GlassCard>

        {/* Mid — centered vertically */}
        <div className="flex flex-col items-center gap-3 px-2 py-4 lg:py-8">
          <div className="text-center">
            <p className="text-[10px] text-lumora-muted uppercase tracking-widest mb-1">Mid Price</p>
            <p className="num text-xl font-bold text-neon-cyan">{ob.midPrice.toLocaleString()}</p>
            <p className="text-xs text-lumora-green mt-0.5">+0.32%</p>
          </div>

          <div className="w-full">
            <div className="flex justify-between text-[10px] text-lumora-muted mb-1">
              <span>Bids {bidPct}%</span>
              <span>{100 - bidPct}% Asks</span>
            </div>
            <div className="h-2 rounded-full overflow-hidden flex">
              <div className="bg-green-500 transition-all" style={{ width: `${bidPct}%` }} />
              <div className="bg-red-500 flex-1" />
            </div>
          </div>

          <Badge variant={bidPct >= 50 ? "green" : "red"} className="text-center w-full justify-center">
            {bidPct >= 50 ? "Bid Dominant" : "Ask Dominant"}
          </Badge>

          <div className="text-center">
            <p className="text-[10px] text-lumora-muted">Spread</p>
            <p className="num text-xs text-lumora-text mt-0.5">4 bps</p>
          </div>
        </div>

        {/* Bids */}
        <GlassCard className="overflow-hidden">
          <div className="px-4 py-2.5 border-b border-lumora-border flex items-center justify-between bg-green-500/5">
            <span className="text-sm font-semibold text-lumora-green">Bids</span>
            <span className="num text-xs text-lumora-muted">${(totalBidUsd / 1000).toFixed(1)}K</span>
          </div>
          <div className="text-xs num">
            <div className="grid grid-cols-3 px-4 py-1.5 text-lumora-muted text-[10px] uppercase tracking-wider border-b border-lumora-border/40">
              <span>Price</span>
              <span className="text-right">BTC</span>
              <span className="text-right">USD</span>
            </div>
            <div className="overflow-y-auto max-h-64">
              {ob.bids.map((row, i) => (
                <div
                  key={i}
                  className="relative px-4 py-1.5 grid grid-cols-3 hover:bg-lumora-surface/50 transition-colors"
                >
                  <div
                    className="absolute inset-y-0 left-0 bg-green-500/10"
                    style={{ width: `${(row.size / maxBidSize) * 100}%` }}
                  />
                  <span className="relative text-lumora-green">{row.price.toLocaleString()}</span>
                  <span className="relative text-right text-lumora-text">{row.size.toFixed(2)}</span>
                  <span className="relative text-right text-lumora-muted">{(row.usd / 1000).toFixed(1)}K</span>
                </div>
              ))}
            </div>
          </div>
        </GlassCard>
      </div>

      {/* Pressure Summary */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          { label: "Spread", value: "4 bps", sub: "0.006% of mid" },
          { label: "Bid / Ask Ratio", value: `${bidPct} / ${100 - bidPct}`, sub: "Bid pressure dominant" },
          { label: "Largest Ask Wall", value: "$215K", sub: "@ 67,440" },
          { label: "Largest Bid Wall", value: "$276K", sub: "@ 67,400" },
        ].map(({ label, value, sub }) => (
          <GlassCard key={label} className="p-3">
            <p className="text-[11px] text-lumora-muted uppercase tracking-wide mb-1">{label}</p>
            <p className="num text-sm font-semibold text-lumora-text">{value}</p>
            <p className="num text-[11px] text-lumora-muted mt-0.5">{sub}</p>
          </GlassCard>
        ))}
      </div>
    </div>
  );
}
