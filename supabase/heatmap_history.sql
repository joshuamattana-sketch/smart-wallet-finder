-- supabase/heatmap_history.sql
-- LM45 — Heatmap history + wall persistence foundation.
--
-- These tables are APPEND-ONLY. They sit alongside heatmap_latest_payloads
-- (which keeps the single most recent payload per symbol/exchange/timeframe)
-- and let downstream code reconstruct heatmap evolution over time, detect
-- wall appearance/disappearance, sweeps, absorption, etc. — features for
-- later milestones. Nothing here changes how `/api/heatmap?source=live` reads
-- the latest payloads.
--
-- Re-running the file is safe (CREATE IF NOT EXISTS, idempotent).
--
-- Security model:
--   * RLS enabled with NO policies → only the service-role key (or direct
--     DB access) can read or write. Anon / authenticated keys are denied
--     by default. Consistent with heatmap_latest_payloads.
--   * Writers (Python collectors) and any future API readers must use the
--     service-role key on the server side. Browsers never see it.
--   * Never commit Supabase keys / project URLs to the repo.


-- ── heatmap_frame_history ─────────────────────────────────────────────────────
-- One row per (symbol, exchange, timeframe, frame_ts). `payload` is a
-- COMPACT body (top-N cells/walls + zones + meta + summary), not the full
-- heatmap matrix — see services/heatmap_history.py::build_compact_history_payload.

create table if not exists public.heatmap_frame_history (
  id            uuid        primary key default gen_random_uuid(),
  symbol        text        not null,
  exchange      text        not null default 'binance_spot',
  timeframe     text        not null,
  frame_ts      timestamptz not null,
  current_price numeric,
  price_min     numeric,
  price_max     numeric,
  range_mode    text,
  collector     text,
  cell_count    integer,
  wall_count    integer,
  zone_count    integer,
  payload       jsonb       not null,
  created_at    timestamptz not null default now()
);

create index if not exists heatmap_frame_history_symbol_tf_ts_idx
  on public.heatmap_frame_history (symbol, exchange, timeframe, frame_ts desc);

create index if not exists heatmap_frame_history_frame_ts_idx
  on public.heatmap_frame_history (frame_ts desc);

create index if not exists heatmap_frame_history_created_at_idx
  on public.heatmap_frame_history (created_at desc);

alter table public.heatmap_frame_history enable row level security;


-- ── liquidity_wall_history ────────────────────────────────────────────────────
-- One row per (symbol, exchange, timeframe, frame_ts, side, center_price).
-- Sourced from a frame's top-N zones (LM44 keyZones). Used later to track
-- wall persistence: appeared/pulled/strengthened/weakened over time.

create table if not exists public.liquidity_wall_history (
  id             uuid        primary key default gen_random_uuid(),
  symbol         text        not null,
  exchange       text        not null default 'binance_spot',
  timeframe      text        not null,
  frame_ts       timestamptz not null,
  side           text        not null,
  price_min      numeric,
  price_max      numeric,
  center_price   numeric,
  total_usd      numeric,
  strength_score numeric,
  wall_rank      integer,
  label          text,
  zone           jsonb,
  created_at     timestamptz not null default now()
);

create index if not exists liquidity_wall_history_symbol_tf_ts_idx
  on public.liquidity_wall_history (symbol, exchange, timeframe, frame_ts desc);

create index if not exists liquidity_wall_history_symbol_tf_center_idx
  on public.liquidity_wall_history (symbol, timeframe, center_price);

create index if not exists liquidity_wall_history_frame_ts_idx
  on public.liquidity_wall_history (frame_ts desc);

alter table public.liquidity_wall_history enable row level security;
