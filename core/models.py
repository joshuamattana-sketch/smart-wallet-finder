"""
core/models.py
--------------
Dataclasses for the Pro Trading Terminal and Meme Alpha Beta.

Rules:
- No Streamlit imports.
- No network calls.
- No external dependencies beyond stdlib.
- All fields have explicit types and sensible defaults.
- Dataclasses are immutable where order-book integrity matters (frozen=True
  on snapshot levels), mutable where the engine needs to fill them in.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ── Orderbook primitives ───────────────────────────────────────────────────────

@dataclass(frozen=True)
class OrderBookLevel:
    """
    A single price level in an order book.

    Attributes:
        price:    Price of the level in quote currency (e.g. USDT).
        qty:      Quantity of base asset at this level.
        usd_size: Notional value in USD (price * qty). Pre-computed by connector.
    """
    price: float
    qty: float
    usd_size: float = 0.0

    def __post_init__(self) -> None:
        if self.price < 0:
            raise ValueError(f"OrderBookLevel.price must be >= 0, got {self.price}")
        if self.qty < 0:
            raise ValueError(f"OrderBookLevel.qty must be >= 0, got {self.qty}")


@dataclass
class OrderBookSnapshot:
    """
    Full order book snapshot for a single market at a point in time.

    Attributes:
        symbol:       Trading pair, e.g. "BTCUSDT".
        exchange:     Source exchange, e.g. "binance", "bybit".
        timestamp_ms: Unix timestamp in milliseconds when snapshot was taken.
        bids:         List of bid levels, sorted descending by price (best bid first).
        asks:         List of ask levels, sorted ascending by price (best ask first).
        mid_price:    Pre-computed mid price ((best_bid + best_ask) / 2). 0 if empty.
        chain:        Chain identifier for on-chain books, e.g. "solana". None for CEX.
        token_mint:   Token mint address for Solana DEX books. None for CEX.
    """
    symbol: str
    exchange: str
    timestamp_ms: int
    bids: list[OrderBookLevel] = field(default_factory=list)
    asks: list[OrderBookLevel] = field(default_factory=list)
    mid_price: float = 0.0
    chain: Optional[str] = None
    token_mint: Optional[str] = None

    @property
    def best_bid(self) -> Optional[OrderBookLevel]:
        return self.bids[0] if self.bids else None

    @property
    def best_ask(self) -> Optional[OrderBookLevel]:
        return self.asks[0] if self.asks else None

    @property
    def is_empty(self) -> bool:
        return not self.bids and not self.asks

    @property
    def has_both_sides(self) -> bool:
        return bool(self.bids) and bool(self.asks)


@dataclass
class OrderBookMetrics:
    """
    Derived metrics computed from an OrderBookSnapshot.

    All fields are safe defaults (0 / empty) when the book is thin or empty.

    Attributes:
        symbol:          Trading pair.
        exchange:        Source exchange.
        timestamp_ms:    Snapshot timestamp in ms.
        mid_price:       (best_bid + best_ask) / 2.
        spread_pct:      (ask - bid) / mid * 100.
        bid_depth_usd:   Total USD size on bids within `depth_pct` of mid.
        ask_depth_usd:   Total USD size on asks within `depth_pct` of mid.
        depth_pct:       The percentage band used for depth calc (e.g. 0.5 = 0.5%).
        imbalance:       (bid_depth - ask_depth) / (bid_depth + ask_depth).
                         +1 = all bids, -1 = all asks, 0 = balanced.
        bid_walls:       Top-N biggest single bid levels (price, qty, usd_size).
        ask_walls:       Top-N biggest single ask levels (price, qty, usd_size).
        slippage_buy_1k:  Estimated slippage % to buy $1,000 worth.
        slippage_sell_1k: Estimated slippage % to sell $1,000 worth.
        liquidity_score: 0–100 score. Higher = deeper, tighter, safer book.
        is_thin:         True when total depth < $5,000 on either side.
        signal:          Human-readable signal derived from metrics.
        signal_reason:   One-sentence explanation.
    """
    symbol: str
    exchange: str
    timestamp_ms: int
    mid_price: float = 0.0
    spread_pct: float = 0.0
    bid_depth_usd: float = 0.0
    ask_depth_usd: float = 0.0
    depth_pct: float = 0.5
    imbalance: float = 0.0
    bid_walls: list[OrderBookLevel] = field(default_factory=list)
    ask_walls: list[OrderBookLevel] = field(default_factory=list)
    slippage_buy_1k: float = 0.0
    slippage_sell_1k: float = 0.0
    liquidity_score: float = 0.0
    is_thin: bool = False
    signal: str = "neutral"
    signal_reason: str = ""


# ── Market snapshot ────────────────────────────────────────────────────────────

@dataclass
class MarketSnapshot:
    """
    Combined market data point for a symbol.

    Aggregates price, volume, change data alongside orderbook metrics.
    Used as the input to Pro Setup Score calculations.

    Attributes:
        symbol:        Trading pair, e.g. "BTCUSDT".
        exchange:      Source exchange.
        timestamp_ms:  Unix timestamp in milliseconds.
        price:         Last traded price.
        price_1h_ago:  Price 1 hour ago. 0 if unavailable.
        price_24h_ago: Price 24 hours ago. 0 if unavailable.
        volume_24h:    24-hour trading volume in USD.
        change_1h_pct: 1-hour price change percentage.
        change_24h_pct:24-hour price change percentage.
        high_24h:      24-hour high price. 0 if unavailable.
        low_24h:       24-hour low price. 0 if unavailable.
        funding_rate:  Current perpetual funding rate. 0 for spot.
        open_interest: Open interest in USD for perp markets. 0 for spot.
        ob_metrics:    Order book metrics, if available.
        market_type:   "spot", "perp", "futures", or "option".
        chain:         Chain for on-chain markets. None for CEX.
    """
    symbol: str
    exchange: str
    timestamp_ms: int
    price: float = 0.0
    price_1h_ago: float = 0.0
    price_24h_ago: float = 0.0
    volume_24h: float = 0.0
    change_1h_pct: float = 0.0
    change_24h_pct: float = 0.0
    high_24h: float = 0.0
    low_24h: float = 0.0
    funding_rate: float = 0.0
    open_interest: float = 0.0
    ob_metrics: Optional[OrderBookMetrics] = None
    market_type: str = "spot"
    chain: Optional[str] = None

    @property
    def has_orderbook(self) -> bool:
        return self.ob_metrics is not None

    @property
    def is_trending_up_1h(self) -> bool:
        return self.change_1h_pct > 0.5

    @property
    def is_trending_down_1h(self) -> bool:
        return self.change_1h_pct < -0.5


# ── Signals ───────────────────────────────────────────────────────────────────

@dataclass
class ProSetupSignal:
    """
    A Pro Terminal setup signal with full reasoning.

    Every signal must have a level, reason, risk, and action hint.
    No signal without data backing it.

    Attributes:
        symbol:         Trading pair.
        exchange:       Source exchange.
        timestamp_ms:   When signal was generated.
        signal_level:   One of SIGNAL_LEVELS keys: "strong_buy", "buy",
                        "watch", "neutral", "avoid", "strong_sell".
        confidence:     0–100. Data quality + confluence score.
        reason:         Plain-English reason, max 2 sentences.
        risk_level:     One of RISK_LEVELS keys: "low", "medium", "high", "extreme".
        action_hint:    Single clearest next step for the user.
        score:          Raw confluence score 0–100 before discretization.
        contributing:   Dict of sub-scores that fed into the signal.
                        e.g. {"structure": 70, "imbalance": 60, "momentum": 80}
        market_type:    "spot" or "perp".
        invalidated_at: If the signal was invalidated, timestamp in ms. None if still valid.
    """
    symbol: str
    exchange: str
    timestamp_ms: int
    signal_level: str = "neutral"
    confidence: float = 0.0
    reason: str = ""
    risk_level: str = "medium"
    action_hint: str = ""
    score: float = 0.0
    contributing: dict[str, float] = field(default_factory=dict)
    market_type: str = "spot"
    invalidated_at: Optional[int] = None

    @property
    def is_valid(self) -> bool:
        return self.invalidated_at is None

    @property
    def is_actionable(self) -> bool:
        return self.signal_level in ("strong_buy", "buy", "strong_sell") and self.confidence >= 60


@dataclass
class AlphaSignal:
    """
    A Meme Alpha Beta signal for a Solana wallet or token.

    Used by the Smart Wallet and Token Finder engines.

    Attributes:
        wallet_address: Full Solana wallet address, if wallet-based. None for token-only.
        token_mint:     Solana token mint address, if token-based. None for wallet-only.
        token_symbol:   Short token symbol or display name, if known.
        timestamp_ms:   When signal was generated.
        signal_type:    "early_buy", "repeated_early", "watch", "avoid", "paper_first".
        score:          0–100 alpha score.
        early_rank:     Position among earliest buyers (1 = first). None if unknown.
        verdict:        Short verdict label, e.g. "Alpha Scout", "Worth watching".
        reason:         Plain-English reason, max 2 sentences.
        risk_level:     "low", "medium", "high", "extreme".
        action_hint:    Single clearest next step.
        liquidity_usd:  Token liquidity at time of signal. 0 if unknown.
        already_saved:  True if wallet is already in the user's watchlist.
        source:         Data source that generated the signal, e.g. "solscan", "helius".
    """
    wallet_address: Optional[str]
    token_mint: Optional[str]
    timestamp_ms: int
    token_symbol: str = "?"
    signal_type: str = "watch"
    score: float = 0.0
    early_rank: Optional[int] = None
    verdict: str = ""
    reason: str = ""
    risk_level: str = "medium"
    action_hint: str = ""
    liquidity_usd: float = 0.0
    already_saved: bool = False
    source: str = "unknown"

    @property
    def is_early_buyer(self) -> bool:
        return self.early_rank is not None and self.early_rank <= 10

    @property
    def is_copy_candidate(self) -> bool:
        return self.score >= 80 and self.signal_type in ("early_buy", "repeated_early")


if __name__ == "__main__":
    # Smoke tests
    lvl = OrderBookLevel(price=100.0, qty=1.5, usd_size=150.0)
    assert lvl.price == 100.0

    snap = OrderBookSnapshot(
        symbol="BTCUSDT", exchange="binance", timestamp_ms=1_000_000,
        bids=[OrderBookLevel(99.0, 2.0, 198.0)],
        asks=[OrderBookLevel(101.0, 1.0, 101.0)],
    )
    assert snap.best_bid is not None
    assert snap.best_ask is not None
    assert snap.has_both_sides
    assert not snap.is_empty

    empty = OrderBookSnapshot("X", "y", 0)
    assert empty.is_empty
    assert not empty.has_both_sides
    assert empty.best_bid is None

    sig = ProSetupSignal("BTCUSDT", "binance", 1_000_000,
                         signal_level="buy", confidence=75.0,
                         reason="Strong bid wall at key level.",
                         risk_level="medium", action_hint="Watch for breakout.")
    assert sig.is_valid
    assert sig.is_actionable

    alpha = AlphaSignal(wallet_address="GS4CU5SNVQnaR" * 2,
                        token_mint="So11111111111111111111111111111111111111112",
                        timestamp_ms=1_000_000, score=85.0,
                        early_rank=3, signal_type="early_buy")
    assert alpha.is_early_buyer
    assert alpha.is_copy_candidate

    try:
        OrderBookLevel(price=-1.0, qty=1.0)
        assert False, "Should have raised"
    except ValueError:
        pass

    print("core/models.py — all assertions passed.")
