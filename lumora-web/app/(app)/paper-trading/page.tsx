import { Panel } from "@/components/ui/Panel";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { PageShell } from "@/components/ui/PageShell";
import { MetricStrip } from "@/components/ui/MetricStrip";
import { mockPaperTrades, mockJournal } from "@/lib/mock-data";
import { fmtNum, fmtUsd } from "@/lib/format";
import { clsx } from "clsx";
import { TrendingUp, TrendingDown, BookOpen } from "lucide-react";

const MOCK_BALANCE = 10000;

export default function PaperTradingPage() {
  const totalPnl = mockPaperTrades.reduce((s, t) => s + t.pnl, 0);
  const equity = MOCK_BALANCE + totalPnl;
  const winCount = mockJournal.filter((j) => j.pnl > 0).length;
  const winRate = Math.round((winCount / mockJournal.length) * 100);

  const fmtSignedUsd = (n: number) =>
    `${n < 0 ? "-" : ""}${fmtUsd(Math.abs(n))}`;

  return (
    <PageShell
      title={
        <>
          <BookOpen className="h-4 w-4 text-lm-purple" /> Paper Trading Desk
        </>
      }
      context="Practice with mock capital — demo data, no real funds"
      status={<StatusBadge variant="demo" size="sm">Mock Mode</StatusBadge>}
    >
      {/* Account / portfolio KPI strip */}
      <MetricStrip
        columns={4}
        size="lg"
        metrics={[
          {
            label: "Mock Equity",
            value: fmtUsd(equity),
            sub: `base ${fmtUsd(MOCK_BALANCE)}`,
          },
          {
            label: "Open P&L",
            value: `${totalPnl >= 0 ? "+" : ""}${fmtSignedUsd(totalPnl)}`,
            valueClassName: clsx(
              "text-2xl",
              totalPnl >= 0 ? "text-emerald-400" : "text-red-400",
            ),
            sub: "unrealized",
          },
          {
            label: "Win Rate",
            value: `${winRate}%`,
            valueClassName: "text-2xl text-lm-cyan",
            sub: `${winCount} / ${mockJournal.length} closed`,
          },
          {
            label: "Open Positions",
            value: mockPaperTrades.length,
            sub: `of ${mockPaperTrades.length} max`,
          },
        ]}
      />

      {/* Form + positions */}
      <div className="grid grid-cols-1 lg:grid-cols-[340px_1fr] gap-3 items-start">

        {/* New trade Panel — secondary support */}
        <Panel level="subtle" flush className="p-3">
          <div className="flex items-center justify-between mb-3">
            <h2 className="lm-section-title">New Paper Trade</h2>
            <StatusBadge variant="demo" size="sm">Mock Only</StatusBadge>
          </div>
          <div className="space-y-2.5">
            {[
              { label: "Symbol",        placeholder: "e.g. BTCUSDT" },
              { label: "Entry Price",   placeholder: "67,100" },
              { label: "Position Size", placeholder: "0.5 BTC" },
              { label: "Stop Loss",     placeholder: "66,200" },
            ].map(({ label, placeholder }) => (
              <div key={label}>
                <label className="text-[9px] uppercase tracking-widest text-lm-muted block mb-1">
                  {label}
                </label>
                <input
                  disabled
                  placeholder={placeholder}
                  className="w-full num bg-lm-bg border border-lm-border rounded-md px-2.5 py-1.5 text-[12px] text-lm-text-dim placeholder:text-lm-border focus:outline-none cursor-not-allowed"
                />
              </div>
            ))}
          </div>
          <div className="flex gap-2 mt-3">
            <button
              disabled
              className="flex-1 py-1.5 rounded-md bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 text-[12px] font-semibold uppercase tracking-wide cursor-not-allowed opacity-60"
            >
              Long
            </button>
            <button
              disabled
              className="flex-1 py-1.5 rounded-md bg-red-500/15 text-red-400 border border-red-500/30 text-[12px] font-semibold uppercase tracking-wide cursor-not-allowed opacity-60"
            >
              Short
            </button>
          </div>
          <p className="text-[10px] text-lm-muted text-center mt-2 leading-snug">
            Execution enabled in next release
          </p>
        </Panel>

        {/* Positions */}
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="lm-section-title">Open Positions</h2>
            <span className="text-[10px] text-lm-muted num">{mockPaperTrades.length} active</span>
          </div>

          {/* Position table (Panel-wrapped) */}
          <Panel flush className="overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-[12px]">
                <thead>
                  <tr className="border-b border-lm-border text-lm-muted text-[10px] uppercase tracking-widest">
                    <th className="px-3 py-2 text-left">Symbol</th>
                    <th className="px-2 py-2 text-left">Side</th>
                    <th className="px-2 py-2 text-right num">Entry</th>
                    <th className="px-2 py-2 text-right num">Current</th>
                    <th className="px-2 py-2 text-right num">Size</th>
                    <th className="px-2 py-2 text-right num">P&amp;L</th>
                    <th className="px-2 py-2 text-right num">%</th>
                    <th className="px-2 py-2 text-right">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-lm-border/60">
                  {mockPaperTrades.map((t) => {
                    const isLong = t.side === "LONG";
                    const positive = t.pnl >= 0;
                    return (
                      <tr key={t.id} className="lm-row">
                        <td className={clsx(
                          "relative pl-4 pr-3 py-2 num font-semibold text-lm-text",
                          isLong ? "lm-rail-bid" : "lm-rail-ask",
                        )}>
                          {t.symbol}
                        </td>
                        <td className="px-2 py-2">
                          <StatusBadge variant={isLong ? "bid" : "ask"} size="sm">
                            {t.side}
                          </StatusBadge>
                        </td>
                        <td className="px-2 py-2 num text-right text-lm-muted">
                          {fmtNum(t.entry)}
                        </td>
                        <td className="px-2 py-2 num text-right text-lm-text">
                          {fmtNum(t.current)}
                        </td>
                        <td className="px-2 py-2 num text-right text-lm-muted">{t.size}</td>
                        <td className={clsx(
                          "px-2 py-2 num text-right font-semibold",
                          positive ? "text-emerald-400" : "text-red-400",
                        )}>
                          {positive ? "+" : ""}${t.pnl}
                        </td>
                        <td className={clsx(
                          "px-2 py-2 num text-right",
                          positive ? "text-emerald-400" : "text-red-400",
                        )}>
                          {positive ? "+" : ""}{t.pnlPct}%
                        </td>
                        <td className="px-2 py-2 text-right">
                          <StatusBadge
                            variant={t.status === "OPEN" ? "live" : "warning"}
                            size="sm"
                            dot={t.status === "OPEN"}
                          >
                            {t.status}
                          </StatusBadge>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </Panel>

          {/* Per-position setup context */}
          <div className="space-y-1.5">
            {mockPaperTrades.map((t) => {
              const isLong = t.side === "LONG";
              const positive = t.pnl >= 0;
              return (
                <Panel
                  flush
                  hover
                  key={t.id}
                  className={clsx(
                    "lm-row relative px-3 py-2 flex items-start gap-3",
                    isLong ? "lm-rail-bid pl-4" : "lm-rail-ask pl-4",
                  )}
                >
                  <div className="shrink-0 mt-0.5">
                    <StatusBadge variant={isLong ? "bid" : "ask"} size="sm">
                      {t.symbol.replace("USDT", "")}
                    </StatusBadge>
                  </div>
                  <p className="text-[11.5px] text-lm-text-dim leading-snug flex-1">{t.setup}</p>
                  <span className={clsx(
                    "lm-price text-[13px] shrink-0",
                    positive ? "text-emerald-400" : "text-red-400",
                  )}>
                    {positive ? "+" : ""}${t.pnl}
                  </span>
                </Panel>
              );
            })}
          </div>
        </div>
      </div>

      {/* Trade Journal */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <h2 className="lm-section-title">Trade Journal</h2>
          <span className="text-[10px] text-lm-muted num">
            {mockJournal.length} entries · {winCount}W / {mockJournal.length - winCount}L
          </span>
        </div>
        <Panel flush className="overflow-hidden divide-y divide-lm-border/60">
          {mockJournal.map((j, i) => {
            const positive = j.pnl > 0;
            return (
              <div
                key={i}
                className={clsx(
                  "lm-row relative px-3 py-2 grid grid-cols-[28px_1fr_auto] items-start gap-3",
                  positive ? "lm-rail-bid pl-4" : "lm-rail-ask pl-4",
                )}
              >
                <div className={clsx(
                  "mt-0.5 p-1 rounded",
                  positive ? "bg-emerald-500/10 text-emerald-400" : "bg-red-500/10 text-red-400",
                )}>
                  {positive
                    ? <TrendingUp className="h-3 w-3" />
                    : <TrendingDown className="h-3 w-3" />}
                </div>
                <div className="min-w-0">
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <span className="num text-[12px] font-semibold text-lm-text">{j.symbol}</span>
                    <StatusBadge variant={j.side === "LONG" ? "bid" : "ask"} size="sm">
                      {j.side}
                    </StatusBadge>
                    <span className="num text-[10px] text-lm-muted ml-auto sm:ml-0">{j.date}</span>
                  </div>
                  <p className="text-[11px] text-lm-text-dim leading-snug mt-0.5">{j.note}</p>
                </div>
                <span className={clsx(
                  "lm-price text-[13px] shrink-0",
                  positive ? "text-emerald-400" : "text-red-400",
                )}>
                  {positive ? "+" : ""}${j.pnl}
                </span>
              </div>
            );
          })}
        </Panel>
      </div>
    </PageShell>
  );
}
