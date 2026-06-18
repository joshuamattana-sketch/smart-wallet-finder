"""
scripts/import_histdata.py
---------------------------
LM113A - Import HistData.com ASCII M1 files into the bot's history CSV format
(RESEARCH-ONLY, offline). Lets us replay/equity-test over MONTHS of real data
instead of the broker's ~4.6-day cap.

HistData M1 line:  YYYYMMDD HHMMSS;Open;High;Low;Close;Volume   (time = EST, no DST)
Bot CSV:           time(ISO UTC),open,high,low,close,tick_volume,spread,real_volume

EST has no DST per HistData, so UTC = EST + 5h. Volume is 0 in HistData; spread is
not provided, so a realistic fixed spread is written for cost-aware backtests.
Merges all files, sorts, de-dups by timestamp. Writes to a SEPARATE history dir so
the broker's own CSV is left untouched. No MT5, no orders, no network.

    python scripts/import_histdata.py --raw-dir data/gold_bot/raw_histdata --spread 4
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from services.gold_bot_historical_market_data import HistoricalBar, csv_path, write_bars_csv  # noqa: E402

EST = timezone(timedelta(hours=-5))   # HistData time zone (no DST)


def parse_args(argv=None):
    p = argparse.ArgumentParser(prog="import_histdata",
                                description="Import HistData ASCII M1 into the bot history format.")
    p.add_argument("--raw-dir", default=str(_REPO_ROOT / "data" / "gold_bot" / "raw_histdata"),
                   dest="raw_dir")
    p.add_argument("--symbol", default="XAUUSD")
    p.add_argument("--timeframe", default="M1")
    p.add_argument("--spread", type=float, default=4.0,
                   help="Fixed spread (points) written per bar (HistData has none). Default 4.")
    p.add_argument("--out-dir", default=str(_REPO_ROOT / "data" / "gold_bot" / "history_histdata"),
                   dest="out_dir", help="Separate dir so the broker CSV is untouched.")
    return p.parse_args(argv)


def parse_histdata_line(line: str, *, symbol: str, timeframe: str, spread: float) -> HistoricalBar | None:
    line = line.strip()
    if not line:
        return None
    parts = line.split(";")
    if len(parts) < 5:
        return None
    try:
        dt_naive = datetime.strptime(parts[0], "%Y%m%d %H%M%S")
        t_utc = dt_naive.replace(tzinfo=EST).astimezone(timezone.utc)
        o, h, l, c = float(parts[1]), float(parts[2]), float(parts[3]), float(parts[4])
    except (ValueError, IndexError):
        return None
    return HistoricalBar(symbol=symbol, timeframe=timeframe.upper(), time=t_utc,
                         open=o, high=h, low=l, close=c, tick_volume=0.0,
                         spread=spread, real_volume=0.0, source="histdata")


def main(argv=None) -> int:
    args = parse_args(argv)
    raw = Path(args.raw_dir)
    files = sorted(raw.glob(f"DAT_ASCII_{args.symbol}_{args.timeframe.upper()}_*.csv"))
    if not files:
        print(f"No HistData CSVs in {raw} (expected DAT_ASCII_{args.symbol}_{args.timeframe.upper()}_*.csv).",
              file=sys.stderr)
        return 1

    by_time: dict[datetime, HistoricalBar] = {}
    bad = 0
    for f in files:
        n = 0
        for line in f.read_text(encoding="utf-8", errors="ignore").splitlines():
            bar = parse_histdata_line(line, symbol=args.symbol, timeframe=args.timeframe,
                                      spread=args.spread)
            if bar is None:
                bad += 1
                continue
            by_time[bar.time] = bar   # de-dup by timestamp (last wins)
            n += 1
        print(f"  {f.name}: {n} bars")

    bars = [by_time[t] for t in sorted(by_time)]
    if not bars:
        print("No valid bars parsed.", file=sys.stderr)
        return 1
    out = csv_path(args.out_dir, args.symbol, args.timeframe)
    out.parent.mkdir(parents=True, exist_ok=True)
    write_bars_csv(out, bars)
    span_days = (bars[-1].time - bars[0].time).total_seconds() / 86400.0
    print(f"\n wrote {len(bars)} bars  ({bad} bad lines skipped)")
    print(f" range: {bars[0].time.isoformat()} -> {bars[-1].time.isoformat()}  (~{span_days:.0f} days)")
    print(f" file : {out}")
    print(f" use  : python scripts/run_gold_bot_replay.py --history-dir {args.out_dir} ...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
