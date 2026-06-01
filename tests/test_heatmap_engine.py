"""
tests/test_heatmap_engine.py
------------------------------
Unit tests for services/heatmap_engine.py.

Zero real API calls. All OrderBookSnapshot fixtures are built inline.

Test classes:
  TestCalculateIntensity        — intensity function bounds and values
  TestHeatmapCellDataclass      — dataclass validation and properties
  TestBuildHeatmapFromOrderbook — snapshot → cells pipeline
  TestDetectHotZones            — hot zone filtering and sorting
  TestDemoHeatmapCells          — demo data integrity
  TestEdgeCases                 — empty/None/zero inputs, no crashes
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from core.models import OrderBookLevel, OrderBookSnapshot
from services.heatmap_engine import (
    SIDE_ASK,
    SIDE_BID,
    HeatmapCell,
    _fmt_size,
    _make_label,
    build_heatmap_from_orderbook,
    calculate_intensity,
    demo_heatmap_cells,
    detect_hot_zones,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def make_level(price: float, qty: float, usd: float = 0.0) -> OrderBookLevel:
    return OrderBookLevel(price=price, qty=qty, usd_size=usd or price * qty)


def simple_snapshot() -> OrderBookSnapshot:
    """Small balanced snapshot with known values."""
    bids = [
        make_level(67_390.0, 5.0,  336_950.0),
        make_level(67_380.0, 2.0,  134_760.0),
        make_level(67_370.0, 8.0,  538_960.0),   # largest bid
    ]
    asks = [
        make_level(67_410.0, 3.0,  202_230.0),
        make_level(67_420.0, 1.0,   67_420.0),
        make_level(67_430.0, 10.0, 674_300.0),   # largest level overall
    ]
    return OrderBookSnapshot(
        "BTCUSDT", "binance", 1_716_200_000_000,
        bids=bids, asks=asks,
        mid_price=(67_390.0 + 67_410.0) / 2,
    )


def make_cells(intensities: list[tuple[str, int]]) -> list[HeatmapCell]:
    """Create cells with specific (side, intensity) pairs for filter tests."""
    cells = []
    for i, (side, inten) in enumerate(intensities):
        cells.append(HeatmapCell(
            price=float(100 - i),
            side=side,
            size_usd=float(inten * 1_000),
            intensity=inten,
            label="",
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

    def test_quarter_is_25(self):
        assert calculate_intensity(2_500_000, 10_000_000) == 25

    def test_result_is_int(self):
        result = calculate_intensity(3_333_333, 10_000_000)
        assert isinstance(result, int)

    def test_result_in_range(self):
        for size in [0, 100_000, 500_000, 1_000_000, 5_000_000, 10_000_000]:
            r = calculate_intensity(size, 10_000_000)
            assert 0 <= r <= 100, f"Out of range: {r}"

    def test_slightly_over_max_clamped(self):
        # Floating point can produce slightly above 100 — should clamp
        result = calculate_intensity(10_000_001, 10_000_000)
        assert result == 100

    def test_negative_size_raises(self):
        with pytest.raises(ValueError, match="size_usd"):
            calculate_intensity(-1, 1_000_000)

    def test_zero_max_raises(self):
        with pytest.raises(ValueError, match="max_size_usd"):
            calculate_intensity(100, 0)

    def test_negative_max_raises(self):
        with pytest.raises(ValueError, match="max_size_usd"):
            calculate_intensity(100, -5)

    def test_proportional_ordering(self):
        max_s = 1_000_000
        s1 = calculate_intensity(200_000, max_s)
        s2 = calculate_intensity(500_000, max_s)
        s3 = calculate_intensity(900_000, max_s)
        assert s1 < s2 < s3


# ══ TestHeatmapCellDataclass ══════════════════════════════════════════════════

class TestHeatmapCellDataclass:
    def test_valid_bid(self):
        c = HeatmapCell(price=100.0, side="bid", size_usd=5_000, intensity=45)
        assert c.price == 100.0
        assert c.side == "bid"

    def test_valid_ask(self):
        c = HeatmapCell(price=100.5, side="ask", size_usd=8_000, intensity=60)
        assert c.side == "ask"

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
        c = HeatmapCell(100.0, "bid", 1000, 70)
        assert c.is_hot

    def test_not_hot_at_69(self):
        c = HeatmapCell(100.0, "bid", 1000, 69)
        assert not c.is_hot

    def test_is_wall_at_85(self):
        c = HeatmapCell(100.0, "bid", 1000, 85)
        assert c.is_wall

    def test_not_wall_at_84(self):
        c = HeatmapCell(100.0, "bid", 1000, 84)
        assert not c.is_wall

    def test_is_bid_property(self):
        assert HeatmapCell(100.0, "bid", 1000, 50).is_bid
        assert not HeatmapCell(100.0, "ask", 1000, 50).is_bid

    def test_is_ask_property(self):
        assert HeatmapCell(100.0, "ask", 1000, 50).is_ask
        assert not HeatmapCell(100.0, "bid", 1000, 50).is_ask

    def test_frozen(self):
        c = HeatmapCell(100.0, "bid", 1000, 50)
        with pytest.raises((AttributeError, TypeError)):
            c.price = 200.0  # type: ignore

    def test_zero_intensity_valid(self):
        c = HeatmapCell(100.0, "bid", 0, 0)
        assert c.intensity == 0

    def test_100_intensity_valid(self):
        c = HeatmapCell(100.0, "bid", 1_000_000, 100)
        assert c.intensity == 100


# ══ TestBuildHeatmapFromOrderbook ═════════════════════════════════════════════

class TestBuildHeatmapFromOrderbook:
    def test_returns_list(self):
        result = build_heatmap_from_orderbook(simple_snapshot())
        assert isinstance(result, list)

    def test_all_heatmap_cells(self):
        result = build_heatmap_from_orderbook(simple_snapshot())
        assert all(isinstance(c, HeatmapCell) for c in result)

    def test_count_equals_bid_plus_ask(self):
        snap = simple_snapshot()
        result = build_heatmap_from_orderbook(snap, levels=10)
        assert len(result) == 6  # 3 bids + 3 asks (capped by actual levels)

    def test_levels_parameter_limits(self):
        snap = simple_snapshot()
        result = build_heatmap_from_orderbook(snap, levels=2)
        assert len(result) == 4  # 2 bids + 2 asks

    def test_max_intensity_is_100(self):
        result = build_heatmap_from_orderbook(simple_snapshot())
        assert max(c.intensity for c in result) == 100

    def test_all_intensities_in_range(self):
        result = build_heatmap_from_orderbook(simple_snapshot())
        assert all(0 <= c.intensity <= 100 for c in result)

    def test_bid_side_correct(self):
        result = build_heatmap_from_orderbook(simple_snapshot())
        bids = [c for c in result if c.side == SIDE_BID]
        assert len(bids) == 3

    def test_ask_side_correct(self):
        result = build_heatmap_from_orderbook(simple_snapshot())
        asks = [c for c in result if c.side == SIDE_ASK]
        assert len(asks) == 3

    def test_empty_snapshot_returns_empty(self):
        empty = OrderBookSnapshot("X", "y", 0)
        assert build_heatmap_from_orderbook(empty) == []

    def test_bids_only_no_crash(self):
        snap = OrderBookSnapshot("X", "y", 0,
            bids=[make_level(100, 1, 100)], asks=[])
        result = build_heatmap_from_orderbook(snap)
        assert len(result) == 1
        assert result[0].side == SIDE_BID

    def test_asks_only_no_crash(self):
        snap = OrderBookSnapshot("X", "y", 0,
            bids=[], asks=[make_level(101, 1, 101)])
        result = build_heatmap_from_orderbook(snap)
        assert len(result) == 1
        assert result[0].side == SIDE_ASK

    def test_type_error_non_snapshot(self):
        with pytest.raises(TypeError):
            build_heatmap_from_orderbook("not a snapshot")

    def test_type_error_dict(self):
        with pytest.raises(TypeError):
            build_heatmap_from_orderbook({"bids": [], "asks": []})

    def test_value_error_zero_levels(self):
        with pytest.raises(ValueError, match="levels"):
            build_heatmap_from_orderbook(simple_snapshot(), levels=0)

    def test_value_error_negative_levels(self):
        with pytest.raises(ValueError, match="levels"):
            build_heatmap_from_orderbook(simple_snapshot(), levels=-1)

    def test_largest_level_gets_intensity_100(self):
        # ask at 67,430 with usd=674,300 is largest
        result = build_heatmap_from_orderbook(simple_snapshot())
        largest = max(result, key=lambda c: c.size_usd)
        assert largest.intensity == 100

    def test_cells_have_positive_prices(self):
        result = build_heatmap_from_orderbook(simple_snapshot())
        assert all(c.price > 0 for c in result)

    def test_cells_have_nonneg_sizes(self):
        result = build_heatmap_from_orderbook(simple_snapshot())
        assert all(c.size_usd >= 0 for c in result)

    def test_usd_size_fallback_price_times_qty(self):
        # Level with usd_size=0 should fall back to price*qty
        bids = [OrderBookLevel(price=100.0, qty=5.0, usd_size=0.0)]
        asks = [OrderBookLevel(price=101.0, qty=2.0, usd_size=0.0)]
        snap = OrderBookSnapshot("X", "y", 0, bids=bids, asks=asks)
        result = build_heatmap_from_orderbook(snap)
        assert result[0].size_usd == pytest.approx(100.0 * 5.0)

    def test_single_level_each_side(self):
        bids = [make_level(99.0, 1.0, 99.0)]
        asks = [make_level(101.0, 1.0, 101.0)]
        snap = OrderBookSnapshot("X", "y", 0, bids=bids, asks=asks)
        result = build_heatmap_from_orderbook(snap)
        assert len(result) == 2
        # Larger ask gets 100
        assert result[1].intensity == 100  # ask at 101 is larger
        assert result[0].intensity < 100   # bid at 99


# ══ TestDetectHotZones ════════════════════════════════════════════════════════

class TestDetectHotZones:
    def test_returns_list(self):
        assert isinstance(detect_hot_zones([]), list)

    def test_filters_below_threshold(self):
        cells = make_cells([("bid", 90), ("ask", 60), ("bid", 75), ("ask", 30)])
        hot = detect_hot_zones(cells, min_intensity=70)
        assert all(c.intensity >= 70 for c in hot)
        assert len(hot) == 2

    def test_sorted_descending(self):
        cells = make_cells([("bid", 40), ("ask", 90), ("bid", 70), ("ask", 80)])
        hot = detect_hot_zones(cells, min_intensity=0)
        scores = [c.intensity for c in hot]
        assert scores == sorted(scores, reverse=True)

    def test_empty_input_empty_output(self):
        assert detect_hot_zones([]) == []

    def test_nothing_qualifies_returns_empty(self):
        cells = make_cells([("bid", 20), ("ask", 30)])
        assert detect_hot_zones(cells, min_intensity=70) == []

    def test_all_qualify_at_zero_threshold(self):
        cells = make_cells([("bid", 0), ("ask", 50), ("bid", 100)])
        result = detect_hot_zones(cells, min_intensity=0)
        assert len(result) == 3

    def test_at_exact_threshold_included(self):
        cells = make_cells([("bid", 70), ("ask", 69)])
        hot = detect_hot_zones(cells, min_intensity=70)
        assert len(hot) == 1
        assert hot[0].intensity == 70

    def test_invalid_threshold_above_100_raises(self):
        with pytest.raises(ValueError):
            detect_hot_zones([], min_intensity=101)

    def test_invalid_threshold_below_0_raises(self):
        with pytest.raises(ValueError):
            detect_hot_zones([], min_intensity=-1)

    def test_type_error_non_list(self):
        with pytest.raises(TypeError):
            detect_hot_zones("not a list")  # type: ignore

    def test_mixed_sides_in_output(self):
        cells = make_cells([("bid", 90), ("ask", 85), ("bid", 75)])
        hot = detect_hot_zones(cells, min_intensity=70)
        sides = {c.side for c in hot}
        assert SIDE_BID in sides
        assert SIDE_ASK in sides


# ══ TestDemoHeatmapCells ══════════════════════════════════════════════════════

class TestDemoHeatmapCells:
    def test_returns_list(self):
        assert isinstance(demo_heatmap_cells(), list)

    def test_exactly_40_cells(self):
        assert len(demo_heatmap_cells()) == 40

    def test_exactly_20_bids(self):
        demo = demo_heatmap_cells()
        assert sum(1 for c in demo if c.side == SIDE_BID) == 20

    def test_exactly_20_asks(self):
        demo = demo_heatmap_cells()
        assert sum(1 for c in demo if c.side == SIDE_ASK) == 20

    def test_all_heatmap_cells(self):
        assert all(isinstance(c, HeatmapCell) for c in demo_heatmap_cells())

    def test_all_intensities_in_range(self):
        for c in demo_heatmap_cells():
            assert 0 <= c.intensity <= 100, f"Out of range: {c.intensity}"

    def test_has_at_least_one_wall(self):
        assert any(c.is_wall for c in demo_heatmap_cells())

    def test_has_at_least_one_hot_zone(self):
        assert any(c.is_hot for c in demo_heatmap_cells())

    def test_all_prices_positive(self):
        assert all(c.price > 0 for c in demo_heatmap_cells())

    def test_all_sizes_nonnegative(self):
        assert all(c.size_usd >= 0 for c in demo_heatmap_cells())

    def test_has_bid_and_ask_sides(self):
        sides = {c.side for c in demo_heatmap_cells()}
        assert SIDE_BID in sides
        assert SIDE_ASK in sides

    def test_hot_zones_detectable(self):
        demo = demo_heatmap_cells()
        hot = detect_hot_zones(demo, min_intensity=70)
        assert len(hot) >= 2

    def test_max_intensity_is_100(self):
        demo = demo_heatmap_cells()
        assert max(c.intensity for c in demo) == 100

    def test_consistent_on_repeated_calls(self):
        d1 = demo_heatmap_cells()
        d2 = demo_heatmap_cells()
        assert len(d1) == len(d2)
        # Prices should be the same
        assert [c.price for c in d1] == [c.price for c in d2]

    def test_label_present_on_high_intensity(self):
        demo = demo_heatmap_cells()
        walls = [c for c in demo if c.intensity >= 85]
        assert all(len(c.label) > 0 for c in walls)


# ══ TestEdgeCases ═════════════════════════════════════════════════════════════

class TestEdgeCases:
    def test_zero_intensity_cell_valid(self):
        c = HeatmapCell(100.0, "bid", 0, 0)
        assert c.intensity == 0
        assert not c.is_hot

    def test_intensity_at_70_is_hot(self):
        c = HeatmapCell(100.0, "bid", 1000, 70)
        assert c.is_hot
        assert not c.is_wall

    def test_intensity_at_100_is_wall(self):
        c = HeatmapCell(100.0, "bid", 1_000_000, 100)
        assert c.is_wall
        assert c.is_hot

    def test_build_single_level_no_crash(self):
        snap = OrderBookSnapshot("X","y",0,
            bids=[make_level(100,1,100)],asks=[make_level(101,2,202)])
        result = build_heatmap_from_orderbook(snap,levels=1)
        assert len(result) == 2

    def test_build_many_levels_no_crash(self):
        bids = [make_level(100.0-i*0.1, 1.0, 100.0-i*0.1) for i in range(100)]
        asks = [make_level(100.1+i*0.1, 1.0, 100.1+i*0.1) for i in range(100)]
        snap = OrderBookSnapshot("X","y",0,bids=bids,asks=asks)
        result = build_heatmap_from_orderbook(snap,levels=50)
        assert len(result) == 100  # 50 bids + 50 asks

    def test_detect_empty_list_no_crash(self):
        assert detect_hot_zones([]) == []

    def test_calculate_intensity_very_small_fraction(self):
        r = calculate_intensity(1, 10_000_000)
        assert 0 <= r <= 100

    def test_calculate_intensity_exact_half(self):
        assert calculate_intensity(500_000, 1_000_000) == 50

    def test_fmt_size_millions(self):
        assert "1.5M" in _fmt_size(1_500_000)

    def test_fmt_size_thousands(self):
        assert "250K" in _fmt_size(250_000)

    def test_fmt_size_small(self):
        assert "$99" in _fmt_size(99)

    def test_make_label_wall(self):
        label = _make_label(5_000_000, 90)
        assert "WALL" in label

    def test_make_label_hot(self):
        label = _make_label(1_000_000, 75)
        assert "HOT" in label

    def test_make_label_empty_for_low(self):
        label = _make_label(10_000, 15)
        assert label == ""
