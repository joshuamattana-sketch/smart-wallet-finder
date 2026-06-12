"""
scripts/run_gold_bot_learning_scorecard.py
--------------------------------------------
LM86A - Build a learning scorecard from replay JSONL (LM85A). READ-ONLY, OFFLINE:
no MT5, no orders, no HTTP. Produces explainable setup scorecards; any modifier
output is a PREVIEW ONLY and is NOT wired into live decisions.

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
    build_scorecard,
    load_replay_rows,
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

    scorecard = build_scorecard(rows, horizon=args.horizon, min_samples=args.min_samples,
                                missed_threshold=args.missed_threshold, top=args.top,
                                warnings=warnings)
    paths = write_scorecard(args.out_dir, scorecard, symbol=args.symbol,
                            timeframe=args.timeframe, risk_mode=args.risk_mode)

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
    print(f"                {paths['preview']}  (PREVIEW ONLY - not used by live decisions)")
    print(" live impact  : NONE. Learning modifiers are not wired into the decision engine "
          "or worker (owner-approved gate is a later patch).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
