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

## LM63G Whale Events Supabase Schema (append-only)

Schema file: `supabase/whale_events.sql`

Apply once in the Supabase SQL editor (or via MCP migration). Re-running is safe — every statement is idempotent (`create table if not exists`, `create index if not exists`, `do $$ … $$` for RLS).

After applying:
- Writers (the Python LM63 pipeline) connect with `SUPABASE_SERVICE_ROLE_KEY` to insert rows.
- Browsers must NEVER use the service-role key and must NEVER insert/update/delete this table directly.
- Anon access is denied by default (RLS on, no policies). Read access for the website should land later via a dedicated `/api/whale-alerts?source=supabase` route, not by adding a permissive policy.

Table summary:

```
public.whale_events
  id              uuid primary key
  whale_event_id  text             -- LM52A deterministic id
  source_type     text
  symbol          text not null
  exchange        text
  chain           text
  side            text
  amount          numeric
  price           numeric
  notional_usd    numeric
  severity        text
  confidence      numeric
  reason          text
  event_ts        timestamptz      -- trade time, not insert time
  wallet          text
  tx_hash         text
  payload         jsonb not null default '{}'::jsonb
  created_at      timestamptz not null default now()
```

Indexes:
- partial unique on `whale_event_id` (when not null) — idempotent inserts
- `(symbol, event_ts desc)` · `(exchange, event_ts desc)` · `(severity, event_ts desc)` · `(created_at desc)`

Run the SQL block:

```sql
\i supabase/whale_events.sql
```

Or paste the contents directly into the Supabase SQL editor and press Run.

### LM63G fix — real UNIQUE constraint on `whale_event_id`

The original LM63G schema declared `whale_event_id` uniqueness as a **partial unique index** (`WHERE whale_event_id IS NOT NULL`). PostgREST's `?on_conflict=whale_event_id` and `Prefer: resolution=*` headers require a real UNIQUE *constraint* (or a complete unique index), not a partial one, so writes from the LM63H Supabase writer fail without it.

`supabase/whale_events.sql` has been updated to:

1. `DROP INDEX IF EXISTS public.whale_events_whale_event_id_uidx;` (removes the old partial index from earlier deployments)
2. Add a real unique constraint inside a `DO` block that only runs when the constraint is missing:

```sql
do $$
begin
  if not exists (
    select 1
      from pg_constraint
     where conname  = 'whale_events_whale_event_id_key'
       and conrelid = 'public.whale_events'::regclass
  ) then
    alter table public.whale_events
      add constraint whale_events_whale_event_id_key
      unique (whale_event_id);
  end if;
end
$$;
```

Re-running `whale_events.sql` against an already-fixed database is a safe no-op. Re-running against a fresh database creates the table, drops the (absent) partial index harmlessly, and adds the constraint.

If you previously hot-fixed production with the exact same constraint name (`whale_events_whale_event_id_key`), the `IF NOT EXISTS` check leaves it untouched.

## LM63H Whale Events Supabase Writer (smoke CLI --target)

Run the writer tests:

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder"
python -m pytest tests/test_whale_event_supabase_writer.py tests/connectors/test_binance_trade_stream.py
python -m compileall services scripts tests
```

The smoke CLI now has a `--target` flag that controls where events land:

| `--target` | stdout | jsonl | supabase | both |
|---|---|---|---|---|
| stdout (default) | ✓ | — | — | — |
| jsonl | ✓ | ✓ | — | — |
| supabase | ✓ | — | ✓ | — |
| both | ✓ | ✓ | ✓ | — |

JSONL writes (when target ∈ {`jsonl`, `both`}, or when `--journal-path` is set as a back-compat shortcut) still go to the file path supplied via `--journal-path`. Supabase writes require `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` in the shell environment.

Stream and persist to Supabase:

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder"
$env:SUPABASE_URL = "https://<your-project>.supabase.co"
$env:SUPABASE_SERVICE_ROLE_KEY = "<service-role-key>"   # NEVER commit
python scripts/run_binance_trade_stream_smoke.py --symbols BTCUSDT,ETHUSDT,SOLUSDT --target supabase --max-events 0
```

Stream + journal + Supabase simultaneously:

```powershell
python scripts/run_binance_trade_stream_smoke.py --target both --journal-path data/whale_events.jsonl
```

Safe behaviors:
- `--target jsonl|both` without `--journal-path` exits with code 2 (no writes, no crash).
- Duplicate `whale_event_id` rows are caught by the partial unique index and counted as `supabase_duplicates` (not failures).
- Missing `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` returns a safe error dict per event and increments `supabase_failures` — the pipeline keeps running for stdout/jsonl sinks.

## LM63I Whale Feed Supabase Loader (website)

The whale-alerts page now reads from Supabase in production with a 3-tier source priority:

1. **Supabase** — when both `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` are present in the server-side env, fetches the latest 50 rows from `public.whale_events` ordered by `event_ts desc nullslast, created_at desc`.
2. **Local JSONL journal** — `<repo_root>/data/whale_events.jsonl`.
3. **Mock alerts** — built-in demo data.

Header badge maps to the source:

| Source | Badge |
|---|---|
| `supabase` | **SUPABASE ●** (green, pulsing dot) |
| `journal`  | **JOURNAL ●** (green, pulsing dot) |
| `mock`     | **DEMO** (amber) |

Configure Vercel (or local dev) with the same env you use for the heatmap writer:

```powershell
$env:SUPABASE_URL = "https://<your-project>.supabase.co"
$env:SUPABASE_SERVICE_ROLE_KEY = "<service-role-key>"   # server-only · NEVER commit · NEVER expose to client
```

The service-role key never leaves the server. It is only attached to the outbound `fetch` call inside the route handler / loader, both of which run server-side. The browser only sees the normalized `WhaleAlertView[]` array.

Safety:
- Missing env → Supabase tier is skipped silently → falls through to journal → mock.
- Network/HTTP errors, non-array responses, all-malformed rows → Supabase tier returns null → falls through.
- Route handler still wraps the loader in a final try/catch so the API never 500s.
- `dynamic = "force-dynamic"` + `runtime = "nodejs"` means Vercel never tries to pre-render the route at build time.

Verify locally:

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder\lumora-web"
$env:SUPABASE_URL = "https://<your-project>.supabase.co"
$env:SUPABASE_SERVICE_ROLE_KEY = "<service-role-key>"
npm run dev
# then visit http://localhost:3000/whale-alerts
# header should display the SUPABASE badge
```

Without the env vars set, the page still works (journal → mock fallback).

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