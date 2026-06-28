"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { loginAdmin } from "./actions";

// Owner gate for /admin. Posts the owner code to the loginAdmin server action,
// which sets the signed admin cookie. On success we refresh so the server
// component re-renders as the authenticated console.
export function AdminLogin({ configured }: { configured: boolean }) {
  const router = useRouter();
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, start] = useTransition();

  function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    start(async () => {
      const res = await loginAdmin(code);
      if (res.ok) router.refresh();
      else setError(res.error ?? "Login failed.");
    });
  }

  return (
    <div className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-6">
      <p className="num text-[11px] uppercase tracking-[0.22em] text-lm-muted">Owner console</p>
      <h1 className="mt-1 text-2xl font-semibold tracking-tight text-lm-text">Admin access</h1>
      <p className="mt-2 text-[13px] text-lm-text-dim">
        Enter the owner code to manage the waitlist.
      </p>

      {!configured && (
        <p className="mt-4 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-[12px] text-amber-200">
          Admin is not configured yet — set <code>LUMORA_OWNER_CODE</code> (≥12 chars) in the
          environment.
        </p>
      )}

      <form onSubmit={submit} className="mt-6 flex flex-col gap-3">
        <input
          type="password"
          value={code}
          onChange={(e) => setCode(e.target.value)}
          placeholder="Owner code"
          autoComplete="off"
          autoFocus
          className="rounded-lg border border-lm-border bg-lm-surface px-4 py-2.5 text-[14px] text-lm-text outline-none focus:border-lm-purple"
        />
        {error && <p className="text-[12px] text-red-300">{error}</p>}
        <button
          type="submit"
          disabled={pending || !code}
          className="rounded-lg bg-lm-purple px-4 py-2.5 text-[14px] font-semibold text-white transition-colors hover:bg-[#7c4ddb] disabled:opacity-50"
        >
          {pending ? "Checking…" : "Enter"}
        </button>
      </form>
    </div>
  );
}
