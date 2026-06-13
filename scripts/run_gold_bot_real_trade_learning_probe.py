"""
scripts/run_gold_bot_real_trade_learning_probe.py
---------------------------------------------------
LM89B - Inspect the REAL demo-trade learning dataset. READ-ONLY, OFFLINE: reads
`demo_trade_outcome` events (LM89A) from learning_events.jsonl and prints
aggregate stats by setup / risk-mode. No MT5, no orders, no HTTP. Safe when there
are no demo outcomes yet (prints a hint, exits 0).

Run from repo root:
    python scripts/run_gold_bot_real_trade_learning_probe.py
    python scripts/run_gold_bot_real_trade_learning_probe.py --min-real-trades 5 --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from services.gold_bot_learning_journal import (  # noqa: E402
    DEFAULT_LEARNING_DIR,
    build_real_trade_stats,
    default_events_file,
    load_demo_trade_outcomes,
)


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="run_gold_bot_real_trade_learning_probe",
        description="Inspect real demo_trade_outcome learning stats (offline, read-only).",
    )
    p.add_argument("--learning-events-file", default=str(default_events_file(DEFAULT_LEARNING_DIR)),
                   dest="learning_events_file")
    p.add_argument("--min-real-trades", type=int, default=5, dest="min_real_trades")
    p.add_argument("--include-open", action="store_true", dest="include_open",
                   help="Include open/unknown outcomes (default off).")
    p.add_argument("--json", action="store_true", dest="json_output")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    outcomes, warnings, dups = load_demo_trade_outcomes(
        args.learning_events_file, include_open=args.include_open)
    stats = build_real_trade_stats(outcomes, min_real_trades=args.min_real_trades,
                                   duplicates_ignored=dups, warnings=warnings)
    g = stats["global"]
    enough = g["trade_count"] >= args.min_real_trades

    if args.json_output:
        print(json.dumps({"events_file": args.learning_events_file, "stats": stats,
                          "enough_for_learning": enough, "warnings": warnings}, indent=2, default=str))
        return 0

    print("=" * 70)
    print(" GOLD BOT REAL-TRADE LEARNING   PROBE   offline, read-only")
    print("=" * 70)
    print(f" events file : {args.learning_events_file}")
    for w in warnings:
        print(f"   warning - {w}")

    if g["trade_count"] == 0:
        print("\n No demo_trade_outcome events found yet. Run a confirmed demo session and "
              "outcome sync first:")
        print("   python scripts/run_gold_bot_demo_session.py --confirm-demo-session --duration-minutes 5 "
              "--max-trades 3 --risk-mode scalp --use-learning-modifiers")
        print("   python scripts/run_gold_bot_trade_outcomes_probe.py "
              "--session-file data/gold_bot/sessions/session_latest.json --write")
        return 0

    print(f"\n GLOBAL: trades {g['trade_count']}  W/L/BE {g['win_count']}/{g['loss_count']}/"
          f"{g['breakeven_count']}  winrate {g['winrate']}  realized {g['realized_pnl']}")
    print(f"         avg_pnl {g['avg_pnl']}  avg_pts {g['avg_pnl_points']}  "
          f"avg_conf {g['avg_confidence']}  loss_streak_max {g['loss_streak_max']}  "
          f"quality {g['sample_quality']}")
    print(f"         duplicates ignored {dups}   min-real-trades {args.min_real_trades}")

    print("\n By setup:")
    for s, v in sorted(stats["by_setup"].items(), key=lambda kv: kv[1]["realized_pnl"]):
        print(f"   {s:<22} n {v['trade_count']:>3}  W/L/BE {v['win_count']}/{v['loss_count']}/"
              f"{v['breakeven_count']}  wr {v['winrate']}  realized {v['realized_pnl']}  "
              f"pts {v['avg_pnl_points']}  [{v['sample_quality']}]")
    print(" By risk mode:")
    for s, v in sorted(stats["by_risk_mode"].items()):
        print(f"   {s:<12} n {v['trade_count']:>3}  wr {v['winrate']}  realized {v['realized_pnl']}  "
              f"pts {v['avg_pnl_points']}  [{v['sample_quality']}]")

    print(f"\n enough for learning : {'YES' if enough else 'NO'} "
          f"(have {g['trade_count']}, need {args.min_real_trades})")
    print(" Enable blending: run_gold_bot_learning_scorecard.py / run_gold_bot_learning_cycle.py "
          "--include-real-trades. Demo-only, confidence-only. No orders sent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
