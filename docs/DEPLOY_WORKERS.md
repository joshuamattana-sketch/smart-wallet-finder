# Deploying the live data workers (24/7)

These workers stream public Binance market data and write it to Supabase so the
web app shows **fresh** heatmap + whale data. They are **data only** — no
trading, no MetaTrader, no orders.

What runs: `scripts/run_data_workers.py` (a supervisor) keeps two writers alive:
- order-book **heatmap** → `heatmap_latest_payloads`
- **whale events** → `whale_events`

## Option A — Render (recommended, simplest)

Cost: a background worker is a paid tier (~$7/month). There is no free always-on
worker tier.

1. Get your Supabase **service_role** key:
   Supabase dashboard → your project → **Settings → API** → copy the
   **`service_role`** secret (NOT the anon key).
2. Go to **render.com** → sign up / log in → **New + → Blueprint**.
3. Connect this GitHub repo. Render reads `render.yaml` and creates the
   `lumora-data-workers` service.
4. Open the service → **Environment** → set:
   - `SUPABASE_URL` = `https://tpbexchxfssdhrhsdncu.supabase.co`
   - `SUPABASE_SERVICE_ROLE_KEY` = *(paste the service_role secret here)*
5. **Deploy**. Watch the logs — you should see `[supervisor] starting 'heatmap'`
   and `'whale'`, then heartbeat lines. Within a minute the web app's heatmap /
   whale pages show fresh data.

The service_role key lives only in Render's encrypted env — never in the repo,
never in chat.

## Option B — Railway / Fly / any VPS

Same idea, container/process running `python scripts/run_data_workers.py` with
`pip install -r requirements-worker.txt` and the same two env vars set in the
host's secrets. Railway: New Project → Deploy from repo → set start command +
env vars. Fly/VPS: run it under a process manager (systemd / `fly deploy`).

## Tuning (optional env vars)

| Var | Default | Meaning |
|-----|---------|---------|
| `HEATMAP_SYMBOL` | `BTCUSDT` | symbol for the order-book heatmap |
| `HEATMAP_TIMEFRAMES` | `5m,15m,1h` | heatmap timeframes |
| `HEATMAP_WRITE_INTERVAL` | `2` | seconds between heatmap writes |
| `WHALE_SYMBOLS` | `BTCUSDT,ETHUSDT,SOLUSDT` | symbols for whale events |

## Stopping / pausing

Suspend or delete the service in the host dashboard. The web app keeps working —
it just shows the last-written (increasingly stale) data, with the stale
indicator on.
