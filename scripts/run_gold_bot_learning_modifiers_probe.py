"""
scripts/run_gold_bot_learning_modifiers_probe.py
-------------------------------------------------
LM86B - Inspect / promote demo learning modifiers. READ-ONLY by default; with
--promote it writes active_demo_modifiers.json (DEMO-ONLY autonomy, no per-setup
approval). No MT5, no orders, no HTTP. Modifiers only nudge confidence and can
never enable live trading or bypass macro lockout / risk / kill switch.

Run from repo root (needs a scorecard preview first - see LM86A):
    python scripts/run_gold_bot_learning_modifiers_probe.py
    python scripts/run_gold_bot_learning_modifiers_probe.py --promote --min-samples 10
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from services.gold_bot_learning_modifiers import (  # noqa: E402
    ACTIVE,
    ACTIVE_FILE,
    DEFAULT_LEARNING_DIR,
    DEFAULT_MIN_SAMPLES,
    load_active_modifiers,
    modifiers_expired,
    promote,
)


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="run_gold_bot_learning_modifiers_probe",
        description="Inspect or promote demo learning modifiers (offline, demo-only).",
    )
    p.add_argument("--learning-dir", default=str(DEFAULT_LEARNING_DIR), dest="learning_dir")
    p.add_argument("--promote", action="store_true",
                   help="Write active_demo_modifiers.json + append modifier_events.jsonl.")
    p.add_argument("--min-samples", type=int, default=DEFAULT_MIN_SAMPLES, dest="min_samples")
    p.add_argument("--json", action="store_true", dest="json_output")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    payload, evaluated, warnings = promote(
        args.learning_dir, min_samples=args.min_samples, write=args.promote)

    if not evaluated and warnings:
        print("LEARNING MODIFIERS: " + warnings[0], file=sys.stderr)
        return 1

    active_path = Path(args.learning_dir) / ACTIVE_FILE
    active_now, active_warn = load_active_modifiers(active_path)
    expired, expires_at = modifiers_expired(active_path)
    if expired:
        active_warn = active_warn + [
            f"active demo modifiers EXPIRED at {expires_at} (stale) - re-run "
            "scripts/run_gold_bot_learning_cycle.py to refresh. (not auto-deleted)"]

    if args.json_output:
        print(json.dumps({"promoted": args.promote, "min_samples": args.min_samples,
                          "evaluated": {s: m.to_dict() for s, m in evaluated.items()},
                          "active_payload": payload, "expired": expired, "expires_at": expires_at,
                          "warnings": warnings + active_warn},
                         indent=2, default=str))
        return 0

    print("=" * 70)
    print(f" GOLD BOT LEARNING MODIFIERS   ({'PROMOTE' if args.promote else 'PREVIEW'})  demo-only")
    print("=" * 70)
    print(f" learning dir : {args.learning_dir}")
    print(f" min-samples  : {args.min_samples}   clamp +8/-12 (hard -20/+12)")
    for w in warnings + active_warn:
        print(f"   warning - {w}")

    print("\n Evaluated (candidate modifiers from the scorecard preview - NOT active unless promoted):")
    for setup, m in sorted(evaluated.items()):
        flag = "ACCEPT" if m.status == ACTIVE else m.status.upper()
        suffix = "" if args.promote else "  (preview only - not active unless promoted)"
        print(f"   [{flag:^18}] {setup:<22} mod {m.confidence_modifier:+d}  "
              f"samples {m.sample_count}  {m.reason}{suffix}")

    if not args.promote:
        if active_now:
            print("\n Currently ACTIVE demo modifiers (what decisions use, only with --use-learning-modifiers):")
            for s, e in sorted(active_now.items()):
                print(f"   {s:<22} {e['confidence_modifier']:+d}")
        else:
            print("\n No active_demo_modifiers.json yet - run with --promote to create it.")
        print("\n Preview only - candidates above are NOT active unless promoted "
              "(use --promote to activate, demo-only). Live trading stays locked.")
        return 0

    print(f"\n Promoted {payload['active_count']} active modifier(s) -> "
          f"{Path(args.learning_dir) / 'active_demo_modifiers.json'}")
    print(f" mode {payload['mode']}  safety {payload['safety']}  source {payload['source_scorecard']}")
    print(" NOTE: demo-only. Modifiers adjust confidence only - they never enable live trading, "
          "never bypass macro lockout / kill switch / risk gate / daily-loss, never change volume.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
