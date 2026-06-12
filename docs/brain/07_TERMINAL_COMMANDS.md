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
