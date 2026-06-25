-- supabase/heatmap_io_cleanup.sql
-- One-off Disk IO recovery + ongoing retention for the heatmap pipeline.
--
-- CONTEXT: the free-tier project smart-wallet-finder (tpbexchxfssdhrhsdncu) ran
-- out of Disk IO budget and became unresponsive. Cause: the live writer upserted
-- ~414 KB JSONB payloads every 10s × N symbols (range-mode "wide") and appended
-- to heatmap_frame_history continuously, while Supabase Realtime decoded every
-- one of those large WAL changes. This script shrinks the append-only history
-- tables (less bloat → less IO) and checks the realtime publication.
--
-- RUN ORDER (only once the DB is responsive again — i.e. AFTER the compute
-- add-on upgrade, or after the writer is stopped and IO budget has refilled):
--   1. Stop the Railway heatmap worker first (so it isn't writing while we prune).
--   2. Run sections 1–2 below (batched deletes — gentle on IO).
--   3. Run section 3 (ANALYZE).
--   4. Run the VACUUM in section 4 SEPARATELY (cannot run in a transaction;
--      use plain VACUUM, NOT VACUUM FULL — full is very IO-heavy).
--   5. Review section 5 (realtime publication) and apply if appropriate.
-- Idempotent and safe to re-run.

-- ── 1. Retention: heatmap_frame_history (keep last 3 days) ─────────────────────
-- Batched so no single statement scans/deletes the whole table at once (which
-- would time out on a throttled instance). Deletes 5k rows per loop.
do $$
declare
  cutoff timestamptz := now() - interval '3 days';
  deleted integer;
begin
  loop
    delete from public.heatmap_frame_history
    where id in (
      select id from public.heatmap_frame_history
      where frame_ts < cutoff
      limit 5000
    );
    get diagnostics deleted = row_count;
    raise notice 'heatmap_frame_history: deleted % rows', deleted;
    exit when deleted = 0;
  end loop;
end $$;

-- ── 2. Retention: liquidity_wall_history (keep last 3 days) ────────────────────
do $$
declare
  cutoff timestamptz := now() - interval '3 days';
  deleted integer;
begin
  loop
    delete from public.liquidity_wall_history
    where id in (
      select id from public.liquidity_wall_history
      where frame_ts < cutoff
      limit 5000
    );
    get diagnostics deleted = row_count;
    raise notice 'liquidity_wall_history: deleted % rows', deleted;
    exit when deleted = 0;
  end loop;
end $$;

-- ── 3. Refresh planner stats ──────────────────────────────────────────────────
analyze public.heatmap_frame_history;
analyze public.liquidity_wall_history;

-- ── 4. Reclaim space — RUN SEPARATELY, NOT inside a transaction ────────────────
-- vacuum (analyze) public.heatmap_frame_history;
-- vacuum (analyze) public.liquidity_wall_history;
-- (Do NOT use VACUUM FULL on the throttled/free instance — it rewrites the whole
--  table and spikes Disk IO. Plain VACUUM is enough to mark space reusable.)

-- ── 5. Realtime publication — inspect, then trim if needed ─────────────────────
-- The Realtime WAL decode (realtime.list_changes) was taking 10–15s per call.
-- Only tables the app actually subscribes to should be in the publication:
--   - heatmap_latest_payloads  (liquidity-map realtime, LM78B)  — KEEP
--   - whale_events             (whale-alerts realtime,  LM78A)  — KEEP
-- The append-only history tables must NOT be published (huge write volume).
--
-- Inspect first:
--   select schemaname, tablename
--   from pg_publication_tables
--   where pubname = 'supabase_realtime'
--   order by tablename;
--
-- If heatmap_frame_history / liquidity_wall_history appear, remove them:
--   alter publication supabase_realtime drop table public.heatmap_frame_history;
--   alter publication supabase_realtime drop table public.liquidity_wall_history;
--
-- (With range-mode "standard" the latest_payloads rows are much smaller, so the
--  remaining realtime decode cost drops sharply on its own.)

-- ── 6. Optional: schedule ongoing retention with pg_cron ──────────────────────
-- Prevents the tables from growing unbounded again. Requires the pg_cron
-- extension (enable in Dashboard → Database → Extensions).
--   select cron.schedule(
--     'heatmap_history_retention', '17 * * * *',
--     $$delete from public.heatmap_frame_history where frame_ts < now() - interval '3 days'$$
--   );
