"use client";

import { Fragment } from "react";
import type { LucideIcon } from "lucide-react";
import { clsx } from "clsx";

// ── IntelligenceDock (LM69C · minimal-dock interaction language) ─────────────
// A restrained dock-style control rail for Lumora instruments: one dark glass
// pill holding small icon controls with a quiet hover halo, a 1px hover lift,
// an active dot and a compact tooltip ABOVE each control. No macOS icons, no
// nav replacement, no framer-motion — CSS transitions only, all motion gated
// with motion-reduce variants.
//
// Tooltip behavior: absolute, floating UPWARD from the control so it never
// drops into the instrument body below, never affects layout. The host panel
// must not clip overflow at its top edge (IntelligenceChartPanel was unclipped
// for this). Hidden under md — on narrow widths the icon + title attribute
// carry the meaning.
//
// Color rules (per LM69 discovery): cyan = live/intelligence, violet =
// selected/brand, emerald = support/long, rose = sell/risk, amber =
// caution/sweep. Alphas stay low so the pill never reads as a casino.

export type DockTone = "cyan" | "violet" | "emerald" | "rose" | "amber";

export interface DockControl {
  id: string;
  /** Tooltip title + accessible name. */
  label: string;
  /** Optional quiet second tooltip line ("price only", "on · demo data"). */
  hint?: string;
  icon: LucideIcon;
  active: boolean;
  tone: DockTone;
  /** Small pulsing badge for a live/new-signal state. */
  badge?: boolean;
  onSelect: () => void;
}

interface ToneClasses {
  activeBg: string;
  activeRing: string;
  activeIcon: string;
  halo: string;
  dot: string;
  tipText: string;
}

const TONES: Record<DockTone, ToneClasses> = {
  cyan: {
    activeBg: "bg-cyan-400/[0.12]",
    activeRing: "shadow-[inset_0_0_0_1px_rgba(34,211,238,0.30)]",
    activeIcon: "text-cyan-300",
    halo: "bg-[radial-gradient(circle,rgba(34,211,238,0.16),transparent_70%)]",
    dot: "bg-cyan-400",
    tipText: "text-cyan-300",
  },
  violet: {
    activeBg: "bg-violet-500/[0.14]",
    activeRing: "shadow-[inset_0_0_0_1px_rgba(139,92,246,0.35)]",
    activeIcon: "text-violet-300",
    halo: "bg-[radial-gradient(circle,rgba(139,92,246,0.16),transparent_70%)]",
    dot: "bg-violet-400",
    tipText: "text-violet-300",
  },
  emerald: {
    activeBg: "bg-emerald-400/[0.10]",
    activeRing: "shadow-[inset_0_0_0_1px_rgba(52,211,153,0.30)]",
    activeIcon: "text-emerald-300",
    halo: "bg-[radial-gradient(circle,rgba(52,211,153,0.15),transparent_70%)]",
    dot: "bg-emerald-400",
    tipText: "text-emerald-300",
  },
  rose: {
    activeBg: "bg-rose-400/[0.10]",
    activeRing: "shadow-[inset_0_0_0_1px_rgba(251,113,133,0.30)]",
    activeIcon: "text-rose-300",
    halo: "bg-[radial-gradient(circle,rgba(251,113,133,0.15),transparent_70%)]",
    dot: "bg-rose-400",
    tipText: "text-rose-300",
  },
  amber: {
    activeBg: "bg-amber-400/[0.10]",
    activeRing: "shadow-[inset_0_0_0_1px_rgba(251,191,36,0.30)]",
    activeIcon: "text-amber-300",
    halo: "bg-[radial-gradient(circle,rgba(251,191,36,0.14),transparent_70%)]",
    dot: "bg-amber-400",
    tipText: "text-amber-300",
  },
};

function DockButton({ label, hint, icon: Icon, active, tone, badge, onSelect }: DockControl) {
  const t = TONES[tone];
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={active}
      aria-label={label}
      title={label}
      className={clsx(
        "group relative flex h-8 w-8 shrink-0 items-center justify-center rounded-full",
        "transition-[transform,background-color] duration-150 ease-out",
        "hover:-translate-y-[1px] active:translate-y-0",
        "motion-reduce:transition-none motion-reduce:hover:translate-y-0",
        "focus-visible:outline focus-visible:outline-1 focus-visible:-outline-offset-1 focus-visible:outline-cyan-400/60",
        active ? clsx(t.activeBg, t.activeRing) : "hover:bg-white/[0.05]",
      )}
    >
      {/* hover halo — soft toned bloom behind the icon */}
      <span
        aria-hidden
        className={clsx(
          "pointer-events-none absolute -inset-1 rounded-full opacity-0 blur-[5px]",
          "transition-opacity duration-200 group-hover:opacity-100 motion-reduce:transition-none",
          t.halo,
        )}
      />
      <Icon
        className={clsx(
          "relative h-3.5 w-3.5 transition-colors duration-150 motion-reduce:transition-none",
          active ? t.activeIcon : "text-lm-muted group-hover:text-lm-text-dim",
        )}
        strokeWidth={2}
      />
      {/* active dot — instrument-style "channel engaged" marker */}
      {active && (
        <span
          aria-hidden
          className={clsx(
            "absolute bottom-[3px] left-1/2 h-[3px] w-[3px] -translate-x-1/2 rounded-full",
            t.dot,
          )}
        />
      )}
      {/* live/new-signal badge */}
      {badge && (
        <span
          aria-hidden
          className="lm-live-dot absolute right-[3px] top-[3px] h-1.5 w-1.5 rounded-full bg-cyan-400 text-cyan-400"
        />
      )}
      {/* compact tooltip — ABOVE the control, floating, never into the chart
          body below. Hidden under md (title attribute covers narrow widths). */}
      <span
        role="presentation"
        className={clsx(
          "pointer-events-none absolute bottom-full left-1/2 z-30 mb-2 hidden -translate-x-1/2 whitespace-nowrap md:block",
          "rounded-md border border-white/[0.08] bg-[#0b0b0e]/95 px-2 py-1 text-center",
          "shadow-[0_6px_20px_-6px_rgba(0,0,0,0.85)] backdrop-blur-sm",
          "translate-y-0.5 opacity-0 transition-[opacity,transform] duration-150 ease-out",
          "group-hover:translate-y-0 group-hover:opacity-100 group-focus-visible:translate-y-0 group-focus-visible:opacity-100",
          "motion-reduce:transition-none motion-reduce:translate-y-0",
        )}
      >
        <span
          className={clsx(
            "num block text-[10px] font-semibold uppercase tracking-[0.14em]",
            active ? t.tipText : "text-lm-text",
          )}
        >
          {label}
        </span>
        {hint && (
          <span className="num block text-[9px] uppercase tracking-wider text-lm-muted">
            {hint}
          </span>
        )}
      </span>
    </button>
  );
}

interface IntelligenceDockProps {
  /** Control groups; a hairline divider renders between groups. */
  groups: DockControl[][];
  className?: string;
}

export function IntelligenceDock({ groups, className }: IntelligenceDockProps) {
  return (
    <div
      className={clsx(
        "inline-flex items-center gap-0.5 rounded-full border border-white/[0.07] bg-[#0e0e12]/85 px-1 py-1 backdrop-blur-md",
        "shadow-[0_4px_16px_-8px_rgba(0,0,0,0.8),inset_0_1px_0_rgba(255,255,255,0.04)]",
        className,
      )}
    >
      {groups.map((group, gi) => (
        <Fragment key={gi}>
          {gi > 0 && <span aria-hidden className="mx-1 h-4 w-px shrink-0 bg-white/[0.08]" />}
          {group.map((c) => (
            <DockButton key={c.id} {...c} />
          ))}
        </Fragment>
      ))}
    </div>
  );
}

export default IntelligenceDock;
