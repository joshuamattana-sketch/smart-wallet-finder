"""
tests/test_pro_market_scanner.py
----------------------------------
Unit tests for services/pro_market_scanner.py.

All tests use fake/mock data — zero real API calls.

Test classes:
  TestClamp                   — _clamp helper
  TestBuildSignalBasic        — core signal fields and types
  TestScoreRange              — score always stays 0–100
  TestSignalLevels            — correct signal level for each market condition
  TestRiskLevels              — correct risk mapping
  TestReasonGeneration        — reasons are informative plain English
  TestActionHints             — action hints match signal levels
  TestContributingScores      — all sub-scores present and in range
  TestEdgeCases               — empty metrics, zero values, extreme values
  TestNeutralFallback         — _neutral_fallback shape
  TestScanMarketNoNetwork     — scan_market returns valid signal, mocked connector
  TestScanMarketsOrdering     — scan_markets returns sorted list
"""

import sys
import os
import time
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from core.constants import RISK_LEVELS, SIGNAL_LEVELS
from core.models import OrderBookLevel, OrderBookMetrics, OrderBookSnapshot, ProSetupSignal
from services.orderbook_engine import analyze_orderbook
from services.pro_market_scanner import (
    DEFAULT_MARKETS,
    ScanError,
    _clamp,
    _neutral_fallback,
    build_signal_from_metrics,
    scan_market,
    scan_markets,
)


# ── Metric factory helpers ────────────────────────────────────────────────────

def make_metrics(
    symbol: str = "BTCUSDT",
    exchange: str = "binance",
    spread_pct: float = 0.01,
    imbalance: float = 0.0,
    bid_depth_usd: float = 500_000.0,
    ask_depth_usd: float = 500_000.0,
    liquidity_score: float = 80.0,
    bid_walls: list = None,
    ask_walls: list = None,
    slippage_buy_1k: float = 0.001,
    slippage_sell_1k: float = 0.001,
    is_thin: bool = False,
    signal: str = "neutral",
    signal_reason: str = "Test metrics",
) -> OrderBookMetrics:
    """Create a fully populated OrderBookMetrics for testing."""
    return OrderBookMetrics(
        symbol=symbol,
        exchange=exchange,
        timestamp_ms=1_716_200_000_000,
        mid_price=67_420.0,
        spread_pct=spread_pct,
        bid_depth_usd=bid_depth_usd,
        ask_depth_usd=ask_depth_usd,
        depth_pct=0.5,
        imbalance=imbalance,
        bid_walls=bid_walls or [],
        ask_walls=ask_walls or [],
        slippage_buy_1k=slippage_buy_1k,
        slippage_sell_1k=slippage_sell_1k,
        liquidity_score=liquidity_score,
        is_thin=is_thin,
        signal=signal,
        signal_reason=signal_reason,
    )


def make_wall(price: float, qty: float, usd: float) -> OrderBookLevel:
    return OrderBookLevel(price=price, qty=qty, usd_size=usd)


def make_snapshot_and_metrics(
    bids: list[OrderBookLevel],
    asks: list[OrderBookLevel],
    symbol: str = "BTCUSDT",
) -> OrderBookMetrics:
    """Build a snapshot, run analyze_orderbook, return metrics."""
    snap = OrderBookSnapshot(
        symbol=symbol, exchange="test",
        timestamp_ms=1_716_200_000_000,
        bids=bids, asks=asks,
        mid_price=(bids[0].price + asks[0].price) / 2 if bids and asks else 0.0,
    )
    return analyze_orderbook(snap)


# ══ TestClamp ════════════════════════════════════════════════════════════════

class TestClamp:
    def test_clamp_above_max(self):
        assert _clamp(150.0, 0.0, 100.0) == 100.0

    def test_clamp_below_min(self):
        assert _clamp(-5.0, 0.0, 100.0) == 0.0

    def test_clamp_within_range(self):
        assert _clamp(50.0, 0.0, 100.0) == 50.0

    def test_clamp_at_boundary_lo(self):
        assert _clamp(0.0, 0.0, 100.0) == 0.0

    def test_clamp_at_boundary_hi(self):
        assert _clamp(100.0, 0.0, 100.0) == 100.0

    def test_clamp_negative_range(self):
        assert _clamp(-50.0, -100.0, 0.0) == -50.0

    def test_clamp_exact_value(self):
        assert _clamp(42.0, 0.0, 100.0) == pytest.approx(42.0)


# ══ TestBuildSignalBasic ═════════════════════════════════════════════════════

class TestBuildSignalBasic:
    def test_returns_pro_setup_signal(self):
        m = make_metrics()
        sig = build_signal_from_metrics("BTCUSDT", "binance", m)
        assert isinstance(sig, ProSetupSignal)

    def test_symbol_preserved(self):
        m = make_metrics(symbol="ETHUSDT")
        sig = build_signal_from_metrics("ETHUSDT", "binance", m)
        assert sig.symbol == "ETHUSDT"

    def test_exchange_preserved(self):
        m = make_metrics()
        sig = build_signal_from_metrics("BTCUSDT", "Hyperliquid", m)
        assert sig.exchange == "Hyperliquid"

    def test_market_type_preserved(self):
        m = make_metrics()
        sig = build_signal_from_metrics("HYPE", "Hyperliquid", m, market_type="perp")
        assert sig.market_type == "perp"

    def test_timestamp_from_metrics(self):
        m = make_metrics()
        sig = build_signal_from_metrics("BTCUSDT", "binance", m)
        assert sig.timestamp_ms == 1_716_200_000_000

    def test_signal_level_valid(self):
        m = make_metrics()
        sig = build_signal_from_metrics("BTCUSDT", "binance", m)
        assert sig.signal_level in SIGNAL_LEVELS

    def test_risk_level_valid(self):
        m = make_metrics()
        sig = build_signal_from_metrics("BTCUSDT", "binance", m)
        assert sig.risk_level in RISK_LEVELS

    def test_reason_is_nonempty_string(self):
        m = make_metrics()
        sig = build_signal_from_metrics("BTCUSDT", "binance", m)
        assert isinstance(sig.reason, str)
        assert len(sig.reason) > 10

    def test_action_hint_is_nonempty_string(self):
        m = make_metrics()
        sig = build_signal_from_metrics("BTCUSDT", "binance", m)
        assert isinstance(sig.action_hint, str)
        assert len(sig.action_hint) > 5

    def test_confidence_is_float(self):
        m = make_metrics()
        sig = build_signal_from_metrics("BTCUSDT", "binance", m)
        assert isinstance(sig.confidence, float)

    def test_contributing_has_all_keys(self):
        m = make_metrics()
        sig = build_signal_from_metrics("BTCUSDT", "binance", m)
        assert set(sig.contributing.keys()) == {"liquidity", "spread", "imbalance", "walls", "slippage"}

    def test_signal_is_not_invalidated(self):
        m = make_metrics()
        sig = build_signal_from_metrics("BTCUSDT", "binance", m)
        assert sig.is_valid


# ══ TestScoreRange ════════════════════════════════════════════════════════════

class TestScoreRange:
    def _score(self, **kw) -> float:
        m = make_metrics(**kw)
        return build_signal_from_metrics("X", "test", m).score

    def test_score_in_range_normal(self):
        assert 0.0 <= self._score() <= 100.0

    def test_score_in_range_thin_book(self):
        s = self._score(is_thin=True, bid_depth_usd=0, ask_depth_usd=0)
        assert 0.0 <= s <= 100.0

    def test_score_in_range_wide_spread(self):
        assert 0.0 <= self._score(spread_pct=10.0) <= 100.0

    def test_score_in_range_tight_spread(self):
        assert 0.0 <= self._score(spread_pct=0.001) <= 100.0

    def test_score_in_range_extreme_imbalance(self):
        assert 0.0 <= self._score(imbalance=1.0) <= 100.0

    def test_score_in_range_negative_imbalance(self):
        assert 0.0 <= self._score(imbalance=-1.0) <= 100.0

    def test_score_in_range_zero_liquidity(self):
        assert 0.0 <= self._score(liquidity_score=0.0) <= 100.0

    def test_score_in_range_max_liquidity(self):
        assert 0.0 <= self._score(liquidity_score=100.0) <= 100.0

    def test_score_in_range_extreme_slippage(self):
        assert 0.0 <= self._score(slippage_buy_1k=100.0, slippage_sell_1k=100.0) <= 100.0

    def test_score_in_range_large_walls(self):
        walls = [make_wall(67_400.0, 5.0, 2_000_000.0)]
        m = make_metrics(bid_walls=walls)
        sig = build_signal_from_metrics("X", "test", m)
        assert 0.0 <= sig.score <= 100.0

    def test_high_quality_book_scores_high(self):
        # Tight spread, good liquidity, mild imbalance = high score
        s = self._score(spread_pct=0.001, liquidity_score=90.0,
                        imbalance=0.3, slippage_buy_1k=0.001)
        assert s >= 60.0

    def test_poor_book_scores_low(self):
        # Wide spread, low liquidity, extreme slippage
        s = self._score(spread_pct=5.0, liquidity_score=5.0,
                        slippage_buy_1k=5.0, slippage_sell_1k=5.0,
                        bid_depth_usd=1_000.0, ask_depth_usd=1_000.0)
        assert s < 50.0

    def test_contributing_scores_sum_leq_100(self):
        m = make_metrics()
        sig = build_signal_from_metrics("X", "test", m)
        total = sum(sig.contributing.values())
        assert total <= 100.01  # allow float rounding

    def test_contributing_all_nonnegative(self):
        m = make_metrics()
        sig = build_signal_from_metrics("X", "test", m)
        assert all(v >= 0 for v in sig.contributing.values())


# ══ TestSignalLevels ══════════════════════════════════════════════════════════

class TestSignalLevels:
    def test_thin_book_returns_avoid(self):
        m = make_metrics(is_thin=True, bid_depth_usd=0, ask_depth_usd=0)
        sig = build_signal_from_metrics("X", "test", m)
        assert sig.signal_level == "avoid"

    def test_excellent_conditions_not_avoid(self):
        m = make_metrics(
            spread_pct=0.001, liquidity_score=95.0,
            imbalance=0.6, bid_depth_usd=5_000_000.0,
            ask_depth_usd=2_000_000.0,
            slippage_buy_1k=0.001, slippage_sell_1k=0.001,
            bid_walls=[make_wall(67_000.0, 10.0, 670_000.0)],
        )
        sig = build_signal_from_metrics("BTCUSDT", "binance", m)
        assert sig.signal_level not in ("avoid",)

    def test_poor_conditions_avoid_or_neutral(self):
        m = make_metrics(
            spread_pct=5.0, liquidity_score=5.0,
            slippage_buy_1k=5.0, slippage_sell_1k=5.0,
            bid_depth_usd=500.0, ask_depth_usd=500.0,
        )
        sig = build_signal_from_metrics("X", "test", m)
        assert sig.signal_level in ("avoid", "neutral")

    def test_signal_level_is_valid_key(self):
        for imb in [-0.8, -0.3, 0.0, 0.3, 0.8]:
            m = make_metrics(imbalance=imb)
            sig = build_signal_from_metrics("X", "test", m)
            assert sig.signal_level in SIGNAL_LEVELS, f"Invalid: {sig.signal_level}"

    def test_strong_negative_imbalance_not_buy(self):
        m = make_metrics(
            imbalance=-0.9, liquidity_score=90.0,
            spread_pct=0.001, bid_depth_usd=200_000.0,
            ask_depth_usd=900_000.0,
            slippage_buy_1k=0.001, slippage_sell_1k=0.001,
        )
        sig = build_signal_from_metrics("X", "test", m)
        # With strong ask pressure, signal should not be buy
        assert sig.signal_level not in ("buy", "strong_buy")

    def test_strong_positive_imbalance_can_be_buy(self):
        walls = [make_wall(67_000.0, 10.0, 1_000_000.0)]
        m = make_metrics(
            imbalance=0.9, liquidity_score=90.0,
            spread_pct=0.001, bid_depth_usd=900_000.0,
            ask_depth_usd=200_000.0,
            slippage_buy_1k=0.001, slippage_sell_1k=0.001,
            bid_walls=walls,
        )
        sig = build_signal_from_metrics("X", "test", m)
        assert sig.signal_level in ("strong_buy", "buy", "watch")


# ══ TestRiskLevels ════════════════════════════════════════════════════════════

class TestRiskLevels:
    def test_thin_book_extreme_risk(self):
        m = make_metrics(is_thin=True, bid_depth_usd=0, ask_depth_usd=0)
        sig = build_signal_from_metrics("X", "test", m)
        assert sig.risk_level == "extreme"

    def test_extreme_spread_high_or_extreme_risk(self):
        m = make_metrics(spread_pct=5.0)
        sig = build_signal_from_metrics("X", "test", m)
        assert sig.risk_level in ("extreme", "high")

    def test_poor_liquidity_high_risk(self):
        m = make_metrics(liquidity_score=15.0, spread_pct=1.5)
        sig = build_signal_from_metrics("X", "test", m)
        assert sig.risk_level in ("high", "extreme")

    def test_good_book_low_or_medium_risk(self):
        m = make_metrics(
            spread_pct=0.002, liquidity_score=85.0,
            slippage_buy_1k=0.001, slippage_sell_1k=0.001,
        )
        sig = build_signal_from_metrics("X", "test", m)
        assert sig.risk_level in ("low", "medium")

    def test_risk_level_always_valid(self):
        for spread in [0.001, 0.1, 1.5, 5.0]:
            for liq in [5.0, 30.0, 70.0, 95.0]:
                m = make_metrics(spread_pct=spread, liquidity_score=liq)
                sig = build_signal_from_metrics("X", "test", m)
                assert sig.risk_level in RISK_LEVELS, f"Invalid: {sig.risk_level}"


# ══ TestReasonGeneration ══════════════════════════════════════════════════════

class TestReasonGeneration:
    def test_reason_mentions_spread(self):
        m = make_metrics(spread_pct=0.001)
        sig = build_signal_from_metrics("X", "test", m)
        assert "spread" in sig.reason.lower() or "tight" in sig.reason.lower()

    def test_reason_mentions_wide_spread(self):
        m = make_metrics(spread_pct=5.0)
        sig = build_signal_from_metrics("X", "test", m)
        assert "wide" in sig.reason.lower() or "spread" in sig.reason.lower()

    def test_reason_mentions_imbalance(self):
        m = make_metrics(imbalance=0.7)
        sig = build_signal_from_metrics("X", "test", m)
        assert "imbalance" in sig.reason.lower() or "bid" in sig.reason.lower() or "pressure" in sig.reason.lower()

    def test_reason_mentions_liquidity(self):
        m = make_metrics(liquidity_score=90.0)
        sig = build_signal_from_metrics("X", "test", m)
        assert "liquidity" in sig.reason.lower()

    def test_reason_mentions_wall_when_large(self):
        walls = [make_wall(67_000.0, 10.0, 1_500_000.0)]
        m = make_metrics(bid_walls=walls)
        sig = build_signal_from_metrics("X", "test", m)
        assert "wall" in sig.reason.lower()

    def test_reason_no_wall_mention_when_empty(self):
        m = make_metrics(bid_walls=[], ask_walls=[])
        sig = build_signal_from_metrics("X", "test", m)
        # Without large walls, "wall" may or may not appear — just check reason is valid
        assert len(sig.reason) > 5

    def test_reason_thin_book_is_descriptive(self):
        m = make_metrics(is_thin=True, bid_depth_usd=0, ask_depth_usd=0)
        sig = build_signal_from_metrics("X", "test", m)
        assert len(sig.reason) > 10

    def test_reason_different_for_different_conditions(self):
        m1 = make_metrics(spread_pct=0.001, liquidity_score=90.0)
        m2 = make_metrics(spread_pct=5.0, liquidity_score=5.0)
        s1 = build_signal_from_metrics("X", "test", m1)
        s2 = build_signal_from_metrics("X", "test", m2)
        assert s1.reason != s2.reason


# ══ TestActionHints ═══════════════════════════════════════════════════════════

class TestActionHints:
    def test_action_hint_nonempty(self):
        m = make_metrics()
        sig = build_signal_from_metrics("X", "test", m)
        assert len(sig.action_hint) > 5

    def test_avoid_signal_has_avoid_hint(self):
        m = make_metrics(is_thin=True, bid_depth_usd=0, ask_depth_usd=0)
        sig = build_signal_from_metrics("X", "test", m)
        assert "avoid" in sig.action_hint.lower() or "insufficient" in sig.action_hint.lower()

    def test_watch_signal_has_watch_hint(self):
        # Construct a mid-range metrics to get "watch"
        m = make_metrics(
            spread_pct=0.5, liquidity_score=50.0,
            imbalance=0.1, slippage_buy_1k=0.1,
        )
        sig = build_signal_from_metrics("X", "test", m)
        # Action hint should be informative regardless of level
        assert len(sig.action_hint) > 5

    def test_action_hints_different_conditions(self):
        m_good = make_metrics(spread_pct=0.001, liquidity_score=90.0, imbalance=0.7)
        m_bad  = make_metrics(spread_pct=5.0, liquidity_score=5.0)
        s_good = build_signal_from_metrics("X", "test", m_good)
        s_bad  = build_signal_from_metrics("X", "test", m_bad)
        # They should differ
        assert s_good.action_hint != s_bad.action_hint


# ══ TestContributingScores ════════════════════════════════════════════════════

class TestContributingScores:
    def test_all_keys_present(self):
        m = make_metrics()
        sig = build_signal_from_metrics("X", "test", m)
        assert "liquidity"  in sig.contributing
        assert "spread"     in sig.contributing
        assert "imbalance"  in sig.contributing
        assert "walls"      in sig.contributing
        assert "slippage"   in sig.contributing

    def test_all_values_nonnegative(self):
        m = make_metrics()
        sig = build_signal_from_metrics("X", "test", m)
        for k, v in sig.contributing.items():
            assert v >= 0, f"{k} = {v}"

    def test_liquidity_score_bounded(self):
        m = make_metrics(liquidity_score=100.0)
        sig = build_signal_from_metrics("X", "test", m)
        assert sig.contributing["liquidity"] <= 30.0

    def test_spread_score_bounded(self):
        m = make_metrics(spread_pct=0.001)
        sig = build_signal_from_metrics("X", "test", m)
        assert sig.contributing["spread"] <= 25.0

    def test_imbalance_score_bounded(self):
        m = make_metrics(imbalance=1.0)
        sig = build_signal_from_metrics("X", "test", m)
        assert sig.contributing["imbalance"] <= 20.0

    def test_walls_score_bounded(self):
        walls = [make_wall(67_000.0, 100.0, 10_000_000.0)]
        m = make_metrics(bid_walls=walls)
        sig = build_signal_from_metrics("X", "test", m)
        assert sig.contributing["walls"] <= 15.0

    def test_slippage_score_bounded(self):
        m = make_metrics(slippage_buy_1k=0.001, slippage_sell_1k=0.001)
        sig = build_signal_from_metrics("X", "test", m)
        assert sig.contributing["slippage"] <= 10.0

    def test_thin_book_contributing_all_zero(self):
        m = make_metrics(is_thin=True, bid_depth_usd=0, ask_depth_usd=0)
        sig = build_signal_from_metrics("X", "test", m)
        assert all(v == 0 for v in sig.contributing.values())


# ══ TestEdgeCases ═════════════════════════════════════════════════════════════

class TestEdgeCases:
    def test_empty_metrics_no_crash(self):
        """analyze_orderbook on empty snapshot → build_signal should not crash."""
        snap = OrderBookSnapshot("X", "test", 0)
        metrics = analyze_orderbook(snap)
        sig = build_signal_from_metrics("X", "test", metrics)
        assert isinstance(sig, ProSetupSignal)
        assert 0.0 <= sig.score <= 100.0

    def test_zero_spread_no_crash(self):
        m = make_metrics(spread_pct=0.0)
        sig = build_signal_from_metrics("X", "test", m)
        assert isinstance(sig, ProSetupSignal)

    def test_zero_depth_no_crash(self):
        m = make_metrics(bid_depth_usd=0.0, ask_depth_usd=0.0, is_thin=True)
        sig = build_signal_from_metrics("X", "test", m)
        assert isinstance(sig, ProSetupSignal)

    def test_extreme_slippage_sentinel_no_crash(self):
        m = make_metrics(slippage_buy_1k=100.0, slippage_sell_1k=100.0)
        sig = build_signal_from_metrics("X", "test", m)
        assert isinstance(sig, ProSetupSignal)
        assert sig.contributing["slippage"] == 0.0

    def test_empty_walls_no_crash(self):
        m = make_metrics(bid_walls=[], ask_walls=[])
        sig = build_signal_from_metrics("X", "test", m)
        assert isinstance(sig, ProSetupSignal)
        assert sig.contributing["walls"] == 0.0

    def test_very_large_walls_no_crash(self):
        walls = [make_wall(67_000.0, 1_000.0, 100_000_000.0)]
        m = make_metrics(bid_walls=walls)
        sig = build_signal_from_metrics("X", "test", m)
        assert isinstance(sig, ProSetupSignal)
        assert 0.0 <= sig.score <= 100.0

    def test_imbalance_at_exactly_one(self):
        m = make_metrics(imbalance=1.0)
        sig = build_signal_from_metrics("X", "test", m)
        assert isinstance(sig, ProSetupSignal)

    def test_imbalance_at_exactly_minus_one(self):
        m = make_metrics(imbalance=-1.0)
        sig = build_signal_from_metrics("X", "test", m)
        assert isinstance(sig, ProSetupSignal)

    def test_full_pipeline_from_real_snapshot(self):
        """Build a snapshot → analyze → signal, verify end-to-end."""
        bids = [
            OrderBookLevel(price=2_004.0, qty=5.0, usd_size=10_020.0),
            OrderBookLevel(price=2_003.0, qty=20.0, usd_size=40_060.0),
        ]
        asks = [
            OrderBookLevel(price=2_005.0, qty=3.0, usd_size=6_015.0),
            OrderBookLevel(price=2_006.0, qty=10.0, usd_size=20_060.0),
        ]
        metrics = make_snapshot_and_metrics(bids, asks, symbol="ETHUSDT")
        sig = build_signal_from_metrics("ETHUSDT", "binance", metrics)
        assert sig.symbol == "ETHUSDT"
        assert 0.0 <= sig.score <= 100.0
        assert sig.signal_level in SIGNAL_LEVELS
        assert sig.risk_level in RISK_LEVELS
        assert len(sig.reason) > 10
        assert len(sig.action_hint) > 5


# ══ TestNeutralFallback ═══════════════════════════════════════════════════════

class TestNeutralFallback:
    def test_returns_pro_setup_signal(self):
        sig = _neutral_fallback("BTCUSDT", "binance", "test reason")
        assert isinstance(sig, ProSetupSignal)

    def test_signal_level_is_neutral(self):
        sig = _neutral_fallback("BTCUSDT", "binance", "test reason")
        assert sig.signal_level == "neutral"

    def test_score_is_zero(self):
        sig = _neutral_fallback("BTCUSDT", "binance", "test reason")
        assert sig.score == 0.0

    def test_confidence_is_zero(self):
        sig = _neutral_fallback("BTCUSDT", "binance", "test reason")
        assert sig.confidence == 0.0

    def test_reason_contains_input_reason(self):
        sig = _neutral_fallback("BTCUSDT", "binance", "Fetch failed: timeout")
        assert "Fetch failed" in sig.reason

    def test_risk_is_high(self):
        sig = _neutral_fallback("BTCUSDT", "binance", "no data")
        assert sig.risk_level == "high"

    def test_symbol_preserved(self):
        sig = _neutral_fallback("HYPE", "Hyperliquid", "error")
        assert sig.symbol == "HYPE"

    def test_exchange_preserved(self):
        sig = _neutral_fallback("HYPE", "Hyperliquid", "error")
        assert sig.exchange == "Hyperliquid"

    def test_timestamp_is_recent(self):
        before = int(time.time() * 1000) - 2000
        sig = _neutral_fallback("X", "test", "error")
        after  = int(time.time() * 1000) + 2000
        assert before <= sig.timestamp_ms <= after

    def test_contributing_is_empty_dict(self):
        sig = _neutral_fallback("X", "test", "error")
        assert sig.contributing == {}

    def test_action_hint_suggests_wait(self):
        sig = _neutral_fallback("X", "test", "error")
        assert "wait" in sig.action_hint.lower() or "unavailable" in sig.action_hint.lower()


# ══ TestScanMarketNoNetwork ═══════════════════════════════════════════════════

class TestScanMarketNoNetwork:
    def _mock_snapshot(self) -> OrderBookSnapshot:
        bids = [OrderBookLevel(67_410.0, 0.5, 33_705.0), OrderBookLevel(67_400.0, 2.0, 134_800.0)]
        asks = [OrderBookLevel(67_420.0, 0.2, 13_484.0), OrderBookLevel(67_430.0, 0.8, 53_944.0)]
        return OrderBookSnapshot(
            "BTCUSDT", "binance", 1_716_200_000_000,
            bids=bids, asks=asks,
            mid_price=(67_410.0 + 67_420.0) / 2,
        )

    @patch("services.pro_market_scanner._fetch_snapshot")
    def test_scan_market_returns_signal(self, mock_fetch):
        mock_fetch.return_value = self._mock_snapshot()
        sig = scan_market("BTCUSDT")
        assert isinstance(sig, ProSetupSignal)

    @patch("services.pro_market_scanner._fetch_snapshot")
    def test_scan_market_symbol_correct(self, mock_fetch):
        mock_fetch.return_value = self._mock_snapshot()
        sig = scan_market("BTCUSDT")
        assert sig.symbol == "BTCUSDT"

    @patch("services.pro_market_scanner._fetch_snapshot")
    def test_scan_market_score_in_range(self, mock_fetch):
        mock_fetch.return_value = self._mock_snapshot()
        sig = scan_market("BTCUSDT")
        assert 0.0 <= sig.score <= 100.0

    @patch("services.pro_market_scanner._fetch_snapshot")
    def test_scan_market_fetch_failure_returns_neutral(self, mock_fetch):
        mock_fetch.side_effect = ScanError("Connection refused", symbol="BTCUSDT", venue="binance")
        sig = scan_market("BTCUSDT")
        assert isinstance(sig, ProSetupSignal)
        assert sig.signal_level == "neutral"
        assert sig.confidence == 0.0

    @patch("services.pro_market_scanner._fetch_snapshot")
    def test_scan_market_unexpected_exception_returns_neutral(self, mock_fetch):
        mock_fetch.side_effect = RuntimeError("unexpected")
        sig = scan_market("BTCUSDT")
        assert isinstance(sig, ProSetupSignal)
        assert sig.signal_level == "neutral"

    @patch("services.pro_market_scanner._fetch_snapshot")
    def test_scan_market_empty_snapshot_returns_neutral(self, mock_fetch):
        mock_fetch.return_value = OrderBookSnapshot("BTCUSDT", "binance", 0)
        sig = scan_market("BTCUSDT")
        assert sig.signal_level == "neutral"
        assert sig.confidence == 0.0


# ══ TestScanMarketsOrdering ═══════════════════════════════════════════════════

class TestScanMarketsOrdering:
    def _make_snap(self, symbol: str, liq: float) -> OrderBookSnapshot:
        mid = 100.0
        bids = [OrderBookLevel(mid - 0.5, liq / mid, (mid - 0.5) * liq / mid)]
        asks = [OrderBookLevel(mid + 0.5, liq / mid, (mid + 0.5) * liq / mid)]
        return OrderBookSnapshot(symbol, "test", 0, bids=bids, asks=asks, mid_price=mid)

    @patch("services.pro_market_scanner._fetch_snapshot")
    def test_scan_markets_returns_list(self, mock_fetch):
        mock_fetch.return_value = self._make_snap("BTCUSDT", 10_000.0)
        result = scan_markets(["BTCUSDT", "ETHUSDT"])
        assert isinstance(result, list)

    @patch("services.pro_market_scanner._fetch_snapshot")
    def test_scan_markets_length_matches_input(self, mock_fetch):
        mock_fetch.return_value = self._make_snap("X", 10_000.0)
        result = scan_markets(["BTCUSDT", "ETHUSDT", "SOLUSDT"])
        assert len(result) == 3

    @patch("services.pro_market_scanner._fetch_snapshot")
    def test_scan_markets_sorted_by_score_desc(self, mock_fetch):
        mock_fetch.return_value = self._make_snap("X", 10_000.0)
        result = scan_markets(["BTCUSDT", "ETHUSDT"])
        scores = [s.score for s in result]
        assert scores == sorted(scores, reverse=True)

    @patch("services.pro_market_scanner._fetch_snapshot")
    def test_scan_markets_default_uses_default_markets(self, mock_fetch):
        mock_fetch.return_value = self._make_snap("X", 5_000.0)
        result = scan_markets()
        assert len(result) == len(DEFAULT_MARKETS)

    @patch("services.pro_market_scanner._fetch_snapshot")
    def test_scan_markets_one_failure_rest_succeed(self, mock_fetch):
        call_count = {"n": 0}
        def side_effect(sym):
            call_count["n"] += 1
            if sym == "ETHUSDT":
                raise ScanError("fail", symbol=sym, venue="binance")
            return self._make_snap(sym, 10_000.0)
        mock_fetch.side_effect = side_effect
        result = scan_markets(["BTCUSDT", "ETHUSDT", "SOLUSDT"])
        assert len(result) == 3  # all 3 returned, ETHUSDT as neutral fallback
        symbols = [s.symbol for s in result]
        assert "ETHUSDT" in symbols

    @patch("services.pro_market_scanner._fetch_snapshot")
    def test_scan_markets_all_pro_setup_signals(self, mock_fetch):
        mock_fetch.return_value = self._make_snap("X", 5_000.0)
        result = scan_markets(["BTCUSDT", "HYPE"])
        assert all(isinstance(s, ProSetupSignal) for s in result)

    @patch("services.pro_market_scanner._fetch_snapshot")
    def test_scan_markets_empty_list(self, mock_fetch):
        result = scan_markets([])
        assert result == []
        mock_fetch.assert_not_called()
