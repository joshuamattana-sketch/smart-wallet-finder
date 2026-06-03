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
from services.orderbook_depth_bucketer import (  # noqa: E402
    VALID_RANGE_MODES,
    auto_scale_price_step,
    build_heatmap_cells,
    resolve_price_range,
)
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
WS_URL_TEMPLATE          = "wss://stream.binance.com:9443/ws/{symbol}@bookTicker"
WS_URL_COMBINED_TEMPLATE = "wss://stream.binance.com:9443/stream?streams={streams}"

# Binance Spot symbol shape: 3-12 chars, A-Z + 0-9 only (no separators).
_SYMBOL_RE = __import__("re").compile(r"^[A-Z0-9]{3,12}$")

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
        out = {
            "bestBid":    float(obj["b"]),
            "bestAsk":    float(obj["a"]),
            "bestBidQty": float(obj.get("B") or 0.0),
            "bestAskQty": float(obj.get("A") or 0.0),
        }
    except (KeyError, ValueError, TypeError):
        return None
    # LM42B: surface the symbol (`s`) so multi-symbol collectors can route
    # the message to the correct per-symbol state. Single-symbol callers
    # can simply ignore the field.
    sym = obj.get("s")
    if isinstance(sym, str) and sym:
        out["symbol"] = sym.upper()
    return out


# ── Multi-symbol helpers (LM42B) ──────────────────────────────────────────────

def is_valid_binance_symbol(sym: str) -> bool:
    """Reject garbage CLI input before we open a stream we know will 404."""
    if not isinstance(sym, str):
        return False
    return bool(_SYMBOL_RE.match(sym.strip().upper()))


def build_ws_url(symbols: list[str]) -> str:
    """
    Build the Binance public WS URL for one or many symbols.

    Single symbol → the simple `/ws/{sym}@bookTicker` endpoint
    (byte-for-byte backward compatible with LM42A).
    Multiple symbols → the combined `/stream?streams=...` endpoint, which
    multiplexes every bookTicker stream over one socket.
    """
    cleaned = [s.strip().lower() for s in symbols if s and s.strip()]
    if not cleaned:
        raise ValueError("at least one symbol is required to build a WS URL")
    if len(cleaned) == 1:
        return WS_URL_TEMPLATE.format(symbol=cleaned[0])
    streams = "/".join(f"{s}@bookTicker" for s in cleaned)
    return WS_URL_COMBINED_TEMPLATE.format(streams=streams)


# ── Payload builder ───────────────────────────────────────────────────────────

def build_ws_payload(
    symbol: str,
    timeframe: str,
    frames: list[dict],
    price_path: list[dict],
    write_interval: float,
    range_meta: dict | None = None,
) -> dict:
    """Build a HeatmapApiPayload from the rolling frame + price-path state."""
    matrix = build_heatmap_matrix(frames)
    current_price = price_path[-1]["price"] if price_path else None
    # LM44: forward zones from the latest frame.
    latest_frame = frames[-1] if frames else None
    payload = build_heatmap_api_payload(
        matrix,
        timeframe=timeframe,
        exchange=EXCHANGE,
        price_path=price_path,
        current_price=current_price,
        price_range_meta=range_meta,
        zones=(latest_frame.get("zones") if latest_frame else None),
        key_zones=(latest_frame.get("key_zones") if latest_frame else None),
        aggregation_mode=(latest_frame.get("aggregation_mode") if latest_frame else None),
        bucket_aggregation=(latest_frame.get("bucket_aggregation") if latest_frame else None),
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
    symbols: list[str] | None = None,
    symbol: str | None = None,                # LM42A backward-compat shim
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
    range_mode: str = "standard",
    price_range_abs: float | None = None,
    price_range_percent: float | None = None,
) -> dict:
    """
    Drive the multi-symbol WS collector loop. Returns
    ``{writes, messages, per_symbol: {sym: writes}}``.

    Accepts either ``symbols=[...]`` (LM42B) or the legacy ``symbol=`` kwarg
    (LM42A, auto-wrapped into a single-element list for backward compat).

    Per-symbol state is fully isolated: a fetch failure or stream error on
    one symbol never wipes another symbol's frames / price_path / range
    meta. KeyboardInterrupt exits cleanly. ``samples`` counts total writes
    across all symbols.
    """
    # ── Resolve symbols (with backward-compat shim) ─────────────────────────
    if symbols is None and symbol is not None:
        symbols = [symbol]
    if not symbols:
        raise ValueError("symbols (or symbol) is required")
    symbols = [s.upper().strip() for s in symbols if s and s.strip()]
    if not symbols:
        raise ValueError("symbols list is empty after normalization")
    for s in symbols:
        if not is_valid_binance_symbol(s):
            raise ValueError(
                f"invalid Binance symbol {s!r} (expect A-Z/0-9, 3-12 chars)"
            )

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
    if range_mode not in VALID_RANGE_MODES:
        raise ValueError(
            f"invalid range mode {range_mode!r}. "
            f"Allowed: {', '.join(VALID_RANGE_MODES)}"
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

    # ── Per-symbol state ─────────────────────────────────────────────────────
    states: dict[str, dict] = {
        sym: {
            "best_bid":            None,
            "best_ask":            None,
            "mid":                 None,
            "last_event_at":       None,
            "range_meta":          None,
            "frames":              [],
            "price_path":          [],
            "last_depth_refresh": -float("inf"),
            "last_write":         -float("inf"),
            "writes":              0,
        }
        for sym in symbols
    }
    total_writes = 0
    messages = 0

    def _resolve_range_for(sym: str, mid: float) -> dict | None:
        try:
            return resolve_price_range(
                sym, range_mode, float(mid),
                abs_override=price_range_abs,
                pct_override=price_range_percent,
            )
        except ValueError as exc:
            _say(f"range resolve failed [{sym}]: {exc}")
            return None

    def _refresh_depth(sym: str) -> None:
        """Fetch one REST snapshot for `sym`, append a new frame per-symbol."""
        st = states[sym]
        try:
            snap = fetch_depth(sym, depth_limit)
        except (DepthCollectorError, ValueError) as exc:
            _say(f"depth refresh failed [{sym}]: {exc}")
            return

        mid = st["mid"]
        price_range: tuple[float, float] | None = None
        effective_step = price_step
        info = None
        if isinstance(mid, (int, float)) and mid > 0:
            info = _resolve_range_for(sym, mid)
            if info is not None:
                price_range = (info["min"], info["max"])
                if range_mode in ("wide", "macro"):
                    effective_step = auto_scale_price_step(
                        info["max"] - info["min"], price_step,
                    )

        frame = build_heatmap_cells(
            snap, price_step=effective_step, wall_threshold_usd=wall_threshold_usd,
            price_range=price_range,
            aggregation_mode=range_mode,
            current_price=(float(mid) if isinstance(mid, (int, float)) and mid > 0 else None),
        )
        st["frames"].append(frame)
        if len(st["frames"]) > max_frames:
            del st["frames"][: len(st["frames"]) - max_frames]

        if info is not None and price_range is not None:
            st["range_meta"] = {
                "mode":                info["mode"],
                "min":                 info["min"],
                "max":                 info["max"],
                "abs":                 info["abs"],
                "pct":                 info["pct"],
                "available_depth_min": frame.get("available_depth_min"),
                "available_depth_max": frame.get("available_depth_max"),
            }

    # Bootstrap each symbol with one initial REST snapshot, then stamp a
    # shared last_depth_refresh so the first periodic refresh is on the
    # same clock for every symbol.
    for sym in symbols:
        try:
            _refresh_depth(sym)
        except Exception as exc:                # pragma: no cover - defensive
            _say(f"bootstrap failed [{sym}]: {exc}")
    t0 = now()
    for sym in symbols:
        states[sym]["last_depth_refresh"] = t0

    try:
        should_stop = False
        for raw in message_iter:
            # One clock read per iteration so injected test clocks tick
            # predictably and so the timing gates use a single monotonic value.
            t = now()
            if raw is not None:
                messages += 1
                parsed = parse_book_ticker(raw)
                if parsed is not None:
                    # Route bookTicker updates to the matching per-symbol
                    # state. If `symbol` is missing (legacy single-stream
                    # format that omits `s`), assume the first configured
                    # symbol — single-symbol mode behaves identically.
                    sym = parsed.get("symbol") or symbols[0]
                    st = states.get(sym)
                    if st is not None:
                        st["best_bid"] = parsed["bestBid"]
                        st["best_ask"] = parsed["bestAsk"]
                        st["mid"] = round(
                            (parsed["bestBid"] + parsed["bestAsk"]) / 2.0, 2,
                        )
                        st["last_event_at"] = t

            for sym in symbols:
                st = states[sym]

                # Periodic depth refresh (REST keeps cells alive).
                if t - st["last_depth_refresh"] >= depth_refresh_seconds:
                    _refresh_depth(sym)
                    st["last_depth_refresh"] = t

                # Periodic write — gated by write_interval and "have-data".
                ready = (
                    st["mid"] is not None and st["frames"]
                    and (t - st["last_write"]) >= write_interval
                )
                if not ready:
                    continue

                ts_iso = datetime.now(timezone.utc).isoformat()
                st["price_path"].append({
                    "t":       ts_iso,
                    "price":   st["mid"],
                    "bestBid": st["best_bid"],
                    "bestAsk": st["best_ask"],
                })
                if len(st["price_path"]) > max_frames:
                    del st["price_path"][: len(st["price_path"]) - max_frames]

                # Refresh range_meta against the LATEST mid so the canvas
                # axis tracks price drift between depth refreshes.
                latest_range_meta = st["range_meta"]
                info = _resolve_range_for(sym, st["mid"])
                if info is not None:
                    avail = (latest_range_meta or {})
                    latest_range_meta = {
                        "mode":                info["mode"],
                        "min":                 info["min"],
                        "max":                 info["max"],
                        "abs":                 info["abs"],
                        "pct":                 info["pct"],
                        "available_depth_min": avail.get("available_depth_min"),
                        "available_depth_max": avail.get("available_depth_max"),
                    }
                    st["range_meta"] = latest_range_meta

                for tf in timeframes:
                    payload = build_ws_payload(
                        sym, tf, st["frames"], st["price_path"], write_interval,
                        range_meta=latest_range_meta,
                    )
                    for kind in write_targets:
                        try:
                            if kind == "supabase":
                                assert supabase is not None
                                upsert(supabase, sym, tf, payload)
                            elif kind == "live":
                                write_payload_atomic(payload, output_for(sym, tf))
                        except (RuntimeError, OSError) as exc:
                            _say(f"write {kind} · {sym} {tf} · failed: {exc}")

                st["writes"]  += 1
                st["last_write"] = t
                total_writes  += 1
                _say(
                    f"write #{total_writes} · {sym} · tfs={','.join(timeframes)} · "
                    f"mid={st['mid']} · msgs={messages} · "
                    f"frames={len(st['frames'])} · pricePath={len(st['price_path'])}"
                )

                if not forever and samples is not None and total_writes >= samples:
                    should_stop = True
                    break
            if should_stop:
                break
    except KeyboardInterrupt:
        _say("interrupted — stopping cleanly, last writes kept")

    return {
        "writes":     total_writes,
        "messages":   messages,
        "per_symbol": {sym: states[sym]["writes"] for sym in symbols},
    }


# ── CLI ───────────────────────────────────────────────────────────────────────

def _split_list(raw: str) -> list[str]:
    return [p.strip() for p in raw.split(",") if p.strip()]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="run_binance_ws_heatmap_live",
        description="WebSocket-based MVP collector for one Binance Spot symbol.",
    )
    parser.add_argument("--symbol", default=DEFAULT_SYMBOL,
                        help=(f"Single symbol (default: {DEFAULT_SYMBOL}). "
                              f"Ignored when --symbols is set."))
    parser.add_argument("--symbols", default=None,
                        help=("Comma-separated symbols, e.g. "
                              "BTCUSDT,ETHUSDT,SOLUSDT. When set, subscribes "
                              "to a combined Binance bookTicker stream."))
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
    parser.add_argument("--depth-limit", type=int, default=None,
                        dest="depth_limit",
                        help=("Binance depth API limit. Defaults to 1000; "
                              "auto-bumped to 5000 for --range-mode wide/macro "
                              "so the wider y-axis actually carries far levels."))
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
    # LM43: analysis-grade price range presets.
    parser.add_argument("--range-mode", default="standard",
                        choices=VALID_RANGE_MODES, dest="range_mode",
                        help=("Heatmap price-range preset: tight | standard | "
                              "wide | macro (default: standard)."))
    parser.add_argument("--price-range-abs", type=float, default=None,
                        dest="price_range_abs",
                        help="Override preset with absolute USD half-range.")
    parser.add_argument("--price-range-percent", type=float, default=None,
                        dest="price_range_percent",
                        help="Override preset with percent half-range (e.g. 0.05).")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    # LM42B: --symbols (CSV) wins; fall back to --symbol for backward compat.
    if args.symbols:
        symbols = [s.upper() for s in _split_list(args.symbols)]
    else:
        symbols = [args.symbol.upper()]

    if not symbols:
        print("error: invalid argument — no symbols resolved", file=sys.stderr)
        return 1
    for sym in symbols:
        if not is_valid_binance_symbol(sym):
            print(
                f"error: invalid argument — invalid Binance symbol {sym!r} "
                f"(expect A-Z/0-9, 3-12 chars)",
                file=sys.stderr,
            )
            return 1

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
    stream_label = "single" if len(symbols) == 1 else f"combined×{len(symbols)}"
    print(
        "run_binance_ws_heatmap_live startup:\n"
        f"  mode               = {mode_label}\n"
        f"  symbols            = {', '.join(symbols)}\n"
        f"  timeframes         = {', '.join(timeframes)}\n"
        f"  target             = {args.target}\n"
        f"  write interval     = {args.write_interval}s\n"
        f"  depth refresh      = {args.depth_refresh}s\n"
        f"  max frames         = {args.max_frames}\n"
        f"  collector          = {COLLECTOR_TAG} ({stream_label} stream)\n"
        f"  supabase           = "
        f"{'configured' if sb_cfg is not None else 'not configured'}\n"
        f"  range mode         = {args.range_mode}"
        f"{f' (abs=±{args.price_range_abs})' if args.price_range_abs else ''}"
        f"{f' (pct=±{args.price_range_percent})' if args.price_range_percent else ''}",
        flush=True,
    )

    url = build_ws_url(symbols)
    progress = lambda m: print(f"  {m}", flush=True)  # noqa: E731
    msg_iter = _default_ws_messages_with_reconnect(url, progress=progress)

    # LM43B: wide/macro want deeper books than the default 1000 levels so
    # the wider y-axis actually carries data far from mid. Explicit
    # --depth-limit always wins.
    if args.depth_limit is not None:
        effective_depth_limit = args.depth_limit
    elif args.range_mode in ("wide", "macro"):
        effective_depth_limit = 5000
    else:
        effective_depth_limit = DEFAULT_DEPTH_LIMIT

    try:
        result = run_ws_collector(
            symbols=symbols,
            timeframes=timeframes,
            write_interval=args.write_interval,
            max_frames=args.max_frames,
            target=args.target,
            supabase=sb_cfg,
            output_for=output_for,
            message_iter=msg_iter,
            depth_limit=effective_depth_limit,
            depth_refresh_seconds=args.depth_refresh,
            price_step=args.price_step,
            wall_threshold_usd=args.wall_threshold,
            samples=args.samples,
            forever=args.forever,
            progress=progress,
            range_mode=args.range_mode,
            price_range_abs=args.price_range_abs,
            price_range_percent=args.price_range_percent,
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
