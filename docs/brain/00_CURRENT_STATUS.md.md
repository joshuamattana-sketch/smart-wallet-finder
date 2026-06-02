# Lumora Current Status

Last updated: update manually after each major milestone.

## Current Milestone
LM38 Compact in progress:
Supabase latest heatmap payload storage.

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

## Current Local Live Flow
Binance Spot REST
→ Python writer
→ local JSON files in `lumora-web/fixtures/live`
→ `/api/heatmap?source=live`
→ Dashboard / Terminal / Liquidity Map

## Current Priority
Finish LM38 Compact:
- Writer upserts latest payload to Supabase.
- API `source=live` reads Supabase first.
- Fallback chain remains:
  Supabase live → local live file → fixture → mock.

## Do Not Commit
- `.env`
- `.env.local`
- `lumora-web/fixtures/live/*.json`
- `lumora-web/fixtures/heatmap/*.json`
- Supabase service role keys
- Any secrets