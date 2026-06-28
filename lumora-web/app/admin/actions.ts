"use server";

import { cookies, headers } from "next/headers";
import { revalidatePath } from "next/cache";
import {
  ADMIN_COOKIE,
  adminConfigured,
  adminCookieMaxAge,
  checkOwnerCode,
  signAdminToken,
  verifyAdminToken,
} from "@/lib/admin-auth";
import { supabaseAdmin } from "@/lib/supabase-admin";
import { emailConfigured, inviteHtml, NOTIFY_EMAIL, sendEmail } from "@/lib/email";
import { clientIp, isRateLimited } from "@/lib/rate-limit";

function isAdmin(): boolean {
  return verifyAdminToken(cookies().get(ADMIN_COOKIE)?.value);
}

type LoginResult = { ok: boolean; error?: string };

export async function loginAdmin(code: string): Promise<LoginResult> {
  if (!adminConfigured()) {
    return { ok: false, error: "Admin is not configured (set LUMORA_OWNER_CODE)." };
  }
  // Owner login is a brute-force target — cap attempts per IP.
  const ip = clientIp(headers());
  if (isRateLimited(`admin-login:${ip}`, 10, 10 * 60 * 1000)) {
    return { ok: false, error: "Too many attempts. Try again later." };
  }
  if (!checkOwnerCode(code.trim())) return { ok: false, error: "Wrong code." };

  cookies().set(ADMIN_COOKIE, signAdminToken(), {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: adminCookieMaxAge(),
  });
  return { ok: true };
}

export async function logoutAdmin(): Promise<void> {
  cookies().delete(ADMIN_COOKIE);
  revalidatePath("/admin");
}

type InviteResult = {
  ok: boolean;
  code?: string;
  emailed?: boolean;
  error?: string;
};

export async function sendInvite(email: string): Promise<InviteResult> {
  if (!isAdmin()) return { ok: false, error: "Not authorized." };

  const sb = supabaseAdmin();
  if (!sb) return { ok: false, error: "SUPABASE_SERVICE_ROLE_KEY not set." };

  const clean = email.trim().toLowerCase();
  if (!clean) return { ok: false, error: "No email." };

  // Mint a single-use code via the SECURITY DEFINER function (setup SQL).
  const { data: code, error: rpcErr } = await sb.rpc("create_beta_invite", { p_email: clean });
  if (rpcErr || !code) {
    return { ok: false, error: rpcErr?.message ?? "Code generation failed — run the setup SQL." };
  }
  const codeStr = String(code);

  // Stamp the waitlist row so the UI shows it as invited (needs the new columns).
  const { error: updErr } = await sb
    .from("waitlist")
    .update({ invited_at: new Date().toISOString(), invite_code: codeStr })
    .eq("email", clean);

  // Deliver the code. If email isn't configured or fails, the code is still
  // returned so the owner can send it by hand — nothing is lost.
  let emailed = false;
  let sendError: string | undefined;
  if (emailConfigured()) {
    const r = await sendEmail({
      to: clean,
      subject: "Your Lumora beta invite code",
      replyTo: NOTIFY_EMAIL,
      html: inviteHtml(codeStr),
    });
    emailed = r.ok;
    if (!r.ok) sendError = r.reason;
  }

  revalidatePath("/admin");
  return {
    ok: true,
    code: codeStr,
    emailed,
    error: sendError ?? (updErr ? `Code sent, but waitlist update failed: ${updErr.message}` : undefined),
  };
}
