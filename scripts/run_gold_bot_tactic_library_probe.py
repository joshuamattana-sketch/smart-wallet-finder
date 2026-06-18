"""
scripts/run_gold_bot_tactic_library_probe.py
----------------------------------------------
LM98C - Inspect the Gold Bot tactic library (RESEARCH-ONLY). Loads + validates the
library, prints every tactic, and shows which are MAPPED to existing replay setup
tags vs research_only / not_implemented_yet. Writes nothing unless --write. Never
trades, no MT5, no orders, no network.

    python scripts/run_gold_bot_tactic_library_probe.py
    python scripts/run_gold_bot_tactic_library_probe.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from services.gold_bot_tactic_library import (  # noqa: E402
    DEFAULT_TACTICS_DIR,
    group_tactics,
    load_library,
    mapped_setup_tags,
)


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="run_gold_bot_tactic_library_probe",
        description="Inspect/validate the Gold Bot tactic library (research-only, offline).",
    )
    p.add_argument("--library", default=None, help="Path to a tactic library JSON (default sample/manual).")
    p.add_argument("--write", action="store_true",
                   help="Write a normalized snapshot to data/gold_bot/tactics/tactic_library.local.json (gitignored).")
    p.add_argument("--json", action="store_true", dest="json_output")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    tactics, meta, warnings = load_library(args.library)
    if not tactics:
        print("TACTIC LIBRARY: " + (warnings[0] if warnings else "no tactics found"), file=sys.stderr)
        return 1
    groups = group_tactics(tactics)
    mapped = mapped_setup_tags(tactics)

    if args.json_output:
        print(json.dumps({"meta": meta, "mapped_setup_tags": mapped,
                          "groups": {k: [t["id"] for t in v] for k, v in groups.items()},
                          "warnings": warnings}, indent=2, default=str))
        return 0

    print("=" * 70)
    print(f" GOLD BOT TACTIC LIBRARY   {meta.get('symbol')}  v{meta.get('version')}  "
          f"({meta.get('count')} tactics, research-only)")
    print("=" * 70)
    print(f" source: {meta.get('path')}")
    for w in warnings:
        print(f"   warning - {w}")

    print(f"\n MAPPED to replay setups ({len(groups['mapped'])}):")
    for t in groups["mapped"]:
        tags = ", ".join((t.get("replay_mapping") or {}).get("setup_tags") or [])
        print(f"   {t['id']:<24} -> setup {tags}")
    print(f"\n RESEARCH ONLY ({len(groups['research_only'])}):")
    for t in groups["research_only"]:
        print(f"   {t['id']:<24} -> {(t.get('replay_mapping') or {}).get('note', 'research only')}")
    print(f"\n NOT IMPLEMENTED YET ({len(groups['not_implemented_yet'])}):")
    for t in groups["not_implemented_yet"]:
        print(f"   {t['id']:<24} -> {(t.get('replay_mapping') or {}).get('note', 'no feature yet')}")

    if args.write:
        try:
            DEFAULT_TACTICS_DIR.mkdir(parents=True, exist_ok=True)
            snap = DEFAULT_TACTICS_DIR / "tactic_library.local.json"
            snap.write_text(json.dumps({"meta": meta, "tactics": tactics}, indent=2, default=str),
                            encoding="utf-8")
            print(f"\n wrote snapshot: {snap}  (gitignored)")
        except OSError as exc:
            print(f"   warning - snapshot not written: {exc}")

    print("\n Research-only tactic library. No tactic is active for demo/live execution.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
