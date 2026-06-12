"""
tests/test_gold_bot_decision_engine.py
----------------------------------------
LM76B — Pure tests for the Gold Bot strategy engine V2. No MT5, no network.
"""

from __future__ import annotations

from datetime import datetime, timezone

from services.gold_bot_decision_engine import (
    SLTP_POINTS,
    compute_market_state,
    decide,
    _find_fvg,
)
from services.gold_bot_macro_context import build_macro_context

POINT = 0.01
_NOW = datetime(2026, 6, 12, 13, 0, 0, tzinfo=timezone.utc)


def _macro(events=None, **biases):
    return build_macro_context(_NOW, events or [], "sample", **biases)


def _lockout_event(minutes_from_now=20):
    return [{"name": "US CPI", "type": "CPI", "currency": "USD",
             "impact": "high", "minutes_from_now": minutes_from_now}]


def _c(o, h, l, cl, t="2026-06-12T13:00:00+00:00"):
    return {"time": t, "open": o, "high": h, "low": l, "close": cl}


def _candles(closes, *, body=1.0, wick=0.5):
    return [_c(c - body, max(c - body, c) + wick, min(c - body, c) - wick, c) for c in closes]


def _rising(n=40, start=2300.0, step=2.0):
    return _candles([start + i * step for i in range(n)])


def _falling(n=40, start=2380.0, step=2.0):
    return _candles([start - i * step for i in range(n)])


def _flat(n=40, base=2300.0):
    return _candles([base for _ in range(n)])


def _decide(candles, **kw):
    base = dict(symbol="XAUUSD", timeframe="M1", risk_mode="balanced",
                spread_points=20, point=POINT, has_open_position=False)
    base.update(kw)
    return decide(candles, **base)


# ── momentum (carried from V1) ────────────────────────────────────────────────
def test_bullish_trend_gives_long():
    idea = _decide(_rising())
    assert idea.decision == "LONG"
    assert idea.sl_points == 300 and idea.tp_points == 600
    assert idea.session == "NewYork"
    assert idea.confidence_components  # explainable breakdown present


def test_bearish_trend_gives_short():
    idea = _decide(_falling())
    assert idea.decision == "SHORT"


# ── liquidity sweep + reclaim ─────────────────────────────────────────────────
def test_bullish_sweep_reclaim_long():
    # Range, then a spike below prior low that closes back inside with a long lower wick.
    candles = _candles([2300.0 + (i % 3) for i in range(36)])  # choppy range ~2300-2302
    # sweep candle: dips to 2294 (below prev_low) but closes 2301 (reclaim), big lower wick.
    candles.append(_c(2300.0, 2301.5, 2294.0, 2301.2))
    idea = _decide(candles)
    assert idea.decision == "LONG"
    assert idea.strategy == "liquidity_sweep_reclaim"
    assert "sweep_level" in idea.zones


def test_bearish_sweep_reclaim_short():
    candles = _candles([2300.0 + (i % 3) for i in range(36)])
    candles.append(_c(2302.0, 2309.0, 2301.5, 2301.8))  # spike above prev_high, close back below
    idea = _decide(candles)
    assert idea.decision == "SHORT"
    assert idea.strategy == "liquidity_sweep_reclaim"
    assert idea.zones.get("side") == "high"


# ── FVG ───────────────────────────────────────────────────────────────────────
def test_bullish_fvg_detected():
    # candle1.high < candle3.low → bullish gap
    cs = [_c(2300, 2301, 2299, 2300), _c(2301, 2305, 2301, 2304), _c(2306, 2308, 2306, 2307)]
    fvg = _find_fvg(cs, POINT)
    assert fvg and fvg["dir"] == "LONG"
    assert fvg["high"] == 2306 and fvg["low"] == 2301


def test_bearish_fvg_detected():
    cs = [_c(2308, 2309, 2306, 2307), _c(2304, 2305, 2301, 2302), _c(2300, 2301, 2299, 2300)]
    fvg = _find_fvg(cs, POINT)
    assert fvg and fvg["dir"] == "SHORT"


# ── breakout / retest ─────────────────────────────────────────────────────────
def test_breakout_retest_candidate():
    # Range to ~2310, break above, then retest just above the prior high.
    candles = _candles([2300.0 + (i % 4) for i in range(34)])
    candles.append(_c(2304, 2316, 2304, 2315))   # breakout up through prev_high (~2303)
    candles.append(_c(2315, 2316, 2304, 2305))   # pull back to retest near prev_high
    idea = _decide(candles)
    assert idea.decision in ("LONG", "NO_TRADE")  # breakout_retest or sweep may win
    if idea.decision == "LONG":
        assert idea.strategy in ("breakout_retest", "liquidity_sweep_reclaim", "momentum")


# ── NO_TRADE paths ────────────────────────────────────────────────────────────
def test_choppy_market_no_trade():
    idea = _decide(_flat())
    assert idea.decision == "NO_TRADE"
    assert idea.should_execute_demo is False


def test_high_spread_no_trade():
    idea = _decide(_rising(), spread_points=500)
    assert idea.decision == "NO_TRADE"
    assert idea.strategy == "no_trade_spread"
    assert any("spread" in b for b in idea.blockers)


def test_chaotic_no_trade():
    candles = _rising()
    candles[-1]["high"] = candles[-1]["close"] + 60.0
    candles[-1]["low"] = candles[-1]["open"] - 60.0
    idea = _decide(candles)
    assert idea.decision == "NO_TRADE"
    assert idea.strategy == "no_trade_chop"


def test_open_position_blocks():
    idea = _decide(_rising(), has_open_position=True)
    assert idea.decision == "NO_TRADE"
    assert idea.strategy == "manage_existing"


def test_insufficient_candles_blocks():
    idea = _decide(_rising(n=10))
    assert idea.decision == "NO_TRADE"
    assert any("insufficient" in b for b in idea.blockers)


# ── scalp mode ────────────────────────────────────────────────────────────────
def test_scalp_uses_smaller_sl_tp():
    idea = _decide(_rising(), risk_mode="scalp", spread_points=10)
    assert idea.decision == "LONG"
    assert idea.strategy in ("scalp_retest", "scalp_momentum", "liquidity_sweep_reclaim")
    assert (idea.sl_points, idea.tp_points) == SLTP_POINTS["scalp"] == (120, 180)


def test_scalp_blocks_wide_spread():
    idea = _decide(_rising(), risk_mode="scalp", spread_points=50)
    assert idea.decision == "NO_TRADE"
    assert idea.strategy == "no_trade_spread"


# ── macro / news / event overlay (LM77A) ──────────────────────────────────────
def test_macro_none_is_identical_to_technical():
    base = _decide(_rising())
    with_macro = _decide(_rising(), macro=None)
    assert base.decision == with_macro.decision == "LONG"


def test_lockout_converts_long_to_no_trade():
    idea = _decide(_rising(), macro=_macro(_lockout_event(20)))
    assert idea.decision == "NO_TRADE"
    assert idea.strategy == "macro_lockout"
    assert idea.should_execute_demo is False
    assert any("lockout" in b.lower() for b in idea.blockers)


def test_lockout_converts_short_to_no_trade():
    idea = _decide(_falling(), macro=_macro(_lockout_event(15)))
    assert idea.decision == "NO_TRADE"
    assert idea.strategy == "macro_lockout"


def test_ignore_lockout_override_keeps_decision_dry_run():
    idea = _decide(_rising(), macro=_macro(_lockout_event(20)), ignore_event_lockout=True)
    assert idea.decision == "LONG"
    assert any("overridden" in w.lower() for w in idea.warnings)


def test_dxy_yields_rising_penalises_long_confidence():
    plain = _decide(_rising())
    biased = _decide(_rising(), macro=_macro(dxy_bias="rising", yields_bias="rising"))
    assert biased.decision == "LONG"
    assert biased.confidence < plain.confidence
    assert biased.macro["applied"]["confidence_delta"] < 0


def test_dxy_yields_falling_helps_long_confidence():
    plain = _decide(_rising())
    biased = _decide(_rising(), macro=_macro(dxy_bias="falling", yields_bias="falling"))
    assert biased.confidence >= plain.confidence


def test_scalp_blocked_in_post_event_window():
    # CPI released 5 min ago → post_event; scalp must stand aside.
    idea = _decide(_rising(), risk_mode="scalp", spread_points=10,
                   macro=_macro(_lockout_event(-5)))
    assert idea.decision == "NO_TRADE"
    assert idea.strategy == "macro_post_event_scalp"


def test_macro_context_attached_to_idea():
    idea = _decide(_rising(), macro=_macro(dxy_bias="rising"))
    assert idea.macro
    assert idea.macro["source_mode"] == "sample"
    assert "applied" in idea.macro


# ── market state context ──────────────────────────────────────────────────────
def test_market_state_has_v2_context():
    ms = compute_market_state(_rising(), spread_points=20, point=POINT)
    assert ms.regime in ("trend", "range")
    assert ms.compression_state in ("compressed", "expanding", "normal")
    assert ms.session == "NewYork"
    assert ms.swing_high >= ms.swing_low
    assert ms.prev_high >= ms.prev_low
