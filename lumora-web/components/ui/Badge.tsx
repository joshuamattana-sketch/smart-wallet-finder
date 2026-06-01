import { clsx } from "clsx";

type BadgeVariant = "purple" | "cyan" | "green" | "red" | "yellow" | "muted";

interface BadgeProps {
  children: React.ReactNode;
  variant?: BadgeVariant;
  className?: string;
}

const variantStyles: Record<BadgeVariant, string> = {
  purple: "bg-purple-500/15 text-purple-300 border border-purple-500/30",
  cyan: "bg-cyan-500/15 text-cyan-300 border border-cyan-500/30",
  green: "bg-green-500/15 text-green-400 border border-green-500/30",
  red: "bg-red-500/15 text-red-400 border border-red-500/30",
  yellow: "bg-yellow-500/15 text-yellow-400 border border-yellow-500/30",
  muted: "bg-lumora-border/50 text-lumora-muted border border-lumora-border",
};

export function Badge({ children, variant = "muted", className }: BadgeProps) {
  return (
    <span className={clsx("inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium tracking-wide", variantStyles[variant], className)}>
      {children}
    </span>
  );
}
