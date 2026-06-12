"""
tests/test_gold_bot_decision_engine.py
----------------------------------------
LM76A — Pure tests for the Gold Bot decision engine V1. No MT5, no network.
"""

from __future__ import annotations

from services.gold_bot_decision_engine import (
    SLTP_POINTS,
    decide,
)

POINT = 0.01


def _candles(closes: list[float], *, body=1.0, wick=0.5) -> list[dict]:
    out = []
    for c in closes:
        o = c - body  # bullish body by default; sign of (c-o) doesn't gate trend
        out.append({"time": "t", "open": round(o, 2), "high": round(max(o, c) + wick, 2),
                    "low": round(min(o, c) - wick, 2), "close": round(c, 2)})
    return out


def _rising(n=40, start=2300.0, step=2.0):
    return _candles([start + i * step for i in range(n)])


def _falling(n=40, start=2380.0, step=2.0):
    return _candles([start - i * step for i in range(n)])


def _flat(n=40, base=2300.0):
    # constant close → SMAs equal last_close → no trend stack (no LONG/SHORT)
    return _candles([base for _ in range(n)])


def test_bullish_candles_give_long():
    idea = decide(_rising(), symbol="XAUUSD", timeframe="M1", risk_mode="balanced",
                  spread_points=20, point=POINT, has_open_position=False)
    assert idea.decision == "LONG"
    assert idea.strategy == "momentum"
    assert idea.sl_points == 300 and idea.tp_points == 600
    assert idea.should_execute_demo is True
    assert idea.confidence >= 55


def test_bearish_candles_give_short():
    idea = decide(_falling(), symbol="XAUUSD", timeframe="M1", risk_mode="balanced",
                  spread_points=20, point=POINT, has_open_position=False)
    assert idea.decision == "SHORT"
    assert idea.strategy == "momentum"


def test_high_spread_blocks():
    idea = decide(_rising(), symbol="XAUUSD", timeframe="M1", risk_mode="balanced",
                  spread_points=500, point=POINT, has_open_position=False)
    assert idea.decision == "NO_TRADE"
    assert any("spread" in b for b in idea.blockers)


def test_open_position_blocks():
    idea = decide(_rising(), symbol="XAUUSD", timeframe="M1", risk_mode="balanced",
                  spread_points=20, point=POINT, has_open_position=True)
    assert idea.decision == "NO_TRADE"
    assert idea.strategy == "manage_existing"
    assert any("stacking disabled" in b for b in idea.blockers)


def test_insufficient_candles_blocks():
    idea = decide(_rising(n=10), symbol="XAUUSD", timeframe="M1", risk_mode="balanced",
                  spread_points=20, point=POINT, has_open_position=False)
    assert idea.decision == "NO_TRADE"
    assert any("insufficient" in b for b in idea.blockers)


def test_scalp_uses_smaller_sl_tp():
    idea = decide(_rising(), symbol="XAUUSD", timeframe="M1", risk_mode="scalp",
                  spread_points=10, point=POINT, has_open_position=False)
    assert idea.decision == "LONG"
    assert idea.strategy == "scalp_momentum"
    assert (idea.sl_points, idea.tp_points) == SLTP_POINTS["scalp"] == (120, 180)


def test_scalp_rejects_wide_spread():
    # 50pt spread is fine for balanced but over scalp's 35pt ceiling.
    idea = decide(_rising(), symbol="XAUUSD", timeframe="M1", risk_mode="scalp",
                  spread_points=50, point=POINT, has_open_position=False)
    assert idea.decision == "NO_TRADE"
    assert any("spread" in b for b in idea.blockers)


def test_chaotic_last_candle_blocks():
    candles = _rising()
    candles[-1]["high"] = candles[-1]["close"] + 50.0   # huge range vs ~2 avg
    candles[-1]["low"] = candles[-1]["open"] - 50.0
    idea = decide(candles, symbol="XAUUSD", timeframe="M1", risk_mode="balanced",
                  spread_points=20, point=POINT, has_open_position=False)
    assert idea.decision == "NO_TRADE"
    assert any("chaotic" in b for b in idea.blockers)


def test_flat_market_no_trade():
    idea = decide(_flat(), symbol="XAUUSD", timeframe="M1", risk_mode="balanced",
                  spread_points=20, point=POINT, has_open_position=False)
    assert idea.decision == "NO_TRADE"
    assert idea.should_execute_demo is False
