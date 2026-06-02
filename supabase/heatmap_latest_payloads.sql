-- supabase/heatmap_latest_payloads.sql
-- Schema for the latest-payload store used by:
--   - scripts/run_local_heatmap_live.py with --target supabase|live-and-supabase|all
--   - lumora-web/lib/heatmap-live-loader.ts (read via PostgREST, server-side only)
--
-- One row per (symbol, exchange, timeframe) holding the most recently built
-- heatmap payload (the same JSON body GET /api/heatmap returns).
--
-- This file is the canonical schema. It was applied to the connected Supabase
-- project (smart-wallet-finder / tpbexchxfssdhrhsdncu) via MCP migration
-- `create_heatmap_latest_payloads`. Re-running the file is safe (CREATE IF NOT
-- EXISTS / CREATE OR REPLACE / DROP TRIGGER IF EXISTS).
--
-- Security model:
--   * RLS is enabled with NO policies → only the service-role key (or direct
--     DB) can read or write. The anon/authenticated keys used by browser
--     clients are denied by default.
--   * The Next.js API route reads via the service-role key on the server
--     (process.env.SUPABASE_SERVICE_ROLE_KEY). The browser only talks to
--     /api/heatmap; the service-role key is never shipped to the client.
--   * The live writer (Python) uses the same service-role key to upsert.
--   * Never commit Supabase keys / project URLs to the repo.

create table if not exists public.heatmap_latest_payloads (
  id               uuid primary key default gen_random_uuid(),
  symbol           text not null,
  exchange         text not null default 'binance_spot',
  timeframe        text not null,
  payload          jsonb not null,
  live_updated_at  timestamptz not null,
  writer_source    text,
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now(),
  constraint heatmap_latest_payloads_symbol_exchange_timeframe_uniq
    unique (symbol, exchange, timeframe)
);

create index if not exists heatmap_latest_payloads_lookup_idx
  on public.heatmap_latest_payloads (symbol, exchange, timeframe);

create index if not exists heatmap_latest_payloads_live_updated_at_idx
  on public.heatmap_latest_payloads (live_updated_at desc);

-- Keep updated_at in sync on every update / upsert.
create or replace function public.heatmap_latest_payloads_touch_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at := now();
  return new;
end
$$;

drop trigger if exists heatmap_latest_payloads_touch_updated_at
  on public.heatmap_latest_payloads;

create trigger heatmap_latest_payloads_touch_updated_at
  before update on public.heatmap_latest_payloads
  for each row execute function public.heatmap_latest_payloads_touch_updated_at();

-- RLS: enabled, no policies → only service-role / direct DB can read or write.
alter table public.heatmap_latest_payloads enable row level security;
