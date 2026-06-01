import { KpiCard } from "@/components/ui/KpiCard";
import { GlassCard } from "@/components/ui/GlassCard";
import { Badge } from "@/components/ui/Badge";
import { mockKpis, mockSetups, mockWhaleAlerts, mockLiquidityZones } from "@/lib/mock-data";
import { clsx } from "clsx";
import { TrendingUp, TrendingDown, Minus, Activity, Zap } from "lucide-react";

export default function DashboardPage() {
  return (
    <div className="space-y-6 animate-[fadeIn_0.4s_ease-out]">
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

      {/* Main grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Top Setups */}
        <div className="lg:col-span-2 space-y-3">
          <h2 className="text-sm font-semibold uppercase tracking-widest text-lumora-muted flex items-center gap-2">
            <TrendingUp className="h-3.5 w-3.5 text-lumora-purple" /> Top Market Setups
          </h2>
          <div className="space-y-2">
            {mockSetups.map((s) => (
              <GlassCard key={s.symbol} className="p-4 flex items-center gap-4">
                <div className="shrink-0 w-20">
                  <p className="num text-sm font-semibold text-lumora-text">{s.symbol}</p>
                  <Badge variant={s.bias === "LONG" ? "green" : s.bias === "SHORT" ? "red" : "muted"} className="mt-1">
                    {s.bias}
                  </Badge>
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-xs text-lumora-muted truncate">{s.reason}</p>
                </div>
                <div className="shrink-0 text-right space-y-1">
                  <div className="flex items-center gap-3 text-xs num">
                    <span className="text-lumora-muted">Entry</span>
                    <span className="text-lumora-text">{s.entry}</span>
                  </div>
                  <div className="flex items-center gap-3 text-xs num">
                    <span className="text-lumora-muted">Target</span>
                    <span className="text-lumora-green">{s.target}</span>
                  </div>
                </div>
                <div className="shrink-0 w-16 text-right">
                  <div className="text-xs text-lumora-muted mb-1">Confidence</div>
                  <div className="h-1.5 rounded-full bg-lumora-border overflow-hidden">
                    <div
                      className="h-full rounded-full bg-gradient-to-r from-lumora-purple to-lumora-cyan"
                      style={{ width: `${s.confidence}%` }}
                    />
                  </div>
                  <p className="num text-xs text-lumora-text-dim mt-1">{s.confidence}%</p>
                </div>
              </GlassCard>
            ))}
          </div>
        </div>

        {/* Right column */}
        <div className="space-y-4">
          {/* Whale Alerts Panel */}
          <div>
            <h2 className="text-sm font-semibold uppercase tracking-widest text-lumora-muted flex items-center gap-2 mb-3">
              <Zap className="h-3.5 w-3.5 text-lumora-cyan" /> Whale Alerts
            </h2>
            <div className="space-y-2 max-h-64 overflow-y-auto pr-1">
              {mockWhaleAlerts.map((a) => (
                <GlassCard key={a.id} className="p-3 flex items-center gap-3">
                  <div className="shrink-0">
                    <Badge variant={a.side === "BUY" ? "green" : "red"}>{a.side}</Badge>
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium text-lumora-text">{a.symbol} · {a.type}</p>
                    <p className="num text-xs text-lumora-muted">{a.exchange} · {a.time}</p>
                  </div>
                  <div className="shrink-0 text-right">
                    <p className="num text-sm font-semibold text-lumora-text">{a.size}</p>
                    <Badge variant={a.risk === "HIGH" ? "red" : a.risk === "MEDIUM" ? "yellow" : "muted"} className="mt-0.5">
                      {a.risk}
                    </Badge>
                  </div>
                </GlassCard>
              ))}
            </div>
          </div>

          {/* Liquidity Highlights */}
          <div>
            <h2 className="text-sm font-semibold uppercase tracking-widest text-lumora-muted flex items-center gap-2 mb-3">
              <Activity className="h-3.5 w-3.5 text-lumora-purple" /> Liquidity Walls
            </h2>
            <div className="space-y-2">
              {mockLiquidityZones.map((z) => (
                <GlassCard key={z.price} className="p-3 flex items-center gap-3">
                  <div className="shrink-0 w-2 h-8 rounded-full" style={{
                    background: z.intensity > 80
                      ? "linear-gradient(180deg, #c084fc, #8b5cf6)"
                      : "linear-gradient(180deg, #22d3ee, #0891b2)"
                  }} />
                  <div className="flex-1">
                    <p className="num text-sm font-medium text-lumora-text">${z.price.toLocaleString()}</p>
                    <p className="text-xs text-lumora-muted">{z.label}</p>
                  </div>
                  <div className="text-right">
                    <Badge variant={z.side === "ASK" ? "red" : "green"}>{z.side}</Badge>
                    <p className="num text-xs text-lumora-text-dim mt-1">{z.intensity}% intensity</p>
                  </div>
                </GlassCard>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Market Bias Cards */}
      <div>
        <h2 className="text-sm font-semibold uppercase tracking-widest text-lumora-muted mb-3">Market Bias Overview</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[
            { symbol: "BTC", bias: "BULLISH", strength: 78, icon: TrendingUp, color: "text-lumora-green" },
            { symbol: "ETH", bias: "BULLISH", strength: 65, icon: TrendingUp, color: "text-lumora-green" },
            { symbol: "SOL", bias: "BEARISH", strength: 61, icon: TrendingDown, color: "text-lumora-red" },
            { symbol: "BNB", bias: "NEUTRAL", strength: 50, icon: Minus, color: "text-lumora-muted" },
          ].map(({ symbol, bias, strength, icon: Icon, color }) => (
            <GlassCard key={symbol} className="p-4 text-center">
              <Icon className={clsx("h-5 w-5 mx-auto mb-2", color)} />
              <p className="num text-lg font-semibold text-lumora-text">{symbol}</p>
              <p className={clsx("text-xs font-medium mt-0.5", color)}>{bias}</p>
              <div className="mt-2 h-1 rounded-full bg-lumora-border overflow-hidden">
                <div className="h-full rounded-full bg-lumora-purple" style={{ width: `${strength}%` }} />
              </div>
              <p className="num text-xs text-lumora-muted mt-1">{strength}%</p>
            </GlassCard>
          ))}
        </div>
      </div>
    </div>
  );
}
