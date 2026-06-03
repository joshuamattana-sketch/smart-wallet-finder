# Terminal Commands

## Main Folder
`C:\Users\Joshua\Desktop\wallet finder`

Use for:
- Python scripts
- tests
- git from repo root

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder"

## Web Folder

`C:\Users\Joshua\Desktop\wallet finder\lumora-web`

Use for:

- Next.js build
- Next.js dev server

cd "C:\Users\Joshua\Desktop\wallet finder\lumora-web"npm run buildnpm run dev
```

```

## Python Tests

cd "C:\Users\Joshua\Desktop\wallet finder"python -m pytest tests/test_local_heatmap_live.pypython -m compileall scripts services tests

## LM46 Wall Event Detector Tests

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder"
python -m pytest tests/test_liquidity_wall_events.py
python -m compileall services tests
```

## LM47 Wall Persistence Feature Tests

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder"
python -m pytest tests/test_wall_persistence_features.py
python -m compileall services tests
```

## LM48 Setup Classifier v1 Tests

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder"
python -m pytest tests/test_setup_classifier.py
python -m compileall services tests
```

## LM49 Signal Object Builder v1 Tests

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder"
python -m pytest tests/test_signal_builder.py
python -m compileall services tests
```

## LM50 Signal Journal Foundation Tests

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder"
python -m pytest tests/test_signal_journal.py
python -m compileall services tests
```

```

```

## WebSocket Collector — Supabase (PRIMARY, recommended)

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder"
python scripts/run_binance_ws_heatmap_live.py --symbols BTCUSDT,ETHUSDT,SOLUSDT --timeframes 5m,15m,1h --write-interval 1 --max-frames 1200 --target supabase --forever --range-mode wide
```

Requires SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in the shell environment.
Requires: pip install websocket-client (one-time)

## WebSocket Collector — Env Config (LM53B)

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder"
$env:WORKER_SYMBOLS = "BTCUSDT,ETHUSDT,SOLUSDT"
$env:WORKER_TIMEFRAMES = "5m,15m,1h"
$env:WORKER_HISTORY_TARGET = "supabase"
$env:WORKER_HISTORY_INTERVAL = "10"
$env:WORKER_MAX_CELLS = "300"
$env:WORKER_MAX_WALLS = "50"
python scripts/run_binance_ws_heatmap_live.py --use-env-config --target supabase --forever --range-mode wide
```

Explicit CLI args (--symbols, --timeframes, etc.) override env values when both are provided.

## WebSocket Collector — Supabase + LM45 History (heatmap_frame_history + liquidity_wall_history)

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder"
python scripts/run_binance_ws_heatmap_live.py --symbols BTCUSDT,ETHUSDT,SOLUSDT --timeframes 5m,15m,1h --write-interval 1 --max-frames 1200 --target supabase --forever --range-mode wide --history-target supabase --history-interval 10
```

Run `supabase/heatmap_history.sql` once in the Supabase SQL editor (or via
MCP migration) before enabling --history-target supabase.

## REST Writer — Supabase (fallback / alternative)

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder"
python scripts/run_local_heatmap_live.py --symbols BTCUSDT,ETHUSDT,SOLUSDT --active-symbol BTCUSDT --timeframes 5m,15m,1h --active-interval 2 --background-interval 10 --forever --max-frames 900 --target supabase
```

## Local Live Writer (fixtures/live only — no Supabase)

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder"
python scripts/run_local_heatmap_live.py --symbols BTCUSDT,ETHUSDT,SOLUSDT --active-symbol BTCUSDT --timeframes 5m,15m,1h --active-interval 2 --background-interval 10 --samples 999999 --max-frames 900 --target live
```

## Local + Supabase (both targets)

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder"
python scripts/run_local_heatmap_live.py --symbols BTCUSDT,ETHUSDT,SOLUSDT --active-symbol BTCUSDT --timeframes 5m,15m,1h --active-interval 2 --background-interval 10 --samples 999999 --max-frames 900 --target both
```

```

## Railway Deploy (LM53C)

See `docs/brain/08_RAILWAY_WORKER_DEPLOY.md` for full beginner guide.

Config file: `railway.worker.toml`

Start command: `python scripts/run_binance_ws_heatmap_live.py --use-env-config --target supabase --forever --range-mode wide`

Verify history rows:
```sql
select * from heatmap_frame_history order by created_at desc limit 10;
```

## LM53D Worker Health Tests

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder"
python -m pytest tests/test_worker_health.py
python -m compileall services tests
```

## Git Rules

Always check: git status

```

```

Never use: git add .

```

```

Always add explicit files only.

Never commit:

- `.env`
- `.env.local`
- `lumora-web/fixtures/live/*.json`
- `lumora-web/fixtures/heatmap/*.json`
- Supabase keys

```
## Commit Brain Notes

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder"
git status
git add docs/brain
git commit -m "Add Lumora project brain notes"
git push
```