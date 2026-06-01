"""
scripts/export_real_heatmap_history.py
---------------------------------------
Manual, local history export tool.

Collects several real Binance Spot orderbook depth snapshots spaced over time
and runs them through the existing Lumora heatmap pipeline, producing a
multi-frame ("history") API payload written to a JSON file.

This is NOT a live worker / service. It runs a bounded number of samples and
exits. No Supabase, no WebSocket, no infinite loop.

Usage:
    python scripts/export_real_heatmap_history.py
    python scripts/export_real_heatmap_history.py \
        --symbol BTCUSDT --limit 1000 --price-step 10 --timeframe 5m \
        --samples 6 --interval 5 \
        --output data/heatmap_history_BTCUSDT_5m.json

Pipeline (per sample):
    fetch_depth_snapshot      (services.connectors.binance_depth_collector)
    -> build_heatmap_cells    (services.orderbook_depth_bucketer)
Then across all frames:
    build_heatmap_matrix      (services.heatmap_matrix_builder)
    -> build_heatmap_api_payload (services.heatmap_api_payload)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Make the repo root importable when run directly as a script. Harmless when
# imported as a package (the path already resolves in that case).
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

SOURCE_TAG = "binance_spot_rest_history"
EXCHANGE = "binance_spot"
DEFAULT_WALL_THRESHOLD_USD = 1_000_000.0


# ── Helpers ───────────────────────────────────────────────────────────────────

def _next_timestamp(prev: datetime | None) -> datetime:
    """
    Return a UTC timestamp strictly greater than `prev`.

    Real snapshots collected `interval` seconds apart already differ, but this
    guarantees distinct per-sample timestamps even when samples are taken in
    rapid succession (e.g. interval=0 or mocked sleep in tests), so the matrix
    yields exactly one time bucket per sample.
    """
    now = datetime.now(timezone.utc)
    if prev is not None and now <= prev:
        now = prev + timedelta(milliseconds=1)
    return now


def _price_point(snapshot: dict, t_iso: str) -> dict | None:
    """Mid-price point {t, price, bestBid, bestAsk} or None if a side is empty."""
    bids = snapshot.get("bids") or []
    asks = snapshot.get("asks") or []
    if not bids or not asks:
        return None
    best_bid = max(lv["price"] for lv in bids)
    best_ask = min(lv["price"] for lv in asks)
    mid = (best_bid + best_ask) / 2.0
    return {"t": t_iso, "price": round(mid, 2), "bestBid": best_bid, "bestAsk": best_ask}


# ── Core ──────────────────────────────────────────────────────────────────────

def build_history_payload(
    symbol: str,
    limit: int,
    price_step: float,
    timeframe: str,
    samples: int,
    interval: float,
    wall_threshold_usd: float = DEFAULT_WALL_THRESHOLD_USD,
    progress=None,
) -> dict:
    """
    Collect `samples` real snapshots and build a multi-frame heatmap payload.

    Args:
        progress: optional callable(message: str) for per-sample reporting.

    Returns:
        API payload dict with history metadata stamped into meta.

    Raises:
        ValueError:          invalid arguments (samples <= 0, interval < 0, or
                             a bad symbol/limit/price_step/timeframe).
        DepthCollectorError: Binance HTTP / network / parse failure.
    """
    if samples <= 0:
        raise ValueError(f"samples must be > 0, got {samples}")
    if interval < 0:
        raise ValueError(f"interval must be >= 0, got {interval}")

    frames: list[dict] = []
    price_path: list[dict] = []
    last_ts: datetime | None = None

    for i in range(samples):
        snapshot = fetch_depth_snapshot(symbol, limit)

        # Stamp a strictly-increasing capture time so each sample becomes its
        # own time bucket in the matrix.
        ts = _next_timestamp(last_ts)
        last_ts = ts
        ts_iso = ts.isoformat()
        snapshot["captured_at"] = ts_iso

        frame = build_heatmap_cells(
            snapshot,
            price_step=price_step,
            wall_threshold_usd=wall_threshold_usd,
        )
        frames.append(frame)

        point = _price_point(snapshot, ts_iso)
        if point is not None:
            price_path.append(point)

        if progress is not None:
            progress(
                f"sample {i + 1}/{samples} collected · "
                f"buckets={len(frame.get('buckets', []))} · "
                f"walls={len(frame.get('walls', []))}"
            )

        # Wait between samples (not after the last one).
        if interval > 0 and i < samples - 1:
            time.sleep(interval)

    matrix = build_heatmap_matrix(frames)
    current_price = price_path[-1]["price"] if price_path else None
    payload = build_heatmap_api_payload(
        matrix,
        timeframe=timeframe,
        exchange=EXCHANGE,
        price_path=price_path,
        current_price=current_price,
    )

    meta = payload["meta"]
    meta["isDemo"] = False
    meta["source"] = SOURCE_TAG
    meta["dataSource"] = SOURCE_TAG
    meta["sampleCount"] = samples
    meta["intervalSeconds"] = interval

    return payload


def write_payload(payload: dict, output: Path) -> Path:
    """Write payload as pretty JSON, creating parent directories as needed."""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return output


# ── CLI ───────────────────────────────────────────────────────────────────────

def _default_output(symbol: str, timeframe: str) -> str:
    return f"data/heatmap_history_{symbol.upper()}_{timeframe}.json"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="export_real_heatmap_history",
        description="Export a multi-sample real Binance Spot heatmap history payload (one-shot, local).",
    )
    parser.add_argument("--symbol", default="BTCUSDT",
                        help="Trading pair, e.g. BTCUSDT (default: BTCUSDT).")
    parser.add_argument("--limit", type=int, default=1000,
                        help="Depth levels per side: 100, 500, 1000, or 5000 (default: 1000).")
    parser.add_argument("--price-step", type=float, default=10.0, dest="price_step",
                        help="Price bucket width in USD (default: 10).")
    parser.add_argument("--timeframe", default="5m",
                        help="Timeframe label: 5m, 15m, 1h, 4h, 1d (default: 5m).")
    parser.add_argument("--samples", type=int, default=6,
                        help="Number of snapshots to collect (default: 6).")
    parser.add_argument("--interval", type=float, default=5.0,
                        help="Seconds to wait between snapshots (default: 5).")
    parser.add_argument("--wall-threshold", type=float, default=DEFAULT_WALL_THRESHOLD_USD,
                        dest="wall_threshold",
                        help="Min bucket USD to flag a liquidity wall (default: 1000000).")
    parser.add_argument("--output", default=None,
                        help="Output JSON path (default: data/heatmap_history_<SYMBOL>_<timeframe>.json).")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns process exit code (0 ok, 1 on handled error)."""
    args = parse_args(argv)

    symbol = args.symbol.upper()
    output = (
        Path(args.output) if args.output
        else Path(_default_output(symbol, args.timeframe))
    )

    try:
        payload = build_history_payload(
            symbol=symbol,
            limit=args.limit,
            price_step=args.price_step,
            timeframe=args.timeframe,
            samples=args.samples,
            interval=args.interval,
            wall_threshold_usd=args.wall_threshold,
            progress=lambda msg: print(f"  {msg}"),
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
    print("Real heatmap history exported:")
    print(f"  symbol      : {payload.get('symbol')}")
    print(f"  samples     : {meta.get('sampleCount')}")
    print(f"  interval    : {meta.get('intervalSeconds')}s")
    print(f"  timeBuckets : {len(payload.get('timeBuckets', []))}")
    print(f"  cells       : {meta.get('cellCount', 0)}")
    print(f"  walls       : {meta.get('wallCount', 0)}")
    print(f"  source      : {meta.get('source')}")
    print(f"  isDemo      : {meta.get('isDemo')}")
    print(f"  output      : {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
