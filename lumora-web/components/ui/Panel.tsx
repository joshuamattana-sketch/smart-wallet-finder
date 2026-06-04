import { clsx } from "clsx";

interface PanelProps {
  children: React.ReactNode;
  className?: string;
  /** Tighter padding (p-2) instead of the default p-3. */
  compact?: boolean;
  /** No internal padding — let the className/children control spacing. */
  flush?: boolean;
  /** Lighten the border on hover (for interactive panels only). */
  hover?: boolean;
}

export function Panel({
  children,
  className,
  compact = false,
  flush = false,
  hover = false,
}: PanelProps) {
  return (
    <div
      className={clsx(
        "rounded-lg border border-lm-border bg-lm-surface",
        flush ? "" : compact ? "p-2" : "p-3",
        hover && "lm-panel-hover",
        className,
      )}
    >
      {children}
    </div>
  );
}

interface InlinePanelProps {
  children: React.ReactNode;
  className?: string;
}

export function InlinePanel({ children, className }: InlinePanelProps) {
  return (
    <div className={clsx("rounded-md bg-lm-surface-muted", className)}>
      {children}
    </div>
  );
}
