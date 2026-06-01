"""
tests/test_orderbook_depth_bucketer.py
---------------------------------------
Unit tests for services/orderbook_depth_bucketer.py.
No API calls; all snapshots are inline mocks.
"""

import pytest
from services.orderbook_depth_bucketer import (
    bucket_depth_snapshot,
    calculate_intensity_scale,
    detect_liquidity_walls,
    build_heatmap_cells,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def make_snapshot(bids=None, asks=None, symbol="BTCUSDT", captured_at="2024-01-01T00:00:00+00:00"):
    return {
        "symbol": symbol,
        "captured_at": captured_at,
        "bids": bids or [],
        "asks": asks or [],
    }


def level(price, qty):
    return {"price": price, "quantity": qty, "usd": round(price * qty, 2)}


# ── bucket_depth_snapshot ─────────────────────────────────────────────────────

class TestBucketDepthSnapshot:
    def test_bid_levels_bucketed_correctly(self):
        # floor(67425/10)*10 = 67420, floor(67418/10)*10 = 67410 — two buckets
        snap = make_snapshot(bids=[level(67425.0, 1.0), level(67428.0, 2.0)])
        result = bucket_depth_snapshot(snap, price_step=10.0)
        # both prices floor to bucket 67420
        assert len(result["buckets"]) == 1
        b = result["buckets"][0]
        assert b["price_bucket"] == 67420.0
        assert b["bid_usd"] == pytest.approx(67425.0 * 1 + 67428.0 * 2, rel=1e-4)
        assert b["side"] == "bid"

    def test_ask_levels_bucketed_correctly(self):
        snap = make_snapshot(asks=[level(67430.0, 0.5), level(67435.0, 1.5)])
        result = bucket_depth_snapshot(snap, price_step=10.0)
        assert len(result["buckets"]) == 1
        b = result["buckets"][0]
        assert b["price_bucket"] == 67430.0
        assert b["ask_usd"] == pytest.approx(67430.0 * 0.5 + 67435.0 * 1.5, rel=1e-4)
        assert b["side"] == "ask"

    def test_mixed_bucket_side(self):
        snap = make_snapshot(
            bids=[level(67425.0, 1.0)],
            asks=[level(67428.0, 1.0)],
        )
        result = bucket_depth_snapshot(snap, price_step=10.0)
        assert len(result["buckets"]) == 1
        b = result["buckets"][0]
        assert b["side"] == "mixed"
        assert b["bid_usd"] > 0
        assert b["ask_usd"] > 0

    def test_usd_sums_are_correct(self):
        snap = make_snapshot(
            bids=[level(100.0, 3.0), level(105.0, 2.0)],
            asks=[level(110.0, 1.0)],
        )
        result = bucket_depth_snapshot(snap, price_step=10.0)
        # 100 and 105 → bucket 100; 110 → bucket 110
        bucket_100 = next(b for b in result["buckets"] if b["price_bucket"] == 100.0)
        assert bucket_100["bid_usd"] == pytest.approx(100.0 * 3 + 105.0 * 2)
        bucket_110 = next(b for b in result["buckets"] if b["price_bucket"] == 110.0)
        assert bucket_110["ask_usd"] == pytest.approx(110.0 * 1.0)

    def test_empty_bids_and_asks(self):
        snap = make_snapshot()
        result = bucket_depth_snapshot(snap, price_step=10.0)
        assert result["buckets"] == []

    def test_empty_bids_only_asks(self):
        snap = make_snapshot(asks=[level(500.0, 1.0)])
        result = bucket_depth_snapshot(snap, price_step=10.0)
        assert len(result["buckets"]) == 1
        assert result["buckets"][0]["bid_usd"] == 0.0

    def test_invalid_price_step_raises(self):
        snap = make_snapshot(bids=[level(100.0, 1.0)])
        with pytest.raises(ValueError):
            bucket_depth_snapshot(snap, price_step=0.0)
        with pytest.raises(ValueError):
            bucket_depth_snapshot(snap, price_step=-5.0)

    def test_metadata_preserved(self):
        snap = make_snapshot(symbol="ETHUSDT", captured_at="2025-06-01T12:00:00+00:00")
        result = bucket_depth_snapshot(snap, price_step=5.0)
        assert result["symbol"] == "ETHUSDT"
        assert result["captured_at"] == "2025-06-01T12:00:00+00:00"
        assert result["price_step"] == 5.0


# ── calculate_intensity_scale ─────────────────────────────────────────────────

class TestCalculateIntensityScale:
    def _buckets(self, totals):
        return [
            {"price_bucket": float(i * 10), "bid_usd": t, "ask_usd": 0.0,
             "total_usd": t, "side": "bid"}
            for i, t in enumerate(totals)
        ]

    def test_intensity_between_0_and_100(self):
        buckets = self._buckets([100_000, 500_000, 1_000_000, 5_000_000])
        result = calculate_intensity_scale(buckets)
        for b in result:
            assert 0.0 <= b["intensity"] <= 100.0

    def test_largest_wall_highest_intensity(self):
        buckets = self._buckets([100_000, 5_000_000, 200_000])
        result = calculate_intensity_scale(buckets)
        intensities = [b["intensity"] for b in result]
        assert intensities[1] > intensities[0]
        assert intensities[1] > intensities[2]

    def test_max_bucket_gets_100(self):
        buckets = self._buckets([100_000, 5_000_000])
        result = calculate_intensity_scale(buckets)
        assert result[-1]["intensity"] == pytest.approx(100.0)

    def test_zero_bucket_gets_0_intensity(self):
        buckets = self._buckets([0, 1_000_000])
        result = calculate_intensity_scale(buckets)
        assert result[0]["intensity"] == 0.0

    def test_all_zero_buckets(self):
        buckets = self._buckets([0, 0, 0])
        result = calculate_intensity_scale(buckets)
        for b in result:
            assert b["intensity"] == 0.0

    def test_single_non_zero_bucket(self):
        buckets = self._buckets([500_000])
        result = calculate_intensity_scale(buckets)
        assert result[0]["intensity"] == pytest.approx(100.0)


# ── detect_liquidity_walls ────────────────────────────────────────────────────

class TestDetectLiquidityWalls:
    def _buckets(self, entries):
        return [
            {"price_bucket": e[0], "bid_usd": e[1], "ask_usd": e[2],
             "total_usd": e[1] + e[2],
             "side": "bid" if e[2] == 0 else ("ask" if e[1] == 0 else "mixed"),
             "intensity": 50.0}
            for e in entries
        ]

    def test_finds_bid_walls(self):
        buckets = self._buckets([(67400.0, 2_000_000.0, 0.0), (67410.0, 500_000.0, 0.0)])
        walls = detect_liquidity_walls(buckets, threshold_usd=1_000_000.0)
        assert len(walls) == 1
        assert walls[0]["price_bucket"] == 67400.0
        assert walls[0]["label"] == "Major Bid Wall"

    def test_finds_ask_walls(self):
        buckets = self._buckets([(67500.0, 0.0, 3_000_000.0)])
        walls = detect_liquidity_walls(buckets, threshold_usd=1_000_000.0)
        assert len(walls) == 1
        assert walls[0]["label"] == "Major Ask Wall"

    def test_mixed_wall_label(self):
        buckets = self._buckets([(67450.0, 800_000.0, 800_000.0)])
        walls = detect_liquidity_walls(buckets, threshold_usd=1_000_000.0)
        assert len(walls) == 1
        assert walls[0]["label"] == "Liquidity Wall"

    def test_no_walls_below_threshold(self):
        buckets = self._buckets([(67400.0, 500_000.0, 0.0)])
        walls = detect_liquidity_walls(buckets, threshold_usd=1_000_000.0)
        assert walls == []

    def test_walls_sorted_by_total_usd_desc(self):
        buckets = self._buckets([
            (67400.0, 1_500_000.0, 0.0),
            (67410.0, 5_000_000.0, 0.0),
            (67420.0, 2_000_000.0, 0.0),
        ])
        walls = detect_liquidity_walls(buckets, threshold_usd=1_000_000.0)
        totals = [w["total_usd"] for w in walls]
        assert totals == sorted(totals, reverse=True)


# ── build_heatmap_cells ───────────────────────────────────────────────────────

class TestBuildHeatmapCells:
    def test_combines_all_stages(self):
        snap = make_snapshot(
            bids=[level(67425.0, 20.0), level(67415.0, 5.0)],
            asks=[level(67435.0, 15.0)],
        )
        result = build_heatmap_cells(snap, price_step=10.0, wall_threshold_usd=100_000.0)
        assert "buckets" in result
        assert "walls" in result
        assert result["symbol"] == "BTCUSDT"
        assert result["price_step"] == 10.0
        for b in result["buckets"]:
            assert "intensity" in b

    def test_wall_threshold_filters_correctly(self):
        snap = make_snapshot(
            bids=[level(100.0, 1.0)],   # usd = 100
            asks=[level(200.0, 1.0)],   # usd = 200
        )
        result = build_heatmap_cells(snap, price_step=100.0, wall_threshold_usd=500.0)
        assert result["walls"] == []

    def test_invalid_price_step_raises(self):
        snap = make_snapshot(bids=[level(100.0, 1.0)])
        with pytest.raises(ValueError):
            build_heatmap_cells(snap, price_step=-1.0)

    def test_empty_snapshot_returns_empty_buckets_and_walls(self):
        snap = make_snapshot()
        result = build_heatmap_cells(snap)
        assert result["buckets"] == []
        assert result["walls"] == []
