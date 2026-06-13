"""
scripts/run_gold_bot_command_gateway.py
-----------------------------------------
LM94A - Local-only command gateway CLI for the Lumora Gold Bot.

Runs ONE whitelisted Gold Bot action (preflight / offline cycle / guarded demo /
session review / discord preview / discord send) as a subprocess, with strict
caps and redacted run logs. DEFAULT = dry-run: it validates + prints the planned
command and runs NOTHING. No free-form shell, no live trading, no secrets read.

    # dry-run (default): validate + show the command, run nothing
    python scripts/run_gold_bot_command_gateway.py --action preflight

    # preview the guarded demo command (still no execution)
    python scripts/run_gold_bot_command_gateway.py --action daily_cycle_guarded_demo --confirm-guarded-demo

    # run the safe offline cycle and write a run log
    python scripts/run_gold_bot_command_gateway.py --action daily_cycle_offline --execute --include-real-trades --write-log

    # run a guarded demo cycle (every order still passes the safety supervisor + risk gate)
    python scripts/run_gold_bot_command_gateway.py --action daily_cycle_guarded_demo --execute --confirm-guarded-demo --duration-minutes 5 --max-trades 3 --risk-mode scalp --use-learning-modifiers --include-real-trades --write-log

    # send the Discord review INTENTIONALLY (needs the env webhook present)
    python scripts/run_gold_bot_command_gateway.py --action discord_send --execute --allow-discord-send --write-log
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from services.gold_bot_command_gateway import (  # noqa: E402
    ALLOWED_ACTIONS,
    DEFAULT_COMMANDS_DIR,
    DEFAULT_TIMEOUT,
    DURATION_DEFAULT,
    MAX_TRADES_DEFAULT,
    GatewayRequest,
    run_gateway,
)


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="run_gold_bot_command_gateway",
        description="Local-only whitelisted command gateway for the Gold Bot "
                    "(dry-run by default; no live trading, no arbitrary shell).",
    )
    p.add_argument("--action", required=True, choices=list(ALLOWED_ACTIONS),
                   help="The single whitelisted action to plan/run.")
    p.add_argument("--execute", action="store_true",
                   help="Actually run the subprocess. Default is dry-run (plan only).")
    p.add_argument("--dry-run", action="store_true", dest="dry_run",
                   help="Force dry-run (validate + show the command, run nothing).")
    p.add_argument("--duration-minutes", type=int, default=DURATION_DEFAULT,
                   dest="duration_minutes", help="Guarded demo only; cap 15.")
    p.add_argument("--max-trades", type=int, default=MAX_TRADES_DEFAULT,
                   dest="max_trades", help="Guarded demo only; cap 5.")
    p.add_argument("--risk-mode", default="scalp", dest="risk_mode",
                   help="Guarded demo only; allowed: safe, balanced, scalp.")
    p.add_argument("--use-learning-modifiers", action="store_true",
                   dest="use_learning_modifiers")
    p.add_argument("--include-real-trades", action="store_true", dest="include_real_trades")
    p.add_argument("--confirm-guarded-demo", action="store_true", dest="confirm_guarded_demo",
                   help="Required for daily_cycle_guarded_demo; otherwise blocked.")
    p.add_argument("--allow-discord-send", action="store_true", dest="allow_discord_send",
                   help="Required for discord_send (plus the env webhook present).")
    p.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT, dest="timeout_seconds")
    p.add_argument("--requested-by", default="local", dest="requested_by")
    p.add_argument("--write-log", action="store_true", dest="write_log",
                   help="Write command_<ts>.json/.jsonl + command_latest.* (gitignored).")
    p.add_argument("--out-dir", default=str(DEFAULT_COMMANDS_DIR), dest="out_dir")
    p.add_argument("--json", action="store_true", dest="json_output")
    return p.parse_args(argv)


def _exit_code(status: str) -> int:
    return {"planned": 0, "success": 0, "failed": 1, "blocked": 2}.get(status, 1)


def main(argv=None) -> int:
    args = parse_args(argv)

    if args.execute and args.dry_run:
        print("error: pass either --execute OR --dry-run, not both.", file=sys.stderr)
        return 2

    req = GatewayRequest(
        action=args.action,
        duration_minutes=args.duration_minutes,
        max_trades=args.max_trades,
        risk_mode=args.risk_mode,
        use_learning_modifiers=args.use_learning_modifiers,
        include_real_trades=args.include_real_trades,
        allow_discord_send=args.allow_discord_send,
        confirm_guarded_demo=args.confirm_guarded_demo,
        dry_run=not args.execute,          # execute wins; default is dry-run
        timeout_seconds=args.timeout_seconds,
        requested_by=args.requested_by,
        source="cli",
    )
    result = run_gateway(req, out_dir=Path(args.out_dir), write_log=args.write_log)

    if args.json_output:
        print(json.dumps(result.to_dict(), indent=2, default=str))
        return _exit_code(result.status)

    print("=" * 74)
    print(" GOLD BOT COMMAND GATEWAY   local-only, whitelisted, no arbitrary shell")
    print("=" * 74)
    print(f" request  : {result.request_id}")
    print(f" action   : {result.action}")
    print(f" accepted : {result.accepted}   status: {result.status.upper()}")
    if result.reason:
        print(f" reason   : {result.reason}")
    for w in result.warnings:
        print(f"   warning - {w}")
    if result.command:
        print(f" command  : {result.command}")

    if result.status == "blocked":
        print("\n BLOCKED - nothing executed. Fix the reason above and retry.")
    elif result.status == "planned":
        print("\n DRY-RUN - nothing executed, no demo trades, no Discord, no live."
              f"{'' if args.write_log else ' (use --write-log to log the plan)'}")
        print(" Add --execute to run this exact command through the existing safe script.")
    else:
        print(f"\n exit code: {result.exit_code}")
        if result.stdout_tail:
            print("\n --- stdout (tail, redacted) ---")
            print(result.stdout_tail)
        if result.stderr_tail:
            print("\n --- stderr (tail, redacted) ---", file=sys.stderr)
            print(result.stderr_tail, file=sys.stderr)
        if result.generated_files:
            print(f"\n run log  : {result.generated_files[0]}")
        print(f" redactions applied to captured output: {result.redactions_applied}")

    print("\n Local-only gateway. No live trading, no arbitrary shell, no webhook value "
          "read/printed. Demo-only, every order still passes the safety supervisor + risk gate.")
    return _exit_code(result.status)


if __name__ == "__main__":
    raise SystemExit(main())
