"""
services/gold_bot_risk_gate.py
-------------------------------
LM75B — Pure risk gate for the guarded MT5 demo trade loop.

No MT5, no I/O, no network — just deterministic rules over a request + config +
today's trade count. The gate has FINAL AUTHORITY: the trade loop must not send
an order unless `evaluate_demo_order(...).approved` is True. Defaults are the
safe position; env parsing always falls back safe.

Hard rules enforced here (mirrors the LM74 blueprint Risk Engine):
    * account must be a verified demo account
    * LIVE_TRADING_ENABLED / ALLOW_REAL_ORDERS must be False
    * kill switch must be off
    * side must be buy/sell
    * volume must be positive and <= max allowed
    * SL and TP must both be present and positive
    * trades today must be under the daily cap

Designed-but-not-yet-computed checks (daily loss %) surface as TODO warnings
and keep conservative behavior — they never silently pass.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

# Conservative ceiling on demo volume unless an explicit (still small) override.
DEFAULT_MAX_VOLUME = 0.05


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw.strip())
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return float(raw.strip())
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class SafetyConfig:
    """
    Safety posture. `from_env()` reads env vars but always defaults safe.

    `max_trades_per_day` is None by default = HIGH-ACTIVITY mode (no fixed
    daily trade cap). The bot may take many trades as long as each passes the
    real risk controls (daily-loss budget, margin, SL/TP, demo-only). A cap is
    enforced only when explicitly set via env or --max-trades-per-day.
    """

    mt5_demo_only: bool = True
    live_trading_enabled: bool = False
    allow_real_orders: bool = False
    kill_switch: bool = False
    max_trades_per_day: int | None = None
    max_daily_loss_pct: float = 7.0
    max_volume: float = DEFAULT_MAX_VOLUME

    @classmethod
    def from_env(cls) -> "SafetyConfig":
        # max_trades_per_day: only set if the env var is explicitly present;
        # otherwise the cap stays disabled (high-activity).
        raw_cap = os.environ.get("GOLD_BOT_MAX_TRADES_PER_DAY")
        cap = _env_int("GOLD_BOT_MAX_TRADES_PER_DAY", 0) if raw_cap is not None else None
        return cls(
            mt5_demo_only=_env_bool("MT5_DEMO_ONLY", True),
            live_trading_enabled=_env_bool("LIVE_TRADING_ENABLED", False),
            allow_real_orders=_env_bool("ALLOW_REAL_ORDERS", False),
            kill_switch=_env_bool("GOLD_BOT_KILL_SWITCH", False),
            max_trades_per_day=cap,
            max_daily_loss_pct=_env_float("GOLD_BOT_MAX_DAILY_LOSS_PCT", 7.0),
            max_volume=_env_float("GOLD_BOT_MAX_VOLUME", DEFAULT_MAX_VOLUME),
        )


# Conservative cap on margin used by a single trade (percent of free margin).
MAX_MARGIN_PCT_PER_TRADE = 10.0


@dataclass
class RiskDecision:
    approved: bool
    reasons: list[str] = field(default_factory=list)   # why blocked
    warnings: list[str] = field(default_factory=list)   # non-blocking notes
    info: dict = field(default_factory=dict)            # computed risk numbers

    def to_dict(self) -> dict:
        return {"approved": self.approved, "reasons": self.reasons,
                "warnings": self.warnings, "info": self.info}


def evaluate_demo_order(
    *,
    config: SafetyConfig,
    account_is_demo: bool,
    side: str,
    volume: float,
    sl_present: bool,
    tp_present: bool,
    trades_today: int,
) -> RiskDecision:
    """
    Evaluate a proposed demo order. Returns a RiskDecision; approved is True
    only when EVERY hard rule passes. Fail closed: any unmet/uncertain rule
    blocks.
    """
    reasons, warnings = _core_safety(
        config=config, account_is_demo=account_is_demo, side=side,
        sl_present=sl_present, tp_present=tp_present, trades_today=trades_today,
    )

    # Volume (LM75B hard cap — applies to MANUAL fixed-lot orders only).
    if not (isinstance(volume, (int, float)) and volume > 0):
        reasons.append("volume must be positive.")
    elif volume > config.max_volume:
        reasons.append(f"volume {volume} exceeds max allowed {config.max_volume}.")

    # Designed-but-not-computed here: daily loss % (LM75D's evaluate_risk_plan
    # does compute it). Keep a TODO note for callers of this base path.
    warnings.append(
        "TODO: realized daily-loss % not computed in evaluate_demo_order - "
        f"hard stop is -{config.max_daily_loss_pct:.0f}% (use evaluate_risk_plan for the budget)."
    )

    return RiskDecision(approved=len(reasons) == 0, reasons=reasons, warnings=warnings)


def _core_safety(
    *,
    config: SafetyConfig,
    account_is_demo: bool,
    side: str,
    sl_present: bool,
    tp_present: bool,
    trades_today: int,
) -> tuple[list[str], list[str]]:
    """Shared hard rules (no volume cap, no daily-loss math). Returns (reasons, warnings)."""
    reasons: list[str] = []
    warnings: list[str] = []

    if not config.mt5_demo_only:
        reasons.append("MT5_DEMO_ONLY is disabled — refusing (this tool is demo-only).")
    if config.live_trading_enabled:
        reasons.append("LIVE_TRADING_ENABLED is true — refusing (no live trading).")
    if config.allow_real_orders:
        reasons.append("ALLOW_REAL_ORDERS is true — refusing (real orders never allowed here).")
    if config.kill_switch:
        reasons.append("GOLD_BOT_KILL_SWITCH is active — all orders blocked.")
    if not account_is_demo:
        reasons.append("Account is not a verified demo account — refusing.")
    if side.lower() not in ("buy", "sell"):
        reasons.append(f"side must be buy/sell, got '{side}'.")
    if not sl_present:
        reasons.append("stop loss is required.")
    if not tp_present:
        reasons.append("take profit is required.")
    # Trade-count cap only when one is explicitly configured (high-activity by
    # default — no fixed daily cap).
    if config.max_trades_per_day is not None and trades_today >= config.max_trades_per_day:
        reasons.append(f"daily trade cap reached ({trades_today}/{config.max_trades_per_day}).")
    return reasons, warnings


def evaluate_risk_plan(
    *,
    config: SafetyConfig,
    account_is_demo: bool,
    side: str,
    volume: float | None,
    sl_present: bool,
    tp_present: bool,
    est_sl_loss: float | None,
    require_risk_calc: bool,
    margin_required: float | None,
    free_margin: float | None,
    equity: float | None,
    daily_realized_pnl: float | None,
    trades_today: int,
    risk_pct: float,
    max_margin_pct: float = MAX_MARGIN_PCT_PER_TRADE,
) -> RiskDecision:
    """
    Full risk authority for a sized order: base safety + SL-loss vs daily-loss
    budget + margin usage + trade-count cap. Computes the daily budget and
    margin allowance and returns them in `info` for display/journaling. Fail
    closed: missing risk numbers block when a calculation was required.
    """
    # Base hard rules WITHOUT the fixed-lot volume cap — here position size is
    # governed by risk%, the daily-loss budget and the margin allowance below.
    reasons, warnings = _core_safety(
        config=config, account_is_demo=account_is_demo, side=side,
        sl_present=sl_present, tp_present=tp_present, trades_today=trades_today,
    )
    if not (isinstance(volume, (int, float)) and volume and volume > 0):
        reasons.append("volume must be positive.")
    info: dict = {"risk_pct": risk_pct}

    # Daily-loss budget (equity-based). Fail closed: a NON-POSITIVE equity is a
    # blown/zero account and must BLOCK — it must never slip through as a soft
    # "unavailable" warning (a `if equity and equity > 0` truthiness check let
    # equity == 0.0 bypass the entire budget). A genuinely missing equity (None)
    # blocks on the sizing path and only warns on the manual path.
    if equity is None:
        if require_risk_calc:
            reasons.append("equity unavailable — cannot verify daily-loss budget (fail closed).")
        else:
            warnings.append("equity unavailable — daily-loss budget not computed.")
    elif equity <= 0:
        reasons.append(f"equity is {equity:.2f} — account blown or zero; blocking.")
    elif daily_realized_pnl is None:
        # Equity is known but today's realized PnL could not be read, so the
        # budget is unverifiable. Block on the sizing path; warn on manual.
        info["equity"] = round(equity, 2)
        if require_risk_calc:
            reasons.append("daily realized PnL unavailable — cannot verify daily-loss budget (fail closed).")
        else:
            warnings.append("daily realized PnL unavailable — daily-loss budget not verified.")
    else:
        max_daily_loss_amount = equity * config.max_daily_loss_pct / 100.0
        today_loss = max(0.0, -daily_realized_pnl)
        remaining = round(max_daily_loss_amount - today_loss, 2)
        info.update({
            "equity": round(equity, 2),
            "daily_realized_pnl": round(daily_realized_pnl, 2),
            "max_daily_loss_amount": round(max_daily_loss_amount, 2),
            "remaining_daily_budget": remaining,
        })
        if remaining <= 0:
            reasons.append(f"daily loss hard stop reached (remaining budget {remaining}).")
        if est_sl_loss is not None and est_sl_loss > remaining:
            reasons.append(
                f"estimated SL loss {est_sl_loss:.2f} exceeds remaining daily budget {remaining:.2f}."
            )

    # SL-loss calculation requirement.
    info["estimated_sl_loss"] = est_sl_loss
    if est_sl_loss is None:
        if require_risk_calc:
            reasons.append("estimated SL loss could not be computed (fail closed for risk sizing).")
        else:
            warnings.append("estimated SL loss unavailable (order_calc_profit) — proceeding on manual volume.")

    # Margin usage. Fail closed: when margin IS required but free margin is
    # missing or non-positive we cannot prove the trade is affordable — block.
    # (A `free_margin and free_margin > 0` truthiness check let free_margin == 0
    # — a fully used-up account — silently skip the margin check.)
    info["margin_required"] = margin_required
    info["free_margin"] = free_margin
    if margin_required is None:
        warnings.append("margin not computed (order_calc_margin unavailable) — cannot verify margin safety.")
    elif free_margin is None:
        reasons.append("free margin unavailable — cannot verify margin safety (fail closed).")
    elif free_margin <= 0:
        reasons.append(f"free margin is {free_margin:.2f} — no margin available; blocking.")
    else:
        allowed = free_margin * max_margin_pct / 100.0
        info["margin_allowed"] = round(allowed, 2)
        if margin_required > allowed:
            reasons.append(
                f"margin {margin_required:.2f} exceeds {max_margin_pct:.0f}% of free margin "
                f"({allowed:.2f})."
            )

    return RiskDecision(approved=len(reasons) == 0, reasons=reasons, warnings=warnings, info=info)


def evaluate_demo_close(
    *,
    config: SafetyConfig,
    account_is_demo: bool,
    ticket_found: bool,
    volume: float | None,
    emergency: bool = False,
) -> RiskDecision:
    """
    Evaluate a proposed position close. Closing is risk-REDUCING, so the
    open-side rules (volume cap, daily trade cap) do not apply. The kill switch
    still blocks unless an explicit demo-only `emergency` override is passed.
    Fail closed: any unmet rule blocks.
    """
    reasons: list[str] = []
    warnings: list[str] = []

    if not config.mt5_demo_only:
        reasons.append("MT5_DEMO_ONLY is disabled — refusing (this tool is demo-only).")
    if config.live_trading_enabled:
        reasons.append("LIVE_TRADING_ENABLED is true — refusing (no live trading).")
    if config.allow_real_orders:
        reasons.append("ALLOW_REAL_ORDERS is true — refusing (real orders never allowed here).")
    if config.kill_switch and not emergency:
        reasons.append("GOLD_BOT_KILL_SWITCH is active — close blocked (use --emergency-close to override, demo only).")
    if config.kill_switch and emergency:
        warnings.append("Kill switch active but EMERGENCY CLOSE override used (demo only).")

    if not account_is_demo:
        reasons.append("Account is not a verified demo account — refusing.")
    if not ticket_found:
        reasons.append("Position ticket not found on this account.")
    if not (isinstance(volume, (int, float)) and volume and volume > 0):
        reasons.append("Position volume must be positive.")

    return RiskDecision(approved=len(reasons) == 0, reasons=reasons, warnings=warnings)
