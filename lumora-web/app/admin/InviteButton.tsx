"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { sendInvite } from "./actions";

// Per-row "send code" control. Mints a single-use code, emails it (if email is
// configured), and shows the code inline either way so the owner can copy it.
export function InviteButton({
  email,
  alreadyInvited,
}: {
  email: string;
  alreadyInvited: boolean;
}) {
  const router = useRouter();
  const [pending, start] = useTransition();
  const [result, setResult] = useState<{ code?: string; emailed?: boolean; error?: string } | null>(
    null,
  );

  function go() {
    if (pending) return;
    if (alreadyInvited && !confirm(`Re-send a NEW code to ${email}?`)) return;
    start(async () => {
      const res = await sendInvite(email);
      if (res.ok) {
        setResult({ code: res.code, emailed: res.emailed, error: res.error });
        router.refresh();
      } else {
        setResult({ error: res.error });
      }
    });
  }

  return (
    <div className="flex flex-col items-end gap-1">
      <button
        type="button"
        onClick={go}
        disabled={pending}
        className="rounded-md border border-lm-border px-3 py-1.5 text-[12px] font-medium text-lm-text transition-colors hover:bg-white/5 disabled:opacity-50"
      >
        {pending ? "Sending…" : alreadyInvited ? "Re-send code" : "Send code"}
      </button>
      {result?.code && (
        <span className="text-[11px] text-lm-text-dim">
          {result.emailed ? "emailed · " : "copy & send · "}
          <code className="text-emerald-400">{result.code}</code>
        </span>
      )}
      {result?.error && <span className="max-w-[220px] text-[11px] text-red-300">{result.error}</span>}
    </div>
  );
}
