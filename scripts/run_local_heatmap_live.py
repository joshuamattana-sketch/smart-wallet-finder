"""
scripts/run_local_heatmap_live.py
-----------------------------------
Local dev "live" mode for the Lumora Liquidity Map.

Repeatedly collects real Binance Spot depth snapshots and continuously rewrites
one or more web fixture files. Paired with the Liquidity Map UI's fixture
auto-refresh, this makes the map feel live — entirely locally, with no Supabase,
no production worker, and no WebSocket.

It keeps a rolling window of the most recent frames (--max-frames) per symbol so
each fixture stays a fixed size while always reflecting the latest book.

Single symbol / timeframe (backward compatible):
    python scripts/run_local_heatmap_live.py \
        --symbol BTCUSDT --timeframe 5m \
        --output lumora-web/fixtures/heatmap/BTCUSDT_5m.json

Multi symbol / multi timeframe:
    python scripts/run_local_heatmap_live.py \
        --symbols BTCUSDT,ETHUSDT,SOLUSDT --timeframes 5m,15m,1h \
        --samples 120 --interval 2 --max-frames 60
    # writes lumora-web/fixtures/heatmap/{SYMBOL}_{timeframe}.json for every pair

Stop early any time with Ctrl+C — the last written fixtures stay in place.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
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
from services.heatmap_api_payload import (  # noqa: E402
    VALID_TIMEFRAMES,
    build_heatmap_api_payload,
)

SOURCE_TAG = "local_live_fixture"
EXCHANGE = "binance_spot"
DEFAULT_WALL_THRESHOLD_USD = 1_000_000.0
DEFAULT_OUTPUT_DIR = "lumora-web/fixtures/heatmap"

# Sensible per-symbol price-bucket widths (USD). Used when --price-step is not
# given. Falls back to FALLBACK_PRICE_STEP for unknown symbols.
DEFAULT_PRICE_STEPS = {
    "BTCUSDT": 10.0,
    "ETHUSDT": 5.0,
    "SOLUSDT": 0.5,
}
FALLBACK_PRICE_STEP = 1.0


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


def _split_list(raw: str) -> list[str]:
    """Split a comma-separated CLI value into trimmed, non-empty parts."""
    return [part.strip() for part in raw.split(",") if part.strip()]


def parse_price_steps(raw: str | None) -> dict[str, float]:
    """
    Parse `--price-steps SYMBOL:step,SYMBOL:step` into a {SYMBOL: float} map.

    Raises ValueError on a malformed entry.
    """
    if not raw:
        return {}
    out: dict[str, float] = {}
    for part in _split_list(raw):
        if ":" not in part:
            raise ValueError(
                f"invalid --price-steps entry {part!r}, expected SYMBOL:step"
            )
        sym, val = part.split(":", 1)
        try:
            out[sym.strip().upper()] = float(val.strip())
        except ValueError as exc:
            raise ValueError(f"invalid price step in {part!r}: {exc}") from exc
    return out


def resolve_price_step(
    symbol: str,
    global_step: float | None,
    steps_map: dict[str, float],
) -> float:
    """
    Resolve the price step for a symbol.

    Precedence: explicit per-symbol map > global --price-step > per-symbol
    default > FALLBACK_PRICE_STEP.
    """
    sym = symbol.upper()
    if sym in steps_map:
        return steps_map[sym]
    if global_step is not None:
        return global_step
    return DEFAULT_PRICE_STEPS.get(sym, FALLBACK_PRICE_STEP)


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
    symbol: str | None = None,
    *,
    active_symbol: str | None = None,
    update_mode: str = "standard",
    effective_interval: float | None = None,
    is_active: bool = False,
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

    if symbol:
        payload["symbol"] = symbol

    meta = payload["meta"]
    meta["isDemo"] = False
    meta["source"] = SOURCE_TAG
    meta["dataSource"] = SOURCE_TAG
    meta["symbol"] = symbol or payload.get("symbol")
    meta["timeframe"] = timeframe
    meta["sampleCount"] = sample_count
    meta["intervalSeconds"] = interval
    meta["maxFrames"] = max_frames
    meta["liveUpdatedAt"] = datetime.now(timezone.utc).isoformat()
    # Active-market fast mode metadata.
    meta["activeSymbol"] = active_symbol
    meta["updateMode"] = update_mode
    meta["effectiveIntervalSeconds"] = (
        effective_interval if effective_interval is not None else interval
    )
    meta["isActiveSymbol"] = is_active
    return payload


def run_live_multi(
    symbols: list[str],
    timeframes: list[str],
    price_steps: dict[str, float],
    limit: int,
    samples: int,
    interval: float,
    max_frames: int,
    output_for,
    wall_threshold_usd: float = DEFAULT_WALL_THRESHOLD_USD,
    progress=None,
    active_symbol: str | None = None,
    active_interval: float | None = None,
    background_interval: float | None = None,
) -> dict:
    """
    Run the multi-symbol / multi-timeframe live collection loop.

    Per tick, each due symbol is fetched once; its rolling frame window feeds a
    fixture file for every requested timeframe (same frames, per-timeframe
    metadata). `output_for(symbol, timeframe) -> Path` decides the target file.

    Active-market fast mode: when `active_symbol` is set, the loop ticks at
    `active_interval`; the active symbol is updated every tick while background
    symbols are updated only every `background_interval` (rounded to whole
    ticks). Without `active_symbol`, every symbol updates every `interval`
    (legacy behaviour).

    Returns {"total": int, "per_symbol": {sym: int}} of successful samples.

    Raises ValueError for invalid arguments. Per-symbol fetch failures are
    caught so other symbols keep running.
    """
    if not symbols:
        raise ValueError("at least one symbol is required")
    if not timeframes:
        raise ValueError("at least one timeframe is required")
    if samples <= 0:
        raise ValueError(f"samples must be > 0, got {samples}")
    if interval <= 0:
        raise ValueError(f"interval must be > 0, got {interval}")
    if max_frames <= 0:
        raise ValueError(f"max-frames must be > 0, got {max_frames}")
    for tf in timeframes:
        if tf not in VALID_TIMEFRAMES:
            raise ValueError(
                f"invalid timeframe {tf!r}. Allowed: {', '.join(sorted(VALID_TIMEFRAMES))}"
            )

    # ── Resolve update schedule ─────────────────────────────────────────────
    active = active_symbol.upper() if active_symbol else None
    if active is not None:
        if active not in symbols:
            raise ValueError(
                f"active-symbol {active!r} is not in symbols {symbols}"
            )
        if active_interval is None or active_interval <= 0:
            raise ValueError(f"active-interval must be > 0, got {active_interval}")
        if background_interval is None or background_interval <= 0:
            raise ValueError(f"background-interval must be > 0, got {background_interval}")
        tick_interval = active_interval
        # How many fast ticks pass between background updates.
        bg_every = max(1, round(background_interval / active_interval))
        eff_interval = {
            sym: (active_interval if sym == active else background_interval)
            for sym in symbols
        }
    else:
        tick_interval = interval
        bg_every = 1
        eff_interval = {sym: interval for sym in symbols}

    def _is_due(sym: str, tick: int) -> bool:
        if active is None or sym == active:
            return True               # legacy mode, or the active symbol → every tick
        return tick % bg_every == 0   # background symbol → every bg_every ticks

    # Per-symbol rolling state.
    state: dict[str, dict] = {
        sym: {"frames": [], "price_path": [], "last_ts": None, "success": 0}
        for sym in symbols
    }
    total_success = 0

    def _process_symbol(sym: str, snapshot: dict) -> None:
        """Update a symbol's rolling state and write one fixture per timeframe."""
        nonlocal total_success
        st = state[sym]
        ts = _next_timestamp(st["last_ts"])
        st["last_ts"] = ts
        ts_iso = ts.isoformat()
        snapshot["captured_at"] = ts_iso

        step = resolve_price_step(sym, None, price_steps)
        frame = build_heatmap_cells(
            snapshot, price_step=step, wall_threshold_usd=wall_threshold_usd,
        )
        st["frames"].append(frame)

        point = _price_point(snapshot, ts_iso)
        if point is not None:
            st["price_path"].append(point)

        if len(st["frames"]) > max_frames:
            st["frames"] = st["frames"][-max_frames:]
        if len(st["price_path"]) > max_frames:
            st["price_path"] = st["price_path"][-max_frames:]

        st["success"] += 1
        total_success += 1

        is_active = active is not None and sym == active
        update_mode = "active_fast" if is_active else "standard"

        # One fixture file per timeframe — all built from the same snapshot/frame.
        for tf in timeframes:
            payload = build_live_payload(
                st["frames"], tf, tick_interval, max_frames,
                st["success"], st["price_path"], symbol=sym,
                active_symbol=active,
                update_mode=update_mode,
                effective_interval=eff_interval[sym],
                is_active=is_active,
            )
            write_payload_atomic(payload, output_for(sym, tf))

    try:
        for i in range(samples):
            tick_start = time.monotonic()

            due = [sym for sym in symbols if _is_due(sym, i)]
            skipped = [sym for sym in symbols if sym not in due]

            # Fetch only the due symbols in parallel. Each symbol's failure is
            # captured independently so the others still proceed.
            snapshots: dict[str, dict] = {}
            if due:
                with ThreadPoolExecutor(max_workers=max(1, len(due))) as pool:
                    futures = {
                        pool.submit(fetch_depth_snapshot, sym, limit): sym
                        for sym in due
                    }
                    for fut in as_completed(futures):
                        sym = futures[fut]
                        try:
                            snapshots[sym] = fut.result()
                        except (DepthCollectorError, ValueError) as exc:
                            if progress is not None:
                                progress(f"sample {i + 1}/{samples} · {sym} fetch failed: {exc}")

            # Process results sequentially so per-symbol state stays single-threaded.
            updated: list[str] = []
            for sym in due:
                snapshot = snapshots.get(sym)
                if snapshot is None:
                    continue
                try:
                    _process_symbol(sym, snapshot)
                    updated.append(sym)
                except (ValueError, KeyError) as exc:
                    if progress is not None:
                        progress(f"sample {i + 1}/{samples} · {sym} build failed: {exc}")

            tick_dur = time.monotonic() - tick_start
            remaining = max(0.0, tick_interval - tick_dur)
            if progress is not None:
                active_note = f"active {active}" if active else "no active symbol"
                progress(
                    f"tick {i + 1}/{samples} · {active_note} · "
                    f"updated [{', '.join(updated) or '-'}] · "
                    f"skipped [{', '.join(skipped) or '-'}] · "
                    f"dur {tick_dur:.2f}s · sleep {remaining:.2f}s"
                )

            # Sleep only the remaining time; if a tick already ran past the tick
            # interval, start the next one immediately.
            if i < samples - 1 and remaining > 0:
                time.sleep(remaining)
    except KeyboardInterrupt:
        if progress is not None:
            progress("interrupted — stopping, last fixtures kept")

    return {
        "total": total_success,
        "per_symbol": {sym: state[sym]["success"] for sym in symbols},
    }


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
    Backward-compatible single symbol / timeframe entry point.

    Delegates to run_live_multi for one pair, writing to `output`. Returns the
    number of successful samples collected.
    """
    sym = symbol.upper()
    result = run_live_multi(
        symbols=[sym],
        timeframes=[timeframe],
        price_steps={sym: price_step},
        limit=limit,
        samples=samples,
        interval=interval,
        max_frames=max_frames,
        output_for=lambda _s, _t: Path(output),
        wall_threshold_usd=wall_threshold_usd,
        progress=progress,
    )
    return result["total"]


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="run_local_heatmap_live",
        description="Local live mode: continuously rewrite heatmap web fixtures from real Binance depth.",
    )
    parser.add_argument("--symbol", default="BTCUSDT",
                        help="Single symbol (default: BTCUSDT). Ignored when --symbols is set.")
    parser.add_argument("--symbols", default=None,
                        help="Comma-separated symbols, e.g. BTCUSDT,ETHUSDT,SOLUSDT.")
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--price-step", type=float, default=None, dest="price_step",
                        help="Global price step override applied to all symbols.")
    parser.add_argument("--price-steps", default=None, dest="price_steps",
                        help="Per-symbol override, e.g. BTCUSDT:10,ETHUSDT:5,SOLUSDT:0.5.")
    parser.add_argument("--timeframe", default="5m",
                        help="Single timeframe (default: 5m). Ignored when --timeframes is set.")
    parser.add_argument("--timeframes", default=None,
                        help="Comma-separated timeframes, e.g. 5m,15m,1h.")
    parser.add_argument("--samples", type=int, default=120)
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--active-symbol", default=None, dest="active_symbol",
                        help="Symbol to update on the fast cadence; others go to background.")
    parser.add_argument("--active-interval", type=float, default=2.0, dest="active_interval",
                        help="Fast cadence (s) for the active symbol (default: 2).")
    parser.add_argument("--background-interval", type=float, default=10.0, dest="background_interval",
                        help="Slow cadence (s) for non-active symbols (default: 10).")
    parser.add_argument("--max-frames", type=int, default=60, dest="max_frames")
    parser.add_argument("--wall-threshold", type=float,
                        default=DEFAULT_WALL_THRESHOLD_USD, dest="wall_threshold")
    parser.add_argument("--output", default=None,
                        help="Single output file (only valid for one symbol + one timeframe).")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, dest="output_dir",
                        help="Directory for {SYMBOL}_{timeframe}.json files (multi mode).")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns process exit code (0 ok, 1 on handled error)."""
    args = parse_args(argv)

    try:
        symbols = (
            [s.upper() for s in _split_list(args.symbols)]
            if args.symbols else [args.symbol.upper()]
        )
        timeframes = (
            [t.lower() for t in _split_list(args.timeframes)]
            if args.timeframes else [args.timeframe.lower()]
        )
        steps_map = parse_price_steps(args.price_steps)
        resolved_steps = {
            sym: resolve_price_step(sym, args.price_step, steps_map)
            for sym in symbols
        }
    except ValueError as exc:
        print(f"error: invalid argument — {exc}", file=sys.stderr)
        return 1

    output_dir = Path(args.output_dir)
    single_pair = len(symbols) == 1 and len(timeframes) == 1
    use_explicit_output = single_pair and args.output is not None

    def output_for(sym: str, tf: str) -> Path:
        if use_explicit_output:
            return Path(args.output)
        return output_dir / f"{sym}_{tf}.json"

    active_symbol = args.active_symbol.upper() if args.active_symbol else None

    try:
        result = run_live_multi(
            symbols=symbols,
            timeframes=timeframes,
            price_steps=resolved_steps,
            limit=args.limit,
            samples=args.samples,
            interval=args.interval,
            max_frames=args.max_frames,
            output_for=output_for,
            wall_threshold_usd=args.wall_threshold,
            progress=lambda msg: print(f"  {msg}"),
            active_symbol=active_symbol,
            active_interval=args.active_interval,
            background_interval=args.background_interval,
        )
    except ValueError as exc:
        print(f"error: invalid argument — {exc}", file=sys.stderr)
        return 1

    if result["total"] == 0:
        print("error: no snapshots were collected successfully", file=sys.stderr)
        return 1

    files = len(symbols) * len(timeframes)
    print(
        f"Done. {result['total']} successful sample(s) across "
        f"{len(symbols)} symbol(s) × {len(timeframes)} timeframe(s) "
        f"({files} fixture file(s))."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
