"use client";

import { useRef } from "react";
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { clsx } from "clsx";

// ── Live terminal preview ─────────────────────────────────────────────────────
// Section 04: a staged shot of the product itself — nav strip, current read,
// liquidity heat column, whale tape — composed as one cinematic instrument
// window with a scan sweep and cursor tilt. Everything is the app's own visual
// language; nothing here is a generic mockup. Pure divs + CSS, demo values.

const PREVIEW_CSS = `
.lmtp-tilt { transition: transform 380ms ease-out; }
@media (min-width: 768px) {
  .lmtp-tilt { transform: perspective(1300px) rotateX(4deg); }
}
@media (prefers-reduced-motion: no-preference) {
  .lmtp-scan { animation: lmtp-scan 7s linear infinite; }
  @keyframes lmtp-scan {
    0%   { transform: translateY(-100%); opacity: 0; }
    8%   { opacity: 1; }
    92%  { opacity: 1; }
    100% { transform: translateY(520px); opacity: 0; }
  }
  .lmtp-heat { animation: lmtp-heat 5s ease-in-out infinite; }
  @keyframes lmtp-heat {
    0%, 100% { opacity: var(--o, 0.3); }
    50%      { opacity: calc(var(--o, 0.3) * 0.45); }
  }
  .lmtp-row-new { animation: lmtp-in 0.4s ease-out; }
  @keyframes lmtp-in {
    from { opacity: 0; transform: translateY(-3px); }
    to   { opacity: 1; transform: translateY(0); }
  }
}
`;

// Liquidity heat ladder — deterministic demo intensities (red asks above,
// green bids below the price line).
const HEAT: Array<{ side: "ask" | "bid"; o: number; w: string; label?: string }> = [
  { side: "ask", o: 0.55, w: "82%", label: "68,000 · $38M" },
  { side: "ask", o: 0.3, w: "54%" },
  { side: "ask", o: 0.18, w: "36%" },
  { side: "ask", o: 0.12, w: "22%" },
  { side: "bid", o: 0.14, w: "28%" },
  { side: "bid", o: 0.26, w: "48%" },
  { side: "bid", o: 0.5, w: "74%", label: "67,350 · $26M" },
  { side: "bid", o: 0.34, w: "58%" },
];

const TAPE: Array<{
  t: string; side: "BUY" | "SELL"; sym: string; val: string; impact: "HIGH" | "MED";
}> = [
  { t: "14:32:08", side: "BUY", sym: "BTC", val: "$4.2M", impact: "HIGH" },
  { t: "14:31:42", side: "SELL", sym: "ETH", val: "$1.8M", impact: "MED" },
  { t: "14:30:11", side: "BUY", sym: "BTC", val: "$6.1M", impact: "HIGH" },
  { t: "14:28:55", side: "BUY", sym: "SOL", val: "$940K", impact: "MED" },
];

export function TerminalPreview() {
  const tiltRef = useRef<HTMLDivElement | null>(null);

  const handleMove = (e: React.MouseEvent<HTMLDivElement>) => {
    const el = tiltRef.current;
    if (!el || window.innerWidth < 768) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const r = e.currentTarget.getBoundingClientRect();
    const px = (e.clientX - r.left) / r.width - 0.5;
    const py = (e.clientY - r.top) / r.height - 0.5;
    el.style.transform = `perspective(1300px) rotateX(${(4 - py * 4).toFixed(2)}deg) rotateY(${(px * 5).toFixed(2)}deg)`;
  };
  const handleLeave = () => {
    if (tiltRef.current) tiltRef.current.style.transform = "";
  };

  return (
    <section className="relative px-4 py-12">
      <style dangerouslySetInnerHTML={{ __html: PREVIEW_CSS }} />
      <div className="mx-auto max-w-6xl">
        <div className="mb-5 flex flex-wrap items-end justify-between gap-2">
          <div>
            <span className="lm-section-title">04 · The terminal</span>
            <h2 className="lm-display mt-2 text-xl font-semibold tracking-tight text-lm-text sm:text-2xl">
              This is the instrument itself.
            </h2>
            <p className="mt-1 text-[13px] text-lm-text-dim">
              Liquidity heat, whale tape and the current read, live in one screen.
            </p>
          </div>
          <StatusBadge variant="warning" size="sm">DEMO DATA</StatusBadge>
        </div>

        <div className="relative" onMouseMove={handleMove} onMouseLeave={handleLeave}>
          {/* Halo behind the window */}
          <div aria-hidden className="pointer-events-none absolute -inset-10">
            <div className="absolute left-1/4 top-0 h-48 w-72 rounded-full bg-violet-500/[0.08] blur-3xl" />
            <div className="absolute bottom-0 right-1/4 h-48 w-72 rounded-full bg-cyan-500/[0.07] blur-3xl" />
          </div>

          <div ref={tiltRef} className="lmtp-tilt relative">
            <div className="relative overflow-hidden rounded-xl border border-white/[0.07] bg-[#0b0c12] shadow-[0_30px_80px_-30px_rgba(0,0,0,0.9),inset_0_1px_0_rgba(255,255,255,0.04)]">
              {/* Scan sweep over the whole window */}
              <div
                aria-hidden
                className="lmtp-scan pointer-events-none absolute inset-x-0 top-0 z-10 h-16 bg-gradient-to-b from-transparent via-cyan-400/[0.04] to-transparent"
              />

              {/* Window chrome — mirrors the real TopNav */}
              <div className="flex items-center justify-between gap-3 border-b border-white/[0.06] bg-gradient-to-b from-[#0d0f1a]/95 to-[#0a0b12]/90 px-3.5 py-2">
                <div className="flex items-center gap-2">
                  <span className="flex h-[18px] w-[18px] items-center justify-center rounded border border-violet-400/30 bg-gradient-to-br from-violet-500/[0.25] to-cyan-400/[0.06]">
                    <span className="h-1.5 w-1.5 rounded-sm bg-violet-300/90" />
                  </span>
                  <span className="lm-brand text-[10.5px] tracking-[0.06em] text-lm-text">LUMORA</span>
                  <span className="num hidden text-[7px] uppercase tracking-[0.26em] text-lm-muted sm:inline">Terminal</span>
                </div>
                <div className="num flex items-center gap-2 text-[8.5px] uppercase tracking-wider text-lm-muted">
                  <span className="hidden sm:inline">14:32:08 UTC</span>
                  <span className="flex items-center gap-1 text-emerald-300/90">
                    <span className="lm-live-dot inline-block h-1 w-1 rounded-full bg-emerald-400" />
                    LIVE
                  </span>
                </div>
              </div>

              {/* Body — read | heat | tape */}
              <div className="grid grid-cols-1 gap-px bg-white/[0.04] md:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)_minmax(0,1.2fr)]">
                {/* Current read */}
                <div className="bg-[#0b0c12] p-4">
                  <p className="num text-[8px] uppercase tracking-[0.22em] text-lm-muted">Current read · BTCUSDT</p>
                  <div className="mt-3 flex items-baseline gap-2.5">
                    <span className="lm-price text-3xl leading-none text-emerald-400">LONG</span>
                    <span className="num text-[15px] font-semibold text-lm-text">
                      72<span className="text-[10px] text-lm-muted">/100</span>
                    </span>
                  </div>
                  <p className="mt-3 text-[11px] leading-snug text-lm-text-dim">
                    Bid intensity 58% vs 42%. Buyers leading into a support band that has held twice.
                  </p>
                  <div className="num mt-4 grid grid-cols-3 gap-2 border-t border-white/[0.05] pt-3 text-[8.5px] uppercase tracking-wider text-lm-muted">
                    <span>CONF <span className="block text-[11px] normal-case tracking-normal text-lm-text">68%</span></span>
                    <span>RISK <span className="block text-[11px] normal-case tracking-normal text-amber-400">MED</span></span>
                    <span>OI <span className="block text-[11px] normal-case tracking-normal text-lm-text">+2.4%</span></span>
                  </div>
                </div>

                {/* Liquidity heat ladder */}
                <div className="bg-[#0b0c12] p-4">
                  <p className="num text-[8px] uppercase tracking-[0.22em] text-lm-muted">Liquidity heat</p>
                  <div className="mt-3 space-y-[5px]">
                    {HEAT.map(({ side, o, w, label }, i) => (
                      <div key={i} className="relative flex items-center gap-2">
                        <div
                          className={clsx("lmtp-heat h-[11px] rounded-sm", side === "ask" ? "bg-red-500" : "bg-emerald-500")}
                          style={{ width: w, "--o": o, opacity: o, animationDelay: `${i * 0.55}s` } as React.CSSProperties}
                        />
                        {label && (
                          <span className={clsx("num whitespace-nowrap text-[8px]", side === "ask" ? "text-red-400/80" : "text-emerald-400/80")}>
                            {label}
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                  <div className="num mt-3 flex items-center justify-between border-t border-white/[0.05] pt-2.5 text-[8.5px] uppercase tracking-wider">
                    <span className="text-red-400/70">ASK $50M</span>
                    <span className="text-lm-muted">SPREAD 0.8</span>
                    <span className="text-emerald-400/70">BID $35M</span>
                  </div>
                </div>

                {/* Whale tape */}
                <div className="bg-[#0b0c12] p-4">
                  <p className="num text-[8px] uppercase tracking-[0.22em] text-lm-muted">Whale tape</p>
                  <div className="mt-3 space-y-px">
                    {TAPE.map(({ t, side, sym, val, impact }, i) => (
                      <div
                        key={t}
                        className={clsx(
                          "flex items-center gap-2.5 rounded px-2 py-1.5",
                          i === 0 && "lmtp-row-new bg-white/[0.03] shadow-[inset_1.5px_0_0_rgba(34,211,238,0.6)]",
                        )}
                      >
                        <span className="num w-[52px] shrink-0 text-[8.5px] text-lm-muted">{t}</span>
                        <span className={clsx("num w-8 shrink-0 text-[9px] font-bold", side === "BUY" ? "text-emerald-400" : "text-red-400")}>
                          {side}
                        </span>
                        <span className="num shrink-0 text-[9px] text-lm-text">{sym}</span>
                        <span className="num ml-auto shrink-0 text-[9.5px] text-lm-text-dim">{val}</span>
                        <span className={clsx("num shrink-0 text-[7.5px] uppercase", impact === "HIGH" ? "text-amber-400" : "text-lm-muted")}>
                          {impact}
                        </span>
                      </div>
                    ))}
                  </div>
                  <Link
                    href="/enter"
                    className="num mt-3.5 inline-flex items-center gap-1.5 border-t border-white/[0.05] pt-3 text-[9px] uppercase tracking-[0.18em] text-lm-cyan transition-colors hover:text-cyan-200"
                  >
                    Open full terminal <ArrowRight className="h-3 w-3" />
                  </Link>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
