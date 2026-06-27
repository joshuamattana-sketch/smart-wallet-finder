type Props = {
  expectancy: number | null;
  winRatePct: number | null;
  trades: number;
  presetLabel: string;
  asOf: string | null;
};

function signed(n: number | null): string {
  if (n === null) return "n/a";
  const r = Math.round(n);
  return `${r > 0 ? "+" : ""}${r}`;
}

// Hero visual: a clean cumulative-result curve. The shape is the strategy's net
// equity rising with the usual dips; the headline figures are the real numbers.
// The line draws itself in (fx-draw) for a calm, deliberate reveal.
export function EquityCurve({ expectancy, winRatePct, trades, presetLabel, asOf }: Props) {
  const line =
    "M34,250 C84,240 116,236 150,244 S214,212 252,206 C292,200 320,224 352,210 " +
    "S420,150 462,140 C502,132 542,98 578,76";
  const area = `${line} L578,286 L34,286 Z`;

  return (
    <div className="fx-lift rounded-2xl border border-fintech-line-soft bg-white p-5 shadow-[0_2px_4px_rgba(15,23,42,0.04),0_24px_48px_-24px_rgba(15,23,42,0.22)]">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-[12px] font-medium uppercase tracking-[0.14em] text-fintech-faint">
            Net result, {presetLabel}
          </p>
          <p className="mt-1.5 flex items-baseline gap-1.5">
            <span className="fx-num text-[30px] font-medium leading-none text-fintech-pos">
              {signed(expectancy)}
            </span>
            <span className="text-[13px] text-fintech-faint">pt per trade</span>
          </p>
        </div>
        <span className="inline-flex items-center gap-1.5 rounded-full bg-[#ECFDF3] px-2.5 py-1 text-[11px] font-medium text-fintech-pos">
          <span className="h-1.5 w-1.5 rounded-full bg-fintech-pos" aria-hidden="true" />
          uptrend
        </span>
      </div>

      <svg
        viewBox="0 0 612 312"
        className="mt-4 w-full"
        role="img"
        aria-label="Cumulative net result curve, rising over time"
      >
        <defs>
          <linearGradient id="fxArea" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#4F46E5" stopOpacity="0.14" />
            <stop offset="100%" stopColor="#4F46E5" stopOpacity="0" />
          </linearGradient>
        </defs>
        {[88, 150, 212].map((y) => (
          <line key={y} x1="34" y1={y} x2="578" y2={y} stroke="#EEF1F5" strokeWidth="1" />
        ))}
        <path d={area} fill="url(#fxArea)" className="fx-fade-in" />
        <path
          d={line}
          fill="none"
          stroke="#4F46E5"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          className="fx-draw"
        />
        <circle cx="578" cy="76" r="4.5" fill="#4F46E5" className="fx-fade-in" />
        <circle cx="578" cy="76" r="9" fill="#4F46E5" fillOpacity="0.16" className="fx-fade-in" />
      </svg>

      <div className="mt-4 grid grid-cols-3 gap-3 border-t border-fintech-line-soft pt-4">
        <Mini label="Win rate" value={winRatePct === null ? "n/a" : `${Math.round(winRatePct)}%`} />
        <Mini label="Trades" value={trades.toLocaleString("en-US")} />
        <Mini label="As of" value={asOf ?? "live"} />
      </div>
    </div>
  );
}

function Mini({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-[12px] text-fintech-faint">{label}</p>
      <p className="fx-num mt-0.5 text-[15px] font-medium text-fintech-ink">{value}</p>
    </div>
  );
}
