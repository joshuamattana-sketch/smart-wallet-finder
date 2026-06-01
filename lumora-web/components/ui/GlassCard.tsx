import { clsx } from "clsx";

interface GlassCardProps {
  children: React.ReactNode;
  className?: string;
  hover?: boolean;
  glow?: "purple" | "cyan" | "none";
}

export function GlassCard({ children, className, hover = true, glow = "none" }: GlassCardProps) {
  return (
    <div
      className={clsx(
        "rounded-xl border border-lumora-border bg-lumora-card shadow-card",
        "bg-gradient-to-br from-[rgba(139,92,246,0.06)] to-[rgba(34,211,238,0.03)]",
        hover && "glass-hover",
        glow === "purple" && "shadow-neon-purple",
        glow === "cyan" && "shadow-neon-cyan",
        className
      )}
    >
      {children}
    </div>
  );
}
