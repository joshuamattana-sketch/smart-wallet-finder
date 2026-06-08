"""
scripts/run_binance_trade_stream_smoke.py
------------------------------------------
LM63B — Smoke runner for the Binance Spot aggTrade collector.

Connects to the public `@aggTrade` stream for the given symbols, normalises
each fill into a whale-engine v2 input dict, passes it through
`services.whale_alert_engine.detect_whale_events` with a notional threshold,
and prints the resulting large-trade events to stdout.

NO Supabase writes. NO Discord. NO secrets required.

Usage:
    python scripts/run_binance_trade_stream_smoke.py \\
        --symbols BTCUSDT,ETHUSDT,SOLUSDT --min-notional 250000

    # Stop after N printed events (handy in dev):
    python scripts/run_binance_trade_stream_smoke.py --samples 5

Requires the optional `websocket-client` package at runtime:
    pip install websocket-client
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Make the repo root importable when run directly.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from services.connectors.binance_trade_stream import (  # noqa: E402
    iter_binance_aggtrades,
    is_valid_binance_symbol,
)
from services.whale_alert_engine import detect_whale_events  # noqa: E402


DEFAULT_SYMBOLS = "BTCUSDT,ETHUSDT,SOLUSDT"
DEFAULT_MIN_NOTIONAL = 250_000.0


def _split_symbols(raw: str) -> list[str]:
    return [s.strip().upper() for s in raw.split(",") if s.strip()]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="run_binance_trade_stream_smoke",
        description=(
            "Stream Binance Spot aggTrade fills and print large-trade "
            "whale-event candidates to stdout. Pure smoke runner — no "
            "Supabase, no Discord."
        ),
    )
    parser.add_argument(
        "--symbols", default=DEFAULT_SYMBOLS,
        help=f"Comma-separated symbols (default: {DEFAULT_SYMBOLS}).",
    )
    parser.add_argument(
        "--min-notional", type=float, default=DEFAULT_MIN_NOTIONAL,
        dest="min_notional",
        help=(f"Minimum trade notional in USD to print as a whale event "
              f"(default: ${int(DEFAULT_MIN_NOTIONAL):,})."),
    )
    parser.add_argument(
        "--samples", type=int, default=None,
        help="Stop after N printed whale events (default: run until Ctrl+C).",
    )
    parser.add_argument(
        "--pretty", action="store_true",
        help="Print each event as indented JSON (default: one compact JSON per line).",
    )
    return parser.parse_args(argv)


def _progress(msg: str) -> None:
    # Diagnostics → stderr so stdout stays a clean event stream.
    print(f"  {msg}", file=sys.stderr, flush=True)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    raw_symbols = _split_symbols(args.symbols)
    if not raw_symbols:
        print("error: --symbols cannot be empty", file=sys.stderr)
        return 1

    valid = [s for s in raw_symbols if is_valid_binance_symbol(s)]
    skipped = [s for s in raw_symbols if s not in valid]
    if not valid:
        print(
            "error: no valid Binance Spot symbols supplied "
            "(expect A-Z/0-9, 3-12 chars)",
            file=sys.stderr,
        )
        return 1
    if skipped:
        print(f"  skipping invalid symbols: {', '.join(skipped)}", file=sys.stderr)

    if args.min_notional < 0:
        print("error: --min-notional must be >= 0", file=sys.stderr)
        return 1

    _progress(
        "binance aggTrade smoke runner starting "
        f"· symbols={','.join(valid)} · min_notional=${args.min_notional:,.0f}"
        + (f" · samples={args.samples}" if args.samples is not None else "")
    )

    try:
        stream = iter_binance_aggtrades(valid, progress=_progress)
    except (ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    printed = 0
    try:
        for item in stream:
            # Threshold via the real consumer so output matches downstream.
            events = detect_whale_events(
                [item],
                options={"min_notional_usd": args.min_notional},
            )
            if not events:
                continue
            for ev in events:
                if args.pretty:
                    print(json.dumps(ev, indent=2, sort_keys=True), flush=True)
                else:
                    print(json.dumps(ev, sort_keys=True), flush=True)
                printed += 1
                if args.samples is not None and printed >= args.samples:
                    _progress(f"reached --samples={args.samples} · stopping")
                    return 0
    except KeyboardInterrupt:
        _progress("interrupted — stopping cleanly")
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
