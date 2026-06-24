"use client";

import { useState, useMemo, useEffect, useCallback } from "react";
import { getSupabaseBrowser } from "@/lib/supabase-browser";
import { Panel } from "@/components/ui/Panel";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { PageShell } from "@/components/ui/PageShell";
import { MetricStrip } from "@/components/ui/MetricStrip";
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

// Loose shape that fits both mock and journal-derived alerts.
interface AlertRow {
  id:         number | string;
  time:       string;
  symbol:     string;
  side:       "BUY" | "SELL";
  size:       string;
  exchange:   string;
  leverage:   string;
  type:       string;
  risk:       "HIGH" | "MEDIUM" | "LOW";
  confidence: number;
  reason:     string;
  action:     string;
}

type AlertsSource = "supabase" | "journal" | "mock";

interface AlertsResponse {
  data_source: AlertsSource;
  generated_at: string;
  row_count?: number;
  journal_row_count?: number;
  alerts: AlertRow[];
  note?: string;
}

const MOCK_FALLBACK: AlertRow[] = mockWhaleAlerts as unknown as AlertRow[];

export default function WhaleAlertsPage() {
  const [risk, setRisk] = useState<Risk>("ALL");
  const [side, setSide] = useState<Side>("ALL");
  const [expanded, setExpanded] = useState<number | string | null>(null);
  const [alerts, setAlerts] = useState<AlertRow[]>(MOCK_FALLBACK);
  const [source, setSource] = useState<AlertsSource>("mock");
  const [loading, setLoading] = useState<boolean>(true);
  const [note, setNote] = useState<string | null>(null);
  const [live, setLive] = useState<boolean>(false);

  const load = useCallback(async () => {
    try {
      const res = await fetch("/api/whale-alerts?limit=50", { cache: "no-store" });
      if (!res.ok) {
        setSource("mock");
        setAlerts(MOCK_FALLBACK);
        setNote(`api error ${res.status}`);
      } else {
        const data: AlertsResponse = await res.json();
        const incoming = Array.isArray(data.alerts) ? data.alerts : [];
        if (incoming.length === 0) {
          setSource("mock");
          setAlerts(MOCK_FALLBACK);
        } else {
          const resolved: AlertsSource =
            data.data_source === "supabase" ? "supabase" :
            data.data_source === "journal"  ? "journal"  : "mock";
          setSource(resolved);
          setAlerts(incoming);
        }
        setNote(typeof data.note === "string" ? data.note : null);
      }
    } catch {
      // Any fetch/JSON error → graceful fallback. Page is never broken.
      setSource("mock");
      setAlerts(MOCK_FALLBACK);
    } finally {
      setLoading(false);
    }
  }, []);

  // Initial load.
  useEffect(() => {
    void load();
  }, [load]);

  // Realtime (LM78A): a new whale_events row pushes an instant refetch — events
  // are sparse, so refetching reuses the API's normalization without polling.
  useEffect(() => {
    const supabase = getSupabaseBrowser();
    if (!supabase) return;
    const channel = supabase
      .channel("rt-whale-events")
      .on(
        "postgres_changes",
        { event: "INSERT", schema: "public", table: "whale_events" },
        () => void load(),
      )
      .subscribe((status) => setLive(status === "SUBSCRIBED"));
    return () => {
      void supabase.removeChannel(channel);
    };
  }, [load]);

  const filtered = useMemo(
    () =>
      alerts.filter(
        (a) => (risk === "ALL" || a.risk === risk) && (side === "ALL" || a.side === side),
      ),
    [alerts, risk, side],
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
    <PageShell
      title={
        <>
          <Zap className="h-4 w-4 text-lm-cyan" /> Whale Intelligence Feed
        </>
      }
      context={
        source === "supabase"
          ? "Live production feed — whale_events from Supabase."
          : source === "journal"
          ? "Live local journal — large order flow from Binance aggTrade detections."
          : "Large order flow & unusual activity across major venues — demo data."
      }
      status={
        <span className="flex items-center gap-2 text-[11px] text-lm-text-dim num uppercase tracking-wide">
          <StatusBadge
            variant={source === "mock" ? "demo" : "live"}
            size="sm"
            dot={source !== "mock"}
          >
            {source === "supabase" ? "SUPABASE" : source === "journal" ? "JOURNAL" : "DEMO"}
          </StatusBadge>
          <span className="text-lm-border">·</span>
          {loading ? (
            <span className="text-lm-muted">loading…</span>
          ) : (
            <>
              <span className="text-lm-text">{filtered.length}</span>
              <span className="text-lm-muted">/ {alerts.length}</span>
              {live && source !== "mock" && (
                <span className="ml-1 inline-flex items-center gap-1 text-emerald-400">
                  <span className="lm-live-dot inline-block h-1.5 w-1.5 rounded-full bg-emerald-400" />
                  live
                </span>
              )}
            </>
          )}
        </span>
      }
    >
      {note && source === "mock" && (
        <p className="text-[10px] text-lm-muted px-1 leading-snug">
          showing demo alerts · {note}
        </p>
      )}

      {/* Summary KPI strip */}
      <MetricStrip
        columns={4}
        metrics={[
          { label: "Total Flow", value: fmtUsd(stats.totalUsd) },
          { label: "Buys", value: String(stats.buys), valueClassName: "text-lg text-emerald-400" },
          { label: "Sells", value: String(stats.sells), valueClassName: "text-lg text-red-400" },
          { label: "High Risk", value: String(stats.high), valueClassName: "text-lg text-amber-400" },
        ]}
      />

      {/* Filter bar — quiet toolbar, not a competing surface */}
      <Panel level="subtle" flush className="p-2 flex flex-wrap items-center gap-2">
        <Filter className="h-3.5 w-3.5 text-lm-muted ml-0.5 shrink-0" />
        <span className="num text-[10px] uppercase tracking-widest text-lm-muted">Risk</span>
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
        <span className="num text-[10px] uppercase tracking-widest text-lm-muted">Side</span>
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
          <h2 className="lm-section-title">
            {source === "mock" ? "Demo Feed" : "Live Feed"}
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
                    "lm-row w-full px-3 py-2 text-left grid grid-cols-[40px_40px_minmax(0,1fr)_auto_auto_14px] sm:grid-cols-[44px_44px_minmax(0,1fr)_auto_auto_auto_14px] items-center gap-2 sm:gap-3",
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
    </PageShell>
  );
}
