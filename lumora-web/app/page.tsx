import Link from "next/link";
import { Activity, Zap, Layers, Bell, BookOpen, Monitor, ArrowRight, MessageCircle } from "lucide-react";
import { GlassCard } from "@/components/ui/GlassCard";
import { Badge } from "@/components/ui/Badge";
import { roadmapItems } from "@/lib/mock-data";
import { clsx } from "clsx";

const features = [
  {
    icon: Monitor,
    title: "Pro Orderbook Terminal",
    desc: "Real-time bid/ask depth with wall detection, pressure ratio, and size-highlighted rows — built for fast reads.",
    badge: "Live",
  },
  {
    icon: Layers,
    title: "Liquidity Maps",
    desc: "Bookmap-style heatmap showing where large liquidity clusters over time. Spot walls before price hits them.",
    badge: "Beta",
  },
  {
    icon: Zap,
    title: "Whale Alert Engine",
    desc: "Track large spot and derivatives whale activity across Binance, Bybit, OKX and Coinbase in real time.",
    badge: "Live",
  },
  {
    icon: Activity,
    title: "AI Market Bias",
    desc: "Multi-signal engine combines CVD, OI, tape absorption and liquidity to generate directional conviction scores.",
    badge: "Q3 2026",
  },
  {
    icon: Bell,
    title: "Smart Alerts",
    desc: "Custom webhook and Discord alerts when your exact price + size conditions are met. No noise.",
    badge: "Q4 2026",
  },
  {
    icon: BookOpen,
    title: "Paper Trading",
    desc: "Test your edge with mock capital, structured journaling and P&L tracking — zero risk.",
    badge: "Beta",
  },
];

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-lumora-bg overflow-hidden">
      {/* Nav */}
      <nav className="sticky top-0 z-50 border-b border-lumora-border bg-lumora-bg/80 backdrop-blur-xl">
        <div className="mx-auto max-w-6xl px-4 sm:px-6 lg:px-8 h-14 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Activity className="h-5 w-5 text-lumora-purple" strokeWidth={2.5} />
            <span className="text-lg font-semibold text-neon-purple">Lumora</span>
          </div>
          <div className="flex items-center gap-3">
            <Badge variant="purple">
              <span className="mr-1 h-1.5 w-1.5 rounded-full bg-purple-400 animate-pulse inline-block" />
              Private Beta
            </Badge>
            <Link
              href="/dashboard"
              className="px-4 py-1.5 rounded-lg bg-lumora-purple text-white text-sm font-medium hover:bg-purple-500 transition-colors"
            >
              Open App
            </Link>
          </div>
        </div>
      </nav>

      {/* Hero */}
      <section className="relative pt-24 pb-16 px-4 text-center overflow-hidden">
        <div className="absolute inset-0 bg-hero-glow pointer-events-none" />
        <div className="relative mx-auto max-w-3xl">
          <Badge variant="purple" className="mb-6 text-xs">
            Now in Private Beta — Limited Access
          </Badge>
          <h1 className="text-4xl sm:text-5xl md:text-6xl font-bold tracking-tight text-lumora-text leading-tight">
            Market Intelligence for
            <br />
            <span className="text-neon-purple">Serious Crypto Traders</span>
          </h1>
          <p className="mt-6 text-lg text-lumora-text-dim max-w-2xl mx-auto leading-relaxed">
            See liquidity walls, whale activity and orderbook pressure before they become obvious on the chart.
          </p>
          <p className="mt-3 text-sm text-lumora-muted max-w-xl mx-auto">
            Lumora combines orderbook depth, liquidity mapping, whale alerts and market setup context in one premium trading terminal.
            <span className="block mt-1.5 text-[12px] text-lumora-border">Demo data shown — live data integrations coming.</span>
          </p>
          <div className="mt-8 flex flex-col sm:flex-row gap-3 justify-center">
            <Link
              href="/dashboard"
              className="flex items-center justify-center gap-2 px-6 py-3 rounded-xl bg-lumora-purple text-white font-semibold hover:bg-purple-500 transition-colors shadow-neon-purple"
            >
              Open App <ArrowRight className="h-4 w-4" />
            </Link>
            {/* TODO: replace with Lumora Discord invite */}
            <a
              href="#"
              className="flex items-center justify-center gap-2 px-6 py-3 rounded-xl border border-lumora-border text-lumora-text font-medium hover:border-lumora-purple/50 hover:bg-lumora-surface transition-all"
            >
              <MessageCircle className="h-4 w-4 text-lumora-cyan" />
              Join Discord
            </a>
          </div>
        </div>
      </section>

      {/* Context not noise */}
      <section className="py-8 px-4">
        <div className="mx-auto max-w-4xl">
          <GlassCard className="px-6 py-5 flex flex-col sm:flex-row items-start sm:items-center gap-4" glow="none">
            <div className="flex-1">
              <p className="text-base font-semibold text-lumora-text">
                Built for traders who need context, not noise.
              </p>
              <p className="text-sm text-lumora-muted mt-1">
                Lumora surfaces the information behind the price move — bid/ask walls, whale flow and liquidity gaps — so
                you can act on context rather than react to candles.
              </p>
            </div>
            <div className="shrink-0">
              <Badge variant="muted" className="text-[11px]">Demo data shown · Live integrations coming</Badge>
            </div>
          </GlassCard>
        </div>
      </section>

      {/* Feature cards */}
      <section className="py-12 px-4">
        <div className="mx-auto max-w-6xl">
          <div className="text-center mb-12">
            <h2 className="text-2xl font-bold text-lumora-text">Everything you need. Nothing you don&apos;t.</h2>
            <p className="text-lumora-muted mt-2">Built around the workflows of professional traders, not retail apps.</p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {features.map(({ icon: Icon, title, desc, badge }) => (
              <GlassCard key={title} className="p-5" hover>
                <div className="flex items-start justify-between mb-3">
                  <div className="p-2 rounded-lg bg-lumora-purple/15">
                    <Icon className="h-5 w-5 text-lumora-purple" />
                  </div>
                  <Badge variant={badge === "Live" ? "green" : badge === "Beta" ? "cyan" : "muted"}>
                    {badge}
                  </Badge>
                </div>
                <h3 className="font-semibold text-lumora-text mb-1.5">{title}</h3>
                <p className="text-sm text-lumora-text-dim leading-relaxed">{desc}</p>
              </GlassCard>
            ))}
          </div>
        </div>
      </section>

      {/* Beta CTA */}
      <section className="py-16 px-4">
        <div className="mx-auto max-w-2xl text-center">
          <GlassCard className="p-10" glow="purple">
            <Badge variant="purple" className="mb-4">Limited Beta Access</Badge>
            <h2 className="text-2xl font-bold text-lumora-text mb-3">Get early access to Lumora</h2>
            <p className="text-lumora-muted mb-6 text-sm">
              We&apos;re onboarding a small group of serious traders. Join the waitlist or request access via Discord.
            </p>
            <div className="flex flex-col sm:flex-row gap-3 justify-center">
              <button className="flex items-center justify-center gap-2 px-6 py-3 rounded-xl bg-lumora-purple text-white font-semibold hover:bg-purple-500 transition-colors">
                Request Beta Access
              </button>
              {/* TODO: replace with Lumora Discord invite */}
              <a
                href="#"
                className="flex items-center justify-center gap-2 px-6 py-3 rounded-xl border border-lumora-border text-lumora-text font-medium hover:border-lumora-cyan/50 transition-all"
              >
                <MessageCircle className="h-4 w-4 text-lumora-cyan" />
                Join Discord
              </a>
            </div>
          </GlassCard>
        </div>
      </section>

      {/* Roadmap */}
      <section className="py-16 px-4">
        <div className="mx-auto max-w-5xl">
          <div className="text-center mb-10">
            <h2 className="text-2xl font-bold text-lumora-text">Roadmap</h2>
            <p className="text-lumora-muted mt-2">Where we&apos;re going and how fast we&apos;re getting there.</p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {roadmapItems.map((item) => (
              <GlassCard key={item.phase} className="p-5">
                <div className="flex items-center justify-between mb-3">
                  <Badge
                    variant={item.status === "active" ? "green" : item.status === "upcoming" ? "cyan" : "muted"}
                  >
                    {item.status === "active" ? "In Progress" : item.status === "upcoming" ? "Up Next" : "Planned"}
                  </Badge>
                  <span className="num text-xs text-lumora-muted">{item.phase}</span>
                </div>
                <h3 className="font-semibold text-lumora-text mb-3">{item.title}</h3>
                <ul className="space-y-1.5">
                  {item.items.map((it) => (
                    <li key={it} className="text-xs text-lumora-text-dim flex items-start gap-1.5">
                      <span className={clsx("mt-1 h-1 w-1 rounded-full shrink-0",
                        item.status === "active" ? "bg-green-400" : item.status === "upcoming" ? "bg-cyan-400" : "bg-lumora-border"
                      )} />
                      {it}
                    </li>
                  ))}
                </ul>
              </GlassCard>
            ))}
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-lumora-border py-8 px-4">
        <div className="mx-auto max-w-6xl flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <Activity className="h-4 w-4 text-lumora-purple" />
            <span className="text-sm font-semibold text-neon-purple">Lumora</span>
            <span className="text-xs text-lumora-muted ml-2">Trading Intelligence Terminal</span>
          </div>
          <p className="text-xs text-lumora-muted">© 2026 Lumora. Not financial advice. For informational use only.</p>
        </div>
      </footer>
    </div>
  );
}
