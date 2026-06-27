"use client";

import { useEffect, useRef, useState } from "react";

type Props = {
  value: number;
  prefix?: string;
  suffix?: string;
  decimals?: number;
  durationMs?: number;
  className?: string;
};

// Counts a number up from zero the first time it scrolls into view. Eyes follow
// movement, and a number climbing reads as momentum. Honors reduced-motion
// (jumps to the final value). Uses requestAnimationFrame, no timers left running.
export function CountUp({
  value,
  prefix = "",
  suffix = "",
  decimals = 0,
  durationMs = 1400,
  className = "",
}: Props) {
  const ref = useRef<HTMLSpanElement>(null);
  const started = useRef(false);
  const rafId = useRef(0);
  const [n, setN] = useState(0);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (
      typeof window !== "undefined" &&
      window.matchMedia?.("(prefers-reduced-motion: reduce)").matches
    ) {
      setN(value);
      return;
    }
    const io = new IntersectionObserver(
      (entries) => {
        if (!entries[0]?.isIntersecting || started.current) return;
        started.current = true;
        const t0 = performance.now();
        const step = (now: number) => {
          const t = Math.min(1, (now - t0) / durationMs);
          const eased = 1 - Math.pow(1 - t, 3);
          setN(value * eased);
          if (t < 1) rafId.current = requestAnimationFrame(step);
          else setN(value);
        };
        rafId.current = requestAnimationFrame(step);
        io.disconnect();
      },
      { threshold: 0.4 },
    );
    io.observe(el);
    return () => {
      io.disconnect();
      cancelAnimationFrame(rafId.current);
    };
  }, [value, durationMs]);

  const display =
    decimals > 0 ? n.toFixed(decimals) : Math.round(n).toLocaleString("en-US");

  return (
    <span ref={ref} className={className}>
      {prefix}
      {display}
      {suffix}
    </span>
  );
}
