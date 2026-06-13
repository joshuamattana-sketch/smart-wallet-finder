"""
scripts/run_gold_bot_demo_session.py
--------------------------------------
LM88A - Run a bounded Gold Bot DEMO auto-session (MT5 demo only, NEVER live).

Composes the worker + demo learning modifiers + LM87A safety supervisor into one
controlled session with hard wall-clock / trade / drawdown limits and a written
report. OBSERVE-ONLY by default: it SENDS NOTHING unless you pass
--confirm-demo-session, and even then the worker's own demo guards still apply.

Run from repo root (Windows, MT5 running on a demo account):
    python scripts/run_gold_bot_demo_session.py --duration-minutes 1 --max-iterations 3
    python scripts/run_gold_bot_demo_session.py --duration-minutes 1 --max-iterations 3 --use-learning-modifiers
    python scripts/run_gold_bot_demo_session.py --confirm-demo-session --duration-minutes 5 --max-trades 3 --risk-mode scalp

Requires the MT5 Python package (Windows only) when running against a terminal;
see scripts/run_gold_bot_worker.py for the install note. No MT5 import lives here.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from services.gold_bot_demo_session_runner import (  # noqa: E402
    DemoSessionConfig,
    DemoSessionRunner,
)
from services.gold_bot_lot_calculator import RISK_MODES  # noqa: E402


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="run_gold_bot_demo_session",
        description="Bounded Gold Bot demo auto-session (MT5 demo only; observe by default).",
    )
    p.add_argument("--symbol", default="XAUUSD")
    p.add_argument("--risk-mode", choices=list(RISK_MODES), default="scalp", dest="risk_mode")
    p.add_argument("--timeframe", default="M1")
    p.add_argument("--interval-seconds", type=float, default=5.0, dest="interval_seconds")
    p.add_argument("--duration-minutes", type=float, default=30.0, dest="duration_minutes")
    p.add_argument("--max-iterations", type=int, default=None, dest="max_iterations")
    p.add_argument("--max-trades", type=int, default=10, dest="max_trades")
    p.add_argument("--max-runtime-loss-pct", type=float, default=3.0, dest="max_runtime_loss_pct")
    p.add_argument("--use-learning-modifiers", action="store_true", default=True,
                   dest="use_learning_modifiers", help="Demo-only confidence learning (default on).")
    p.add_argument("--no-learning-modifiers", action="store_false", dest="use_learning_modifiers",
                   help="Disable demo learning modifiers for this session.")
    p.add_argument("--calendar-file", default=None, dest="calendar_file")
    p.add_argument("--macro-events-file", default=None, dest="macro_events_file")
    p.add_argument("--confirm-demo-session", action="store_true", dest="confirm_demo_session",
                   help="ARM the session: allow demo orders (still gated by the worker demo flags).")
    p.add_argument("--no-sync-outcomes", action="store_false", dest="sync_outcomes", default=True,
                   help="Skip the post-session MT5 trade-outcome feedback sync (armed sessions only).")
    p.add_argument("--json", action="store_true", dest="json_output")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    cfg = DemoSessionConfig(
        symbol=args.symbol, risk_mode=args.risk_mode, timeframe=args.timeframe,
        interval_seconds=args.interval_seconds, duration_minutes=args.duration_minutes,
        max_iterations=args.max_iterations, max_trades=args.max_trades,
        max_runtime_loss_pct=args.max_runtime_loss_pct,
        use_learning_modifiers=args.use_learning_modifiers,
        calendar_file=args.calendar_file, macro_events_file=args.macro_events_file,
        confirm_demo_session=args.confirm_demo_session, sync_outcomes=args.sync_outcomes,
    )
    result = DemoSessionRunner(cfg).run()
    if args.json_output:
        print(json.dumps(result.to_dict(), indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
