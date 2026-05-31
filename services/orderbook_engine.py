"""
services/orderbook_engine.py
----------------------------
Pure-Python orderbook analysis for the Pro Trading Terminal.

Rules:
- No Streamlit imports.
- No network calls.
- No external dependencies beyond stdlib and core/.
- All functions accept an OrderBookSnapshot and return typed values.
- Never raise on malformed/empty books — return safe defaults.
- Every function is independently callable and testable.
"""

from __future__ import annotations

import math
from typing import Optional

from core.models import OrderBookLevel, OrderBookMetrics, OrderBookSnapshot
from core.formatting import safe_float


# ── Internal helpers ───────────────────────────────────────────────────────────

def _levels_within_pct(
    levels: list[OrderBookLevel],
    reference_price: float,
    pct: float,
) -> list[OrderBookLevel]:
    """
    Return levels whose price is within `pct`% of reference_price.

    Args:
        levels:          List of OrderBookLevel objects.
        reference_price: Mid price or last price to measure from.
        pct:             Percentage band, e.g. 0.5 for 0.5%.

    Returns:
        Filtered list of levels within the band.
    """
    if reference_price <= 0 or pct <= 0:
        return []
    band = reference_price * (pct / 100.0)
    return [lvl for lvl in levels if abs(lvl.price - reference_price) <= band]


def _total_usd(levels: list[OrderBookLevel]) -> float:
    """Sum the usd_size of a list of levels. Falls back to price * qty if usd_size is 0."""
    total = 0.0
    for lvl in levels:
        size = lvl.usd_size if lvl.usd_size > 0 else (lvl.price * lvl.qty)
        total += size
    return total


# ── Public API ─────────────────────────────────────────────────────────────────

def calculate_mid_price(snapshot: OrderBookSnapshot) -> float:
    """
    Calculate the mid price as (best_bid + best_ask) / 2.

    Args:
        snapshot: OrderBookSnapshot with at least one bid and one ask.

    Returns:
        Mid price as float. Returns 0.0 if either side is empty.

    Examples:
        >>> from core.models import OrderBookLevel, OrderBookSnapshot
        >>> snap = OrderBookSnapshot("X", "ex", 0,
        ...     bids=[OrderBookLevel(99.0, 1.0)],
        ...     asks=[OrderBookLevel(101.0, 1.0)])
        >>> calculate_mid_price(snap)
        100.0
    """
    if not snapshot.has_both_sides:
        return 0.0
    return (snapshot.best_bid.price + snapshot.best_ask.price) / 2.0


def calculate_spread_pct(snapshot: OrderBookSnapshot) -> float:
    """
    Calculate the bid-ask spread as a percentage of the mid price.

    spread_pct = (ask - bid) / mid * 100

    Args:
        snapshot: OrderBookSnapshot.

    Returns:
        Spread percentage. Returns 0.0 if book is empty or mid is 0.

    Examples:
        >>> snap = OrderBookSnapshot("X", "ex", 0,
        ...     bids=[OrderBookLevel(99.0, 1.0)],
        ...     asks=[OrderBookLevel(101.0, 1.0)])
        >>> calculate_spread_pct(snap)
        2.0
    """
    if not snapshot.has_both_sides:
        return 0.0
    mid = calculate_mid_price(snapshot)
    if mid <= 0:
        return 0.0
    spread = snapshot.best_ask.price - snapshot.best_bid.price
    if spread < 0:
        return 0.0  # Crossed book — data error, treat as 0
    return (spread / mid) * 100.0


def calculate_depth_usd(
    snapshot: OrderBookSnapshot,
    pct: float = 0.5,
) -> tuple[float, float]:
    """
    Calculate total USD liquidity depth on each side within `pct`% of mid.

    Args:
        snapshot: OrderBookSnapshot.
        pct:      Percentage band from mid price to include. Default 0.5%.

    Returns:
        Tuple of (bid_depth_usd, ask_depth_usd).
        Both are 0.0 if book is empty or mid is 0.

    Examples:
        >>> snap = OrderBookSnapshot("X", "ex", 0,
        ...     bids=[OrderBookLevel(99.5, 2.0, 199.0), OrderBookLevel(90.0, 5.0, 450.0)],
        ...     asks=[OrderBookLevel(100.5, 1.0, 100.5)])
        >>> bid_d, ask_d = calculate_depth_usd(snap, pct=1.0)
        >>> bid_d  # only 99.5 is within 1% of mid=100.0
        199.0
        >>> ask_d
        100.5
    """
    if not snapshot.has_both_sides:
        return 0.0, 0.0
    mid = calculate_mid_price(snapshot)
    if mid <= 0:
        return 0.0, 0.0
    bid_levels = _levels_within_pct(snapshot.bids, mid, pct)
    ask_levels = _levels_within_pct(snapshot.asks, mid, pct)
    return _total_usd(bid_levels), _total_usd(ask_levels)


def calculate_imbalance(
    snapshot: OrderBookSnapshot,
    pct: float = 0.5,
) -> float:
    """
    Calculate order book imbalance within `pct`% of mid.

    imbalance = (bid_depth - ask_depth) / (bid_depth + ask_depth)

    Result ranges from -1.0 (all asks, sell pressure) to +1.0 (all bids, buy pressure).
    0.0 means perfectly balanced.

    Args:
        snapshot: OrderBookSnapshot.
        pct:      Percentage band for depth calculation. Default 0.5%.

    Returns:
        Imbalance ratio as float in [-1.0, +1.0]. Returns 0.0 if total depth is 0.

    Examples:
        >>> snap = OrderBookSnapshot("X", "ex", 0,
        ...     bids=[OrderBookLevel(99.5, 3.0, 300.0)],
        ...     asks=[OrderBookLevel(100.5, 1.0, 100.0)])
        >>> round(calculate_imbalance(snap, pct=1.0), 2)
        0.5
    """
    bid_d, ask_d = calculate_depth_usd(snapshot, pct)
    total = bid_d + ask_d
    if total <= 0:
        return 0.0
    return (bid_d - ask_d) / total


def find_biggest_walls(
    snapshot: OrderBookSnapshot,
    top_n: int = 3,
) -> tuple[list[OrderBookLevel], list[OrderBookLevel]]:
    """
    Find the largest individual price levels (walls) on each side.

    A "wall" is a single level with an unusually large USD size — often a sign
    of a large limit order acting as support or resistance.

    Args:
        snapshot: OrderBookSnapshot.
        top_n:    Number of top walls to return per side. Default 3.

    Returns:
        Tuple of (bid_walls, ask_walls), each sorted descending by usd_size.
        Both lists may be shorter than top_n if the book has fewer levels.

    Examples:
        >>> snap = OrderBookSnapshot("X", "ex", 0,
        ...     bids=[OrderBookLevel(99.0, 1.0, 99.0), OrderBookLevel(98.0, 10.0, 980.0)],
        ...     asks=[OrderBookLevel(101.0, 5.0, 505.0), OrderBookLevel(102.0, 1.0, 102.0)])
        >>> bid_walls, ask_walls = find_biggest_walls(snap, top_n=1)
        >>> bid_walls[0].price
        98.0
        >>> ask_walls[0].price
        101.0
    """
    if top_n < 1:
        return [], []

    def _size(lvl: OrderBookLevel) -> float:
        return lvl.usd_size if lvl.usd_size > 0 else (lvl.price * lvl.qty)

    sorted_bids = sorted(snapshot.bids, key=_size, reverse=True)[:top_n]
    sorted_asks = sorted(snapshot.asks, key=_size, reverse=True)[:top_n]
    return sorted_bids, sorted_asks


def estimate_slippage(
    snapshot: OrderBookSnapshot,
    side: str,
    usd_size: float,
) -> float:
    """
    Estimate the average slippage percentage to fill a market order of `usd_size` USD.

    Walks the order book levels greedily until the full size is filled or the
    book is exhausted. Returns the volume-weighted average fill price vs the
    best price as a percentage.

    Args:
        snapshot: OrderBookSnapshot.
        side:     "buy" (walks asks) or "sell" (walks bids).
        usd_size: Size of the market order in USD. Must be > 0.

    Returns:
        Slippage as a percentage. 0.0 if book is empty, size is 0, or book
        has insufficient liquidity (returns 100.0 as a hard cap signal).

    Examples:
        >>> snap = OrderBookSnapshot("X", "ex", 0,
        ...     bids=[OrderBookLevel(99.0, 10.0, 990.0)],
        ...     asks=[OrderBookLevel(101.0, 10.0, 1010.0)])
        >>> estimate_slippage(snap, "buy", 500.0)
        0.0
    """
    side = side.lower().strip()
    if side not in ("buy", "sell"):
        return 0.0
    if usd_size <= 0:
        return 0.0

    levels = snapshot.asks if side == "buy" else snapshot.bids
    if not levels:
        return 0.0

    best_price = levels[0].price
    if best_price <= 0:
        return 0.0

    remaining_usd = usd_size
    total_qty = 0.0
    total_cost = 0.0

    for lvl in levels:
        lvl_usd = lvl.usd_size if lvl.usd_size > 0 else (lvl.price * lvl.qty)
        if lvl_usd <= 0:
            continue
        fill_usd = min(remaining_usd, lvl_usd)
        fill_qty = (fill_usd / lvl.price) if lvl.price > 0 else 0.0
        total_qty += fill_qty
        total_cost += fill_usd
        remaining_usd -= fill_usd
        if remaining_usd <= 0:
            break

    if remaining_usd > 0:
        # Could not fill the full order — extreme slippage signal
        return 100.0

    if total_qty <= 0:
        return 0.0

    avg_price = total_cost / total_qty
    slippage = abs(avg_price - best_price) / best_price * 100.0
    return round(slippage, 4)


def calculate_liquidity_score(snapshot: OrderBookSnapshot) -> float:
    """
    Calculate a 0–100 liquidity score for the order book.

    Higher score = deeper book, tighter spread, more balanced, less slippage.

    Scoring breakdown (max 100 points):
    - Spread tightness:   up to 30 pts  (0% spread = 30, >=5% spread = 0)
    - Bid depth USD:      up to 25 pts  (>=$1M = 25, log-scaled below)
    - Ask depth USD:      up to 25 pts  (>=$1M = 25, log-scaled below)
    - Imbalance balance:  up to 10 pts  (0 imbalance = 10, ±1 = 0)
    - Slippage on $1k:    up to 10 pts  (0% slippage = 10, >=2% = 0)

    Args:
        snapshot: OrderBookSnapshot.

    Returns:
        Score from 0.0 to 100.0. Returns 0.0 for empty books.
    """
    if not snapshot.has_both_sides:
        return 0.0

    score = 0.0

    # ── Spread tightness (0–30 pts) ──────────────────────────────
    spread = calculate_spread_pct(snapshot)
    if spread <= 0:
        spread_score = 30.0
    elif spread >= 5.0:
        spread_score = 0.0
    else:
        spread_score = 30.0 * (1.0 - spread / 5.0)
    score += spread_score

    # ── Depth (0–25 pts each side) ───────────────────────────────
    bid_d, ask_d = calculate_depth_usd(snapshot, pct=0.5)
    target_depth = 1_000_000.0  # $1M = full score

    def _depth_score(depth_usd: float, max_pts: float = 25.0) -> float:
        if depth_usd <= 0:
            return 0.0
        if depth_usd >= target_depth:
            return max_pts
        # Log scale: $10k ≈ half score, $1M = full score
        ratio = math.log10(max(depth_usd, 1)) / math.log10(target_depth)
        return max(0.0, min(max_pts, ratio * max_pts))

    score += _depth_score(bid_d)
    score += _depth_score(ask_d)

    # ── Imbalance balance (0–10 pts) ─────────────────────────────
    imbalance = calculate_imbalance(snapshot, pct=0.5)
    balance_score = 10.0 * (1.0 - abs(imbalance))
    score += max(0.0, balance_score)

    # ── Slippage on $1k (0–10 pts) ───────────────────────────────
    slip = estimate_slippage(snapshot, "buy", 1_000.0)
    if slip >= 2.0 or slip >= 100.0:
        slip_score = 0.0
    else:
        slip_score = 10.0 * (1.0 - slip / 2.0)
    score += max(0.0, slip_score)

    return round(min(100.0, max(0.0, score)), 2)


def analyze_orderbook(snapshot: OrderBookSnapshot) -> OrderBookMetrics:
    """
    Run the full orderbook analysis pipeline and return an OrderBookMetrics object.

    This is the main entry point for the Pro Terminal and any service that needs
    a complete picture of a market's book.

    Args:
        snapshot: OrderBookSnapshot from any connector.

    Returns:
        OrderBookMetrics with all computed fields populated.
        Safe defaults (zeros, empty lists) are returned for empty/broken books.
    """
    mid = calculate_mid_price(snapshot)
    spread = calculate_spread_pct(snapshot)
    bid_d, ask_d = calculate_depth_usd(snapshot, pct=0.5)
    imbalance = calculate_imbalance(snapshot, pct=0.5)
    bid_walls, ask_walls = find_biggest_walls(snapshot, top_n=3)
    slip_buy = estimate_slippage(snapshot, "buy", 1_000.0)
    slip_sell = estimate_slippage(snapshot, "sell", 1_000.0)
    liq_score = calculate_liquidity_score(snapshot)

    is_thin = (bid_d < 5_000 or ask_d < 5_000)

    # ── Derive signal from metrics ────────────────────────────────────────────
    signal, reason = _derive_signal(imbalance, spread, liq_score, is_thin, bid_d, ask_d)

    return OrderBookMetrics(
        symbol=snapshot.symbol,
        exchange=snapshot.exchange,
        timestamp_ms=snapshot.timestamp_ms,
        mid_price=round(mid, 8),
        spread_pct=round(spread, 4),
        bid_depth_usd=round(bid_d, 2),
        ask_depth_usd=round(ask_d, 2),
        depth_pct=0.5,
        imbalance=round(imbalance, 4),
        bid_walls=bid_walls,
        ask_walls=ask_walls,
        slippage_buy_1k=round(slip_buy, 4),
        slippage_sell_1k=round(slip_sell, 4),
        liquidity_score=liq_score,
        is_thin=is_thin,
        signal=signal,
        signal_reason=reason,
    )


def _derive_signal(
    imbalance: float,
    spread_pct: float,
    liq_score: float,
    is_thin: bool,
    bid_d: float,
    ask_d: float,
) -> tuple[str, str]:
    """
    Map orderbook metrics to a signal level and plain-English reason.

    Returns:
        Tuple of (signal_level_key, reason_string).
    """
    if is_thin:
        return "avoid", "Book is too thin — less than $5k depth on one side. High risk of manipulation."

    if liq_score < 20:
        return "avoid", f"Poor liquidity (score {liq_score:.0f}/100) and wide spread of {spread_pct:.2f}%. Not safe to trade."

    if imbalance >= 0.6:
        return "buy", f"Strong bid-side imbalance ({imbalance:+.2f}). ${bid_d:,.0f} bids vs ${ask_d:,.0f} asks within 0.5% of mid."

    if imbalance <= -0.6:
        return "avoid", f"Strong ask-side pressure ({imbalance:+.2f}). ${ask_d:,.0f} asks vs ${bid_d:,.0f} bids within 0.5% of mid."

    if imbalance >= 0.3:
        return "watch", f"Slight bid-side lean ({imbalance:+.2f}). Book is liquid (score {liq_score:.0f}/100)."

    if imbalance <= -0.3:
        return "watch", f"Slight ask-side lean ({imbalance:+.2f}). Monitor for breakout or rejection."

    return "neutral", f"Balanced book (imbalance {imbalance:+.2f}, score {liq_score:.0f}/100, spread {spread_pct:.3f}%)."


if __name__ == "__main__":
    # Smoke test with a simple book
    from core.models import OrderBookLevel, OrderBookSnapshot

    bids = [
        OrderBookLevel(99.5, 10.0, 995.0),
        OrderBookLevel(99.0, 50.0, 4950.0),
        OrderBookLevel(98.0, 5.0, 490.0),
    ]
    asks = [
        OrderBookLevel(100.5, 8.0, 804.0),
        OrderBookLevel(101.0, 20.0, 2020.0),
        OrderBookLevel(102.0, 3.0, 306.0),
    ]
    snap = OrderBookSnapshot("XUSDT", "test", 0, bids=bids, asks=asks)

    mid = calculate_mid_price(snap)
    assert mid == 100.0, f"Expected 100.0, got {mid}"

    spread = calculate_spread_pct(snap)
    assert spread == 1.0, f"Expected 1.0, got {spread}"

    bid_d, ask_d = calculate_depth_usd(snap, pct=1.0)
    assert bid_d > 0
    assert ask_d > 0

    imb = calculate_imbalance(snap, pct=1.0)
    assert -1.0 <= imb <= 1.0

    b_walls, a_walls = find_biggest_walls(snap, top_n=2)
    assert len(b_walls) == 2
    assert b_walls[0].price == 99.0  # biggest bid wall

    slip = estimate_slippage(snap, "buy", 500.0)
    assert 0.0 <= slip < 100.0

    liq = calculate_liquidity_score(snap)
    assert 0.0 <= liq <= 100.0

    metrics = analyze_orderbook(snap)
    assert metrics.symbol == "XUSDT"
    assert metrics.mid_price == 100.0
    assert metrics.spread_pct == 1.0
    assert isinstance(metrics.signal, str)
    assert len(metrics.bid_walls) <= 3

    # Empty book
    empty = OrderBookSnapshot("X", "ex", 0)
    empty_metrics = analyze_orderbook(empty)
    assert empty_metrics.mid_price == 0.0
    assert empty_metrics.liquidity_score == 0.0
    assert empty_metrics.is_thin

    print("services/orderbook_engine.py — all assertions passed.")
