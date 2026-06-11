"use client";

import { motion, useReducedMotion, type Variants } from "framer-motion";
import { clsx } from "clsx";

// ── TextEffect ───────────────────────────────────────────────────────────────
// Reusable staggered text animation (adapted from the motion-primitives
// TextEffect idea, simplified for Lumora). Splits a string per word or per
// character and animates each segment through enter/exit variants — designed
// to sit inside an AnimatePresence so rotating copy gets a clean handoff.
//
// Reduced motion renders the plain string with no animation. Segments are
// aria-hidden behind a single aria-label, so screen readers hear one word,
// not a stream of letters.

type Per = "word" | "char";
type Preset = "blur-scan" | "fade";

const PRESETS: Record<Preset, { container: Variants; item: Variants }> = {
  // Characters resolve out of a blur, left to right — like a scanner locking
  // onto hidden structure. The exit dissolves upward, slightly faster.
  "blur-scan": {
    container: {
      hidden: {},
      visible: { transition: { staggerChildren: 0.04 } },
      exit: { transition: { staggerChildren: 0.015 } },
    },
    item: {
      hidden: { opacity: 0, y: 8, filter: "blur(10px)" },
      visible: {
        opacity: 1,
        y: 0,
        filter: "blur(0px)",
        transition: { duration: 0.35, ease: "easeOut" },
      },
      exit: {
        opacity: 0,
        y: -6,
        filter: "blur(8px)",
        transition: { duration: 0.18, ease: "easeIn" },
      },
    },
  },
  fade: {
    container: {
      hidden: {},
      visible: { transition: { staggerChildren: 0.03 } },
      exit: { transition: { staggerChildren: 0.015 } },
    },
    item: {
      hidden: { opacity: 0 },
      visible: { opacity: 1, transition: { duration: 0.3, ease: "easeOut" } },
      exit: { opacity: 0, transition: { duration: 0.15, ease: "easeIn" } },
    },
  },
};

interface TextEffectProps {
  /** The text to animate. Plain string only. */
  children: string;
  /** Split granularity: per word or per character. */
  per?: Per;
  preset?: Preset;
  className?: string;
  /** Applied to every animated segment (e.g. gradient text classes). */
  segmentClassName?: string;
}

export function TextEffect({
  children,
  per = "word",
  preset = "blur-scan",
  className,
  segmentClassName,
}: TextEffectProps) {
  const reduced = useReducedMotion();

  if (reduced) {
    return (
      <span className={clsx("inline-block", className)}>
        <span className={segmentClassName}>{children}</span>
      </span>
    );
  }

  const segments =
    per === "word"
      ? children.split(/(\s+)/).filter((s) => s.length > 0)
      : Array.from(children);
  const { container, item } = PRESETS[preset];

  return (
    <motion.span
      className={clsx("inline-block", className)}
      initial="hidden"
      animate="visible"
      exit="exit"
      variants={container}
      aria-label={children}
    >
      {segments.map((seg, i) =>
        seg.trim() === "" ? (
          // Plain spacer — keeps word gaps out of the animation.
          <span key={i} aria-hidden>
            {" "}
          </span>
        ) : (
          <motion.span
            key={i}
            aria-hidden
            variants={item}
            className={clsx(
              "inline-block will-change-[transform,filter,opacity]",
              segmentClassName,
            )}
          >
            {seg}
          </motion.span>
        ),
      )}
    </motion.span>
  );
}
