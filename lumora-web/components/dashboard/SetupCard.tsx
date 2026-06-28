import { clsx } from "clsx";

// LM81A — Setup card. The dashboard's "what to watch" used to be thin one-line
// rows; this turns each setup into a present, scannable card: a score ring, the
// thesis tags the data already carried (but the old rows hid), the full reason,
// and a level ladder that places entry between target and invalidation so the
// risk/reward reads at a glance.

export type Setup = {
  symbol: string;
  bias: string; // LONG | SHORT | NEUTRAL
  confidence: number;
  entry: string;
  target: string;
  stop: string;
  reason: string;
  tags: string[];
};

type Accent = {
  text: string;
  ring: string;
  glow: string;
  chip: string;
  edge: string;
};

const ACCENTS: Record<string, Accent> = {
  LONG: {
    text: "text-emerald-400",
    ring: "stroke-emerald-400",
    glow: "from-emerald-400/[0.10]",
    chip: "border-emerald-400/25 bg-emerald-400/[0.06] text-emerald-200/90",
    edge: "bg-emerald-400/70 shadow-[0_0_10px_rgba(52,211,153,0.5)]",
  },
  SHORT: {
    text: "text-rose-400",
    ring: "stroke-rose-400",
    glow: "from-rose-400/[0.10]",
    chip: "border-rose-400/25 bg-rose-400/[0.06] text-rose-200/90",
    edge: "bg-rose-400/70 shadow-[0_0_10px_rgba(251,113,133,0.5)]",
  },
  NEUTRAL: {
    text: "text-lm-cyan",
    ring: "stroke-cyan-400",
    glow: "from-cyan-400/[0.08]",
    chip: "border-cyan-400/20 bg-cyan-400/[0.05] text-cyan-200/80",
    edge: "bg-zinc-500/60",
  },
};

// Strip thousands separators so "67,100" → 67100. Returns null for "—" etc.
function num(v: string): number | null {
  const n = parseFloat(v.replace(/[, ]/g, ""));
  return Number.isFinite(n) ? n : null;
}

// Score ring — circular confidence gauge with the number in the centre.
function ScoreRing({ value, ringClass }: { value: number; ringClass: string }) {
  const r = 18;
  const c = 2 * Math.PI * r;
  const pct = Math.max(0, Math.min(100, value));
  return (
    <div className="relative h-12 w-12 shrink-0">
      <svg viewBox="0 0 44 44" className="h-12 w-12 -rotate-90">
        <circle cx="22" cy="22" r={r} className="fill-none stroke-white/[0.06]" strokeWidth="3" />
        <circle
          cx="22"
          cy="22"
          r={r}
          className={clsx("fill-none transition-[stroke-dashoffset] duration-700", ringClass)}
          strokeWidth="3"
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={c * (1 - pct / 100)}
        />
      </svg>
      <span className="num absolute inset-0 flex items-center justify-center text-[13px] font-semibold text-lm-text">
        {value}
      </span>
    </div>
  );
}

// Level ladder — invalidation (red) ── entry marker ── target (green), with the
// entry placed proportionally so the distance to each side is visible.
function LevelLadder({ setup, accent }: { setup: Setup; accent: Accent }) {
  const entry = num(setup.entry);
  const target = num(setup.target);
  const stop = num(setup.stop);

  if (entry === null || target === null || stop === null) {
    return (
      <p className="num text-[10.5px] uppercase tracking-wider text-lm-muted">
        No active levels · monitor
      </p>
    );
  }

  const span = Math.abs(target - stop) || 1;
  const pos = Math.max(6, Math.min(94, (Math.abs(entry - stop) / span) * 100));
  const risk = Math.abs(entry - stop);
  const reward = Math.abs(target - entry);
  const rr = risk > 0 ? reward / risk : 0;

  return (
    <div className="space-y-1.5">
      <div className="relative h-1.5 rounded-full bg-gradient-to-r from-rose-500/30 via-white/[0.06] to-emerald-500/30">
        <span
          className="absolute top-1/2 h-3 w-[3px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-lm-text shadow-[0_0_6px_rgba(255,255,255,0.5)]"
          style={{ left: `${pos}%` }}
        />
      </div>
      <div className="num flex items-center justify-between text-[10px]">
        <span className="text-rose-400/90">{setup.stop}</span>
        <span className="text-lm-text-dim">
          entry <span className="text-lm-text">{setup.entry}</span>
          <span className="mx-1 text-lm-border">·</span>
          <span className={accent.text}>1:{rr.toFixed(1)}</span>
        </span>
        <span className="text-emerald-400/90">{setup.target}</span>
      </div>
    </div>
  );
}

export function SetupCard({ setup }: { setup: Setup }) {
  const accent = ACCENTS[setup.bias] ?? ACCENTS.NEUTRAL;

  return (
    <div
      className={clsx(
        "group relative overflow-hidden rounded-xl border border-white/[0.06] bg-lm-surface/40 p-3.5",
        "shadow-[0_8px_24px_-16px_rgba(0,0,0,0.8)] transition-all duration-200",
        "hover:border-white/[0.10] hover:bg-lm-surface/60 hover:shadow-[0_10px_30px_-14px_rgba(0,0,0,0.9)]",
      )}
    >
      {/* Bias-tinted corner glow + left edge */}
      <span
        aria-hidden
        className={clsx(
          "pointer-events-none absolute -left-10 -top-10 h-24 w-24 rounded-full bg-gradient-to-br to-transparent blur-2xl",
          accent.glow,
        )}
      />
      <span aria-hidden className={clsx("absolute inset-y-2.5 left-0 w-[3px] rounded-full", accent.edge)} />

      {/* Header: symbol + bias · score ring */}
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="num text-[16px] font-semibold leading-none tracking-wide text-lm-text">
            {setup.symbol}
          </p>
          <p className={clsx("num mt-1 text-[11px] font-semibold uppercase tracking-wider", accent.text)}>
            {setup.bias}
          </p>
        </div>
        <ScoreRing value={setup.confidence} ringClass={accent.ring} />
      </div>

      {/* Thesis tags */}
      {setup.tags.length > 0 && (
        <div className="mt-2.5 flex flex-wrap gap-1.5">
          {setup.tags.map((t) => (
            <span
              key={t}
              className={clsx(
                "num rounded-md border px-1.5 py-0.5 text-[9.5px] uppercase tracking-wide",
                accent.chip,
              )}
            >
              {t}
            </span>
          ))}
        </div>
      )}

      {/* Reason — full, not truncated */}
      <p className="mt-2.5 text-[11.5px] leading-relaxed text-lm-text-dim">{setup.reason}</p>

      {/* Level ladder */}
      <div className="mt-3 border-t border-lm-border/40 pt-3">
        <LevelLadder setup={setup} accent={accent} />
      </div>
    </div>
  );
}
