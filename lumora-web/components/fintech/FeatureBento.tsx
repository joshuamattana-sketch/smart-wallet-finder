import {
  Target,
  SlidersHorizontal,
  ShieldCheck,
  LineChart,
  Bell,
  Hand,
  type LucideIcon,
} from "lucide-react";

type Tile = {
  icon: LucideIcon;
  title: string;
  desc: string;
  status?: "coming";
  wide?: boolean;
};

const TILES: Tile[] = [
  {
    icon: Target,
    title: "One validated edge on gold",
    desc: "A single rules-based strategy on XAUUSD, held on time. Not ten noisy indicators, one thing that works, run with discipline.",
    wide: true,
  },
  {
    icon: SlidersHorizontal,
    title: "Two exit presets",
    desc: "Run it guarded for bounded risk, or full for the higher average. Your call, same entries.",
  },
  {
    icon: ShieldCheck,
    title: "Graded honestly",
    desc: "No look-ahead, net of spread, losing trades left in. The method is the proof.",
  },
  {
    icon: LineChart,
    title: "A live track record",
    desc: "The numbers keep updating as trades close. You watch the edge, you do not take it on faith.",
  },
  {
    icon: Hand,
    title: "You stay in control",
    desc: "Signals only. You place every trade at your own broker. We never touch your account.",
  },
  {
    icon: Bell,
    title: "Instant alerts",
    desc: "Get each signal the moment it fires, on the channel you already use.",
    status: "coming",
  },
];

export function FeatureBento() {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {TILES.map((t) => {
        const Icon = t.icon;
        return (
          <div
            key={t.title}
            className={`fx-lift relative rounded-2xl border border-fintech-line-soft bg-white p-6 hover:shadow-[0_14px_34px_-20px_rgba(15,23,42,0.32)] ${
              t.wide ? "sm:col-span-2" : ""
            }`}
          >
            {t.status === "coming" ? (
              <span className="absolute right-5 top-5 rounded-full bg-fintech-mist px-2.5 py-0.5 text-[11px] font-medium text-fintech-muted">
                Coming soon
              </span>
            ) : null}
            <span className="grid h-10 w-10 place-items-center rounded-xl bg-fintech-indigo-soft text-fintech-indigo">
              <Icon className="h-5 w-5" aria-hidden="true" />
            </span>
            <h3 className={`mt-4 font-medium text-fintech-ink ${t.wide ? "text-[18px]" : "text-[15px]"}`}>
              {t.title}
            </h3>
            <p className="mt-2 text-[13.5px] leading-[1.7] text-fintech-ink-soft">{t.desc}</p>
          </div>
        );
      })}
    </div>
  );
}
