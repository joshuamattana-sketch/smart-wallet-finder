// An illustrative signal card so a trader can picture exactly what they receive:
// direction, entry, protective stop, and the time-based exit. Clearly labelled as
// a format example, not a live call, so it can never read as a recommendation.
export function SignalChip() {
  const rows = [
    { label: "Direction", value: "Long" },
    { label: "Entry", value: "2,418.40" },
    { label: "Protective stop", value: "2,391.40" },
    { label: "Exit", value: "Time, ~30 bars" },
  ];
  return (
    <div className="rounded-2xl border border-fintech-line-soft bg-white p-5 shadow-[0_2px_4px_rgba(15,23,42,0.04),0_18px_40px_-24px_rgba(15,23,42,0.2)]">
      <div className="flex items-center justify-between">
        <span className="fx-num text-[12px] font-medium uppercase tracking-[0.12em] text-fintech-muted">
          XAUUSD · M15
        </span>
        <span className="rounded-full bg-fintech-mist px-2.5 py-0.5 text-[11px] text-fintech-faint">
          format example
        </span>
      </div>
      <dl className="mt-4 divide-y divide-fintech-line-soft">
        {rows.map((r) => (
          <div key={r.label} className="flex items-center justify-between py-2.5">
            <dt className="text-[13.5px] text-fintech-ink-soft">{r.label}</dt>
            <dd className="fx-num text-[14px] font-medium text-fintech-ink">{r.value}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
