"""
tests/test_binance_depth_collector.py
--------------------------------------
Unit tests for services/connectors/binance_depth_collector.py

No real Binance API calls — all HTTP is intercepted with unittest.mock.patch.
"""

import sys
import os
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.connectors.binance_depth_collector import (
    fetch_depth_snapshot,
    normalize_depth_levels,
    calculate_top_wall,
    summarize_snapshot,
    DepthCollectorError,
    RateLimitError,
    VALID_LIMITS,
)

# ── Shared mock data ───────────────────────────────────────────────────────────

_RAW_BIDS = [
    ["67500.00", "2.000"],   # usd = 135_000.00
    ["67450.00", "5.000"],   # usd = 337_250.00  ← top bid wall
    ["67400.00", "1.200"],   # usd =  80_880.00
]

_RAW_ASKS = [
    ["67510.00", "3.000"],   # usd = 202_530.00
    ["67520.00", "8.000"],   # usd = 540_160.00  ← top ask wall
    ["67530.00", "0.800"],   # usd =  54_024.00
]

_API_PAYLOAD = {
    "lastUpdateId": 987654321,
    "bids": _RAW_BIDS,
    "asks": _RAW_ASKS,
}


def _ok(data: dict) -> MagicMock:
    r = MagicMock()
    r.ok = True
    r.status_code = 200
    r.json.return_value = data
    return r


def _err(status: int, text: str = "error") -> MagicMock:
    r = MagicMock()
    r.ok = False
    r.status_code = status
    r.text = text
    return r


# ── normalize_depth_levels ─────────────────────────────────────────────────────

def test_normalize_depth_levels_calculates_usd():
    levels = normalize_depth_levels([["50000.00", "2.0"]], "bid")
    assert len(levels) == 1
    assert levels[0]["price"] == 50_000.00
    assert levels[0]["quantity"] == 2.0
    assert levels[0]["usd"] == pytest.approx(100_000.00)


def test_normalize_depth_levels_excludes_zero_quantity():
    raw = [["67500.00", "1.0"], ["67400.00", "0.000"], ["67300.00", "3.0"]]
    levels = normalize_depth_levels(raw, "bid")
    assert len(levels) == 2
    prices = [lv["price"] for lv in levels]
    assert 67400.00 not in prices


def test_normalize_depth_levels_invalid_side_raises():
    with pytest.raises(ValueError, match="side must be"):
        normalize_depth_levels(_RAW_BIDS, "both")


def test_normalize_depth_levels_empty_input():
    assert normalize_depth_levels([], "ask") == []


def test_normalize_depth_levels_malformed_raises():
    with pytest.raises(DepthCollectorError, match="Malformed"):
        normalize_depth_levels([["not_a_number", "1.0"]], "bid")


# ── calculate_top_wall ────────────────────────────────────────────────────────

def test_calculate_top_wall_returns_largest_usd_level():
    levels = normalize_depth_levels(_RAW_BIDS, "bid")
    wall = calculate_top_wall(levels)
    assert wall is not None
    # 67_450 * 5.0 = 337_250 is largest
    assert wall["price"] == pytest.approx(67_450.00)
    assert wall["usd"] == pytest.approx(337_250.00, rel=1e-5)


def test_calculate_top_wall_returns_none_for_empty():
    assert calculate_top_wall([]) is None


def test_calculate_top_wall_single_level():
    levels = normalize_depth_levels([["67000.00", "3.0"]], "bid")
    wall = calculate_top_wall(levels)
    assert wall is not None
    assert wall["price"] == 67_000.00


def test_calculate_top_wall_ask_side():
    levels = normalize_depth_levels(_RAW_ASKS, "ask")
    wall = calculate_top_wall(levels)
    # 67_520 * 8.0 = 540_160 is largest
    assert wall is not None
    assert wall["price"] == pytest.approx(67_520.00)


# ── fetch_depth_snapshot ──────────────────────────────────────────────────────

def test_fetch_depth_snapshot_normalizes_response():
    with patch("requests.get", return_value=_ok(_API_PAYLOAD)):
        snap = fetch_depth_snapshot("BTCUSDT", limit=1000)

    assert snap["symbol"] == "BTCUSDT"
    assert snap["last_update_id"] == 987654321
    assert isinstance(snap["bids"], list)
    assert isinstance(snap["asks"], list)
    assert "captured_at" in snap
    assert "T" in snap["captured_at"]  # ISO 8601


def test_fetch_depth_snapshot_bids_sorted_descending():
    with patch("requests.get", return_value=_ok(_API_PAYLOAD)):
        snap = fetch_depth_snapshot()
    prices = [lv["price"] for lv in snap["bids"]]
    assert prices == sorted(prices, reverse=True)


def test_fetch_depth_snapshot_asks_sorted_ascending():
    with patch("requests.get", return_value=_ok(_API_PAYLOAD)):
        snap = fetch_depth_snapshot()
    prices = [lv["price"] for lv in snap["asks"]]
    assert prices == sorted(prices)


def test_fetch_depth_snapshot_usd_on_every_level():
    with patch("requests.get", return_value=_ok(_API_PAYLOAD)):
        snap = fetch_depth_snapshot()
    for lv in snap["bids"] + snap["asks"]:
        assert "usd" in lv
        assert lv["usd"] == pytest.approx(lv["price"] * lv["quantity"], rel=1e-5)


def test_fetch_depth_snapshot_symbol_uppercased():
    with patch("requests.get", return_value=_ok(_API_PAYLOAD)) as mock_get:
        fetch_depth_snapshot("btcusdt", limit=100)
    assert mock_get.call_args[1]["params"]["symbol"] == "BTCUSDT"


# ── summarize_snapshot ────────────────────────────────────────────────────────

def test_summarize_snapshot_calculates_spread_and_imbalance():
    with patch("requests.get", return_value=_ok(_API_PAYLOAD)):
        snap = fetch_depth_snapshot()
    s = summarize_snapshot(snap)

    # best bid = 67_500 (highest), best ask = 67_510 (lowest)
    assert s["best_bid"] == pytest.approx(67_500.00)
    assert s["best_ask"] == pytest.approx(67_510.00)
    assert s["spread"] == pytest.approx(10.00, rel=1e-5)
    assert s["spread_pct"] > 0

    # ask_usd > bid_usd in this fixture → imbalance < 0.5
    assert 0.0 < s["imbalance"] < 0.5

    assert s["top_bid_wall"] is not None
    assert s["top_ask_wall"] is not None
    assert s["total_bid_usd"] > 0
    assert s["total_ask_usd"] > 0


def test_summarize_snapshot_imbalance_range():
    with patch("requests.get", return_value=_ok(_API_PAYLOAD)):
        snap = fetch_depth_snapshot()
    s = summarize_snapshot(snap)
    assert 0.0 <= s["imbalance"] <= 1.0


def test_summarize_snapshot_empty_bids_raises():
    snap = {
        "symbol": "BTCUSDT", "last_update_id": 1,
        "bids": [],
        "asks": [{"price": 67510.0, "quantity": 1.0, "usd": 67510.0}],
        "captured_at": "2025-01-01T00:00:00+00:00",
    }
    with pytest.raises(DepthCollectorError, match="no bid levels"):
        summarize_snapshot(snap)


def test_summarize_snapshot_empty_asks_raises():
    snap = {
        "symbol": "BTCUSDT", "last_update_id": 1,
        "bids": [{"price": 67500.0, "quantity": 1.0, "usd": 67500.0}],
        "asks": [],
        "captured_at": "2025-01-01T00:00:00+00:00",
    }
    with pytest.raises(DepthCollectorError, match="no ask levels"):
        summarize_snapshot(snap)


# ── invalid_limit ─────────────────────────────────────────────────────────────

def test_invalid_limit_raises_value_error():
    with pytest.raises(ValueError, match="Invalid depth limit"):
        with patch("requests.get") as mock_get:
            fetch_depth_snapshot(limit=200)
        # Confirm the HTTP call was never made
        mock_get.assert_not_called()


def test_valid_limits_all_accepted():
    for lim in VALID_LIMITS:
        with patch("requests.get", return_value=_ok(_API_PAYLOAD)):
            snap = fetch_depth_snapshot(limit=lim)
        assert snap["symbol"] == "BTCUSDT"


def test_invalid_limit_does_not_hit_network():
    with patch("requests.get") as mock_get:
        with pytest.raises(ValueError):
            fetch_depth_snapshot(limit=999)
        mock_get.assert_not_called()


# ── http_error_is_handled ─────────────────────────────────────────────────────

def test_http_error_is_handled():
    with patch("requests.get", return_value=_err(400, "Bad Request")):
        with pytest.raises(DepthCollectorError):
            fetch_depth_snapshot()


def test_http_429_raises_rate_limit_error():
    with patch("requests.get", return_value=_err(429)):
        with pytest.raises(RateLimitError):
            fetch_depth_snapshot()


def test_rate_limit_error_is_subclass_of_collector_error():
    assert issubclass(RateLimitError, DepthCollectorError)


def test_http_500_raises_collector_error():
    with patch("requests.get", return_value=_err(500, "Internal Server Error")):
        with pytest.raises(DepthCollectorError):
            fetch_depth_snapshot()


def test_timeout_raises_collector_error():
    import requests as req
    with patch("requests.get", side_effect=req.exceptions.Timeout):
        with pytest.raises(DepthCollectorError, match="timed out"):
            fetch_depth_snapshot()


def test_network_error_raises_collector_error():
    import requests as req
    with patch("requests.get", side_effect=req.exceptions.ConnectionError("no route")):
        with pytest.raises(DepthCollectorError, match="Network error"):
            fetch_depth_snapshot()


def test_missing_last_update_id_raises_collector_error():
    bad = {"bids": _RAW_BIDS, "asks": _RAW_ASKS}  # no lastUpdateId key
    with patch("requests.get", return_value=_ok(bad)):
        with pytest.raises(DepthCollectorError, match="missing 'lastUpdateId'"):
            fetch_depth_snapshot()


def test_error_stores_status_code():
    with patch("requests.get", return_value=_err(400, "err")):
        try:
            fetch_depth_snapshot()
            pytest.fail("Expected DepthCollectorError")
        except DepthCollectorError as exc:
            assert exc.status_code == 400
