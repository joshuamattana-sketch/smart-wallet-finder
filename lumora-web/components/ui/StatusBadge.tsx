import { clsx } from "clsx";

type StatusVariant = "live" | "stale" | "error" | "neutral" | "bid" | "ask" | "warning";
type StatusSize = "sm" | "md";

interface StatusBadgeProps {
  children: React.ReactNode;
  variant?: StatusVariant;
  size?: StatusSize;
  className?: string;
  dot?: boolean;
}

const styles: Record<StatusVariant, { bg: string; text: string; dot: string }> = {
  live:    { bg: "bg-emerald-500/10", text: "text-emerald-400", dot: "bg-emerald-400" },
  stale:   { bg: "bg-amber-500/10",   text: "text-amber-400",   dot: "bg-amber-400" },
  error:   { bg: "bg-red-500/10",     text: "text-red-400",     dot: "bg-red-400" },
  warning: { bg: "bg-yellow-500/10",  text: "text-yellow-400",  dot: "bg-yellow-400" },
  bid:     { bg: "bg-emerald-500/10", text: "text-emerald-400", dot: "bg-emerald-400" },
  ask:     { bg: "bg-red-500/10",     text: "text-red-400",     dot: "bg-red-400" },
  neutral: { bg: "bg-zinc-500/10",    text: "text-zinc-400",    dot: "bg-zinc-400" },
};

const sizes: Record<StatusSize, string> = {
  sm: "text-[9px] px-1 py-0 gap-1",
  md: "text-[11px] px-2 py-0.5 gap-1.5",
};

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
        "inline-flex items-center rounded font-medium tracking-wide border",
        sizes[size],
        s.bg,
        s.text,
        variant === "neutral" ? "border-zinc-700/50" : "border-transparent",
        className,
      )}
    >
      {dot && (
        <span
          className={clsx(
            "inline-block h-1.5 w-1.5 rounded-full shrink-0",
            s.dot,
            variant === "live" && "animate-pulse",
          )}
        />
      )}
      {children}
    </span>
  );
}
