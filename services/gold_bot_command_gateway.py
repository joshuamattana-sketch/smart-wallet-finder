"""
services/gold_bot_command_gateway.py
-------------------------------------
LM94A - Local-only command gateway for the Lumora Gold Bot.

This is the SAFE FOUNDATION for future one-click website controls. It does NOT
add UI, an HTTP route, live trading, or any new strategy/trading logic. It only
lets a caller (CLI today, a localhost-only API later) trigger a SMALL, FIXED
WHITELIST of already-existing Gold Bot scripts as subprocesses, with strict caps,
redacted run logs, and a dry-run/no-execution default.

Whitelisted actions (NOTHING else is runnable):
  * preflight                 -> run_gold_bot_first_run_preflight.py   (read-only)
  * daily_cycle_offline       -> run_gold_bot_daily_cycle.py --execute --skip-session
  * daily_cycle_guarded_demo  -> run_gold_bot_daily_cycle.py --execute --confirm-demo-session ...
  * session_review            -> run_gold_bot_session_review.py        (offline)
  * discord_preview           -> run_gold_bot_discord_review.py        (no network)
  * discord_send              -> run_gold_bot_discord_review.py --send-discord

Safety (by construction, not by trust):
  * No free-form shell. Commands are built from a fixed table + validated values
    only; nothing the caller types is ever interpolated into the argv.
  * No live trading. There is no `environment`/`--allow-live-trading` knob here;
    guarded demo always routes through the existing daily-cycle -> demo session
    runner -> safety supervisor -> risk gate -> macro lockout -> kill switch path.
  * Guarded demo requires explicit confirmation AND obeys caps
    (duration <= 15m, max_trades <= 5, risk_mode in {safe, balanced, scalp}).
  * Discord send requires BOTH allow_discord_send AND the env var
    LUMORA_GOLD_DISCORD_WEBHOOK_URL being present. The value is NEVER read here,
    NEVER printed, NEVER logged. Anything webhook-shaped in captured output is
    redacted before it touches a log.
  * No MT5 trading calls, no order placement, and no HTTP client live in this
    module - Discord delivery is delegated entirely to the existing review script.
  * Default is dry-run: validate + print the planned command, run NO subprocess.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Mapping

_REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_COMMANDS_DIR = _REPO_ROOT / "data" / "gold_bot" / "commands"
DEFAULT_TIMEOUT = 900          # seconds
MAX_TIMEOUT = 3600             # hard ceiling so a bad value can't run away
_TAIL_CHARS = 1200

WEBHOOK_ENV = "LUMORA_GOLD_DISCORD_WEBHOOK_URL"

# ── caps for the guarded demo cycle ────────────────────────────────────────────────
DURATION_DEFAULT = 5
DURATION_MAX = 15
MAX_TRADES_DEFAULT = 3
MAX_TRADES_MAX = 5
RISK_MODES_ALLOWED = ("safe", "balanced", "scalp")   # aggressive/experimental rejected


# ── allowed actions (enum + tuple; nothing else is runnable) ────────────────────────
class Action(str, Enum):
    PREFLIGHT = "preflight"
    DAILY_CYCLE_OFFLINE = "daily_cycle_offline"
    DAILY_CYCLE_GUARDED_DEMO = "daily_cycle_guarded_demo"
    SESSION_REVIEW = "session_review"
    DISCORD_PREVIEW = "discord_preview"
    DISCORD_SEND = "discord_send"


ALLOWED_ACTIONS: tuple[str, ...] = tuple(a.value for a in Action)

# Scripts the gateway may drive (all pre-existing, all demo-only / read-only).
SCRIPTS = {
    "preflight": "run_gold_bot_first_run_preflight.py",
    "daily_cycle": "run_gold_bot_daily_cycle.py",
    "session_review": "run_gold_bot_session_review.py",
    "discord_review": "run_gold_bot_discord_review.py",
}

# Flags the gateway may ever attach. The "no arbitrary command" guarantee: every
# token in a built command is either python, a whitelisted script path, a flag in
# this set, or a value we validated (risk_mode / clamped int). Used by tests too.
ALLOWED_FLAGS: frozenset[str] = frozenset({
    "--execute", "--skip-session", "--confirm-demo-session",
    "--duration-minutes", "--max-trades", "--risk-mode",
    "--use-learning-modifiers", "--include-real-trades", "--send-discord",
})

_WEBHOOK_RE = re.compile(r"https?://(?:\w+\.)?discord(?:app)?\.com/api/webhooks/\S+", re.IGNORECASE)


# ── secrets hygiene ─────────────────────────────────────────────────────────────────
def redact(text: str | None) -> str:
    """Strip anything that looks like a Discord webhook URL. Logs must never carry it."""
    if not isinstance(text, str):
        return ""
    return _WEBHOOK_RE.sub("https://discord.com/api/webhooks/...REDACTED", text)


def _redaction_count(text: str | None) -> int:
    return len(_WEBHOOK_RE.findall(text)) if isinstance(text, str) else 0


def _tail(text: str | None) -> str:
    return redact(text or "")[-_TAIL_CHARS:]


def _webhook_present(env: Mapping[str, str]) -> bool:
    """Presence check ONLY. Never returns or stores the value."""
    val = env.get(WEBHOOK_ENV, "")
    return bool(isinstance(val, str) and val.strip())


# ── request / result models ─────────────────────────────────────────────────────────
@dataclass
class GatewayRequest:
    action: str
    duration_minutes: int = DURATION_DEFAULT
    max_trades: int = MAX_TRADES_DEFAULT
    risk_mode: str = "scalp"
    use_learning_modifiers: bool = False
    include_real_trades: bool = False
    allow_discord_send: bool = False
    confirm_guarded_demo: bool = False
    dry_run: bool = True
    timeout_seconds: int = DEFAULT_TIMEOUT
    requested_by: str = "local"
    source: str = "cli"           # "cli" | "web_local"

    def effective_timeout(self) -> int:
        try:
            t = int(self.timeout_seconds)
        except (TypeError, ValueError):
            t = DEFAULT_TIMEOUT
        if t <= 0:
            t = DEFAULT_TIMEOUT
        return min(t, MAX_TIMEOUT)


@dataclass
class GatewayResult:
    request_id: str
    action: str
    accepted: bool
    status: str = "blocked"        # planned | success | failed | blocked
    reason: str | None = None
    command: str | None = None     # readable, redacted; never contains a secret
    started_at: str | None = None
    ended_at: str | None = None
    exit_code: int | None = None
    stdout_tail: str = ""
    stderr_tail: str = ""
    warnings: list[str] = field(default_factory=list)
    generated_files: list[str] = field(default_factory=list)
    redactions_applied: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ── validation (pure; only env presence is consulted, never the value) ──────────────
def validate(req: GatewayRequest, *, env: Mapping[str, str] | None = None
             ) -> tuple[bool, str | None, list[str]]:
    """
    Return (accepted, reason, warnings). A False accepted means the request is
    BLOCKED and no subprocess may run. Reasons are caller-safe (no secrets).
    """
    e = os.environ if env is None else env
    warnings: list[str] = []

    if req.action not in ALLOWED_ACTIONS:
        return (False,
                f"unknown action '{req.action}' - allowed: {', '.join(ALLOWED_ACTIONS)}",
                warnings)

    if req.action == Action.DAILY_CYCLE_GUARDED_DEMO.value:
        if not req.confirm_guarded_demo:
            return (False, "guarded demo blocked: requires confirm_guarded_demo=True "
                    "(pass --confirm-guarded-demo)", warnings)
        if req.duration_minutes <= 0:
            return (False, "guarded demo blocked: duration_minutes must be > 0", warnings)
        if req.duration_minutes > DURATION_MAX:
            return (False, f"guarded demo blocked: duration_minutes "
                    f"{req.duration_minutes} exceeds cap {DURATION_MAX}", warnings)
        if req.max_trades <= 0:
            return (False, "guarded demo blocked: max_trades must be > 0", warnings)
        if req.max_trades > MAX_TRADES_MAX:
            return (False, f"guarded demo blocked: max_trades {req.max_trades} "
                    f"exceeds cap {MAX_TRADES_MAX}", warnings)
        if req.risk_mode not in RISK_MODES_ALLOWED:
            return (False, f"guarded demo blocked: risk_mode '{req.risk_mode}' not allowed "
                    f"(use {', '.join(RISK_MODES_ALLOWED)})", warnings)

    if req.action == Action.DISCORD_SEND.value:
        if not req.allow_discord_send:
            return (False, "discord_send blocked: requires allow_discord_send=True "
                    "(pass --allow-discord-send)", warnings)
        if not _webhook_present(e):
            return (False, f"discord_send blocked: env {WEBHOOK_ENV} is not set "
                    "(presence required; value never read or logged)", warnings)

    return True, None, warnings


# ── command builder (fixed table + validated values only; never a secret) ───────────
def _py(script: str, *args: str) -> list[str]:
    return [sys.executable, str(Path("scripts") / script), *args]


def build_command(req: GatewayRequest) -> list[str] | None:
    """
    Build the argv for a whitelisted action. Returns None for an unknown action.
    Nothing the caller free-types is interpolated: only fixed flags, the validated
    risk_mode, and clamped integers ever appear.
    """
    a = req.action

    if a == Action.PREFLIGHT.value:
        cmd = _py(SCRIPTS["preflight"])
        if req.use_learning_modifiers:
            cmd.append("--use-learning-modifiers")
        if req.include_real_trades:
            cmd.append("--include-real-trades")
        return cmd

    if a == Action.DAILY_CYCLE_OFFLINE.value:
        cmd = _py(SCRIPTS["daily_cycle"], "--execute", "--skip-session")
        if req.use_learning_modifiers:
            cmd.append("--use-learning-modifiers")
        if req.include_real_trades:
            cmd.append("--include-real-trades")
        return cmd

    if a == Action.DAILY_CYCLE_GUARDED_DEMO.value:
        cmd = _py(SCRIPTS["daily_cycle"], "--execute", "--confirm-demo-session",
                  "--duration-minutes", str(int(req.duration_minutes)),
                  "--max-trades", str(int(req.max_trades)),
                  "--risk-mode", req.risk_mode)
        if req.use_learning_modifiers:
            cmd.append("--use-learning-modifiers")
        if req.include_real_trades:
            cmd.append("--include-real-trades")
        return cmd

    if a == Action.SESSION_REVIEW.value:
        return _py(SCRIPTS["session_review"])

    if a == Action.DISCORD_PREVIEW.value:
        return _py(SCRIPTS["discord_review"])

    if a == Action.DISCORD_SEND.value:
        # The script itself reads the env webhook; the gateway never touches it.
        return _py(SCRIPTS["discord_review"], "--send-discord")

    return None


def display_command(cmd: list[str] | None) -> str:
    """Readable, redacted form for logs/console. Never contains a secret anyway."""
    if not cmd:
        return ""
    parts: list[str] = []
    for c in cmd:
        if c == sys.executable or Path(c).name.lower().startswith("python"):
            parts.append("python")
        else:
            parts.append(str(c).replace("\\", "/"))
    return redact(" ".join(parts))


# ── subprocess runner (injectable for tests) ────────────────────────────────────────
def _default_runner(cmd: list[str], *, cwd: str, timeout: int):
    return subprocess.run(cmd, cwd=cwd, timeout=timeout, capture_output=True, text=True)


# ── execution ────────────────────────────────────────────────────────────────────
def run_gateway(req: GatewayRequest, *, repo_root: Path = _REPO_ROOT,
                out_dir: Path = DEFAULT_COMMANDS_DIR,
                runner_fn: Callable[..., Any] = _default_runner,
                now_fn: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
                env: Mapping[str, str] | None = None,
                write_log: bool = False) -> GatewayResult:
    """
    Validate, then either plan (dry-run, default) or execute one whitelisted action.

    * Blocked  -> accepted=False, status="blocked", no subprocess.
    * Dry-run  -> status="planned", command shown, NO subprocess; logs only if write_log.
    * Execute  -> runs the subprocess via runner_fn (cwd=repo_root, timeout), captures
                  + redacts output, status success|failed; always writes run logs.
    """
    now = now_fn()
    result = GatewayResult(
        request_id="cmd_" + now.strftime("%Y%m%d_%H%M%S_%f"),
        action=req.action, accepted=False, status="blocked",
        started_at=now.isoformat())

    accepted, reason, warnings = validate(req, env=env)
    result.accepted = accepted
    result.warnings = list(warnings)
    if not accepted:
        result.status = "blocked"
        result.reason = reason
        result.ended_at = now_fn().isoformat()
        if write_log:
            _write_logs(result, out_dir)
        return result

    cmd = build_command(req)
    result.command = display_command(cmd)

    if req.dry_run:
        result.status = "planned"
        result.reason = "dry-run: validated; command not executed"
        result.ended_at = now_fn().isoformat()
        if write_log:
            _write_logs(result, out_dir)
        return result

    # EXECUTE — one subprocess, captured + redacted.
    timeout = req.effective_timeout()
    started = now_fn()
    result.started_at = started.isoformat()
    try:
        proc = runner_fn(cmd, cwd=str(repo_root), timeout=timeout)
        ended = now_fn()
        raw_out = getattr(proc, "stdout", "") or ""
        raw_err = getattr(proc, "stderr", "") or ""
        code = int(getattr(proc, "returncode", 1))
        result.exit_code = code
        result.stdout_tail = _tail(raw_out)
        result.stderr_tail = _tail(raw_err)
        result.redactions_applied = _redaction_count(raw_out) + _redaction_count(raw_err)
        result.status = "success" if code == 0 else "failed"
        result.reason = None if code == 0 else f"exit {code}"
        result.ended_at = ended.isoformat()
    except subprocess.TimeoutExpired:
        result.status = "failed"
        result.exit_code = None
        result.reason = f"timeout after {timeout}s"
        result.ended_at = now_fn().isoformat()
    except Exception as exc:  # noqa: BLE001 - a bad subprocess must not crash the gateway
        result.status = "failed"
        result.reason = redact(f"runner error: {exc}")
        result.ended_at = now_fn().isoformat()

    _write_logs(result, out_dir)
    return result


# ── logs (json + jsonl, named + latest; best-effort, always redacted) ───────────────
def _write_logs(result: GatewayResult, out_dir: Path) -> None:
    try:
        d = Path(out_dir)
        d.mkdir(parents=True, exist_ok=True)
        named_json = d / f"command_{result.request_id}.json"
        named_jsonl = d / f"command_{result.request_id}.jsonl"
        latest_json = d / "command_latest.json"
        latest_jsonl = d / "command_latest.jsonl"
        # record the files we are about to write so the log is self-describing
        result.generated_files = [str(named_json), str(named_jsonl),
                                  str(latest_json), str(latest_jsonl)]
        payload = redact(json.dumps(result.to_dict(), indent=2, default=str))
        named_json.write_text(payload, encoding="utf-8")
        latest_json.write_text(payload, encoding="utf-8")
        line = redact(json.dumps({"event": "command", **result.to_dict()}, default=str)) + "\n"
        named_jsonl.write_text(line, encoding="utf-8")
        latest_jsonl.write_text(line, encoding="utf-8")
    except OSError:
        result.generated_files = []   # logging is best-effort; never break the run
