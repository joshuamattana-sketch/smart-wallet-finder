"use client";

// components/gold-bot/GoldChartInstrument.tsx
// LM73C — the heart of the command room: a framed XAUUSD instrument.
//
// No real gold feed exists yet, so this is a deterministic staged session
// (seeded PRNG — SSR and client always agree) drawn as pure SVG: session
// shading (Asia/London/NY), candles, a liquidity sweep + reclaim narrative,
// an FVG zone, key levels, and a watching-ring on the live edge. The frame
// carries tactical corner brackets, edge lighting and a slow scan sweep —
// an instrument, not a screenshot. All motion is reduced-motion gated.

import { clsx } from "clsx";
import { StatusBadge } from "@/components/ui/StatusBadge";

const CHART_CSS = `
.lmgc-scan { opacity: 0; }
@media (prefers-reduced-motion: no-preference) {
  .lmgc-scan { opacity: 1; animation: lmgc-scan 9s linear infinite; }
  @keyframes lmgc-scan {
    0%   { transform: translateX(0); }
    100% { transform: translateX(740px); }
  }
  .lmgc-now {
    transform-box: fill-box;
    transform-origin: center;
    animation: lmgc-now 2.8s ease-in-out infinite;
  }
  @keyframes lmgc-now {
    0%, 100% { opacity: 0.25; transform: scale(1); }
    50%      { opacity: 0.05; transform: scale(1.7); }
  }
  .lmgc-sweep-ring {
    transform-box: fill-box;
    transform-origin: center;
    animation: lmgc-ring 6s ease-out infinite;
  }
  @keyframes lmgc-ring {
    0%, 4% { opacity: 0; transform: scale(0.4); }
    8%     { opacity: 0.7; transform: scale(0.7); }
    26%    { opacity: 0; transform: scale(2.3); }
    100%   { opacity: 0; transform: scale(0.4); }
  }
  .lmgc-fvg { animation: lmgc-fvg 5s ease-in-out infinite; }
  @keyframes lmgc-fvg {
    0%, 100% { opacity: 0.9; }
    50%      { opacity: 0.55; }
  }
}
`;

const MONO = "'JetBrains Mono', monospace";

// ── Deterministic XAUUSD session ─────────────────────────────────────────────
function mulberry32(seed: number): () => number {
  let a = seed;
  return () => {
    a += 0x6d2b79f5;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// Narrative waypoints (bar index → close): Asia drift → London sweep of the
// Asia low → reclaim + displacement (leaves FVG) → NY continuation, watching.
const WAYPOINTS: Array<[number, number]> = [
  [0, 2386], [10, 2384], [18, 2381], [26, 2379],          // Asia drift down
  [32, 2374], [35, 2369],                                  // London sweep
  [38, 2378], [44, 2389], [50, 2393],                      // reclaim + displacement
  [58, 2391], [66, 2395], [72, 2392],                      // NY hold
];
const BAR_COUNT = 73;

function targetAt(i: number): number {
  for (let s = 0; s < WAYPOINTS.length - 1; s++) {
    const [i0, p0] = WAYPOINTS[s];
    const [i1, p1] = WAYPOINTS[s + 1];
    if (i >= i0 && i <= i1) {
      const f = i1 === i0 ? 0 : (i - i0) / (i1 - i0);
      return p0 + (p1 - p0) * f;
    }
  }
  return WAYPOINTS[WAYPOINTS.length - 1][1];
}

interface Bar { o: number; h: number; l: number; c: number }

function buildBars(): Bar[] {
  const rand = mulberry32(7331);
  const bars: Bar[] = [];
  let prev = targetAt(0);
  for (let i = 0; i < BAR_COUNT; i++) {
    const drift = targetAt(i);
    const c = i === BAR_COUNT - 1 ? drift : drift + (rand() - 0.5) * 2.2;
    const o = i === 0 ? drift - 0.8 : prev;
    const h = Math.max(o, c) + rand() * 1.4;
    const l = Math.min(o, c) - rand() * 1.4;
    bars.push({ o, h, l, c });
    prev = c;
  }
  // Force the sweep bar to actually pierce the Asia low.
  bars[35].l = 2367.4;
  return bars;
}

const BARS = buildBars();

// Plot geometry
const W = 740;
const H = 380;
const PAD_R = 56;
const PAD_T = 18;
const PAD_B = 26;
const PLOT_W = W - PAD_R;
const PLOT_H = H - PAD_T - PAD_B;

const P_MIN = 2364;
const P_MAX = 2400;
function py(p: number): number {
  return PAD_T + ((P_MAX - p) / (P_MAX - P_MIN)) * PLOT_H;
}
function bx(i: number): number {
  return (i + 0.5) * (PLOT_W / BAR_COUNT);
}
const BAR_W = (PLOT_W / BAR_COUNT) * 0.62;

// Key levels + zones of the staged narrative
const ASIA_LOW = 2374.2;
const KEY_LEVEL = 2392.5;
const FVG_TOP = 2384.5;
const FVG_BOT = 2380.8;
const LAST = BARS[BAR_COUNT - 1].c;

// Session boundaries (bar index)
const LONDON_AT = 26;
const NY_AT = 48;

export function GoldChartInstrument({ className }: { className?: string }) {
  return (
    <div className={clsx("relative", className)}>
      <style dangerouslySetInnerHTML={{ __html: CHART_CSS }} />

      {/* Halo under the instrument */}
      <div aria-hidden className="pointer-events-none absolute -inset-6">
        <div className="absolute left-1/4 top-0 h-40 w-64 rounded-full bg-amber-400/[0.07] blur-3xl" />
        <div className="absolute bottom-0 right-1/5 h-36 w-56 rounded-full bg-cyan-500/[0.05] blur-3xl" />
      </div>

      {/* Instrument frame — tactical corner brackets + edge light */}
      <div className="relative overflow-hidden rounded-xl border border-amber-400/[0.14] bg-[#0b0a08] shadow-[0_30px_70px_-28px_rgba(0,0,0,0.95),inset_0_1px_0_rgba(255,255,255,0.05),0_0_40px_-18px_rgba(252,211,77,0.35)]">
        {/* corner brackets */}
        {[
          "left-2 top-2 border-l-2 border-t-2",
          "right-2 top-2 border-r-2 border-t-2",
          "left-2 bottom-2 border-l-2 border-b-2",
          "right-2 bottom-2 border-r-2 border-b-2",
        ].map((pos) => (
          <span
            key={pos}
            aria-hidden
            className={clsx("pointer-events-none absolute z-10 h-3.5 w-3.5 rounded-[1px] border-amber-300/40", pos)}
          />
        ))}
        {/* edge lighting */}
        <span aria-hidden className="pointer-events-none absolute inset-x-0 top-0 z-10 h-px bg-gradient-to-r from-transparent via-amber-300/30 to-transparent" />
        <span aria-hidden className="pointer-events-none absolute left-0 top-0 z-10 h-24 w-px bg-gradient-to-b from-amber-300/25 to-transparent" />
        <span aria-hidden className="pointer-events-none absolute right-0 top-0 z-10 h-24 w-px bg-gradient-to-b from-cyan-400/20 to-transparent" />

        {/* Instrument header */}
        <div className="relative flex flex-wrap items-center gap-x-3 gap-y-1.5 border-b border-amber-400/[0.1] bg-gradient-to-b from-[#12100b]/90 to-[#0c0b08]/80 px-3.5 py-2">
          <span className="num text-[12px] font-bold tracking-[0.1em] text-amber-200">XAUUSD</span>
          <span className="num text-[9px] uppercase tracking-[0.2em] mt-px text-lm-muted">M5 · Demo environment</span>
          <span className="ml-auto flex items-center gap-2">
            <span className="lm-price text-[15px] leading-none text-amber-200 drop-shadow-[0_0_10px_rgba(252,211,77,0.35)]">
              {LAST.toFixed(1)}
            </span>
            <StatusBadge variant="demo" size="sm">VISUAL MOCK</StatusBadge>
          </span>
        </div>

        {/* The field */}
        <svg
          viewBox={`0 0 ${W} ${H}`}
          className="block h-auto w-full"
          role="img"
          aria-label="Staged XAUUSD session: Asia drift, London sweep of the Asia low with reclaim leaving a fair value gap, New York continuation above the key level — the bot is watching the live edge."
        >
          <defs>
            <linearGradient id="lmgcScan" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stopColor="#fcd34d" stopOpacity="0" />
              <stop offset="60%" stopColor="#fcd34d" stopOpacity="0.04" />
              <stop offset="92%" stopColor="#fcd34d" stopOpacity="0.12" />
              <stop offset="100%" stopColor="#fcd34d" stopOpacity="0" />
            </linearGradient>
            <radialGradient id="lmgcVig" cx="50%" cy="40%" r="80%">
              <stop offset="55%" stopColor="#000" stopOpacity="0" />
              <stop offset="100%" stopColor="#000" stopOpacity="0.35" />
            </radialGradient>
            <linearGradient id="lmgcNY" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#fcd34d" stopOpacity="0.045" />
              <stop offset="100%" stopColor="#fcd34d" stopOpacity="0.01" />
            </linearGradient>
          </defs>

          {/* plate */}
          <rect width={W} height={H} fill="#0b0a08" />

          {/* session shading */}
          <rect x={bx(LONDON_AT)} y={PAD_T} width={bx(NY_AT) - bx(LONDON_AT)} height={PLOT_H} fill="#22d3ee" opacity="0.025" />
          <rect x={bx(NY_AT)} y={PAD_T} width={PLOT_W - bx(NY_AT)} height={PLOT_H} fill="url(#lmgcNY)" />

          {/* grid */}
          {[2370, 2380, 2390, 2400].map((p) => (
            <g key={p}>
              <line x1="0" y1={py(p)} x2={PLOT_W} y2={py(p)} stroke="#1c1812" strokeWidth="1" />
              <text x={W - 8} y={py(p) + 3} fill="#6b5d3f" textAnchor="end" fontFamily={MONO} fontSize="8.5">
                {p.toFixed(0)}
              </text>
            </g>
          ))}
          {/* session labels */}
          {[
            [bx(LONDON_AT / 2), "ASIA"],
            [bx((LONDON_AT + NY_AT) / 2), "LONDON"],
            [bx((NY_AT + BAR_COUNT) / 2), "NEW YORK"],
          ].map(([x, s]) => (
            <text key={s as string} x={x as number} y={H - 9} fill="#6b5d3f" fontFamily={MONO} fontSize="8" textAnchor="middle" letterSpacing="2" opacity="0.8">
              {s as string}
            </text>
          ))}
          {[bx(LONDON_AT), bx(NY_AT)].map((x) => (
            <line key={x} x1={x} y1={PAD_T} x2={x} y2={PAD_T + PLOT_H} stroke="#241e14" strokeWidth="1" strokeDasharray="2 5" />
          ))}

          {/* FVG zone — left by the reclaim displacement */}
          <g className="lmgc-fvg">
            <rect x={bx(38)} y={py(FVG_TOP)} width={PLOT_W - bx(38)} height={py(FVG_BOT) - py(FVG_TOP)} fill="#fcd34d" opacity="0.06" />
            <line x1={bx(38)} y1={py(FVG_TOP)} x2={PLOT_W} y2={py(FVG_TOP)} stroke="#fcd34d" strokeWidth="1" opacity="0.25" strokeDasharray="3 4" />
            <line x1={bx(38)} y1={py(FVG_BOT)} x2={PLOT_W} y2={py(FVG_BOT)} stroke="#fcd34d" strokeWidth="1" opacity="0.25" strokeDasharray="3 4" />
          </g>
          <text x={PLOT_W - 6} y={py(FVG_TOP) + 11} fill="#fcd34d" opacity="0.65" fontFamily={MONO} fontSize="8" textAnchor="end" letterSpacing="1.2">
            FVG · UNTAPPED
          </text>

          {/* Asia low — swept level */}
          <line x1="0" y1={py(ASIA_LOW)} x2={PLOT_W} y2={py(ASIA_LOW)} stroke="#f87171" strokeWidth="1" opacity="0.3" strokeDasharray="5 4" />
          <text x="8" y={py(ASIA_LOW) - 5} fill="#f87171" opacity="0.7" fontFamily={MONO} fontSize="8" letterSpacing="1.2">
            ASIA LOW · SWEPT
          </text>

          {/* Key level above */}
          <line x1="0" y1={py(KEY_LEVEL)} x2={PLOT_W} y2={py(KEY_LEVEL)} stroke="#22d3ee" strokeWidth="1" opacity="0.3" strokeDasharray="5 4" />
          <text x="8" y={py(KEY_LEVEL) - 5} fill="#22d3ee" opacity="0.7" fontFamily={MONO} fontSize="8" letterSpacing="1.2">
            KEY LEVEL · PRIOR DAY HIGH
          </text>

          {/* candles */}
          {BARS.map((b, i) => {
            const up = b.c >= b.o;
            const x = bx(i);
            return (
              <g key={i}>
                <line x1={x} y1={py(b.h)} x2={x} y2={py(b.l)} stroke={up ? "rgba(52,211,153,0.5)" : "rgba(248,113,113,0.5)"} strokeWidth="1" />
                <rect
                  x={x - BAR_W / 2}
                  y={py(Math.max(b.o, b.c))}
                  width={BAR_W}
                  height={Math.max(1.5, Math.abs(py(b.o) - py(b.c)))}
                  fill={up ? "rgba(52,211,153,0.8)" : "rgba(248,113,113,0.78)"}
                />
              </g>
            );
          })}

          {/* sweep marker — ring at the London sweep low */}
          <circle className="lmgc-sweep-ring" cx={bx(35)} cy={py(2367.4)} r="9" fill="none" stroke="#fcd34d" strokeWidth="1.5" />
          <circle cx={bx(35)} cy={py(2367.4)} r="2.4" fill="#fcd34d" />
          <text x={bx(35) + 12} y={py(2367.4) + 4} fill="#fcd34d" opacity="0.85" fontFamily={MONO} fontSize="8.5" letterSpacing="1.2">
            SWEEP + RECLAIM
          </text>

          {/* live edge — watching ring */}
          <line x1={bx(BAR_COUNT - 1)} y1={PAD_T} x2={bx(BAR_COUNT - 1)} y2={PAD_T + PLOT_H} stroke="#fcd34d" strokeWidth="1" opacity="0.12" />
          <circle className="lmgc-now" cx={bx(BAR_COUNT - 1)} cy={py(LAST)} r="11" fill="#fcd34d" opacity="0.2" />
          <circle cx={bx(BAR_COUNT - 1)} cy={py(LAST)} r="3" fill="#fcd34d" />
          <text x={bx(BAR_COUNT - 1)} y={py(LAST) - 16} fill="#fcd34d" fontFamily={MONO} fontSize="8" textAnchor="middle" letterSpacing="1.5">
            WATCHING
          </text>

          {/* price tag at live edge */}
          <rect x={PLOT_W + 4} y={py(LAST) - 8} width={PAD_R - 10} height="16" rx="2" fill="#fcd34d" opacity="0.14" />
          <text x={PLOT_W + (PAD_R - 6) / 2} y={py(LAST) + 3.5} fill="#fde68a" fontFamily={MONO} fontSize="9" fontWeight="700" textAnchor="middle">
            {LAST.toFixed(1)}
          </text>

          {/* scan sweep + vignette */}
          <rect className="lmgc-scan" x="-110" y={PAD_T} width="110" height={PLOT_H} fill="url(#lmgcScan)" />
          <rect width={W} height={H} fill="url(#lmgcVig)" pointerEvents="none" />
        </svg>

        {/* Instrument footer — thesis + risk state around the chart */}
        <div className="relative flex flex-wrap items-center justify-between gap-x-4 gap-y-1.5 border-t border-amber-400/[0.1] bg-[#0c0b08]/90 px-3.5 py-2">
          <span className="num flex min-w-0 items-center gap-2 text-[9.5px] uppercase tracking-wider text-lm-muted">
            <span className="text-amber-300/90">THESIS</span>
            <span className="truncate text-lm-text-dim normal-case tracking-normal text-[10.5px]">
              Sweep of Asia low reclaimed — long continuation valid while FVG holds.
            </span>
          </span>
          <span className="num flex shrink-0 items-center gap-3 text-[9px] uppercase tracking-wider">
            <span className="text-lm-muted">RISK <span className="text-emerald-400">CHECKED</span></span>
            <span className="text-lm-muted">MODE <span className="text-amber-300">OBSERVE</span></span>
            <span className="text-lm-muted">EXEC <span className="text-amber-300/90">DEMO GUARDED</span></span>
          </span>
        </div>
      </div>
    </div>
  );
}
