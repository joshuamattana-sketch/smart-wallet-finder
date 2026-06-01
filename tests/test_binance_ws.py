"""
tests/test_binance_ws.py
--------------------------
Unit tests for connectors/binance_ws.py.

Zero real WebSocket connections. All inputs are inline dicts/strings.

Test classes:
  TestBuildDepthStreamName     — stream name construction
  TestBuildSubscribeMessage    — subscribe/unsubscribe message builders
  TestNormalizeDepthLevels     — raw → normalised level conversion
  TestParseDepthMessage        — message type routing and field extraction
  TestParseDepthMessageEdges   — malformed / empty / bytes inputs
  TestPrivateHelpers           — _clean_symbol, _symbol_from_stream, _safe_normalize
  TestListenDepthImportGuard   — ImportError when websockets absent
"""

import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from connectors.binance_ws import (
    VALID_DEPTH_LEVELS,
    VALID_SPEED_MS,
    WS_BASE_URL,
    WSConnectorError,
    WSMessageError,
    _clean_symbol,
    _safe_normalize,
    _symbol_from_stream,
    build_depth_stream_name,
    build_subscribe_message,
    build_unsubscribe_message,
    normalize_depth_levels,
    parse_depth_message,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

PARTIAL_BOOK_MSG = {
    "lastUpdateId": 160,
    "bids": [["99.0", "5.0"], ["98.5", "2.0"]],
    "asks": [["101.0", "3.0"], ["101.5", "1.0"]],
}

DIFF_DEPTH_MSG = {
    "e": "depthUpdate",
    "E": 1_716_200_000_000,
    "s": "BTCUSDT",
    "U": 160,
    "u": 161,
    "b": [["100.0", "5.0"], ["99.5", "1.5"]],
    "a": [["101.0", "3.0"]],
}

COMBINED_STREAM_MSG = {
    "stream": "btcusdt@depth20@100ms",
    "data": {
        "lastUpdateId": 200,
        "bids": [["99.0", "1.0"], ["98.0", "2.0"]],
        "asks": [["101.0", "2.0"]],
    },
}

ACK_MSG = {"result": None, "id": 1}


# ══ TestBuildDepthStreamName ══════════════════════════════════════════════════

class TestBuildDepthStreamName:
    def test_default_params(self):
        assert build_depth_stream_name("BTCUSDT") == "btcusdt@depth20@100ms"

    def test_lowercase_output(self):
        result = build_depth_stream_name("BTCUSDT")
        assert result == result.lower()

    def test_slash_separator_removed(self):
        assert build_depth_stream_name("BTC/USDT") == "btcusdt@depth20@100ms"

    def test_dash_separator_removed(self):
        assert build_depth_stream_name("ETH-USDT") == "ethusdt@depth20@100ms"

    def test_underscore_separator_removed(self):
        assert build_depth_stream_name("SOL_USDT") == "solusdt@depth20@100ms"

    def test_whitespace_stripped(self):
        assert build_depth_stream_name("  BTCUSDT  ") == "btcusdt@depth20@100ms"

    def test_levels_5(self):
        assert build_depth_stream_name("BTCUSDT", levels=5) == "btcusdt@depth5@100ms"

    def test_levels_10(self):
        assert build_depth_stream_name("BTCUSDT", levels=10) == "btcusdt@depth10@100ms"

    def test_levels_20(self):
        assert build_depth_stream_name("BTCUSDT", levels=20) == "btcusdt@depth20@100ms"

    def test_speed_1000ms(self):
        assert build_depth_stream_name("BTCUSDT", speed_ms=1000) == "btcusdt@depth20@1000ms"

    def test_levels_5_speed_1000(self):
        assert build_depth_stream_name("ETHUSDT", levels=5, speed_ms=1000) == "ethusdt@depth5@1000ms"

    def test_invalid_levels_raises(self):
        with pytest.raises(ValueError, match="levels"):
            build_depth_stream_name("BTCUSDT", levels=7)

    def test_zero_levels_raises(self):
        with pytest.raises(ValueError, match="levels"):
            build_depth_stream_name("BTCUSDT", levels=0)

    def test_invalid_speed_raises(self):
        with pytest.raises(ValueError, match="speed_ms"):
            build_depth_stream_name("BTCUSDT", speed_ms=500)

    def test_none_symbol_raises(self):
        with pytest.raises(TypeError, match="symbol"):
            build_depth_stream_name(None)  # type: ignore

    def test_empty_symbol_raises(self):
        with pytest.raises(ValueError, match="empty"):
            build_depth_stream_name("")

    def test_format_structure(self):
        result = build_depth_stream_name("SOLUSDT", levels=10, speed_ms=100)
        parts = result.split("@")
        assert len(parts) == 3
        assert parts[0] == "solusdt"
        assert parts[1] == "depth10"
        assert parts[2] == "100ms"


# ══ TestBuildSubscribeMessage ════════════════════════════════════════════════

class TestBuildSubscribeMessage:
    def test_single_symbol(self):
        msg = build_subscribe_message(["BTCUSDT"])
        assert msg["method"] == "SUBSCRIBE"
        assert "btcusdt@depth20@100ms" in msg["params"]
        assert msg["id"] == 1

    def test_multiple_symbols(self):
        msg = build_subscribe_message(["BTCUSDT", "ETHUSDT"])
        assert len(msg["params"]) == 2
        assert "btcusdt@depth20@100ms" in msg["params"]
        assert "ethusdt@depth20@100ms" in msg["params"]

    def test_custom_levels(self):
        msg = build_subscribe_message(["BTCUSDT"], levels=5)
        assert "btcusdt@depth5@100ms" in msg["params"]

    def test_custom_speed(self):
        msg = build_subscribe_message(["BTCUSDT"], speed_ms=1000)
        assert "btcusdt@depth20@1000ms" in msg["params"]

    def test_custom_request_id(self):
        msg = build_subscribe_message(["BTCUSDT"], request_id=42)
        assert msg["id"] == 42

    def test_default_request_id_is_1(self):
        msg = build_subscribe_message(["BTCUSDT"])
        assert msg["id"] == 1

    def test_empty_symbols_raises(self):
        with pytest.raises(ValueError, match="empty"):
            build_subscribe_message([])

    def test_non_list_raises(self):
        with pytest.raises(TypeError, match="list"):
            build_subscribe_message("BTCUSDT")  # type: ignore

    def test_invalid_levels_raises(self):
        with pytest.raises(ValueError, match="levels"):
            build_subscribe_message(["BTCUSDT"], levels=99)

    def test_invalid_speed_raises(self):
        with pytest.raises(ValueError, match="speed_ms"):
            build_subscribe_message(["BTCUSDT"], speed_ms=200)

    def test_result_is_json_serialisable(self):
        msg = build_subscribe_message(["BTCUSDT", "ETHUSDT"])
        serialised = json.dumps(msg)
        assert isinstance(serialised, str)

    def test_unsubscribe_method(self):
        msg = build_unsubscribe_message(["BTCUSDT"], request_id=5)
        assert msg["method"] == "UNSUBSCRIBE"
        assert msg["id"] == 5
        assert "btcusdt@depth20@100ms" in msg["params"]

    def test_separator_stripped_in_params(self):
        msg = build_subscribe_message(["BTC/USDT"])
        assert "btcusdt@depth20@100ms" in msg["params"]


# ══ TestNormalizeDepthLevels ══════════════════════════════════════════════════

class TestNormalizeDepthLevels:
    def test_basic_conversion(self):
        result = normalize_depth_levels([["100.0", "5.0"]])
        assert len(result) == 1
        assert result[0] == {"price": 100.0, "size": 5.0, "notional": 500.0}

    def test_multiple_levels(self):
        result = normalize_depth_levels([["99.5", "2.5"], ["99.0", "1.0"]])
        assert len(result) == 2
        assert result[0]["price"] == 99.5
        assert result[1]["price"] == 99.0

    def test_notional_computed(self):
        result = normalize_depth_levels([["67420.0", "0.5"]])
        assert result[0]["notional"] == pytest.approx(67420.0 * 0.5)

    def test_empty_list_returns_empty(self):
        assert normalize_depth_levels([]) == []

    def test_zero_size_included(self):
        # Binance uses 0-size entries as DELETE signals
        result = normalize_depth_levels([["100.0", "0.0"]])
        assert len(result) == 1
        assert result[0]["size"] == 0.0

    def test_string_prices_parsed(self):
        result = normalize_depth_levels([["45123.50000000", "0.01000000"]])
        assert result[0]["price"] == pytest.approx(45123.5)
        assert result[0]["size"] == pytest.approx(0.01)

    def test_float_inputs_accepted(self):
        result = normalize_depth_levels([[100.0, 5.0]])
        assert result[0]["price"] == 100.0

    def test_not_list_raises_type_error(self):
        with pytest.raises(TypeError):
            normalize_depth_levels("not a list")  # type: ignore

    def test_malformed_element_raises(self):
        with pytest.raises(WSMessageError):
            normalize_depth_levels([{"price": "100"}])  # type: ignore

    def test_non_numeric_price_raises(self):
        with pytest.raises(WSMessageError):
            normalize_depth_levels([["bad_price", "1.0"]])

    def test_non_numeric_size_raises(self):
        with pytest.raises(WSMessageError):
            normalize_depth_levels([["100.0", "bad_size"]])

    def test_short_element_raises(self):
        with pytest.raises(WSMessageError):
            normalize_depth_levels([["100.0"]])  # only one element

    def test_output_keys_correct(self):
        result = normalize_depth_levels([["100.0", "1.0"]])
        assert set(result[0].keys()) == {"price", "size", "notional"}

    def test_price_and_size_are_floats(self):
        result = normalize_depth_levels([["100.0", "5.0"]])
        assert isinstance(result[0]["price"],    float)
        assert isinstance(result[0]["size"],     float)
        assert isinstance(result[0]["notional"], float)


# ══ TestParseDepthMessage ═════════════════════════════════════════════════════

class TestParseDepthMessage:
    # ── Partial book snapshot ──────────────────────────────────────────────────

    def test_partial_book_type(self):
        assert parse_depth_message(PARTIAL_BOOK_MSG)["type"] == "depth"

    def test_partial_book_last_update_id(self):
        p = parse_depth_message(PARTIAL_BOOK_MSG)
        assert p["last_update_id"] == 160

    def test_partial_book_bid_count(self):
        p = parse_depth_message(PARTIAL_BOOK_MSG)
        assert len(p["bids"]) == 2

    def test_partial_book_ask_count(self):
        p = parse_depth_message(PARTIAL_BOOK_MSG)
        assert len(p["asks"]) == 2

    def test_partial_book_bid_price(self):
        p = parse_depth_message(PARTIAL_BOOK_MSG)
        assert p["bids"][0]["price"] == 99.0

    def test_partial_book_raw_preserved(self):
        p = parse_depth_message(PARTIAL_BOOK_MSG)
        assert p["raw"] is PARTIAL_BOOK_MSG

    # ── Diff depth event ──────────────────────────────────────────────────────

    def test_diff_event_type(self):
        assert parse_depth_message(DIFF_DEPTH_MSG)["type"] == "depth"

    def test_diff_event_symbol(self):
        assert parse_depth_message(DIFF_DEPTH_MSG)["symbol"] == "BTCUSDT"

    def test_diff_event_event_time(self):
        assert parse_depth_message(DIFF_DEPTH_MSG)["event_time"] == 1_716_200_000_000

    def test_diff_event_bids(self):
        p = parse_depth_message(DIFF_DEPTH_MSG)
        assert len(p["bids"]) == 2
        assert p["bids"][0]["price"] == 100.0

    def test_diff_event_asks(self):
        p = parse_depth_message(DIFF_DEPTH_MSG)
        assert len(p["asks"]) == 1

    # ── Combined stream ───────────────────────────────────────────────────────

    def test_combined_stream_type(self):
        assert parse_depth_message(COMBINED_STREAM_MSG)["type"] == "depth"

    def test_combined_stream_symbol_extracted(self):
        p = parse_depth_message(COMBINED_STREAM_MSG)
        assert p["symbol"] == "BTCUSDT"

    def test_combined_stream_last_update_id(self):
        p = parse_depth_message(COMBINED_STREAM_MSG)
        assert p["last_update_id"] == 200

    def test_combined_stream_bids(self):
        p = parse_depth_message(COMBINED_STREAM_MSG)
        assert len(p["bids"]) == 2

    # ── ACK message ───────────────────────────────────────────────────────────

    def test_ack_type(self):
        assert parse_depth_message(ACK_MSG)["type"] == "ack"

    def test_ack_bids_empty(self):
        assert parse_depth_message(ACK_MSG)["bids"] == []

    def test_ack_asks_empty(self):
        assert parse_depth_message(ACK_MSG)["asks"] == []

    def test_ack_raw_preserved(self):
        p = parse_depth_message(ACK_MSG)
        assert p["raw"] is ACK_MSG

    # ── JSON string input ─────────────────────────────────────────────────────

    def test_json_string_accepted(self):
        p = parse_depth_message(json.dumps(PARTIAL_BOOK_MSG))
        assert p["type"] == "depth"

    def test_bytes_accepted(self):
        p = parse_depth_message(json.dumps(PARTIAL_BOOK_MSG).encode())
        assert p["type"] == "depth"

    # ── Result keys always present ────────────────────────────────────────────

    def test_all_result_keys_present(self):
        expected = {"type", "symbol", "bids", "asks", "event_time",
                    "last_update_id", "raw"}
        for msg in [PARTIAL_BOOK_MSG, DIFF_DEPTH_MSG, COMBINED_STREAM_MSG, ACK_MSG]:
            p = parse_depth_message(msg)
            assert expected.issubset(p.keys()), f"Missing keys for {msg}"


# ══ TestParseDepthMessageEdges ════════════════════════════════════════════════

class TestParseDepthMessageEdges:
    def test_empty_dict_no_crash(self):
        p = parse_depth_message({})
        assert p["bids"] == []
        assert p["asks"] == []
        assert p["type"] in ("depth", "unknown", "ack")

    def test_bids_asks_empty_lists(self):
        p = parse_depth_message({"lastUpdateId": 1, "bids": [], "asks": []})
        assert p["type"] == "depth"
        assert p["bids"] == []
        assert p["asks"] == []

    def test_malformed_bid_level_returns_empty(self):
        # _safe_normalize catches bad levels without crashing parse
        msg = {"lastUpdateId": 1, "bids": ["not a pair"], "asks": []}
        p = parse_depth_message(msg)
        assert p["bids"] == []

    def test_missing_bids_key(self):
        msg = {"lastUpdateId": 1, "asks": [["101.0", "1.0"]]}
        p = parse_depth_message(msg)
        assert p["bids"] == []
        assert len(p["asks"]) == 1

    def test_bad_json_string_raises(self):
        with pytest.raises(WSMessageError, match="JSON"):
            parse_depth_message("not valid json {{{")

    def test_non_dict_json_raises(self):
        with pytest.raises(WSMessageError):
            parse_depth_message("[1, 2, 3]")

    def test_wrong_type_raises(self):
        with pytest.raises(WSMessageError):
            parse_depth_message(12345)  # type: ignore

    def test_bytes_utf8_decoded(self):
        raw = json.dumps(DIFF_DEPTH_MSG).encode("utf-8")
        p   = parse_depth_message(raw)
        assert p["symbol"] == "BTCUSDT"

    def test_unknown_message_type(self):
        msg = {"unknown_key": "unknown_value"}
        p   = parse_depth_message(msg)
        assert p["type"] in ("unknown", "depth", "ack")  # won't crash

    def test_combined_with_malformed_data_raises(self):
        msg = {"stream": "btcusdt@depth20@100ms", "data": "not a dict"}
        with pytest.raises(WSMessageError):
            parse_depth_message(msg)

    def test_large_realistic_message(self):
        bids = [[str(99.0 - i * 0.01), str(1.0 + i * 0.1)] for i in range(20)]
        asks = [[str(101.0 + i * 0.01), str(1.0 + i * 0.1)] for i in range(20)]
        msg  = {"lastUpdateId": 99999, "bids": bids, "asks": asks}
        p    = parse_depth_message(msg)
        assert len(p["bids"]) == 20
        assert len(p["asks"]) == 20


# ══ TestPrivateHelpers ════════════════════════════════════════════════════════

class TestPrivateHelpers:
    # _clean_symbol
    def test_clean_symbol_lowercase(self):
        assert _clean_symbol("BTCUSDT") == "btcusdt"

    def test_clean_symbol_slash_removed(self):
        assert _clean_symbol("BTC/USDT") == "btcusdt"

    def test_clean_symbol_dash_removed(self):
        assert _clean_symbol("ETH-USDT") == "ethusdt"

    def test_clean_symbol_underscore_removed(self):
        assert _clean_symbol("SOL_USDT") == "solusdt"

    def test_clean_symbol_whitespace_stripped(self):
        assert _clean_symbol("  BTCUSDT  ") == "btcusdt"

    def test_clean_symbol_none_raises(self):
        with pytest.raises(TypeError, match="symbol"):
            _clean_symbol(None)  # type: ignore

    def test_clean_symbol_empty_raises(self):
        with pytest.raises(ValueError, match="empty"):
            _clean_symbol("")

    def test_clean_symbol_whitespace_only_raises(self):
        with pytest.raises(ValueError, match="empty"):
            _clean_symbol("   ")

    # _symbol_from_stream
    def test_symbol_from_stream_basic(self):
        assert _symbol_from_stream("btcusdt@depth20@100ms") == "BTCUSDT"

    def test_symbol_from_stream_eth(self):
        assert _symbol_from_stream("ethusdt@depth5@1000ms") == "ETHUSDT"

    def test_symbol_from_stream_empty(self):
        assert _symbol_from_stream("") == ""

    def test_symbol_from_stream_no_at(self):
        assert _symbol_from_stream("nodepth") == ""

    # _safe_normalize
    def test_safe_normalize_valid(self):
        result = _safe_normalize([["100.0", "1.0"]])
        assert len(result) == 1
        assert result[0]["price"] == 100.0

    def test_safe_normalize_empty(self):
        assert _safe_normalize([]) == []

    def test_safe_normalize_bad_input_returns_empty(self):
        assert _safe_normalize("not a list") == []  # type: ignore

    def test_safe_normalize_malformed_returns_empty(self):
        assert _safe_normalize([{"price": 100}]) == []  # type: ignore


# ══ TestListenDepthImportGuard ════════════════════════════════════════════════

class TestListenDepthImportGuard:
    def test_listen_depth_raises_import_error_without_websockets(self):
        """
        listen_depth should raise ImportError with a clear install message
        when websockets is not installed.
        We simulate this by temporarily hiding the module.
        """
        import sys
        import asyncio
        from connectors.binance_ws import listen_depth

        # Stash and remove websockets from sys.modules
        _ws_saved = sys.modules.pop("websockets", None)
        _ws_client_saved = sys.modules.pop("websockets.client", None)
        try:
            async def try_listen():
                # listen_depth is an async generator — must be iterated
                gen = listen_depth(["BTCUSDT"])
                await gen.__anext__()

            with pytest.raises(ImportError, match="websockets"):
                asyncio.run(try_listen())
        finally:
            if _ws_saved is not None:
                sys.modules["websockets"] = _ws_saved
            if _ws_client_saved is not None:
                sys.modules["websockets.client"] = _ws_client_saved

    def test_listen_depth_is_async_generator(self):
        """listen_depth must be an async generator function."""
        import inspect
        from connectors.binance_ws import listen_depth
        assert inspect.isasyncgenfunction(listen_depth)

    def test_listen_depth_accepts_correct_params(self):
        """listen_depth must accept symbols, levels, speed_ms without error."""
        import inspect
        from connectors.binance_ws import listen_depth
        sig = inspect.signature(listen_depth)
        params = list(sig.parameters.keys())
        assert "symbols"   in params
        assert "levels"    in params
        assert "speed_ms"  in params

    def test_constants_exported(self):
        assert len(VALID_DEPTH_LEVELS) == 3
        assert 5 in VALID_DEPTH_LEVELS
        assert 10 in VALID_DEPTH_LEVELS
        assert 20 in VALID_DEPTH_LEVELS
        assert len(VALID_SPEED_MS) == 2
        assert 100 in VALID_SPEED_MS
        assert 1000 in VALID_SPEED_MS
        assert WS_BASE_URL.startswith("wss://")
