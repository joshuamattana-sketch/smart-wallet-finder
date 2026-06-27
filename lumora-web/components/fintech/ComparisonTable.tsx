import { Check, X } from "lucide-react";

// Every row is defensible from the methodology, no invented competitor claims.
const ROWS: { label: string; meridian: string; typical: string }[] = [
  { label: "Sample size", meridian: "17,000+ scored trades", typical: "A few screenshots" },
  { label: "Trading costs", meridian: "Net of spread", typical: "Gross, or unstated" },
  { label: "Look-ahead", meridian: "None, graded bar by bar", typical: "Curve-fit in hindsight" },
  { label: "Win rate", meridian: "Shown openly", typical: "Hidden" },
  { label: "Your account", meridian: "You place every trade", typical: "Auto-trades your money" },
  { label: "Losing trades", meridian: "Left in the average", typical: "Cropped out" },
];

export function ComparisonTable() {
  return (
    <div className="overflow-hidden rounded-2xl border border-fintech-line-soft bg-white">
      <div className="grid grid-cols-[1.2fr_1fr_1fr] border-b border-fintech-line-soft bg-fintech-mist text-[12.5px] font-medium text-fintech-muted">
        <div className="px-5 py-3.5">What matters</div>
        <div className="px-5 py-3.5 text-fintech-indigo-ink">Meridian</div>
        <div className="px-5 py-3.5">The usual gold bot</div>
      </div>
      {ROWS.map((r, i) => (
        <div
          key={r.label}
          className={`grid grid-cols-[1.2fr_1fr_1fr] items-center text-[13.5px] ${
            i < ROWS.length - 1 ? "border-b border-fintech-line-soft" : ""
          }`}
        >
          <div className="px-5 py-3.5 text-fintech-ink-soft">{r.label}</div>
          <div className="flex items-center gap-2 bg-fintech-indigo-soft/40 px-5 py-3.5 font-medium text-fintech-ink">
            <Check className="h-4 w-4 shrink-0 text-fintech-indigo" aria-hidden="true" />
            <span>{r.meridian}</span>
          </div>
          <div className="flex items-center gap-2 px-5 py-3.5 text-fintech-muted">
            <X className="h-4 w-4 shrink-0 text-fintech-faint" aria-hidden="true" />
            <span>{r.typical}</span>
          </div>
        </div>
      ))}
    </div>
  );
}
