"use client";

import { useState, useMemo } from "react";
import { Panel } from "@/components/ui/Panel";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { mockWhaleAlerts } from "@/lib/mock-data";
import { clsx } from "clsx";
import { ChevronDown, ChevronUp, Filter, Zap } from "lucide-react";

type Risk = "ALL" | "HIGH" | "MEDIUM" | "LOW";
type Side = "ALL" | "BUY" | "SELL";

type RiskVariant = "error" | "warning" | "neutral";
const RISK_VARIANT: Record<string, RiskVariant> = {
  HIGH: "error",
  MEDIUM: "warning",
  LOW: "neutral",
};

export default function WhaleAlertsPage() {
  const [risk, setRisk] = useState<Risk>("ALL");
  const [side, setSide] = useState<Side>("ALL");
  const [expanded, setExpanded] = useState<number | null>(null);

  const filtered = useMemo(
    () =>
      mockWhaleAlerts.filter(
        (a) => (risk === "ALL" || a.risk === risk) && (side === "ALL" || a.side === side),
      ),
    [risk, side],
  );

  // Summary stats — derived from filtered set (read-only, no fetch impact).
  const stats = useMemo(() => {
    const parseUsd = (s: string) =>
      Number.parseFloat(s.replace(/[^0-9.]/g, "")) *
      (/B/i.test(s) ? 1_000_000_000 : /M/i.test(s) ? 1_000_000 : /K/i.test(s) ? 1_000 : 1);
    const totalUsd = filtered.reduce((sum, a) => sum + parseUsd(a.size), 0);
    const buys = filtered.filter((a) => a.side === "BUY").length;
    const sells = filtered.filter((a) => a.side === "SELL").length;
    const high = filtered.filter((a) => a.risk === "HIGH").length;
    return { totalUsd, buys, sells, high };
  }, [filtered]);

  const fmtUsd = (n: number) =>
    n >= 1_000_000_000 ? `$${(n / 1_000_000_000).toFixed(2)}B`
    : n >= 1_000_000 ? `$${(n / 1_000_000).toFixed(2)}M`
    : n >= 1_000 ? `$${(n / 1_000).toFixed(1)}K`
    : `$${n.toFixed(0)}`;

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-lm-text flex items-center gap-2">
            <Zap className="h-4 w-4 text-lm-cyan" /> Whale Intelligence Feed
          </h1>
          <p className="text-[12px] text-lm-muted mt-0.5">
            Large order flow &amp; unusual activity across major venues — demo data
          </p>
        </div>
        <div className="flex items-center gap-2 text-[11px] text-lm-text-dim num uppercase tracking-wide">
          <span className="lm-live-dot inline-block h-1.5 w-1.5 rounded-full bg-emerald-400 text-emerald-400" />
          Monitoring
          <span className="text-lm-border">·</span>
          <span className="text-lm-text">{filtered.length}</span>
          <span className="text-lm-muted">/ {mockWhaleAlerts.length}</span>
        </div>
      </div>

      {/* Summary KPI strip */}
      <Panel flush className="grid grid-cols-2 sm:grid-cols-4 divide-x divide-lm-border/60">
        {[
          { label: "Total Flow", value: fmtUsd(stats.totalUsd), tone: "text-lm-text" },
          { label: "Buys",  value: String(stats.buys),  tone: "text-emerald-400" },
          { label: "Sells", value: String(stats.sells), tone: "text-red-400" },
          { label: "High Risk", value: String(stats.high), tone: "text-amber-400" },
        ].map((s) => (
          <div key={s.label} className="px-4 py-2.5">
            <p className="text-[10px] uppercase tracking-widest text-lm-muted">{s.label}</p>
            <p className={clsx("lm-price text-lg mt-0.5 leading-none", s.tone)}>{s.value}</p>
          </div>
        ))}
      </Panel>

      {/* Filter bar */}
      <Panel flush className="p-2 flex flex-wrap items-center gap-2">
        <Filter className="h-3.5 w-3.5 text-lm-muted ml-0.5 shrink-0" />
        <span className="text-[10px] uppercase tracking-widest text-lm-muted">Risk</span>
        <div className="flex rounded-md border border-lm-border overflow-hidden">
          {(["ALL", "HIGH", "MEDIUM", "LOW"] as Risk[]).map((r) => (
            <button
              key={r}
              onClick={() => setRisk(r)}
              className={clsx(
                "lm-segment-btn px-2.5 py-1 text-[11px] font-medium",
                risk === r ? "lm-segment-active" : "text-lm-muted bg-lm-surface",
              )}
            >
              {r}
            </button>
          ))}
        </div>
        <div className="h-4 w-px bg-lm-border hidden sm:block" />
        <span className="text-[10px] uppercase tracking-widest text-lm-muted">Side</span>
        <div className="flex rounded-md border border-lm-border overflow-hidden">
          {(["ALL", "BUY", "SELL"] as Side[]).map((s) => (
            <button
              key={s}
              onClick={() => setSide(s)}
              className={clsx(
                "lm-segment-btn px-2.5 py-1 text-[11px] font-medium",
                side === s ? "lm-segment-active" : "text-lm-muted bg-lm-surface",
              )}
            >
              {s}
            </button>
          ))}
        </div>
      </Panel>

      {/* Feed */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <h2 className="text-[11px] font-semibold uppercase tracking-widest text-lm-muted">
            Live Feed
          </h2>
          <span className="text-[10px] text-lm-muted num">
            sorted by time · most recent first
          </span>
        </div>

        <Panel flush className="overflow-hidden divide-y divide-lm-border/60">
          {filtered.map((a) => {
            const isOpen = expanded === a.id;
            return (
              <div key={a.id}>
                <button
                  onClick={() => setExpanded(isOpen ? null : a.id)}
                  className={clsx(
                    "lm-row w-full px-3 py-2 text-left grid grid-cols-[44px_44px_1fr_auto_auto_auto_14px] items-center gap-3",
                    isOpen && "lm-row-open",
                  )}
                >
                  {/* Time */}
                  <span className="num text-[11px] text-lm-muted">{a.time}</span>

                  {/* Side */}
                  <StatusBadge
                    variant={a.side === "BUY" ? "bid" : "ask"}
                    size="sm"
                    className="w-10 justify-center"
                  >
                    {a.side}
                  </StatusBadge>

                  {/* Symbol + type */}
                  <div className="min-w-0">
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <span className="num text-[13px] font-semibold text-lm-text">{a.symbol}</span>
                      <span className="text-[10px] uppercase tracking-wide text-lm-muted">
                        {a.type}
                      </span>
                      {a.leverage !== "1×" && (
                        <StatusBadge variant="warning" size="sm">{a.leverage}</StatusBadge>
                      )}
                    </div>
                    <p className="text-[10px] text-lm-muted truncate mt-0.5">{a.exchange}</p>
                  </div>

                  {/* Notional — primary read */}
                  <div className="text-right">
                    <p className="lm-price text-[14px] text-lm-text leading-none">{a.size}</p>
                    <p className="num text-[10px] text-lm-muted mt-0.5">conf {a.confidence}%</p>
                  </div>

                  {/* Risk */}
                  <StatusBadge
                    variant={RISK_VARIANT[a.risk] ?? "neutral"}
                    size="sm"
                    className="w-14 justify-center"
                  >
                    {a.risk}
                  </StatusBadge>

                  {/* Confidence micro-bar */}
                  <div className="hidden sm:block w-14">
                    <div className="h-1 rounded-full bg-lm-border overflow-hidden">
                      <div
                        className="h-full rounded-full bg-lm-cyan/80"
                        style={{ width: `${a.confidence}%` }}
                      />
                    </div>
                  </div>

                  {/* Chevron */}
                  {isOpen
                    ? <ChevronUp className="h-3.5 w-3.5 text-lm-muted" />
                    : <ChevronDown className="h-3.5 w-3.5 text-lm-muted" />}
                </button>

                {/* Expanded detail */}
                {isOpen && (
                  <div className="px-3 pb-3 pt-1 bg-lm-surface-muted/40 grid grid-cols-1 sm:grid-cols-[1fr_1fr] gap-3">
                    <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-[11px]">
                      {[
                        { label: "Exchange",   value: a.exchange },
                        { label: "Order Size", value: a.size },
                        { label: "Leverage",   value: a.leverage },
                        { label: "Confidence", value: `${a.confidence}%` },
                      ].map(({ label, value }) => (
                        <div key={label} className="contents">
                          <span className="text-[9px] uppercase tracking-wide text-lm-muted self-center">
                            {label}
                          </span>
                          <span className="num text-right text-lm-text">{value}</span>
                        </div>
                      ))}
                    </div>

                    <div className="space-y-2">
                      <div>
                        <p className="text-[9px] uppercase tracking-widest text-lm-muted mb-0.5">
                          Reason
                        </p>
                        <p className="text-[11px] text-lm-text-dim leading-snug">{a.reason}</p>
                      </div>
                      <div>
                        <p className="text-[9px] uppercase tracking-widest text-lm-muted mb-0.5">
                          Suggested Action
                        </p>
                        <p className="text-[11px] text-lm-text-dim leading-snug">{a.action}</p>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            );
          })}

          {filtered.length === 0 && (
            <div className="px-3 py-10 text-center">
              <p className="text-lm-muted text-[12px]">No alerts match the current filters.</p>
              <button
                className="mt-2 text-[11px] text-lm-cyan hover:text-cyan-300 transition-colors"
                onClick={() => { setRisk("ALL"); setSide("ALL"); }}
              >
                Clear filters
              </button>
            </div>
          )}
        </Panel>
      </div>
    </div>
  );
}
