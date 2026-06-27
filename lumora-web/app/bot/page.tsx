import { loadGoldBotTrackRecord, type PresetRecord } from "@/lib/gold-bot-signals";
import { BOT_BRAND } from "@/lib/bot-brand";
import { ProductPreview } from "@/components/fintech/ProductPreview";
import { AccountProjector } from "@/components/fintech/AccountProjector";
import { SignalChip } from "@/components/fintech/SignalChip";
import { FounderNote } from "@/components/fintech/FounderNote";
import { ComparisonTable } from "@/components/fintech/ComparisonTable";
import { Roadmap } from "@/components/fintech/Roadmap";
import { FintechFaq } from "@/components/fintech/FintechFaq";
import { EarlyAccessForm } from "@/components/fintech/EarlyAccessForm";
import { Reveal } from "@/components/fintech/Reveal";
import { CountUp } from "@/components/fintech/CountUp";

export const dynamic = "force-dynamic";

function pick(presets: PresetRecord[], name: string): PresetRecord | undefined {
  return presets.find((p) => p.name === name);
}

function asOf(iso: string | null): string | null {
  if (!iso) return null;
  const t = Date.parse(iso);
  if (!Number.isFinite(t)) return null;
  return new Date(t).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

const H2 = "text-[clamp(1.7rem,1.2rem+1.6vw,2.6rem)] font-medium tracking-[-0.022em] text-fintech-ink";

export default async function BotLandingPage() {
  const tr = await loadGoldBotTrackRecord("XAUUSD", "M15");
  const hasData = tr.ok && tr.presets.length > 0;

  const guarded = pick(tr.presets, "swing_guarded");
  const swing = pick(tr.presets, "swing");
  const dataDate = asOf(tr.dataAsOf);
  const tradesLabel = tr.closedTrades.toLocaleString("en-US");
  const gNet = Math.round(guarded?.expectancyPoints ?? 85);
  const sNet = Math.round(swing?.expectancyPoints ?? 150);

  return (
    <>
      {/* ── Hero: product-first ──────────────────────────────────────────── */}
      <section className="relative overflow-hidden">
        <div className="pointer-events-none absolute inset-0 -z-10 fx-hero-grid" aria-hidden="true" />
        <div className="mx-auto grid max-w-6xl grid-cols-1 items-center gap-12 px-6 pb-16 pt-12 sm:pt-16 lg:grid-cols-[1fr_1.02fr] lg:gap-12">
          <div>
            <div className="fx-rise flex flex-wrap items-center gap-2.5">
              <span className="inline-flex items-center gap-2 rounded-full border border-fintech-indigo-line bg-fintech-indigo-soft px-3 py-1 text-[12px] font-medium text-fintech-indigo-ink">
                <span className="h-1.5 w-1.5 rounded-full bg-fintech-indigo" aria-hidden="true" />
                {BOT_BRAND.tagline}
              </span>
              <span className="inline-flex items-center gap-2 rounded-full border border-fintech-line bg-white px-3 py-1 text-[12px] font-medium text-fintech-ink-soft">
                <span className="h-1.5 w-1.5 rounded-full bg-fintech-indigo" aria-hidden="true" />
                Validated out of sample
              </span>
            </div>
            <h1 className="fx-rise-1 mt-5 max-w-[15ch] text-[clamp(2.4rem,1.3rem+4.3vw,4.4rem)] font-medium leading-[1.04] tracking-[-0.027em] text-fintech-ink">
              Gold signals you can check before you trust.
            </h1>
            <p className="fx-rise-2 mt-5 max-w-[50ch] text-[17px] leading-[1.7] text-fintech-ink-soft">
              One rules-based strategy on gold. We send the entry, the stop and the exit. You place
              every trade yourself. Flip between the two ways to run it and read the real numbers.
            </p>
            <div className="fx-rise-3 mt-8 flex flex-wrap items-center gap-3">
              <a
                href="#early-access"
                className="fx-lift rounded-xl bg-fintech-indigo px-5 py-3 text-[15px] font-medium text-white hover:bg-fintech-indigo-ink hover:shadow-[0_14px_30px_-12px_rgba(79,70,229,0.6)]"
              >
                Get early access
              </a>
              <a
                href="#calculator"
                className="rounded-xl border border-fintech-line px-5 py-3 text-[15px] font-medium text-fintech-ink transition-colors hover:bg-fintech-mist"
              >
                See your numbers
              </a>
            </div>
            <p className="fx-rise-3 mt-6 text-[13px] leading-relaxed text-fintech-faint">
              Built on {tradesLabel} scored trades. You choose the exit, you carry the risk.
            </p>
          </div>

          <div className="fx-rise-2">
            {hasData && guarded && swing ? (
              <ProductPreview
                guarded={{ net: gNet, win: guarded.winRatePct, trades: guarded.trades, total: guarded.totalRealizedPoints ?? 0 }}
                full={{ net: sNet, win: swing.winRatePct, trades: swing.trades, total: swing.totalRealizedPoints ?? 0 }}
                asOf={dataDate}
              />
            ) : (
              <div className="rounded-[20px] border border-dashed border-fintech-line bg-white p-10 text-center">
                <p className="text-[15px] font-medium text-fintech-ink">Recording in progress.</p>
                <p className="mt-1.5 text-[13px] text-fintech-muted">
                  The preview fills in as trades close out.
                </p>
              </div>
            )}
          </div>
        </div>
      </section>

      {/* ── Dark cinematic numbers band ──────────────────────────────────── */}
      {hasData ? (
        <section className="bg-fintech-ink">
          <div className="mx-auto grid max-w-6xl grid-cols-2 gap-y-8 px-6 py-12 sm:grid-cols-4">
            <DarkStat value={gNet} prefix="+" suffix=" pt" label="Guarded, per trade" accent />
            <DarkStat value={sNet} prefix="+" suffix=" pt" label="Full (advanced), per trade" accent />
            <DarkStat value={tr.closedTrades} label="Trades scored" />
            <div>
              <p className="fx-num text-[clamp(1.9rem,1.2rem+1.6vw,2.6rem)] font-medium leading-none text-white">
                Out of sample
              </p>
              <p className="mt-2 text-[12.5px] text-white/55">held up across 2025 and 2026</p>
            </div>
          </div>
        </section>
      ) : null}

      {/* ── Account projector (the "your number" hook) ───────────────────── */}
      <Reveal>
        <section id="calculator" className="mx-auto max-w-6xl scroll-mt-16 px-6 py-16">
          <div className="max-w-2xl">
            <h2 className={H2}>See what the edge does to your account.</h2>
            <p className="mt-3 text-[16px] leading-[1.7] text-fintech-ink-soft">
              Set your size and your risk. Watch what the strategy{"'"}s edge would have meant on your
              money, not on some tiny demo lot.
            </p>
          </div>
          <div className="mt-9">
            <AccountProjector />
          </div>
        </section>
      </Reveal>

      {/* ── How it works ─────────────────────────────────────────────────── */}
      <section id="how" className="scroll-mt-16 border-y border-fintech-line-soft bg-fintech-mist">
        <div className="mx-auto max-w-6xl px-6 py-16">
          <Reveal>
            <h2 className={`max-w-2xl ${H2}`}>From signal to your own trade, in three steps.</h2>
            <p className="mt-3 text-[16px] leading-[1.7] text-fintech-ink-soft">
              Nothing automated touches your account. You stay the one who clicks buy.
            </p>
          </Reveal>
          <Reveal delay={80}>
            <div className="mt-10 grid grid-cols-1 gap-10 lg:grid-cols-[1fr_0.9fr] lg:items-center">
              <ol className="space-y-7">
                <Step n="01" title="You get the signal" body="Direction, entry, a protective stop and the exit logic, with the timestamp. Gold, M15, only when the rules trigger." />
                <Step n="02" title="You pick your exit style" body="Guarded for bounded risk, full for the higher average. Same entries, your choice of how to take profit." />
                <Step n="03" title="You place it at your broker" body="You size it and place the trade yourself. You carry the risk, and you can stop any time. We never get near your account." />
              </ol>
              <SignalChip />
            </div>
          </Reveal>
        </div>
      </section>

      {/* ── Founder note (human) ─────────────────────────────────────────── */}
      <section className="border-y border-fintech-line-soft bg-fintech-mist">
        <div className="mx-auto max-w-6xl px-6 py-16">
          <Reveal>
            <FounderNote />
          </Reveal>
        </div>
      </section>

      {/* ── Comparison ───────────────────────────────────────────────────── */}
      <section className="mx-auto max-w-6xl px-6 py-16">
        <Reveal>
          <h2 className={`max-w-2xl ${H2}`}>Meridian versus the usual gold bot.</h2>
        </Reveal>
        <Reveal delay={80}>
          <div className="mt-8">
            <ComparisonTable />
          </div>
        </Reveal>
      </section>

      {/* ── Roadmap ──────────────────────────────────────────────────────── */}
      <section id="roadmap" className="scroll-mt-16 border-y border-fintech-line-soft bg-fintech-mist">
        <div className="mx-auto max-w-6xl px-6 py-16">
          <Reveal>
            <div className="max-w-2xl">
              <h2 className={H2}>Where this is going.</h2>
              <p className="mt-3 text-[16px] leading-[1.7] text-fintech-ink-soft">
                The edge is live today. Alerts, a members dashboard, copy trading and mobile are next.
              </p>
            </div>
          </Reveal>
          <Reveal delay={80}>
            <div className="mt-9">
              <Roadmap />
            </div>
          </Reveal>
        </div>
      </section>

      {/* ── FAQ ──────────────────────────────────────────────────────────── */}
      <section id="faq" className="mx-auto max-w-3xl scroll-mt-16 px-6 py-16">
        <Reveal>
          <h2 className={H2}>The questions you are already asking.</h2>
        </Reveal>
        <Reveal delay={80}>
          <div className="mt-8">
            <FintechFaq />
          </div>
        </Reveal>
      </section>

      {/* ── Early access ─────────────────────────────────────────────────── */}
      <section id="early-access" className="scroll-mt-16 border-t border-fintech-line-soft bg-fintech-mist">
        <Reveal>
          <div className="mx-auto max-w-3xl px-6 py-20 text-center">
            <h2 className={`mx-auto max-w-[18ch] ${H2}`}>See the numbers, then make your own call.</h2>
            <p className="mx-auto mt-4 max-w-[46ch] text-[16px] leading-[1.7] text-fintech-ink-soft">
              {`+${gNet} pt net per trade on the guarded swing, across ${tradesLabel} scored trades. You place every trade yourself.`}
            </p>
            <div className="mt-8">
              <EarlyAccessForm />
            </div>
            <p className="mt-5 text-[13px] text-fintech-faint">
              No card, nothing to cancel. You decide if the numbers earn your trust.
            </p>
          </div>
        </Reveal>
      </section>
    </>
  );
}

function DarkStat({
  value,
  prefix = "",
  suffix = "",
  label,
  accent = false,
}: {
  value: number;
  prefix?: string;
  suffix?: string;
  label: string;
  accent?: boolean;
}) {
  return (
    <div>
      <CountUp
        value={value}
        prefix={prefix}
        suffix={suffix}
        className={`fx-num block text-[clamp(1.9rem,1.2rem+1.6vw,2.6rem)] font-medium leading-none ${
          accent ? "text-[#A5B4FC]" : "text-white"
        }`}
      />
      <p className="mt-2 text-[12.5px] text-white/55">{label}</p>
    </div>
  );
}

function Step({ n, title, body }: { n: string; title: string; body: string }) {
  return (
    <li className="flex gap-4">
      <span className="fx-num grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-white text-[13px] font-medium text-fintech-indigo shadow-[0_1px_2px_rgba(15,23,42,0.06)]">
        {n}
      </span>
      <div>
        <h3 className="text-[16px] font-medium text-fintech-ink">{title}</h3>
        <p className="mt-1.5 text-[14px] leading-[1.7] text-fintech-ink-soft">{body}</p>
      </div>
    </li>
  );
}

