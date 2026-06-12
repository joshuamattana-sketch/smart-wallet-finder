"""
services/connectors/binance_trade_stream.py
--------------------------------------------
LM63B — Binance Spot aggTrade WebSocket collector.

Pure module. NO Supabase writes, NO Discord, NO frontend.

Subscribes to the public `@aggTrade` stream for one or many symbols and
emits dicts that are directly compatible with
`services.whale_alert_engine.detect_whale_events(items, options)`.

Public API:
    build_binance_aggtrade_ws_url(symbols)         -> str
    parse_agg_trade_message(raw)                   -> dict | None
    normalize_agg_trade_to_whale_input(parsed)     -> dict
    iter_binance_aggtrades(symbols, message_iter)  -> Iterable[dict]

Binance aggTrade payload (single-stream form, public docs):
    {
      "e": "aggTrade",   # event type
      "E": 123456789,    # event time (ms)
      "s": "BTCUSDT",    # symbol
      "a": 12345,        # aggregate trade id
      "p": "0.001",      # price (string)
      "q": "100",        # quantity (string)
      "f": 100,          # first trade id
      "l": 105,          # last trade id
      "T": 123456785,    # trade time (ms)
      "m": true,         # true if buyer is the maker (taker SOLD)
      "M": true          # ignore (deprecated)
    }

Combined-stream wrapper form (from `/stream?streams=...`):
    {"stream":"btcusdt@aggTrade", "data": {... single-stream form ...}}

Side mapping for `m`:
    m == true  → taker hit the bid  → "sell"  (aggressive sell)
    m == false → taker lifted the ask → "buy"  (aggressive buy)

This module **never** opens a real network socket inside its public
functions; the real WS transport is opt-in via `iter_binance_aggtrades`
with `message_iter=None`, which lazily imports `websocket-client`. Tests
pass an injected message iterator so the entire pipeline is exercised
network-free.
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Iterator

# ── Constants ─────────────────────────────────────────────────────────────────

# Binance Spot endpoints (default).
_SPOT_WS_URL_SINGLE   = "wss://stream.binance.com:9443/ws/{stream}"
_SPOT_WS_URL_COMBINED = "wss://stream.binance.com:9443/stream?streams={streams}"

# Binance USD-M Futures endpoints (LM64B).
_FUTURES_WS_URL_SINGLE   = "wss://fstream.binance.com/ws/{stream}"
_FUTURES_WS_URL_COMBINED = "wss://fstream.binance.com/stream?streams={streams}"

# Back-compat aliases — keep the LM63B exported names pointing at spot.
_WS_URL_SINGLE   = _SPOT_WS_URL_SINGLE
_WS_URL_COMBINED = _SPOT_WS_URL_COMBINED

# Binance Spot symbols: 3–12 alphanumeric chars, no separators. The same
# regex matches USD-M futures perpetual symbols (BTCUSDT, ETHUSDT, …).
_SYMBOL_RE = re.compile(r"^[A-Z0-9]{3,12}$")

# Reconnect backoff bounds (used by the lazy real-network iterator).
_MIN_BACKOFF_S = 1.0
_MAX_BACKOFF_S = 30.0
_WS_RECV_TIMEOUT_S = 0.5

# Default (spot) tagging — preserved as module-level constants for LM63B
# callers. The market-aware helpers below pick the right values per call.
SOURCE_TYPE = "exchange_trade"
EXCHANGE_TAG = "binance_spot"

# Per-market source_type + exchange tags. The URL templates pick spot vs
# futures endpoints. `metadata.market` carries the explicit label so any
# downstream consumer can filter without parsing the `exchange` string.
VALID_MARKETS: tuple[str, ...] = ("spot", "futures")

_MARKET_CONFIG: dict[str, dict[str, str]] = {
    "spot": {
        "source_type":  "exchange_trade",
        "exchange":     "binance_spot",
        "ws_single":    _SPOT_WS_URL_SINGLE,
        "ws_combined":  _SPOT_WS_URL_COMBINED,
    },
    "futures": {
        "source_type":  "futures_trade",
        "exchange":     "binance_futures",
        "ws_single":    _FUTURES_WS_URL_SINGLE,
        "ws_combined":  _FUTURES_WS_URL_COMBINED,
    },
}


def _require_market(market: str | None) -> dict[str, str]:
    """
    Strict market lookup. Raises ValueError with a clear message for unknown
    or non-string inputs. Used by all public LM64B-aware functions to keep
    every code path on a single source of truth for the venue.
    """
    if not isinstance(market, str) or market.strip().lower() not in _MARKET_CONFIG:
        raise ValueError(
            f"unsupported market {market!r} — must be one of "
            f"{sorted(_MARKET_CONFIG)}"
        )
    return _MARKET_CONFIG[market.strip().lower()]


# Back-compat alias: callers from earlier LM64B drafts may still import the
# soft-fallback name. Keep it pointing at the strict resolver so behavior is
# consistent — silent fallbacks are the bug we are fixing in LM64B-fix.
_resolve_market = _require_market


# ── Symbol helpers ────────────────────────────────────────────────────────────

def is_valid_binance_symbol(sym: Any) -> bool:
    """True iff `sym` matches the Binance Spot symbol shape."""
    if not isinstance(sym, str):
        return False
    return bool(_SYMBOL_RE.match(sym.strip().upper()))


def _clean_symbols(symbols: Iterable[Any]) -> list[str]:
    """Uppercase + drop empties + drop invalid; preserve input order, dedupe."""
    seen: set[str] = set()
    out: list[str] = []
    for s in symbols:
        if not isinstance(s, str):
            continue
        up = s.strip().upper()
        if not up or up in seen or not is_valid_binance_symbol(up):
            continue
        seen.add(up)
        out.append(up)
    return out


# ── URL builder ───────────────────────────────────────────────────────────────

def build_binance_aggtrade_ws_url(
    symbols: Iterable[str],
    market: str = "spot",
) -> str:
    """
    Build the public Binance aggTrade WS URL for one or many symbols.

    `market="spot"`    → `wss://stream.binance.com:9443/...`
    `market="futures"` → `wss://fstream.binance.com/...` (USD-M perpetuals)

    Spot, one symbol    → `…/ws/{symbol}@aggTrade`            (LM63B, unchanged)
    Spot, many symbols  → `…/stream?streams=s1@aggTrade/…`
    Futures, any count  → `…/stream?streams=s1@aggTrade/…`    (LM64C)

    LM64C: USD-M futures ALWAYS uses the combined-stream endpoint. The
    single-stream `/ws/{symbol}@aggTrade` form on fstream.binance.com
    connects but closes without delivering any events; the combined
    `/stream?streams=…` form is reliable for one or many symbols alike.

    Raises:
        ValueError: if no valid symbols are supplied, OR if `market` is not
                    one of the supported venues. Silent fallback to spot
                    was removed in LM64B-fix — bad values are now an error.
    """
    cfg = _require_market(market)
    cleaned = _clean_symbols(symbols)
    if not cleaned:
        raise ValueError("at least one valid Binance symbol is required")
    is_spot = cfg is _MARKET_CONFIG["spot"]
    if len(cleaned) == 1 and is_spot:
        return cfg["ws_single"].format(stream=f"{cleaned[0].lower()}@aggTrade")
    streams = "/".join(f"{s.lower()}@aggTrade" for s in cleaned)
    return cfg["ws_combined"].format(streams=streams)


# ── Message parsing ───────────────────────────────────────────────────────────

def parse_agg_trade_message(raw: Any) -> dict | None:
    """
    Parse one raw WS message into a normalized aggTrade dict, or return
    None on bad/incomplete input. NEVER raises on malformed JSON or
    missing fields — the caller can simply skip None results.

    Returns dict shape:
        {
          "agg_id":      int,
          "symbol":      str (uppercase),
          "price":       float,
          "quantity":    float,
          "trade_ts_ms": int,
          "is_maker":    bool,
        }
    """
    if raw is None:
        return None

    obj: Any = raw
    if isinstance(raw, (str, bytes, bytearray)):
        try:
            obj = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None
    if not isinstance(obj, dict):
        return None

    # Combined-stream wrapper: {"stream": "...", "data": {...}}
    if "data" in obj and isinstance(obj["data"], dict):
        obj = obj["data"]

    # Only treat objects that look like aggTrade payloads. We don't
    # demand the "e" field because some upstream samples omit it.
    if "a" not in obj or "p" not in obj or "q" not in obj or "s" not in obj:
        return None

    try:
        agg_id   = int(obj["a"])
        symbol   = str(obj["s"]).strip().upper()
        price    = float(obj["p"])
        quantity = float(obj["q"])
    except (TypeError, ValueError):
        return None

    if not symbol or price <= 0 or quantity <= 0:
        return None

    # Trade timestamp — prefer T (trade time), then E (event time), then now.
    ts_ms_raw = obj.get("T", obj.get("E"))
    try:
        trade_ts_ms = int(ts_ms_raw) if ts_ms_raw is not None else int(time.time() * 1000)
    except (TypeError, ValueError):
        trade_ts_ms = int(time.time() * 1000)

    is_maker = bool(obj.get("m", False))

    return {
        "agg_id":      agg_id,
        "symbol":      symbol,
        "price":       price,
        "quantity":    quantity,
        "trade_ts_ms": trade_ts_ms,
        "is_maker":    is_maker,
    }


# ── Normalize to whale-engine v2 input shape ─────────────────────────────────

def _iso_from_ms(ts_ms: int) -> str:
    """Convert ms since epoch → ISO 8601 UTC string. Robust to bad input."""
    try:
        return datetime.fromtimestamp(int(ts_ms) / 1000.0, tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError, OverflowError):
        return datetime.now(timezone.utc).isoformat()


def normalize_agg_trade_to_whale_input(
    parsed: dict,
    market: str = "spot",
) -> dict:
    """
    Convert a `parse_agg_trade_message` result into a dict matching the
    `detect_whale_events` v2 item schema.

    `market` controls `source_type` and `exchange`:
        spot    → "exchange_trade" / "binance_spot"     (LM63B, default)
        futures → "futures_trade"  / "binance_futures"  (LM64B)

    Unknown markets fall back to spot semantics. The chosen label is also
    stamped into `metadata.market` so consumers can filter without parsing
    the `exchange` string.

    Returns:
        {
          source_type:   "exchange_trade" | "futures_trade",
          symbol:        "BTCUSDT",
          chain:         "",
          exchange:      "binance_spot" | "binance_futures",
          side:          "buy" | "sell",
          amount:        float,
          price:         float,
          notional_usd:  float,
          wallet:        "agg:{agg_id}",
          tx_hash:       "agg:{symbol}:{agg_id}",
          event_ts:      ISO 8601 UTC,
          metadata: { "agg_trade_id": int, "source": "binance_aggtrade",
                      "trade_ts_ms": int, "is_maker": bool,
                      "market": "spot" | "futures" },
        }

    Raises:
        TypeError: if `parsed` is not a dict.
        KeyError:  if any required field is missing in `parsed`.
    """
    if not isinstance(parsed, dict):
        raise TypeError(f"parsed must be a dict, got {type(parsed).__name__}")

    cfg = _require_market(market)
    market_label = "futures" if cfg is _MARKET_CONFIG["futures"] else "spot"

    agg_id      = int(parsed["agg_id"])
    symbol      = str(parsed["symbol"]).strip().upper()
    price       = float(parsed["price"])
    quantity    = float(parsed["quantity"])
    trade_ts_ms = int(parsed["trade_ts_ms"])
    is_maker    = bool(parsed["is_maker"])

    side = "sell" if is_maker else "buy"
    notional_usd = round(price * quantity, 8)

    return {
        "source_type":  cfg["source_type"],
        "symbol":       symbol,
        "chain":        "",
        "exchange":     cfg["exchange"],
        "side":         side,
        "amount":       quantity,
        "price":        price,
        "notional_usd": notional_usd,
        "wallet":       f"agg:{agg_id}",
        "tx_hash":      f"agg:{symbol}:{agg_id}",
        "event_ts":     _iso_from_ms(trade_ts_ms),
        "metadata": {
            "agg_trade_id": agg_id,
            "source":       "binance_aggtrade",
            "trade_ts_ms":  trade_ts_ms,
            "is_maker":     is_maker,
            "market":       market_label,
        },
    }


# ── Iterator ──────────────────────────────────────────────────────────────────

def iter_binance_aggtrades(
    symbols: Iterable[str],
    message_iter: Iterable[Any] | None = None,
    *,
    market: str = "spot",
    symbol_filter: bool = True,
    progress: Callable[[str], None] | None = None,
) -> Iterator[dict]:
    """
    Yield whale-engine v2 input dicts from a Binance aggTrade WS feed.

    `market` selects the Spot or USD-M Futures endpoint and tag:
        "spot"    → wss://stream.binance.com:9443/...   (default)
        "futures" → wss://fstream.binance.com/...        (LM64B)

    When `message_iter` is None the real public WebSocket is opened via
    a lazy `websocket-client` import and the iterator stays alive across
    reconnects. When `message_iter` is provided, no network is touched —
    the caller can drive the generator from any source (tests, replay,
    a file).

    Args:
        symbols:        Iterable of Binance symbols. Invalid entries
                        are skipped without raising.
        message_iter:   Optional pre-supplied iterable of raw WS frames
                        (str/bytes/dict). When None, a real WS connection
                        is opened.
        market:         "spot" (default) or "futures". Unknown values fall
                        back to spot to preserve LM63B behavior.
        symbol_filter:  When True (default), normalized records whose
                        `symbol` is not in the cleaned symbol set are
                        dropped. Set False to pass everything through.
        progress:       Optional callback for one-line status messages
                        (connect/disconnect).

    Yields:
        dict — `normalize_agg_trade_to_whale_input` result.

    Raises:
        ValueError:  if no valid symbols.
        RuntimeError: if real WS is requested but `websocket-client` is
                      not installed.
    """
    # Validate the market UP-FRONT so a bad value never silently degrades to
    # the spot endpoint partway through the loop.
    _require_market(market)

    cleaned = _clean_symbols(symbols)
    if not cleaned:
        raise ValueError("at least one valid Binance symbol is required")
    allowed: set[str] = set(cleaned)

    if message_iter is None:
        url = build_binance_aggtrade_ws_url(cleaned, market=market)
        message_iter = _default_ws_messages_with_reconnect(url, progress=progress)

    for raw in message_iter:
        if raw is None:
            # Idle tick from a timed-out recv() — let the caller's outer
            # loop run periodic tasks. We simply skip.
            continue
        parsed = parse_agg_trade_message(raw)
        if parsed is None:
            continue
        if symbol_filter and parsed["symbol"] not in allowed:
            continue
        try:
            yield normalize_agg_trade_to_whale_input(parsed, market=market)
        except (TypeError, KeyError, ValueError):
            # Defensive: never let one malformed message kill the stream.
            continue


# ── Real WS transport (lazy import; never touched by tests) ───────────────────

def _default_ws_messages_with_reconnect(
    url: str,
    progress: Callable[[str], None] | None = None,
) -> Iterable[str | None]:
    """
    Generator that yields raw aggTrade WS messages with capped exponential
    reconnect. Lazily imports `websocket-client` so this module (and its
    tests) load without that dependency installed.
    """
    try:
        from websocket import (  # type: ignore[import-not-found]
            WebSocketException,
            WebSocketTimeoutException,
            create_connection,
        )
    except ImportError as exc:  # pragma: no cover - exercised only when installed
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
                    yield None
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


__all__ = [
    "build_binance_aggtrade_ws_url",
    "parse_agg_trade_message",
    "normalize_agg_trade_to_whale_input",
    "iter_binance_aggtrades",
    "is_valid_binance_symbol",
    "VALID_MARKETS",
    "SOURCE_TYPE",
    "EXCHANGE_TAG",
]
