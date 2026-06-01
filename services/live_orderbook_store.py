"""
services/live_orderbook_store.py
----------------------------------
Thread-safe in-memory store for live OrderBookSnapshot objects.

Designed to be the shared data layer between a future WebSocket worker
(writer) and the Pro Terminal UI (reader). Currently operates as a
pure in-memory cache — no persistence, no network calls.

Usage pattern (future):
    # WebSocket worker thread:
    store = LiveOrderBookStore()
    store.set_snapshot("BTCUSDT", snapshot)
    store.add_history("BTCUSDT", snapshot)

    # UI render thread:
    snap = store.get_snapshot("BTCUSDT")
    if store.is_stale("BTCUSDT", max_age_seconds=5):
        st.warning("Data may be stale")
    history = store.get_history("BTCUSDT", limit=50)

Rules:
- No Streamlit imports.
- No network calls.
- No WebSocket code yet.
- No external dependencies beyond stdlib.
- No silent except pass.
- Thread-safe via threading.Lock per symbol.
"""

from __future__ import annotations

import time
import threading
from collections import deque
from typing import Optional

# ── Supported symbols ─────────────────────────────────────────────────────────

SUPPORTED_SYMBOLS: tuple[str, ...] = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "HYPE")

# Default limits
DEFAULT_MAX_HISTORY: int = 300
DEFAULT_MAX_AGE_SECONDS: int = 10
DEFAULT_HISTORY_LIMIT: int = 100

# ── Stored entry ──────────────────────────────────────────────────────────────

class SnapshotEntry:
    """
    Wraps an OrderBookSnapshot with a wall-clock receipt timestamp.

    Attributes:
        snapshot:     The OrderBookSnapshot object.
        received_at:  Unix timestamp (seconds) when store.set_snapshot()
                      or store.add_history() was called. Used for stale checks.
    """

    __slots__ = ("snapshot", "received_at")

    def __init__(self, snapshot: object, received_at: Optional[float] = None) -> None:
        self.snapshot    = snapshot
        self.received_at = received_at if received_at is not None else time.time()


# ── Store ─────────────────────────────────────────────────────────────────────

class LiveOrderBookStore:
    """
    Thread-safe in-memory store for live OrderBookSnapshot objects.

    Each symbol gets:
    - A single "current" snapshot slot (latest only).
    - A history deque (bounded, FIFO).
    - A dedicated RLock for thread safety.

    The store accepts any symbol string — not limited to SUPPORTED_SYMBOLS —
    but initialises those symbols eagerly on construction.

    Thread safety:
        All public methods acquire the per-symbol lock.
        clear(symbol=None) acquires all locks to prevent partial state.
    """

    def __init__(self, max_history: int = DEFAULT_MAX_HISTORY) -> None:
        """
        Initialise the store.

        Args:
            max_history: Default maximum history entries per symbol.
                         Can be overridden per call to add_history().
        """
        if max_history < 1:
            raise ValueError(f"max_history must be >= 1, got {max_history}")

        self._max_history = max_history

        # {symbol: SnapshotEntry | None}
        self._latest:  dict[str, Optional[SnapshotEntry]] = {}
        # {symbol: deque[SnapshotEntry]}
        self._history: dict[str, deque[SnapshotEntry]]   = {}
        # {symbol: RLock}
        self._locks:   dict[str, threading.RLock]        = {}

        # Pre-register supported symbols
        for sym in SUPPORTED_SYMBOLS:
            self._ensure_symbol(sym)

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _ensure_symbol(self, symbol: str) -> None:
        """Create data structures for symbol if not already present."""
        if symbol not in self._locks:
            self._locks[symbol]   = threading.RLock()
            self._latest[symbol]  = None
            self._history[symbol] = deque(maxlen=self._max_history)

    def _lock(self, symbol: str) -> threading.RLock:
        self._ensure_symbol(symbol)
        return self._locks[symbol]

    # ── Public API ────────────────────────────────────────────────────────────

    def set_snapshot(self, symbol: str, snapshot: object) -> None:
        """
        Store the most recent snapshot for a symbol, replacing any previous value.

        Args:
            symbol:   Trading symbol, e.g. "BTCUSDT".
            snapshot: OrderBookSnapshot (or any snapshot-like object in tests).

        Raises:
            TypeError:  if symbol is not a string.
            ValueError: if symbol is empty after stripping.
        """
        symbol = _validate_symbol(symbol)
        with self._lock(symbol):
            self._latest[symbol] = SnapshotEntry(snapshot)

    def get_snapshot(self, symbol: str) -> Optional[object]:
        """
        Return the most recent snapshot for a symbol, or None if not set.

        Args:
            symbol: Trading symbol.

        Returns:
            The OrderBookSnapshot, or None.

        Raises:
            TypeError:  if symbol is not a string.
            ValueError: if symbol is empty.
        """
        symbol = _validate_symbol(symbol)
        with self._lock(symbol):
            entry = self._latest.get(symbol)
            return entry.snapshot if entry is not None else None

    def add_history(
        self,
        symbol: str,
        snapshot: object,
        max_items: int = DEFAULT_MAX_HISTORY,
    ) -> None:
        """
        Append a snapshot to the symbol's history deque.

        The deque is bounded: once it reaches max_items, the oldest
        entry is automatically discarded (FIFO). If max_items differs
        from the current deque maxlen a new deque is created preserving
        as many recent entries as possible.

        Args:
            symbol:    Trading symbol.
            snapshot:  OrderBookSnapshot to record.
            max_items: Maximum number of historical entries. Default 300.

        Raises:
            TypeError:  if symbol is not a string.
            ValueError: if symbol is empty or max_items < 1.
        """
        symbol = _validate_symbol(symbol)
        if max_items < 1:
            raise ValueError(f"max_items must be >= 1, got {max_items}")

        with self._lock(symbol):
            dq = self._history[symbol]
            if dq.maxlen != max_items:
                # Resize while keeping as many recent entries as possible
                self._history[symbol] = deque(dq, maxlen=max_items)
                dq = self._history[symbol]
            dq.append(SnapshotEntry(snapshot))

    def get_history(
        self,
        symbol: str,
        limit: int = DEFAULT_HISTORY_LIMIT,
    ) -> list[object]:
        """
        Return up to limit recent snapshots for a symbol, newest last.

        Args:
            symbol: Trading symbol.
            limit:  Maximum number of snapshots to return. Default 100.

        Returns:
            List of snapshots (not SnapshotEntry wrappers), newest last.
            Empty list if no history or symbol unknown.

        Raises:
            TypeError:  if symbol is not a string.
            ValueError: if symbol is empty or limit < 1.
        """
        symbol = _validate_symbol(symbol)
        if limit < 1:
            raise ValueError(f"limit must be >= 1, got {limit}")

        with self._lock(symbol):
            dq = self._history.get(symbol)
            if not dq:
                return []
            entries = list(dq)[-limit:]
            return [e.snapshot for e in entries]

    def clear(self, symbol: Optional[str] = None) -> None:
        """
        Clear stored data.

        Args:
            symbol: If given, clear only that symbol's latest + history.
                    If None, clear ALL symbols.

        Raises:
            TypeError:  if symbol is not a string (when provided).
            ValueError: if symbol is empty (when provided).
        """
        if symbol is not None:
            symbol = _validate_symbol(symbol)
            with self._lock(symbol):
                self._latest[symbol]  = None
                self._history[symbol] = deque(maxlen=self._max_history)
        else:
            # Acquire all locks in deterministic order to prevent deadlock
            for sym in sorted(self._locks):
                self._locks[sym].acquire()
            try:
                for sym in self._locks:
                    self._latest[sym]  = None
                    self._history[sym] = deque(maxlen=self._max_history)
            finally:
                for sym in sorted(self._locks):
                    self._locks[sym].release()

    def is_stale(
        self,
        symbol: str,
        max_age_seconds: float = DEFAULT_MAX_AGE_SECONDS,
    ) -> bool:
        """
        Return True if the latest snapshot is older than max_age_seconds,
        or if no snapshot has been stored for the symbol.

        Args:
            symbol:          Trading symbol.
            max_age_seconds: Age threshold in seconds. Default 10.

        Returns:
            True if data is missing or stale, False if fresh.

        Raises:
            TypeError:  if symbol is not a string.
            ValueError: if symbol is empty or max_age_seconds <= 0.
        """
        symbol = _validate_symbol(symbol)
        if max_age_seconds <= 0:
            raise ValueError(
                f"max_age_seconds must be > 0, got {max_age_seconds}"
            )

        with self._lock(symbol):
            entry = self._latest.get(symbol)
            if entry is None:
                return True
            age = time.time() - entry.received_at
            return age > max_age_seconds

    def snapshot_age(self, symbol: str) -> Optional[float]:
        """
        Return the age in seconds of the latest snapshot, or None if absent.

        Args:
            symbol: Trading symbol.

        Returns:
            Float age in seconds, or None.
        """
        symbol = _validate_symbol(symbol)
        with self._lock(symbol):
            entry = self._latest.get(symbol)
            if entry is None:
                return None
            return time.time() - entry.received_at

    def history_length(self, symbol: str) -> int:
        """Return the number of snapshots in the history deque for symbol."""
        symbol = _validate_symbol(symbol)
        with self._lock(symbol):
            return len(self._history.get(symbol, []))

    def symbols(self) -> list[str]:
        """Return all currently registered symbols."""
        return list(self._locks.keys())

    def __repr__(self) -> str:
        counts = {s: self.history_length(s) for s in self.symbols()}
        return f"LiveOrderBookStore(symbols={counts})"


# ── Validation helper ─────────────────────────────────────────────────────────

def _validate_symbol(symbol: object) -> str:
    """
    Validate and normalise a symbol string.

    Returns:
        Stripped uppercase symbol string.

    Raises:
        TypeError:  if symbol is not a str.
        ValueError: if symbol is empty after stripping.
    """
    if not isinstance(symbol, str):
        raise TypeError(f"symbol must be a str, got {type(symbol).__name__}")
    stripped = symbol.strip().upper()
    if not stripped:
        raise ValueError("symbol cannot be empty")
    return stripped


if __name__ == "__main__":
    # ── Self-tests ────────────────────────────────────────────────────────────
    import sys
    sys.path.insert(0, ".")
    from core.models import OrderBookLevel, OrderBookSnapshot

    def make_snap(sym: str) -> OrderBookSnapshot:
        return OrderBookSnapshot(
            symbol=sym, exchange="binance", timestamp_ms=int(time.time() * 1000),
        )

    store = LiveOrderBookStore(max_history=10)

    # set / get
    snap = make_snap("BTCUSDT")
    store.set_snapshot("BTCUSDT", snap)
    assert store.get_snapshot("BTCUSDT") is snap
    assert store.get_snapshot("ETHUSDT") is None  # not set yet

    # history
    for i in range(15):
        store.add_history("BTCUSDT", make_snap("BTCUSDT"), max_items=10)
    assert store.history_length("BTCUSDT") == 10  # capped at max_items

    # get_history limit
    h = store.get_history("BTCUSDT", limit=5)
    assert len(h) == 5

    # stale check — freshly set should not be stale
    store.set_snapshot("SOLUSDT", make_snap("SOLUSDT"))
    assert not store.is_stale("SOLUSDT", max_age_seconds=10)
    assert store.is_stale("ETHUSDT", max_age_seconds=10)  # never set

    # clear single symbol
    store.clear("BTCUSDT")
    assert store.get_snapshot("BTCUSDT") is None
    assert store.history_length("BTCUSDT") == 0
    assert store.get_snapshot("SOLUSDT") is not None  # untouched

    # clear all
    store.set_snapshot("BTCUSDT", make_snap("BTCUSDT"))
    store.clear()
    for sym in store.symbols():
        assert store.get_snapshot(sym) is None
        assert store.history_length(sym) == 0

    # missing / unknown symbol returns safely
    assert store.get_snapshot("XYZUSDT") is None
    assert store.get_history("XYZUSDT") == []
    assert store.is_stale("XYZUSDT") is True
    assert store.snapshot_age("XYZUSDT") is None

    # normalisation
    store.set_snapshot("btcusdt", make_snap("BTCUSDT"))
    assert store.get_snapshot("BTCUSDT") is not None  # same key

    # validation errors
    try:
        store.set_snapshot(None, snap)  # type: ignore
        assert False
    except TypeError:
        pass
    try:
        store.set_snapshot("", snap)
        assert False
    except ValueError:
        pass
    try:
        store.add_history("BTCUSDT", snap, max_items=0)
        assert False
    except ValueError:
        pass
    try:
        store.is_stale("BTCUSDT", max_age_seconds=0)
        assert False
    except ValueError:
        pass
    try:
        LiveOrderBookStore(max_history=0)
        assert False
    except ValueError:
        pass

    # thread safety smoke test
    import threading
    errors = []
    def worker():
        try:
            for _ in range(50):
                store.set_snapshot("BTCUSDT", make_snap("BTCUSDT"))
                store.add_history("BTCUSDT", make_snap("BTCUSDT"))
                store.get_snapshot("BTCUSDT")
                store.get_history("BTCUSDT", limit=10)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(6)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert not errors, f"Thread errors: {errors}"

    print("services/live_orderbook_store.py — all assertions passed.")
