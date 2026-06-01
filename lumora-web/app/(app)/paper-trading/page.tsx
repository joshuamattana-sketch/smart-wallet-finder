import { GlassCard } from "@/components/ui/GlassCard";
import { Badge } from "@/components/ui/Badge";
import { mockPaperTrades, mockJournal } from "@/lib/mock-data";
import { clsx } from "clsx";
import { TrendingUp, TrendingDown, BookOpen } from "lucide-react";

const MOCK_BALANCE = 10000;

export default function PaperTradingPage() {
  const totalPnl = mockPaperTrades.reduce((s, t) => s + t.pnl, 0);
  const equity = MOCK_BALANCE + totalPnl;
  const winCount = mockJournal.filter((j) => j.pnl > 0).length;
  const winRate = Math.round((winCount / mockJournal.length) * 100);

  return (
    <div className="space-y-5 animate-[fadeIn_0.4s_ease-out]">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-semibold text-lumora-text flex items-center gap-2">
            <BookOpen className="h-5 w-5 text-lumora-purple" /> Paper Trading
          </h1>
          <p className="text-sm text-lumora-muted mt-0.5">Practice with mock capital — demo data, no real funds</p>
        </div>
        <Badge variant="muted">Mock Mode</Badge>
      </div>

      {/* PnL summary */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {[
          { label: "Mock Equity",     value: `$${equity.toLocaleString()}`, positive: null  },
          { label: "Open P&L",        value: `+$${totalPnl}`,              positive: true  },
          { label: "Win Rate",        value: `${winRate}%`,                positive: true  },
          { label: "Open Positions",  value: String(mockPaperTrades.length), positive: null },
        ].map(({ label, value, positive }) => (
          <GlassCard key={label} className="p-4">
            <p className="text-[11px] text-lumora-muted uppercase tracking-widest mb-1.5">{label}</p>
            <p className={clsx("num text-xl font-bold", positive === true ? "text-lumora-green" : "text-lumora-text")}>
              {value}
            </p>
          </GlassCard>
        ))}
      </div>

      {/* Form + positions */}
      <div className="grid grid-cols-1 lg:grid-cols-[360px_1fr] gap-5 items-start">

        {/* Open trade card */}
        <GlassCard className="p-4" glow="purple">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold text-lumora-text">New Paper Trade</h2>
            <Badge variant="purple">Mock Only</Badge>
          </div>
          <div className="space-y-3">
            {[
              { label: "Symbol",               placeholder: "e.g. BTCUSDT"  },
              { label: "Entry Price",           placeholder: "67,100"        },
              { label: "Position Size",         placeholder: "0.5 BTC"       },
              { label: "Stop Loss",             placeholder: "66,200"        },
            ].map(({ label, placeholder }) => (
              <div key={label}>
                <label className="text-[11px] text-lumora-muted uppercase tracking-wide block mb-1">
                  {label}
                </label>
                <input
                  disabled
                  placeholder={placeholder}
                  className="w-full num bg-lumora-bg border border-lumora-border/60 rounded-lg px-3 py-2 text-sm text-lumora-text-dim placeholder:text-lumora-border focus:outline-none cursor-not-allowed"
                />
              </div>
            ))}
          </div>
          <div className="flex gap-2 mt-4">
            <button disabled className="flex-1 py-2 rounded-lg bg-green-500/20 text-green-400 border border-green-500/30 text-sm font-semibold cursor-not-allowed opacity-60">
              Long
            </button>
            <button disabled className="flex-1 py-2 rounded-lg bg-red-500/20 text-red-400 border border-red-500/30 text-sm font-semibold cursor-not-allowed opacity-60">
              Short
            </button>
          </div>
          <p className="text-[11px] text-lumora-muted text-center mt-2">
            Execution enabled in next release
          </p>
        </GlassCard>

        {/* Positions + P&L bars */}
        <div className="space-y-4">
          <h2 className="text-xs font-semibold uppercase tracking-widest text-lumora-muted">Open Positions</h2>
          <GlassCard className="overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-lumora-border text-lumora-muted text-[11px] uppercase tracking-wider">
                    <th className="px-4 py-2.5 text-left">Symbol</th>
                    <th className="px-3 py-2.5 text-left">Side</th>
                    <th className="px-3 py-2.5 text-right num">Entry</th>
                    <th className="px-3 py-2.5 text-right num">Current</th>
                    <th className="px-3 py-2.5 text-right num">Size</th>
                    <th className="px-3 py-2.5 text-right num">P&amp;L</th>
                    <th className="px-3 py-2.5 text-right num">%</th>
                    <th className="px-3 py-2.5 text-right">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-lumora-border/40">
                  {mockPaperTrades.map((t) => (
                    <tr key={t.id} className="hover:bg-lumora-surface/40 transition-colors">
                      <td className="px-4 py-3 num font-semibold text-lumora-text">{t.symbol}</td>
                      <td className="px-3 py-3">
                        <Badge variant={t.side === "LONG" ? "green" : "red"}>{t.side}</Badge>
                      </td>
                      <td className="px-3 py-3 num text-right text-lumora-muted">{t.entry.toLocaleString()}</td>
                      <td className="px-3 py-3 num text-right text-lumora-text">{t.current.toLocaleString()}</td>
                      <td className="px-3 py-3 num text-right text-lumora-muted">{t.size}</td>
                      <td className="px-3 py-3 num text-right text-lumora-green font-semibold">+${t.pnl}</td>
                      <td className="px-3 py-3 num text-right text-lumora-green">+{t.pnlPct}%</td>
                      <td className="px-3 py-3 text-right">
                        <Badge variant={t.status === "OPEN" ? "green" : "yellow"}>{t.status}</Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </GlassCard>

          {/* Setup context per position */}
          <div className="space-y-2">
            {mockPaperTrades.map((t) => (
              <GlassCard key={t.id} className="px-4 py-3 flex items-start gap-3">
                <div className="shrink-0 mt-0.5">
                  <Badge variant={t.side === "LONG" ? "green" : "red"}>{t.symbol.replace("USDT", "")}</Badge>
                </div>
                <p className="text-xs text-lumora-muted leading-relaxed flex-1">{t.setup}</p>
                <span className={clsx("num text-sm font-bold shrink-0", t.pnl >= 0 ? "text-lumora-green" : "text-lumora-red")}>
                  +${t.pnl}
                </span>
              </GlassCard>
            ))}
          </div>
        </div>
      </div>

      {/* Trade Journal */}
      <div>
        <h2 className="text-xs font-semibold uppercase tracking-widest text-lumora-muted mb-3">Trade Journal</h2>
        <div className="space-y-2">
          {mockJournal.map((j, i) => (
            <GlassCard key={i} className="p-3 flex items-start gap-3">
              <div className={clsx(
                "mt-0.5 shrink-0 p-1.5 rounded-lg",
                j.pnl > 0 ? "bg-green-500/15 text-lumora-green" : "bg-red-500/15 text-lumora-red"
              )}>
                {j.pnl > 0
                  ? <TrendingUp className="h-3.5 w-3.5" />
                  : <TrendingDown className="h-3.5 w-3.5" />}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap mb-0.5">
                  <span className="num text-sm font-semibold text-lumora-text">{j.symbol}</span>
                  <Badge variant={j.side === "LONG" ? "green" : "red"}>{j.side}</Badge>
                  <span className="num text-[11px] text-lumora-muted">{j.date}</span>
                </div>
                <p className="text-xs text-lumora-muted leading-relaxed">{j.note}</p>
              </div>
              <div className={clsx("num font-bold text-sm shrink-0", j.pnl > 0 ? "text-lumora-green" : "text-lumora-red")}>
                {j.pnl > 0 ? "+" : ""}${j.pnl}
              </div>
            </GlassCard>
          ))}
        </div>
      </div>
    </div>
  );
}
