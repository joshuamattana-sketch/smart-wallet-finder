"use client";

import { useTransition } from "react";
import { useRouter } from "next/navigation";
import { logoutAdmin } from "./actions";

export function LogoutButton() {
  const router = useRouter();
  const [pending, start] = useTransition();
  return (
    <button
      type="button"
      onClick={() => start(async () => {
        await logoutAdmin();
        router.refresh();
      })}
      disabled={pending}
      className="rounded-md border border-lm-border px-3 py-1.5 text-[12px] text-lm-text-dim transition-colors hover:text-lm-text disabled:opacity-50"
    >
      {pending ? "…" : "Log out"}
    </button>
  );
}
