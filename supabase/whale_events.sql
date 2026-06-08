-- supabase/whale_events.sql
-- LM63G — Whale event persistence (append-only).
--
-- Mirrors the local LM63E JSONL journal so production can move beyond
-- file-only storage. Sits alongside:
--   * heatmap_latest_payloads (single most recent payload per market)
--   * heatmap_frame_history   (append-only heatmap frames)
--   * liquidity_wall_history  (append-only wall observations)
--
-- Re-running the file is safe (CREATE TABLE IF NOT EXISTS / CREATE INDEX IF
-- NOT EXISTS / DO blocks are all idempotent). Existing data is never touched.
--
-- Security model:
--   * RLS is ENABLED with NO policies → only the service-role key (or direct
--     DB access) can read or write. Anon / authenticated keys are denied by
--     default. Consistent with heatmap_latest_payloads / heatmap_frame_history.
--   * Writers (Python LM63 pipeline) must use the service-role key on the
--     server side. **Browsers must never see the service-role key and must
--     never write directly to this table.**
--   * Anon reads should only become possible via an explicit, narrow API
--     route that selects the columns you choose to expose — never by adding
--     a permissive RLS policy on this table.
--   * Never commit Supabase keys / project URLs to the repo.


-- ── whale_events ──────────────────────────────────────────────────────────────
-- Append-only. One row per detected whale event from the LM63C pipeline.
-- `payload` carries the full original event dict for forward compatibility
-- (new fields land in payload before they become first-class columns).

create table if not exists public.whale_events (
  id              uuid        primary key default gen_random_uuid(),
  whale_event_id  text,
  source_type     text,
  symbol          text        not null,
  exchange        text,
  chain           text,
  side            text,
  amount          numeric,
  price           numeric,
  notional_usd    numeric,
  severity        text,
  confidence      numeric,
  reason          text,
  event_ts        timestamptz,
  wallet          text,
  tx_hash         text,
  payload         jsonb       not null default '{}'::jsonb,
  created_at      timestamptz not null default now()
);

comment on table public.whale_events is
  'LM63G — append-only whale event store. Writers use the service-role key; '
  'browsers must never insert/update/delete here directly. Anon access is '
  'denied by RLS; expose via a dedicated API route if/when needed.';

comment on column public.whale_events.whale_event_id is
  'Deterministic 16-char id from the LM52A engine. May be null for legacy rows; '
  'when present, must be globally unique (see whale_events_whale_event_id_uidx).';
comment on column public.whale_events.payload is
  'Full original event dict (jsonb). Carries forward-compatible fields not yet '
  'promoted to columns.';
comment on column public.whale_events.event_ts is
  'Trade/transfer timestamp from the source feed (NOT created_at).';
comment on column public.whale_events.created_at is
  'Server insert time — useful for replay/ordering, not for analysis.';


-- ── Unique constraint on whale_event_id ──────────────────────────────────────
-- A real UNIQUE *constraint* (not a partial unique index) is required for
-- PostgREST's `?on_conflict=whale_event_id` / `Prefer: resolution=*` headers
-- to work — PostgREST needs a constraint or a *complete* unique index it can
-- target. The LM52A id is deterministic, so this also enforces idempotency
-- on retries from the Python writer.
--
-- Multiple NULL values are still allowed: by default Postgres treats NULLs
-- as distinct in unique constraints, so legacy / imported rows without a
-- whale_event_id remain insertable.
--
-- If an earlier deployment created the LM63G partial unique index
-- (whale_events_whale_event_id_uidx), drop it first — the new constraint
-- supersedes it. Wrapped in IF EXISTS so this stays a no-op on fresh DBs.

drop index if exists public.whale_events_whale_event_id_uidx;

do $$
begin
  if not exists (
    select 1
      from pg_constraint
     where conname  = 'whale_events_whale_event_id_key'
       and conrelid = 'public.whale_events'::regclass
  ) then
    alter table public.whale_events
      add constraint whale_events_whale_event_id_key
      unique (whale_event_id);
  end if;
end
$$;


-- ── Query indexes (most-recent-first reads) ──────────────────────────────────

create index if not exists whale_events_symbol_event_ts_idx
  on public.whale_events (symbol, event_ts desc);

create index if not exists whale_events_exchange_event_ts_idx
  on public.whale_events (exchange, event_ts desc);

create index if not exists whale_events_severity_event_ts_idx
  on public.whale_events (severity, event_ts desc);

create index if not exists whale_events_created_at_idx
  on public.whale_events (created_at desc);


-- ── Row-level security ───────────────────────────────────────────────────────
-- Enable RLS and provide NO policies. With RLS on and no policies, anon /
-- authenticated keys get nothing (default deny). The service-role key always
-- bypasses RLS by design. Wrapping in DO blocks keeps the script idempotent
-- across reruns.

do $$
begin
  execute 'alter table public.whale_events enable row level security';
end
$$;

-- (No policies are created on purpose. If a future API route needs anon
-- reads, add the narrowest possible policy here — never grant write access
-- to anon / authenticated.)


-- ── End of file ──────────────────────────────────────────────────────────────
