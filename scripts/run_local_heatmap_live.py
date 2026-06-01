"""
scripts/run_local_heatmap_live.py
-----------------------------------
Local dev "live" mode for the Lumora Liquidity Map.

Repeatedly collects real Binance Spot depth snapshots and continuously rewrites
a web fixture file. Paired with the Liquidity Map UI's fixture auto-refresh,
this makes the map feel live — entirely locally, with no Supabase, no
production worker, and no WebSocket.

It keeps a rolling window of the most recent frames (--max-frames) so the
fixture stays a fixed size while always reflecting the latest book.

Usage:
    python scripts/run_local_heatmap_live.py
    python scripts/run_local_heatmap_live.py \
        --symbol BTCUSDT --limit 1000 --price-step 10 --timeframe 5m \
        --samples 120 --interval 2 --max-frames 60 \
        --output lumora-web/fixtures/heatmap/BTCUSDT_5m.json

Stop early any time with Ctrl+C — the last written fixture stays in place.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Make the repo root importable when run directly as a script.
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

SOURCE_TAG = "local_live_fixture"
EXCHANGE = "binance_spot"
DEFAULT_WALL_THRESHOLD_USD = 1_000_000.0
DEFAULT_OUTPUT = "lumora-web/fixtures/heatmap/BTCUSDT_5m.json"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _next_timestamp(prev: datetime | None) -> datetime:
    """UTC timestamp strictly greater than `prev` (keeps time buckets distinct)."""
    now = datetime.now(timezone.utc)
    if prev is not None and now <= prev:
        now = prev + timedelta(milliseconds=1)
    return now


def _price_point(snapshot: dict, t_iso: str) -> dict | None:
    """
    Build a single price-path point from a depth snapshot.

    Returns {t, price (mid), bestBid, bestAsk} or None when either side of the
    book is empty (so the caller can simply skip it without crashing).
    """
    bids = snapshot.get("bids") or []
    asks = snapshot.get("asks") or []
    if not bids or not asks:
        return None
    best_bid = max(lv["price"] for lv in bids)
    best_ask = min(lv["price"] for lv in asks)
    mid = (best_bid + best_ask) / 2.0
    return {
        "t": t_iso,
        "price": round(mid, 2),
        "bestBid": best_bid,
        "bestAsk": best_ask,
    }


def write_payload_atomic(payload: dict, output: Path) -> None:
    """
    Write payload to `output` atomically: write a temp file in the same dir,
    flush+fsync, then os.replace() onto the target so readers never see a
    half-written file.
    """
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_suffix(output.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, output)


# ── Core tick ─────────────────────────────────────────────────────────────────

def build_live_payload(
    frames: list[dict],
    timeframe: str,
    interval: float,
    max_frames: int,
    sample_count: int,
    price_path: list[dict] | None = None,
) -> dict:
    """Build the API payload for the current rolling frame window + live meta."""
    matrix = build_heatmap_matrix(frames)
    current_price = price_path[-1]["price"] if price_path else None
    payload = build_heatmap_api_payload(
        matrix,
        timeframe=timeframe,
        exchange=EXCHANGE,
        price_path=price_path if price_path is not None else [],
        current_price=current_price,
    )

    meta = payload["meta"]
    meta["isDemo"] = False
    meta["source"] = SOURCE_TAG
    meta["dataSource"] = SOURCE_TAG
    meta["sampleCount"] = sample_count
    meta["intervalSeconds"] = interval
    meta["maxFrames"] = max_frames
    meta["liveUpdatedAt"] = datetime.now(timezone.utc).isoformat()
    return payload


def run_live(
    symbol: str,
    limit: int,
    price_step: float,
    timeframe: str,
    samples: int,
    interval: float,
    max_frames: int,
    output: Path,
    wall_threshold_usd: float = DEFAULT_WALL_THRESHOLD_USD,
    progress=None,
) -> int:
    """
    Run the live collection loop.

    Returns the number of successful samples collected. Validation errors raise
    ValueError; per-tick Binance failures are caught and reported so the loop
    keeps trying the next tick.
    """
    if samples <= 0:
        raise ValueError(f"samples must be > 0, got {samples}")
    if interval <= 0:
        raise ValueError(f"interval must be > 0, got {interval}")
    if max_frames <= 0:
        raise ValueError(f"max-frames must be > 0, got {max_frames}")

    frames: list[dict] = []
    price_path: list[dict] = []
    last_ts: datetime | None = None
    success = 0

    try:
        for i in range(samples):
            try:
                snapshot = fetch_depth_snapshot(symbol, limit)
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

                # Track the mid-price point in lock-step with the frame so the
                # path stays aligned to the heatmap's time buckets.
                point = _price_point(snapshot, ts_iso)
                if point is not None:
                    price_path.append(point)

                # Keep only the most recent max_frames on both lists.
                if len(frames) > max_frames:
                    frames = frames[-max_frames:]
                if len(price_path) > max_frames:
                    price_path = price_path[-max_frames:]

                success += 1
                payload = build_live_payload(
                    frames, timeframe, interval, max_frames, success, price_path,
                )
                write_payload_atomic(payload, output)

                if progress is not None:
                    meta = payload["meta"]
                    progress(
                        f"sample {i + 1}/{samples} · frames={len(frames)} · "
                        f"cells={meta.get('cellCount', 0)} · "
                        f"walls={meta.get('wallCount', 0)} · "
                        f"liveUpdatedAt={meta.get('liveUpdatedAt')} · "
                        f"-> {output}"
                    )
            except DepthCollectorError as exc:
                if progress is not None:
                    progress(f"sample {i + 1}/{samples} · fetch failed: {exc}")
                # fall through to the wait and try the next tick

            # Wait before the next tick (not after the last sample).
            if i < samples - 1:
                time.sleep(interval)
    except KeyboardInterrupt:
        if progress is not None:
            progress("interrupted — stopping, last fixture kept")

    return success


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="run_local_heatmap_live",
        description="Local live mode: continuously rewrite a heatmap web fixture from real Binance depth.",
    )
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--price-step", type=float, default=10.0, dest="price_step")
    parser.add_argument("--timeframe", default="5m")
    parser.add_argument("--samples", type=int, default=120)
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--max-frames", type=int, default=60, dest="max_frames")
    parser.add_argument("--wall-threshold", type=float,
                        default=DEFAULT_WALL_THRESHOLD_USD, dest="wall_threshold")
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns process exit code (0 ok, 1 on handled error)."""
    args = parse_args(argv)
    symbol = args.symbol.upper()

    try:
        success = run_live(
            symbol=symbol,
            limit=args.limit,
            price_step=args.price_step,
            timeframe=args.timeframe,
            samples=args.samples,
            interval=args.interval,
            max_frames=args.max_frames,
            output=Path(args.output),
            wall_threshold_usd=args.wall_threshold,
            progress=lambda msg: print(f"  {msg}"),
        )
    except ValueError as exc:
        print(f"error: invalid argument — {exc}", file=sys.stderr)
        return 1

    if success == 0:
        print("error: no snapshots were collected successfully", file=sys.stderr)
        return 1

    print(f"Done. {success} live update(s) written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
