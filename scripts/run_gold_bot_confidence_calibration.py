"""
scripts/run_gold_bot_confidence_calibration.py
-----------------------------------------------
LM102A - Confidence calibration probe (RESEARCH / PREVIEW-ONLY).

Loads recorded demo trade outcomes (learning_events.jsonl), buckets them by
engine confidence, and reports win-rate + expectancy per bucket plus a verdict:
is confidence PREDICTIVE, FLAT, or INVERTED? Read-only by default; --write
persists a preview report. SENDS NO ORDERS, no MT5, no network. The suggested
confidence remap is PREVIEW ONLY and never wired into the trader.

    python scripts/run_gold_bot_confidence_calibration.py
    python scripts/run_gold_bot_confidence_calibration.py --min-samples 20 --write
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

from services.gold_bot_confidence_calibration import (  # noqa: E402
    DEFAULT_MIN_SAMPLES,
    calibrate,
)
from services.gold_bot_learning_journal import (  # noqa: E402
    DEFAULT_LEARNING_DIR,
    load_demo_trade_outcomes,
)

DEFAULT_OUT_DIR = _REPO_ROOT / "data" / "gold_bot" / "calibration"


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="run_gold_bot_confidence_calibration",
        description="Confidence calibration from recorded demo outcomes (read-only by default).",
    )
    p.add_argument("--learning-dir", default=str(DEFAULT_LEARNING_DIR), dest="learning_dir")
    p.add_argument("--events-file", default=None, dest="events_file",
                   help="Explicit learning_events.jsonl (default: <learning-dir>/learning_events.jsonl).")
    p.add_argument("--min-samples", type=int, default=DEFAULT_MIN_SAMPLES, dest="min_samples")
    p.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR), dest="out_dir")
    p.add_argument("--write", action="store_true", help="Persist the preview report JSON.")
    p.add_argument("--json", action="store_true", dest="json_output")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    outcomes, warnings, dups = load_demo_trade_outcomes(
        events_file=args.events_file, learning_dir=args.learning_dir)
    report = calibrate(outcomes, min_samples=args.min_samples)
    report["source_outcomes_loaded"] = len(outcomes)
    report["duplicates_ignored"] = dups
    report["load_warnings"] = warnings

    written = None
    if args.write:
        d = Path(args.out_dir)
        d.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc)
        payload = {"generated_at": now.isoformat(), "mode": "confidence_calibration",
                   "safety": "preview_only", **report}
        blob = json.dumps(payload, indent=2, default=str)
        (d / f"calibration_{now.strftime('%Y%m%d_%H%M%S')}.json").write_text(blob, encoding="utf-8")
        latest = d / "calibration_latest.json"
        latest.write_text(blob, encoding="utf-8")
        written = latest

    if args.json_output:
        print(json.dumps({**report, "written": str(written) if written else None}, indent=2, default=str))
        return 0

    print("=" * 72)
    print(" GOLD BOT CONFIDENCE CALIBRATION   research / PREVIEW-ONLY" + ("  +WRITE" if args.write else ""))
    print("=" * 72)
    print(f" outcomes loaded : {len(outcomes)}  (dups ignored {dups})")
    for w in warnings + report["warnings"]:
        print(f"   warning - {w}")
    print(f" verdict         : {report['verdict'].upper()}   "
          f"(total {report['total_outcomes']}, min-samples {args.min_samples})")
    print(f"\n {'bucket':>8} {'n':>5} {'win':>4} {'loss':>5} {'winrate':>8} {'avg_pnl':>9} {'avg_pts':>8}")
    for b in report["buckets"]:
        wr = f"{b['winrate']:.3f}" if b["winrate"] is not None else "   -  "
        ap = f"{b['avg_pnl']:.2f}" if b["avg_pnl"] is not None else "  -  "
        pt = f"{b['avg_pnl_points']:.1f}" if b["avg_pnl_points"] is not None else "  -  "
        print(f" {b['bucket']:>8} {b['count']:>5} {b['wins']:>4} {b['losses']:>5} {wr:>8} {ap:>9} {pt:>8}")
    print(f"\n suggested remap (PREVIEW, not wired): {report['suggested_confidence_map_preview']}")
    if report["verdict"] == "inverted":
        print(" NOTE: INVERTED - higher confidence currently wins LESS. Confidence is mis-signed; "
              "do not size up on it until fixed.")
    elif report["verdict"] == "insufficient":
        print(" NOTE: not enough samples per bucket yet - run the worker with --sync-outcomes-every "
              "to record more demo trades first.")
    if written:
        print(f"\n written         : {written}")
    else:
        print("\n Read-only - nothing written. Use --write to persist the preview report.")
    print(" PREVIEW ONLY - the suggested remap is NOT used by the trader.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
