"""
scripts/run_data_workers.py
---------------------------
LM77A — cloud supervisor for the live DATA workers (Binance -> Supabase).

Runs both market-data writers as child processes and keeps them alive:
  1. Heatmap   : run_binance_ws_heatmap_live.py  (order-book heatmap)
  2. Whale     : run_binance_trade_stream_smoke.py (whale_events)

DATA ONLY. No MetaTrader, no trading, no orders — this never touches the
gold-bot trading path. Each child restarts on exit with capped backoff; the
backoff resets after the child has stayed up a while. SIGTERM/SIGINT are
propagated so the host can stop the service cleanly.

Required env (set in the host dashboard, never committed):
    SUPABASE_URL
    SUPABASE_SERVICE_ROLE_KEY
Optional env (defaults shown):
    HEATMAP_SYMBOL=BTCUSDT
    HEATMAP_TIMEFRAMES=5m,15m,1h
    HEATMAP_WRITE_INTERVAL=2
    WHALE_SYMBOLS=BTCUSDT,ETHUSDT,SOLUSDT

Run locally (needs the two env vars):  python scripts/run_data_workers.py
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent

BACKOFF_START = 5.0
BACKOFF_MAX = 60.0
# Uptime after which a child is considered "stable" and its backoff resets.
STABLE_AFTER = 120.0
POLL_SECONDS = 2.0


def _env(name: str, default: str) -> str:
    val = os.environ.get(name, "").strip()
    return val or default


def build_workers() -> list[dict]:
    py = sys.executable
    heatmap_symbol = _env("HEATMAP_SYMBOL", "BTCUSDT")
    heatmap_tfs = _env("HEATMAP_TIMEFRAMES", "5m,15m,1h")
    heatmap_interval = _env("HEATMAP_WRITE_INTERVAL", "2")
    whale_symbols = _env("WHALE_SYMBOLS", "BTCUSDT,ETHUSDT,SOLUSDT")
    return [
        {
            "name": "heatmap",
            "cmd": [
                py, "scripts/run_binance_ws_heatmap_live.py",
                "--symbol", heatmap_symbol,
                "--timeframes", heatmap_tfs,
                "--write-interval", heatmap_interval,
                "--target", "supabase",
                "--forever",
            ],
        },
        {
            "name": "whale",
            "cmd": [
                py, "scripts/run_binance_trade_stream_smoke.py",
                "--symbols", whale_symbols,
                "--target", "supabase",
                "--forever",
            ],
        },
    ]


def log(msg: str) -> None:
    print(f"[supervisor] {msg}", flush=True)


def main() -> int:
    # Fail fast with a clear message if the write credentials are absent.
    if not os.environ.get("SUPABASE_URL") or not os.environ.get("SUPABASE_SERVICE_ROLE_KEY"):
        log("FATAL: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set.")
        return 2

    workers = build_workers()
    procs: dict[str, subprocess.Popen] = {}
    backoff: dict[str, float] = {}
    started_at: dict[str, float] = {}

    def spawn(w: dict) -> None:
        log(f"starting '{w['name']}': {' '.join(w['cmd'])}")
        procs[w["name"]] = subprocess.Popen(w["cmd"], cwd=str(_REPO_ROOT))
        started_at[w["name"]] = time.monotonic()

    for w in workers:
        backoff[w["name"]] = BACKOFF_START
        spawn(w)

    stop = {"flag": False}

    def handle(signum, _frame) -> None:
        log(f"signal {signum} — shutting down children")
        stop["flag"] = True

    signal.signal(signal.SIGTERM, handle)
    signal.signal(signal.SIGINT, handle)

    try:
        while not stop["flag"]:
            for w in workers:
                name = w["name"]
                p = procs[name]
                code = p.poll()
                if code is None:
                    continue
                uptime = time.monotonic() - started_at[name]
                if uptime >= STABLE_AFTER:
                    backoff[name] = BACKOFF_START
                wait = backoff[name]
                log(f"'{name}' exited (code={code}, uptime={uptime:.0f}s) — "
                    f"restart in {wait:.0f}s")
                # Sleep in small slices so a stop signal is honored promptly.
                slept = 0.0
                while slept < wait and not stop["flag"]:
                    time.sleep(min(1.0, wait - slept))
                    slept += 1.0
                if stop["flag"]:
                    break
                spawn(w)
                backoff[name] = min(backoff[name] * 2, BACKOFF_MAX)
            time.sleep(POLL_SECONDS)
    finally:
        for name, p in procs.items():
            if p.poll() is None:
                log(f"terminating '{name}'")
                p.terminate()
        deadline = time.monotonic() + 10
        for name, p in procs.items():
            try:
                p.wait(timeout=max(0.0, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                log(f"killing '{name}'")
                p.kill()
    log("stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
