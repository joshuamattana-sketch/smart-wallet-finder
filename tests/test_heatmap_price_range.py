"""
tests/test_heatmap_price_range.py
----------------------------------
LM43: analysis-grade heatmap price range presets.

Tests the bucketer's new helpers in isolation:
  - resolve_price_range (preset + overrides + fallback)
  - auto_scale_price_step (keeps bucket count bounded)
  - build_heatmap_cells with price_range filtering + available_depth metadata
"""

from __future__ import annotations

import pytest

from services.orderbook_depth_bucketer import (
    PRESET_ABS,
    PRESET_PCT_FALLBACK,
    VALID_RANGE_MODES,
    auto_scale_price_step,
    build_heatmap_cells,
    resolve_price_range,
)


def _lvl(price: float, qty: float) -> dict:
    return {"price": price, "quantity": qty, "usd": round(price * qty, 2)}


def _wide_snapshot() -> dict:
    """A snapshot that spans far wider than any tight preset for BTC."""
    return {
        "symbol":      "BTCUSDT",
        "captured_at": "2026-06-01T12:00:00+00:00",
        "bids": [_lvl(50000.0, 0.1), _lvl(67400.0, 5.0), _lvl(67490.0, 0.5)],
        "asks": [_lvl(67500.0, 0.5), _lvl(67600.0, 4.0), _lvl(80000.0, 0.1)],
    }


# ── resolve_price_range ──────────────────────────────────────────────────────

class TestResolvePriceRange:

    def test_btc_tight_preset(self):
        r = resolve_price_range("BTCUSDT", "tight", 100_000.0)
        assert r["abs"] == 1000.0
        assert r["pct"] is None
        assert r["min"] == 99_000.0
        assert r["max"] == 101_000.0
        assert r["mode"] == "tight"
        assert r["center"] == 100_000.0

    def test_btc_macro_is_wider_than_tight(self):
        tight = resolve_price_range("BTCUSDT", "tight", 100_000.0)
        macro = resolve_price_range("BTCUSDT", "macro", 100_000.0)
        assert (macro["max"] - macro["min"]) > (tight["max"] - tight["min"])

    def test_eth_standard_preset(self):
        r = resolve_price_range("ETHUSDT", "standard", 3500.0)
        assert r["abs"] == 300.0
        assert r["min"] == 3200.0 and r["max"] == 3800.0

    def test_sol_wide_preset(self):
        r = resolve_price_range("SOLUSDT", "wide", 150.0)
        assert r["abs"] == 75.0
        assert r["min"] == 75.0 and r["max"] == 225.0

    def test_unknown_symbol_uses_pct_fallback(self):
        # 5% (wide fallback) around 1000 → ±70
        r = resolve_price_range("FOOUSDT", "wide", 1000.0)
        assert r["abs"] is None
        assert r["pct"] == PRESET_PCT_FALLBACK["wide"]
        assert r["min"] == 1000.0 - 70.0
        assert r["max"] == 1000.0 + 70.0

    def test_abs_override_beats_preset(self):
        r = resolve_price_range("BTCUSDT", "tight", 100_000.0, abs_override=2500.0)
        assert r["abs"] == 2500.0
        assert r["pct"] is None
        assert r["min"] == 97_500.0 and r["max"] == 102_500.0

    def test_percent_override_beats_preset(self):
        r = resolve_price_range("BTCUSDT", "standard", 100_000.0, pct_override=0.05)
        assert r["pct"] == 0.05
        assert r["abs"] is None
        assert r["min"] == 95_000.0 and r["max"] == 105_000.0

    def test_abs_override_beats_percent_override(self):
        r = resolve_price_range(
            "BTCUSDT", "standard", 100_000.0,
            abs_override=2500.0, pct_override=0.05,
        )
        assert r["abs"] == 2500.0
        assert r["pct"] is None

    def test_invalid_mode_raises(self):
        with pytest.raises(ValueError, match="invalid range mode"):
            resolve_price_range("BTCUSDT", "bogus", 100_000.0)

    def test_invalid_center_raises(self):
        with pytest.raises(ValueError, match="center"):
            resolve_price_range("BTCUSDT", "tight", 0)

    def test_all_valid_modes_resolve(self):
        for mode in VALID_RANGE_MODES:
            r = resolve_price_range("BTCUSDT", mode, 100_000.0)
            assert r["mode"] == mode
            assert r["max"] > r["min"]

    def test_presets_match_spec(self):
        """Sanity-check the documented per-symbol presets."""
        assert PRESET_ABS["BTCUSDT"] == {
            "tight": 1000.0, "standard": 3000.0, "wide": 7500.0, "macro": 15000.0,
        }
        assert PRESET_ABS["ETHUSDT"] == {
            "tight": 100.0, "standard": 300.0, "wide": 750.0, "macro": 1500.0,
        }
        assert PRESET_ABS["SOLUSDT"] == {
            "tight": 10.0, "standard": 30.0, "wide": 75.0, "macro": 150.0,
        }
        assert PRESET_PCT_FALLBACK == {
            "tight": 0.01, "standard": 0.03, "wide": 0.07, "macro": 0.15,
        }


# ── auto_scale_price_step ─────────────────────────────────────────────────────

class TestAutoScalePriceStep:

    def test_narrow_range_keeps_base_step(self):
        # 2000 wide / 600 target = ~3.3 needed; base 10 already coarse enough.
        assert auto_scale_price_step(2000.0, 10.0) == 10.0

    def test_btc_standard_keeps_step_unchanged(self):
        """BTC standard = ±3000 = 6000 wide, target 600 → needed 10. Keep 10."""
        assert auto_scale_price_step(6000.0, 10.0) == 10.0

    def test_wide_range_scales_up(self):
        # 30000 / 600 = 50 needed; expect step >= 50.
        step = auto_scale_price_step(30000.0, 10.0)
        assert step >= 50.0

    def test_macro_range_caps_buckets(self):
        # macro BTC = ±15000 = 30000 wide; target 600 → step ≈ 50.
        step = auto_scale_price_step(30000.0, 10.0, target_buckets=600)
        bucket_count = 30000.0 / step
        assert bucket_count <= 700  # small slack for snap

    def test_zero_range_returns_base(self):
        assert auto_scale_price_step(0, 10.0) == 10.0

    def test_zero_step_passes_through(self):
        assert auto_scale_price_step(1000.0, 0) == 0


# ── build_heatmap_cells + price_range ────────────────────────────────────────

class TestBuildHeatmapCellsWithRange:

    def test_no_range_keeps_all_levels(self):
        frame = build_heatmap_cells(_wide_snapshot(), price_step=10.0)
        prices = {b["price_bucket"] for b in frame["buckets"]}
        assert 50000.0 in prices
        assert 80000.0 in prices

    def test_range_filters_out_of_band_levels(self):
        frame = build_heatmap_cells(
            _wide_snapshot(), price_step=10.0,
            price_range=(67000.0, 68000.0),
        )
        prices = {b["price_bucket"] for b in frame["buckets"]}
        assert 50000.0 not in prices
        assert 80000.0 not in prices
        assert any(67400 <= p <= 67600 for p in prices)

    def test_available_depth_reflects_raw_snapshot(self):
        """Even with filtering, available_depth_* reports the full raw range."""
        frame = build_heatmap_cells(
            _wide_snapshot(), price_step=10.0,
            price_range=(67000.0, 68000.0),
        )
        assert frame["available_depth_min"] == 50000.0
        assert frame["available_depth_max"] == 80000.0

    def test_empty_snapshot_has_none_available(self):
        frame = build_heatmap_cells(
            {"symbol": "X", "captured_at": "", "bids": [], "asks": []},
            price_step=10.0,
        )
        assert frame["available_depth_min"] is None
        assert frame["available_depth_max"] is None
        assert frame["buckets"] == []

    def test_filter_to_empty_range_is_harmless(self):
        frame = build_heatmap_cells(
            _wide_snapshot(), price_step=10.0,
            price_range=(0.0, 100.0),  # no real BTC liquidity here
        )
        assert frame["buckets"] == []
        assert frame["walls"] == []
        # available_depth still reflects the real snapshot extremes.
        assert frame["available_depth_min"] == 50000.0
        assert frame["available_depth_max"] == 80000.0

    def test_invalid_range_min_above_max_raises(self):
        with pytest.raises(ValueError, match="price_range max"):
            build_heatmap_cells(
                _wide_snapshot(), price_step=10.0,
                price_range=(100.0, 50.0),
            )


# ── Payload meta integration ──────────────────────────────────────────────────

class TestPayloadMetaIntegration:

    def test_meta_carries_range_fields(self):
        from services.heatmap_matrix_builder import build_heatmap_matrix
        from services.heatmap_api_payload import build_heatmap_api_payload

        frame = build_heatmap_cells(
            _wide_snapshot(), price_step=10.0,
            price_range=(67000.0, 68000.0),
        )
        matrix = build_heatmap_matrix([frame])
        payload = build_heatmap_api_payload(
            matrix,
            price_range_meta={
                "mode": "tight",
                "min":  67000.0,
                "max":  68000.0,
                "abs":  500.0,
                "pct":  None,
                "available_depth_min": frame["available_depth_min"],
                "available_depth_max": frame["available_depth_max"],
            },
        )
        m = payload["meta"]
        assert m["priceRangeMode"]          == "tight"
        assert m["priceRangeMin"]           == 67000.0
        assert m["priceRangeMax"]           == 68000.0
        assert m["priceRangeRequestedMin"]  == 67000.0
        assert m["priceRangeRequestedMax"]  == 68000.0
        assert m["priceRangeAbs"]           == 500.0
        assert m["availableDepthMin"]       == 50000.0
        assert m["availableDepthMax"]       == 80000.0
        assert "priceRangePercent" not in m  # not used in this call

    def test_payload_without_range_meta_unchanged(self):
        """Existing callers that don't pass price_range_meta get no new fields."""
        from services.heatmap_matrix_builder import build_heatmap_matrix
        from services.heatmap_api_payload import build_heatmap_api_payload

        frame = build_heatmap_cells(_wide_snapshot(), price_step=10.0)
        matrix = build_heatmap_matrix([frame])
        payload = build_heatmap_api_payload(matrix)
        m = payload["meta"]
        for k in ("priceRangeMode", "priceRangeMin", "priceRangeMax",
                  "priceRangeAbs", "priceRangePercent",
                  "priceRangeRequestedMin", "priceRangeRequestedMax",
                  "availableDepthMin", "availableDepthMax"):
            assert k not in m
