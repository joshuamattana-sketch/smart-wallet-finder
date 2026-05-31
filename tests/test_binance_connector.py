"""
tests/test_binance_connector.py
--------------------------------
Unit tests for connectors/binance.py.

All tests use mock data only — zero real API calls.
Uses unittest.mock.patch to intercept requests.get.

Test classes:
  TestNormalizeSymbol          — input normalisation
  TestParseOrderBookLevels     — _parse_levels internal helper
  TestBuildOrderBookSnapshot   — full fetch_orderbook from mock JSON
  TestFetch24hTicker           — ticker parsing from mock JSON
  TestFetchKlines              — kline parsing from mock JSON
  TestFetchRecentTrades        — trades parsing from mock JSON
  TestErrorHandling            — HTTP errors, malformed data, rate limits
  TestEdgeCases                — empty book, zero-price levels, large books
"""

import sys
import os
import json
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from connectors.binance import (
    EXCHANGE,
    InvalidSymbolError,
    ConnectorError,
    RateLimitError,
    _f,
    _parse_levels,
    normalize_symbol,
    fetch_orderbook,
    fetch_24h_ticker,
    fetch_klines,
    fetch_recent_trades,
)
from core.models import OrderBookLevel, OrderBookSnapshot


# ── Sample Binance API responses ───────────────────────────────────────────────

SAMPLE_DEPTH = {
    "lastUpdateId": 1027024,
    "bids": [
        ["99.50000000", "10.00000000"],
        ["99.00000000", "50.00000000"],
        ["98.00000000", "5.00000000"],
    ],
    "asks": [
        ["100.50000000", "8.00000000"],
        ["101.00000000", "20.00000000"],
        ["102.00000000", "3.00000000"],
    ],
}

SAMPLE_TICKER = {
    "symbol": "BTCUSDT",
    "priceChange": "500.00000000",
    "priceChangePercent": "1.25",
    "weightedAvgPrice": "40250.00000000",
    "prevClosePrice": "40000.00000000",
    "lastPrice": "40500.00000000",
    "lastQty": "0.01000000",
    "bidPrice": "40499.00000000",
    "askPrice": "40501.00000000",
    "openPrice": "40000.00000000",
    "highPrice": "41000.00000000",
    "lowPrice": "39500.00000000",
    "volume": "1234.56000000",
    "quoteVolume": "49750000.00000000",
    "openTime": 1716100000000,
    "closeTime": 1716186400000,
    "firstId": 100000,
    "lastId": 110000,
    "count": 10001,
}

SAMPLE_KLINES = [
    [
        1716100000000,   # open_time_ms
        "40000.00",      # open
        "41000.00",      # high
        "39500.00",      # low
        "40500.00",      # close
        "123.45",        # volume
        1716100059999,   # close_time_ms
        "4987654.32",    # quote_asset_volume
        500,             # trade_count
        "60.00",         # taker_buy_base
        "2430000.00",    # taker_buy_quote
        "0",             # ignore
    ],
    [
        1716100060000,
        "40500.00",
        "40800.00",
        "40200.00",
        "40600.00",
        "98.76",
        1716100119999,
        "4009480.00",
        430,
        "50.00",
        "2025000.00",
        "0",
    ],
]

SAMPLE_TRADES = [
    {
        "id": 28457,
        "price": "40500.00000000",
        "qty": "0.00100000",
        "quoteQty": "40.50000000",
        "time": 1716100000000,
        "isBuyerMaker": False,
        "isBestMatch": True,
    },
    {
        "id": 28458,
        "price": "40499.00000000",
        "qty": "0.00500000",
        "quoteQty": "202.49500000",
        "time": 1716100001000,
        "isBuyerMaker": True,
        "isBestMatch": True,
    },
]


# ── Mock response builder ──────────────────────────────────────────────────────

def mock_response(data: dict | list, status_code: int = 200) -> MagicMock:
    """Build a mock requests.Response object returning given data."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.ok = (200 <= status_code < 300)
    resp.json.return_value = data
    resp.text = json.dumps(data) if isinstance(data, (dict, list)) else str(data)
    resp.headers = {}
    return resp


def mock_error_response(status_code: int, binance_code: int, msg: str) -> MagicMock:
    """Build a mock error response matching Binance error shape."""
    data = {"code": binance_code, "msg": msg}
    resp = MagicMock()
    resp.status_code = status_code
    resp.ok = False
    resp.json.return_value = data
    resp.text = json.dumps(data)
    resp.headers = {}
    return resp


# ══ TestNormalizeSymbol ════════════════════════════════════════════════════════

class TestNormalizeSymbol:
    def test_lowercase_converted(self):
        assert normalize_symbol("btcusdt") == "BTCUSDT"

    def test_already_uppercase(self):
        assert normalize_symbol("BTCUSDT") == "BTCUSDT"

    def test_slash_removed(self):
        assert normalize_symbol("BTC/USDT") == "BTCUSDT"

    def test_dash_removed(self):
        assert normalize_symbol("eth-usdt") == "ETHUSDT"

    def test_underscore_removed(self):
        assert normalize_symbol("SOL_USDT") == "SOLUSDT"

    def test_whitespace_stripped(self):
        assert normalize_symbol("  BTCUSDT  ") == "BTCUSDT"

    def test_mixed_case_and_separator(self):
        assert normalize_symbol("  eth-Usdt  ") == "ETHUSDT"

    def test_empty_string_raises(self):
        with pytest.raises(InvalidSymbolError, match="empty"):
            normalize_symbol("")

    def test_whitespace_only_raises(self):
        with pytest.raises(InvalidSymbolError, match="empty"):
            normalize_symbol("   ")

    def test_non_string_raises(self):
        with pytest.raises(InvalidSymbolError, match="string"):
            normalize_symbol(None)  # type: ignore

    def test_integer_raises(self):
        with pytest.raises(InvalidSymbolError):
            normalize_symbol(12345)  # type: ignore

    def test_special_chars_raise(self):
        with pytest.raises(InvalidSymbolError, match="invalid characters"):
            normalize_symbol("BTC@USDT")

    def test_all_default_symbols(self):
        from connectors.binance import SUPPORTED_SYMBOLS
        for sym in SUPPORTED_SYMBOLS:
            assert normalize_symbol(sym) == sym

    def test_lowercase_all_default_symbols(self):
        from connectors.binance import SUPPORTED_SYMBOLS
        for sym in SUPPORTED_SYMBOLS:
            assert normalize_symbol(sym.lower()) == sym


# ══ TestParseOrderBookLevels ══════════════════════════════════════════════════

class TestParseOrderBookLevels:
    def test_parses_bid_levels(self):
        raw = [["99.5", "10.0"], ["99.0", "50.0"]]
        levels = _parse_levels(raw, "bid")
        assert len(levels) == 2
        assert levels[0].price == 99.5
        assert levels[0].qty == 10.0
        assert levels[1].price == 99.0

    def test_usd_size_computed(self):
        raw = [["100.0", "2.5"]]
        levels = _parse_levels(raw, "bid")
        assert levels[0].usd_size == pytest.approx(250.0)

    def test_zero_price_skipped(self):
        raw = [["0.0", "100.0"], ["99.5", "10.0"]]
        levels = _parse_levels(raw, "bid")
        assert len(levels) == 1
        assert levels[0].price == 99.5

    def test_empty_list_returns_empty(self):
        assert _parse_levels([], "bid") == []

    def test_not_list_raises(self):
        with pytest.raises(ConnectorError):
            _parse_levels("not a list", "bid")  # type: ignore

    def test_malformed_element_raises(self):
        with pytest.raises(ConnectorError):
            _parse_levels([{"price": "99"}], "bid")  # type: ignore

    def test_non_numeric_price_raises(self):
        with pytest.raises(ConnectorError):
            _parse_levels([["bad", "1.0"]], "bid")

    def test_non_numeric_qty_raises(self):
        with pytest.raises(ConnectorError):
            _parse_levels([["99.5", "bad"]], "bid")

    def test_short_element_raises(self):
        with pytest.raises(ConnectorError):
            _parse_levels([["99.5"]], "bid")  # only one element

    def test_string_prices_parsed_as_float(self):
        raw = [["45123.50000000", "0.01000000"]]
        levels = _parse_levels(raw, "ask")
        assert levels[0].price == pytest.approx(45123.5)
        assert levels[0].qty == pytest.approx(0.01)

    def test_levels_are_order_book_level_instances(self):
        raw = [["100.0", "1.0"]]
        levels = _parse_levels(raw, "ask")
        assert isinstance(levels[0], OrderBookLevel)


# ══ TestBuildOrderBookSnapshot ════════════════════════════════════════════════

class TestBuildOrderBookSnapshot:
    @patch("connectors.binance.requests.get")
    def test_returns_snapshot(self, mock_get):
        mock_get.return_value = mock_response(SAMPLE_DEPTH)
        snap = fetch_orderbook("BTCUSDT", limit=100)
        assert isinstance(snap, OrderBookSnapshot)

    @patch("connectors.binance.requests.get")
    def test_symbol_preserved(self, mock_get):
        mock_get.return_value = mock_response(SAMPLE_DEPTH)
        snap = fetch_orderbook("BTCUSDT")
        assert snap.symbol == "BTCUSDT"

    @patch("connectors.binance.requests.get")
    def test_exchange_is_binance(self, mock_get):
        mock_get.return_value = mock_response(SAMPLE_DEPTH)
        snap = fetch_orderbook("BTCUSDT")
        assert snap.exchange == EXCHANGE

    @patch("connectors.binance.requests.get")
    def test_lowercase_symbol_normalised(self, mock_get):
        mock_get.return_value = mock_response(SAMPLE_DEPTH)
        snap = fetch_orderbook("btcusdt")
        assert snap.symbol == "BTCUSDT"

    @patch("connectors.binance.requests.get")
    def test_bid_count(self, mock_get):
        mock_get.return_value = mock_response(SAMPLE_DEPTH)
        snap = fetch_orderbook("BTCUSDT")
        assert len(snap.bids) == 3

    @patch("connectors.binance.requests.get")
    def test_ask_count(self, mock_get):
        mock_get.return_value = mock_response(SAMPLE_DEPTH)
        snap = fetch_orderbook("BTCUSDT")
        assert len(snap.asks) == 3

    @patch("connectors.binance.requests.get")
    def test_bids_sorted_descending(self, mock_get):
        mock_get.return_value = mock_response(SAMPLE_DEPTH)
        snap = fetch_orderbook("BTCUSDT")
        prices = [b.price for b in snap.bids]
        assert prices == sorted(prices, reverse=True)

    @patch("connectors.binance.requests.get")
    def test_asks_sorted_ascending(self, mock_get):
        mock_get.return_value = mock_response(SAMPLE_DEPTH)
        snap = fetch_orderbook("BTCUSDT")
        prices = [a.price for a in snap.asks]
        assert prices == sorted(prices)

    @patch("connectors.binance.requests.get")
    def test_best_bid_price(self, mock_get):
        mock_get.return_value = mock_response(SAMPLE_DEPTH)
        snap = fetch_orderbook("BTCUSDT")
        assert snap.best_bid is not None
        assert snap.best_bid.price == pytest.approx(99.5)

    @patch("connectors.binance.requests.get")
    def test_best_ask_price(self, mock_get):
        mock_get.return_value = mock_response(SAMPLE_DEPTH)
        snap = fetch_orderbook("BTCUSDT")
        assert snap.best_ask is not None
        assert snap.best_ask.price == pytest.approx(100.5)

    @patch("connectors.binance.requests.get")
    def test_mid_price_correct(self, mock_get):
        mock_get.return_value = mock_response(SAMPLE_DEPTH)
        snap = fetch_orderbook("BTCUSDT")
        assert snap.mid_price == pytest.approx(100.0)

    @patch("connectors.binance.requests.get")
    def test_usd_size_populated(self, mock_get):
        mock_get.return_value = mock_response(SAMPLE_DEPTH)
        snap = fetch_orderbook("BTCUSDT")
        assert snap.bids[0].usd_size == pytest.approx(99.5 * 10.0)

    @patch("connectors.binance.requests.get")
    def test_timestamp_ms_is_int(self, mock_get):
        mock_get.return_value = mock_response(SAMPLE_DEPTH)
        snap = fetch_orderbook("BTCUSDT")
        assert isinstance(snap.timestamp_ms, int)
        assert snap.timestamp_ms > 0

    @patch("connectors.binance.requests.get")
    def test_has_both_sides_true(self, mock_get):
        mock_get.return_value = mock_response(SAMPLE_DEPTH)
        snap = fetch_orderbook("BTCUSDT")
        assert snap.has_both_sides

    @patch("connectors.binance.requests.get")
    def test_empty_book_both_sides(self, mock_get):
        mock_get.return_value = mock_response({"lastUpdateId": 1, "bids": [], "asks": []})
        snap = fetch_orderbook("BTCUSDT")
        assert snap.is_empty
        assert snap.mid_price == 0.0

    @patch("connectors.binance.requests.get")
    def test_correct_api_url_called(self, mock_get):
        mock_get.return_value = mock_response(SAMPLE_DEPTH)
        fetch_orderbook("BTCUSDT", limit=50)
        call_args = mock_get.call_args
        assert "/api/v3/depth" in call_args[0][0]

    @patch("connectors.binance.requests.get")
    def test_correct_params_sent(self, mock_get):
        mock_get.return_value = mock_response(SAMPLE_DEPTH)
        fetch_orderbook("ETHUSDT", limit=20)
        call_kwargs = mock_get.call_args[1]
        assert call_kwargs["params"]["symbol"] == "ETHUSDT"
        assert call_kwargs["params"]["limit"] == 20

    def test_invalid_limit_raises(self):
        with pytest.raises(ConnectorError, match="limit"):
            fetch_orderbook("BTCUSDT", limit=99)  # 99 not in VALID_DEPTH_LIMITS

    def test_invalid_symbol_raises(self):
        with pytest.raises(InvalidSymbolError):
            fetch_orderbook("")


# ══ TestFetch24hTicker ════════════════════════════════════════════════════════

class TestFetch24hTicker:
    @patch("connectors.binance.requests.get")
    def test_returns_dict(self, mock_get):
        mock_get.return_value = mock_response(SAMPLE_TICKER)
        result = fetch_24h_ticker("BTCUSDT")
        assert isinstance(result, dict)

    @patch("connectors.binance.requests.get")
    def test_symbol_field(self, mock_get):
        mock_get.return_value = mock_response(SAMPLE_TICKER)
        result = fetch_24h_ticker("BTCUSDT")
        assert result["symbol"] == "BTCUSDT"

    @patch("connectors.binance.requests.get")
    def test_price_is_float(self, mock_get):
        mock_get.return_value = mock_response(SAMPLE_TICKER)
        result = fetch_24h_ticker("BTCUSDT")
        assert isinstance(result["price"], float)
        assert result["price"] == pytest.approx(40500.0)

    @patch("connectors.binance.requests.get")
    def test_price_change_pct_is_float(self, mock_get):
        mock_get.return_value = mock_response(SAMPLE_TICKER)
        result = fetch_24h_ticker("BTCUSDT")
        assert isinstance(result["price_change_pct"], float)
        assert result["price_change_pct"] == pytest.approx(1.25)

    @patch("connectors.binance.requests.get")
    def test_volume_is_float(self, mock_get):
        mock_get.return_value = mock_response(SAMPLE_TICKER)
        result = fetch_24h_ticker("BTCUSDT")
        assert isinstance(result["volume_24h"], float)
        assert result["volume_24h"] == pytest.approx(1234.56)

    @patch("connectors.binance.requests.get")
    def test_count_is_int(self, mock_get):
        mock_get.return_value = mock_response(SAMPLE_TICKER)
        result = fetch_24h_ticker("BTCUSDT")
        assert isinstance(result["count"], int)
        assert result["count"] == 10001

    @patch("connectors.binance.requests.get")
    def test_all_expected_keys_present(self, mock_get):
        mock_get.return_value = mock_response(SAMPLE_TICKER)
        result = fetch_24h_ticker("BTCUSDT")
        expected_keys = {
            "symbol", "price", "price_change", "price_change_pct",
            "high_24h", "low_24h", "volume_24h", "quote_volume_24h",
            "open_price", "weighted_avg_price", "bid_price", "ask_price",
            "count", "open_time_ms", "close_time_ms",
        }
        assert expected_keys.issubset(result.keys())

    def test_invalid_symbol_raises(self):
        with pytest.raises(InvalidSymbolError):
            fetch_24h_ticker(None)  # type: ignore


# ══ TestFetchKlines ═══════════════════════════════════════════════════════════

class TestFetchKlines:
    @patch("connectors.binance.requests.get")
    def test_returns_list(self, mock_get):
        mock_get.return_value = mock_response(SAMPLE_KLINES)
        result = fetch_klines("BTCUSDT")
        assert isinstance(result, list)

    @patch("connectors.binance.requests.get")
    def test_correct_length(self, mock_get):
        mock_get.return_value = mock_response(SAMPLE_KLINES)
        result = fetch_klines("BTCUSDT")
        assert len(result) == 2

    @patch("connectors.binance.requests.get")
    def test_open_is_float(self, mock_get):
        mock_get.return_value = mock_response(SAMPLE_KLINES)
        result = fetch_klines("BTCUSDT")
        assert isinstance(result[0]["open"], float)
        assert result[0]["open"] == pytest.approx(40000.0)

    @patch("connectors.binance.requests.get")
    def test_all_ohlcv_keys_present(self, mock_get):
        mock_get.return_value = mock_response(SAMPLE_KLINES)
        result = fetch_klines("BTCUSDT")
        expected = {"open_time_ms", "open", "high", "low", "close",
                    "volume", "close_time_ms", "quote_volume",
                    "trade_count", "taker_buy_volume", "taker_buy_quote_volume"}
        assert expected.issubset(result[0].keys())

    @patch("connectors.binance.requests.get")
    def test_trade_count_is_int(self, mock_get):
        mock_get.return_value = mock_response(SAMPLE_KLINES)
        result = fetch_klines("BTCUSDT")
        assert isinstance(result[0]["trade_count"], int)
        assert result[0]["trade_count"] == 500

    @patch("connectors.binance.requests.get")
    def test_open_time_is_int(self, mock_get):
        mock_get.return_value = mock_response(SAMPLE_KLINES)
        result = fetch_klines("BTCUSDT")
        assert isinstance(result[0]["open_time_ms"], int)

    @patch("connectors.binance.requests.get")
    def test_empty_klines_returns_empty_list(self, mock_get):
        mock_get.return_value = mock_response([])
        result = fetch_klines("BTCUSDT")
        assert result == []

    def test_invalid_interval_raises(self):
        with pytest.raises(ConnectorError, match="interval"):
            fetch_klines("BTCUSDT", interval="2s")  # not a valid interval

    def test_limit_out_of_range_raises(self):
        with pytest.raises(ConnectorError, match="limit"):
            fetch_klines("BTCUSDT", limit=0)

    def test_limit_too_large_raises(self):
        with pytest.raises(ConnectorError, match="limit"):
            fetch_klines("BTCUSDT", limit=1001)

    def test_invalid_symbol_raises(self):
        with pytest.raises(InvalidSymbolError):
            fetch_klines("")


# ══ TestFetchRecentTrades ═════════════════════════════════════════════════════

class TestFetchRecentTrades:
    @patch("connectors.binance.requests.get")
    def test_returns_list(self, mock_get):
        mock_get.return_value = mock_response(SAMPLE_TRADES)
        result = fetch_recent_trades("BTCUSDT")
        assert isinstance(result, list)

    @patch("connectors.binance.requests.get")
    def test_correct_length(self, mock_get):
        mock_get.return_value = mock_response(SAMPLE_TRADES)
        result = fetch_recent_trades("BTCUSDT")
        assert len(result) == 2

    @patch("connectors.binance.requests.get")
    def test_price_is_float(self, mock_get):
        mock_get.return_value = mock_response(SAMPLE_TRADES)
        result = fetch_recent_trades("BTCUSDT")
        assert isinstance(result[0]["price"], float)
        assert result[0]["price"] == pytest.approx(40500.0)

    @patch("connectors.binance.requests.get")
    def test_is_buyer_maker_is_bool(self, mock_get):
        mock_get.return_value = mock_response(SAMPLE_TRADES)
        result = fetch_recent_trades("BTCUSDT")
        assert isinstance(result[0]["is_buyer_maker"], bool)
        assert result[0]["is_buyer_maker"] is False
        assert result[1]["is_buyer_maker"] is True

    @patch("connectors.binance.requests.get")
    def test_all_keys_present(self, mock_get):
        mock_get.return_value = mock_response(SAMPLE_TRADES)
        result = fetch_recent_trades("BTCUSDT")
        expected = {"id", "price", "qty", "quote_qty", "time_ms", "is_buyer_maker"}
        assert expected.issubset(result[0].keys())

    @patch("connectors.binance.requests.get")
    def test_empty_trades(self, mock_get):
        mock_get.return_value = mock_response([])
        result = fetch_recent_trades("BTCUSDT")
        assert result == []

    def test_limit_zero_raises(self):
        with pytest.raises(ConnectorError, match="limit"):
            fetch_recent_trades("BTCUSDT", limit=0)

    def test_limit_too_large_raises(self):
        with pytest.raises(ConnectorError, match="limit"):
            fetch_recent_trades("BTCUSDT", limit=1001)


# ══ TestErrorHandling ═════════════════════════════════════════════════════════

class TestErrorHandling:
    @patch("connectors.binance.requests.get")
    def test_http_400_raises_connector_error(self, mock_get):
        mock_get.return_value = mock_error_response(400, -1121, "Invalid symbol")
        with pytest.raises(ConnectorError) as exc_info:
            fetch_orderbook("BTCUSDT")
        assert "Invalid symbol" in str(exc_info.value) or "400" in str(exc_info.value)

    @patch("connectors.binance.requests.get")
    def test_http_429_raises_rate_limit_error(self, mock_get):
        resp = MagicMock()
        resp.status_code = 429
        resp.ok = False
        resp.headers = {"Retry-After": "30"}
        resp.json.return_value = {}
        resp.text = ""
        mock_get.return_value = resp
        with pytest.raises(RateLimitError):
            fetch_orderbook("BTCUSDT")

    @patch("connectors.binance.requests.get")
    def test_http_418_raises_rate_limit_error(self, mock_get):
        resp = MagicMock()
        resp.status_code = 418
        resp.ok = False
        resp.headers = {}
        resp.json.return_value = {}
        resp.text = "IP banned"
        mock_get.return_value = resp
        with pytest.raises(RateLimitError, match="418"):
            fetch_orderbook("BTCUSDT")

    @patch("connectors.binance.requests.get")
    def test_http_500_raises_connector_error(self, mock_get):
        resp = MagicMock()
        resp.status_code = 500
        resp.ok = False
        resp.headers = {}
        resp.json.side_effect = ValueError("no json")
        resp.text = "Internal server error"
        mock_get.return_value = resp
        with pytest.raises(ConnectorError):
            fetch_orderbook("BTCUSDT")

    @patch("connectors.binance.requests.get")
    def test_timeout_raises_connector_error(self, mock_get):
        import requests as req
        mock_get.side_effect = req.exceptions.Timeout("timed out")
        with pytest.raises(ConnectorError, match="timed out"):
            fetch_orderbook("BTCUSDT")

    @patch("connectors.binance.requests.get")
    def test_connection_error_raises_connector_error(self, mock_get):
        import requests as req
        mock_get.side_effect = req.exceptions.ConnectionError("no route to host")
        with pytest.raises(ConnectorError, match="Connection"):
            fetch_orderbook("BTCUSDT")

    @patch("connectors.binance.requests.get")
    def test_bad_json_response_raises_connector_error(self, mock_get):
        resp = MagicMock()
        resp.status_code = 200
        resp.ok = True
        resp.headers = {}
        resp.json.side_effect = ValueError("bad json")
        mock_get.return_value = resp
        with pytest.raises(ConnectorError):
            fetch_orderbook("BTCUSDT")

    @patch("connectors.binance.requests.get")
    def test_wrong_response_type_raises(self, mock_get):
        # /api/v3/depth returns a dict, not a list — if we get a list, error
        mock_get.return_value = mock_response([1, 2, 3])
        with pytest.raises(ConnectorError):
            fetch_orderbook("BTCUSDT")

    @patch("connectors.binance.requests.get")
    def test_malformed_kline_raises(self, mock_get):
        # Kline with only 5 elements instead of 11+
        mock_get.return_value = mock_response([[1716100000000, "40000", "41000"]])
        with pytest.raises(ConnectorError):
            fetch_klines("BTCUSDT")

    @patch("connectors.binance.requests.get")
    def test_malformed_trade_raises(self, mock_get):
        mock_get.return_value = mock_response(["not a dict"])
        with pytest.raises(ConnectorError):
            fetch_recent_trades("BTCUSDT")


# ══ TestEdgeCases ═════════════════════════════════════════════════════════════

class TestEdgeCases:
    @patch("connectors.binance.requests.get")
    def test_empty_bids_and_asks(self, mock_get):
        mock_get.return_value = mock_response({"lastUpdateId": 1, "bids": [], "asks": []})
        snap = fetch_orderbook("BTCUSDT")
        assert snap.is_empty
        assert snap.mid_price == 0.0
        assert not snap.has_both_sides

    @patch("connectors.binance.requests.get")
    def test_zero_price_levels_skipped(self, mock_get):
        depth = {
            "lastUpdateId": 1,
            "bids": [["0.0", "100.0"], ["99.5", "10.0"]],
            "asks": [["100.5", "8.0"]],
        }
        mock_get.return_value = mock_response(depth)
        snap = fetch_orderbook("BTCUSDT")
        # The zero-price bid should be skipped
        assert all(b.price > 0 for b in snap.bids)
        assert len(snap.bids) == 1

    @patch("connectors.binance.requests.get")
    def test_single_level_each_side(self, mock_get):
        depth = {
            "lastUpdateId": 1,
            "bids": [["99.0", "5.0"]],
            "asks": [["101.0", "5.0"]],
        }
        mock_get.return_value = mock_response(depth)
        snap = fetch_orderbook("BTCUSDT")
        assert snap.has_both_sides
        assert snap.mid_price == pytest.approx(100.0)

    @patch("connectors.binance.requests.get")
    def test_large_book_parsed(self, mock_get):
        bids = [[str(100.0 - i * 0.01), "1.0"] for i in range(100)]
        asks = [[str(100.01 + i * 0.01), "1.0"] for i in range(100)]
        mock_get.return_value = mock_response({"lastUpdateId": 99, "bids": bids, "asks": asks})
        snap = fetch_orderbook("BTCUSDT")
        assert len(snap.bids) == 100
        assert len(snap.asks) == 100
        # Bids sorted descending
        assert snap.bids[0].price >= snap.bids[-1].price

    @patch("connectors.binance.requests.get")
    def test_btcusdt_realistic_prices(self, mock_get):
        depth = {
            "lastUpdateId": 99,
            "bids": [["67432.50000000", "0.12300000"]],
            "asks": [["67433.10000000", "0.05000000"]],
        }
        mock_get.return_value = mock_response(depth)
        snap = fetch_orderbook("BTCUSDT")
        assert snap.best_bid.price == pytest.approx(67432.5)
        assert snap.best_ask.price == pytest.approx(67433.1)
        assert snap.mid_price == pytest.approx((67432.5 + 67433.1) / 2, rel=1e-6)

    def test_f_helper_string_float(self):
        assert _f("45123.50000000") == pytest.approx(45123.5)

    def test_f_helper_zero(self):
        assert _f(0) == 0.0
        assert _f("0") == 0.0
        assert _f("0.00000000") == 0.0

    def test_f_helper_bad_string(self):
        assert _f("bad") == 0.0

    def test_f_helper_none(self):
        assert _f(None) == 0.0

    def test_f_helper_negative(self):
        assert _f("-123.45") == pytest.approx(-123.45)
