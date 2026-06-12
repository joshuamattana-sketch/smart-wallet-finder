"""
scripts/run_gold_bot_macro_history_import.py
---------------------------------------------
LM84B — Import a free macro CSV (DXY / US10Y / US02Y / VIX) into normalized
local history under data/gold_bot/macro_history/. OFFLINE only: reads a local
CSV file, writes a normalized CSV + metadata JSON. NO HTTP, no orders, no MT5.

Run from repo root:
    python scripts/run_gold_bot_macro_history_import.py --input data/gold_bot/macro_history/samples/DXY_D1.sample.csv --symbol DXY --timeframe D1 --dry-run
    python scripts/run_gold_bot_macro_history_import.py --input <downloaded.csv> --symbol DXY --timeframe D1 --overwrite
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from services.gold_bot_macro_history import (  # noqa: E402
    DEFAULT_MACRO_HISTORY_DIR,
    MACRO_INSTRUMENTS,
    SUPPORTED_TIMEFRAMES,
    import_csv,
)


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="run_gold_bot_macro_history_import",
        description="Import a free macro CSV into normalized local history (offline, no HTTP).",
    )
    p.add_argument("--input", required=True, help="Path to a downloaded macro CSV (OHLC or value).")
    p.add_argument("--symbol", required=True,
                   help=f"Instrument (suggested: {', '.join(MACRO_INSTRUMENTS)}).")
    p.add_argument("--timeframe", default="D1",
                   help=f"Timeframe (default D1; supported {', '.join(SUPPORTED_TIMEFRAMES)}).")
    p.add_argument("--source", default="manual_csv")
    p.add_argument("--out-dir", default=str(DEFAULT_MACRO_HISTORY_DIR), dest="out_dir")
    p.add_argument("--overwrite", action="store_true")
    p.add_argument("--dry-run", action="store_true", dest="dry_run")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    print("=" * 64)
    print(" GOLD BOT MACRO HISTORY IMPORT   (offline CSV, no HTTP)")
    print("=" * 64)
    print(f" input       : {args.input}")
    print(f" symbol/TF   : {args.symbol.upper()} / {args.timeframe.upper()}")
    print(f" source      : {args.source}")
    print(f" out-dir     : {args.out_dir}")
    print(f" mode        : {'DRY-RUN (validate only, no writes)' if args.dry_run else 'WRITE'}"
          f"{'  overwrite' if args.overwrite else ''}")
    print("")

    result = import_csv(
        input_file=args.input, symbol=args.symbol, timeframe=args.timeframe,
        out_dir=args.out_dir, source=args.source, overwrite=args.overwrite, dry_run=args.dry_run,
    )

    print(f" [{result['status']}]  rows={result.get('rows', '-')}  -> {result.get('csv')}")
    if result.get("meta"):
        print(f"   meta: {result['meta']}")
    for w in result.get("warnings", []):
        print(f"   warning - {w}")

    ok = result["status"] in ("written", "planned", "skipped_exists")
    if result["status"] == "written":
        print(f"\n Imported {result['rows']} rows.")
    elif result["status"] == "planned":
        print("\n Dry-run only - nothing written.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
