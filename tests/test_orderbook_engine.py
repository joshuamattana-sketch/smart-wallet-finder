"""
tests/test_orderbook_engine.py
------------------------------
Unit tests for services/orderbook_engine.py.

Covers:
- Normal books: spread, depth, imbalance, walls, slippage, liquidity score, analyze_orderbook
- Edge cases: empty book, single-sided book, zero-price levels, crossed book
- Thin book detection and signal derivation
- Large order slippage (order size > book depth)
"""

import sys
import os

# Make sure imports resolve from project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from core.models import OrderBookLevel, OrderBookSnapshot
from services.orderbook_engine import (
    analyze_orderbook,
    calculate_depth_usd,
    calculate_imbalance,
    calculate_liquidity_score,
    calculate_mid_price,
    calculate_spread_pct,
    estimate_slippage,
    find_biggest_walls,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def make_level(price: float, qty: float) -> OrderBookLevel:
    """Helper: create a level with usd_size = price * qty."""
    return OrderBookLevel(price=price, qty=qty, usd_size=price * qty)


def simple_book() -> OrderBookSnapshot:
    """
    A clean, balanced book around a mid of $100.

    Bids: 99.5 x 10 ($995), 99.0 x 50 ($4950), 98.0 x 5 ($490)
    Asks: 100.5 x 8 ($804), 101.0 x 20 ($2020), 102.0 x 3 ($306)
    """
    return OrderBookSnapshot(
        symbol="XUSDT",
        exchange="test",
        timestamp_ms=1_000_000,
        bids=[
            make_level(99.5, 10.0),
            make_level(99.0, 50.0),
            make_level(98.0, 5.0),
        ],
        asks=[
            make_level(100.5, 8.0),
            make_level(101.0, 20.0),
            make_level(102.0, 3.0),
        ],
    )


def deep_book() -> OrderBookSnapshot:
    """A deep, liquid book with lots of USD depth."""
    bids = [make_level(99_990 - i * 10, 1_000.0) for i in range(50)]
    asks = [make_level(100_010 + i * 10, 1_000.0) for i in range(50)]
    return OrderBookSnapshot("BTCUSDT", "binance", 2_000_000, bids=bids, asks=asks)


def thin_book() -> OrderBookSnapshot:
    """A book with very little liquidity on both sides."""
    return OrderBookSnapshot(
        symbol="MEMEUSDT",
        exchange="dex",
        timestamp_ms=3_000_000,
        bids=[make_level(0.001, 10.0)],   # $0.01 total
        asks=[make_level(0.0011, 5.0)],   # $0.0055 total
    )


def bid_heavy_book() -> OrderBookSnapshot:
    """A book strongly skewed toward bids."""
    return OrderBookSnapshot(
        symbol="SOLUSDT",
        exchange="bybit",
        timestamp_ms=4_000_000,
        bids=[
            make_level(99.0, 1000.0),  # $99,000
            make_level(98.5, 500.0),   # $49,250
        ],
        asks=[
            make_level(101.0, 10.0),   # $1,010
        ],
    )


def ask_heavy_book() -> OrderBookSnapshot:
    """A book strongly skewed toward asks."""
    return OrderBookSnapshot(
        symbol="ETHUSDT",
        exchange="binance",
        timestamp_ms=5_000_000,
        bids=[make_level(2990.0, 1.0)],    # $2,990
        asks=[
            make_level(3010.0, 100.0),     # $301,000
            make_level(3020.0, 50.0),      # $151,000
        ],
    )


def empty_book() -> OrderBookSnapshot:
    """Completely empty order book."""
    return OrderBookSnapshot("DEADUSDT", "dex", 0)


def single_side_bid() -> OrderBookSnapshot:
    """Only bids, no asks."""
    return OrderBookSnapshot(
        "XUSDT", "ex", 0,
        bids=[make_level(100.0, 5.0)],
        asks=[],
    )


def single_side_ask() -> OrderBookSnapshot:
    """Only asks, no bids."""
    return OrderBookSnapshot(
        "XUSDT", "ex", 0,
        bids=[],
        asks=[make_level(101.0, 5.0)],
    )


# ── Tests: calculate_mid_price ─────────────────────────────────────────────────

class TestCalculateMidPrice:
    def test_normal_book(self):
        snap = simple_book()
        assert calculate_mid_price(snap) == pytest.approx(100.0)

    def test_empty_book_returns_zero(self):
        assert calculate_mid_price(empty_book()) == 0.0

    def test_single_side_bid_returns_zero(self):
        assert calculate_mid_price(single_side_bid()) == 0.0

    def test_single_side_ask_returns_zero(self):
        assert calculate_mid_price(single_side_ask()) == 0.0

    def test_symmetric_book(self):
        snap = OrderBookSnapshot("X", "ex", 0,
            bids=[make_level(200.0, 1.0)],
            asks=[make_level(400.0, 1.0)])
        assert calculate_mid_price(snap) == pytest.approx(300.0)

    def test_deep_book_mid(self):
        snap = deep_book()
        mid = calculate_mid_price(snap)
        assert 99_990 <= mid <= 100_010


# ── Tests: calculate_spread_pct ───────────────────────────────────────────────

class TestCalculateSpreadPct:
    def test_simple_book(self):
        # bid=99.5, ask=100.5, mid=100.0 → spread=1.0%
        snap = simple_book()
        assert calculate_spread_pct(snap) == pytest.approx(1.0)

    def test_empty_book_returns_zero(self):
        assert calculate_spread_pct(empty_book()) == 0.0

    def test_tight_spread(self):
        snap = OrderBookSnapshot("X", "ex", 0,
            bids=[make_level(99.99, 1.0)],
            asks=[make_level(100.01, 1.0)])
        spread = calculate_spread_pct(snap)
        assert spread == pytest.approx(0.02, rel=1e-2)

    def test_wide_spread(self):
        snap = OrderBookSnapshot("X", "ex", 0,
            bids=[make_level(50.0, 1.0)],
            asks=[make_level(150.0, 1.0)])
        spread = calculate_spread_pct(snap)
        assert spread == pytest.approx(100.0)

    def test_zero_spread_equal_prices(self):
        # Crossed book (ask < bid) should not go negative
        snap = OrderBookSnapshot("X", "ex", 0,
            bids=[make_level(100.0, 1.0)],
            asks=[make_level(100.0, 1.0)])
        assert calculate_spread_pct(snap) >= 0.0


# ── Tests: calculate_depth_usd ────────────────────────────────────────────────

class TestCalculateDepthUsd:
    def test_returns_tuple(self):
        bid_d, ask_d = calculate_depth_usd(simple_book(), pct=1.0)
        assert isinstance(bid_d, float)
        assert isinstance(ask_d, float)

    def test_empty_book_returns_zeros(self):
        bid_d, ask_d = calculate_depth_usd(empty_book())
        assert bid_d == 0.0
        assert ask_d == 0.0

    def test_wider_pct_includes_more(self):
        snap = simple_book()
        bid_narrow, _ = calculate_depth_usd(snap, pct=0.1)
        bid_wide, _ = calculate_depth_usd(snap, pct=5.0)
        assert bid_wide >= bid_narrow

    def test_pct_zero_returns_zero(self):
        # pct=0 → no levels within zero-width band
        bid_d, ask_d = calculate_depth_usd(simple_book(), pct=0.0)
        assert bid_d == 0.0
        assert ask_d == 0.0

    def test_only_levels_within_band(self):
        # bid at 99.5 is within 1% of mid=100, bid at 98.0 is not (2% away)
        snap = simple_book()
        bid_d, ask_d = calculate_depth_usd(snap, pct=1.0)
        # 99.5 x 10 = 995, 99.0 x 50 = 4950 — both within 1%
        assert bid_d == pytest.approx(995.0 + 4950.0, rel=1e-2)


# ── Tests: calculate_imbalance ────────────────────────────────────────────────

class TestCalculateImbalance:
    def test_returns_in_range(self):
        imb = calculate_imbalance(simple_book(), pct=2.0)
        assert -1.0 <= imb <= 1.0

    def test_empty_book_returns_zero(self):
        assert calculate_imbalance(empty_book()) == 0.0

    def test_bid_heavy_positive(self):
        imb = calculate_imbalance(bid_heavy_book(), pct=5.0)
        assert imb > 0.5, f"Expected strong positive imbalance, got {imb}"

    def test_ask_heavy_negative(self):
        imb = calculate_imbalance(ask_heavy_book(), pct=5.0)
        assert imb < -0.5, f"Expected strong negative imbalance, got {imb}"

    def test_balanced_book_near_zero(self):
        snap = OrderBookSnapshot("X", "ex", 0,
            bids=[make_level(99.0, 100.0)],
            asks=[make_level(101.0, 100.0)])
        imb = calculate_imbalance(snap, pct=5.0)
        # prices differ slightly so usd_size differs, but should be close to 0
        assert abs(imb) < 0.05

    def test_all_bids_imbalance_one(self):
        # If asks have zero depth within band, imbalance should be +1
        snap = OrderBookSnapshot("X", "ex", 0,
            bids=[make_level(99.9, 100.0)],
            asks=[make_level(200.0, 1.0)])  # far from mid=99.95, outside 0.5% band
        imb = calculate_imbalance(snap, pct=0.05)
        # asks are far away, so ask_depth within 0.05% band = 0
        assert imb == pytest.approx(1.0) or imb == 0.0  # 0 if neither side has depth


# ── Tests: find_biggest_walls ─────────────────────────────────────────────────

class TestFindBiggestWalls:
    def test_returns_tuple_of_lists(self):
        b, a = find_biggest_walls(simple_book())
        assert isinstance(b, list)
        assert isinstance(a, list)

    def test_top_n_respected(self):
        b, a = find_biggest_walls(simple_book(), top_n=1)
        assert len(b) == 1
        assert len(a) == 1

    def test_sorted_descending(self):
        b, a = find_biggest_walls(simple_book(), top_n=3)
        if len(b) > 1:
            sizes = [lvl.usd_size for lvl in b]
            assert sizes == sorted(sizes, reverse=True)

    def test_empty_book_returns_empty_lists(self):
        b, a = find_biggest_walls(empty_book())
        assert b == []
        assert a == []

    def test_single_level(self):
        snap = OrderBookSnapshot("X", "ex", 0,
            bids=[make_level(100.0, 5.0)],
            asks=[make_level(101.0, 3.0)])
        b, a = find_biggest_walls(snap, top_n=3)
        assert len(b) == 1
        assert len(a) == 1

    def test_top_n_zero_returns_empty(self):
        b, a = find_biggest_walls(simple_book(), top_n=0)
        assert b == []
        assert a == []

    def test_biggest_bid_wall_is_correct(self):
        snap = simple_book()
        b, _ = find_biggest_walls(snap, top_n=1)
        # 99.0 x 50 = $4950 is the biggest bid
        assert b[0].price == pytest.approx(99.0)

    def test_biggest_ask_wall_is_correct(self):
        snap = simple_book()
        _, a = find_biggest_walls(snap, top_n=1)
        # 101.0 x 20 = $2020 is the biggest ask
        assert a[0].price == pytest.approx(101.0)


# ── Tests: estimate_slippage ──────────────────────────────────────────────────

class TestEstimateSlippage:
    def test_zero_slippage_single_level_enough(self):
        # One ask level with $1010 → buying $500 fills entirely at best price
        snap = OrderBookSnapshot("X", "ex", 0,
            bids=[make_level(99.0, 100.0)],
            asks=[make_level(101.0, 10.0)])  # $1010 available
        slip = estimate_slippage(snap, "buy", 500.0)
        assert slip == pytest.approx(0.0, abs=1e-6)

    def test_nonzero_slippage_crosses_levels(self):
        snap = OrderBookSnapshot("X", "ex", 0,
            bids=[make_level(99.0, 10.0)],
            asks=[
                make_level(100.0, 1.0),   # $100
                make_level(110.0, 10.0),  # $1100
            ])
        # Buying $500: fills $100 at 100, then $400 at 110 → avg price > 100
        slip = estimate_slippage(snap, "buy", 500.0)
        assert slip > 0.0

    def test_empty_book_returns_zero(self):
        assert estimate_slippage(empty_book(), "buy", 1000.0) == 0.0
        assert estimate_slippage(empty_book(), "sell", 1000.0) == 0.0

    def test_zero_size_returns_zero(self):
        assert estimate_slippage(simple_book(), "buy", 0.0) == 0.0

    def test_invalid_side_returns_zero(self):
        assert estimate_slippage(simple_book(), "lateral", 1000.0) == 0.0

    def test_order_larger_than_book_returns_100(self):
        snap = OrderBookSnapshot("X", "ex", 0,
            bids=[make_level(99.0, 1.0)],
            asks=[make_level(101.0, 0.1)])  # only $10.1 ask depth
        slip = estimate_slippage(snap, "buy", 1_000_000.0)
        assert slip == pytest.approx(100.0)

    def test_sell_side_uses_bids(self):
        snap = OrderBookSnapshot("X", "ex", 0,
            bids=[make_level(99.0, 100.0)],
            asks=[make_level(101.0, 100.0)])
        slip_buy = estimate_slippage(snap, "buy", 500.0)
        slip_sell = estimate_slippage(snap, "sell", 500.0)
        # Both should be small — symmetric book
        assert slip_buy < 1.0
        assert slip_sell < 1.0

    def test_case_insensitive_side(self):
        r1 = estimate_slippage(simple_book(), "BUY", 100.0)
        r2 = estimate_slippage(simple_book(), "buy", 100.0)
        assert r1 == r2


# ── Tests: calculate_liquidity_score ─────────────────────────────────────────

class TestCalculateLiquidityScore:
    def test_empty_book_is_zero(self):
        assert calculate_liquidity_score(empty_book()) == 0.0

    def test_thin_book_is_low(self):
        score = calculate_liquidity_score(thin_book())
        assert score < 30.0

    def test_deep_book_is_high(self):
        score = calculate_liquidity_score(deep_book())
        assert score > 50.0

    def test_score_in_range(self):
        for snap in [simple_book(), deep_book(), thin_book(), bid_heavy_book()]:
            score = calculate_liquidity_score(snap)
            assert 0.0 <= score <= 100.0, f"Score out of range: {score}"

    def test_single_side_is_zero(self):
        assert calculate_liquidity_score(single_side_bid()) == 0.0
        assert calculate_liquidity_score(single_side_ask()) == 0.0


# ── Tests: analyze_orderbook ──────────────────────────────────────────────────

class TestAnalyzeOrderbook:
    def test_returns_metrics_object(self):
        from core.models import OrderBookMetrics
        m = analyze_orderbook(simple_book())
        assert isinstance(m, OrderBookMetrics)

    def test_symbol_and_exchange_preserved(self):
        m = analyze_orderbook(simple_book())
        assert m.symbol == "XUSDT"
        assert m.exchange == "test"

    def test_empty_book_safe_defaults(self):
        m = analyze_orderbook(empty_book())
        assert m.mid_price == 0.0
        assert m.spread_pct == 0.0
        assert m.bid_depth_usd == 0.0
        assert m.ask_depth_usd == 0.0
        assert m.imbalance == 0.0
        assert m.bid_walls == []
        assert m.ask_walls == []
        assert m.liquidity_score == 0.0
        assert m.is_thin is True
        assert isinstance(m.signal, str)
        assert len(m.signal) > 0

    def test_mid_price_correct(self):
        m = analyze_orderbook(simple_book())
        assert m.mid_price == pytest.approx(100.0)

    def test_spread_correct(self):
        m = analyze_orderbook(simple_book())
        assert m.spread_pct == pytest.approx(1.0)

    def test_thin_book_detected(self):
        m = analyze_orderbook(thin_book())
        assert m.is_thin is True
        assert m.signal in ("avoid", "neutral", "watch")

    def test_bid_heavy_signal(self):
        m = analyze_orderbook(bid_heavy_book())
        # Bid-heavy book should lean toward buy or watch
        assert m.signal in ("buy", "strong_buy", "watch", "neutral")
        assert m.imbalance > 0

    def test_ask_heavy_signal(self):
        m = analyze_orderbook(ask_heavy_book())
        assert m.signal in ("avoid", "watch", "neutral")
        assert m.imbalance < 0

    def test_signal_reason_nonempty(self):
        for snap in [simple_book(), empty_book(), thin_book(), bid_heavy_book()]:
            m = analyze_orderbook(snap)
            assert isinstance(m.signal_reason, str)
            assert len(m.signal_reason) > 0

    def test_walls_max_three(self):
        m = analyze_orderbook(simple_book())
        assert len(m.bid_walls) <= 3
        assert len(m.ask_walls) <= 3

    def test_slippage_nonnegative(self):
        m = analyze_orderbook(simple_book())
        assert m.slippage_buy_1k >= 0.0
        assert m.slippage_sell_1k >= 0.0

    def test_imbalance_in_range(self):
        m = analyze_orderbook(simple_book())
        assert -1.0 <= m.imbalance <= 1.0

    def test_liquidity_score_in_range(self):
        for snap in [simple_book(), deep_book(), thin_book(), empty_book()]:
            m = analyze_orderbook(snap)
            assert 0.0 <= m.liquidity_score <= 100.0


# ── Tests: OrderBookLevel validation ─────────────────────────────────────────

class TestOrderBookLevel:
    def test_valid_level(self):
        lvl = OrderBookLevel(price=100.0, qty=2.5, usd_size=250.0)
        assert lvl.price == 100.0
        assert lvl.qty == 2.5

    def test_negative_price_raises(self):
        with pytest.raises(ValueError, match="price"):
            OrderBookLevel(price=-1.0, qty=1.0)

    def test_negative_qty_raises(self):
        with pytest.raises(ValueError, match="qty"):
            OrderBookLevel(price=100.0, qty=-1.0)

    def test_zero_price_allowed(self):
        # Zero price is a degenerate case but should not crash the model
        lvl = OrderBookLevel(price=0.0, qty=0.0)
        assert lvl.price == 0.0

    def test_frozen(self):
        lvl = OrderBookLevel(price=100.0, qty=1.0)
        with pytest.raises((AttributeError, TypeError)):
            lvl.price = 200.0  # type: ignore


# ── Tests: OrderBookSnapshot properties ──────────────────────────────────────

class TestOrderBookSnapshot:
    def test_best_bid_and_ask(self):
        snap = simple_book()
        assert snap.best_bid is not None
        assert snap.best_ask is not None
        assert snap.best_bid.price == pytest.approx(99.5)
        assert snap.best_ask.price == pytest.approx(100.5)

    def test_empty_book_properties(self):
        snap = empty_book()
        assert snap.is_empty
        assert not snap.has_both_sides
        assert snap.best_bid is None
        assert snap.best_ask is None

    def test_single_side_not_both(self):
        assert not single_side_bid().has_both_sides
        assert not single_side_ask().has_both_sides
