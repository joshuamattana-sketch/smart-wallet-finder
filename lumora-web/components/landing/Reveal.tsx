"use client";

import { motion, useReducedMotion } from "framer-motion";

// ── Scroll reveal ─────────────────────────────────────────────────────────────
// Shared landing-page reveal: content rises out of the dark as it enters the
// viewport, once. Reduced motion renders children statically — no wrapper
// animation at all, so the page is identical minus the motion.

export function Reveal({
  children,
  delay = 0,
  y = 22,
  className,
}: {
  children: React.ReactNode;
  delay?: number;
  y?: number;
  className?: string;
}) {
  const reduced = useReducedMotion();
  if (reduced) return <div className={className}>{children}</div>;
  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, y }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-70px" }}
      transition={{ duration: 0.65, delay, ease: [0.21, 0.47, 0.32, 0.98] }}
    >
      {children}
    </motion.div>
  );
}
