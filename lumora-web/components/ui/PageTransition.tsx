import { clsx } from "clsx";

interface PageTransitionProps {
  children: React.ReactNode;
  className?: string;
}

/**
 * Subtle page entrance wrapper — short fade + tiny upward translate.
 * CSS-only, no client boundary needed. Honors `prefers-reduced-motion`
 * via the shared `.lm-page-enter` style.
 */
export function PageTransition({ children, className }: PageTransitionProps) {
  return <div className={clsx("lm-page-enter", className)}>{children}</div>;
}
