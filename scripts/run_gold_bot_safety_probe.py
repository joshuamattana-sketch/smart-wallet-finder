"""
scripts/run_gold_bot_safety_probe.py
--------------------------------------
LM87A - Inspect the Gold Bot demo safety supervisor. READ-ONLY, OFFLINE: no MT5,
no orders, no HTTP. Reports the learning-modifier contract status, the safety
state file, and any active cooldown so you can see what the supervisor would
enforce before running the worker.

Run from repo root:
    python scripts/run_gold_bot_safety_probe.py
    python scripts/run_gold_bot_safety_probe.py --json
    python scripts/run_gold_bot_safety_probe.py --learning-modifiers-file data/gold_bot/learning/active_demo_modifiers.json
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

from services.gold_bot_demo_safety_supervisor import (  # noqa: E402
    DEFAULT_STATE_PATH,
    DemoSafetySupervisor,
    SupervisorConfig,
    _parse_iso,
)
from services.gold_bot_learning_modifiers import DEFAULT_ACTIVE_MODIFIERS_PATH  # noqa: E402


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="run_gold_bot_safety_probe",
        description="Inspect the demo safety supervisor (read-only, offline, no MT5).",
    )
    p.add_argument("--learning-modifiers-file", default=str(DEFAULT_ACTIVE_MODIFIERS_PATH),
                   dest="learning_modifiers_file")
    p.add_argument("--state-file", default=str(DEFAULT_STATE_PATH), dest="state_file")
    p.add_argument("--json", action="store_true", dest="json_output")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    now = datetime.now(timezone.utc)
    sup = DemoSafetySupervisor(SupervisorConfig(), state_path=args.state_file)

    learning = sup.evaluate_learning(args.learning_modifiers_file, enabled=True, now=now)
    state = sup.load_state()
    cooldown = state.get("cooldown_until")
    cooldown_active = bool(_parse_iso(cooldown) and now < _parse_iso(cooldown))
    state_exists = Path(args.state_file).exists()

    if args.json_output:
        print(json.dumps({
            "now": now.isoformat(),
            "learning_contract": learning.to_dict(),
            "state_file": args.state_file, "state_exists": state_exists,
            "state": state, "cooldown_until": cooldown, "cooldown_active": cooldown_active,
            "supervisor_config": sup.config.__dict__,
        }, indent=2, default=str))
        return 0

    print("=" * 70)
    print(" GOLD BOT DEMO SAFETY SUPERVISOR   PROBE   read-only, offline, no MT5")
    print("=" * 70)
    cfg = sup.config
    print(f" limits       : max-open {cfg.max_open_positions}  <={cfg.max_trades_per_hour}/h  "
          f"gap {cfg.min_seconds_between_trades}s  loss-streak {cfg.max_consecutive_losses}"
          f"->{cfg.cooldown_minutes_after_loss_streak}m  drawdown warn {cfg.warning_daily_loss_pct}%"
          f"/block {cfg.max_daily_loss_pct}%")
    print(" spread ceil  : balanced 35pt  scalp 25pt  (override --max-spread-points)")
    print("\n Learning modifier contract:")
    print(f"   file       : {args.learning_modifiers_file}")
    flag = "OK" if learning.allowed else "DISABLED"
    print(f"   status     : [{flag}] {learning.severity.upper()} - {learning.reason}")
    for vio in learning.details.get("violations", []):
        print(f"     violation- {vio}")
    if learning.allowed:
        print(f"   active     : {learning.details.get('active_count')} demo modifier(s), confidence-only")

    print("\n Safety state:")
    print(f"   file       : {args.state_file}  ({'exists' if state_exists else 'not created yet'})")
    print(f"   updated_at : {state.get('updated_at')}")
    print(f"   recent     : {len(state.get('recent_trades', []))} trade timestamp(s); "
          f"last {state.get('last_trade_at')}")
    print(f"   losses     : consecutive {state.get('consecutive_losses', 0)}")
    if cooldown_active:
        print(f"   COOLDOWN   : ACTIVE until {cooldown} (demo execution paused)")
    else:
        print(f"   cooldown   : none active ({cooldown or 'unset'})")

    print(f"\n generated state path : {Path(args.state_file).resolve()}")
    print(" Note: supervisor ALWAYS runs in the worker - there is no off switch. It can only "
          "block/downgrade; it never sends orders, never enables live trading, never touches MT5.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
