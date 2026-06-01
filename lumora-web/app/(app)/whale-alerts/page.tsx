"use client";

import { useState } from "react";
import { GlassCard } from "@/components/ui/GlassCard";
import { Badge } from "@/components/ui/Badge";
import { mockWhaleAlerts } from "@/lib/mock-data";
import { clsx } from "clsx";
import { ChevronDown, ChevronUp, Filter } from "lucide-react";

type Risk = "ALL" | "HIGH" | "MEDIUM" | "LOW";
type Side = "ALL" | "BUY" | "SELL";

export default function WhaleAlertsPage() {
  const [risk, setRisk] = useState<Risk>("ALL");
  const [side, setSide] = useState<Side>("ALL");
  const [expanded, setExpanded] = useState<number | null>(null);

  const filtered = mockWhaleAlerts.filter(
    (a) => (risk === "ALL" || a.risk === risk) && (side === "ALL" || a.side === side)
  );

  return (
    <div className="space-y-5 animate-[fadeIn_0.4s_ease-out]">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-lumora-text">Whale Alerts</h1>
          <p className="text-sm text-lumora-muted mt-0.5">Large order & unusual flow detection</p>
        </div>
        <div className="flex items-center gap-2 text-xs text-lumora-green">
          <span className="h-1.5 w-1.5 rounded-full bg-green-400 animate-pulse inline-block" />
          Monitoring {mockWhaleAlerts.length} alerts
        </div>
      </div>

      {/* Filters */}
      <GlassCard className="p-3 flex flex-wrap items-center gap-3">
        <Filter className="h-4 w-4 text-lumora-muted" />
        <span className="text-xs text-lumora-muted uppercase tracking-wide">Risk:</span>
        {(["ALL", "HIGH", "MEDIUM", "LOW"] as Risk[]).map((r) => (
          <button
            key={r}
            onClick={() => setRisk(r)}
            className={clsx(
              "px-3 py-1 rounded-lg text-xs font-medium transition-colors",
              risk === r ? "bg-lumora-purple text-white" : "bg-lumora-surface text-lumora-muted hover:text-lumora-text"
            )}
          >
            {r}
          </button>
        ))}
        <span className="text-lumora-border">|</span>
        <span className="text-xs text-lumora-muted uppercase tracking-wide">Side:</span>
        {(["ALL", "BUY", "SELL"] as Side[]).map((s) => (
          <button
            key={s}
            onClick={() => setSide(s)}
            className={clsx(
              "px-3 py-1 rounded-lg text-xs font-medium transition-colors",
              side === s ? "bg-lumora-purple text-white" : "bg-lumora-surface text-lumora-muted hover:text-lumora-text"
            )}
          >
            {s}
          </button>
        ))}
      </GlassCard>

      {/* Alert cards */}
      <div className="space-y-2">
        {filtered.map((a) => (
          <GlassCard key={a.id} className="overflow-hidden">
            <button
              className="w-full px-4 py-3 flex items-center gap-4 text-left hover:bg-lumora-surface/30 transition-colors"
              onClick={() => setExpanded(expanded === a.id ? null : a.id)}
            >
              <Badge variant={a.side === "BUY" ? "green" : "red"} className="shrink-0">{a.side}</Badge>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="num font-semibold text-lumora-text">{a.symbol}</span>
                  <span className="text-lumora-muted text-xs">·</span>
                  <span className="text-xs text-lumora-muted">{a.type}</span>
                </div>
                <div className="text-xs text-lumora-muted mt-0.5">{a.exchange} · {a.time}</div>
              </div>
              <div className="shrink-0 text-right">
                <p className="num font-bold text-lumora-text">{a.size}</p>
              </div>
              <Badge
                variant={a.risk === "HIGH" ? "red" : a.risk === "MEDIUM" ? "yellow" : "muted"}
                className="shrink-0"
              >
                {a.risk}
              </Badge>
              {expanded === a.id ? (
                <ChevronUp className="h-4 w-4 text-lumora-muted shrink-0" />
              ) : (
                <ChevronDown className="h-4 w-4 text-lumora-muted shrink-0" />
              )}
            </button>

            {expanded === a.id && (
              <div className="px-4 pb-4 border-t border-lumora-border/50 pt-3 grid grid-cols-2 md:grid-cols-4 gap-3">
                {[
                  { label: "Exchange", value: a.exchange },
                  { label: "Size", value: a.size },
                  { label: "Type", value: a.type },
                  { label: "Time", value: a.time },
                ].map(({ label, value }) => (
                  <div key={label}>
                    <p className="text-xs text-lumora-muted">{label}</p>
                    <p className="num text-sm text-lumora-text mt-0.5">{value}</p>
                  </div>
                ))}
                <div className="col-span-2 md:col-span-4 mt-2">
                  <p className="text-xs text-lumora-muted mb-1">Risk Assessment</p>
                  <p className="text-sm text-lumora-text-dim">
                    {a.risk === "HIGH"
                      ? "Significant market impact expected. Monitor for follow-through within 15m."
                      : a.risk === "MEDIUM"
                      ? "Moderate position size. May signal directional conviction."
                      : "Small relative to daily volume. Background noise likely."}
                  </p>
                </div>
              </div>
            )}
          </GlassCard>
        ))}

        {filtered.length === 0 && (
          <GlassCard className="p-8 text-center text-lumora-muted">
            No alerts match current filters.
          </GlassCard>
        )}
      </div>
    </div>
  );
}
