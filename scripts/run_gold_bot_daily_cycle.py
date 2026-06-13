"""
scripts/run_gold_bot_daily_cycle.py
-------------------------------------
LM92A - Local offline orchestrator for the Gold Bot demo-learning-review loop.

Chains the existing safe scripts (demo session -> outcome sync -> learning cycle
-> session review -> discord preview) into one repeatable command. It adds NO
trading logic. DEFAULT = plan/dry-run: prints the planned steps and runs NOTHING.

    python scripts/run_gold_bot_daily_cycle.py                         # plan only
    python scripts/run_gold_bot_daily_cycle.py --execute --skip-session --include-real-trades
    python scripts/run_gold_bot_daily_cycle.py --execute --confirm-demo-session --duration-minutes 5 --max-trades 3 --risk-mode scalp --use-learning-modifiers --include-real-trades

Trading happens ONLY with BOTH --execute AND --confirm-demo-session (and even then
the real session runner + safety supervisor + risk gate still gate every order).
Discord sends ONLY with --send-discord. No webhook value is ever read or printed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from services.gold_bot_scheduled_runner import (  # noqa: E402
    DEFAULT_RUNS_DIR,
    CycleConfig,
    build_plan,
    redact,
    run_cycle,
)


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="run_gold_bot_daily_cycle",
        description="Sequence the existing Gold Bot demo-learning-review scripts (plan by default).",
    )
    p.add_argument("--execute", action="store_true",
                   help="Actually run the safe offline steps (still no demo trades without --confirm-demo-session).")
    p.add_argument("--confirm-demo-session", action="store_true", dest="confirm_demo_session",
                   help="Allow a guarded demo session (still passes through the safety supervisor).")
    p.add_argument("--duration-minutes", type=float, default=5.0, dest="duration_minutes")
    p.add_argument("--max-trades", type=int, default=3, dest="max_trades")
    p.add_argument("--risk-mode", default="scalp", dest="risk_mode")
    p.add_argument("--use-learning-modifiers", action="store_true", dest="use_learning_modifiers")
    p.add_argument("--include-real-trades", action="store_true", dest="include_real_trades")
    p.add_argument("--real-trade-weight", type=float, default=2.0, dest="real_trade_weight")
    p.add_argument("--min-real-trades", type=int, default=5, dest="min_real_trades")
    p.add_argument("--send-discord", action="store_true", dest="send_discord",
                   help="Send the review to Discord (needs LUMORA_GOLD_DISCORD_WEBHOOK_URL). Default: preview only.")
    p.add_argument("--skip-session", action="store_true", dest="skip_session")
    p.add_argument("--skip-outcomes", action="store_true", dest="skip_outcomes")
    p.add_argument("--skip-learning-cycle", action="store_true", dest="skip_learning_cycle")
    p.add_argument("--skip-review", action="store_true", dest="skip_review")
    p.add_argument("--skip-discord-preview", action="store_true", dest="skip_discord_preview")
    p.add_argument("--continue-on-error", action="store_true", dest="continue_on_error")
    p.add_argument("--dry-run-log", action="store_true", dest="dry_run_log",
                   help="Write a run log even in plan mode.")
    # learning-cycle overrides
    p.add_argument("--cycle-timeframe", default="M1", dest="cycle_timeframe")
    p.add_argument("--cycle-risk-mode", default="balanced", dest="cycle_risk_mode")
    p.add_argument("--cycle-max-bars", type=int, default=500, dest="cycle_max_bars")
    p.add_argument("--cycle-horizon", type=int, default=15, dest="cycle_horizon")
    p.add_argument("--cycle-min-samples", type=int, default=10, dest="cycle_min_samples")
    p.add_argument("--out-dir", default=str(DEFAULT_RUNS_DIR), dest="out_dir")
    p.add_argument("--json", action="store_true", dest="json_output")
    return p.parse_args(argv)


def _cfg(args) -> CycleConfig:
    return CycleConfig(
        execute=args.execute, confirm_demo_session=args.confirm_demo_session,
        duration_minutes=args.duration_minutes, max_trades=args.max_trades, risk_mode=args.risk_mode,
        use_learning_modifiers=args.use_learning_modifiers,
        include_real_trades=args.include_real_trades, real_trade_weight=args.real_trade_weight,
        min_real_trades=args.min_real_trades, send_discord=args.send_discord,
        skip_session=args.skip_session, skip_outcomes=args.skip_outcomes,
        skip_learning_cycle=args.skip_learning_cycle, skip_review=args.skip_review,
        skip_discord_preview=args.skip_discord_preview, continue_on_error=args.continue_on_error,
        dry_run_log=args.dry_run_log, cycle_timeframe=args.cycle_timeframe,
        cycle_risk_mode=args.cycle_risk_mode, cycle_max_bars=args.cycle_max_bars,
        cycle_horizon=args.cycle_horizon, cycle_min_samples=args.cycle_min_samples,
    )


def _fmt_cmd(cmd) -> str:
    if not cmd:
        return "(internal)"
    parts = []
    for c in cmd:
        if c == sys.executable or Path(c).name.lower().startswith("python"):
            parts.append("python")
        elif c.endswith(".py"):
            parts.append(Path(c).name)
        else:
            parts.append(c)
    return redact(" ".join(parts))


def main(argv=None) -> int:
    args = parse_args(argv)
    cfg = _cfg(args)
    run = run_cycle(cfg, out_dir=Path(args.out_dir))

    if args.json_output:
        print(json.dumps(run.to_dict(), indent=2, default=str))
        return 0 if run.overall_status in ("planned", "success", "partial") else 1

    mode = "PLAN (dry-run)" if not cfg.execute else f"EXECUTE [{run.overall_status.upper()}]"
    print("=" * 74)
    print(f" GOLD BOT DAILY CYCLE   ({mode})   offline orchestrator, demo-only")
    print("=" * 74)
    print(f" run id   : {run.run_id}")
    print(f" trading  : {'ARMED (demo session + safety supervisor)' if (cfg.execute and cfg.confirm_demo_session) else 'OFF (no demo trades)'}")
    print(f" discord  : {'SEND' if cfg.send_discord else 'preview only'}")
    for w in run.warnings:
        print(f"   warning - {w}")

    print("\n steps:")
    for s in run.steps:
        tag = {"planned": "PLAN", "skipped": "SKIP", "success": " OK ", "failed": "FAIL"}.get(
            s["status"], s["status"])
        print(f"   [{tag}] {s['name']:<16} {_fmt_cmd(s.get('command'))}")
        if s.get("reason"):
            print(f"          - {redact(str(s['reason']))}")

    if not cfg.execute:
        print("\n PLAN ONLY - nothing executed, no demo trades, no Discord, no files written"
              f"{' (use --dry-run-log to log the plan)' if not cfg.dry_run_log else ''}.")
        print(" To run safe offline steps: --execute   (demo trades also need --confirm-demo-session).")
    else:
        print(f"\n overall  : {run.overall_status.upper()}")
        if run.run_json_path:
            print(f" run log  : {run.run_json_path}")
            print(f"            {run.run_jsonl_path}")
        print(" Demo-only: every order still passed through the session runner + safety supervisor "
              "+ risk gate. No webhook value was read or logged.")
    return 0 if run.overall_status in ("planned", "success", "partial") else 1


if __name__ == "__main__":
    raise SystemExit(main())
