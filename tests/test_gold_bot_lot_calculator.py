"""
tests/test_gold_bot_lot_calculator.py
--------------------------------------
LM75D — Pure tests for risk-percent resolution and auto lot sizing.
"""

from __future__ import annotations

import pytest

from services.gold_bot_lot_calculator import (
    DEFAULT_MAX_RISK_PCT,
    HIGH_DEMO_MAX_RISK_PCT,
    RISK_MODE_PCT,
    calc_auto_volume,
    confidence_risk_fraction,
    resolve_risk_pct,
)


# ── risk pct resolution ───────────────────────────────────────────────────────
def test_mode_defaults():
    assert resolve_risk_pct(mode="safe", override_pct=None, allow_high_demo_risk=False).pct == 0.25
    assert resolve_risk_pct(mode="balanced", override_pct=None, allow_high_demo_risk=False).pct == 0.50
    assert resolve_risk_pct(mode="aggressive", override_pct=None, allow_high_demo_risk=False).pct == 1.00


def test_override_capped_at_default():
    r = resolve_risk_pct(mode="balanced", override_pct=5.0, allow_high_demo_risk=False)
    assert r.pct == DEFAULT_MAX_RISK_PCT
    assert any("capped" in w for w in r.warnings)


def test_override_capped_at_high_demo():
    r = resolve_risk_pct(mode="balanced", override_pct=5.0, allow_high_demo_risk=True)
    assert r.pct == HIGH_DEMO_MAX_RISK_PCT


def test_experimental_stays_small():
    r = resolve_risk_pct(mode="experimental", override_pct=5.0, allow_high_demo_risk=True)
    assert r.pct <= 0.25


def test_nonpositive_pct_fails():
    r = resolve_risk_pct(mode="balanced", override_pct=0, allow_high_demo_risk=False)
    assert r.pct == 0.0


# ── auto volume ───────────────────────────────────────────────────────────────
def test_auto_volume_scales_to_target():
    # loss is 300 per 1.0 lot → linear. target 30 → 0.1 lot.
    def loss(v):
        return 300.0 * v
    plan = calc_auto_volume(target_risk_amount=30.0, loss_at_volume=loss,
                            volume_min=0.01, volume_step=0.01, volume_max=50.0)
    assert plan is not None
    assert plan.volume == pytest.approx(0.10)
    assert plan.estimated_loss == pytest.approx(30.0)


def test_auto_volume_rounds_down_to_step():
    def loss(v):
        return 100.0 * v  # target 25 → raw 0.25 exactly
    plan = calc_auto_volume(target_risk_amount=27.0, loss_at_volume=loss,
                            volume_min=0.01, volume_step=0.05, volume_max=50.0)
    # raw = 0.27 → round down to step 0.05 → 0.25
    assert plan.volume == pytest.approx(0.25)
    assert plan.estimated_loss <= 27.0


def test_auto_volume_floors_at_min_with_warning():
    def loss(v):
        return 10000.0 * v  # even 0.01 lot loses 100 > target 5
    plan = calc_auto_volume(target_risk_amount=5.0, loss_at_volume=loss,
                            volume_min=0.01, volume_step=0.01, volume_max=50.0)
    assert plan.volume == 0.01
    assert plan.at_min is True
    assert any("floored" in w for w in plan.warnings)


def test_auto_volume_fail_closed_when_loss_uncomputable():
    assert calc_auto_volume(target_risk_amount=30.0, loss_at_volume=lambda v: None,
                            volume_min=0.01, volume_step=0.01, volume_max=50.0) is None


# ── LM75D scalp mode ──────────────────────────────────────────────────────────
def test_scalp_mode_default_pct():
    r = resolve_risk_pct(mode="scalp", override_pct=None, allow_high_demo_risk=False)
    assert r.pct == 0.10
    assert RISK_MODE_PCT["scalp"] == 0.10


def test_scalp_mode_stays_small_even_with_override():
    r = resolve_risk_pct(mode="scalp", override_pct=5.0, allow_high_demo_risk=True)
    assert r.pct <= 0.25


# ── LM103A demo-only hard mode ─────────────────────────────────────────────────
def test_hard_demo_lifts_small_cap():
    # scalp normally caps at 0.25; hard_demo lifts it to the requested override.
    r = resolve_risk_pct(mode="scalp", override_pct=5.0, allow_high_demo_risk=True, hard_demo=True)
    assert r.pct == 5.0


def test_hard_demo_capped_at_wall():
    from services.gold_bot_lot_calculator import HARD_DEMO_MAX_RISK_PCT
    r = resolve_risk_pct(mode="balanced", override_pct=50.0, allow_high_demo_risk=True, hard_demo=True)
    assert r.pct == HARD_DEMO_MAX_RISK_PCT == 10.0
    assert any("capped" in w for w in r.warnings)


def test_hard_demo_off_unchanged():
    # Without hard_demo the small cap still applies (no behavior change).
    assert resolve_risk_pct(mode="scalp", override_pct=5.0, allow_high_demo_risk=True).pct <= 0.25


# ── LM99A confidence-scaled risk fraction (demo-only sizing) ───────────────────
def test_confidence_fraction_full_at_or_above_full_confidence():
    assert confidence_risk_fraction(100, min_confidence=50) == 1.0
    assert confidence_risk_fraction(120, min_confidence=50) == 1.0


def test_confidence_fraction_floor_at_or_below_min():
    assert confidence_risk_fraction(50, min_confidence=50, floor_fraction=0.5) == 0.5
    assert confidence_risk_fraction(10, min_confidence=50, floor_fraction=0.5) == 0.5


def test_confidence_fraction_linear_midpoint():
    # min 50, full 100, floor 0.5 → at 75 → 0.5 + 0.5*0.5 = 0.75
    assert confidence_risk_fraction(75, min_confidence=50, floor_fraction=0.5) == pytest.approx(0.75)


def test_confidence_fraction_never_exceeds_one():
    # Across the whole band the fraction must stay within (0, 1].
    for c in range(0, 121, 5):
        f = confidence_risk_fraction(c, min_confidence=50, floor_fraction=0.5)
        assert 0.0 < f <= 1.0


def test_confidence_fraction_respects_custom_floor():
    assert confidence_risk_fraction(50, min_confidence=50, floor_fraction=0.25) == 0.25
    assert confidence_risk_fraction(0, min_confidence=50, floor_fraction=0.0) == 0.0


def test_confidence_fraction_degenerate_band_no_scaling():
    # full <= min → no scaling (1.0), never a divide-by-zero.
    assert confidence_risk_fraction(60, min_confidence=100, full_confidence=100) == 1.0


def test_confidence_fraction_non_numeric_falls_back_to_one():
    assert confidence_risk_fraction(None, min_confidence=50) == 1.0
