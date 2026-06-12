"""
scripts/run_gold_bot_macro_history_probe.py
--------------------------------------------
LM84B — Inspect locally-imported macro history (READ-ONLY, no HTTP, no MT5).

Summarizes DXY / US10Y / US02Y / VIX CSV + metadata under
data/gold_bot/macro_history/: rows, first/last timestamp, last close/value,
quality scan, and which instruments are still missing.

Run from repo root:
    python scripts/run_gold_bot_macro_history_probe.py --symbol DXY --timeframe D1 --tail 5
    python scripts/run_gold_bot_macro_history_probe.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from services.gold_bot_macro_history import (  # noqa: E402
    DEFAULT_MACRO_HISTORY_DIR,
    MACRO_INSTRUMENTS,
    macro_csv_path,
    macro_market_statuses,
    macro_meta_path,
    quality_summary,
    read_macro_csv,
    read_metadata,
)


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="run_gold_bot_macro_history_probe",
        description="Summarize local macro history files + quality (read-only).",
    )
    p.add_argument("--history-dir", default=str(DEFAULT_MACRO_HISTORY_DIR), dest="history_dir")
    p.add_argument("--symbol", default=None,
                   help=f"One instrument ({', '.join(MACRO_INSTRUMENTS)}). Omit for all.")
    p.add_argument("--timeframe", default="D1")
    p.add_argument("--tail", type=int, default=5)
    p.add_argument("--json", action="store_true", dest="json_output")
    return p.parse_args(argv)


def _summarize(history_dir, symbol, tf, tail):
    cp = macro_csv_path(history_dir, symbol, tf)
    if not cp.exists():
        return {"symbol": symbol, "timeframe": tf, "present": False}
    bars = read_macro_csv(cp, symbol=symbol, timeframe=tf)
    q = quality_summary(bars)
    return {
        "symbol": symbol, "timeframe": tf, "present": True, "csv": str(cp), "rows": len(bars),
        "first_time": bars[0].time.isoformat() if bars else None,
        "last_time": bars[-1].time.isoformat() if bars else None,
        "last_close": bars[-1].close if bars else None,
        "quality": q, "meta": read_metadata(macro_meta_path(history_dir, symbol, tf)),
        "tail": [b.csv_row() for b in bars[-tail:]] if tail and bars else [],
    }


def main(argv=None) -> int:
    args = parse_args(argv)
    symbols = [args.symbol.upper()] if args.symbol else list(MACRO_INSTRUMENTS)
    entries = [_summarize(args.history_dir, s, args.timeframe.upper(), args.tail) for s in symbols]
    statuses = macro_market_statuses(args.history_dir)

    if args.json_output:
        print(json.dumps({"history_dir": args.history_dir,
                          "statuses": [s.to_dict() for s in statuses],
                          "entries": entries}, indent=2, default=str))
        return 0

    print("=" * 70)
    print(" GOLD BOT MACRO HISTORY PROBE   (read-only)")
    print("=" * 70)
    print(f" history dir : {args.history_dir}")
    for s in statuses:
        print(f"   {s.name:<18} [{s.status}] {s.freshness:<7} {s.message}")
    for e in entries:
        if not e["present"]:
            print(f"\n {e['symbol']} {e['timeframe']}: MISSING - import with "
                  "run_gold_bot_macro_history_import.py")
            continue
        print(f"\n {e['symbol']} {e['timeframe']}: rows={e['rows']}  "
              f"{e['first_time']} -> {e['last_time']}  last_close={e['last_close']}")
        q = e["quality"]
        print(f"   quality : dup={q['duplicate_timestamps']} missing_close={q['missing_close']} "
              f"high<low={q['high_lt_low']} non_monotonic={q['non_monotonic_time']} "
              f"gaps={q['time_gaps']}")
        for w in q["warnings"]:
            print(f"   warning - {w}")
        for row in e["tail"]:
            print(f"     {row['time']}  close={row['close']}"
                  f"{'  value=' + str(row['value']) if row['value'] != '' else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
