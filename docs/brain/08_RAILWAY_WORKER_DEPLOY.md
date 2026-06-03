# Railway Worker Deploy

How to deploy the heatmap WebSocket worker to Railway.

## Prerequisites

- GitHub repo connected to Railway
- Supabase project with `heatmap_frame_history` and `liquidity_wall_history` tables created (run `supabase/heatmap_history.sql` in Supabase SQL editor first)
- `websocket-client` in `requirements.txt`

## Step 1: Create Railway Project

1. Go to https://railway.app and sign in
2. Click **New Project** > **Deploy from GitHub repo**
3. Select your wallet-finder repo
4. Railway will detect Python and start building

## Step 2: Select Worker Config

If Railway asks which config to use, or if you have multiple services:

1. Go to your service **Settings** tab
2. Under **Config as Code**, set the path to `railway.worker.toml`
3. This tells Railway to use the worker start command instead of a web server

## Step 3: Add Environment Variables

Go to **Variables** tab in your Railway service and add:

### Required

| Variable | Value |
|---|---|
| `SUPABASE_URL` | Your Supabase project URL (from Supabase dashboard > Settings > API) |
| `SUPABASE_SERVICE_ROLE_KEY` | Your Supabase service role key (from Supabase dashboard > Settings > API) |

### Worker Config

| Variable | Starter Value | Description |
|---|---|---|
| `WORKER_SYMBOLS` | `BTCUSDT,ETHUSDT,SOLUSDT` | Comma-separated trading pairs |
| `WORKER_EXCHANGE` | `binance` | Exchange name |
| `WORKER_TIMEFRAMES` | `5m` | Comma-separated timeframes |
| `WORKER_HISTORY_TARGET` | `supabase` | Where to write history rows |
| `WORKER_HISTORY_INTERVAL` | `10` | Seconds between history appends |
| `WORKER_MAX_CELLS` | `300` | Max cells per history row |
| `WORKER_MAX_WALLS` | `50` | Max walls per history row |
| `WORKER_DISCORD_ENABLED` | `false` | Enable Discord alerts (true/false) |

### Optional

| Variable | Description |
|---|---|
| `DISCORD_WEBHOOK_URL` | Discord webhook URL for alerts (only needed if `WORKER_DISCORD_ENABLED=true`) |

**Never paste real secrets into docs or code files.** Only set them in Railway's Variables UI.

## Step 4: Deploy

1. After adding env vars, Railway will auto-redeploy
2. Or click **Deploy** manually if needed
3. The worker runs: `python scripts/run_binance_ws_heatmap_live.py --use-env-config --target supabase --forever --range-mode wide`

## Step 5: Check Logs

1. Go to **Deployments** tab
2. Click the active deployment
3. You should see:
   - `run_binance_ws_heatmap_live startup:` with your config
   - `ws connecting:` followed by `ws connected`
   - `write #1`, `write #2`, etc. appearing every second

If you see `error:` lines, check your env vars.

## Step 6: Verify Supabase History Rows

Open the Supabase SQL editor and run:

```sql
select * from heatmap_frame_history order by created_at desc limit 10;
```

You should see rows appearing every `WORKER_HISTORY_INTERVAL` seconds per symbol per timeframe.

To check wall history:

```sql
select * from liquidity_wall_history order by created_at desc limit 10;
```

## Troubleshooting

| Problem | Fix |
|---|---|
| `SUPABASE_URL` error | Check the variable is set correctly in Railway, no trailing slash |
| `ws disconnected` then reconnects | Normal — Binance drops idle connections, worker reconnects automatically |
| No history rows in Supabase | Check `WORKER_HISTORY_TARGET=supabase` is set, and that you ran `heatmap_history.sql` |
| Build fails | Make sure `websocket-client` is in `requirements.txt` |
| Worker restarts repeatedly | Check logs for the error — usually a missing env var |
