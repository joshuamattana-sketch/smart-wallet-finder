import { Check, X } from "lucide-react";

// Plain-language questions a normal person can grasp at a glance. Every row is
// still defensible from the methodology, no invented competitor claims.
const ROWS: { label: string; meridian: string; typical: string }[] = [
  { label: "How much is it tested on?", meridian: "17,000+ real trades", typical: "A few screenshots" },
  { label: "Are trading costs counted?", meridian: "Yes, spread included", typical: "Usually ignored" },
  { label: "Tested without hindsight?", meridian: "Yes, trade by trade", typical: "Tuned to fit old data" },
  { label: "Is the win rate shown?", meridian: "Yes, in full", typical: "Hidden or cropped" },
  { label: "Who places the trades?", meridian: "You do, every time", typical: "The bot, with your money" },
  { label: "Are losing trades counted?", meridian: "Yes, left in", typical: "Quietly removed" },
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
