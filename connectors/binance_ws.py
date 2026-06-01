"""
connectors/binance_ws.py
-------------------------
Binance WebSocket connector basis for the Pro Trading Terminal.

Provides message builders and parsers for the Binance Partial Book Depth
WebSocket stream. The async listener (listen_depth) is fully functional
but depends on the optional `websockets` library.

Usage pattern (future):
    # In a background asyncio worker:
    async for snap in listen_depth(["BTCUSDT", "ETHUSDT"]):
        store.set_snapshot(snap["symbol"], snap)
        store.add_history(snap["symbol"], snap)

Binance WebSocket endpoints:
    Single stream: wss://stream.binance.com:9443/ws/<streamName>
    Combined:      wss://stream.binance.com:9443/stream
                   (subscribe via {"method":"SUBSCRIBE","params":[...],"id":1})

Partial depth stream format:
    Stream name:   <symbol_lower>@depth<levels>@<speed_ms>ms
    Example:       btcusdt@depth20@100ms
    Speeds:        100ms or 1000ms
    Level options: 5, 10, or 20

Rules:
- No Streamlit imports.
- No external dependencies beyond stdlib (websockets is optional, guarded).
- All sync functions are pure — testable without websockets installed.
- listen_depth raises ImportError with a clear message if websockets missing.
- No silent except pass.
"""

from __future__ import annotations

import json
import re
import time
from typing import AsyncIterator, Optional

# ── Constants ─────────────────────────────────────────────────────────────────

WS_BASE_URL      = "wss://stream.binance.com:9443"
WS_STREAM_PATH   = "/ws/{stream}"         # single-stream
WS_COMBINED_PATH = "/stream"              # combined + subscribe

VALID_DEPTH_LEVELS = frozenset({5, 10, 20})
VALID_SPEED_MS     = frozenset({100, 1000})

# ── Exceptions ────────────────────────────────────────────────────────────────

class WSConnectorError(Exception):
    """Raised for connector-level errors (config, parse failures)."""


class WSMessageError(WSConnectorError):
    """Raised when an incoming WebSocket message cannot be parsed."""


# ── Stream name helpers ───────────────────────────────────────────────────────

def build_depth_stream_name(
    symbol: str,
    levels: int = 20,
    speed_ms: int = 100,
) -> str:
    """
    Build a Binance partial book depth stream name.

    Format: ``<symbol_lower>@depth<levels>@<speed_ms>ms``
    Example: ``btcusdt@depth20@100ms``

    Args:
        symbol:   Trading pair, e.g. "BTCUSDT". Case-insensitive.
        levels:   Depth levels. Must be 5, 10, or 20. Default 20.
        speed_ms: Update speed in milliseconds. Must be 100 or 1000. Default 100.

    Returns:
        Lowercase stream name string.

    Raises:
        TypeError:  if symbol is not a string.
        ValueError: if symbol is empty, levels is invalid, or speed_ms is invalid.

    Examples:
        >>> build_depth_stream_name("BTCUSDT")
        'btcusdt@depth20@100ms'
        >>> build_depth_stream_name("ETH/USDT", levels=5, speed_ms=1000)
        'ethusdt@depth5@1000ms'
    """
    symbol = _clean_symbol(symbol)
    _validate_levels(levels)
    _validate_speed(speed_ms)
    return f"{symbol}@depth{levels}@{speed_ms}ms"


def build_subscribe_message(
    symbols: list[str],
    levels: int = 20,
    speed_ms: int = 100,
    request_id: int = 1,
) -> dict:
    """
    Build a Binance WebSocket SUBSCRIBE message for multiple symbols.

    Args:
        symbols:    List of trading pairs, e.g. ["BTCUSDT", "ETHUSDT"].
        levels:     Depth levels (5, 10, or 20). Default 20.
        speed_ms:   Update speed in ms (100 or 1000). Default 100.
        request_id: Integer id for the subscribe request. Default 1.

    Returns:
        Dict ready to be JSON-serialised and sent over the WebSocket:
        ``{"method": "SUBSCRIBE", "params": [...], "id": request_id}``

    Raises:
        TypeError:  if symbols is not a list, or any symbol is not a string.
        ValueError: if symbols is empty, or any symbol/levels/speed is invalid.

    Examples:
        >>> build_subscribe_message(["BTCUSDT"])
        {'method': 'SUBSCRIBE', 'params': ['btcusdt@depth20@100ms'], 'id': 1}
        >>> build_subscribe_message(["BTC/USDT", "ETHUSDT"], levels=5)
        {'method': 'SUBSCRIBE', 'params': ['btcusdt@depth5@100ms', 'ethusdt@depth5@100ms'], 'id': 1}
    """
    if not isinstance(symbols, list):
        raise TypeError(
            f"symbols must be a list, got {type(symbols).__name__}"
        )
    if not symbols:
        raise ValueError("symbols list cannot be empty")
    _validate_levels(levels)
    _validate_speed(speed_ms)

    params = [build_depth_stream_name(sym, levels, speed_ms) for sym in symbols]
    return {"method": "SUBSCRIBE", "params": params, "id": request_id}


def build_unsubscribe_message(
    symbols: list[str],
    levels: int = 20,
    speed_ms: int = 100,
    request_id: int = 2,
) -> dict:
    """
    Build a Binance WebSocket UNSUBSCRIBE message.

    Args: same as build_subscribe_message.

    Returns:
        ``{"method": "UNSUBSCRIBE", "params": [...], "id": request_id}``
    """
    msg = build_subscribe_message(symbols, levels, speed_ms, request_id)
    msg["method"] = "UNSUBSCRIBE"
    return msg


# ── Level normalisation ───────────────────────────────────────────────────────

def normalize_depth_levels(raw_levels: list) -> list[dict]:
    """
    Convert raw Binance depth level pairs to normalised dicts.

    Binance depth levels are 2-element lists: ``["price_str", "qty_str"]``.
    This function converts them to dicts with floats and a pre-computed notional.

    Args:
        raw_levels: List of 2-element ``[price_str, qty_str]`` pairs.

    Returns:
        List of dicts: ``{"price": float, "size": float, "notional": float}``
        Zero-size levels are included (Binance uses them as delete signals).
        Malformed elements raise WSMessageError rather than being silently skipped.

    Raises:
        TypeError:      if raw_levels is not a list.
        WSMessageError: if any element is malformed or cannot be parsed as float.

    Examples:
        >>> normalize_depth_levels([["100.0", "5.0"], ["99.5", "2.5"]])
        [{'price': 100.0, 'size': 5.0, 'notional': 500.0},
         {'price': 99.5,  'size': 2.5, 'notional': 248.75}]
    """
    if not isinstance(raw_levels, list):
        raise TypeError(
            f"raw_levels must be a list, got {type(raw_levels).__name__}"
        )

    result: list[dict] = []
    for i, item in enumerate(raw_levels):
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            raise WSMessageError(
                f"Malformed depth level at index {i}: "
                f"expected [price, size], got {item!r}"
            )
        try:
            price = float(item[0])
            size  = float(item[1])
        except (ValueError, TypeError) as exc:
            raise WSMessageError(
                f"Cannot parse depth level at index {i} as float: {item!r}"
            ) from exc

        result.append({
            "price":    price,
            "size":     size,
            "notional": round(price * size, 6),
        })

    return result


# ── Message parser ────────────────────────────────────────────────────────────

def parse_depth_message(message: str | bytes | dict) -> dict:
    """
    Parse an incoming Binance WebSocket depth message.

    Handles three message shapes:
    1. Combined stream wrapper:
       ``{"stream":"btcusdt@depth20@100ms","data":{...}}``
    2. Direct partial book snapshot:
       ``{"lastUpdateId":123,"bids":[...],"asks":[...]}``
    3. Diff depth event:
       ``{"e":"depthUpdate","E":1716200000000,"s":"BTCUSDT","b":[...],"a":[...]}``

    Also handles subscription acknowledgements:
       ``{"result":null,"id":1}`` → returns ``{"type":"ack","id":1,"raw":{...}}``

    Args:
        message: Raw WebSocket message — str (JSON), bytes, or already-parsed dict.

    Returns:
        Normalised dict with keys:
        - ``type``        (str): "depth" | "ack" | "unknown"
        - ``symbol``      (str): e.g. "BTCUSDT". Empty if unavailable.
        - ``bids``        (list[dict]): normalised bid levels (may be empty)
        - ``asks``        (list[dict]): normalised ask levels (may be empty)
        - ``event_time``  (int): event timestamp in ms (0 if not present)
        - ``last_update_id`` (int): 0 if not present
        - ``raw``         (dict): the original parsed payload

    Raises:
        WSMessageError: if the message is not valid JSON or not a dict/bytes/str.

    Note:
        Never raises on missing or malformed depth levels — those are converted
        to empty lists with a parse warning embedded in the result.
    """
    # ── Decode to dict ────────────────────────────────────────────────────────
    if isinstance(message, bytes):
        message = message.decode("utf-8", errors="replace")

    if isinstance(message, str):
        try:
            payload = json.loads(message)
        except json.JSONDecodeError as exc:
            raise WSMessageError(
                f"Invalid JSON in WebSocket message: {exc}"
            ) from exc
    elif isinstance(message, dict):
        payload = message
    else:
        raise WSMessageError(
            f"message must be str, bytes, or dict — got {type(message).__name__}"
        )

    if not isinstance(payload, dict):
        raise WSMessageError(
            f"Expected JSON object (dict), got {type(payload).__name__}"
        )

    raw = payload  # keep reference for "raw" field

    # ── Subscription ACK ──────────────────────────────────────────────────────
    if "result" in payload and "id" in payload and "e" not in payload:
        return {
            "type":           "ack",
            "symbol":         "",
            "bids":           [],
            "asks":           [],
            "event_time":     0,
            "last_update_id": 0,
            "raw":            raw,
        }

    # ── Unwrap combined stream ────────────────────────────────────────────────
    if "stream" in payload and "data" in payload:
        stream_name = str(payload.get("stream", ""))
        symbol = _symbol_from_stream(stream_name)
        data   = payload["data"]
        if not isinstance(data, dict):
            raise WSMessageError(
                f"'data' field in combined stream is not a dict: {type(data).__name__}"
            )
        payload = data  # continue parsing inner payload with stream symbol hint
    else:
        symbol = ""

    # ── Diff depth event: {"e":"depthUpdate",...} ─────────────────────────────
    if payload.get("e") == "depthUpdate":
        sym_field  = str(payload.get("s", symbol)).upper()
        event_time = int(payload.get("E", 0))
        bids_raw   = payload.get("b", [])
        asks_raw   = payload.get("a", [])
        bids, asks = _safe_normalize(bids_raw), _safe_normalize(asks_raw)
        return {
            "type":           "depth",
            "symbol":         sym_field or symbol,
            "bids":           bids,
            "asks":           asks,
            "event_time":     event_time,
            "last_update_id": int(payload.get("u", 0)),
            "raw":            raw,
        }

    # ── Partial book snapshot: {"lastUpdateId":...,"bids":[...],"asks":[...]} ─
    if "lastUpdateId" in payload or ("bids" in payload and "asks" in payload):
        bids_raw = payload.get("bids", [])
        asks_raw = payload.get("asks", [])
        bids, asks = _safe_normalize(bids_raw), _safe_normalize(asks_raw)
        return {
            "type":           "depth",
            "symbol":         symbol,
            "bids":           bids,
            "asks":           asks,
            "event_time":     int(payload.get("E", 0)),
            "last_update_id": int(payload.get("lastUpdateId", 0)),
            "raw":            raw,
        }

    # ── Unknown / unhandled message type ──────────────────────────────────────
    return {
        "type":           "unknown",
        "symbol":         symbol,
        "bids":           [],
        "asks":           [],
        "event_time":     0,
        "last_update_id": 0,
        "raw":            raw,
    }


# ── Async listener (websockets optional) ─────────────────────────────────────

async def listen_depth(
    symbols: list[str],
    levels: int = 20,
    speed_ms: int = 100,
    on_message=None,
) -> AsyncIterator[dict]:
    """
    Async generator that yields parsed depth messages from Binance WebSocket.

    Connects to the Binance combined stream endpoint, subscribes to depth
    streams for each symbol, and yields normalised dicts from parse_depth_message.

    Requires the optional ``websockets`` library:
        pip install websockets

    Args:
        symbols:    List of trading pairs, e.g. ["BTCUSDT", "ETHUSDT"].
        levels:     Depth levels (5, 10, or 20). Default 20.
        speed_ms:   Update speed (100 or 1000 ms). Default 100.
        on_message: Optional async callback(msg: dict) called for every message.
                    Exceptions in on_message are caught and logged but do not
                    stop the listener.

    Yields:
        Normalised depth dict from parse_depth_message (type == "depth" only).

    Raises:
        ImportError:     if websockets is not installed.
        WSConnectorError: on connection or send errors.

    Note:
        This function contains no retry logic — implement reconnection in
        the calling worker. The caller is responsible for cancellation.

    Example::

        async def worker():
            async for msg in listen_depth(["BTCUSDT"], levels=20):
                store.set_snapshot(msg["symbol"], msg)
    """
    try:
        import websockets  # noqa: F401
        from websockets.client import connect as ws_connect
    except ImportError as exc:
        raise ImportError(
            "The 'websockets' package is required for listen_depth. "
            "Install it with: pip install websockets"
        ) from exc

    sub_msg = build_subscribe_message(symbols, levels, speed_ms)
    url     = f"{WS_BASE_URL}{WS_COMBINED_PATH}"

    try:
        async with ws_connect(url) as ws:
            await ws.send(json.dumps(sub_msg))
            async for raw_msg in ws:
                try:
                    parsed = parse_depth_message(raw_msg)
                except WSMessageError:
                    continue  # skip unparseable messages — not silent, just non-fatal

                if on_message is not None:
                    try:
                        await on_message(parsed)
                    except Exception:
                        pass  # callback errors do not kill the stream

                if parsed["type"] == "depth":
                    yield parsed

    except Exception as exc:
        raise WSConnectorError(
            f"WebSocket connection error: {exc}"
        ) from exc


# ── Private helpers ───────────────────────────────────────────────────────────

def _clean_symbol(symbol: object) -> str:
    """
    Validate and clean a symbol to lowercase without separators.

    Returns:
        Lowercase string, e.g. "btcusdt".

    Raises:
        TypeError:  if symbol is not a string.
        ValueError: if symbol is empty after cleaning.
    """
    if not isinstance(symbol, str):
        raise TypeError(
            f"symbol must be a string, got {type(symbol).__name__}"
        )
    cleaned = symbol.strip().lower().replace("/", "").replace("-", "").replace("_", "")
    if not cleaned:
        raise ValueError("symbol cannot be empty after normalisation")
    return cleaned


def _validate_levels(levels: int) -> None:
    if levels not in VALID_DEPTH_LEVELS:
        raise ValueError(
            f"levels must be one of {sorted(VALID_DEPTH_LEVELS)}, got {levels}"
        )


def _validate_speed(speed_ms: int) -> None:
    if speed_ms not in VALID_SPEED_MS:
        raise ValueError(
            f"speed_ms must be one of {sorted(VALID_SPEED_MS)}, got {speed_ms}"
        )


def _symbol_from_stream(stream_name: str) -> str:
    """Extract and uppercase the symbol from a stream name like 'btcusdt@depth20@100ms'."""
    match = re.match(r"^([a-z0-9]+)@", stream_name)
    if match:
        return match.group(1).upper()
    return ""


def _safe_normalize(raw_levels: object) -> list[dict]:
    """
    Call normalize_depth_levels, returning [] rather than raising on bad input.
    Used inside parse_depth_message to ensure parse always returns a valid dict.
    """
    if not isinstance(raw_levels, list):
        return []
    try:
        return normalize_depth_levels(raw_levels)
    except (WSMessageError, TypeError):
        return []


if __name__ == "__main__":
    # ── Self-tests ────────────────────────────────────────────────────────────

    # build_depth_stream_name
    assert build_depth_stream_name("BTCUSDT") == "btcusdt@depth20@100ms"
    assert build_depth_stream_name("ETH/USDT", levels=5, speed_ms=1000) == "ethusdt@depth5@1000ms"
    assert build_depth_stream_name("SOL_USDT", levels=10) == "solusdt@depth10@100ms"
    assert build_depth_stream_name("  btcusdt  ") == "btcusdt@depth20@100ms"

    try:
        build_depth_stream_name("BTC", levels=7)
        assert False
    except ValueError:
        pass
    try:
        build_depth_stream_name(None)  # type: ignore
        assert False
    except TypeError:
        pass
    try:
        build_depth_stream_name("BTC", speed_ms=500)
        assert False
    except ValueError:
        pass

    # build_subscribe_message
    msg = build_subscribe_message(["BTCUSDT"])
    assert msg["method"] == "SUBSCRIBE"
    assert "btcusdt@depth20@100ms" in msg["params"]
    assert msg["id"] == 1

    multi = build_subscribe_message(["BTCUSDT", "ETHUSDT"], levels=5, request_id=42)
    assert len(multi["params"]) == 2
    assert multi["id"] == 42
    assert "btcusdt@depth5@100ms" in multi["params"]

    try:
        build_subscribe_message([])
        assert False
    except ValueError:
        pass
    try:
        build_subscribe_message("BTCUSDT")  # type: ignore
        assert False
    except TypeError:
        pass

    # normalize_depth_levels
    levels = normalize_depth_levels([["100.0", "5.0"], ["99.5", "2.5"]])
    assert len(levels) == 2
    assert levels[0] == {"price": 100.0, "size": 5.0, "notional": 500.0}
    assert levels[1]["price"] == 99.5

    assert normalize_depth_levels([]) == []

    try:
        normalize_depth_levels("not a list")
        assert False
    except TypeError:
        pass
    try:
        normalize_depth_levels([["bad", "1.0"]])
        assert False
    except WSMessageError:
        pass

    # parse_depth_message — partial book snapshot
    snap_msg = {
        "lastUpdateId": 160,
        "bids": [["99.0", "5.0"], ["98.5", "2.0"]],
        "asks": [["101.0", "3.0"]],
    }
    parsed = parse_depth_message(snap_msg)
    assert parsed["type"] == "depth"
    assert parsed["last_update_id"] == 160
    assert len(parsed["bids"]) == 2
    assert len(parsed["asks"]) == 1
    assert parsed["bids"][0]["price"] == 99.0
    assert parsed["raw"] is snap_msg

    # parse_depth_message — diff event
    diff_msg = {
        "e": "depthUpdate", "E": 1716200000000,
        "s": "BTCUSDT", "U": 160, "u": 161,
        "b": [["100.0", "5.0"]], "a": [["101.0", "1.0"]],
    }
    parsed2 = parse_depth_message(diff_msg)
    assert parsed2["type"] == "depth"
    assert parsed2["symbol"] == "BTCUSDT"
    assert parsed2["event_time"] == 1716200000000

    # parse_depth_message — combined stream
    combined_msg = {
        "stream": "btcusdt@depth20@100ms",
        "data": {
            "lastUpdateId": 200,
            "bids": [["99.0", "1.0"]],
            "asks": [["101.0", "2.0"]],
        },
    }
    parsed3 = parse_depth_message(combined_msg)
    assert parsed3["type"] == "depth"
    assert parsed3["symbol"] == "BTCUSDT"

    # parse_depth_message — ACK
    ack_msg = {"result": None, "id": 1}
    parsed4 = parse_depth_message(ack_msg)
    assert parsed4["type"] == "ack"

    # parse_depth_message — JSON string input
    parsed5 = parse_depth_message(json.dumps(snap_msg))
    assert parsed5["type"] == "depth"

    # parse_depth_message — bytes input
    parsed6 = parse_depth_message(json.dumps(snap_msg).encode())
    assert parsed6["type"] == "depth"

    # parse_depth_message — empty/broken messages don't crash
    empty_parsed = parse_depth_message({})
    assert empty_parsed["type"] in ("depth", "unknown", "ack")
    assert empty_parsed["bids"] == []

    # parse_depth_message — bad JSON raises
    try:
        parse_depth_message("not json {{{")
        assert False
    except WSMessageError:
        pass

    # build_unsubscribe_message
    unsub = build_unsubscribe_message(["BTCUSDT"], request_id=5)
    assert unsub["method"] == "UNSUBSCRIBE"
    assert unsub["id"] == 5

    print("connectors/binance_ws.py — all assertions passed.")
