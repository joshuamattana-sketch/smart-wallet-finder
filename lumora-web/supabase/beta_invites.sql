-- LM79A — Beta invite automation for the /admin "send code" flow.
-- Run ONCE in Supabase → SQL Editor.
--
-- ⚠️ The INSERT in create_beta_invite() assumes the standard invite_codes shape
--    (code, max_uses, used_count, active). If your table differs, adjust the
--    column list — paste the output of the query at the bottom and Claude will
--    match it.

-- 1. Track invite status on the waitlist so the admin UI shows who's been invited.
alter table public.waitlist
  add column if not exists invited_at timestamptz,
  add column if not exists invite_code text;

-- 2. Mint a single-use invite code. SECURITY DEFINER so the service role can
--    write invite_codes through it. pgcrypto (gen_random_bytes) ships with Supabase.
create extension if not exists pgcrypto;

create or replace function public.create_beta_invite(p_email text)
returns text
language plpgsql
security definer
set search_path = public
as $$
declare
  v_code text;
begin
  v_code := 'LMR-' || upper(substr(encode(gen_random_bytes(6), 'hex'), 1, 10));
  insert into public.invite_codes (code, max_uses, used_count, active)
  values (v_code, 1, 0, true);
  return v_code;
end;
$$;

-- 3. Allow the admin server actions (service role) to call it.
grant execute on function public.create_beta_invite(text) to service_role;

-- ── If step 2 errors on column names, run this and share the result ──────────
-- select column_name, data_type, is_nullable, column_default
-- from information_schema.columns
-- where table_name = 'invite_codes'
-- order by ordinal_position;
