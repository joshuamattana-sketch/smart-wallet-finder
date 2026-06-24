import { createClient, type SupabaseClient } from "@supabase/supabase-js";

// LM78A — singleton browser Supabase client for Realtime subscriptions.
// Uses the public anon/publishable key; RLS (anon SELECT on the market-data
// tables) governs what Realtime delivers. Returns null when unconfigured so
// callers degrade gracefully to their existing fetch path.

let client: SupabaseClient | null = null;

export function getSupabaseBrowser(): SupabaseClient | null {
  if (client) return client;
  if (typeof window === "undefined") return null;
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
  if (!url || !key) return null;
  client = createClient(url, key, {
    auth: { persistSession: false },
    realtime: { params: { eventsPerSecond: 5 } },
  });
  return client;
}
