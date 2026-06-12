"""
scripts/run_gold_bot_calendar_probe.py
----------------------------------------
LM83A — Economic calendar probe (READ-ONLY, no MT5, no orders).

Loads a local/sample economic calendar JSON, normalizes + filters events and
prints the upcoming high-impact picture for XAUUSD: the next high-impact USD
event, everything inside the window, minutes-to-event and the resulting macro
event-risk state (clear / watch / lockout / post_event).

Run from repo root:
    python scripts/run_gold_bot_calendar_probe.py --calendar-file data/gold_bot/economic_calendar.sample.json --window-hours 48 --currency USD
    python scripts/run_gold_bot_calendar_probe.py --calendar-file data/gold_bot/economic_calendar.sample.json --impact high --json
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

from services.gold_bot_economic_calendar import (  # noqa: E402
    filter_events,
    next_high_impact,
    resolve_calendar_provider,
)
from services.gold_bot_macro_context import classify_event_state  # noqa: E402


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="run_gold_bot_calendar_probe",
        description="Economic calendar probe (local JSON; read-only).",
    )
    p.add_argument("--calendar-file", default="data/gold_bot/economic_calendar.sample.json",
                   dest="calendar_file")
    p.add_argument("--window-hours", type=float, default=48.0, dest="window_hours")
    p.add_argument("--currency", default=None, help="Filter by currency (e.g. USD). Omit for all.")
    p.add_argument("--impact", choices=["low", "medium", "high"], default=None)
    p.add_argument("--json", action="store_true", dest="json_output")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    now = datetime.now(timezone.utc)
    provider = resolve_calendar_provider(args.calendar_file)
    all_events, source, warnings = provider.fetch(now=now)
    pstatus = provider.status(now)
    windowed = filter_events(all_events, now=now, window_hours=args.window_hours,
                             currency=args.currency, impact=args.impact)
    nxt = next_high_impact(all_events, now=now, currency=args.currency or "USD")

    out: dict = {
        "source_mode": source,
        "provider_status": pstatus.to_dict(),
        "calendar_file": args.calendar_file,
        "now": now.isoformat(),
        "window_hours": args.window_hours,
        "currency_filter": args.currency,
        "impact_filter": args.impact,
        "events_loaded": len(all_events),
        "events_in_window": len(windowed),
        "warnings": warnings,
        "events": [e.to_dict() for e in windowed],
    }

    if not args.json_output:
        print("=" * 64)
        print(" GOLD BOT ECONOMIC CALENDAR PROBE   (read-only)")
        print("=" * 64)
        print(f" source      : {source}")
        print(f" provider    : {pstatus.name} [{pstatus.status}] freshness {pstatus.freshness}")
        print(f" file        : {args.calendar_file}")
        print(f" now (UTC)   : {now.isoformat()}")
        print(f" window      : next {args.window_hours:g}h   "
              f"currency {args.currency or 'ALL'}   impact {args.impact or 'ALL'}")
        print(f" loaded      : {len(all_events)} events   in-window {len(windowed)}")
        for w in warnings:
            print(f"   warning - {w}")

        if nxt is not None:
            mins = int(round(nxt.minutes_until(now)))
            state, _ = classify_event_state(nxt.impact, nxt.currency, mins)
            print(f"\n Next high-impact {args.currency or 'USD'} event:")
            print(f"   {nxt.title} [{nxt.event_type}] {nxt.currency} {nxt.impact}")
            print(f"   in {mins}m  ({nxt.scheduled_at.isoformat()})   state: {state}"
                  f"{'  *gold-major*' if nxt.is_gold_major() else ''}")
        else:
            print(f"\n Next high-impact {args.currency or 'USD'} event: none in calendar.")

        print("\n Events in window:")
        if not windowed:
            print("   (none)")
        for e in windowed:
            mins = int(round(e.minutes_until(now)))
            state, _ = classify_event_state(e.impact, e.currency, mins)
            when = f"in {mins}m" if mins >= 0 else f"{-mins}m ago"
            print(f"   {when:>9}  {e.currency} {e.impact:<6} {e.event_type:<22} {e.title}"
                  f"  [{state}]")
    else:
        print(json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
