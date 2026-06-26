"use client";

import { useState } from "react";
import { ArrowRight, Check, Loader2 } from "lucide-react";
import { joinWaitlist } from "@/app/actions/waitlist";

type Status = "idle" | "loading" | "success" | "error";

// LM73A — primary beta conversion: capture an email even when the visitor
// isn't ready to open the terminal or join Discord. Posts to the joinWaitlist
// server action; optimistic states keep the CTA responsive.
export function WaitlistForm() {
  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState("");

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const data = new FormData(form);
    setStatus("loading");
    setError("");
    const res = await joinWaitlist(data);
    if (res.ok) {
      setStatus("success");
      form.reset();
    } else {
      setStatus("error");
      setError(res.error);
    }
  }

  if (status === "success") {
    return (
      <div className="flex items-center justify-center gap-2 rounded-md border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-[13px] text-emerald-300">
        <Check className="h-4 w-4" />
        You&apos;re on the list. We&apos;ll email you when a spot opens.
      </div>
    );
  }

  return (
    <div className="mx-auto w-full max-w-md">
    <form onSubmit={onSubmit} className="flex w-full flex-col gap-2 sm:flex-row" noValidate>
      <label htmlFor="waitlist-email" className="sr-only">
        Email address
      </label>
      <input
        id="waitlist-email"
        name="email"
        type="email"
        required
        autoComplete="email"
        placeholder="you@email.com"
        disabled={status === "loading"}
        className="min-h-[44px] flex-1 rounded-md border border-lm-border bg-lm-surface px-4 text-[13px] text-lm-text placeholder:text-lm-muted focus:border-cyan-400/50 disabled:opacity-60"
      />
      <button
        type="submit"
        disabled={status === "loading"}
        className="inline-flex min-h-[44px] items-center justify-center gap-2 rounded-md bg-cyan-400 px-5 text-[13px] font-semibold text-zinc-950 transition-all hover:bg-cyan-300 disabled:opacity-70"
      >
        {status === "loading" ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <>
            Get early access <ArrowRight className="h-3.5 w-3.5" />
          </>
        )}
      </button>
      {status === "error" && (
        <p role="alert" className="w-full text-center text-[11px] text-red-400 sm:text-left">
          {error}
        </p>
      )}
    </form>
      <p className="mt-2.5 text-center text-[11px] leading-relaxed text-lm-muted">
        We only use your email to invite you to the beta. By joining you agree to our{" "}
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
  );
}
