"""
services/gold_bot_signal_presets.py
-----------------------------------
Exit presets for the forward signal logger (LM87A).

A preset is an EXIT POLICY the trader chooses — it never touches the bot's
entry logic or stop-loss. The trader owns their own risk by picking how far to
let a winner run, while the bot's SL (= 1R) is held constant. Presets are
expressed in R multiples of that SL so they auto-scale to any risk_mode:
``balanced`` SL/TP is (300, 600) points → 1R = 300; ``scalp`` is (120, 180) →
1R = 120. The same preset means the same risk appetite on either.

OFFLINE / RESEARCH ONLY. This module is pure config + arithmetic: no MT5, no
orders, no network, no I/O. Mirrors the RISK_MODES preset precedent in
services/gold_bot_lot_calculator.py.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExitPreset:
    """A trader-selectable exit policy.

    Two families:

    * FIXED BRACKET (``hold_bars`` None) — exit at a take-profit in R multiples
      of the signal's SL. ``tp1_r`` None -> single target at ``tp_r``; ``tp1_r``
      float -> close ``partial_ratio`` at ``tp1_r``, the rest runs to ``tp_r``.
    * TIME / SWING (``hold_bars`` set) — hold for ``hold_bars`` bars then exit at
      market (this is the VALIDATED M15-swing edge: the move needs time, a tight
      bracket gets shaken out). ``sl_r`` None means no protective stop (pure
      hold); a float keeps an SL floor at that R multiple.

    ``sl_r`` scales the stop in R; ``tp_r``/``tp1_r`` are ignored when
    ``hold_bars`` is set.
    """
    name: str
    label: str
    description: str
    tp_r: float                  # final target, in R (multiples of SL distance)
    tp1_r: float | None = None   # partial target in R, or None for a single TP
    partial_ratio: float = 0.5   # fraction closed at tp1 (0..1); used only if tp1_r set
    hold_bars: int | None = None # time-exit: hold N bars then exit at market
    sl_r: float | None = 1.0     # stop in R; None = no protective stop (pure hold)


# Ordered low-risk -> high-risk. Keep names stable: the dashboard + track record
# reference them as keys.
PRESETS: dict[str, ExitPreset] = {
    "conservative": ExitPreset(
        name="conservative", label="Conservative",
        description="Bank 50% at 1R, let the rest run to 2R. Smoothest equity, "
                    "lowest give-back; caps the upside.",
        tp_r=2.0, tp1_r=1.0, partial_ratio=0.5),
    "balanced": ExitPreset(
        name="balanced", label="Balanced",
        description="Single fixed target at 2R. The bot's default reward:risk.",
        tp_r=2.0, tp1_r=None),
    "runner": ExitPreset(
        name="runner", label="Runner",
        description="Single fixed target at 3R. Fewer wins, bigger winners; "
                    "more give-back when price reverses before 3R.",
        tp_r=3.0, tp1_r=None),
    "swing": ExitPreset(
        name="swing", label="Swing (time exit)",
        description="Hold ~30 bars then exit at market, no fixed target. The "
                    "validated M15-swing edge: the move needs room, a tight "
                    "bracket gets shaken out. No protective stop (pure hold).",
        tp_r=0.0, tp1_r=None, hold_bars=30, sl_r=None),
    "swing_guarded": ExitPreset(
        name="swing_guarded", label="Swing (guarded)",
        description="Same time exit, but with a WIDE 3R safety stop to cap the "
                    "tail risk of an unguarded hold. Trades a little edge for "
                    "bounded downside — the retail-safe swing.",
        tp_r=0.0, tp1_r=None, hold_bars=30, sl_r=3.0),
}

DEFAULT_PRESET = "swing"


def get_preset(name: str) -> ExitPreset:
    """Return the preset by name. Raises KeyError with the valid set on miss."""
    try:
        return PRESETS[name]
    except KeyError:
        valid = ", ".join(PRESETS)
        raise KeyError(f"unknown preset {name!r}; valid presets: {valid}") from None


def resolve_preset_points(preset: ExitPreset, sl_points: int) -> tuple[int | None, int]:
    """Scale a preset to concrete (tp1_points, tp_points) given the signal's SL.

    ``sl_points`` is 1R. Returns integer point distances. ``tp1_points`` is None
    when the preset uses a single fixed target. SL itself is unchanged — the
    trader varies only the target, never the stop.
    """
    if sl_points is None or sl_points <= 0:
        raise ValueError(f"sl_points must be a positive int (got {sl_points!r})")
    tp_points = int(round(sl_points * preset.tp_r))
    tp1_points = int(round(sl_points * preset.tp1_r)) if preset.tp1_r is not None else None
    return tp1_points, tp_points
