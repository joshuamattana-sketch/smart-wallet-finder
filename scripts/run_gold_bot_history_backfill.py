"""
scripts/run_gold_bot_history_backfill.py
------------------------------------------
LM84A — Backfill XAUUSD historical bars from a running MT5 demo terminal into
local CSV + metadata under data/gold_bot/history/. READ-ONLY: copies history,
sends NO orders, never touches live trading.

Run from repo root (Windows, MT5 running on a demo account):
    python scripts/run_gold_bot_history_backfill.py --dry-run
    python scripts/run_gold_bot_history_backfill.py --days 7 --timeframes M1,M5 --overwrite

Requires the MetaTrader5 package (Windows only) for a real run:  pip install MetaTrader5
Dry-run needs no MT5.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from services.gold_bot_historical_market_data import (  # noqa: E402
    DEFAULT_HISTORY_DIR,
    SUPPORTED_TIMEFRAMES,
    MT5HistoricalXauusdProvider,
)


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="run_gold_bot_history_backfill",
        description="Backfill XAUUSD history from MT5 demo into local CSV (read-only).",
    )
    p.add_argument("--symbol", default="XAUUSD")
    p.add_argument("--timeframes", default="M1,M5,M15,H1",
                   help=f"Comma list from {', '.join(SUPPORTED_TIMEFRAMES)} (default all).")
    p.add_argument("--days", type=int, default=30, help="Lookback days (default 30).")
    p.add_argument("--from-date", default=None, dest="from_date", help="YYYY-MM-DD (overrides --days).")
    p.add_argument("--to-date", default=None, dest="to_date", help="YYYY-MM-DD (default now).")
    p.add_argument("--out-dir", default=str(DEFAULT_HISTORY_DIR), dest="out_dir")
    p.add_argument("--overwrite", action="store_true")
    p.add_argument("--dry-run", action="store_true", dest="dry_run")
    return p.parse_args(argv)


def _parse_date(s: str, *, end: bool) -> datetime:
    d = datetime.fromisoformat(s)
    d = d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc)
    return d


def main(argv=None) -> int:
    args = parse_args(argv)
    now = datetime.now(timezone.utc)
    date_to = _parse_date(args.to_date, end=True) if args.to_date else now
    if args.from_date:
        date_from = _parse_date(args.from_date, end=False)
    else:
        date_from = date_to - timedelta(days=args.days)
    timeframes = [tf.strip().upper() for tf in args.timeframes.split(",") if tf.strip()]

    print("=" * 64)
    print(" GOLD BOT HISTORY BACKFILL   (MT5 DEMO, read-only)")
    print("=" * 64)
    print(f" symbol      : {args.symbol}")
    print(f" timeframes  : {', '.join(timeframes)}")
    print(f" range (UTC) : {date_from.isoformat()}  ->  {date_to.isoformat()}")
    print(f" out-dir     : {args.out_dir}")
    print(f" mode        : {'DRY-RUN (no writes, no MT5)' if args.dry_run else 'WRITE'}"
          f"{'  overwrite' if args.overwrite else ''}")
    print("")

    provider = MT5HistoricalXauusdProvider(history_dir=args.out_dir, symbol=args.symbol)
    try:
        results = provider.backfill(
            timeframes=timeframes, date_from=date_from, date_to=date_to,
            overwrite=args.overwrite, dry_run=args.dry_run, printer=print,
        )
    except Exception as exc:  # noqa: BLE001 - surface MT5/connection errors clearly, never crash hard
        print(f"BACKFILL FAILED (fail-closed): {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    for r in results:
        line = f" [{r['status']:^17}] {r['timeframe']}"
        if r.get("rows") is not None:
            line += f"  rows={r['rows']}"
        if r.get("csv"):
            line += f"  -> {r['csv']}"
        print(line)
        for w in r.get("warnings", []):
            print(f"     warning - {w}")

    written = sum(1 for r in results if r["status"] == "written")
    print(f"\n Done. {written} file(s) written"
          f"{' (dry-run: none)' if args.dry_run else ''}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
