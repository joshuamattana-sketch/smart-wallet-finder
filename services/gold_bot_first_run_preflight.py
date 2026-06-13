"""
services/gold_bot_first_run_preflight.py
------------------------------------------
LM92B - First market-open demo run PREFLIGHT for the Gold Bot.

A READ-ONLY checklist that tells the owner GO / NO-GO before a short autonomous
demo run. It runs the EXISTING read-only probes (MT5 connector probe, safety
probe, daily-cycle PLAN) as subprocesses, reads local artifacts, checks the
kill-switch/live flags in-process, and prints a clear checklist + the exact next
command. It adds NO strategy/trading logic and PLACES NO ORDERS.

Strict boundaries: read-only. Places no orders, no demo execution, no Discord send,
no MT5 import here (the connector probe runs as a separate read-only subprocess).
The webhook env value is never read or printed (only presence, only with
--check-discord-env).
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from services.gold_bot_risk_gate import SafetyConfig

_REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PREFLIGHT_DIR = _REPO_ROOT / "data" / "gold_bot" / "preflight"
DEFAULT_TIMEOUT = 120

PASS, WARN, FAIL, SKIP = "PASS", "WARN", "FAIL", "SKIP"

REQUIRED_SCRIPTS = (
    "run_gold_bot_daily_cycle.py",
    "run_gold_bot_safety_probe.py",
    "run_mt5_demo_connector_probe.py",
    "run_gold_bot_session_review.py",
    "run_gold_bot_discord_review.py",
)

# Substrings in MT5 probe output that mean "do not trade now".
_STALE_MARKERS = ("stale", "market closed", "no tick", "no fresh tick", "not a verified demo")
# Substrings in safety probe output that block.
_SAFETY_BLOCK_MARKERS = ("cooldown   : active", "cooldown : active", "active until", "critical")


@dataclass
class PreflightConfig:
    skip_mt5: bool = False
    skip_safety: bool = False
    duration_minutes: float = 5.0
    max_trades: int = 3
    risk_mode: str = "scalp"
    use_learning_modifiers: bool = False
    include_real_trades: bool = False
    send_discord: bool = False
    check_discord_env: bool = False
    write: bool = False
    timeout_seconds: int = DEFAULT_TIMEOUT


@dataclass
class CheckResult:
    name: str
    status: str            # PASS | WARN | FAIL | SKIP
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Preflight:
    generated_at: str
    overall: str           # GO | NO-GO
    go: bool
    checks: list[dict] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    go_command: str = ""
    troubleshooting: list[str] = field(default_factory=list)
    config: dict = field(default_factory=dict)
    preflight_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ── subprocess ──────────────────────────────────────────────────────────────────
def _default_runner(cmd: list[str], *, cwd: str, timeout: int):
    return subprocess.run(cmd, cwd=cwd, timeout=timeout, capture_output=True, text=True)


def _py(script: str, *args: str) -> list[str]:
    return [sys.executable, str(Path("scripts") / script), *args]


def _safe_run(runner_fn, cmd, *, cwd, timeout) -> tuple[int, str]:
    try:
        res = runner_fn(cmd, cwd=cwd, timeout=timeout)
        out = ((getattr(res, "stdout", "") or "") + "\n" + (getattr(res, "stderr", "") or "")).lower()
        return int(getattr(res, "returncode", 1)), out
    except subprocess.TimeoutExpired:
        return 124, "timeout"
    except Exception as exc:  # noqa: BLE001 - a probe failure must not crash preflight
        return 1, f"runner error: {exc}".lower()


# ── individual checks ───────────────────────────────────────────────────────────
def _check_repo_root(repo_root: Path) -> CheckResult:
    ok = (repo_root / "scripts").is_dir()
    return CheckResult("repo_root", PASS if ok else FAIL,
                       str(repo_root) if ok else f"scripts/ not found under {repo_root}")


def _check_required_scripts(repo_root: Path) -> CheckResult:
    missing = [s for s in REQUIRED_SCRIPTS if not (repo_root / "scripts" / s).exists()]
    if missing:
        return CheckResult("required_scripts", FAIL, "missing: " + ", ".join(missing))
    return CheckResult("required_scripts", PASS, f"{len(REQUIRED_SCRIPTS)} scripts present")


def _check_daily_cycle_plan(repo_root: Path, runner_fn, timeout: int) -> CheckResult:
    rc, out = _safe_run(runner_fn, _py("run_gold_bot_daily_cycle.py"),
                        cwd=str(repo_root), timeout=timeout)
    if rc == 0 and "plan" in out:
        return CheckResult("daily_cycle_plan", PASS, "plan mode runs cleanly")
    return CheckResult("daily_cycle_plan", FAIL, f"daily cycle plan failed (exit {rc})")


def _check_mt5(cfg: PreflightConfig, repo_root: Path, runner_fn) -> CheckResult:
    if cfg.skip_mt5:
        return CheckResult("mt5_demo_tick", SKIP, "skipped (--skip-mt5); tick freshness unknown")
    rc, out = _safe_run(runner_fn, _py("run_mt5_demo_connector_probe.py", "--bars", "10"),
                        cwd=str(repo_root), timeout=cfg.timeout_seconds)
    if rc != 0:
        return CheckResult("mt5_demo_tick", FAIL,
                           "MT5 unavailable / not a demo account / no candles (probe failed)")
    if any(m in out for m in _STALE_MARKERS):
        return CheckResult("mt5_demo_tick", FAIL, "MT5 reports stale tick / market closed")
    return CheckResult("mt5_demo_tick", PASS, "MT5 demo connected, fresh tick, read-only")


def _check_safety(cfg: PreflightConfig, repo_root: Path, runner_fn) -> CheckResult:
    if cfg.skip_safety:
        return CheckResult("safety_probe", SKIP, "skipped (--skip-safety)")
    rc, out = _safe_run(runner_fn, _py("run_gold_bot_safety_probe.py"),
                        cwd=str(repo_root), timeout=cfg.timeout_seconds)
    if rc != 0:
        return CheckResult("safety_probe", FAIL, f"safety probe failed (exit {rc})")
    if any(m in out for m in _SAFETY_BLOCK_MARKERS):
        return CheckResult("safety_probe", FAIL, "safety reports active cooldown / critical block")
    return CheckResult("safety_probe", PASS, "supervisor green (no active cooldown)")


def _check_kill_switch(safety_config_fn: Callable[[], SafetyConfig]) -> CheckResult:
    try:
        s = safety_config_fn()
    except Exception as exc:  # noqa: BLE001
        return CheckResult("kill_switch", WARN, f"could not read safety config ({exc})")
    if getattr(s, "kill_switch", False):
        return CheckResult("kill_switch", FAIL, "GOLD_BOT_KILL_SWITCH is ACTIVE — all orders blocked")
    if getattr(s, "live_trading_enabled", False) or getattr(s, "allow_real_orders", False):
        return CheckResult("kill_switch", FAIL, "live/real-order flags set — refuse (demo-only tool)")
    return CheckResult("kill_switch", PASS, "kill switch off, demo-only flags safe")


def _default_macro_state() -> str | None:
    """Offline macro event-risk state from the default calendar/macro (no MT5)."""
    try:
        from services.gold_bot_macro_context import build_macro_context, load_calendar_or_macro
        now = datetime.now(timezone.utc)
        events, source, _w = load_calendar_or_macro(calendar_file=None, macro_events_file=None, now=now)
        return build_macro_context(now, events, source).event_risk_state
    except Exception:  # noqa: BLE001 - macro context is advisory; never crash preflight
        return None


def _check_macro(macro_state_fn: Callable[[], str | None]) -> CheckResult:
    try:
        state = macro_state_fn()
    except Exception as exc:  # noqa: BLE001
        return CheckResult("macro_lockout", WARN, f"unknown ({exc})")
    if state == "lockout":
        return CheckResult("macro_lockout", FAIL, "macro lockout ACTIVE — no new trades")
    if state == "watch":
        return CheckResult("macro_lockout", WARN, "macro watch window (elevated event risk)")
    if state in ("clear", "normal", "post_event"):
        return CheckResult("macro_lockout", PASS, f"no macro lockout ({state})")
    return CheckResult("macro_lockout", WARN,
                       "unknown (no calendar configured; supervisor enforces lockout at runtime)")


def _check_artifacts(repo_root: Path) -> CheckResult:
    d = repo_root / "data" / "gold_bot"
    paths = {
        "session": d / "sessions" / "session_latest.json",
        "review": d / "reviews" / "session_review_latest.json",
        "active_modifiers": d / "learning" / "active_demo_modifiers.json",
        "scorecard": d / "learning" / "scorecard_latest.json",
        "run_log": d / "runs" / "run_latest.json",
    }
    missing = [k for k, p in paths.items() if not p.exists()]
    if not missing:
        return CheckResult("local_artifacts", PASS, "all local artifacts present")
    return CheckResult("local_artifacts", WARN, "missing (ok for first run): " + ", ".join(missing))


def _check_discord(cfg: PreflightConfig) -> CheckResult:
    if cfg.check_discord_env:
        import os
        present = bool(os.environ.get("LUMORA_GOLD_DISCORD_WEBHOOK_URL"))
        # Presence only — the value is never read or printed.
        return CheckResult("discord", PASS if present else WARN,
                           "webhook env present (value not read)" if present
                           else "webhook env not set — review send unavailable (preview still works)")
    return CheckResult("discord", PASS, "optional / manual; not required for GO (no env checked)")


# ── orchestration ─────────────────────────────────────────────────────────────────
_BLOCKING = {"repo_root", "required_scripts", "daily_cycle_plan", "mt5_demo_tick",
             "safety_probe", "kill_switch", "macro_lockout"}


def run_preflight(cfg: PreflightConfig, *, repo_root: Path = _REPO_ROOT,
                  out_dir: Path = DEFAULT_PREFLIGHT_DIR,
                  runner_fn: Callable[..., Any] = _default_runner,
                  safety_config_fn: Callable[[], SafetyConfig] = SafetyConfig.from_env,
                  macro_state_fn: Callable[[], str | None] = _default_macro_state,
                  now_fn: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> Preflight:
    checks = [
        _check_repo_root(repo_root),
        _check_required_scripts(repo_root),
        _check_daily_cycle_plan(repo_root, runner_fn, cfg.timeout_seconds),
        _check_mt5(cfg, repo_root, runner_fn),
        _check_safety(cfg, repo_root, runner_fn),
        _check_kill_switch(safety_config_fn),
        _check_macro(macro_state_fn),
        _check_artifacts(repo_root),
        _check_discord(cfg),
    ]
    reasons = [f"{c.name}: {c.detail}" for c in checks if c.status == FAIL and c.name in _BLOCKING]
    go = not reasons
    pf = Preflight(
        generated_at=now_fn().isoformat(),
        overall="GO" if go else "NO-GO", go=go,
        checks=[c.to_dict() for c in checks], reasons=reasons,
        go_command=_go_command(cfg), troubleshooting=_troubleshooting(),
        config=asdict(cfg))
    if cfg.write:
        pf.preflight_path = _write(pf, out_dir, now_fn())
    return pf


def _go_command(cfg: PreflightConfig) -> str:
    parts = [".\\scripts\\start_gold_bot_daily_cycle.ps1", "-Execute", "-ConfirmDemoSession",
             "-DurationMinutes", str(cfg.duration_minutes), "-MaxTrades", str(cfg.max_trades),
             "-RiskMode", cfg.risk_mode]
    if cfg.use_learning_modifiers:
        parts.append("-UseLearningModifiers")
    if cfg.include_real_trades:
        parts.append("-IncludeRealTrades")
    if cfg.send_discord:
        parts.append("-SendDiscord")
    return " ".join(parts)


def _troubleshooting() -> list[str]:
    return [
        "python scripts/run_mt5_demo_connector_probe.py --bars 10 --history-debug",
        "python scripts/run_gold_bot_safety_probe.py",
        "python scripts/run_gold_bot_daily_cycle.py",
    ]


def _write(pf: Preflight, out_dir: Path, now: datetime) -> str | None:
    try:
        d = Path(out_dir)
        d.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(pf.to_dict(), indent=2, default=str)
        named = d / f"preflight_{now.strftime('%Y%m%d_%H%M%S')}.json"
        latest = d / "preflight_latest.json"
        named.write_text(payload, encoding="utf-8")
        latest.write_text(payload, encoding="utf-8")
        return str(named)
    except OSError:
        return None
