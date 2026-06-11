import { clsx } from "clsx";

// ── StatusBadge (LM69B baseline) ─────────────────────────────────────────────
// Semantic chips, standardized app-wide:
//   data state  → live / stale / demo / error
//   direction   → bid / ask (and dense LONG/SHORT rows)
//   risk        → live(green) / warning(amber) / error(red) via call sites
//   neutral     → counts, metadata
//
// Color rules: amber means RISK or STALENESS only. Demo/mock/source labels
// are gray (`demo`), never amber — demo data must not scream like risk.
// Rendering: mono, uppercase, compact. Max ~2 chips per surface by
// convention; if a surface needs more, the extras belong in a disclosure.

type StatusVariant =
  | "live"
  | "stale"
  | "error"
  | "neutral"
  | "demo"
  | "bid"
  | "ask"
  | "warning";
type StatusSize = "sm" | "md";

// Each variant carries a faint matching border so chips read as crisp
// hardware indicators instead of soft color blobs. Alpha stays ≤25% so the
// page never turns into badge soup.
const styles: Record<StatusVariant, { bg: string; text: string; dot: string; border?: string }> = {
  live:    { bg: "bg-emerald-500/10", text: "text-emerald-400", dot: "bg-emerald-400", border: "border-emerald-500/25" },
  stale:   { bg: "bg-amber-500/10",   text: "text-amber-400",   dot: "bg-amber-400",   border: "border-amber-500/25" },
  error:   { bg: "bg-red-500/10",     text: "text-red-400",     dot: "bg-red-400",     border: "border-red-500/25" },
  warning: { bg: "bg-amber-500/10",   text: "text-amber-400",   dot: "bg-amber-400",   border: "border-amber-500/25" },
  bid:     { bg: "bg-emerald-500/10", text: "text-emerald-400", dot: "bg-emerald-400", border: "border-emerald-500/25" },
  ask:     { bg: "bg-red-500/10",     text: "text-red-400",     dot: "bg-red-400",     border: "border-red-500/25" },
  neutral: { bg: "bg-zinc-500/10",    text: "text-zinc-400",    dot: "bg-zinc-400",    border: "border-zinc-700/50" },
  demo:    { bg: "bg-zinc-500/10",    text: "text-zinc-400",    dot: "bg-zinc-400",    border: "border-zinc-700/50" },
};

const sizes: Record<StatusSize, string> = {
  sm: "text-[10px] px-1.5 py-px gap-1",
  md: "text-[10.5px] px-2 py-0.5 gap-1.5",
};

interface StatusBadgeProps {
  children: React.ReactNode;
  variant?: StatusVariant;
  size?: StatusSize;
  className?: string;
  dot?: boolean;
}

export function StatusBadge({
  children,
  variant = "neutral",
  size = "md",
  className,
  dot = false,
}: StatusBadgeProps) {
  const s = styles[variant];
  return (
    <span
      className={clsx(
        "num inline-flex items-center rounded border font-medium uppercase tracking-wider",
        sizes[size],
        s.bg,
        s.text,
        s.border ?? "border-transparent",
        className,
      )}
    >
      {dot && (
        <span
          className={clsx(
            "inline-block h-1.5 w-1.5 shrink-0 rounded-full",
            s.dot,
            variant === "live" && "lm-live-dot",
          )}
        />
      )}
      {children}
    </span>
  );
}
