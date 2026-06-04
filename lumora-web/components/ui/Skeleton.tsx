import { clsx } from "clsx";

type SkeletonVariant = "line" | "block" | "card";

interface SkeletonProps {
  variant?: SkeletonVariant;
  className?: string;
  /** Custom width (Tailwind class, e.g. "w-24"). Overrides variant default. */
  width?: string;
  /** Custom height (Tailwind class, e.g. "h-6"). Overrides variant default. */
  height?: string;
}

const variantStyles: Record<SkeletonVariant, string> = {
  line:  "h-3 w-full",
  block: "h-16 w-full",
  card:  "h-28 w-full",
};

export function Skeleton({ variant = "line", className, width, height }: SkeletonProps) {
  return (
    <div
      className={clsx(
        "lm-skeleton",
        variantStyles[variant],
        width,
        height,
        className,
      )}
      aria-hidden="true"
    />
  );
}

/** Composite card skeleton — header line, big block, two short lines. */
export function SkeletonCard({ className }: { className?: string }) {
  return (
    <div className={clsx("rounded-lg border border-lm-border bg-lm-surface p-3 space-y-2", className)}>
      <Skeleton variant="line" width="w-20" />
      <Skeleton variant="line" height="h-6" width="w-2/3" />
      <Skeleton variant="line" width="w-1/2" />
      <Skeleton variant="line" width="w-3/4" />
    </div>
  );
}
