import Link from "next/link";
import { ArrowRight, MessageCircle } from "lucide-react";
import { LumoraMark } from "@/components/brand/LumoraMark";
import { Panel } from "@/components/ui/Panel";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { LumoraFieldHero } from "@/components/landing/LumoraFieldHero";
import { SpiralIntro } from "@/components/landing/SpiralIntro";
import { MarketReplayStrip } from "@/components/landing/MarketReplayStrip";
import { LandingFeatureGrid } from "@/components/landing/LandingFeatureGrid";
import { TerminalPreview } from "@/components/landing/TerminalPreview";
import { FaqSection } from "@/components/landing/FaqSection";
import { Reveal } from "@/components/landing/Reveal";
import { WaitlistForm } from "@/components/landing/WaitlistForm";
import { ProductSwitch } from "@/components/fintech/ProductSwitch";
import { SiteFooter } from "@/components/ui/SiteFooter";
import { DISCORD_URL } from "@/lib/site";
import { clsx } from "clsx";

// ── Landing page (LM70B experience rebuild) ──────────────────────────────────
// One continuous descent: hero field → signal tape → structure → read →
// terminal → CTA. A fixed atmospheric backdrop (violet dawn + instrument grid)
// runs under every section so the page reads as one world, not stacked blocks.
// Sections rise out of the dark via <Reveal>; connectors carry a falling
// signal dot between chapters.

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
  .lmcta-sweep { animation: lmcta-sweep 4.5s ease-in-out infinite; }
  @keyframes lmcta-sweep {
    0%, 100% { transform: translateX(-110%); }
    50%      { transform: translateX(110%); }
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
    reason: "Bid intensity 58% vs 42% ask. Buyers are leading into a support band that has held twice.",
    action: "Watch reclaim of 67,500 · read invalidates below 66,800.",
  },
  {
    symbol: "ETHUSDT",
    bias: "NEUTRAL",
    score: 41,
    risk: "LOW",
    reason: "Order book sits near 50/50, so there is no clean directional edge in the current structure.",
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

const HOW_STEPS: Array<{ title: string; body: string }> = [
  {
    title: "We watch the live book",
    body: "Every resting bid and ask, and every large print the moment it lands on the tape. Nothing sampled, nothing on a delay.",
  },
  {
    title: "We score the pressure",
    body: "Bid versus ask intensity, whale flow and futures positioning get weighed into one bias, a score out of 100, and a risk level.",
  },
  {
    title: "You get one read",
    body: "A single line with the reason behind it, so you can make the call in seconds instead of squinting at twelve charts.",
  },
];

function biasClass(b: Bias): string {
  return b === "LONG" ? "text-emerald-400" : b === "SHORT" ? "text-red-400" : "text-lm-text-dim";
}
function riskVariant(r: "LOW" | "MEDIUM" | "HIGH"): "live" | "warning" | "error" {
  return r === "LOW" ? "live" : r === "MEDIUM" ? "warning" : "error";
}

// Falling-signal connector between chapters — the page's vertical spine.
function SignalDrop({ label }: { label?: string }) {
  return (
    <div className="flex flex-col items-center px-4 pb-2 pt-6 text-center">
      {label && (
        <span className="num text-[9px] uppercase tracking-[0.22em] text-lm-muted">{label}</span>
      )}
      <div className={clsx("relative h-12 w-px bg-gradient-to-b from-zinc-700 to-transparent", label && "mt-3")}>
        <span className="lmb-drop absolute -left-[2px] top-0 h-[5px] w-[5px] rounded-full bg-cyan-400/70" />
      </div>
    </div>
  );
}

export default function LandingPage({
  searchParams,
}: {
  searchParams?: { intro?: string };
}) {
  // Galaxy gate is on by default; ?intro=off skips it (hero boots up on load).
  const introGate = searchParams?.intro !== "off";
  return (
    <div className="relative min-h-screen overflow-x-clip bg-lm-bg">
      <div className="lm-veil" aria-hidden />
      {/* Intro: galaxy gate, then the hero boots up the moment you Enter.
          Pass ?intro=off to skip the gate and boot the hero up on load. */}
      {introGate && <SpiralIntro />}

      <style dangerouslySetInnerHTML={{ __html: PAGE_CSS }} />

      <a href="#main-content" className="lm-skip-link">
        Skip to content
      </a>

      {/* Fixed instrument plane — graph-paper grid (fine + major), no decorative
          color blobs. Structure, not atmosphere. */}
      <div aria-hidden className="pointer-events-none fixed inset-0">
        <div
          className="absolute inset-0"
          style={{
            backgroundImage:
              "linear-gradient(rgba(255,255,255,0.022) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.022) 1px, transparent 1px), linear-gradient(rgba(255,255,255,0.04) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.04) 1px, transparent 1px)",
            backgroundSize: "34px 34px, 34px 34px, 170px 170px, 170px 170px",
            maskImage: "radial-gradient(ellipse 82% 72% at 50% 28%, black 36%, transparent 80%)",
            WebkitMaskImage: "radial-gradient(ellipse 82% 72% at 50% 28%, black 36%, transparent 80%)",
          }}
        />
        {/* One quiet cyan undercurrent — the only color in the field */}
        <div className="absolute inset-x-0 bottom-0 h-1/3 bg-[radial-gradient(ellipse_55%_90%_at_50%_122%,rgba(34,211,238,0.04),transparent_72%)]" />
      </div>

      {/* Nav */}
      <nav className="lm-topnav sticky top-0 z-50">
        <div className="relative mx-auto flex h-14 max-w-6xl items-center justify-between px-4 sm:px-6 lg:px-8">
          <div className="flex items-center gap-2.5">
            <LumoraMark size={26} />
            <span className="lm-brand text-[15px] text-lm-text">Lumora</span>
          </div>
          {/* Centered, position-stable across both brands */}
          <div className="pointer-events-none absolute inset-0 hidden items-center justify-center sm:flex">
            <div className="pointer-events-auto">
              <ProductSwitch active="terminal" variant="dark" />
            </div>
          </div>
          <div className="flex items-center gap-3">
            <StatusBadge variant="neutral" size="sm" className="hidden sm:inline-flex">
              PRIVATE BETA
            </StatusBadge>
            <Link
              href="/enter"
              className="rounded-md bg-cyan-400 px-3.5 py-1.5 text-[13px] font-semibold text-zinc-950 transition-colors hover:bg-cyan-300"
            >
              Launch terminal
            </Link>
          </div>
        </div>
      </nav>

      <div className="relative">
        <main id="main-content">
        {/* Hero — The Lumora Field */}
        <LumoraFieldHero introGate={introGate} />

        {/* Capabilities ticker */}
        <div className="overflow-hidden border-y border-lm-border/60 bg-black/20 py-2.5 backdrop-blur-sm">
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

        {/* 01 — Signal tape */}
        <Reveal>
          <MarketReplayStrip />
        </Reveal>

        <SignalDrop label="From the tape to the field" />

        {/* 02 — What Lumora reads */}
        <Reveal>
          <LandingFeatureGrid />
        </Reveal>

        <SignalDrop label="Four layers · one read" />

        {/* 02b — How it works */}
        <Reveal>
          <section id="how" className="px-4 py-9" aria-labelledby="how-heading">
            <div className="mx-auto max-w-6xl">
              <div className="mb-5">
                <span className="lm-section-title">How it works</span>
                <h2 id="how-heading" className="lm-display mt-2 text-xl font-semibold tracking-tight text-lm-text">
                  From raw order flow to a read you can actually act on.
                </h2>
              </div>
              <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
                {HOW_STEPS.map((s, i) => (
                  <Reveal key={s.title} delay={i * 0.1}>
                    <Panel flush className="h-full p-4">
                      <span className="num text-[12px] font-semibold text-lm-cyan">0{i + 1}</span>
                      <h3 className="mt-2 text-[15px] font-semibold text-lm-text">{s.title}</h3>
                      <p className="mt-1.5 text-[12.5px] leading-relaxed text-lm-text-dim">{s.body}</p>
                    </Panel>
                  </Reveal>
                ))}
              </div>
            </div>
          </section>
        </Reveal>

        {/* 03 — Market read examples */}
        <Reveal>
          <section className="px-4 py-9" aria-labelledby="read-heading">
            <div className="mx-auto max-w-6xl">
              <div className="mb-4 flex flex-wrap items-end justify-between gap-2">
                <div>
                  <span className="lm-section-title">03 · The read</span>
                  <h2 id="read-heading" className="lm-display mt-2 text-xl font-semibold tracking-tight text-lm-text">
                    The output is a read, not another wall of charts.
                  </h2>
                  <p className="mt-1 text-[13px] text-lm-text-dim">
                    Bias, score, risk, and the reason behind it, in one sentence.
                  </p>
                </div>
                <StatusBadge variant="warning" size="sm">Illustrative</StatusBadge>
              </div>
              <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
                {READS.map((r, i) => (
                  <Reveal key={r.symbol} delay={i * 0.1}>
                    <Panel flush hover className="lm-accent-top-cyan h-full p-3.5">
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
                  </Reveal>
                ))}
              </div>
            </div>
          </section>
        </Reveal>

        <SignalDrop label="Step inside" />

        {/* 04 — Live terminal preview */}
        <Reveal>
          <TerminalPreview />
        </Reveal>

        <SignalDrop label="Still skeptical? Good." />

        {/* 06 — FAQ / objection handling (CRO) */}
        <Reveal>
          <FaqSection />
        </Reveal>

        {/* 05 — Early access CTA */}
        <section className="relative overflow-hidden px-4 py-16" aria-labelledby="cta-heading">
          <div aria-hidden className="pointer-events-none absolute inset-0">
            <div className="absolute inset-0 bg-[radial-gradient(ellipse_45%_60%_at_50%_50%,rgba(139,92,246,0.07),transparent_70%)]" />
            <div className="absolute inset-0 bg-[radial-gradient(ellipse_35%_45%_at_50%_60%,rgba(34,211,238,0.05),transparent_70%)]" />
          </div>
          <Reveal>
            <div className="relative mx-auto max-w-2xl">
              {/* Gradient hairline border with a slow light sweep */}
              <div className="relative overflow-hidden rounded-lg bg-gradient-to-r from-violet-500/30 via-cyan-500/20 to-violet-500/30 p-px">
                <span
                  aria-hidden
                  className="lmcta-sweep pointer-events-none absolute inset-y-0 w-1/3 bg-gradient-to-r from-transparent via-white/[0.07] to-transparent"
                />
                <div className="relative rounded-[7px] bg-lm-surface px-6 py-9 text-center sm:px-10 sm:py-11">
                  <span className="num text-[9px] uppercase tracking-[0.22em] text-lm-muted">
                    Early access
                  </span>
                  <h2 id="cta-heading" className="lm-display mt-3 text-2xl font-semibold tracking-tight text-lm-text sm:text-[30px]">
                    Step into the field.
                  </h2>
                  <p className="mx-auto mt-2.5 max-w-md text-[13px] leading-relaxed text-lm-text-dim">
                    We&apos;re onboarding a small group of traders during private beta. Leave your
                    email for an invite, request beta access, or join the Discord.
                  </p>

                  <div className="mt-6">
                    <WaitlistForm />
                  </div>

                  <div className="my-5 flex items-center gap-3 text-[9px] uppercase tracking-[0.22em] text-lm-muted">
                    <span className="h-px flex-1 bg-lm-border" />
                    or
                    <span className="h-px flex-1 bg-lm-border" />
                  </div>

                  <div className="flex flex-col justify-center gap-2.5 sm:flex-row">
                    <Link
                      href="/enter"
                      className="inline-flex min-h-[44px] items-center justify-center gap-2 rounded-md bg-cyan-400 px-5 py-2.5 text-[13px] font-semibold text-zinc-950 shadow-[0_0_28px_rgba(34,211,238,0.25)] transition-all hover:bg-cyan-300 hover:shadow-[0_0_36px_rgba(34,211,238,0.4)]"
                    >
                      Request beta access <ArrowRight className="h-3.5 w-3.5" />
                    </Link>
                    <a
                      href={DISCORD_URL}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex min-h-[44px] items-center justify-center gap-2 rounded-md border border-lm-border px-5 py-2.5 text-[13px] font-medium text-lm-text-dim transition-colors hover:border-zinc-600 hover:text-lm-text"
                    >
                      <MessageCircle className="h-3.5 w-3.5 text-lm-cyan" />
                      Join the Discord
                    </a>
                  </div>
                  <p className="mt-4 num text-[10px] uppercase tracking-[0.18em] text-lm-text-dim">
                    Free during private beta · we onboard in small waves
                  </p>
                  <p className="mt-3 text-[10px] leading-snug text-lm-muted">
                    Lumora gives you market context for information only. No guaranteed outcomes,
                    and no financial advice.
                  </p>
                </div>
              </div>
            </div>
          </Reveal>
        </section>

        </main>

        {/* Footer */}
        <SiteFooter variant="full" />
      </div>
    </div>
  );
}
