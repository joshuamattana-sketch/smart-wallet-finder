"""
scripts/run_local_status_check.py
----------------------------------
LM59 — Local CLI that runs end-to-end status checks and prints a
beginner-friendly summary. NO UI, NO API, NO DB, NO network.

Run:
    python scripts/run_local_status_check.py
    python scripts/run_local_status_check.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from services.local_end_to_end_status import run_local_end_to_end_status  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="run_local_status_check",
        description="Run local end-to-end status checks.",
    )
    parser.add_argument("--json", action="store_true", dest="json_output",
                        help="Print raw JSON output instead of human summary.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = run_local_end_to_end_status()

    if args.json_output:
        print(json.dumps(result, indent=2, default=str))
    else:
        status = result["status"].upper()
        summary = result["summary"]
        print(f"Status: {status}  ({summary['ok']}/{summary['total']} checks passed)")
        print()
        for check in result["checks"]:
            mark = "OK" if check["ok"] else "FAIL"
            line = f"  [{mark:4s}] {check['name']}"
            if check["ok"] and check["details"]:
                line += f"  — {check['details']}"
            elif not check["ok"] and check["error"]:
                line += f"  — {check['error']}"
            print(line)
        print()
        if result["status"] == "ready":
            print("All checks passed. Local pipeline is ready.")
        else:
            print(f"{summary['failed']} check(s) failed. See errors above.")

    return 0 if result["status"] == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
