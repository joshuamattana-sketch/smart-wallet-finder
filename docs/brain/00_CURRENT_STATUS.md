# Lumora Current Status

Last updated: update manually after each major milestone.

## Current Milestone
LM45 in progress — Heatmap History / Wall Persistence foundation:
- Append-only Supabase tables `heatmap_frame_history` +
  `liquidity_wall_history` (see `supabase/heatmap_history.sql`).
- New helper module `services/heatmap_history_persistence.py`.
- WS collector gains `--history-target none|supabase`,
  `--history-interval`, `--history-max-cells`, `--history-max-walls`.
- Off by default — existing latest-payload behaviour unchanged.
- 1230 tests passing; history writes fail-isolated from latest writes.

Previous completed milestones:
- LM44 — Trader-grade liquidity aggregation (zones, keyZones, wall scoring v2)
- LM43C — Smart viewport (wide/macro ranges stay readable)
- LM43B — Wide range actually visible (cell.price_bucket, canvas fix)
- LM43  — Analysis-grade price range presets (tight/standard/wide/macro)
- LM42C — UI polling fix post-multi-symbol WebSocket (heatmapResolvedStatus)
- LM42B — Multi-symbol WebSocket collector (combined stream)
- LM42A — BTCUSDT Binance WebSocket collector MVP
- LM41A — Hosted worker mode (--forever flag, startup banner)
- LM39B — Supabase live updates stabilized end-to-end
- LM38  — Supabase latest heatmap payload storage

## Completed
- Lumora Web deployed on Vercel.
- Next.js app with Dashboard, Terminal, Liquidity Map, Whale Alerts, Paper Trading.
- `/api/heatmap` supports `mock`, `fixture`, and `live`.
- Local live writer supports multi-symbol and multi-timeframe.
- Active market fast mode works.
- Price path overlay added to Liquidity Map.
- Dashboard, Terminal, and Liquidity Map can use live source locally.
- Writer can write local live payloads to `lumora-web/fixtures/live`.
- Production live source skeleton exists.

## Confirmed Supabase State (LM38 / LM39B)
- Supabase table `heatmap_latest_payloads` exists
  (unique on symbol/exchange/timeframe; indexes + RLS in place).
- Writer can write/upsert to Supabase
  (`--target supabase | live-and-supabase | all`).
- Rows present for BTCUSDT/ETHUSDT/SOLUSDT × 5m/15m/1h.
- `/api/heatmap?source=live` can return
  `dataSource="supabase_live"`, `resolvedSource="live"`,
  `isFallback=false`, `stale=false`.
- Loader reads latest row
  (`order=live_updated_at.desc`, exact symbol/exchange/timeframe filter)
  and uses `live_updated_at` as the authoritative freshness timestamp.

## Current Live Flow (while PC is running the collector)
Binance Spot WebSocket (bookTicker)
→ `scripts/run_binance_ws_heatmap_live.py` (LM42A/B WS collector)
→ Supabase `heatmap_latest_payloads`
→ `/api/heatmap?source=live` (Vercel, force-dynamic, no-store)
→ Dashboard / Terminal / Liquidity Map (2s / 9s polling)
Fallback chain: Supabase live → local live file → fixture → mock.

Active local command:
```
python scripts/run_binance_ws_heatmap_live.py \
    --symbols BTCUSDT,ETHUSDT,SOLUSDT \
    --timeframes 5m,15m,1h \
    --write-interval 1 --max-frames 1200 \
    --target supabase --forever --range-mode wide
```
Required shell env (never in files): SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY

## Hosted Worker — Deployment Postponed
- Code is 100% ready (`--forever --target supabase`, startup banner, clean
  Ctrl+C, no secrets in files).
- Railway Free plan blocks new resource creation and requires upgrade.
- Decision: do not pay/upgrade yet.
- PC must stay on for live data until a hosted worker is deployed.
- Next deployment target options: Railway (paid), Render, Fly.io, VPS.

## LM41A — Hosted Worker Mode (code-complete, not deployed)
- Writer now supports `--forever`: runs indefinitely, ignores `--samples`,
  exits cleanly on Ctrl+C / SIGINT.
- Startup banner prints mode / target / symbols / timeframes / intervals /
  supabase=configured|not (no secrets printed).
- Recommended hosted command (REST writer):
  `python scripts/run_local_heatmap_live.py --forever --target supabase \
      --symbols BTCUSDT,ETHUSDT,SOLUSDT --timeframes 5m,15m,1h \
      --active-symbol BTCUSDT --active-interval 2 --background-interval 10`
- Recommended hosted command (WS collector, preferred):
  `python scripts/run_binance_ws_heatmap_live.py \
      --symbols BTCUSDT,ETHUSDT,SOLUSDT --timeframes 5m,15m,1h \
      --write-interval 1 --max-frames 1200 \
      --target supabase --forever --range-mode wide`
- Required env vars (hosting platform only, never in files):
  SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY

## SECURITY — Action Required
- The Supabase service-role key was exposed in screenshots and MUST be rotated.
- After rotating, update the key only in environment variables
  (shell / Vercel project env) — never in committed files.
- Until rotated, treat the old key as compromised.

## Current Priority
1. Keep PC running the WS collector for live data until a hosted worker
   is deployed.
2. Next product step: LM45 Heatmap History / Wall Persistence
   (Supabase schema for historical snapshots, wall trend analysis).
3. Hosted Worker deployment — when ready to pay/commit:
   Railway (upgrade required), Render Free, Fly.io Free, or any VPS.
4. Supabase service-role key rotation remains an open security action item.

## Do Not Commit
- `.env`
- `.env.local`
- `lumora-web/fixtures/live/*.json`
- `lumora-web/fixtures/heatmap/*.json`
- Supabase service role keys
- Any secrets