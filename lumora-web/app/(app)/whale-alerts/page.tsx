"use client";

import { useState } from "react";
import { GlassCard } from "@/components/ui/GlassCard";
import { Badge } from "@/components/ui/Badge";
import { mockWhaleAlerts } from "@/lib/mock-data";
import { clsx } from "clsx";
import { ChevronDown, ChevronUp, Filter, Zap } from "lucide-react";

type Risk = "ALL" | "HIGH" | "MEDIUM" | "LOW";
type Side = "ALL" | "BUY" | "SELL";

const RISK_OPTIONS: Risk[] = ["ALL", "HIGH", "MEDIUM", "LOW"];
const SIDE_OPTIONS: Side[] = ["ALL", "BUY", "SELL"];

const RISK_VARIANT: Record<string, "red" | "yellow" | "muted"> = {
  HIGH: "red",
  MEDIUM: "yellow",
  LOW: "muted",
};

export default function WhaleAlertsPage() {
  const [risk, setRisk] = useState<Risk>("ALL");
  const [side, setSide] = useState<Side>("ALL");
  const [expanded, setExpanded] = useState<number | null>(null);

  const filtered = mockWhaleAlerts.filter(
    (a) => (risk === "ALL" || a.risk === risk) && (side === "ALL" || a.side === side)
  );

  return (
    <div className="space-y-4 animate-[fadeIn_0.4s_ease-out]">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-lumora-text flex items-center gap-2">
            <Zap className="h-5 w-5 text-lumora-cyan" /> Whale Alerts
          </h1>
          <p className="text-sm text-lumora-muted mt-0.5">Large order flow &amp; unusual activity detection</p>
        </div>
        <div className="flex items-center gap-2 text-xs">
          <span className="h-1.5 w-1.5 rounded-full bg-green-400 animate-pulse inline-block" />
          <span className="text-lumora-green">Monitoring</span>
          <Badge variant="green">{filtered.length} / {mockWhaleAlerts.length}</Badge>
        </div>
      </div>

      {/* Filter bar */}
      <GlassCard className="p-2.5 flex flex-wrap items-center gap-2">
        <Filter className="h-3.5 w-3.5 text-lumora-muted ml-0.5 shrink-0" />

        <span className="text-[11px] text-lumora-muted uppercase tracking-wide">Risk</span>
        <div className="flex rounded-md border border-lumora-border overflow-hidden">
          {RISK_OPTIONS.map((r) => (
            <button
              key={r}
              onClick={() => setRisk(r)}
              className={clsx(
                "px-2.5 py-1 text-xs font-medium transition-colors",
                risk === r
                  ? "bg-lumora-purple text-white"
                  : "text-lumora-muted hover:text-lumora-text bg-lumora-card"
              )}
            >
              {r}
            </button>
          ))}
        </div>

        <div className="h-4 w-px bg-lumora-border hidden sm:block" />

        <span className="text-[11px] text-lumora-muted uppercase tracking-wide">Side</span>
        <div className="flex rounded-md border border-lumora-border overflow-hidden">
          {SIDE_OPTIONS.map((s) => (
            <button
              key={s}
              onClick={() => setSide(s)}
              className={clsx(
                "px-2.5 py-1 text-xs font-medium transition-colors",
                side === s
                  ? "bg-lumora-purple text-white"
                  : "text-lumora-muted hover:text-lumora-text bg-lumora-card"
              )}
            >
              {s}
            </button>
          ))}
        </div>
      </GlassCard>

      {/* Alert list */}
      <div className="space-y-1.5">
        {filtered.map((a) => (
          <GlassCard key={a.id} className="overflow-hidden">
            {/* Compact row — always visible */}
            <button
              className="w-full px-4 py-3 flex items-center gap-3 text-left hover:bg-lumora-surface/30 transition-colors"
              onClick={() => setExpanded(expanded === a.id ? null : a.id)}
            >
              {/* Side badge */}
              <Badge
                variant={a.side === "BUY" ? "green" : "red"}
                className="shrink-0 w-12 justify-center"
              >
                {a.side}
              </Badge>

              {/* Symbol + type */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-1.5 flex-wrap">
                  <span className="num text-sm font-semibold text-lumora-text">{a.symbol}</span>
                  <span className="text-[11px] text-lumora-muted">{a.type}</span>
                </div>
                <div className="flex items-center gap-1.5 mt-0.5">
                  <Badge variant="muted" className="text-[10px]">{a.exchange}</Badge>
                  <span className="num text-[11px] text-lumora-muted">{a.time}</span>
                </div>
              </div>

              {/* Size */}
              <div className="shrink-0 text-right">
                <p className="num text-sm font-bold text-lumora-text">{a.size}</p>
              </div>

              {/* Risk badge */}
              <Badge variant={RISK_VARIANT[a.risk] ?? "muted"} className="shrink-0 w-16 justify-center">
                {a.risk}
              </Badge>

              {/* Expand chevron */}
              {expanded === a.id
                ? <ChevronUp className="h-4 w-4 text-lumora-muted shrink-0" />
                : <ChevronDown className="h-4 w-4 text-lumora-muted shrink-0" />}
            </button>

            {/* Expanded detail */}
            {expanded === a.id && (
              <div className="border-t border-lumora-border/50 px-4 py-3 bg-lumora-surface/20">
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-3">
                  {[
                    { label: "Exchange", value: a.exchange },
                    { label: "Order Size", value: a.size },
                    { label: "Order Type", value: a.type },
                    { label: "Detected", value: a.time },
                  ].map(({ label, value }) => (
                    <div key={label}>
                      <p className="text-[11px] text-lumora-muted mb-0.5">{label}</p>
                      <p className="num text-sm text-lumora-text font-medium">{value}</p>
                    </div>
                  ))}
                </div>
                <div className="rounded-lg bg-lumora-card border border-lumora-border/60 px-3 py-2">
                  <p className="text-[11px] text-lumora-muted uppercase tracking-wide mb-1">Risk Assessment</p>
                  <p className="text-xs text-lumora-text-dim leading-relaxed">
                    {a.risk === "HIGH"
                      ? "Significant market impact expected. Watch for price follow-through in the next 15 minutes."
                      : a.risk === "MEDIUM"
                      ? "Moderate position size. May signal directional conviction — combine with CVD before acting."
                      : "Small relative to daily volume. Likely background noise unless part of a pattern."}
                  </p>
                </div>
              </div>
            )}
          </GlassCard>
        ))}

        {filtered.length === 0 && (
          <GlassCard className="p-10 text-center">
            <p className="text-lumora-muted text-sm">No alerts match the current filters.</p>
            <button
              className="mt-3 text-xs text-lumora-purple hover:text-lumora-purple-bright transition-colors"
              onClick={() => { setRisk("ALL"); setSide("ALL"); }}
            >
              Clear filters
            </button>
          </GlassCard>
        )}
      </div>
    </div>
  );
}
