import Link from "next/link";
import { Compass } from "lucide-react";

export const metadata = { title: "Not found" };

export default function NotFound() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center bg-lm-bg px-4 text-center">
      <span className="mb-4 flex h-11 w-11 items-center justify-center rounded-lg border border-violet-400/30 bg-violet-500/10">
        <Compass className="h-5 w-5 text-violet-300" />
      </span>
      <p className="num text-[11px] uppercase tracking-[0.28em] text-lm-muted">404</p>
      <h1 className="mt-2 text-lg font-semibold text-lm-text">Page not found</h1>
      <p className="mt-1 max-w-sm text-[13px] leading-relaxed text-lm-text-dim">
        That route doesn&apos;t exist. It may have moved, or it&apos;s part of the private terminal.
      </p>
      <Link
        href="/"
        className="mt-6 inline-flex min-h-[40px] items-center justify-center rounded-md bg-cyan-400 px-5 text-[13px] font-semibold text-zinc-950 transition-colors hover:bg-cyan-300"
      >
        Back to home
      </Link>
    </main>
  );
}
