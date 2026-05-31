"""
connectors/binance.py
---------------------
Binance public market data connector for the Pro Trading Terminal.

Covers public endpoints only — no API key required.
Binance REST API v3: https://binance-docs.github.io/apidocs/spot/en/

Rules:
- No Streamlit imports.
- No API key needed for the endpoints used here.
- All requests have explicit timeouts.
- All errors raise ConnectorError or return typed safe structures.
- Never silent except pass.
- Returns types from core/models.py.
"""

from __future__ import annotations

import time
from typing import Optional

import requests

from core.models import OrderBookLevel, OrderBookSnapshot

# ── Constants ─────────────────────────────────────────────────────────────────

BASE_URL = "https://api.binance.com"
EXCHANGE = "binance"

DEFAULT_TIMEOUT = 8  # seconds
DEFAULT_OB_LIMIT = 100  # depth levels per side
DEFAULT_KLINE_LIMIT = 100
DEFAULT_TRADES_LIMIT = 50

SUPPORTED_SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")

# Valid depth limits accepted by Binance API (others will be rejected server-side)
VALID_DEPTH_LIMITS = (5, 10, 20, 50, 100, 500, 1000, 5000)

# Valid kline intervals
VALID_INTERVALS = (
    "1s", "1m", "3m", "5m", "15m", "30m",
    "1h", "2h", "4h", "6h", "8h", "12h",
    "1d", "3d", "1w", "1M",
)


# ── Exceptions ────────────────────────────────────────────────────────────────

class ConnectorError(Exception):
    """
    Raised when a Binance connector call fails unrecoverably.

    Attributes:
        message:     Human-readable description.
        status_code: HTTP status code, if available. None for network errors.
        endpoint:    The URL that was called.
    """

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        endpoint: str = "",
    ) -> None:
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


class RateLimitError(ConnectorError):
    """Raised when Binance returns HTTP 429 (rate limit exceeded)."""


class InvalidSymbolError(ConnectorError):
    """Raised when a symbol fails validation before a request is made."""


class RestrictedLocationError(ConnectorError):
    """
    Raised when Binance returns HTTP 451 (Unavailable For Legal Reasons).

    This happens on Streamlit Cloud and other hosted environments where
    Binance blocks requests based on server region.
    The caller should fall back to demo/mock data rather than crashing.
    """


# ── Input normalisation ───────────────────────────────────────────────────────

def normalize_symbol(symbol: object) -> str:
    """
    Normalize a trading symbol for use with the Binance API.

    Strips whitespace, uppercases, and removes common separators
    (/, -, _) that users might paste from other platforms.

    Args:
        symbol: Any object. Must be a non-empty string after stripping.

    Returns:
        Normalized symbol string, e.g. "BTCUSDT".

    Raises:
        InvalidSymbolError: if symbol is not a string, is empty after stripping,
                            or contains characters not in [A-Z0-9].

    Examples:
        >>> normalize_symbol("btcusdt")
        'BTCUSDT'
        >>> normalize_symbol("BTC/USDT")
        'BTCUSDT'
        >>> normalize_symbol("  eth-usdt  ")
        'ETHUSDT'
        >>> normalize_symbol("SOL_USDT")
        'SOLUSDT'
    """
    if not isinstance(symbol, str):
        raise InvalidSymbolError(
            f"Symbol must be a string, got {type(symbol).__name__}"
        )

    cleaned = symbol.strip().upper().replace("/", "").replace("-", "").replace("_", "")

    if not cleaned:
        raise InvalidSymbolError("Symbol cannot be empty after normalisation")

    import re
    if not re.match(r"^[A-Z0-9]+$", cleaned):
        raise InvalidSymbolError(
            f"Symbol '{cleaned}' contains invalid characters. "
            "Only A-Z and 0-9 are allowed."
        )

    return cleaned


# ── Internal HTTP helper ──────────────────────────────────────────────────────

def _get(
    path: str,
    params: Optional[dict] = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict | list:
    """
    Make a GET request to the Binance REST API.

    Args:
        path:    API path, e.g. "/api/v3/depth".
        params:  Query parameters dict. None sends no params.
        timeout: Request timeout in seconds.

    Returns:
        Parsed JSON response (dict or list depending on endpoint).

    Raises:
        ConnectorError:          On HTTP errors, JSON parse failures, or unexpected response shape.
        RateLimitError:          On HTTP 429 or 418.
        RestrictedLocationError: On HTTP 451 (region blocked by Binance).
        ConnectorError:          On connection/timeout errors.
    """
    url = f"{BASE_URL}{path}"
    try:
        response = requests.get(url, params=params, timeout=timeout)
    except requests.exceptions.Timeout as exc:
        raise ConnectorError(
            f"Request timed out after {timeout}s", endpoint=url
        ) from exc
    except requests.exceptions.ConnectionError as exc:
        raise ConnectorError(
            f"Connection failed: {exc}", endpoint=url
        ) from exc
    except requests.exceptions.RequestException as exc:
        raise ConnectorError(
            f"Request failed: {exc}", endpoint=url
        ) from exc

    if response.status_code == 429:
        retry_after = response.headers.get("Retry-After", "unknown")
        raise RateLimitError(
            f"Binance rate limit exceeded. Retry after: {retry_after}s",
            status_code=429,
            endpoint=url,
        )

    if response.status_code == 418:
        raise RateLimitError(
            "Binance IP banned (HTTP 418). Wait before retrying.",
            status_code=418,
            endpoint=url,
        )

    if response.status_code == 451:
        raise RestrictedLocationError(
            "Binance is unavailable from this server region (HTTP 451). "
            "This typically occurs on hosted platforms such as Streamlit Cloud. "
            "Use a local environment or a VPS in a supported region.",
            status_code=451,
            endpoint=url,
        )

    if not response.ok:
        # Try to get the Binance error message
        try:
            err_body = response.json()
            msg = err_body.get("msg", response.text[:200])
            code = err_body.get("code", response.status_code)
        except Exception:
            msg = response.text[:200] or "No error body"
            code = response.status_code

        raise ConnectorError(
            f"Binance API error {code}: {msg}",
            status_code=response.status_code,
            endpoint=url,
        )

    try:
        return response.json()
    except ValueError as exc:
        raise ConnectorError(
            f"Failed to parse JSON response from {url}: {exc}",
            status_code=response.status_code,
            endpoint=url,
        ) from exc


# ── Public endpoints ──────────────────────────────────────────────────────────

def fetch_orderbook(
    symbol: str = "BTCUSDT",
    limit: int = DEFAULT_OB_LIMIT,
    timeout: int = DEFAULT_TIMEOUT,
) -> OrderBookSnapshot:
    """
    Fetch the current order book for a symbol from Binance.

    Endpoint: GET /api/v3/depth

    Args:
        symbol:  Trading pair, e.g. "BTCUSDT". Will be normalised.
        limit:   Number of depth levels per side. Binance accepts:
                 5, 10, 20, 50, 100 (default), 500, 1000, 5000.
        timeout: HTTP timeout in seconds.

    Returns:
        OrderBookSnapshot with bids sorted descending (best bid first)
        and asks sorted ascending (best ask first).
        usd_size is pre-computed as price * qty for every level.

    Raises:
        InvalidSymbolError: if symbol fails normalisation.
        ConnectorError:     on HTTP or parse errors.

    Example response shape from Binance:
        {
            "lastUpdateId": 1027024,
            "bids": [["4.00000000", "431.00000000"], ...],
            "asks": [["4.00000200", "12.00000000"], ...]
        }
    """
    sym = normalize_symbol(symbol)

    if limit not in VALID_DEPTH_LIMITS:
        raise ConnectorError(
            f"Invalid depth limit {limit}. Must be one of {VALID_DEPTH_LIMITS}."
        )

    data = _get("/api/v3/depth", params={"symbol": sym, "limit": limit}, timeout=timeout)

    if not isinstance(data, dict):
        raise ConnectorError(
            f"Unexpected response type for /api/v3/depth: {type(data).__name__}"
        )

    timestamp_ms = int(time.time() * 1000)
    bids = _parse_levels(data.get("bids", []), side="bid")
    asks = _parse_levels(data.get("asks", []), side="ask")

    # Bids: descending by price (best bid = highest price = index 0)
    bids.sort(key=lambda lvl: lvl.price, reverse=True)
    # Asks: ascending by price (best ask = lowest price = index 0)
    asks.sort(key=lambda lvl: lvl.price)

    mid = 0.0
    if bids and asks:
        mid = (bids[0].price + asks[0].price) / 2.0

    return OrderBookSnapshot(
        symbol=sym,
        exchange=EXCHANGE,
        timestamp_ms=timestamp_ms,
        bids=bids,
        asks=asks,
        mid_price=round(mid, 8),
    )


def fetch_24h_ticker(
    symbol: str = "BTCUSDT",
    timeout: int = DEFAULT_TIMEOUT,
) -> dict:
    """
    Fetch 24-hour rolling window statistics for a symbol.

    Endpoint: GET /api/v3/ticker/24hr

    Args:
        symbol:  Trading pair. Will be normalised.
        timeout: HTTP timeout in seconds.

    Returns:
        Dict with normalised float values for numeric fields. Keys include:
        - symbol (str)
        - price (float): last traded price
        - price_change (float): absolute price change
        - price_change_pct (float): percentage change (e.g. 1.5 for +1.5%)
        - high_24h (float)
        - low_24h (float)
        - volume_24h (float): base asset volume
        - quote_volume_24h (float): quote asset volume in USD
        - open_price (float)
        - weighted_avg_price (float)
        - bid_price (float)
        - ask_price (float)
        - count (int): number of trades
        - open_time_ms (int)
        - close_time_ms (int)

    Raises:
        InvalidSymbolError: if symbol fails normalisation.
        ConnectorError:     on HTTP or parse errors.
    """
    sym = normalize_symbol(symbol)
    raw = _get("/api/v3/ticker/24hr", params={"symbol": sym}, timeout=timeout)

    if not isinstance(raw, dict):
        raise ConnectorError(
            f"Unexpected response type for /api/v3/ticker/24hr: {type(raw).__name__}"
        )

    return {
        "symbol":             raw.get("symbol", sym),
        "price":              _f(raw.get("lastPrice", 0)),
        "price_change":       _f(raw.get("priceChange", 0)),
        "price_change_pct":   _f(raw.get("priceChangePercent", 0)),
        "high_24h":           _f(raw.get("highPrice", 0)),
        "low_24h":            _f(raw.get("lowPrice", 0)),
        "volume_24h":         _f(raw.get("volume", 0)),
        "quote_volume_24h":   _f(raw.get("quoteVolume", 0)),
        "open_price":         _f(raw.get("openPrice", 0)),
        "weighted_avg_price": _f(raw.get("weightedAvgPrice", 0)),
        "bid_price":          _f(raw.get("bidPrice", 0)),
        "ask_price":          _f(raw.get("askPrice", 0)),
        "count":              int(raw.get("count", 0)),
        "open_time_ms":       int(raw.get("openTime", 0)),
        "close_time_ms":      int(raw.get("closeTime", 0)),
    }


def fetch_klines(
    symbol: str = "BTCUSDT",
    interval: str = "1m",
    limit: int = DEFAULT_KLINE_LIMIT,
    timeout: int = DEFAULT_TIMEOUT,
) -> list[dict]:
    """
    Fetch OHLCV candlestick data for a symbol.

    Endpoint: GET /api/v3/klines

    Args:
        symbol:   Trading pair. Will be normalised.
        interval: Candlestick interval. Must be one of VALID_INTERVALS.
        limit:    Number of candles to return (1–1000).
        timeout:  HTTP timeout in seconds.

    Returns:
        List of dicts, newest candle last. Each dict has:
        - open_time_ms (int): candle open timestamp in ms
        - open (float)
        - high (float)
        - low (float)
        - close (float)
        - volume (float): base asset volume
        - close_time_ms (int)
        - quote_volume (float): quote asset volume
        - trade_count (int): number of trades in candle
        - taker_buy_volume (float): taker buy base asset volume
        - taker_buy_quote_volume (float): taker buy quote asset volume

    Raises:
        InvalidSymbolError: if symbol fails normalisation.
        ConnectorError:     if interval is invalid or on HTTP/parse errors.

    Binance kline element indices:
        [0]  open_time, [1] open, [2] high, [3] low, [4] close,
        [5]  volume, [6] close_time, [7] quote_asset_volume,
        [8]  trade_count, [9] taker_buy_base, [10] taker_buy_quote, [11] ignore
    """
    sym = normalize_symbol(symbol)

    if interval not in VALID_INTERVALS:
        raise ConnectorError(
            f"Invalid interval '{interval}'. Must be one of {VALID_INTERVALS}."
        )

    if not (1 <= limit <= 1000):
        raise ConnectorError(
            f"Kline limit must be between 1 and 1000, got {limit}."
        )

    raw = _get(
        "/api/v3/klines",
        params={"symbol": sym, "interval": interval, "limit": limit},
        timeout=timeout,
    )

    if not isinstance(raw, list):
        raise ConnectorError(
            f"Unexpected response type for /api/v3/klines: {type(raw).__name__}"
        )

    result = []
    for i, candle in enumerate(raw):
        if not isinstance(candle, list) or len(candle) < 11:
            raise ConnectorError(
                f"Malformed kline at index {i}: expected list of >=11 elements, "
                f"got {type(candle).__name__} len={len(candle) if isinstance(candle, list) else 'N/A'}"
            )
        result.append({
            "open_time_ms":            int(candle[0]),
            "open":                    _f(candle[1]),
            "high":                    _f(candle[2]),
            "low":                     _f(candle[3]),
            "close":                   _f(candle[4]),
            "volume":                  _f(candle[5]),
            "close_time_ms":           int(candle[6]),
            "quote_volume":            _f(candle[7]),
            "trade_count":             int(candle[8]),
            "taker_buy_volume":        _f(candle[9]),
            "taker_buy_quote_volume":  _f(candle[10]),
        })

    return result


def fetch_recent_trades(
    symbol: str = "BTCUSDT",
    limit: int = DEFAULT_TRADES_LIMIT,
    timeout: int = DEFAULT_TIMEOUT,
) -> list[dict]:
    """
    Fetch the most recent trades for a symbol.

    Endpoint: GET /api/v3/trades

    Args:
        symbol:  Trading pair. Will be normalised.
        limit:   Number of trades to return (1–1000).
        timeout: HTTP timeout in seconds.

    Returns:
        List of dicts, newest trade last. Each dict has:
        - id (int): trade ID
        - price (float)
        - qty (float): base asset quantity
        - quote_qty (float): quote asset quantity (USD)
        - time_ms (int): trade timestamp in ms
        - is_buyer_maker (bool): True if the buyer was the market maker

    Raises:
        InvalidSymbolError: if symbol fails normalisation.
        ConnectorError:     on HTTP or parse errors.
    """
    sym = normalize_symbol(symbol)

    if not (1 <= limit <= 1000):
        raise ConnectorError(
            f"Trades limit must be between 1 and 1000, got {limit}."
        )

    raw = _get(
        "/api/v3/trades",
        params={"symbol": sym, "limit": limit},
        timeout=timeout,
    )

    if not isinstance(raw, list):
        raise ConnectorError(
            f"Unexpected response type for /api/v3/trades: {type(raw).__name__}"
        )

    result = []
    for i, trade in enumerate(raw):
        if not isinstance(trade, dict):
            raise ConnectorError(
                f"Malformed trade at index {i}: expected dict, got {type(trade).__name__}"
            )
        result.append({
            "id":              int(trade.get("id", 0)),
            "price":           _f(trade.get("price", 0)),
            "qty":             _f(trade.get("qty", 0)),
            "quote_qty":       _f(trade.get("quoteQty", 0)),
            "time_ms":         int(trade.get("time", 0)),
            "is_buyer_maker":  bool(trade.get("isBuyerMaker", False)),
        })

    return result


# ── Private helpers ───────────────────────────────────────────────────────────

def _parse_levels(
    raw_levels: list,
    side: str,
) -> list[OrderBookLevel]:
    """
    Parse a raw Binance bid/ask list into a list of OrderBookLevel objects.

    Binance format: [["price_str", "qty_str"], ...]

    Args:
        raw_levels: List of [price_string, qty_string] pairs from Binance.
        side:       "bid" or "ask" — used for error context only.

    Returns:
        List of OrderBookLevel. Skips any malformed or zero-price entries
        with a logged note rather than crashing.

    Raises:
        ConnectorError: if raw_levels is not a list.
    """
    if not isinstance(raw_levels, list):
        raise ConnectorError(
            f"Expected list for {side} levels, got {type(raw_levels).__name__}"
        )

    levels: list[OrderBookLevel] = []
    for i, item in enumerate(raw_levels):
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            raise ConnectorError(
                f"Malformed {side} level at index {i}: "
                f"expected [price, qty], got {item!r}"
            )
        try:
            price = float(item[0])
            qty = float(item[1])
        except (ValueError, TypeError) as exc:
            raise ConnectorError(
                f"Could not parse {side} level at index {i} as float: {item!r}"
            ) from exc

        if price <= 0:
            # Skip zero/negative price levels — they're invalid data
            continue

        usd_size = round(price * qty, 6)
        levels.append(OrderBookLevel(price=price, qty=qty, usd_size=usd_size))

    return levels


def _f(value: object) -> float:
    """
    Safely convert a Binance string or numeric value to float.

    Binance returns most numeric fields as strings (e.g. "45123.50000000").

    Returns 0.0 on any conversion failure.
    """
    try:
        return float(value)  # type: ignore[arg-type]
    except (ValueError, TypeError):
        return 0.0


if __name__ == "__main__":
    # Verify RestrictedLocationError is importable and subclasses ConnectorError
    assert issubclass(RestrictedLocationError, ConnectorError)
    try:
        raise RestrictedLocationError("test 451", status_code=451, endpoint="/test")
    except ConnectorError as e:
        assert e.status_code == 451

    # Smoke test: parse known Binance-shaped depth response without a network call
    sample_depth = {
        "lastUpdateId": 1027024,
        "bids": [["99.50", "10.0"], ["99.00", "50.0"], ["98.00", "5.0"]],
        "asks": [["100.50", "8.0"], ["101.00", "20.0"], ["102.00", "3.0"]],
    }

    bids = _parse_levels(sample_depth["bids"], side="bid")
    asks = _parse_levels(sample_depth["asks"], side="ask")
    bids.sort(key=lambda lvl: lvl.price, reverse=True)
    asks.sort(key=lambda lvl: lvl.price)

    snap = OrderBookSnapshot(
        symbol="BTCUSDT",
        exchange=EXCHANGE,
        timestamp_ms=1_000_000,
        bids=bids,
        asks=asks,
        mid_price=round((bids[0].price + asks[0].price) / 2, 8),
    )

    assert snap.symbol == "BTCUSDT"
    assert snap.best_bid is not None
    assert snap.best_bid.price == 99.5
    assert snap.best_ask is not None
    assert snap.best_ask.price == 100.5
    assert snap.mid_price == 100.0
    assert len(snap.bids) == 3
    assert len(snap.asks) == 3
    assert snap.bids[0].usd_size == round(99.5 * 10.0, 6)

    # normalize_symbol
    assert normalize_symbol("btcusdt") == "BTCUSDT"
    assert normalize_symbol("BTC/USDT") == "BTCUSDT"
    assert normalize_symbol("  eth-usdt  ") == "ETHUSDT"
    assert normalize_symbol("SOL_USDT") == "SOLUSDT"

    try:
        normalize_symbol("")
        assert False, "Should have raised"
    except InvalidSymbolError:
        pass

    try:
        normalize_symbol(None)  # type: ignore
        assert False, "Should have raised"
    except InvalidSymbolError:
        pass

    # _f helper
    assert _f("45123.50000000") == 45123.5
    assert _f(0) == 0.0
    assert _f("bad") == 0.0
    assert _f(None) == 0.0

    print("connectors/binance.py — all assertions passed.")
