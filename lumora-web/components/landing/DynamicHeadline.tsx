"use client";

import { useEffect, useState } from "react";
import { AnimatePresence, useReducedMotion } from "framer-motion";
import { TextEffect } from "@/components/ui/text-effect";

// ── Dynamic hero headline ────────────────────────────────────────────────────
// "See the {pressure} behind the price." — the key word rotates through what
// Lumora actually reads, each one resolving out of a blur character by
// character, like the terminal scanning hidden market structure.
//
// LCP: this is the largest text on the page, so WORDS[0] is rendered as plain
// opaque gradient text on the server and first paint. The blur rotation is a
// progressive enhancement that only starts after mount (and never under
// reduced motion), so the headline is legible immediately instead of after
// framer-motion hydrates.
//
// Mobile: the type size is fluid (clamp) and the rotating word slot reserves
// the widest candidate in one inline-grid cell, so there is no layout shift
// and no horizontal overflow at 320px.

const WORDS = ["pressure", "liquidity", "whale flow", "risk"];
const HOLD_MS = 3400;

const GRADIENT = "bg-gradient-to-b from-cyan-200 via-cyan-300 to-sky-500 bg-clip-text text-transparent";

export function DynamicHeadline() {
  const reduced = useReducedMotion();
  const [mounted, setMounted] = useState(false);
  const [idx, setIdx] = useState(0);

  useEffect(() => setMounted(true), []);

  useEffect(() => {
    if (reduced || !mounted) return;
    const id = setTimeout(() => setIdx((i) => (i + 1) % WORDS.length), HOLD_MS);
    return () => clearTimeout(id);
  }, [reduced, mounted, idx]);

  const animate = mounted && !reduced;

  return (
    <h1 className="lm-display mt-5 font-semibold leading-[1.02] tracking-[-0.02em] text-lm-text text-[clamp(2.1rem,9vw,2.9rem)] sm:text-[58px] lg:text-[72px]">
      See the{" "}
      <span className="relative inline-grid whitespace-nowrap align-bottom">
        {/* Invisible stack of all candidates reserves the widest slot. */}
        {WORDS.map((w) => (
          <span key={w} aria-hidden className="invisible col-start-1 row-start-1">
            {w}
          </span>
        ))}
        <span className="col-start-1 row-start-1">
          {animate ? (
            <AnimatePresence mode="wait" initial={false}>
              <TextEffect
                key={WORDS[idx]}
                per="char"
                preset="blur-scan"
                segmentClassName={GRADIENT}
              >
                {WORDS[idx]}
              </TextEffect>
            </AnimatePresence>
          ) : (
            // Server + first paint + reduced-motion: static, fully legible.
            <span className={GRADIENT}>{WORDS[0]}</span>
          )}
        </span>
      </span>
      <br />
      behind the price.
    </h1>
  );
}
