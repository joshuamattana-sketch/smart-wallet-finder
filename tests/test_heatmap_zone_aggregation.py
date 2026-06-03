"""
tests/test_heatmap_zone_aggregation.py
---------------------------------------
LM44: trader-grade liquidity aggregation.

Pure-function tests for the new bucketer helpers:
  - aggregate_liquidity_zones (same-side grouping, gap thresholds)
  - score_zones (strengthScore + proximity boost)
  - score_walls (wallRank by strengthScore)
  - pick_key_zones (top-N)
  - build_heatmap_cells with aggregation_mode + current_price
  - build_heatmap_api_payload zones / keyZones / meta integration
"""

from __future__ import annotations

import pytest

from services.orderbook_depth_bucketer import (
    DEFAULT_KEY_ZONE_COUNT,
    DEFAULT_ZONE_GAP_BUCKETS,
    WALL_SCORE_VERSION,
    aggregate_liquidity_zones,
    build_heatmap_cells,
    pick_key_zones,
    score_walls,
    score_zones,
)


def _bucket(price: float, bid: float = 0.0, ask: float = 0.0,
            intensity: float = 50.0) -> dict:
    """Build a bucket dict matching the bucketer's output shape."""
    side = (
        "mixed" if bid > 0 and ask > 0
        else "bid" if bid > 0
        else "ask"
    )
    return {
        "price_bucket": price,
        "bid_usd":      bid,
        "ask_usd":      ask,
        "total_usd":    bid + ask,
        "side":         side,
        "intensity":    intensity,
    }


def _lvl(price: float, qty: float) -> dict:
    return {"price": price, "quantity": qty, "usd": round(price * qty, 2)}


# ── aggregate_liquidity_zones ────────────────────────────────────────────────

class TestAggregateLiquidityZones:

    def test_adjacent_bid_buckets_merge_into_one_zone(self):
        buckets = [
            _bucket(100.0, bid=10_000),
            _bucket(110.0, bid=20_000),
            _bucket(120.0, bid=15_000),
        ]
        zones = aggregate_liquidity_zones(buckets, max_gap_buckets=0, price_step=10.0)
        assert len(zones) == 1
        z = zones[0]
        assert z["side"]        == "bid"
        assert z["priceMin"]    == 100.0
        assert z["priceMax"]    == 120.0
        assert z["bucketCount"] == 3
        assert z["totalUsd"]    == 45_000.0
        assert z["label"]       == "Bid Zone"

    def test_asks_aggregate_separately_from_bids(self):
        buckets = [
            _bucket(100.0, bid=10_000),
            _bucket(110.0, bid=20_000),
            _bucket(200.0, ask=15_000),
            _bucket(210.0, ask=25_000),
        ]
        zones = aggregate_liquidity_zones(buckets, max_gap_buckets=0, price_step=10.0)
        sides = sorted({z["side"] for z in zones})
        assert sides == ["ask", "bid"]
        bid_zone = next(z for z in zones if z["side"] == "bid")
        ask_zone = next(z for z in zones if z["side"] == "ask")
        assert bid_zone["bucketCount"] == 2
        assert ask_zone["bucketCount"] == 2

    def test_small_gap_groups_buckets(self):
        # gap of one empty bucket (10 USD) between 100 and 120 → merged
        # when max_gap_buckets >= 1.
        buckets = [
            _bucket(100.0, bid=10_000),
            _bucket(120.0, bid=15_000),
        ]
        merged = aggregate_liquidity_zones(buckets, max_gap_buckets=1, price_step=10.0)
        assert len(merged) == 1

    def test_large_gap_splits_zones(self):
        # gap of 100 USD between 100 and 200 with max_gap=2 (≤30 USD) → split
        buckets = [
            _bucket(100.0, bid=10_000),
            _bucket(200.0, bid=15_000),
        ]
        split = aggregate_liquidity_zones(buckets, max_gap_buckets=2, price_step=10.0)
        assert len(split) == 2

    def test_mixed_bucket_contributes_to_both_sides(self):
        buckets = [
            _bucket(100.0, bid=5_000, ask=3_000, intensity=70),
            _bucket(110.0, bid=8_000),
            _bucket(110.0, ask=4_000),  # adjacent ask
        ]
        zones = aggregate_liquidity_zones(buckets, max_gap_buckets=0, price_step=10.0)
        bid_zones = [z for z in zones if z["side"] == "bid"]
        ask_zones = [z for z in zones if z["side"] == "ask"]
        # Bid zone has both 100 and 110.
        assert bid_zones and bid_zones[0]["bucketCount"] == 2
        # Ask zone has 100 (from mixed) + 110.
        assert ask_zones and ask_zones[0]["bucketCount"] == 2

    def test_empty_input_returns_empty(self):
        assert aggregate_liquidity_zones([], max_gap_buckets=0, price_step=10.0) == []

    def test_center_price_is_usd_weighted(self):
        buckets = [
            _bucket(100.0, bid=10_000),
            _bucket(200.0, bid=90_000),
        ]
        z = aggregate_liquidity_zones(buckets, max_gap_buckets=20, price_step=10.0)[0]
        # weighted: (100*10000 + 200*90000)/100000 = 190
        assert abs(z["centerPrice"] - 190.0) < 0.001


# ── score_zones / score_walls ────────────────────────────────────────────────

class TestScoring:

    def test_larger_total_yields_higher_strength(self):
        zones = [
            {"side": "bid", "centerPrice": 100.0, "priceMin": 100.0,
             "priceMax": 100.0, "totalUsd": 10_000.0, "maxIntensity": 50,
             "bucketCount": 1, "label": "Bid Zone", "strengthScore": 0.0},
            {"side": "bid", "centerPrice": 200.0, "priceMin": 200.0,
             "priceMax": 200.0, "totalUsd": 5_000_000.0, "maxIntensity": 90,
             "bucketCount": 1, "label": "Bid Zone", "strengthScore": 0.0},
        ]
        score_zones(zones, current_price=None)
        assert zones[1]["strengthScore"] > zones[0]["strengthScore"]

    def test_proximity_boost(self):
        """A zone near current price scores higher than an equally-large far zone."""
        near = {"side": "bid", "centerPrice": 100.0, "priceMin": 100.0,
                "priceMax": 100.0, "totalUsd": 100_000.0, "maxIntensity": 50,
                "bucketCount": 1, "label": "Bid Zone", "strengthScore": 0.0}
        far  = {"side": "bid", "centerPrice": 200.0, "priceMin": 200.0,
                "priceMax": 200.0, "totalUsd": 100_000.0, "maxIntensity": 50,
                "bucketCount": 1, "label": "Bid Zone", "strengthScore": 0.0}
        score_zones([near, far], current_price=100.0)
        assert near["strengthScore"] > far["strengthScore"]
        assert "distancePctFromPrice" in near

    def test_score_walls_assigns_rank(self):
        walls = [
            {"price_bucket": 100.0, "side": "bid", "total_usd": 100_000,
             "intensity": 50, "label": "Major Bid Wall"},
            {"price_bucket": 200.0, "side": "ask", "total_usd": 5_000_000,
             "intensity": 90, "label": "Major Ask Wall"},
            {"price_bucket": 150.0, "side": "bid", "total_usd": 1_000_000,
             "intensity": 70, "label": "Major Bid Wall"},
        ]
        score_walls(walls, current_price=None)
        ranks_by_total = sorted(walls, key=lambda w: w["total_usd"], reverse=True)
        assert ranks_by_total[0]["wallRank"] == 1
        assert ranks_by_total[1]["wallRank"] == 2
        assert ranks_by_total[2]["wallRank"] == 3

    def test_score_walls_empty_passthrough(self):
        assert score_walls([], current_price=100.0) == []


# ── pick_key_zones ────────────────────────────────────────────────────────────

class TestPickKeyZones:

    def test_top_n_orders_by_strength(self):
        zones = [
            {"strengthScore": s, "side": "bid", "centerPrice": 100.0 + i}
            for i, s in enumerate([50, 80, 30, 95, 10])
        ]
        picked = pick_key_zones(zones, top_n=3)
        assert [z["strengthScore"] for z in picked] == [95, 80, 50]

    def test_default_cap(self):
        zones = [{"strengthScore": 50 - i, "side": "bid", "centerPrice": float(i)}
                 for i in range(20)]
        assert len(pick_key_zones(zones)) == DEFAULT_KEY_ZONE_COUNT


# ── build_heatmap_cells integration ──────────────────────────────────────────

class TestBuildHeatmapCellsZones:

    def _snap(self) -> dict:
        return {
            "symbol":      "BTCUSDT",
            "captured_at": "2026-06-01T12:00:00+00:00",
            "bids": [_lvl(67400.0, 5.0), _lvl(67410.0, 10.0), _lvl(67420.0, 8.0)],
            "asks": [_lvl(67500.0, 7.0), _lvl(67510.0, 12.0), _lvl(67520.0, 9.0)],
        }

    def test_frame_includes_zones_and_key_zones(self):
        frame = build_heatmap_cells(
            self._snap(), price_step=10.0,
            aggregation_mode="standard", current_price=67455.0,
        )
        assert "zones" in frame
        assert "key_zones" in frame
        assert frame["aggregation_mode"] == "standard"
        assert frame["bucket_aggregation"] == DEFAULT_ZONE_GAP_BUCKETS["standard"]
        # Bids cluster (3 adjacent buckets) → 1 bid zone; same for asks.
        sides = sorted({z["side"] for z in frame["zones"]})
        assert sides == ["ask", "bid"]

    def test_walls_get_strength_score(self):
        # Force a wall by using a low threshold.
        frame = build_heatmap_cells(
            self._snap(), price_step=10.0, wall_threshold_usd=100_000.0,
            aggregation_mode="standard", current_price=67455.0,
        )
        assert frame["walls"], "expected at least one wall"
        for w in frame["walls"]:
            assert "strengthScore" in w
            assert "wallRank" in w
            assert "distancePctFromPrice" in w

    def test_wide_mode_aggregates_more_than_tight(self):
        """Wide mode allows larger gaps → fewer, broader zones than tight."""
        # Buckets with 30-USD gaps between groups: tight (gap=0) keeps each
        # bucket separate, wide (gap=5 × step10 = 50 USD allowance) merges.
        sym_snap = {
            "symbol":      "BTCUSDT",
            "captured_at": "2026-06-01T12:00:00+00:00",
            "bids": [_lvl(67400.0, 5.0), _lvl(67430.0, 7.0), _lvl(67460.0, 9.0)],
            "asks": [_lvl(67500.0, 6.0), _lvl(67530.0, 8.0), _lvl(67560.0, 10.0)],
        }
        tight = build_heatmap_cells(sym_snap, price_step=10.0, aggregation_mode="tight")
        wide  = build_heatmap_cells(sym_snap, price_step=10.0, aggregation_mode="wide")
        assert len(wide["zones"]) <= len(tight["zones"])
        # Wide should collapse same-side groups into 1 zone per side.
        assert len([z for z in wide["zones"] if z["side"] == "bid"]) == 1


# ── API payload integration ──────────────────────────────────────────────────

class TestPayloadZonesIntegration:

    def test_payload_carries_zones_and_meta(self):
        from services.heatmap_matrix_builder import build_heatmap_matrix
        from services.heatmap_api_payload import build_heatmap_api_payload

        snap = {
            "symbol":      "BTCUSDT",
            "captured_at": "2026-06-01T12:00:00+00:00",
            "bids": [_lvl(67400.0, 5.0), _lvl(67410.0, 10.0)],
            "asks": [_lvl(67500.0, 7.0), _lvl(67510.0, 12.0)],
        }
        frame = build_heatmap_cells(
            snap, price_step=10.0,
            aggregation_mode="standard", current_price=67455.0,
        )
        matrix = build_heatmap_matrix([frame])
        payload = build_heatmap_api_payload(
            matrix,
            zones=frame["zones"],
            key_zones=frame["key_zones"],
            aggregation_mode=frame["aggregation_mode"],
            bucket_aggregation=frame["bucket_aggregation"],
        )
        assert "zones" in payload
        assert "keyZones" in payload
        m = payload["meta"]
        assert m["zoneCount"]         == len(payload["zones"])
        assert m["aggregationMode"]   == "standard"
        assert m["bucketAggregation"] == DEFAULT_ZONE_GAP_BUCKETS["standard"]
        assert m["wallScoreVersion"]  == WALL_SCORE_VERSION

    def test_payload_without_zones_keeps_old_shape(self):
        """When zones aren't passed, payload omits zones / zone meta entirely."""
        from services.heatmap_matrix_builder import build_heatmap_matrix
        from services.heatmap_api_payload import build_heatmap_api_payload

        snap = {
            "symbol":      "BTCUSDT",
            "captured_at": "2026-06-01T12:00:00+00:00",
            "bids": [_lvl(67400.0, 5.0)],
            "asks": [_lvl(67500.0, 7.0)],
        }
        frame = build_heatmap_cells(snap, price_step=10.0)
        matrix = build_heatmap_matrix([frame])
        payload = build_heatmap_api_payload(matrix)
        assert "zones" not in payload
        assert "keyZones" not in payload
        for k in ("zoneCount", "aggregationMode", "bucketAggregation",
                  "wallScoreVersion"):
            assert k not in payload["meta"]
