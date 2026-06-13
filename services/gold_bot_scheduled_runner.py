"""
services/gold_bot_scheduled_runner.py
---------------------------------------
LM92A - Local offline orchestrator for the Gold Bot demo-learning-review loop.

Chains the ALREADY-EXISTING safe scripts into one repeatable cycle:
  1. preflight        (offline checks - scripts/data dirs)
  2. demo session     (run_gold_bot_demo_session.py - ONLY with --confirm-demo-session)
  3. outcome sync     (run_gold_bot_trade_outcomes_probe.py --write)
  4. learning cycle   (run_gold_bot_learning_cycle.py [--include-real-trades])
  5. session review   (run_gold_bot_session_review.py)
  6. discord          (run_gold_bot_discord_review.py - preview by default, send only with --send-discord)

It adds NO strategy/trading logic - it only SEQUENCES existing commands as
subprocesses, with a plan/dry-run default, per-step guards, redacted run logs, and
fail-stop handling. Trading is impossible unless BOTH --execute AND
--confirm-demo-session are passed (and even then the real session runner + safety
supervisor + risk gate still gate every order). Discord sends only with
--send-discord. No MT5 import here, no webhook value ever read/printed/logged.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

_REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RUNS_DIR = _REPO_ROOT / "data" / "gold_bot" / "runs"
DEFAULT_STEP_TIMEOUT = 900  # seconds, per step
_TAIL_CHARS = 1200

# Scripts the cycle drives (all pre-existing, all demo-only / read-only).
SCRIPTS = {
    "demo_session": "run_gold_bot_demo_session.py",
    "outcome_sync": "run_gold_bot_trade_outcomes_probe.py",
    "learning_cycle": "run_gold_bot_learning_cycle.py",
    "session_review": "run_gold_bot_session_review.py",
    "discord": "run_gold_bot_discord_review.py",
}

_WEBHOOK_RE = re.compile(r"https?://(?:\w+\.)?discord(?:app)?\.com/api/webhooks/\S+", re.IGNORECASE)


def redact(text: str) -> str:
    """Strip anything that looks like a Discord webhook URL. Logs must never carry it."""
    if not isinstance(text, str):
        return ""
    return _WEBHOOK_RE.sub("https://discord.com/api/webhooks/...REDACTED", text)


def _tail(text: str | None) -> str:
    t = redact(text or "")
    return t[-_TAIL_CHARS:]


# ── config ───────────────────────────────────────────────────────────────────────
@dataclass
class CycleConfig:
    execute: bool = False
    confirm_demo_session: bool = False
    duration_minutes: float = 5.0
    max_trades: int = 3
    risk_mode: str = "scalp"
    use_learning_modifiers: bool = False
    include_real_trades: bool = False
    real_trade_weight: float = 2.0
    min_real_trades: int = 5
    send_discord: bool = False
    discord_preview: bool = True
    skip_session: bool = False
    skip_outcomes: bool = False
    skip_learning_cycle: bool = False
    skip_review: bool = False
    skip_discord_preview: bool = False
    continue_on_error: bool = False
    dry_run_log: bool = False
    # learning-cycle overrides
    cycle_timeframe: str = "M1"
    cycle_risk_mode: str = "balanced"
    cycle_max_bars: int = 500
    cycle_horizon: int = 15
    cycle_min_samples: int = 10
    step_timeout: int = DEFAULT_STEP_TIMEOUT


@dataclass
class StepResult:
    name: str
    status: str                       # planned | skipped | success | failed
    command: list[str] | None = None
    started_at: str | None = None
    ended_at: str | None = None
    duration_seconds: float | None = None
    exit_code: int | None = None
    stdout_tail: str = ""
    stderr_tail: str = ""
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CycleRun:
    run_id: str
    started_at: str
    ended_at: str | None = None
    args: dict = field(default_factory=dict)
    steps: list[dict] = field(default_factory=list)
    overall_status: str = "planned"   # planned | success | partial | failed
    warnings: list[str] = field(default_factory=list)
    run_json_path: str | None = None
    run_jsonl_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ── command builders (argv lists; never include the webhook) ───────────────────────
def _py(repo_root: Path, script: str, *args: str) -> list[str]:
    return [sys.executable, str(Path("scripts") / script), *args]


def _demo_cmd(cfg: CycleConfig, repo_root: Path) -> list[str]:
    cmd = _py(repo_root, SCRIPTS["demo_session"], "--confirm-demo-session",
              "--duration-minutes", str(cfg.duration_minutes), "--max-trades", str(cfg.max_trades),
              "--risk-mode", cfg.risk_mode)
    if cfg.use_learning_modifiers:
        cmd.append("--use-learning-modifiers")
    return cmd


def _outcome_cmd(cfg: CycleConfig, repo_root: Path) -> list[str]:
    return _py(repo_root, SCRIPTS["outcome_sync"], "--session-file",
               "data/gold_bot/sessions/session_latest.json", "--write")


def _learning_cmd(cfg: CycleConfig, repo_root: Path) -> list[str]:
    cmd = _py(repo_root, SCRIPTS["learning_cycle"], "--timeframe", cfg.cycle_timeframe,
              "--risk-mode", cfg.cycle_risk_mode, "--max-bars", str(cfg.cycle_max_bars),
              "--horizon", str(cfg.cycle_horizon), "--min-samples", str(cfg.cycle_min_samples))
    if cfg.include_real_trades:
        cmd += ["--include-real-trades", "--real-trade-weight", str(cfg.real_trade_weight),
                "--min-real-trades", str(cfg.min_real_trades)]
    return cmd


def _review_cmd(cfg: CycleConfig, repo_root: Path) -> list[str]:
    return _py(repo_root, SCRIPTS["session_review"])


def _discord_cmd(cfg: CycleConfig, repo_root: Path) -> list[str]:
    cmd = _py(repo_root, SCRIPTS["discord"])
    if cfg.send_discord:
        cmd.append("--send-discord")          # the script itself reads the env webhook
    return cmd


# ── planning ───────────────────────────────────────────────────────────────────────
def _session_latest(repo_root: Path) -> Path:
    return repo_root / "data" / "gold_bot" / "sessions" / "session_latest.json"


def _review_latest(repo_root: Path) -> Path:
    return repo_root / "data" / "gold_bot" / "reviews" / "session_review_latest.json"


def build_plan(cfg: CycleConfig, repo_root: Path = _REPO_ROOT) -> list[dict]:
    """
    Declarative plan: one entry per step with {name, command, willRun, reason}.
    `willRun` is whether a real --execute run would invoke it now; `reason`
    explains a skip. Pure - reads only the filesystem for existence checks.
    """
    plan: list[dict] = []

    def add(name, command, will, reason):
        plan.append({"name": name, "command": command, "willRun": will, "reason": reason})

    add("preflight", None, True, "offline checks")

    # demo session — needs --confirm-demo-session
    if cfg.skip_session:
        add("demo_session", _demo_cmd(cfg, repo_root), False, "skipped (--skip-session)")
    elif not cfg.confirm_demo_session:
        add("demo_session", _demo_cmd(cfg, repo_root), False,
            "demo session not confirmed (pass --confirm-demo-session to run a guarded demo session)")
    else:
        add("demo_session", _demo_cmd(cfg, repo_root), True, None)

    # outcome sync — needs session_latest.json
    if cfg.skip_outcomes:
        add("outcome_sync", _outcome_cmd(cfg, repo_root), False, "skipped (--skip-outcomes)")
    elif not _session_latest(repo_root).exists():
        add("outcome_sync", _outcome_cmd(cfg, repo_root), False,
            "session_latest.json missing (run a demo session first)")
    else:
        add("outcome_sync", _outcome_cmd(cfg, repo_root), True, None)

    if cfg.skip_learning_cycle:
        add("learning_cycle", _learning_cmd(cfg, repo_root), False, "skipped (--skip-learning-cycle)")
    else:
        add("learning_cycle", _learning_cmd(cfg, repo_root), True, None)

    if cfg.skip_review:
        add("session_review", _review_cmd(cfg, repo_root), False, "skipped (--skip-review)")
    else:
        add("session_review", _review_cmd(cfg, repo_root), True, None)

    # discord — preview by default, send only with --send-discord
    if cfg.skip_discord_preview:
        add("discord", _discord_cmd(cfg, repo_root), False, "skipped (--skip-discord-preview)")
    elif not _review_latest(repo_root).exists():
        add("discord", _discord_cmd(cfg, repo_root), False,
            "no session review yet (will skip; review step produces it)")
    else:
        mode = "send" if cfg.send_discord else "preview"
        add("discord", _discord_cmd(cfg, repo_root), True, f"discord {mode}")
    return plan


# ── subprocess ───────────────────────────────────────────────────────────────────
def _default_runner(cmd: list[str], *, cwd: str, timeout: int):
    return subprocess.run(cmd, cwd=cwd, timeout=timeout, capture_output=True, text=True)


# ── execution ────────────────────────────────────────────────────────────────────
def run_cycle(cfg: CycleConfig, *, repo_root: Path = _REPO_ROOT, out_dir: Path = DEFAULT_RUNS_DIR,
              runner_fn: Callable[..., Any] = _default_runner,
              now_fn: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> CycleRun:
    """
    Run (or plan) the cycle. Default (cfg.execute=False) plans only and runs NO
    subprocess. With execute=True it runs each enabled step via runner_fn, stops on
    the first failure unless continue_on_error. Run logs are written only when
    executing (or cfg.dry_run_log). Never trades unless execute AND confirm.
    """
    now = now_fn()
    run = CycleRun(run_id="run_" + now.strftime("%Y%m%d_%H%M%S"), started_at=now.isoformat(),
                   args={k: v for k, v in asdict(cfg).items()})
    plan = build_plan(cfg, repo_root)

    # preflight (offline; runs in plan + execute)
    pf_warnings = _preflight(cfg, repo_root)
    run.warnings += pf_warnings
    run.steps.append(StepResult(
        name="preflight", status="success" if not _preflight_fatal(pf_warnings) else "failed",
        reason="; ".join(pf_warnings) or "ok").to_dict())

    if not cfg.execute:
        # PLAN ONLY — no subprocess, no trading, no discord.
        for p in plan:
            if p["name"] == "preflight":
                continue
            status = "planned" if p["willRun"] else "skipped"
            run.steps.append(StepResult(name=p["name"], status=status, command=p["command"],
                                        reason=p["reason"] or "requires --execute").to_dict())
        run.overall_status = "planned"
        run.ended_at = now_fn().isoformat()
        if cfg.dry_run_log:
            _write_logs(run, out_dir)
        return run

    # EXECUTE
    failed = False
    stopped = False
    for p in plan:
        if p["name"] == "preflight":
            continue
        if stopped:
            run.steps.append(StepResult(name=p["name"], status="skipped", command=p["command"],
                                        reason="skipped after earlier failure").to_dict())
            continue
        if not p["willRun"]:
            run.steps.append(StepResult(name=p["name"], status="skipped", command=p["command"],
                                        reason=p["reason"]).to_dict())
            continue
        res = _run_step(p["name"], p["command"], cwd=str(repo_root), timeout=cfg.step_timeout,
                        runner_fn=runner_fn, now_fn=now_fn)
        run.steps.append(res.to_dict())
        if res.status == "failed":
            failed = True
            if not cfg.continue_on_error:
                stopped = True

    executed = [s for s in run.steps if s["status"] in ("success", "failed")]
    if failed and any(s["status"] == "success" for s in executed):
        run.overall_status = "partial" if cfg.continue_on_error else "failed"
    elif failed:
        run.overall_status = "failed"
    else:
        run.overall_status = "success"
    run.ended_at = now_fn().isoformat()
    _write_logs(run, out_dir)
    return run


def _run_step(name: str, command: list[str], *, cwd: str, timeout: int, runner_fn, now_fn) -> StepResult:
    started = now_fn()
    try:
        res = runner_fn(command, cwd=cwd, timeout=timeout)
        ended = now_fn()
        code = int(getattr(res, "returncode", 1))
        return StepResult(
            name=name, status="success" if code == 0 else "failed", command=command,
            started_at=started.isoformat(), ended_at=ended.isoformat(),
            duration_seconds=round((ended - started).total_seconds(), 2), exit_code=code,
            stdout_tail=_tail(getattr(res, "stdout", "")), stderr_tail=_tail(getattr(res, "stderr", "")),
            reason=None if code == 0 else f"exit {code}")
    except subprocess.TimeoutExpired:
        ended = now_fn()
        return StepResult(name=name, status="failed", command=command,
                          started_at=started.isoformat(), ended_at=ended.isoformat(),
                          exit_code=None, reason=f"timeout after {timeout}s")
    except Exception as exc:  # noqa: BLE001 - one bad step must not crash the runner
        ended = now_fn()
        return StepResult(name=name, status="failed", command=command,
                          started_at=started.isoformat(), ended_at=ended.isoformat(),
                          reason=redact(f"runner error: {exc}"))


# ── preflight ────────────────────────────────────────────────────────────────────
def _preflight(cfg: CycleConfig, repo_root: Path) -> list[str]:
    warnings: list[str] = []
    if not (repo_root / "scripts").is_dir():
        warnings.append(f"FATAL: scripts/ not found under {repo_root}")
    for script in SCRIPTS.values():
        if not (repo_root / "scripts" / script).exists():
            warnings.append(f"FATAL: missing scripts/{script}")
    if not (repo_root / "data" / "gold_bot").is_dir():
        warnings.append("data/gold_bot not found (will be created by the steps)")
    # Webhook env is checked ONLY when a send is requested — and only for presence,
    # never the value. (We do not read it in dry-run.)
    if cfg.execute and cfg.send_discord:
        import os
        if not os.environ.get("LUMORA_GOLD_DISCORD_WEBHOOK_URL"):
            warnings.append("--send-discord set but LUMORA_GOLD_DISCORD_WEBHOOK_URL is unset "
                            "(discord step will fail-safe)")
    return warnings


def _preflight_fatal(warnings: list[str]) -> bool:
    return any(w.startswith("FATAL") for w in warnings)


# ── logs ─────────────────────────────────────────────────────────────────────────
def _write_logs(run: CycleRun, out_dir: Path) -> None:
    try:
        d = Path(out_dir)
        d.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(run.to_dict(), indent=2, default=str)
        named = d / f"{run.run_id}.json"
        latest = d / "run_latest.json"
        named.write_text(payload, encoding="utf-8")
        latest.write_text(payload, encoding="utf-8")
        jl = d / f"{run.run_id}.jsonl"
        jl_latest = d / "run_latest.jsonl"
        lines = [json.dumps({"run_id": run.run_id, "event": "run_start",
                             "started_at": run.started_at}, default=str)]
        lines += [json.dumps({"run_id": run.run_id, "event": "step", **s}, default=str)
                  for s in run.steps]
        lines.append(json.dumps({"run_id": run.run_id, "event": "run_end",
                                 "overall_status": run.overall_status, "ended_at": run.ended_at,
                                 "warnings": run.warnings}, default=str))
        blob = "\n".join(lines) + "\n"
        jl.write_text(blob, encoding="utf-8")
        jl_latest.write_text(blob, encoding="utf-8")
        run.run_json_path = str(named)
        run.run_jsonl_path = str(jl)
    except OSError:
        pass  # logging is best-effort; never break the run
