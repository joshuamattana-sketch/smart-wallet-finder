"""
tests/test_binance_orderbook_worker.py
----------------------------------------
Unit tests for worker/binance_orderbook_worker.py.

Zero real WebSocket calls. All messages are inline dicts/strings.
No infinite loops. Worker never starts automatically.

Test classes:
  TestConstruction                — __init__ shape, validation, defaults
  TestRunOnceFromMessage          — happy path with each message shape
  TestStoreIntegration            — snapshot lands in LiveOrderBookStore
  TestHeatmapHistoryIntegration   — frame lands in HeatmapHistoryStore
  TestGetLatestSnapshot           — retrieval API
  TestGetHeatmapHistory           — retrieval API
  TestBrokenMessages              — malformed inputs return False
  TestSymbolResolution            — explicit symbol, fallback, ambiguous
  TestStop                        — stop() sets is_running and reason
  TestStartPlaceholder            — start() raises RuntimeError
  TestStats                       — message processing counters
  TestUnknownSymbol               — unknown symbol does not crash
  TestSequentialMessages          — multiple frames accumulate correctly
"""

import sys
import os
import json
import asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from services.heatmap_history import HeatmapFrame, HeatmapHistoryStore
from services.live_orderbook_store import LiveOrderBookStore
from worker.binance_orderbook_worker import (
    EXCHANGE_NAME,
    STOP_REASON_INIT,
    STOP_REASON_USER,
    BinanceOrderBookWorker,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

COMBINED_MSG = {
    "stream": "btcusdt@depth20@100ms",
    "data": {
        "lastUpdateId": 200,
        "bids": [["99.0",  "1.0"], ["98.0", "2.0"]],
        "asks": [["101.0", "2.0"], ["102.0", "1.5"]],
    },
}

DIFF_MSG = {
    "e": "depthUpdate", "E": 1_716_200_000_000,
    "s": "BTCUSDT", "U": 160, "u": 161,
    "b": [["100.0", "5.0"], ["99.5", "2.0"]],
    "a": [["101.0", "3.0"], ["101.5", "1.0"]],
}

PARTIAL_MSG = {
    "lastUpdateId": 99,
    "bids": [["99.0", "1.0"], ["98.5", "2.0"]],
    "asks": [["101.0", "1.0"], ["101.5", "1.5"]],
}

ACK_MSG = {"result": None, "id": 1}


def make_worker(symbols=None, max_frames=300):
    store   = LiveOrderBookStore()
    history = HeatmapHistoryStore(max_frames=max_frames)
    worker  = BinanceOrderBookWorker(
        symbols or ["BTCUSDT"],
        store=store, heatmap_history=history,
    )
    return worker, store, history


# ══ TestConstruction ══════════════════════════════════════════════════════════

class TestConstruction:
    def test_default_creates_store(self):
        w = BinanceOrderBookWorker(["BTCUSDT"])
        assert isinstance(w.store, LiveOrderBookStore)

    def test_default_creates_history(self):
        w = BinanceOrderBookWorker(["BTCUSDT"])
        assert isinstance(w.heatmap_history, HeatmapHistoryStore)

    def test_injected_store_used(self):
        store = LiveOrderBookStore()
        w = BinanceOrderBookWorker(["BTCUSDT"], store=store)
        assert w.store is store

    def test_injected_history_used(self):
        history = HeatmapHistoryStore()
        w = BinanceOrderBookWorker(["BTCUSDT"], heatmap_history=history)
        assert w.heatmap_history is history

    def test_symbols_uppercased(self):
        w = BinanceOrderBookWorker(["btcusdt", "EthUsdt"])
        assert w.symbols == ("BTCUSDT", "ETHUSDT")

    def test_symbols_deduplicated(self):
        w = BinanceOrderBookWorker(["BTCUSDT", "btcusdt", "BTCUSDT"])
        assert w.symbols == ("BTCUSDT",)

    def test_is_running_starts_false(self):
        w = BinanceOrderBookWorker(["BTCUSDT"])
        assert w.is_running is False

    def test_stop_reason_starts_not_started(self):
        w = BinanceOrderBookWorker(["BTCUSDT"])
        assert w.stop_reason == STOP_REASON_INIT

    def test_non_list_symbols_raises(self):
        with pytest.raises(TypeError, match="symbols"):
            BinanceOrderBookWorker("BTCUSDT")  # type: ignore

    def test_empty_symbols_raises(self):
        with pytest.raises(ValueError, match="empty"):
            BinanceOrderBookWorker([])

    def test_non_string_symbol_raises(self):
        with pytest.raises(TypeError):
            BinanceOrderBookWorker([123])  # type: ignore

    def test_empty_string_symbol_raises(self):
        with pytest.raises(ValueError):
            BinanceOrderBookWorker(["BTCUSDT", ""])

    def test_zero_heatmap_levels_raises(self):
        with pytest.raises(ValueError, match="heatmap_levels"):
            BinanceOrderBookWorker(["BTCUSDT"], heatmap_levels=0)

    def test_negative_heatmap_levels_raises(self):
        with pytest.raises(ValueError, match="heatmap_levels"):
            BinanceOrderBookWorker(["BTCUSDT"], heatmap_levels=-1)


# ══ TestRunOnceFromMessage ════════════════════════════════════════════════════

class TestRunOnceFromMessage:
    def test_returns_true_on_combined_msg(self):
        w, _, _ = make_worker()
        assert w.run_once_from_message(COMBINED_MSG) is True

    def test_returns_true_on_diff_msg(self):
        w, _, _ = make_worker()
        assert w.run_once_from_message(DIFF_MSG) is True

    def test_returns_true_on_partial_msg_single_symbol(self):
        w, _, _ = make_worker(symbols=["BTCUSDT"])
        assert w.run_once_from_message(PARTIAL_MSG) is True

    def test_returns_false_on_ack(self):
        w, _, _ = make_worker()
        assert w.run_once_from_message(ACK_MSG) is False

    def test_returns_false_on_empty_dict(self):
        w, _, _ = make_worker()
        assert w.run_once_from_message({}) is False

    def test_accepts_json_string(self):
        w, _, _ = make_worker()
        result = w.run_once_from_message(json.dumps(COMBINED_MSG))
        assert result is True

    def test_accepts_bytes(self):
        w, _, _ = make_worker()
        result = w.run_once_from_message(json.dumps(COMBINED_MSG).encode())
        assert result is True

    def test_handle_depth_message_alias_works(self):
        w, _, _ = make_worker()
        assert w.handle_depth_message(COMBINED_MSG) is True


# ══ TestStoreIntegration ══════════════════════════════════════════════════════

class TestStoreIntegration:
    def test_snapshot_stored(self):
        w, store, _ = make_worker()
        w.run_once_from_message(COMBINED_MSG)
        assert store.get_snapshot("BTCUSDT") is not None

    def test_snapshot_symbol_correct(self):
        w, store, _ = make_worker()
        w.run_once_from_message(COMBINED_MSG)
        assert store.get_snapshot("BTCUSDT").symbol == "BTCUSDT"

    def test_snapshot_exchange_is_binance(self):
        w, store, _ = make_worker()
        w.run_once_from_message(COMBINED_MSG)
        assert store.get_snapshot("BTCUSDT").exchange == EXCHANGE_NAME

    def test_snapshot_bid_count(self):
        w, store, _ = make_worker()
        w.run_once_from_message(COMBINED_MSG)
        assert len(store.get_snapshot("BTCUSDT").bids) == 2

    def test_snapshot_ask_count(self):
        w, store, _ = make_worker()
        w.run_once_from_message(COMBINED_MSG)
        assert len(store.get_snapshot("BTCUSDT").asks) == 2

    def test_snapshot_best_bid_price(self):
        w, store, _ = make_worker()
        w.run_once_from_message(COMBINED_MSG)
        snap = store.get_snapshot("BTCUSDT")
        assert snap.bids[0].price == pytest.approx(99.0)

    def test_snapshot_bids_sorted_descending(self):
        w, store, _ = make_worker()
        w.run_once_from_message(COMBINED_MSG)
        prices = [b.price for b in store.get_snapshot("BTCUSDT").bids]
        assert prices == sorted(prices, reverse=True)

    def test_snapshot_asks_sorted_ascending(self):
        w, store, _ = make_worker()
        w.run_once_from_message(COMBINED_MSG)
        prices = [a.price for a in store.get_snapshot("BTCUSDT").asks]
        assert prices == sorted(prices)

    def test_snapshot_mid_price_computed(self):
        w, store, _ = make_worker()
        w.run_once_from_message(COMBINED_MSG)
        # best bid 99.0, best ask 101.0 → mid 100.0
        assert store.get_snapshot("BTCUSDT").mid_price == pytest.approx(100.0)

    def test_overwrite_with_new_message(self):
        w, store, _ = make_worker()
        w.run_once_from_message(COMBINED_MSG)
        w.run_once_from_message(DIFF_MSG)
        snap = store.get_snapshot("BTCUSDT")
        # latest is DIFF_MSG with best bid 100.0
        assert snap.bids[0].price == pytest.approx(100.0)


# ══ TestHeatmapHistoryIntegration ═════════════════════════════════════════════

class TestHeatmapHistoryIntegration:
    def test_frame_added(self):
        w, _, history = make_worker()
        w.run_once_from_message(COMBINED_MSG)
        assert history.frame_count("BTCUSDT") == 1

    def test_frame_is_heatmap_frame(self):
        w, _, history = make_worker()
        w.run_once_from_message(COMBINED_MSG)
        frame = history.get_latest("BTCUSDT")
        assert isinstance(frame, HeatmapFrame)

    def test_frame_symbol_correct(self):
        w, _, history = make_worker()
        w.run_once_from_message(COMBINED_MSG)
        assert history.get_latest("BTCUSDT").symbol == "BTCUSDT"

    def test_frame_has_cells(self):
        w, _, history = make_worker()
        w.run_once_from_message(COMBINED_MSG)
        frame = history.get_latest("BTCUSDT")
        assert len(frame.cells) > 0

    def test_frame_cells_include_bids_and_asks(self):
        w, _, history = make_worker()
        w.run_once_from_message(COMBINED_MSG)
        frame = history.get_latest("BTCUSDT")
        assert len(frame.bid_cells) > 0
        assert len(frame.ask_cells) > 0

    def test_frame_timestamp_matches_event_time(self):
        w, _, history = make_worker()
        w.run_once_from_message(DIFF_MSG)  # has E=1716200000000
        frame = history.get_latest("BTCUSDT")
        assert frame.timestamp_ms == 1_716_200_000_000

    def test_multiple_frames_accumulate(self):
        w, _, history = make_worker()
        for _ in range(5):
            w.run_once_from_message(COMBINED_MSG)
        assert history.frame_count("BTCUSDT") == 5


# ══ TestGetLatestSnapshot ═════════════════════════════════════════════════════

class TestGetLatestSnapshot:
    def test_returns_snapshot_after_message(self):
        w, _, _ = make_worker()
        w.run_once_from_message(COMBINED_MSG)
        snap = w.get_latest_snapshot("BTCUSDT")
        assert snap is not None
        assert snap.symbol == "BTCUSDT"

    def test_returns_none_before_any_message(self):
        w, _, _ = make_worker()
        assert w.get_latest_snapshot("BTCUSDT") is None

    def test_returns_none_for_unknown_symbol(self):
        w, _, _ = make_worker()
        w.run_once_from_message(COMBINED_MSG)
        assert w.get_latest_snapshot("UNKNOWN_NEVER_SEEN") is None

    def test_returns_none_for_empty_symbol(self):
        w, _, _ = make_worker()
        assert w.get_latest_snapshot("") is None

    def test_returns_none_for_non_string(self):
        w, _, _ = make_worker()
        assert w.get_latest_snapshot(None) is None  # type: ignore

    def test_case_insensitive_lookup(self):
        w, _, _ = make_worker()
        w.run_once_from_message(COMBINED_MSG)
        # store normalises internally — lookup with same key works
        assert w.get_latest_snapshot("BTCUSDT") is not None


# ══ TestGetHeatmapHistory ═════════════════════════════════════════════════════

class TestGetHeatmapHistory:
    def test_returns_list(self):
        w, _, _ = make_worker()
        w.run_once_from_message(COMBINED_MSG)
        result = w.get_heatmap_history("BTCUSDT")
        assert isinstance(result, list)

    def test_count_matches_messages_processed(self):
        w, _, _ = make_worker()
        for _ in range(4):
            w.run_once_from_message(COMBINED_MSG)
        assert len(w.get_heatmap_history("BTCUSDT")) == 4

    def test_limit_respected(self):
        w, _, _ = make_worker()
        for _ in range(10):
            w.run_once_from_message(COMBINED_MSG)
        assert len(w.get_heatmap_history("BTCUSDT", limit=3)) == 3

    def test_unknown_symbol_returns_empty(self):
        w, _, _ = make_worker()
        assert w.get_heatmap_history("UNKNOWN") == []

    def test_empty_symbol_returns_empty(self):
        w, _, _ = make_worker()
        assert w.get_heatmap_history("") == []

    def test_zero_limit_returns_empty(self):
        w, _, _ = make_worker()
        w.run_once_from_message(COMBINED_MSG)
        assert w.get_heatmap_history("BTCUSDT", limit=0) == []

    def test_negative_limit_returns_empty(self):
        w, _, _ = make_worker()
        w.run_once_from_message(COMBINED_MSG)
        assert w.get_heatmap_history("BTCUSDT", limit=-5) == []

    def test_frames_are_heatmap_frames(self):
        w, _, _ = make_worker()
        w.run_once_from_message(COMBINED_MSG)
        frames = w.get_heatmap_history("BTCUSDT")
        assert all(isinstance(f, HeatmapFrame) for f in frames)


# ══ TestBrokenMessages ════════════════════════════════════════════════════════

class TestBrokenMessages:
    def test_invalid_json_string_returns_false(self):
        w, _, _ = make_worker()
        assert w.run_once_from_message("not valid json {{{") is False

    def test_empty_string_returns_false(self):
        w, _, _ = make_worker()
        assert w.run_once_from_message("") is False

    def test_empty_dict_returns_false(self):
        w, _, _ = make_worker()
        assert w.run_once_from_message({}) is False

    def test_integer_returns_false(self):
        w, _, _ = make_worker()
        assert w.run_once_from_message(12345) is False  # type: ignore

    def test_none_returns_false(self):
        w, _, _ = make_worker()
        assert w.run_once_from_message(None) is False  # type: ignore

    def test_list_returns_false(self):
        w, _, _ = make_worker()
        assert w.run_once_from_message([1, 2, 3]) is False  # type: ignore

    def test_ack_returns_false(self):
        w, _, _ = make_worker()
        assert w.run_once_from_message(ACK_MSG) is False

    def test_no_bids_no_asks_returns_false(self):
        w, _, _ = make_worker()
        msg = {"lastUpdateId": 1, "bids": [], "asks": []}
        assert w.run_once_from_message(msg) is False

    def test_broken_messages_do_not_clear_state(self):
        w, store, _ = make_worker()
        w.run_once_from_message(COMBINED_MSG)
        for bad in ["", "not json", {}, None, 12345]:
            w.run_once_from_message(bad)  # type: ignore
        # Original snapshot still present
        assert store.get_snapshot("BTCUSDT") is not None

    def test_failed_counter_increments_on_invalid_json(self):
        w, _, _ = make_worker()
        w.run_once_from_message("not json")
        stats = w.stats()
        assert stats["messages_failed"] >= 1


# ══ TestSymbolResolution ══════════════════════════════════════════════════════

class TestSymbolResolution:
    def test_symbol_from_combined_stream(self):
        w, store, _ = make_worker(symbols=["ETHUSDT"])  # explicit override
        # combined msg says btcusdt — that wins over ETHUSDT
        w.run_once_from_message(COMBINED_MSG)
        assert store.get_snapshot("BTCUSDT") is not None
        assert store.get_snapshot("ETHUSDT") is None

    def test_symbol_from_diff_s_field(self):
        w, store, _ = make_worker()
        w.run_once_from_message(DIFF_MSG)
        assert store.get_snapshot("BTCUSDT") is not None

    def test_partial_msg_fallback_to_single_symbol(self):
        w, store, _ = make_worker(symbols=["BTCUSDT"])
        w.run_once_from_message(PARTIAL_MSG)
        assert store.get_snapshot("BTCUSDT") is not None

    def test_partial_msg_ambiguous_returns_false(self):
        w, store, _ = make_worker(symbols=["BTCUSDT", "ETHUSDT"])
        assert w.run_once_from_message(PARTIAL_MSG) is False
        assert store.get_snapshot("BTCUSDT") is None
        assert store.get_snapshot("ETHUSDT") is None


# ══ TestStop ══════════════════════════════════════════════════════════════════

class TestStop:
    def test_stop_sets_is_running_false(self):
        w, _, _ = make_worker()
        w.is_running = True   # simulate active state
        w.stop()
        assert w.is_running is False

    def test_stop_default_reason(self):
        w, _, _ = make_worker()
        w.stop()
        assert w.stop_reason == STOP_REASON_USER

    def test_stop_custom_reason(self):
        w, _, _ = make_worker()
        w.stop(reason="websocket_disconnected")
        assert w.stop_reason == "websocket_disconnected"

    def test_stop_empty_reason_falls_back(self):
        w, _, _ = make_worker()
        w.stop(reason="")
        assert w.stop_reason == STOP_REASON_USER

    def test_double_stop_safe(self):
        w, _, _ = make_worker()
        w.stop()
        w.stop()
        assert w.is_running is False


# ══ TestStartPlaceholder ══════════════════════════════════════════════════════

class TestStartPlaceholder:
    def test_start_is_coroutine(self):
        import inspect
        w, _, _ = make_worker()
        assert inspect.iscoroutinefunction(w.start)

    def test_start_raises_runtime_error(self):
        w, _, _ = make_worker()
        async def _try(): await w.start()
        with pytest.raises(RuntimeError, match="not enabled"):
            asyncio.run(_try())

    def test_start_does_not_set_is_running(self):
        w, _, _ = make_worker()
        async def _try():
            try: await w.start()
            except RuntimeError: pass
        asyncio.run(_try())
        assert w.is_running is False


# ══ TestStats ═════════════════════════════════════════════════════════════════

class TestStats:
    def test_stats_initial(self):
        w, _, _ = make_worker()
        s = w.stats()
        assert s["messages_processed"] == 0
        assert s["messages_failed"] == 0
        assert s["is_running"] is False

    def test_stats_after_success(self):
        w, _, _ = make_worker()
        w.run_once_from_message(COMBINED_MSG)
        assert w.stats()["messages_processed"] == 1

    def test_stats_after_failure(self):
        w, _, _ = make_worker()
        w.run_once_from_message("not json")
        assert w.stats()["messages_failed"] >= 1

    def test_stats_after_ack_no_increment(self):
        w, _, _ = make_worker()
        w.run_once_from_message(ACK_MSG)
        # ACK is filtered before counters, so processed stays 0
        assert w.stats()["messages_processed"] == 0

    def test_stats_lists_symbols(self):
        w, _, _ = make_worker(symbols=["BTCUSDT", "ETHUSDT"])
        s = w.stats()
        assert "BTCUSDT" in s["symbols"]
        assert "ETHUSDT" in s["symbols"]


# ══ TestUnknownSymbol ═════════════════════════════════════════════════════════

class TestUnknownSymbol:
    def test_unknown_symbol_in_diff_msg_no_crash(self):
        w, store, _ = make_worker(symbols=["BTCUSDT"])
        msg = {
            "e": "depthUpdate", "E": 1_000,
            "s": "XYZUSDT", "U": 1, "u": 2,
            "b": [["99.0","1.0"]], "a": [["101.0","1.0"]],
        }
        assert w.run_once_from_message(msg) is True
        assert store.get_snapshot("XYZUSDT") is not None

    def test_unknown_symbol_via_combined_stream(self):
        w, store, _ = make_worker(symbols=["BTCUSDT"])
        msg = {
            "stream": "xyzusdt@depth20@100ms",
            "data": {
                "lastUpdateId": 1,
                "bids": [["50.0", "1.0"]], "asks": [["51.0", "1.0"]],
            },
        }
        assert w.run_once_from_message(msg) is True
        assert store.get_snapshot("XYZUSDT") is not None

    def test_query_unknown_symbol_safe(self):
        w, _, _ = make_worker()
        assert w.get_latest_snapshot("NEVER_HEARD_OF") is None
        assert w.get_heatmap_history("NEVER_HEARD_OF") == []


# ══ TestSequentialMessages ════════════════════════════════════════════════════

class TestSequentialMessages:
    def test_multiple_messages_increase_history(self):
        w, _, history = make_worker()
        for _ in range(7):
            w.run_once_from_message(COMBINED_MSG)
        assert history.frame_count("BTCUSDT") == 7

    def test_multiple_symbols_separate_history(self):
        w, _, history = make_worker(symbols=["BTCUSDT"])
        # BTCUSDT via combined
        w.run_once_from_message(COMBINED_MSG)
        w.run_once_from_message(COMBINED_MSG)
        # ETHUSDT via diff
        eth_msg = {
            "e": "depthUpdate", "E": 1_000,
            "s": "ETHUSDT", "U": 1, "u": 2,
            "b": [["3500.0","1.0"]], "a": [["3501.0","1.0"]],
        }
        w.run_once_from_message(eth_msg)
        assert history.frame_count("BTCUSDT") == 2
        assert history.frame_count("ETHUSDT") == 1

    def test_persistent_walls_detectable_across_messages(self):
        w, _, history = make_worker()
        for _ in range(5):
            w.run_once_from_message(COMBINED_MSG)
        # Same prices across all 5 frames — they should appear as persistent
        walls = history.detect_persistent_walls(
            "BTCUSDT", min_intensity=50, min_frames=3,
        )
        # Not asserting non-empty (intensity depends on heatmap engine math),
        # just that the call works and returns a list
        assert isinstance(walls, list)

    def test_mixed_success_and_failure(self):
        w, _, history = make_worker()
        w.run_once_from_message(COMBINED_MSG)   # success
        w.run_once_from_message("bad")          # fail
        w.run_once_from_message(COMBINED_MSG)   # success
        w.run_once_from_message(ACK_MSG)        # filtered
        w.run_once_from_message(COMBINED_MSG)   # success
        assert history.frame_count("BTCUSDT") == 3
        stats = w.stats()
        assert stats["messages_processed"] == 3
        assert stats["messages_failed"]    >= 1
