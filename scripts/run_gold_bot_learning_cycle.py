"""
scripts/run_gold_bot_learning_cycle.py
----------------------------------------
LM86C - Run the Gold Bot automatic learning cycle (DEMO-ONLY).

Chains: baseline replay -> scorecard -> promote CANDIDATE -> candidate replay ->
compare -> keep or rollback. A candidate only replaces the active demo modifiers
when it OBJECTIVELY beats the baseline (expectancy improvement + trade-count /
winrate guards). Otherwise the active modifiers are kept and the candidate is
recorded as rejected.

OFFLINE + DEMO-ONLY: never calls MT5, never sends orders, no HTTP, no secrets.
Modifiers stay confidence-only and can never enable live trading or bypass the
macro lockout / risk gate / kill switch.

Run from repo root (needs local history first - see LM84A/LM84B):
    python scripts/run_gold_bot_learning_cycle.py --dry-run
    python scripts/run_gold_bot_learning_cycle.py --timeframe M1 --risk-mode balanced --max-bars 500 --horizon 15 --min-samples 10
    python scripts/run_gold_bot_learning_cycle.py --rollback
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from services.gold_bot_learning_cycle import (  # noqa: E402
    DEFAULT_MIN_IMPROVEMENT_POINTS,
    DEFAULT_MIN_TRADE_COUNT_RATIO,
    DEFAULT_MIN_TRADES,
    DEFAULT_REPLAY_DIR,
    CycleError,
    run_cycle,
    run_rollback,
)
from services.gold_bot_learning_modifiers import DEFAULT_LEARNING_DIR  # noqa: E402


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="run_gold_bot_learning_cycle",
        description="Automatic demo-only learning cycle (offline, no MT5, no orders).",
    )
    p.add_argument("--symbol", default="XAUUSD")
    p.add_argument("--timeframe", default="M1")
    p.add_argument("--risk-mode", default="balanced", dest="risk_mode")
    p.add_argument("--max-bars", type=int, default=500, dest="max_bars")
    p.add_argument("--horizons", default="5,15,30", help="Comma list of forward bar counts.")
    p.add_argument("--horizon", type=int, default=15, help="Horizon used for comparison.")
    p.add_argument("--min-samples", type=int, default=10, dest="min_samples")
    p.add_argument("--min-trades", type=int, default=DEFAULT_MIN_TRADES, dest="min_trades")
    p.add_argument("--min-improvement-points", type=float, default=DEFAULT_MIN_IMPROVEMENT_POINTS,
                   dest="min_improvement_points")
    p.add_argument("--min-trade-count-ratio", type=float, default=DEFAULT_MIN_TRADE_COUNT_RATIO,
                   dest="min_trade_count_ratio")
    p.add_argument("--learning-dir", default=str(DEFAULT_LEARNING_DIR), dest="learning_dir")
    p.add_argument("--replay-out-dir", default=str(DEFAULT_REPLAY_DIR), dest="replay_out_dir")
    # LM89B real demo-trade blending (default off for backward compatibility).
    p.add_argument("--include-real-trades", action="store_true", dest="include_real_trades",
                   help="Blend real demo_trade_outcome events into the cycle scorecard (demo-only).")
    p.add_argument("--real-trade-weight", type=float, default=2.0, dest="real_trade_weight")
    p.add_argument("--min-real-trades", type=int, default=5, dest="min_real_trades")
    # Walk-forward: fit modifiers on a TRAIN slice, accept/reject on a disjoint,
    # unseen VALIDATE slice. The structural defence against in-sample overfitting.
    p.add_argument("--walk-forward", action="store_true", dest="walk_forward",
                   help="Fit the scorecard on a TRAIN window and accept/reject on a disjoint "
                        "VALIDATE window (out-of-sample). Recommended for trustworthy learning.")
    p.add_argument("--train-fraction", type=float, default=0.6, dest="train_fraction",
                   help="Fraction of history used for the TRAIN window (rest is VALIDATE).")
    p.add_argument("--dry-run", action="store_true", dest="dry_run",
                   help="Print planned steps + validate files. Writes nothing.")
    p.add_argument("--rollback", action="store_true",
                   help="Restore active_demo_modifiers.json from its backup, then exit.")
    p.add_argument("--json", action="store_true", dest="json_output")
    return p.parse_args(argv)


def _fmt_summary(label: str, view: dict) -> str:
    if view.get("no_data"):
        return f" {label:<9}: NO DATA at horizon {view.get('horizon')}"
    d = view.get("decisions", {})
    return (f" {label:<9}: exp {view['expectancy_points']}pt  winrate {view['winrate']}  "
            f"trades {view['trade_count']}  no_trade {view['no_trade_count']}  "
            f"(L {d.get('long')}/S {d.get('short')}, avg conf {view.get('avg_confidence')})")


def main(argv=None) -> int:
    args = parse_args(argv)

    # ── rollback short-circuit ──────────────────────────────────────────────────
    if args.rollback:
        ok, message = run_rollback(args.learning_dir)
        if args.json_output:
            print(json.dumps({"rollback": True, "ok": ok, "message": message}, indent=2))
        else:
            print("=" * 70)
            print(" GOLD BOT LEARNING CYCLE   ROLLBACK   demo-only")
            print("=" * 70)
            print(f" {'OK' if ok else 'NO-OP'} - {message}")
        return 0 if ok else 1

    horizons = tuple(int(h) for h in args.horizons.split(",") if h.strip())
    try:
        result = run_cycle(
            symbol=args.symbol, timeframe=args.timeframe, risk_mode=args.risk_mode,
            max_bars=args.max_bars, horizons=horizons, horizon=args.horizon,
            min_samples=args.min_samples, min_trades=args.min_trades,
            min_improvement_points=args.min_improvement_points,
            min_trade_count_ratio=args.min_trade_count_ratio,
            learning_dir=args.learning_dir, replay_out_dir=args.replay_out_dir,
            include_real_trades=args.include_real_trades,
            real_trade_weight=args.real_trade_weight, min_real_trades=args.min_real_trades,
            walk_forward=args.walk_forward, train_fraction=args.train_fraction,
            dry_run=args.dry_run)
    except CycleError as exc:
        print(f"LEARNING CYCLE FAILED: {exc}", file=sys.stderr)
        return 1

    if args.json_output:
        print(json.dumps(result.to_dict(), indent=2, default=str))
        return 0

    print("=" * 70)
    print(f" GOLD BOT LEARNING CYCLE   ({'DRY-RUN' if result.dry_run else 'RUN'})   demo-only, offline")
    print("=" * 70)
    print(f" cycle id    : {result.cycle_id}")
    print(f" symbol/TF   : {args.symbol} / {args.timeframe}   risk {args.risk_mode}   "
          f"horizon {args.horizon}")
    for w in result.warnings:
        print(f"   warning - {w}")

    if result.dry_run:
        print("\n Planned steps:")
        for step in result.planned_steps:
            print(f"   {step}")
        print("\n Dry-run only - no files written. Never calls MT5, never sends orders, no HTTP.")
        print(" Demo-only: modifiers stay confidence-only; macro lockout / risk gate / kill "
              "switch / volume are never touched.")
        return 0

    print("\n" + _fmt_summary("baseline", result.baseline))
    print(_fmt_summary("candidate", result.candidate))
    c = result.comparison
    if not result.baseline.get("no_data") and not result.candidate.get("no_data"):
        print(f" diff      : expectancy {c.get('expectancy_improvement'):+}pt  "
              f"winrate {c.get('winrate_change'):+}  trade ratio {c.get('trade_count_ratio')}")
        print(f" checks    : {c.get('checks')}")

    verdict = "ACCEPTED" if result.accepted else "REJECTED"
    print(f"\n verdict   : {verdict}")
    print(f" reason    : {result.reason}")
    if result.real_trades_used:
        print(f" real demo : blended {result.real_trade_count} demo trade(s) "
              f"(weight {result.real_trade_weight})")
    print(f"\n active modifiers : {result.active_modifiers_path}")
    print(f" candidate file   : {result.candidate_modifiers_path}")
    if result.backup_modifiers_path:
        print(f" backup (prev)    : {result.backup_modifiers_path}")
    if result.rejected_modifiers_path:
        print(f" rejected file    : {result.rejected_modifiers_path}")
    print(f" cycle summary    : {result.cycle_summary_path}")
    print("\n Demo-only: candidate modifiers are confidence-only. This cycle never enables live "
          "trading, never sends orders, never touches MT5, and never changes volume / lot size.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
