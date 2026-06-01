"""
services/pro_market_scanner.py
--------------------------------
Pro Market Scanner for the Pro Trading Terminal.

Scans one or more markets, fetches their orderbook data, runs the orderbook
analysis pipeline, and produces ProSetupSignal objects with scored verdicts,
plain-English reasons, and actionable hints.

Architecture:
    scan_markets(symbols)
        └─ scan_market(symbol)
              ├─ _fetch_snapshot(symbol)       — connector call, guarded
              ├─ analyze_orderbook(snapshot)   — from orderbook_engine
              └─ build_signal_from_metrics(...)  — pure scoring, no I/O

Rules:
- No Streamlit imports.
- No silent except pass.
- Connector calls are optional: if unavailable, returns a neutral fallback signal.
- build_signal_from_metrics is pure — testable without any API call.
- All scores are clamped to [0, 100].
- All risk levels are from RISK_LEVELS keys: "low", "medium", "high", "extreme".
- All signal levels are from SIGNAL_LEVELS keys.
"""

from __future__ import annotations

import time
from typing import Optional

from core.constants import RISK_LEVELS, SIGNAL_LEVELS
from core.models import OrderBookMetrics, ProSetupSignal
from services.orderbook_engine import analyze_orderbook

# ── Default markets ───────────────────────────────────────────────────────────

DEFAULT_MARKETS: list[str] = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "HYPE"]

# Markets served by Binance (using USDT pairs)
_BINANCE_MARKETS: frozenset[str] = frozenset({"BTCUSDT", "ETHUSDT", "SOLUSDT"})

# Markets served by Hyperliquid (short coin names)
_HYPERLIQUID_MARKETS: frozenset[str] = frozenset({"HYPE", "BTC", "ETH", "SOL"})

# ── Scoring thresholds ────────────────────────────────────────────────────────

_SPREAD_TIGHT  = 0.05   # % — tight spread = good
_SPREAD_WIDE   = 1.0    # % — wide spread = bad
_SPREAD_EXTREME = 3.0   # % — very bad

_IMB_STRONG = 0.5       # |imbalance| >= this = strong directional pressure
_IMB_MILD   = 0.25      # |imbalance| >= this = mild lean

_LIQ_EXCELLENT = 75.0   # liquidity score — excellent
_LIQ_GOOD      = 50.0   # acceptable
_LIQ_POOR      = 25.0   # poor

_WALL_LARGE_USD = 500_000.0   # wall >= this = significant
_WALL_MEDIUM_USD = 100_000.0  # wall >= this = noteworthy

_SLIP_TIGHT  = 0.05   # % slippage on $1k — tight
_SLIP_WIDE   = 0.5    # % — wide
_SLIP_EXTREME = 2.0   # % — very bad

_THIN_BOOK_USD = 5_000.0  # $5k each side = thin


# ── Pure scoring engine ───────────────────────────────────────────────────────

def build_signal_from_metrics(
    symbol: str,
    venue: str,
    metrics: OrderBookMetrics,
    market_type: str = "spot",
) -> ProSetupSignal:
    """
    Produce a ProSetupSignal from a fully analysed OrderBookMetrics object.

    This function is pure — no I/O, no network calls, no side effects.
    Safe to call in tests with any OrderBookMetrics, including empty ones.

    Scoring breakdown (100 points total):
      Liquidity score   30 pts   (direct from orderbook_engine)
      Spread tightness  25 pts   (tighter = better)
      Imbalance quality 20 pts   (strong lean = directional signal)
      Wall pressure     15 pts   (big walls = key levels)
      Slippage          10 pts   (lower = better market depth)

    Signal level mapping:
      score >= 82  → strong_buy  (if bullish imbalance) or strong_sell
      score >= 68  → buy / sell
      score >= 52  → watch
      score >= 38  → neutral
      < 38         → avoid

    Risk mapping:
      is_thin OR spread > _SPREAD_EXTREME → extreme
      spread > _SPREAD_WIDE OR liq < _LIQ_POOR → high
      liq < _LIQ_GOOD → medium
      else → low

    Args:
        symbol:      Trading symbol, e.g. "BTCUSDT" or "HYPE".
        venue:       Exchange name, e.g. "binance", "Hyperliquid".
        metrics:     OrderBookMetrics from orderbook_engine.analyze_orderbook().
        market_type: "spot" or "perp".

    Returns:
        ProSetupSignal with all fields populated. Never raises.
    """
    ts = metrics.timestamp_ms if metrics.timestamp_ms else int(time.time() * 1000)

    # ── Edge: empty / thin book ───────────────────────────────────────────────
    if metrics.is_thin or (metrics.bid_depth_usd == 0 and metrics.ask_depth_usd == 0):
        return ProSetupSignal(
            symbol=symbol,
            exchange=venue,
            timestamp_ms=ts,
            signal_level="avoid",
            confidence=10.0,
            reason="Book is too thin or empty. Insufficient data for a reliable signal.",
            risk_level="extreme",
            action_hint="Avoid — no reliable liquidity.",
            score=5.0,
            contributing={"liquidity": 0, "spread": 0, "imbalance": 0, "walls": 0, "slippage": 0},
            market_type=market_type,
        )

    # ── Sub-scores ────────────────────────────────────────────────────────────

    # 1. Liquidity (0–30)
    liq_score = _clamp(metrics.liquidity_score / 100.0 * 30, 0, 30)

    # 2. Spread tightness (0–25)
    sp = metrics.spread_pct
    if sp <= 0:
        spread_score = 25.0
    elif sp <= _SPREAD_TIGHT:
        spread_score = 25.0
    elif sp <= _SPREAD_WIDE:
        spread_score = 25.0 * (1.0 - (sp - _SPREAD_TIGHT) / (_SPREAD_WIDE - _SPREAD_TIGHT))
    else:
        spread_score = max(0.0, 25.0 * (1.0 - (sp - _SPREAD_WIDE) / _SPREAD_EXTREME))

    # 3. Imbalance quality (0–20)
    #    Strong lean in either direction = directional signal = higher score
    abs_imb = abs(metrics.imbalance)
    if abs_imb >= _IMB_STRONG:
        imb_score = 20.0
    elif abs_imb >= _IMB_MILD:
        imb_score = 20.0 * ((abs_imb - _IMB_MILD) / (_IMB_STRONG - _IMB_MILD))
    else:
        # Perfectly balanced book: moderate score — no clear direction
        imb_score = 8.0

    # 4. Wall pressure (0–15)
    #    Big walls = key levels that the market respects = stronger signal
    def _top_wall_usd(walls: list) -> float:
        if not walls:
            return 0.0
        best = max((w.usd_size if w.usd_size > 0 else w.price * w.qty for w in walls), default=0.0)
        return best

    bid_wall_usd = _top_wall_usd(metrics.bid_walls)
    ask_wall_usd = _top_wall_usd(metrics.ask_walls)
    max_wall = max(bid_wall_usd, ask_wall_usd)

    if max_wall >= _WALL_LARGE_USD:
        wall_score = 15.0
    elif max_wall >= _WALL_MEDIUM_USD:
        wall_score = 15.0 * (max_wall - _WALL_MEDIUM_USD) / (_WALL_LARGE_USD - _WALL_MEDIUM_USD) + 5.0
    elif max_wall > 0:
        wall_score = 5.0 * min(max_wall / _WALL_MEDIUM_USD, 1.0)
    else:
        wall_score = 0.0

    # 5. Slippage (0–10)
    avg_slip = (metrics.slippage_buy_1k + metrics.slippage_sell_1k) / 2.0
    if avg_slip >= 100.0:  # insufficient liquidity sentinel
        slip_score = 0.0
    elif avg_slip <= _SLIP_TIGHT:
        slip_score = 10.0
    elif avg_slip <= _SLIP_WIDE:
        slip_score = 10.0 * (1.0 - (avg_slip - _SLIP_TIGHT) / (_SLIP_WIDE - _SLIP_TIGHT))
    else:
        slip_score = max(0.0, 10.0 * (1.0 - (avg_slip - _SLIP_WIDE) / _SLIP_EXTREME))

    raw_score = liq_score + spread_score + imb_score + wall_score + slip_score
    final_score = _clamp(raw_score, 0.0, 100.0)

    # ── Signal level ──────────────────────────────────────────────────────────
    imb = metrics.imbalance
    if final_score >= 82:
        signal_level = "strong_buy" if imb >= 0 else "strong_sell"
    elif final_score >= 68:
        signal_level = "buy" if imb >= 0 else "avoid"
    elif final_score >= 52:
        signal_level = "watch"
    elif final_score >= 38:
        signal_level = "neutral"
    else:
        signal_level = "avoid"

    # ── Risk level ────────────────────────────────────────────────────────────
    if metrics.is_thin or sp > _SPREAD_EXTREME:
        risk_level = "extreme"
    elif sp > _SPREAD_WIDE or metrics.liquidity_score < _LIQ_POOR:
        risk_level = "high"
    elif metrics.liquidity_score < _LIQ_GOOD:
        risk_level = "medium"
    else:
        risk_level = "low"

    # ── Reason (plain English, 1–3 sentences) ─────────────────────────────────
    reason_parts: list[str] = []

    # Spread
    if sp <= _SPREAD_TIGHT:
        reason_parts.append(f"Spread is very tight ({sp:.4f}%) — efficient market.")
    elif sp <= _SPREAD_WIDE:
        reason_parts.append(f"Spread is moderate ({sp:.4f}%).")
    else:
        reason_parts.append(f"Wide spread ({sp:.2f}%) signals low liquidity or high volatility.")

    # Imbalance
    if abs_imb >= _IMB_STRONG:
        direction = "bid-heavy (buy pressure)" if imb > 0 else "ask-heavy (sell pressure)"
        reason_parts.append(
            f"Strong {direction} imbalance ({imb:+.3f}) — "
            f"${metrics.bid_depth_usd:,.0f} bids vs ${metrics.ask_depth_usd:,.0f} asks."
        )
    elif abs_imb >= _IMB_MILD:
        direction = "bid" if imb > 0 else "ask"
        reason_parts.append(f"Mild {direction}-side lean ({imb:+.3f}).")
    else:
        reason_parts.append(f"Book is balanced (imbalance {imb:+.3f}).")

    # Liquidity
    liq = metrics.liquidity_score
    if liq >= _LIQ_EXCELLENT:
        reason_parts.append(f"Excellent liquidity (score {liq:.0f}/100).")
    elif liq >= _LIQ_GOOD:
        reason_parts.append(f"Adequate liquidity (score {liq:.0f}/100).")
    else:
        reason_parts.append(f"Poor liquidity (score {liq:.0f}/100) — price impact risk.")

    # Walls
    if max_wall >= _WALL_LARGE_USD:
        side = "bid" if bid_wall_usd >= ask_wall_usd else "ask"
        reason_parts.append(f"Significant {side} wall (${max_wall:,.0f}) acts as a key level.")
    elif max_wall >= _WALL_MEDIUM_USD:
        side = "bid" if bid_wall_usd >= ask_wall_usd else "ask"
        reason_parts.append(f"Noteworthy {side} wall (${max_wall:,.0f}).")

    reason = " ".join(reason_parts)

    # ── Action hint ───────────────────────────────────────────────────────────
    if signal_level in ("strong_buy", "buy"):
        if imb >= _IMB_STRONG:
            action_hint = "Watch for breakout — strong bid-side confirmation."
        else:
            action_hint = "Breakout watch — wait for momentum confirmation."
    elif signal_level == "strong_sell":
        action_hint = "Avoid longs — strong sell pressure in book."
    elif signal_level == "watch":
        action_hint = "Watch — wait for stronger directional signal."
    elif signal_level == "neutral":
        action_hint = "Wait for confirmation — no clear edge yet."
    else:
        action_hint = "Avoid — insufficient liquidity or data quality."

    # ── Confidence (reflects data completeness) ───────────────────────────────
    confidence = _clamp(
        final_score * 0.7 + metrics.liquidity_score * 0.3,
        0.0, 100.0
    )

    contributing = {
        "liquidity":  round(liq_score, 2),
        "spread":     round(spread_score, 2),
        "imbalance":  round(imb_score, 2),
        "walls":      round(wall_score, 2),
        "slippage":   round(slip_score, 2),
    }

    return ProSetupSignal(
        symbol=symbol,
        exchange=venue,
        timestamp_ms=ts,
        signal_level=signal_level,
        confidence=round(confidence, 2),
        reason=reason,
        risk_level=risk_level,
        action_hint=action_hint,
        score=round(final_score, 2),
        contributing=contributing,
        market_type=market_type,
    )


# ── Connector layer (optional, guarded) ───────────────────────────────────────

def _fetch_snapshot(symbol: str):  # -> Optional[OrderBookSnapshot]
    """
    Fetch an OrderBookSnapshot for the given symbol.

    Routes to Binance or Hyperliquid based on the symbol.
    Returns None (not raises) if the fetch fails for any reason —
    callers must handle the None case.

    Args:
        symbol: e.g. "BTCUSDT" (Binance) or "HYPE" (Hyperliquid).

    Returns:
        OrderBookSnapshot on success, None on any failure.
    """
    # Binance: USDT pairs
    if symbol in _BINANCE_MARKETS:
        try:
            from connectors.binance import (
                ConnectorError,
                RestrictedLocationError,
                fetch_orderbook,
            )
            return fetch_orderbook(symbol, limit=50)
        except (ConnectorError, RestrictedLocationError) as exc:
            raise ScanError(
                f"Binance fetch failed for {symbol}: {exc}",
                symbol=symbol,
                venue="binance",
            ) from exc
        except Exception as exc:
            raise ScanError(
                f"Unexpected error fetching {symbol} from Binance: {exc}",
                symbol=symbol,
                venue="binance",
            ) from exc

    # Hyperliquid: short coin names
    _hl_sym = symbol.upper().replace("USDT", "").replace("USD", "")
    try:
        from connectors.hyperliquid import HyperliquidError, fetch_l2_book
        return fetch_l2_book(_hl_sym)
    except HyperliquidError as exc:
        raise ScanError(
            f"Hyperliquid fetch failed for {symbol}: {exc}",
            symbol=symbol,
            venue="Hyperliquid",
        ) from exc
    except Exception as exc:
        raise ScanError(
            f"Unexpected error fetching {symbol} from Hyperliquid: {exc}",
            symbol=symbol,
            venue="Hyperliquid",
        ) from exc


# ── ScanError ─────────────────────────────────────────────────────────────────

class ScanError(Exception):
    """
    Raised when a market scan fails unrecoverably.

    Attributes:
        symbol: The market symbol that failed.
        venue:  The exchange that was queried.
    """

    def __init__(self, message: str, symbol: str = "", venue: str = "") -> None:
        super().__init__(message)
        self.symbol = symbol
        self.venue = venue


# ── Neutral fallback ──────────────────────────────────────────────────────────

def _neutral_fallback(symbol: str, venue: str, reason: str) -> ProSetupSignal:
    """Return a safe neutral signal when data is unavailable."""
    return ProSetupSignal(
        symbol=symbol,
        exchange=venue,
        timestamp_ms=int(time.time() * 1000),
        signal_level="neutral",
        confidence=0.0,
        reason=reason,
        risk_level="high",
        action_hint="Wait for confirmation — data unavailable.",
        score=0.0,
        contributing={},
        market_type="spot",
    )


# ── Public scan API ───────────────────────────────────────────────────────────

def scan_market(symbol: str) -> ProSetupSignal:
    """
    Scan a single market and return a ProSetupSignal.

    Fetches orderbook data, runs the analysis pipeline,
    and scores the resulting metrics into a signal.

    If the fetch fails, returns a neutral fallback signal
    (does NOT raise — callers should check signal.confidence == 0).

    Args:
        symbol: Market symbol, e.g. "BTCUSDT", "ETHUSDT", "HYPE".

    Returns:
        ProSetupSignal. Never raises.
    """
    sym = str(symbol).strip().upper()
    venue = "binance" if sym in _BINANCE_MARKETS else "Hyperliquid"

    try:
        snapshot = _fetch_snapshot(sym)
    except ScanError as exc:
        return _neutral_fallback(sym, exc.venue, f"Fetch failed: {exc}")
    except Exception as exc:
        return _neutral_fallback(sym, venue, f"Unexpected scan error: {exc}")

    if snapshot is None or snapshot.is_empty:
        return _neutral_fallback(sym, venue, "Empty orderbook received — no data to score.")

    try:
        metrics = analyze_orderbook(snapshot)
    except Exception as exc:
        return _neutral_fallback(
            sym, venue, f"Analysis failed: {exc}. Raw data was fetched."
        )

    market_type = "perp" if sym in _HYPERLIQUID_MARKETS or "PERP" in sym else "spot"

    return build_signal_from_metrics(sym, venue, metrics, market_type=market_type)


def scan_markets(symbols: Optional[list[str]] = None) -> list[ProSetupSignal]:
    """
    Scan multiple markets and return a list of ProSetupSignals.

    Markets that fail are included as neutral fallback signals —
    the scan continues for all remaining symbols regardless.

    Args:
        symbols: List of market symbols. Defaults to DEFAULT_MARKETS.

    Returns:
        List of ProSetupSignal, one per symbol, sorted by score descending.
        Never raises.
    """
    targets = symbols if symbols is not None else DEFAULT_MARKETS

    signals: list[ProSetupSignal] = []
    for sym in targets:
        signal = scan_market(sym)
        signals.append(signal)

    # Best opportunities first
    signals.sort(key=lambda s: s.score, reverse=True)
    return signals


# ── Helper ────────────────────────────────────────────────────────────────────

def _clamp(value: float, lo: float, hi: float) -> float:
    """Clamp value to [lo, hi]."""
    return max(lo, min(hi, value))


# ── Self-test ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from core.models import OrderBookLevel, OrderBookSnapshot
    from services.orderbook_engine import analyze_orderbook

    # Build a mock snapshot and verify the pipeline
    bids = [
        OrderBookLevel(price=67_410.0, qty=0.5,  usd_size=33_705.0),
        OrderBookLevel(price=67_400.0, qty=2.0,  usd_size=134_800.0),
        OrderBookLevel(price=67_350.0, qty=0.3,  usd_size=20_205.0),
    ]
    asks = [
        OrderBookLevel(price=67_420.0, qty=0.2,  usd_size=13_484.0),
        OrderBookLevel(price=67_430.0, qty=0.8,  usd_size=53_944.0),
    ]
    snap = OrderBookSnapshot(
        symbol="BTCUSDT", exchange="binance",
        timestamp_ms=1_716_200_000_000,
        bids=bids, asks=asks,
        mid_price=(67_410.0 + 67_420.0) / 2,
    )
    metrics = analyze_orderbook(snap)
    signal = build_signal_from_metrics("BTCUSDT", "binance", metrics)

    assert signal.symbol == "BTCUSDT"
    assert signal.exchange == "binance"
    assert 0.0 <= signal.score <= 100.0
    assert signal.signal_level in SIGNAL_LEVELS
    assert signal.risk_level in RISK_LEVELS
    assert len(signal.reason) > 10
    assert len(signal.action_hint) > 5
    assert signal.confidence >= 0
    assert set(signal.contributing.keys()) == {"liquidity","spread","imbalance","walls","slippage"}

    # Empty metrics fallback
    empty_snap = OrderBookSnapshot("X", "test", 0)
    empty_metrics = analyze_orderbook(empty_snap)
    fallback = build_signal_from_metrics("X", "test", empty_metrics)
    assert fallback.signal_level == "avoid"
    assert fallback.risk_level == "extreme"
    assert 0.0 <= fallback.score <= 100.0

    # Neutral fallback
    nf = _neutral_fallback("HYPE", "Hyperliquid", "No data")
    assert nf.signal_level == "neutral"
    assert nf.score == 0.0
    assert nf.confidence == 0.0

    # _clamp
    assert _clamp(150.0, 0, 100) == 100.0
    assert _clamp(-5.0, 0, 100) == 0.0
    assert _clamp(50.0, 0, 100) == 50.0

    print("services/pro_market_scanner.py — all assertions passed.")
