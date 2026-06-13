"""
scripts/run_gold_bot_first_run_preflight.py
---------------------------------------------
LM92B - First market-open demo run PREFLIGHT (READ-ONLY GO / NO-GO).

Runs the existing read-only probes (MT5 connector probe, safety probe, daily-cycle
PLAN), checks local artifacts + kill switch, and prints a clear checklist plus the
exact next command. PLACES NO ORDERS, sends NO Discord, prints NO secrets.

    python scripts/run_gold_bot_first_run_preflight.py                 # market-open preflight
    python scripts/run_gold_bot_first_run_preflight.py --skip-mt5 --skip-safety   # weekend/offline prep
    python scripts/run_gold_bot_first_run_preflight.py --json --write
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from services.gold_bot_first_run_preflight import (  # noqa: E402
    DEFAULT_PREFLIGHT_DIR,
    PreflightConfig,
    run_preflight,
)


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="run_gold_bot_first_run_preflight",
        description="Read-only GO/NO-GO preflight for the first market-open demo run.",
    )
    p.add_argument("--skip-mt5", action="store_true", dest="skip_mt5",
                   help="Skip the MT5 connector probe (weekend/offline prep).")
    p.add_argument("--skip-safety", action="store_true", dest="skip_safety")
    p.add_argument("--duration-minutes", type=float, default=5.0, dest="duration_minutes")
    p.add_argument("--max-trades", type=int, default=3, dest="max_trades")
    p.add_argument("--risk-mode", default="scalp", dest="risk_mode")
    p.add_argument("--use-learning-modifiers", action="store_true", dest="use_learning_modifiers")
    p.add_argument("--include-real-trades", action="store_true", dest="include_real_trades")
    p.add_argument("--send-discord", action="store_true", dest="send_discord",
                   help="Include -SendDiscord in the recommended GO command (still needs the env webhook).")
    p.add_argument("--check-discord-env", action="store_true", dest="check_discord_env",
                   help="Report whether the webhook env is set (presence only; value never read).")
    p.add_argument("--write", action="store_true", help="Write preflight_<ts>.json + preflight_latest.json.")
    p.add_argument("--timeout-seconds", type=int, default=120, dest="timeout_seconds")
    p.add_argument("--out-dir", default=str(DEFAULT_PREFLIGHT_DIR), dest="out_dir")
    p.add_argument("--json", action="store_true", dest="json_output")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    cfg = PreflightConfig(
        skip_mt5=args.skip_mt5, skip_safety=args.skip_safety,
        duration_minutes=args.duration_minutes, max_trades=args.max_trades, risk_mode=args.risk_mode,
        use_learning_modifiers=args.use_learning_modifiers,
        include_real_trades=args.include_real_trades, send_discord=args.send_discord,
        check_discord_env=args.check_discord_env, write=args.write,
        timeout_seconds=args.timeout_seconds,
    )
    pf = run_preflight(cfg, out_dir=Path(args.out_dir))

    if args.json_output:
        print(json.dumps(pf.to_dict(), indent=2, default=str))
        return 0 if pf.go else 1

    print("=" * 70)
    print(" GOLD BOT FIRST MARKET-OPEN PREFLIGHT   read-only, no orders")
    print("=" * 70)
    print(f" Overall: {pf.overall}")
    print("\n Checks:")
    for c in pf.checks:
        print(f"   [{c['status']:^4}] {c['name']:<18} {c['detail']}")

    if pf.go:
        print("\n GO - when the market is open, run the first guarded demo cycle:")
        print(f"   {pf.go_command}")
        print(" (demo-only; every order still passes the session runner + safety supervisor + risk gate)")
    else:
        print("\n NO-GO - do not run yet. Reasons:")
        for r in pf.reasons:
            print(f"   - {r}")
        print("\n Safe read-only commands to investigate:")
        for cmd in pf.troubleshooting:
            print(f"   {cmd}")
    if pf.preflight_path:
        print(f"\n written: {pf.preflight_path}")
    print("\n Read-only preflight. No orders placed, no Discord sent, no secrets printed. Demo-only, never live.")
    return 0 if pf.go else 1


if __name__ == "__main__":
    raise SystemExit(main())
