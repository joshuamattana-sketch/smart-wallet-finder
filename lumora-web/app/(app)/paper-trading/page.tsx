import { GlassCard } from "@/components/ui/GlassCard";
import { Badge } from "@/components/ui/Badge";
import { mockPaperTrades, mockJournal } from "@/lib/mock-data";
import { clsx } from "clsx";
import { TrendingUp, TrendingDown } from "lucide-react";

export default function PaperTradingPage() {
  const totalPnl = mockPaperTrades.reduce((s, t) => s + t.pnl, 0);

  return (
    <div className="space-y-6 animate-[fadeIn_0.4s_ease-out]">
      <div>
        <h1 className="text-xl font-semibold text-lumora-text">Paper Trading</h1>
        <p className="text-sm text-lumora-muted mt-0.5">Practice with mock capital — no real funds at risk</p>
      </div>

      {/* PnL Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          { label: "Total P&L", value: `+$${totalPnl}`, positive: true },
          { label: "Open Positions", value: String(mockPaperTrades.length), positive: null },
          { label: "Win Rate", value: "66.7%", positive: true },
          { label: "Mock Balance", value: "$10,469", positive: null },
        ].map(({ label, value, positive }) => (
          <GlassCard key={label} className="p-4">
            <p className="text-xs text-lumora-muted uppercase tracking-widest mb-2">{label}</p>
            <p className={clsx("num text-xl font-bold", positive === true ? "text-lumora-green" : "text-lumora-text")}>{value}</p>
          </GlassCard>
        ))}
      </div>

      {/* Open Positions */}
      <div>
        <h2 className="text-sm font-semibold uppercase tracking-widest text-lumora-muted mb-3">Open Positions</h2>
        <GlassCard className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-lumora-border text-lumora-muted text-xs uppercase tracking-wider">
                  <th className="px-4 py-3 text-left">Symbol</th>
                  <th className="px-4 py-3 text-left">Side</th>
                  <th className="px-4 py-3 text-right num">Entry</th>
                  <th className="px-4 py-3 text-right num">Current</th>
                  <th className="px-4 py-3 text-right num">Size</th>
                  <th className="px-4 py-3 text-right num">P&L</th>
                  <th className="px-4 py-3 text-right num">%</th>
                  <th className="px-4 py-3 text-right">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-lumora-border/50">
                {mockPaperTrades.map((t) => (
                  <tr key={t.id} className="hover:bg-lumora-surface/40 transition-colors">
                    <td className="px-4 py-3 num font-semibold text-lumora-text">{t.symbol}</td>
                    <td className="px-4 py-3">
                      <Badge variant={t.side === "LONG" ? "green" : "red"}>{t.side}</Badge>
                    </td>
                    <td className="px-4 py-3 num text-right text-lumora-text-dim">{t.entry.toLocaleString()}</td>
                    <td className="px-4 py-3 num text-right text-lumora-text">{t.current.toLocaleString()}</td>
                    <td className="px-4 py-3 num text-right text-lumora-text-dim">{t.size}</td>
                    <td className="px-4 py-3 num text-right text-lumora-green">+${t.pnl}</td>
                    <td className="px-4 py-3 num text-right text-lumora-green">+{t.pnlPct}%</td>
                    <td className="px-4 py-3 text-right">
                      <Badge variant="cyan">{t.status}</Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </GlassCard>
      </div>

      {/* New Paper Trade Card */}
      <div>
        <h2 className="text-sm font-semibold uppercase tracking-widest text-lumora-muted mb-3">Open Paper Trade</h2>
        <GlassCard className="p-5">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {[
              { label: "Symbol", placeholder: "e.g. BTCUSDT" },
              { label: "Entry Price", placeholder: "67420" },
              { label: "Position Size", placeholder: "0.5" },
              { label: "Stop Loss", placeholder: "66800" },
            ].map(({ label, placeholder }) => (
              <div key={label}>
                <label className="text-xs text-lumora-muted block mb-1.5">{label}</label>
                <input
                  disabled
                  placeholder={placeholder}
                  className="w-full num bg-lumora-bg border border-lumora-border rounded-lg px-3 py-2 text-sm text-lumora-text-dim placeholder:text-lumora-border focus:outline-none cursor-not-allowed"
                />
              </div>
            ))}
          </div>
          <div className="flex gap-3 mt-4">
            <button disabled className="px-5 py-2 rounded-lg bg-green-500/20 text-green-400 border border-green-500/30 text-sm font-medium cursor-not-allowed opacity-60">
              Long
            </button>
            <button disabled className="px-5 py-2 rounded-lg bg-red-500/20 text-red-400 border border-red-500/30 text-sm font-medium cursor-not-allowed opacity-60">
              Short
            </button>
            <span className="text-xs text-lumora-muted self-center ml-2">Mock only — no real funds</span>
          </div>
        </GlassCard>
      </div>

      {/* Trade Journal */}
      <div>
        <h2 className="text-sm font-semibold uppercase tracking-widest text-lumora-muted mb-3">Trade Journal</h2>
        <div className="space-y-2">
          {mockJournal.map((j, i) => (
            <GlassCard key={i} className="p-4 flex items-start gap-4">
              <div className={clsx("mt-0.5 shrink-0", j.pnl > 0 ? "text-lumora-green" : "text-lumora-red")}>
                {j.pnl > 0 ? <TrendingUp className="h-4 w-4" /> : <TrendingDown className="h-4 w-4" />}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="num text-sm font-semibold text-lumora-text">{j.symbol}</span>
                  <Badge variant={j.side === "LONG" ? "green" : "red"}>{j.side}</Badge>
                  <span className="text-xs text-lumora-muted">{j.date}</span>
                </div>
                <p className="text-xs text-lumora-muted mt-1">{j.note}</p>
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
