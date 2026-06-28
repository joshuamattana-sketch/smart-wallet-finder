import type { Metadata } from "next";
import { cookies } from "next/headers";
import { ADMIN_COOKIE, adminConfigured, verifyAdminToken } from "@/lib/admin-auth";
import { supabaseAdmin } from "@/lib/supabase-admin";
import { emailConfigured } from "@/lib/email";
import { AdminLogin } from "./AdminLogin";
import { InviteButton } from "./InviteButton";
import { LogoutButton } from "./LogoutButton";

// Owner-only console: see waitlist signups, send a one-time invite code per
// person. Never indexed, always dynamic.
export const dynamic = "force-dynamic";
export const metadata: Metadata = {
  title: "Admin",
  robots: { index: false, follow: false },
};

type Row = {
  email: string;
  source: string | null;
  created_at: string;
  invited_at?: string | null;
  invite_code?: string | null;
};

function fmt(ts: string): string {
  // Stable, locale-free timestamp (avoids server/client hydration drift).
  return ts.replace("T", " ").replace(/\..*$/, "").replace("Z", " UTC");
}

export default async function AdminPage() {
  if (!verifyAdminToken(cookies().get(ADMIN_COOKIE)?.value)) {
    return <AdminLogin configured={adminConfigured()} />;
  }

  const sb = supabaseAdmin();
  let rows: Row[] = [];
  let loadError: string | null = null;

  if (!sb) {
    loadError = "SUPABASE_SERVICE_ROLE_KEY is not set — cannot read the waitlist.";
  } else {
    const { data, error } = await sb
      .from("waitlist")
      .select("*")
      .order("created_at", { ascending: false })
      .limit(500);
    if (error) loadError = error.message;
    else rows = (data ?? []) as Row[];
  }

  const pending = rows.filter((r) => !r.invited_at).length;

  return (
    <div className="mx-auto min-h-screen max-w-4xl px-4 py-10 sm:px-6">
      <header className="mb-8 flex items-end justify-between gap-4">
        <div>
          <p className="num text-[11px] uppercase tracking-[0.22em] text-lm-muted">Owner console</p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight text-lm-text">Waitlist</h1>
          <p className="mt-1 text-[13px] text-lm-text-dim">
            {rows.length} signups · {pending} pending
            {!emailConfigured() && (
              <span className="ml-2 rounded bg-amber-500/15 px-1.5 py-0.5 text-[11px] text-amber-300">
                email off — codes shown for manual send
              </span>
            )}
          </p>
        </div>
        <LogoutButton />
      </header>

      {loadError ? (
        <div className="rounded-lg border border-red-500/40 bg-red-500/10 px-4 py-3 text-[13px] text-red-200">
          {loadError}
        </div>
      ) : rows.length === 0 ? (
        <p className="text-[14px] text-lm-text-dim">No signups yet.</p>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-lm-border">
          <table className="w-full text-left text-[13px]">
            <thead className="border-b border-lm-border text-[11px] uppercase tracking-wide text-lm-muted">
              <tr>
                <th className="px-4 py-3 font-medium">Email</th>
                <th className="px-4 py-3 font-medium">Joined</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 text-right font-medium">Action</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.email} className="border-b border-lm-border/50 last:border-0">
                  <td className="px-4 py-3 text-lm-text">{r.email}</td>
                  <td className="px-4 py-3 text-lm-text-dim">{fmt(r.created_at)}</td>
                  <td className="px-4 py-3">
                    {r.invited_at ? (
                      <span className="text-emerald-400">
                        invited{r.invite_code ? ` · ${r.invite_code}` : ""}
                      </span>
                    ) : (
                      <span className="text-lm-muted">pending</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <InviteButton email={r.email} alreadyInvited={Boolean(r.invited_at)} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
