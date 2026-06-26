"use client";

import { useState } from "react";
import { Activity, ArrowRight, Loader2 } from "lucide-react";

// LM76A — invite-code gate. Redeems a code via /api/beta-unlock; on success the
// server sets the access cookie and we continue to the requested route.
export default function EnterPage() {
  const [code, setCode] = useState("");
  const [status, setStatus] = useState<"idle" | "loading" | "error">("idle");
  const [error, setError] = useState("");

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!code.trim()) return;
    setStatus("loading");
    setError("");
    try {
      const res = await fetch("/api/beta-unlock", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code }),
      });
      const data = (await res.json().catch(() => null)) as { ok?: boolean; error?: string } | null;
      if (res.ok && data?.ok) {
        const params = new URLSearchParams(window.location.search);
        const next = params.get("next");
        const dest = next && next.startsWith("/") ? next : "/dashboard";
        window.location.href = dest;
        return;
      }
      setStatus("error");
      setError(data?.error ?? "Something went wrong. Try again.");
    } catch {
      setStatus("error");
      setError("Network error. Try again.");
    }
  }

  return (
    <main className="relative flex min-h-screen items-center justify-center overflow-hidden bg-lm-bg px-4">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            "radial-gradient(60% 50% at 50% 0%, rgba(139,92,246,0.10), transparent 60%), radial-gradient(50% 50% at 50% 110%, rgba(34,211,238,0.07), transparent 60%)",
        }}
      />
      <div className="relative w-full max-w-sm">
        <div className="mb-6 flex items-center justify-center gap-2.5">
          <span className="flex h-7 w-7 items-center justify-center rounded-md border border-violet-400/30 bg-gradient-to-br from-violet-500/25 to-cyan-400/10">
            <Activity className="h-4 w-4 text-violet-200" strokeWidth={2.5} />
          </span>
          <span className="lm-brand text-lg text-lm-text">Lumora</span>
        </div>

        <div className="rounded-lg border border-lm-border bg-lm-surface/80 p-6 backdrop-blur-sm">
          <p className="num text-[10px] uppercase tracking-[0.22em] text-lm-muted">Private beta</p>
          <h1 className="mt-2 text-lg font-semibold tracking-tight text-lm-text">Enter your invite code</h1>
          <p className="mt-1 text-[13px] leading-relaxed text-lm-text-dim">
            The terminal is invite-only during private beta.
          </p>

          <form onSubmit={onSubmit} className="mt-5 flex flex-col gap-2.5">
            <label htmlFor="invite" className="sr-only">
              Invite code
            </label>
            <input
              id="invite"
              name="invite"
              autoComplete="off"
              autoCapitalize="characters"
              spellCheck={false}
              autoFocus
              value={code}
              onChange={(e) => setCode(e.target.value)}
              disabled={status === "loading"}
              placeholder="LUMORA-XXXX"
              className="min-h-[44px] w-full rounded-md border border-lm-border bg-lm-bg px-4 text-[14px] tracking-wider text-lm-text placeholder:text-lm-muted focus:border-cyan-400/50 disabled:opacity-60"
            />
            <button
              type="submit"
              disabled={status === "loading" || !code.trim()}
              className="inline-flex min-h-[44px] items-center justify-center gap-2 rounded-md bg-cyan-400 px-5 text-[13px] font-semibold text-zinc-950 transition-all hover:bg-cyan-300 disabled:opacity-60"
            >
              {status === "loading" ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <>
                  Enter terminal <ArrowRight className="h-3.5 w-3.5" />
                </>
              )}
            </button>
            {status === "error" && (
              <p role="alert" className="text-center text-[12px] text-red-400">
                {error}
              </p>
            )}
          </form>
        </div>

        <p className="mt-4 text-center text-[12px] text-lm-text-dim">
          No code?{" "}
          <a href="/" className="text-lm-cyan hover:underline">
            Join the waitlist
          </a>
        </p>
        <p className="mt-4 text-center text-[11px] leading-relaxed text-lm-muted">
          Entering sets an essential cookie that keeps you signed in. See our{" "}
          <a href="/datenschutz" className="text-lm-text-dim underline underline-offset-2 hover:text-lm-text">
            Privacy Policy
          </a>{" "}
          and{" "}
          <a href="/risk" className="text-lm-text-dim underline underline-offset-2 hover:text-lm-text">
            Risk &amp; Terms
          </a>
          .
        </p>
      </div>
    </main>
  );
}
