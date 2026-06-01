"""
scripts/export_real_heatmap_payload.py
---------------------------------------
Manual, local demo export tool.

Fetches ONE real Binance Spot orderbook depth snapshot and pushes it through
the existing Lumora heatmap pipeline, writing the resulting API payload to a
JSON file on disk.

This is NOT a live worker. It runs once, does no Supabase writes, opens no
WebSocket, and loops never. It is meant to be invoked by hand to produce a
real-data sample payload for inspection / frontend testing.

Usage:
    python scripts/export_real_heatmap_payload.py
    python scripts/export_real_heatmap_payload.py --symbol ETHUSDT --limit 500
    python scripts/export_real_heatmap_payload.py --price-step 5 --timeframe 1h \
        --output data/heatmap_payload_BTCUSDT.json

Pipeline:
    fetch_depth_snapshot      (services.connectors.binance_depth_collector)
    -> build_heatmap_cells    (services.orderbook_depth_bucketer)
    -> build_heatmap_matrix   (services.heatmap_matrix_builder)
    -> build_heatmap_api_payload (services.heatmap_api_payload)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Make the repo root importable when run directly as a script
# (python scripts/export_real_heatmap_payload.py). Harmless when imported as
# a package (the path is already resolvable in that case).
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from services.connectors.binance_depth_collector import (  # noqa: E402
    DepthCollectorError,
    fetch_depth_snapshot,
)
from services.orderbook_depth_bucketer import build_heatmap_cells  # noqa: E402
from services.heatmap_matrix_builder import build_heatmap_matrix  # noqa: E402
from services.heatmap_api_payload import build_heatmap_api_payload  # noqa: E402

# Source tag stamped into meta so consumers can tell this came from a real
# REST snapshot rather than the synthetic demo generator.
SOURCE_TAG = "binance_spot_rest_snapshot"
EXCHANGE = "binance_spot"
DEFAULT_WALL_THRESHOLD_USD = 1_000_000.0


# ── Core ──────────────────────────────────────────────────────────────────────

def build_real_payload(
    symbol: str,
    limit: int,
    price_step: float,
    timeframe: str,
    wall_threshold_usd: float = DEFAULT_WALL_THRESHOLD_USD,
) -> dict:
    """
    Fetch one real depth snapshot and run it through the heatmap pipeline.

    Returns the API payload dict with meta.isDemo == False and a
    meta.source == SOURCE_TAG tag added.

    Raises:
        ValueError:          invalid argument (bad symbol, limit, price_step,
                             or timeframe).
        DepthCollectorError: Binance HTTP / network / parse failure.
    """
    snapshot = fetch_depth_snapshot(symbol, limit)

    frame = build_heatmap_cells(
        snapshot,
        price_step=price_step,
        wall_threshold_usd=wall_threshold_usd,
    )
    matrix = build_heatmap_matrix([frame])
    payload = build_heatmap_api_payload(matrix, timeframe=timeframe, exchange=EXCHANGE)

    # Stamp real-source metadata.
    payload["meta"]["isDemo"] = False
    payload["meta"]["source"] = SOURCE_TAG

    # Keep the raw bucket count handy for the summary print.
    payload["meta"]["bucketCount"] = len(frame.get("buckets", []))

    return payload


def write_payload(payload: dict, output: Path) -> Path:
    """Write payload as pretty JSON, creating parent directories as needed."""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return output


# ── CLI ───────────────────────────────────────────────────────────────────────

def _default_output(symbol: str) -> str:
    return f"data/heatmap_payload_{symbol.upper()}.json"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="export_real_heatmap_payload",
        description="Export a real Binance Spot heatmap payload to JSON (one-shot, local).",
    )
    parser.add_argument("--symbol", default="BTCUSDT",
                        help="Trading pair, e.g. BTCUSDT (default: BTCUSDT).")
    parser.add_argument("--limit", type=int, default=1000,
                        help="Depth levels per side: 100, 500, 1000, or 5000 (default: 1000).")
    parser.add_argument("--price-step", type=float, default=10.0, dest="price_step",
                        help="Price bucket width in USD (default: 10).")
    parser.add_argument("--timeframe", default="5m",
                        help="Timeframe label: 5m, 15m, 1h, 4h, 1d (default: 5m).")
    parser.add_argument("--wall-threshold", type=float, default=DEFAULT_WALL_THRESHOLD_USD,
                        dest="wall_threshold",
                        help="Min bucket USD to flag a liquidity wall (default: 1000000).")
    parser.add_argument("--output", default=None,
                        help="Output JSON path (default: data/heatmap_payload_<SYMBOL>.json).")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """
    Entry point. Returns process exit code (0 ok, 1 on handled error).
    """
    args = parse_args(argv)

    symbol = args.symbol.upper()
    output = Path(args.output) if args.output else Path(_default_output(symbol))

    try:
        payload = build_real_payload(
            symbol=symbol,
            limit=args.limit,
            price_step=args.price_step,
            timeframe=args.timeframe,
            wall_threshold_usd=args.wall_threshold,
        )
    except ValueError as exc:
        print(f"error: invalid argument — {exc}", file=sys.stderr)
        return 1
    except DepthCollectorError as exc:
        print(f"error: Binance depth fetch failed — {exc}", file=sys.stderr)
        return 1

    try:
        path = write_payload(payload, output)
    except OSError as exc:
        print(f"error: could not write output {output} — {exc}", file=sys.stderr)
        return 1

    meta = payload.get("meta", {})
    print("Real heatmap payload exported:")
    print(f"  symbol      : {payload.get('symbol')}")
    print(f"  buckets     : {meta.get('bucketCount', 0)}")
    print(f"  cells       : {meta.get('cellCount', 0)}")
    print(f"  walls       : {meta.get('wallCount', 0)}")
    print(f"  source      : {meta.get('source')}")
    print(f"  isDemo      : {meta.get('isDemo')}")
    print(f"  generatedAt : {meta.get('generatedAt')}")
    print(f"  output      : {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
