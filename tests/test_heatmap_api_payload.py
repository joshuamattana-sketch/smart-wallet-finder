"""
tests/test_heatmap_api_payload.py
-----------------------------------
Unit tests for services/heatmap_api_payload.py.
No API calls; all data is inline mock matrices/frames.
"""

import pytest
from services.heatmap_matrix_builder import build_heatmap_matrix
from services.heatmap_api_payload import (
    build_heatmap_api_payload,
    build_demo_heatmap_api_payload,
    validate_heatmap_api_payload,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _bucket(price, bid_usd=0.0, ask_usd=0.0, intensity=50.0):
    total = bid_usd + ask_usd
    side = "bid" if ask_usd == 0 else ("ask" if bid_usd == 0 else "mixed")
    return {"price_bucket": price, "bid_usd": bid_usd, "ask_usd": ask_usd,
            "total_usd": total, "side": side, "intensity": intensity}


def _wall(price, side="bid", total_usd=2_000_000.0, intensity=80.0):
    label = "Major Bid Wall" if side == "bid" else "Major Ask Wall"
    return {"price_bucket": price, "side": side, "total_usd": total_usd,
            "intensity": intensity, "label": label}


def _frame(captured_at, buckets=None, walls=None, symbol="BTCUSDT"):
    return {"symbol": symbol, "captured_at": captured_at, "price_step": 10.0,
            "buckets": buckets or [], "walls": walls or []}


def _simple_matrix():
    frames = [
        _frame("T1", [_bucket(100.0, bid_usd=500_000.0, intensity=60.0),
                      _bucket(110.0, ask_usd=300_000.0, intensity=40.0)],
               walls=[_wall(100.0)]),
    ]
    return build_heatmap_matrix(frames)


# ── build_heatmap_api_payload ─────────────────────────────────────────────────

class TestBuildHeatmapApiPayload:

    def test_required_fields_present(self):
        payload = build_heatmap_api_payload(_simple_matrix())
        for field in ("symbol", "exchange", "timeframe", "priceMin", "priceMax",
                      "priceStep", "timeBuckets", "cells", "walls", "summary", "meta"):
            assert field in payload

    def test_cells_come_from_compressed_matrix(self):
        matrix = _simple_matrix()
        payload = build_heatmap_api_payload(matrix)
        assert isinstance(payload["cells"], list)
        assert len(payload["cells"]) > 0

    def test_summary_present_and_non_empty(self):
        payload = build_heatmap_api_payload(_simple_matrix())
        assert isinstance(payload["summary"], dict)
        assert "max_total_intensity" in payload["summary"]

    def test_meta_fields(self):
        payload = build_heatmap_api_payload(_simple_matrix())
        meta = payload["meta"]
        assert meta["schemaVersion"] == "1.0"
        assert "generatedAt" in meta
        assert isinstance(meta["cellCount"], int)
        assert isinstance(meta["wallCount"], int)
        assert meta["isDemo"] is False

    def test_meta_cell_count_matches_cells(self):
        payload = build_heatmap_api_payload(_simple_matrix())
        assert payload["meta"]["cellCount"] == len(payload["cells"])

    def test_meta_wall_count_matches_walls(self):
        payload = build_heatmap_api_payload(_simple_matrix())
        assert payload["meta"]["wallCount"] == len(payload["walls"])

    def test_invalid_timeframe_raises(self):
        with pytest.raises(ValueError):
            build_heatmap_api_payload(_simple_matrix(), timeframe="3m")

    def test_non_dict_matrix_raises(self):
        with pytest.raises(TypeError):
            build_heatmap_api_payload([1, 2, 3])

    def test_symbol_fallback_for_missing_symbol(self):
        matrix = build_heatmap_matrix([])
        matrix["symbol"] = ""
        payload = build_heatmap_api_payload(matrix)
        assert payload["symbol"] == "UNKNOWN"

    def test_empty_matrix_does_not_crash(self):
        payload = build_heatmap_api_payload(build_heatmap_matrix([]))
        assert payload["cells"] == []
        assert payload["timeBuckets"] == []
        assert payload["priceMin"] is None

    def test_exchange_and_timeframe_in_payload(self):
        payload = build_heatmap_api_payload(_simple_matrix(), timeframe="1h", exchange="bybit")
        assert payload["exchange"] == "bybit"
        assert payload["timeframe"] == "1h"

    def test_all_valid_timeframes_accepted(self):
        m = _simple_matrix()
        for tf in ("5m", "15m", "1h", "4h", "1d"):
            payload = build_heatmap_api_payload(m, timeframe=tf)
            assert payload["timeframe"] == tf


# ── build_demo_heatmap_api_payload ────────────────────────────────────────────

class TestBuildDemoHeatmapApiPayload:

    def test_is_demo_true(self):
        payload = build_demo_heatmap_api_payload()
        assert payload["meta"]["isDemo"] is True

    def test_required_fields_present(self):
        payload = build_demo_heatmap_api_payload()
        for field in ("symbol", "exchange", "timeframe", "cells", "timeBuckets",
                      "walls", "summary", "meta"):
            assert field in payload

    def test_has_cells(self):
        payload = build_demo_heatmap_api_payload()
        assert isinstance(payload["cells"], list)
        assert len(payload["cells"]) > 0

    def test_custom_symbol(self):
        payload = build_demo_heatmap_api_payload(symbol="ETHUSDT")
        assert payload["symbol"] == "ETHUSDT"

    def test_invalid_timeframe_raises(self):
        with pytest.raises(ValueError):
            build_demo_heatmap_api_payload(timeframe="99x")


# ── validate_heatmap_api_payload ──────────────────────────────────────────────

class TestValidateHeatmapApiPayload:

    def test_valid_payload_returns_true(self):
        payload = build_heatmap_api_payload(_simple_matrix())
        assert validate_heatmap_api_payload(payload) is True

    def test_demo_payload_returns_true(self):
        assert validate_heatmap_api_payload(build_demo_heatmap_api_payload()) is True

    def test_missing_top_level_field_returns_false(self):
        payload = build_heatmap_api_payload(_simple_matrix())
        del payload["cells"]
        assert validate_heatmap_api_payload(payload) is False

    def test_cells_not_list_returns_false(self):
        payload = build_heatmap_api_payload(_simple_matrix())
        payload["cells"] = "not a list"
        assert validate_heatmap_api_payload(payload) is False

    def test_time_buckets_not_list_returns_false(self):
        payload = build_heatmap_api_payload(_simple_matrix())
        payload["timeBuckets"] = None
        assert validate_heatmap_api_payload(payload) is False

    def test_missing_schema_version_returns_false(self):
        payload = build_heatmap_api_payload(_simple_matrix())
        del payload["meta"]["schemaVersion"]
        assert validate_heatmap_api_payload(payload) is False

    def test_non_dict_returns_false(self):
        assert validate_heatmap_api_payload("not a dict") is False

    def test_empty_dict_returns_false(self):
        assert validate_heatmap_api_payload({}) is False
