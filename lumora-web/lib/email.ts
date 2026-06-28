import "server-only";
import { SITE_URL } from "@/lib/site";

// LM79A — minimal Resend sender over the REST API (no extra dependency).
// Everything no-ops cleanly when RESEND_API_KEY is unset, so the app — and the
// /admin "send code" button — keep working before email is configured (the code
// is just shown for manual sending instead).

const FROM = process.env.RESEND_FROM ?? "Lumora <onboarding@resend.dev>";
export const NOTIFY_EMAIL = process.env.LUMORA_NOTIFY_EMAIL ?? "legal.lumora@gmail.com";

type SendResult = { ok: true } | { ok: false; reason: string };

export function emailConfigured(): boolean {
  return Boolean(process.env.RESEND_API_KEY);
}

export function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

export async function sendEmail(opts: {
  to: string;
  subject: string;
  html: string;
  replyTo?: string;
}): Promise<SendResult> {
  const key = process.env.RESEND_API_KEY;
  if (!key) return { ok: false, reason: "RESEND_API_KEY not set" };
  try {
    const res = await fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: { Authorization: `Bearer ${key}`, "Content-Type": "application/json" },
      body: JSON.stringify({
        from: FROM,
        to: [opts.to],
        subject: opts.subject,
        html: opts.html,
        ...(opts.replyTo ? { reply_to: opts.replyTo } : {}),
      }),
    });
    if (!res.ok) {
      const txt = await res.text().catch(() => "");
      return { ok: false, reason: `Resend ${res.status}: ${txt.slice(0, 200)}` };
    }
    return { ok: true };
  } catch (e) {
    return { ok: false, reason: e instanceof Error ? e.message : "send failed" };
  }
}

// Owner notification when someone joins the waitlist. Best-effort.
export async function notifyNewSignup(email: string): Promise<void> {
  if (!emailConfigured()) return;
  await sendEmail({
    to: NOTIFY_EMAIL,
    subject: "New Lumora waitlist signup",
    html: `<p>New signup: <strong>${escapeHtml(email)}</strong></p>
<p>Approve &amp; send a one-time code: <a href="${SITE_URL}/admin">${SITE_URL}/admin</a></p>`,
  }).catch(() => {});
}

// The invite email delivered to an approved person.
export function inviteHtml(code: string): string {
  const safe = escapeHtml(code);
  return `<p>You're in. Here is your personal Lumora beta invite code:</p>
<p style="font-size:20px;font-weight:700;letter-spacing:1px">${safe}</p>
<p>Redeem it at <a href="${SITE_URL}/enter">${SITE_URL}/enter</a>. It works once.</p>
<p style="color:#888;font-size:12px">Lumora · informational market context only, not financial advice.</p>`;
}
