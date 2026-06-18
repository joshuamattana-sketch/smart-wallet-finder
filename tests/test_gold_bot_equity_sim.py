"""
tests/test_gold_bot_equity_sim.py
----------------------------------
LM110A - Pure tests for the equity / risk-of-ruin simulator.
"""

from __future__ import annotations

from services.gold_bot_equity_sim import extract_realized, simulate_equity


def test_full_sl_loss_equals_risk_pct():
    # one trade losing a full SL at 10% risk → balance ×0.9
    r = simulate_equity([-1000.0], sl_points=1000, risk_pct=10.0, start_balance=10000.0)
    assert r.final_balance == 9000.0
    assert r.losses == 1 and r.wins == 0


def test_compounding_winner():
    # +TP twice: r=2000 over SL 1000 at 5% → +10% each, compounded
    r = simulate_equity([2000.0, 2000.0], sl_points=1000, risk_pct=5.0, start_balance=10000.0)
    assert r.final_balance == round(10000.0 * 1.10 * 1.10, 2)   # 12100
    assert r.wins == 2


def test_high_risk_ruins_on_loss_streak():
    # 80% risk, several full-SL losses → ruin (balance collapses)
    losses = [-1000.0] * 5
    r = simulate_equity(losses, sl_points=1000, risk_pct=80.0, start_balance=10000.0)
    assert r.ruined is True
    assert r.ruin_at_trade is not None and r.ruin_at_trade <= 3   # ×0.2 each → dead fast
    assert r.longest_loss_streak == 5


def test_small_risk_survives_same_streak():
    losses = [-1000.0] * 5
    r = simulate_equity(losses, sl_points=1000, risk_pct=1.0, start_balance=10000.0)
    assert r.ruined is False
    assert r.final_balance > 9000.0          # only ~5% drawdown at 1% risk


def test_max_drawdown_tracked():
    seq = [2000.0, -1000.0, -1000.0]          # up then two losses
    r = simulate_equity(seq, sl_points=1000, risk_pct=10.0, start_balance=10000.0)
    assert r.max_drawdown_pct > 0


def test_extract_realized_skips_no_trade():
    rows = [
        {"decision": "LONG", "score": {"30": {"realized_return_points": 12.0}}},
        {"decision": "NO_TRADE", "score": {"30": {"realized_return_points": None}}},
        {"decision": "SHORT", "score": {"30": {"realized_return_points": -8.0}}},
    ]
    assert extract_realized(rows, 30) == [12.0, -8.0]
