"use client";

import { useState, useTransition } from "react";
import { Check } from "lucide-react";
import { joinWaitlist } from "@/app/actions/waitlist";

// Light early-access capture wired to the real waitlist server action, so the
// signup actually records instead of opening a mail client. Inline success and
// error states, no page reload.
export function EarlyAccessForm() {
  const [done, setDone] = useState(false);
  const [error, setError] = useState("");
  const [pending, start] = useTransition();

  function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError("");
    const formData = new FormData(e.currentTarget);
    start(async () => {
      const res = await joinWaitlist(formData);
      if (res.ok) setDone(true);
      else setError(res.error);
    });
  }

  if (done) {
    return (
      <div className="mx-auto flex max-w-md items-center justify-center gap-2.5 rounded-xl border border-fintech-indigo-line bg-fintech-indigo-soft px-5 py-4 text-[15px] font-medium text-fintech-indigo-ink">
        <Check className="h-4 w-4" aria-hidden="true" />
        You are on the list. We will email your invite when a spot opens.
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="mx-auto max-w-md" noValidate>
      <div className="flex flex-col gap-2.5 sm:flex-row">
        <input
          type="email"
          name="email"
          required
          autoComplete="email"
          placeholder="you@email.com"
          aria-label="Email address"
          className="h-12 flex-1 rounded-xl border border-fintech-line bg-white px-4 text-[15px] text-fintech-ink outline-none transition-shadow placeholder:text-fintech-faint focus:border-fintech-indigo focus:ring-4 focus:ring-fintech-indigo/15"
        />
        <button
          type="submit"
          disabled={pending}
          className="fx-lift h-12 rounded-xl bg-fintech-indigo px-6 text-[15px] font-medium text-white hover:bg-fintech-indigo-ink disabled:opacity-70"
        >
          {pending ? "Adding you..." : "Request early access"}
        </button>
      </div>
      {error ? (
        <p role="alert" className="mt-2.5 text-[13px] text-fintech-neg">
          {error}
        </p>
      ) : null}
      <p className="mt-3 text-[12.5px] text-fintech-faint">
        No card. No spam. Unsubscribe any time.
      </p>
    </form>
  );
}
