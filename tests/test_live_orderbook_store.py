"""
tests/test_live_orderbook_store.py
------------------------------------
Unit tests for services/live_orderbook_store.py.

All tests run fully in-process — no API calls, no network, no WebSocket.
Uses lightweight fake snapshot objects rather than full OrderBookSnapshot
to keep tests fast and focused on store behaviour.

Test classes:
  TestSetGetSnapshot      — basic set/get lifecycle
  TestHistoryManagement   — add_history, max length, get_history
  TestStaleCheck          — is_stale and snapshot_age
  TestClear               — clear single symbol and clear all
  TestMissingSymbol       — unknown symbol never crashes
  TestValidation          — TypeError / ValueError on bad inputs
  TestNormalisation       — case-insensitive symbol handling
  TestThreadSafety        — concurrent read/write correctness
  TestStoreInspection     — symbols(), history_length(), repr()
  TestEdgeCases           — boundary values, resize, mixed usage
"""

import sys
import os
import time
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from services.live_orderbook_store import (
    DEFAULT_MAX_AGE_SECONDS,
    DEFAULT_MAX_HISTORY,
    SUPPORTED_SYMBOLS,
    LiveOrderBookStore,
    SnapshotEntry,
    _validate_symbol,
)


# ── Fake snapshot ─────────────────────────────────────────────────────────────

class FakeSnap:
    """Lightweight stand-in for OrderBookSnapshot in tests."""
    def __init__(self, symbol: str = "BTCUSDT", seq: int = 0) -> None:
        self.symbol = symbol
        self.seq    = seq  # lets tests verify which snapshot was stored

    def __repr__(self) -> str:
        return f"FakeSnap({self.symbol}, seq={self.seq})"


def snap(symbol: str = "BTCUSDT", seq: int = 0) -> FakeSnap:
    return FakeSnap(symbol, seq)


# ══ TestSetGetSnapshot ════════════════════════════════════════════════════════

class TestSetGetSnapshot:
    def test_set_and_get_same_object(self):
        store = LiveOrderBookStore()
        s = snap("BTCUSDT", 1)
        store.set_snapshot("BTCUSDT", s)
        assert store.get_snapshot("BTCUSDT") is s

    def test_get_unknown_symbol_returns_none(self):
        store = LiveOrderBookStore()
        assert store.get_snapshot("BTCUSDT") is None

    def test_overwrite_replaces_previous(self):
        store = LiveOrderBookStore()
        s1, s2 = snap("BTCUSDT", 1), snap("BTCUSDT", 2)
        store.set_snapshot("BTCUSDT", s1)
        store.set_snapshot("BTCUSDT", s2)
        assert store.get_snapshot("BTCUSDT") is s2

    def test_symbols_independent(self):
        store = LiveOrderBookStore()
        sbtc, seth = snap("BTCUSDT"), snap("ETHUSDT")
        store.set_snapshot("BTCUSDT", sbtc)
        store.set_snapshot("ETHUSDT", seth)
        assert store.get_snapshot("BTCUSDT") is sbtc
        assert store.get_snapshot("ETHUSDT") is seth

    def test_all_supported_symbols_accepted(self):
        store = LiveOrderBookStore()
        for sym in SUPPORTED_SYMBOLS:
            s = snap(sym)
            store.set_snapshot(sym, s)
            assert store.get_snapshot(sym) is s

    def test_unsupported_symbol_auto_registered(self):
        store = LiveOrderBookStore()
        s = snap("ARBUSDT")
        store.set_snapshot("ARBUSDT", s)
        assert store.get_snapshot("ARBUSDT") is s

    def test_get_returns_snapshot_not_entry(self):
        store = LiveOrderBookStore()
        s = snap("BTCUSDT")
        store.set_snapshot("BTCUSDT", s)
        result = store.get_snapshot("BTCUSDT")
        assert not isinstance(result, SnapshotEntry)
        assert result is s


# ══ TestHistoryManagement ═════════════════════════════════════════════════════

class TestHistoryManagement:
    def test_add_and_retrieve_history(self):
        store = LiveOrderBookStore()
        s = snap("BTCUSDT", 1)
        store.add_history("BTCUSDT", s)
        history = store.get_history("BTCUSDT", limit=10)
        assert len(history) == 1
        assert history[0] is s

    def test_history_max_length_caps_entries(self):
        store = LiveOrderBookStore(max_history=10)
        for i in range(20):
            store.add_history("BTCUSDT", snap("BTCUSDT", i), max_items=10)
        assert store.history_length("BTCUSDT") == 10

    def test_history_fifo_oldest_dropped(self):
        store = LiveOrderBookStore(max_history=3)
        snaps = [snap("BTCUSDT", i) for i in range(5)]
        for s in snaps:
            store.add_history("BTCUSDT", s, max_items=3)
        history = store.get_history("BTCUSDT", limit=10)
        # only last 3 should remain
        assert len(history) == 3
        assert history[0] is snaps[2]
        assert history[1] is snaps[3]
        assert history[2] is snaps[4]

    def test_get_history_limit_respected(self):
        store = LiveOrderBookStore()
        for i in range(20):
            store.add_history("BTCUSDT", snap("BTCUSDT", i))
        history = store.get_history("BTCUSDT", limit=5)
        assert len(history) == 5

    def test_get_history_newest_last(self):
        store = LiveOrderBookStore()
        snaps = [snap("BTCUSDT", i) for i in range(5)]
        for s in snaps:
            store.add_history("BTCUSDT", s)
        history = store.get_history("BTCUSDT", limit=5)
        assert [h.seq for h in history] == [0, 1, 2, 3, 4]

    def test_get_history_unknown_symbol_returns_empty(self):
        store = LiveOrderBookStore()
        assert store.get_history("XYZUSDT") == []

    def test_get_history_empty_store_returns_empty(self):
        store = LiveOrderBookStore()
        assert store.get_history("BTCUSDT") == []

    def test_get_history_returns_snapshots_not_entries(self):
        store = LiveOrderBookStore()
        s = snap("BTCUSDT")
        store.add_history("BTCUSDT", s)
        result = store.get_history("BTCUSDT", limit=1)
        assert not isinstance(result[0], SnapshotEntry)
        assert result[0] is s

    def test_history_independent_per_symbol(self):
        store = LiveOrderBookStore()
        store.add_history("BTCUSDT", snap("BTCUSDT", 1))
        store.add_history("BTCUSDT", snap("BTCUSDT", 2))
        store.add_history("ETHUSDT", snap("ETHUSDT", 99))
        btc = store.get_history("BTCUSDT", limit=10)
        eth = store.get_history("ETHUSDT", limit=10)
        assert len(btc) == 2
        assert len(eth) == 1
        assert eth[0].seq == 99

    def test_max_items_overrides_per_call(self):
        store = LiveOrderBookStore(max_history=100)
        for i in range(10):
            store.add_history("BTCUSDT", snap("BTCUSDT", i), max_items=5)
        assert store.history_length("BTCUSDT") == 5


# ══ TestStaleCheck ════════════════════════════════════════════════════════════

class TestStaleCheck:
    def test_no_snapshot_is_stale(self):
        store = LiveOrderBookStore()
        assert store.is_stale("BTCUSDT", max_age_seconds=10) is True

    def test_fresh_snapshot_not_stale(self):
        store = LiveOrderBookStore()
        store.set_snapshot("BTCUSDT", snap())
        assert store.is_stale("BTCUSDT", max_age_seconds=5) is False

    def test_unknown_symbol_is_stale(self):
        store = LiveOrderBookStore()
        assert store.is_stale("XYZUSDT") is True

    def test_stale_after_age_exceeded(self, monkeypatch):
        store = LiveOrderBookStore()
        # Set received_at in the past by patching time.time in the check
        store.set_snapshot("BTCUSDT", snap())
        # Manually age the entry
        entry = store._latest["BTCUSDT"]
        entry.received_at = time.time() - 20.0   # 20 seconds old
        assert store.is_stale("BTCUSDT", max_age_seconds=10) is True

    def test_not_stale_just_within_threshold(self):
        store = LiveOrderBookStore()
        store.set_snapshot("BTCUSDT", snap())
        entry = store._latest["BTCUSDT"]
        entry.received_at = time.time() - 4.9
        assert store.is_stale("BTCUSDT", max_age_seconds=5) is False

    def test_snapshot_age_none_when_absent(self):
        store = LiveOrderBookStore()
        assert store.snapshot_age("BTCUSDT") is None

    def test_snapshot_age_returns_float(self):
        store = LiveOrderBookStore()
        store.set_snapshot("BTCUSDT", snap())
        age = store.snapshot_age("BTCUSDT")
        assert isinstance(age, float)
        assert age >= 0.0

    def test_snapshot_age_increases_over_time(self):
        store = LiveOrderBookStore()
        store.set_snapshot("BTCUSDT", snap())
        age1 = store.snapshot_age("BTCUSDT")
        time.sleep(0.05)
        age2 = store.snapshot_age("BTCUSDT")
        assert age2 > age1

    def test_invalid_max_age_raises(self):
        store = LiveOrderBookStore()
        with pytest.raises(ValueError, match="max_age_seconds"):
            store.is_stale("BTCUSDT", max_age_seconds=0)

    def test_negative_max_age_raises(self):
        store = LiveOrderBookStore()
        with pytest.raises(ValueError, match="max_age_seconds"):
            store.is_stale("BTCUSDT", max_age_seconds=-1)


# ══ TestClear ═════════════════════════════════════════════════════════════════

class TestClear:
    def test_clear_single_removes_latest(self):
        store = LiveOrderBookStore()
        store.set_snapshot("BTCUSDT", snap())
        store.clear("BTCUSDT")
        assert store.get_snapshot("BTCUSDT") is None

    def test_clear_single_removes_history(self):
        store = LiveOrderBookStore()
        store.add_history("BTCUSDT", snap())
        store.add_history("BTCUSDT", snap())
        store.clear("BTCUSDT")
        assert store.history_length("BTCUSDT") == 0

    def test_clear_single_leaves_others_intact(self):
        store = LiveOrderBookStore()
        sbtc, seth = snap("BTCUSDT"), snap("ETHUSDT")
        store.set_snapshot("BTCUSDT", sbtc)
        store.set_snapshot("ETHUSDT", seth)
        store.add_history("ETHUSDT", seth)
        store.clear("BTCUSDT")
        assert store.get_snapshot("BTCUSDT") is None
        assert store.get_snapshot("ETHUSDT") is seth
        assert store.history_length("ETHUSDT") == 1

    def test_clear_all_removes_everything(self):
        store = LiveOrderBookStore()
        for sym in SUPPORTED_SYMBOLS:
            store.set_snapshot(sym, snap(sym))
            store.add_history(sym, snap(sym))
        store.clear()
        for sym in SUPPORTED_SYMBOLS:
            assert store.get_snapshot(sym) is None
            assert store.history_length(sym) == 0

    def test_clear_unknown_symbol_no_crash(self):
        store = LiveOrderBookStore()
        store.clear("XYZUSDT")   # should not raise

    def test_clear_all_when_empty_no_crash(self):
        store = LiveOrderBookStore()
        store.clear()   # should not raise

    def test_double_clear_safe(self):
        store = LiveOrderBookStore()
        store.set_snapshot("BTCUSDT", snap())
        store.clear("BTCUSDT")
        store.clear("BTCUSDT")   # second clear should not raise


# ══ TestMissingSymbol ════════════════════════════════════════════════════════

class TestMissingSymbol:
    def test_get_snapshot_missing_returns_none(self):
        store = LiveOrderBookStore()
        assert store.get_snapshot("MISSINGUSDT") is None

    def test_get_history_missing_returns_empty(self):
        store = LiveOrderBookStore()
        assert store.get_history("MISSINGUSDT") == []

    def test_is_stale_missing_is_true(self):
        store = LiveOrderBookStore()
        assert store.is_stale("MISSINGUSDT") is True

    def test_snapshot_age_missing_is_none(self):
        store = LiveOrderBookStore()
        assert store.snapshot_age("MISSINGUSDT") is None

    def test_history_length_missing_is_zero(self):
        store = LiveOrderBookStore()
        assert store.history_length("MISSINGUSDT") == 0

    def test_set_then_get_for_any_symbol(self):
        store = LiveOrderBookStore()
        s = snap("ARBUSDT")
        store.set_snapshot("ARBUSDT", s)
        assert store.get_snapshot("ARBUSDT") is s


# ══ TestValidation ════════════════════════════════════════════════════════════

class TestValidation:
    def test_set_none_symbol_raises(self):
        store = LiveOrderBookStore()
        with pytest.raises(TypeError, match="symbol"):
            store.set_snapshot(None, snap())  # type: ignore

    def test_set_int_symbol_raises(self):
        store = LiveOrderBookStore()
        with pytest.raises(TypeError, match="symbol"):
            store.set_snapshot(42, snap())  # type: ignore

    def test_set_empty_symbol_raises(self):
        store = LiveOrderBookStore()
        with pytest.raises(ValueError, match="empty"):
            store.set_snapshot("", snap())

    def test_set_whitespace_symbol_raises(self):
        store = LiveOrderBookStore()
        with pytest.raises(ValueError, match="empty"):
            store.set_snapshot("   ", snap())

    def test_get_none_symbol_raises(self):
        store = LiveOrderBookStore()
        with pytest.raises(TypeError):
            store.get_snapshot(None)  # type: ignore

    def test_add_history_bad_max_items_raises(self):
        store = LiveOrderBookStore()
        with pytest.raises(ValueError, match="max_items"):
            store.add_history("BTCUSDT", snap(), max_items=0)

    def test_add_history_negative_max_items_raises(self):
        store = LiveOrderBookStore()
        with pytest.raises(ValueError, match="max_items"):
            store.add_history("BTCUSDT", snap(), max_items=-1)

    def test_get_history_bad_limit_raises(self):
        store = LiveOrderBookStore()
        with pytest.raises(ValueError, match="limit"):
            store.get_history("BTCUSDT", limit=0)

    def test_constructor_bad_max_history_raises(self):
        with pytest.raises(ValueError, match="max_history"):
            LiveOrderBookStore(max_history=0)

    def test_validate_symbol_strips_whitespace(self):
        assert _validate_symbol("  btcusdt  ") == "BTCUSDT"

    def test_validate_symbol_uppercases(self):
        assert _validate_symbol("ethusdt") == "ETHUSDT"


# ══ TestNormalisation ════════════════════════════════════════════════════════

class TestNormalisation:
    def test_lowercase_same_as_uppercase(self):
        store = LiveOrderBookStore()
        s = snap("BTCUSDT")
        store.set_snapshot("btcusdt", s)
        assert store.get_snapshot("BTCUSDT") is s
        assert store.get_snapshot("btcusdt") is s

    def test_mixed_case_normalised(self):
        store = LiveOrderBookStore()
        s = snap("ETHUSDT")
        store.set_snapshot("EthUsdt", s)
        assert store.get_snapshot("ETHUSDT") is s

    def test_whitespace_stripped_from_symbol(self):
        store = LiveOrderBookStore()
        s = snap("SOLUSDT")
        store.set_snapshot("  SOLUSDT  ", s)
        assert store.get_snapshot("SOLUSDT") is s

    def test_history_uses_normalised_key(self):
        store = LiveOrderBookStore()
        store.add_history("btcusdt", snap())
        assert store.history_length("BTCUSDT") == 1

    def test_stale_check_normalised(self):
        store = LiveOrderBookStore()
        store.set_snapshot("BTCUSDT", snap())
        assert store.is_stale("btcusdt", max_age_seconds=5) is False


# ══ TestThreadSafety ══════════════════════════════════════════════════════════

class TestThreadSafety:
    def test_concurrent_set_get(self):
        store = LiveOrderBookStore()
        errors: list[Exception] = []

        def writer():
            try:
                for i in range(100):
                    store.set_snapshot("BTCUSDT", snap("BTCUSDT", i))
            except Exception as e:
                errors.append(e)

        def reader():
            try:
                for _ in range(100):
                    store.get_snapshot("BTCUSDT")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer) for _ in range(3)]
        threads += [threading.Thread(target=reader) for _ in range(3)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert not errors, f"Thread errors: {errors}"

    def test_concurrent_add_history(self):
        store = LiveOrderBookStore(max_history=50)
        errors: list[Exception] = []

        def adder():
            try:
                for i in range(30):
                    store.add_history("ETHUSDT", snap("ETHUSDT", i), max_items=50)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=adder) for _ in range(5)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert not errors
        # Total added = 5*30=150, capped at 50
        assert store.history_length("ETHUSDT") <= 50

    def test_concurrent_clear_and_set(self):
        store = LiveOrderBookStore()
        errors: list[Exception] = []

        def setter():
            try:
                for i in range(50):
                    store.set_snapshot("SOLUSDT", snap("SOLUSDT", i))
            except Exception as e:
                errors.append(e)

        def clearer():
            try:
                for _ in range(20):
                    store.clear("SOLUSDT")
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=setter)
        t2 = threading.Thread(target=clearer)
        t1.start(); t2.start()
        t1.join();  t2.join()
        assert not errors

    def test_concurrent_clear_all(self):
        store = LiveOrderBookStore()
        errors: list[Exception] = []

        def mixed():
            try:
                for i in range(30):
                    store.set_snapshot("BTCUSDT", snap("BTCUSDT", i))
                    store.add_history("BTCUSDT", snap("BTCUSDT", i))
                    if i % 5 == 0:
                        store.clear()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=mixed) for _ in range(4)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert not errors


# ══ TestStoreInspection ═══════════════════════════════════════════════════════

class TestStoreInspection:
    def test_symbols_includes_supported(self):
        store = LiveOrderBookStore()
        syms = store.symbols()
        for s in SUPPORTED_SYMBOLS:
            assert s in syms

    def test_symbols_includes_custom(self):
        store = LiveOrderBookStore()
        store.set_snapshot("ARBUSDT", snap())
        assert "ARBUSDT" in store.symbols()

    def test_history_length_zero_initially(self):
        store = LiveOrderBookStore()
        assert store.history_length("BTCUSDT") == 0

    def test_history_length_after_add(self):
        store = LiveOrderBookStore()
        for _ in range(5):
            store.add_history("BTCUSDT", snap())
        assert store.history_length("BTCUSDT") == 5

    def test_repr_contains_symbol_counts(self):
        store = LiveOrderBookStore()
        r = repr(store)
        assert "LiveOrderBookStore" in r
        assert "BTCUSDT" in r

    def test_supported_symbols_constant(self):
        assert "BTCUSDT" in SUPPORTED_SYMBOLS
        assert "ETHUSDT" in SUPPORTED_SYMBOLS
        assert "SOLUSDT" in SUPPORTED_SYMBOLS
        assert "HYPE"    in SUPPORTED_SYMBOLS


# ══ TestEdgeCases ═════════════════════════════════════════════════════════════

class TestEdgeCases:
    def test_history_limit_1(self):
        store = LiveOrderBookStore()
        for i in range(5):
            store.add_history("BTCUSDT", snap("BTCUSDT", i), max_items=1)
        assert store.history_length("BTCUSDT") == 1
        h = store.get_history("BTCUSDT", limit=10)
        assert h[0].seq == 4   # only the last one

    def test_get_history_limit_larger_than_stored(self):
        store = LiveOrderBookStore()
        store.add_history("BTCUSDT", snap())
        h = store.get_history("BTCUSDT", limit=1000)
        assert len(h) == 1

    def test_set_same_snapshot_twice(self):
        store = LiveOrderBookStore()
        s = snap()
        store.set_snapshot("BTCUSDT", s)
        store.set_snapshot("BTCUSDT", s)
        assert store.get_snapshot("BTCUSDT") is s

    def test_snapshot_entry_received_at_set_automatically(self):
        before = time.time()
        entry = SnapshotEntry(snap())
        after  = time.time()
        assert before <= entry.received_at <= after

    def test_snapshot_entry_custom_received_at(self):
        entry = SnapshotEntry(snap(), received_at=1_000_000.0)
        assert entry.received_at == 1_000_000.0

    def test_set_none_value_is_accepted(self):
        # Storing None as a snapshot value is a valid operation
        store = LiveOrderBookStore()
        store.set_snapshot("BTCUSDT", None)
        result = store.get_snapshot("BTCUSDT")
        assert result is None  # None snapshot set and retrieved

    def test_max_history_resize_on_add_history(self):
        store = LiveOrderBookStore(max_history=100)
        for i in range(20):
            store.add_history("BTCUSDT", snap("BTCUSDT", i), max_items=100)
        # Now add with smaller max_items — should resize deque, keeping recent
        store.add_history("BTCUSDT", snap("BTCUSDT", 99), max_items=5)
        assert store.history_length("BTCUSDT") == 5

    def test_hype_symbol_supported(self):
        store = LiveOrderBookStore()
        s = snap("HYPE")
        store.set_snapshot("HYPE", s)
        assert store.get_snapshot("HYPE") is s

    def test_store_default_max_history(self):
        store = LiveOrderBookStore()
        # Fill past default
        for i in range(DEFAULT_MAX_HISTORY + 10):
            store.add_history("BTCUSDT", snap("BTCUSDT", i))
        assert store.history_length("BTCUSDT") == DEFAULT_MAX_HISTORY

    def test_is_stale_large_max_age(self):
        store = LiveOrderBookStore()
        store.set_snapshot("BTCUSDT", snap())
        assert store.is_stale("BTCUSDT", max_age_seconds=86_400) is False
