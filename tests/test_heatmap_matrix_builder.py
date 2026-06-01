"""
tests/test_heatmap_matrix_builder.py
--------------------------------------
Unit tests for services/heatmap_matrix_builder.py.
No API calls; all data is inline mock frames.
"""

import pytest
from services.heatmap_matrix_builder import (
    build_heatmap_matrix,
    compress_heatmap_matrix,
    summarize_heatmap_matrix,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_bucket(price, bid_usd=0.0, ask_usd=0.0, intensity=50.0):
    total = bid_usd + ask_usd
    if bid_usd > 0 and ask_usd > 0:
        side = "mixed"
    elif bid_usd > 0:
        side = "bid"
    else:
        side = "ask"
    return {
        "price_bucket": price,
        "bid_usd": bid_usd,
        "ask_usd": ask_usd,
        "total_usd": total,
        "side": side,
        "intensity": intensity,
    }


def make_wall(price, side="bid", total_usd=2_000_000.0, intensity=80.0, label=None):
    label = label or ("Major Bid Wall" if side == "bid" else "Major Ask Wall")
    return {"price_bucket": price, "side": side, "total_usd": total_usd,
            "intensity": intensity, "label": label}


def make_frame(captured_at, buckets=None, walls=None, symbol="BTCUSDT", price_step=10.0):
    return {
        "symbol": symbol,
        "captured_at": captured_at,
        "price_step": price_step,
        "buckets": buckets or [],
        "walls": walls or [],
    }


# ── build_heatmap_matrix ──────────────────────────────────────────────────────

class TestBuildHeatmapMatrix:

    def test_price_axis_sorted_ascending(self):
        frames = [
            make_frame("T1", [make_bucket(67430.0, bid_usd=100.0)]),
            make_frame("T2", [make_bucket(67410.0, bid_usd=100.0)]),
            make_frame("T3", [make_bucket(67420.0, bid_usd=100.0)]),
        ]
        m = build_heatmap_matrix(frames)
        assert m["price_axis"] == sorted(m["price_axis"])

    def test_time_axis_sorted_ascending(self):
        frames = [
            make_frame("2026-06-01T12:02:00Z", [make_bucket(67420.0, bid_usd=100.0)]),
            make_frame("2026-06-01T12:00:00Z", [make_bucket(67420.0, bid_usd=100.0)]),
            make_frame("2026-06-01T12:01:00Z", [make_bucket(67420.0, bid_usd=100.0)]),
        ]
        m = build_heatmap_matrix(frames)
        assert m["time_axis"] == sorted(m["time_axis"])

    def test_matrix_dimensions(self):
        frames = [
            make_frame("T1", [make_bucket(100.0, bid_usd=10.0), make_bucket(110.0, ask_usd=10.0)]),
            make_frame("T2", [make_bucket(100.0, bid_usd=10.0)]),
        ]
        m = build_heatmap_matrix(frames)
        n_prices = len(m["price_axis"])
        n_times = len(m["time_axis"])
        assert len(m["bid_matrix"]) == n_prices
        assert len(m["ask_matrix"]) == n_prices
        assert len(m["total_matrix"]) == n_prices
        for row in m["bid_matrix"]:
            assert len(row) == n_times

    def test_bid_value_at_correct_position(self):
        frames = [make_frame("T1", [make_bucket(200.0, bid_usd=500.0, intensity=75.0)])]
        m = build_heatmap_matrix(frames)
        p_idx = m["price_axis"].index(200.0)
        t_idx = m["time_axis"].index("T1")
        assert m["bid_matrix"][p_idx][t_idx] == 75.0

    def test_ask_value_at_correct_position(self):
        frames = [make_frame("T1", [make_bucket(300.0, ask_usd=800.0, intensity=60.0)])]
        m = build_heatmap_matrix(frames)
        p_idx = m["price_axis"].index(300.0)
        t_idx = m["time_axis"].index("T1")
        assert m["ask_matrix"][p_idx][t_idx] == 60.0

    def test_total_matrix_value(self):
        frames = [make_frame("T1", [make_bucket(200.0, bid_usd=500.0, intensity=80.0)])]
        m = build_heatmap_matrix(frames)
        p_idx = m["price_axis"].index(200.0)
        t_idx = m["time_axis"].index("T1")
        assert m["total_matrix"][p_idx][t_idx] == 80.0

    def test_missing_cells_are_zero(self):
        # Frame T1 has price 100, frame T2 has price 200 — no overlap
        frames = [
            make_frame("T1", [make_bucket(100.0, bid_usd=10.0, intensity=50.0)]),
            make_frame("T2", [make_bucket(200.0, bid_usd=10.0, intensity=50.0)]),
        ]
        m = build_heatmap_matrix(frames)
        p100 = m["price_axis"].index(100.0)
        p200 = m["price_axis"].index(200.0)
        t1 = m["time_axis"].index("T1")
        t2 = m["time_axis"].index("T2")
        assert m["bid_matrix"][p100][t2] == 0.0
        assert m["bid_matrix"][p200][t1] == 0.0

    def test_price_min_max_filter(self):
        frames = [
            make_frame("T1", [
                make_bucket(100.0, bid_usd=10.0),
                make_bucket(200.0, bid_usd=10.0),
                make_bucket(300.0, bid_usd=10.0),
            ])
        ]
        m = build_heatmap_matrix(frames, price_min=150.0, price_max=250.0)
        assert m["price_axis"] == [200.0]

    def test_empty_frames_returns_empty_structure(self):
        m = build_heatmap_matrix([])
        assert m["price_axis"] == []
        assert m["time_axis"] == []
        assert m["bid_matrix"] == []
        assert m["frame_count"] == 0

    def test_frames_without_captured_at_are_skipped(self):
        frames = [
            {"symbol": "BTCUSDT", "price_step": 10.0, "buckets": [make_bucket(100.0, bid_usd=1.0)], "walls": []},
            make_frame("T1", [make_bucket(100.0, bid_usd=1.0)]),
        ]
        m = build_heatmap_matrix(frames)
        assert m["frame_count"] == 1
        assert m["time_axis"] == ["T1"]

    def test_walls_deduplicated_keeps_highest_intensity(self):
        wall_low  = make_wall(67400.0, intensity=40.0)
        wall_high = make_wall(67400.0, intensity=90.0)
        frames = [
            make_frame("T1", walls=[wall_low]),
            make_frame("T2", walls=[wall_high]),
        ]
        m = build_heatmap_matrix(frames)
        matching = [w for w in m["walls"] if w["price_bucket"] == 67400.0 and w["side"] == "bid"]
        assert len(matching) == 1
        assert matching[0]["intensity"] == 90.0

    def test_frame_count(self):
        frames = [
            make_frame("T1", [make_bucket(100.0, bid_usd=1.0)]),
            make_frame("T2", [make_bucket(100.0, bid_usd=1.0)]),
            make_frame("T3", [make_bucket(100.0, bid_usd=1.0)]),
        ]
        m = build_heatmap_matrix(frames)
        assert m["frame_count"] == 3


# ── compress_heatmap_matrix ───────────────────────────────────────────────────

class TestCompressHeatmapMatrix:

    def _build(self):
        frames = [
            make_frame("T1", [make_bucket(100.0, bid_usd=10.0, intensity=50.0)]),
            make_frame("T2", [make_bucket(200.0, ask_usd=10.0, intensity=70.0)]),
        ]
        return build_heatmap_matrix(frames)

    def test_only_non_zero_cells_emitted(self):
        m = self._build()
        compressed = compress_heatmap_matrix(m)
        for cell in compressed["cells"]:
            assert cell["bid"] or cell["ask"] or cell["total"]

    def test_cell_count_matches_non_zero_entries(self):
        m = self._build()
        compressed = compress_heatmap_matrix(m)
        # 2 prices × 2 times = 4 cells total, but only 2 are non-zero
        assert len(compressed["cells"]) == 2

    def test_price_min_max_set(self):
        m = self._build()
        compressed = compress_heatmap_matrix(m)
        assert compressed["priceMin"] == min(m["price_axis"])
        assert compressed["priceMax"] == max(m["price_axis"])

    def test_empty_matrix_produces_empty_cells(self):
        m = build_heatmap_matrix([])
        compressed = compress_heatmap_matrix(m)
        assert compressed["cells"] == []
        assert compressed["priceMin"] is None
        assert compressed["priceMax"] is None

    def test_time_buckets_preserved(self):
        m = self._build()
        compressed = compress_heatmap_matrix(m)
        assert compressed["timeBuckets"] == m["time_axis"]


# ── summarize_heatmap_matrix ──────────────────────────────────────────────────

class TestSummarizeHeatmapMatrix:

    def test_max_intensities_computed(self):
        frames = [
            make_frame("T1", [
                make_bucket(100.0, bid_usd=10.0, intensity=30.0),
                make_bucket(200.0, ask_usd=10.0, intensity=80.0),
            ]),
            make_frame("T2", [
                make_bucket(100.0, bid_usd=10.0, intensity=60.0),
            ]),
        ]
        m = build_heatmap_matrix(frames)
        s = summarize_heatmap_matrix(m)
        assert s["max_bid_intensity"] == pytest.approx(60.0)
        assert s["max_ask_intensity"] == pytest.approx(80.0)
        assert s["max_total_intensity"] == pytest.approx(80.0)

    def test_price_range(self):
        frames = [
            make_frame("T1", [
                make_bucket(100.0, bid_usd=1.0),
                make_bucket(300.0, bid_usd=1.0),
            ])
        ]
        m = build_heatmap_matrix(frames)
        s = summarize_heatmap_matrix(m)
        assert s["price_min"] == 100.0
        assert s["price_max"] == 300.0

    def test_time_range(self):
        frames = [
            make_frame("2026-01-01T00:00:00Z", [make_bucket(100.0, bid_usd=1.0)]),
            make_frame("2026-01-01T01:00:00Z", [make_bucket(100.0, bid_usd=1.0)]),
        ]
        m = build_heatmap_matrix(frames)
        s = summarize_heatmap_matrix(m)
        assert s["time_start"] == "2026-01-01T00:00:00Z"
        assert s["time_end"] == "2026-01-01T01:00:00Z"

    def test_wall_count(self):
        frames = [
            make_frame("T1", walls=[make_wall(100.0), make_wall(200.0, side="ask")]),
        ]
        m = build_heatmap_matrix(frames)
        s = summarize_heatmap_matrix(m)
        assert s["wall_count"] == 2

    def test_empty_matrix_summary(self):
        m = build_heatmap_matrix([])
        s = summarize_heatmap_matrix(m)
        assert s["frame_count"] == 0
        assert s["price_min"] is None
        assert s["price_max"] is None
        assert s["time_start"] is None
        assert s["time_end"] is None
        assert s["max_bid_intensity"] == 0.0
        assert s["max_total_intensity"] == 0.0
