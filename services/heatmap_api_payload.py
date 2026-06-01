"""
services/heatmap_api_payload.py
---------------------------------
Converts a heatmap matrix into a frontend/API-ready JSON payload.

No API calls, no Supabase writes, no external dependencies.

Public API:
    build_heatmap_api_payload(matrix, timeframe, exchange) -> dict
    build_demo_heatmap_api_payload(symbol, timeframe)      -> dict
    validate_heatmap_api_payload(payload)                  -> bool
"""

from __future__ import annotations

from datetime import datetime, timezone

from services.heatmap_matrix_builder import (
    build_heatmap_matrix,
    compress_heatmap_matrix,
    summarize_heatmap_matrix,
)

VALID_TIMEFRAMES = {"5m", "15m", "1h", "4h", "1d"}


# ── build_heatmap_api_payload ─────────────────────────────────────────────────

def build_heatmap_api_payload(
    matrix: dict,
    timeframe: str = "5m",
    exchange: str = "binance_spot",
    price_path: list | None = None,
    current_price: float | None = None,
) -> dict:
    """
    Convert a built heatmap matrix into a frontend-ready API payload.

    Args:
        matrix:        Result of build_heatmap_matrix().
        timeframe:     Candle timeframe label. Must be one of VALID_TIMEFRAMES.
        exchange:      Exchange identifier string.
        price_path:    Optional list of price points (one per time bucket), each
                       a dict like {"t": iso, "price": mid, "bestBid": ...,
                       "bestAsk": ...}. When provided it is included as
                       payload["pricePath"]; otherwise the key is omitted and
                       older consumers keep working unchanged.
        current_price: Optional latest mid price. When provided it is stamped
                       into summary.currentPrice and meta.currentPrice.

    Returns:
        Dict suitable for JSON serialisation and canvas rendering.

    Raises:
        TypeError:  If matrix is not a dict.
        ValueError: If timeframe is not in VALID_TIMEFRAMES.
    """
    if not isinstance(matrix, dict):
        raise TypeError(f"matrix must be a dict, got {type(matrix).__name__!r}")
    if timeframe not in VALID_TIMEFRAMES:
        raise ValueError(
            f"Invalid timeframe {timeframe!r}. Must be one of: {', '.join(sorted(VALID_TIMEFRAMES))}"
        )

    compressed = compress_heatmap_matrix(matrix)
    summary    = summarize_heatmap_matrix(matrix)
    cells      = compressed.get("cells", [])
    walls      = compressed.get("walls", [])

    payload = {
        "symbol":      matrix.get("symbol") or "UNKNOWN",
        "exchange":    exchange,
        "timeframe":   timeframe,
        "priceMin":    compressed.get("priceMin"),
        "priceMax":    compressed.get("priceMax"),
        "priceStep":   compressed.get("priceStep", 0.0),
        "timeBuckets": compressed.get("timeBuckets", []),
        "cells":       cells,
        "walls":       walls,
        "summary":     summary,
        "meta": {
            "schemaVersion": "1.0",
            "generatedAt":   datetime.now(timezone.utc).isoformat(),
            "cellCount":     len(cells),
            "wallCount":     len(walls),
            "isDemo":        False,
        },
    }

    # Optional price-path overlay — only added when provided so existing
    # payloads/consumers stay unchanged.
    if price_path is not None:
        payload["pricePath"] = price_path
    if current_price is not None:
        payload["summary"]["currentPrice"] = current_price
        payload["meta"]["currentPrice"] = current_price

    return payload


# ── build_demo_heatmap_api_payload ────────────────────────────────────────────

def build_demo_heatmap_api_payload(
    symbol: str = "BTCUSDT",
    timeframe: str = "5m",
) -> dict:
    """
    Build a small synthetic demo payload for UI/canvas testing.

    No real API calls. Uses a hardcoded miniature orderbook to produce a
    realistic-looking but entirely fake heatmap.

    Args:
        symbol:    Trading pair label embedded in the payload.
        timeframe: Timeframe label (validated against VALID_TIMEFRAMES).

    Returns:
        Payload dict with meta.isDemo == True.
    """
    def _lvl(price: float, qty: float) -> dict:
        return {"price": price, "quantity": qty, "usd": round(price * qty, 2)}

    demo_frames = [
        {
            "symbol": symbol,
            "captured_at": "2026-06-01T12:00:00+00:00",
            "price_step": 10.0,
            "buckets": [],
            "walls": [],
        },
        {
            "symbol": symbol,
            "captured_at": "2026-06-01T12:05:00+00:00",
            "price_step": 10.0,
            "buckets": [],
            "walls": [],
        },
    ]

    # Use the bucketer inline to avoid circular imports — build buckets manually
    # so this module stays self-contained without importing the bucketer.
    from services.orderbook_depth_bucketer import build_heatmap_cells

    snap1 = {
        "symbol": symbol,
        "captured_at": "2026-06-01T12:00:00+00:00",
        "bids": [_lvl(67420.0, 5.0), _lvl(67410.0, 10.0), _lvl(67400.0, 20.0)],
        "asks": [_lvl(67430.0, 4.0), _lvl(67440.0, 8.0),  _lvl(67450.0, 15.0)],
    }
    snap2 = {
        "symbol": symbol,
        "captured_at": "2026-06-01T12:05:00+00:00",
        "bids": [_lvl(67420.0, 7.0), _lvl(67410.0, 12.0), _lvl(67400.0, 25.0)],
        "asks": [_lvl(67430.0, 3.0), _lvl(67440.0, 9.0),  _lvl(67450.0, 18.0)],
    }

    frame1 = build_heatmap_cells(snap1, price_step=10.0, wall_threshold_usd=200_000.0)
    frame2 = build_heatmap_cells(snap2, price_step=10.0, wall_threshold_usd=200_000.0)

    matrix = build_heatmap_matrix([frame1, frame2])
    payload = build_heatmap_api_payload(matrix, timeframe=timeframe)
    payload["meta"]["isDemo"] = True
    return payload


# ── validate_heatmap_api_payload ──────────────────────────────────────────────

_REQUIRED_TOP_LEVEL = {"symbol", "exchange", "timeframe", "cells", "timeBuckets", "walls", "summary", "meta"}
_REQUIRED_META      = {"schemaVersion", "generatedAt", "cellCount", "wallCount", "isDemo"}


def validate_heatmap_api_payload(payload: dict) -> bool:
    """
    Return True if payload contains all required fields, False otherwise.

    Checks:
    - All top-level required keys present
    - cells is a list
    - timeBuckets is a list
    - meta.schemaVersion present
    """
    if not isinstance(payload, dict):
        return False
    if not _REQUIRED_TOP_LEVEL.issubset(payload.keys()):
        return False
    if not isinstance(payload.get("cells"), list):
        return False
    if not isinstance(payload.get("timeBuckets"), list):
        return False
    meta = payload.get("meta")
    if not isinstance(meta, dict):
        return False
    if not _REQUIRED_META.issubset(meta.keys()):
        return False
    return True
