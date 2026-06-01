"""
connectors/binance_depth_collector.py
--------------------------------------
Binance Spot REST depth snapshot collector for the Liquidity Map pipeline.

Fetches a full orderbook depth snapshot from Binance, normalises levels to
typed dicts with pre-computed USD size, and exposes summary helpers for
wall detection and imbalance scoring.

No WebSocket, no Supabase writes, no secrets required — public endpoint only.

Public API:
    fetch_depth_snapshot(symbol, limit) -> DepthSnapshot
    summarize_snapshot(snapshot)        -> SnapshotSummary
    normalize_depth_levels(levels, side) -> list[DepthLevel]   (also used internally)
    calculate_top_wall(levels)          -> DepthLevel | None

Types (TypedDicts):
    DepthLevel      — one price level with usd value pre-computed
    DepthSnapshot   — full normalised snapshot
    SnapshotSummary — human-readable summary metrics
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Optional

import requests

# ── Constants ─────────────────────────────────────────────────────────────────

_BASE_URL = "https://api.binance.com"
_DEPTH_ENDPOINT = "/api/v3/depth"
_DEFAULT_TIMEOUT = 8  # seconds

# Binance only accepts these specific limit values for /api/v3/depth
VALID_LIMITS = (100, 500, 1000, 5000)


# ── Exceptions ────────────────────────────────────────────────────────────────

class DepthCollectorError(Exception):
    """Raised when the depth snapshot fetch fails unrecoverably."""

    def __init__(self, message: str, status_code: Optional[int] = None, endpoint: str = "") -> None:
        super().__init__(message)
        self.status_code = status_code
        self.endpoint = endpoint

    def __str__(self) -> str:
        parts = [super().__str__()]
        if self.status_code is not None:
            parts.append(f"(HTTP {self.status_code})")
        if self.endpoint:
            parts.append(f"[{self.endpoint}]")
        return " ".join(parts)


class RateLimitError(DepthCollectorError):
    """Raised when Binance returns HTTP 429."""


# ── Types (plain dicts — no dataclass overhead, compatible with JSON) ─────────

class DepthLevel(dict):
    """
    A single price level on one side of the orderbook.

    Keys:
        price    (float) — price in quote currency (USDT)
        quantity (float) — base asset quantity (BTC)
        usd      (float) — price * quantity, pre-computed for performance
    """


class DepthSnapshot(dict):
    """
    Full normalised snapshot returned by fetch_depth_snapshot().

    Keys:
        symbol         (str)
        last_update_id (int)
        bids           (list[DepthLevel]) — sorted best→worst (high→low price)
        asks           (list[DepthLevel]) — sorted best→worst (low→high price)
        captured_at    (str)              — ISO 8601 UTC timestamp
    """


class SnapshotSummary(dict):
    """
    Compact summary of a snapshot, suitable for display or alerts.

    Keys:
        best_bid      (float)
        best_ask      (float)
        spread        (float)
        spread_pct    (float)
        total_bid_usd (float)
        total_ask_usd (float)
        top_bid_wall  (DepthLevel | None)
        top_ask_wall  (DepthLevel | None)
        imbalance     (float)  — bid_usd / (bid_usd + ask_usd), 0.0–1.0
    """


# ── Internal helpers ──────────────────────────────────────────────────────────

def _validate_symbol(symbol: str) -> str:
    """Return uppercased symbol or raise ValueError for obviously bad input."""
    cleaned = symbol.strip().upper()
    if not cleaned or not cleaned.isalnum():
        raise ValueError(f"Invalid symbol: {symbol!r}. Must be alphanumeric (e.g. 'BTCUSDT').")
    return cleaned


def _validate_limit(limit: int) -> None:
    """Raise ValueError if limit is not an accepted Binance depth limit."""
    if limit not in VALID_LIMITS:
        raise ValueError(
            f"Invalid depth limit: {limit}. "
            f"Binance accepts only: {', '.join(str(v) for v in VALID_LIMITS)}."
        )


# ── Public helpers ────────────────────────────────────────────────────────────

def normalize_depth_levels(
    raw_levels: list[list[str]],
    side: str,
) -> list[DepthLevel]:
    """
    Convert Binance raw level tuples to typed DepthLevel dicts.

    Args:
        raw_levels: List of [price_str, qty_str] pairs from Binance JSON.
        side:       "bid" or "ask" — used only for documentation; does not
                    affect sort order (caller is responsible for ordering).

    Returns:
        List of DepthLevel dicts with float price, quantity, and usd fields.
        Levels with zero quantity are excluded (Binance uses qty=0 to signal
        a level deletion in diff streams).
    """
    if side not in ("bid", "ask"):
        raise ValueError(f"side must be 'bid' or 'ask', got {side!r}")

    result: list[DepthLevel] = []
    for raw in raw_levels:
        try:
            price = float(raw[0])
            qty   = float(raw[1])
        except (IndexError, ValueError) as exc:
            raise DepthCollectorError(f"Malformed depth level {raw!r}: {exc}") from exc

        if qty == 0.0:
            continue  # deleted level in diff stream, skip

        level = DepthLevel(price=price, quantity=qty, usd=round(price * qty, 2))
        result.append(level)

    return result


def calculate_top_wall(levels: list[DepthLevel]) -> Optional[DepthLevel]:
    """
    Return the single level with the highest USD size, or None if empty.

    This is the dominant resting wall on the given side — the price level
    where the largest USD order sits.
    """
    if not levels:
        return None
    return max(levels, key=lambda lv: lv["usd"])


def summarize_snapshot(snapshot: DepthSnapshot) -> SnapshotSummary:
    """
    Compute display-ready summary metrics from a normalised snapshot.

    Args:
        snapshot: Result of fetch_depth_snapshot().

    Returns:
        SnapshotSummary with spread, totals, top walls, and imbalance ratio.

    Raises:
        DepthCollectorError: If the snapshot has no bids or no asks.
    """
    bids: list[DepthLevel] = snapshot["bids"]
    asks: list[DepthLevel] = snapshot["asks"]

    if not bids:
        raise DepthCollectorError("Snapshot has no bid levels — cannot summarize.")
    if not asks:
        raise DepthCollectorError("Snapshot has no ask levels — cannot summarize.")

    best_bid = bids[0]["price"]   # bids sorted high→low
    best_ask = asks[0]["price"]   # asks sorted low→high
    spread   = round(best_ask - best_bid, 8)
    spread_pct = round((spread / best_bid) * 100, 6) if best_bid > 0 else 0.0

    total_bid_usd = round(sum(lv["usd"] for lv in bids), 2)
    total_ask_usd = round(sum(lv["usd"] for lv in asks), 2)

    total_usd = total_bid_usd + total_ask_usd
    imbalance = round(total_bid_usd / total_usd, 6) if total_usd > 0 else 0.5

    return SnapshotSummary(
        best_bid=best_bid,
        best_ask=best_ask,
        spread=spread,
        spread_pct=spread_pct,
        total_bid_usd=total_bid_usd,
        total_ask_usd=total_ask_usd,
        top_bid_wall=calculate_top_wall(bids),
        top_ask_wall=calculate_top_wall(asks),
        imbalance=imbalance,
    )


# ── Main public function ──────────────────────────────────────────────────────

def fetch_depth_snapshot(
    symbol: str = "BTCUSDT",
    limit: int = 1000,
    *,
    timeout: int = _DEFAULT_TIMEOUT,
) -> DepthSnapshot:
    """
    Fetch and normalise a Binance Spot orderbook depth snapshot.

    Hits GET /api/v3/depth with the given symbol and limit.  No authentication
    required — this is a public endpoint.

    Args:
        symbol:  Trading pair, e.g. "BTCUSDT". Case-insensitive; normalised
                 to uppercase before the request.
        limit:   Number of depth levels per side. Must be one of
                 100, 500, 1000, 5000.  Higher values increase response size
                 and latency; 1000 is a reasonable default.
        timeout: HTTP request timeout in seconds.

    Returns:
        DepthSnapshot dict with normalised bids/asks sorted best-first and
        usd field pre-computed on every level.

    Raises:
        ValueError:          symbol is invalid or limit is not accepted.
        RateLimitError:      Binance returned HTTP 429.
        DepthCollectorError: Any other HTTP error or malformed response.
    """
    symbol = _validate_symbol(symbol)
    _validate_limit(limit)

    url = f"{_BASE_URL}{_DEPTH_ENDPOINT}"
    params = {"symbol": symbol, "limit": limit}

    try:
        resp = requests.get(url, params=params, timeout=timeout)
    except requests.exceptions.Timeout as exc:
        raise DepthCollectorError(
            f"Request timed out after {timeout}s fetching depth for {symbol}.",
            endpoint=url,
        ) from exc
    except requests.exceptions.RequestException as exc:
        raise DepthCollectorError(
            f"Network error fetching depth for {symbol}: {exc}",
            endpoint=url,
        ) from exc

    if resp.status_code == 429:
        raise RateLimitError(
            f"Rate limit exceeded fetching depth for {symbol}.",
            status_code=429,
            endpoint=url,
        )

    if not resp.ok:
        raise DepthCollectorError(
            f"Binance API error for {symbol}: {resp.text[:200]}",
            status_code=resp.status_code,
            endpoint=url,
        )

    try:
        data = resp.json()
    except ValueError as exc:
        raise DepthCollectorError(
            f"Failed to parse JSON response for {symbol}: {exc}",
            endpoint=url,
        ) from exc

    if "lastUpdateId" not in data:
        raise DepthCollectorError(
            f"Unexpected response shape for {symbol} — missing 'lastUpdateId'.",
            endpoint=url,
        )

    # Bids: sorted high→low price (best bid first)
    bids = sorted(
        normalize_depth_levels(data.get("bids", []), "bid"),
        key=lambda lv: lv["price"],
        reverse=True,
    )

    # Asks: sorted low→high price (best ask first)
    asks = sorted(
        normalize_depth_levels(data.get("asks", []), "ask"),
        key=lambda lv: lv["price"],
    )

    return DepthSnapshot(
        symbol=symbol,
        last_update_id=int(data["lastUpdateId"]),
        bids=bids,
        asks=asks,
        captured_at=datetime.now(timezone.utc).isoformat(),
    )
