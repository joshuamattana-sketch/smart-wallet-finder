"""
scripts/run_gold_bot_learning_scorecard.py
--------------------------------------------
LM86A - Build a learning scorecard from replay JSONL (LM85A). READ-ONLY, OFFLINE:
no MT5, no orders, no HTTP. Produces explainable setup scorecards; the modifier
output (setup_modifiers.preview.json) is a PREVIEW ONLY and is not active. Active
modifiers live in active_demo_modifiers.json and apply only with
--use-learning-modifiers. Live trading stays locked.

Run from repo root (needs replay output first - see LM85A):
    python scripts/run_gold_bot_learning_scorecard.py --dry-run
    python scripts/run_gold_bot_learning_scorecard.py --horizon 15 --min-samples 10 --top 10
    python scripts/run_gold_bot_learning_scorecard.py --timeframe M5 --risk-mode scalp --horizon 12 --min-samples 10 --top 10
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
    DEFAULT_REPLAY_DIR,
    build_real_trade_stats,
    build_scorecard,
    load_demo_trade_outcomes,
    load_replay_rows,
    write_real_trade_blend,
    write_scorecard,
)


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="run_gold_bot_learning_scorecard",
        description="Aggregate replay JSONL into setup scorecards (offline, read-only).",
    )
    p.add_argument("--replay-dir", default=str(DEFAULT_REPLAY_DIR), dest="replay_dir")
    p.add_argument("--out-dir", default=str(DEFAULT_LEARNING_DIR), dest="out_dir")
    p.add_argument("--symbol", default="XAUUSD")
    p.add_argument("--timeframe", default=None)
    p.add_argument("--risk-mode", default=None, dest="risk_mode")
    p.add_argument("--horizon", type=int, default=15)
    p.add_argument("--min-samples", type=int, default=20, dest="min_samples")
    p.add_argument("--missed-move-threshold-points", type=float, default=150.0,
                   dest="missed_threshold")
    p.add_argument("--top", type=int, default=10)
    # LM89B real demo-trade blending (default off for backward compatibility).
    p.add_argument("--include-real-trades", action="store_true", dest="include_real_trades",
                   help="Blend real demo_trade_outcome events into the scorecard (demo-only).")
    p.add_argument("--real-trade-weight", type=float, default=2.0, dest="real_trade_weight")
    p.add_argument("--min-real-trades", type=int, default=5, dest="min_real_trades")
    p.add_argument("--learning-events-file", default=None, dest="learning_events_file",
                   help="learning_events.jsonl (default data/gold_bot/learning/learning_events.jsonl).")
    p.add_argument("--dry-run", action="store_true", dest="dry_run")
    p.add_argument("--json", action="store_true", dest="json_output")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    rows, files, warnings = load_replay_rows(
        args.replay_dir, symbol=args.symbol, timeframe=args.timeframe, risk_mode=args.risk_mode)

    if not files:
        print(f"LEARNING FAILED: no replay JSONL files in {args.replay_dir} - run "
              "scripts/run_gold_bot_replay.py first.", file=sys.stderr)
        return 1
    if not rows:
        print(f"LEARNING FAILED: replay files found but 0 rows matched filters "
              f"(symbol={args.symbol} timeframe={args.timeframe} risk={args.risk_mode}).",
              file=sys.stderr)
        return 1

    if args.dry_run:
        out = {"mode": "dry_run", "replay_files": files, "rows": len(rows),
               "horizon": args.horizon, "min_samples": args.min_samples, "warnings": warnings}
        if args.json_output:
            print(json.dumps(out, indent=2, default=str))
        else:
            print("=" * 70)
            print(" GOLD BOT LEARNING SCORECARD   (DRY-RUN)   offline, read-only")
            print("=" * 70)
            print(f" replay files : {len(files)}  ({', '.join(files)})")
            print(f" rows         : {len(rows)}   horizon {args.horizon}  min-samples {args.min_samples}")
            for w in warnings:
                print(f"   warning - {w}")
            print("\n Dry-run only - no files written. Never calls MT5, never sends orders.")
        return 0

    real_stats = None
    if args.include_real_trades:
        events_file = args.learning_events_file or (Path(args.out_dir) / "learning_events.jsonl")
        outcomes, rt_warn, dups = load_demo_trade_outcomes(events_file)
        real_stats = build_real_trade_stats(outcomes, min_real_trades=args.min_real_trades,
                                            duplicates_ignored=dups, warnings=rt_warn)
        warnings = warnings + rt_warn
        if not outcomes:
            warnings.append("--include-real-trades set but no demo_trade_outcome events found "
                            "(run a confirmed demo session + outcome sync first).")

    scorecard = build_scorecard(rows, horizon=args.horizon, min_samples=args.min_samples,
                                missed_threshold=args.missed_threshold, top=args.top,
                                warnings=warnings, real_stats=real_stats,
                                real_trade_weight=args.real_trade_weight)
    paths = write_scorecard(args.out_dir, scorecard, symbol=args.symbol,
                            timeframe=args.timeframe, risk_mode=args.risk_mode)
    if real_stats is not None:
        paths.update(write_real_trade_blend(args.out_dir, scorecard, real_stats))

    if args.json_output:
        print(json.dumps({"scorecard": scorecard,
                          "paths": {k: str(v) for k, v in paths.items()}}, indent=2, default=str))
        return 0

    g = scorecard["global"]
    print("=" * 70)
    print(" GOLD BOT LEARNING SCORECARD   offline, read-only (preview only)")
    print("=" * 70)
    print(f" replay files : {len(files)}   rows {scorecard['rows']}   horizon {scorecard['horizon']}")
    print(f" filters      : symbol {args.symbol}  timeframe {args.timeframe or 'all'}  "
          f"risk {args.risk_mode or 'all'}")
    for w in warnings:
        print(f"   warning - {w}")
    print(f"\n GLOBAL: trades {g['trade_count']}  no_trade {g['no_trade_count']}  "
          f"L/S {g['long_count']}/{g['short_count']}  avg_conf {g['avg_confidence']}")
    print(f"         winrate {g['winrate']}  expectancy {g['expectancy_points']}pt  "
          f"status {g['recommended_status']}")

    if scorecard.get("include_real_trades"):
        rg = scorecard.get("real_global") or {}
        print(f"\n REAL demo (weight {scorecard['real_trade_weight']}): trades {rg.get('trade_count')}  "
              f"W/L/BE {rg.get('win_count')}/{rg.get('loss_count')}/{rg.get('breakeven_count')}  "
              f"winrate {rg.get('winrate')}  realized {rg.get('realized_pnl')}  "
              f"avg_pts {rg.get('avg_pnl_points')}  quality {rg.get('sample_quality')}")
        print(f"         duplicates ignored {scorecard.get('real_duplicates_ignored')}  "
              "(combined_* per setup; status uses combined when real present)")

    print(f"\n TOP setups by expectancy (h{scorecard['horizon']}, >= {args.min_samples} trades):")
    if not scorecard["top_setups_by_expectancy"]:
        print("   (none clear the sample guard yet)")
    for t in scorecard["top_setups_by_expectancy"]:
        print(f"   {t['setup']:<22} exp {t['expectancy_points']}pt  winrate {t['winrate']}  "
              f"trades {t['trade_count']}  [{t['recommended_status']}]")
    if scorecard["weak_or_avoid_setups"]:
        print(f" WEAK/AVOID   : {', '.join(scorecard['weak_or_avoid_setups'])}")

    print("\n Confidence buckets (winrate / expectancy):")
    for b, v in scorecard["confidence_buckets"].items():
        print(f"   {b:<8} trades {v['trade_count']:>4}  winrate {v['winrate']}  "
              f"exp {v['expectancy_points']}pt")

    nt = scorecard["no_trade_missed"].get(str(scorecard["horizon"]), {})
    print(f"\n NO_TRADE missed (h{scorecard['horizon']}): count {nt.get('count')}  "
          f"avg raw move {nt.get('avg_raw_move_points')}pt  "
          f"large moves > {int(args.missed_threshold)}pt: {nt.get('missed_large_moves')}")

    print(f"\n output       : {paths['named']}")
    print(f"                {paths['latest']}")
    print(f"                {paths['preview']}")

    rg = scorecard.get("real_global") or {}
    real_count = rg.get("trade_count") or 0
    print("\n Impact:")
    print("   scorecard         : read-only preview")
    print("   preview modifiers : written to setup_modifiers.preview.json, not active")
    print("   active modifiers  : read from active_demo_modifiers.json")
    print("   decision impact   : active modifiers apply only when --use-learning-modifiers is passed")
    if real_count > 0:
        print(f"   real demo         : {real_count} trades included with weight "
              f"{scorecard.get('real_trade_weight')}")
    else:
        print("   real demo         : 0 trades - learning is replay-dominant")
    print("   live trading      : locked")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
