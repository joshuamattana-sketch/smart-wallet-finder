"""
services/gold_bot_replay_backtest_worker_heartbeat.py
------------------------------------------------------
LM98B - REPLAY/BACKTEST WORKER heartbeat. Upgrades the LM98A reporter into an
offline worker: while the market is closed it actually RUNS new no-lookahead
replay/backtest jobs (LM85A) across a timeframe/risk/horizon plan, refreshes the
LM86A scorecard after each job, and reports the replay-data GROWTH (files/rows/
trades deltas) + performance via Discord every N minutes.

REPLAY / OFFLINE ONLY. It calls the existing `run_replay` service directly (no
subprocess, no shell), never imports MT5 order senders, never runs a demo session,
never enables live trading, and makes no network call unless --send-discord (the
webhook is validated, never printed, and posting fails safely on a bad URL). It
changes no strategy / risk / sizing logic - it only sequences existing replay runs.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from itertools import product
from pathlib import Path
from typing import Any, Callable

from services.gold_bot_replay_backtest_heartbeat import (
    SAFETY_LINE as _HB_SAFETY,
    WEBHOOK_ENV,
    DISCORD_CONTENT_LIMIT,
    HeartbeatConfig,
    _commas,
    _ipts,
    _pct,
    read_active_modifiers,
    refresh_scorecard,
)
from services.gold_bot_discord_review_sender import redact_webhook, resolve_webhook, send_review
from services.gold_bot_learning_journal import DEFAULT_LEARNING_DIR, DEFAULT_REPLAY_DIR

_REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_WORKER_DIR = _REPO_ROOT / "data" / "gold_bot" / "replay_worker"
WORKER_SAFETY_LINE = "Replay worker only. No MT5 orders, no demo session, live locked."
ENVIRONMENT = "replay/offline worker"

# Discord webhook shape (presence + format check; value never printed).
_WEBHOOK_OK = re.compile(r"^https://(?:\w+\.)?discord(?:app)?\.com/api/webhooks/\S+$", re.IGNORECASE)


@dataclass(frozen=True)
class ReplayJob:
    timeframe: str
    risk_mode: str
    horizon: int
    max_bars: int

    @property
    def label(self) -> str:
        return f"{self.timeframe} / {self.risk_mode} / h{self.horizon} / {self.max_bars} bars"


@dataclass
class WorkerConfig:
    duration_minutes: int = 60
    report_every_minutes: int = 15
    job_every_minutes: int = 15
    timeframes: tuple[str, ...] = ("M1", "M5")
    risk_modes: tuple[str, ...] = ("balanced", "scalp")
    horizons: tuple[int, ...] = (15, 30)
    max_bars: int = 1000
    min_samples: int = 10
    include_real_trades: bool = True
    real_trade_weight: float = 2.0
    min_real_trades: int = 5
    send_discord: bool = False
    once: bool = False
    dry_run_plan: bool = False
    sleep_seconds: int | None = None
    symbol: str = "XAUUSD"

    def effective_sleep(self) -> int:
        if self.sleep_seconds is not None and int(self.sleep_seconds) >= 0:
            return int(self.sleep_seconds)
        return max(1, min(int(self.report_every_minutes), int(self.job_every_minutes)) * 60)


@dataclass
class WorkerCycleResult:
    cycle: int
    generated_at: str
    job: str
    mode: str                       # preview | send
    sent: bool
    job_ok: bool
    target: str | None = None       # redacted webhook placeholder only
    content: str = ""
    before: dict = field(default_factory=dict)
    after: dict = field(default_factory=dict)
    data: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    paths: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ── job plan ────────────────────────────────────────────────────────────────────
def build_plan(cfg: WorkerConfig) -> list[ReplayJob]:
    return [ReplayJob(tf, rm, int(h), int(cfg.max_bars))
            for tf, rm, h in product(cfg.timeframes, cfg.risk_modes, cfg.horizons)]


def format_plan(plan: list[ReplayJob]) -> str:
    lines = [f" Replay worker job plan ({len(plan)} jobs):"]
    for i, j in enumerate(plan, 1):
        lines.append(f"   {i:>2}. {j.label}")
    lines.append(" Each cycle runs the next job (offline replay), refreshes the scorecard, "
                 "and reports growth. No orders, no live.")
    return "\n".join(lines)


# ── real replay job (direct service call; imported lazily so tests can inject) ──────
def _default_run_job(job: ReplayJob) -> tuple[bool, str | None]:
    try:
        from services.gold_bot_replay_engine import (  # local import keeps module light
            DEFAULT_HISTORY_DIR, DEFAULT_MACRO_HISTORY_DIR, DEFAULT_REPLAY_DIR as _RDIR,
            ReplayError, run_replay,
        )
    except Exception as exc:  # pragma: no cover - replay engine missing
        return False, f"replay engine unavailable: {exc}"
    try:
        run_replay(symbol="XAUUSD", timeframe=job.timeframe, risk_mode=job.risk_mode,
                   horizons=(job.horizon,), max_bars=job.max_bars, warmup_bars=120,
                   history_dir=str(DEFAULT_HISTORY_DIR), macro_history_dir=str(DEFAULT_MACRO_HISTORY_DIR),
                   out_dir=str(_RDIR), from_time=None, to_time=None, dry_run=False,
                   use_learning_modifiers=False, learning_modifiers_file=None)
        return True, None
    except ReplayError as exc:
        return False, f"replay job [{job.label}] skipped: {exc}"
    except Exception as exc:  # noqa: BLE001 - one bad job must not crash the worker
        return False, f"replay job [{job.label}] error: {exc}"


# ── stats snapshot (global, all replay files) ───────────────────────────────────────
def _collect(cfg: WorkerConfig, horizon: int, *, learning_dir: Path, replay_dir: Path):
    rc = HeartbeatConfig(
        timeframe=None, risk_mode=None, horizon=horizon, min_samples=cfg.min_samples,
        include_real_trades=cfg.include_real_trades, real_trade_weight=cfg.real_trade_weight,
        min_real_trades=cfg.min_real_trades, max_bars=None, symbol=cfg.symbol)
    scorecard, _files, warnings = refresh_scorecard(rc, learning_dir=learning_dir, replay_dir=replay_dir)
    g = (scorecard or {}).get("global") or {}
    stats = {
        "files": (scorecard or {}).get("replay_files_count") or 0,
        "rows": (scorecard or {}).get("rows") or 0,
        "trades": g.get("trade_count") or 0,
        "no_trade": g.get("no_trade_count") or 0,
    }
    return scorecard, stats, warnings


# ── report ───────────────────────────────────────────────────────────────────────
def _delta_line(label: str, before: Any, after: Any) -> str:
    try:
        d = int(after) - int(before)
        sign = "+" if d >= 0 else ""
        return f"{label} {_commas(before)} -> {_commas(after)} ({sign}{_commas(d)})"
    except (TypeError, ValueError):
        return f"{label} {_commas(after)}"


def build_worker_report(*, scorecard: dict | None, before: dict, after: dict,
                        active_modifiers: dict[str, int], real_count: int, cfg: WorkerConfig,
                        job: ReplayJob, cycle: int, elapsed_min: int,
                        remaining_min: int | None, job_ok: bool) -> str:
    title = f"**Lumora Replay Worker · {cfg.report_every_minutes}m Update**"
    head = f"Mode: {ENVIRONMENT} | Current job: {job.label}" + ("" if job_ok else " (skipped)")
    prog = f"Job: {cycle} | Elapsed: {elapsed_min}m"
    if remaining_min is not None:
        prog += f" | Remaining: {remaining_min}m"

    mods = (", ".join(f"{s} {v:+d}" for s, v in sorted(active_modifiers.items()))
            if active_modifiers else "none")

    lines = [title, head, prog, "", "Replay growth:",
             _delta_line("Files", before.get("files"), after.get("files")),
             _delta_line("Rows", before.get("rows"), after.get("rows")),
             _delta_line("Trades", before.get("trades"), after.get("trades")),
             _delta_line("No-trade", before.get("no_trade"), after.get("no_trade"))]

    g = (scorecard or {}).get("global") or {}
    if scorecard:
        lines += ["", "Performance:",
                  (f"Winrate {_pct(g.get('winrate'))} | Expectancy {g.get('expectancy_points')}pt | "
                   f"Status {g.get('recommended_status')}")]
        top = scorecard.get("top_setups_by_expectancy") or []
        if top:
            lines.append("")
            lines.append("Best tactics:")
            for i, t in enumerate(top[:3], 1):
                lines.append(f"{i}. {t.get('setup')} {_ipts(t.get('expectancy_points'))} "
                             f"/ {_commas(t.get('trade_count'))} trades")
        weak = scorecard.get("weak_or_avoid_setups") or []
        if weak:
            lines.append(f"Weak/Avoid: {', '.join(weak[:6])}")
    else:
        lines += ["", "No replay data yet - jobs will populate it (run history backfill if jobs skip)."]

    learning = "replay-dominant" if not real_count else "replay+demo"
    lines.append(f"Learning: {learning} | real demo trades {real_count}")
    lines.append(f"Active modifiers: {mods}")
    lines.append("")
    lines.append(WORKER_SAFETY_LINE)

    content = "\n".join(lines)
    if len(content) > DISCORD_CONTENT_LIMIT:
        content = content[:DISCORD_CONTENT_LIMIT - 18].rstrip() + "\n... (truncated)"
    return content


# ── one cycle: run a job, refresh, report, persist, send/preview ────────────────────
def run_one_cycle(cfg: WorkerConfig, *, job: ReplayJob, cycle: int, elapsed_min: int,
                  remaining_min: int | None, before_stats: dict,
                  out_dir: Path = DEFAULT_WORKER_DIR, learning_dir: Path = DEFAULT_LEARNING_DIR,
                  replay_dir: Path = DEFAULT_REPLAY_DIR,
                  now_fn: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
                  run_job_fn: Callable[[ReplayJob], tuple[bool, str | None]] = _default_run_job,
                  send_fn: Callable[..., dict] = send_review,
                  env: dict | None = None) -> WorkerCycleResult:
    now = now_fn()
    warnings: list[str] = []

    job_ok, job_warn = run_job_fn(job)
    if job_warn:
        warnings.append(job_warn)

    scorecard, after_stats, scw = _collect(cfg, job.horizon, learning_dir=learning_dir, replay_dir=replay_dir)
    warnings += scw
    real_global = (scorecard or {}).get("real_global") or {}
    real_count = int(real_global.get("trade_count") or 0)
    active = read_active_modifiers(learning_dir)

    content = build_worker_report(
        scorecard=scorecard, before=before_stats, after=after_stats, active_modifiers=active,
        real_count=real_count, cfg=cfg, job=job, cycle=cycle, elapsed_min=elapsed_min,
        remaining_min=remaining_min, job_ok=job_ok)

    mode = "send" if cfg.send_discord else "preview"
    sent = False
    target = None
    if cfg.send_discord:
        url = (env.get(WEBHOOK_ENV) if env is not None else resolve_webhook()) or ""
        url = url.strip() if isinstance(url, str) else ""
        if not url:
            warnings.append(f"--send-discord set but env {WEBHOOK_ENV} is missing - not sent")
        elif not _WEBHOOK_OK.match(url):
            warnings.append(f"--send-discord set but {WEBHOOK_ENV} is not a valid Discord webhook URL - not sent")
        else:
            try:
                result = send_fn(content, webhook_url=url, timeout=10.0)
                sent = bool(result.get("ok"))
                target = redact_webhook(url)
                if not sent:
                    warnings.append(f"discord send failed: {result.get('error')}")
            except Exception as exc:  # noqa: BLE001 - never traceback on a bad send
                warnings.append(f"discord send error: {exc}")

    res = WorkerCycleResult(
        cycle=cycle, generated_at=now.isoformat(), job=job.label, mode=mode, sent=sent,
        job_ok=job_ok, target=target, content=content, before=before_stats, after=after_stats,
        warnings=warnings,
        data={"environment": ENVIRONMENT, "broker_orders": "disabled", "live": "locked",
              "job": {"timeframe": job.timeframe, "risk_mode": job.risk_mode,
                      "horizon": job.horizon, "max_bars": job.max_bars},
              "winrate": ((scorecard or {}).get("global") or {}).get("winrate"),
              "expectancy_points": ((scorecard or {}).get("global") or {}).get("expectancy_points"),
              "status": ((scorecard or {}).get("global") or {}).get("recommended_status"),
              "real_demo_trades": real_count, "active_modifiers": active})
    _write_logs(res, out_dir, now)
    return res


# ── loop ──────────────────────────────────────────────────────────────────────────
def run_loop(cfg: WorkerConfig, *, out_dir: Path = DEFAULT_WORKER_DIR,
             learning_dir: Path = DEFAULT_LEARNING_DIR, replay_dir: Path = DEFAULT_REPLAY_DIR,
             now_fn: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
             sleep_fn: Callable[[int], Any] = time.sleep,
             run_job_fn: Callable[[ReplayJob], tuple[bool, str | None]] = _default_run_job,
             send_fn: Callable[..., dict] = send_review) -> list[WorkerCycleResult]:
    """Run the next job + a heartbeat each cycle until duration elapses. --dry-run-plan
    runs NO jobs (returns []); --once runs exactly one cycle and never sleeps."""
    if cfg.dry_run_plan:
        return []

    plan = build_plan(cfg)
    if not plan:
        return []

    start = now_fn()
    results: list[WorkerCycleResult] = []
    carried_after: dict | None = None
    cycle = 0
    while True:
        cycle += 1
        elapsed = max(0, int((now_fn() - start).total_seconds() // 60))
        remaining = None if cfg.once else max(0, int(cfg.duration_minutes) - elapsed)
        job = plan[(cycle - 1) % len(plan)]

        if carried_after is not None:
            before_stats = carried_after
        else:
            _, before_stats, _ = _collect(cfg, job.horizon, learning_dir=learning_dir, replay_dir=replay_dir)

        res = run_one_cycle(
            cfg, job=job, cycle=cycle, elapsed_min=elapsed, remaining_min=remaining,
            before_stats=before_stats, out_dir=out_dir, learning_dir=learning_dir,
            replay_dir=replay_dir, now_fn=now_fn, run_job_fn=run_job_fn, send_fn=send_fn)
        results.append(res)
        carried_after = res.after

        if cfg.once or elapsed >= int(cfg.duration_minutes):
            break
        sleep_fn(cfg.effective_sleep())
    return results


# ── logs ──────────────────────────────────────────────────────────────────────────
def _write_logs(res: WorkerCycleResult, out_dir: Path, now: datetime) -> None:
    try:
        d = Path(out_dir)
        d.mkdir(parents=True, exist_ok=True)
        stamp = now.strftime("%Y%m%d_%H%M%S")
        named_json = d / f"worker_{stamp}.json"
        latest_json = d / "worker_latest.json"
        named_md = d / f"worker_{stamp}.md"
        latest_md = d / "worker_latest.md"
        events = d / "worker_events.jsonl"
        res.paths = {"json": str(named_json), "latest_json": str(latest_json),
                     "md": str(named_md), "latest_md": str(latest_md), "events": str(events)}
        payload = json.dumps(res.to_dict(), indent=2, default=str)
        named_json.write_text(payload, encoding="utf-8")
        latest_json.write_text(payload, encoding="utf-8")
        named_md.write_text(res.content + "\n", encoding="utf-8")
        latest_md.write_text(res.content + "\n", encoding="utf-8")
        with events.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"event": "cycle", "cycle": res.cycle, "job": res.job,
                                "generated_at": res.generated_at, "job_ok": res.job_ok,
                                "sent": res.sent, "before": res.before, "after": res.after},
                               default=str) + "\n")
    except OSError:
        res.paths = {}
