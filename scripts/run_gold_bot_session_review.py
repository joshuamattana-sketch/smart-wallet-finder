"""
scripts/run_gold_bot_session_review.py
----------------------------------------
LM90A - Build a local session review digest (Markdown + JSON) for the Gold Bot.
OFFLINE: joins the demo session report, trade outcomes, safety events, learning
events and learning-cycle summaries into one human-readable review. Never calls
MT5, never sends orders, no HTTP. Missing optional inputs degrade to warnings.

Run from repo root (after a demo session):
    python scripts/run_gold_bot_session_review.py --dry-run
    python scripts/run_gold_bot_session_review.py
    python scripts/run_gold_bot_session_review.py --session-file data/gold_bot/sessions/session_latest.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from services.gold_bot_session_review import (  # noqa: E402
    DEFAULT_LEARNING_DIR,
    DEFAULT_REVIEWS_DIR,
    DEFAULT_SAFETY_DIR,
    DEFAULT_SESSION_FILE,
    DEFAULT_TRADE_OUTCOMES_DIR,
    build_review,
    read_json,
    read_jsonl,
    render_markdown,
    write_review,
)


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="run_gold_bot_session_review",
        description="Build a local Gold Bot session review digest (offline, no MT5).",
    )
    p.add_argument("--session-file", default=str(DEFAULT_SESSION_FILE), dest="session_file")
    p.add_argument("--out-dir", default=str(DEFAULT_REVIEWS_DIR), dest="out_dir")
    p.add_argument("--learning-dir", default=str(DEFAULT_LEARNING_DIR), dest="learning_dir")
    p.add_argument("--safety-dir", default=str(DEFAULT_SAFETY_DIR), dest="safety_dir")
    p.add_argument("--trade-outcomes-dir", default=str(DEFAULT_TRADE_OUTCOMES_DIR),
                   dest="trade_outcomes_dir")
    p.add_argument("--json", action="store_true", dest="json_output")
    p.add_argument("--dry-run", action="store_true", dest="dry_run")
    return p.parse_args(argv)


def _latest_cycle_json(cycles_dir: Path) -> Path | None:
    if not cycles_dir.exists():
        return None
    files = [f for f in cycles_dir.glob("cycle_*.json")]
    return max(files, key=lambda f: f.stat().st_mtime) if files else None


def _gather(args) -> tuple[dict, dict, list[str]]:
    """Resolve + read every input. Returns (inputs, files_used, warnings)."""
    learning = Path(args.learning_dir)
    safety = Path(args.safety_dir)
    outcomes_dir = Path(args.trade_outcomes_dir)
    warnings: list[str] = []
    files_used: dict[str, str] = {}

    def track(name: str, path: Path, warn: str | None, *, optional: bool = True) -> None:
        files_used[name] = str(path) if path.exists() else f"(missing) {path}"
        if warn and optional:
            warnings.append(f"{name}: {warn}")

    report, w = read_json(args.session_file)
    track("session_report", Path(args.session_file), w, optional=False)

    # outcomes: prefer the file the session recorded, else outcomes_latest.json
    out_path = None
    if report and report.get("outcome_file"):
        out_path = Path(report["outcome_file"])
    if out_path is None or not out_path.exists():
        out_path = outcomes_dir / "outcomes_latest.json"
    outcomes_doc, w = read_json(out_path)
    track("trade_outcomes", out_path, w)

    safety_events, w1 = read_jsonl(safety / "safety_events.jsonl")
    track("safety_events", safety / "safety_events.jsonl", w1)
    safety_state, w2 = read_json(safety / "safety_state.json")
    track("safety_state", safety / "safety_state.json", w2)

    learning_events, w3 = read_jsonl(learning / "learning_events.jsonl")
    track("learning_events", learning / "learning_events.jsonl", w3)
    cycle_events, w4 = read_jsonl(learning / "cycles" / "cycle_events.jsonl")
    track("cycle_events", learning / "cycles" / "cycle_events.jsonl", w4)
    latest_cycle_path = _latest_cycle_json(learning / "cycles")
    latest_cycle = None
    if latest_cycle_path:
        latest_cycle, _ = read_json(latest_cycle_path)
        files_used["latest_cycle"] = str(latest_cycle_path)
    active_modifiers, _ = read_json(learning / "active_demo_modifiers.json")
    files_used["active_modifiers"] = str(learning / "active_demo_modifiers.json")
    scorecard, _ = read_json(learning / "scorecard_latest.json")
    files_used["scorecard"] = str(learning / "scorecard_latest.json")

    inputs = {
        "session_report": report, "outcomes_doc": outcomes_doc,
        "safety_events": safety_events, "safety_state": safety_state,
        "learning_events": learning_events, "cycle_events": cycle_events,
        "latest_cycle": latest_cycle, "active_modifiers": active_modifiers,
        "scorecard": scorecard,
    }
    return inputs, files_used, warnings


def main(argv=None) -> int:
    args = parse_args(argv)

    if not Path(args.session_file).exists():
        print(f"No session report found at {args.session_file}. "
              "Run run_gold_bot_demo_session.py first.", file=sys.stderr)
        return 1

    inputs, files_used, warnings = _gather(args)

    if args.dry_run:
        print("=" * 70)
        print(" GOLD BOT SESSION REVIEW   (DRY-RUN)   offline, read-only")
        print("=" * 70)
        print(" would read:")
        for name, path in files_used.items():
            print(f"   {name:<18} {path}")
        sid = (inputs["session_report"] or {}).get("session_id", "unknown")
        for stem in (f"session_review_{sid}", "session_review_latest"):
            print(f" would write: {Path(args.out_dir) / (stem + '.md')}")
            print(f"              {Path(args.out_dir) / (stem + '.json')}")
        print("\n Dry-run only - no files written. Never calls MT5, never sends orders, no HTTP.")
        return 0

    review = build_review(files_used=files_used, warnings=warnings, **inputs)
    markdown = render_markdown(review)
    paths = write_review(args.out_dir, review, markdown)

    if args.json_output:
        print(json.dumps({"review": review.to_dict(),
                          "paths": {k: str(v) for k, v in paths.items()}}, indent=2, default=str))
        return 0

    print(markdown)
    print(f"\n review written : {paths['markdown']}")
    print(f"                  {paths['json']}")
    print(f"                  {paths['markdown_latest']} / {paths['json_latest'].name}")
    print(" Offline digest only. No orders, no MT5, no HTTP. Demo-only reporting.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
