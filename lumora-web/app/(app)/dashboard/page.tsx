import { KpiCard } from "@/components/ui/KpiCard";
import { GlassCard } from "@/components/ui/GlassCard";
import { Badge } from "@/components/ui/Badge";
import { mockKpis, mockSetups, mockWhaleAlerts, mockLiquidityZones } from "@/lib/mock-data";
import { clsx } from "clsx";
import { TrendingUp, TrendingDown, Minus, Activity, Zap } from "lucide-react";

export default function DashboardPage() {
  return (
    <div className="space-y-5 animate-[fadeIn_0.4s_ease-out]">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-lumora-text">Market Dashboard</h1>
          <p className="text-sm text-lumora-muted mt-0.5">Live market intelligence — updated every 10s</p>
        </div>
        <div className="flex items-center gap-2 text-xs text-lumora-green">
          <span className="h-1.5 w-1.5 rounded-full bg-green-400 animate-pulse inline-block" />
          Live Feed Active
        </div>
      </div>

      {/* KPI Grid */}
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3">
        {mockKpis.map((kpi) => (
          <KpiCard key={kpi.label} {...kpi} />
        ))}
      </div>

      {/* Main 2-col grid — left takes 2/3, right panel takes 1/3 */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5 items-start">

        {/* Left — setups + bias */}
        <div className="lg:col-span-2 space-y-5">
          {/* Top Setups */}
          <div>
            <h2 className="text-xs font-semibold uppercase tracking-widest text-lumora-muted flex items-center gap-2 mb-2">
              <TrendingUp className="h-3.5 w-3.5 text-lumora-purple" /> Top Market Setups
            </h2>
            <div className="space-y-2">
              {mockSetups.map((s) => (
                <GlassCard key={s.symbol} className="p-3 flex items-center gap-4">
                  <div className="shrink-0 w-24">
                    <p className="num text-sm font-semibold text-lumora-text">{s.symbol}</p>
                    <Badge
                      variant={s.bias === "LONG" ? "green" : s.bias === "SHORT" ? "red" : "muted"}
                      className="mt-1"
                    >
                      {s.bias}
                    </Badge>
                  </div>
                  <div className="flex-1 min-w-0 hidden sm:block">
                    <p className="text-xs text-lumora-muted truncate">{s.reason}</p>
                  </div>
                  <div className="shrink-0 grid grid-cols-2 gap-x-4 gap-y-0.5 text-xs num">
                    <span className="text-lumora-muted">Entry</span>
                    <span className="text-lumora-text text-right">{s.entry}</span>
                    <span className="text-lumora-muted">Target</span>
                    <span className="text-lumora-green text-right">{s.target}</span>
                    <span className="text-lumora-muted">Stop</span>
                    <span className="text-lumora-red text-right">{s.stop}</span>
                  </div>
                  <div className="shrink-0 w-14 text-right">
                    <div className="h-1.5 rounded-full bg-lumora-border overflow-hidden">
                      <div
                        className="h-full rounded-full bg-gradient-to-r from-lumora-purple to-lumora-cyan"
                        style={{ width: `${s.confidence}%` }}
                      />
                    </div>
                    <p className="num text-[11px] text-lumora-text-dim mt-1">{s.confidence}%</p>
                  </div>
                </GlassCard>
              ))}
            </div>
          </div>

          {/* Market Bias */}
          <div>
            <h2 className="text-xs font-semibold uppercase tracking-widest text-lumora-muted mb-2">Market Bias</h2>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {[
                { symbol: "BTC", bias: "BULLISH", strength: 78, icon: TrendingUp, color: "text-lumora-green" },
                { symbol: "ETH", bias: "BULLISH", strength: 65, icon: TrendingUp, color: "text-lumora-green" },
                { symbol: "SOL", bias: "BEARISH", strength: 61, icon: TrendingDown, color: "text-lumora-red" },
                { symbol: "BNB", bias: "NEUTRAL", strength: 50, icon: Minus, color: "text-lumora-muted" },
              ].map(({ symbol, bias, strength, icon: Icon, color }) => (
                <GlassCard key={symbol} className="p-3 flex items-center gap-3">
                  <Icon className={clsx("h-4 w-4 shrink-0", color)} />
                  <div className="flex-1 min-w-0">
                    <p className="num text-sm font-semibold text-lumora-text">{symbol}</p>
                    <p className={clsx("text-[11px] font-medium", color)}>{bias}</p>
                  </div>
                  <div className="shrink-0 w-10">
                    <div className="h-1 rounded-full bg-lumora-border overflow-hidden">
                      <div className="h-full rounded-full bg-lumora-purple" style={{ width: `${strength}%` }} />
                    </div>
                    <p className="num text-[10px] text-lumora-muted text-right mt-0.5">{strength}%</p>
                  </div>
                </GlassCard>
              ))}
            </div>
          </div>
        </div>

        {/* Right panel — fixed height, internally scrollable sections */}
        <div className="space-y-4">
          {/* Whale Alerts — scrollable */}
          <GlassCard className="overflow-hidden">
            <div className="px-3 py-2.5 border-b border-lumora-border flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-widest text-lumora-muted flex items-center gap-1.5">
                <Zap className="h-3 w-3 text-lumora-cyan" /> Whale Alerts
              </span>
              <Badge variant="cyan">{mockWhaleAlerts.length}</Badge>
            </div>
            <div className="overflow-y-auto max-h-56 divide-y divide-lumora-border/40">
              {mockWhaleAlerts.map((a) => (
                <div key={a.id} className="px-3 py-2.5 flex items-center gap-2.5 hover:bg-lumora-surface/30 transition-colors">
                  <Badge variant={a.side === "BUY" ? "green" : "red"} className="shrink-0 w-10 justify-center">
                    {a.side}
                  </Badge>
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium text-lumora-text leading-tight">
                      {a.symbol}
                      <span className="text-lumora-muted font-normal"> · {a.type}</span>
                    </p>
                    <p className="num text-[11px] text-lumora-muted">{a.exchange} · {a.time}</p>
                  </div>
                  <div className="shrink-0 text-right">
                    <p className="num text-xs font-semibold text-lumora-text">{a.size}</p>
                    <Badge
                      variant={a.risk === "HIGH" ? "red" : a.risk === "MEDIUM" ? "yellow" : "muted"}
                      className="mt-0.5"
                    >
                      {a.risk}
                    </Badge>
                  </div>
                </div>
              ))}
            </div>
          </GlassCard>

          {/* Liquidity Walls */}
          <GlassCard className="overflow-hidden">
            <div className="px-3 py-2.5 border-b border-lumora-border flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-widest text-lumora-muted flex items-center gap-1.5">
                <Activity className="h-3 w-3 text-lumora-purple" /> Liquidity Walls
              </span>
              <Badge variant="purple">BTC</Badge>
            </div>
            <div className="divide-y divide-lumora-border/40">
              {mockLiquidityZones.map((z) => (
                <div key={z.price} className="px-3 py-2.5 flex items-center gap-2.5 hover:bg-lumora-surface/30 transition-colors">
                  <div
                    className="shrink-0 w-1.5 h-7 rounded-full"
                    style={{
                      background:
                        z.intensity > 80
                          ? "linear-gradient(180deg,#c084fc,#8b5cf6)"
                          : "linear-gradient(180deg,#22d3ee,#0891b2)",
                    }}
                  />
                  <div className="flex-1 min-w-0">
                    <p className="num text-xs font-medium text-lumora-text">${z.price.toLocaleString()}</p>
                    <p className="text-[11px] text-lumora-muted">{z.label}</p>
                  </div>
                  <div className="shrink-0 text-right space-y-0.5">
                    <Badge variant={z.side === "ASK" ? "red" : "green"}>{z.side}</Badge>
                    <p className="num text-[10px] text-lumora-text-dim">{z.intensity}%</p>
                  </div>
                </div>
              ))}
            </div>
          </GlassCard>
        </div>
      </div>
    </div>
  );
}
