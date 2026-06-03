"""
services/whale_alert_engine.py
--------------------------------
Smart Whale Alert Engine for the Pro Trading Terminal.

Goes beyond raw size detection — evaluates event context (orderbook
imbalance, funding, open interest, market structure proximity) to
produce meaningful, low-noise alerts.

Alert types (ordered by severity):
    aggressive_long_opened    — large long with bullish context
    aggressive_short_opened   — large short with bearish context
    position_increased        — existing large position growing
    position_reduced          — whale scaling out (partial close)
    whale_exit                — large position fully closed
    crowded_leverage_risk     — many leveraged positions stacking same side
    liquidation_risk          — position near liquidation price
    smart_accumulation        — stealth buy pattern without orderbook trace
    possible_trap             — size/leverage diverges from market structure

Rules:
- No Streamlit imports.
- No network calls.
- No external dependencies beyond stdlib.
- No silent except pass.
- All scores are clamped to [0, 100].
- Timestamps are Unix milliseconds.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

# ── Alert type constants ──────────────────────────────────────────────────────

ALERT_AGGRESSIVE_LONG    = "aggressive_long_opened"
ALERT_AGGRESSIVE_SHORT   = "aggressive_short_opened"
ALERT_POSITION_INCREASED = "position_increased"
ALERT_POSITION_REDUCED   = "position_reduced"
ALERT_WHALE_EXIT         = "whale_exit"
ALERT_CROWDED_LEVERAGE   = "crowded_leverage_risk"
ALERT_LIQUIDATION_RISK   = "liquidation_risk"
ALERT_SMART_ACCUMULATION = "smart_accumulation"
ALERT_POSSIBLE_TRAP      = "possible_trap"

VALID_ALERT_TYPES: frozenset[str] = frozenset({
    ALERT_AGGRESSIVE_LONG,
    ALERT_AGGRESSIVE_SHORT,
    ALERT_POSITION_INCREASED,
    ALERT_POSITION_REDUCED,
    ALERT_WHALE_EXIT,
    ALERT_CROWDED_LEVERAGE,
    ALERT_LIQUIDATION_RISK,
    ALERT_SMART_ACCUMULATION,
    ALERT_POSSIBLE_TRAP,
})

SIDE_LONG  = "long"
SIDE_SHORT = "short"
SIDE_EXIT  = "exit"
SIDE_NONE  = "none"

RISK_LOW     = "low"
RISK_MEDIUM  = "medium"
RISK_HIGH    = "high"
RISK_EXTREME = "extreme"
VALID_RISKS: frozenset[str] = frozenset({RISK_LOW, RISK_MEDIUM, RISK_HIGH, RISK_EXTREME})

# Size thresholds (USD)
_SIZE_MEDIUM  =    500_000   # $500k
_SIZE_HIGH    =  2_000_000   # $2M
_SIZE_EXTREME = 10_000_000   # $10M

# Leverage thresholds
_LEV_MEDIUM  =  5
_LEV_HIGH    = 10
_LEV_EXTREME = 20


# ── Market context helper ─────────────────────────────────────────────────────

@dataclass
class MarketContext:
    """
    Optional market context fed into smart alert evaluation.

    All fields default to neutral/unknown — provide only what is available.

    Attributes:
        imbalance:          Orderbook imbalance [-1, +1]. +1 = all bids. 0 = unknown.
        liquidity_score:    0–100 from orderbook engine. 0 = unknown.
        funding_rate:       Perpetual funding rate. Positive = longs pay. 0 = unknown.
        oi_change_pct:      Open interest 24h change in %. 0 = unknown.
        near_breakout:      True if price is near a key breakout level.
        near_support:       True if price is near a key support level.
        near_resistance:    True if price is near a key resistance level.
        bid_wall_usd:       Largest single bid wall in USD. 0 = none detected.
        ask_wall_usd:       Largest single ask wall in USD. 0 = none detected.
        repeated_trader:    True if this wallet/account has acted similarly before.
    """
    imbalance:        float = 0.0
    liquidity_score:  float = 0.0
    funding_rate:     float = 0.0
    oi_change_pct:    float = 0.0
    near_breakout:    bool  = False
    near_support:     bool  = False
    near_resistance:  bool  = False
    bid_wall_usd:     float = 0.0
    ask_wall_usd:     float = 0.0
    repeated_trader:  bool  = False


# ── WhaleAlert dataclass ──────────────────────────────────────────────────────

@dataclass
class WhaleAlert:
    """
    A smart whale or leverage alert with full context.

    Attributes:
        symbol:           Trading pair, e.g. "BTCUSDT" or "HYPE".
        venue:            Exchange, e.g. "binance", "Hyperliquid".
        alert_type:       One of VALID_ALERT_TYPES.
        side:             "long", "short", "exit", or "none".
        size_usd:         Notional position/trade size in USD.
        leverage:         Leverage multiplier. None = spot.
        risk:             "low", "medium", "high", or "extreme".
        confidence:       0–100. How confident we are this is a real signal.
        importance_score: 0–100. Combined signal strength (size + context + risk).
        context:          Short plain-English context summary (1 sentence).
        reasons:          List of reasons supporting the alert.
        warnings:         List of caution notes that reduce confidence.
        action:           Suggested next step for the trader.
        timestamp_ms:     Unix timestamp in milliseconds.
        price:            Asset price at alert time. 0 if unknown.
        wallet:           Wallet address or identifier. Empty if unknown.
        tags:             Additional classification labels.
        raw:              Original raw event for debugging.
    """
    symbol:           str
    venue:            str
    alert_type:       str
    side:             str
    size_usd:         float
    risk:             str
    message:          str
    timestamp_ms:     int
    confidence:       float = 50.0
    importance_score: float = 0.0
    context:          str = ""
    reasons:          list[str] = field(default_factory=list)
    warnings:         list[str] = field(default_factory=list)
    action:           str = "Watch"
    leverage:         Optional[float] = None
    price:            float = 0.0
    wallet:           str = ""
    tags:             list[str] = field(default_factory=list)
    raw:              dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.alert_type not in VALID_ALERT_TYPES:
            raise ValueError(
                f"Invalid alert_type '{self.alert_type}'. "
                f"Must be one of: {sorted(VALID_ALERT_TYPES)}"
            )
        if self.risk not in VALID_RISKS:
            raise ValueError(
                f"Invalid risk '{self.risk}'. Must be one of: {sorted(VALID_RISKS)}"
            )
        if self.size_usd < 0:
            raise ValueError(f"size_usd must be >= 0, got {self.size_usd}")
        if self.leverage is not None and self.leverage < 0:
            raise ValueError(f"leverage must be >= 0, got {self.leverage}")
        self.confidence       = _clamp(self.confidence, 0.0, 100.0)
        self.importance_score = _clamp(self.importance_score, 0.0, 100.0)

    @property
    def is_bullish(self) -> bool:
        return self.side == SIDE_LONG

    @property
    def is_bearish(self) -> bool:
        return self.side == SIDE_SHORT

    @property
    def is_high_risk(self) -> bool:
        return self.risk in (RISK_HIGH, RISK_EXTREME)

    @property
    def leverage_str(self) -> str:
        return f"{self.leverage:.0f}x" if self.leverage else "spot"

    @property
    def size_str(self) -> str:
        return _fmt_size(self.size_usd)


# ── Risk classification ───────────────────────────────────────────────────────

def classify_whale_risk(
    size_usd: float,
    leverage: Optional[float] = None,
    market_context: Optional[MarketContext] = None,
) -> str:
    """
    Classify the risk level of a whale event with optional market context.

    Base risk from effective exposure (size × leverage):
        >= $10M  → extreme
        >= $2M   → high
        >= $500k → medium
        < $500k  → low

    Leverage floors (even at small size):
        >= 20x → extreme floor
        >= 10x → high floor
        >= 5x  → medium floor

    Context escalations (+1 level each, max extreme):
        - Liquidity score < 30: thin book amplifies risk
        - |Funding rate| > 0.05%: crowded side adds risk
        - Near resistance (longs) or near support (shorts): structural risk

    Args:
        size_usd:       Notional USD size.
        leverage:       Leverage multiple. None = spot.
        market_context: Optional MarketContext for context-aware escalation.

    Returns:
        "low", "medium", "high", or "extreme".

    Raises:
        ValueError: if size_usd < 0 or leverage < 0.
    """
    if size_usd < 0:
        raise ValueError(f"size_usd must be >= 0, got {size_usd}")
    if leverage is not None and leverage < 0:
        raise ValueError(f"leverage must be >= 0, got {leverage}")

    effective = size_usd * (leverage if leverage else 1.0)

    _order = [RISK_LOW, RISK_MEDIUM, RISK_HIGH, RISK_EXTREME]

    # Size-based
    if effective >= _SIZE_EXTREME:
        risk = RISK_EXTREME
    elif effective >= _SIZE_HIGH:
        risk = RISK_HIGH
    elif effective >= _SIZE_MEDIUM:
        risk = RISK_MEDIUM
    else:
        risk = RISK_LOW

    # Leverage floor
    lev_floor = RISK_LOW
    if leverage:
        if leverage >= _LEV_EXTREME:
            lev_floor = RISK_EXTREME
        elif leverage >= _LEV_HIGH:
            lev_floor = RISK_HIGH
        elif leverage >= _LEV_MEDIUM:
            lev_floor = RISK_MEDIUM
    risk = _order[max(_order.index(risk), _order.index(lev_floor))]

    # Context escalation (each bad factor can push up one level)
    if market_context:
        idx = _order.index(risk)
        if market_context.liquidity_score > 0 and market_context.liquidity_score < 30:
            idx = min(idx + 1, 3)
        if abs(market_context.funding_rate) > 0.05:
            idx = min(idx + 1, 3)
        risk = _order[idx]

    return risk


# ── Importance score ──────────────────────────────────────────────────────────

def calculate_importance_score(
    size_usd: float,
    leverage: Optional[float] = None,
    market_context: Optional[MarketContext] = None,
) -> float:
    """
    Calculate a 0–100 importance score for a whale event.

    Higher = more important, harder to ignore.

    Scoring breakdown:
        Size contribution    40 pts   (log-scaled, $10M+ = full)
        Leverage amplifier   20 pts   (1x = 0, 20x+ = full)
        Context confluence   25 pts   (orderbook + funding + structure)
        Repeat trader bonus  15 pts   (known behavioral pattern)

    Args:
        size_usd:       Notional USD size.
        leverage:       Leverage multiple. None = spot.
        market_context: Optional MarketContext.

    Returns:
        Float score in [0, 100].
    """
    import math

    score = 0.0

    # ── Size (0–40) ───────────────────────────────────────────────────────────
    if size_usd > 0:
        # log10($100) = 2, log10($10M) = 7 → scale to 40
        log_size = math.log10(max(size_usd, 1))
        size_score = _clamp((log_size - 4) / 3 * 40, 0, 40)  # $10k=0, $10M=40
    else:
        size_score = 0.0
    score += size_score

    # ── Leverage (0–20) ───────────────────────────────────────────────────────
    if leverage and leverage > 0:
        lev_score = _clamp((leverage - 1) / (_LEV_EXTREME - 1) * 20, 0, 20)
    else:
        lev_score = 0.0
    score += lev_score

    # ── Context confluence (0–25) ─────────────────────────────────────────────
    if market_context:
        ctx_score = 0.0

        # Orderbook imbalance aligns with event (0–8)
        if abs(market_context.imbalance) > 0.3:
            ctx_score += _clamp(abs(market_context.imbalance) * 8, 0, 8)

        # Liquidity score — low liquidity = high impact (0–6)
        if market_context.liquidity_score > 0:
            liq_impact = _clamp((100 - market_context.liquidity_score) / 100 * 6, 0, 6)
            ctx_score += liq_impact

        # Funding rate magnitude (0–5)
        if market_context.funding_rate != 0:
            ctx_score += _clamp(abs(market_context.funding_rate) / 0.1 * 5, 0, 5)

        # OI change (0–4)
        if market_context.oi_change_pct != 0:
            ctx_score += _clamp(abs(market_context.oi_change_pct) / 20 * 4, 0, 4)

        # Structure proximity (0–2)
        if market_context.near_breakout or market_context.near_support or market_context.near_resistance:
            ctx_score += 2.0

        score += _clamp(ctx_score, 0, 25)

    # ── Repeat trader bonus (0–15) ────────────────────────────────────────────
    if market_context and market_context.repeated_trader:
        score += 15.0

    return _clamp(score, 0.0, 100.0)


# ── Alert type classification ─────────────────────────────────────────────────

def classify_alert_type(event: dict) -> str:
    """
    Determine the most appropriate alert type from an event dict.

    Event dict expected keys (all optional):
        event_type  (str)  — "opened", "increased", "reduced", "closed",
                             "liquidation_risk", "accumulation"
        side        (str)  — "long", "short", "buy", "sell", "exit"
        leverage    (float)— leverage multiple
        size_usd    (float)— position size
        oi_change_pct (float) — open interest change %
        funding_rate  (float) — current funding rate

    Returns:
        One of VALID_ALERT_TYPES.

    Raises:
        TypeError: if event is not a dict.
    """
    if not isinstance(event, dict):
        raise TypeError(f"event must be a dict, got {type(event).__name__}")

    ev_type  = str(event.get("event_type", "opened")).lower()
    raw_side = str(event.get("side", "long")).lower()
    size_usd = float(event.get("size_usd", 0) or 0)
    leverage = event.get("leverage")
    leverage = float(leverage) if leverage is not None else None
    oi_chg   = float(event.get("oi_change_pct", 0) or 0)
    funding  = float(event.get("funding_rate", 0) or 0)

    is_long  = raw_side in ("long", "buy", "b")
    is_short = raw_side in ("short", "sell", "a")

    # Liquidation risk — highest priority
    if ev_type in ("liquidation_risk", "liquidation"):
        return ALERT_LIQUIDATION_RISK

    # Position reduced or closed
    if ev_type in ("reduced", "reduce", "partial_close"):
        return ALERT_POSITION_REDUCED
    if ev_type in ("closed", "close", "exit"):
        if size_usd >= _SIZE_HIGH:
            return ALERT_WHALE_EXIT
        return ALERT_WHALE_EXIT

    # Increased
    if ev_type in ("increased", "increase"):
        return ALERT_POSITION_INCREASED

    # Stealth accumulation (small orders, no orderbook trace)
    if ev_type in ("accumulation", "smart_buy"):
        return ALERT_SMART_ACCUMULATION

    # Crowded leverage (OI spike + extreme leverage on same side)
    if leverage and leverage >= _LEV_HIGH and abs(oi_chg) > 10:
        return ALERT_CROWDED_LEVERAGE

    # Trap detection — size/leverage mismatch with funding
    if leverage and leverage >= _LEV_HIGH:
        if (is_long and funding > 0.1) or (is_short and funding < -0.1):
            return ALERT_POSSIBLE_TRAP

    # Default: aggressive open by direction
    if is_long:
        return ALERT_AGGRESSIVE_LONG
    if is_short:
        return ALERT_AGGRESSIVE_SHORT

    return ALERT_AGGRESSIVE_LONG  # neutral fallback


# ── Action derivation ─────────────────────────────────────────────────────────

def _derive_action(
    alert_type: str,
    side: str,
    risk: str,
    market_context: Optional[MarketContext] = None,
    importance_score: float = 0.0,
) -> str:
    """Derive a short plain-English action hint from alert attributes."""
    if alert_type == ALERT_LIQUIDATION_RISK:
        return "Possible squeeze watch — liquidation cascade risk."
    if alert_type == ALERT_CROWDED_LEVERAGE:
        return "Avoid chasing — crowded leverage increases reversal risk."
    if alert_type == ALERT_POSSIBLE_TRAP:
        return "Wait for confirmation — funding diverges from direction."
    if alert_type == ALERT_WHALE_EXIT:
        return "Monitor for distribution — large exit may signal reversal."
    if alert_type == ALERT_SMART_ACCUMULATION:
        return "Watch — stealth accumulation may precede a breakout."
    if alert_type == ALERT_POSITION_REDUCED:
        return "Monitor for full exit — partial close may signal distribution."

    # Aggressive open
    if market_context:
        if alert_type == ALERT_AGGRESSIVE_LONG:
            if market_context.near_breakout:
                return "Possible breakout watch — bid wall supports move."
            if market_context.near_support:
                return "Monitor bid wall — large long at support level."
        if alert_type == ALERT_AGGRESSIVE_SHORT:
            if market_context.near_resistance:
                return "Monitor ask wall — large short at resistance level."

    if importance_score >= 75:
        return "Possible breakout watch — high importance signal."
    if risk in (RISK_HIGH, RISK_EXTREME):
        return "Watch — high-risk event requires confirmation."
    return "Watch — monitor for follow-through."


# ── Reason + warning generation ───────────────────────────────────────────────

def _build_reasons_and_warnings(
    size_usd: float,
    leverage: Optional[float],
    alert_type: str,
    side: str,
    market_context: Optional[MarketContext],
) -> tuple[list[str], list[str]]:
    """
    Build plain-English reasons and warnings for an alert.

    Returns:
        (reasons, warnings) — two lists of strings.
    """
    reasons:  list[str] = []
    warnings: list[str] = []

    # Size
    size_disp = _fmt_size(size_usd)
    if size_usd >= _SIZE_EXTREME:
        reasons.append(f"Extremely large position: {size_disp} — institutional-scale size.")
    elif size_usd >= _SIZE_HIGH:
        reasons.append(f"Large position: {size_disp} — well above retail scale.")
    else:
        reasons.append(f"Significant position size: {size_disp}.")

    # Leverage
    if leverage and leverage >= _LEV_EXTREME:
        reasons.append(f"Very high leverage ({leverage:.0f}x) amplifies directional conviction.")
        warnings.append(f"Extreme leverage ({leverage:.0f}x) — liquidation cascade risk if price moves against.")
    elif leverage and leverage >= _LEV_HIGH:
        reasons.append(f"High leverage ({leverage:.0f}x) signals strong directional bet.")
        warnings.append(f"High leverage ({leverage:.0f}x) — elevated liquidation risk.")
    elif leverage and leverage >= _LEV_MEDIUM:
        reasons.append(f"Moderate leverage ({leverage:.0f}x) in use.")

    # Alert-type context
    if alert_type == ALERT_SMART_ACCUMULATION:
        reasons.append("Stealth accumulation pattern — no orderbook footprint.")
    if alert_type == ALERT_POSSIBLE_TRAP:
        warnings.append("Funding diverges from position direction — possible trap for retail followers.")
    if alert_type == ALERT_CROWDED_LEVERAGE:
        warnings.append("Open interest spiking — crowded same-side positioning increases squeeze risk.")
    if alert_type == ALERT_LIQUIDATION_RISK:
        warnings.append("Position approaching liquidation — forced close may cause cascade.")

    # Market context
    if market_context:
        if abs(market_context.imbalance) >= 0.5:
            direction = "bid" if market_context.imbalance > 0 else "ask"
            reasons.append(
                f"Orderbook strongly {direction}-heavy (imbalance {market_context.imbalance:+.2f}) "
                f"{'supports' if (side==SIDE_LONG)==(market_context.imbalance>0) else 'contradicts'} "
                f"the trade direction."
            )
        if 0 < market_context.liquidity_score < 30:
            warnings.append(f"Thin liquidity (score {market_context.liquidity_score:.0f}/100) — price impact risk.")
        if abs(market_context.funding_rate) > 0.05:
            fund_dir = "longs paying" if market_context.funding_rate > 0 else "shorts paying"
            reasons.append(f"Elevated funding rate ({market_context.funding_rate:+.3f}%) — {fund_dir}.")
        if market_context.oi_change_pct > 10:
            reasons.append(f"Open interest rising sharply (+{market_context.oi_change_pct:.1f}%) — new money entering.")
        elif market_context.oi_change_pct < -10:
            warnings.append(f"Open interest falling ({market_context.oi_change_pct:.1f}%) — possible deleverage.")
        if market_context.near_breakout:
            reasons.append("Price near a key breakout level — structural significance.")
        if market_context.near_support and side == SIDE_LONG:
            reasons.append("Large long opened at support — high-conviction structural trade.")
        if market_context.near_resistance and side == SIDE_SHORT:
            reasons.append("Large short at resistance — high-conviction structural trade.")
        if market_context.repeated_trader:
            reasons.append("Repeated trader — this account has successfully front-run moves before.")
            warnings.append("Past performance does not guarantee future results — still use confirmation.")
        if market_context.bid_wall_usd >= 500_000 and side == SIDE_LONG:
            reasons.append(f"Strong bid wall (${market_context.bid_wall_usd/1e6:.1f}M) supporting the long.")
        if market_context.ask_wall_usd >= 500_000 and side == SIDE_SHORT:
            reasons.append(f"Strong ask wall (${market_context.ask_wall_usd/1e6:.1f}M) pressuring price.")

    return reasons, warnings


# ── Main detection function ───────────────────────────────────────────────────

def detect_smart_whale_event(
    event: dict,
    market_context: Optional[MarketContext] = None,
    min_size_usd: float = 100_000,
) -> Optional[WhaleAlert]:
    """
    Analyse a raw event dict and produce a contextualised WhaleAlert.

    Expected event dict keys (all optional):
        symbol         (str)   — trading pair
        venue          (str)   — exchange
        event_type     (str)   — "opened", "increased", "reduced", "closed", etc.
        side           (str)   — "long", "short", "buy", "sell", "exit"
        size_usd       (float) — position/trade size in USD
        leverage       (float) — leverage multiple
        price          (float) — asset price
        wallet         (str)   — wallet identifier
        time_ms        (int)   — Unix ms timestamp
        oi_change_pct  (float) — OI 24h change %
        funding_rate   (float) — current funding rate

    Args:
        event:          Event dict.
        market_context: Optional MarketContext for smart scoring.
        min_size_usd:   Minimum USD size to qualify. Default $100k.

    Returns:
        WhaleAlert if event qualifies, None if below threshold.

    Raises:
        TypeError:  if event is not a dict.
        ValueError: if min_size_usd < 0.
    """
    if not isinstance(event, dict):
        raise TypeError(f"event must be a dict, got {type(event).__name__}")
    if min_size_usd < 0:
        raise ValueError(f"min_size_usd must be >= 0, got {min_size_usd}")

    size_usd = float(event.get("size_usd", 0) or 0)
    if size_usd < min_size_usd:
        return None

    symbol    = str(event.get("symbol",     "UNKNOWN"))
    venue     = str(event.get("venue",      "unknown"))
    raw_side  = str(event.get("side",       "long")).lower()
    leverage  = event.get("leverage")
    leverage  = float(leverage) if leverage is not None else None
    price     = float(event.get("price",    0) or 0)
    wallet    = str(event.get("wallet",     ""))
    ts        = int(event.get("time_ms",    time.time() * 1000))

    side = SIDE_LONG if raw_side in ("long", "buy", "b") else \
           SIDE_SHORT if raw_side in ("short", "sell", "a") else \
           SIDE_EXIT  if raw_side in ("exit", "close") else SIDE_NONE

    alert_type = classify_alert_type(event)
    risk       = classify_whale_risk(size_usd, leverage, market_context)
    importance = calculate_importance_score(size_usd, leverage, market_context)
    reasons, warnings = _build_reasons_and_warnings(
        size_usd, leverage, alert_type, side, market_context
    )

    # Confidence: starts at 50, boosted by context richness, penalised by warnings
    confidence = 50.0
    if market_context:
        confidence += min(20.0, len(reasons) * 4.0)
        confidence -= min(20.0, len(warnings) * 6.0)
        if market_context.repeated_trader:
            confidence += 15.0
    confidence = _clamp(confidence, 10.0, 95.0)

    action = _derive_action(alert_type, side, risk, market_context, importance)

    size_disp = _fmt_size(size_usd)
    lev_str   = f" at {leverage:.0f}x" if leverage else ""
    side_word = side.upper() if side != SIDE_NONE else ""
    message   = (
        f"{side_word} {alert_type.replace('_', ' ').title()}: "
        f"{size_disp} {symbol}{lev_str} on {venue}."
    ).strip()

    ctx_summary = ""
    if market_context:
        parts = []
        if abs(market_context.imbalance) >= 0.3:
            parts.append(f"OB imbalance {market_context.imbalance:+.2f}")
        if market_context.liquidity_score > 0:
            parts.append(f"liq {market_context.liquidity_score:.0f}/100")
        if market_context.funding_rate != 0:
            parts.append(f"funding {market_context.funding_rate:+.3f}%")
        ctx_summary = " | ".join(parts) if parts else ""

    return WhaleAlert(
        symbol=symbol,
        venue=venue,
        alert_type=alert_type,
        side=side,
        size_usd=size_usd,
        risk=risk,
        message=message,
        timestamp_ms=ts,
        confidence=round(confidence, 1),
        importance_score=round(importance, 1),
        context=ctx_summary,
        reasons=reasons,
        warnings=warnings,
        action=action,
        leverage=leverage,
        price=price,
        wallet=wallet,
        tags=[],
        raw=event,
    )


# ── Build alert (manual constructor) ─────────────────────────────────────────

def build_whale_alert(
    symbol: str,
    venue: str,
    alert_type: str,
    side: str,
    size_usd: float,
    message: str,
    leverage: Optional[float] = None,
    price: float = 0.0,
    wallet: str = "",
    tags: Optional[list[str]] = None,
    timestamp_ms: Optional[int] = None,
    confidence: float = 60.0,
    importance_score: float = 0.0,
    context: str = "",
    reasons: Optional[list[str]] = None,
    warnings: Optional[list[str]] = None,
    action: str = "Watch",
    raw: Optional[dict] = None,
) -> WhaleAlert:
    """
    Construct a WhaleAlert manually with explicit risk classification.

    Risk is auto-computed from size_usd and leverage.
    Use detect_smart_whale_event() for context-aware alerts.
    """
    risk = classify_whale_risk(size_usd, leverage)
    return WhaleAlert(
        symbol=symbol, venue=venue, alert_type=alert_type, side=side,
        size_usd=size_usd, risk=risk, message=message,
        timestamp_ms=timestamp_ms if timestamp_ms is not None else int(time.time() * 1000),
        leverage=leverage, price=price, wallet=wallet, tags=tags or [],
        confidence=confidence, importance_score=importance_score,
        context=context, reasons=reasons or [], warnings=warnings or [],
        action=action, raw=raw or {},
    )


# ── Noise filter ──────────────────────────────────────────────────────────────

def filter_noise_alerts(
    alerts: list[WhaleAlert],
    min_importance: float = 60.0,
) -> list[WhaleAlert]:
    """
    Filter out low-importance whale alerts.

    Keeps alerts with importance_score >= min_importance, sorted
    by importance descending.

    Args:
        alerts:         List of WhaleAlert objects.
        min_importance: Minimum importance score to keep. Default 60.

    Returns:
        Filtered and sorted list. Never raises on empty input.

    Raises:
        ValueError: if min_importance < 0 or > 100.
    """
    if not (0 <= min_importance <= 100):
        raise ValueError(f"min_importance must be in [0, 100], got {min_importance}")
    filtered = [a for a in alerts if a.importance_score >= min_importance]
    filtered.sort(key=lambda a: a.importance_score, reverse=True)
    return filtered


# ── Demo alerts ───────────────────────────────────────────────────────────────

def demo_whale_alerts() -> list[WhaleAlert]:
    """
    Return realistic demo WhaleAlerts covering all alert types.

    Uses detect_smart_whale_event with rich MarketContext for each alert.
    """
    now = int(time.time() * 1000)
    def ts(m: int) -> int: return now - m * 60 * 1000

    alerts = []

    # 1. Aggressive long with bid-wall support
    ctx1 = MarketContext(
        imbalance=0.62, liquidity_score=88,
        funding_rate=0.012, oi_change_pct=8.5,
        near_breakout=True, bid_wall_usd=8_400_000,
    )
    a1 = detect_smart_whale_event(
        {"symbol":"BTCUSDT","venue":"binance","event_type":"opened",
         "side":"long","size_usd":8_400_000,"leverage":10,"price":67_420,"time_ms":ts(4)},
        market_context=ctx1
    )
    if a1: alerts.append(a1)

    # 2. Large HYPE long — repeated trader, high importance
    ctx2 = MarketContext(
        imbalance=0.71, liquidity_score=76,
        funding_rate=0.031, oi_change_pct=14.2,
        near_breakout=True, repeated_trader=True,
        bid_wall_usd=3_200_000,
    )
    a2 = detect_smart_whale_event(
        {"symbol":"HYPE","venue":"Hyperliquid","event_type":"opened",
         "side":"long","size_usd":12_400_000,"leverage":5,"price":28.14,"time_ms":ts(11)},
        market_context=ctx2
    )
    if a2: alerts.append(a2)

    # 3. Possible trap — short with negative funding
    ctx3 = MarketContext(
        imbalance=-0.55, liquidity_score=60,
        funding_rate=-0.12, oi_change_pct=18,
        near_resistance=True,
    )
    a3 = detect_smart_whale_event(
        {"symbol":"SOLUSDT","venue":"binance","event_type":"opened",
         "side":"short","size_usd":3_200_000,"leverage":15,"price":174.30,
         "time_ms":ts(22),"oi_change_pct":18,"funding_rate":-0.12},
        market_context=ctx3
    )
    if a3: alerts.append(a3)

    # 4. Position increased — ETH whale scaling up
    ctx4 = MarketContext(
        imbalance=0.38, liquidity_score=91,
        funding_rate=0.018, oi_change_pct=6.1,
        near_breakout=True, repeated_trader=True,
    )
    a4 = detect_smart_whale_event(
        {"symbol":"ETHUSDT","venue":"binance","event_type":"increased",
         "side":"long","size_usd":5_750_000,"leverage":12,"price":3_512,"time_ms":ts(35)},
        market_context=ctx4
    )
    if a4: alerts.append(a4)

    # 5. Whale exit — BTC large position closing
    ctx5 = MarketContext(imbalance=-0.22, liquidity_score=82)
    a5 = detect_smart_whale_event(
        {"symbol":"BTCUSDT","venue":"binance","event_type":"closed",
         "side":"exit","size_usd":14_200_000,"leverage":None,"price":67_180,"time_ms":ts(51)},
        market_context=ctx5
    )
    if a5: alerts.append(a5)

    # 6. Liquidation risk — extreme leverage HYPE
    ctx6 = MarketContext(
        imbalance=0.15, liquidity_score=44,
        funding_rate=0.08, oi_change_pct=22,
    )
    a6 = detect_smart_whale_event(
        {"symbol":"HYPE","venue":"Hyperliquid","event_type":"liquidation_risk",
         "side":"long","size_usd":6_800_000,"leverage":20,"price":25.40,"time_ms":ts(67)},
        market_context=ctx6
    )
    if a6: alerts.append(a6)

    # 7. Smart accumulation — stealth buy
    ctx7 = MarketContext(
        imbalance=0.51, liquidity_score=55,
        funding_rate=0.002, near_support=True,
    )
    a7 = detect_smart_whale_event(
        {"symbol":"SOLUSDT","venue":"binance","event_type":"accumulation",
         "side":"long","size_usd":2_100_000,"leverage":None,"price":174,"time_ms":ts(88)},
        market_context=ctx7
    )
    if a7: alerts.append(a7)

    return alerts


# ── Minimal whale event detection (v2) ───────────────────────────────────

_SEVERITY_INFO     = "info"
_SEVERITY_NOTABLE  = "notable"
_SEVERITY_HIGH     = "high"
_SEVERITY_EXTREME  = "extreme"

_DEFAULT_OPTIONS = {
    "min_notional_usd": 100_000,
    "high_notional_usd": 500_000,
    "extreme_notional_usd": 1_000_000,
    "allowed_symbols": None,
    "blocked_symbols": None,
}


def _make_whale_event_id(source_type, symbol, tx_hash, wallet, notional_usd, event_ts):
    import hashlib
    raw = f"{source_type}|{symbol}|{tx_hash}|{wallet}|{notional_usd}|{event_ts}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _classify_severity(notional_usd, high_thresh, extreme_thresh):
    if notional_usd >= extreme_thresh:
        return _SEVERITY_EXTREME
    if notional_usd >= high_thresh:
        return _SEVERITY_HIGH
    return _SEVERITY_NOTABLE


def detect_whale_events(items, options=None):
    """
    Turn a list of trade/transfer dicts into whale event dicts.

    Each item may contain: source_type, symbol, chain, exchange, side,
    amount, price, notional_usd, wallet, tx_hash, event_ts, metadata.

    Returns a list of whale event dicts for items above the notional threshold.
    """
    if not items:
        return []

    opts = dict(_DEFAULT_OPTIONS)
    if options:
        opts.update(options)

    min_usd = float(opts["min_notional_usd"])
    high_usd = float(opts["high_notional_usd"])
    extreme_usd = float(opts["extreme_notional_usd"])
    allowed = opts.get("allowed_symbols")
    blocked = opts.get("blocked_symbols")

    results = []
    for item in items:
        if not isinstance(item, dict):
            continue

        notional = float(item.get("notional_usd", 0) or 0)
        if notional < min_usd:
            continue

        symbol = str(item.get("symbol", "") or "")
        if allowed and symbol not in allowed:
            continue
        if blocked and symbol in blocked:
            continue

        source_type = str(item.get("source_type", "unknown") or "unknown")
        chain = str(item.get("chain", "") or "")
        exchange = str(item.get("exchange", "") or "")
        side = str(item.get("side", "") or "")
        amount = float(item.get("amount", 0) or 0)
        price = float(item.get("price", 0) or 0)
        wallet = str(item.get("wallet", "") or "")
        tx_hash = str(item.get("tx_hash", "") or "")
        event_ts = str(item.get("event_ts", "") or "")
        metadata = item.get("metadata") or {}

        severity = _classify_severity(notional, high_usd, extreme_usd)
        confidence = 0.8 if tx_hash else 0.5
        reason = f"{source_type} of {symbol} worth ${notional:,.0f}"

        whale_event_id = _make_whale_event_id(
            source_type, symbol, tx_hash, wallet, notional, event_ts
        )

        results.append({
            "whale_event_id": whale_event_id,
            "event_ts": event_ts,
            "source_type": source_type,
            "symbol": symbol,
            "chain": chain,
            "exchange": exchange,
            "side": side,
            "amount": amount,
            "price": price,
            "notional_usd": notional,
            "wallet": wallet,
            "tx_hash": tx_hash,
            "severity": severity,
            "confidence": confidence,
            "reason": reason,
            "metadata": metadata,
        })

    return results


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fmt_size(size_usd: float) -> str:
    if size_usd >= 1_000_000:
        return f"${size_usd / 1_000_000:.1f}M"
    if size_usd >= 1_000:
        return f"${size_usd / 1_000:.0f}K"
    return f"${size_usd:.0f}"


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


if __name__ == "__main__":
    # classify_whale_risk
    assert classify_whale_risk(50_000) == "low"
    assert classify_whale_risk(600_000) == "medium"
    assert classify_whale_risk(3_000_000) == "high"
    assert classify_whale_risk(15_000_000) == "extreme"
    assert classify_whale_risk(100_000, leverage=25) == "extreme"
    assert classify_whale_risk(100_000, leverage=12) == "high"
    assert classify_whale_risk(0) == "low"

    ctx = MarketContext(liquidity_score=20, funding_rate=0.1)
    assert classify_whale_risk(400_000, leverage=4, market_context=ctx) in ("high","extreme")

    # calculate_importance_score
    s = calculate_importance_score(10_000_000, leverage=10)
    assert 0 <= s <= 100
    s_low = calculate_importance_score(50_000)
    s_high = calculate_importance_score(10_000_000, leverage=20)
    assert s_high > s_low

    # classify_alert_type
    assert classify_alert_type({"event_type":"liquidation_risk"}) == ALERT_LIQUIDATION_RISK
    assert classify_alert_type({"event_type":"opened","side":"long"}) == ALERT_AGGRESSIVE_LONG
    assert classify_alert_type({"event_type":"increased"}) == ALERT_POSITION_INCREASED
    assert classify_alert_type({"event_type":"closed","size_usd":5_000_000}) == ALERT_WHALE_EXIT

    # detect_smart_whale_event
    ev = {"symbol":"BTCUSDT","venue":"binance","event_type":"opened",
          "side":"long","size_usd":5_000_000,"leverage":10,"price":67420}
    alert = detect_smart_whale_event(ev)
    assert alert is not None
    assert alert.symbol == "BTCUSDT"
    assert 0 <= alert.importance_score <= 100
    assert 0 <= alert.confidence <= 100
    assert alert.risk in (RISK_LOW, RISK_MEDIUM, RISK_HIGH, RISK_EXTREME)
    assert len(alert.reasons) > 0
    assert len(alert.action) > 5

    # Below threshold
    assert detect_smart_whale_event({"size_usd":500}) is None

    # TypeError
    try: detect_smart_whale_event("bad"); assert False
    except TypeError: pass

    # filter_noise_alerts
    demos = demo_whale_alerts()
    assert len(demos) >= 5
    filtered = filter_noise_alerts(demos, min_importance=60)
    assert all(a.importance_score >= 60 for a in filtered)
    scores = [a.importance_score for a in filtered]
    assert scores == sorted(scores, reverse=True)

    # filter with all kept
    all_kept = filter_noise_alerts(demos, min_importance=0)
    assert len(all_kept) == len(demos)

    # filter_noise_alerts bad input
    try: filter_noise_alerts([], min_importance=-1); assert False
    except ValueError: pass

    # WhaleAlert validation
    try:
        WhaleAlert("X","y","bad_type","long",1000,"low","msg",0)
        assert False
    except ValueError: pass

    print("services/whale_alert_engine.py — all assertions passed.")
