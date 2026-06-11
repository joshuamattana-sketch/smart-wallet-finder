import { clsx } from "clsx";

// ── Surface levels (LM69B · texture pass LM69C) ──────────────────────────────
// Border is earned. Three levels only:
//   default — standard bordered surface (back-compat with all call sites).
//             A 1px inner top highlight + soft drop kill the flat
//             "cheap border card" feel without reading as glass.
//   focus   — THE instrument on a page: recessed inset frame, deeper outer
//             shadow, and a faint cyan top stripe (the only accent stripe in
//             the system — live energy, not decoration). Max one per region.
//   subtle  — supporting content: recessed background, NO border, whisper of
//             an inner highlight so it still feels machined.
type PanelLevel = "default" | "focus" | "subtle";

const LEVEL_CLASSES: Record<PanelLevel, string> = {
  default:
    "rounded-lg border border-lm-border bg-lm-surface " +
    "shadow-[inset_0_1px_0_rgba(255,255,255,0.025),0_2px_10px_-6px_rgba(0,0,0,0.6)]",
  focus:
    "relative rounded-lg border border-[#26262c] bg-lm-surface " +
    "shadow-[inset_0_0_0_1px_rgba(255,255,255,0.03),inset_0_1px_2px_rgba(0,0,0,0.4),0_10px_30px_-14px_rgba(0,0,0,0.75)]",
  subtle:
    "rounded-md bg-lm-surface-muted shadow-[inset_0_1px_0_rgba(255,255,255,0.015)]",
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
      {level === "focus" && (
        <span
          aria-hidden
          className="pointer-events-none absolute inset-x-2.5 top-0 z-10 h-px bg-gradient-to-r from-transparent via-cyan-400/35 to-transparent"
        />
      )}
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
