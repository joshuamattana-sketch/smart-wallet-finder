"""
tests/test_heatmap_history.py
-------------------------------
Unit tests for services/heatmap_history.py.

Zero API calls, zero network. All cells are built inline.

Test classes:
  TestHeatmapFrameDataclass       — frame properties and accessors
  TestAddGetFrames                — add_frame / get_frames lifecycle
  TestMaxFramesCap                — frame deque bounded correctly
  TestGetLatest                   — latest frame accessor
  TestClear                       — clear single and clear all
  TestBuildIntensityMatrix        — 2-D matrix construction
  TestDetectPersistentWalls       — wall persistence detection
  TestMissingSymbol               — unknown symbol never crashes
  TestValidation                  — TypeError / ValueError on bad inputs
  TestEdgeCases                   — single frame, resize, mixed usage
"""

import sys
import os
import time
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from services.heatmap_engine import HeatmapCell, SIDE_BID, SIDE_ASK, demo_heatmap_cells
from services.heatmap_history import (
    DEFAULT_FRAME_LIMIT,
    DEFAULT_MAX_FRAMES,
    DEFAULT_MIN_FRAMES,
    DEFAULT_MIN_INTENSITY,
    HeatmapFrame,
    HeatmapHistoryStore,
    _validate_symbol,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def cell(price: float, side: str, intensity: int, size_usd: float = 100_000.0) -> HeatmapCell:
    return HeatmapCell(price=price, side=side, size_usd=size_usd, intensity=intensity)


def bid(price: float, intensity: int = 50) -> HeatmapCell:
    return cell(price, SIDE_BID, intensity)


def ask(price: float, intensity: int = 50) -> HeatmapCell:
    return cell(price, SIDE_ASK, intensity)


def simple_cells() -> list[HeatmapCell]:
    return [bid(99.0, 80), bid(98.0, 40), ask(101.0, 90), ask(102.0, 30)]


def wall_cells() -> list[HeatmapCell]:
    """Cells with at least one wall-level bid and ask."""
    return [bid(99.0, 90), bid(98.0, 40), ask(101.0, 88), ask(102.0, 20)]


def store_with_frames(n: int, cells_fn=None, symbol: str = "BTCUSDT") -> HeatmapHistoryStore:
    store = HeatmapHistoryStore(max_frames=100)
    cells_fn = cells_fn or simple_cells
    for i in range(n):
        store.add_frame(symbol, cells_fn(), timestamp_ms=(i + 1) * 1000)
    return store


# ══ TestHeatmapFrameDataclass ═════════════════════════════════════════════════

class TestHeatmapFrameDataclass:
    def test_basic_construction(self):
        f = HeatmapFrame("BTCUSDT", 1_000, simple_cells())
        assert f.symbol == "BTCUSDT"
        assert f.timestamp_ms == 1_000
        assert len(f.cells) == 4

    def test_bid_cells_property(self):
        f = HeatmapFrame("X", 0, simple_cells())
        bids = f.bid_cells
        assert all(c.is_bid for c in bids)
        assert len(bids) == 2

    def test_ask_cells_property(self):
        f = HeatmapFrame("X", 0, simple_cells())
        asks = f.ask_cells
        assert all(c.is_ask for c in asks)
        assert len(asks) == 2

    def test_hot_cells_property(self):
        f = HeatmapFrame("X", 0, simple_cells())  # bid@80 and ask@90 are hot
        hot = f.hot_cells
        assert all(c.intensity >= 70 for c in hot)

    def test_wall_cells_property(self):
        f = HeatmapFrame("X", 0, wall_cells())  # ask@88 is wall
        walls = f.wall_cells
        assert all(c.intensity >= 85 for c in walls)

    def test_is_empty_false_with_cells(self):
        f = HeatmapFrame("X", 0, simple_cells())
        assert not f.is_empty

    def test_is_empty_true_with_no_cells(self):
        f = HeatmapFrame("X", 0, [])
        assert f.is_empty

    def test_cells_are_independent_copy(self):
        original = simple_cells()
        store = HeatmapHistoryStore()
        frame = store.add_frame("BTCUSDT", original)
        # Mutating original list should not affect stored cells
        original.clear()
        assert len(frame.cells) == 4


# ══ TestAddGetFrames ══════════════════════════════════════════════════════════

class TestAddGetFrames:
    def test_add_returns_frame(self):
        store = HeatmapHistoryStore()
        f = store.add_frame("BTCUSDT", simple_cells())
        assert isinstance(f, HeatmapFrame)

    def test_add_preserves_symbol(self):
        store = HeatmapHistoryStore()
        f = store.add_frame("ETHUSDT", simple_cells())
        assert f.symbol == "ETHUSDT"

    def test_add_preserves_timestamp(self):
        store = HeatmapHistoryStore()
        f = store.add_frame("BTCUSDT", simple_cells(), timestamp_ms=99_000)
        assert f.timestamp_ms == 99_000

    def test_add_defaults_timestamp_to_now(self):
        before = int(time.time() * 1000)
        store  = HeatmapHistoryStore()
        f = store.add_frame("BTCUSDT", simple_cells())
        after  = int(time.time() * 1000)
        assert before <= f.timestamp_ms <= after

    def test_get_frames_returns_list(self):
        store = store_with_frames(3)
        assert isinstance(store.get_frames("BTCUSDT"), list)

    def test_get_frames_count(self):
        store = store_with_frames(5)
        assert len(store.get_frames("BTCUSDT")) == 5

    def test_get_frames_oldest_first(self):
        store = store_with_frames(3)
        frames = store.get_frames("BTCUSDT")
        ts = [f.timestamp_ms for f in frames]
        assert ts == sorted(ts)

    def test_get_frames_limit(self):
        store = store_with_frames(10)
        assert len(store.get_frames("BTCUSDT", limit=3)) == 3

    def test_get_frames_limit_larger_than_stored(self):
        store = store_with_frames(3)
        assert len(store.get_frames("BTCUSDT", limit=100)) == 3

    def test_get_frames_empty_symbol(self):
        store = HeatmapHistoryStore()
        assert store.get_frames("BTCUSDT") == []

    def test_get_frames_unknown_symbol(self):
        store = HeatmapHistoryStore()
        assert store.get_frames("XYZUSDT") == []

    def test_multiple_symbols_independent(self):
        store = HeatmapHistoryStore()
        store.add_frame("BTCUSDT", simple_cells())
        store.add_frame("BTCUSDT", simple_cells())
        store.add_frame("ETHUSDT", simple_cells())
        assert len(store.get_frames("BTCUSDT")) == 2
        assert len(store.get_frames("ETHUSDT")) == 1

    def test_cells_stored_correctly(self):
        store  = HeatmapHistoryStore()
        cells  = simple_cells()
        frame  = store.add_frame("BTCUSDT", cells)
        stored = store.get_frames("BTCUSDT")[0]
        assert len(stored.cells) == len(cells)

    def test_frame_count_method(self):
        store = store_with_frames(7)
        assert store.frame_count("BTCUSDT") == 7

    def test_frame_count_zero_initially(self):
        store = HeatmapHistoryStore()
        assert store.frame_count("BTCUSDT") == 0

    def test_symbols_method(self):
        store = HeatmapHistoryStore()
        store.add_frame("BTCUSDT", simple_cells())
        store.add_frame("SOLUSDT", simple_cells())
        syms = store.symbols()
        assert "BTCUSDT" in syms
        assert "SOLUSDT" in syms


# ══ TestMaxFramesCap ══════════════════════════════════════════════════════════

class TestMaxFramesCap:
    def test_default_max_frames_applied(self):
        store = HeatmapHistoryStore(max_frames=5)
        for i in range(10):
            store.add_frame("BTCUSDT", simple_cells())
        assert store.frame_count("BTCUSDT") == 5

    def test_fifo_oldest_dropped(self):
        store = HeatmapHistoryStore(max_frames=3)
        for i in range(5):
            store.add_frame("BTCUSDT", simple_cells(), timestamp_ms=(i + 1) * 1000)
        frames = store.get_frames("BTCUSDT")
        assert len(frames) == 3
        assert frames[0].timestamp_ms == 3_000  # oldest surviving
        assert frames[-1].timestamp_ms == 5_000  # newest

    def test_per_call_max_frames_override(self):
        store = HeatmapHistoryStore(max_frames=100)
        for i in range(10):
            store.add_frame("BTCUSDT", simple_cells(), max_frames=5)
        assert store.frame_count("BTCUSDT") == 5

    def test_resize_preserves_recent_frames(self):
        store = HeatmapHistoryStore(max_frames=20)
        for i in range(10):
            store.add_frame("BTCUSDT", simple_cells(), timestamp_ms=(i + 1) * 1000)
        # Resize to 3 — should keep 3 most recent
        store.add_frame("BTCUSDT", simple_cells(), timestamp_ms=99_000, max_frames=3)
        assert store.frame_count("BTCUSDT") == 3
        latest = store.get_latest("BTCUSDT")
        assert latest.timestamp_ms == 99_000


# ══ TestGetLatest ════════════════════════════════════════════════════════════

class TestGetLatest:
    def test_returns_last_added(self):
        store = store_with_frames(3)
        latest = store.get_latest("BTCUSDT")
        assert latest.timestamp_ms == 3_000  # 3rd frame at 3000ms

    def test_returns_none_if_empty(self):
        assert HeatmapHistoryStore().get_latest("BTCUSDT") is None

    def test_returns_none_for_unknown_symbol(self):
        assert HeatmapHistoryStore().get_latest("XYZUSDT") is None

    def test_returns_same_as_last_get_frames(self):
        store = store_with_frames(5)
        latest    = store.get_latest("BTCUSDT")
        last_list = store.get_frames("BTCUSDT")[-1]
        assert latest is last_list

    def test_updates_after_add(self):
        store = store_with_frames(2)
        f_new = store.add_frame("BTCUSDT", simple_cells(), timestamp_ms=9_000)
        assert store.get_latest("BTCUSDT") is f_new


# ══ TestClear ════════════════════════════════════════════════════════════════

class TestClear:
    def test_clear_single_removes_frames(self):
        store = store_with_frames(5)
        store.clear("BTCUSDT")
        assert store.frame_count("BTCUSDT") == 0

    def test_clear_single_leaves_others(self):
        store = HeatmapHistoryStore()
        store.add_frame("BTCUSDT", simple_cells())
        store.add_frame("ETHUSDT", simple_cells())
        store.clear("BTCUSDT")
        assert store.frame_count("BTCUSDT") == 0
        assert store.frame_count("ETHUSDT") == 1

    def test_clear_all_removes_everything(self):
        store = HeatmapHistoryStore()
        for sym in ["BTCUSDT", "ETHUSDT", "SOLUSDT"]:
            store.add_frame(sym, simple_cells())
        store.clear()
        for sym in store.symbols():
            assert store.frame_count(sym) == 0

    def test_clear_unknown_symbol_no_crash(self):
        HeatmapHistoryStore().clear("XYZUSDT")

    def test_clear_empty_store_no_crash(self):
        HeatmapHistoryStore().clear()

    def test_double_clear_safe(self):
        store = store_with_frames(3)
        store.clear("BTCUSDT")
        store.clear("BTCUSDT")
        assert store.frame_count("BTCUSDT") == 0

    def test_add_after_clear_works(self):
        store = store_with_frames(3)
        store.clear("BTCUSDT")
        store.add_frame("BTCUSDT", simple_cells(), timestamp_ms=1_000)
        assert store.frame_count("BTCUSDT") == 1


# ══ TestBuildIntensityMatrix ══════════════════════════════════════════════════

class TestBuildIntensityMatrix:
    def test_returns_dict(self):
        store = store_with_frames(2)
        mx = store.build_intensity_matrix("BTCUSDT")
        assert isinstance(mx, dict)

    def test_has_required_keys(self):
        store = store_with_frames(2)
        mx = store.build_intensity_matrix("BTCUSDT")
        assert "prices" in mx
        assert "timestamps" in mx
        assert "matrix" in mx
        assert "sides" in mx

    def test_prices_are_sorted(self):
        store = store_with_frames(2)
        mx = store.build_intensity_matrix("BTCUSDT")
        assert mx["prices"] == sorted(mx["prices"], reverse=True)

    def test_timestamps_match_frame_count(self):
        store = store_with_frames(3)
        mx = store.build_intensity_matrix("BTCUSDT")
        assert len(mx["timestamps"]) == 3

    def test_matrix_row_length_equals_frame_count(self):
        store = store_with_frames(4)
        mx = store.build_intensity_matrix("BTCUSDT")
        for price, row in mx["matrix"].items():
            assert len(row) == 4

    def test_matrix_values_are_ints(self):
        store = store_with_frames(2)
        mx = store.build_intensity_matrix("BTCUSDT")
        for row in mx["matrix"].values():
            assert all(isinstance(v, int) for v in row)

    def test_matrix_values_in_range(self):
        store = store_with_frames(3)
        mx = store.build_intensity_matrix("BTCUSDT")
        for row in mx["matrix"].values():
            assert all(0 <= v <= 100 for v in row)

    def test_missing_price_fills_zero(self):
        # Add frame with only one level, then another with two
        store = HeatmapHistoryStore()
        store.add_frame("BTCUSDT", [bid(99.0, 80)], timestamp_ms=1_000)
        store.add_frame("BTCUSDT", [bid(99.0, 70), bid(98.0, 60)], timestamp_ms=2_000)
        mx = store.build_intensity_matrix("BTCUSDT")
        # 98.0 was absent in frame 1 → should be 0
        assert mx["matrix"][98.0][0] == 0
        assert mx["matrix"][98.0][1] == 60

    def test_sides_dict_correct(self):
        store = store_with_frames(2)
        mx = store.build_intensity_matrix("BTCUSDT")
        for price, side in mx["sides"].items():
            assert side in (SIDE_BID, SIDE_ASK)

    def test_empty_symbol_returns_empty_structure(self):
        store = HeatmapHistoryStore()
        mx = store.build_intensity_matrix("BTCUSDT")
        assert mx == {"prices": [], "timestamps": [], "matrix": {}, "sides": {}}

    def test_limit_applied(self):
        store = store_with_frames(10)
        mx = store.build_intensity_matrix("BTCUSDT", limit=3)
        assert len(mx["timestamps"]) == 3

    def test_prices_count_equals_unique_levels(self):
        store = store_with_frames(3)  # simple_cells has 4 unique prices
        mx = store.build_intensity_matrix("BTCUSDT")
        assert len(mx["prices"]) == 4


# ══ TestDetectPersistentWalls ═════════════════════════════════════════════════

class TestDetectPersistentWalls:
    def test_returns_list(self):
        store = store_with_frames(5)
        assert isinstance(store.detect_persistent_walls("BTCUSDT"), list)

    def test_all_entries_have_required_keys(self):
        store = store_with_frames(5, cells_fn=wall_cells)
        walls = store.detect_persistent_walls("BTCUSDT", min_intensity=70, min_frames=3)
        for w in walls:
            assert "price" in w
            assert "side" in w
            assert "persistence_count" in w
            assert "avg_intensity" in w
            assert "max_intensity" in w
            assert "is_wall" in w

    def test_sorted_by_persistence_desc(self):
        store = store_with_frames(8, cells_fn=wall_cells)
        walls = store.detect_persistent_walls("BTCUSDT", min_intensity=50, min_frames=1)
        counts = [w["persistence_count"] for w in walls]
        assert counts == sorted(counts, reverse=True)

    def test_min_frames_threshold(self):
        store = HeatmapHistoryStore()
        # bid@99 appears in 5 frames with intensity 80
        for _ in range(5):
            store.add_frame("BTCUSDT", [bid(99.0, 80)])
        walls = store.detect_persistent_walls("BTCUSDT", min_intensity=70, min_frames=3)
        assert any(w["price"] == 99.0 for w in walls)

    def test_below_min_frames_excluded(self):
        store = HeatmapHistoryStore()
        # bid@99 appears in only 2 frames
        for _ in range(2):
            store.add_frame("BTCUSDT", [bid(99.0, 80)])
        walls = store.detect_persistent_walls("BTCUSDT", min_intensity=70, min_frames=3)
        # With only 2 qualifying frames and min_frames=3, should not appear
        assert not any(w["price"] == 99.0 for w in walls)

    def test_below_min_intensity_excluded(self):
        store = HeatmapHistoryStore()
        for _ in range(5):
            store.add_frame("BTCUSDT", [bid(99.0, 50)])  # intensity 50 < threshold 70
        walls = store.detect_persistent_walls("BTCUSDT", min_intensity=70, min_frames=3)
        assert walls == []

    def test_avg_intensity_computed(self):
        store = HeatmapHistoryStore()
        # Three frames: intensities 80, 90, 70 for same price
        for inten in [80, 90, 70]:
            store.add_frame("BTCUSDT", [bid(99.0, inten)])
        walls = store.detect_persistent_walls("BTCUSDT", min_intensity=70, min_frames=3)
        w = next(x for x in walls if x["price"] == 99.0)
        assert w["avg_intensity"] == pytest.approx((80 + 90 + 70) / 3)

    def test_max_intensity_computed(self):
        store = HeatmapHistoryStore()
        for inten in [70, 85, 75]:
            store.add_frame("BTCUSDT", [bid(99.0, inten)])
        walls = store.detect_persistent_walls("BTCUSDT", min_intensity=70, min_frames=3)
        w = next(x for x in walls if x["price"] == 99.0)
        assert w["max_intensity"] == 85

    def test_is_wall_true_above_85_avg(self):
        store = HeatmapHistoryStore()
        for _ in range(3):
            store.add_frame("BTCUSDT", [bid(99.0, 90)])
        walls = store.detect_persistent_walls("BTCUSDT", min_intensity=70, min_frames=3)
        w = next(x for x in walls if x["price"] == 99.0)
        assert w["is_wall"] is True

    def test_is_wall_false_below_85_avg(self):
        store = HeatmapHistoryStore()
        for _ in range(3):
            store.add_frame("BTCUSDT", [bid(99.0, 72)])
        walls = store.detect_persistent_walls("BTCUSDT", min_intensity=70, min_frames=3)
        w = next(x for x in walls if x["price"] == 99.0)
        assert w["is_wall"] is False

    def test_side_preserved(self):
        store = HeatmapHistoryStore()
        for _ in range(4):
            store.add_frame("BTCUSDT", [ask(101.0, 88)])
        walls = store.detect_persistent_walls("BTCUSDT", min_intensity=70, min_frames=3)
        w = next(x for x in walls if x["price"] == 101.0)
        assert w["side"] == SIDE_ASK

    def test_empty_store_returns_empty(self):
        store = HeatmapHistoryStore()
        assert store.detect_persistent_walls("BTCUSDT") == []

    def test_unknown_symbol_returns_empty(self):
        store = store_with_frames(5)
        assert store.detect_persistent_walls("XYZUSDT") == []

    def test_invalid_min_intensity_raises(self):
        store = HeatmapHistoryStore()
        with pytest.raises(ValueError, match="min_intensity"):
            store.detect_persistent_walls("BTCUSDT", min_intensity=150)

    def test_invalid_min_frames_raises(self):
        store = HeatmapHistoryStore()
        with pytest.raises(ValueError, match="min_frames"):
            store.detect_persistent_walls("BTCUSDT", min_frames=0)

    def test_demo_cells_produce_walls(self):
        store = HeatmapHistoryStore()
        demo  = demo_heatmap_cells()
        for _ in range(5):
            store.add_frame("BTCUSDT", demo)
        walls = store.detect_persistent_walls("BTCUSDT", min_intensity=85, min_frames=3)
        assert len(walls) >= 1  # demo has walls at intensity 85+


# ══ TestMissingSymbol ════════════════════════════════════════════════════════

class TestMissingSymbol:
    def test_get_frames_missing(self):
        assert HeatmapHistoryStore().get_frames("MISSING") == []

    def test_get_latest_missing(self):
        assert HeatmapHistoryStore().get_latest("MISSING") is None

    def test_frame_count_missing(self):
        assert HeatmapHistoryStore().frame_count("MISSING") == 0

    def test_build_matrix_missing(self):
        mx = HeatmapHistoryStore().build_intensity_matrix("MISSING")
        assert mx == {"prices": [], "timestamps": [], "matrix": {}, "sides": {}}

    def test_detect_walls_missing(self):
        assert HeatmapHistoryStore().detect_persistent_walls("MISSING") == []

    def test_clear_missing_no_crash(self):
        HeatmapHistoryStore().clear("MISSING")

    def test_unknown_symbol_auto_registered_on_add(self):
        store = HeatmapHistoryStore()
        store.add_frame("ARBUSDT", simple_cells())
        assert store.frame_count("ARBUSDT") == 1


# ══ TestValidation ════════════════════════════════════════════════════════════

class TestValidation:
    def test_none_symbol_raises(self):
        with pytest.raises(TypeError, match="symbol"):
            HeatmapHistoryStore().add_frame(None, simple_cells())  # type: ignore

    def test_empty_symbol_raises(self):
        with pytest.raises(ValueError, match="empty"):
            HeatmapHistoryStore().add_frame("", simple_cells())

    def test_whitespace_symbol_raises(self):
        with pytest.raises(ValueError, match="empty"):
            HeatmapHistoryStore().add_frame("   ", simple_cells())

    def test_non_list_cells_raises(self):
        with pytest.raises(TypeError, match="cells"):
            HeatmapHistoryStore().add_frame("BTCUSDT", "not a list")  # type: ignore

    def test_bad_max_frames_raises(self):
        with pytest.raises(ValueError, match="max_frames"):
            HeatmapHistoryStore().add_frame("BTCUSDT", simple_cells(), max_frames=0)

    def test_bad_limit_raises(self):
        with pytest.raises(ValueError, match="limit"):
            HeatmapHistoryStore().get_frames("BTCUSDT", limit=0)

    def test_constructor_bad_max_frames_raises(self):
        with pytest.raises(ValueError, match="max_frames"):
            HeatmapHistoryStore(max_frames=0)

    def test_validate_symbol_strips_and_uppercases(self):
        assert _validate_symbol("  btcusdt  ") == "BTCUSDT"

    def test_validate_symbol_none_raises(self):
        with pytest.raises(TypeError):
            _validate_symbol(None)  # type: ignore

    def test_lowercase_symbol_normalised(self):
        store = HeatmapHistoryStore()
        store.add_frame("btcusdt", simple_cells())
        assert store.frame_count("BTCUSDT") == 1


# ══ TestEdgeCases ════════════════════════════════════════════════════════════

class TestEdgeCases:
    def test_single_frame(self):
        store = HeatmapHistoryStore()
        f = store.add_frame("BTCUSDT", simple_cells())
        assert store.frame_count("BTCUSDT") == 1
        assert store.get_latest("BTCUSDT") is f

    def test_empty_cells_list(self):
        store = HeatmapHistoryStore()
        f = store.add_frame("BTCUSDT", [])
        assert f.is_empty
        assert store.frame_count("BTCUSDT") == 1

    def test_matrix_with_single_frame(self):
        store = HeatmapHistoryStore()
        store.add_frame("BTCUSDT", simple_cells(), timestamp_ms=1_000)
        mx = store.build_intensity_matrix("BTCUSDT")
        assert len(mx["timestamps"]) == 1
        for row in mx["matrix"].values():
            assert len(row) == 1

    def test_persistent_walls_single_frame(self):
        store = HeatmapHistoryStore()
        store.add_frame("BTCUSDT", [bid(99.0, 90)])
        # min_frames=1 so a single high-intensity frame qualifies
        walls = store.detect_persistent_walls("BTCUSDT", min_intensity=70, min_frames=1)
        assert any(w["price"] == 99.0 for w in walls)

    def test_large_number_of_frames(self):
        store = HeatmapHistoryStore(max_frames=300)
        for i in range(300):
            store.add_frame("BTCUSDT", simple_cells(), timestamp_ms=(i + 1) * 1000)
        assert store.frame_count("BTCUSDT") == 300
        mx = store.build_intensity_matrix("BTCUSDT", limit=50)
        assert len(mx["timestamps"]) == 50

    def test_thread_safe_concurrent_add(self):
        store  = HeatmapHistoryStore(max_frames=200)
        errors: list[Exception] = []

        def adder():
            try:
                for i in range(50):
                    store.add_frame("BTCUSDT", simple_cells(), timestamp_ms=i * 1000)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=adder) for _ in range(6)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert not errors
        assert store.frame_count("BTCUSDT") <= 200  # capped

    def test_get_frames_returns_frames_not_copies_of_list(self):
        store = store_with_frames(3)
        frames = store.get_frames("BTCUSDT")
        assert all(isinstance(f, HeatmapFrame) for f in frames)

    def test_demo_cells_workflow(self):
        """Full end-to-end with real demo cells."""
        store = HeatmapHistoryStore()
        demo  = demo_heatmap_cells()
        for i in range(5):
            store.add_frame("BTCUSDT", demo, timestamp_ms=(i + 1) * 1000)
        assert store.frame_count("BTCUSDT") == 5
        mx = store.build_intensity_matrix("BTCUSDT")
        assert len(mx["prices"]) == len(demo)  # 40 unique prices
        walls = store.detect_persistent_walls("BTCUSDT", min_intensity=85, min_frames=3)
        assert len(walls) >= 1
        assert all(w["persistence_count"] >= 3 for w in walls)
