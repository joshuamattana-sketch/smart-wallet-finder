"""
tests/test_heatmap_engine.py
------------------------------
Unit tests for services/heatmap_engine.py.

Zero real API calls. All OrderBookSnapshot fixtures are built inline.

Test classes:
  TestCalculateIntensity          — intensity function bounds and values
  TestHeatmapCellDataclass        — dataclass validation and properties
  TestBuildHeatmapFromOrderbook   — snapshot → cells pipeline
  TestDetectHotZones              — hot zone filtering and sorting
  TestDemoHeatmapCells            — existing demo data integrity
  TestFilterCellsByPriceRange     — new range filter function
  TestGenerateWideDemoHeatmap     — wide multi-wall demo generator
  TestRangeConstants              — range mode constants exist and are valid
  TestEdgeCases                   — empty/None/zero/unknown inputs, no crashes
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from core.models import OrderBookLevel, OrderBookSnapshot
from services.heatmap_engine import (
    RANGE_FIVE_PCT,
    RANGE_NEAR,
    RANGE_ONE_PCT,
    RANGE_TWO_PCT,
    RANGE_WIDE_DEMO,
    SIDE_ASK,
    SIDE_BID,
    VALID_RANGE_MODES,
    HeatmapCell,
    _fmt_size,
    _make_label,
    build_heatmap_from_orderbook,
    calculate_intensity,
    demo_heatmap_cells,
    detect_hot_zones,
    filter_cells_by_price_range,
    generate_wide_demo_heatmap,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def make_level(price: float, qty: float, usd: float = 0.0) -> OrderBookLevel:
    return OrderBookLevel(price=price, qty=qty, usd_size=usd or price * qty)


def simple_snapshot() -> OrderBookSnapshot:
    bids = [
        make_level(67_390.0, 5.0,  336_950.0),
        make_level(67_380.0, 2.0,  134_760.0),
        make_level(67_370.0, 8.0,  538_960.0),
    ]
    asks = [
        make_level(67_410.0, 3.0,  202_230.0),
        make_level(67_420.0, 1.0,   67_420.0),
        make_level(67_430.0, 10.0, 674_300.0),
    ]
    return OrderBookSnapshot("BTCUSDT","binance",1_716_200_000_000,
                             bids=bids, asks=asks, mid_price=67_400.0)


def make_cells(prices_sides: list[tuple[float, str]]) -> list[HeatmapCell]:
    max_usd = 1_000_000.0
    cells = []
    for price, side in prices_sides:
        usd = max_usd * (price / 70_000)
        intensity = calculate_intensity(usd, max_usd)
        cells.append(HeatmapCell(
            price=price, side=side, size_usd=round(usd, 2),
            intensity=intensity, label="",
        ))
    return cells


# ══ TestCalculateIntensity ════════════════════════════════════════════════════

class TestCalculateIntensity:
    def test_max_is_100(self):
        assert calculate_intensity(10_000_000, 10_000_000) == 100

    def test_half_is_50(self):
        assert calculate_intensity(5_000_000, 10_000_000) == 50

    def test_zero_is_zero(self):
        assert calculate_intensity(0, 10_000_000) == 0

    def test_result_is_int(self):
        assert isinstance(calculate_intensity(3_000_000, 10_000_000), int)

    def test_result_always_in_range(self):
        for s in [0, 100_000, 1_000_000, 5_000_000, 10_000_000]:
            r = calculate_intensity(s, 10_000_000)
            assert 0 <= r <= 100

    def test_negative_size_raises(self):
        with pytest.raises(ValueError, match="size_usd"):
            calculate_intensity(-1, 1_000_000)

    def test_zero_max_raises(self):
        with pytest.raises(ValueError, match="max_size_usd"):
            calculate_intensity(100, 0)

    def test_proportional_ordering(self):
        m = 1_000_000
        assert calculate_intensity(200_000, m) < calculate_intensity(500_000, m) < calculate_intensity(900_000, m)


# ══ TestHeatmapCellDataclass ══════════════════════════════════════════════════

class TestHeatmapCellDataclass:
    def test_valid_bid(self):
        c = HeatmapCell(100.0, "bid", 5_000, 45)
        assert c.is_bid and not c.is_ask

    def test_valid_ask(self):
        c = HeatmapCell(100.5, "ask", 8_000, 60)
        assert c.is_ask and not c.is_bid

    def test_invalid_side_raises(self):
        with pytest.raises(ValueError, match="side"):
            HeatmapCell(100.0, "both", 1000, 50)

    def test_negative_price_raises(self):
        with pytest.raises(ValueError, match="price"):
            HeatmapCell(-1.0, "bid", 1000, 50)

    def test_negative_size_raises(self):
        with pytest.raises(ValueError, match="size_usd"):
            HeatmapCell(100.0, "bid", -1, 50)

    def test_intensity_above_100_raises(self):
        with pytest.raises(ValueError, match="intensity"):
            HeatmapCell(100.0, "bid", 1000, 150)

    def test_intensity_below_0_raises(self):
        with pytest.raises(ValueError, match="intensity"):
            HeatmapCell(100.0, "bid", 1000, -1)

    def test_is_hot_at_70(self):
        assert HeatmapCell(100.0, "bid", 1000, 70).is_hot

    def test_not_hot_at_69(self):
        assert not HeatmapCell(100.0, "bid", 1000, 69).is_hot

    def test_is_wall_at_85(self):
        assert HeatmapCell(100.0, "bid", 1000, 85).is_wall

    def test_frozen(self):
        c = HeatmapCell(100.0, "bid", 1000, 50)
        with pytest.raises((AttributeError, TypeError)):
            c.price = 200.0  # type: ignore


# ══ TestBuildHeatmapFromOrderbook ═════════════════════════════════════════════

class TestBuildHeatmapFromOrderbook:
    def test_returns_list(self):
        assert isinstance(build_heatmap_from_orderbook(simple_snapshot()), list)

    def test_all_heatmap_cells(self):
        result = build_heatmap_from_orderbook(simple_snapshot())
        assert all(isinstance(c, HeatmapCell) for c in result)

    def test_levels_cap(self):
        result = build_heatmap_from_orderbook(simple_snapshot(), levels=2)
        assert len(result) == 4  # 2 bids + 2 asks

    def test_max_intensity_is_100(self):
        result = build_heatmap_from_orderbook(simple_snapshot())
        assert max(c.intensity for c in result) == 100

    def test_all_intensities_in_range(self):
        result = build_heatmap_from_orderbook(simple_snapshot())
        assert all(0 <= c.intensity <= 100 for c in result)

    def test_empty_snapshot_returns_empty(self):
        assert build_heatmap_from_orderbook(OrderBookSnapshot("X","y",0)) == []

    def test_type_error_non_snapshot(self):
        with pytest.raises(TypeError):
            build_heatmap_from_orderbook("not a snapshot")

    def test_value_error_zero_levels(self):
        with pytest.raises(ValueError, match="levels"):
            build_heatmap_from_orderbook(simple_snapshot(), levels=0)

    def test_usd_size_fallback(self):
        bids = [OrderBookLevel(100.0, 5.0, 0.0)]
        asks = [OrderBookLevel(101.0, 2.0, 0.0)]
        snap = OrderBookSnapshot("X","y",0,bids=bids,asks=asks)
        result = build_heatmap_from_orderbook(snap)
        assert result[0].size_usd == pytest.approx(100.0 * 5.0)


# ══ TestDetectHotZones ════════════════════════════════════════════════════════

class TestDetectHotZones:
    def test_filters_below_threshold(self):
        cells = make_cells([(67_400,SIDE_BID),(67_390,SIDE_BID),(67_410,SIDE_ASK)])
        hot = detect_hot_zones(cells, min_intensity=70)
        assert all(c.intensity >= 70 for c in hot)

    def test_sorted_descending(self):
        demo = demo_heatmap_cells()
        hot = detect_hot_zones(demo, min_intensity=0)
        scores = [c.intensity for c in hot]
        assert scores == sorted(scores, reverse=True)

    def test_empty_input_empty_output(self):
        assert detect_hot_zones([]) == []

    def test_bad_threshold_raises(self):
        with pytest.raises(ValueError):
            detect_hot_zones([], min_intensity=101)

    def test_type_error_non_list(self):
        with pytest.raises(TypeError):
            detect_hot_zones("not list")  # type: ignore


# ══ TestDemoHeatmapCells ══════════════════════════════════════════════════════

class TestDemoHeatmapCells:
    def test_exactly_40_cells(self):
        assert len(demo_heatmap_cells()) == 40

    def test_20_bids_20_asks(self):
        demo = demo_heatmap_cells()
        assert sum(1 for c in demo if c.side == SIDE_BID) == 20
        assert sum(1 for c in demo if c.side == SIDE_ASK) == 20

    def test_all_intensities_in_range(self):
        assert all(0 <= c.intensity <= 100 for c in demo_heatmap_cells())

    def test_has_wall(self):
        assert any(c.is_wall for c in demo_heatmap_cells())

    def test_max_intensity_is_100(self):
        assert max(c.intensity for c in demo_heatmap_cells()) == 100

    def test_consistent_on_repeated_calls(self):
        d1 = demo_heatmap_cells()
        d2 = demo_heatmap_cells()
        assert [c.price for c in d1] == [c.price for c in d2]


# ══ TestFilterCellsByPriceRange ═══════════════════════════════════════════════

class TestFilterCellsByPriceRange:
    def _demo_mid(self) -> float:
        return 67_400.0

    def _demo(self) -> list[HeatmapCell]:
        return demo_heatmap_cells()

    def test_returns_list(self):
        result = filter_cells_by_price_range(self._demo(), self._demo_mid(), RANGE_ONE_PCT)
        assert isinstance(result, list)

    def test_near_is_subset_of_one_pct(self):
        mid = self._demo_mid()
        demo = self._demo()
        near = filter_cells_by_price_range(demo, mid, RANGE_NEAR)
        one  = filter_cells_by_price_range(demo, mid, RANGE_ONE_PCT)
        assert len(near) <= len(one)

    def test_one_pct_is_subset_of_two_pct(self):
        mid = self._demo_mid()
        demo = self._demo()
        one = filter_cells_by_price_range(demo, mid, RANGE_ONE_PCT)
        two = filter_cells_by_price_range(demo, mid, RANGE_TWO_PCT)
        assert len(one) <= len(two)

    def test_two_pct_is_subset_of_five_pct(self):
        mid = self._demo_mid()
        demo = self._demo()
        two  = filter_cells_by_price_range(demo, mid, RANGE_TWO_PCT)
        five = filter_cells_by_price_range(demo, mid, RANGE_FIVE_PCT)
        assert len(two) <= len(five)

    def test_near_cells_within_015pct(self):
        mid  = self._demo_mid()
        near = filter_cells_by_price_range(self._demo(), mid, RANGE_NEAR)
        assert all(abs(c.price - mid) / mid * 100 <= 0.15 for c in near)

    def test_one_pct_cells_within_1pct(self):
        mid = self._demo_mid()
        one = filter_cells_by_price_range(self._demo(), mid, RANGE_ONE_PCT)
        assert all(abs(c.price - mid) / mid * 100 <= 1.0 for c in one)

    def test_five_pct_cells_within_5pct(self):
        mid  = self._demo_mid()
        five = filter_cells_by_price_range(self._demo(), mid, RANGE_FIVE_PCT)
        assert all(abs(c.price - mid) / mid * 100 <= 5.0 for c in five)

    def test_unknown_mode_returns_all(self):
        mid  = self._demo_mid()
        demo = self._demo()
        result = filter_cells_by_price_range(demo, mid, "bogus_mode")
        assert len(result) == len(demo)

    def test_zero_mid_returns_all(self):
        demo = self._demo()
        result = filter_cells_by_price_range(demo, 0.0, RANGE_NEAR)
        assert len(result) == len(demo)

    def test_negative_mid_returns_all(self):
        demo = self._demo()
        result = filter_cells_by_price_range(demo, -100.0, RANGE_ONE_PCT)
        assert len(result) == len(demo)

    def test_empty_cells_returns_empty(self):
        result = filter_cells_by_price_range([], 67_400.0, RANGE_ONE_PCT)
        assert result == []

    def test_type_error_non_list(self):
        with pytest.raises(TypeError):
            filter_cells_by_price_range("not list", 67_400.0, RANGE_ONE_PCT)  # type: ignore

    def test_all_returned_cells_are_heatmap_cells(self):
        result = filter_cells_by_price_range(self._demo(), self._demo_mid(), RANGE_TWO_PCT)
        assert all(isinstance(c, HeatmapCell) for c in result)

    def test_result_preserves_original_order(self):
        mid  = self._demo_mid()
        demo = self._demo()
        result = filter_cells_by_price_range(demo, mid, RANGE_FIVE_PCT)
        # Every cell in result appeared in demo in the same relative order
        demo_prices = [c.price for c in demo]
        result_prices = [c.price for c in result]
        last_idx = -1
        for p in result_prices:
            idx = demo_prices.index(p)
            assert idx > last_idx
            last_idx = idx

    def test_wide_demo_mode_returns_all(self):
        # RANGE_WIDE_DEMO is not in _RANGE_PCT so should return all cells
        demo = self._demo()
        result = filter_cells_by_price_range(demo, self._demo_mid(), RANGE_WIDE_DEMO)
        assert len(result) == len(demo)


# ══ TestGenerateWideDemoHeatmap ═══════════════════════════════════════════════

class TestGenerateWideDemoHeatmap:
    def test_returns_list(self):
        assert isinstance(generate_wide_demo_heatmap(), list)

    def test_minimum_count(self):
        assert len(generate_wide_demo_heatmap()) >= 10

    def test_all_heatmap_cells(self):
        assert all(isinstance(c, HeatmapCell) for c in generate_wide_demo_heatmap())

    def test_has_at_least_one_wall(self):
        assert any(c.is_wall for c in generate_wide_demo_heatmap())

    def test_all_intensities_in_range(self):
        wide = generate_wide_demo_heatmap()
        assert all(0 <= c.intensity <= 100 for c in wide)

    def test_all_prices_positive(self):
        wide = generate_wide_demo_heatmap()
        assert all(c.price > 0 for c in wide)

    def test_contains_bids_and_asks(self):
        wide = generate_wide_demo_heatmap()
        assert any(c.is_bid for c in wide)
        assert any(c.is_ask for c in wide)

    def test_bids_well_below_mid(self):
        # Must have at least one bid more than 1% below BTC mid (~$67,500)
        mid = 67_500.0
        wide = generate_wide_demo_heatmap("BTCUSDT")
        assert any(c.is_bid and c.price < mid * 0.99 for c in wide)

    def test_asks_well_above_mid(self):
        mid = 67_500.0
        wide = generate_wide_demo_heatmap("BTCUSDT")
        assert any(c.is_ask and c.price > mid * 1.01 for c in wide)

    def test_wider_price_range_than_demo(self):
        # Wide heatmap should span a bigger range than the tight demo
        wide = generate_wide_demo_heatmap()
        demo = demo_heatmap_cells()
        wide_span = max(c.price for c in wide) - min(c.price for c in wide)
        demo_span = max(c.price for c in demo) - min(c.price for c in demo)
        assert wide_span > demo_span

    def test_ethusdt_symbol(self):
        eth_wide = generate_wide_demo_heatmap("ETHUSDT")
        assert len(eth_wide) > 0
        # ETH mid ~$3500 — all prices should be in ETH range not BTC range
        assert all(c.price < 10_000 for c in eth_wide)

    def test_solusdt_symbol(self):
        sol_wide = generate_wide_demo_heatmap("SOLUSDT")
        assert len(sol_wide) > 0
        assert all(c.price < 1_000 for c in sol_wide)

    def test_unknown_symbol_no_crash(self):
        result = generate_wide_demo_heatmap("UNKNOWNUSDT")
        assert isinstance(result, list)
        assert len(result) > 0

    def test_lowercase_symbol_works(self):
        result = generate_wide_demo_heatmap("btcusdt")
        assert len(result) > 0

    def test_max_intensity_is_100(self):
        wide = generate_wide_demo_heatmap()
        assert max(c.intensity for c in wide) == 100

    def test_consistent_on_repeated_calls(self):
        w1 = generate_wide_demo_heatmap()
        w2 = generate_wide_demo_heatmap()
        assert len(w1) == len(w2)
        assert [c.price for c in w1] == [c.price for c in w2]


# ══ TestRangeConstants ════════════════════════════════════════════════════════

class TestRangeConstants:
    def test_all_five_modes_in_valid_set(self):
        assert RANGE_NEAR        in VALID_RANGE_MODES
        assert RANGE_ONE_PCT     in VALID_RANGE_MODES
        assert RANGE_TWO_PCT     in VALID_RANGE_MODES
        assert RANGE_FIVE_PCT    in VALID_RANGE_MODES
        assert RANGE_WIDE_DEMO   in VALID_RANGE_MODES

    def test_valid_range_modes_has_five_entries(self):
        assert len(VALID_RANGE_MODES) == 5

    def test_range_mode_values_are_strings(self):
        for mode in VALID_RANGE_MODES:
            assert isinstance(mode, str)
            assert len(mode) > 0

    def test_near_is_tighter_than_one_pct(self):
        # Verify by filtering: near returns fewer or equal cells than 1%
        mid  = 67_400.0
        demo = demo_heatmap_cells()
        near = filter_cells_by_price_range(demo, mid, RANGE_NEAR)
        one  = filter_cells_by_price_range(demo, mid, RANGE_ONE_PCT)
        assert len(near) <= len(one)

    def test_wide_demo_constant_value(self):
        assert RANGE_WIDE_DEMO == "wide_demo"

    def test_near_constant_value(self):
        assert RANGE_NEAR == "near"


# ══ TestEdgeCases ═════════════════════════════════════════════════════════════

class TestEdgeCases:
    def test_filter_tight_range_may_return_empty(self):
        # Build cells all far from mid — near filter should return empty
        cells = [
            HeatmapCell(50_000.0, "bid", 1000, 50),
            HeatmapCell(80_000.0, "ask", 1000, 50),
        ]
        mid = 67_400.0
        # Near band is ±0.15% of 67400 = ~$101 — 50k and 80k are outside
        result = filter_cells_by_price_range(cells, mid, RANGE_NEAR)
        assert result == []

    def test_filter_five_pct_catches_more(self):
        cells = [
            HeatmapCell(67_300.0, "bid", 1000, 50),   # 0.15% below mid
            HeatmapCell(65_000.0, "bid", 1000, 50),   # 3.6% below mid
        ]
        mid = 67_400.0
        near = filter_cells_by_price_range(cells, mid, RANGE_NEAR)
        five = filter_cells_by_price_range(cells, mid, RANGE_FIVE_PCT)
        assert len(five) >= len(near)

    def test_wide_demo_no_crash_for_empty_symbol(self):
        result = generate_wide_demo_heatmap("")
        assert isinstance(result, list)

    def test_calculate_intensity_clamped(self):
        # Float precision: slightly over max should still give 100
        result = calculate_intensity(10_000_001, 10_000_000)
        assert result == 100

    def test_build_from_snapshot_large(self):
        bids = [make_level(float(100 - i), 1.0) for i in range(100)]
        asks = [make_level(float(101 + i), 1.0) for i in range(100)]
        snap = OrderBookSnapshot("X","y",0, bids=bids, asks=asks)
        result = build_heatmap_from_orderbook(snap, levels=30)
        assert len(result) == 60  # 30 bids + 30 asks

    def test_fmt_size_helpers(self):
        assert "1.5M" in _fmt_size(1_500_000)
        assert "250K" in _fmt_size(250_000)
        assert "$99"  in _fmt_size(99)

    def test_make_label_helpers(self):
        assert "WALL" in _make_label(5_000_000, 90)
        assert "HOT"  in _make_label(1_000_000, 75)
        assert _make_label(10_000, 15) == ""

    def test_filter_preserves_heatmap_cell_types(self):
        result = filter_cells_by_price_range(
            demo_heatmap_cells(), 67_400.0, RANGE_TWO_PCT
        )
        assert all(isinstance(c, HeatmapCell) for c in result)

    def test_wide_demo_all_cells_valid(self):
        for c in generate_wide_demo_heatmap():
            assert c.price > 0
            assert c.size_usd >= 0
            assert 0 <= c.intensity <= 100
            assert c.side in (SIDE_BID, SIDE_ASK)
