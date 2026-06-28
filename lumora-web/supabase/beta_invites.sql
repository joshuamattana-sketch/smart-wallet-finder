-- LM79A — OPTIONAL polish for the /admin invite flow.
--
-- Not required: the "Send code" button mints + emails a single-use code without
-- any DB changes (it inserts straight into invite_codes via the service role).
-- These two columns only let the admin UI remember which signups were already
-- invited across page reloads (the "invited · CODE" badge). Without them the
-- flow still works; the badge just won't persist.
--
-- Already applied to the live project on 2026-06-28 (migration
-- "waitlist_invite_tracking"). Kept here as the source of record; re-running is
-- safe (idempotent).

alter table public.waitlist
  add column if not exists invited_at timestamptz,
  add column if not exists invite_code text;
