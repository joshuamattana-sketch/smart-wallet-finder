// Grounds the headline numbers in money and honest risk. Hiding the downside
// reads as hiding; showing it plainly is what a burned trader actually trusts.
// All three statements are true of the strategy, not spin.
const ITEMS = [
  {
    label: "In money",
    value: "about $8.50 a trade",
    note: "+85 pt is roughly $8.50 per 0.10 lot on gold, on average. You set the size.",
  },
  {
    label: "Most trades lose",
    value: "around 70% red",
    note: "A few winners, held on time, carry the average. Expect long losing stretches.",
  },
  {
    label: "Worst per trade",
    value: "guarded is capped",
    note: "Guarded exits at its wide stop. The full swing runs until the trade closes.",
  },
];

export function RealityCheck() {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
      {ITEMS.map((it) => (
        <div key={it.label} className="rounded-2xl border border-fintech-line-soft bg-white p-5">
          <p className="text-[12px] font-medium uppercase tracking-[0.1em] text-fintech-faint">
            {it.label}
          </p>
          <p className="fx-num mt-2 text-[18px] font-medium text-fintech-ink">{it.value}</p>
          <p className="mt-2.5 text-[13px] leading-[1.65] text-fintech-ink-soft">{it.note}</p>
        </div>
      ))}
    </div>
  );
}
