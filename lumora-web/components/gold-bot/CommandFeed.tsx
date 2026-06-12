"use client";

// components/gold-bot/CommandFeed.tsx
// LM73C — right rail of the command room: what the engine just did.
//
// A typed event feed (zone / risk / update / journal), the risk permission
// block with hard guardrails, the paper-trading state strip and a one-line
// learning-journal seed. Staged data only — the feed reads like a session
// log, the newest entry pulses, and a waiting cursor blinks at the bottom.

import { clsx } from "clsx";
import { ShieldCheck, FlaskConical, ScrollText } from "lucide-react";
import { StatusBadge } from "@/components/ui/StatusBadge";

const FEED_CSS = `
@media (prefers-reduced-motion: no-preference) {
  .lmcf-new { animation: lmcf-in 0.4s ease-out; }
  @keyframes lmcf-in {
    from { opacity: 0; transform: translateY(-3px); }
    to   { opacity: 1; transform: translateY(0); }
  }
  .lmcf-cursor { animation: lmcf-blink 1.1s steps(2, start) infinite; }
  @keyframes lmcf-blink {
    0%, 100% { opacity: 1; }
    50%      { opacity: 0; }
  }
}
.lmcf-row { transition: background-color 130ms ease-out; }
.lmcf-row:hover { background-color: rgba(252,211,77,0.025); }
`;

type FeedTone = "gold" | "cyan" | "rose" | "violet" | "emerald";

const TONE_TEXT: Record<FeedTone, string> = {
  gold: "text-amber-300",
  cyan: "text-cyan-300",
  rose: "text-rose-400",
  violet: "text-violet-300",
  emerald: "text-emerald-400",
};
const TONE_DOT: Record<FeedTone, string> = {
  gold: "bg-amber-300",
  cyan: "bg-cyan-300",
  rose: "bg-rose-400",
  violet: "bg-violet-300",
  emerald: "bg-emerald-400",
};

const FEED: Array<{ t: string; tag: string; tone: FeedTone; text: string }> = [
  { t: "13:42:10", tag: "UPDATE",   tone: "cyan",    text: "Reclaim confirmed above 2378 — thesis upgraded to long continuation." },
  { t: "13:38:44", tag: "STRATEGY", tone: "gold",    text: "Setup class sweep+reclaim scored 7.5/10 — entry only on FVG retest." },
  { t: "13:31:55", tag: "ZONE",     tone: "gold",    text: "FVG 2380.8–2384.5 registered from displacement leg." },
  { t: "13:18:02", tag: "NEWS",     tone: "rose",    text: "CPI in 3h — trade permission narrows 30m before release." },
  { t: "12:54:38", tag: "ZONE",     tone: "gold",    text: "Liquidity sweep detected at Asia low 2367.4 · reclaim watch armed." },
  { t: "12:30:00", tag: "UPDATE",   tone: "cyan",    text: "New York pre-open — session bias model switched to NY weighting." },
  { t: "11:47:21", tag: "LEARNING", tone: "violet",  text: "Yesterday's review stored: 1 valid setup skipped — lesson logged for owner approval." },
  { t: "11:15:30", tag: "DISCORD",  tone: "violet",  text: "Daily review report staged — webhook delivery planned, not wired." },
  { t: "11:02:09", tag: "EXEC",     tone: "rose",    text: "Live execution adapter check: LOCKED. Paper engine only." },
];

const GUARDRAILS: Array<{ rule: string; value: string; ok: boolean }> = [
  { rule: "Trades today",        value: "0 / 3",   ok: true },
  { rule: "Daily loss",          value: "0.0R / -1.0R", ok: true },
  { rule: "News lockout",        value: "inactive", ok: true },
  { rule: "Cooldown",            value: "—",        ok: true },
  { rule: "Kill switch",         value: "planned",  ok: false },
];

export function CommandFeed({ className }: { className?: string }) {
  return (
    <div className={clsx("space-y-3", className)}>
      <style dangerouslySetInnerHTML={{ __html: FEED_CSS }} />

      {/* Engine feed */}
      <section className="overflow-hidden rounded-lg bg-[#0d0c09]/80 ring-1 ring-amber-400/[0.08] shadow-[inset_0_1px_0_rgba(255,255,255,0.03),0_10px_26px_-14px_rgba(0,0,0,0.8)]">
        <div className="relative flex items-center justify-between gap-2 px-3 py-2">
          <span className="num text-[9.5px] font-semibold uppercase tracking-[0.18em] text-amber-200/80">
            Engine Feed
          </span>
          <StatusBadge variant="demo" size="sm">Staged</StatusBadge>
          <span aria-hidden className="pointer-events-none absolute inset-x-0 bottom-0 h-px bg-gradient-to-r from-amber-400/25 via-white/[0.04] to-transparent" />
        </div>
        <div className="max-h-[300px] divide-y divide-white/[0.04] overflow-y-auto">
          {FEED.map(({ t, tag, tone, text }, i) => (
            <div
              key={t}
              className={clsx(
                "lmcf-row px-3 py-2",
                i === 0 && "lmcf-new bg-amber-400/[0.03] shadow-[inset_1.5px_0_0_rgba(252,211,77,0.55)]",
              )}
            >
              <div className="flex items-center gap-2">
                <span className={clsx("h-1 w-1 shrink-0 rounded-full", TONE_DOT[tone])} />
                <span className={clsx("num text-[8.5px] font-semibold uppercase tracking-[0.16em]", TONE_TEXT[tone])}>
                  {tag}
                </span>
                <span className="num ml-auto shrink-0 text-[9px] text-lm-muted">{t}</span>
              </div>
              <p className={clsx("mt-1 text-[10.5px] leading-snug", i === 0 ? "text-lm-text" : "text-lm-text-dim")}>
                {text}
              </p>
            </div>
          ))}
          <div className="flex items-center gap-2 px-3 py-2">
            <span className="lmcf-cursor num text-[10px] leading-none text-amber-300">▌</span>
            <span className="num text-[8.5px] uppercase tracking-[0.18em] text-lm-muted">
              engine watching · next event pending
            </span>
          </div>
        </div>
      </section>

      {/* Risk permission */}
      <section className="overflow-hidden rounded-lg bg-[#0d0c09]/80 ring-1 ring-amber-400/[0.08] shadow-[inset_0_1px_0_rgba(255,255,255,0.03),0_10px_26px_-14px_rgba(0,0,0,0.8)]">
        <div className="relative flex items-center justify-between gap-2 px-3 py-2">
          <span className="flex items-center gap-1.5">
            <ShieldCheck className="h-3 w-3 text-amber-400/70" />
            <span className="num text-[9.5px] font-semibold uppercase tracking-[0.18em] text-amber-200/80">
              Risk Permission
            </span>
          </span>
          <span className="num text-[8.5px] uppercase tracking-wider text-emerald-400">GRANTED · PAPER</span>
          <span aria-hidden className="pointer-events-none absolute inset-x-0 bottom-0 h-px bg-gradient-to-r from-amber-400/25 via-white/[0.04] to-transparent" />
        </div>
        <div className="divide-y divide-white/[0.04]">
          {GUARDRAILS.map(({ rule, value, ok }) => (
            <div key={rule} className="lmcf-row flex items-center justify-between gap-3 px-3 py-1.5">
              <span className="text-[10.5px] text-lm-text-dim">{rule}</span>
              <span className={clsx(
                "num text-[10px] font-semibold",
                ok ? "text-lm-text" : "uppercase tracking-wider text-lm-muted",
              )}>
                {value}
              </span>
            </div>
          ))}
        </div>
      </section>

      {/* Paper state */}
      <section className="overflow-hidden rounded-lg bg-[#0d0c09]/80 ring-1 ring-amber-400/[0.08] shadow-[inset_0_1px_0_rgba(255,255,255,0.03),0_10px_26px_-14px_rgba(0,0,0,0.8)]">
        <div className="relative flex items-center justify-between gap-2 px-3 py-2">
          <span className="flex items-center gap-1.5">
            <FlaskConical className="h-3 w-3 text-amber-400/70" />
            <span className="num text-[9.5px] font-semibold uppercase tracking-[0.18em] text-amber-200/80">
              Paper State
            </span>
          </span>
          <StatusBadge variant="warning" size="sm">PAPER</StatusBadge>
          <span aria-hidden className="pointer-events-none absolute inset-x-0 bottom-0 h-px bg-gradient-to-r from-amber-400/25 via-white/[0.04] to-transparent" />
        </div>
        <div className="grid grid-cols-2 divide-x divide-white/[0.04]">
          {[
            ["Position", "none"],
            ["Last idea", "waiting"],
            ["Today PnL", "0.00"],
            ["Trades", "0"],
          ].map(([l, v]) => (
            <div key={l} className="lmcf-row px-3 py-2.5">
              <p className="num text-[8px] uppercase tracking-[0.16em] text-lm-muted">{l}</p>
              <p className={clsx(
                "num mt-0.5 text-[13px] font-semibold leading-none",
                v === "waiting" ? "text-amber-300/90" : "text-lm-text-dim",
              )}>
                {v}
              </p>
            </div>
          ))}
        </div>
      </section>

      {/* Learning journal — the self-improvement contract */}
      <section className="overflow-hidden rounded-lg bg-[#0d0c09]/80 ring-1 ring-amber-400/[0.08] shadow-[inset_0_1px_0_rgba(255,255,255,0.03),0_10px_26px_-14px_rgba(0,0,0,0.8)]">
        <div className="relative flex items-center justify-between gap-2 px-3 py-2">
          <span className="flex items-center gap-1.5">
            <ScrollText className="h-3 w-3 text-violet-300/70" />
            <span className="num text-[9.5px] font-semibold uppercase tracking-[0.18em] text-amber-200/80">
              Learning Journal
            </span>
          </span>
          <span className="num text-[8.5px] uppercase tracking-wider text-violet-300/80">SELF-LEARNING</span>
          <span aria-hidden className="pointer-events-none absolute inset-x-0 bottom-0 h-px bg-gradient-to-r from-amber-400/25 via-white/[0.04] to-transparent" />
        </div>
        <div className="px-3 py-2">
          <p className="num text-[8.5px] uppercase tracking-[0.14em] leading-relaxed text-lm-muted">
            setup type · session · news context · entry reason · exit reason · result · mistake · lesson · score
          </p>
          <p className="mt-1.5 text-[10px] leading-snug text-lm-text-dim">
            Every paper trade writes all nine fields. Analytics over the journal propose strategy
            changes — the bot never rewrites its own rules without owner approval.
          </p>
        </div>
      </section>
    </div>
  );
}
