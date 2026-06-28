"use server";

import { headers } from "next/headers";
import { createClient } from "@supabase/supabase-js";
import { notifyNewSignup } from "@/lib/email";

// LM73A — waitlist email capture. Runs on the server; inserts into the
// insert-only `waitlist` table (RLS). Never reads the list back.

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

// Best-effort in-memory rate limit (per server instance). Not a hard guarantee
// across serverless instances, but blunts trivial spam without extra infra.
const RL_WINDOW_MS = 10 * 60 * 1000;
const RL_MAX = 5;
const rlHits = new Map<string, number[]>();

function rateLimited(ip: string): boolean {
  const now = Date.now();
  const recent = (rlHits.get(ip) ?? []).filter((t) => now - t < RL_WINDOW_MS);
  if (recent.length >= RL_MAX) {
    rlHits.set(ip, recent);
    return true;
  }
  recent.push(now);
  rlHits.set(ip, recent);
  return false;
}

export type WaitlistResult = { ok: true } | { ok: false; error: string };

export async function joinWaitlist(formData: FormData): Promise<WaitlistResult> {
  const ip = (headers().get("x-forwarded-for") ?? "").split(",")[0].trim() || "unknown";
  if (rateLimited(ip)) {
    return { ok: false, error: "Too many attempts. Please try again later." };
  }

  const email = String(formData.get("email") ?? "").trim().toLowerCase();

  if (!EMAIL_RE.test(email) || email.length > 254) {
    return { ok: false, error: "Enter a valid email address." };
  }

  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
  if (!url || !key) {
    return { ok: false, error: "The waitlist isn't configured yet." };
  }

  const supabase = createClient(url, key, { auth: { persistSession: false } });
  const { error } = await supabase
    .from("waitlist")
    .insert({ email, source: "landing" });

  if (error) {
    // 23505 = unique violation → already signed up; treat as success (no
    // duplicate notification).
    if (error.code === "23505") return { ok: true };
    return { ok: false, error: "Something went wrong. Please try again." };
  }

  // Fresh signup → notify the owner. Best-effort; never fail the signup over it.
  await notifyNewSignup(email).catch(() => {});

  return { ok: true };
}
