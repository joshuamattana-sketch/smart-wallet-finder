"""
services/gold_bot_demo_safety_supervisor.py
---------------------------------------------
LM87A - Runtime DEMO safety supervisor for the Gold Bot worker.

Runs before/around every worker iteration and enforces HARD demo safety limits
so autonomous MT5 *demo* execution can never run away:

    1.  learning-modifier contract  (demo_only / not expired / no forbidden keys / clamp)
    2.  open-position guard          (max_open_positions, default 1)
    3.  no-stacking guard            (one symbol at a time unless explicitly allowed)
    4.  trade-frequency guard        (max/hour + min seconds between trades)
    5.  loss-streak guard            (consecutive losses -> cooldown)
    6.  daily-drawdown guard         (warning + hard block, on top of the risk gate)
    7.  spread guard                 (per risk-mode ceiling)
    8.  MT5 health guard             (demo + symbol selected + fresh tick + free margin)
    9.  macro-lockout respect        (never overrides a macro lockout)
    10. kill-switch respect          (kill switch blocks everything)

This is a SECOND layer on top of (never a replacement for) the LM75 risk gate,
the macro lockout and the kill switch. It can only ever BLOCK or downgrade; it
can never enable live trading, send orders, change volume/lot, or bypass any
existing control. There is deliberately NO off switch.

Pure + offline: no MT5 import, no HTTP, no secrets. The supervisor is fed
plain values (equity, pnl, spread, open positions, tick freshness) so it is fully
unit-testable with fakes. State lives in a small JSON file; events append to a
JSONL log. Both are best-effort and never break the loop.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from services.gold_bot_learning_modifiers import (
    FORBIDDEN_MODIFIER_KEYS,
    HARD_MAX_MODIFIER,
    HARD_MIN_MODIFIER,
    contract_violations,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SAFETY_DIR = _REPO_ROOT / "data" / "gold_bot" / "safety"
DEFAULT_STATE_PATH = DEFAULT_SAFETY_DIR / "safety_state.json"
DEFAULT_EVENTS_PATH = DEFAULT_SAFETY_DIR / "safety_events.jsonl"

# Severities + actions (kept as constants so callers/tests don't guess strings).
INFO, WARNING, BLOCK, CRITICAL = "info", "warning", "block", "critical"
CONTINUE_OBSERVE = "continue_observe"
BLOCK_EXECUTION = "block_execution"
DISABLE_LEARNING = "disable_learning"
PAUSE_DEMO = "pause_demo"
REQUIRE_MANUAL_RESTART = "require_manual_restart"

# Per-risk-mode spread ceilings (points) when no explicit override is given.
SPREAD_CEILING_BY_MODE = {"scalp": 25.0}
SPREAD_CEILING_DEFAULT = 35.0
TICK_STALE_SECONDS = 120
RECENT_TRADES_CAP = 50


# ── config ───────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class SupervisorConfig:
    """Hard demo limits. All default safe; there is no 'disable supervisor' flag."""
    max_open_positions: int = 1
    allow_stacking: bool = False
    max_trades_per_hour: int = 6
    min_seconds_between_trades: int = 120
    max_consecutive_losses: int = 3
    cooldown_minutes_after_loss_streak: int = 30
    max_daily_loss_pct: float = 7.0
    warning_daily_loss_pct: float = 4.0
    max_spread_points: float | None = None   # None -> resolve from risk mode

    def spread_ceiling(self, risk_mode: str) -> float:
        if self.max_spread_points is not None:
            return float(self.max_spread_points)
        return SPREAD_CEILING_BY_MODE.get((risk_mode or "").lower(), SPREAD_CEILING_DEFAULT)


# ── decision object ───────────────────────────────────────────────────────────────
@dataclass
class SafetyDecision:
    allowed: bool
    severity: str                       # info | warning | block | critical
    reason: str
    details: dict = field(default_factory=dict)
    cooldown_until: str | None = None
    actions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"allowed": self.allowed, "severity": self.severity, "reason": self.reason,
                "details": self.details, "cooldown_until": self.cooldown_until,
                "actions": list(self.actions)}


# ── execution context (everything the runtime guards need) ────────────────────────
@dataclass
class SafetyExecContext:
    now: datetime
    risk_mode: str = "balanced"
    account_is_demo: bool = True
    symbol_selected: bool = True
    open_positions: int = 0
    spread_points: float | None = None
    equity: float | None = None
    free_margin: float | None = None
    daily_realized_pnl: float | None = None
    tick_fresh: bool = True
    kill_switch: bool = False
    macro_lockout: bool = False
    decision: str = "NO_TRADE"


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


# ── the supervisor ────────────────────────────────────────────────────────────────
class DemoSafetySupervisor:
    """Enforces demo safety limits. No MT5, no orders. Cannot be disabled."""

    def __init__(self, config: SupervisorConfig | None = None, *,
                 state_path: Path | str = DEFAULT_STATE_PATH,
                 events_path: Path | str = DEFAULT_EVENTS_PATH) -> None:
        self.config = config or SupervisorConfig()
        self.state_path = Path(state_path)
        self.events_path = Path(events_path)

    # ── state IO (best-effort) ────────────────────────────────────────────────
    def load_state(self) -> dict[str, Any]:
        default = {"recent_trades": [], "consecutive_losses": 0,
                   "cooldown_until": None, "last_trade_at": None, "updated_at": None}
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return default
        if not isinstance(data, dict):
            return default
        return {**default, **data}

    def save_state(self, state: dict[str, Any], *, now: datetime | None = None) -> None:
        state["updated_at"] = (now or datetime.now(timezone.utc)).isoformat()
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            self.state_path.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")
        except OSError:
            pass  # state is best-effort; never break the loop

    def record_event(self, decision: SafetyDecision, *, now: datetime | None = None,
                     context: str = "") -> None:
        line = {"recorded_at": (now or datetime.now(timezone.utc)).isoformat(),
                "context": context, **decision.to_dict()}
        try:
            self.events_path.parent.mkdir(parents=True, exist_ok=True)
            with self.events_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(line, default=str) + "\n")
        except OSError:
            pass

    # ── 1. learning-modifier contract ─────────────────────────────────────────
    def evaluate_learning(self, path: str | Path | None, *, enabled: bool,
                          now: datetime | None = None) -> SafetyDecision:
        """
        Validate active_demo_modifiers.json against the demo contract. Returns a
        decision where `allowed` means 'learning modifiers may be used'. Invalid
        / expired / missing -> allowed False (worker disables learning, keeps
        running). Files are never deleted here - in-memory deactivation is enough.
        """
        now = now or datetime.now(timezone.utc)
        if not enabled:
            return SafetyDecision(True, INFO, "learning modifiers not requested",
                                  details={"enabled": False}, actions=[CONTINUE_OBSERVE])
        p = Path(path) if path else None
        if p is None or not p.exists():
            return SafetyDecision(False, WARNING,
                                  f"learning modifier file missing: {p} - learning disabled",
                                  details={"path": str(p)},
                                  actions=[DISABLE_LEARNING, CONTINUE_OBSERVE])
        try:
            payload = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            return SafetyDecision(False, WARNING,
                                  f"learning modifier file unreadable ({exc}) - learning disabled",
                                  details={"path": str(p)},
                                  actions=[DISABLE_LEARNING, CONTINUE_OBSERVE])
        violations = contract_violations(payload, now=now)
        if violations:
            return SafetyDecision(False, WARNING,
                                  "learning modifier contract failed - learning disabled",
                                  details={"path": str(p), "violations": violations,
                                           "forbidden_keys": list(FORBIDDEN_MODIFIER_KEYS),
                                           "clamp": [HARD_MIN_MODIFIER, HARD_MAX_MODIFIER]},
                                  actions=[DISABLE_LEARNING, CONTINUE_OBSERVE])
        return SafetyDecision(True, INFO, "demo learning contract OK (demo-only, confidence-only)",
                              details={"path": str(p), "active_count": len(payload.get("modifiers") or {})},
                              actions=[CONTINUE_OBSERVE])

    # ── 2-10. runtime execution guards ─────────────────────────────────────────
    def evaluate_execution(self, ctx: SafetyExecContext) -> SafetyDecision:
        """
        Run every runtime guard for a would-be demo order. Returns a SafetyDecision;
        `allowed` is True only when NO guard blocks. May persist a loss-streak
        cooldown to the state file (and append one event when a cooldown starts).
        Read-mostly otherwise. Never sends orders, never touches MT5.
        """
        cfg = self.config
        now = ctx.now
        state = self.load_state()
        failures: list[dict] = []     # block/critical
        warnings: list[dict] = []     # non-blocking

        def block(reason, *, severity=BLOCK, actions=None, **detail):
            failures.append({"reason": reason, "severity": severity,
                             "actions": actions or [BLOCK_EXECUTION], "detail": detail})

        def warn(reason, **detail):
            warnings.append({"reason": reason, "severity": WARNING, "detail": detail})

        # 10. kill switch (hardest)
        if ctx.kill_switch:
            block("kill_switch", severity=CRITICAL, actions=[BLOCK_EXECUTION, PAUSE_DEMO])
        # 9. macro lockout (never overridden)
        if ctx.macro_lockout:
            block("macro_lockout")
        # 8. MT5 health
        if not ctx.account_is_demo:
            block("mt5_health_guard", severity=CRITICAL,
                  actions=[BLOCK_EXECUTION, REQUIRE_MANUAL_RESTART], issue="account_not_demo")
        if not ctx.symbol_selected:
            block("mt5_health_guard", issue="symbol_not_selected")
        if not ctx.tick_fresh:
            block("mt5_health_guard", issue="stale_tick")
        if ctx.free_margin is not None and ctx.free_margin <= 0:
            block("mt5_health_guard", issue="no_free_margin", free_margin=ctx.free_margin)
        elif ctx.free_margin is None:
            warn("free margin unavailable - cannot fully verify MT5 health")

        # 6. daily drawdown (warning + hard block; risk gate still applies separately)
        loss_pct = None
        if ctx.equity and ctx.equity > 0 and ctx.daily_realized_pnl is not None:
            loss_pct = round(max(0.0, -ctx.daily_realized_pnl) / ctx.equity * 100.0, 2)
            if loss_pct >= cfg.max_daily_loss_pct:
                block("daily_drawdown_guard", actions=[BLOCK_EXECUTION, PAUSE_DEMO],
                      loss_pct=loss_pct, max_pct=cfg.max_daily_loss_pct)
            elif loss_pct >= cfg.warning_daily_loss_pct:
                warn("daily drawdown warning", loss_pct=loss_pct, warning_pct=cfg.warning_daily_loss_pct)
        else:
            warn("equity/pnl unavailable - daily drawdown not computed")

        # 5. loss-streak cooldown (may persist state)
        cool_until = _parse_iso(state.get("cooldown_until"))
        state_changed = False
        if cool_until and now >= cool_until:        # cooldown expired -> reset
            state["cooldown_until"], state["consecutive_losses"] = None, 0
            cool_until, state_changed = None, True
        cooldown_started = False
        if cool_until and now < cool_until:
            block("loss_streak_cooldown", actions=[BLOCK_EXECUTION, PAUSE_DEMO],
                  cooldown_until=state["cooldown_until"],
                  consecutive_losses=state.get("consecutive_losses"))
        elif state.get("consecutive_losses", 0) >= cfg.max_consecutive_losses:
            new_cool = (now + timedelta(minutes=cfg.cooldown_minutes_after_loss_streak)).isoformat()
            state["cooldown_until"] = new_cool
            state_changed = cooldown_started = True
            cool_until = _parse_iso(new_cool)
            block("loss_streak_cooldown", actions=[BLOCK_EXECUTION, PAUSE_DEMO],
                  cooldown_until=new_cool, consecutive_losses=state.get("consecutive_losses"))

        # 2. open positions
        if ctx.open_positions >= cfg.max_open_positions:
            block("max_open_positions_reached", open_positions=ctx.open_positions,
                  max_open_positions=cfg.max_open_positions)
        # 3. no stacking
        if ctx.open_positions > 0 and not cfg.allow_stacking:
            block("no_stacking", open_positions=ctx.open_positions)
        # 7. spread
        ceiling = cfg.spread_ceiling(ctx.risk_mode)
        if ctx.spread_points is not None and ctx.spread_points > ceiling:
            block("spread_guard", spread_points=ctx.spread_points, max_spread_points=ceiling)
        # 4. trade frequency
        recent = [t for t in state.get("recent_trades", [])
                  if _parse_iso(t) and (now - _parse_iso(t)).total_seconds() <= 3600]
        if len(recent) >= cfg.max_trades_per_hour:
            block("trade_frequency_guard", issue="max_per_hour",
                  trades_last_hour=len(recent), max_trades_per_hour=cfg.max_trades_per_hour)
        last = _parse_iso(state.get("last_trade_at"))
        if last is not None:
            gap = (now - last).total_seconds()
            if gap < cfg.min_seconds_between_trades:
                block("trade_frequency_guard", issue="min_gap", seconds_since_last=round(gap, 1),
                      min_seconds_between_trades=cfg.min_seconds_between_trades)

        if state_changed:
            self.save_state(state, now=now)

        # assemble
        all_failures = failures + warnings
        details = {"checks": all_failures, "loss_pct": loss_pct,
                   "spread_ceiling": ceiling, "open_positions": ctx.open_positions}
        if failures:
            first = failures[0]
            cooldown = first.get("detail", {}).get("cooldown_until")
            dec = SafetyDecision(False, first["severity"], first["reason"], details=details,
                                 cooldown_until=cooldown,
                                 actions=sorted(set(first["actions"] + [CONTINUE_OBSERVE])))
        elif warnings:
            dec = SafetyDecision(True, WARNING, warnings[0]["reason"], details=details,
                                 actions=[CONTINUE_OBSERVE])
        else:
            dec = SafetyDecision(True, INFO, "all_clear", details=details, actions=[CONTINUE_OBSERVE])

        if cooldown_started:
            self.record_event(dec, now=now, context="loss_streak_cooldown_started")
        return dec

    # ── state mutators (frequency / loss outcomes) ─────────────────────────────
    def register_trade_sent(self, *, now: datetime | None = None) -> None:
        """Record an actually-sent demo order so the frequency guard can see it."""
        now = now or datetime.now(timezone.utc)
        state = self.load_state()
        recent = list(state.get("recent_trades", []))
        recent.append(now.isoformat())
        state["recent_trades"] = recent[-RECENT_TRADES_CAP:]
        state["last_trade_at"] = now.isoformat()
        self.save_state(state, now=now)

    @staticmethod
    def _result_label(outcome: Any, won: bool | None) -> str:
        """Map a TradeOutcome / str / legacy `won` bool to win|loss|breakeven|skip."""
        if won is not None:
            return "win" if won else "loss"
        if outcome is None:
            return "skip"
        s = (outcome if isinstance(outcome, str) else getattr(outcome, "outcome", "")).lower()
        return s if s in ("win", "loss", "breakeven") else "skip"

    def record_trade_result(self, outcome: Any = None, *, won: bool | None = None,
                            now: datetime | None = None) -> dict:
        """
        LM89A: update the consecutive-loss counter from a REAL trade outcome (a
        TradeOutcome, an outcome string, or the legacy `won` bool). A loss that
        reaches max_consecutive_losses arms the cooldown + writes a safety event;
        a win resets the streak; a breakeven reduces it by one. open/unknown ->
        no change. Persists to safety_state.json. Returns the updated state.
        """
        now = now or datetime.now(timezone.utc)
        label = self._result_label(outcome, won)
        state = self.load_state()
        n = int(state.get("consecutive_losses", 0))
        if label == "loss":
            n += 1
        elif label == "win":
            n = 0
        elif label == "breakeven":
            n = max(0, n - 1)
        else:
            return state                       # open / unknown -> no change
        state["consecutive_losses"] = n

        cooldown_started = False
        if label == "loss" and n >= self.config.max_consecutive_losses:
            until = (now + timedelta(minutes=self.config.cooldown_minutes_after_loss_streak)).isoformat()
            state["cooldown_until"] = until
            cooldown_started = True
        self.save_state(state, now=now)
        if cooldown_started:
            self.record_event(
                SafetyDecision(False, BLOCK, "loss_streak_cooldown",
                               details={"consecutive_losses": n, "source": "trade_outcome"},
                               cooldown_until=state["cooldown_until"],
                               actions=[BLOCK_EXECUTION, PAUSE_DEMO]),
                now=now, context="loss_streak_from_outcomes")
        return state
