"""
scripts/run_gold_bot_signal_logger.py
--------------------------------------
LM87A - Forward signal logger + track-record scorer (offline, no MT5).

Builds an honest LIVE-tail track record for the Gold Bot: logs one signal per
CLOSED bar using the same no-lookahead engine as the backtest, then scores
still-open signals against bars that arrived AFTER them. Idempotent - safe to
run on a schedule.

Typical loop (run M15 every 15 min after refreshing data):
    python scripts/run_gold_bot_history_backfill.py --timeframes M15
    python scripts/run_gold_bot_signal_logger.py --timeframe M15 --trend-filter

Inspect the growing record:
    python scripts/run_gold_bot_signal_logger.py --timeframe M15 --json

READ-ONLY / OFFLINE: never calls MT5, never sends orders. A preset is an exit
policy only; it cannot move the stop or size a position.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from services.gold_bot_lot_calculator import RISK_MODES  # noqa: E402
from services.gold_bot_signal_logger import (  # noqa: E402
    DEFAULT_HISTORY_DIR,
    DEFAULT_MACRO_HISTORY_DIR,
    DEFAULT_MAX_FORWARD_BARS,
    DEFAULT_SIGNALS_DIR,
    SignalLoggerError,
    run_signal_logger,
)


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="run_gold_bot_signal_logger",
        description="Forward signal logger + track-record scorer (offline, no MT5).",
    )
    p.add_argument("--symbol", default="XAUUSD")
    p.add_argument("--timeframe", default="M15")
    p.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR), dest="history_dir")
    p.add_argument("--macro-history-dir", default=str(DEFAULT_MACRO_HISTORY_DIR),
                   dest="macro_history_dir")
    p.add_argument("--signals-dir", default=str(DEFAULT_SIGNALS_DIR), dest="signals_dir")
    p.add_argument("--risk-mode", choices=list(RISK_MODES), default="balanced",
                   dest="risk_mode")
    p.add_argument("--warmup-bars", type=int, default=120, dest="warmup_bars")
    p.add_argument("--max-forward-bars", type=int, default=DEFAULT_MAX_FORWARD_BARS,
                   dest="max_forward_bars",
                   help="Bars after entry to wait for TP/SL before an expiry exit.")
    p.add_argument("--cost-points", type=float, default=0.0, dest="cost_points",
                   help="Flat round-trip cost (commission) in points, subtracted from "
                        "each trade so the track record is NET. Default 0.")
    p.add_argument("--spread-cost", action="store_true", dest="spread_cost",
                   help="Also subtract the entry bar's REAL spread as round-trip cost "
                        "(honest net P&L). Combine with --cost-points for extra commission.")
    p.add_argument("--include-forming-bar", action="store_true", dest="include_forming_bar",
                   help="Also decide on the newest (possibly still-forming) bar. "
                        "Default OFF — only fully closed bars are logged.")
    p.add_argument("--trend-filter", action="store_true", dest="use_trend_filter",
                   help="Higher-timeframe trend filter (the validated M15-swing edge).")
    p.add_argument("--mean-reversion", action="store_true", dest="use_mean_reversion",
                   help="Add the mean-reversion detector.")
    p.add_argument("--json", action="store_true", dest="json_output")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        result = run_signal_logger(
            symbol=args.symbol, timeframe=args.timeframe, history_dir=args.history_dir,
            macro_history_dir=args.macro_history_dir, signals_dir=args.signals_dir,
            risk_mode=args.risk_mode, warmup_bars=args.warmup_bars,
            skip_forming_bar=not args.include_forming_bar,
            use_trend_filter=args.use_trend_filter,
            use_mean_reversion=args.use_mean_reversion,
            max_forward_bars=args.max_forward_bars,
            cost_points=args.cost_points, spread_cost=args.spread_cost,
        )
    except SignalLoggerError as exc:
        print(f"SIGNAL LOGGER FAILED: {exc}", file=sys.stderr)
        return 1

    s = result.summary
    if args.json_output:
        print(json.dumps(s, indent=2, default=str))
        return 0

    print("=" * 70)
    print(" GOLD BOT SIGNAL LOGGER   no-lookahead, offline, never trades")
    print("=" * 70)
    print(f" symbol/TF   : {s['symbol']} / {s['timeframe']}   risk {s['risk_mode']}")
    print(f" filters     : trend={s['use_trend_filter']}  mean_rev={s['use_mean_reversion']}")
    print(f" cost basis  : {s['expectancy_basis']}  "
          f"(cost_points={s['cost_points']}, spread_cost={s['spread_cost']})")
    print(f" this run    : +{s['new_signals_this_run']} new signal(s), "
          f"{s['closed_this_run']} closed")
    print(f" totals      : {s['total_signals']} signal(s)  "
          f"by status {s['by_status']}")
    for w in s.get("warnings", []):
        print(f"   warning - {w}")

    print(f"\n track record ({s['closed_trades']} closed trade(s)) by preset:")
    pr = s["per_preset"]
    for name, info in s["presets"].items():
        b = pr.get(name, {})
        print(f"   {info['label']:<13} ({info['description'][:46]})")
        print(f"      trades {b.get('trades', 0):>3}  win {b.get('wins', 0):>3} "
              f"loss {b.get('losses', 0):>3} neutral {b.get('neutral', 0):>3}  "
              f"| win% {b.get('win_rate_pct')}  "
              f"expectancy {b.get('expectancy_points')}pt  "
              f"total {b.get('total_realized_points')}pt")

    print(f"\n signals     : {result.signals_path}")
    print(f" summary     : {result.summary_path}")
    print(" no-lookahead: decisions saw only bars <= bar time; signals scored only "
          "against bars AFTER them. Never calls MT5, never sends orders.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
