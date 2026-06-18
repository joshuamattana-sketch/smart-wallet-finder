"""
scripts/run_gold_bot_inverse_replay_test.py
---------------------------------------------
LM98C - Inverse replay test (RESEARCH-ONLY, OFFLINE). Compares ORIGINAL vs INVERSE
(LONG<->SHORT) replay results per horizon / timeframe / mapped tactic, surfaces
h15-vs-h30 differences, and writes a PREVIEW-ONLY demo whitelist/blacklist. No MT5,
no orders, no demo/live execution, no network.

    python scripts/run_gold_bot_inverse_replay_test.py
    python scripts/run_gold_bot_inverse_replay_test.py --horizons 30 --timeframes M1,M5 --min-samples 20
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from services.gold_bot_inverse_replay_test import (  # noqa: E402
    DEFAULT_TACTIC_TESTS_DIR,
    InverseConfig,
    run_inverse_test,
)
from services.gold_bot_replay_engine import DEFAULT_REPLAY_DIR  # noqa: E402


def _csv(s: str) -> tuple[str, ...]:
    return tuple(x.strip() for x in str(s).split(",") if x.strip())


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="run_gold_bot_inverse_replay_test",
        description="Compare original vs inverse replay results per tactic/horizon (offline research).",
    )
    p.add_argument("--replay-dir", default=str(DEFAULT_REPLAY_DIR), dest="replay_dir")
    p.add_argument("--timeframes", default="M1,M5")
    p.add_argument("--horizons", default="15,30")
    p.add_argument("--min-samples", type=int, default=20, dest="min_samples")
    p.add_argument("--library", default=None, help="Tactic library JSON (default sample/manual).")
    p.add_argument("--out-dir", default=str(DEFAULT_TACTIC_TESTS_DIR), dest="out_dir")
    p.add_argument("--json", action="store_true", dest="json_output")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    cfg = InverseConfig(
        timeframes=_csv(args.timeframes),
        horizons=tuple(int(h) for h in _csv(args.horizons)),
        min_samples=args.min_samples, library_path=args.library)

    result = run_inverse_test(cfg, replay_dir=Path(args.replay_dir), out_dir=Path(args.out_dir))

    if not result.get("ok"):
        print("INVERSE TEST: " + result.get("error", "failed"), file=sys.stderr)
        for w in result.get("warnings", []):
            print(f"   warning - {w}", file=sys.stderr)
        return 1

    if args.json_output:
        print(json.dumps(result, indent=2, default=str))
        return 0

    paths = result.get("paths") or {}
    if paths.get("latest_md") and Path(paths["latest_md"]).exists():
        print(Path(paths["latest_md"]).read_text(encoding="utf-8"))
    print(f"\n report : {paths.get('latest_md')}")
    print(f" json   : {paths.get('latest_json')}")
    print(f" preview: {paths.get('whitelist_preview')}  (NOT used by demo execution)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
