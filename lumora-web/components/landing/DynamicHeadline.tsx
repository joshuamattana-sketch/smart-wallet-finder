"use client";

import { useEffect, useState } from "react";
import { AnimatePresence, useReducedMotion } from "framer-motion";
import { TextEffect } from "@/components/ui/text-effect";

// ── Dynamic hero headline ────────────────────────────────────────────────────
// "See the {pressure} behind the price." — the key word rotates through what
// Lumora actually reads, each one resolving out of a blur character by
// character, like the terminal scanning hidden market structure.
//
// Layout shift is avoided by stacking every candidate word invisibly in one
// inline-grid cell, so the slot is always sized to the widest word. With
// reduced motion the headline stays static on "pressure".

const WORDS = ["pressure", "liquidity", "whale flow", "risk"];
const HOLD_MS = 3400;

export function DynamicHeadline() {
  const reduced = useReducedMotion();
  const [idx, setIdx] = useState(0);

  useEffect(() => {
    if (reduced) return;
    const id = setTimeout(() => setIdx((i) => (i + 1) % WORDS.length), HOLD_MS);
    return () => clearTimeout(id);
  }, [reduced, idx]);

  return (
    <h1 className="mt-4 text-4xl font-semibold leading-[1.06] tracking-[-0.02em] text-lm-text sm:text-[44px] lg:text-[50px]">
      See the{" "}
      <span className="relative inline-grid whitespace-nowrap align-bottom">
        {/* Invisible stack of all candidates reserves the widest slot. */}
        {WORDS.map((w) => (
          <span key={w} aria-hidden className="invisible col-start-1 row-start-1">
            {w}
          </span>
        ))}
        <span className="col-start-1 row-start-1">
          <AnimatePresence mode="wait" initial={false}>
            <TextEffect
              key={WORDS[idx]}
              per="char"
              preset="blur-scan"
              segmentClassName="bg-gradient-to-b from-cyan-200 via-cyan-300 to-sky-500 bg-clip-text text-transparent"
            >
              {WORDS[idx]}
            </TextEffect>
          </AnimatePresence>
        </span>
      </span>
      <br />
      behind the price.
    </h1>
  );
}
