"use client";

import { useEffect } from "react";
import Link from "next/link";
import { AlertTriangle, RotateCcw } from "lucide-react";

// Route-level error boundary — replaces the white-screen on any render/runtime
// error in a page with a recoverable, branded fallback.
export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Surfaced in the browser console / server logs; wire to an error tracker later.
    console.error(error);
  }, [error]);

  return (
    <main className="flex min-h-screen flex-col items-center justify-center bg-lm-bg px-4 text-center">
      <span className="mb-4 flex h-11 w-11 items-center justify-center rounded-lg border border-red-500/30 bg-red-500/10">
        <AlertTriangle className="h-5 w-5 text-red-400" />
      </span>
      <h1 className="text-lg font-semibold text-lm-text">Something went wrong</h1>
      <p className="mt-1 max-w-sm text-[13px] leading-relaxed text-lm-text-dim">
        An unexpected error interrupted this view. You can retry, or head back to the landing page.
      </p>
      {error.digest && (
        <p className="num mt-2 text-[10px] uppercase tracking-widest text-lm-muted">ref {error.digest}</p>
      )}
      <div className="mt-6 flex gap-2.5">
        <button
          type="button"
          onClick={reset}
          className="inline-flex min-h-[40px] items-center justify-center gap-2 rounded-md bg-cyan-400 px-5 text-[13px] font-semibold text-zinc-950 transition-colors hover:bg-cyan-300"
        >
          <RotateCcw className="h-3.5 w-3.5" /> Try again
        </button>
        <Link
          href="/"
          className="inline-flex min-h-[40px] items-center justify-center rounded-md border border-lm-border px-5 text-[13px] font-medium text-lm-text-dim transition-colors hover:border-zinc-600 hover:text-lm-text"
        >
          Back to home
        </Link>
      </div>
    </main>
  );
}
