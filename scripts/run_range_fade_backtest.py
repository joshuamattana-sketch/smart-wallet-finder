"""
scripts/run_range_fade_backtest.py
----------------------------------
Standalone backtester for the "4-hour opening-range fakeout FADE" scalp, the
strategy from the Data Trader YouTube video. RESEARCH-ONLY: no MT5, no orders,
no lookahead. Separate from the Decision-Engine replay because it is a different
strategy with its own clean, auditable rules.

STRATEGY (strict, mechanical, per New-York day):
  1. Opening range = high/low of the first 4 hours of the NY day (00:00-04:00 NY).
  2. On lower-timeframe bars AFTER the range, watch for a FAILED breakout:
       a bar CLOSES outside the range (close > range_high or close < range_low).
       Wicks alone never count. Track the breakout EXTREME (highest high on an
       up-break / lowest low on a down-break).
  3. When a later bar CLOSES back inside the range, FADE it:
       up-break then re-enter  -> SHORT
       down-break then re-enter -> LONG
  4. Stop = the breakout extreme. Risk R = |entry - stop|. Entry = re-entry close.
  5. Take-profit = entry +/- tp_r * R (default 2R).
  6. Resolve first-touch on strictly-later bars, same NY day; if neither hit by
     day end, exit at the last bar's close (marked to market in R).
  7. Multiple trades per day allowed; the next search resumes after the prior
     trade resolves (no overlapping positions).

NO-LOOKAHEAD: the range is fixed from 00:00-04:00 NY before any entry; the entry
uses only the re-entry bar's close; exits scan strictly forward.

  python scripts/run_range_fade_backtest.py \
      --history data/gold_bot/history_histdata/XAUUSD_M5.csv --tp-r 2 --year-breakdown
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")


@dataclass
class Bar:
    t_utc: datetime
    t_ny: datetime
    o: float
    h: float
    l: float
    c: float
    spread: float


def read_bars(path: str) -> list[Bar]:
    out: list[Bar] = []
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            try:
                t = datetime.fromisoformat(row["time"])
            except (ValueError, KeyError):
                continue
            if t.tzinfo is None:
                t = t.replace(tzinfo=UTC)
            out.append(Bar(
                t_utc=t, t_ny=t.astimezone(NY),
                o=float(row["open"]), h=float(row["high"]),
                l=float(row["low"]), c=float(row["close"]),
                spread=float(row.get("spread") or 0.0),
            ))
    out.sort(key=lambda b: b.t_utc)
    return out


def group_by_ny_day(bars: list[Bar]) -> dict[str, list[Bar]]:
    days: dict[str, list[Bar]] = {}
    for b in bars:
        key = b.t_ny.date().isoformat()
        days.setdefault(key, []).append(b)
    return days


@dataclass
class Trade:
    day: str
    direction: str          # "LONG" | "SHORT"
    entry: float
    stop: float
    tp: float
    risk: float             # price distance to stop
    outcome: str            # "tp" | "sl" | "expired"
    r_gross: float          # R multiple before cost
    r_net: float            # R after round-trip spread cost
    year: int


_RANGE_END = dtime(4, 0)   # 00:00-04:00 NY opening range


def _resolve(direction: str, entry: float, stop: float, tp: float,
             risk: float, fwd: list[Bar], spread_pts: float) -> tuple[str, float]:
    """First-touch resolution on strictly-later bars. SL assumed first if both
    hit in one bar (conservative). Returns (outcome, r_gross)."""
    for b in fwd:
        if direction == "LONG":
            if b.l <= stop:
                return "sl", -1.0
            if b.h >= tp:
                return "tp", 2.0 if tp != entry else 0.0
        else:  # SHORT
            if b.h >= stop:
                return "sl", -1.0
            if b.l <= tp:
                return "tp", 2.0
    # time exit at last available bar close (mark to market)
    if fwd:
        last = fwd[-1].c
        pnl = (last - entry) if direction == "LONG" else (entry - last)
        return "expired", pnl / risk if risk else 0.0
    return "expired", 0.0


def backtest(bars: list[Bar], tp_r: float, spread_pts: float,
             min_risk_pts: float, max_risk_pts: float = 1e9) -> list[Trade]:
    trades: list[Trade] = []
    for day, day_bars in group_by_ny_day(bars).items():
        opening = [b for b in day_bars if b.t_ny.time() < _RANGE_END]
        if len(opening) < 6:           # need a real opening range
            continue
        rng_hi = max(b.h for b in opening)
        rng_lo = min(b.l for b in opening)
        if rng_hi <= rng_lo:
            continue
        trade_bars = [b for b in day_bars if b.t_ny.time() >= _RANGE_END]
        year = day_bars[0].t_ny.year

        i = 0
        n = len(trade_bars)
        mode = "seek"
        ext = 0.0
        while i < n:
            b = trade_bars[i]
            if mode == "seek":
                if b.c > rng_hi:
                    mode, ext = "up", b.h
                elif b.c < rng_lo:
                    mode, ext = "down", b.l
                i += 1
                continue
            if mode == "up":
                ext = max(ext, b.h)
                if b.c <= rng_hi:                       # re-entered -> SHORT
                    entry, stop = b.c, ext
                    risk = stop - entry
                    if not (min_risk_pts <= risk * 100 <= max_risk_pts):
                        mode = "seek"; i += 1; continue
                    tp = entry - tp_r * risk
                    fwd = trade_bars[i + 1:]
                    outcome, rg = _resolve("SHORT", entry, stop, tp, risk, fwd, spread_pts)
                    rn = rg - (spread_pts / (risk * 100)) if risk else rg
                    trades.append(Trade(day, "SHORT", entry, stop, tp, risk, outcome, rg, rn, year))
                    mode = "seek"
                i += 1
                continue
            if mode == "down":
                ext = min(ext, b.l)
                if b.c >= rng_lo:                       # re-entered -> LONG
                    entry, stop = b.c, ext
                    risk = entry - stop
                    if not (min_risk_pts <= risk * 100 <= max_risk_pts):
                        mode = "seek"; i += 1; continue
                    tp = entry + tp_r * risk
                    fwd = trade_bars[i + 1:]
                    outcome, rg = _resolve("LONG", entry, stop, tp, risk, fwd, spread_pts)
                    rn = rg - (spread_pts / (risk * 100)) if risk else rg
                    trades.append(Trade(day, "LONG", entry, stop, tp, risk, outcome, rg, rn, year))
                    mode = "seek"
                i += 1
                continue
    return trades


def summarize(trades: list[Trade], label: str) -> None:
    n = len(trades)
    if n == 0:
        print(f"  {label:<14} no trades")
        return
    wins = sum(1 for t in trades if t.r_gross > 0)
    losses = sum(1 for t in trades if t.r_gross < 0)
    expired = sum(1 for t in trades if t.outcome == "expired")
    tot_g = sum(t.r_gross for t in trades)
    tot_n = sum(t.r_net for t in trades)
    avg_stop = sum(t.risk * 100 for t in trades) / n
    wr = 100.0 * wins / n
    print(f"  {label:<14} trades {n:>5}  win% {wr:5.1f}  "
          f"R_gross {tot_g:+8.1f} (exp {tot_g/n:+.3f})  "
          f"R_net {tot_n:+8.1f} (exp {tot_n/n:+.3f})  "
          f"avg stop {avg_stop:.0f}pt  expired {expired}")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="4H opening-range fakeout FADE backtest (research-only).")
    p.add_argument("--history", default="data/gold_bot/history_histdata/XAUUSD_M5.csv")
    p.add_argument("--tp-r", type=float, default=2.0, dest="tp_r")
    p.add_argument("--spread-points", type=float, default=4.0, dest="spread_pts")
    p.add_argument("--min-risk-points", type=float, default=20.0, dest="min_risk_pts",
                   help="Skip fades whose stop is tighter than this (point=0.01).")
    p.add_argument("--max-risk-points", type=float, default=1e9, dest="max_risk_pts",
                   help="Skip fades whose stop is wider than this (filter big real moves).")
    p.add_argument("--side", choices=["both", "long", "short"], default="both")
    p.add_argument("--year-breakdown", action="store_true", dest="year_breakdown")
    args = p.parse_args(argv)

    bars = read_bars(args.history)
    if not bars:
        print(f"no bars at {args.history}")
        return 1
    print("=" * 92)
    print(" 4H OPENING-RANGE FAKEOUT FADE  (research-only, no-lookahead, NY 00:00-04:00 range)")
    print("=" * 92)
    print(f" data        : {args.history}")
    print(f" bars        : {len(bars):,}  ({bars[0].t_ny.date()} .. {bars[-1].t_ny.date()} NY)")
    print(f" rules       : close outside range -> close back inside -> FADE, "
          f"stop=breakout extreme, TP={args.tp_r}R")
    print(f" cost        : {args.spread_pts}pt round-trip spread; skip stops < {args.min_risk_pts}pt")
    print("-" * 92)

    trades = backtest(bars, args.tp_r, args.spread_pts, args.min_risk_pts, args.max_risk_pts)
    if args.side != "both":
        trades = [t for t in trades if t.direction == args.side.upper()]
    summarize(trades, "ALL")
    longs = [t for t in trades if t.direction == "LONG"]
    shorts = [t for t in trades if t.direction == "SHORT"]
    summarize(longs, "  longs")
    summarize(shorts, "  shorts")

    if args.year_breakdown:
        print("-" * 92)
        for yr in sorted({t.year for t in trades}):
            summarize([t for t in trades if t.year == yr], f"year {yr}")

    print("-" * 92)
    print(" R_net subtracts the spread per trade. TP=2R/SL=1R -> breakeven win rate ~33.3%.")
    print(" Reminder: video claimed ~60% on 10 hand-picked gold trades. This is the full sample.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
