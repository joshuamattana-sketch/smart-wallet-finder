"""
tests/test_signal_builder.py
-----------------------------
LM49 — Signal object builder v1 tests.

Pure-function tests. No network, no Supabase. All timestamps passed
explicitly so output is fully deterministic.
"""

from __future__ import annotations

from services.signal_builder import (
    DIR_LONG,
    DIR_NEUTRAL,
    DIR_SHORT,
    HINT_AVOID_TRADE,
    HINT_MONITOR_ONLY,
    HINT_WAIT_FOR_CONFIRMATION,
    HINT_WAIT_FOR_RETEST,
    LEVEL_NO_TRADE,
    LEVEL_SETUP,
    LEVEL_STRONG_SETUP,
    LEVEL_WATCH,
    STATUS_ACTIVE,
    STATUS_INVALIDATED,
    STATUS_NO_TRADE,
    STATUS_WAITING,
    VALID_ACTION_HINTS,
    VALID_DIRECTIONS,
    VALID_SIGNAL_LEVELS,
    VALID_STATUSES,
    SignalBuilderOptions,
    build_signals,
)


# ── Setup builder ────────────────────────────────────────────────────────────

def _setup(
    *,
    setup_id: str = "setup_test_0001",
    symbol: str = "BTCUSDT",
    exchange: str = "binance_spot",
    timeframe: str = "5m",
    setup_ts: str = "2026-06-01T12:00:00+00:00",
    setup_type: str = "long_absorption",
    direction: str = "long",
    score: float = 80.0,
    confidence: float = 0.85,
    price_zone_low: float = 67000.0,
    price_zone_high: float = 67010.0,
    price_zone_mid: float | None = None,
    primary_wall_id: str = "wall_test_0001",
    related_wall_ids: list[str] | None = None,
    reasons: list[str] | None = None,
    risks: list[str] | None = None,
    status: str = "confirmed",
    metadata: dict | None = None,
) -> dict:
    mid = price_zone_mid if price_zone_mid is not None else (price_zone_low + price_zone_high) / 2.0
    return {
        "setup_id":         setup_id,
        "symbol":           symbol,
        "exchange":         exchange,
        "timeframe":        timeframe,
        "setup_ts":         setup_ts,
        "setup_type":       setup_type,
        "direction":        direction,
        "score":            score,
        "confidence":       confidence,
        "price_zone_low":   price_zone_low,
        "price_zone_high":  price_zone_high,
        "price_zone_mid":   mid,
        "primary_wall_id":  primary_wall_id,
        "related_wall_ids": related_wall_ids or [],
        "reasons":          reasons or [],
        "risks":            risks or [],
        "status":           status,
        "metadata":         metadata or {},
    }


# ── long signal ─────────────────────────────────────────────────────────────

class TestLongSignal:

    def test_long_absorption_high_score_builds_strong_setup(self):
        s = _setup(setup_type="long_absorption", direction="long",
                   score=82.0, confidence=0.88,
                   price_zone_low=67000, price_zone_high=67010)
        out = build_signals([s])
        assert len(out) == 1
        sig = out[0]
        assert sig["direction"]    == DIR_LONG
        assert sig["signal_level"] == LEVEL_STRONG_SETUP
        assert sig["status"]       == STATUS_ACTIVE
        assert sig["action_hint"]  == HINT_WAIT_FOR_RETEST
        assert sig["entry_zone_low"]  == 67000.0
        assert sig["entry_zone_high"] == 67010.0
        assert sig["entry_zone_mid"]  == 67005.0
        assert sig["invalidation_price"] is not None
        assert sig["invalidation_price"] < sig["entry_zone_low"]
        assert len(sig["targets"]) == 2
        # Targets above entry mid (long direction).
        assert sig["targets"][0] > sig["entry_zone_mid"]
        assert sig["targets"][1] > sig["targets"][0]

    def test_breakout_pressure_long_uses_confirmation_hint(self):
        s = _setup(setup_type="breakout_pressure", direction="long",
                   score=80.0, confidence=0.85, status="confirmed",
                   price_zone_low=67500, price_zone_high=67510)
        out = build_signals([s])
        sig = out[0]
        assert sig["signal_level"] == LEVEL_STRONG_SETUP
        assert sig["action_hint"]  == HINT_WAIT_FOR_CONFIRMATION
        assert sig["targets"][0]   > sig["entry_zone_mid"]


# ── short signal ────────────────────────────────────────────────────────────

class TestShortSignal:

    def test_short_rejection_high_score_builds_strong_setup(self):
        s = _setup(setup_type="short_rejection", direction="short",
                   score=78.0, confidence=0.86,
                   price_zone_low=67500, price_zone_high=67510)
        out = build_signals([s])
        sig = out[0]
        assert sig["direction"]    == DIR_SHORT
        assert sig["signal_level"] == LEVEL_STRONG_SETUP
        assert sig["status"]       == STATUS_ACTIVE
        assert sig["action_hint"]  == HINT_WAIT_FOR_RETEST
        # Short: invalidation ABOVE high, targets BELOW mid.
        assert sig["invalidation_price"] > sig["entry_zone_high"]
        assert sig["targets"][0] < sig["entry_zone_mid"]
        assert sig["targets"][1] < sig["targets"][0]


# ── no_trade signal ─────────────────────────────────────────────────────────

class TestNoTradeSignal:

    def test_no_trade_setup_becomes_no_trade_signal(self):
        s = _setup(setup_type="no_trade", direction="neutral",
                   score=0.0, confidence=0.0, status="no_trade",
                   price_zone_low=0.0, price_zone_high=0.0)
        out = build_signals([s])
        sig = out[0]
        assert sig["signal_level"]      == LEVEL_NO_TRADE
        assert sig["status"]            == STATUS_NO_TRADE
        assert sig["direction"]         == DIR_NEUTRAL
        assert sig["action_hint"]       == HINT_AVOID_TRADE
        assert sig["invalidation_price"] is None
        assert sig["targets"]           == []

    def test_low_score_directional_setup_becomes_no_trade(self):
        # Direction long but score below watch_score → level no_trade.
        s = _setup(setup_type="long_absorption", direction="long",
                   score=20.0, confidence=0.80,
                   price_zone_low=67000, price_zone_high=67010)
        out = build_signals([s])
        sig = out[0]
        assert sig["signal_level"] == LEVEL_NO_TRADE
        assert sig["status"]       == STATUS_NO_TRADE
        assert sig["direction"]    == DIR_NEUTRAL  # downgraded
        assert sig["invalidation_price"] is None
        assert sig["targets"] == []

    def test_low_confidence_demotes_to_no_trade(self):
        s = _setup(setup_type="long_absorption", direction="long",
                   score=85.0, confidence=0.20,  # below default 0.40
                   price_zone_low=67000, price_zone_high=67010)
        out = build_signals([s])
        sig = out[0]
        assert sig["signal_level"] == LEVEL_NO_TRADE


# ── signal_level thresholds ─────────────────────────────────────────────────

class TestSignalLevelThresholds:

    def test_watch_threshold(self):
        # Score 35 ∈ [watch_score=30, setup_score=50) → watch.
        s = _setup(setup_type="long_absorption", direction="long",
                   score=35.0, confidence=0.80)
        out = build_signals([s])
        sig = out[0]
        assert sig["signal_level"] == LEVEL_WATCH
        assert sig["status"]       == STATUS_WAITING
        assert sig["action_hint"]  == HINT_MONITOR_ONLY
        # Watch level still computes geometry for context.
        assert sig["invalidation_price"] is not None

    def test_setup_threshold(self):
        # Score 55 ∈ [setup_score=50, strong_setup_score=70) → setup.
        s = _setup(setup_type="long_absorption", direction="long",
                   score=55.0, confidence=0.80)
        out = build_signals([s])
        sig = out[0]
        assert sig["signal_level"] == LEVEL_SETUP
        assert sig["status"]       == STATUS_ACTIVE
        # Default setup-level hint is wait_for_confirmation.
        assert sig["action_hint"] == HINT_WAIT_FOR_CONFIRMATION

    def test_strong_setup_threshold(self):
        s = _setup(setup_type="long_absorption", direction="long",
                   score=72.0, confidence=0.80)
        out = build_signals([s])
        sig = out[0]
        assert sig["signal_level"] == LEVEL_STRONG_SETUP
        assert sig["status"]       == STATUS_ACTIVE

    def test_custom_thresholds_change_level(self):
        s = _setup(setup_type="long_absorption", direction="long",
                   score=45.0, confidence=0.80)
        # With tighter setup threshold, 45 falls in watch band.
        out = build_signals([s], options=SignalBuilderOptions(
            watch_score=10.0, setup_score=60.0, strong_setup_score=90.0,
        ))
        assert out[0]["signal_level"] == LEVEL_WATCH


# ── invalidation calculation ────────────────────────────────────────────────

class TestInvalidation:

    def test_long_invalidation_below_zone_low(self):
        s = _setup(setup_type="long_absorption", direction="long",
                   score=80.0, confidence=0.85,
                   price_zone_low=67000, price_zone_high=67010)
        out = build_signals([s])
        sig = out[0]
        # invalidation = 67000 - 67005 * 0.20% = 67000 - 134.01 = 66865.99
        assert sig["invalidation_price"] < 67000.0
        # Buffer is small relative to zone (default 0.20%).
        assert sig["invalidation_price"] > 66800.0

    def test_short_invalidation_above_zone_high(self):
        s = _setup(setup_type="short_rejection", direction="short",
                   score=80.0, confidence=0.85,
                   price_zone_low=67500, price_zone_high=67510)
        out = build_signals([s])
        sig = out[0]
        assert sig["invalidation_price"] > 67510.0

    def test_custom_invalidation_buffer(self):
        s = _setup(setup_type="long_absorption", direction="long",
                   score=80.0, confidence=0.85,
                   price_zone_low=67000, price_zone_high=67010)
        # 1.0% of 67005 ≈ 670.05 → invalidation should land near 66330.
        out = build_signals([s], options=SignalBuilderOptions(
            invalidation_buffer_pct=1.0,
        ))
        sig = out[0]
        assert sig["invalidation_price"] < 66400.0
        assert sig["invalidation_price"] > 66300.0


# ── target calculation ──────────────────────────────────────────────────────

class TestTargets:

    def test_target_r_multiples_for_long(self):
        s = _setup(setup_type="long_absorption", direction="long",
                   score=80.0, confidence=0.85,
                   price_zone_low=67000, price_zone_high=67010)
        out = build_signals([s], options=SignalBuilderOptions(
            target_r_multiple_1=2.0, target_r_multiple_2=4.0,
        ))
        sig = out[0]
        assert sig["invalidation_price"] is not None
        risk = sig["entry_zone_mid"] - sig["invalidation_price"]
        # target_1 ≈ mid + 2R; target_2 ≈ mid + 4R.
        assert abs(sig["targets"][0] - (sig["entry_zone_mid"] + 2 * risk)) < 0.01
        assert abs(sig["targets"][1] - (sig["entry_zone_mid"] + 4 * risk)) < 0.01

    def test_target_r_multiples_for_short(self):
        s = _setup(setup_type="short_rejection", direction="short",
                   score=80.0, confidence=0.85,
                   price_zone_low=67500, price_zone_high=67510)
        out = build_signals([s], options=SignalBuilderOptions(
            target_r_multiple_1=1.5, target_r_multiple_2=3.0,
        ))
        sig = out[0]
        risk = sig["invalidation_price"] - sig["entry_zone_mid"]
        assert abs(sig["targets"][0] - (sig["entry_zone_mid"] - 1.5 * risk)) < 0.01
        assert abs(sig["targets"][1] - (sig["entry_zone_mid"] - 3.0 * risk)) < 0.01

    def test_neutral_signal_has_no_targets(self):
        s = _setup(setup_type="liquidity_trap_risk", direction="neutral",
                   score=60.0, confidence=0.80,
                   price_zone_low=67000, price_zone_high=67010)
        out = build_signals([s])
        sig = out[0]
        assert sig["invalidation_price"] is None
        assert sig["targets"]            == []
        assert sig["action_hint"]        == HINT_MONITOR_ONLY


# ── deterministic signal_id ─────────────────────────────────────────────────

class TestSignalId:

    def test_same_input_same_signal_id(self):
        s = _setup(setup_type="long_absorption", direction="long",
                   score=80.0, confidence=0.85)
        a = build_signals([s])
        b = build_signals([s])
        assert a == b
        assert a[0]["signal_id"] == b[0]["signal_id"]

    def test_signal_id_changes_with_level(self):
        # Same setup_id, different scores → different signal_level → diff id.
        weak   = _setup(setup_id="setup_x", score=20.0, confidence=0.80)
        strong = _setup(setup_id="setup_x", score=85.0, confidence=0.80)
        a = build_signals([weak])
        b = build_signals([strong])
        assert a[0]["signal_id"] != b[0]["signal_id"]

    def test_signal_id_format(self):
        out = build_signals([_setup(score=80.0, confidence=0.85)])
        sid = out[0]["signal_id"]
        assert sid.startswith("sig_")
        assert len(sid) == len("sig_") + 12


# ── invalidated setup status ────────────────────────────────────────────────

class TestInvalidatedSetup:

    def test_setup_invalidated_passes_through(self):
        s = _setup(setup_type="long_absorption", direction="long",
                   score=80.0, confidence=0.85, status="invalidated",
                   price_zone_low=67000, price_zone_high=67010)
        out = build_signals([s])
        sig = out[0]
        assert sig["status"] == STATUS_INVALIDATED
        # Level still computed from score so caller can see what was invalidated.
        assert sig["signal_level"] == LEVEL_STRONG_SETUP


# ── missing / partial inputs ────────────────────────────────────────────────

class TestMissingAndPartial:

    def test_none_returns_empty(self):
        assert build_signals(None) == []

    def test_empty_list_returns_empty(self):
        assert build_signals([]) == []

    def test_malformed_setups_silently_skipped(self):
        items = [
            None,
            "not a dict",                                               # type: ignore[list-item]
            {},                                                         # empty
            {"setup_id": "x"},                                          # missing fields
            {"setup_id": "x", "setup_type": "bogus", "direction": "long",
             "score": 50, "confidence": 0.6,
             "price_zone_low": 1, "price_zone_high": 2, "price_zone_mid": 1.5},
            _setup(setup_type="long_absorption", direction="long",
                   score=80.0, confidence=0.85),                        # valid
        ]
        out = build_signals(items)
        # Only the valid setup remains.
        assert len(out) == 1
        assert out[0]["signal_level"] == LEVEL_STRONG_SETUP

    def test_all_malformed_returns_empty(self):
        assert build_signals([None, "x", {}, {"setup_id": "x"}]) == []

    def test_iterable_input_accepted(self):
        def _gen():
            yield _setup(setup_type="long_absorption", direction="long",
                         score=80.0, confidence=0.85)
        out = build_signals(_gen())
        assert len(out) == 1


# ── deterministic output ────────────────────────────────────────────────────

class TestDeterministicOutput:

    def test_same_input_identical_lists(self):
        setups = [
            _setup(setup_id="a", symbol="BTCUSDT", setup_type="long_absorption",
                   direction="long", score=80, confidence=0.85,
                   price_zone_low=67000, price_zone_high=67010),
            _setup(setup_id="b", symbol="BTCUSDT", setup_type="short_rejection",
                   direction="short", score=75, confidence=0.85,
                   price_zone_low=67500, price_zone_high=67510),
        ]
        a = build_signals(setups)
        b = build_signals(setups)
        assert a == b

    def test_output_sorted_by_market_then_type(self):
        setups = [
            _setup(setup_id="a", symbol="ETHUSDT",
                   setup_type="short_rejection", direction="short",
                   score=80, confidence=0.85,
                   price_zone_low=3500, price_zone_high=3510),
            _setup(setup_id="b", symbol="BTCUSDT",
                   setup_type="long_absorption", direction="long",
                   score=80, confidence=0.85,
                   price_zone_low=67000, price_zone_high=67010),
            _setup(setup_id="c", symbol="BTCUSDT",
                   setup_type="short_rejection", direction="short",
                   score=80, confidence=0.85,
                   price_zone_low=67500, price_zone_high=67510),
        ]
        out = build_signals(setups)
        keys = [(s["symbol"], s["timeframe"], s["setup_type"],
                 s["direction"], s["entry_zone_mid"]) for s in out]
        assert keys == sorted(keys)

    def test_signal_dict_has_all_required_fields(self):
        out = build_signals([_setup(score=80.0, confidence=0.85)])
        assert out
        required = {
            "signal_id", "symbol", "exchange", "timeframe", "signal_ts",
            "setup_id", "setup_type", "direction", "signal_level",
            "score", "confidence",
            "entry_zone_low", "entry_zone_high", "entry_zone_mid",
            "invalidation_price", "targets",
            "reasons", "risks", "action_hint", "status", "metadata",
        }
        for sig in out:
            assert required <= set(sig.keys())
            assert sig["direction"]    in VALID_DIRECTIONS
            assert sig["signal_level"] in VALID_SIGNAL_LEVELS
            assert sig["status"]       in VALID_STATUSES
            assert sig["action_hint"]  in VALID_ACTION_HINTS
            assert isinstance(sig["targets"], list)
            assert isinstance(sig["reasons"], list)
            assert isinstance(sig["risks"], list)
            assert isinstance(sig["metadata"], dict)

    def test_score_and_confidence_clamped(self):
        # Out-of-range inputs are clamped to valid ranges.
        s = _setup(setup_type="long_absorption", direction="long",
                   score=200.0, confidence=2.5)
        out = build_signals([s])
        sig = out[0]
        assert 0.0 <= sig["score"]      <= 100.0
        assert 0.0 <= sig["confidence"] <= 1.0
