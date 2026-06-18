"""
services/gold_bot_basket_scalper.py
------------------------------------
LM100A — Basket scalp orchestration logic (PURE, demo-only, opt-in).

Decides, from the current open positions + aggregate P&L + a fresh engine
signal, whether to OPEN a basket of N same-direction scalp positions, HOLD, or
CLOSE ALL. Close-all fires on the FIRST of: aggregate profit target, a HARD
aggregate loss cap (the non-negotiable brake that stops bag-holding losers), or a
time stop. No MT5, no I/O, no orders here — the worker performs the guarded demo
sends. This layer never enables live trading, never bypasses the risk gate, the
macro lockout, the kill switch, or the demo-account check.

The hard loss cap is what separates this from a blow-up martingale: a basket can
never sit underwater past -hard_loss_cap_pct of equity before being force-closed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

# close-all reasons
CLOSE_PROFIT_TARGET = "profit_target"
CLOSE_HARD_LOSS = "hard_loss_cap"
CLOSE_TIME_STOP = "time_stop"
CLOSE_PROFIT_LOCK = "profit_lock"        # trailing floor after a profit peak
CLOSE_PRESSURE_FLIP = "pressure_flip"    # in profit + price-action pressure turned against us
CLOSE_ENGINE_REVERSAL = "engine_reversal"  # the decision engine flipped to a strong opposite signal

# Price-action pressure weighting: how much the last candle's wick imbalance adds
# to recent momentum (in points). NOT real order-flow — a candle-based proxy.
PRESSURE_WICK_POINTS = 50.0

# action kinds
OPEN = "open"
ADD = "add"            # scale-in: add more same-direction legs to an open basket
HOLD = "hold"
CLOSE_ALL = "close_all"
NONE = "none"


@dataclass
class BasketConfig:
    num_positions: int = 5                 # base leg count (at the entry confidence floor)
    max_positions: int = 0                 # 0 = no scaling; else scale up to this with confidence
    scale_in: bool = False                 # nachkaufen: top up toward the scaled target while open
    basket_risk_cap_pct: float = 3.0       # max TOTAL risk across the basket (% equity)
    profit_target_pct: float = 0.6         # close-all at +this % equity (aggregate)
    hard_loss_cap_pct: float = 1.5         # force close-all at -this % equity (the brake)
    time_stop_seconds: float = 60.0
    allow_flip: bool = True
    cooldown_seconds_after_loss: float = 60.0
    # Trailing profit lock: once aggregate profit peaks at >= lock_arm_pct% equity,
    # close-all if it retraces below lock_floor_frac of that PEAK. lock_floor_frac
    # 0.0 = protect break-even (don't let a winner go red); 0.1 = lock 10% of peak.
    # lock_arm_pct 0 disables the lock.
    lock_arm_pct: float = 0.4
    lock_floor_frac: float = 0.0
    # Price-action pressure close: while in profit (>= pressure_min_profit_pct% equity),
    # close-all if pressure turns against the basket by >= pressure_threshold_points
    # for pressure_confirm_bars CONSECUTIVE reads (debounce — never on a single tick).
    pressure_close: bool = True
    pressure_min_profit_pct: float = 0.1
    pressure_threshold_points: float = 300.0   # gold point-pressure runs ~200-300; 100 was too twitchy
    pressure_confirm_bars: int = 3
    # Engine reversal exit: if the decision engine emits a STRONG opposite signal
    # while the basket is open, close-all (cut/bank on a real structure flip).
    reversal_close: bool = True
    reversal_confidence: float = 70.0


@dataclass
class BasketAction:
    kind: str                              # open | hold | close_all | none
    reason: str
    direction: str | None = None           # for open
    num_positions: int = 0
    aggregate_profit: float | None = None


def aggregate_profit(positions: list[dict]) -> float:
    """Sum the floating P&L across open positions (position_view dicts)."""
    return round(sum(float(p.get("profit") or 0.0) for p in positions), 2)


def scaled_position_count(confidence: float, *, min_confidence: float, base_positions: int,
                          max_positions: int, full_confidence: float = 100.0) -> int:
    """
    Target leg count scaled by confidence: base_positions at (or below) the entry
    floor, max_positions at (or above) full_confidence, linear between. max 0/<=base
    disables scaling (returns base). Pure.
    """
    base = max(1, int(base_positions))
    mx = max(base, int(max_positions or base))
    if mx <= base:
        return base
    try:
        c = float(confidence)
    except (TypeError, ValueError):
        return base
    lo, hi = float(min_confidence), float(full_confidence)
    if hi <= lo or c <= lo:
        return base
    if c >= hi:
        return mx
    return int(round(base + (mx - base) * (c - lo) / (hi - lo)))


def basket_side(positions: list[dict]) -> str:
    """Net direction of the basket from position_view 'side' fields."""
    sides = {p.get("side") for p in positions}
    if sides == {"buy"}:
        return "LONG"
    if sides == {"sell"}:
        return "SHORT"
    return "MIXED"


def pressure_opposes(side: str, pressure: float | None, threshold_points: float) -> bool:
    """True if price-action pressure is against the basket beyond the threshold."""
    if pressure is None:
        return False
    if side == "LONG":
        return pressure <= -threshold_points
    if side == "SHORT":
        return pressure >= threshold_points
    return False


def price_action_pressure(candles: list[dict], point: float, *, bars: int = 3) -> float:
    """
    Candle-based buy/sell pressure proxy (NOT order-flow): recent close momentum
    in points plus the last candle's wick imbalance (lower wick = buyers, upper =
    sellers). Positive = buy pressure, negative = sell pressure. 0.0 when there is
    not enough data.
    """
    if not candles or len(candles) < bars + 1 or not point:
        return 0.0
    closes = [c["close"] for c in candles]
    mom = (closes[-1] - closes[-1 - bars]) / point
    last = candles[-1]
    rng = last["high"] - last["low"]
    if rng > 0:
        lower = (min(last["open"], last["close"]) - last["low"]) / rng
        upper = (last["high"] - max(last["open"], last["close"])) / rng
        wick_bias = lower - upper
    else:
        wick_bias = 0.0
    return round(mom + wick_bias * PRESSURE_WICK_POINTS, 1)


def cap_basket_positions(requested_n: int, per_trade_risk_amount: float, equity: float,
                         cap_pct: float) -> int:
    """
    Largest number of equally-sized legs whose TOTAL risk stays at/under
    cap_pct% of equity. Returns 0 when inputs are unusable or even one leg breaks
    the cap. Pure; the hard ceiling on basket exposure at entry time.
    """
    if requested_n <= 0 or per_trade_risk_amount <= 0 or equity <= 0 or cap_pct <= 0:
        return 0
    cap_amount = equity * cap_pct / 100.0
    max_n = int(cap_amount // per_trade_risk_amount)
    return max(0, min(requested_n, max_n))


def decide_basket_action(*, open_positions: list[dict], equity: float, now: datetime,
                         opened_at: datetime | None, signal_decision: str,
                         signal_confidence: int, min_confidence: int, cfg: BasketConfig,
                         in_cooldown: bool = False, peak_profit: float = 0.0,
                         pressure: float | None = None,
                         pressure_against_streak: int = 0) -> BasketAction:
    """
    Pure basket decision. With positions open it HOLDs, CLOSE_ALLs, or ADDs
    (scale-in). Close priority (each only closes EARLIER, never holds longer):
      1. hard loss cap (the brake)
      2. engine reversal (strong opposite engine signal — real structure flip)
      3. trailing profit lock (gave back a peak profit)
      4. pressure flip (in profit + price-action pressure turned against us)
      5. fixed profit target
      6. time stop
      7. scale-in (top up toward the confidence-scaled target, same direction)
    Flat + a valid engine signal (and not in cooldown) → OPEN. Else → NONE.
    `peak_profit` is the highest aggregate profit seen since the basket opened
    (tracked by the caller); `pressure` is price_action_pressure (None = skip).
    """
    n_open = len(open_positions)
    if n_open > 0:
        agg = aggregate_profit(open_positions)
        eq = equity if equity > 0 else 0.0

        # 1) hard loss cap — the non-negotiable brake, always first.
        if eq and agg <= -eq * cfg.hard_loss_cap_pct / 100.0:
            return BasketAction(CLOSE_ALL, CLOSE_HARD_LOSS, aggregate_profit=agg, num_positions=n_open)

        # 2) engine reversal — a STRONG opposite engine signal flips the thesis;
        #    cut/bank regardless of P&L (uses the real engine, not a candle proxy).
        if cfg.reversal_close and signal_decision in ("LONG", "SHORT") \
                and signal_confidence >= cfg.reversal_confidence:
            side = basket_side(open_positions)
            if (side == "LONG" and signal_decision == "SHORT") \
                    or (side == "SHORT" and signal_decision == "LONG"):
                return BasketAction(CLOSE_ALL, CLOSE_ENGINE_REVERSAL, aggregate_profit=agg,
                                    num_positions=n_open)

        # 3) trailing profit lock — armed once the peak hit lock_arm_pct% equity;
        #    then close if profit retraces below lock_floor_frac of that peak.
        if eq and cfg.lock_arm_pct > 0 and peak_profit >= eq * cfg.lock_arm_pct / 100.0:
            floor = peak_profit * cfg.lock_floor_frac
            if agg <= floor:
                return BasketAction(CLOSE_ALL, CLOSE_PROFIT_LOCK, aggregate_profit=agg,
                                    num_positions=n_open)

        # 4) pressure flip — only while in profit AND pressure has opposed us for
        #    pressure_confirm_bars consecutive reads (debounce; never one tick).
        if (cfg.pressure_close and pressure is not None and eq
                and agg >= eq * cfg.pressure_min_profit_pct / 100.0
                and pressure_against_streak >= cfg.pressure_confirm_bars
                and pressure_opposes(basket_side(open_positions), pressure,
                                     cfg.pressure_threshold_points)):
            return BasketAction(CLOSE_ALL, CLOSE_PRESSURE_FLIP, aggregate_profit=agg,
                                num_positions=n_open)

        # 5) fixed profit target.
        if eq and agg >= eq * cfg.profit_target_pct / 100.0:
            return BasketAction(CLOSE_ALL, CLOSE_PROFIT_TARGET, aggregate_profit=agg,
                                num_positions=n_open)

        # 6) time stop.
        if opened_at is not None and (now - opened_at).total_seconds() >= cfg.time_stop_seconds:
            return BasketAction(CLOSE_ALL, CLOSE_TIME_STOP, aggregate_profit=agg, num_positions=n_open)

        # 7) scale-in (nachkaufen): top up toward the confidence-scaled target, SAME
        #    direction only. The hard loss cap above still force-closes the basket.
        if cfg.scale_in and signal_decision in ("LONG", "SHORT") \
                and signal_confidence >= min_confidence:
            side = basket_side(open_positions)
            if side in ("LONG", "SHORT") and side == signal_decision:
                target = scaled_position_count(signal_confidence, min_confidence=min_confidence,
                                               base_positions=cfg.num_positions,
                                               max_positions=cfg.max_positions)
                if n_open < target:
                    return BasketAction(ADD, f"scale-in to {target} (conf {signal_confidence})",
                                        direction=side, num_positions=target - n_open,
                                        aggregate_profit=agg)

        return BasketAction(HOLD, "within thresholds", aggregate_profit=agg, num_positions=n_open)

    # flat
    if in_cooldown:
        return BasketAction(NONE, "cooldown after loss close")
    if signal_decision in ("LONG", "SHORT") and signal_confidence >= min_confidence:
        target = scaled_position_count(signal_confidence, min_confidence=min_confidence,
                                       base_positions=cfg.num_positions, max_positions=cfg.max_positions)
        return BasketAction(OPEN, f"signal {signal_decision} conf {signal_confidence} -> {target} legs",
                            direction=signal_decision, num_positions=target)
    return BasketAction(NONE, "no entry signal")
