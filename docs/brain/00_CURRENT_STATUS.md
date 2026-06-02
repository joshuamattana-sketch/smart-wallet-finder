# Lumora Current Status

Last updated: update manually after each major milestone.

## Current Milestone
LM41A in progress:
Prepare hosted heatmap worker mode
(writer can run forever as a hosted process; PC no longer required).

Previous: LM39B — Supabase live updates stabilized end-to-end
(writer → Supabase → API → Dashboard/Terminal/Liquidity Map).

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

## Current Live Flow
Binance Spot REST
→ Python writer (`scripts/run_local_heatmap_live.py`)
→ Supabase `heatmap_latest_payloads`
→ `/api/heatmap?source=live`
→ Dashboard / Terminal / Liquidity Map
Fallback chain: Supabase live → local live file → fixture → mock.

## Current Unresolved Issue
Diagnosis = Cause B (API read/refresh layer).
- Writer/Supabase confirmed updating (not Cause A).
- UI polling hardened in prior LM39B patches (not the root Cause C):
  `source=live` + `_ts` + `cache:"no-store"`, persistent 2s/9s intervals,
  functional setState (Dashboard), AbortController (Terminal),
  visibilitychange immediate refresh.
- API route now forced non-cacheable
  (`dynamic="force-dynamic"`, `revalidate=0`,
  `Cache-Control: no-store, no-cache, must-revalidate`).
- To verify in production: confirm Dashboard/Terminal update without manual
  refresh and the API response header carries `Cache-Control: no-store`.
  If a fallback still occurs, inspect safe debug meta
  (`supabaseConfigured / supabaseAttempted / supabaseStatus / supabaseError`).

## SECURITY — Action Required
- The Supabase service-role key was exposed in screenshots and MUST be rotated.
- After rotating, update the key only in environment variables
  (shell / Vercel project env) — never in committed files.
- Until rotated, treat the old key as compromised.

## LM41A — Hosted Worker Mode (this patch)
- Writer now supports `--forever`: runs indefinitely, ignores `--samples`,
  exits cleanly on Ctrl+C / SIGINT.
- Startup banner prints mode / target / symbols / timeframes / intervals /
  supabase=configured|not (no secrets are printed).
- In `--forever` mode, an empty initial collection does not exit 1 — the
  worker is expected to be long-running.
- Recommended hosted command:
  `python scripts/run_local_heatmap_live.py --forever --target supabase \
      --symbols BTCUSDT,ETHUSDT,SOLUSDT --timeframes 5m,15m,1h \
      --active-symbol BTCUSDT --active-interval 2 --background-interval 10`
- Required env vars (shell / hosting platform only, never in files):
  `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`.
- Not deployed yet — code-ready only.

## Current Priority
- Pick a hosting target (Fly.io / Railway / Render / VPS) and deploy
  the `--forever --target supabase` worker.
- Rotate the exposed Supabase service-role key before deploying.
- Confirm LM39B live refresh continues to work end-to-end with the
  hosted worker driving Supabase.

## Do Not Commit
- `.env`
- `.env.local`
- `lumora-web/fixtures/live/*.json`
- `lumora-web/fixtures/heatmap/*.json`
- Supabase service role keys
- Any secrets