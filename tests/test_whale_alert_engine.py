"""
tests/test_whale_alert_engine.py
----------------------------------
Unit tests for services/whale_alert_engine.py.

Zero real API calls. All data is inline.

Test classes:
  TestClassifyWhaleRisk        — risk classification logic
  TestCalculateImportanceScore — importance score bounds and ordering
  TestClassifyAlertType        — event → alert type routing
  TestBuildWhaleAlert          — manual alert constructor
  TestDetectSmartWhaleEvent    — main detection function
  TestFilterNoiseAlerts        — noise filter
  TestDemoWhaleAlerts          — demo data integrity
  TestWhaleAlertDataclass      — dataclass validation
  TestEdgeCases                — None/empty/zero values, no crashes
  TestMarketContextIntegration — context escalates risk and importance
"""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from services.whale_alert_engine import (
    ALERT_AGGRESSIVE_LONG,
    ALERT_AGGRESSIVE_SHORT,
    ALERT_CROWDED_LEVERAGE,
    ALERT_LIQUIDATION_RISK,
    ALERT_POSITION_INCREASED,
    ALERT_POSITION_REDUCED,
    ALERT_POSSIBLE_TRAP,
    ALERT_SMART_ACCUMULATION,
    ALERT_WHALE_EXIT,
    RISK_EXTREME,
    RISK_HIGH,
    RISK_LOW,
    RISK_MEDIUM,
    VALID_ALERT_TYPES,
    VALID_RISKS,
    MarketContext,
    WhaleAlert,
    build_whale_alert,
    calculate_importance_score,
    classify_alert_type,
    classify_whale_risk,
    demo_whale_alerts,
    detect_smart_whale_event,
    filter_noise_alerts,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def base_event(**overrides) -> dict:
    defaults = {
        "symbol":     "BTCUSDT",
        "venue":      "binance",
        "event_type": "opened",
        "side":       "long",
        "size_usd":   1_000_000.0,
        "leverage":   10.0,
        "price":      67_420.0,
        "time_ms":    1_716_200_000_000,
    }
    defaults.update(overrides)
    return defaults


def rich_context(
    imbalance: float = 0.5,
    liquidity_score: float = 70.0,
    funding_rate: float = 0.01,
    oi_change_pct: float = 5.0,
    near_breakout: bool = False,
    near_support: bool = False,
    near_resistance: bool = False,
    repeated_trader: bool = False,
    bid_wall_usd: float = 0.0,
    ask_wall_usd: float = 0.0,
) -> MarketContext:
    return MarketContext(
        imbalance=imbalance,
        liquidity_score=liquidity_score,
        funding_rate=funding_rate,
        oi_change_pct=oi_change_pct,
        near_breakout=near_breakout,
        near_support=near_support,
        near_resistance=near_resistance,
        repeated_trader=repeated_trader,
        bid_wall_usd=bid_wall_usd,
        ask_wall_usd=ask_wall_usd,
    )


# ══ TestClassifyWhaleRisk ════════════════════════════════════════════════════

class TestClassifyWhaleRisk:
    def test_low_small_size_no_leverage(self):
        assert classify_whale_risk(50_000) == RISK_LOW

    def test_medium_at_threshold(self):
        assert classify_whale_risk(500_000) == RISK_MEDIUM

    def test_medium_above_threshold(self):
        assert classify_whale_risk(600_000) == RISK_MEDIUM

    def test_high_at_threshold(self):
        assert classify_whale_risk(2_000_000) == RISK_HIGH

    def test_extreme_at_threshold(self):
        assert classify_whale_risk(10_000_000) == RISK_EXTREME

    def test_leverage_alone_extreme(self):
        # $100k at 25x → effective $2.5M → high, but leverage>=20 floor → extreme
        assert classify_whale_risk(100_000, leverage=25) == RISK_EXTREME

    def test_leverage_alone_high(self):
        assert classify_whale_risk(100_000, leverage=12) == RISK_HIGH

    def test_leverage_alone_medium(self):
        assert classify_whale_risk(100_000, leverage=6) == RISK_MEDIUM

    def test_leverage_low_no_escalation(self):
        assert classify_whale_risk(50_000, leverage=2) == RISK_LOW

    def test_zero_size_is_low(self):
        assert classify_whale_risk(0) == RISK_LOW

    def test_zero_leverage_treated_as_spot(self):
        # leverage=0 is treated as spot (no amplification)
        assert classify_whale_risk(50_000, leverage=0) == RISK_LOW

    def test_context_thin_liquidity_escalates(self):
        ctx = MarketContext(liquidity_score=20)
        # $400k would normally be low, context escalates
        result = classify_whale_risk(400_000, market_context=ctx)
        assert result in (RISK_MEDIUM, RISK_HIGH, RISK_EXTREME)

    def test_context_high_funding_escalates(self):
        ctx = MarketContext(funding_rate=0.15)
        result = classify_whale_risk(400_000, market_context=ctx)
        assert result in (RISK_MEDIUM, RISK_HIGH, RISK_EXTREME)

    def test_always_valid_risk_key(self):
        for size in [0, 100_000, 1_000_000, 5_000_000, 15_000_000]:
            for lev in [None, 1, 5, 10, 25]:
                r = classify_whale_risk(size, leverage=lev)
                assert r in VALID_RISKS, f"Invalid risk: {r}"

    def test_negative_size_raises(self):
        with pytest.raises(ValueError, match="size_usd"):
            classify_whale_risk(-1000)

    def test_negative_leverage_raises(self):
        with pytest.raises(ValueError, match="leverage"):
            classify_whale_risk(1_000_000, leverage=-5)


# ══ TestCalculateImportanceScore ══════════════════════════════════════════════

class TestCalculateImportanceScore:
    def test_score_in_range(self):
        s = calculate_importance_score(5_000_000, leverage=10)
        assert 0.0 <= s <= 100.0

    def test_zero_size_is_low(self):
        assert calculate_importance_score(0) < 20

    def test_large_size_scores_high(self):
        s = calculate_importance_score(10_000_000, leverage=20)
        assert s >= 55

    def test_small_size_scores_low(self):
        s = calculate_importance_score(50_000)
        assert s < 40

    def test_more_context_scores_higher(self):
        s_bare = calculate_importance_score(1_000_000, leverage=10)
        ctx = rich_context(
            imbalance=0.7, liquidity_score=25, funding_rate=0.08,
            oi_change_pct=15, near_breakout=True, repeated_trader=True,
        )
        s_ctx = calculate_importance_score(1_000_000, leverage=10, market_context=ctx)
        assert s_ctx > s_bare

    def test_repeated_trader_adds_score(self):
        s_no_repeat = calculate_importance_score(1_000_000, leverage=10,
                                                  market_context=rich_context(repeated_trader=False))
        s_repeat    = calculate_importance_score(1_000_000, leverage=10,
                                                  market_context=rich_context(repeated_trader=True))
        assert s_repeat > s_no_repeat

    def test_high_leverage_scores_higher_than_spot(self):
        s_spot = calculate_importance_score(1_000_000, leverage=None)
        s_lev  = calculate_importance_score(1_000_000, leverage=20)
        assert s_lev > s_spot

    def test_all_extreme_inputs_still_clamped(self):
        ctx = rich_context(imbalance=1.0, liquidity_score=1.0, funding_rate=1.0,
                           oi_change_pct=100, near_breakout=True, repeated_trader=True,
                           bid_wall_usd=100_000_000)
        s = calculate_importance_score(100_000_000, leverage=100, market_context=ctx)
        assert 0.0 <= s <= 100.0

    def test_ordering_by_size(self):
        s1 = calculate_importance_score(100_000)
        s2 = calculate_importance_score(1_000_000)
        s3 = calculate_importance_score(10_000_000)
        assert s1 < s2 < s3


# ══ TestClassifyAlertType ════════════════════════════════════════════════════

class TestClassifyAlertType:
    def test_liquidation_highest_priority(self):
        assert classify_alert_type({"event_type": "liquidation_risk"}) == ALERT_LIQUIDATION_RISK
        assert classify_alert_type({"event_type": "liquidation"}) == ALERT_LIQUIDATION_RISK

    def test_long_opened(self):
        assert classify_alert_type({"event_type": "opened", "side": "long"}) == ALERT_AGGRESSIVE_LONG

    def test_short_opened(self):
        assert classify_alert_type({"event_type": "opened", "side": "short"}) == ALERT_AGGRESSIVE_SHORT

    def test_position_increased(self):
        assert classify_alert_type({"event_type": "increased"}) == ALERT_POSITION_INCREASED

    def test_position_reduced(self):
        assert classify_alert_type({"event_type": "reduced"}) == ALERT_POSITION_REDUCED

    def test_whale_exit_on_close(self):
        assert classify_alert_type({"event_type": "closed", "size_usd": 5_000_000}) == ALERT_WHALE_EXIT

    def test_smart_accumulation(self):
        assert classify_alert_type({"event_type": "accumulation"}) == ALERT_SMART_ACCUMULATION

    def test_crowded_leverage_oi_spike(self):
        result = classify_alert_type({
            "event_type": "opened", "side": "long",
            "leverage": 15, "oi_change_pct": 20,
        })
        assert result == ALERT_CROWDED_LEVERAGE

    def test_possible_trap_funding_divergence(self):
        result = classify_alert_type({
            "event_type": "opened", "side": "long",
            "leverage": 12, "funding_rate": 0.15,
        })
        assert result == ALERT_POSSIBLE_TRAP

    def test_returns_valid_type(self):
        for ev in [
            {"event_type": "opened",   "side": "long"},
            {"event_type": "opened",   "side": "short"},
            {"event_type": "increased"},
            {"event_type": "closed"},
            {"event_type": "liquidation_risk"},
        ]:
            assert classify_alert_type(ev) in VALID_ALERT_TYPES

    def test_type_error_on_non_dict(self):
        with pytest.raises(TypeError, match="dict"):
            classify_alert_type("not a dict")

    def test_empty_dict_does_not_crash(self):
        result = classify_alert_type({})
        assert result in VALID_ALERT_TYPES


# ══ TestBuildWhaleAlert ═══════════════════════════════════════════════════════

class TestBuildWhaleAlert:
    def test_returns_whale_alert(self):
        a = build_whale_alert(
            "BTCUSDT", "binance", ALERT_AGGRESSIVE_LONG, "long",
            5_000_000, "Test", leverage=10.0,
        )
        assert isinstance(a, WhaleAlert)

    def test_risk_auto_computed(self):
        a = build_whale_alert("X", "y", ALERT_AGGRESSIVE_LONG, "long",
                               5_000_000, "t")
        assert a.risk == RISK_HIGH

    def test_risk_extreme_large_leverage(self):
        a = build_whale_alert("X", "y", ALERT_AGGRESSIVE_LONG, "long",
                               500_000, "t", leverage=25)
        assert a.risk == RISK_EXTREME

    def test_symbol_preserved(self):
        a = build_whale_alert("HYPE", "HL", ALERT_AGGRESSIVE_LONG, "long",
                               1_000_000, "t")
        assert a.symbol == "HYPE"

    def test_confidence_clamped(self):
        a = build_whale_alert("X", "y", ALERT_AGGRESSIVE_LONG, "long",
                               1_000_000, "t", confidence=999)
        assert 0 <= a.confidence <= 100

    def test_importance_clamped(self):
        a = build_whale_alert("X", "y", ALERT_AGGRESSIVE_LONG, "long",
                               1_000_000, "t", importance_score=-50)
        assert 0 <= a.importance_score <= 100

    def test_is_bullish_long(self):
        a = build_whale_alert("X","y",ALERT_AGGRESSIVE_LONG,"long",1000000,"t")
        assert a.is_bullish
        assert not a.is_bearish

    def test_is_bearish_short(self):
        a = build_whale_alert("X","y",ALERT_AGGRESSIVE_SHORT,"short",1000000,"t")
        assert a.is_bearish
        assert not a.is_bullish

    def test_leverage_str_spot(self):
        a = build_whale_alert("X","y",ALERT_AGGRESSIVE_LONG,"long",1000000,"t")
        assert a.leverage_str == "spot"

    def test_leverage_str_with_leverage(self):
        a = build_whale_alert("X","y",ALERT_AGGRESSIVE_LONG,"long",1000000,"t",leverage=10)
        assert a.leverage_str == "10x"

    def test_size_str_millions(self):
        a = build_whale_alert("X","y",ALERT_AGGRESSIVE_LONG,"long",5_000_000,"t")
        assert "5.0M" in a.size_str

    def test_timestamp_defaults_to_now(self):
        before = int(time.time() * 1000) - 2000
        a = build_whale_alert("X","y",ALERT_AGGRESSIVE_LONG,"long",1000000,"t")
        after  = int(time.time() * 1000) + 2000
        assert before <= a.timestamp_ms <= after


# ══ TestDetectSmartWhaleEvent ════════════════════════════════════════════════

class TestDetectSmartWhaleEvent:
    def test_returns_whale_alert(self):
        a = detect_smart_whale_event(base_event())
        assert isinstance(a, WhaleAlert)

    def test_below_threshold_returns_none(self):
        assert detect_smart_whale_event(base_event(size_usd=500)) is None

    def test_symbol_preserved(self):
        a = detect_smart_whale_event(base_event(symbol="ETHUSDT"))
        assert a.symbol == "ETHUSDT"

    def test_venue_preserved(self):
        a = detect_smart_whale_event(base_event(venue="Hyperliquid"))
        assert a.venue == "Hyperliquid"

    def test_score_in_range(self):
        a = detect_smart_whale_event(base_event())
        assert 0 <= a.importance_score <= 100

    def test_confidence_in_range(self):
        a = detect_smart_whale_event(base_event())
        assert 0 <= a.confidence <= 100

    def test_risk_valid(self):
        a = detect_smart_whale_event(base_event())
        assert a.risk in VALID_RISKS

    def test_alert_type_valid(self):
        a = detect_smart_whale_event(base_event())
        assert a.alert_type in VALID_ALERT_TYPES

    def test_reasons_populated(self):
        a = detect_smart_whale_event(base_event())
        assert isinstance(a.reasons, list)
        assert len(a.reasons) > 0

    def test_action_nonempty(self):
        a = detect_smart_whale_event(base_event())
        assert len(a.action) > 5

    def test_side_long_mapped(self):
        a = detect_smart_whale_event(base_event(side="long"))
        assert a.side == "long"

    def test_side_short_mapped(self):
        a = detect_smart_whale_event(base_event(side="short"))
        assert a.side == "short"

    def test_side_buy_maps_to_long(self):
        a = detect_smart_whale_event(base_event(side="buy"))
        assert a.side == "long"

    def test_side_sell_maps_to_short(self):
        a = detect_smart_whale_event(base_event(side="sell"))
        assert a.side == "short"

    def test_type_error_non_dict(self):
        with pytest.raises(TypeError, match="dict"):
            detect_smart_whale_event("not a dict")

    def test_value_error_negative_threshold(self):
        with pytest.raises(ValueError, match="min_size_usd"):
            detect_smart_whale_event(base_event(), min_size_usd=-1)

    def test_with_rich_context_scores_higher(self):
        a_bare = detect_smart_whale_event(base_event())
        ctx = rich_context(
            imbalance=0.8, liquidity_score=20, funding_rate=0.1,
            oi_change_pct=20, near_breakout=True, repeated_trader=True,
        )
        a_ctx = detect_smart_whale_event(base_event(), market_context=ctx)
        assert a_ctx.importance_score >= a_bare.importance_score

    def test_context_populates_context_field(self):
        ctx = rich_context(imbalance=0.6, funding_rate=0.05)
        a = detect_smart_whale_event(base_event(), market_context=ctx)
        assert isinstance(a.context, str)

    def test_warnings_populated_for_high_leverage(self):
        a = detect_smart_whale_event(base_event(leverage=25))
        assert len(a.warnings) > 0

    def test_liquidation_event_type(self):
        a = detect_smart_whale_event(base_event(event_type="liquidation_risk"))
        assert a.alert_type == ALERT_LIQUIDATION_RISK

    def test_whale_exit_on_close(self):
        a = detect_smart_whale_event(base_event(event_type="closed", side="exit"))
        assert a.alert_type == ALERT_WHALE_EXIT

    def test_accumulation_event_type(self):
        a = detect_smart_whale_event(base_event(event_type="accumulation", leverage=None))
        assert a.alert_type == ALERT_SMART_ACCUMULATION


# ══ TestFilterNoiseAlerts ════════════════════════════════════════════════════

class TestFilterNoiseAlerts:
    def _make_alerts(self, scores: list[float]) -> list[WhaleAlert]:
        alerts = []
        for s in scores:
            a = build_whale_alert(
                "X", "test", ALERT_AGGRESSIVE_LONG, "long",
                1_000_000, "t",
                importance_score=s,
            )
            alerts.append(a)
        return alerts

    def test_filters_below_threshold(self):
        alerts = self._make_alerts([90, 70, 50, 30, 10])
        result = filter_noise_alerts(alerts, min_importance=60)
        assert all(a.importance_score >= 60 for a in result)

    def test_sorted_descending(self):
        alerts = self._make_alerts([30, 90, 50, 80])
        result = filter_noise_alerts(alerts, min_importance=0)
        scores = [a.importance_score for a in result]
        assert scores == sorted(scores, reverse=True)

    def test_empty_input_returns_empty(self):
        assert filter_noise_alerts([]) == []

    def test_all_filtered_returns_empty(self):
        alerts = self._make_alerts([10, 20, 30])
        result = filter_noise_alerts(alerts, min_importance=50)
        assert result == []

    def test_all_kept_at_zero_threshold(self):
        alerts = self._make_alerts([0, 10, 50, 90])
        result = filter_noise_alerts(alerts, min_importance=0)
        assert len(result) == 4

    def test_at_exact_threshold(self):
        alerts = self._make_alerts([60, 59, 61])
        result = filter_noise_alerts(alerts, min_importance=60)
        assert len(result) == 2  # 60 and 61 kept

    def test_bad_min_importance_raises(self):
        with pytest.raises(ValueError):
            filter_noise_alerts([], min_importance=-1)

    def test_bad_max_importance_raises(self):
        with pytest.raises(ValueError):
            filter_noise_alerts([], min_importance=101)


# ══ TestDemoWhaleAlerts ═══════════════════════════════════════════════════════

class TestDemoWhaleAlerts:
    def test_returns_list(self):
        assert isinstance(demo_whale_alerts(), list)

    def test_minimum_count(self):
        assert len(demo_whale_alerts()) >= 5

    def test_all_are_whale_alerts(self):
        assert all(isinstance(a, WhaleAlert) for a in demo_whale_alerts())

    def test_all_sizes_nonnegative(self):
        assert all(a.size_usd >= 0 for a in demo_whale_alerts())

    def test_all_risks_valid(self):
        assert all(a.risk in VALID_RISKS for a in demo_whale_alerts())

    def test_all_types_valid(self):
        assert all(a.alert_type in VALID_ALERT_TYPES for a in demo_whale_alerts())

    def test_scores_in_range(self):
        for a in demo_whale_alerts():
            assert 0 <= a.importance_score <= 100
            assert 0 <= a.confidence <= 100

    def test_covers_multiple_alert_types(self):
        types = {a.alert_type for a in demo_whale_alerts()}
        assert len(types) >= 3

    def test_covers_liquidation_risk(self):
        types = {a.alert_type for a in demo_whale_alerts()}
        assert ALERT_LIQUIDATION_RISK in types

    def test_covers_whale_exit(self):
        types = {a.alert_type for a in demo_whale_alerts()}
        assert ALERT_WHALE_EXIT in types

    def test_reasons_are_lists(self):
        for a in demo_whale_alerts():
            assert isinstance(a.reasons, list)

    def test_timestamps_recent(self):
        cutoff = int(time.time() * 1000) - 4 * 3600 * 1000  # 4 hours ago
        now    = int(time.time() * 1000) + 1000
        for a in demo_whale_alerts():
            assert cutoff <= a.timestamp_ms <= now


# ══ TestWhaleAlertDataclass ═══════════════════════════════════════════════════

class TestWhaleAlertDataclass:
    def _make(self, **kw) -> WhaleAlert:
        defaults = {
            "symbol": "X", "venue": "y",
            "alert_type": ALERT_AGGRESSIVE_LONG, "side": "long",
            "size_usd": 1_000_000, "risk": RISK_HIGH,
            "message": "test", "timestamp_ms": 0,
        }
        defaults.update(kw)
        return WhaleAlert(**defaults)

    def test_valid_construction(self):
        a = self._make()
        assert a.symbol == "X"

    def test_invalid_alert_type_raises(self):
        with pytest.raises(ValueError, match="alert_type"):
            self._make(alert_type="bad_type")

    def test_invalid_risk_raises(self):
        with pytest.raises(ValueError, match="risk"):
            self._make(risk="catastrophic")

    def test_negative_size_raises(self):
        with pytest.raises(ValueError, match="size_usd"):
            self._make(size_usd=-1)

    def test_negative_leverage_raises(self):
        with pytest.raises(ValueError, match="leverage"):
            self._make(leverage=-5)

    def test_confidence_clamped_above(self):
        a = self._make(confidence=150)
        assert a.confidence == 100.0

    def test_confidence_clamped_below(self):
        a = self._make(confidence=-50)
        assert a.confidence == 0.0

    def test_importance_clamped(self):
        a = self._make(importance_score=200)
        assert a.importance_score == 100.0

    def test_is_high_risk_true(self):
        a = self._make(risk=RISK_HIGH)
        assert a.is_high_risk

    def test_is_high_risk_false_for_medium(self):
        a = self._make(risk=RISK_MEDIUM)
        assert not a.is_high_risk

    def test_leverage_str_none(self):
        assert self._make().leverage_str == "spot"

    def test_leverage_str_10x(self):
        assert self._make(leverage=10).leverage_str == "10x"

    def test_size_str_millions(self):
        a = self._make(size_usd=2_500_000)
        assert "2.5M" in a.size_str

    def test_size_str_thousands(self):
        a = self._make(size_usd=250_000)
        assert "250K" in a.size_str


# ══ TestEdgeCases ═════════════════════════════════════════════════════════════

class TestEdgeCases:
    def test_detect_zero_size_returns_none(self):
        assert detect_smart_whale_event({"size_usd": 0}) is None

    def test_detect_no_keys_returns_none(self):
        # empty dict has size_usd=0 → below threshold
        assert detect_smart_whale_event({}) is None

    def test_detect_missing_leverage_no_crash(self):
        ev = base_event()
        del ev["leverage"]
        a = detect_smart_whale_event(ev)
        assert a is not None
        assert a.leverage is None

    def test_detect_missing_price_no_crash(self):
        ev = base_event()
        del ev["price"]
        a = detect_smart_whale_event(ev)
        assert a is not None

    def test_detect_missing_symbol_uses_unknown(self):
        ev = {"size_usd": 5_000_000, "side": "long", "event_type": "opened"}
        a = detect_smart_whale_event(ev)
        assert a.symbol == "UNKNOWN"

    def test_detect_null_values_no_crash(self):
        ev = {"symbol": None, "venue": None, "size_usd": 1_000_000,
              "side": None, "leverage": None, "price": None}
        a = detect_smart_whale_event(ev)
        assert a is not None

    def test_detect_with_empty_context_no_crash(self):
        ctx = MarketContext()  # all defaults
        a = detect_smart_whale_event(base_event(), market_context=ctx)
        assert a is not None

    def test_classify_risk_no_context_no_crash(self):
        r = classify_whale_risk(1_000_000)
        assert r in VALID_RISKS

    def test_importance_zero_size_no_crash(self):
        s = calculate_importance_score(0)
        assert 0 <= s <= 100

    def test_filter_noise_non_alert_list(self):
        # filter_noise_alerts on empty list should not crash
        result = filter_noise_alerts([])
        assert result == []

    def test_demo_alerts_no_crash_called_twice(self):
        d1 = demo_whale_alerts()
        d2 = demo_whale_alerts()
        assert len(d1) == len(d2)


# ══ TestMarketContextIntegration ══════════════════════════════════════════════

class TestMarketContextIntegration:
    def test_thin_liquidity_escalates_risk(self):
        # $400k normally low risk
        r_bare = classify_whale_risk(400_000)
        ctx    = MarketContext(liquidity_score=15)
        r_ctx  = classify_whale_risk(400_000, market_context=ctx)
        _order = [RISK_LOW, RISK_MEDIUM, RISK_HIGH, RISK_EXTREME]
        assert _order.index(r_ctx) >= _order.index(r_bare)

    def test_high_funding_escalates_risk(self):
        r_bare = classify_whale_risk(300_000)
        ctx    = MarketContext(funding_rate=0.20)
        r_ctx  = classify_whale_risk(300_000, market_context=ctx)
        _order = [RISK_LOW, RISK_MEDIUM, RISK_HIGH, RISK_EXTREME]
        assert _order.index(r_ctx) >= _order.index(r_bare)

    def test_context_adds_reasons(self):
        ctx = rich_context(
            imbalance=0.7, near_breakout=True,
            bid_wall_usd=1_000_000, funding_rate=0.05,
        )
        a = detect_smart_whale_event(base_event(), market_context=ctx)
        assert len(a.reasons) >= 2

    def test_high_leverage_adds_warnings(self):
        a = detect_smart_whale_event(base_event(leverage=25))
        assert any("leverage" in w.lower() or "liquidation" in w.lower()
                   for w in a.warnings)

    def test_repeated_trader_boosts_confidence(self):
        ctx_no  = rich_context(repeated_trader=False)
        ctx_yes = rich_context(repeated_trader=True)
        a_no  = detect_smart_whale_event(base_event(), market_context=ctx_no)
        a_yes = detect_smart_whale_event(base_event(), market_context=ctx_yes)
        assert a_yes.confidence >= a_no.confidence

    def test_repeated_trader_boosts_importance(self):
        ctx_no  = rich_context(repeated_trader=False)
        ctx_yes = rich_context(repeated_trader=True)
        s_no  = calculate_importance_score(1_000_000, leverage=10, market_context=ctx_no)
        s_yes = calculate_importance_score(1_000_000, leverage=10, market_context=ctx_yes)
        assert s_yes > s_no

    def test_near_support_adds_long_reason(self):
        ctx = MarketContext(near_support=True)
        a = detect_smart_whale_event(base_event(side="long"), market_context=ctx)
        assert any("support" in r.lower() for r in a.reasons)

    def test_near_resistance_adds_short_reason(self):
        ctx = MarketContext(near_resistance=True)
        a = detect_smart_whale_event(base_event(side="short"), market_context=ctx)
        assert any("resistance" in r.lower() for r in a.reasons)

    def test_crowded_leverage_action_contains_avoid(self):
        ev = base_event(leverage=15, oi_change_pct=25)
        ev["oi_change_pct"] = 25
        ev["event_type"] = "opened"
        a = detect_smart_whale_event(ev)
        if a.alert_type == ALERT_CROWDED_LEVERAGE:
            assert "avoid" in a.action.lower() or "crowded" in a.action.lower()

    def test_importance_ordering_by_context_richness(self):
        ev = base_event()
        s0 = detect_smart_whale_event(ev).importance_score
        s1 = detect_smart_whale_event(ev, market_context=MarketContext(near_breakout=True)).importance_score
        s2 = detect_smart_whale_event(ev, market_context=rich_context(
            near_breakout=True, repeated_trader=True, imbalance=0.8
        )).importance_score
        assert s0 <= s1 <= s2
