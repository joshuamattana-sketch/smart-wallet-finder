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


# ═════════════════════════════════════════════════════════════════════════════
# LM45 — Supabase persistence tests
# ═════════════════════════════════════════════════════════════════════════════
# Pure-function tests for the new helpers added to services/heatmap_history.py.
# No real Supabase / network calls — urllib.request.urlopen is patched.

from unittest.mock import patch  # noqa: E402

from services.heatmap_history import (  # noqa: E402
    DEFAULT_HISTORY_INTERVAL_S,
    DEFAULT_HISTORY_MAX_CELLS,
    DEFAULT_HISTORY_MAX_WALLS,
    HISTORY_FRAME_TABLE,
    HISTORY_PAYLOAD_TAG,
    VALID_HISTORY_TARGETS,
    WALL_HISTORY_TABLE,
    HistoryWriteError,
    append_history_frame,
    append_wall_history_rows,
    build_compact_history_payload,
    build_history_frame_row,
    build_wall_history_rows,
)


def _lm45_sample_payload(
    *, cell_count: int = 5, wall_count: int = 3, with_zones: bool = True,
) -> dict:
    cells = [
        {"p": i, "t": 0, "bid": 1.0, "ask": 0.0,
         "total": float(100 - i), "price_bucket": 67000.0 + i}
        for i in range(cell_count)
    ]
    walls = [
        {"price_bucket": 67000.0 + (i * 10), "side": "bid" if i % 2 else "ask",
         "total_usd": 1_000_000.0 - i * 100_000, "intensity": 80.0,
         "label": "Major Bid Wall" if i % 2 else "Major Ask Wall",
         "strengthScore": 90.0 - i, "wallRank": i + 1}
        for i in range(wall_count)
    ]
    payload = {
        "symbol": "BTCUSDT", "exchange": "binance_spot", "timeframe": "5m",
        "priceMin": 67000.0, "priceMax": 67200.0, "priceStep": 10.0,
        "timeBuckets": ["2026-06-01T12:00:00+00:00"],
        "cells": cells, "walls": walls,
        "summary": {"frame_count": 1, "currentPrice": 67100.5,
                    "price_min": 67000.0, "price_max": 67200.0,
                    "time_start": "t0", "time_end": "t0",
                    "max_bid_intensity": 100.0, "max_ask_intensity": 80.0,
                    "max_total_intensity": 100.0, "wall_count": wall_count,
                    "symbol": "BTCUSDT"},
        "meta": {
            "schemaVersion":   "1.0",
            "generatedAt":     "2026-06-01T12:00:00+00:00",
            "cellCount":       cell_count,
            "wallCount":       wall_count,
            "isDemo":          False,
            "liveUpdatedAt":   "2026-06-01T12:00:00+00:00",
            "currentPrice":    67100.5,
            "collector":       "binance_websocket",
            "aggregationMode": "wide",
            "zoneCount":       2,
        },
        "pricePath": [
            {"t": "2026-06-01T11:59:00+00:00", "price": 67099.0,
             "bestBid": 67098.0, "bestAsk": 67100.0},
            {"t": "2026-06-01T12:00:00+00:00", "price": 67100.5,
             "bestBid": 67099.5, "bestAsk": 67101.5},
        ],
    }
    if with_zones:
        payload["zones"] = [
            {"side": "bid", "priceMin": 67000.0, "priceMax": 67010.0,
             "centerPrice": 67005.0, "totalUsd": 800000.0, "maxIntensity": 80.0,
             "bucketCount": 2, "label": "Bid Zone", "strengthScore": 70.0},
            {"side": "ask", "priceMin": 67100.0, "priceMax": 67110.0,
             "centerPrice": 67105.0, "totalUsd": 1200000.0, "maxIntensity": 95.0,
             "bucketCount": 2, "label": "Ask Zone", "strengthScore": 92.0},
        ]
        payload["keyZones"] = list(payload["zones"])
    return payload


class TestLM45CompactPayload:

    def test_drops_cells_above_max(self):
        payload = _lm45_sample_payload(cell_count=500)
        compact = build_compact_history_payload(payload, max_cells=50, max_walls=5)
        assert len(compact["cells"]) == 50
        totals = [c["total"] for c in compact["cells"]]
        assert totals == sorted(totals, reverse=True)

    def test_drops_walls_above_max(self):
        payload = _lm45_sample_payload(wall_count=80)
        compact = build_compact_history_payload(payload, max_cells=10, max_walls=20)
        assert len(compact["walls"]) == 20
        usds = [w["total_usd"] for w in compact["walls"]]
        assert usds == sorted(usds, reverse=True)

    def test_history_meta_tags_present(self):
        compact = build_compact_history_payload(_lm45_sample_payload(cell_count=10))
        m = compact["meta"]
        assert m["historyTag"]        == HISTORY_PAYLOAD_TAG
        assert m["historyCellsKept"]  == 10
        assert m["historyCellsTotal"] == 10
        assert "historyWallsKept"     in m
        assert "historyWallsTotal"    in m

    def test_keeps_only_last_price_path_point(self):
        compact = build_compact_history_payload(_lm45_sample_payload())
        assert "lastPricePoint" in compact
        assert compact["lastPricePoint"]["price"] == 67100.5
        assert "pricePath" not in compact

    def test_zones_and_keyzones_preserved(self):
        compact = build_compact_history_payload(_lm45_sample_payload(with_zones=True))
        assert "zones" in compact
        assert "keyZones" in compact

    def test_zones_absent_when_payload_has_none(self):
        compact = build_compact_history_payload(_lm45_sample_payload(with_zones=False))
        assert "zones" not in compact
        assert "keyZones" not in compact

    def test_does_not_mutate_original(self):
        payload = _lm45_sample_payload(cell_count=100, wall_count=20)
        original_cells = list(payload["cells"])
        original_walls = list(payload["walls"])
        build_compact_history_payload(payload, max_cells=10, max_walls=5)
        assert payload["cells"] == original_cells
        assert payload["walls"] == original_walls
        assert "historyTag" not in payload["meta"]

    def test_negative_caps_rejected(self):
        import pytest
        with pytest.raises(ValueError, match=">= 0"):
            build_compact_history_payload(_lm45_sample_payload(), max_cells=-1)
        with pytest.raises(ValueError, match=">= 0"):
            build_compact_history_payload(_lm45_sample_payload(), max_walls=-1)

    def test_non_dict_payload_rejected(self):
        import pytest
        with pytest.raises(TypeError, match="payload must be a dict"):
            build_compact_history_payload("not a payload")  # type: ignore[arg-type]


class TestLM45HistoryFrameRow:

    def test_row_shape(self):
        row = build_history_frame_row(
            _lm45_sample_payload(), symbol="BTCUSDT", timeframe="5m",
        )
        expected = {
            "symbol", "exchange", "timeframe", "frame_ts", "current_price",
            "price_min", "price_max", "range_mode", "collector",
            "cell_count", "wall_count", "zone_count", "payload",
        }
        assert expected <= set(row.keys())
        assert row["symbol"]        == "BTCUSDT"
        assert row["exchange"]      == "binance_spot"
        assert row["timeframe"]     == "5m"
        assert row["range_mode"]    == "wide"
        assert row["collector"]     == "binance_websocket"
        assert row["current_price"] == 67100.5
        assert row["price_min"]     == 67000.0
        assert row["price_max"]     == 67200.0
        assert row["cell_count"]    == 5
        assert row["wall_count"]    == 3
        assert row["zone_count"]    == 2
        assert row["frame_ts"]      == "2026-06-01T12:00:00+00:00"
        assert isinstance(row["payload"], dict)
        assert row["payload"]["meta"]["historyTag"] == HISTORY_PAYLOAD_TAG

    def test_explicit_frame_ts_wins(self):
        row = build_history_frame_row(
            _lm45_sample_payload(), symbol="BTCUSDT", timeframe="5m",
            frame_ts="2030-01-01T00:00:00+00:00",
        )
        assert row["frame_ts"] == "2030-01-01T00:00:00+00:00"

    def test_falls_back_to_now_when_no_meta_ts(self):
        payload = _lm45_sample_payload()
        del payload["meta"]["liveUpdatedAt"]
        row = build_history_frame_row(
            payload, symbol="BTCUSDT", timeframe="5m",
        )
        assert row["frame_ts"]
        assert "T" in row["frame_ts"]

    def test_current_price_fallback_chain(self):
        payload = _lm45_sample_payload()
        del payload["summary"]["currentPrice"]
        row = build_history_frame_row(payload, symbol="BTCUSDT", timeframe="5m")
        assert row["current_price"] == 67100.5  # meta.currentPrice
        del payload["meta"]["currentPrice"]
        row = build_history_frame_row(payload, symbol="BTCUSDT", timeframe="5m")
        assert row["current_price"] == 67100.5  # lastPricePoint.price


class TestLM45WallHistoryRows:

    def test_uses_key_zones_top_n_ordered_by_strength(self):
        rows = build_wall_history_rows(
            _lm45_sample_payload(with_zones=True),
            symbol="BTCUSDT", timeframe="5m", max_walls=10,
        )
        assert len(rows) == 2
        assert rows[0]["strength_score"] >= rows[1]["strength_score"]
        assert rows[0]["wall_rank"] == 1
        assert rows[1]["wall_rank"] == 2
        for r in rows:
            for k in ("symbol", "exchange", "timeframe", "frame_ts", "side",
                      "price_min", "price_max", "center_price", "total_usd",
                      "strength_score", "wall_rank", "label", "zone"):
                assert k in r

    def test_max_walls_caps_output(self):
        payload = _lm45_sample_payload(with_zones=False)
        payload["keyZones"] = [
            {"side": "bid", "priceMin": float(p), "priceMax": float(p + 1),
             "centerPrice": float(p), "totalUsd": 1000.0 * p,
             "maxIntensity": 50.0, "bucketCount": 1, "label": "Bid Zone",
             "strengthScore": float(p)}
            for p in range(1, 21)
        ]
        rows = build_wall_history_rows(
            payload, symbol="BTCUSDT", timeframe="5m", max_walls=5,
        )
        assert len(rows) == 5
        assert [r["wall_rank"] for r in rows] == [1, 2, 3, 4, 5]

    def test_falls_back_to_zones_when_keyzones_missing(self):
        payload = _lm45_sample_payload(with_zones=True)
        del payload["keyZones"]
        rows = build_wall_history_rows(
            payload, symbol="BTCUSDT", timeframe="5m",
        )
        assert len(rows) == 2

    def test_empty_when_no_zones(self):
        rows = build_wall_history_rows(
            _lm45_sample_payload(with_zones=False),
            symbol="BTCUSDT", timeframe="5m",
        )
        assert rows == []


class _LM45FakeCfg:
    def __init__(self) -> None:
        self.url = "https://example.supabase.co"
        self.service_role_key = "fake-key"


class _LM45OKResp:
    status = 201
    def read(self): return b""
    def __enter__(self): return self
    def __exit__(self, *a): return False


class _LM45ErrResp:
    def __init__(self, status: int = 500) -> None:
        self.status = status
    def read(self): return b""
    def __enter__(self): return self
    def __exit__(self, *a): return False


class TestLM45SupabaseAppend:

    def test_append_history_frame_posts_one_row(self):
        cfg = _LM45FakeCfg()
        captured: dict = {}
        def _fake_urlopen(req, timeout=None):
            captured["url"]     = req.full_url
            captured["headers"] = dict(req.headers)
            captured["body"]    = req.data
            return _LM45OKResp()
        row = build_history_frame_row(
            _lm45_sample_payload(), symbol="BTCUSDT", timeframe="5m",
        )
        with patch(
            "services.heatmap_history.urllib.request.urlopen",
            side_effect=_fake_urlopen,
        ):
            append_history_frame(cfg, row)
        assert captured["url"].endswith(f"/rest/v1/{HISTORY_FRAME_TABLE}")
        assert b"fake-key" not in captured["body"]

    def test_append_wall_history_rows_targets_correct_table(self):
        cfg = _LM45FakeCfg()
        seen: list = []
        def _fake(req, timeout=None):
            seen.append(req.full_url)
            return _LM45OKResp()
        rows = build_wall_history_rows(
            _lm45_sample_payload(with_zones=True),
            symbol="BTCUSDT", timeframe="5m",
        )
        with patch(
            "services.heatmap_history.urllib.request.urlopen",
            side_effect=_fake,
        ):
            append_wall_history_rows(cfg, rows)
        assert seen and seen[0].endswith(f"/rest/v1/{WALL_HISTORY_TABLE}")

    def test_append_wall_history_rows_empty_is_noop(self):
        cfg = _LM45FakeCfg()
        called: list = []
        def _fake_urlopen(req, timeout=None):
            called.append(req.full_url)
            return _LM45OKResp()
        with patch(
            "services.heatmap_history.urllib.request.urlopen",
            side_effect=_fake_urlopen,
        ):
            append_wall_history_rows(cfg, [])
        assert called == []

    def test_history_write_error_on_http_500(self):
        import pytest
        cfg = _LM45FakeCfg()
        with patch(
            "services.heatmap_history.urllib.request.urlopen",
            return_value=_LM45ErrResp(500),
        ):
            with pytest.raises(HistoryWriteError):
                append_history_frame(cfg, {"symbol": "BTCUSDT"})


class TestLM45ModuleConstants:

    def test_valid_history_targets(self):
        assert VALID_HISTORY_TARGETS == ("none", "supabase")

    def test_defaults_sane(self):
        assert DEFAULT_HISTORY_INTERVAL_S >= 1.0
        assert DEFAULT_HISTORY_MAX_CELLS >= 50
        assert DEFAULT_HISTORY_MAX_WALLS >= 5

    def test_history_payload_tag_versioned(self):
        assert HISTORY_PAYLOAD_TAG.startswith("heatmap_history_")
        assert any(ch.isdigit() for ch in HISTORY_PAYLOAD_TAG)
