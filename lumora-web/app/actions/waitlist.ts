"use server";

import { createClient } from "@supabase/supabase-js";

// LM73A — waitlist email capture. Runs on the server; inserts into the
// insert-only `waitlist` table (RLS). Never reads the list back.

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export type WaitlistResult = { ok: true } | { ok: false; error: string };

export async function joinWaitlist(formData: FormData): Promise<WaitlistResult> {
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
    // 23505 = unique violation → already signed up; treat as success.
    if (error.code === "23505") return { ok: true };
    return { ok: false, error: "Something went wrong — please try again." };
  }

  return { ok: true };
}
