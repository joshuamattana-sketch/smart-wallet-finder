"""
services/gold_bot_decision_engine.py
--------------------------------------
LM76A — Gold Bot decision engine V1 (pure, transparent, no ML).

Reads recent XAUUSD candles + a few market metrics and emits a structured
TradeIdea: LONG / SHORT / NO_TRADE with reasons and blockers. No MT5, no I/O,
no network here — the probe script feeds candles/spread/position state in and
prints/executes the result through the existing LM75 risk + trade-loop guards.

V1 detectors:
  - momentum continuation (SMA alignment + recent momentum)
  - breakout watch (price pressed against the recent high/low) — watch only
  - scalp momentum (faster, smaller SL/TP, demo-only)
  - no-trade (insufficient data / wide spread / chaotic / open position / low confidence)

Everything is deterministic given the same inputs.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any

# ── Tunable thresholds (transparent, conservative) ───────────────────────────
SMA_SHORT = 9
SMA_LONG = 21
LOOKBACK = 30            # recent high/low window
MOM_BARS = 5            # momentum lookback (bars)
SCALP_MOM_BARS = 3      # faster momentum for scalp
VOL_BARS = 14          # average range window
NEAR_EXTREME_POINTS = 150   # "pressed against" the recent high/low (points)
CHAOTIC_RANGE_MULT = 3.0    # last-bar range > this x avg range = chaotic

# Spread ceilings (points). Scalp is stricter — it can't pay a wide spread.
MAX_SPREAD_POINTS = {"safe": 60, "balanced": 60, "aggressive": 80,
                     "experimental": 60, "scalp": 35}
# Minimum confidence to act, by mode.
MIN_CONFIDENCE = {"safe": 60, "balanced": 55, "aggressive": 50,
                  "experimental": 55, "scalp": 50}
# SL/TP suggestions (points).
SLTP_POINTS = {"safe": (300, 600), "balanced": (300, 600), "aggressive": (300, 600),
               "experimental": (300, 600), "scalp": (120, 180)}


@dataclass
class MarketState:
    last_close: float
    sma_short: float
    sma_long: float
    recent_high: float
    recent_low: float
    body_strength: float       # 0–1 (last candle body / range)
    momentum_points: float     # close - close[-MOM] in points
    volatility_points: float   # avg(high-low) over VOL_BARS in points
    spread_points: float
    dist_from_high_points: float
    dist_from_low_points: float
    bars: int

    def summary(self) -> str:
        trend = ("up" if self.last_close > self.sma_short > self.sma_long
                 else "down" if self.last_close < self.sma_short < self.sma_long
                 else "mixed")
        return (f"trend {trend} | close {self.last_close:.2f} | "
                f"SMA{SMA_SHORT} {self.sma_short:.2f} / SMA{SMA_LONG} {self.sma_long:.2f} | "
                f"mom {self.momentum_points:+.0f}pt | vol {self.volatility_points:.0f}pt | "
                f"spread {self.spread_points:.0f}pt")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TradeIdea:
    decision_id: str
    timestamp: str
    symbol: str
    timeframe: str
    decision: str               # LONG | SHORT | NO_TRADE
    strategy: str               # momentum | breakout_watch | scalp_momentum | no_trade | manage_existing
    confidence: int             # 0–100
    entry_reference_price: float | None
    sl_points: int | None
    tp_points: int | None
    risk_mode: str
    reasons: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    market_state: dict[str, Any] = field(default_factory=dict)
    should_execute_demo: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def compute_market_state(candles: list[dict], *, spread_points: float, point: float) -> MarketState:
    """Build the market metrics from normalized candles (oldest→newest)."""
    closes = [c["close"] for c in candles]
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    n = len(candles)
    p = point if point and point > 0 else 0.01

    last = candles[-1]
    last_close = closes[-1]
    sma_short = _mean(closes[-SMA_SHORT:])
    sma_long = _mean(closes[-SMA_LONG:])
    recent_high = max(highs[-LOOKBACK:])
    recent_low = min(lows[-LOOKBACK:])

    rng = (last["high"] - last["low"])
    body_strength = abs(last["close"] - last["open"]) / rng if rng > 0 else 0.0

    mom_idx = max(0, n - 1 - MOM_BARS)
    momentum_points = (last_close - closes[mom_idx]) / p

    ranges = [(h - l) for h, l in zip(highs[-VOL_BARS:], lows[-VOL_BARS:])]
    volatility_points = (_mean(ranges) / p) if ranges else 0.0

    return MarketState(
        last_close=last_close, sma_short=sma_short, sma_long=sma_long,
        recent_high=recent_high, recent_low=recent_low,
        body_strength=round(body_strength, 3), momentum_points=round(momentum_points, 1),
        volatility_points=round(volatility_points, 1), spread_points=round(spread_points, 1),
        dist_from_high_points=round((recent_high - last_close) / p, 1),
        dist_from_low_points=round((last_close - recent_low) / p, 1),
        bars=n,
    )


def _new_idea(symbol, timeframe, risk_mode, ms: MarketState | None, **kw) -> TradeIdea:
    return TradeIdea(
        decision_id=uuid.uuid4().hex[:12],
        timestamp=datetime.now(timezone.utc).isoformat(),
        symbol=symbol, timeframe=timeframe, risk_mode=risk_mode,
        market_state=ms.to_dict() if ms else {},
        **kw,
    )


def decide(
    candles: list[dict],
    *,
    symbol: str,
    timeframe: str,
    risk_mode: str,
    spread_points: float,
    point: float,
    has_open_position: bool,
) -> TradeIdea:
    """
    Produce a TradeIdea from candles + context. NO_TRADE is the safe default;
    LONG/SHORT only when a detector fires with enough confidence and no blocker.
    """
    mode = risk_mode.lower()
    sl_pts, tp_pts = SLTP_POINTS.get(mode, SLTP_POINTS["balanced"])
    max_spread = MAX_SPREAD_POINTS.get(mode, 60)
    min_conf = MIN_CONFIDENCE.get(mode, 55)

    # ── Hard blockers first (fail closed to NO_TRADE) ─────────────────────────
    if len(candles) < SMA_LONG:
        return _new_idea(symbol, timeframe, mode, None, decision="NO_TRADE",
                         strategy="no_trade", confidence=0, entry_reference_price=None,
                         sl_points=None, tp_points=None,
                         blockers=[f"insufficient candles ({len(candles)} < {SMA_LONG})."])

    ms = compute_market_state(candles, spread_points=spread_points, point=point)
    entry = ms.last_close

    if has_open_position:
        return _new_idea(symbol, timeframe, mode, ms, decision="NO_TRADE",
                         strategy="manage_existing", confidence=0, entry_reference_price=entry,
                         sl_points=None, tp_points=None,
                         reasons=["An XAUUSD position is already open."],
                         blockers=["position stacking disabled in V1 - manage the existing trade."])

    blockers: list[str] = []
    if ms.spread_points > max_spread:
        blockers.append(f"spread {ms.spread_points:.0f}pt > max {max_spread}pt for {mode}.")
    # Chaotic filter: last bar range vs average range.
    last_range_pts = (candles[-1]["high"] - candles[-1]["low"]) / (point or 0.01)
    if ms.volatility_points > 0 and last_range_pts > CHAOTIC_RANGE_MULT * ms.volatility_points:
        blockers.append("last candle range is chaotic (>3x average) - standing aside.")

    if blockers:
        return _new_idea(symbol, timeframe, mode, ms, decision="NO_TRADE",
                         strategy="no_trade", confidence=0, entry_reference_price=entry,
                         sl_points=None, tp_points=None, blockers=blockers)

    # ── Detectors ─────────────────────────────────────────────────────────────
    mom_bars = SCALP_MOM_BARS if mode == "scalp" else MOM_BARS
    mom_idx = max(0, len(candles) - 1 - mom_bars)
    momentum = (ms.last_close - candles[mom_idx]["close"]) / (point or 0.01)

    bull_aligned = ms.last_close > ms.sma_short > ms.sma_long
    bear_aligned = ms.last_close < ms.sma_short < ms.sma_long

    reasons: list[str] = []
    decision = "NO_TRADE"
    strategy = "no_trade"
    confidence = 40

    if bull_aligned and momentum > 0:
        decision, strategy = "LONG", ("scalp_momentum" if mode == "scalp" else "momentum")
        confidence = _score(aligned=True, momentum=momentum, body=ms.body_strength)
        reasons = [f"close above SMA{SMA_SHORT} above SMA{SMA_LONG} (uptrend stack).",
                   f"momentum +{momentum:.0f}pt over last {mom_bars} bars.",
                   f"last candle body strength {ms.body_strength:.2f}."]
    elif bear_aligned and momentum < 0:
        decision, strategy = "SHORT", ("scalp_momentum" if mode == "scalp" else "momentum")
        confidence = _score(aligned=True, momentum=momentum, body=ms.body_strength)
        reasons = [f"close below SMA{SMA_SHORT} below SMA{SMA_LONG} (downtrend stack).",
                   f"momentum {momentum:.0f}pt over last {mom_bars} bars.",
                   f"last candle body strength {ms.body_strength:.2f}."]
    else:
        # Breakout watch — pressed against a recent extreme but no clean trend stack.
        if ms.dist_from_high_points <= NEAR_EXTREME_POINTS:
            strategy = "breakout_watch"
            reasons = [f"price {ms.dist_from_high_points:.0f}pt under recent high - "
                       "possible bullish breakout, waiting for confirmation."]
        elif ms.dist_from_low_points <= NEAR_EXTREME_POINTS:
            strategy = "breakout_watch"
            reasons = [f"price {ms.dist_from_low_points:.0f}pt above recent low - "
                       "possible bearish breakdown, waiting for confirmation."]
        else:
            reasons = ["no trend stack and not near an extreme - no edge."]
        return _new_idea(symbol, timeframe, mode, ms, decision="NO_TRADE",
                         strategy=strategy, confidence=confidence, entry_reference_price=entry,
                         sl_points=None, tp_points=None, reasons=reasons)

    # Confidence gate.
    if confidence < min_conf:
        return _new_idea(symbol, timeframe, mode, ms, decision="NO_TRADE",
                         strategy="no_trade", confidence=confidence, entry_reference_price=entry,
                         sl_points=None, tp_points=None, reasons=reasons,
                         blockers=[f"confidence {confidence} < min {min_conf} for {mode}."])

    return _new_idea(symbol, timeframe, mode, ms, decision=decision, strategy=strategy,
                     confidence=confidence, entry_reference_price=entry,
                     sl_points=sl_pts, tp_points=tp_pts, reasons=reasons,
                     should_execute_demo=True)


def _score(*, aligned: bool, momentum: float, body: float) -> int:
    """Transparent 0–100 confidence: base + alignment + momentum + body strength."""
    score = 45
    if aligned:
        score += 20
    score += min(20, abs(momentum) / 20.0)   # 400pt momentum → +20
    score += min(15, body * 15.0)            # full-body candle → +15
    return int(max(0, min(100, round(score))))
