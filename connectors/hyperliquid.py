"""
connectors/hyperliquid.py
--------------------------
Hyperliquid public Info API connector for the Pro Trading Terminal.

Hyperliquid exposes all market data via a single POST endpoint:
    POST https://api.hyperliquid.xyz/info
    Content-Type: application/json
    Body: {"type": "<request_type>", ...params}

No API key required for any endpoint used here.

Reference:
    https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint

Rules:
- No Streamlit imports.
- No API key.
- All requests have explicit timeouts.
- No silent except pass — every error raises a typed exception.
- Returns types from core/models.py where appropriate.
"""

from __future__ import annotations

import re
import time
from typing import Optional

import requests

from core.models import OrderBookLevel, OrderBookSnapshot

# ── Constants ─────────────────────────────────────────────────────────────────

BASE_URL = "https://api.hyperliquid.xyz/info"
EXCHANGE = "Hyperliquid"
DEFAULT_TIMEOUT = 10  # seconds

# Hyperliquid uses short coin names without USDT suffix
# e.g. "BTC", "ETH", "SOL", "HYPE"
_KNOWN_COINS = frozenset({
    "BTC", "ETH", "SOL", "HYPE", "ARB", "OP", "BNB",
    "AVAX", "INJ", "SUI", "APT", "TIA", "SEI", "STRK",
})


# ── Exceptions ────────────────────────────────────────────────────────────────

class HyperliquidError(Exception):
    """
    Base exception for all Hyperliquid connector errors.

    Attributes:
        message:     Human-readable description.
        status_code: HTTP status code if applicable, else None.
        request_type: The Hyperliquid request type that failed.
    """

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        request_type: str = "",
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.request_type = request_type

    def __str__(self) -> str:
        parts = [super().__str__()]
        if self.status_code is not None:
            parts.append(f"(HTTP {self.status_code})")
        if self.request_type:
            parts.append(f"[type={self.request_type}]")
        return " ".join(parts)


class HyperliquidRateLimitError(HyperliquidError):
    """Raised on HTTP 429 from the Hyperliquid Info API."""


class InvalidCoinError(HyperliquidError):
    """Raised when a coin name fails validation before a request is made."""


# ── Input normalisation ───────────────────────────────────────────────────────

def normalize_coin(coin: object) -> str:
    """
    Normalize a coin name for use with the Hyperliquid API.

    Hyperliquid uses short uppercase names without any USDT/USD suffix:
        "BTC", "ETH", "HYPE", "SOL" — not "BTCUSDT" or "BTC-USD".

    Strips whitespace, uppercases, and removes common suffixes and separators.

    Args:
        coin: Any object. Must be a non-empty string after stripping.

    Returns:
        Normalized coin string, e.g. "HYPE", "BTC", "SOL".

    Raises:
        InvalidCoinError: if coin is not a string, empty, or contains
                          characters outside [A-Z0-9].

    Examples:
        >>> normalize_coin("hype")
        'HYPE'
        >>> normalize_coin("BTC/USDT")
        'BTC'
        >>> normalize_coin("  eth-usd  ")
        'ETH'
        >>> normalize_coin("SOLUSDT")
        'SOL'
    """
    if not isinstance(coin, str):
        raise InvalidCoinError(
            f"Coin name must be a string, got {type(coin).__name__}"
        )

    cleaned = coin.strip().upper()

    # Remove known quote currency suffixes
    for suffix in ("USDT", "USD", "USDC", "BUSD", "DAI"):
        if cleaned.endswith(suffix) and len(cleaned) > len(suffix):
            cleaned = cleaned[: -len(suffix)]
            break

    # Remove separators
    cleaned = cleaned.replace("/", "").replace("-", "").replace("_", "")

    if not cleaned:
        raise InvalidCoinError("Coin name cannot be empty after normalisation")

    if not re.match(r"^[A-Z0-9]+$", cleaned):
        raise InvalidCoinError(
            f"Coin name '{cleaned}' contains invalid characters. "
            "Only A-Z and 0-9 are allowed."
        )

    return cleaned


# ── Core HTTP helper ──────────────────────────────────────────────────────────

def post_info(
    payload: dict,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict | list:
    """
    POST a request to the Hyperliquid Info API.

    Args:
        payload: JSON body. Must include a "type" key, e.g.
                 {"type": "l2Book", "coin": "HYPE"}.
        timeout: Request timeout in seconds. Default 10.

    Returns:
        Parsed JSON response (dict or list depending on request type).

    Raises:
        HyperliquidRateLimitError: On HTTP 429.
        HyperliquidError:          On HTTP errors, connection failures,
                                   JSON parse failures, or empty body.

    Example:
        >>> post_info({"type": "allMids"})
        {"BTC": "67420.5", "HYPE": "28.15", ...}
    """
    request_type = str(payload.get("type", "unknown"))

    try:
        response = requests.post(
            BASE_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=timeout,
        )
    except requests.exceptions.Timeout as exc:
        raise HyperliquidError(
            f"Request timed out after {timeout}s",
            request_type=request_type,
        ) from exc
    except requests.exceptions.ConnectionError as exc:
        raise HyperliquidError(
            f"Connection failed: {exc}",
            request_type=request_type,
        ) from exc
    except requests.exceptions.RequestException as exc:
        raise HyperliquidError(
            f"Request failed: {exc}",
            request_type=request_type,
        ) from exc

    if response.status_code == 429:
        raise HyperliquidRateLimitError(
            "Hyperliquid rate limit exceeded. Wait before retrying.",
            status_code=429,
            request_type=request_type,
        )

    if not response.ok:
        _body = response.text[:300] if response.text else "No response body"
        raise HyperliquidError(
            f"Hyperliquid API error: {_body}",
            status_code=response.status_code,
            request_type=request_type,
        )

    if not response.text or not response.text.strip():
        raise HyperliquidError(
            "Empty response body from Hyperliquid API",
            status_code=response.status_code,
            request_type=request_type,
        )

    try:
        return response.json()
    except ValueError as exc:
        raise HyperliquidError(
            f"Failed to parse JSON from Hyperliquid ({request_type}): {exc}",
            status_code=response.status_code,
            request_type=request_type,
        ) from exc


# ── Level parser ──────────────────────────────────────────────────────────────

def _parse_hl_levels(raw: list, side: str) -> list[OrderBookLevel]:
    """
    Parse Hyperliquid l2Book levels into OrderBookLevel objects.

    Hyperliquid level format: {"px": "28.15", "sz": "120.5", "n": 3}
    where n = number of orders at this level.

    Args:
        raw:  List of level dicts from the API.
        side: "bid" or "ask" — used for error context.

    Returns:
        List of OrderBookLevel. Skips zero-price levels silently.

    Raises:
        HyperliquidError: on malformed data.
    """
    if not isinstance(raw, list):
        raise HyperliquidError(
            f"Expected list for {side} levels, got {type(raw).__name__}",
            request_type="l2Book",
        )

    levels: list[OrderBookLevel] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise HyperliquidError(
                f"Malformed {side} level at index {i}: "
                f"expected dict, got {type(item).__name__}: {item!r}",
                request_type="l2Book",
            )
        try:
            price = float(item["px"])
            qty   = float(item["sz"])
        except (KeyError, ValueError, TypeError) as exc:
            raise HyperliquidError(
                f"Cannot parse {side} level at index {i}: {item!r}",
                request_type="l2Book",
            ) from exc

        if price <= 0:
            continue  # skip invalid levels — don't crash

        usd_size = round(price * qty, 6)
        levels.append(OrderBookLevel(price=price, qty=qty, usd_size=usd_size))

    return levels


# ── Public endpoints ──────────────────────────────────────────────────────────

def fetch_l2_book(
    coin: str = "HYPE",
    timeout: int = DEFAULT_TIMEOUT,
) -> OrderBookSnapshot:
    """
    Fetch the current L2 order book for a Hyperliquid perpetual market.

    Endpoint type: "l2Book"
    Response shape:
        {
            "coin": "HYPE",
            "time": 1716200000000,
            "levels": [
                [{"px": "28.15", "sz": "120.5", "n": 3}, ...],  <- bids
                [{"px": "28.20", "sz": "80.2",  "n": 1}, ...],  <- asks
            ]
        }

    Args:
        coin:    Coin name, e.g. "HYPE", "BTC". Will be normalised.
        timeout: HTTP timeout in seconds.

    Returns:
        OrderBookSnapshot with:
        - bids sorted descending (best bid first)
        - asks sorted ascending  (best ask first)
        - usd_size = price * size for every level
        - exchange = "Hyperliquid"
        - symbol = normalised coin name (e.g. "HYPE")

    Raises:
        InvalidCoinError:    if coin fails normalisation.
        HyperliquidError:    on HTTP or parse errors.

    Example:
        >>> snap = fetch_l2_book("HYPE")
        >>> snap.best_bid.price
        28.15
    """
    c = normalize_coin(coin)
    data = post_info({"type": "l2Book", "coin": c}, timeout=timeout)

    if not isinstance(data, dict):
        raise HyperliquidError(
            f"Unexpected l2Book response type: {type(data).__name__}",
            request_type="l2Book",
        )

    levels = data.get("levels")
    if not isinstance(levels, list) or len(levels) < 2:
        raise HyperliquidError(
            f"l2Book response missing valid 'levels' field: {data!r}",
            request_type="l2Book",
        )

    timestamp_ms = int(data.get("time", time.time() * 1000))
    bids = _parse_hl_levels(levels[0], "bid")
    asks = _parse_hl_levels(levels[1], "ask")

    # Ensure correct sort order
    bids.sort(key=lambda lvl: lvl.price, reverse=True)  # descending
    asks.sort(key=lambda lvl: lvl.price)                 # ascending

    mid = 0.0
    if bids and asks:
        mid = (bids[0].price + asks[0].price) / 2.0

    return OrderBookSnapshot(
        symbol=c,
        exchange=EXCHANGE,
        timestamp_ms=timestamp_ms,
        bids=bids,
        asks=asks,
        mid_price=round(mid, 8),
    )


def fetch_meta(timeout: int = DEFAULT_TIMEOUT) -> dict:
    """
    Fetch Hyperliquid universe metadata (all listed perpetual markets).

    Endpoint type: "meta"
    Response shape:
        {
            "universe": [
                {"name": "BTC", "szDecimals": 3, "maxLeverage": 50, ...},
                {"name": "HYPE", "szDecimals": 0, "maxLeverage": 5, ...},
                ...
            ]
        }

    Returns:
        Raw response dict with "universe" list.
        Each item has at minimum "name" (str) and "szDecimals" (int).

    Raises:
        HyperliquidError: on HTTP or parse errors.

    Example:
        >>> meta = fetch_meta()
        >>> [m["name"] for m in meta["universe"][:3]]
        ['BTC', 'ETH', 'HYPE']
    """
    data = post_info({"type": "meta"}, timeout=timeout)

    if not isinstance(data, dict):
        raise HyperliquidError(
            f"Unexpected meta response type: {type(data).__name__}",
            request_type="meta",
        )

    if "universe" not in data:
        raise HyperliquidError(
            f"meta response missing 'universe' field: {data!r}",
            request_type="meta",
        )

    return data


def fetch_all_mids(timeout: int = DEFAULT_TIMEOUT) -> dict[str, float]:
    """
    Fetch mid prices for all Hyperliquid perpetual markets.

    Endpoint type: "allMids"
    Response shape:
        {"BTC": "67420.5", "ETH": "3512.1", "HYPE": "28.15", ...}

    Returns:
        Dict of {coin: mid_price_float}, e.g. {"BTC": 67420.5, "HYPE": 28.15}.
        String prices are converted to float. Unparseable values are skipped.

    Raises:
        HyperliquidError: on HTTP or parse errors.

    Example:
        >>> mids = fetch_all_mids()
        >>> mids["HYPE"]
        28.15
    """
    data = post_info({"type": "allMids"}, timeout=timeout)

    if not isinstance(data, dict):
        raise HyperliquidError(
            f"Unexpected allMids response type: {type(data).__name__}",
            request_type="allMids",
        )

    result: dict[str, float] = {}
    for coin, price_str in data.items():
        try:
            result[str(coin)] = float(price_str)
        except (ValueError, TypeError):
            # Skip unparseable values — don't crash the whole call
            continue

    return result


def fetch_recent_trades(
    coin: str = "HYPE",
    timeout: int = DEFAULT_TIMEOUT,
) -> list[dict]:
    """
    Fetch recent public trades for a Hyperliquid perpetual market.

    Endpoint type: "recentTrades"
    Response shape (per trade):
        {
            "coin": "HYPE",
            "side": "B" | "A",
            "px": "28.15",
            "sz": "10.5",
            "time": 1716200000000,
            "hash": "0xabc..."
        }

    Args:
        coin:    Coin name, e.g. "HYPE". Will be normalised.
        timeout: HTTP timeout in seconds.

    Returns:
        List of normalised trade dicts with keys:
        - coin (str)
        - side (str): "buy" or "sell"
        - price (float)
        - qty (float)
        - time_ms (int)
        - hash (str)

    Raises:
        InvalidCoinError: if coin fails normalisation.
        HyperliquidError: on HTTP or parse errors.
    """
    c = normalize_coin(coin)
    data = post_info({"type": "recentTrades", "coin": c}, timeout=timeout)

    if not isinstance(data, list):
        raise HyperliquidError(
            f"Unexpected recentTrades response type: {type(data).__name__}",
            request_type="recentTrades",
        )

    result = []
    for i, trade in enumerate(data):
        if not isinstance(trade, dict):
            raise HyperliquidError(
                f"Malformed trade at index {i}: expected dict, got {type(trade).__name__}",
                request_type="recentTrades",
            )
        try:
            result.append({
                "coin":    str(trade.get("coin", c)),
                "side":    "buy" if trade.get("side") == "B" else "sell",
                "price":   float(trade.get("px", 0)),
                "qty":     float(trade.get("sz", 0)),
                "time_ms": int(trade.get("time", 0)),
                "hash":    str(trade.get("hash", "")),
            })
        except (ValueError, TypeError) as exc:
            raise HyperliquidError(
                f"Cannot parse trade at index {i}: {trade!r}",
                request_type="recentTrades",
            ) from exc

    return result


if __name__ == "__main__":
    # Smoke test: build OrderBookSnapshot from known response shape
    sample_l2 = {
        "coin": "HYPE",
        "time": 1_716_200_000_000,
        "levels": [
            [
                {"px": "28.15", "sz": "120.5", "n": 3},
                {"px": "28.10", "sz": "80.2",  "n": 2},
                {"px": "28.00", "sz": "50.0",  "n": 1},
            ],
            [
                {"px": "28.20", "sz": "60.0",  "n": 1},
                {"px": "28.25", "sz": "40.5",  "n": 2},
                {"px": "28.30", "sz": "30.0",  "n": 1},
            ],
        ],
    }

    bids = _parse_hl_levels(sample_l2["levels"][0], "bid")
    asks = _parse_hl_levels(sample_l2["levels"][1], "ask")
    bids.sort(key=lambda l: l.price, reverse=True)
    asks.sort(key=lambda l: l.price)
    mid = (bids[0].price + asks[0].price) / 2.0

    snap = OrderBookSnapshot(
        symbol="HYPE",
        exchange=EXCHANGE,
        timestamp_ms=1_716_200_000_000,
        bids=bids,
        asks=asks,
        mid_price=round(mid, 8),
    )

    assert snap.symbol == "HYPE"
    assert snap.exchange == "Hyperliquid"
    assert snap.best_bid is not None
    assert snap.best_bid.price == 28.15
    assert snap.best_ask is not None
    assert snap.best_ask.price == 28.20
    assert snap.mid_price == round((28.15 + 28.20) / 2, 8)
    assert snap.bids[0].usd_size == round(28.15 * 120.5, 6)
    assert len(snap.bids) == 3
    assert len(snap.asks) == 3

    # normalize_coin
    assert normalize_coin("hype")      == "HYPE"
    assert normalize_coin("BTC/USDT")  == "BTC"
    assert normalize_coin("  eth-usd ") == "ETH"
    assert normalize_coin("SOLUSDT")   == "SOL"

    try:
        normalize_coin("")
        assert False, "Should have raised"
    except InvalidCoinError:
        pass

    try:
        normalize_coin(None)  # type: ignore
        assert False, "Should have raised"
    except InvalidCoinError:
        pass

    # RestrictedLocationError-equivalent: HyperliquidError is ConnectorError-like
    assert issubclass(HyperliquidRateLimitError, HyperliquidError)

    # allMids normalisation
    raw_mids = {"BTC": "67420.5", "HYPE": "28.15", "BAD": "not_a_number", "ETH": "3512"}
    result = {}
    for coin, price_str in raw_mids.items():
        try:
            result[str(coin)] = float(price_str)
        except (ValueError, TypeError):
            continue
    assert result["BTC"] == 67420.5
    assert result["HYPE"] == 28.15
    assert result["ETH"] == 3512.0
    assert "BAD" not in result

    print("connectors/hyperliquid.py — all assertions passed.")
