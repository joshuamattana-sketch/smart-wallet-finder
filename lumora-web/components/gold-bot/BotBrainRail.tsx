"use client";

// components/gold-bot/BotBrainRail.tsx
// LM73C — left rail of the command room: the bot's analytical state.
//
// Quiet machine-brain blocks: context meters (session bias, news risk),
// the current thought with a thinking indicator, why-no-trade reasoning,
// and the detector stack with armed pulses. All copy is staged — there is
// no model behind this yet, and the rail never pretends otherwise.

import { clsx } from "clsx";
import { Brain, Crosshair, ListChecks, Check, TriangleAlert } from "lucide-react";
import { StatusBadge } from "@/components/ui/StatusBadge";

const RAIL_CSS = `
@media (prefers-reduced-motion: no-preference) {
  .lmbb-think span { animation: lmbb-think 1.4s ease-in-out infinite; }
  .lmbb-think span:nth-child(2) { animation-delay: 0.2s; }
  .lmbb-think span:nth-child(3) { animation-delay: 0.4s; }
  @keyframes lmbb-think {
    0%, 100% { opacity: 0.25; }
    50%      { opacity: 1; }
  }
  .lmbb-armed { animation: lmbb-armed 2.6s ease-in-out infinite; }
  @keyframes lmbb-armed {
    0%, 100% { opacity: 1; box-shadow: 0 0 6px 1px rgba(252,211,77,0.4); }
    50%      { opacity: 0.5; box-shadow: 0 0 2px 0 rgba(252,211,77,0.15); }
  }
}
.lmbb-row { transition: background-color 130ms ease-out; }
.lmbb-row:hover { background-color: rgba(252,211,77,0.025); }
`;

function RailPanel({
  title,
  right,
  children,
  className,
}: {
  title: string;
  right?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section
      className={clsx(
        "overflow-hidden rounded-lg bg-[#0d0c09]/80 ring-1 ring-amber-400/[0.08]",
        "shadow-[inset_0_1px_0_rgba(255,255,255,0.03),0_10px_26px_-14px_rgba(0,0,0,0.8)]",
        className,
      )}
    >
      <div className="relative flex items-center justify-between gap-2 px-3 py-2">
        <span className="num text-[9.5px] font-semibold uppercase tracking-[0.18em] text-amber-200/80">
          {title}
        </span>
        {right}
        <span
          aria-hidden
          className="pointer-events-none absolute inset-x-0 bottom-0 h-px bg-gradient-to-r from-amber-400/25 via-white/[0.04] to-transparent"
        />
      </div>
      {children}
    </section>
  );
}

/** Thin analytical meter: label, value text, 0–100 fill with a glow tip. */
function Meter({
  label,
  text,
  value,
  tone,
}: {
  label: string;
  text: string;
  value: number;
  tone: "gold" | "cyan" | "rose" | "emerald";
}) {
  const fill =
    tone === "gold" ? "bg-amber-300/80 text-amber-300"
    : tone === "cyan" ? "bg-cyan-400/70 text-cyan-400"
    : tone === "rose" ? "bg-rose-400/70 text-rose-400"
    : "bg-emerald-400/70 text-emerald-400";
  return (
    <div className="lmbb-row px-3 py-2">
      <div className="flex items-baseline justify-between gap-2">
        <span className="num text-[8.5px] uppercase tracking-[0.18em] text-lm-muted">{label}</span>
        <span className="text-[10.5px] leading-snug text-lm-text-dim">{text}</span>
      </div>
      <div className="mt-1.5 h-[3px] overflow-hidden rounded-full bg-black/45 shadow-[inset_0_1px_1px_rgba(0,0,0,0.5)]">
        <div
          className={clsx("h-full rounded-full shadow-[0_0_6px_0_currentColor]", fill)}
          style={{ width: `${value}%` }}
        />
      </div>
    </div>
  );
}

const DETECTORS: Array<{ name: string; status: "armed" | "planned"; note: string }> = [
  { name: "Liquidity Sweep",  status: "armed",   note: "Asia low swept 08:12 · reclaimed" },
  { name: "FVG",              status: "armed",   note: "M5 gap 2380.8–2384.5 untapped" },
  { name: "Session High/Low", status: "armed",   note: "London range locked" },
  { name: "Key Level",        status: "planned", note: "prior day high 2392.5" },
  { name: "News Window",      status: "planned", note: "CPI lockout arms in 2h 30m" },
];

export function BotBrainRail({ className }: { className?: string }) {
  return (
    <div className={clsx("space-y-3", className)}>
      <style dangerouslySetInnerHTML={{ __html: RAIL_CSS }} />

      {/* Bot Brain — context meters + current thought */}
      <RailPanel
        title="Bot Brain"
        right={
          <span className="flex items-center gap-1.5">
            <Brain className="h-3 w-3 text-amber-400/70" />
            <StatusBadge variant="demo" size="sm">Mock</StatusBadge>
          </span>
        }
      >
        <div className="divide-y divide-white/[0.04]">
          <Meter label="Market State"  text="post-sweep expansion"          value={68} tone="cyan" />
          <Meter label="Session Bias"  text="long lean · NY continuation"   value={62} tone="emerald" />
          <Meter label="News Risk"     text="CPI in 3h · window narrows"    value={74} tone="rose" />
          <Meter label="Macro Context" text="DXY soft · yields flat → gold supportive" value={58} tone="cyan" />
          <Meter label="Zone Context"  text="FVG below · key level above"   value={55} tone="gold" />
          <Meter label="Spread / Vol Filter" text="spread normal · vol expanding" value={42} tone="emerald" />
        </div>

        {/* Current thought — the quiet machine voice */}
        <div className="border-t border-amber-400/[0.12] bg-amber-400/[0.035] px-3 py-2.5">
          <p className="num flex items-center gap-2 text-[8.5px] uppercase tracking-[0.2em] text-amber-400/70">
            Processing
            <span className="lmbb-think flex gap-[3px] text-amber-300">
              <span>·</span><span>·</span><span>·</span>
            </span>
          </p>
          <p className="mt-1 text-[11.5px] italic leading-snug text-lm-text">
            &ldquo;Reclaim held. Watching FVG retest for long entry — invalid below 2380.&rdquo;
          </p>
        </div>

        {/* Why no trade */}
        <div className="border-t border-white/[0.04] px-3 py-2">
          <p className="num text-[8.5px] uppercase tracking-[0.18em] text-lm-muted">Why no trade yet</p>
          <p className="mt-0.5 text-[10.5px] leading-snug text-lm-text-dim">
            Price hasn&apos;t returned to the gap. Chasing the displacement breaks the risk model — entry only on retest. Staying flat is the position.
          </p>
        </div>
      </RailPanel>

      {/* Trade permission — the evaluation the engine runs before any idea */}
      <RailPanel
        title="Trade Permission"
        right={
          <span className="flex items-center gap-1.5">
            <ListChecks className="h-3 w-3 text-amber-400/70" />
            <span className="num text-[8.5px] uppercase tracking-wider text-amber-300/80">EVALUATING</span>
          </span>
        }
      >
        <div className="divide-y divide-white/[0.04]">
          {([
            ["Valid setup?",          "sweep + reclaim confirmed · awaiting FVG retest", "wait"],
            ["News risk acceptable?", "yes until CPI -30m",                              "ok"],
            ["Risk mode allows?",     "Balanced · idea class permitted",                 "ok"],
            ["Funded profile safe?",  "no profile attached · paper rules apply",         "ok"],
            ["Paper execution?",      "allowed · live execution locked",                 "ok"],
          ] as Array<[string, string, "ok" | "wait"]>).map(([q, a, s]) => (
            <div key={q} className="lmbb-row flex items-start gap-2 px-3 py-1.5">
              {s === "ok" ? (
                <Check className="mt-0.5 h-3 w-3 shrink-0 text-emerald-400" />
              ) : (
                <TriangleAlert className="mt-0.5 h-3 w-3 shrink-0 text-amber-300" />
              )}
              <span className="min-w-0">
                <span className="num block text-[10px] font-semibold text-lm-text">{q}</span>
                <span className="block text-[9.5px] leading-snug text-lm-muted">{a}</span>
              </span>
            </div>
          ))}
        </div>
        <p className="num border-t border-white/[0.04] bg-black/20 px-3 py-1.5 text-[8.5px] uppercase tracking-wider text-lm-muted">
          Verdict <span className="text-amber-300">STAY FLAT</span> · re-check on FVG touch
        </p>
      </RailPanel>

      {/* Detector stack */}
      <RailPanel
        title="Detectors"
        right={
          <span className="flex items-center gap-1.5">
            <Crosshair className="h-3 w-3 text-amber-400/70" />
            <span className="num text-[8.5px] uppercase tracking-wider text-lm-muted">3 armed</span>
          </span>
        }
      >
        <div className="divide-y divide-white/[0.04]">
          {DETECTORS.map(({ name, status, note }) => (
            <div key={name} className="lmbb-row flex items-start gap-2.5 px-3 py-2">
              <span
                className={clsx(
                  "mt-[5px] h-1.5 w-1.5 shrink-0 rounded-full",
                  status === "armed" ? "lmbb-armed bg-amber-300" : "bg-zinc-600",
                )}
              />
              <span className="min-w-0 flex-1">
                <span className="flex items-baseline justify-between gap-2">
                  <span className="num text-[11px] font-semibold text-lm-text">{name}</span>
                  <span className={clsx(
                    "num shrink-0 text-[8px] uppercase tracking-wider",
                    status === "armed" ? "text-amber-300/80" : "text-lm-muted",
                  )}>
                    {status}
                  </span>
                </span>
                <span className="num block text-[9.5px] leading-snug text-lm-muted">{note}</span>
              </span>
            </div>
          ))}
        </div>
      </RailPanel>
    </div>
  );
}
