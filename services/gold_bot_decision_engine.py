"""
services/gold_bot_decision_engine.py
--------------------------------------
LM76B — Gold Bot strategy engine V2 (pure, transparent, no ML).

Reads recent XAUUSD candles + market context and emits a structured TradeIdea:
LONG / SHORT / NO_TRADE with reasons, blockers, detected zones and an
explainable confidence breakdown. No MT5, no I/O, no network here — the probe
script feeds candles/spread/position state in and prints/executes the result
through the existing LM75 risk + trade-loop guards.

V2 detectors (priority order):
  1. liquidity_sweep_reclaim — sweep of a prior high/low then reclaim/rejection
  2. fvg_retest             — 3-candle imbalance, price retesting the gap
  3. breakout_retest        — range break then retest of the broken level
  4. momentum               — SMA stack + recent momentum
  5. scalp_retest / scalp_momentum — fast M1 setups (scalp mode)
  6. no_trade               — insufficient / wide spread / chaotic / extended / open position

Everything is deterministic given the same inputs. NO_TRADE is the safe default.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any

from services.gold_bot_macro_context import MacroContext, macro_directional_adjustment

# ── Tunable thresholds (transparent, conservative) ───────────────────────────
SMA_SHORT = 9
SMA_LONG = 21
LOOKBACK = 30            # recent high/low window
SWING_WIN = 10          # swing pivot window
RECENT_EXCL = 3         # bars excluded from "previous" high/low (the sweep candidates)
MOM_BARS = 5
SCALP_MOM_BARS = 3
VOL_BARS = 14
SHORT_VOL = 5
FVG_SCAN = 20           # bars back to scan for the most recent FVG
NEAR_EXTREME_POINTS = 150
RETEST_POINTS = 120     # "near" a level for retest/reclaim (points)
EXTENSION_POINTS = 800  # too far from SMA21 without a retest = chase
CHAOTIC_RANGE_MULT = 3.0
REGIME_TREND_POINTS = 60   # SMA9–SMA21 separation (pts) to call it a trend

MAX_SPREAD_POINTS = {"safe": 60, "balanced": 60, "aggressive": 80,
                     "experimental": 60, "scalp": 35}
MIN_CONFIDENCE = {"safe": 60, "balanced": 55, "aggressive": 50,
                  "experimental": 55, "scalp": 50}
SLTP_POINTS = {"safe": (300, 600), "balanced": (300, 600), "aggressive": (300, 600),
               "experimental": (300, 600), "scalp": (120, 180)}

# Setup priority (lower = preferred when confidence is comparable).
SETUP_PRIORITY = {
    "liquidity_sweep_reclaim": 1,
    "fvg_retest": 2,
    "breakout_retest": 3,
    "momentum": 4,
    "scalp_retest": 5,
    "scalp_momentum": 6,
}


@dataclass
class MarketState:
    last_close: float
    last_open: float
    sma_short: float
    sma_long: float
    recent_high: float
    recent_low: float
    swing_high: float
    swing_low: float
    prev_high: float
    prev_low: float
    body_strength: float
    upper_wick_ratio: float
    lower_wick_ratio: float
    momentum_points: float
    volatility_points: float
    spread_points: float
    dist_from_high_points: float
    dist_from_low_points: float
    compression_state: str      # compressed | expanding | normal
    regime: str                 # trend | range
    session: str                # Asia | London | NewYork | Off-session | unknown
    bars: int

    def summary(self) -> str:
        return (f"{self.session} | {self.regime} | {self.compression_state} | "
                f"close {self.last_close:.2f} | SMA{SMA_SHORT} {self.sma_short:.2f} / "
                f"SMA{SMA_LONG} {self.sma_long:.2f} | mom {self.momentum_points:+.0f}pt | "
                f"vol {self.volatility_points:.0f}pt | spread {self.spread_points:.0f}pt")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TradeIdea:
    decision_id: str
    timestamp: str
    symbol: str
    timeframe: str
    decision: str
    strategy: str
    confidence: int
    entry_reference_price: float | None
    sl_points: int | None
    tp_points: int | None
    risk_mode: str
    session: str = "unknown"
    regime: str = "unknown"
    reasons: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    zones: dict[str, Any] = field(default_factory=dict)
    confidence_components: dict[str, Any] = field(default_factory=dict)
    market_state: dict[str, Any] = field(default_factory=dict)
    macro: dict[str, Any] = field(default_factory=dict)
    should_execute_demo: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ── candidate produced by a detector ─────────────────────────────────────────
@dataclass
class _Candidate:
    decision: str               # LONG | SHORT
    strategy: str
    components: dict[str, float]
    reasons: list[str]
    zones: dict[str, Any]

    @property
    def confidence(self) -> int:
        return int(max(0, min(100, round(sum(self.components.values())))))

    @property
    def priority(self) -> int:
        return SETUP_PRIORITY.get(self.strategy, 9)


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _session_from_iso(iso: str | None) -> str:
    if not iso:
        return "unknown"
    try:
        h = datetime.fromisoformat(iso).astimezone(timezone.utc).hour
    except (ValueError, TypeError):
        return "unknown"
    if 0 <= h < 7:
        return "Asia"
    if 7 <= h < 12:
        return "London"
    if 12 <= h < 21:
        return "NewYork"
    return "Off-session"


def compute_market_state(candles: list[dict], *, spread_points: float, point: float) -> MarketState:
    closes = [c["close"] for c in candles]
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    n = len(candles)
    p = point if point and point > 0 else 0.01
    last = candles[-1]

    sma_short = _mean(closes[-SMA_SHORT:])
    sma_long = _mean(closes[-SMA_LONG:])
    recent_high = max(highs[-LOOKBACK:])
    recent_low = min(lows[-LOOKBACK:])
    swing_high = max(highs[-SWING_WIN:])
    swing_low = min(lows[-SWING_WIN:])
    # "Previous" structural levels: exclude the most recent RECENT_EXCL bars so a
    # fresh sweep of them is detectable.
    prior = candles[-LOOKBACK:-RECENT_EXCL] if n > LOOKBACK else candles[:-RECENT_EXCL] or candles
    prev_high = max(c["high"] for c in prior)
    prev_low = min(c["low"] for c in prior)

    rng = last["high"] - last["low"]
    body = abs(last["close"] - last["open"])
    body_strength = body / rng if rng > 0 else 0.0
    upper_wick = (last["high"] - max(last["open"], last["close"])) / rng if rng > 0 else 0.0
    lower_wick = (min(last["open"], last["close"]) - last["low"]) / rng if rng > 0 else 0.0

    mom_idx = max(0, n - 1 - MOM_BARS)
    momentum_points = (closes[-1] - closes[mom_idx]) / p

    ranges = [h - l for h, l in zip(highs[-VOL_BARS:], lows[-VOL_BARS:])]
    vol = _mean(ranges)
    short_ranges = [h - l for h, l in zip(highs[-SHORT_VOL:], lows[-SHORT_VOL:])]
    short_vol = _mean(short_ranges)
    if vol > 0 and short_vol < vol * 0.7:
        compression = "compressed"
    elif vol > 0 and short_vol > vol * 1.4:
        compression = "expanding"
    else:
        compression = "normal"

    sma_sep_pts = abs(sma_short - sma_long) / p
    aligned = closes[-1] > sma_short > sma_long or closes[-1] < sma_short < sma_long
    regime = "trend" if (sma_sep_pts >= REGIME_TREND_POINTS and aligned) else "range"

    return MarketState(
        last_close=closes[-1], last_open=last["open"], sma_short=sma_short, sma_long=sma_long,
        recent_high=recent_high, recent_low=recent_low, swing_high=swing_high, swing_low=swing_low,
        prev_high=prev_high, prev_low=prev_low,
        body_strength=round(body_strength, 3), upper_wick_ratio=round(upper_wick, 3),
        lower_wick_ratio=round(lower_wick, 3), momentum_points=round(momentum_points, 1),
        volatility_points=round(vol / p, 1), spread_points=round(spread_points, 1),
        dist_from_high_points=round((recent_high - closes[-1]) / p, 1),
        dist_from_low_points=round((closes[-1] - recent_low) / p, 1),
        compression_state=compression, regime=regime,
        session=_session_from_iso(last.get("time")), bars=n,
    )


# ── detectors (each returns a _Candidate or None) ────────────────────────────
def _detect_sweep(candles, ms, point, mode) -> _Candidate | None:
    p = point or 0.01
    last = candles[-1]
    # Bullish sweep: a recent bar pierced prev_low and price reclaimed above it.
    swept_low = any(c["low"] < ms.prev_low for c in candles[-RECENT_EXCL - 1:])
    if swept_low and last["close"] > ms.prev_low and ms.lower_wick_ratio >= 0.4:
        comp = {"base": 45, "sweep": 18, "reclaim": 12,
                "wick": min(10, ms.lower_wick_ratio * 12),
                "momentum": 8 if ms.momentum_points > 0 else -6}
        comp.update(_penalties(ms))
        return _Candidate("LONG", "liquidity_sweep_reclaim", comp,
                          [f"swept prior low {ms.prev_low:.2f} then reclaimed (close {last['close']:.2f}).",
                           f"rejection wick ratio {ms.lower_wick_ratio:.2f}.",
                           f"momentum {ms.momentum_points:+.0f}pt."],
                          {"sweep_level": round(ms.prev_low, 2), "side": "low"})
    # Bearish sweep.
    swept_high = any(c["high"] > ms.prev_high for c in candles[-RECENT_EXCL - 1:])
    if swept_high and last["close"] < ms.prev_high and ms.upper_wick_ratio >= 0.4:
        comp = {"base": 45, "sweep": 18, "reclaim": 12,
                "wick": min(10, ms.upper_wick_ratio * 12),
                "momentum": 8 if ms.momentum_points < 0 else -6}
        comp.update(_penalties(ms))
        return _Candidate("SHORT", "liquidity_sweep_reclaim", comp,
                          [f"swept prior high {ms.prev_high:.2f} then rejected (close {last['close']:.2f}).",
                           f"rejection wick ratio {ms.upper_wick_ratio:.2f}.",
                           f"momentum {ms.momentum_points:+.0f}pt."],
                          {"sweep_level": round(ms.prev_high, 2), "side": "high"})
    return None


def _find_fvg(candles, point):
    """Most recent 3-candle imbalance in the last FVG_SCAN bars. Returns dict or None."""
    p = point or 0.01
    window = candles[-FVG_SCAN:]
    for i in range(len(window) - 3, -1, -1):
        c1, c3 = window[i], window[i + 2]
        if c1["high"] < c3["low"]:  # bullish gap
            return {"dir": "LONG", "low": c1["high"], "high": c3["low"],
                    "size_pts": round((c3["low"] - c1["high"]) / p, 1)}
        if c1["low"] > c3["high"]:  # bearish gap
            return {"dir": "SHORT", "low": c3["high"], "high": c1["low"],
                    "size_pts": round((c1["low"] - c3["high"]) / p, 1)}
    return None


def _detect_fvg(candles, ms, point, mode) -> _Candidate | None:
    fvg = _find_fvg(candles, point)
    if not fvg:
        return None
    p = point or 0.01
    close = ms.last_close
    near = fvg["low"] - RETEST_POINTS * p <= close <= fvg["high"] + RETEST_POINTS * p
    if not near:
        return None  # FVG exists but no retest yet — handled as a watch reason later
    direction = fvg["dir"]
    # Confirmation: momentum agrees with the gap direction.
    confirmed = (direction == "LONG" and ms.momentum_points > 0) or \
                (direction == "SHORT" and ms.momentum_points < 0)
    comp = {"base": 42, "fvg": 14, "retest": 10,
            "size": min(8, fvg["size_pts"] / 25.0),
            "confirm": 10 if confirmed else -8}
    comp.update(_penalties(ms))
    return _Candidate(direction, "fvg_retest", comp,
                      [f"price retesting {direction} FVG {fvg['low']:.2f}-{fvg['high']:.2f} "
                       f"({fvg['size_pts']:.0f}pt).",
                       f"momentum {'confirms' if confirmed else 'not confirming'} "
                       f"({ms.momentum_points:+.0f}pt)."],
                      {"fvg_zone": [round(fvg["low"], 2), round(fvg["high"], 2)],
                       "fvg_dir": direction})


def _detect_breakout_retest(candles, ms, point, mode) -> _Candidate | None:
    p = point or 0.01
    close = ms.last_close
    # Broke above prev_high then pulled back to retest it (within RETEST_POINTS).
    broke_up = any(c["high"] > ms.prev_high for c in candles[-SWING_WIN:])
    if broke_up and 0 <= (close - ms.prev_high) / p <= RETEST_POINTS and ms.momentum_points >= 0:
        comp = {"base": 44, "breakout": 14, "retest": 10,
                "trend": 6 if ms.regime == "trend" else 0}
        comp.update(_penalties(ms))
        return _Candidate("LONG", "breakout_retest", comp,
                          [f"broke above {ms.prev_high:.2f}, retesting from {close:.2f} "
                           f"({(close - ms.prev_high) / p:.0f}pt).",
                           f"regime {ms.regime}."],
                          {"breakout_level": round(ms.prev_high, 2), "side": "up"})
    broke_dn = any(c["low"] < ms.prev_low for c in candles[-SWING_WIN:])
    if broke_dn and 0 <= (ms.prev_low - close) / p <= RETEST_POINTS and ms.momentum_points <= 0:
        comp = {"base": 44, "breakout": 14, "retest": 10,
                "trend": 6 if ms.regime == "trend" else 0}
        comp.update(_penalties(ms))
        return _Candidate("SHORT", "breakout_retest", comp,
                          [f"broke below {ms.prev_low:.2f}, retesting from {close:.2f} "
                           f"({(ms.prev_low - close) / p:.0f}pt).",
                           f"regime {ms.regime}."],
                          {"breakout_level": round(ms.prev_low, 2), "side": "down"})
    return None


def _detect_momentum(candles, ms, point, mode) -> _Candidate | None:
    bull = ms.last_close > ms.sma_short > ms.sma_long and ms.momentum_points > 0
    bear = ms.last_close < ms.sma_short < ms.sma_long and ms.momentum_points < 0
    if not (bull or bear):
        return None
    strategy = "scalp_momentum" if mode == "scalp" else "momentum"
    comp = {"base": 45, "alignment": 18,
            "momentum": min(15, abs(ms.momentum_points) / 25.0),
            "body": min(12, ms.body_strength * 14),
            "session": _session_mod(ms.session)}
    comp.update(_penalties(ms))
    direction = "LONG" if bull else "SHORT"
    stack = "uptrend" if bull else "downtrend"
    return _Candidate(direction, strategy, comp,
                      [f"close {'above' if bull else 'below'} SMA{SMA_SHORT} {'above' if bull else 'below'} "
                       f"SMA{SMA_LONG} ({stack} stack).",
                       f"momentum {ms.momentum_points:+.0f}pt, body {ms.body_strength:.2f}.",
                       f"session {ms.session}."],
                      {})


def _detect_scalp_retest(candles, ms, point, mode) -> _Candidate | None:
    """Scalp: fast momentum + a micro pullback (small counter wick) into the move."""
    if mode != "scalp":
        return None
    p = point or 0.01
    fast_idx = max(0, len(candles) - 1 - SCALP_MOM_BARS)
    fast_mom = (ms.last_close - candles[fast_idx]["close"]) / p
    bull = ms.last_close > ms.sma_short and fast_mom > 0 and ms.lower_wick_ratio >= 0.3
    bear = ms.last_close < ms.sma_short and fast_mom < 0 and ms.upper_wick_ratio >= 0.3
    if not (bull or bear):
        return None
    comp = {"base": 44, "fast_momentum": min(14, abs(fast_mom) / 15.0),
            "micro_retest": 10, "session": _session_mod(ms.session)}
    comp.update(_penalties(ms))
    direction = "LONG" if bull else "SHORT"
    wick = ms.lower_wick_ratio if bull else ms.upper_wick_ratio
    return _Candidate(direction, "scalp_retest", comp,
                      [f"scalp {direction}: fast momentum {fast_mom:+.0f}pt over {SCALP_MOM_BARS} bars.",
                       f"micro pullback wick {wick:.2f} into the move."],
                      {})


def _penalties(ms: MarketState) -> dict[str, float]:
    """Shared spread / volatility / extension / chase penalties (negative)."""
    pen: dict[str, float] = {}
    if ms.spread_points > 25:
        pen["spread_penalty"] = -min(15, (ms.spread_points - 25) / 3.0)
    if ms.compression_state == "expanding":
        pen["vol_penalty"] = -6
    ext = abs(ms.last_close - ms.sma_long) / 0.01
    if ext > EXTENSION_POINTS:
        pen["extension_penalty"] = -min(15, (ext - EXTENSION_POINTS) / 80.0)
    return pen


def _session_mod(session: str) -> float:
    return {"London": 6, "NewYork": 6, "Asia": -2, "Off-session": -6}.get(session, 0)


def _new_idea(symbol, timeframe, mode, ms: MarketState | None, **kw) -> TradeIdea:
    return TradeIdea(
        decision_id=uuid.uuid4().hex[:12],
        timestamp=datetime.now(timezone.utc).isoformat(),
        symbol=symbol, timeframe=timeframe, risk_mode=mode,
        session=ms.session if ms else "unknown", regime=ms.regime if ms else "unknown",
        market_state=ms.to_dict() if ms else {},
        **kw,
    )


def _decide_core(
    candles: list[dict],
    *,
    symbol: str,
    timeframe: str,
    risk_mode: str,
    spread_points: float,
    point: float,
    has_open_position: bool,
) -> TradeIdea:
    mode = risk_mode.lower()
    sl_pts, tp_pts = SLTP_POINTS.get(mode, SLTP_POINTS["balanced"])
    max_spread = MAX_SPREAD_POINTS.get(mode, 60)
    min_conf = MIN_CONFIDENCE.get(mode, 55)

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
                         blockers=["position stacking disabled in V2 - manage the existing trade."])

    # Global blockers.
    blockers: list[str] = []
    if ms.spread_points > max_spread:
        blockers.append(f"spread {ms.spread_points:.0f}pt > max {max_spread}pt for {mode}.")
    last_range_pts = (candles[-1]["high"] - candles[-1]["low"]) / (point or 0.01)
    # Chaotic = an outsized range WITHOUT a dominant rejection wick. A clean
    # sweep candle is also large-range but has a strong one-sided wick, so it is
    # NOT treated as chaotic.
    dominant_wick = max(ms.upper_wick_ratio, ms.lower_wick_ratio)
    if (ms.volatility_points > 0 and last_range_pts > CHAOTIC_RANGE_MULT * ms.volatility_points
            and dominant_wick < 0.5):
        blockers.append("last candle range is chaotic (>3x average, no rejection wick) - standing aside.")
    if blockers:
        strat = "no_trade_spread" if any("spread" in b for b in blockers) else "no_trade_chop"
        return _new_idea(symbol, timeframe, mode, ms, decision="NO_TRADE",
                         strategy=strat, confidence=0, entry_reference_price=entry,
                         sl_points=None, tp_points=None, blockers=blockers)

    # Run detectors. Scalp mode favors scalp + structure; others run the full stack.
    if mode == "scalp":
        detectors = [_detect_sweep, _detect_fvg, _detect_scalp_retest, _detect_momentum]
    else:
        detectors = [_detect_sweep, _detect_fvg, _detect_breakout_retest, _detect_momentum]

    candidates: list[_Candidate] = []
    for d in detectors:
        c = d(candles, ms, point, mode)
        if c is not None:
            candidates.append(c)

    # Pick best: meets confidence, then by priority, then confidence.
    valid = [c for c in candidates if c.confidence >= min_conf]
    if valid:
        valid.sort(key=lambda c: (c.priority, -c.confidence))
        best = valid[0]
        return _new_idea(symbol, timeframe, mode, ms, decision=best.decision, strategy=best.strategy,
                         confidence=best.confidence, entry_reference_price=entry,
                         sl_points=sl_pts, tp_points=tp_pts, reasons=best.reasons,
                         zones=best.zones, confidence_components={k: round(v, 1) for k, v in best.components.items()},
                         should_execute_demo=True)

    # No tradeable setup — explain the best near-miss / watch context.
    reasons: list[str] = []
    zones: dict[str, Any] = {}
    if candidates:
        nearest = max(candidates, key=lambda c: c.confidence)
        reasons.append(f"{nearest.strategy} seen but confidence {nearest.confidence} < min {min_conf}.")
        reasons += nearest.reasons
        zones = nearest.zones
    else:
        fvg = _find_fvg(candles, point)
        if fvg:
            zones = {"fvg_zone": [round(fvg["low"], 2), round(fvg["high"], 2)], "fvg_dir": fvg["dir"]}
            reasons.append(f"{fvg['dir']} FVG {fvg['low']:.2f}-{fvg['high']:.2f} present but not retesting yet.")
        elif ms.dist_from_high_points <= NEAR_EXTREME_POINTS:
            reasons.append(f"{ms.dist_from_high_points:.0f}pt under recent high - watching for breakout.")
        elif ms.dist_from_low_points <= NEAR_EXTREME_POINTS:
            reasons.append(f"{ms.dist_from_low_points:.0f}pt above recent low - watching for breakdown.")
        else:
            reasons.append(f"{ms.regime} / {ms.compression_state} with no clean setup - no edge.")
    return _new_idea(symbol, timeframe, mode, ms, decision="NO_TRADE", strategy="no_trade",
                     confidence=0, entry_reference_price=entry, sl_points=None, tp_points=None,
                     reasons=reasons, zones=zones)


# ── macro / news / event overlay (LM77A) ─────────────────────────────────────
def _apply_macro(
    idea: TradeIdea,
    macro: MacroContext,
    *,
    mode: str,
    min_conf: int,
    ignore_lockout: bool,
) -> TradeIdea:
    """
    Fold the macro context into a technical TradeIdea. Lockout is a hard gate;
    watch / post-event reduce confidence (scalp stricter); DXY/yields/geo nudge
    a directional idea. Pure: mutates and returns the same idea.
    """
    idea.macro = macro.to_dict()
    idea.warnings = list(idea.warnings) + list(macro.warnings)
    applied = {"confidence_delta": 0, "forced_no_trade": False, "overrode_lockout": False}

    # 1) Lockout — hard gate (all modes) unless explicitly overridden (demo dry-run).
    if macro.event_risk_state == "lockout":
        if ignore_lockout:
            idea.warnings.append(
                "event lockout overridden (--ignore-event-lockout-demo); demo dry-run only.")
            applied["overrode_lockout"] = True
        else:
            if idea.decision in ("LONG", "SHORT"):
                idea.decision = "NO_TRADE"
                idea.strategy = "macro_lockout"
                idea.confidence = 0
                idea.should_execute_demo = False
                applied["forced_no_trade"] = True
            idea.blockers.append(
                f"High-impact {macro.event_type} lockout window active "
                f"({macro.event_currency}, {macro.minutes_to_next_event:+d}m).")
            idea.reasons += [f"macro: {r}" for r in macro.reasons]
            idea.macro["applied"] = applied
            return idea

    # Attach macro reasons regardless of decision.
    idea.reasons += [f"macro: {r}" for r in macro.reasons]

    # 2) Directional ideas: event window + DXY/yields/geo + scalp strictness.
    if idea.decision in ("LONG", "SHORT"):
        delta = macro.confidence_modifier
        dir_delta, dir_reasons = macro_directional_adjustment(macro, idea.decision)
        delta += dir_delta
        idea.reasons += [f"macro: {r}" for r in dir_reasons]

        if mode == "scalp":
            if macro.event_risk_state == "post_event":
                idea.decision = "NO_TRADE"
                idea.strategy = "macro_post_event_scalp"
                idea.should_execute_demo = False
                idea.confidence = max(0, idea.confidence + delta)
                idea.blockers.append("scalp blocked in post-event window (volatility).")
                applied.update({"forced_no_trade": True, "confidence_delta": delta})
                idea.macro["applied"] = applied
                return idea
            if macro.event_risk_state == "watch":
                delta -= 8
                idea.reasons.append("macro: scalp tightened in watch window (-8).")

        new_conf = max(0, min(100, idea.confidence + delta))
        applied["confidence_delta"] = delta
        if new_conf < min_conf:
            idea.blockers.append(
                f"macro pulled confidence to {new_conf} < min {min_conf} for {mode}.")
            idea.decision = "NO_TRADE"
            idea.strategy = "macro_low_confidence"
            idea.should_execute_demo = False
            applied["forced_no_trade"] = True
        idea.confidence = new_conf

    idea.macro["applied"] = applied
    return idea


def decide(
    candles: list[dict],
    *,
    symbol: str,
    timeframe: str,
    risk_mode: str,
    spread_points: float,
    point: float,
    has_open_position: bool,
    macro: MacroContext | None = None,
    ignore_event_lockout: bool = False,
) -> TradeIdea:
    """
    Public entry point. Runs the pure technical engine, then (optionally) folds
    in the macro/news/event context. With ``macro=None`` the result is identical
    to the technical engine — macro is purely additive.
    """
    idea = _decide_core(
        candles, symbol=symbol, timeframe=timeframe, risk_mode=risk_mode,
        spread_points=spread_points, point=point, has_open_position=has_open_position,
    )
    if macro is None:
        return idea
    mode = risk_mode.lower()
    return _apply_macro(idea, macro, mode=mode, min_conf=MIN_CONFIDENCE.get(mode, 55),
                        ignore_lockout=ignore_event_lockout)
