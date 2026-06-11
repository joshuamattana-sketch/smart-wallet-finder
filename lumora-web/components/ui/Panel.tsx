import { clsx } from "clsx";

// ── Surface levels (LM69B) ───────────────────────────────────────────────────
// Border is earned. Three levels only:
//   default — standard bordered surface (back-compat with all call sites)
//   focus   — THE instrument on a page: bordered + recessed inset frame.
//             At most one focus surface per page region.
//   subtle  — supporting content: recessed background, NO border. Most
//             secondary panels should live here so the instrument stands out.
type PanelLevel = "default" | "focus" | "subtle";

const LEVEL_CLASSES: Record<PanelLevel, string> = {
  default: "rounded-lg border border-lm-border bg-lm-surface",
  focus: "rounded-lg border border-lm-border bg-lm-surface lm-chart-frame",
  subtle: "rounded-md bg-lm-surface-muted",
};

interface PanelProps {
  children: React.ReactNode;
  className?: string;
  /** Surface weight — see level notes above. */
  level?: PanelLevel;
  /** Tighter padding (p-2) instead of the default p-3. */
  compact?: boolean;
  /** No internal padding — let the className/children control spacing. */
  flush?: boolean;
  /** Lighten the surface on hover (for interactive panels only). */
  hover?: boolean;
}

export function Panel({
  children,
  className,
  level = "default",
  compact = false,
  flush = false,
  hover = false,
}: PanelProps) {
  return (
    <div
      className={clsx(
        LEVEL_CLASSES[level],
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
