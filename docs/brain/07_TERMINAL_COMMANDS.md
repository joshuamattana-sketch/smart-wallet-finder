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

## LM63B Binance aggTrade Collector Tests

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder"
python -m pytest tests/connectors/test_binance_trade_stream.py
python -m compileall services scripts tests
```

## LM63B Binance aggTrade Smoke Runner (stdout only · no Supabase · no Discord)

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder"
python scripts/run_binance_trade_stream_smoke.py --symbols BTCUSDT,ETHUSDT,SOLUSDT --min-notional 250000
```

Requires `pip install websocket-client` for the live WS transport.

## LM63C Whale Live Pipeline Smoke (aggTrade → whale → filter → Discord)

Default: observe only, stops after 10 sendable events. **No Discord send.**

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder"
python scripts/run_binance_trade_stream_smoke.py --symbols BTCUSDT,ETHUSDT,SOLUSDT --min-notional 250000 --max-events 10
```

Tune confidence floor:

```powershell
python scripts/run_binance_trade_stream_smoke.py --min-confidence 0.7
```

Inspect the Discord payload without sending:

```powershell
python scripts/run_binance_trade_stream_smoke.py --print-payload --max-events 3
```

Actually POST to Discord (need a real webhook URL — never commit it):

```powershell
$env:LUMORA_WHALE_DISCORD = "https://discord.com/api/webhooks/..."
python scripts/run_binance_trade_stream_smoke.py --send-discord --discord-webhook-url $env:LUMORA_WHALE_DISCORD --max-events 5
```

Safe behaviors:
- `--send-discord` without `--discord-webhook-url` exits with code 2 (no send, no crash).
- Invalid Binance symbols are warned and skipped.
- `--max-events 0` disables the cap (run until Ctrl+C).

## LM63D Per-Symbol Whale Thresholds (Tests + Smoke Wiring)

Built-in presets (services/whale_symbol_thresholds.py):

| Symbol   | min      | high     | extreme   | min_conf |
|----------|----------|----------|-----------|----------|
| BTCUSDT  | 250 000  | 750 000  | 2 000 000 | 0.60     |
| ETHUSDT  |  75 000  | 250 000  | 1 000 000 | 0.60     |
| SOLUSDT  |  50 000  | 150 000  |   500 000 | 0.60     |
| BNBUSDT  |  75 000  | 250 000  |   750 000 | 0.60     |
| LINKUSDT |  25 000  | 100 000  |   300 000 | 0.60     |
| DOGEUSDT |  25 000  | 100 000  |   300 000 | 0.60     |
| (any other) | 100 000 | 500 000 | 1 000 000 | 0.60   |

Run the threshold tests:

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder"
python -m pytest tests/test_whale_symbol_thresholds.py tests/connectors/test_binance_trade_stream.py
python -m compileall services scripts tests
```

Smoke CLI uses per-symbol thresholds **by default**:

```powershell
python scripts/run_binance_trade_stream_smoke.py --symbols BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT
```

Opt out (global $250k floor for every symbol):

```powershell
python scripts/run_binance_trade_stream_smoke.py --no-use-symbol-thresholds
```

`--min-notional` and `--min-confidence` still override the per-symbol values when explicitly passed.

## LM63E Whale Event Local Journal (JSONL · append-only · off by default)

Run the journal tests:

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder"
python -m pytest tests/test_whale_event_journal.py tests/connectors/test_binance_trade_stream.py
python -m compileall services scripts tests
```

Stream and journal every detected event to a local file (no Discord):

```powershell
python scripts/run_binance_trade_stream_smoke.py --symbols BTCUSDT,ETHUSDT,SOLUSDT --journal-path logs/whales.jsonl
```

Journal row shape (one JSON object per line):

```json
{
  "event": {"whale_event_id": "…", "symbol": "BTCUSDT", "side": "buy", "notional_usd": 1400000.0, "severity": "extreme", "…": "…"},
  "meta":  {"should_send": true, "filter_reason": "extreme severity always sent", "blocked_low_conf": false, "sent_attempted": false},
  "written_at": "2026-06-08T12:34:56.789012+00:00"
}
```

Read newest-first programmatically:

```python
from services.whale_event_journal import read_whale_event_journal
rows = read_whale_event_journal("logs/whales.jsonl", limit=20)
```

Safe behaviors:
- `--journal-path` defaults to empty → **no file is written**.
- Parent directories are created on demand.
- Filesystem errors are swallowed and counted as `journal_failures` — the live whale pipeline keeps running.

## LM63F Whale Feed API + Website (local journal → /api/whale-alerts)

Default journal location read by the website:

```
<repo_root>/data/whale_events.jsonl
```

Generate it by running the LM63E pipeline with `--journal-path`:

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder"
python scripts/run_binance_trade_stream_smoke.py --symbols BTCUSDT,ETHUSDT,SOLUSDT --journal-path data/whale_events.jsonl --max-events 0
```

Then run the website:

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder\lumora-web"
npm run dev
```

Visit `http://localhost:3000/whale-alerts` — the page will show a green `JOURNAL ●` badge when reading real local events, or an amber `DEMO` badge with mock data when the journal is missing or empty. The API itself is callable directly:

```
GET /api/whale-alerts?limit=50
```

returning JSON with `{ data_source: "journal"|"mock", journal_row_count, alerts: [...], note? }`.

Vercel-safe: the API route is `dynamic = "force-dynamic"` so it never tries to pre-render at build time, and missing/unreadable journal files transparently fall back to mock — no build or runtime crash.

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

## LM53D/E Worker Health Tests

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder"
python -m pytest tests/test_worker_health.py
python -m compileall services tests
```

## LM59 Local Status Check

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder"
python scripts/run_local_status_check.py
python scripts/run_local_status_check.py --json
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