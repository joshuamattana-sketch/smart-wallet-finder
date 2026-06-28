"use server";

import crypto from "node:crypto";
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

  // Mint a single-use code directly in invite_codes via the service role (no DB
  // function needed). A fresh random code makes collisions astronomically
  // unlikely; retry once on the off chance of a unique-violation (23505).
  let codeStr = "";
  let insErr: { code?: string; message: string } | null = null;
  for (let attempt = 0; attempt < 2; attempt++) {
    codeStr = "LMR-" + crypto.randomBytes(5).toString("hex").toUpperCase();
    // invite_codes columns: code, label, active, max_uses, uses, created_at.
    // label records who the personal code was issued to (visible in the table).
    const { error } = await sb
      .from("invite_codes")
      .insert({ code: codeStr, label: clean, max_uses: 1, uses: 0, active: true });
    if (!error) {
      insErr = null;
      break;
    }
    insErr = error;
    if (error.code !== "23505") break; // not a collision → real error, stop
  }
  if (insErr) {
    return { ok: false, error: `Code generation failed: ${insErr.message}` };
  }

  // Best-effort: stamp the waitlist row so the UI shows "invited" across
  // reloads. Optional polish — only persists once the waitlist has the
  // invited_at/invite_code columns (supabase/beta_invites.sql). Failure here
  // never affects the actual invite, so it is intentionally swallowed.
  await sb
    .from("waitlist")
    .update({ invited_at: new Date().toISOString(), invite_code: codeStr })
    .eq("email", clean)
    .then(undefined, () => {});

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
  return { ok: true, code: codeStr, emailed, error: sendError };
}
