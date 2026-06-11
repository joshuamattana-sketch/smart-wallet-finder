import { clsx } from "clsx";
import { Panel } from "@/components/ui/Panel";

// ── MetricStrip (LM69B) ──────────────────────────────────────────────────────
// The one KPI strip: divided cells with a micro label, a mono value and an
// optional sub line. Replaces the hand-rolled strips on Terminal, Whale
// Alerts, Paper Trading and the Liquidity Map summary cards.
//
// `valueClassName` fully replaces the default value styling (size + color),
// so a cell can be promoted (e.g. "text-2xl text-lm-cyan") without class
// conflicts.

export interface Metric {
  label: string;
  value: React.ReactNode;
  sub?: React.ReactNode;
  /** Replaces the default value classes (size + tone). */
  valueClassName?: string;
}

const COLS: Record<number, string> = {
  3: "grid-cols-2 sm:grid-cols-3",
  4: "grid-cols-2 sm:grid-cols-4",
  5: "grid-cols-2 sm:grid-cols-3 lg:grid-cols-5",
  6: "grid-cols-2 sm:grid-cols-3 lg:grid-cols-6",
};

interface MetricStripProps {
  metrics: Metric[];
  /** Column count at desktop width (3–6). Defaults to metric count, capped. */
  columns?: 3 | 4 | 5 | 6;
  /** lg = hero numbers (2xl), md = standard (lg). */
  size?: "md" | "lg";
  className?: string;
}

export function MetricStrip({
  metrics,
  columns,
  size = "md",
  className,
}: MetricStripProps) {
  const cols = COLS[columns ?? (Math.min(6, Math.max(3, metrics.length)) as 3 | 4 | 5 | 6)];
  const defaultValue = size === "lg" ? "text-2xl text-lm-text" : "text-lg text-lm-text";

  return (
    <Panel
      flush
      className={clsx("grid divide-x divide-lm-border/50 overflow-hidden", cols, className)}
    >
      {metrics.map((m) => (
        <div key={m.label} className="min-w-0 px-3.5 py-3">
          <p className="num text-[10px] uppercase tracking-[0.16em] text-lm-muted">{m.label}</p>
          <p className={clsx("lm-price mt-1 leading-none", m.valueClassName ?? defaultValue)}>
            {m.value}
          </p>
          {m.sub ? (
            <p className="num mt-1 text-[10px] leading-tight text-lm-muted">{m.sub}</p>
          ) : null}
        </div>
      ))}
    </Panel>
  );
}
