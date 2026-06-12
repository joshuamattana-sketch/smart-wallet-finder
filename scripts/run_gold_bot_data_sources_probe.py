"""
scripts/run_gold_bot_data_sources_probe.py
--------------------------------------------
LM83A (part 2) — Data source status overview (READ-ONLY, no MT5, no HTTP).

Prints a grouped snapshot of every Gold Bot data source: the REAL local + manual
economic calendars (with live file status) and every PLACEHOLDER provider
(Finnhub / TradingEconomics / MT5 export / GDELT / RSS / FRED / yfinance / MT5
XAUUSD + DXY + yields + VIX history). Makes NO external calls.

Run from repo root:
    python scripts/run_gold_bot_data_sources_probe.py
    python scripts/run_gold_bot_data_sources_probe.py --calendar-file data/gold_bot/economic_calendar.sample.json --json
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

from services.gold_bot_data_sources import (  # noqa: E402
    DEFAULT_MANUAL_CALENDAR,
    DEFAULT_SAMPLE_CALENDAR,
    build_data_source_overview,
    group_by_category,
)

_CATEGORY_TITLES = {
    "economic_calendar": "Economic calendar",
    "historical_market": "Historical market",
    "macro_market": "Macro market",
    "news": "News",
    "manual": "Manual",
}


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="run_gold_bot_data_sources_probe",
        description="Gold Bot data source status overview (read-only, no HTTP).",
    )
    p.add_argument("--calendar-file", default=DEFAULT_SAMPLE_CALENDAR, dest="calendar_file")
    p.add_argument("--manual-file", default=DEFAULT_MANUAL_CALENDAR, dest="manual_file")
    p.add_argument("--json", action="store_true", dest="json_output")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    now = datetime.now(timezone.utc)
    statuses = build_data_source_overview(
        calendar_file=args.calendar_file, manual_file=args.manual_file, now=now)

    if args.json_output:
        print(json.dumps({"now": now.isoformat(),
                          "sources": [s.to_dict() for s in statuses]}, indent=2, default=str))
        return 0

    print("=" * 78)
    print(" GOLD BOT DATA SOURCES   (read-only - no external HTTP calls)")
    print("=" * 78)
    grouped = group_by_category(statuses)
    for category, title in _CATEGORY_TITLES.items():
        rows = grouped.get(category)
        if not rows:
            continue
        print(f"\n {title}:")
        for s in rows:
            tag = {"active": "ACTIVE", "fallback": "FALLBACK", "placeholder": "placeholder",
                   "missing": "MISSING", "error": "ERROR"}.get(s.status, s.status)
            print(f"   [{tag:^11}] {s.name:<22} {s.freshness:<6} {s.message}")
            for w in s.warnings:
                print(f"                  warning - {w}")

    active = [s for s in statuses if s.status in ("active", "fallback")]
    print("\n Summary:")
    print(f"   real sources : {', '.join(s.name + '(' + s.status + ')' for s in active) or 'none'}")
    print(f"   placeholders : {sum(1 for s in statuses if s.status == 'placeholder')} "
          "(no HTTP, status-only until wired)")
    print("   manual_json  : temporary free fallback only - replace with automatic provider later.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
