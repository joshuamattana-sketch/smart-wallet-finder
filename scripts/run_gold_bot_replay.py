"""
scripts/run_gold_bot_replay.py
-------------------------------
LM85A - Run a no-lookahead historical replay/backtest of the Gold Bot decision
engine over locally-stored XAUUSD history (LM84A) with causal macro alignment
(LM84B). READ-ONLY, OFFLINE: never calls MT5, never sends orders.

Run from repo root:
    python scripts/run_gold_bot_replay.py --timeframe M1 --max-bars 200 --dry-run
    python scripts/run_gold_bot_replay.py --timeframe M1 --max-bars 200 --risk-mode balanced --horizons 5,15,30
    python scripts/run_gold_bot_replay.py --timeframe M5 --max-bars 200 --risk-mode scalp --horizons 3,6,12

Needs local history first:
    python scripts/run_gold_bot_history_backfill.py --timeframes M1,M5
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from services.gold_bot_lot_calculator import RISK_MODES  # noqa: E402
from services.gold_bot_replay_engine import (  # noqa: E402
    DEFAULT_HISTORY_DIR,
    DEFAULT_MACRO_HISTORY_DIR,
    DEFAULT_REPLAY_DIR,
    ReplayError,
    run_replay,
)


def _parse_iso(s: str) -> datetime:
    d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc)


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="run_gold_bot_replay",
        description="No-lookahead replay/backtest over local history (offline, no MT5).",
    )
    p.add_argument("--symbol", default="XAUUSD")
    p.add_argument("--timeframe", default="M1")
    p.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR), dest="history_dir")
    p.add_argument("--macro-history-dir", default=str(DEFAULT_MACRO_HISTORY_DIR), dest="macro_history_dir")
    p.add_argument("--out-dir", default=str(DEFAULT_REPLAY_DIR), dest="out_dir")
    p.add_argument("--warmup-bars", type=int, default=120, dest="warmup_bars")
    p.add_argument("--max-bars", type=int, default=500, dest="max_bars")
    p.add_argument("--from-time", default=None, dest="from_time", help="ISO UTC (optional).")
    p.add_argument("--to-time", default=None, dest="to_time", help="ISO UTC (optional).")
    p.add_argument("--risk-mode", choices=list(RISK_MODES), default="balanced", dest="risk_mode")
    p.add_argument("--horizons", default="5,15,30", help="Comma list of forward bar counts.")
    p.add_argument("--use-learning-modifiers", action="store_true", dest="use_learning_modifiers",
                   help="Apply demo-only learned confidence modifiers (default off).")
    p.add_argument("--learning-modifiers-file", default=None, dest="learning_modifiers_file",
                   help="Active demo modifiers JSON (default data/gold_bot/learning/active_demo_modifiers.json).")
    p.add_argument("--dry-run", action="store_true", dest="dry_run")
    p.add_argument("--json", action="store_true", dest="json_output")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    horizons = tuple(int(h) for h in args.horizons.split(",") if h.strip())
    from_time = _parse_iso(args.from_time) if args.from_time else None
    to_time = _parse_iso(args.to_time) if args.to_time else None

    try:
        result = run_replay(
            symbol=args.symbol, timeframe=args.timeframe, history_dir=args.history_dir,
            macro_history_dir=args.macro_history_dir, out_dir=args.out_dir,
            warmup_bars=args.warmup_bars, max_bars=args.max_bars, from_time=from_time,
            to_time=to_time, risk_mode=args.risk_mode, horizons=horizons, dry_run=args.dry_run,
            use_learning_modifiers=args.use_learning_modifiers,
            learning_modifiers_file=args.learning_modifiers_file,
        )
    except ReplayError as exc:
        print(f"REPLAY FAILED: {exc}", file=sys.stderr)
        return 1

    s = result.summary
    if args.json_output:
        print(json.dumps(s, indent=2, default=str))
        return 0

    print("=" * 70)
    print(f" GOLD BOT REPLAY   ({'DRY-RUN' if args.dry_run else 'RUN'})   no-lookahead, offline")
    print("=" * 70)
    print(f" symbol/TF   : {s['symbol']} / {s['timeframe']}   risk {s['risk_mode']}")
    print(f" history     : {s['history_rows']} rows  {s['first_bar']} -> {s['last_bar']}")
    print(f" range       : warmup {s['warmup_bars']}  max-bars {s['max_bars']}  "
          f"horizons {s['horizons']}")
    print(f" macro loaded: {', '.join(s['macro_loaded']) or '(none - macro unknown)'}")
    print(f" learning     : {'ON' if s.get('used_learning_modifiers') else 'off'}"
          f"  ({s.get('learning_modifiers_count', 0)} demo modifier(s), confidence-only)")
    print(f" planned     : {s['planned_steps']} step(s)")
    for w in s.get("warnings", []):
        print(f"   warning - {w}")

    if args.dry_run:
        print("\n Dry-run only - no files written. Safe: never calls MT5, never sends orders.")
        return 0

    print(f"\n bars processed : {s['bars_processed']}")
    d = s["decisions"]
    print(f" decisions      : LONG {d['long']}  SHORT {d['short']}  NO_TRADE {d['no_trade']}  "
          f"(avg conf {s['avg_confidence']})")
    print(" by horizon     :")
    for hz, b in s["by_horizon"].items():
        print(f"   {hz:>3} bars: win {b['win']} loss {b['loss']} neutral {b['neutral']} "
              f"no_data {b['no_data']} | avg trade ret {b['avg_trade_return_points']}pt")
    if s["top_setups"]:
        tops = ", ".join(f"{t['strategy']}={t['count']}" for t in s["top_setups"][:5])
        print(f" top setups     : {tops}")
    print(f"\n output         : {result.jsonl_path}")
    print(f"                  {result.summary_path}")
    print(" no-lookahead   : decisions saw only bars <= current time; macro joined as-of; "
          "forward scoring used future bars only AFTER each decision.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
