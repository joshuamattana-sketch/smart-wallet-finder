"""
scripts/run_binance_ws_heatmap_live.py
---------------------------------------
WebSocket-based MVP collector for one Binance Spot symbol (default BTCUSDT).

Subscribes to the public bookTicker stream for sub-second best bid/ask
updates. Bootstraps a heatmap "cells" frame from one REST depth snapshot at
startup and refreshes it periodically. Every --write-interval seconds, writes
the latest HeatmapApiPayload (per timeframe) to Supabase and/or the local
live fixture so the UI's `/api/heatmap?source=live` reflects fast updates.

This is additive — it does NOT replace `scripts/run_local_heatmap_live.py`.
Run it alongside the existing REST writer (or instead of it for one symbol)
to test a faster live feel.

Run:
    python scripts/run_binance_ws_heatmap_live.py \\
        --symbol BTCUSDT --timeframes 5m,15m,1h \\
        --write-interval 1 --max-frames 1200 \\
        --target supabase --forever

Required env for --target supabase|both|all:
    SUPABASE_URL
    SUPABASE_SERVICE_ROLE_KEY
(Set in your shell / host platform env only — never in committed files.)

Optional dependency: WebSocket transport uses `websocket-client`
(https://pypi.org/project/websocket-client/). It is imported lazily so tests
and `--help` work without it. Install with:
    pip install websocket-client
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

# Make the repo root importable when run directly.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.run_local_heatmap_live import (  # noqa: E402
    DEFAULT_WALL_THRESHOLD_USD,
    EXCHANGE,
    SupabaseConfig,
    resolve_supabase_config,
    upsert_supabase_payload,
    write_payload_atomic,
)
from services.connectors.binance_depth_collector import (  # noqa: E402
    DepthCollectorError,
    fetch_depth_snapshot,
)
from services.orderbook_depth_bucketer import build_heatmap_cells  # noqa: E402
from services.heatmap_matrix_builder import build_heatmap_matrix  # noqa: E402
from services.heatmap_api_payload import (  # noqa: E402
    VALID_TIMEFRAMES,
    build_heatmap_api_payload,
)

# ── Constants ─────────────────────────────────────────────────────────────────

SOURCE_TAG = "binance_ws_live_writer"
COLLECTOR_TAG = "binance_websocket"
STREAM_TAG = "bookTicker"
DEFAULT_SYMBOL = "BTCUSDT"
DEFAULT_TIMEFRAMES = "5m,15m,1h"
DEFAULT_WRITE_INTERVAL_S = 1.0
DEFAULT_MAX_FRAMES = 1200
DEFAULT_DEPTH_REFRESH_S = 30.0
DEFAULT_DEPTH_LIMIT = 1000
DEFAULT_PRICE_STEP = 10.0
DEFAULT_LIVE_DIR = "lumora-web/fixtures/live"
VALID_TARGETS = ("supabase", "live", "both", "all")
WS_URL_TEMPLATE = "wss://stream.binance.com:9443/ws/{symbol}@bookTicker"

# Reconnect backoff bounds.
_MIN_BACKOFF_S = 1.0
_MAX_BACKOFF_S = 30.0
# How long the live recv() blocks before yielding a tick (None) so the main
# loop can run periodic tasks even when no WS message has arrived.
_WS_RECV_TIMEOUT_S = 0.5


# ── Targets ───────────────────────────────────────────────────────────────────

def targets_for(target: str) -> list[str]:
    """Expand --target into concrete write kinds. all == live + supabase here."""
    mapping = {
        "supabase": ["supabase"],
        "live":     ["live"],
        "both":     ["live", "supabase"],
        "all":      ["live", "supabase"],
    }
    return mapping.get(target, [target])


def target_requires_supabase(target: str) -> bool:
    return "supabase" in targets_for(target)


# ── Message parsing ──────────────────────────────────────────────────────────

def parse_book_ticker(raw: str | dict | None) -> dict | None:
    """
    Parse a Binance Spot bookTicker JSON payload into a normalized dict
    {bestBid, bestAsk, bestBidQty, bestAskQty}. Accepts either the bare
    bookTicker object or a combined-stream wrapper {"stream":..., "data":...}.

    Returns None on missing fields, bad JSON, or non-numeric values — the
    caller can simply skip it and stay running.
    """
    if raw is None:
        return None
    obj: object = raw
    if isinstance(raw, (str, bytes, bytearray)):
        try:
            obj = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None
    if not isinstance(obj, dict):
        return None
    # Combined-stream wrapper.
    if "data" in obj and isinstance(obj["data"], dict):
        obj = obj["data"]
    try:
        return {
            "bestBid":    float(obj["b"]),
            "bestAsk":    float(obj["a"]),
            "bestBidQty": float(obj.get("B") or 0.0),
            "bestAskQty": float(obj.get("A") or 0.0),
        }
    except (KeyError, ValueError, TypeError):
        return None


# ── Payload builder ───────────────────────────────────────────────────────────

def build_ws_payload(
    symbol: str,
    timeframe: str,
    frames: list[dict],
    price_path: list[dict],
    write_interval: float,
) -> dict:
    """Build a HeatmapApiPayload from the rolling frame + price-path state."""
    matrix = build_heatmap_matrix(frames)
    current_price = price_path[-1]["price"] if price_path else None
    payload = build_heatmap_api_payload(
        matrix,
        timeframe=timeframe,
        exchange=EXCHANGE,
        price_path=price_path,
        current_price=current_price,
    )
    payload["symbol"] = symbol
    now_iso = datetime.now(timezone.utc).isoformat()
    meta = payload["meta"]
    meta.update({
        "symbol":               symbol,
        "timeframe":            timeframe,
        "source":               SOURCE_TAG,
        "dataSource":           SOURCE_TAG,
        "resolvedSource":       "live",
        "isDemo":               False,
        "stale":                False,
        "liveUpdatedAt":        now_iso,
        "collector":            COLLECTOR_TAG,
        "stream":               STREAM_TAG,
        "writeIntervalSeconds": write_interval,
    })
    return payload


# ── Live WebSocket transport (real network) ───────────────────────────────────

def _default_ws_messages_with_reconnect(
    url: str,
    progress: Callable[[str], None] | None = None,
) -> Iterable[str | None]:
    """
    Generator that yields raw WS messages (str) or None on idle ticks.
    Reconnects with capped exponential backoff on transport errors.

    Lazy-imports `websocket-client` so the rest of this module (and tests)
    works without that dependency installed.
    """
    try:
        from websocket import (  # type: ignore[import-not-found]
            WebSocketException,
            WebSocketTimeoutException,
            create_connection,
        )
    except ImportError as exc:  # pragma: no cover - exercised via install error
        raise RuntimeError(
            "WebSocket transport requires the 'websocket-client' package. "
            "Install with: pip install websocket-client"
        ) from exc

    def _say(msg: str) -> None:
        if progress is not None:
            progress(msg)

    backoff = _MIN_BACKOFF_S
    while True:
        ws = None
        try:
            _say(f"ws connecting: {url}")
            ws = create_connection(url, timeout=_WS_RECV_TIMEOUT_S * 4)
            ws.settimeout(_WS_RECV_TIMEOUT_S)
            _say("ws connected")
            backoff = _MIN_BACKOFF_S
            while True:
                try:
                    yield ws.recv()
                except WebSocketTimeoutException:
                    yield None  # tick so caller can run periodic tasks
        except (WebSocketException, OSError) as exc:
            _say(f"ws disconnected: {exc} — reconnecting in {backoff:.1f}s")
            time.sleep(backoff)
            backoff = min(backoff * 2, _MAX_BACKOFF_S)
        except GeneratorExit:
            return
        finally:
            if ws is not None:
                try:
                    ws.close()
                except Exception:
                    pass
                _say("ws closed")


# ── Core collector loop (dependency-injected for tests) ──────────────────────

def run_ws_collector(
    *,
    symbol: str,
    timeframes: list[str],
    write_interval: float,
    max_frames: int,
    target: str,
    supabase: SupabaseConfig | None,
    output_for: Callable[[str, str], Path],
    message_iter: Iterable[str | None],
    fetch_depth: Callable[..., dict] = fetch_depth_snapshot,
    depth_limit: int = DEFAULT_DEPTH_LIMIT,
    depth_refresh_seconds: float = DEFAULT_DEPTH_REFRESH_S,
    price_step: float = DEFAULT_PRICE_STEP,
    wall_threshold_usd: float = DEFAULT_WALL_THRESHOLD_USD,
    samples: int | None = None,
    forever: bool = False,
    progress: Callable[[str], None] | None = None,
    now: Callable[[], float] = time.monotonic,
    upsert: Callable[..., None] = upsert_supabase_payload,
) -> dict:
    """
    Drive the collector loop. Returns {writes: int, messages: int}.

    Validates inputs, bootstraps a single REST depth frame, then iterates
    `message_iter`. On every loop step it checks:
      * depth refresh (every depth_refresh_seconds via fetch_depth)
      * write cycle (every write_interval) — builds + writes the payload
        for each timeframe to the requested targets.

    Per-symbol failures (fetch errors, supabase errors) are logged but do not
    crash the loop. KeyboardInterrupt exits cleanly.
    """
    if not symbol:
        raise ValueError("symbol is required")
    if not timeframes:
        raise ValueError("at least one timeframe is required")
    if write_interval <= 0:
        raise ValueError(f"write-interval must be > 0, got {write_interval}")
    if max_frames <= 0:
        raise ValueError(f"max-frames must be > 0, got {max_frames}")
    if target not in VALID_TARGETS:
        raise ValueError(
            f"invalid target {target!r}. Allowed: {', '.join(VALID_TARGETS)}"
        )
    for tf in timeframes:
        if tf not in VALID_TIMEFRAMES:
            raise ValueError(
                f"invalid timeframe {tf!r}. Allowed: {', '.join(sorted(VALID_TIMEFRAMES))}"
            )

    write_targets = targets_for(target)
    if "supabase" in write_targets and supabase is None:
        raise ValueError(
            "supabase target requested but Supabase config was not provided"
        )

    def _say(msg: str) -> None:
        if progress is not None:
            progress(msg)

    state: dict[str, object] = {
        "best_bid": None, "best_ask": None, "mid": None,
        "last_event_at": None,
    }
    frames: list[dict] = []
    price_path: list[dict] = []
    writes = 0
    messages = 0

    def _refresh_depth() -> None:
        """Fetch one REST depth snapshot, append a new frame, cap history."""
        try:
            snap = fetch_depth(symbol, depth_limit)
        except (DepthCollectorError, ValueError) as exc:
            _say(f"depth refresh failed: {exc}")
            return
        frame = build_heatmap_cells(
            snap, price_step=price_step, wall_threshold_usd=wall_threshold_usd,
        )
        frames.append(frame)
        if len(frames) > max_frames:
            del frames[: len(frames) - max_frames]

    # Bootstrap — one REST snapshot so the very first write has real cells.
    _refresh_depth()
    last_depth_refresh = now()
    last_write = -float("inf")  # force first write as soon as we have a mid

    try:
        for raw in message_iter:
            # One clock read per iteration so injected test clocks tick
            # predictably and so the timing gates use a single monotonic value.
            t = now()
            if raw is not None:
                messages += 1
                parsed = parse_book_ticker(raw)
                if parsed is not None:
                    state["best_bid"] = parsed["bestBid"]
                    state["best_ask"] = parsed["bestAsk"]
                    state["mid"] = round(
                        (parsed["bestBid"] + parsed["bestAsk"]) / 2.0, 2,
                    )
                    state["last_event_at"] = t

            # Periodic depth refresh (REST keeps cells alive).
            if t - last_depth_refresh >= depth_refresh_seconds:
                _refresh_depth()
                last_depth_refresh = t

            # Periodic write — gated by write_interval and "have-data" guards.
            ready = (
                state["mid"] is not None and frames
                and (t - last_write) >= write_interval
            )
            if ready:
                ts_iso = datetime.now(timezone.utc).isoformat()
                price_path.append({
                    "t":       ts_iso,
                    "price":   state["mid"],
                    "bestBid": state["best_bid"],
                    "bestAsk": state["best_ask"],
                })
                if len(price_path) > max_frames:
                    del price_path[: len(price_path) - max_frames]

                for tf in timeframes:
                    payload = build_ws_payload(
                        symbol, tf, frames, price_path, write_interval,
                    )
                    for kind in write_targets:
                        try:
                            if kind == "supabase":
                                assert supabase is not None  # checked above
                                upsert(supabase, symbol, tf, payload)
                            elif kind == "live":
                                write_payload_atomic(payload, output_for(symbol, tf))
                        except (RuntimeError, OSError) as exc:
                            _say(f"write {kind} · {symbol} {tf} · failed: {exc}")

                writes += 1
                last_write = t
                _say(
                    f"write #{writes} · {symbol} · tfs={','.join(timeframes)} · "
                    f"mid={state['mid']} · msgs={messages} · "
                    f"frames={len(frames)} · pricePath={len(price_path)}"
                )

                if not forever and samples is not None and writes >= samples:
                    break
    except KeyboardInterrupt:
        _say("interrupted — stopping cleanly, last writes kept")

    return {"writes": writes, "messages": messages}


# ── CLI ───────────────────────────────────────────────────────────────────────

def _split_list(raw: str) -> list[str]:
    return [p.strip() for p in raw.split(",") if p.strip()]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="run_binance_ws_heatmap_live",
        description="WebSocket-based MVP collector for one Binance Spot symbol.",
    )
    parser.add_argument("--symbol", default=DEFAULT_SYMBOL,
                        help=f"Symbol to subscribe to (default: {DEFAULT_SYMBOL}).")
    parser.add_argument("--timeframes", default=DEFAULT_TIMEFRAMES,
                        help=f"Comma-separated timeframes (default: {DEFAULT_TIMEFRAMES}).")
    parser.add_argument("--write-interval", type=float,
                        default=DEFAULT_WRITE_INTERVAL_S, dest="write_interval",
                        help="Seconds between writes (default: 1).")
    parser.add_argument("--max-frames", type=int, default=DEFAULT_MAX_FRAMES,
                        dest="max_frames",
                        help="Rolling frame / pricePath cap (default: 1200).")
    parser.add_argument("--depth-refresh", type=float,
                        default=DEFAULT_DEPTH_REFRESH_S, dest="depth_refresh",
                        help="Seconds between REST depth snapshots (default: 30).")
    parser.add_argument("--price-step", type=float, default=DEFAULT_PRICE_STEP,
                        dest="price_step",
                        help="USD price bucket size for cells (default: 10).")
    parser.add_argument("--wall-threshold", type=float,
                        default=DEFAULT_WALL_THRESHOLD_USD, dest="wall_threshold")
    parser.add_argument("--target", default="supabase", choices=VALID_TARGETS,
                        help="Where to write: supabase | live | both | all "
                             "(default: supabase).")
    parser.add_argument("--live-dir", default=DEFAULT_LIVE_DIR, dest="live_dir",
                        help="Directory for local live {SYMBOL}_{tf}.json files.")
    parser.add_argument("--samples", type=int, default=None,
                        help="Stop after N writes (dev/tests). Ignored with --forever.")
    parser.add_argument("--forever", action="store_true",
                        help="Run until Ctrl+C / SIGINT (recommended for hosted worker).")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    symbol = args.symbol.upper()
    try:
        timeframes = [t.lower() for t in _split_list(args.timeframes)]
    except ValueError as exc:
        print(f"error: invalid argument — {exc}", file=sys.stderr)
        return 1

    for tf in timeframes:
        if tf not in VALID_TIMEFRAMES:
            print(
                f"error: invalid argument — invalid timeframe {tf!r}. "
                f"Allowed: {', '.join(sorted(VALID_TIMEFRAMES))}",
                file=sys.stderr,
            )
            return 1

    sb_cfg: SupabaseConfig | None = None
    if target_requires_supabase(args.target):
        try:
            sb_cfg = resolve_supabase_config(None, None)
        except ValueError as exc:
            print(f"error: invalid argument — {exc}", file=sys.stderr)
            return 1

    live_dir = Path(args.live_dir)

    def output_for(sym: str, tf: str) -> Path:
        return live_dir / f"{sym}_{tf}.json"

    mode_label = "forever" if args.forever else (
        f"samples={args.samples}" if args.samples is not None else "samples=∞"
    )
    print(
        "run_binance_ws_heatmap_live startup:\n"
        f"  mode               = {mode_label}\n"
        f"  symbol             = {symbol}\n"
        f"  timeframes         = {', '.join(timeframes)}\n"
        f"  target             = {args.target}\n"
        f"  write interval     = {args.write_interval}s\n"
        f"  depth refresh      = {args.depth_refresh}s\n"
        f"  max frames         = {args.max_frames}\n"
        f"  collector          = {COLLECTOR_TAG}\n"
        f"  supabase           = "
        f"{'configured' if sb_cfg is not None else 'not configured'}",
        flush=True,
    )

    url = WS_URL_TEMPLATE.format(symbol=symbol.lower())
    progress = lambda m: print(f"  {m}", flush=True)  # noqa: E731
    msg_iter = _default_ws_messages_with_reconnect(url, progress=progress)

    try:
        result = run_ws_collector(
            symbol=symbol,
            timeframes=timeframes,
            write_interval=args.write_interval,
            max_frames=args.max_frames,
            target=args.target,
            supabase=sb_cfg,
            output_for=output_for,
            message_iter=msg_iter,
            depth_refresh_seconds=args.depth_refresh,
            price_step=args.price_step,
            wall_threshold_usd=args.wall_threshold,
            samples=args.samples,
            forever=args.forever,
            progress=progress,
        )
    except RuntimeError as exc:
        # Includes "websocket-client not installed".
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"error: invalid argument — {exc}", file=sys.stderr)
        return 1

    print(
        f"Done. {result['writes']} write(s) · {result['messages']} ws message(s) "
        f"· target '{args.target}'."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
