"""
scripts/run_mt5_demo_connector_probe.py
-----------------------------------------
LM75A — Read-only MetaTrader 5 demo connector probe.

Connects to a *running, logged-in* MT5 terminal and reads demo account +
XAUUSD data. SENDS NO ORDERS. Fails closed on a real/live account.

Run from repo root (Windows, with MT5 running):
    python scripts/run_mt5_demo_connector_probe.py
    python scripts/run_mt5_demo_connector_probe.py --bars 50
    python scripts/run_mt5_demo_connector_probe.py --symbol XAUUSD --timeframe M5 --bars 100
    python scripts/run_mt5_demo_connector_probe.py --json

Requires the MetaTrader5 package (Windows only):
    pip install MetaTrader5
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from services.connectors.mt5_demo_connector import (  # noqa: E402
    Mt5ConnectorError,
    Mt5DemoConnector,
    ProbeResult,
    run_probe,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="run_mt5_demo_connector_probe",
        description="Read-only MT5 demo connector probe (no orders sent).",
    )
    parser.add_argument("--symbol", default=None,
                        help="Gold symbol to use. Omit to auto-discover (XAUUSD/GOLD/...).")
    parser.add_argument("--timeframe", default="M1",
                        help="Candle timeframe: M1 M5 M15 M30 H1 H4 D1 (default M1).")
    parser.add_argument("--bars", type=int, default=100,
                        help="Number of recent candles to read (default 100).")
    parser.add_argument("--json", action="store_true", dest="json_output",
                        help="Print a compact JSON summary instead of human output.")
    return parser.parse_args(argv)


def _fmt(v: object) -> str:
    return "—" if v is None else str(v)


def print_human(result: ProbeResult) -> None:
    r = result
    print("=" * 60)
    print(" MT5 DEMO CONNECTOR PROBE  —  READ ONLY - NO ORDERS SENT")
    print("=" * 60)
    print(f" Connection         : {'connected' if r.connected else 'not connected'}")

    print("\n Account")
    print(f"   Login            : {_fmt(r.account_login)}")
    print(f"   Server           : {_fmt(r.account_server)}")
    print(f"   Name             : {_fmt(r.account_name)}")
    print(f"   Currency         : {_fmt(r.account_currency)}")
    demo_str = (
        "DEMO" if r.is_demo
        else "non-real" if r.trade_mode_raw == 1
        else "UNKNOWN" if r.is_demo is None
        else "REAL"
    )
    print(f"   Trade mode       : {_fmt(r.trade_mode_label)} ({_fmt(r.trade_mode_raw)}) → {demo_str}")
    print(f"   Balance          : {_fmt(r.balance)}")
    print(f"   Equity           : {_fmt(r.equity)}")
    print(f"   Margin           : {_fmt(r.margin)}")
    print(f"   Free margin      : {_fmt(r.margin_free)}")

    print("\n Symbol")
    print(f"   Selected         : {_fmt(r.selected_symbol)}  (via {_fmt(r.symbol_discovery)})")

    print("\n Tick / Spread")
    if r.tick_bid is None and r.tick_ask is None:
        print("   (tick unavailable)")
    else:
        print(f"   Bid              : {_fmt(r.tick_bid)}")
        print(f"   Ask              : {_fmt(r.tick_ask)}")
        print(f"   Spread           : {_fmt(r.tick_spread)}")
        print(f"   Tick time        : {_fmt(r.tick_time)}")

    print("\n Candles")
    print(f"   Timeframe        : {_fmt(r.timeframe)}")
    print(f"   Bars             : {_fmt(r.bars_returned)} / {_fmt(r.bars_requested)} requested")
    if r.last_candle:
        c = r.last_candle
        print(f"   Last candle      : {_fmt(c.get('time'))}")
        print(f"     O/H/L/C        : {_fmt(c.get('open'))} / {_fmt(c.get('high'))} / "
              f"{_fmt(c.get('low'))} / {_fmt(c.get('close'))}")

    print("\n Positions / History")
    print(f"   Open positions   : {_fmt(r.open_positions)}")
    if r.history_deals is None:
        print("   Recent history   : (unavailable)")
    else:
        print(f"   Recent history   : {r.history_deals} deals over last {_fmt(r.history_days)} days")

    if r.warnings:
        print("\n Warnings")
        for w in r.warnings:
            print(f"   ! {w}")

    print("\n" + "-" * 60)
    print(f" READ ONLY - NO ORDERS SENT   (orders_sent={r.orders_sent})")
    print("-" * 60)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    connector = Mt5DemoConnector()  # real MetaTrader5, lazy-imported at connect()
    try:
        result = run_probe(
            connector,
            symbol=args.symbol,
            timeframe=args.timeframe,
            bars=args.bars,
        )
    except Mt5ConnectorError as exc:
        if args.json_output:
            print(json.dumps({"ok": False, "error": str(exc), "read_only": True,
                              "orders_sent": 0}, indent=2))
        else:
            print("PROBE FAILED (fail-closed):", exc, file=sys.stderr)
            print("READ ONLY - NO ORDERS SENT", file=sys.stderr)
        return 1

    if args.json_output:
        payload = result.to_dict()
        payload["ok"] = True
        print(json.dumps(payload, indent=2, default=str))
    else:
        print_human(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
