"""
scripts/run_gold_bot_history_probe.py
---------------------------------------
LM84A — Inspect locally-stored XAUUSD history (READ-ONLY, no MT5, no orders).

Summarizes the CSV/metadata files under data/gold_bot/history/: rows, first/last
timestamps, last close, missing files, metadata, and a small data-quality scan.

Run from repo root:
    python scripts/run_gold_bot_history_probe.py --timeframe M1 --tail 5
    python scripts/run_gold_bot_history_probe.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from services.gold_bot_historical_market_data import (  # noqa: E402
    DEFAULT_HISTORY_DIR,
    SUPPORTED_TIMEFRAMES,
    csv_path,
    history_status,
    meta_path,
    quality_summary,
    read_bars_csv,
    read_metadata,
)


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="run_gold_bot_history_probe",
        description="Summarize local XAUUSD history files + quality (read-only).",
    )
    p.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR), dest="history_dir")
    p.add_argument("--symbol", default="XAUUSD")
    p.add_argument("--timeframe", default=None,
                   help="Inspect one timeframe in detail (e.g. M1). Omit for all.")
    p.add_argument("--tail", type=int, default=5, help="Show the last N bars (default 5).")
    p.add_argument("--json", action="store_true", dest="json_output")
    return p.parse_args(argv)


def _summarize_tf(history_dir, symbol, tf, tail):
    cp = csv_path(history_dir, symbol, tf)
    if not cp.exists():
        return {"timeframe": tf, "present": False}
    bars = read_bars_csv(cp, symbol=symbol, timeframe=tf)
    meta = read_metadata(meta_path(history_dir, symbol, tf))
    q = quality_summary(bars, timeframe=tf)
    entry = {
        "timeframe": tf, "present": True, "csv": str(cp), "rows": len(bars),
        "first_time": bars[0].time.isoformat() if bars else None,
        "last_time": bars[-1].time.isoformat() if bars else None,
        "last_close": bars[-1].close if bars else None,
        "quality": q, "meta": meta,
        "tail": [b.csv_row() for b in bars[-tail:]] if tail and bars else [],
    }
    return entry


def main(argv=None) -> int:
    args = parse_args(argv)
    timeframes = [args.timeframe.upper()] if args.timeframe else list(SUPPORTED_TIMEFRAMES)
    status = history_status(args.history_dir, args.symbol)
    entries = [_summarize_tf(args.history_dir, args.symbol, tf, args.tail) for tf in timeframes]

    if args.json_output:
        print(json.dumps({"provider_status": status.to_dict(), "history_dir": args.history_dir,
                          "entries": entries}, indent=2, default=str))
        return 0

    print("=" * 70)
    print(" GOLD BOT HISTORY PROBE   (read-only)")
    print("=" * 70)
    print(f" history dir : {args.history_dir}")
    print(f" provider    : {status.name} [{status.status}] freshness {status.freshness}")
    print(f"               {status.message}")
    for e in entries:
        if not e["present"]:
            print(f"\n {e['timeframe']}: MISSING (no CSV) - run run_gold_bot_history_backfill.py")
            continue
        print(f"\n {e['timeframe']}: rows={e['rows']}  "
              f"{e['first_time']} -> {e['last_time']}  last_close={e['last_close']}")
        q = e["quality"]
        print(f"   quality : dup={q['duplicate_timestamps']} bad_ohlc={q['missing_or_zero_ohlc']} "
              f"high<low={q['high_lt_low']} non_monotonic={q['non_monotonic_time']} "
              f"gaps={q['time_gaps']}", end="")
        if "spread_avg" in q:
            print(f"  spread[min/avg/max]={q['spread_min']}/{q['spread_avg']}/{q['spread_max']}")
        else:
            print("")
        for w in q["warnings"]:
            print(f"   warning - {w}")
        if e["meta"] and e["meta"].get("warnings"):
            for w in e["meta"]["warnings"]:
                print(f"   meta warning - {w}")
        for row in e["tail"]:
            print(f"     {row['time']}  O{row['open']} H{row['high']} L{row['low']} C{row['close']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
