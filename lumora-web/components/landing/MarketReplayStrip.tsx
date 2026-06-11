"use client";

import { useEffect, useState } from "react";
import { Panel } from "@/components/ui/Panel";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { clsx } from "clsx";

// ── Signal tape — endless intelligence feed ──────────────────────────────────
// Eight staged events stream through a sliding window: the newest row glows,
// older rows fade with age, and timestamps keep rolling forward so the tape
// never visibly "resets" — it reads like an ongoing session, not a looping
// video. Users who prefer reduced motion get the full staged sequence at rest.

const STRIP_CSS = `
@media (prefers-reduced-motion: no-preference) {
  .lmrs-new { animation: lmrs-in 0.35s ease-out; }
  @keyframes lmrs-in {
    from { opacity: 0; transform: translateY(-4px); }
    to   { opacity: 1; transform: translateY(0); }
  }
  .lmrs-blink { animation: lmrs-blink 1.1s steps(2, start) infinite; }
  @keyframes lmrs-blink {
    0%, 100% { opacity: 1; }
    50%      { opacity: 0; }
  }
}
`;

const EVENTS = [
  {
    tag: "APPROACH",
    tagClass: "text-red-400",
    dot: "bg-red-400",
    text: "Price drifts into the $38M ask wall at 68,000.",
    val: "$38M",
    valClass: "text-red-400/80",
  },
  {
    tag: "WHALE SELL",
    tagClass: "text-red-400",
    dot: "bg-red-400",
    text: "$7.1M market sell hits the tape — price rejects.",
    val: "-$7.1M",
    valClass: "text-red-400/80",
  },
  {
    tag: "ABSORPTION",
    tagClass: "text-emerald-400",
    dot: "bg-emerald-400",
    text: "Bids absorb the flush — 67,350 support holds twice.",
    val: "$26M",
    valClass: "text-emerald-400/80",
  },
  {
    tag: "LIQ BUILD",
    tagClass: "text-emerald-400",
    dot: "bg-emerald-400",
    text: "Bid ladder thickens below price — demand stacking.",
    val: "+$8.4M",
    valClass: "text-emerald-400/80",
  },
  {
    tag: "PRESSURE",
    tagClass: "text-amber-400",
    dot: "bg-amber-400",
    text: "Futures pressure leans long — sweep risk fading.",
    val: "OI +2.4%",
    valClass: "text-lm-text-dim",
  },
  {
    tag: "FUNDING",
    tagClass: "text-cyan-300",
    dot: "bg-cyan-300",
    text: "Funding ticks positive — longs paying, crowd leaning in.",
    val: "+0.012%",
    valClass: "text-lm-text-dim",
  },
  {
    tag: "SWEEP WATCH",
    tagClass: "text-amber-400",
    dot: "bg-amber-400",
    text: "Stops clustered below 66,800 — flush risk if support breaks.",
    val: "ZONE 66.8K",
    valClass: "text-amber-400/80",
  },
  {
    tag: "READ",
    tagClass: "text-lm-cyan",
    dot: "bg-lm-cyan",
    text: "Read updates: LONG · score 72 · risk medium.",
    val: "LONG 72",
    valClass: "text-emerald-400/80",
  },
];

const WINDOW = 6;
const STEP_MS = 3600;

// Rolling session clock: event N happens 6s after event N-1, starting at
// 14:31:38. Timestamps derive from the absolute tick, so the tape's time
// always moves forward even as the staged sequence cycles.
const BASE_S = 14 * 3600 + 31 * 60 + 38;
function clock(abs: number): string {
  const t = BASE_S + abs * 6;
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(Math.floor(t / 3600) % 24)}:${p(Math.floor((t % 3600) / 60))}:${p(t % 60)}`;
}

// Older rows dim with age — newest at full strength.
const AGE_DIM = ["", "opacity-90", "opacity-80", "opacity-70", "opacity-60", "opacity-50"];

export function MarketReplayStrip() {
  const [tick, setTick] = useState(0);
  const [animate, setAnimate] = useState(false);

  // Stream events only when the user is fine with motion; otherwise show the
  // full staged sequence at rest.
  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setTick(EVENTS.length - 1);
    } else {
      setAnimate(true);
    }
  }, []);

  useEffect(() => {
    if (!animate) return;
    const id = setTimeout(() => setTick((t) => t + 1), STEP_MS);
    return () => clearTimeout(id);
  }, [animate, tick]);

  const start = animate ? Math.max(0, tick - WINDOW + 1) : 0;
  const end = animate ? tick : EVENTS.length - 1;
  const rows: number[] = [];
  for (let abs = start; abs <= end; abs++) rows.push(abs);

  const isReadNow = animate && EVENTS[tick % EVENTS.length].tag === "READ";

  return (
    <section className="px-4 py-9">
      <style dangerouslySetInnerHTML={{ __html: STRIP_CSS }} />
      <div className="mx-auto max-w-6xl">
        <div className="mb-2.5 flex flex-wrap items-end justify-between gap-2">
          <div>
            <span className="lm-section-title">01 · The signal</span>
            <h2 className="mt-2 text-xl font-semibold tracking-tight text-lm-text">
              Raw market events, as they hit the tape.
            </h2>
          </div>
          <span className="num text-[9px] uppercase tracking-wider text-lm-muted">
            How Lumora narrates pressure as it builds
          </span>
        </div>
        <Panel flush className="overflow-hidden">
          {/* Tape header */}
          <div className="flex items-center justify-between gap-2 border-b border-lm-border bg-lm-surface-muted/80 px-3 py-1.5">
            <span className="num text-[9px] font-semibold uppercase tracking-[0.18em] text-lm-text-dim">
              Signal tape ▸ BTCUSDT
            </span>
            <div className="flex items-center gap-2.5">
              <span
                key={isReadNow ? tick : -1}
                className={clsx(
                  "num rounded border border-lm-border bg-lm-surface px-1.5 py-0.5 text-[8.5px] uppercase tracking-wider text-emerald-400",
                  isReadNow && "lmrs-new",
                )}
              >
                READ LONG · 72
              </span>
              <span className="num hidden text-[9px] uppercase tracking-wider text-lm-muted sm:inline">
                {clock(end)} UTC
              </span>
              <StatusBadge variant="warning" size="sm">DEMO</StatusBadge>
            </div>
          </div>

          {/* Streaming rows */}
          <div className="divide-y divide-lm-border/60">
            {rows.map((abs) => {
              const e = EVENTS[abs % EVENTS.length];
              const age = end - abs;
              const isNew = animate && age === 0;
              return (
                <div
                  key={abs}
                  className={clsx(
                    "flex items-baseline gap-3 px-3 py-2",
                    isNew
                      ? "lmrs-new bg-lm-surface-muted shadow-[inset_1.5px_0_0_rgba(34,211,238,0.7)]"
                      : animate && AGE_DIM[Math.min(age, AGE_DIM.length - 1)],
                  )}
                >
                  <span className="num w-[58px] shrink-0 text-[10px] text-lm-muted">{clock(abs)}</span>
                  <span className="flex w-[92px] shrink-0 items-center gap-1.5">
                    <span className={clsx("h-1 w-1 shrink-0 rounded-full", e.dot)} />
                    <span className={clsx("num text-[9px] font-semibold uppercase tracking-widest", e.tagClass)}>
                      {e.tag}
                    </span>
                  </span>
                  <span
                    className={clsx(
                      "min-w-0 flex-1 text-[11.5px] leading-snug",
                      isNew ? "text-lm-text" : "text-lm-text-dim",
                    )}
                  >
                    {e.text}
                  </span>
                  <span className={clsx("num hidden shrink-0 text-[10px] sm:inline", e.valClass)}>
                    {e.val}
                  </span>
                </div>
              );
            })}
            {/* Waiting cursor */}
            <div className="flex items-center gap-2 px-3 py-2">
              <span className="lmrs-blink num text-[10px] leading-none text-lm-cyan">▌</span>
              <span className="num text-[9px] uppercase tracking-widest text-lm-muted">
                awaiting next event
              </span>
            </div>
          </div>
        </Panel>
        <p className="mt-2 px-1 text-[10px] leading-snug text-lm-muted">
          Looping replay of an illustrative staged sequence. Demo data, not live events.
        </p>
      </div>
    </section>
  );
}
