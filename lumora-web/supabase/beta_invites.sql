-- LM79A — OPTIONAL polish for the /admin invite flow.
--
-- Not required: the "Send code" button mints + emails a single-use code without
-- any DB changes (it inserts straight into invite_codes via the service role).
-- These two columns only let the admin UI remember which signups were already
-- invited across page reloads (the "invited · CODE" badge). Without them the
-- flow still works; the badge just won't persist.
--
-- Run once in Supabase → SQL Editor if you want the persistent badge.

alter table public.waitlist
  add column if not exists invited_at timestamptz,
  add column if not exists invite_code text;
