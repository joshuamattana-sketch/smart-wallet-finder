import "server-only";
import { createClient, type SupabaseClient } from "@supabase/supabase-js";

// LM79A — service-role Supabase client for owner-only admin work: reading the
// insert-only `waitlist` table and minting single-use invite codes. service_role
// BYPASSES RLS, so this must never be imported from a client component. Returns
// null when not configured (the /admin page degrades to a clear notice).
export function supabaseAdmin(): SupabaseClient | null {
  const url = process.env.SUPABASE_URL ?? process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!url || !key) return null;
  return createClient(url, key, { auth: { persistSession: false } });
}
