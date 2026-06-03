"""
tests/test_setup_classifier.py
-------------------------------
LM48 — Setup classifier v1 tests.

Pure-function tests. No network, no Supabase. All timestamps passed
explicitly so output is fully deterministic.
"""

from __future__ import annotations

from services.setup_classifier import (
    DIR_LONG,
    DIR_NEUTRAL,
    DIR_SHORT,
    STATUS_CANDIDATE,
    STATUS_CONFIRMED,
    STATUS_INVALIDATED,
    STATUS_NO_TRADE,
    ST_BREAKOUT_PRESSURE,
    ST_LIQUIDITY_TRAP_RISK,
    ST_LONG_ABSORPTION,
    ST_NO_TRADE,
    ST_SHORT_REJECTION,
    VALID_DIRECTIONS,
    VALID_SETUP_TYPES,
    VALID_STATUSES,
    SetupClassifierOptions,
    classify_setups,
)


# ── Feature builder ──────────────────────────────────────────────────────────

def _feature(
    *,
    wall_id: str = "wall_test_0001",
    symbol: str = "BTCUSDT",
    exchange: str = "binance_spot",
    timeframe: str = "5m",
    side: str = "bid",
    price_low: float = 67000.0,
    price_high: float = 67010.0,
    price_mid: float | None = None,
    first_seen_ts: str = "2026-06-01T12:00:00+00:00",
    last_seen_ts: str = "2026-06-01T12:05:00+00:00",
    persistence_seconds: float = 300.0,
    touch_count: int = 0,
    defense_count: int = 0,
    break_count: int = 0,
    pull_count: int = 0,
    strengthen_count: int = 0,
    weaken_count: int = 0,
    current_strength: float = 75.0,
    max_strength: float | None = None,
    min_strength: float = 50.0,
    strength_delta_pct: float = 0.0,
    avg_distance_to_price_pct: float | None = 0.10,
    last_event_type: str = "wall_strengthened",
    confidence: float = 0.85,
    status: str = "active",
    reasons: list[str] | None = None,
    metadata: dict | None = None,
) -> dict:
    mid = price_mid if price_mid is not None else (price_low + price_high) / 2.0
    return {
        "wall_id":                   wall_id,
        "symbol":                    symbol,
        "exchange":                  exchange,
        "timeframe":                 timeframe,
        "side":                      side,
        "price_low":                 price_low,
        "price_high":                price_high,
        "price_mid":                 mid,
        "first_seen_ts":             first_seen_ts,
        "last_seen_ts":              last_seen_ts,
        "persistence_seconds":       persistence_seconds,
        "touch_count":               touch_count,
        "defense_count":             defense_count,
        "break_count":               break_count,
        "pull_count":                pull_count,
        "strengthen_count":          strengthen_count,
        "weaken_count":              weaken_count,
        "current_strength":          current_strength,
        "max_strength":              max_strength if max_strength is not None else current_strength,
        "min_strength":              min_strength,
        "strength_delta_pct":        strength_delta_pct,
        "avg_distance_to_price_pct": avg_distance_to_price_pct,
        "last_event_type":           last_event_type,
        "confidence":                confidence,
        "status":                    status,
        "reasons":                   reasons or [],
        "metadata":                  metadata or {},
    }


# ── long_absorption ─────────────────────────────────────────────────────────

class TestLongAbsorption:

    def test_strong_defended_bid_wall_emits_long_absorption(self):
        f = _feature(side="bid", status="defended",
                     current_strength=85, persistence_seconds=180,
                     defense_count=2, touch_count=1, confidence=0.9,
                     last_event_type="wall_defended")
        setups = classify_setups([f])
        # Exactly one setup type (defended bid → long_absorption confirmed).
        long_abs = [s for s in setups if s["setup_type"] == ST_LONG_ABSORPTION]
        assert len(long_abs) == 1
        s = long_abs[0]
        assert s["direction"] == DIR_LONG
        assert s["status"]    == STATUS_CONFIRMED
        assert s["primary_wall_id"] == "wall_test_0001"
        assert s["price_zone_mid"] == 67005.0
        assert 0.0 <= s["confidence"] <= 1.0
        assert 0.0 <= s["score"]      <= 100.0

    def test_active_bid_wall_emits_candidate(self):
        f = _feature(side="bid", status="active",
                     current_strength=75, persistence_seconds=120,
                     defense_count=0, touch_count=0, confidence=0.7,
                     last_event_type="wall_strengthened")
        setups = classify_setups([f])
        long_abs = [s for s in setups if s["setup_type"] == ST_LONG_ABSORPTION]
        assert long_abs and long_abs[0]["status"] == STATUS_CANDIDATE

    def test_weak_bid_wall_rejected(self):
        f = _feature(side="bid", status="active",
                     current_strength=40,  # below strong_wall_strength
                     persistence_seconds=120, confidence=0.7)
        setups = classify_setups([f])
        # Bid wall too weak → no long_absorption; falls back to no_trade.
        assert all(s["setup_type"] != ST_LONG_ABSORPTION for s in setups)
        assert any(s["setup_type"] == ST_NO_TRADE for s in setups)


# ── short_rejection ─────────────────────────────────────────────────────────

class TestShortRejection:

    def test_strong_defended_ask_wall_emits_short_rejection(self):
        f = _feature(side="ask", status="defended",
                     price_low=67500, price_high=67510,
                     current_strength=82, persistence_seconds=240,
                     defense_count=3, confidence=0.88,
                     last_event_type="wall_defended")
        setups = classify_setups([f])
        short_rej = [s for s in setups if s["setup_type"] == ST_SHORT_REJECTION]
        assert len(short_rej) == 1
        s = short_rej[0]
        assert s["direction"] == DIR_SHORT
        assert s["status"]    == STATUS_CONFIRMED

    def test_broken_ask_wall_does_not_emit_short_rejection(self):
        f = _feature(side="ask", status="broken",
                     current_strength=20, max_strength=80,
                     persistence_seconds=180, confidence=0.7,
                     last_event_type="wall_broken")
        setups = classify_setups([f])
        assert all(s["setup_type"] != ST_SHORT_REJECTION for s in setups)


# ── breakout_pressure ───────────────────────────────────────────────────────

class TestBreakoutPressure:

    def test_broken_bid_wall_signals_short_breakout(self):
        f = _feature(side="bid", status="broken",
                     current_strength=15, max_strength=85,
                     persistence_seconds=180, break_count=1,
                     defense_count=0, touch_count=0,
                     confidence=0.85, last_event_type="wall_broken")
        setups = classify_setups([f])
        bp = [s for s in setups if s["setup_type"] == ST_BREAKOUT_PRESSURE]
        assert len(bp) == 1
        assert bp[0]["direction"] == DIR_SHORT  # bid floor failed → bearish
        assert bp[0]["status"]    == STATUS_CONFIRMED

    def test_broken_ask_wall_signals_long_breakout(self):
        f = _feature(side="ask", status="broken",
                     current_strength=18, max_strength=78,
                     persistence_seconds=200, break_count=1,
                     confidence=0.82, last_event_type="wall_broken")
        setups = classify_setups([f])
        bp = [s for s in setups if s["setup_type"] == ST_BREAKOUT_PRESSURE]
        assert len(bp) == 1
        assert bp[0]["direction"] == DIR_LONG  # ask ceiling failed → bullish

    def test_pulled_wall_neutral_breakout(self):
        f = _feature(side="bid", status="pulled",
                     current_strength=0, max_strength=72,
                     persistence_seconds=150, pull_count=1,
                     confidence=0.75, last_event_type="wall_pulled")
        setups = classify_setups([f])
        bp = [s for s in setups if s["setup_type"] == ST_BREAKOUT_PRESSURE]
        assert len(bp) == 1
        assert bp[0]["direction"] == DIR_NEUTRAL
        assert bp[0]["status"]    == STATUS_CANDIDATE

    def test_low_max_strength_skips_breakout(self):
        f = _feature(side="bid", status="broken",
                     current_strength=10, max_strength=40,  # below threshold
                     persistence_seconds=200, break_count=1,
                     confidence=0.85, last_event_type="wall_broken")
        setups = classify_setups([f])
        assert all(s["setup_type"] != ST_BREAKOUT_PRESSURE for s in setups)


# ── liquidity_trap_risk ─────────────────────────────────────────────────────

class TestLiquidityTrapRisk:

    def test_failed_defense_trap(self):
        # Wall broken AFTER 2 defenses + 3 touches → failed-defense trap.
        f = _feature(side="bid", status="broken",
                     current_strength=15, max_strength=85,
                     persistence_seconds=400,
                     defense_count=2, touch_count=3, break_count=1,
                     confidence=0.9, last_event_type="wall_broken")
        setups = classify_setups([f])
        trap = [s for s in setups if s["setup_type"] == ST_LIQUIDITY_TRAP_RISK]
        assert len(trap) == 1
        assert trap[0]["direction"] == DIR_NEUTRAL
        assert trap[0]["metadata"]["trigger"] == "failed_defense"

    def test_conflict_trap_balanced_walls(self):
        bid = _feature(wall_id="wall_bid_a", side="bid", status="defended",
                       price_low=67000, price_high=67010,
                       current_strength=80, persistence_seconds=240,
                       defense_count=2, confidence=0.85,
                       last_event_type="wall_defended")
        ask = _feature(wall_id="wall_ask_a", side="ask", status="defended",
                       price_low=67200, price_high=67210,
                       current_strength=82, persistence_seconds=240,
                       defense_count=2, confidence=0.85,
                       last_event_type="wall_defended")
        setups = classify_setups([bid, ask])
        trap = [s for s in setups if s["setup_type"] == ST_LIQUIDITY_TRAP_RISK]
        assert len(trap) == 1
        assert trap[0]["direction"] == DIR_NEUTRAL
        assert trap[0]["metadata"]["trigger"] == "balanced_walls"
        # related_wall_ids must contain the other side's id.
        all_ids = {trap[0]["primary_wall_id"], *trap[0]["related_wall_ids"]}
        assert all_ids == {"wall_bid_a", "wall_ask_a"}

    def test_broken_with_no_history_does_not_trap(self):
        # Broken but zero touches/defenses → not a failed-defense trap.
        f = _feature(side="bid", status="broken",
                     current_strength=15, max_strength=80,
                     persistence_seconds=200,
                     defense_count=0, touch_count=0, break_count=1,
                     confidence=0.8, last_event_type="wall_broken")
        setups = classify_setups([f])
        assert all(s["setup_type"] != ST_LIQUIDITY_TRAP_RISK for s in setups)


# ── no_trade ─────────────────────────────────────────────────────────────────

class TestNoTrade:

    def test_weak_features_emit_no_trade(self):
        f = _feature(side="bid", status="weakening",
                     current_strength=25, persistence_seconds=10,
                     confidence=0.3, last_event_type="wall_weakened")
        setups = classify_setups([f])
        assert len(setups) == 1
        assert setups[0]["setup_type"] == ST_NO_TRADE
        assert setups[0]["status"]     == STATUS_NO_TRADE
        assert setups[0]["direction"]  == DIR_NEUTRAL
        assert setups[0]["score"]      == 0.0
        assert setups[0]["confidence"] == 0.0

    def test_empty_features_returns_empty_list(self):
        # No features at all → return []. We don't emit no_trade for empties.
        assert classify_setups([]) == []
        assert classify_setups(None) == []


# ── score / confidence ranges ────────────────────────────────────────────────

class TestScoreAndConfidenceRanges:

    def test_score_is_zero_to_hundred(self):
        f = _feature(side="bid", status="defended",
                     current_strength=95, persistence_seconds=600,
                     defense_count=5, confidence=0.98,
                     last_event_type="wall_defended")
        setups = classify_setups([f])
        for s in setups:
            assert 0.0 <= s["score"]      <= 100.0
            assert 0.0 <= s["confidence"] <= 1.0

    def test_strong_inputs_yield_high_score(self):
        f = _feature(side="bid", status="defended",
                     current_strength=95, persistence_seconds=600,
                     defense_count=5, confidence=0.98,
                     last_event_type="wall_defended")
        setups = classify_setups([f])
        long_abs = [s for s in setups if s["setup_type"] == ST_LONG_ABSORPTION]
        assert long_abs and long_abs[0]["score"] > 70.0


# ── deterministic output ─────────────────────────────────────────────────────

class TestDeterministic:

    def test_deterministic_setup_id_same_input(self):
        f = _feature(side="bid", status="defended",
                     current_strength=80, persistence_seconds=180,
                     defense_count=2, confidence=0.85,
                     last_event_type="wall_defended")
        a = classify_setups([f])
        b = classify_setups([f])
        assert a == b
        # All matching setups carry identical setup_ids.
        for sa, sb in zip(a, b):
            assert sa["setup_id"] == sb["setup_id"]

    def test_different_symbols_yield_different_setup_ids(self):
        a = _feature(symbol="BTCUSDT", side="bid", status="defended",
                     current_strength=80, persistence_seconds=180,
                     defense_count=2, confidence=0.85,
                     last_event_type="wall_defended")
        b = _feature(symbol="ETHUSDT", side="bid", status="defended",
                     current_strength=80, persistence_seconds=180,
                     defense_count=2, confidence=0.85,
                     last_event_type="wall_defended")
        setups = classify_setups([a, b])
        ids = {s["setup_id"] for s in setups}
        # Two markets × at least one setup each → at least two unique ids.
        assert len(ids) >= 2

    def test_output_sorted_by_market_then_type(self):
        # Two markets, one setup each.
        a = _feature(symbol="ETHUSDT", side="ask", status="defended",
                     current_strength=80, persistence_seconds=200,
                     defense_count=2, confidence=0.85,
                     last_event_type="wall_defended")
        b = _feature(symbol="BTCUSDT", side="bid", status="defended",
                     current_strength=80, persistence_seconds=200,
                     defense_count=2, confidence=0.85,
                     last_event_type="wall_defended")
        setups = classify_setups([a, b])
        keys = [(s["symbol"], s["timeframe"], s["setup_type"],
                 s["direction"], s["price_zone_mid"]) for s in setups]
        assert keys == sorted(keys)

    def test_setup_dict_has_all_required_fields(self):
        f = _feature(side="bid", status="defended",
                     current_strength=80, persistence_seconds=180,
                     defense_count=2, confidence=0.85,
                     last_event_type="wall_defended")
        setups = classify_setups([f])
        assert setups
        required = {
            "setup_id", "symbol", "exchange", "timeframe", "setup_ts",
            "setup_type", "direction", "score", "confidence",
            "price_zone_low", "price_zone_high", "price_zone_mid",
            "primary_wall_id", "related_wall_ids", "reasons", "risks",
            "status", "metadata",
        }
        for s in setups:
            assert required <= set(s.keys())
            assert s["setup_type"] in VALID_SETUP_TYPES
            assert s["direction"]  in VALID_DIRECTIONS
            assert s["status"]     in VALID_STATUSES
            assert isinstance(s["related_wall_ids"], list)
            assert isinstance(s["reasons"], list)
            assert isinstance(s["risks"], list)
            assert isinstance(s["metadata"], dict)


# ── missing / partial inputs ─────────────────────────────────────────────────

class TestMissingAndPartial:

    def test_none_returns_empty(self):
        assert classify_setups(None) == []

    def test_empty_list_returns_empty(self):
        assert classify_setups([]) == []

    def test_malformed_features_silently_skipped(self):
        # Mix of garbage entries + one valid weak feature → no_trade for the valid one.
        items = [
            None,
            "not a dict",                                            # type: ignore[list-item]
            {},                                                      # empty
            {"side": "bid"},                                         # missing prices
            {"side": "x", "price_low": 1, "price_high": 2,
             "price_mid": 1.5, "current_strength": 50,
             "max_strength": 50, "persistence_seconds": 100,
             "confidence": 0.6, "status": "active"},                 # bad side
            _feature(side="bid", status="weakening",
                     current_strength=20, persistence_seconds=10,
                     confidence=0.3),                                # valid but weak → no_trade
        ]
        setups = classify_setups(items)
        # Only the valid weak feature passed validation → no_trade is the sole output.
        assert len(setups) == 1
        assert setups[0]["setup_type"] == ST_NO_TRADE

    def test_all_invalid_returns_empty(self):
        # No valid features at all → return [].
        items = [None, "x", {}, {"side": "bid"}, {"side": "bogus"}]
        assert classify_setups(items) == []

    def test_iterable_input_accepted(self):
        def _gen():
            yield _feature(side="bid", status="defended",
                           current_strength=80, persistence_seconds=180,
                           defense_count=2, confidence=0.85,
                           last_event_type="wall_defended")
        setups = classify_setups(_gen())
        assert len(setups) >= 1


# ── threshold tuning ─────────────────────────────────────────────────────────

class TestOptions:

    def test_min_confidence_filters_features(self):
        # Bid wall otherwise strong, but confidence too low for default 0.4.
        f = _feature(side="bid", status="defended",
                     current_strength=80, persistence_seconds=180,
                     defense_count=2, confidence=0.30,
                     last_event_type="wall_defended")
        setups = classify_setups([f])
        # Default min_confidence (0.4) excludes it → no_trade.
        assert all(s["setup_type"] != ST_LONG_ABSORPTION for s in setups)
        assert any(s["setup_type"] == ST_NO_TRADE for s in setups)
        # Lower the threshold → setup qualifies.
        opts = SetupClassifierOptions(min_confidence=0.20)
        setups2 = classify_setups([f], options=opts)
        assert any(s["setup_type"] == ST_LONG_ABSORPTION for s in setups2)

    def test_min_persistence_filters_short_walls(self):
        f = _feature(side="bid", status="defended",
                     current_strength=80, persistence_seconds=20,  # below default 30
                     defense_count=2, confidence=0.85,
                     last_event_type="wall_defended")
        setups = classify_setups([f])
        assert all(s["setup_type"] != ST_LONG_ABSORPTION for s in setups)
