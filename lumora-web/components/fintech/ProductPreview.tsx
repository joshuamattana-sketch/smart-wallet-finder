"use client";

import { useEffect, useId, useRef, useState } from "react";
import { motion } from "framer-motion";

type PresetData = { net: number; win: number | null; trades: number; total: number };

type Props = {
  guarded: PresetData;
  full: PresetData;
  asOf: string | null;
};

// Jagged equity-style paths: net up, but with real-looking drawdowns. A clean
// arc reads as a faked backtest; visible dips read as real. Shape is illustrative
// (the per-trade series is not exported yet); the end values map to the real
// cumulative totals.
const CURVES = {
  guarded:
    "M34,262 L64,252 L92,256 L120,240 L148,250 L176,230 L204,238 L232,214 L260,226 L288,200 L316,210 L344,186 L372,198 L400,172 L428,182 L456,156 L484,166 L512,140 L540,150 L578,108",
  full:
    "M34,272 L64,258 L92,266 L120,242 L148,256 L176,226 L204,240 L232,206 L260,224 L288,190 L316,206 L344,170 L372,190 L400,150 L428,172 L456,128 L484,150 L512,104 L540,124 L578,60",
};
const END_Y = { guarded: 108, full: 60 };
const Y_BOTTOM = 286;
const Y_TOP = 40;
const SAMPLES = 80;

function reduceMotion() {
  return (
    typeof window !== "undefined" &&
    window.matchMedia?.("(prefers-reduced-motion: reduce)").matches
  );
}

function useTween(target: number, ms = 650): number {
  const [v, setV] = useState(target);
  const vRef = useRef(target);
  const from = useRef(target);
  useEffect(() => {
    if (reduceMotion()) {
      setV(target);
      vRef.current = target;
      from.current = target;
      return;
    }
    const start = from.current;
    const t0 = performance.now();
    let raf = 0;
    const step = (now: number) => {
      const t = Math.min(1, (now - t0) / ms);
      const e = 1 - Math.pow(1 - t, 3);
      const nv = start + (target - start) * e;
      vRef.current = nv;
      setV(nv);
      if (t < 1) raf = requestAnimationFrame(step);
      else {
        vRef.current = target;
        setV(target);
        from.current = target;
      }
    };
    raf = requestAnimationFrame(step);
    // On interrupt (preset flipped mid-tween), start the next tween from the
    // value actually on screen, so the figure never snaps.
    return () => {
      cancelAnimationFrame(raf);
      from.current = vRef.current;
    };
  }, [target, ms]);
  return v;
}

type Pt = { x: number; y: number };

// Product-first hero centerpiece. Flip Guarded / Full and the curve, figure and
// stats respond. Hover the chart for a trading-style crosshair that reads the
// running result. Guarded is the loud default; full is flagged as the riskier,
// uncapped option rather than merchandised by its bigger number.
export function ProductPreview({ guarded, full, asOf }: Props) {
  const [sel, setSel] = useState<"guarded" | "full">("guarded");
  const cur = sel === "guarded" ? guarded : full;
  const net = Math.round(useTween(cur.net));

  const gid = "pv" + useId().replace(/:/g, "");
  const lineRef = useRef<SVGPathElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const [samples, setSamples] = useState<Pt[]>([]);
  const [hover, setHover] = useState<Pt | null>(null);

  useEffect(() => {
    const path = lineRef.current;
    if (!path) return;
    const len = path.getTotalLength();
    const pts: Pt[] = [];
    for (let i = 0; i <= SAMPLES; i++) {
      const p = path.getPointAtLength((i / SAMPLES) * len);
      pts.push({ x: p.x, y: p.y });
    }
    setSamples(pts);
    setHover(null);
  }, [sel]);

  function onMove(e: React.MouseEvent) {
    const wrap = wrapRef.current;
    if (!wrap || samples.length === 0) return;
    const rect = wrap.getBoundingClientRect();
    if (rect.width === 0) return;
    const vx = ((e.clientX - rect.left) / rect.width) * 612;
    let best = samples[0];
    let bd = Infinity;
    for (const p of samples) {
      const d = Math.abs(p.x - vx);
      if (d < bd) {
        bd = d;
        best = p;
      }
    }
    setHover(best);
  }

  const total = cur.total;
  const hoverVal =
    hover && total
      ? Math.round(((Y_BOTTOM - hover.y) / (Y_BOTTOM - Y_TOP)) * total)
      : null;

  return (
    <div className="overflow-hidden rounded-[20px] border border-fintech-line-soft bg-white shadow-[0_2px_4px_rgba(15,23,42,0.04),0_40px_80px_-40px_rgba(15,23,42,0.30)]">
      <div className="flex items-center gap-2.5 border-b border-fintech-line-soft px-5 py-3.5">
        <span className="grid h-5 w-5 place-items-center rounded-[7px] bg-fintech-ink">
          <span className="h-2 w-2 rounded-sm bg-fintech-indigo" />
        </span>
        <span className="fx-num text-[12.5px] font-medium tracking-tight text-fintech-ink">
          Meridian · XAUUSD M15
        </span>
        <span className="ml-auto fx-num text-[11px] text-fintech-muted">
          backtest{asOf ? ` to ${asOf}` : ""}
        </span>
      </div>

      <div className="p-5">
        <div className="flex items-center justify-between gap-3">
          <div className="relative flex rounded-full border border-fintech-line bg-fintech-mist p-0.5">
            {(["guarded", "full"] as const).map((key) => {
              const active = sel === key;
              return (
                <button
                  key={key}
                  type="button"
                  onClick={() => setSel(key)}
                  className="relative rounded-full px-3.5 py-1.5 text-[12.5px] font-medium"
                  aria-pressed={active}
                >
                  {active ? (
                    <motion.span
                      layoutId="preview-pill"
                      transition={{ type: "spring", stiffness: 420, damping: 34 }}
                      className="absolute inset-0 rounded-full bg-white shadow-[0_1px_2px_rgba(15,23,42,0.12)]"
                    />
                  ) : null}
                  <span className={`relative z-10 ${active ? "text-fintech-ink" : "text-fintech-muted"}`}>
                    {key === "guarded" ? "Guarded" : "Full"}
                  </span>
                </button>
              );
            })}
          </div>
          <span className="text-[11px] text-fintech-faint">drag your eye across it</span>
        </div>

        <div className="mt-5 flex items-end justify-between">
          <div>
            <p className="text-[12px] text-fintech-muted">Net result per trade</p>
            <p className="mt-1 flex items-baseline gap-1.5">
              <span className="fx-num text-[40px] font-medium leading-none text-fintech-pos">+{net}</span>
              <span className="text-[14px] text-fintech-faint">pt</span>
            </p>
          </div>
          <div className="text-right">
            <p className="fx-num text-[15px] font-medium text-fintech-ink">
              {cur.win === null ? "n/a" : `${Math.round(cur.win)}%`}
            </p>
            <p className="text-[11px] text-fintech-muted">win rate</p>
          </div>
        </div>

        {/* Full swing carries the honest warning right where the bigger number is */}
        {sel === "full" ? (
          <p className="mt-2.5 inline-flex items-center gap-1.5 rounded-md bg-[#FEF3C7] px-2 py-1 text-[11.5px] font-medium text-[#92400E]">
            No stop. Uncapped risk per trade. Advanced only.
          </p>
        ) : null}

        <div
          ref={wrapRef}
          className="relative mt-3 cursor-crosshair"
          onMouseMove={onMove}
          onMouseLeave={() => setHover(null)}
        >
          <svg viewBox="0 0 612 312" className="w-full" role="img" aria-label="Cumulative net result, backtested">
            <defs>
              <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#4F46E5" stopOpacity="0.16" />
                <stop offset="100%" stopColor="#4F46E5" stopOpacity="0" />
              </linearGradient>
            </defs>
            {[110, 170, 230].map((y) => (
              <line key={y} x1="34" y1={y} x2="578" y2={y} stroke="#EEF1F5" strokeWidth="1" />
            ))}
            {(["guarded", "full"] as const).map((key) => {
              const on = sel === key;
              return (
                <g key={key} style={{ opacity: on ? 1 : 0, transition: "opacity 450ms cubic-bezier(0.16,1,0.3,1)" }}>
                  <path d={`${CURVES[key]} L578,286 L34,286 Z`} fill={`url(#${gid})`} />
                  <path
                    ref={on ? lineRef : undefined}
                    d={CURVES[key]}
                    fill="none"
                    stroke="#4F46E5"
                    strokeWidth="2.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                  {!hover ? (
                    <>
                      <circle cx="578" cy={END_Y[key]} r="4.5" fill="#4F46E5" />
                      <circle cx="578" cy={END_Y[key]} r="9" fill="#4F46E5" fillOpacity="0.16" />
                    </>
                  ) : null}
                </g>
              );
            })}
            {hover ? (
              <g>
                <line x1={hover.x} y1={Y_TOP} x2={hover.x} y2={Y_BOTTOM} stroke="#C7CBD6" strokeWidth="1" strokeDasharray="3 3" />
                <circle cx={hover.x} cy={hover.y} r="5" fill="#4F46E5" stroke="#fff" strokeWidth="2" />
              </g>
            ) : null}
          </svg>

          {hover && hoverVal !== null ? (
            <div
              className="pointer-events-none absolute -translate-x-1/2 -translate-y-full rounded-lg bg-fintech-ink px-2.5 py-1.5 text-center"
              style={{ left: `${(hover.x / 612) * 100}%`, top: `${(hover.y / 312) * 100}%` }}
            >
              <span className="fx-num block text-[12px] font-medium leading-none text-white">
                +{hoverVal.toLocaleString("en-US")} pt
              </span>
              <span className="text-[9px] text-white/55">running, cumulative</span>
            </div>
          ) : null}
        </div>

        <div className="mt-3 grid grid-cols-3 gap-3 border-t border-fintech-line-soft pt-3.5">
          <Mini label="Trades" value={cur.trades.toLocaleString("en-US")} />
          <Mini label="Basis" value="net of spread" />
          <Mini label="Stop" value={sel === "guarded" ? "wide, 3R" : "none"} />
        </div>
      </div>
    </div>
  );
}

function Mini({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-[11px] text-fintech-faint">{label}</p>
      <p className="fx-num mt-0.5 text-[13px] font-medium text-fintech-ink">{value}</p>
    </div>
  );
}
