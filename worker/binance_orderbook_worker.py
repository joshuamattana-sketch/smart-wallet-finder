"""
worker/binance_orderbook_worker.py
------------------------------------
Binance Order Book Worker — bridges parsed WebSocket depth messages
into the LiveOrderBookStore and HeatmapHistoryStore.

This worker is the integration layer between:
    connectors/binance_ws.py    (parses raw messages)
    core/models.py              (snapshot dataclasses)
    services/live_orderbook_store.py
    services/heatmap_engine.py
    services/heatmap_history.py

Usage pattern (future, when live loop is enabled)::

    store     = LiveOrderBookStore()
    history   = HeatmapHistoryStore(max_frames=300)
    worker    = BinanceOrderBookWorker(["BTCUSDT", "ETHUSDT"],
                                       store=store,
                                       heatmap_history=history)

    # In a background asyncio task (NOT yet enabled):
    #   await worker.start()
    #
    # In the meantime, raw messages can be fed manually:
    worker.run_once_from_message(raw_message)

    latest = worker.get_latest_snapshot("BTCUSDT")
    frames = worker.get_heatmap_history("BTCUSDT", limit=50)

Rules:
- No Streamlit imports.
- No automatic startup — start() is a placeholder that raises RuntimeError.
- No real WebSocket connections from this module.
- No silent except pass — broken messages return False, never raise.
- Thread-safe via underlying store and history locks.
"""

from __future__ import annotations

import time
from typing import Optional

from connectors.binance_ws import WSMessageError, parse_depth_message
from core.models import OrderBookLevel, OrderBookSnapshot
from services.heatmap_engine import build_heatmap_from_orderbook
from services.heatmap_history import HeatmapHistoryStore
from services.live_orderbook_store import LiveOrderBookStore

# ── Constants ─────────────────────────────────────────────────────────────────

EXCHANGE_NAME      = "binance"
DEFAULT_HEATMAP_LEVELS = 20

# Reasons returned in stop()/diagnostic output
STOP_REASON_USER   = "stopped_by_user"
STOP_REASON_INIT   = "not_started"


# ── Worker class ──────────────────────────────────────────────────────────────

class BinanceOrderBookWorker:
    """
    Processes parsed Binance order book depth messages.

    Each incoming message is:
      1. Parsed via ``parse_depth_message`` (handles all four Binance shapes)
      2. Converted into an OrderBookSnapshot
      3. Stored in the LiveOrderBookStore (latest slot)
      4. Converted into HeatmapCells via build_heatmap_from_orderbook
      5. Stored as a HeatmapFrame in the HeatmapHistoryStore

    Broken messages, ACKs, and unknown types return False from
    ``handle_depth_message``/``run_once_from_message`` — they never raise.

    Attributes:
        symbols:           Uppercase tuple of symbols this worker was created for.
        store:             LiveOrderBookStore (created if not injected).
        heatmap_history:   HeatmapHistoryStore (created if not injected).
        heatmap_levels:    Depth levels passed to build_heatmap_from_orderbook.
        is_running:        True while the live loop is active. Stays False
                           in Streamlit mode (start() raises).
        stop_reason:       Last stop reason, e.g. "stopped_by_user".
    """

    def __init__(
        self,
        symbols: list[str],
        store: Optional[LiveOrderBookStore] = None,
        heatmap_history: Optional[HeatmapHistoryStore] = None,
        heatmap_levels: int = DEFAULT_HEATMAP_LEVELS,
    ) -> None:
        """
        Initialise the worker.

        Args:
            symbols:         List of trading symbols this worker covers,
                             e.g. ["BTCUSDT", "ETHUSDT"]. Used as a fallback
                             when a message arrives without an explicit symbol
                             (only used if the worker covers exactly one symbol).
            store:           Optional injected LiveOrderBookStore. Default: new.
            heatmap_history: Optional injected HeatmapHistoryStore. Default: new.
            heatmap_levels:  Levels to extract for the heatmap. Default 20.

        Raises:
            TypeError:  if symbols is not a list.
            ValueError: if symbols is empty or heatmap_levels < 1.
        """
        if not isinstance(symbols, list):
            raise TypeError(f"symbols must be a list, got {type(symbols).__name__}")
        if not symbols:
            raise ValueError("symbols list cannot be empty")
        if heatmap_levels < 1:
            raise ValueError(f"heatmap_levels must be >= 1, got {heatmap_levels}")

        # Normalise + dedupe symbols
        norm: list[str] = []
        seen: set[str]  = set()
        for sym in symbols:
            if not isinstance(sym, str):
                raise TypeError(
                    f"each symbol must be a str, got {type(sym).__name__}"
                )
            cleaned = sym.strip().upper()
            if not cleaned:
                raise ValueError("symbol cannot be empty after stripping")
            if cleaned not in seen:
                seen.add(cleaned)
                norm.append(cleaned)

        self.symbols:         tuple[str, ...]      = tuple(norm)
        self.store:           LiveOrderBookStore   = store or LiveOrderBookStore()
        self.heatmap_history: HeatmapHistoryStore  = heatmap_history or HeatmapHistoryStore()
        self.heatmap_levels:  int                  = heatmap_levels
        self.is_running:      bool                 = False
        self.stop_reason:     str                  = STOP_REASON_INIT
        self._messages_processed: int              = 0
        self._messages_failed:    int              = 0

    # ── Public message processing ─────────────────────────────────────────────

    def handle_depth_message(self, message) -> bool:
        """
        Process a single raw or parsed depth message.

        Args:
            message: str (JSON), bytes, or dict — any shape accepted by
                     parse_depth_message.

        Returns:
            True if the message was successfully processed and stored.
            False if the message was an ACK, an unknown type, malformed,
            or had no resolvable symbol. Never raises.

        Side effects on success:
            - Calls ``self.store.set_snapshot(symbol, snapshot)``
            - Calls ``self.heatmap_history.add_frame(symbol, cells)``
        """
        # ── Parse ─────────────────────────────────────────────────────────────
        try:
            parsed = parse_depth_message(message)
        except WSMessageError:
            self._messages_failed += 1
            return False
        except Exception:
            # Defensive: any unexpected parser error is a failed message,
            # not a worker crash.
            self._messages_failed += 1
            return False

        # ── Filter: only "depth" messages contain bids/asks ──────────────────
        if not isinstance(parsed, dict) or parsed.get("type") != "depth":
            return False

        bids_raw = parsed.get("bids") or []
        asks_raw = parsed.get("asks") or []
        if not bids_raw and not asks_raw:
            # Nothing to store
            return False

        # ── Resolve symbol ────────────────────────────────────────────────────
        symbol = self._resolve_symbol(parsed.get("symbol", ""))
        if not symbol:
            return False

        # ── Build OrderBookSnapshot ──────────────────────────────────────────
        try:
            snapshot = self._build_snapshot(symbol, bids_raw, asks_raw,
                                            parsed.get("event_time", 0))
        except Exception:
            self._messages_failed += 1
            return False

        # ── Write to store ───────────────────────────────────────────────────
        try:
            self.store.set_snapshot(symbol, snapshot)
        except Exception:
            self._messages_failed += 1
            return False

        # ── Build heatmap cells + record history frame ───────────────────────
        try:
            cells = build_heatmap_from_orderbook(
                snapshot, levels=self.heatmap_levels
            )
        except Exception:
            # Snapshot is already stored; just skip heatmap recording.
            self._messages_processed += 1
            return True

        try:
            self.heatmap_history.add_frame(
                symbol, cells, timestamp_ms=snapshot.timestamp_ms
            )
        except Exception:
            # Snapshot stored, heatmap build OK, only history write failed.
            self._messages_processed += 1
            return True

        self._messages_processed += 1
        return True

    def run_once_from_message(self, message) -> bool:
        """
        Convenience alias for handle_depth_message — provided for clarity in
        scripted / single-shot usage.
        """
        return self.handle_depth_message(message)

    # ── Inspection ────────────────────────────────────────────────────────────

    def get_latest_snapshot(self, symbol: str):
        """Return the most recent stored OrderBookSnapshot for symbol, or None."""
        if not isinstance(symbol, str) or not symbol.strip():
            return None
        return self.store.get_snapshot(symbol)

    def get_heatmap_history(self, symbol: str, limit: int = 100) -> list:
        """
        Return up to ``limit`` recent HeatmapFrame objects for symbol.

        Returns an empty list for unknown symbols or invalid input.
        Never raises.
        """
        if not isinstance(symbol, str) or not symbol.strip():
            return []
        if not isinstance(limit, int) or limit < 1:
            return []
        try:
            return self.heatmap_history.get_frames(symbol, limit=limit)
        except Exception:
            return []

    def stats(self) -> dict:
        """Return a dict of processing statistics — useful for diagnostics."""
        return {
            "messages_processed": self._messages_processed,
            "messages_failed":    self._messages_failed,
            "is_running":         self.is_running,
            "stop_reason":        self.stop_reason,
            "symbols":            list(self.symbols),
        }

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        """
        Async entry point for the live WebSocket loop.

        Currently NOT implemented — the live loop is disabled in Streamlit mode.
        Use ``run_once_from_message`` to feed messages manually instead.

        Raises:
            RuntimeError: Always, with a clear explanation.
        """
        raise RuntimeError(
            "Live websocket loop is not enabled in Streamlit mode yet."
        )

    def stop(self, reason: str = STOP_REASON_USER) -> None:
        """
        Stop the worker. Sets is_running=False and records the reason.

        Args:
            reason: Short human-readable reason. Default "stopped_by_user".
        """
        self.is_running  = False
        self.stop_reason = str(reason) if reason else STOP_REASON_USER

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _resolve_symbol(self, parsed_symbol: str) -> str:
        """
        Decide which symbol to attribute a message to.

        Priority:
            1. parsed_symbol if non-empty (most reliable)
            2. If worker covers exactly one symbol, use that
            3. Empty string → caller treats as "skip"
        """
        if isinstance(parsed_symbol, str) and parsed_symbol.strip():
            return parsed_symbol.strip().upper()
        if len(self.symbols) == 1:
            return self.symbols[0]
        return ""

    def _build_snapshot(
        self,
        symbol: str,
        bids_raw: list,
        asks_raw: list,
        event_time_ms: int,
    ) -> OrderBookSnapshot:
        """
        Convert parsed bid/ask dicts into an OrderBookSnapshot.

        Args:
            symbol:        Trading symbol.
            bids_raw:      List of {"price","size","notional"} dicts.
            asks_raw:      List of {"price","size","notional"} dicts.
            event_time_ms: Binance event time. Falls back to wall-clock now.

        Returns:
            OrderBookSnapshot with bids sorted descending, asks ascending,
            mid_price computed if both sides present.
        """
        bids = [
            OrderBookLevel(
                price=float(b.get("price", 0.0)),
                qty=float(b.get("size", 0.0)),
                usd_size=float(b.get("notional", 0.0)),
            )
            for b in bids_raw
            if isinstance(b, dict) and float(b.get("price", 0.0)) > 0
        ]
        asks = [
            OrderBookLevel(
                price=float(a.get("price", 0.0)),
                qty=float(a.get("size", 0.0)),
                usd_size=float(a.get("notional", 0.0)),
            )
            for a in asks_raw
            if isinstance(a, dict) and float(a.get("price", 0.0)) > 0
        ]

        # Binance partial book streams already sort correctly, but enforce it
        bids.sort(key=lambda lvl: lvl.price, reverse=True)
        asks.sort(key=lambda lvl: lvl.price)

        mid = 0.0
        if bids and asks:
            mid = (bids[0].price + asks[0].price) / 2.0

        ts = int(event_time_ms) if event_time_ms else int(time.time() * 1000)

        return OrderBookSnapshot(
            symbol=symbol,
            exchange=EXCHANGE_NAME,
            timestamp_ms=ts,
            bids=bids,
            asks=asks,
            mid_price=round(mid, 8),
        )


if __name__ == "__main__":
    # ── Self-tests (no real WebSocket) ────────────────────────────────────────
    from services.live_orderbook_store import LiveOrderBookStore
    from services.heatmap_history import HeatmapHistoryStore

    # Construction
    w = BinanceOrderBookWorker(["BTCUSDT", "ETHUSDT"])
    assert w.symbols == ("BTCUSDT", "ETHUSDT")
    assert isinstance(w.store, LiveOrderBookStore)
    assert isinstance(w.heatmap_history, HeatmapHistoryStore)
    assert not w.is_running
    assert w.stop_reason == STOP_REASON_INIT

    # Dedup + uppercase
    w2 = BinanceOrderBookWorker(["btcusdt", "BTCUSDT", "ethusdt"])
    assert w2.symbols == ("BTCUSDT", "ETHUSDT")

    # Validation
    try: BinanceOrderBookWorker("BTCUSDT"); assert False
    except TypeError: pass
    try: BinanceOrderBookWorker([]); assert False
    except ValueError: pass
    try: BinanceOrderBookWorker(["BTCUSDT"], heatmap_levels=0); assert False
    except ValueError: pass

    # Process a combined-stream message
    combined_msg = {
        "stream": "btcusdt@depth20@100ms",
        "data": {
            "lastUpdateId": 200,
            "bids": [["99.0","1.0"],["98.0","2.0"]],
            "asks": [["101.0","2.0"],["102.0","1.5"]],
        },
    }
    store   = LiveOrderBookStore()
    history = HeatmapHistoryStore(max_frames=50)
    w3 = BinanceOrderBookWorker(["BTCUSDT"], store=store, heatmap_history=history)
    ok = w3.run_once_from_message(combined_msg)
    assert ok is True

    snap = w3.get_latest_snapshot("BTCUSDT")
    assert snap is not None
    assert snap.symbol == "BTCUSDT"
    assert snap.exchange == "binance"
    assert len(snap.bids) == 2
    assert len(snap.asks) == 2

    frames = w3.get_heatmap_history("BTCUSDT")
    assert len(frames) == 1
    assert frames[0].symbol == "BTCUSDT"
    assert len(frames[0].cells) > 0

    # Stats
    s = w3.stats()
    assert s["messages_processed"] == 1
    assert s["messages_failed"] == 0

    # Broken message
    assert w3.run_once_from_message("not json {{{") is False
    assert w3.run_once_from_message({}) is False
    assert w3.run_once_from_message({"result": None, "id": 1}) is False  # ACK

    # Snapshot still intact after broken messages
    assert w3.get_latest_snapshot("BTCUSDT") is not None

    # Unknown symbol — diff event with unknown symbol field
    unknown_msg = {
        "e": "depthUpdate", "E": 1_716_200_000_000,
        "s": "XYZUSDT", "U": 1, "u": 2,
        "b": [["99.0","1.0"]], "a": [["101.0","1.0"]],
    }
    assert w3.run_once_from_message(unknown_msg) is True
    assert w3.get_latest_snapshot("XYZUSDT") is not None

    # Partial book with no symbol — single-symbol worker can resolve
    partial_msg = {
        "lastUpdateId": 99, "bids": [["99.0","1.0"]], "asks": [["101.0","1.0"]],
    }
    assert w3.run_once_from_message(partial_msg) is True

    # Partial book with no symbol on a multi-symbol worker — ambiguous, skip
    multi_w = BinanceOrderBookWorker(["BTCUSDT", "ETHUSDT"])
    assert multi_w.run_once_from_message(partial_msg) is False

    # stop()
    w3.stop()
    assert w3.is_running is False
    assert w3.stop_reason == STOP_REASON_USER
    w3.stop(reason="custom")
    assert w3.stop_reason == "custom"

    # start() raises
    import asyncio
    async def _try_start():
        await w3.start()
    try:
        asyncio.run(_try_start())
        assert False
    except RuntimeError as e:
        assert "not enabled" in str(e).lower()

    # get_latest_snapshot / get_heatmap_history with bad input
    assert w3.get_latest_snapshot("") is None
    assert w3.get_latest_snapshot(None) is None  # type: ignore
    assert w3.get_heatmap_history("") == []
    assert w3.get_heatmap_history("BTCUSDT", limit=0) == []

    print("worker/binance_orderbook_worker.py — all assertions passed.")
