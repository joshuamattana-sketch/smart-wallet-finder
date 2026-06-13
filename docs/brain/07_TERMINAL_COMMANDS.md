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

## LM63J Whale Worker Mode (continuous Supabase writes)

Run the worker tests:

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder"
python -m pytest tests/connectors/test_binance_trade_stream.py
python -m compileall services scripts tests
```

### Local one-shot Supabase test (5 events then exit)

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder"
$env:SUPABASE_URL = "https://<your-project>.supabase.co"
$env:SUPABASE_SERVICE_ROLE_KEY = "<service-role-key>"   # NEVER commit
python scripts/run_binance_trade_stream_smoke.py --symbols BTCUSDT,ETHUSDT,SOLUSDT --target supabase --max-events 5
```

### Local forever Supabase worker (heartbeat every 60s)

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder"
$env:SUPABASE_URL = "https://<your-project>.supabase.co"
$env:SUPABASE_SERVICE_ROLE_KEY = "<service-role-key>"
python scripts/run_binance_trade_stream_smoke.py --symbols BTCUSDT,ETHUSDT,SOLUSDT --target supabase --forever --heartbeat-interval 60
```

`--forever` disables the implicit `--max-events 10` cap. An explicit `--max-events N` (N > 0) still wins. `--heartbeat-interval 0` silences the periodic stderr summary.

### Env-driven worker (no CLI flags)

The runner reads `WORKER_SYMBOLS`, `WHALE_WORKER_MIN_NOTIONAL`, `WHALE_WORKER_TARGET`, and `WHALE_WORKER_FOREVER` when `--use-env-config` is set. Any CLI flag the user explicitly passes still wins.

```powershell
$env:SUPABASE_URL = "https://<your-project>.supabase.co"
$env:SUPABASE_SERVICE_ROLE_KEY = "<service-role-key>"
$env:WORKER_SYMBOLS = "BTCUSDT,ETHUSDT,SOLUSDT"
$env:WHALE_WORKER_MIN_NOTIONAL = "250000"
$env:WHALE_WORKER_TARGET = "supabase"
$env:WHALE_WORKER_FOREVER = "true"
python scripts/run_binance_trade_stream_smoke.py --use-env-config
```

### Safe behaviors

- `--target supabase|both` with missing `SUPABASE_URL` or `SUPABASE_SERVICE_ROLE_KEY` → process exits with code 2 (`stopped=missing_supabase_env`) **before** opening the websocket.
- Supabase writes that raise an exception are caught and counted as `supabase_failures` — the loop keeps processing the next event.
- Bad events / malformed messages are skipped via the existing parser (LM63B).
- Ctrl+C / SIGINT exits cleanly with `stopped=interrupted` and the final summary on stderr.

### Railway notes

The existing `railway.worker.toml` deploys the **heatmap** worker (`scripts/run_binance_ws_heatmap_live.py`). To run the **whale worker** on Railway, deploy it as a separate service — duplicate the toml and change the `startCommand` to:

```toml
[deploy]
startCommand = "python scripts/run_binance_trade_stream_smoke.py --use-env-config --heartbeat-interval 60"
restartPolicyType = "ON_FAILURE"
restartPolicyMaxRetries = 10
```

Set the following Railway service env vars:

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `WORKER_SYMBOLS`           e.g. `BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT`
- `WHALE_WORKER_TARGET`      `supabase`
- `WHALE_WORKER_FOREVER`     `true`
- `WHALE_WORKER_MIN_NOTIONAL` (optional, overrides per-symbol thresholds)

The whale worker never sends Discord by default — leave `--send-discord` off until you're ready.

## LM63K Whale Worker Deployment Playbook

This is the canonical end-to-end deployment guide for the Binance aggTrade whale worker writing into Supabase. Everything here is documentation — no new code.

### Required env vars

| Name | Purpose |
|---|---|
| `SUPABASE_URL` | Supabase project URL, e.g. `https://abc.supabase.co`. Server-only. |
| `SUPABASE_SERVICE_ROLE_KEY` | Service-role key. **Server-only. Never expose to the browser. Never commit.** |

### Optional env vars (read when `--use-env-config` is set)

| Name | Default | Purpose |
|---|---|---|
| `WORKER_SYMBOLS` | `BTCUSDT,ETHUSDT,SOLUSDT` | Comma-separated Binance Spot symbols. |
| `WHALE_WORKER_MIN_NOTIONAL` | per-symbol presets | Global notional override (USD). |
| `WHALE_WORKER_TARGET` | `stdout` | One of `stdout`, `jsonl`, `supabase`, `both`. |
| `WHALE_WORKER_FOREVER` | `false` | `true` enables continuous worker mode. |

Explicit CLI flags always override env values when both are provided.

### Local one-shot Supabase test (5 events then exit)

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder"
$env:SUPABASE_URL = "https://<your-project>.supabase.co"
$env:SUPABASE_SERVICE_ROLE_KEY = "<service-role-key>"   # NEVER commit
python scripts/run_binance_trade_stream_smoke.py `
    --symbols BTCUSDT,ETHUSDT,SOLUSDT `
    --target supabase `
    --max-events 5
```

Expected stderr lines:
- startup banner with `target=supabase · supabase=on`
- per-event readable lines on stdout
- `summary: seen=… events=5 sent=0 supabase_writes=5 …`
- exit code `0`

### Local forever Supabase worker (Ctrl+C to stop)

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder"
$env:SUPABASE_URL = "https://<your-project>.supabase.co"
$env:SUPABASE_SERVICE_ROLE_KEY = "<service-role-key>"
python scripts/run_binance_trade_stream_smoke.py `
    --symbols BTCUSDT,ETHUSDT,SOLUSDT `
    --target supabase `
    --forever `
    --heartbeat-interval 60
```

`--forever` removes the implicit 10-event cap. An explicit `--max-events N` still wins.

### Expected heartbeat output

Every `--heartbeat-interval` seconds the worker prints a single line to stderr:

```
heartbeat · uptime=120s · seen=842 events=11 sendable=11 sent=0 supabase_writes=10 supabase_duplicates=1 supabase_failures=0 journaled=0 journal_failures=0
```

Field meanings:
- `seen`: raw aggTrades parsed from the WS feed
- `events`: passed the per-symbol notional floor and turned into whale events
- `sendable`: filter said send AND confidence ≥ threshold
- `sent`: Discord HTTP 2xx (always `0` unless `--send-discord` is set)
- `supabase_writes` / `supabase_duplicates` / `supabase_failures`: Supabase outcomes
- `journaled` / `journal_failures`: JSONL outcomes (when `--journal-path` is set)

### Safe stop (Ctrl+C)

The worker traps `KeyboardInterrupt`, prints `interrupted — stopping cleanly`, emits the final summary line, and exits with code `0`. Pending Supabase writes already in flight are not aborted.

### Verify rows in Supabase

After the worker runs, paste either query into the Supabase SQL editor:

```sql
-- Most recent rows the worker wrote
select symbol, side, notional_usd, severity, confidence, event_ts, created_at
from public.whale_events
order by created_at desc
limit 20;
```

```sql
-- Count by symbol over the last hour
select symbol, count(*) as events, sum(notional_usd)::numeric(20,2) as total_usd
from public.whale_events
where created_at >= now() - interval '1 hour'
group by symbol
order by events desc;
```

```sql
-- Verify the LM63G unique constraint is present (idempotency on whale_event_id)
select conname, contype
from pg_constraint
where conrelid = 'public.whale_events'::regclass
  and contype = 'u';
```

### Common errors and fixes

| Symptom | Cause | Fix |
|---|---|---|
| `error: --target supabase requires missing SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY` (exit 2 before websocket) | Both env vars unset | Set both in the shell before running. |
| `error: --target supabase requires missing SUPABASE_SERVICE_ROLE_KEY` | URL set but key missing | Add `SUPABASE_SERVICE_ROLE_KEY`. |
| Heartbeat shows `supabase_writes=0 supabase_failures=N` and stderr has lines like `supabase write failed for BTCUSDT: {'ok': False, ...}` | Auth / network / RLS / schema mismatch | Re-check the key, the table name `whale_events`, and re-run `supabase/whale_events.sql`. |
| `supabase write failed … 'error': 'there is no unique or exclusion constraint matching the ON CONFLICT specification'` | Old deployment only has the LM63G **partial** unique index | Apply the LM63G fix block — see the "Unique constraint on whale_event_id" section above. The SQL is idempotent. |
| Heartbeat shows `events=0` after a long uptime | Notional threshold too high for the streamed symbols | Lower `--min-notional` (e.g. `--min-notional 50000`) or pass `--no-use-symbol-thresholds` to fall back to the global $250k default; or add cheaper symbols (LINKUSDT, DOGEUSDT). |
| `supabase_duplicates` grows each restart with `supabase_writes=0` | Worker is replaying the same Binance aggTrade IDs (same `whale_event_id`); the constraint is doing its job | Expected on a single-symbol high-volume stream after a restart — let it run. To force more variety, broaden `--symbols`. |
| `journal_failures > 0` | `--journal-path` parent dir not writable | Choose a writable path (the runner creates parent dirs but can't fix permission errors). |

### Railway / VPS deployment notes

**Important:** the existing `railway.worker.toml` deploys the **heatmap** worker. The whale worker should run as a **separate** Railway service (or systemd unit on a VPS) so the two can scale and restart independently.

#### Railway

1. Create a second Railway service in the same project.
2. Use the same Nixpacks build settings as the heatmap worker.
3. Set the start command:

   ```
   python scripts/run_binance_trade_stream_smoke.py --use-env-config --heartbeat-interval 60
   ```

4. Set the service env vars (Railway Variables tab):

   - `SUPABASE_URL`               (your project URL)
   - `SUPABASE_SERVICE_ROLE_KEY`  (server-only; never expose to client)
   - `WORKER_SYMBOLS`             e.g. `BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT,BNBUSDT`
   - `WHALE_WORKER_TARGET`        `supabase`
   - `WHALE_WORKER_FOREVER`       `true`
   - `WHALE_WORKER_MIN_NOTIONAL`  (optional; otherwise per-symbol thresholds apply)

5. Restart policy: `ON_FAILURE` with max 10 retries.
6. **Do NOT add `SUPABASE_SERVICE_ROLE_KEY` to the Vercel/frontend project.** Frontend uses the anon-safe API route only; the key must stay server-side.

#### VPS (systemd example)

```ini
[Unit]
Description=Lumora whale worker (Binance aggTrade -> Supabase)
After=network.target

[Service]
Type=simple
WorkingDirectory=/srv/lumora
EnvironmentFile=/etc/lumora/whale-worker.env
ExecStart=/usr/bin/python3 scripts/run_binance_trade_stream_smoke.py --use-env-config --heartbeat-interval 60
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

`/etc/lumora/whale-worker.env` (chmod 600, owned by root):

```
SUPABASE_URL=https://<your-project>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<service-role-key>
WORKER_SYMBOLS=BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT,BNBUSDT
WHALE_WORKER_TARGET=supabase
WHALE_WORKER_FOREVER=true
```

#### Secret hygiene

- **`SUPABASE_SERVICE_ROLE_KEY` is server-only.** Never put it in a frontend `.env`, `next.config`, public route, or `NEXT_PUBLIC_*` var.
- Frontend reads via the existing `/api/whale-alerts` route, which runs server-side and never returns the key.
- Never commit any env file (`.env*`, `*.env`, `whale-worker.env`).
- Rotate the service-role key if it ever appears in logs / screenshots / chat threads.

## LM64B Binance Futures aggTrade Stream (--market flag)

The whale worker now supports the **Binance USD-M Futures** aggTrade stream as an optional venue alongside the existing Spot feed. Spot remains the default — no existing behavior or schema changed.

### CLI

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder"
# Spot (default — unchanged):
python scripts/run_binance_trade_stream_smoke.py --symbols BTCUSDT,ETHUSDT,SOLUSDT

# USD-M futures perpetuals:
python scripts/run_binance_trade_stream_smoke.py --symbols BTCUSDT,ETHUSDT,SOLUSDT --market futures
```

Env-config variant (new `WHALE_WORKER_MARKET`):

```powershell
$env:WHALE_WORKER_MARKET = "futures"
python scripts/run_binance_trade_stream_smoke.py --use-env-config
```

### What changes per market

| Field | spot (default) | futures |
|---|---|---|
| WS endpoint | `wss://stream.binance.com:9443/...` | `wss://fstream.binance.com/...` |
| `source_type` | `exchange_trade` | `futures_trade` |
| `exchange` | `binance_spot` | `binance_futures` |
| `metadata.market` | `spot` | `futures` |

The Supabase `whale_events` row carries `source_type`, `exchange`, and the full `metadata` block in `payload` — **no schema change needed** to filter by market in SQL later. Side mapping (`m == true` → SELL aggressor), notional math, and per-symbol thresholds are identical across markets.

### What we still don't claim

LM64B is *flow only*. Even on the futures stream, **leverage per trade is not in the public payload** and Lumora never claims it. The richer derived signals (`leverage_heat`, `oi_expansion`, funding-based context) arrive in **LM64C** (funding/OI poller) and **LM64D** (force-order stream + composite).

### Run the tests

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder"
python -m pytest tests/connectors/test_binance_trade_stream.py
python -m compileall services scripts tests
```

### LM64B-fix — strict market validation + URL regression guard

Two safety nets added so the futures WS endpoint is the one actually opened:

1. **Strict market validation.** Unknown values for `--market` (or the `market=` kwarg) now raise `ValueError` with a clear message — silent fallback to spot was removed.

   ```
   ValueError: unsupported market 'bogus' — must be one of ['futures', 'spot']
   ```

2. **Iterator transport-URL guard.** `iter_binance_aggtrades(market="futures", message_iter=None)` is asserted (in tests) to hand a `wss://fstream.binance.com/...` URL to the websocket transport. If a future edit ever wires the wrong base URL through, the test fails before any real network call.

If you observe `ws connecting: wss://stream.binance.com:9443/...` while running with `--market futures`, you are on an **old build**. Re-pull and re-deploy — the current code raises long before that mismatch is possible.

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

## LM68C Intelligence Chart — Live Binance Candles (web only · no Python)

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder\lumora-web"
npm run lint
npm run build
npm run dev
```

Then open:
- http://localhost:3000/terminal       (chart section near the top)
- http://localhost:3000/liquidity-map  (collapsed "Intelligence Chart · Preview" — click "Show preview")

Data source (public, no keys, read-only):
- REST snapshot: `https://api.binance.com/api/v3/klines` (300 bars)
- Live updates:  `wss://stream.binance.com:9443/ws/<symbol>@kline_<interval>`
- Symbols: BTCUSDT, ETHUSDT, SOLUSDT · Intervals: 1m, 5m, 15m

Status badge states on the panel header:
- `CONNECTING…`     initial REST snapshot in flight
- `LIVE · BINANCE`  live data flowing (`· WS` or `· REST` shows the transport)
- `STALE`           no tick for 30s
- `DEMO FALLBACK`   snapshot failed twice → deterministic mock session shown

Safe behaviors:
- WS blocked/closed → automatic REST polling every 8s (no crash, no spinner lock).
- Binance fully unreachable → mock candles + DEMO FALLBACK badge; page keeps working.
- Overlays (heatmap bands / whale markers / pressure / read) are DEMO data until LM68D,
  derived relative to the displayed candle range so they fit any symbol/price level.

## LM69B App Shell + Panel Primitives (web only · no Python)

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder\lumora-web"
npm run lint
npm run build
npm run dev
```

Check all five app pages still load: /dashboard /terminal /liquidity-map /whale-alerts /paper-trading

New shared primitives (use these instead of hand-rolling):
- `components/ui/PageShell.tsx`  — page header (title/context/status slot) + section rhythm
- `components/ui/MetricStrip.tsx` — the one KPI strip (label / mono value / sub)
- `Panel level="focus"`  — the page's instrument (bordered + inset frame; max one per region)
- `Panel level="subtle"` — supporting surfaces (recessed, NO border)
- `StatusBadge variant="demo"` — gray; amber is reserved for risk/staleness only

## LM69C UI Texture + Interaction Pass (web only · no Python)

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder\lumora-web"
npm run lint
npm run build
npm run dev
```

Then open http://localhost:3000/terminal and http://localhost:3000/dashboard.

What changed (texture only — LM69B layout intact):
- `Panel` levels gained depth: default = inner top highlight + soft drop;
  focus = instrument shadow + built-in cyan top stripe (do NOT also add
  `lm-accent-top-cyan` to focus panels — the stripe is included).
- `StatusBadge` variants now carry faint matching borders (≤25% alpha).
- Chart header: group dividers, `aria-pressed` on all segments/toggles,
  overlay toggles show a cyan indicator dot when on, read chip has a
  bias-colored left rail, honesty footer is a two-sided status line.
- TopNav: LIVE is a bordered emerald chip; active link icon tinted purple.
- Dashboard opens with a ~40px Current Read command strip (bias · score ·
  conf · risk · action · live price · status · Terminal link) instead of the
  old full-size read card; watchlist + whale tape live in the right rail.

Check: hover nav/buttons/chips, active mode/toggle states, chart LIVE ·
BINANCE, dashboard loads, no console errors.

## LM69C IntelligenceDock + Visual Liveness (web only · no Python)

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder\lumora-web"
npm run lint
npm run build
npm run dev
```

Then open http://localhost:3000/terminal and http://localhost:3000/dashboard.

What changed:
- New `components/ui/IntelligenceDock.tsx` — a dark glass pill of icon
  controls (hover halo, 1px hover lift, compact tooltip, active dot,
  optional live badge). Reusable; CSS transitions only, motion-reduce safe.
- Intelligence Chart header: mode presets (Clean / Assisted / Full Intel,
  violet = selected) and overlay channels (Heatmap cyan / Whales emerald /
  Pressure amber / Read cyan) moved into the dock. Tooltips name each
  control and show on/off + demo state.
- Chart pane: faint cyan (left) / violet (right) edge-light hairlines under
  the focus stripe; LIVE · BINANCE badge gets a quiet emerald halo when live.
- Terminal: perpetual walls spinner removed; pressure caption has a cyan
  left edge; segments expose aria-pressed.
- Dashboard: compact Current Read command strip (no giant read card),
  watchlist rail + whale tape on the right, setups on the left.

Check: hover each dock control (halo + lift + tooltip), click modes and
overlays (active dot + tone), chart LIVE badge, dashboard top strip,
no console errors.

## LM69C Nav Refinement Fix (web only · no Python)

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder\lumora-web"
npm run lint
npm run build
npm run dev
```

Then open http://localhost:3000/dashboard and http://localhost:3000/terminal.

What changed:
- TopNav is a dark-glass command bar (in-component Tailwind, no global
  classes): violet logo tile + LUMORA + TERMINAL suffix, active link =
  violet inset pill with a luminous violet→cyan bottom edge, hover = 1px
  lift + inner highlight, UTC + LIVE fused into one status capsule.
- Intelligence Chart: the futures pressure strip renders as an absolute
  overlay at the bottom of the chart pane — toggling Pressure (or any
  overlay) causes zero layout shift and nothing appears below the chart.

Check: hover every nav item, active tab on /dashboard and /terminal,
UTC/LIVE capsule, narrow width (icon-only links scroll, no break),
toggle Pressure/Read — chart height must not jump, no console errors.

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
## LM68D Real Whale Markers — verify

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder\lumora-web"
npm run lint
npm run build
npm run dev
# open http://localhost:3000/terminal and http://localhost:3000/liquidity-map
# chart footer shows: whales · live | fallback | none
```

## LM75A MT5 Demo Connector Probe — read-only, no orders

Requires MetaTrader 5 installed + a running, logged-in MetaQuotes DEMO account
with XAUUSD visible. Windows only. Install the dependency once (not in
requirements.txt — it is Windows-only and would break the Linux workers):

```powershell
pip install MetaTrader5
```

Run from repo root (sends NO orders, fails closed on a real account):

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder"
python scripts/run_mt5_demo_connector_probe.py
python scripts/run_mt5_demo_connector_probe.py --bars 50
python scripts/run_mt5_demo_connector_probe.py --symbol XAUUSD --timeframe M5 --bars 100
python scripts/run_mt5_demo_connector_probe.py --json
```

Expected: connects to the running terminal, confirms DEMO, auto-discovers the
gold symbol (XAUUSD/GOLD/...), prints account + tick + latest candles, ends
with `READ ONLY - NO ORDERS SENT`. Exits 1 (fail-closed) if MT5 can't
initialize, account info can't be read, the account is real/live, no gold
symbol is selectable, or no candles return.

Tests (no terminal needed, fake MT5 injected):

```powershell
python -m pytest tests/connectors/test_mt5_demo_connector.py -q
```

## LM75B MT5 Demo Guarded Trade Loop — demo only, heavily guarded

DEMO ONLY. Default behavior sends nothing. An order is sent ONLY with
`--confirm-demo-order` (and not `--dry-run`), on a verified demo account, after
the risk gate approves and order_check passes. Close-position is deferred.

Safety env (defaults safe): MT5_DEMO_ONLY=true · LIVE_TRADING_ENABLED=false ·
ALLOW_REAL_ORDERS=false · GOLD_BOT_KILL_SWITCH=false ·
GOLD_BOT_MAX_TRADES_PER_DAY=3 · GOLD_BOT_MAX_DAILY_LOSS_PCT=7

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder"

# read-only probe still works:
python scripts/run_mt5_demo_connector_probe.py --bars 50

# validate only (sends NOTHING):
python scripts/run_mt5_demo_trade_loop.py --side buy  --volume 0.01 --sl-points 300 --tp-points 600 --dry-run
python scripts/run_mt5_demo_trade_loop.py --side sell --volume 0.01 --sl-points 300 --tp-points 600 --dry-run

# actually place a guarded DEMO order (opens a real position on the demo account):
python scripts/run_mt5_demo_trade_loop.py --side buy  --volume 0.01 --sl-points 300 --tp-points 600 --confirm-demo-order
```

Journal (gitignored): `data/gold_bot/demo_trade_journal.jsonl` — one line per
attempt (dry_run / blocked / demo_order).

Tests (no terminal needed):

```powershell
python -m pytest tests/connectors/test_mt5_demo_connector.py tests/test_gold_bot_risk_gate.py -q
```

## LM75C MT5 Demo Position Manager + Close — demo only, guarded

List is read-only. Close sends nothing unless `--confirm-demo-order`, on a
verified demo account, with the ticket found. Closing is risk-reducing so the
open-side caps don't apply; the kill switch still blocks a close unless
`--emergency-close` (demo only) is given.

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder"

# list open positions (read-only):
python scripts/run_mt5_demo_trade_loop.py --list-positions

# close one position by ticket (guarded):
python scripts/run_mt5_demo_trade_loop.py --close-position TICKET --confirm-demo-order

# emergency close even if kill switch is on (still demo only):
python scripts/run_mt5_demo_trade_loop.py --close-position TICKET --confirm-demo-order --emergency-close

# verify afterwards:
python scripts/run_mt5_demo_connector_probe.py --bars 10
```

Close uses the position's exact ticket/symbol/volume with the opposite order
type (close BUY → SELL at bid, close SELL → BUY at ask). `order_check` on a
close is advisory only (unreliable in the MT5 Python API) — demo verification +
the safety checks are the real guard. Close attempts are journaled
(`mode=close_position` / `blocked`).

## LM75C-fix MT5 deal/history import — robust, multi-window

The probe now queries deals AND orders across today / 7d / 30d windows with
tz-aware UTC bounds, padding `date_to` +1 day so a broker clock ahead of UTC
can't hide a just-closed deal. Prints per-window deal/order counts, XAUUSD
deal count, entry/exit counts and profit/commission/swap sums; with
`--history-debug` it also lists recent deal rows and the exact query windows.

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder"
python scripts/run_mt5_demo_connector_probe.py --bars 10 --history-debug
python scripts/run_mt5_demo_connector_probe.py --bars 10
```

If no deals appear, the output prints likely reasons + the exact windows used.

## LM75D MT5 demo risk/margin/lot calculator — demo only, guarded

The trade loop now sizes positions from risk instead of blind fixed lots and
prints a full risk plan (equity, risk%, target risk, est SL loss, margin, daily
PnL, remaining daily-loss budget, trades today, decision). The Risk Engine
blocks unsafe trades (SL loss over remaining daily budget, margin over 10% of
free margin, daily -7% hard stop, trade cap). Auto-volume fails closed if it
cannot size. Sending still needs --confirm-demo-order on a verified demo account.

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder"

# manual volume (still supported) — prints est SL loss + risk %:
python scripts/run_mt5_demo_trade_loop.py --side buy --volume 0.01 --sl-points 300 --tp-points 600 --dry-run

# auto-size from risk (equity x risk% / SL loss):
python scripts/run_mt5_demo_trade_loop.py --side buy  --sl-points 300 --tp-points 600 --auto-volume --risk-mode balanced --dry-run
python scripts/run_mt5_demo_trade_loop.py --side sell --sl-points 300 --tp-points 600 --auto-volume --risk-mode aggressive --dry-run

# risk modes: safe 0.25% / balanced 0.50% / aggressive 1.0% / experimental 0.10%
# override (capped 1.0%, or 2.0% with --allow-high-demo-risk):
python scripts/run_mt5_demo_trade_loop.py --side buy --sl-points 300 --tp-points 600 --auto-volume --risk-pct 0.75 --dry-run

# place the guarded demo order with auto size:
python scripts/run_mt5_demo_trade_loop.py --side buy --sl-points 300 --tp-points 600 --auto-volume --risk-mode balanced --confirm-demo-order
```

## LM75D high-activity mode (no fixed trade cap)

The daily trade cap is now OFF by default (high-activity): the bot may take
many trades as long as each passes risk/margin/daily-loss/SL-TP. Pass
`--max-trades-per-day N` (or set GOLD_BOT_MAX_TRADES_PER_DAY) only if you want a cap.

```powershell
# high-activity (no cap) — prints "Trades today: X / unlimited":
python scripts/run_mt5_demo_trade_loop.py --side buy --sl-points 300 --tp-points 600 --auto-volume --risk-mode balanced --dry-run

# enforce a cap:
python scripts/run_mt5_demo_trade_loop.py --side buy --sl-points 300 --tp-points 600 --auto-volume --risk-mode balanced --max-trades-per-day 1 --dry-run
```

## LM75D scalp mode (experimental, demo-only high-frequency)

`--risk-mode scalp`: 0.10% risk/trade, no fixed trade cap, prints
"Frequency mode: experimental-scalp". For M1/M5 XAUUSD scalp testing — still
obeys demo check, SL/TP, daily -7% stop, margin, kill switch (no martingale,
no live).

```powershell
python scripts/run_mt5_demo_trade_loop.py --side buy --sl-points 120 --tp-points 180 --auto-volume --risk-mode scalp --dry-run
```

## LM75E close dry-run + richer post-close

Close now supports a dry-run preview (build + print, no send) and prints
post-close balance/equity/today-PnL. List shows the XAUUSD open count.
`--emergency-close-demo` is an alias of `--emergency-close`.

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder"
python scripts/run_mt5_demo_trade_loop.py --list-positions
python scripts/run_mt5_demo_trade_loop.py --close-position TICKET --dry-run        # preview, no send
python scripts/run_mt5_demo_trade_loop.py --close-position TICKET --confirm-demo-order
python scripts/run_mt5_demo_connector_probe.py --bars 10 --history-debug
```

## LM76A Gold Bot decision engine V1 — decision-only, demo execution guarded

Reads live XAUUSD candles + spread + position state, outputs LONG/SHORT/NO_TRADE
with reasons. Decision-only + dry-run by default (sends nothing). Demo
execution needs BOTH --auto-execute-demo AND --confirm-demo-order, demo account,
no open XAUUSD position, and the LM75D risk gate approving.

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder"
python scripts/run_gold_bot_decision_probe.py --risk-mode balanced --dry-run
python scripts/run_gold_bot_decision_probe.py --risk-mode scalp --dry-run
python scripts/run_gold_bot_decision_probe.py --risk-mode aggressive --dry-run
# intentional guarded demo execution (opens a real demo position if APPROVED):
python scripts/run_gold_bot_decision_probe.py --risk-mode scalp --auto-execute-demo --confirm-demo-order
```

Decision journal (gitignored): data/gold_bot/decision_journal.jsonl.
Tests: python -m pytest tests/test_gold_bot_decision_engine.py -q

## LM76B Gold Bot strategy engine V2

Richer context (sessions, swing/prev levels, compression, regime) + detectors:
liquidity_sweep_reclaim, fvg_retest, breakout_retest, momentum, scalp_retest/
scalp_momentum. Picks best by priority+confidence; explainable score breakdown.
Same guards as V1 (decision-only + dry-run default; demo execution needs both
--auto-execute-demo + --confirm-demo-order).

```powershell
python scripts/run_gold_bot_decision_probe.py --risk-mode balanced --dry-run
python scripts/run_gold_bot_decision_probe.py --risk-mode scalp --dry-run
python scripts/run_gold_bot_decision_probe.py --risk-mode aggressive --dry-run
```

## LM81A Gold Bot worker loop - MT5 DEMO ONLY, observe by default, sends nothing

Long-running loop version of the decision probe. Each iteration: reads MT5 demo
account/symbol/tick/candles, builds the LM77A macro context, runs Decision
Engine V2, prints a safety banner once + a compact `[HB]` heartbeat per
iteration, journals every iteration to `data/gold_bot/worker_journal.jsonl`
(gitignored) and writes `data/gold_bot/worker_status.json` (gitignored).

OBSERVE / dry-run by default - it SENDS NOTHING. A demo order is only ever
attempted with `--mode demo` AND `--auto-execute-demo` AND `--confirm-demo-order`,
on a verified demo account, after the LM75D risk gate APPROVES, and never during
a macro lockout or with an open XAUUSD position (no stacking). Kill switch /
LIVE / REAL flags block orders. Non-demo account, live-trading flags, or MT5
unavailable for 5 consecutive iterations stop the worker fail-closed (exit 2).

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder"
# observe once / a few loops (no orders):
python scripts/run_gold_bot_worker.py --max-iterations 1
python scripts/run_gold_bot_worker.py --max-iterations 5 --interval-seconds 5
# scalp observe:
python scripts/run_gold_bot_worker.py --risk-mode scalp --max-iterations 5 --interval-seconds 5
# with macro context (sample events, DXY/yields placeholders):
python scripts/run_gold_bot_worker.py --risk-mode scalp --macro-events-file data/gold_bot/macro_events.sample.json --dxy-bias rising --yields-bias rising --max-iterations 5 --interval-seconds 5
# intentional guarded demo execution (opens a real demo position if APPROVED):
python scripts/run_gold_bot_worker.py --mode demo --risk-mode scalp --auto-execute-demo --confirm-demo-order --max-iterations 1
```

Kill switch (blocks all orders, worker still observes):
`$env:GOLD_BOT_KILL_SWITCH = "true"` before running.

Tests: `python -m pytest tests/test_gold_bot_worker.py -q` (11, fake connector,
no terminal needed).

## LM82A Gold Bot start scripts (PowerShell convenience launchers)

Thin `.ps1` wrappers around the LM81A worker so you don't memorize long Python
commands. MT5 DEMO ONLY, never live. The observe/scalp/macro scripts send NO
orders. Each resolves the repo root from `$PSScriptRoot` (works from repo root
or the scripts folder) and prints a banner (mode / MT5 demo only / no live /
orders disabled-or-armed). `$ErrorActionPreference = "Stop"` - errors are not
hidden. No core trading/strategy logic changed.

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder"

# read-only one-shot health check (connector probe + decision probe, dry-run):
.\scripts\gold_bot_health_check.ps1

# observe loops (no orders) - Ctrl+C to stop:
.\scripts\start_gold_bot_observe.ps1        # balanced observe, 5s
.\scripts\start_gold_bot_scalp.ps1          # scalp observe, 5s
.\scripts\start_gold_bot_macro_scalp.ps1    # scalp observe + sample macro lockout context

# guarded demo launcher - DEFAULTS to observe/dry-run (sends nothing):
.\scripts\start_gold_bot_demo_guarded.ps1
#   -> prints "Demo execution requires explicit -ConfirmDemoExecution" and runs observe.
# Arm demo orders (MT5 demo only; still passes risk gate / macro lockout / no-stacking):
.\scripts\start_gold_bot_demo_guarded.ps1 -ConfirmDemoExecution
#   -> python scripts/run_gold_bot_worker.py --mode demo --risk-mode scalp \
#        --auto-execute-demo --confirm-demo-order --interval-seconds 5
# Optional params: -RiskMode <mode> -IntervalSeconds <n>
```

Safety: only `start_gold_bot_demo_guarded.ps1 -ConfirmDemoExecution` ever passes
the execution flags; no script enables live trading or contains secrets.
Generated `data/gold_bot/worker_journal.jsonl` + `worker_status.json` stay
gitignored.

## LM83A Economic calendar source layer (provider-neutral, local JSON real)

Normalized economic calendar (`services/gold_bot_economic_calendar.py`) feeds
the LM77A macro brain. ONE real provider (`LocalJsonEconomicCalendarProvider`)
reads `data/gold_bot/economic_calendar.sample.json`; `FutureApiEconomicCalendar
Provider` + `ManualImportProvider` are placeholders (no paid API, no secrets, no
scraping). `EconomicEvent` is normalized (title/type/currency/impact/scheduled_at
UTC/previous/forecast/actual/tags...); USD high-impact CPI/NFP/FOMC/Fed Speech/
Rate Decision are tagged `gold_major`. Lockout/watch/post-event rules unchanged.

Calendar probe (read-only, no MT5):

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder"
python scripts/run_gold_bot_calendar_probe.py --calendar-file data/gold_bot/economic_calendar.sample.json --window-hours 48 --currency USD
python scripts/run_gold_bot_calendar_probe.py --calendar-file data/gold_bot/economic_calendar.sample.json --impact high --json
```

Decision probe + worker now accept `--calendar-file` (preferred); the legacy
`--macro-events-file` still works as a fallback when `--calendar-file` is omitted.

```powershell
python scripts/run_gold_bot_decision_probe.py --risk-mode balanced --calendar-file data/gold_bot/economic_calendar.sample.json --dry-run
python scripts/run_gold_bot_worker.py --risk-mode scalp --calendar-file data/gold_bot/economic_calendar.sample.json --max-iterations 3 --interval-seconds 5
```

Tests: `python -m pytest tests/test_gold_bot_economic_calendar.py tests/test_gold_bot_macro_context.py -q`
(no MT5). Generated worker journal/status stay gitignored; the `.sample.json`
calendar is tracked.

### LM83A part 2 — data source architecture (provider status + manual fallback)

`services/gold_bot_data_sources.py` adds a `ProviderStatus` model
(name/category/status/freshness/last_updated/message/warnings) and a registry.
REAL providers: `LocalJsonEconomicCalendarProvider` (status `active`) and
`ManualJsonEconomicCalendarProvider` (status `fallback` — a TEMPORARY free
fallback, `data/gold_bot/economic_calendar.manual.json`). PLACEHOLDER providers
(status-only, NO HTTP, no keys): Finnhub, TradingEconomics, MT5 calendar export,
GDELT, RSS, FRED, yfinance, and MT5 XAUUSD / DXY / US-yields / VIX history
(historical = placeholder until LM84A/LM84B). `resolve_calendar_provider(path)`
picks Manual when the filename contains `manual`, else Local.

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder"
# full data-source status overview (read-only, no HTTP):
python scripts/run_gold_bot_data_sources_probe.py
python scripts/run_gold_bot_data_sources_probe.py --json

# calendar probe now prints provider status; manual fallback file works too:
python scripts/run_gold_bot_calendar_probe.py --calendar-file data/gold_bot/economic_calendar.manual.json --window-hours 720 --currency USD
```

Decision probe + worker print the active provider status (active/fallback/
missing) in the Macro Context block / banner. `--calendar-file` accepts either
the sample or the manual file. Tests:
`python -m pytest tests/test_gold_bot_data_sources.py -q`. Both `.sample.json`
and `.manual.json` calendars are tracked; runtime journals/status stay
gitignored.

## LM84A Historical market backfill (REAL MT5 XAUUSD history)

First real historical provider. `services/gold_bot_historical_market_data.py`
copies XAUUSD bars from a running MT5 demo terminal (connector's new read-only
`copy_rates_range`) into `data/gold_bot/history/XAUUSD_<TF>.csv` + `.meta.json`.
Read-only, NO orders. `HistoricalBar` model (symbol/timeframe/time UTC/OHLC/
tick_volume/spread/real_volume/source/loaded_at); timeframes M1/M5/M15/H1.
`MT5HistoricalXauusdProvider` verifies a DEMO account, fetches per timeframe,
normalizes to UTC, writes CSV + metadata (rows_written/first+last bar/warnings),
and reports `ProviderStatus` active/missing/fresh/stale from the files. Generated
CSV/meta are gitignored.

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder"
# preview only (no writes, no MT5 needed):
python scripts/run_gold_bot_history_backfill.py --dry-run
# write CSV/meta (MT5 demo terminal must be running):
python scripts/run_gold_bot_history_backfill.py --days 7 --timeframes M1,M5 --overwrite
python scripts/run_gold_bot_history_backfill.py --days 30 --timeframes M1,M5,M15,H1
# inspect local history + data-quality scan:
python scripts/run_gold_bot_history_probe.py --timeframe M1 --tail 5
# data-sources overview now shows mt5_xauusd_history ACTIVE once files exist:
python scripts/run_gold_bot_data_sources_probe.py
```

Backfill flags: `--symbol XAUUSD --timeframes M1,M5,M15,H1 --days 30
--from-date YYYY-MM-DD --to-date YYYY-MM-DD --out-dir data/gold_bot/history
--overwrite --dry-run`. Existing files are skipped unless `--overwrite`. If MT5
returns fewer bars than the naive expectation (limited terminal history /
weekends), it WARNS in the metadata + probe but never crashes. Tests
`python -m pytest tests/test_gold_bot_historical_market_data.py -q` (no MT5 —
injected fetch_fn + temp dirs). History files (`data/gold_bot/history/*.csv|*.json`)
are gitignored.

## LM84B Macro history import (DXY / US10Y / US02Y / VIX, offline CSV)

Offline bootstrap (NO HTTP / API / scraping) that moves DXY/yields/VIX from
placeholder to missing/active. `services/gold_bot_macro_history.py` imports a
free, manually-downloaded CSV into a normalized `MacroBar` (time UTC / OHLC opt /
close / value opt) under `data/gold_bot/macro_history/<SYM>_<TF>.csv` + `.meta.json`
(D1; H1 optional). Auto-detects **OHLC** (`time,open,high,low,close`) or
**value-only** (`time,value`; close=value). `macro_market_statuses` reports
`dxy_history` / `us_yields_history` (US10Y and/or US02Y) / `vix_history` as
active/missing (category macro_market); FRED + yfinance stay placeholder.

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder"
# validate only (no writes):
python scripts/run_gold_bot_macro_history_import.py --input data/gold_bot/macro_history/samples/DXY_D1.sample.csv --symbol DXY --timeframe D1 --dry-run
# import the bundled samples:
python scripts/run_gold_bot_macro_history_import.py --input data/gold_bot/macro_history/samples/DXY_D1.sample.csv --symbol DXY --timeframe D1 --overwrite
python scripts/run_gold_bot_macro_history_import.py --input data/gold_bot/macro_history/samples/US10Y_D1.sample.csv --symbol US10Y --timeframe D1 --overwrite
python scripts/run_gold_bot_macro_history_import.py --input data/gold_bot/macro_history/samples/VIX_D1.sample.csv --symbol VIX --timeframe D1 --overwrite
# inspect + status:
python scripts/run_gold_bot_macro_history_probe.py --symbol DXY --timeframe D1 --tail 5
python scripts/run_gold_bot_data_sources_probe.py     # Macro market now shows ACTIVE dxy/yields
```

Import flags: `--input --symbol --timeframe D1 --source manual_csv --out-dir
data/gold_bot/macro_history --overwrite --dry-run`. Existing files skipped unless
`--overwrite`; dry-run validates + shows target path, writes nothing. Tracked:
`data/gold_bot/macro_history/README.md` + `samples/*.sample.csv`. Ignored
(generated): `data/gold_bot/macro_history/*.csv|*.json`. See the folder README
for the free workflow. Tests `python -m pytest tests/test_gold_bot_macro_history.py -q`
(no internet, no MT5). Later LM84C/LM84D add yfinance/FRED behind the same
interface.

## LM85A No-lookahead replay engine (backtest over local history)

`services/gold_bot_replay_engine.py` streams stored XAUUSD history (LM84A) one
bar at a time, joins macro history (LM84B DXY/US10Y/US02Y/VIX) AS-OF the current
bar only, runs the real Decision Engine V2 through a CSV->candle adapter (NO MT5,
NO orders), then scores each decision against FUTURE bars — but only after the
decision is recorded. `ReplayClock` exposes `visible_bars` (time <= current);
`MacroSeries.snapshot` returns the latest macro row <= current time; forward
scoring reads `bars[i+1:]`. Horizons give win/loss/neutral/no_data + MFE/MAE +
TP/SL first-touch + forward return.

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder"
# needs local history first (LM84A):
python scripts/run_gold_bot_history_backfill.py --timeframes M1,M5
# validate only (no files):
python scripts/run_gold_bot_replay.py --timeframe M1 --max-bars 200 --dry-run
# run a replay (writes JSONL + summary under data/gold_bot/replay/):
python scripts/run_gold_bot_replay.py --timeframe M1 --max-bars 200 --risk-mode balanced --horizons 5,15,30
python scripts/run_gold_bot_replay.py --timeframe M5 --max-bars 200 --risk-mode scalp --horizons 3,6,12
```

Output: `data/gold_bot/replay/replay_XAUUSD_<TF>_<YYYYMMDD>_NNN.jsonl` (one row
per step: decision/strategy/confidence/reasons/macro snapshot/score-by-horizon/
`no_lookahead_visible_bars_count`/`forward_scoring_uses_future_after_decision`)
+ `.summary.json` (bars processed, long/short/no_trade, avg confidence, win/loss/
neutral/no_data + avg return per horizon, top setups, warnings). Flags:
`--symbol --timeframe --history-dir --macro-history-dir --out-dir --warmup-bars
--max-bars --from-time --to-time --risk-mode --horizons --dry-run --json`.
Missing history → clear error (hint: run LM84A backfill). Missing macro → warn +
continue (macro unknown). NEVER calls MT5, never sends orders. Generated replay
files (`data/gold_bot/replay/*.jsonl|*.json|*.csv`) are gitignored. Tests
`python -m pytest tests/test_gold_bot_replay_engine.py -q` (no MT5/internet;
assert no future bars in visible window, causal macro as-of, NO_TRADE not scored
win/loss, dry-run writes nothing, MetaTrader5 never imported).

## LM86A Pattern scoring / learning journal (replay -> setup scorecards)

`services/gold_bot_learning_journal.py` aggregates the LM85A replay JSONL into
explainable per-setup scorecards: sample/trade/no_trade counts, win/loss/neutral/
no_data + winrate + avg_dir_return + expectancy by horizon, MFE/MAE, plus slices
by confidence bucket / direction / timeframe / risk_mode / session / macro bias,
and a NO_TRADE missed-opportunity analysis. `recommended_status` =
promising / weak / avoid / insufficient_sample / mixed (min-sample guarded).
READ-ONLY + OFFLINE: no MT5, no orders, no HTTP. It writes a
`setup_modifiers.preview.json` but that is PREVIEW ONLY (`LEARNING_MODIFIERS_LIVE
= False`) — NOT wired into the decision engine or worker; live behavior is
unchanged until a future owner-approved gate.

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder"
# needs replay output first (LM85A):
python scripts/run_gold_bot_replay.py --timeframe M1 --max-bars 500 --risk-mode balanced --horizons 5,15,30
# build scorecards:
python scripts/run_gold_bot_learning_scorecard.py --dry-run
python scripts/run_gold_bot_learning_scorecard.py --horizon 15 --min-samples 10 --top 10
python scripts/run_gold_bot_learning_scorecard.py --timeframe M5 --risk-mode scalp --horizon 12 --min-samples 10 --top 10
```

Reads `data/gold_bot/replay/*.jsonl` (risk_mode pulled from the sibling
`.summary.json`; session derived from bar time when absent). Writes
`data/gold_bot/learning/scorecard_<SYMBOL>_<TF>_<RISK>_<date>.json` +
`scorecard_latest.json` + `setup_modifiers.preview.json` + appends
`learning_events.jsonl`. Flags: `--replay-dir --out-dir --symbol --timeframe
--risk-mode --horizon --min-samples --missed-move-threshold-points --top
--dry-run --json`. dry-run writes nothing; no replay files -> clear error (hint:
run LM85A). All learning outputs (`data/gold_bot/learning/*.json|*.jsonl|*.csv`)
are gitignored. Tests `python -m pytest tests/test_gold_bot_learning_journal.py -q`
(no MT5/internet). LIVE TRADING UNCHANGED — learning is analysis only.

## LM86B Demo auto learning modifiers (preview -> active, demo-only)

`services/gold_bot_learning_modifiers.py` promotes the LM86A preview into an
ACTIVE demo modifier set the decision engine / replay / worker may OPTIONALLY
apply. DEMO-ONLY autonomy: no per-setup approval, but modifiers only nudge
CONFIDENCE — they can NEVER enable live trading or bypass macro lockout / kill
switch / daily-loss / margin / risk gate, and never change volume. Values are
clamped twice: promotion [-12,+8], hard [-20,+12]. `decide()` gains
`use_learning_modifiers` (default False), `learning_modifiers`/
`learning_modifiers_file`, `learning_mode`; when on it adds an explainable
`reason` and `idea.learning` = {original_confidence, learning_modifier,
final_confidence, learning_modifier_source, learning_mode}, clamps 0-100, and may
fall to NO_TRADE (`learning_low_confidence`) — but a NO_TRADE / macro lockout is
NEVER revived by a boost.

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder"
# inspect which preview modifiers would activate (read-only):
python scripts/run_gold_bot_learning_modifiers_probe.py
# auto-promote preview -> active_demo_modifiers.json (demo-only, no approval):
python scripts/run_gold_bot_learning_modifiers_probe.py --promote --min-samples 10

# compare replay WITHOUT vs WITH learning:
python scripts/run_gold_bot_replay.py --timeframe M1 --max-bars 500 --risk-mode balanced --horizons 5,15,30
python scripts/run_gold_bot_replay.py --timeframe M1 --max-bars 500 --risk-mode balanced --horizons 5,15,30 --use-learning-modifiers

# observe worker with learning (still sends nothing; demo exec needs the demo flags too):
python scripts/run_gold_bot_worker.py --mode observe --risk-mode scalp --use-learning-modifiers --max-iterations 3 --interval-seconds 5
```

Worker banner shows learning enabled/disabled + modifier file + learning mode +
demo-only. Demo execution STILL requires `--mode demo --auto-execute-demo
--confirm-demo-order` on a verified demo account through the risk gate — learning
changes none of that. Generated `data/gold_bot/learning/active_demo_modifiers.json`
+ `modifier_events.jsonl` are gitignored. Missing/invalid modifier file → warn +
continue without modifiers. Tests
`python -m pytest tests/test_gold_bot_learning_modifiers.py -q` (no MT5/internet).

## LM86C Automatic learning cycle (replay → learn → adapt, demo-only)

`services/gold_bot_learning_cycle.py` chains **baseline replay → scorecard →
promote CANDIDATE → candidate replay → compare → keep or rollback**. A candidate
modifier set only replaces the active one when it OBJECTIVELY beats the baseline;
otherwise the active set is kept and the candidate is recorded as rejected. This
is what catches the LM86B regression (learning made h15 avg trade ret ~-41.1pt →
~-49.8pt) automatically.

OFFLINE + DEMO-ONLY: never calls MT5, never sends orders, no HTTP, no secrets.
Modifiers stay confidence-only; the macro lockout / risk gate / kill switch /
volume are never touched. The candidate is staged in
`candidate_demo_modifiers.json` and never overwrites `active_demo_modifiers.json`
until the comparison accepts it.

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder"
# preview the planned steps + validate files (writes nothing):
python scripts/run_gold_bot_learning_cycle.py --dry-run

# run the full cycle (needs local history first — LM84A/LM84B):
python scripts/run_gold_bot_learning_cycle.py --timeframe M1 --risk-mode balanced --max-bars 500 --horizon 15 --min-samples 10

# inspect modifiers (now warns if the active set is expired):
python scripts/run_gold_bot_learning_modifiers_probe.py

# compare replay WITHOUT vs WITH learning by hand:
python scripts/run_gold_bot_replay.py --timeframe M1 --max-bars 500 --risk-mode balanced --horizons 5,15,30 --use-learning-modifiers

# undo the last accepted promotion (restore backup):
python scripts/run_gold_bot_learning_cycle.py --rollback
```

Accept rules at the selected horizon (defaults): candidate expectancy ≥ baseline
+ `--min-improvement-points 10`; candidate trades ≥ baseline × `--min-trade-count-ratio 0.5`;
candidate ≥ `--min-trades 30`; winrate not down > 0.05 unless expectancy improved
strongly (≥ 2× the improvement floor); baseline/candidate with no data → reject
safely. CLI: `--symbol --timeframe --risk-mode --max-bars --horizons --horizon
--min-samples --min-trades --min-improvement-points --min-trade-count-ratio
--learning-dir --replay-out-dir --dry-run --rollback --json`.

Generated (all gitignored): `data/gold_bot/learning/cycles/cycle_<ts>.json`,
`cycles/cycle_events.jsonl`, `candidate_demo_modifiers.json`,
`active_demo_modifiers.json`, `active_demo_modifiers.backup.json`,
`rejected_demo_modifiers.json`. Active/candidate carry metadata: `generated_at`,
`expires_at` (default now + 7 days), `cycle_id`, `source_scorecard`,
`baseline_summary`, `candidate_summary`, accept/reject `reason`. Expiry only WARNS
(probe) — nothing is auto-deleted in this patch.

Live-verified: real M1 balanced cycle → baseline exp -41.1pt / candidate exp
-50.7pt → **REJECTED** (expectancy -9.6pt, need ≥ +10pt), active modifiers kept,
no backup written. Tests
`python -m pytest tests/test_gold_bot_learning_cycle.py -q` (no MT5/internet).

## LM87A Demo safety supervisor (runtime guard, demo-only, no off switch)

`services/gold_bot_demo_safety_supervisor.py` runs before/around every worker
iteration and enforces HARD demo limits so autonomous demo execution can't run
away. It is a SECOND layer on top of (never a replacement for) the risk gate,
macro lockout and kill switch — it can only BLOCK/downgrade, never send orders,
enable live trading, change volume/lot, or bypass any control. **There is no off
switch** (no `--disable-safety-supervisor`).

Guards: learning-modifier contract (demo_only / mode demo_auto_learning / not
expired / no forbidden keys live·live_trading·order_send·volume·lot·leverage·bypass
/ clamp -20..+12), open-position (max 1), no-stacking, trade-frequency
(<=6/h + >=120s gap), loss-streak (3 → 30m cooldown), daily-drawdown (warn 4% /
block 7%), spread (balanced 35pt / scalp 25pt), MT5 health (demo + symbol
selected + fresh tick + free margin), macro-lockout respect, kill-switch respect.
An invalid/expired modifier file DISABLES learning for the run (in-memory only —
files are never deleted) and the worker continues safely.

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder"
# inspect the supervisor (read-only, offline):
python scripts/run_gold_bot_safety_probe.py
python scripts/run_gold_bot_safety_probe.py --json

# observe worker shows the supervisor banner + per-iteration safety status:
python scripts/run_gold_bot_worker.py --mode observe --risk-mode scalp --use-learning-modifiers --max-iterations 3 --interval-seconds 5

# demo mode WITHOUT the execute flags still sends nothing:
python scripts/run_gold_bot_worker.py --mode demo --risk-mode scalp --use-learning-modifiers --max-iterations 1 --interval-seconds 5

# intentional demo execution STILL requires the existing explicit flags:
python scripts/run_gold_bot_worker.py --mode demo --risk-mode scalp --use-learning-modifiers --auto-execute-demo --confirm-demo-order --max-iterations 1
```

Worker CLI additions (limits only — the supervisor always runs):
`--max-open-positions 1 --max-trades-per-hour 6 --min-seconds-between-trades 120
--max-consecutive-losses 3 --cooldown-minutes-after-loss-streak 30
--max-spread-points <override>`.

When the supervisor blocks an armed demo order the worker journals
`execution_status = blocked_by_safety_supervisor` with the blocker reason in the
`safety` field, and appends `data/gold_bot/safety/safety_events.jsonl`. State
(recent trades, loss streak, cooldown) lives in
`data/gold_bot/safety/safety_state.json`. Both are gitignored. Live-verified
(fake connector): armed demo + kill switch → heartbeat
`blocked_by_safety_supervisor` / `safety - CRITICAL kill_switch`, nothing sent.
Tests `python -m pytest tests/test_gold_bot_demo_safety_supervisor.py tests/test_gold_bot_worker.py -q`
(no MT5/internet).

## LM88A Demo auto-session runner (bounded MT5 demo session, demo-only)

`services/gold_bot_demo_session_runner.py` composes the worker + demo learning
modifiers + LM87A safety supervisor into ONE controlled session with hard limits
(wall-clock duration, max iterations, max trades, max runtime-loss %, auto-stop on
critical / 3 consecutive safety blocks) and a written report. No strategy logic is
duplicated — it drives `GoldBotWorker` through a new per-iteration hook. **MT5 DEMO
ONLY, NEVER LIVE, SAFETY SUPERVISOR ALWAYS ON, LEARNING CONFIDENCE-ONLY.**

OBSERVE-ONLY by default — **sends nothing** unless `--confirm-demo-session` is
passed, and even then the worker's own demo guards (`--mode demo` +
`--auto-execute-demo` + `--confirm-demo-order`, verified demo account, risk gate,
supervisor) still apply.

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder"
# observe-only session (no orders), short:
python scripts/run_gold_bot_demo_session.py --duration-minutes 1 --max-iterations 3
python scripts/run_gold_bot_demo_session.py --duration-minutes 1 --max-iterations 3 --use-learning-modifiers

# ARMED demo session (intentional only — still gated by every demo guard):
python scripts/run_gold_bot_demo_session.py --confirm-demo-session --duration-minutes 5 --max-trades 3 --risk-mode scalp --use-learning-modifiers

# PowerShell launchers (default observe; -ConfirmDemoSession to arm):
.\scripts\start_gold_bot_demo_session.ps1
.\scripts\start_gold_bot_demo_session.ps1 -ConfirmDemoSession -DurationMinutes 5 -MaxTrades 3
```

CLI: `--symbol --risk-mode --timeframe --interval-seconds --duration-minutes
--max-iterations --max-trades --max-runtime-loss-pct --use-learning-modifiers /
--no-learning-modifiers --calendar-file --macro-events-file --confirm-demo-session
--json`. Stop reasons: `duration_reached` · `max_iterations_reached` ·
`max_trades_reached` · `critical_safety` · `consecutive_safety_blocks` ·
`runtime_loss_limit` · `keyboard_interrupt`.

Report `data/gold_bot/sessions/session_<ts>.json` + `session_latest.json` (session_id,
started/ended, mode observe|demo, learning enabled + active modifier count,
iterations, decisions L/S/no_trade, macro_lockout count, demo orders attempted/sent,
blocked_by_safety count + reasons, start/end equity, realized PnL, stop reason,
warnings) + event log `session_<ts>.jsonl` (session_start / heartbeat / decision /
order_attempt / order_sent / safety_block / session_stop). All gitignored.

Live-verified (real demo terminal, Sat market closed): observe → 3 iters, 0 orders,
report written; armed → supervisor blocked every attempt (`mt5_health_guard` stale
tick), **0 sent**, auto-stopped `consecutive_safety_blocks`. Tests
`python -m pytest tests/test_gold_bot_demo_session_runner.py -q` (fake worker, no
MT5/internet).

## LM89A Trade outcome feedback loop (real demo P&L → safety + learning)

`services/gold_bot_trade_outcomes.py` reads MT5 **demo** deal history for the bot's
own trades (filtered by symbol + magic 810810), reconstructs entry/exit into
`TradeOutcome` records (win/loss/breakeven/open, exit_reason sl|tp|manual_close|
unknown from the exit comment), and feeds the REAL outcomes back into (a) the LM87A
safety supervisor loss-streak state — making that guard real, not a placeholder —
and (b) the LM86A learning journal as `demo_trade_outcome` events (the dataset for a
later scorecard-ingestion patch). **This patch SENDS NO ORDERS and changes no
strategy logic — it only reads history and writes local feedback files.**

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder"
# read-only: reconstruct + print bot demo trades (writes nothing):
python scripts/run_gold_bot_trade_outcomes_probe.py --symbol XAUUSD --magic 810810

# write outcomes + learning feedback for the latest session window:
python scripts/run_gold_bot_trade_outcomes_probe.py --session-file data/gold_bot/sessions/session_latest.json --write

# explicit window / JSON:
python scripts/run_gold_bot_trade_outcomes_probe.py --from-time 2026-06-13T00:00:00 --to-time 2026-06-13T23:59:59 --json
```

Session integration: an ARMED demo session auto-syncs outcomes after it ends
(default on; `--no-sync-outcomes` to skip; observe sessions skip with reason
`observe_session`). The session report gains `outcomes_synced`, `outcomes_count`,
`outcome_wins/losses/breakeven/open`, `outcome_realized_pnl`, `outcome_file`,
`safety_state_updated`, `outcome_sync_reason`; a `outcome_sync` JSONL event is
appended.

```powershell
# armed demo session — syncs real outcomes into safety + learning afterwards:
python scripts/run_gold_bot_demo_session.py --confirm-demo-session --duration-minutes 5 --max-trades 3 --risk-mode scalp --use-learning-modifiers
# same, but skip the outcome sync:
python scripts/run_gold_bot_demo_session.py --confirm-demo-session --duration-minutes 5 --max-trades 3 --risk-mode scalp --use-learning-modifiers --no-sync-outcomes
```

Outcome rules: pnl (net = profit+commission+swap) > +0.01 → win; < -0.01 → loss;
else breakeven; no exit deal → open. Partial closes are aggregated with a warning.
Generated `data/gold_bot/trade_outcomes/outcomes_<ts>.json` + `outcomes_latest.json`
+ `outcomes_events.jsonl` are gitignored; learning feedback appends to
`data/gold_bot/learning/learning_events.jsonl`. Live-verified: probe read the real
MetaQuotes-Demo account (5 deals scanned, 0 match magic 810810 — bot hasn't traded
yet); synthetic 3-loss run armed the supervisor cooldown + wrote `demo_trade_outcome`
journal rows. Tests `python -m pytest tests/test_gold_bot_trade_outcomes.py -q`
(fake deals, no MT5/internet).

## LM89B Real-trade learning ingestion (blend replay + real demo P&L)

The learning system now READS the LM89A `demo_trade_outcome` events from
`learning_events.jsonl` and blends real demo fills into the scorecard / learning
cycle. Replay stays the base signal; real demo outcomes carry a higher weight
(they include actual execution/spread/slippage) but **cannot dominate a small
sample**. Learning stays demo-only + confidence-only — no volume/lot change, no
orders, no live trading.

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder"
# inspect the real demo-trade dataset (read-only; safe with no data yet):
python scripts/run_gold_bot_real_trade_learning_probe.py
python scripts/run_gold_bot_real_trade_learning_probe.py --min-real-trades 5 --json

# scorecard blending replay + real demo:
python scripts/run_gold_bot_learning_scorecard.py --horizon 15 --min-samples 10 --include-real-trades --real-trade-weight 2.0 --min-real-trades 5

# learning cycle blending real demo (default OFF; enable once demo sessions have trades):
python scripts/run_gold_bot_learning_cycle.py --timeframe M1 --risk-mode balanced --max-bars 500 --horizon 15 --min-samples 10 --include-real-trades --real-trade-weight 2.0
```

Weighting:
`combined = (replay_exp*replay_n + real_avg_pts*real_n*weight) / (replay_n + real_n*weight)`.
With `weight 2.0`, 8 demo trades count as 16 vs a 445-trade replay sample — real
demo nudges, doesn't flip. Below `--min-real-trades` (default 5) a setup is marked
`insufficient` and a contradiction with replay adds a reason warning.

Scorecard / preview gain per setup: `replay_trade_count`, `real_trade_count`,
`real_avg_pnl[_points]`, `combined_expectancy`, `combined_winrate`,
`real_sample_quality`, `recommended_status_combined`. Modifier reasons read e.g.
`"combined replay+demo: replay exp -45.0pt over 607, demo exp -3.4pt over 7,
combined -44.06pt"`. Cycle summary gains `real_trades_used` / `real_trade_count` /
`real_trade_weight`.

Generated (gitignored): `data/gold_bot/learning/real_trade_scorecard_latest.json`,
`real_trade_learning_summary.json`, `real_trade_learning_events.jsonl`. Duplicates
(by trade_id) and open/unknown outcomes are ignored (use `--include-open` to keep
open). Live-verified: probe is safe with no demo outcomes (prints a hint, exits 0);
scorecard blended real replay (fvg_retest 607) with 7 synthetic demo trades →
combined -44.06pt; tests `python -m pytest tests/test_gold_bot_real_trade_learning.py -q`
(fake events, no MT5/internet).

## LM90A Session review digest (offline Markdown + JSON report)

`services/gold_bot_session_review.py` joins the artifacts the LM86-LM89 loop
already writes - the demo session report (LM88A), reconstructed trade outcomes
(LM89A), safety events + state (LM87A), learning events + cycle summaries
(LM86A/C/89B), active modifiers + scorecard - into ONE human-readable Markdown +
machine-readable JSON review. It is the reporting layer that makes the bot's
autonomous demo behavior legible BEFORE any Discord/UI surface. **Pure offline:
reads local JSON/JSONL only - no MT5, no orders, no HTTP, no strategy change.**
Missing optional inputs degrade to warnings (never crash).

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder"
# preview what would be read/written (no files):
python scripts/run_gold_bot_session_review.py --dry-run
# build the review from the latest session:
python scripts/run_gold_bot_session_review.py
# or a specific session report + JSON output:
python scripts/run_gold_bot_session_review.py --session-file data/gold_bot/sessions/session_latest.json --json
```

CLI: `--session-file --out-dir --learning-dir --safety-dir --trade-outcomes-dir
--json --dry-run`. No session report -> clear error ("Run run_gold_bot_demo_session.py
first."). Markdown sections: Summary / Decisions / Orders & Outcomes / Safety /
Learning / Key Findings / Next Actions / Files Used / Warnings (tables, no raw JSON
dump). Findings + next-actions are DERIVED only (no hallucination) e.g. "Armed demo
session sent no orders; blocked by mt5_health_guard (likely stale tick / market
closed)", "Latest learning candidate was rejected: ...", "Loss-streak cooldown is
active until ...".

Generated (gitignored): `data/gold_bot/reviews/session_review_<id>.md` + `.json`
+ `session_review_latest.md` + `.json`. Live-verified on the real armed session:
review correctly showed mode demo, stop `consecutive_safety_blocks`, 3 orders
attempted / 0 sent / blocked mt5_health_guard x3, active modifiers (3x -8), the
LM86C cycle REJECTED (-41.1 -> -50.7pt), and next-actions to check tick/spread.
Tests `python -m pytest tests/test_gold_bot_session_review.py -q` (fake temp files,
no MT5/internet).

## LM90B Discord session-review sender (optional, env-only webhook)

`services/gold_bot_discord_review_sender.py` reads the LM90A review files
(`session_review_latest.json` for structured fields + `.md` optionally) and posts
a CONCISE session review to Discord. It adds NO trading logic - it only formats +
transmits the existing digest. **Preview by default (no network); sending requires
BOTH `--send-discord` AND the env var `LUMORA_GOLD_DISCORD_WEBHOOK_URL`.** The
webhook is never hardcoded, never committed, never printed in full (redacted to
`https://discord.com/api/webhooks/...REDACTED`). HTTP is stdlib `urllib` only -
reuses the LM51B sender, no new dependencies. No MT5, no orders.

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder"
# preview only (no send, no env var needed):
python scripts/run_gold_bot_discord_review.py
# if no review exists yet, build one first:
python scripts/run_gold_bot_session_review.py
python scripts/run_gold_bot_discord_review.py

# send intentionally (webhook ONLY from env, never commit it):
$env:LUMORA_GOLD_DISCORD_WEBHOOK_URL = "YOUR_WEBHOOK_URL"
python scripts/run_gold_bot_discord_review.py --send-discord
Remove-Item Env:LUMORA_GOLD_DISCORD_WEBHOOK_URL
```

CLI: `--review-md --review-json --send-discord --dry-run --max-findings 5
--max-actions 5 --timeout-seconds 10 --json`. Behavior: default preview; `--send-discord`
sends; `--send-discord` + `--dry-run` -> error (exit 2); `--send-discord` without the
env webhook -> clear error (exit 2, no network); missing review JSON -> "No session
review found. Run run_gold_bot_session_review.py first." (exit 1). Message: title +
session/mode/symbol/risk/stop + Decisions/Orders/Outcomes/Safety/Learning lines +
top-5 key findings + top-5 next actions, hard-capped at Discord's 2000-char limit.
Live-verified: preview rendered the real session review (stop consecutive_safety_blocks,
3 attempted/0 sent, mt5_health_guard x3, modifiers 3x -8, cycle rejected) with NO
network call. Tests `python -m pytest tests/test_gold_bot_discord_review_sender.py -q`
(HTTP mocked, no real network/Discord/MT5).

## LM91A Local read-only Gold Bot status API + panel (web)

`lumora-web/app/api/gold-bot/status/route.ts` (`GET /api/gold-bot/status`,
`force-dynamic` + `runtime nodejs`) + `lib/gold-bot-status.ts` read the local demo
artifacts (`data/gold_bot/…`: session_latest, session_review_latest, outcomes_latest,
safety_state, active_demo_modifiers, scorecard_latest, cycles/cycle_events.jsonl,
worker_status) and return ONE tolerant status object. A compact READ-ONLY panel
`components/gold-bot/GoldBotStatusPanel.tsx` is mounted on the existing `/gold-bot`
page (after the planned-modules band). **STRICT read-only: no trading controls, no
start/stop/order buttons — the only button reloads status.** The API NEVER calls
MT5, runs Python/shell, makes external HTTP, or reads secrets / the Discord webhook
env (Discord send-readiness is reported as `unknown_env_not_checked`). Missing files
→ flags + warnings, never a crash.

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder\lumora-web"
npm run lint
npm run build
npm run dev
# then open:
#   http://localhost:3000/gold-bot                (read-only status panel near the bottom)
#   http://localhost:3000/api/gold-bot/status     (raw JSON)
```

Static safety invariants (offline, no Node): `python -m pytest tests/test_gold_bot_status_api.py -q`
(asserts force-dynamic, no `process.env`/shell/MT5/webhook/external-http in the
server files, single refresh button + "no trading controls" in the panel). Browser-
verified against the real local data: panel showed session `consecutive_safety_blocks`,
orders 3/0/3, blockers `mt5_health_guard x3`, modifiers 3 ACTIVE (-8), scorecard
`avoid`, latest cycle `REJECTED`; API `readyToSend: unknown_env_not_checked`.

## LM92A Scheduled local runner (one-command demo-learning-review cycle)

`services/gold_bot_scheduled_runner.py` chains the EXISTING safe scripts into one
repeatable cycle via subprocess — it adds NO trading/strategy logic. Order:
preflight → demo session → outcome sync → learning cycle → session review → discord
preview. **DEFAULT = plan/dry-run: prints the steps and runs NOTHING.** Trading
happens only with BOTH `--execute` AND `--confirm-demo-session` (and even then the
real session runner + safety supervisor + risk gate still gate every order).
Discord sends only with `--send-discord`. No webhook value is ever read or logged
(run logs redact webhook-like strings).

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder"
# plan only (safe default — nothing runs):
python scripts/run_gold_bot_daily_cycle.py
# execute the safe OFFLINE steps, no demo trades:
python scripts/run_gold_bot_daily_cycle.py --execute --skip-session --include-real-trades
# full guarded loop (demo trades go through the session runner + supervisor):
python scripts/run_gold_bot_daily_cycle.py --execute --confirm-demo-session --duration-minutes 5 --max-trades 3 --risk-mode scalp --use-learning-modifiers --include-real-trades
# PowerShell (defaults to plan):
.\scripts\start_gold_bot_daily_cycle.ps1
.\scripts\start_gold_bot_daily_cycle.ps1 -Execute -ConfirmDemoSession -DurationMinutes 5 -MaxTrades 3 -RiskMode scalp -UseLearningModifiers -IncludeRealTrades
```

Flags: `--execute --confirm-demo-session --duration-minutes --max-trades --risk-mode
--use-learning-modifiers --include-real-trades --real-trade-weight --min-real-trades
--send-discord --skip-session/--skip-outcomes/--skip-learning-cycle/--skip-review/
--skip-discord-preview --continue-on-error --dry-run-log --json` (+ `--cycle-*`
learning overrides). Per step: subprocess `cwd=repo root`, `timeout 900s`, captured
stdout/stderr tails (redacted). On failure the run STOPS unless `--continue-on-error`.
Run logs `data/gold_bot/runs/run_<ts>.json` + `.jsonl` + `run_latest.*` are written
only when executing (or `--dry-run-log`) and are gitignored. Live-verified: plan
mode ran no subprocess; `--execute --skip-session --skip-outcomes --skip-discord-preview
--include-real-trades` ran learning_cycle + session_review → SUCCESS, log written.
Tests `python -m pytest tests/test_gold_bot_scheduled_runner.py -q` (subprocess
mocked, no MT5/internet).

## LM92B First market-open demo run preflight (read-only GO / NO-GO)

`services/gold_bot_first_run_preflight.py` is a READ-ONLY checklist that tells the
owner GO/NO-GO before a short autonomous demo run. It runs the EXISTING read-only
probes (MT5 connector probe, safety probe, daily-cycle PLAN) as subprocesses, reads
local artifacts, checks the kill switch / live flags in-process, and prints the
exact next command. **Places NO orders, sends NO Discord, prints NO secrets, no MT5
import.** Full runbook: `docs/gold_bot/FIRST_MARKET_OPEN_DEMO_RUN.md`.

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder"
# weekend / offline prep (tick check SKIP, still reaches GO):
python scripts/run_gold_bot_first_run_preflight.py --skip-mt5 --skip-safety
# market-open preflight:
python scripts/run_gold_bot_first_run_preflight.py --use-learning-modifiers --include-real-trades --write
# PowerShell wrapper (defaults to a full read-only preflight):
.\scripts\start_gold_bot_first_run_preflight.ps1 -SkipMt5 -SkipSafety
```

Checks (PASS/WARN/FAIL/SKIP): repo_root · required_scripts · daily_cycle_plan ·
mt5_demo_tick · safety_probe · kill_switch · macro_lockout · local_artifacts ·
discord. NO-GO if any BLOCKING check FAILs (required scripts, daily plan, MT5
stale/closed, safety cooldown/critical, kill switch, macro lockout). On GO it prints
the conservative `start_gold_bot_daily_cycle.ps1 -Execute -ConfirmDemoSession …`
command; on NO-GO it prints the reasons + read-only troubleshooting commands.
Flags: `--skip-mt5 --skip-safety --duration-minutes --max-trades --risk-mode
--use-learning-modifiers --include-real-trades --send-discord --check-discord-env
--write --timeout-seconds --json`. Webhook env checked for PRESENCE only (and only
with `--check-discord-env`); value never read/printed. Generated
`data/gold_bot/preflight/preflight_<ts>.json` + `preflight_latest.json` (only with
`--write`) are gitignored. Live-verified: offline prep + full real preflight both
→ GO (MT5 demo connected, read-only); mocked stale tick → NO-GO with reasons +
troubleshooting. Tests `python -m pytest tests/test_gold_bot_first_run_preflight.py -q`
(subprocess + safety/macro mocked, no MT5/internet).

## LM93A Execution environment abstraction (demo only; live hard-locked)

`services/gold_bot_execution_environment.py` replaces scattered "demo" naming with a
clear model: **environment** (`paper`|`demo`|`live`) × **mode** (`observe`|`execute`).
`ExecutionContext` + `assert_execution_allowed` gate codes: `OBSERVE_ONLY` /
`PAPER_NO_BROKER` / `DEMO_ALLOWED` / `LIVE_NOT_IMPLEMENTED` / `UNKNOWN_ACCOUNT`. **It
is an ADDITIONAL gate — never replaces the confirm flags, safety supervisor or risk
gate.** Live is hard-locked: even with `LUMORA_GOLD_ALLOW_LIVE_TRADING=I_UNDERSTAND_LIVE_RISK`
+ `--allow-live-trading`, the gate returns `LIVE_NOT_IMPLEMENTED`; `--environment live`
makes every CLI exit 2. Full reference: `docs/gold_bot/EXECUTION_ENVIRONMENTS.md`.

Legacy mapping (commands unchanged): `--mode observe` → demo/observe, `--mode demo`
→ demo/execute (still needs the confirm flags). New optional flags on worker /
demo-session / daily-cycle / preflight: `--environment` + `--allow-live-trading`
(no-op). Framing now appears in: worker banner (`execution : environment: demo | …
| live: locked`) + journal `execution_context`; session report `environment` /
`execution_mode` / `live_locked` + banner; supervisor decision `details.execution`;
daily-cycle plan (`environ. : demo | execution: plan | live: locked`); preflight
(`Execution environment: demo` / `Live trading: LOCKED`).

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder"
python -m pytest tests/test_gold_bot_execution_environment.py -q
python scripts/run_gold_bot_daily_cycle.py                # plan shows environment/live framing
python scripts/run_gold_bot_worker.py --mode observe --risk-mode scalp --max-iterations 1   # legacy flag still works
```

No live trading enabled, no orders, no MT5 required in tests. Live-verified: context
matrix (demo/observe→OBSERVE_ONLY, demo/execute→DEMO_ALLOWED, paper→PAPER_NO_BROKER,
live→LIVE_NOT_IMPLEMENTED), CLIs refuse `--environment live`, 417 existing gold_bot
tests still green. Tests `python -m pytest tests/test_gold_bot_execution_environment.py -q`.

## LM94A Local command gateway (whitelisted, dry-run default; no arbitrary shell)

Local-only foundation for future one-click website controls. Runs ONE whitelisted
Gold Bot action as a subprocess with strict caps + redacted logs. **Default is
dry-run** (validate + print the command, run nothing). No UI, no API route, no live
trading, no free-form shell, no webhook value read/printed. Full runbook:
`docs/gold_bot/LOCAL_COMMAND_GATEWAY.md`.

Actions: `preflight` · `daily_cycle_offline` · `daily_cycle_guarded_demo` ·
`session_review` · `discord_preview` · `discord_send`. Guarded demo needs
`--confirm-guarded-demo` and obeys caps (duration ≤15/default 5, max_trades ≤5/
default 3, risk_mode ∈ {safe,balanced,scalp}). `discord_send` needs BOTH
`--allow-discord-send` AND env `LUMORA_GOLD_DISCORD_WEBHOOK_URL` present.

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder"
# dry-run (default): validate + show command, run nothing
python scripts/run_gold_bot_command_gateway.py --action preflight
python scripts/run_gold_bot_command_gateway.py --action daily_cycle_guarded_demo --confirm-guarded-demo
# execute
python scripts/run_gold_bot_command_gateway.py --action daily_cycle_offline --execute --include-real-trades --write-log
python scripts/run_gold_bot_command_gateway.py --action session_review --execute --write-log
python scripts/run_gold_bot_command_gateway.py --action discord_preview --execute --write-log
# tests (subprocess + env mocked; no MT5/Discord/internet)
python -m pytest tests/test_gold_bot_command_gateway.py -q
python -m compileall services/gold_bot_command_gateway.py scripts/run_gold_bot_command_gateway.py
```

Exit codes: planned/success 0, failed 1, blocked 2. Run logs (gitignored):
`data/gold_bot/commands/command_<ts>.json|.jsonl` + `command_latest.*`. Old direct
script commands still work unchanged. Live-verified: dry-run preflight →
`python scripts/run_gold_bot_first_run_preflight.py` (nothing run); guarded demo
without confirm → BLOCKED exit 2; `daily_cycle_offline --execute` → SUCCESS exit 0,
demo session skipped (no demo trades), discord preview only, run + command logs
written, 0 redactions.

## LM94B Local Gold Bot web control panel (calls the LM94A gateway; local-only)

Web control panel on `/gold-bot` that triggers the LM94A gateway via
`POST /api/gold-bot/command`. LOCAL-OWNER tooling: whitelisted actions only, no
live trading, no order buttons, no free-form command input, no secrets. The route
validates + caps, then `execFile("python", [argv])` (NEVER a shell, cwd=repo root)
the existing gateway script; the gateway re-validates and is the final authority.

Buttons: Preflight · Offline Cycle · Build Review · Discord Preview (safe, one
click) + gated Guarded Demo 5m (confirm checkbox) + Send Discord (confirm checkbox,
needs `LUMORA_GOLD_DISCORD_WEBHOOK_URL` env — value never read/shown). Result
console shows status/reason/command/stdout+stderr tail/run log/timestamp.

```powershell
# Python static safety tests (POST-only, argv-not-shell, caps, whitelist, no secrets/MT5/orders)
cd "C:\Users\Joshua\Desktop\wallet finder"
python -m pytest tests/test_gold_bot_web_command_api.py -q

# web build + run
cd "C:\Users\Joshua\Desktop\wallet finder\lumora-web"
npm run lint
npm run build
npm run dev
# open http://localhost:3000/gold-bot   (Gold Bot Controls panel above the read-only status panel)
```

Try Preflight / Offline Cycle / Build Review / Discord Preview. Do NOT click
Guarded Demo unless the market is open and you intend it; do NOT Send Discord unless
the env webhook is set. Local-only guard: non-local hosts get 403 in production
(dev is always allowed); add real local-token/CSRF auth before any non-local deploy.
Live-verified over HTTP (dev): preflight execute=false → `planned`; guarded demo
without confirm → `blocked`; `discord_preview` execute=true → `success` (offline
preview, 0 redactions). lint + build clean, `/api/gold-bot/command` is ƒ dynamic.

## LM95A Gold Bot page hierarchy polish (presentation only; no logic/API/trading change)

Reorganized `/gold-bot` into a clear command-room hierarchy with subtle section
headers: **OPERATE** (controls + latest gateway result, amber), **OBSERVE**
(read-only status telemetry, cyan), **LEARN** (strategy instrument + guardrail
modules, violet), **REPORT** (compact latest review, zinc). Operations + status now
sit at the top; the chart/brain/feed room + planned modules moved below. New
presentational `components/gold-bot/GoldBotSectionCard.tsx` (eyebrow + hairline, no
hooks/data). Review key-findings/next-actions were LIFTED out of the status panel
into the REPORT card (single `/api/gold-bot/status` fetch, no duplicate copy) via
new `GoldBotStatusPanel` props `showReview`/`onData` (backward-compatible; the panel
stays read-only with its one Refresh button). No trading logic, no API change, no
new commands, no live controls, gateway confirmations unchanged, Heatmap untouched.

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder"
python -m pytest tests/test_gold_bot_ui_hierarchy.py -q

cd "C:\Users\Joshua\Desktop\wallet finder\lumora-web"
npm run lint
npm run build
npm run dev
# open http://localhost:3000/gold-bot  (OPERATE → OBSERVE → LEARN → REPORT)
```

Live-verified (dev): the four sections render in order; OBSERVE shows
session/safety/learning/outcomes (review removed, no duplication); status fetched
real data once (no fetch loop); controls + gated checkboxes intact; no console
errors; lint + build clean (`/gold-bot` 17.5 kB, APIs unchanged ƒ dynamic).

## LM95B Gold Bot operations layout fix (compact terminal; no logic/API/trading change)

Re-laid out `/gold-bot` so the command room reads like a trading terminal, not a
control dump. Sections regrouped **OPERATE → WATCH → LEARN → REPORT**. The controls
became a COMPACT operations bar (`GoldBotControlPanel` rewritten: one row of small
toolbar buttons Preflight | Offline Cycle | Build Review | Discord Preview, compact
guarded Guarded Demo 5m + Send Discord each behind their confirm checkbox, badges
LOCAL ONLY / DEMO ENV / LIVE LOCKED / GATEWAY, result console now collapsible +
capped `max-h-[220px]`). New compact `GoldBotStatusStrip.tsx` (pure, one-line:
session/stop · orders a/s/blk · safety blocker · mods · cycle verdict · W/L/BE) sits
under WATCH above the chart; the full read-only `GoldBotStatusPanel` moved into a
collapsed `<details>` under REPORT (still the single `/api/gold-bot/status` fetcher
feeding the strip + review via onData). The chart/brain/feed room moved UP under
WATCH. No trading logic, no API change, no new commands, no live controls, gateway
confirmations unchanged, Heatmap untouched.

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder"
python -m pytest tests/test_gold_bot_ui_hierarchy.py -q

cd "C:\Users\Joshua\Desktop\wallet finder\lumora-web"
npm run lint
npm run build
npm run dev
# open http://localhost:3000/gold-bot  (compact bar + status strip, chart high)
```

Live-verified (dev, 1366×900): chart top at y≈557 (visible in the first screen);
operations bar ≈166px tall with six 25px toolbar buttons (no giant cards); status
strip renders one line from real data; full status panel collapsed inside REPORT
`<details>` (open=false); no console errors; lint + build clean (`/gold-bot`
18.1 kB, APIs still ƒ dynamic).

## LM95C Gold Bot layout + mode-language simplification (presentation/copy only)

Fixed the big empty block under the chart and clarified the mode language. **Layout:**
the WATCH row was unbalanced (left rail ≈1008px vs chart column ≈502px → ~506px blank
under the chart). The status strip moved UNDER the chart and the **Detectors** panel
was split out of `BotBrainRail` (new exported `BotDetectorRail`) and rendered under the
chart too, so the center column fills the row — gap dropped to ~139px (columns ≈681 /
734 / 820). Grid already `items-start`; no min-heights. **Mode language:** removed the
fake Watch/Hunt/Review tabs and the Aggressive risk mode; header now shows clear,
non-overlapping badges **ENV DEMO · EXEC OBSERVE · LIVE LOCKED · LEARNING ACTIVE**, risk
chips **Safe / Balanced / Scalp** (matches the gateway), one **"Live locked · demo
guarded"** badge (no repeated "no live" prose). Chart header → "M5 · Demo environment"
+ **VISUAL MOCK** badge; chart footer → MODE OBSERVE · EXEC DEMO GUARDED. Footer line →
"RISK CHECKED · MODE OBSERVE · EXECUTION DEMO GUARDED · RISK … · ENV DEMO". No trading
logic, no API change, no new commands, no live, gateway confirmations intact, Heatmap
untouched.

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder"
python -m pytest tests/test_gold_bot_ui_hierarchy.py -q

cd "C:\Users\Joshua\Desktop\wallet finder\lumora-web"
npm run lint
npm run build
npm run dev
# open http://localhost:3000/gold-bot
```

Live-verified (dev, 1366×900): under-chart gap 506px→139px (≈73% less), columns
681/734/820, chart top y≈514 (first screen); ENV DEMO/EXEC OBSERVE/LIVE LOCKED/LEARNING
ACTIVE + SCALP + VISUAL MOCK render; Aggressive/Hunt/"PAPER MODE"/"no broker connection"/
"EXEC DISABLED" all gone; no console errors; lint + build clean.

## LM96A Gold Bot Windows Task Scheduler helper (offline maintenance only)

PowerShell helper to schedule the OFFLINE maintenance cycle on Windows via the LM94A
gateway. NO demo trading by default, no live, no Discord send, no secrets, no admin.
The scheduled run is exactly the whitelisted offline gateway action. Full runbook:
`docs/gold_bot/WINDOWS_TASK_SCHEDULER.md`.

```powershell
cd "C:\Users\Joshua\Desktop\wallet finder"

# manual one-off offline cycle (no demo session, Discord preview only)
.\scripts\start_gold_bot_offline_cycle.ps1
.\scripts\start_gold_bot_offline_cycle.ps1 -LogTranscript   # -> data/gold_bot/task_logs/*.log (gitignored)

# plan the scheduled task (DEFAULT: nothing registered)
.\scripts\create_gold_bot_offline_task.ps1 -WhatIfPlan

# register (explicit)
.\scripts\create_gold_bot_offline_task.ps1 -Register -Frequency Hourly -EveryHours 1
.\scripts\create_gold_bot_offline_task.ps1 -Register -Frequency Daily -At "09:00"
.\scripts\create_gold_bot_offline_task.ps1 -Register -Force                 # replace existing

# disable / delete
Disable-ScheduledTask  -TaskName "LumoraGoldBotOfflineCycle"
Unregister-ScheduledTask -TaskName "LumoraGoldBotOfflineCycle" -Confirm:$false

# tests (static; no registration, no MT5, no internet)
python -m pytest tests/test_gold_bot_windows_task_scheduler.py -q
```

Scheduled run executes: `python scripts/run_gold_bot_command_gateway.py --action
daily_cycle_offline --execute --include-real-trades --write-log`. Registers in the
current-user limited context (no admin). Live-verified: `-WhatIfPlan` registers
nothing (exit 0); the manual wrapper ran the offline cycle SUCCESS exit 0 (demo
session SKIPPED, Discord preview only, run + command logs written, 0 redactions).
12 static tests pass.
