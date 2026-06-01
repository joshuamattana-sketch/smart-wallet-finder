import { clsx } from "clsx";

export function SkeletonLine({ className }: { className?: string }) {
  return <div className={clsx("skeleton rounded h-3", className)} />;
}

export function SkeletonCard({ lines = 3, className }: { lines?: number; className?: string }) {
  return (
    <div className={clsx("rounded-xl border border-lumora-border bg-lumora-card p-4 space-y-3", className)}>
      {Array.from({ length: lines }).map((_, i) => (
        <SkeletonLine key={i} className={i === 0 ? "w-1/3" : i === lines - 1 ? "w-2/3" : "w-full"} />
      ))}
    </div>
  );
}
