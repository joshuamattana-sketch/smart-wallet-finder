type Tone = "default" | "pos" | "neg";

type Props = {
  label: string;
  value: string;
  sub?: string;
  tone?: Tone;
};

const valueTone: Record<Tone, string> = {
  default: "text-fintech-ink",
  pos: "text-fintech-pos",
  neg: "text-fintech-neg",
};

// Light metric card for the proof strip. Mono figure (financial-credibility
// cue), hairline border, soft shadow, gentle lift on hover.
export function StatCard({ label, value, sub, tone = "default" }: Props) {
  return (
    <div className="fx-lift rounded-2xl border border-fintech-line-soft bg-white p-5 shadow-[0_1px_2px_rgba(15,23,42,0.04)] hover:shadow-[0_10px_28px_-16px_rgba(15,23,42,0.28)]">
      <p className="text-[12.5px] text-fintech-muted">{label}</p>
      <p className={`fx-num mt-2 text-[27px] font-medium leading-none ${valueTone[tone]}`}>
        {value}
      </p>
      {sub ? <p className="mt-2 text-[12.5px] text-fintech-muted">{sub}</p> : null}
    </div>
  );
}
