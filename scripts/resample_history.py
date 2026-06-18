"""
scripts/resample_history.py
----------------------------
LM118A - Resample M1 history into higher timeframes (M5/M15/M30/H1), RESEARCH-ONLY.

Lets us test the engine NATIVELY on a higher timeframe over the full HistData span
without downloading more data. OHLC aggregation: open=first, high=max, low=min,
close=last, volume=sum, spread=avg. Buckets are aligned to the timeframe boundary.
Writes into the same history dir so run_replay --timeframe M5 just works. No MT5,
no orders, no network.

    python scripts/resample_history.py --in-dir data/gold_bot/history_histdata --timeframes M5,M15
"""

from __future__ import annotations

import argparse
import sys
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from services.gold_bot_historical_market_data import (  # noqa: E402
    HistoricalBar, csv_path, read_bars_csv, write_bars_csv,
)

TF_MINUTES = {"M5": 5, "M15": 15, "M30": 30, "H1": 60}


def resample(bars: list[HistoricalBar], *, symbol: str, timeframe: str) -> list[HistoricalBar]:
    tf_min = TF_MINUTES[timeframe]
    buckets: "OrderedDict[int, list[HistoricalBar]]" = OrderedDict()
    for b in bars:
        bstart = (int(b.time.timestamp()) // 60 // tf_min) * tf_min   # bucket start (minutes)
        buckets.setdefault(bstart, []).append(b)
    out: list[HistoricalBar] = []
    for start_min, group in buckets.items():
        spreads = [g.spread for g in group if g.spread is not None]
        out.append(HistoricalBar(
            symbol=symbol, timeframe=timeframe,
            time=datetime.fromtimestamp(start_min * 60, tz=timezone.utc),
            open=group[0].open, high=max(g.high for g in group),
            low=min(g.low for g in group), close=group[-1].close,
            tick_volume=sum((g.tick_volume or 0.0) for g in group),
            spread=round(sum(spreads) / len(spreads), 1) if spreads else None,
            real_volume=0.0, source="resampled_m1"))
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="resample_history",
                                description="Resample M1 history into higher timeframes.")
    p.add_argument("--in-dir", default=str(_REPO_ROOT / "data" / "gold_bot" / "history_histdata"),
                   dest="in_dir")
    p.add_argument("--out-dir", default=None, dest="out_dir", help="Default: same as --in-dir.")
    p.add_argument("--symbol", default="XAUUSD")
    p.add_argument("--timeframes", default="M5,M15")
    args = p.parse_args(argv)
    out_dir = args.out_dir or args.in_dir

    m1 = read_bars_csv(csv_path(args.in_dir, args.symbol, "M1"), symbol=args.symbol, timeframe="M1")
    if not m1:
        print(f"No M1 history at {csv_path(args.in_dir, args.symbol, 'M1')}", file=sys.stderr)
        return 1
    print(f"  M1 source: {len(m1)} bars")
    for tf in [t.strip().upper() for t in args.timeframes.split(",") if t.strip()]:
        if tf not in TF_MINUTES:
            print(f"  skip {tf} (unsupported)")
            continue
        bars = resample(m1, symbol=args.symbol, timeframe=tf)
        out = csv_path(out_dir, args.symbol, tf)
        write_bars_csv(out, bars)
        print(f"  {tf}: {len(bars)} bars -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
