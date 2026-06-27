import type { PresetRecord } from "@/lib/gold-bot-signals";

type Props = {
  preset: PresetRecord;
  featured?: boolean;
  badge?: string;
  blurb?: string;
};

function fmtSigned(n: number | null): string {
  if (n === null) return "n/a";
  const r = Math.round(n);
  return `${r > 0 ? "+" : ""}${r}`;
}

// One preset's track-record card. Expectancy is the headline figure (mono,
// colored by sign). The featured pick gets a 2px indigo ring and a badge.
export function PresetCard({ preset, featured = false, badge, blurb }: Props) {
  const expTone = preset.isPositive ? "text-fintech-pos" : "text-fintech-neg";
  const copy = blurb ?? preset.description;
  return (
    <div
      className={`fx-lift relative rounded-2xl bg-white p-5 ${
        featured
          ? "border-2 border-fintech-indigo shadow-[0_12px_32px_-16px_rgba(79,70,229,0.45)]"
          : "border border-fintech-line-soft hover:shadow-[0_12px_30px_-18px_rgba(15,23,42,0.3)]"
      }`}
    >
      {badge ? (
        <span className="absolute -top-2.5 left-5 rounded-full bg-fintech-indigo px-2.5 py-0.5 text-[11px] font-medium text-white shadow-[0_4px_12px_-4px_rgba(79,70,229,0.6)]">
          {badge}
        </span>
      ) : null}

      <div className="flex items-baseline justify-between">
        <h3 className="text-[15px] font-medium text-fintech-ink">{preset.label}</h3>
        <span className="fx-num text-[12px] text-fintech-faint">
          {preset.trades.toLocaleString("en-US")}
        </span>
      </div>

      <div className="mt-3 flex items-baseline gap-1.5">
        <span className={`fx-num text-[30px] font-medium leading-none ${expTone}`}>
          {fmtSigned(preset.expectancyPoints)}
        </span>
        <span className="text-[13px] text-fintech-faint">pt / trade</span>
      </div>

      <div className="fx-num mt-1.5 text-[12.5px] text-fintech-muted">
        {preset.winRatePct === null ? "n/a" : `${Math.round(preset.winRatePct)}% win`}
      </div>

      {copy ? (
        <p className="mt-4 border-t border-fintech-line-soft pt-3.5 text-[13.5px] leading-relaxed text-fintech-ink-soft">
          {copy}
        </p>
      ) : null}
    </div>
  );
}
