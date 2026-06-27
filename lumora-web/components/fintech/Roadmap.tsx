import { Check } from "lucide-react";

type Phase = {
  label: string;
  when: string;
  tone: "live" | "building" | "planned";
  items: string[];
};

// Honest roadmap: only the "Now" column is live. Copy trading, mobile and more
// instruments are clearly marked as planned, so the excitement is real without
// claiming anything that does not exist yet.
const PHASES: Phase[] = [
  {
    label: "Ready today",
    when: "Now",
    tone: "live",
    items: [
      "The validated strategy and its presets",
      "Guarded and full swing exits",
      "The full backtested track record",
      "No look-ahead, net-of-spread grading",
    ],
  },
  {
    label: "In build",
    when: "Next",
    tone: "building",
    items: [
      "Instant alerts on Discord, Telegram and email",
      "A members dashboard for the live record",
      "Per-signal performance history",
    ],
  },
  {
    label: "On the roadmap",
    when: "Later",
    tone: "planned",
    items: [
      "Opt-in copy trading at your own broker",
      "Mobile app with push alerts",
      "More instruments beyond gold",
      "Additional strategy variants",
    ],
  },
];

const TONE: Record<Phase["tone"], { dot: string; chip: string }> = {
  live: { dot: "bg-fintech-pos", chip: "bg-[#ECFDF3] text-fintech-pos" },
  building: { dot: "bg-fintech-indigo", chip: "bg-fintech-indigo-soft text-fintech-indigo-ink" },
  planned: { dot: "bg-fintech-faint", chip: "bg-fintech-mist text-fintech-muted" },
};

export function Roadmap() {
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
      {PHASES.map((p) => {
        const tone = TONE[p.tone];
        return (
          <div key={p.label} className="rounded-2xl border border-fintech-line-soft bg-white p-6">
            <div className="flex items-center gap-2">
              <span className={`h-2 w-2 rounded-full ${tone.dot} ${p.tone === "live" ? "fx-pulse" : ""}`} aria-hidden="true" />
              <span className={`rounded-full px-2.5 py-0.5 text-[11px] font-medium ${tone.chip}`}>
                {p.when}
              </span>
            </div>
            <h3 className="mt-3 text-[16px] font-medium text-fintech-ink">{p.label}</h3>
            <ul className="mt-4 space-y-3">
              {p.items.map((it) => (
                <li key={it} className="flex items-start gap-2.5 text-[13.5px] leading-snug text-fintech-ink-soft">
                  <Check
                    className={`mt-0.5 h-4 w-4 shrink-0 ${p.tone === "planned" ? "text-fintech-faint" : "text-fintech-indigo"}`}
                    aria-hidden="true"
                  />
                  <span>{it}</span>
                </li>
              ))}
            </ul>
          </div>
        );
      })}
    </div>
  );
}
