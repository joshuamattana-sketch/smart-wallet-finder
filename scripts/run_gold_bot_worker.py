"""
scripts/run_gold_bot_worker.py
-------------------------------
LM81A — Long-running Gold Bot worker loop (MT5 DEMO ONLY).

Continuously reads the MT5 demo terminal, builds macro context, runs the
Decision Engine V2 and journals a compact result every iteration. OBSERVE /
dry-run by default — it SENDS NOTHING. A demo order is only attempted with
--mode demo AND --auto-execute-demo AND --confirm-demo-order, on a verified
demo account, after the LM75 risk gate approves (and never during a macro
lockout or with an open XAUUSD position).

Run from repo root (Windows, MT5 running on a demo account):
    python scripts/run_gold_bot_worker.py --max-iterations 1
    python scripts/run_gold_bot_worker.py --max-iterations 5 --interval-seconds 5
    python scripts/run_gold_bot_worker.py --risk-mode scalp \
        --macro-events-file data/gold_bot/macro_events.sample.json \
        --max-iterations 5 --interval-seconds 5

Requires the MetaTrader5 package (Windows only):  pip install MetaTrader5
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from services.gold_bot_lot_calculator import RISK_MODES  # noqa: E402
from services.gold_bot_worker import GoldBotWorker, WorkerConfig  # noqa: E402


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="run_gold_bot_worker",
        description="Gold Bot worker loop (MT5 demo only; observe/dry-run by default).",
    )
    p.add_argument("--mode", choices=["observe", "demo"], default="observe",
                   help="observe = never send; demo = may send only with the execute+confirm flags.")
    p.add_argument("--environment", choices=["paper", "demo", "live"], default="demo",
                   help="Execution environment (LM93A). live is hard-locked.")
    p.add_argument("--allow-live-trading", action="store_true", dest="allow_live_trading",
                   help="No-op safety flag; live stays hard-locked in this build.")
    p.add_argument("--risk-mode", choices=list(RISK_MODES), default="balanced", dest="risk_mode")
    p.add_argument("--interval-seconds", type=float, default=10.0, dest="interval_seconds")
    p.add_argument("--max-iterations", type=int, default=None, dest="max_iterations",
                   help="Stop after N iterations (default: run until interrupted).")
    p.add_argument("--symbol", default=None, help="Gold symbol; omit to auto-discover.")
    p.add_argument("--timeframe", default="M1")
    p.add_argument("--bars", type=int, default=120)
    p.add_argument("--calendar-file", default=None, dest="calendar_file",
                   help="Normalized economic calendar JSON (preferred).")
    p.add_argument("--macro-events-file", default=None, dest="macro_events_file",
                   help="Legacy LM77A macro events JSON (fallback if --calendar-file omitted).")
    p.add_argument("--dxy-bias", choices=["rising", "falling", "flat", "unknown"],
                   default="unknown", dest="dxy_bias")
    p.add_argument("--yields-bias", choices=["rising", "falling", "flat", "unknown"],
                   default="unknown", dest="yields_bias")
    p.add_argument("--geopolitical-risk", choices=["low", "medium", "high", "unknown"],
                   default="unknown", dest="geopolitical_risk")
    p.add_argument("--auto-execute-demo", action="store_true", dest="auto_execute_demo")
    p.add_argument("--confirm-demo-order", action="store_true", dest="confirm_demo_order")
    p.add_argument("--close-on-no-trade", action="store_true", dest="close_on_no_trade",
                   help="Placeholder in V1 (surfaced, never sends a close).")
    p.add_argument("--use-learning-modifiers", action="store_true", dest="use_learning_modifiers",
                   help="Apply demo-only learned confidence modifiers (default off; never live).")
    p.add_argument("--learning-modifiers-file", default=None, dest="learning_modifiers_file",
                   help="Active demo modifiers JSON (default data/gold_bot/learning/active_demo_modifiers.json).")
    p.add_argument("--no-status-file", action="store_true", dest="no_status_file",
                   help="Do not write data/gold_bot/worker_status.json.")
    # LM87A demo safety supervisor limits (the supervisor itself has NO off switch).
    p.add_argument("--max-open-positions", type=int, default=1, dest="max_open_positions")
    p.add_argument("--max-trades-per-hour", type=int, default=6, dest="max_trades_per_hour")
    p.add_argument("--min-seconds-between-trades", type=int, default=120,
                   dest="min_seconds_between_trades")
    p.add_argument("--max-consecutive-losses", type=int, default=3, dest="max_consecutive_losses")
    p.add_argument("--cooldown-minutes-after-loss-streak", type=int, default=30,
                   dest="cooldown_minutes_after_loss_streak")
    p.add_argument("--max-spread-points", type=float, default=None, dest="max_spread_points",
                   help="Override the per-risk-mode spread ceiling (balanced 35 / scalp 25).")
    p.add_argument("--json", action="store_true", dest="json_output")
    return p.parse_args(argv)


def _refuse_live(args) -> bool:
    if getattr(args, "environment", "demo") == "live":
        print("error: live environment is hard-locked and not implemented "
              "(LIVE_NOT_IMPLEMENTED). This tool runs demo/paper only.", file=sys.stderr)
        return True
    return False


def main(argv=None) -> int:
    args = parse_args(argv)
    if _refuse_live(args):
        return 2
    cfg = WorkerConfig(
        mode=args.mode, environment=args.environment, risk_mode=args.risk_mode,
        interval_seconds=args.interval_seconds,
        max_iterations=args.max_iterations, symbol=args.symbol, timeframe=args.timeframe,
        bars=args.bars, calendar_file=args.calendar_file,
        macro_events_file=args.macro_events_file, dxy_bias=args.dxy_bias,
        yields_bias=args.yields_bias, geopolitical_risk=args.geopolitical_risk,
        auto_execute_demo=args.auto_execute_demo, confirm_demo_order=args.confirm_demo_order,
        close_on_no_trade=args.close_on_no_trade,
        use_learning_modifiers=args.use_learning_modifiers,
        learning_modifiers_file=args.learning_modifiers_file, json_output=args.json_output,
        write_status=not args.no_status_file,
        max_open_positions=args.max_open_positions,
        max_trades_per_hour=args.max_trades_per_hour,
        min_seconds_between_trades=args.min_seconds_between_trades,
        max_consecutive_losses=args.max_consecutive_losses,
        cooldown_minutes_after_loss_streak=args.cooldown_minutes_after_loss_streak,
        max_spread_points=args.max_spread_points,
    )
    return GoldBotWorker(cfg).run()


if __name__ == "__main__":
    raise SystemExit(main())
