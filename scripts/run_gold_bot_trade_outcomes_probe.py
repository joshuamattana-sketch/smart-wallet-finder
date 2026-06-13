"""
scripts/run_gold_bot_trade_outcomes_probe.py
----------------------------------------------
LM89A - Reconstruct Gold Bot DEMO trade outcomes from MT5 deal history. READ-ONLY
by default (prints, writes nothing); with --write it persists the outcome files +
appends learning-journal feedback events. SENDS NO ORDERS. Fail-closed if MT5 is
unavailable or the account is not a verified demo account.

Run from repo root (Windows, MT5 running on a demo account):
    python scripts/run_gold_bot_trade_outcomes_probe.py --symbol XAUUSD --magic 810810
    python scripts/run_gold_bot_trade_outcomes_probe.py --session-file data/gold_bot/sessions/session_latest.json --write
    python scripts/run_gold_bot_trade_outcomes_probe.py --from-time 2026-06-13T00:00:00 --to-time 2026-06-13T23:59:59 --json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from services.gold_bot_trade_outcomes import (  # noqa: E402
    DEFAULT_MAGIC,
    DEFAULT_OUTCOMES_DIR,
    DEFAULT_SYMBOL,
    append_outcomes_to_learning_journal,
    reconstruct_outcomes,
    summarize_outcomes,
    write_outcomes,
)


def _parse_iso(s: str) -> datetime:
    d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc)


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="run_gold_bot_trade_outcomes_probe",
        description="Reconstruct demo trade outcomes from MT5 history (read-only by default).",
    )
    p.add_argument("--symbol", default=DEFAULT_SYMBOL)
    p.add_argument("--magic", type=int, default=DEFAULT_MAGIC)
    p.add_argument("--from-time", default=None, dest="from_time", help="ISO UTC (optional).")
    p.add_argument("--to-time", default=None, dest="to_time", help="ISO UTC (optional).")
    p.add_argument("--session-file", default=None, dest="session_file",
                   help="Session report JSON; derive the time window from started_at/ended_at.")
    p.add_argument("--out-dir", default=str(DEFAULT_OUTCOMES_DIR), dest="out_dir")
    p.add_argument("--write", action="store_true",
                   help="Persist outcomes JSON/latest/events + append learning-journal feedback.")
    p.add_argument("--json", action="store_true", dest="json_output")
    return p.parse_args(argv)


def _resolve_window(args) -> tuple[datetime, datetime, str | None, list[str]]:
    warnings: list[str] = []
    session_id = None
    if args.session_file:
        try:
            data = json.loads(Path(args.session_file).read_text(encoding="utf-8"))
            session_id = data.get("session_id")
            frm = _parse_iso(data["started_at"]) - timedelta(minutes=5)
            to = _parse_iso(data["ended_at"]) + timedelta(minutes=5)
            return frm, to, session_id, warnings
        except (OSError, KeyError, ValueError) as exc:
            warnings.append(f"could not read session window from {args.session_file}: {exc}")
    if args.from_time and args.to_time:
        return _parse_iso(args.from_time), _parse_iso(args.to_time), session_id, warnings
    now = datetime.now(timezone.utc)
    return now - timedelta(days=7), now + timedelta(days=1), session_id, warnings


def main(argv=None) -> int:
    args = parse_args(argv)
    frm, to, session_id, warnings = _resolve_window(args)

    try:
        from services.connectors.mt5_demo_connector import Mt5DemoConnector, ProbeResult
        conn = Mt5DemoConnector()
        conn.connect()
        probe = ProbeResult()
        conn.read_account(probe)
        if not conn.demo_verified:
            print("TRADE OUTCOMES FAILED: account is not a verified DEMO account (fail closed).",
                  file=sys.stderr)
            return 1
        deals = conn.deal_history(frm, to)
        account = {"login": probe.account_login, "server": probe.account_server,
                   "demo": conn.demo_verified}
        try:
            conn.shutdown()
        except Exception:  # noqa: BLE001
            pass
    except Exception as exc:  # noqa: BLE001 - fail closed, never sends orders
        print(f"TRADE OUTCOMES FAILED: MT5 unavailable ({exc}). Read-only; no orders sent.",
              file=sys.stderr)
        return 1

    outcomes = reconstruct_outcomes(deals, symbol=args.symbol, magic=args.magic,
                                    session_id=session_id)
    summary = summarize_outcomes(outcomes)
    paths = {}
    journaled = 0
    if args.write:
        paths = write_outcomes(args.out_dir, outcomes, session_id=session_id)
        journaled = append_outcomes_to_learning_journal(outcomes)

    if args.json_output:
        print(json.dumps({"account": account, "window": [frm.isoformat(), to.isoformat()],
                          "deals_scanned": len(deals), "summary": summary,
                          "outcomes": [o.to_dict() for o in outcomes],
                          "written": {k: str(v) for k, v in paths.items()},
                          "journaled": journaled, "warnings": warnings + summary["warnings"]},
                         indent=2, default=str))
        return 0

    print("=" * 70)
    print(" GOLD BOT TRADE OUTCOMES   PROBE   read-only" + ("  +WRITE" if args.write else ""))
    print("=" * 70)
    print(f" account     : {account['login']} @ {account['server']}  demo {account['demo']}")
    print(f" filter      : symbol {args.symbol}  magic {args.magic}")
    print(f" window      : {frm.isoformat()} -> {to.isoformat()}")
    print(f" deals       : {len(deals)} scanned")
    for w in warnings:
        print(f"   warning - {w}")
    print(f"\n outcomes    : {summary['count']}  "
          f"W {summary['wins']} / L {summary['losses']} / BE {summary['breakeven']} / open {summary['open']}")
    print(f" realized PnL: {summary['realized_pnl']}")
    for o in outcomes:
        print(f"   {o.trade_id}  {o.side:<5} {o.outcome:<9} exit {o.exit_reason:<12} "
              f"pnl {o.pnl}  pts {o.pnl_points}  {o.entry_time} -> {o.exit_time}")
    for w in summary["warnings"]:
        print(f"   warning - {w}")
    if args.write:
        print(f"\n written     : {paths.get('named')}")
        print(f"               {paths.get('latest')}")
        print(f"               {paths.get('events')}   (+{journaled} learning_events.jsonl rows)")
    else:
        print("\n Read-only - nothing written. Use --write to persist outcomes + learning feedback.")
    print(" No orders sent. Demo-only. Safety/loss-streak state is updated by the session runner.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
