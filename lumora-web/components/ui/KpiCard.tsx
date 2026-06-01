import { GlassCard } from "./GlassCard";
import { clsx } from "clsx";

interface KpiCardProps {
  label: string;
  value: string;
  change: string;
  positive?: boolean | null;
}

export function KpiCard({ label, value, change, positive }: KpiCardProps) {
  return (
    <GlassCard className="p-4">
      <p className="text-xs font-medium uppercase tracking-widest text-lumora-muted mb-2">{label}</p>
      <p className="num text-2xl font-semibold text-lumora-text mb-1">{value}</p>
      <p
        className={clsx(
          "text-xs num",
          positive === true && "text-lumora-green",
          positive === false && "text-lumora-red",
          positive === null && "text-lumora-text-dim"
        )}
      >
        {change}
      </p>
    </GlassCard>
  );
}
