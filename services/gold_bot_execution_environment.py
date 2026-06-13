"""
services/gold_bot_execution_environment.py
--------------------------------------------
LM93A - Execution environment model for the Gold Bot.

Gives the (currently demo-only) execution stack a clear vocabulary instead of
"demo" scattered everywhere, WITHOUT enabling anything unsafe:

    environment : paper | demo | live          (where orders would land)
    mode        : observe | execute            (whether an order may be attempted)

Policy (this patch keeps demo as the only enabled broker environment):
  * observe          -> never sends orders (reads/analyses only).
  * paper            -> simulated, never sends broker orders.
  * demo + execute   -> demo broker orders ALLOWED *by environment policy* only on a
                        verified demo account — and STILL gated by the existing
                        confirmation flags + safety supervisor + risk gate (this
                        layer never replaces them).
  * live             -> HARD-LOCKED. Even with both the env token and the CLI flag,
                        live is not implemented and is refused (LIVE_NOT_IMPLEMENTED).
  * unknown account  -> execution blocked.

This module is pure: no MT5, no orders, no network, no I/O. It only describes and
gates; callers combine its result with their own guards.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, asdict
from typing import Any

ENVIRONMENTS = ("paper", "demo", "live")
MODES = ("observe", "execute")
ACCOUNT_TYPES = ("paper", "demo", "live", "unknown")

# Live double-lock. BOTH must be present before live could even be *considered* -
# and this patch still refuses (LIVE_IMPLEMENTED is False).
LIVE_ENV_VAR = "LUMORA_GOLD_ALLOW_LIVE_TRADING"
LIVE_ENV_TOKEN = "I_UNDERSTAND_LIVE_RISK"
LIVE_IMPLEMENTED = False

# Gate codes
OBSERVE_ONLY = "OBSERVE_ONLY"
PAPER_NO_BROKER = "PAPER_NO_BROKER"
DEMO_ALLOWED = "DEMO_ALLOWED"
LIVE_LOCKED = "LIVE_LOCKED"
LIVE_NOT_IMPLEMENTED = "LIVE_NOT_IMPLEMENTED"
LIVE_ACCOUNT_BLOCKED = "LIVE_ACCOUNT_BLOCKED"
UNKNOWN_ACCOUNT = "UNKNOWN_ACCOUNT"


def normalize_environment(value: Any) -> str:
    v = str(value or "").strip().lower()
    return v if v in ENVIRONMENTS else "demo"


def normalize_mode(value: Any) -> str:
    v = str(value or "").strip().lower()
    if v in ("demo", "execute"):       # legacy --mode demo means "execute"
        return "execute"
    return "observe"


def account_type_from_info(info: Any) -> str:
    """Map a connector account snapshot / probe dict to an account type."""
    if not isinstance(info, dict):
        return "unknown"
    if info.get("demo_verified") is True:
        return "demo"
    label = str(info.get("trade_mode_label") or info.get("account_type") or "").strip().lower()
    if label == "demo":
        return "demo"
    if label in ("real", "live", "contest"):
        return "live"
    if label == "paper":
        return "paper"
    if info.get("demo_verified") is False:
        return "live"          # verified NOT demo -> treat as live (block)
    return "unknown"


@dataclass(frozen=True)
class ExecutionContext:
    environment: str = "demo"          # paper | demo | live
    mode: str = "observe"              # observe | execute
    account_type: str = "unknown"      # paper | demo | live | unknown
    live_enabled: bool = False         # both live gates present (still refused this patch)
    demo_required: bool = True
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ExecutionGateResult:
    allowed: bool                      # may a broker order be ATTEMPTED (env policy only)
    level: str                         # pass | warn | block
    code: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _result(allowed: bool, level: str, code: str, message: str) -> ExecutionGateResult:
    return ExecutionGateResult(allowed=allowed, level=level, code=code, message=message)


def build_execution_context(environment: str = "demo", mode: str = "observe", *,
                            account_info: Any = None, allow_live_flag: bool = False
                            ) -> ExecutionContext:
    env = normalize_environment(environment)
    md = normalize_mode(mode)
    account_type = "paper" if env == "paper" else account_type_from_info(account_info)
    live_token_ok = os.environ.get(LIVE_ENV_VAR) == LIVE_ENV_TOKEN
    live_enabled = bool(env == "live" and allow_live_flag and live_token_ok)
    return ExecutionContext(environment=env, mode=md, account_type=account_type,
                            live_enabled=live_enabled, demo_required=(env == "demo"))


def context_from_legacy_mode(mode: str, *, environment: str = "demo", account_info: Any = None,
                             allow_live_flag: bool = False) -> ExecutionContext:
    """Back-compat: map the old worker/session `--mode observe|demo` onto the model.
    observe -> mode observe (default demo environment); demo -> demo + execute."""
    return build_execution_context(environment, mode, account_info=account_info,
                                   allow_live_flag=allow_live_flag)


def assert_execution_allowed(context: ExecutionContext) -> ExecutionGateResult:
    """
    Whether a broker order may be ATTEMPTED under the environment policy. This is an
    ADDITIONAL gate - the caller's existing confirmation flags, safety supervisor and
    risk gate still apply on top. Never weakens anything.
    """
    if context.environment == "live":
        # Hard-locked regardless of the env token / CLI flag in this patch.
        return _result(False, "block", LIVE_NOT_IMPLEMENTED,
                       "Live environment is hard-locked and not implemented; this run can only "
                       "execute on demo/paper.")
    if context.mode == "observe":
        return _result(False, "pass", OBSERVE_ONLY,
                       "Observe mode: reads/analyses only, never sends broker orders.")
    if context.environment == "paper":
        return _result(False, "pass", PAPER_NO_BROKER,
                       "Paper environment: simulated only, never sends broker orders.")
    # demo + execute
    if context.account_type == "demo":
        return _result(True, "pass", DEMO_ALLOWED,
                       "Demo broker execution permitted by environment policy - still gated by the "
                       "existing confirmation flags, safety supervisor and risk gate.")
    if context.account_type == "live":
        return _result(False, "block", LIVE_ACCOUNT_BLOCKED,
                       "Account is live/real - execution blocked (demo-only tool).")
    return _result(False, "block", UNKNOWN_ACCOUNT,
                   "Account type unknown - execution blocked until a verified demo account is confirmed.")


def is_demo_execution(context: ExecutionContext) -> bool:
    return context.environment == "demo" and context.mode == "execute"


def is_live_blocked(context: ExecutionContext) -> bool:
    """A live context is always blocked in this patch (LIVE_IMPLEMENTED is False)."""
    return context.environment == "live"


def live_lock_active() -> bool:
    """True whenever live trading is not available (always True in this patch)."""
    return not LIVE_IMPLEMENTED


def describe_execution_context(context: ExecutionContext) -> str:
    live = "locked" if (context.environment == "live" or live_lock_active()) else "enabled"
    if context.environment == "demo" and context.mode == "execute":
        exec_word = "guarded broker demo"
    elif context.mode == "observe":
        exec_word = "observe (no orders)"
    elif context.environment == "paper":
        exec_word = "paper (no broker)"
    else:
        exec_word = context.mode
    return (f"environment: {context.environment} | execution: {exec_word} | "
            f"live: {live} | account: {context.account_type}")
