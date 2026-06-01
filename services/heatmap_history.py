"""
services/heatmap_history.py
-----------------------------
Heatmap History Store for the Pro Trading Terminal.

Accumulates snapshots of HeatmapCells over time to enable:
  - Time-series liquidity wall visualisation (Bookmap-style)
  - Persistent wall detection (walls that hold across multiple frames)
  - Future live WebSocket heatmap replay

Architecture:
    HeatmapFrame          — single timestamped snapshot of cells
    HeatmapHistoryStore   — in-memory store of frames per symbol

    External flow (future):
        WebSocket worker  →  heatmap_engine.build_heatmap_from_orderbook()
                          →  store.add_frame(symbol, cells)
        UI reader         →  store.get_frames(symbol)
                          →  store.detect_persistent_walls(symbol)

Rules:
- No Streamlit imports.
- No network calls.
- No WebSocket code.
- No external dependencies beyond stdlib.
- No silent except pass.
- Thread-safe frame storage via per-symbol threading.Lock.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

from services.heatmap_engine import SIDE_ASK, SIDE_BID, HeatmapCell

# ── Constants ─────────────────────────────────────────────────────────────────

DEFAULT_MAX_FRAMES:  int = 300
DEFAULT_FRAME_LIMIT: int = 100
DEFAULT_MIN_INTENSITY: int = 70
DEFAULT_MIN_FRAMES:    int = 3


# ── HeatmapFrame ─────────────────────────────────────────────────────────────

@dataclass
class HeatmapFrame:
    """
    A single timestamped snapshot of HeatmapCells for one symbol.

    Attributes:
        symbol:       Trading symbol, e.g. "BTCUSDT".
        timestamp_ms: Unix timestamp in milliseconds when this frame was captured.
        cells:        Ordered list of HeatmapCell objects (bids then asks).
    """
    symbol:       str
    timestamp_ms: int
    cells:        list[HeatmapCell] = field(default_factory=list)

    @property
    def bid_cells(self) -> list[HeatmapCell]:
        return [c for c in self.cells if c.is_bid]

    @property
    def ask_cells(self) -> list[HeatmapCell]:
        return [c for c in self.cells if c.is_ask]

    @property
    def hot_cells(self) -> list[HeatmapCell]:
        return [c for c in self.cells if c.is_hot]

    @property
    def wall_cells(self) -> list[HeatmapCell]:
        return [c for c in self.cells if c.is_wall]

    @property
    def is_empty(self) -> bool:
        return len(self.cells) == 0


# ── HeatmapHistoryStore ───────────────────────────────────────────────────────

class HeatmapHistoryStore:
    """
    Thread-safe in-memory store for HeatmapFrame sequences.

    Each symbol has a bounded deque of HeatmapFrames. The store is designed
    to be written by a background worker (WebSocket or REST poller) and
    read by the Pro Terminal UI.

    Key capabilities:
      add_frame()           — append a new frame for a symbol
      get_frames()          — retrieve recent frames
      get_latest()          — get the most recent frame
      clear()               — clear one or all symbols
      build_intensity_matrix() — 2-D matrix [frame][price_level] for visualisation
      detect_persistent_walls() — find walls appearing in >= N consecutive frames
    """

    def __init__(self, max_frames: int = DEFAULT_MAX_FRAMES) -> None:
        """
        Initialise the store.

        Args:
            max_frames: Default maximum frames per symbol. Can be overridden
                        per add_frame() call. Must be >= 1.

        Raises:
            ValueError: if max_frames < 1.
        """
        if max_frames < 1:
            raise ValueError(f"max_frames must be >= 1, got {max_frames}")

        self._max_frames = max_frames
        # {symbol: deque[HeatmapFrame]}
        self._frames: dict[str, deque[HeatmapFrame]] = {}
        # {symbol: threading.Lock}
        self._locks:  dict[str, threading.Lock]      = {}

    # ── Internal ──────────────────────────────────────────────────────────────

    def _ensure(self, symbol: str) -> None:
        if symbol not in self._locks:
            self._locks[symbol]  = threading.Lock()
            # Start unbounded; add_frame enforces the cap on every call
            self._frames[symbol] = deque()

    def _lock(self, symbol: str) -> threading.Lock:
        self._ensure(symbol)
        return self._locks[symbol]

    # ── Public API ────────────────────────────────────────────────────────────

    def add_frame(
        self,
        symbol: str,
        cells: list[HeatmapCell],
        timestamp_ms: Optional[int] = None,
        max_frames: Optional[int] = None,
    ) -> HeatmapFrame:
        """
        Append a new HeatmapFrame for a symbol.

        Args:
            symbol:       Trading symbol, e.g. "BTCUSDT".
            cells:        List of HeatmapCell objects for this snapshot.
            timestamp_ms: Unix ms timestamp. Defaults to now.
            max_frames:   Maximum frames to retain per symbol.
                          Defaults to the value passed to __init__ (default 300).

        Returns:
            The HeatmapFrame that was stored.

        Raises:
            TypeError:  if symbol is not a str or cells is not a list.
            ValueError: if symbol is empty or max_frames < 1.
        """
        symbol = _validate_symbol(symbol)
        if not isinstance(cells, list):
            raise TypeError(f"cells must be a list, got {type(cells).__name__}")
        # Resolve effective cap: per-call override → constructor default
        effective_max = max_frames if max_frames is not None else self._max_frames
        if effective_max < 1:
            raise ValueError(f"max_frames must be >= 1, got {effective_max}")
        max_frames = effective_max

        ts = timestamp_ms if timestamp_ms is not None else int(time.time() * 1000)
        frame = HeatmapFrame(symbol=symbol, timestamp_ms=ts, cells=list(cells))

        with self._lock(symbol):
            dq = self._frames[symbol]
            dq.append(frame)
            # Trim oldest frames until we are within max_frames
            while len(dq) > max_frames:
                dq.popleft()

        return frame

    def get_frames(
        self,
        symbol: str,
        limit: int = DEFAULT_FRAME_LIMIT,
    ) -> list[HeatmapFrame]:
        """
        Return up to limit recent frames for a symbol, oldest first.

        Args:
            symbol: Trading symbol.
            limit:  Maximum number of frames. Default 100.

        Returns:
            List of HeatmapFrame, oldest first. Empty list if none stored.

        Raises:
            TypeError:  if symbol is not a str.
            ValueError: if symbol is empty or limit < 1.
        """
        symbol = _validate_symbol(symbol)
        if limit < 1:
            raise ValueError(f"limit must be >= 1, got {limit}")

        with self._lock(symbol):
            dq = self._frames.get(symbol)
            if not dq:
                return []
            return list(dq)[-limit:]

    def get_latest(self, symbol: str) -> Optional[HeatmapFrame]:
        """
        Return the most recently added frame for a symbol, or None.

        Args:
            symbol: Trading symbol.

        Returns:
            HeatmapFrame or None.

        Raises:
            TypeError:  if symbol is not a str.
            ValueError: if symbol is empty.
        """
        symbol = _validate_symbol(symbol)
        with self._lock(symbol):
            dq = self._frames.get(symbol)
            if not dq:
                return None
            return dq[-1]

    def clear(self, symbol: Optional[str] = None) -> None:
        """
        Clear frames for one symbol, or all symbols.

        Args:
            symbol: If given, clear only that symbol. If None, clear all.

        Raises:
            TypeError:  if symbol is not a str (when provided).
            ValueError: if symbol is empty (when provided).
        """
        if symbol is not None:
            symbol = _validate_symbol(symbol)
            with self._lock(symbol):
                self._frames[symbol] = deque()
        else:
            for sym in sorted(self._locks):
                self._locks[sym].acquire()
            try:
                for sym in self._locks:
                    self._frames[sym] = deque()
            finally:
                for sym in sorted(self._locks):
                    self._locks[sym].release()

    def frame_count(self, symbol: str) -> int:
        """Return the number of frames stored for a symbol."""
        symbol = _validate_symbol(symbol)
        with self._lock(symbol):
            return len(self._frames.get(symbol, []))

    def symbols(self) -> list[str]:
        """Return all symbols with registered frame deques."""
        return list(self._locks.keys())

    # ── Analytics ─────────────────────────────────────────────────────────────

    def build_intensity_matrix(
        self,
        symbol: str,
        limit: int = DEFAULT_FRAME_LIMIT,
    ) -> dict:
        """
        Build a 2-D intensity matrix for visualisation.

        Aggregates frames into a matrix keyed by price level, with
        intensity values across time. Useful for rendering a Bookmap-style
        heat band where the X axis is time and Y axis is price.

        Returns:
            dict with:
            - ``prices``     (list[float]): sorted unique price levels
            - ``timestamps`` (list[int]):   frame timestamps ms, oldest first
            - ``matrix``     (dict[float, list[int]]): price → [intensity per frame]
              Missing entries are filled with 0.
            - ``sides``      (dict[float, str]): price → "bid" or "ask"

        Args:
            symbol: Trading symbol.
            limit:  Maximum frames to include. Default 100.

        Returns empty structure if no frames exist.

        Raises:
            TypeError:  if symbol is not a str.
            ValueError: if symbol is empty or limit < 1.
        """
        frames = self.get_frames(symbol, limit=limit)
        if not frames:
            return {"prices": [], "timestamps": [], "matrix": {}, "sides": {}}

        # Collect all unique prices and the side for each
        price_side: dict[float, str] = {}
        for frame in frames:
            for cell in frame.cells:
                if cell.price not in price_side:
                    price_side[cell.price] = cell.side

        prices     = sorted(price_side.keys(), reverse=True)  # bids descend, asks descend
        timestamps = [f.timestamp_ms for f in frames]

        # Build frame-indexed lookup: {timestamp_ms: {price: intensity}}
        frame_maps: list[dict[float, int]] = []
        for frame in frames:
            fm: dict[float, int] = {c.price: c.intensity for c in frame.cells}
            frame_maps.append(fm)

        # Matrix: price → [intensity in each frame], 0 if level absent in that frame
        matrix: dict[float, list[int]] = {
            p: [fm.get(p, 0) for fm in frame_maps]
            for p in prices
        }

        return {
            "prices":     prices,
            "timestamps": timestamps,
            "matrix":     matrix,
            "sides":      price_side,
        }

    def detect_persistent_walls(
        self,
        symbol: str,
        min_intensity: int = DEFAULT_MIN_INTENSITY,
        min_frames: int = DEFAULT_MIN_FRAMES,
        limit: int = DEFAULT_FRAME_LIMIT,
    ) -> list[dict]:
        """
        Find price levels with consistently high intensity across multiple frames.

        A "persistent wall" is a level whose intensity stayed >= min_intensity
        in at least min_frames of the most recent frames. These represent genuine
        structural liquidity zones rather than fleeting large orders.

        Args:
            symbol:        Trading symbol.
            min_intensity: Minimum intensity to qualify in a frame. Default 70.
            min_frames:    Minimum qualifying frames. Default 3.
            limit:         How many recent frames to examine. Default 100.

        Returns:
            List of dicts sorted by persistence_count descending, each with:
            - ``price``             (float)
            - ``side``              (str): "bid" or "ask"
            - ``persistence_count`` (int): frames where intensity >= threshold
            - ``avg_intensity``     (float): mean intensity across qualifying frames
            - ``max_intensity``     (int): peak intensity seen
            - ``is_wall``           (bool): True if avg_intensity >= 85

        Returns [] if no frames exist or none qualify.

        Raises:
            TypeError:  if symbol is not a str.
            ValueError: if symbol is empty, min_intensity outside [0,100],
                        min_frames < 1, or limit < 1.
        """
        symbol = _validate_symbol(symbol)
        if not (0 <= min_intensity <= 100):
            raise ValueError(
                f"min_intensity must be in [0, 100], got {min_intensity}"
            )
        if min_frames < 1:
            raise ValueError(f"min_frames must be >= 1, got {min_frames}")
        if limit < 1:
            raise ValueError(f"limit must be >= 1, got {limit}")

        frames = self.get_frames(symbol, limit=limit)
        if not frames:
            return []

        # Gather price metadata
        price_side: dict[float, str] = {}
        for frame in frames:
            for cell in frame.cells:
                if cell.price not in price_side:
                    price_side[cell.price] = cell.side

        result: list[dict] = []
        for price, side in price_side.items():
            qualifying_intensities: list[int] = []
            for frame in frames:
                fm = {c.price: c.intensity for c in frame.cells}
                inten = fm.get(price, 0)
                if inten >= min_intensity:
                    qualifying_intensities.append(inten)

            count = len(qualifying_intensities)
            if count < min_frames:
                continue

            avg_inten = sum(qualifying_intensities) / count
            max_inten = max(qualifying_intensities)

            result.append({
                "price":             price,
                "side":              side,
                "persistence_count": count,
                "avg_intensity":     round(avg_inten, 2),
                "max_intensity":     max_inten,
                "is_wall":           avg_inten >= 85,
            })

        result.sort(key=lambda d: d["persistence_count"], reverse=True)
        return result


# ── Validation ────────────────────────────────────────────────────────────────

def _validate_symbol(symbol: object) -> str:
    if not isinstance(symbol, str):
        raise TypeError(f"symbol must be a str, got {type(symbol).__name__}")
    stripped = symbol.strip().upper()
    if not stripped:
        raise ValueError("symbol cannot be empty")
    return stripped


if __name__ == "__main__":
    from services.heatmap_engine import calculate_intensity, demo_heatmap_cells

    store = HeatmapHistoryStore(max_frames=10)
    demo  = demo_heatmap_cells()

    # add_frame
    f1 = store.add_frame("BTCUSDT", demo, timestamp_ms=1_000)
    assert isinstance(f1, HeatmapFrame)
    assert f1.symbol == "BTCUSDT"
    assert f1.timestamp_ms == 1_000
    assert len(f1.cells) == 40

    # get_frames
    frames = store.get_frames("BTCUSDT")
    assert len(frames) == 1
    assert frames[0] is f1

    # get_latest
    f2 = store.add_frame("BTCUSDT", demo, timestamp_ms=2_000)
    assert store.get_latest("BTCUSDT") is f2
    assert store.get_latest("ETHUSDT") is None

    # max_frames cap
    for i in range(15):
        store.add_frame("BTCUSDT", demo, max_frames=10)
    assert store.frame_count("BTCUSDT") == 10

    # frame properties
    assert f1.bid_cells == [c for c in demo if c.is_bid]
    assert f1.ask_cells == [c for c in demo if c.is_ask]
    assert any(c.is_hot for c in f1.hot_cells)
    assert not f1.is_empty

    # empty frame
    ef = HeatmapFrame("X", 0, [])
    assert ef.is_empty

    # clear single
    store.add_frame("ETHUSDT", demo)
    store.clear("ETHUSDT")
    assert store.frame_count("ETHUSDT") == 0
    assert store.frame_count("BTCUSDT") > 0

    # clear all
    store.clear()
    for sym in store.symbols():
        assert store.frame_count(sym) == 0

    # build_intensity_matrix
    store.add_frame("BTCUSDT", demo, timestamp_ms=1_000)
    store.add_frame("BTCUSDT", demo, timestamp_ms=2_000)
    mx = store.build_intensity_matrix("BTCUSDT", limit=10)
    assert isinstance(mx["prices"], list)
    assert isinstance(mx["timestamps"], list)
    assert isinstance(mx["matrix"], dict)
    assert len(mx["timestamps"]) == 2
    assert len(mx["prices"]) == 40  # 40 unique prices from demo
    # Every price in matrix has a list of len 2 (one per frame)
    for p, row in mx["matrix"].items():
        assert len(row) == 2
    assert "sides" in mx

    # detect_persistent_walls
    # Add enough frames with wall-level intensities
    wall_cells = [c for c in demo if c.intensity >= 70]
    assert wall_cells
    for _ in range(5):
        store.add_frame("BTCUSDT", demo)
    walls = store.detect_persistent_walls("BTCUSDT", min_intensity=70, min_frames=3)
    assert isinstance(walls, list)
    assert all("price" in w and "persistence_count" in w for w in walls)
    if walls:
        counts = [w["persistence_count"] for w in walls]
        assert counts == sorted(counts, reverse=True)

    # Missing symbol no crash
    assert store.get_frames("XYZUSDT") == []
    assert store.get_latest("XYZUSDT") is None
    assert store.frame_count("XYZUSDT") == 0
    assert store.build_intensity_matrix("XYZUSDT") == {
        "prices":[], "timestamps":[], "matrix":{}, "sides":{}
    }
    assert store.detect_persistent_walls("XYZUSDT") == []

    # Validation
    try: store.add_frame(None, demo); assert False  # type: ignore
    except TypeError: pass
    try: store.add_frame("", demo); assert False
    except ValueError: pass
    try: store.add_frame("BTC", "not a list"); assert False  # type: ignore
    except TypeError: pass
    try: store.add_frame("BTC", demo, max_frames=0); assert False
    except ValueError: pass
    try: HeatmapHistoryStore(max_frames=0); assert False
    except ValueError: pass
    try: store.detect_persistent_walls("BTC", min_intensity=150); assert False
    except ValueError: pass
    try: store.detect_persistent_walls("BTC", min_frames=0); assert False
    except ValueError: pass

    print("services/heatmap_history.py — all assertions passed.")
