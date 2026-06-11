"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { DynamicHeadline } from "@/components/landing/DynamicHeadline";
import { clsx } from "clsx";

// ── The Lumora Field ─────────────────────────────────────────────────────────
// The signature hero: a living market pressure object. Layered depth — glowing
// pressure field, breathing liquidity bands, energy flowing along the price
// path, whale shockwaves, futures pressure streams, a particle drift and a
// radar scan sweep — plus cursor parallax so the field responds like an
// instrument, not a screenshot. Pure SVG + CSS, no canvas, no 3D library.
// Every animation sits behind prefers-reduced-motion; the frozen frame is
// still a complete, labeled scene.

const FIELD_CSS = `
.lmf-tilt { transition: transform 350ms ease-out; }
@media (min-width: 640px) {
  .lmf-tilt { transform: perspective(1100px) rotateX(7deg); }
}
.lmf-ring {
  opacity: 0;
  transform-box: fill-box;
  transform-origin: center;
}
.lmf-flow { opacity: 0; }
.lmf-scan-r { opacity: 0; }
.lmf-cell { opacity: var(--o, 0.1); }
@media (prefers-reduced-motion: no-preference) {
  .lmf-ring { animation: lmf-ping 14s ease-out infinite; }
  .lmf-ring-a2 { animation-delay: 0.35s; }
  .lmf-ring-b  { animation-delay: 4.6s; }
  .lmf-ring-b2 { animation-delay: 4.95s; }
  .lmf-ring-c  { animation-delay: 9.2s; }
  .lmf-ring-c2 { animation-delay: 9.55s; }
  @keyframes lmf-ping {
    0%, 3% { opacity: 0; transform: scale(0.3); }
    5%     { opacity: 0.7; transform: scale(0.55); }
    16%    { opacity: 0; transform: scale(2.4); }
    100%   { opacity: 0; transform: scale(0.3); }
  }
  .lmf-now-halo {
    transform-box: fill-box;
    transform-origin: center;
    animation: lmf-now 2.6s ease-in-out infinite;
  }
  @keyframes lmf-now {
    0%, 100% { opacity: 0.2; transform: scale(1); }
    50%      { opacity: 0.06; transform: scale(1.55); }
  }
  .lmf-drift-a { animation: lmf-drift 16s linear infinite; }
  .lmf-drift-b { animation: lmf-drift 22s linear infinite; animation-delay: -10s; }
  @keyframes lmf-drift {
    0%   { transform: translateX(-16px); opacity: 0; }
    12%  { opacity: 0.32; }
    85%  { opacity: 0.32; }
    100% { transform: translateX(30px); opacity: 0; }
  }
  .lmf-scan-r {
    opacity: 1;
    animation: lmf-scan 8s linear infinite;
  }
  @keyframes lmf-scan {
    0%   { transform: translateX(0); }
    100% { transform: translateX(910px); }
  }
  .lmf-flow {
    opacity: 0.85;
    animation: lmf-flow 8s linear infinite;
  }
  @keyframes lmf-flow {
    to { stroke-dashoffset: -920; }
  }
  .lmf-cell { animation: lmf-cellpulse 5.5s ease-in-out infinite; }
  @keyframes lmf-cellpulse {
    0%, 100% { opacity: var(--o, 0.1); }
    50%      { opacity: calc(var(--o, 0.1) * 0.4); }
  }
  .lmf-band-a { animation: lmf-band 9s ease-in-out infinite; }
  .lmf-band-b { animation: lmf-band 11s ease-in-out infinite; animation-delay: -4s; }
  @keyframes lmf-band {
    0%, 100% { opacity: 1; }
    50%      { opacity: 0.65; }
  }
  .lmf-part { animation: lmf-part var(--dur, 13s) linear infinite; }
  @keyframes lmf-part {
    0%   { transform: translate(0, 0); opacity: 0; }
    20%  { opacity: 0.35; }
    75%  { opacity: 0.15; }
    100% { transform: translate(16px, -20px); opacity: 0; }
  }
  .lmf-ann-in { animation: lmf-annin 0.45s ease-out; }
  @keyframes lmf-annin {
    from { opacity: 0; transform: translateY(4px); }
    to   { opacity: 1; transform: translateY(0); }
  }
  .lmf-ann-dot { animation: lmf-blink 1.6s ease-in-out infinite; }
  @keyframes lmf-blink {
    0%, 100% { opacity: 1; }
    50%      { opacity: 0.4; }
  }
  .lmf-scroll-dot { animation: lmf-sdrop 2.2s ease-in-out infinite; }
  @keyframes lmf-sdrop {
    0%   { transform: translateY(0); opacity: 0; }
    20%  { opacity: 0.9; }
    80%  { opacity: 0.9; }
    100% { transform: translateY(30px); opacity: 0; }
  }
}
`;

const MONO = "'JetBrains Mono', monospace";

const PATH_D =
  "M 0 232 C 50 228, 100 196, 150 158 C 168 146, 182 138, 194 142 C 232 158, 268 232, 308 264 C 322 276, 342 278, 358 266 C 396 240, 430 252, 462 240 C 510 222, 552 200, 596 188 C 628 180, 658 174, 684 170";

// Live annotation ticker — the field narrating itself.
const ANNOTATIONS = [
  { text: "Liquidity wall forming", cls: "text-red-400", dot: "bg-red-400" },
  { text: "Whale impact detected", cls: "text-emerald-400", dot: "bg-emerald-400" },
  { text: "Futures pressure rising", cls: "text-cyan-300", dot: "bg-cyan-300" },
  { text: "Sweep risk below", cls: "text-amber-400", dot: "bg-amber-400" },
  { text: "Read updating", cls: "text-lm-cyan", dot: "bg-lm-cyan" },
];

const SYMBOL_TABS = [
  { symbol: "BTCUSDT", active: true },
  { symbol: "ETHUSDT", active: false },
  { symbol: "SOLUSDT", active: false },
];

// Heatmap intensity cells inside the liquidity bands (deterministic — no
// render-time randomness, so SSR and client markup always match).
const ASK_CELLS = [
  { o: 0.2, d: "0s" }, { o: 0.09, d: "1.2s" }, { o: 0.16, d: "2.4s" }, { o: 0.07, d: "0.6s" },
  { o: 0.13, d: "3.1s" }, { o: 0.18, d: "1.8s" }, { o: 0.08, d: "2.7s" }, { o: 0.15, d: "0.9s" },
];
const BID_CELLS = [
  { o: 0.07, d: "0.4s" }, { o: 0.13, d: "1.6s" }, { o: 0.18, d: "2.8s" }, { o: 0.09, d: "0.8s" },
  { o: 0.15, d: "3.4s" }, { o: 0.08, d: "2.1s" }, { o: 0.19, d: "1.1s" }, { o: 0.12, d: "2.9s" },
];

// Ambient particle drift: [x, y, r, duration, delay]
const PARTICLES: Array<[number, number, number, string, string]> = [
  [60, 150, 1, "12s", "0s"], [130, 250, 1.2, "15s", "-3s"], [210, 120, 1, "11s", "-6s"],
  [280, 210, 1.3, "16s", "-2s"], [350, 300, 1, "13s", "-8s"], [420, 160, 1.2, "12s", "-5s"],
  [505, 250, 1, "17s", "-1s"], [585, 120, 1.2, "14s", "-7s"], [640, 210, 1, "12s", "-4s"],
  [170, 320, 1, "15s", "-9s"], [450, 330, 1.2, "13s", "-6s"], [625, 300, 1, "16s", "-2.5s"],
];

function FieldLabel({
  x, y, fill, children, anchor = "start", opacity = 0.85, size = 9,
}: {
  x: number; y: number; fill: string; children: string;
  anchor?: "start" | "middle" | "end"; opacity?: number; size?: number;
}) {
  return (
    <text
      x={x} y={y} fill={fill} opacity={opacity} textAnchor={anchor}
      fontFamily={MONO} fontSize={size} fontWeight="600" letterSpacing="1.4"
    >
      {children}
    </text>
  );
}

function FieldSvg() {
  return (
    <svg
      viewBox="0 0 720 400"
      className="block h-auto w-full"
      role="img"
      aria-label="The Lumora Field — a living market pressure scene for BTCUSDT showing a price path moving between liquidity bands, whale impact shockwaves, futures pressure streams and a sweep risk zone, summarized by a current read of LONG with score 72 and medium risk."
    >
      <defs>
        <linearGradient id="lmfPlane" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#0d0d11" />
          <stop offset="100%" stopColor="#0e0e14" />
        </linearGradient>
        <linearGradient id="lmfAsk" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="#ef4444" stopOpacity="0.16" />
          <stop offset="40%" stopColor="#ef4444" stopOpacity="0.07" />
          <stop offset="75%" stopColor="#ef4444" stopOpacity="0.13" />
          <stop offset="100%" stopColor="#ef4444" stopOpacity="0.06" />
        </linearGradient>
        <linearGradient id="lmfBid" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="#22c55e" stopOpacity="0.06" />
          <stop offset="35%" stopColor="#22c55e" stopOpacity="0.13" />
          <stop offset="70%" stopColor="#22c55e" stopOpacity="0.08" />
          <stop offset="100%" stopColor="#22c55e" stopOpacity="0.15" />
        </linearGradient>
        <linearGradient id="lmfScanG" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="#22d3ee" stopOpacity="0" />
          <stop offset="55%" stopColor="#22d3ee" stopOpacity="0.05" />
          <stop offset="92%" stopColor="#22d3ee" stopOpacity="0.16" />
          <stop offset="100%" stopColor="#22d3ee" stopOpacity="0" />
        </linearGradient>
        <radialGradient id="lmfVig" cx="50%" cy="42%" r="75%">
          <stop offset="55%" stopColor="#000000" stopOpacity="0" />
          <stop offset="100%" stopColor="#000000" stopOpacity="0.3" />
        </radialGradient>
        <pattern id="lmfHatch" width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <line x1="0" y1="0" x2="0" y2="8" stroke="#f59e0b" strokeWidth="1.5" opacity="0.28" />
        </pattern>
      </defs>

      {/* Plane */}
      <rect x="0" y="0" width="720" height="400" fill="url(#lmfPlane)" />

      {/* Grid — hairline, instrument-like */}
      {[40, 80, 120, 160, 200, 240, 280, 320, 360].map((y) => (
        <line key={y} x1="0" y1={y} x2="720" y2={y} stroke="#17171b" strokeWidth="1" />
      ))}
      {[120, 240, 360, 480, 600].map((x) => (
        <line key={x} x1={x} y1="0" x2={x} y2="368" stroke="#141418" strokeWidth="1" />
      ))}

      {/* Axes — price right, time bottom */}
      <FieldLabel x={712} y={83} fill="#52525b" anchor="end" opacity={0.9} size={8}>68.2k</FieldLabel>
      <FieldLabel x={712} y={163} fill="#52525b" anchor="end" opacity={0.9} size={8}>67.8k</FieldLabel>
      <FieldLabel x={712} y={243} fill="#52525b" anchor="end" opacity={0.9} size={8}>67.3k</FieldLabel>
      <FieldLabel x={712} y={323} fill="#52525b" anchor="end" opacity={0.9} size={8}>66.8k</FieldLabel>
      {[
        [120, "10:00"], [240, "11:00"], [360, "12:00"], [480, "13:00"], [600, "14:00"],
      ].map(([x, t]) => (
        <FieldLabel key={t} x={x as number} y={381} fill="#4b4b52" anchor="middle" opacity={0.9} size={8}>
          {t as string}
        </FieldLabel>
      ))}

      {/* Ask-side liquidity bands — breathing, with flickering intensity cells */}
      <g className="lmf-band-a">
        <rect x="0" y="64" width="720" height="24" fill="url(#lmfAsk)" />
        {ASK_CELLS.map(({ o, d }, i) => (
          <rect
            key={i} x={i * 90} y="64" width="90" height="24" fill="#ef4444"
            className="lmf-cell"
            style={{ "--o": o, animationDelay: d } as React.CSSProperties}
          />
        ))}
        <line x1="0" y1="88" x2="720" y2="88" stroke="#ef4444" strokeWidth="1" opacity="0.3" />
        <rect x="0" y="118" width="720" height="12" fill="#ef4444" opacity="0.04" />
      </g>
      <FieldLabel x={10} y={80} fill="#f87171" opacity={0.85}>ASK WALL · $38M</FieldLabel>
      <FieldLabel x={10} y={127} fill="#f87171" opacity={0.45}>ASK · $12M</FieldLabel>

      {/* Bid-side liquidity bands */}
      <g className="lmf-band-b">
        <rect x="0" y="272" width="720" height="22" fill="url(#lmfBid)" />
        {BID_CELLS.map(({ o, d }, i) => (
          <rect
            key={i} x={i * 90} y="272" width="90" height="22" fill="#22c55e"
            className="lmf-cell"
            style={{ "--o": o, animationDelay: d } as React.CSSProperties}
          />
        ))}
        <line x1="0" y1="272" x2="720" y2="272" stroke="#22c55e" strokeWidth="1" opacity="0.3" />
        <rect x="0" y="314" width="720" height="12" fill="#22c55e" opacity="0.04" />
      </g>
      <FieldLabel x={10} y={287} fill="#4ade80" opacity={0.85}>BID SUPPORT · $26M</FieldLabel>
      <FieldLabel x={10} y={323} fill="#4ade80" opacity={0.45}>BID · $9M</FieldLabel>

      {/* Sweep risk zone */}
      <rect x="0" y="344" width="720" height="20" fill="url(#lmfHatch)" />
      <rect x="0.5" y="344.5" width="719" height="19" fill="none" stroke="#f59e0b" strokeWidth="1" strokeDasharray="4 4" opacity="0.22" />
      <FieldLabel x={10} y={357} fill="#fbbf24" opacity={0.75}>SWEEP RISK</FieldLabel>

      {/* Ambient particle drift */}
      <g fill="#22d3ee">
        {PARTICLES.map(([x, y, r, dur, d], i) => (
          <circle
            key={i} cx={x} cy={y} r={r} opacity="0.16"
            className="lmf-part"
            style={{ "--dur": dur, animationDelay: d } as React.CSSProperties}
          />
        ))}
      </g>

      {/* Futures pressure streams — ticks leaning long */}
      <g className="lmf-drift-a" stroke="#a1a1a6" strokeWidth="1" opacity="0.3">
        <line x1="95" y1="172" x2="115" y2="172" />
        <line x1="235" y1="206" x2="255" y2="206" />
        <line x1="365" y1="158" x2="385" y2="158" />
        <line x1="485" y1="224" x2="505" y2="224" />
        <line x1="610" y1="148" x2="630" y2="148" />
      </g>
      <g className="lmf-drift-b" stroke="#a1a1a6" strokeWidth="1" opacity="0.3">
        <line x1="160" y1="238" x2="180" y2="238" />
        <line x1="320" y1="186" x2="340" y2="186" />
        <line x1="525" y1="222" x2="545" y2="222" />
        <line x1="648" y1="232" x2="668" y2="232" />
      </g>
      <FieldLabel x={712} y={262} fill="#a1a1a6" anchor="end" opacity={0.5} size={8}>FUTURES PRESSURE → LONG</FieldLabel>

      {/* Price path — glow underlay, crisp line, flowing energy */}
      <path d={PATH_D} fill="none" stroke="#22d3ee" strokeWidth="6" opacity="0.12" strokeLinecap="round" />
      <path d={PATH_D} fill="none" stroke="#22d3ee" strokeWidth="1.75" strokeLinecap="round" />
      <path
        d={PATH_D} fill="none" stroke="#a5f3fc" strokeWidth="2.4" strokeLinecap="round"
        strokeDasharray="6 109" className="lmf-flow"
      />

      {/* Whale impact shockwaves — double rings */}
      <circle className="lmf-ring" cx="192" cy="141" r="10" fill="none" stroke="#ef4444" strokeWidth="1.5" />
      <circle className="lmf-ring lmf-ring-a2" cx="192" cy="141" r="10" fill="none" stroke="#ef4444" strokeWidth="1" />
      <circle cx="192" cy="141" r="2.5" fill="#ef4444" />
      <FieldLabel x={206} y={146} fill="#f87171" opacity={0.85}>WHALE SELL · $7.1M</FieldLabel>

      <circle className="lmf-ring lmf-ring-b" cx="338" cy="276" r="10" fill="none" stroke="#22c55e" strokeWidth="1.5" />
      <circle className="lmf-ring lmf-ring-b2" cx="338" cy="276" r="10" fill="none" stroke="#22c55e" strokeWidth="1" />
      <circle cx="338" cy="276" r="2.5" fill="#22c55e" />
      <FieldLabel x={352} y={305} fill="#4ade80" opacity={0.85}>WHALE BUY · $4.2M</FieldLabel>

      <circle className="lmf-ring lmf-ring-c" cx="560" cy="198" r="10" fill="none" stroke="#22c55e" strokeWidth="1.5" />
      <circle className="lmf-ring lmf-ring-c2" cx="560" cy="198" r="10" fill="none" stroke="#22c55e" strokeWidth="1" />
      <circle cx="560" cy="198" r="2" fill="#22c55e" opacity="0.85" />
      <FieldLabel x={572} y={220} fill="#4ade80" opacity={0.6}>WHALE BUY · $2.8M</FieldLabel>

      {/* Now marker */}
      <circle className="lmf-now-halo" cx="684" cy="170" r="10" fill="#22d3ee" opacity="0.2" />
      <circle cx="684" cy="170" r="3" fill="#22d3ee" />
      <FieldLabel x={684} y={152} fill="#22d3ee" anchor="middle" opacity={0.85} size={8}>NOW</FieldLabel>

      {/* Radar scan sweep */}
      <rect className="lmf-scan-r" x="-90" y="0" width="90" height="368" fill="url(#lmfScanG)" />

      {/* Corner vignette for depth */}
      <rect x="0" y="0" width="720" height="400" fill="url(#lmfVig)" pointerEvents="none" />
    </svg>
  );
}

export function LumoraFieldHero() {
  const tiltRef = useRef<HTMLDivElement | null>(null);
  const motionOkRef = useRef(false);
  const [motionOk, setMotionOk] = useState(false);
  const [annIdx, setAnnIdx] = useState(0);

  useEffect(() => {
    const ok = !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    motionOkRef.current = ok;
    setMotionOk(ok);
  }, []);

  // Annotation ticker — the field narrating itself, one state at a time.
  useEffect(() => {
    if (!motionOk) return;
    const id = setTimeout(() => setAnnIdx((i) => (i + 1) % ANNOTATIONS.length), 3600);
    return () => clearTimeout(id);
  }, [motionOk, annIdx]);

  // Cursor parallax — direct style mutation, no re-render per mousemove.
  const handleMove = (e: React.MouseEvent<HTMLDivElement>) => {
    const el = tiltRef.current;
    if (!el || !motionOkRef.current || window.innerWidth < 640) return;
    const r = e.currentTarget.getBoundingClientRect();
    const px = (e.clientX - r.left) / r.width - 0.5;
    const py = (e.clientY - r.top) / r.height - 0.5;
    el.style.transform = `perspective(1100px) rotateX(${(7 - py * 6).toFixed(2)}deg) rotateY(${(px * 8).toFixed(2)}deg)`;
  };
  const handleLeave = () => {
    if (tiltRef.current) tiltRef.current.style.transform = "";
  };

  const ann = ANNOTATIONS[annIdx];

  return (
    <section className="relative overflow-hidden px-4 pb-12 pt-12 sm:pt-16">
      <style dangerouslySetInnerHTML={{ __html: FIELD_CSS }} />

      {/* Ambient pressure glow behind the whole hero */}
      <div aria-hidden className="pointer-events-none absolute inset-0">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_55%_42%_at_68%_18%,rgba(34,211,238,0.08),transparent_70%)]" />
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_38%_32%_at_12%_32%,rgba(139,92,246,0.06),transparent_70%)]" />
      </div>

      <div className="relative mx-auto grid max-w-6xl grid-cols-1 items-center gap-9 lg:grid-cols-[minmax(0,4.5fr)_minmax(0,7.5fr)] lg:gap-12">
        {/* Copy */}
        <div>
          <div className="flex flex-wrap items-center gap-2.5">
            <span className="num text-[10px] uppercase tracking-[0.22em] text-lm-muted">
              Liquidity intelligence terminal
            </span>
            <StatusBadge variant="neutral" size="sm">PRIVATE BETA</StatusBadge>
          </div>
          <DynamicHeadline />
          <p className="mt-4 max-w-md text-[15px] leading-relaxed text-lm-text-dim">
            Lumora turns liquidity, whale flow and futures pressure into a live market read.
          </p>
          <div className="mt-7 flex flex-col gap-2.5 sm:flex-row">
            <Link
              href="/dashboard"
              className="inline-flex items-center justify-center gap-2 rounded-md bg-cyan-400 px-5 py-2.5 text-[13px] font-semibold text-zinc-950 shadow-[0_0_28px_rgba(34,211,238,0.25)] transition-colors hover:bg-cyan-300"
            >
              Launch terminal <ArrowRight className="h-3.5 w-3.5" />
            </Link>
            <Link
              href="/liquidity-map"
              className="inline-flex items-center justify-center gap-2 rounded-md border border-lm-border px-5 py-2.5 text-[13px] font-medium text-lm-text-dim transition-colors hover:border-zinc-600 hover:text-lm-text"
            >
              View live intelligence
            </Link>
          </div>
          <p className="mt-5 max-w-md text-[10.5px] leading-relaxed text-lm-muted">
            Demo data shown — live integrations rolling out in beta. Informational market
            context only: no guaranteed outcomes, not financial advice.
          </p>
        </div>

        {/* The Lumora Field — living market object */}
        <div className="relative" onMouseMove={handleMove} onMouseLeave={handleLeave}>
          {/* Pressure glow halo around the instrument */}
          <div aria-hidden className="pointer-events-none absolute -inset-8">
            <div className="absolute -right-6 top-6 h-64 w-64 rounded-full bg-cyan-500/10 blur-3xl" />
            <div className="absolute -top-4 left-4 h-44 w-56 rounded-full bg-red-500/[0.07] blur-3xl" />
            <div className="absolute bottom-0 left-1/4 h-44 w-64 rounded-full bg-emerald-500/[0.07] blur-3xl" />
          </div>

          <div ref={tiltRef} className="lmf-tilt relative">
            <div className="overflow-hidden rounded-lg border border-lm-border bg-lm-surface lm-chart-frame">
              {/* Chrome — symbol tabs · market state · feed status */}
              <div className="flex items-center justify-between gap-2 border-b border-lm-border bg-lm-surface-muted/80 px-2.5 py-1.5">
                <div className="flex items-center gap-1">
                  {SYMBOL_TABS.map(({ symbol, active }) => (
                    <span
                      key={symbol}
                      className={clsx(
                        "num rounded px-2 py-1 text-[9px] font-semibold tracking-wider",
                        active
                          ? "border border-lm-border bg-lm-surface text-lm-cyan"
                          : "text-lm-muted",
                      )}
                    >
                      {symbol}
                    </span>
                  ))}
                </div>
                <div className="num hidden items-center gap-2 text-[9px] uppercase tracking-wider text-lm-muted md:flex">
                  <span>SPOT + FUT</span>
                  <span className="text-lm-border">|</span>
                  <span>STATE · EXPANSION</span>
                </div>
                <div className="flex items-center gap-2">
                  <StatusBadge variant="live" size="sm" dot>DEMO FEED</StatusBadge>
                  <span className="num hidden text-[9px] text-lm-muted sm:inline">UPD 14:32:08 UTC</span>
                </div>
              </div>

              {/* The field */}
              <div className="relative">
                <FieldSvg />

                {/* Live annotation ticker */}
                <div className="absolute left-2.5 top-2.5 flex items-center gap-1.5 rounded-md border border-lm-border bg-[#0c0c0e]/85 px-2.5 py-1.5">
                  <span className={clsx("h-1.5 w-1.5 rounded-full", ann.dot, "lmf-ann-dot")} />
                  <span
                    key={annIdx}
                    className={clsx("lmf-ann-in num text-[9px] uppercase tracking-widest", ann.cls)}
                  >
                    {ann.text}
                  </span>
                </div>

                {/* Current read chip — same language as the app's Current Read */}
                <div className="absolute right-2.5 top-2.5 rounded-md border border-lm-border bg-lm-surface/95 px-2.5 py-1.5">
                  <p className="num text-[7.5px] uppercase tracking-[0.2em] text-lm-muted">Current read</p>
                  <div className="mt-0.5 flex items-baseline gap-1.5">
                    <span className="num text-[12px] font-bold leading-none text-emerald-400">LONG</span>
                    <span className="num text-[10px] leading-none text-lm-text">
                      72<span className="text-lm-muted">/100</span>
                    </span>
                  </div>
                </div>
              </div>

              {/* Status bar — read, confidence, risk, futures context */}
              <div className="lm-no-scrollbar flex items-center justify-between gap-3 overflow-x-auto border-t border-lm-border bg-lm-surface-muted/80 px-3 py-1.5">
                <div className="num flex items-center gap-3.5 whitespace-nowrap text-[9px] uppercase tracking-wider text-lm-muted">
                  <span>READ <span className="font-semibold text-emerald-400">LONG</span></span>
                  <span>SCORE <span className="text-lm-text">72/100</span></span>
                  <span>CONF <span className="text-lm-text">68%</span></span>
                  <span>RISK <span className="text-amber-400">MED</span></span>
                  <span className="hidden md:inline">FUNDING <span className="text-lm-text">+0.012%</span></span>
                  <span className="hidden md:inline">OI <span className="text-lm-text">+2.4%</span></span>
                  <span className="hidden lg:inline">PRESSURE <span className="text-emerald-400">→ LONG</span></span>
                </div>
                <span className="num whitespace-nowrap text-[9px] text-lm-muted">LAST EVENT 6s AGO</span>
              </div>
            </div>
          </div>

          <div className="mt-2 flex items-center justify-between px-1">
            <span className="num text-[8.5px] uppercase tracking-[0.18em] text-lm-muted">
              The Lumora Field — illustrative pressure scene
            </span>
            <span className="num text-[8.5px] uppercase tracking-[0.18em] text-lm-muted">
              <span className="hidden lg:inline">⌖ responds to cursor · </span>
              private beta · demo data
            </span>
          </div>
        </div>
      </div>

      {/* Scroll cue — invite the descent into the product world */}
      <div className="relative mx-auto mt-9 hidden w-fit flex-col items-center gap-1.5 sm:flex">
        <span className="num text-[8.5px] uppercase tracking-[0.25em] text-lm-muted">
          Decode the field
        </span>
        <div className="relative h-9 w-px bg-gradient-to-b from-zinc-700 to-transparent">
          <span className="lmf-scroll-dot absolute -left-[2px] top-0 h-[5px] w-[5px] rounded-full bg-cyan-400/70" />
        </div>
      </div>
    </section>
  );
}
