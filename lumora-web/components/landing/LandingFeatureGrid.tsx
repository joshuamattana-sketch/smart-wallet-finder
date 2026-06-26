import { Layers, Zap, Gauge, Crosshair } from "lucide-react";
import { Panel } from "@/components/ui/Panel";
import { clsx } from "clsx";

// ── The pressure map — what Lumora reads ────────────────────────────────────
// Four layers, four cards, each carrying a live mini-diagram of its layer:
// a breathing depth ladder, a whale ping on the tape, a leaning pressure
// gauge, and the read score dial everything condenses into. Animations are
// gated behind prefers-reduced-motion; the static diagrams read fine frozen.

const GRID_CSS = `
.lmd-ring {
  opacity: 0;
  transform-box: fill-box;
  transform-origin: center;
}
@media (prefers-reduced-motion: no-preference) {
  .lmd-bar {
    transform-box: fill-box;
    transform-origin: left center;
    animation: lmd-bar 4.5s ease-in-out infinite;
  }
  .lmd-bar-2 { animation-delay: -2.2s; }
  @keyframes lmd-bar {
    0%, 100% { transform: scaleX(1); }
    50%      { transform: scaleX(1.08); }
  }
  .lmd-ring { animation: lmd-ping 6s ease-out infinite; }
  .lmd-ring-2 { animation-delay: 0.3s; }
  @keyframes lmd-ping {
    0%, 6% { opacity: 0; transform: scale(0.3); }
    10%    { opacity: 0.7; transform: scale(0.6); }
    32%    { opacity: 0; transform: scale(2.6); }
    100%   { opacity: 0; transform: scale(0.3); }
  }
  .lmd-needle {
    transform-box: view-box;
    transform-origin: 100px 50px;
    animation: lmd-needle 6s ease-in-out infinite alternate;
  }
  @keyframes lmd-needle {
    0%   { transform: rotate(-24deg); }
    100% { transform: rotate(20deg); }
  }
  .lmd-read-halo {
    transform-box: fill-box;
    transform-origin: center;
    animation: lmd-halo 2.8s ease-in-out infinite;
  }
  @keyframes lmd-halo {
    0%, 100% { opacity: 0.18; transform: scale(1); }
    50%      { opacity: 0.05; transform: scale(1.55); }
  }
}
`;

const MONO = "'JetBrains Mono', monospace";

function LiquidityDiagram() {
  return (
    <svg viewBox="0 0 200 56" className="h-14 w-full" aria-hidden>
      <line x1="0" y1="28" x2="200" y2="28" stroke="#22d3ee" strokeWidth="1" strokeDasharray="3 4" opacity="0.5" />
      <rect className="lmd-bar" x="0" y="5" width="128" height="5" rx="1" fill="#ef4444" opacity="0.45" />
      <rect x="0" y="13" width="78" height="5" rx="1" fill="#ef4444" opacity="0.28" />
      <rect x="0" y="21" width="44" height="5" rx="1" fill="#ef4444" opacity="0.18" />
      <rect x="0" y="30" width="52" height="5" rx="1" fill="#22c55e" opacity="0.18" />
      <rect x="0" y="38" width="96" height="5" rx="1" fill="#22c55e" opacity="0.28" />
      <rect className="lmd-bar lmd-bar-2" x="0" y="46" width="150" height="5" rx="1" fill="#22c55e" opacity="0.45" />
    </svg>
  );
}

function WhaleDiagram() {
  return (
    <svg viewBox="0 0 200 56" className="h-14 w-full" aria-hidden>
      <line x1="0" y1="40" x2="200" y2="40" stroke="#1e1e22" strokeWidth="1" />
      {[20, 50, 80, 140, 170].map((x) => (
        <circle key={x} cx={x} cy="40" r="1.5" fill="#71717a" opacity="0.5" />
      ))}
      <line x1="110" y1="40" x2="110" y2="16" stroke="#22c55e" strokeWidth="1" opacity="0.4" />
      <circle className="lmd-ring" cx="110" cy="40" r="9" fill="none" stroke="#22c55e" strokeWidth="1.5" />
      <circle className="lmd-ring lmd-ring-2" cx="110" cy="40" r="9" fill="none" stroke="#22c55e" strokeWidth="1" />
      <circle cx="110" cy="40" r="3" fill="#22c55e" />
    </svg>
  );
}

function FuturesDiagram() {
  return (
    <svg viewBox="0 0 200 56" className="h-14 w-full" aria-hidden>
      <defs>
        <linearGradient id="lmdGauge" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="#ef4444" stopOpacity="0.6" />
          <stop offset="50%" stopColor="#f59e0b" stopOpacity="0.6" />
          <stop offset="100%" stopColor="#22c55e" stopOpacity="0.6" />
        </linearGradient>
      </defs>
      <path d="M 32 50 A 68 68 0 0 1 168 50" fill="none" stroke="url(#lmdGauge)" strokeWidth="4" strokeLinecap="round" opacity="0.55" />
      <line className="lmd-needle" x1="100" y1="50" x2="100" y2="20" stroke="#e0e0e4" strokeWidth="1.5" strokeLinecap="round" />
      <circle cx="100" cy="50" r="2.5" fill="#a1a1a6" />
    </svg>
  );
}

function ReadDiagram() {
  return (
    <svg viewBox="0 0 200 56" className="h-14 w-full" aria-hidden>
      <defs>
        <linearGradient id="lmdRead" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="#22d3ee" stopOpacity="0.8" />
          <stop offset="100%" stopColor="#22c55e" stopOpacity="0.8" />
        </linearGradient>
      </defs>
      <text x="10" y="14" fill="#71717a" fontFamily={MONO} fontSize="8" letterSpacing="1.5">SCORE</text>
      <text x="140" y="14" fill="#4ade80" fontFamily={MONO} fontSize="9" fontWeight="700" textAnchor="middle">72</text>
      <line x1="10" y1="30" x2="190" y2="30" stroke="#1e1e22" strokeWidth="4" strokeLinecap="round" />
      <line x1="10" y1="30" x2="140" y2="30" stroke="url(#lmdRead)" strokeWidth="4" strokeLinecap="round" />
      <circle className="lmd-read-halo" cx="140" cy="30" r="8" fill="#22d3ee" opacity="0.15" />
      <circle cx="140" cy="30" r="3" fill="#22d3ee" />
      <text x="10" y="48" fill="#52525b" fontFamily={MONO} fontSize="7">0</text>
      <text x="190" y="48" fill="#52525b" fontFamily={MONO} fontSize="7" textAnchor="end">100</text>
    </svg>
  );
}

const FEATURES = [
  {
    icon: Layers,
    title: "Liquidity pressure",
    desc: "Where size is actually resting. Walls, gaps and demand zones mapped over time, before price gets there.",
    sample: "ASK WALL 68,000 · $38M · HELD 2X",
    sampleClass: "text-red-400/75",
    glow: "bg-red-500/10",
    diagram: LiquidityDiagram,
  },
  {
    icon: Zap,
    title: "Whale impact",
    desc: "Large prints as they hit the tape: side, size and market impact, filtered so only meaningful flow gets through.",
    sample: "SELL $7.1M · BINANCE · IMPACT HIGH",
    sampleClass: "text-red-400/75",
    glow: "bg-cyan-500/10",
    diagram: WhaleDiagram,
  },
  {
    icon: Gauge,
    title: "Futures context",
    desc: "Funding, open interest and liquidations as context: which way aggregate leverage is leaning, and how crowded it is.",
    sample: "FUNDING +0.012% · OI +2.4% · LEAN LONG",
    sampleClass: "text-emerald-400/75",
    glow: "bg-emerald-500/10",
    diagram: FuturesDiagram,
  },
  {
    icon: Crosshair,
    title: "Market read",
    desc: "Everything condenses into one bias, score and risk line, with the reason behind it in plain language.",
    sample: "LONG · 72/100 · RISK MED",
    sampleClass: "text-lm-cyan/80",
    glow: "bg-cyan-500/10",
    diagram: ReadDiagram,
  },
];

export function LandingFeatureGrid() {
  return (
    <section className="px-4 py-9">
      <style dangerouslySetInnerHTML={{ __html: GRID_CSS }} />
      <div className="mx-auto max-w-6xl">
        <div className="mb-4">
          <span className="lm-section-title">02 · The structure</span>
          <h2 className="lm-display mt-2 text-xl font-semibold tracking-tight text-lm-text">
            Four layers of market structure, one readable field.
          </h2>
          <p className="mt-1 text-[13px] text-lm-text-dim">
            Every layer in the field above maps to a live read inside the terminal.
          </p>
        </div>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-4">
          {FEATURES.map(({ icon: Icon, title, desc, sample, sampleClass, glow, diagram: Diagram }, i) => (
            <Panel key={title} flush hover className="group relative overflow-hidden p-4">
              {/* Corner glow that wakes on hover */}
              <div
                aria-hidden
                className={clsx(
                  "pointer-events-none absolute -right-10 -top-10 h-32 w-32 rounded-full opacity-0 blur-2xl transition-opacity duration-300 group-hover:opacity-100",
                  glow,
                )}
              />
              <div className="relative">
                <div className="flex items-center justify-between">
                  <span className="num text-[9px] tracking-[0.2em] text-lm-muted">0{i + 1}</span>
                  <Icon className="h-3.5 w-3.5 text-lm-muted" />
                </div>
                <div className="mt-2">
                  <Diagram />
                </div>
                <h3 className="mt-2 text-[14px] font-semibold text-lm-text">{title}</h3>
                <p className="mt-1 text-[12px] leading-relaxed text-lm-text-dim">{desc}</p>
                <div
                  className={clsx(
                    "num mt-3 border-t border-lm-border/60 pt-2 text-[9px] tracking-wider",
                    sampleClass,
                  )}
                >
                  {sample}
                </div>
              </div>
            </Panel>
          ))}
        </div>
      </div>
    </section>
  );
}
