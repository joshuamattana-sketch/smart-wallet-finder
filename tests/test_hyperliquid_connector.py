"""
tests/test_hyperliquid_connector.py
-------------------------------------
Unit tests for connectors/hyperliquid.py.

All tests use mock data only — zero real API calls.
Uses unittest.mock.patch to intercept requests.post.

Test classes:
  TestNormalizeCoin            — coin name normalisation
  TestParseHLLevels            — _parse_hl_levels internal helper
  TestBuildOrderBookSnapshot   — fetch_l2_book from mock JSON
  TestFetchMeta                — fetch_meta from mock JSON
  TestFetchAllMids             — fetch_all_mids from mock JSON
  TestFetchRecentTrades        — fetch_recent_trades from mock JSON
  TestErrorHandling            — HTTP errors, malformed data, rate limits
  TestEdgeCases                — empty book, zero-price, single level
"""

import sys
import os
import json
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from connectors.hyperliquid import (
    EXCHANGE,
    HyperliquidError,
    HyperliquidRateLimitError,
    InvalidCoinError,
    _parse_hl_levels,
    fetch_all_mids,
    fetch_l2_book,
    fetch_meta,
    fetch_recent_trades,
    normalize_coin,
    post_info,
)
from core.models import OrderBookLevel, OrderBookSnapshot


# ── Sample API responses ───────────────────────────────────────────────────────

SAMPLE_L2 = {
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

SAMPLE_META = {
    "universe": [
        {"name": "BTC",  "szDecimals": 3, "maxLeverage": 50},
        {"name": "ETH",  "szDecimals": 2, "maxLeverage": 50},
        {"name": "HYPE", "szDecimals": 0, "maxLeverage": 5},
        {"name": "SOL",  "szDecimals": 1, "maxLeverage": 20},
    ]
}

SAMPLE_MIDS = {
    "BTC":  "67420.5",
    "ETH":  "3512.1",
    "HYPE": "28.15",
    "SOL":  "174.3",
}

SAMPLE_TRADES = [
    {"coin": "HYPE", "side": "B", "px": "28.15", "sz": "10.5", "time": 1_716_200_000_000, "hash": "0xabc"},
    {"coin": "HYPE", "side": "A", "px": "28.20", "sz": "5.0",  "time": 1_716_200_001_000, "hash": "0xdef"},
]


# ── Mock builder ───────────────────────────────────────────────────────────────

def mock_response(data: dict | list, status_code: int = 200) -> MagicMock:
    r = MagicMock()
    r.status_code = status_code
    r.ok = (200 <= status_code < 300)
    r.json.return_value = data
    r.text = json.dumps(data) if isinstance(data, (dict, list)) else str(data)
    r.headers = {}
    return r


def mock_error_response(status_code: int, body: str = "error") -> MagicMock:
    r = MagicMock()
    r.status_code = status_code
    r.ok = False
    r.json.side_effect = ValueError("no json")
    r.text = body
    r.headers = {}
    return r


# ══ TestNormalizeCoin ═════════════════════════════════════════════════════════

class TestNormalizeCoin:
    def test_lowercase(self):
        assert normalize_coin("hype") == "HYPE"

    def test_uppercase_passthrough(self):
        assert normalize_coin("BTC") == "BTC"

    def test_strip_usdt_suffix(self):
        assert normalize_coin("BTCUSDT") == "BTC"

    def test_strip_usd_suffix(self):
        assert normalize_coin("ETHUSD") == "ETH"

    def test_strip_usdc_suffix(self):
        assert normalize_coin("SOLUSDC") == "SOL"

    def test_strip_slash_separator(self):
        assert normalize_coin("BTC/USDT") == "BTC"

    def test_strip_dash_separator(self):
        assert normalize_coin("eth-usd") == "ETH"

    def test_strip_underscore_separator(self):
        assert normalize_coin("SOL_USDT") == "SOL"

    def test_whitespace_stripped(self):
        assert normalize_coin("  HYPE  ") == "HYPE"

    def test_mixed_case_and_suffix(self):
        assert normalize_coin("  Btc/Usdt  ") == "BTC"

    def test_empty_raises(self):
        with pytest.raises(InvalidCoinError, match="empty"):
            normalize_coin("")

    def test_whitespace_only_raises(self):
        with pytest.raises(InvalidCoinError, match="empty"):
            normalize_coin("   ")

    def test_none_raises(self):
        with pytest.raises(InvalidCoinError, match="string"):
            normalize_coin(None)  # type: ignore

    def test_int_raises(self):
        with pytest.raises(InvalidCoinError):
            normalize_coin(42)  # type: ignore

    def test_special_chars_raise(self):
        with pytest.raises(InvalidCoinError, match="invalid"):
            normalize_coin("BTC@USDT")

    def test_hype_passthrough(self):
        assert normalize_coin("HYPE") == "HYPE"

    def test_hype_lowercase(self):
        assert normalize_coin("hypeusdt") == "HYPE"


# ══ TestParseHLLevels ═════════════════════════════════════════════════════════

class TestParseHLLevels:
    def test_parses_bid_levels(self):
        raw = [{"px": "28.15", "sz": "120.5", "n": 3}]
        levels = _parse_hl_levels(raw, "bid")
        assert len(levels) == 1
        assert levels[0].price == pytest.approx(28.15)
        assert levels[0].qty   == pytest.approx(120.5)

    def test_usd_size_computed(self):
        raw = [{"px": "28.15", "sz": "100.0", "n": 1}]
        levels = _parse_hl_levels(raw, "bid")
        assert levels[0].usd_size == pytest.approx(28.15 * 100.0, rel=1e-5)

    def test_zero_price_skipped(self):
        raw = [{"px": "0.0", "sz": "100.0", "n": 1}, {"px": "28.15", "sz": "50.0", "n": 1}]
        levels = _parse_hl_levels(raw, "ask")
        assert len(levels) == 1
        assert levels[0].price == pytest.approx(28.15)

    def test_empty_list_returns_empty(self):
        assert _parse_hl_levels([], "bid") == []

    def test_not_list_raises(self):
        with pytest.raises(HyperliquidError):
            _parse_hl_levels("not a list", "bid")  # type: ignore

    def test_non_dict_element_raises(self):
        with pytest.raises(HyperliquidError):
            _parse_hl_levels([["28.15", "100.0"]], "bid")

    def test_missing_px_raises(self):
        with pytest.raises(HyperliquidError):
            _parse_hl_levels([{"sz": "100.0", "n": 1}], "bid")

    def test_missing_sz_raises(self):
        with pytest.raises(HyperliquidError):
            _parse_hl_levels([{"px": "28.15", "n": 1}], "bid")

    def test_non_numeric_px_raises(self):
        with pytest.raises(HyperliquidError):
            _parse_hl_levels([{"px": "bad", "sz": "100.0", "n": 1}], "bid")

    def test_string_prices_parsed_as_float(self):
        raw = [{"px": "28.150000", "sz": "120.500000", "n": 3}]
        levels = _parse_hl_levels(raw, "bid")
        assert levels[0].price == pytest.approx(28.15)
        assert levels[0].qty   == pytest.approx(120.5)

    def test_returns_order_book_level_instances(self):
        raw = [{"px": "28.15", "sz": "10.0", "n": 1}]
        levels = _parse_hl_levels(raw, "ask")
        assert isinstance(levels[0], OrderBookLevel)

    def test_multiple_levels(self):
        raw = SAMPLE_L2["levels"][0]
        levels = _parse_hl_levels(raw, "bid")
        assert len(levels) == 3


# ══ TestBuildOrderBookSnapshot ════════════════════════════════════════════════

class TestBuildOrderBookSnapshot:
    @patch("connectors.hyperliquid.requests.post")
    def test_returns_snapshot(self, mock_post):
        mock_post.return_value = mock_response(SAMPLE_L2)
        snap = fetch_l2_book("HYPE")
        assert isinstance(snap, OrderBookSnapshot)

    @patch("connectors.hyperliquid.requests.post")
    def test_symbol_normalised(self, mock_post):
        mock_post.return_value = mock_response(SAMPLE_L2)
        snap = fetch_l2_book("hype")
        assert snap.symbol == "HYPE"

    @patch("connectors.hyperliquid.requests.post")
    def test_exchange_is_hyperliquid(self, mock_post):
        mock_post.return_value = mock_response(SAMPLE_L2)
        snap = fetch_l2_book("HYPE")
        assert snap.exchange == EXCHANGE
        assert snap.exchange == "Hyperliquid"

    @patch("connectors.hyperliquid.requests.post")
    def test_bid_count(self, mock_post):
        mock_post.return_value = mock_response(SAMPLE_L2)
        snap = fetch_l2_book("HYPE")
        assert len(snap.bids) == 3

    @patch("connectors.hyperliquid.requests.post")
    def test_ask_count(self, mock_post):
        mock_post.return_value = mock_response(SAMPLE_L2)
        snap = fetch_l2_book("HYPE")
        assert len(snap.asks) == 3

    @patch("connectors.hyperliquid.requests.post")
    def test_bids_sorted_descending(self, mock_post):
        mock_post.return_value = mock_response(SAMPLE_L2)
        snap = fetch_l2_book("HYPE")
        prices = [b.price for b in snap.bids]
        assert prices == sorted(prices, reverse=True)

    @patch("connectors.hyperliquid.requests.post")
    def test_asks_sorted_ascending(self, mock_post):
        mock_post.return_value = mock_response(SAMPLE_L2)
        snap = fetch_l2_book("HYPE")
        prices = [a.price for a in snap.asks]
        assert prices == sorted(prices)

    @patch("connectors.hyperliquid.requests.post")
    def test_best_bid_price(self, mock_post):
        mock_post.return_value = mock_response(SAMPLE_L2)
        snap = fetch_l2_book("HYPE")
        assert snap.best_bid is not None
        assert snap.best_bid.price == pytest.approx(28.15)

    @patch("connectors.hyperliquid.requests.post")
    def test_best_ask_price(self, mock_post):
        mock_post.return_value = mock_response(SAMPLE_L2)
        snap = fetch_l2_book("HYPE")
        assert snap.best_ask is not None
        assert snap.best_ask.price == pytest.approx(28.20)

    @patch("connectors.hyperliquid.requests.post")
    def test_mid_price(self, mock_post):
        mock_post.return_value = mock_response(SAMPLE_L2)
        snap = fetch_l2_book("HYPE")
        expected_mid = round((28.15 + 28.20) / 2, 8)
        assert snap.mid_price == pytest.approx(expected_mid)

    @patch("connectors.hyperliquid.requests.post")
    def test_usd_size_populated(self, mock_post):
        mock_post.return_value = mock_response(SAMPLE_L2)
        snap = fetch_l2_book("HYPE")
        assert snap.bids[0].usd_size == pytest.approx(28.15 * 120.5, rel=1e-4)

    @patch("connectors.hyperliquid.requests.post")
    def test_timestamp_from_response(self, mock_post):
        mock_post.return_value = mock_response(SAMPLE_L2)
        snap = fetch_l2_book("HYPE")
        assert snap.timestamp_ms == 1_716_200_000_000

    @patch("connectors.hyperliquid.requests.post")
    def test_has_both_sides(self, mock_post):
        mock_post.return_value = mock_response(SAMPLE_L2)
        snap = fetch_l2_book("HYPE")
        assert snap.has_both_sides

    @patch("connectors.hyperliquid.requests.post")
    def test_correct_payload_sent(self, mock_post):
        mock_post.return_value = mock_response(SAMPLE_L2)
        fetch_l2_book("HYPE")
        call_kwargs = mock_post.call_args[1]
        assert call_kwargs["json"]["type"] == "l2Book"
        assert call_kwargs["json"]["coin"] == "HYPE"

    def test_invalid_coin_raises(self):
        with pytest.raises(InvalidCoinError):
            fetch_l2_book("")

    @patch("connectors.hyperliquid.requests.post")
    def test_wrong_response_type_raises(self, mock_post):
        mock_post.return_value = mock_response([1, 2, 3])
        with pytest.raises(HyperliquidError):
            fetch_l2_book("HYPE")

    @patch("connectors.hyperliquid.requests.post")
    def test_missing_levels_raises(self, mock_post):
        mock_post.return_value = mock_response({"coin": "HYPE", "time": 1000})
        with pytest.raises(HyperliquidError):
            fetch_l2_book("HYPE")

    @patch("connectors.hyperliquid.requests.post")
    def test_empty_book_both_sides(self, mock_post):
        mock_post.return_value = mock_response(
            {"coin": "HYPE", "time": 1000, "levels": [[], []]}
        )
        snap = fetch_l2_book("HYPE")
        assert snap.is_empty
        assert snap.mid_price == 0.0


# ══ TestFetchMeta ═════════════════════════════════════════════════════════════

class TestFetchMeta:
    @patch("connectors.hyperliquid.requests.post")
    def test_returns_dict(self, mock_post):
        mock_post.return_value = mock_response(SAMPLE_META)
        result = fetch_meta()
        assert isinstance(result, dict)

    @patch("connectors.hyperliquid.requests.post")
    def test_has_universe_key(self, mock_post):
        mock_post.return_value = mock_response(SAMPLE_META)
        result = fetch_meta()
        assert "universe" in result

    @patch("connectors.hyperliquid.requests.post")
    def test_universe_is_list(self, mock_post):
        mock_post.return_value = mock_response(SAMPLE_META)
        result = fetch_meta()
        assert isinstance(result["universe"], list)

    @patch("connectors.hyperliquid.requests.post")
    def test_universe_count(self, mock_post):
        mock_post.return_value = mock_response(SAMPLE_META)
        result = fetch_meta()
        assert len(result["universe"]) == 4

    @patch("connectors.hyperliquid.requests.post")
    def test_coin_names_in_universe(self, mock_post):
        mock_post.return_value = mock_response(SAMPLE_META)
        result = fetch_meta()
        names = [m["name"] for m in result["universe"]]
        assert "BTC" in names
        assert "HYPE" in names

    @patch("connectors.hyperliquid.requests.post")
    def test_correct_payload_sent(self, mock_post):
        mock_post.return_value = mock_response(SAMPLE_META)
        fetch_meta()
        assert mock_post.call_args[1]["json"]["type"] == "meta"

    @patch("connectors.hyperliquid.requests.post")
    def test_missing_universe_raises(self, mock_post):
        mock_post.return_value = mock_response({"other": "data"})
        with pytest.raises(HyperliquidError, match="universe"):
            fetch_meta()

    @patch("connectors.hyperliquid.requests.post")
    def test_wrong_type_raises(self, mock_post):
        mock_post.return_value = mock_response([1, 2, 3])
        with pytest.raises(HyperliquidError):
            fetch_meta()


# ══ TestFetchAllMids ══════════════════════════════════════════════════════════

class TestFetchAllMids:
    @patch("connectors.hyperliquid.requests.post")
    def test_returns_dict(self, mock_post):
        mock_post.return_value = mock_response(SAMPLE_MIDS)
        result = fetch_all_mids()
        assert isinstance(result, dict)

    @patch("connectors.hyperliquid.requests.post")
    def test_prices_are_float(self, mock_post):
        mock_post.return_value = mock_response(SAMPLE_MIDS)
        result = fetch_all_mids()
        assert isinstance(result["BTC"], float)
        assert result["BTC"] == pytest.approx(67420.5)

    @patch("connectors.hyperliquid.requests.post")
    def test_hype_price(self, mock_post):
        mock_post.return_value = mock_response(SAMPLE_MIDS)
        result = fetch_all_mids()
        assert result["HYPE"] == pytest.approx(28.15)

    @patch("connectors.hyperliquid.requests.post")
    def test_unparseable_value_skipped(self, mock_post):
        mock_post.return_value = mock_response(
            {"BTC": "67420.5", "BAD": "not_a_number", "HYPE": "28.15"}
        )
        result = fetch_all_mids()
        assert "BTC" in result
        assert "HYPE" in result
        assert "BAD" not in result

    @patch("connectors.hyperliquid.requests.post")
    def test_empty_mids(self, mock_post):
        mock_post.return_value = mock_response({})
        result = fetch_all_mids()
        assert result == {}

    @patch("connectors.hyperliquid.requests.post")
    def test_correct_payload_sent(self, mock_post):
        mock_post.return_value = mock_response(SAMPLE_MIDS)
        fetch_all_mids()
        assert mock_post.call_args[1]["json"]["type"] == "allMids"

    @patch("connectors.hyperliquid.requests.post")
    def test_wrong_type_raises(self, mock_post):
        mock_post.return_value = mock_response([1, 2])
        with pytest.raises(HyperliquidError):
            fetch_all_mids()


# ══ TestFetchRecentTrades ═════════════════════════════════════════════════════

class TestFetchRecentTrades:
    @patch("connectors.hyperliquid.requests.post")
    def test_returns_list(self, mock_post):
        mock_post.return_value = mock_response(SAMPLE_TRADES)
        result = fetch_recent_trades("HYPE")
        assert isinstance(result, list)

    @patch("connectors.hyperliquid.requests.post")
    def test_correct_length(self, mock_post):
        mock_post.return_value = mock_response(SAMPLE_TRADES)
        result = fetch_recent_trades("HYPE")
        assert len(result) == 2

    @patch("connectors.hyperliquid.requests.post")
    def test_buy_side_mapped(self, mock_post):
        mock_post.return_value = mock_response(SAMPLE_TRADES)
        result = fetch_recent_trades("HYPE")
        assert result[0]["side"] == "buy"

    @patch("connectors.hyperliquid.requests.post")
    def test_sell_side_mapped(self, mock_post):
        mock_post.return_value = mock_response(SAMPLE_TRADES)
        result = fetch_recent_trades("HYPE")
        assert result[1]["side"] == "sell"

    @patch("connectors.hyperliquid.requests.post")
    def test_price_is_float(self, mock_post):
        mock_post.return_value = mock_response(SAMPLE_TRADES)
        result = fetch_recent_trades("HYPE")
        assert isinstance(result[0]["price"], float)
        assert result[0]["price"] == pytest.approx(28.15)

    @patch("connectors.hyperliquid.requests.post")
    def test_all_keys_present(self, mock_post):
        mock_post.return_value = mock_response(SAMPLE_TRADES)
        result = fetch_recent_trades("HYPE")
        expected = {"coin", "side", "price", "qty", "time_ms", "hash"}
        assert expected.issubset(result[0].keys())

    @patch("connectors.hyperliquid.requests.post")
    def test_empty_trades(self, mock_post):
        mock_post.return_value = mock_response([])
        result = fetch_recent_trades("HYPE")
        assert result == []

    @patch("connectors.hyperliquid.requests.post")
    def test_correct_payload_sent(self, mock_post):
        mock_post.return_value = mock_response(SAMPLE_TRADES)
        fetch_recent_trades("HYPE")
        call_kwargs = mock_post.call_args[1]
        assert call_kwargs["json"]["type"] == "recentTrades"
        assert call_kwargs["json"]["coin"] == "HYPE"

    def test_invalid_coin_raises(self):
        with pytest.raises(InvalidCoinError):
            fetch_recent_trades("")

    @patch("connectors.hyperliquid.requests.post")
    def test_malformed_trade_raises(self, mock_post):
        mock_post.return_value = mock_response(["not a dict"])
        with pytest.raises(HyperliquidError):
            fetch_recent_trades("HYPE")

    @patch("connectors.hyperliquid.requests.post")
    def test_wrong_response_type_raises(self, mock_post):
        mock_post.return_value = mock_response({"error": "unexpected"})
        with pytest.raises(HyperliquidError):
            fetch_recent_trades("HYPE")


# ══ TestErrorHandling ═════════════════════════════════════════════════════════

class TestErrorHandling:
    @patch("connectors.hyperliquid.requests.post")
    def test_http_429_raises_rate_limit(self, mock_post):
        r = MagicMock(); r.status_code = 429; r.ok = False
        r.text = "rate limited"; r.headers = {}
        mock_post.return_value = r
        with pytest.raises(HyperliquidRateLimitError):
            fetch_l2_book("HYPE")

    @patch("connectors.hyperliquid.requests.post")
    def test_http_500_raises_error(self, mock_post):
        mock_post.return_value = mock_error_response(500, "internal error")
        with pytest.raises(HyperliquidError) as exc_info:
            fetch_l2_book("HYPE")
        assert exc_info.value.status_code == 500

    @patch("connectors.hyperliquid.requests.post")
    def test_http_403_raises_error(self, mock_post):
        mock_post.return_value = mock_error_response(403, "forbidden")
        with pytest.raises(HyperliquidError):
            fetch_l2_book("HYPE")

    @patch("connectors.hyperliquid.requests.post")
    def test_timeout_raises_error(self, mock_post):
        import requests as req
        mock_post.side_effect = req.exceptions.Timeout("timed out")
        with pytest.raises(HyperliquidError, match="timed out"):
            fetch_l2_book("HYPE")

    @patch("connectors.hyperliquid.requests.post")
    def test_connection_error_raises(self, mock_post):
        import requests as req
        mock_post.side_effect = req.exceptions.ConnectionError("no route")
        with pytest.raises(HyperliquidError, match="Connection"):
            fetch_l2_book("HYPE")

    @patch("connectors.hyperliquid.requests.post")
    def test_empty_body_raises(self, mock_post):
        r = MagicMock(); r.status_code = 200; r.ok = True
        r.text = ""; r.headers = {}
        mock_post.return_value = r
        with pytest.raises(HyperliquidError, match="Empty"):
            fetch_l2_book("HYPE")

    @patch("connectors.hyperliquid.requests.post")
    def test_bad_json_raises(self, mock_post):
        r = MagicMock(); r.status_code = 200; r.ok = True
        r.text = "not valid json"; r.json.side_effect = ValueError("bad json")
        r.headers = {}
        mock_post.return_value = r
        with pytest.raises(HyperliquidError):
            fetch_l2_book("HYPE")

    def test_rate_limit_is_subclass_of_error(self):
        assert issubclass(HyperliquidRateLimitError, HyperliquidError)

    def test_invalid_coin_is_subclass_of_error(self):
        assert issubclass(InvalidCoinError, HyperliquidError)

    def test_error_has_status_code(self):
        e = HyperliquidError("test", status_code=451, request_type="l2Book")
        assert e.status_code == 451
        assert e.request_type == "l2Book"
        assert "451" in str(e)
        assert "l2Book" in str(e)


# ══ TestEdgeCases ═════════════════════════════════════════════════════════════

class TestEdgeCases:
    @patch("connectors.hyperliquid.requests.post")
    def test_empty_bids_and_asks(self, mock_post):
        mock_post.return_value = mock_response(
            {"coin": "HYPE", "time": 1000, "levels": [[], []]}
        )
        snap = fetch_l2_book("HYPE")
        assert snap.is_empty
        assert snap.mid_price == 0.0
        assert snap.best_bid is None
        assert snap.best_ask is None

    @patch("connectors.hyperliquid.requests.post")
    def test_zero_price_levels_skipped(self, mock_post):
        data = {
            "coin": "HYPE", "time": 1000,
            "levels": [
                [{"px": "0.0", "sz": "100.0", "n": 1}, {"px": "28.10", "sz": "50.0", "n": 1}],
                [{"px": "28.20", "sz": "60.0", "n": 1}],
            ],
        }
        mock_post.return_value = mock_response(data)
        snap = fetch_l2_book("HYPE")
        assert all(b.price > 0 for b in snap.bids)
        assert len(snap.bids) == 1

    @patch("connectors.hyperliquid.requests.post")
    def test_single_level_each_side(self, mock_post):
        data = {
            "coin": "HYPE", "time": 1000,
            "levels": [
                [{"px": "28.10", "sz": "50.0", "n": 1}],
                [{"px": "28.20", "sz": "40.0", "n": 1}],
            ],
        }
        mock_post.return_value = mock_response(data)
        snap = fetch_l2_book("HYPE")
        assert snap.has_both_sides
        assert snap.mid_price == pytest.approx((28.10 + 28.20) / 2)

    @patch("connectors.hyperliquid.requests.post")
    def test_levels_not_pre_sorted(self, mock_post):
        # API may return bids not in descending order — connector must sort
        data = {
            "coin": "HYPE", "time": 1000,
            "levels": [
                [
                    {"px": "28.00", "sz": "50.0", "n": 1},
                    {"px": "28.15", "sz": "120.5", "n": 3},  # out of order
                    {"px": "28.10", "sz": "80.2",  "n": 2},
                ],
                [{"px": "28.20", "sz": "60.0", "n": 1}],
            ],
        }
        mock_post.return_value = mock_response(data)
        snap = fetch_l2_book("HYPE")
        prices = [b.price for b in snap.bids]
        assert prices == sorted(prices, reverse=True)
        assert snap.best_bid.price == pytest.approx(28.15)

    @patch("connectors.hyperliquid.requests.post")
    def test_large_numbers_parsed(self, mock_post):
        data = {
            "coin": "BTC", "time": 1000,
            "levels": [
                [{"px": "67432.50000000", "sz": "0.12300000", "n": 1}],
                [{"px": "67433.10000000", "sz": "0.05000000", "n": 1}],
            ],
        }
        mock_post.return_value = mock_response(data)
        snap = fetch_l2_book("BTC")
        assert snap.best_bid.price == pytest.approx(67432.5)
        assert snap.best_ask.price == pytest.approx(67433.1)
        mid = (67432.5 + 67433.1) / 2
        assert snap.mid_price == pytest.approx(mid, rel=1e-6)

    @patch("connectors.hyperliquid.requests.post")
    def test_symbol_stored_on_snapshot(self, mock_post):
        mock_post.return_value = mock_response(SAMPLE_L2)
        snap = fetch_l2_book("hypeusdt")  # normalised to HYPE
        assert snap.symbol == "HYPE"

    @patch("connectors.hyperliquid.requests.post")
    def test_all_mids_integer_prices(self, mock_post):
        # Some coins may return integer-like strings
        mock_post.return_value = mock_response({"BTC": "67420", "ETH": "3512"})
        result = fetch_all_mids()
        assert result["BTC"] == pytest.approx(67420.0)
        assert isinstance(result["BTC"], float)
