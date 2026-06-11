import Link from "next/link";
import { Activity, ArrowRight, MessageCircle } from "lucide-react";
import { Panel } from "@/components/ui/Panel";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { LumoraFieldHero } from "@/components/landing/LumoraFieldHero";
import { MarketReplayStrip } from "@/components/landing/MarketReplayStrip";
import { LandingFeatureGrid } from "@/components/landing/LandingFeatureGrid";
import { clsx } from "clsx";

// ── Capabilities ticker — scrolling intelligence readout ─────────────────────
const PAGE_CSS = `
@media (prefers-reduced-motion: no-preference) {
  .lmk-track { animation: lmk-marquee 34s linear infinite; }
  .lmk-track:hover { animation-play-state: paused; }
  @keyframes lmk-marquee {
    to { transform: translateX(-50%); }
  }
}
@media (prefers-reduced-motion: reduce) {
  .lmk-track { width: 100%; flex-wrap: wrap; justify-content: center; }
  .lmk-dup { display: none; }
}
@media (prefers-reduced-motion: no-preference) {
  .lmb-drop { animation: lmb-drop 2.4s ease-in-out infinite; }
  @keyframes lmb-drop {
    0%   { transform: translateY(0); opacity: 0; }
    18%  { opacity: 0.9; }
    82%  { opacity: 0.9; }
    100% { transform: translateY(40px); opacity: 0; }
  }
}
`;

const CAPABILITIES = [
  "Orderbook depth · L2",
  "Whale tape · aggTrade",
  "Funding + open interest",
  "Liquidity heatmap",
  "Sweep risk zones",
  "Market reads",
  "Discord alerts",
];

// ── Market read examples ─────────────────────────────────────────────────────
// Illustrative Current Read cards in the app's own visual language — the
// landing-page proof that Lumora's output is a sentence, not a dashboard dump.

type Bias = "LONG" | "SHORT" | "NEUTRAL";

const READS: Array<{
  symbol: string;
  bias: Bias;
  score: number;
  risk: "LOW" | "MEDIUM" | "HIGH";
  reason: string;
  action: string;
}> = [
  {
    symbol: "BTCUSDT",
    bias: "LONG",
    score: 72,
    risk: "MEDIUM",
    reason: "Bid intensity 58% vs 42% ask — buyers leading into a support band that has held twice.",
    action: "Watch reclaim of 67,500 · read invalidates below 66,800.",
  },
  {
    symbol: "ETHUSDT",
    bias: "NEUTRAL",
    score: 41,
    risk: "LOW",
    reason: "Order book balanced near 50/50 — no clean directional edge in the current structure.",
    action: "Stand aside · wait for a sweep of either liquidity band.",
  },
  {
    symbol: "SOLUSDT",
    bias: "SHORT",
    score: 64,
    risk: "HIGH",
    reason: "Ask wall rebuilt twice above price while futures positioning leans crowded long.",
    action: "Pressure favors sellers into 168.50 · read invalidates above 172.",
  },
];

function biasClass(b: Bias): string {
  return b === "LONG" ? "text-emerald-400" : b === "SHORT" ? "text-red-400" : "text-lm-text-dim";
}
function riskVariant(r: "LOW" | "MEDIUM" | "HIGH"): "live" | "warning" | "error" {
  return r === "LOW" ? "live" : r === "MEDIUM" ? "warning" : "error";
}

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-lm-bg">
      <style dangerouslySetInnerHTML={{ __html: PAGE_CSS }} />

      {/* Nav */}
      <nav className="lm-topnav sticky top-0 z-50">
        <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-4 sm:px-6 lg:px-8">
          <div className="flex items-center gap-2">
            <Activity className="h-5 w-5 text-lm-purple" strokeWidth={2.5} />
            <span className="lm-brand text-[15px] text-lm-text">Lumora</span>
          </div>
          <div className="flex items-center gap-3">
            <StatusBadge variant="neutral" size="sm" className="hidden sm:inline-flex">
              PRIVATE BETA
            </StatusBadge>
            <Link
              href="/dashboard"
              className="rounded-md bg-cyan-400 px-3.5 py-1.5 text-[13px] font-semibold text-zinc-950 transition-colors hover:bg-cyan-300"
            >
              Launch terminal
            </Link>
          </div>
        </div>
      </nav>

      {/* 1+2 — Hero with The Lumora Field */}
      <LumoraFieldHero />

      {/* Capabilities ticker */}
      <div className="overflow-hidden border-y border-lm-border/60 py-2.5">
        <div className="lmk-track num flex w-max items-center text-[9px] uppercase tracking-[0.18em] text-lm-muted">
          {CAPABILITIES.map((c) => (
            <span key={c} className="flex items-center gap-3 pr-3">
              <span>{c}</span>
              <span className="text-lm-border">/</span>
            </span>
          ))}
          {CAPABILITIES.map((c) => (
            <span key={`dup-${c}`} aria-hidden className="lmk-dup flex items-center gap-3 pr-3">
              <span>{c}</span>
              <span className="text-lm-border">/</span>
            </span>
          ))}
        </div>
      </div>

      {/* 3 — Signal tape (staged market replay) */}
      <MarketReplayStrip />

      {/* Bridge — from the tape to the field */}
      <div className="flex flex-col items-center px-4 pb-2 pt-8 text-center">
        <span className="num text-[9px] uppercase tracking-[0.22em] text-lm-muted">
          From the tape to the field
        </span>
        <h2 className="mt-3 max-w-xl text-xl font-semibold tracking-tight text-lm-text sm:text-2xl">
          From raw market events to a{" "}
          <span className="bg-gradient-to-r from-cyan-300 to-sky-500 bg-clip-text text-transparent">
            readable pressure map
          </span>
          .
        </h2>
        <div className="relative mt-6 h-12 w-px bg-gradient-to-b from-zinc-700 to-transparent">
          <span className="lmb-drop absolute -left-[2px] top-0 h-[5px] w-[5px] rounded-full bg-cyan-400/70" />
        </div>
      </div>

      {/* 4 — What Lumora reads */}
      <LandingFeatureGrid />

      {/* 5 — Market read examples */}
      <section className="px-4 py-9">
        <div className="mx-auto max-w-6xl">
          <div className="mb-4 flex flex-wrap items-end justify-between gap-2">
            <div>
              <span className="lm-section-title">03 · The read</span>
              <h2 className="mt-2 text-xl font-semibold tracking-tight text-lm-text">
                The output is a read, not another wall of charts.
              </h2>
              <p className="mt-1 text-[13px] text-lm-text-dim">
                Bias, score, risk — and the reason behind it, in one sentence.
              </p>
            </div>
            <StatusBadge variant="warning" size="sm">Illustrative</StatusBadge>
          </div>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
            {READS.map((r) => (
              <Panel key={r.symbol} flush hover className="lm-accent-top-cyan p-3.5">
                <div className="flex items-center justify-between">
                  <span className="num text-[11px] font-semibold uppercase tracking-widest text-lm-text">
                    {r.symbol}
                  </span>
                  <StatusBadge variant={riskVariant(r.risk)} size="sm">
                    {r.risk} RISK
                  </StatusBadge>
                </div>
                <div className="mt-2.5 flex items-baseline gap-2.5">
                  <span className={clsx("lm-price text-xl leading-none", biasClass(r.bias))}>
                    {r.bias}
                  </span>
                  <span className="num text-[12px] font-semibold text-lm-text">
                    {r.score}
                    <span className="text-[9px] text-lm-muted">/100</span>
                  </span>
                </div>
                <p className="mt-2.5 text-[11.5px] leading-snug text-lm-text-dim">{r.reason}</p>
                <div className="lm-verdict-rule mt-2.5">
                  <p className="text-[9px] uppercase tracking-widest text-lm-muted">Action context</p>
                  <p className="mt-0.5 text-[11.5px] font-medium leading-snug text-lm-text">{r.action}</p>
                </div>
              </Panel>
            ))}
          </div>
          <p className="mt-2.5 px-1 text-[10px] leading-snug text-lm-muted">
            Illustrative examples, not live signals or trade recommendations. Reads describe
            market structure — they do not predict outcomes.
          </p>
        </div>
      </section>

      {/* 6 — Early access CTA */}
      <section className="relative overflow-hidden px-4 py-14">
        {/* Ambient glow behind the CTA */}
        <div aria-hidden className="pointer-events-none absolute inset-0">
          <div className="absolute inset-0 bg-[radial-gradient(ellipse_45%_60%_at_50%_50%,rgba(34,211,238,0.06),transparent_70%)]" />
        </div>
        <div className="relative mx-auto max-w-2xl">
          {/* Gradient hairline border */}
          <div className="rounded-lg bg-gradient-to-r from-cyan-500/25 via-purple-500/20 to-emerald-500/25 p-px">
            <div className="rounded-[7px] bg-lm-surface px-6 py-8 text-center sm:px-10 sm:py-10">
              <span className="num text-[9px] uppercase tracking-[0.22em] text-lm-muted">
                Early access
              </span>
              <h2 className="mt-3 text-2xl font-semibold tracking-tight text-lm-text">
                Read the market with Lumora
              </h2>
              <p className="mx-auto mt-2.5 max-w-md text-[13px] leading-relaxed text-lm-text-dim">
                We&apos;re onboarding a small group of traders during private beta. Open the
                terminal with demo data today, or join the Discord for live-integration updates.
              </p>
              <div className="mt-6 flex flex-col justify-center gap-2.5 sm:flex-row">
                <Link
                  href="/dashboard"
                  className="inline-flex items-center justify-center gap-2 rounded-md bg-cyan-400 px-5 py-2.5 text-[13px] font-semibold text-zinc-950 shadow-[0_0_28px_rgba(34,211,238,0.25)] transition-colors hover:bg-cyan-300"
                >
                  Launch terminal <ArrowRight className="h-3.5 w-3.5" />
                </Link>
                {/* TODO: replace with Lumora Discord invite */}
                <a
                  href="#"
                  className="inline-flex items-center justify-center gap-2 rounded-md border border-lm-border px-5 py-2.5 text-[13px] font-medium text-lm-text-dim transition-colors hover:border-zinc-600 hover:text-lm-text"
                >
                  <MessageCircle className="h-3.5 w-3.5 text-lm-cyan" />
                  Join the Discord
                </a>
              </div>
              <p className="mt-5 text-[10px] leading-snug text-lm-muted">
                Lumora provides informational market context only — no guaranteed outcomes,
                no financial advice.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-lm-border px-4 py-7">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-3 sm:flex-row">
          <div className="flex items-center gap-2">
            <Activity className="h-4 w-4 text-lm-purple" />
            <span className="lm-brand text-sm text-lm-text">Lumora</span>
            <span className="ml-2 text-xs text-lm-muted">Liquidity intelligence terminal</span>
          </div>
          <div className="flex flex-col items-center gap-1 sm:items-end">
            <p className="text-xs text-lm-muted">
              © 2026 Lumora. Not financial advice. For informational use only.
            </p>
            <p className="num text-[9px] uppercase tracking-[0.18em] text-lm-muted/80">
              Private beta · demo data shown
            </p>
          </div>
        </div>
      </footer>
    </div>
  );
}
