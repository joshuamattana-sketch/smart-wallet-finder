"""
scripts/run_orb_backtest.py
----------------------------
Standalone Opening Range Breakout (ORB) backtester for XAUUSD, RESEARCH-ONLY,
no MT5, no orders, no lookahead. Separate from the Decision-Engine replay — ORB
is a different strategy, so it gets its own clean, auditable backtest.

Strategy (per session open, per day):
  1. Opening range = high/low of the first `range_min` minutes after the open.
  2. First M1 bar whose HIGH breaks range-high  -> enter LONG at range-high.
     First M1 bar whose LOW  breaks range-low   -> enter SHORT at range-low.
     (Only the FIRST break is taken — one trade per session.)
  3. Stop = opposite side of the range. Risk R = |entry - stop|.
  4. Exit on (first-touch, SL assumed first if both hit in one bar):
        - stop hit, or
        - take-profit at `tp_r` * R (when set), or
        - time exit at `max_hold_min` (exit at that bar's close).
  5. Net P&L in price points minus round-trip spread cost.

No lookahead: the range is fixed before any entry; exits scan strictly forward.

    python scripts/run_orb_backtest.py --history data/gold_bot/history_dukascopy/XAUUSD_M1.csv \
        --session-opens 07:00,13:00 --range-min 15 --max-hold-min 360 --tp-r 2 --year-breakdown
"""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from datetime import datetime, timedelta, timezone

# Gold price point: 1 point = 0.01 in price (matches the bot's POINT convention).
# Returns are reported in POINTS; spread is given in points and converted here.
POINT = 0.01


def load_bars(path: str):
    """Return list of (dt_utc, open, high, low, close, spread_points)."""
    out = []
    with open(path, "r", newline="") as f:
        for r in csv.DictReader(f):
            try:
                dt = datetime.fromisoformat(r["time"])
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                out.append((dt, float(r["open"]), float(r["high"]),
                            float(r["low"]), float(r["close"]), float(r.get("spread", 0) or 0)))
            except (ValueError, KeyError):
                continue
    out.sort(key=lambda b: b[0])
    return out


def parse_hhmm(s: str) -> tuple[int, int]:
    h, m = s.split(":")
    return int(h), int(m)


def run_session(day_bars, open_h, open_m, range_min, max_hold_min, tp_r, spread_pts):
    """Run ORB for one session open within a day's bars. Returns a trade dict or None."""
    # Locate the opening-range window.
    base = day_bars[0][0]
    open_dt = base.replace(hour=open_h, minute=open_m, second=0, microsecond=0)
    range_end = open_dt + timedelta(minutes=range_min)
    hold_end = open_dt + timedelta(minutes=max_hold_min)

    rng = [b for b in day_bars if open_dt <= b[0] < range_end]
    if len(rng) < 2:
        return None
    hi = max(b[2] for b in rng)
    lo = min(b[3] for b in rng)

    after = [b for b in day_bars if range_end <= b[0] <= hold_end]
    if not after:
        return None

    # First break of the range (forward only).
    entry = direction = stop = None
    entry_idx = -1
    for i, b in enumerate(after):
        _, o, h, l, c, sp = b
        if h > hi:
            entry, direction, stop, entry_idx = hi, "LONG", lo, i
            break
        if l < lo:
            entry, direction, stop, entry_idx = lo, "SHORT", hi, i
            break
    if entry is None:
        return None

    risk = abs(entry - stop)
    if risk <= 0:
        return None
    tp = None
    if tp_r is not None:
        tp = entry + tp_r * risk if direction == "LONG" else entry - tp_r * risk

    # Forward exit scan (strictly after entry bar's break).
    exit_price = after[-1][4]
    exit_reason = "time"
    for b in after[entry_idx:]:
        _, o, h, l, c, sp = b
        if direction == "LONG":
            hit_sl, hit_tp = l <= stop, (tp is not None and h >= tp)
        else:
            hit_sl, hit_tp = h >= stop, (tp is not None and l <= tp)
        if hit_sl:  # conservative: adverse level assumed first
            exit_price, exit_reason = stop, "sl"
            break
        if hit_tp:
            exit_price, exit_reason = tp, "tp"
            break

    sign = 1.0 if direction == "LONG" else -1.0
    gross = (exit_price - entry) * sign            # price terms
    cost = 2.0 * spread_pts * POINT                # round-trip spread (entry+exit), price terms
    net = gross - cost                             # price terms
    return {"date": open_dt.date().isoformat(), "year": open_dt.year, "dir": direction,
            "entry": entry, "exit": exit_price, "reason": exit_reason,
            "risk": risk, "r_multiple": net / risk if risk else 0.0, "net_pts": net / POINT}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="run_orb_backtest")
    ap.add_argument("--history", default="data/gold_bot/history_dukascopy/XAUUSD_M1.csv")
    ap.add_argument("--session-opens", default="13:00", help="Comma UTC HH:MM list, e.g. 07:00,13:00")
    ap.add_argument("--range-min", type=int, default=15)
    ap.add_argument("--max-hold-min", type=int, default=360)
    ap.add_argument("--tp-r", type=float, default=None, help="Take-profit in R (omit = time exit only).")
    ap.add_argument("--spread-points", type=float, default=4.0, help="One-way spread in price points.")
    ap.add_argument("--year-breakdown", action="store_true")
    args = ap.parse_args(argv)

    bars = load_bars(args.history)
    if not bars:
        print("no bars loaded")
        return 1
    by_day = defaultdict(list)
    for b in bars:
        by_day[b[0].date()].append(b)
    opens = [parse_hhmm(s) for s in args.session_opens.split(",") if s.strip()]

    trades = []
    for day, db in by_day.items():
        for (oh, om) in opens:
            t = run_session(db, oh, om, args.range_min, args.max_hold_min, args.tp_r, args.spread_points)
            if t:
                trades.append(t)

    def stats(ts):
        n = len(ts)
        if n == 0:
            return "no trades"
        wins = [t for t in ts if t["net_pts"] > 0]
        net = sum(t["net_pts"] for t in ts)
        avg_r = sum(t["r_multiple"] for t in ts) / n
        return (f"trades {n}  win% {100*len(wins)/n:.1f}  net {net:+.0f}pt  "
                f"avg {net/n:+.1f}pt/trade  avg {avg_r:+.2f}R  total {sum(t['r_multiple'] for t in ts):+.1f}R")

    print(f"ORB  opens={args.session_opens}  range={args.range_min}m  hold={args.max_hold_min}m  "
          f"tp={args.tp_r}R  spread={args.spread_points}pt")
    print(f"history: {bars[0][0].date()} -> {bars[-1][0].date()}  ({len(by_day)} days)")
    print(f"ALL: {stats(trades)}")
    if args.year_breakdown:
        for y in sorted({t['year'] for t in trades}):
            print(f"  {y}: {stats([t for t in trades if t['year'] == y])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
