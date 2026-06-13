// LM95A — Gold Bot section header (presentation only, no logic).
//
// A subtle labeled divider used to give the command room a clear hierarchy:
// OPERATE (actionable) · OBSERVE (read-only telemetry) · LEARN (strategy /
// guardrails) · REPORT (latest review). Pure layout — no hooks, no data, no
// trading logic. Accent colors follow the Lumora language: amber = bot
// identity/action, cyan = intelligence/telemetry, violet = memory/strategy.

import { clsx } from "clsx";

type Accent = "operate" | "observe" | "watch" | "learn" | "report";

const ACCENT: Record<Accent, { dot: string; text: string }> = {
  operate: { dot: "bg-amber-400", text: "text-amber-300/85" },
  observe: { dot: "bg-cyan-400", text: "text-cyan-300/85" },
  watch: { dot: "bg-cyan-400", text: "text-cyan-300/85" },
  learn: { dot: "bg-violet-400", text: "text-violet-300/85" },
  report: { dot: "bg-zinc-400", text: "text-zinc-300/75" },
};

export function GoldBotSectionCard({
  eyebrow,
  accent = "operate",
  hint,
  children,
  className,
}: {
  eyebrow: string;
  accent?: Accent;
  hint?: string;
  children: React.ReactNode;
  className?: string;
}) {
  const a = ACCENT[accent];
  return (
    <section className={clsx("space-y-2", className)} aria-label={eyebrow}>
      <div className="flex items-center gap-2">
        <span className={clsx("h-1.5 w-1.5 shrink-0 rounded-full", a.dot)} aria-hidden />
        <h2 className={clsx("num text-[10px] font-semibold uppercase tracking-[0.22em]", a.text)}>
          {eyebrow}
        </h2>
        {hint ? (
          <span className="num text-[9px] uppercase tracking-wider text-lm-muted/60">{hint}</span>
        ) : null}
        <span
          aria-hidden
          className="ml-1 h-px flex-1 bg-gradient-to-r from-lm-border/60 to-transparent"
        />
      </div>
      {children}
    </section>
  );
}
