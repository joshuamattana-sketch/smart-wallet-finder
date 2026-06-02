# Live heatmap payloads

Local stand-in for the **production live** heatmap store. Files here are read by
`lib/heatmap-live-loader.ts` to serve `GET /api/heatmap?source=live`.

> This is a local dev convenience, **not** production infrastructure. The real
> live source (object storage / Supabase / hosted worker) is described in
> `../../docs/PRODUCTION_LIVE_HEATMAP_PLAN.md`. No Supabase or external network
> call is made from Next.js.

## Naming convention

```
{SYMBOL}_{timeframe}.json
```

e.g. `BTCUSDT_5m.json`, `ETHUSDT_1h.json` (SYMBOL upper-case, timeframe
lower-case).

## How to populate it

Run the local live writer with a live (or both) target:

```bash
# from the repo root — write live payloads only
python scripts/run_local_heatmap_live.py \
  --symbols BTCUSDT,ETHUSDT,SOLUSDT --timeframes 5m,15m,1h \
  --active-symbol BTCUSDT --active-interval 2 --background-interval 10 \
  --target live

# write both the fixture (heatmap/) and live (live/) folders at once
python scripts/run_local_heatmap_live.py --symbols BTCUSDT --target both
```

Payloads written to the **live** target carry live-writer metadata so the API
resolves them as `live`:

- `meta.source` / `meta.dataSource` = `"local_live_writer"`
- `meta.resolvedSource` = `"live"`, `meta.writerTarget` = `live` | `both`
- `meta.isDemo` = `false`, `meta.stale` = `false`, plus `meta.liveUpdatedAt`

With the writer running, `GET /api/heatmap?source=live&symbol=BTCUSDT&timeframe=5m`
returns `meta.resolvedSource = "live"`; otherwise it falls back to fixture, then
mock.
