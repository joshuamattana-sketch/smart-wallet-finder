"""
services/gold_bot_lot_calculator.py
------------------------------------
LM75D — Pure risk-aware lot sizing + risk-percent resolution.

No MT5, no I/O. The bot thinks in equity / risk% / stop distance / contract
metadata — never in "leverage". Given a loss estimator (ideally backed by
mt5.order_calc_profit) the calculator finds the largest volume whose estimated
stop-loss loss stays at or under the target risk amount, respecting the
symbol's volume_min/step/max. Fails closed (returns None) when it cannot size.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

# Default risk-per-trade by mode (percent of equity).
RISK_MODE_PCT = {
    "safe": 0.25,
    "balanced": 0.50,
    "aggressive": 1.00,
    "experimental": 0.10,  # demo-only, deliberately tiny for new ideas
    "scalp": 0.10,         # demo-only high-frequency M1/M5 scalp testing
}
RISK_MODES = tuple(RISK_MODE_PCT)

# Modes that stay small regardless of override/high-demo flag (demo-only,
# experimental in spirit).
SMALL_CAP_MODES = ("experimental", "scalp")

# Hard caps on risk-per-trade (percent of equity).
DEFAULT_MAX_RISK_PCT = 1.0          # without --allow-high-demo-risk
HIGH_DEMO_MAX_RISK_PCT = 2.0        # even with the override, demo never exceeds this
EXPERIMENTAL_MAX_RISK_PCT = 0.25    # experimental/scalp stay small regardless
# LM103A demo-only HARD mode: an explicit, higher ceiling used ONLY behind the
# --hard-mode flag on a verified demo account. Even hard mode never exceeds this
# wall, and the daily-loss budget in the risk gate still bounds each trade.
HARD_DEMO_MAX_RISK_PCT = 10.0


@dataclass
class RiskPctResolution:
    pct: float
    warnings: list[str] = field(default_factory=list)


def resolve_risk_pct(
    *,
    mode: str,
    override_pct: float | None,
    allow_high_demo_risk: bool,
    hard_demo: bool = False,
) -> RiskPctResolution:
    """
    Resolve the effective risk-per-trade percent. An explicit --risk-pct
    overrides the mode default; both are then capped. Experimental/scalp are kept
    small UNLESS hard_demo is set (LM103A demo-only hard mode), which lifts the
    ceiling to HARD_DEMO_MAX_RISK_PCT and opts out of the small-cap shrink. Even
    hard mode never exceeds that wall. Returns the capped pct plus any warnings.
    """
    warnings: list[str] = []
    mode = mode.lower()
    base = override_pct if override_pct is not None else RISK_MODE_PCT.get(mode, RISK_MODE_PCT["balanced"])

    if base <= 0:
        # Fail closed at the caller; signal with 0 + warning.
        warnings.append("risk-pct must be > 0.")
        return RiskPctResolution(pct=0.0, warnings=warnings)

    if hard_demo:
        cap = HARD_DEMO_MAX_RISK_PCT
    else:
        cap = HIGH_DEMO_MAX_RISK_PCT if allow_high_demo_risk else DEFAULT_MAX_RISK_PCT
        if mode in SMALL_CAP_MODES:
            cap = min(cap, EXPERIMENTAL_MAX_RISK_PCT)

    pct = base
    if pct > cap:
        warnings.append(f"risk-pct {pct:.2f}% capped to {cap:.2f}% "
                        f"({'demo high-risk cap' if allow_high_demo_risk else 'default cap'}).")
        pct = cap

    return RiskPctResolution(pct=round(pct, 4), warnings=warnings)


# Confidence-scaled sizing (LM99A, demo-only). The returned fraction is ALWAYS
# within (0, 1], so it can only ever risk LESS than the configured risk% — it can
# never raise the per-trade risk above the resolved risk-pct / risk-gate ceiling.
DEFAULT_LOT_CONFIDENCE_FLOOR = 0.5


def confidence_risk_fraction(
    confidence: float,
    *,
    min_confidence: float,
    full_confidence: float = 100.0,
    floor_fraction: float = DEFAULT_LOT_CONFIDENCE_FLOOR,
) -> float:
    """
    Map a decision confidence to a fraction of the configured risk amount.

    `floor_fraction` at (or below) `min_confidence`, 1.0 at (or above)
    `full_confidence`, linear in between. Clamped to [floor_fraction, 1.0] so
    confidence scaling can only REDUCE the risk amount, never raise it above what
    resolve_risk_pct already allows. Pure; no I/O. Non-numeric / degenerate band
    falls back to 1.0 (no scaling).
    """
    try:
        c = float(confidence)
    except (TypeError, ValueError):
        return 1.0
    floor = min(1.0, max(0.0, float(floor_fraction)))
    lo, hi = float(min_confidence), float(full_confidence)
    if hi <= lo:
        return 1.0
    if c <= lo:
        return floor
    if c >= hi:
        return 1.0
    frac = floor + (1.0 - floor) * (c - lo) / (hi - lo)
    return round(min(1.0, max(floor, frac)), 4)


@dataclass
class LotPlan:
    volume: float
    estimated_loss: float          # absolute EUR/account-ccy loss at SL
    target_risk_amount: float
    at_min: bool = False           # volume floored at volume_min
    warnings: list[str] = field(default_factory=list)


def _round_down_to_step(value: float, step: float) -> float:
    if step <= 0:
        return value
    # Avoid float drift (e.g. 0.07000000000001) by working in step units.
    n = int(round(value / step + 1e-9))
    # round_down: ensure we don't exceed value
    while n * step > value + 1e-9 and n > 0:
        n -= 1
    return round(n * step, 8)


def calc_auto_volume(
    *,
    target_risk_amount: float,
    loss_at_volume: Callable[[float], float | None],
    volume_min: float,
    volume_step: float,
    volume_max: float,
) -> LotPlan | None:
    """
    Largest volume whose estimated SL loss <= target_risk_amount.

    `loss_at_volume(v)` returns the ABSOLUTE loss (>0) for volume v, or None if
    it can't be computed. order_calc_profit is linear in volume, so we measure
    the loss at volume_min once and scale — then round DOWN to the step grid and
    clamp to [min, max]. Returns None (fail closed) if inputs are unusable.
    """
    if target_risk_amount <= 0 or volume_min <= 0 or volume_max < volume_min:
        return None
    step = volume_step if volume_step > 0 else volume_min

    loss_min = loss_at_volume(volume_min)
    if loss_min is None or loss_min <= 0:
        return None

    warnings: list[str] = []
    # Loss is linear: loss(v) = loss_min * v / volume_min.
    loss_per_lot = loss_min / volume_min
    raw_volume = target_risk_amount / loss_per_lot

    if raw_volume < volume_min:
        # Even the smallest tradable size risks more than target — floor at min.
        vol = volume_min
        at_min = True
        warnings.append(
            f"volume floored at min {volume_min}: its SL loss "
            f"{loss_min:.2f} exceeds target {target_risk_amount:.2f}."
        )
    else:
        vol = _round_down_to_step(min(raw_volume, volume_max), step)
        vol = max(vol, volume_min)
        at_min = vol <= volume_min
        if raw_volume > volume_max:
            warnings.append(f"volume capped at max {volume_max}.")

    est_loss = loss_at_volume(vol)
    if est_loss is None:
        return None

    # order_calc_profit isn't perfectly linear (broker rounding), so the scaled
    # volume can overshoot the target slightly. Step down until at/under target
    # (bounded), unless already at the minimum tradable size.
    guard = 0
    while est_loss is not None and est_loss > target_risk_amount and vol - step >= volume_min and guard < 1000:
        vol = round(vol - step, 8)
        est_loss = loss_at_volume(vol)
        guard += 1
    if est_loss is None:
        return None
    at_min = vol <= volume_min

    return LotPlan(volume=round(vol, 8), estimated_loss=round(est_loss, 2),
                   target_risk_amount=round(target_risk_amount, 2),
                   at_min=at_min, warnings=warnings)
