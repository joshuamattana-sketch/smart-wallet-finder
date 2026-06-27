"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { BOT_BRAND } from "@/lib/bot-brand";

type Active = "terminal" | "signals";
type Variant = "light" | "dark";

const SEGMENTS = [
  { key: "terminal" as const, label: "Terminal", href: BOT_BRAND.terminalSwitchHref },
  { key: "signals" as const, label: "Signals", href: BOT_BRAND.signalsHref },
];

const STYLES: Record<Variant, { container: string; pill: string; on: string; off: string }> = {
  light: {
    container: "border-fintech-line bg-white",
    pill: "bg-fintech-ink",
    on: "text-white",
    off: "text-fintech-muted hover:text-fintech-ink",
  },
  dark: {
    container: "border-[#2a2a30] bg-[#141416]",
    pill: "bg-[rgba(139,92,246,0.22)] ring-1 ring-[rgba(139,92,246,0.5)]",
    on: "text-white",
    off: "text-lm-text-dim hover:text-lm-text",
  },
};

// Two-segment product switch. A spring-animated pill settles under the active
// segment, and the whole control slides in on mount, so crossing between the two
// brands reads as one deliberate motion in either direction.
export function ProductSwitch({
  active,
  variant = "light",
}: {
  active: Active;
  variant?: Variant;
}) {
  const s = STYLES[variant];
  return (
    <div className={`relative flex items-center rounded-full border p-0.5 ${s.container}`}>
      {SEGMENTS.map((seg) => {
        const isActive = seg.key === active;
        return (
          <Link
            key={seg.key}
            href={seg.href}
            aria-current={isActive ? "page" : undefined}
            className="relative rounded-full px-3.5 py-1.5 text-xs font-medium"
          >
            {isActive ? (
              <motion.span
                layoutId={`fx-switch-pill-${variant}`}
                initial={{ opacity: 0, scale: 0.85 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ type: "spring", stiffness: 420, damping: 34 }}
                className={`absolute inset-0 rounded-full ${s.pill}`}
              />
            ) : null}
            <span className={`relative z-10 transition-colors ${isActive ? s.on : s.off}`}>
              {seg.label}
            </span>
          </Link>
        );
      })}
    </div>
  );
}
