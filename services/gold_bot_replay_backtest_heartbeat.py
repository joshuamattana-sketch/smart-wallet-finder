"""
services/gold_bot_replay_backtest_heartbeat.py
-----------------------------------------------
LM98A - Long-running REPLAY / BACKTEST heartbeat for the Gold Bot.

Every N minutes it refreshes the offline learning scorecard (LM86A, from stored
replay JSONL), reads the active demo modifiers, counts real demo outcomes, and
builds a compact Discord progress report. DEFAULT = preview (prints, never sends).
Sending requires BOTH --send-discord AND the env LUMORA_GOLD_DISCORD_WEBHOOK_URL.

This runner is REPLAY / OFFLINE ONLY:
  * environment = replay/offline, execution = observe, broker orders = disabled,
    live = locked - all hard-coded here.
  * It NEVER imports or calls MT5 order senders, NEVER calls the demo session
    runner, NEVER accepts arbitrary commands, and makes NO network call unless
    --send-discord is set. The webhook value is never printed or logged
    (redacted target only). It changes no strategy / risk / modifier math - it
    only reads the existing learning artifacts and reports them.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from services.gold_bot_learning_journal import (
    DEFAULT_LEARNING_DIR,
    DEFAULT_REPLAY_DIR,
    build_real_trade_stats,
    build_scorecard,
    load_demo_trade_outcomes,
    load_replay_rows,
    write_real_trade_blend,
    write_scorecard,
)
from services.gold_bot_learning_modifiers import ACTIVE_FILE, load_active_modifiers
from services.gold_bot_discord_review_sender import (
    WEBHOOK_ENV,
    redact_webhook,
    resolve_webhook,
    send_review,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_HEARTBEAT_DIR = _REPO_ROOT / "data" / "gold_bot" / "replay_heartbeat"
DISCORD_CONTENT_LIMIT = 2000

# Hard safety framing - this runner is replay/offline only.
ENVIRONMENT = "replay/offline"
EXECUTION = "observe"
SAFETY_LINE = "Replay only. No MT5 orders, no demo session, live locked."


# ── config ───────────────────────────────────────────────────────────────────────
@dataclass
class HeartbeatConfig:
    duration_minutes: int = 60
    report_every_minutes: int = 15
    timeframe: str = "M1"
    risk_mode: str = "balanced"
    horizon: int = 15
    min_samples: int = 10
    include_real_trades: bool = True
    real_trade_weight: float = 2.0
    min_real_trades: int = 5
    max_bars: int | None = None
    send_discord: bool = False
    once: bool = False
    symbol: str = "XAUUSD"
    sleep_seconds: int | None = None   # default computed from report interval

    def effective_sleep(self) -> int:
        if self.sleep_seconds is not None and int(self.sleep_seconds) >= 0:
            return int(self.sleep_seconds)
        return max(1, int(self.report_every_minutes) * 60)


@dataclass
class HeartbeatResult:
    heartbeat: int
    generated_at: str
    mode: str                       # preview | send
    sent: bool
    target: str | None = None       # redacted webhook placeholder, never the value
    content: str = ""
    data: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    paths: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ── scorecard refresh (offline; reuses the LM86A service, no subprocess) ────────────
def refresh_scorecard(cfg: HeartbeatConfig, *, learning_dir: Path = DEFAULT_LEARNING_DIR,
                      replay_dir: Path = DEFAULT_REPLAY_DIR
                      ) -> tuple[dict | None, list[str], list[str]]:
    """Rebuild the scorecard from stored replay JSONL. Returns (scorecard|None, files, warnings)."""
    rows, files, warnings = load_replay_rows(
        replay_dir, symbol=cfg.symbol, timeframe=cfg.timeframe, risk_mode=cfg.risk_mode)
    if not files or not rows:
        return None, files, warnings + [
            "no replay data yet - run scripts/run_gold_bot_replay.py first"]
    if cfg.max_bars:
        rows = rows[: int(cfg.max_bars)]
    real_stats = None
    if cfg.include_real_trades:
        events_file = Path(learning_dir) / "learning_events.jsonl"
        outcomes, rt_warn, dups = load_demo_trade_outcomes(events_file)
        real_stats = build_real_trade_stats(outcomes, min_real_trades=cfg.min_real_trades,
                                            duplicates_ignored=dups, warnings=rt_warn)
        warnings = warnings + rt_warn
    scorecard = build_scorecard(rows, horizon=cfg.horizon, min_samples=cfg.min_samples,
                                warnings=warnings, real_stats=real_stats,
                                real_trade_weight=cfg.real_trade_weight)
    scorecard["replay_files_count"] = len(files)
    try:
        write_scorecard(learning_dir, scorecard, symbol=cfg.symbol,
                        timeframe=cfg.timeframe, risk_mode=cfg.risk_mode)
        if real_stats is not None:
            write_real_trade_blend(learning_dir, scorecard, real_stats)
    except OSError:
        pass  # reporting is best-effort; never break the heartbeat
    return scorecard, files, warnings


def read_active_modifiers(learning_dir: Path = DEFAULT_LEARNING_DIR) -> dict[str, int]:
    """Return {setup: confidence_modifier} for the ACTIVE modifiers (read-only)."""
    active, _ = load_active_modifiers(Path(learning_dir) / ACTIVE_FILE)
    out: dict[str, int] = {}
    for setup, entry in (active or {}).items():
        if isinstance(entry, dict):
            out[setup] = int(entry.get("confidence_modifier", 0))
        elif isinstance(entry, (int, float)):
            out[setup] = int(entry)
    return out


# ── report builder ─────────────────────────────────────────────────────────────────
def _pct(frac: Any) -> str:
    try:
        return f"{round(float(frac) * 100)}%"
    except (TypeError, ValueError):
        return "n/a"


def _ipts(v: Any) -> str:
    try:
        return f"{float(v):+.1f}pt"
    except (TypeError, ValueError):
        return "n/a"


def _commas(n: Any) -> str:
    try:
        return f"{int(n):,}"
    except (TypeError, ValueError):
        return str(n)


def build_report(*, scorecard: dict | None, active_modifiers: dict[str, int], real_count: int,
                 cfg: HeartbeatConfig, heartbeat: int, elapsed_min: int,
                 remaining_min: int | None) -> str:
    """Compact, Discord-safe heartbeat message (under the 2000-char limit)."""
    title = f"**Lumora Replay Backtest · {cfg.report_every_minutes}m Update**"
    head = (f"Mode: {ENVIRONMENT} | Symbol: {cfg.symbol} | TF: {cfg.timeframe} | "
            f"Risk: {cfg.risk_mode} | h{cfg.horizon}")
    prog = f"Heartbeat: {heartbeat} | Elapsed: {elapsed_min}m"
    if remaining_min is not None:
        prog += f" | Remaining: {remaining_min}m"

    mods = (", ".join(f"{s} {v:+d}" for s, v in sorted(active_modifiers.items()))
            if active_modifiers else "none")

    if not scorecard:
        lines = [title, head, prog, "",
                 "No replay data yet - run scripts/run_gold_bot_replay.py first.",
                 f"Active modifiers: {mods}", "", SAFETY_LINE]
        return "\n".join(lines)[:DISCORD_CONTENT_LIMIT]

    g = scorecard.get("global") or {}
    files = scorecard.get("replay_files_count", "?")
    lines = [
        title, head, prog, "",
        (f"Replay: {files} files | {_commas(scorecard.get('rows'))} rows | "
         f"{_commas(g.get('trade_count'))} trades | {_commas(g.get('no_trade_count'))} no-trade"),
        (f"Performance: winrate {_pct(g.get('winrate'))} | "
         f"expectancy {g.get('expectancy_points')}pt | status {g.get('recommended_status')}"),
    ]

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

    buckets = scorecard.get("confidence_buckets") or {}
    bparts = [f"{b} {_pct(v.get('winrate'))}/{v.get('expectancy_points')}pt"
              for b, v in buckets.items() if (v or {}).get("trade_count")]
    if bparts:
        lines.append("Buckets: " + " · ".join(bparts[-3:]))

    learning = "replay-dominant" if not real_count else "replay+demo"
    lines.append(f"Learning: {learning} | real demo trades {real_count}")
    lines.append(f"Active modifiers: {mods}")
    lines.append("")
    lines.append(SAFETY_LINE)

    content = "\n".join(lines)
    if len(content) > DISCORD_CONTENT_LIMIT:
        content = content[:DISCORD_CONTENT_LIMIT - 18].rstrip() + "\n... (truncated)"
    return content


# ── one heartbeat ───────────────────────────────────────────────────────────────────
def run_one_heartbeat(cfg: HeartbeatConfig, *, heartbeat: int, elapsed_min: int,
                      remaining_min: int | None,
                      out_dir: Path = DEFAULT_HEARTBEAT_DIR,
                      learning_dir: Path = DEFAULT_LEARNING_DIR,
                      replay_dir: Path = DEFAULT_REPLAY_DIR,
                      now_fn: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
                      send_fn: Callable[..., dict] = send_review,
                      env: dict | None = None) -> HeartbeatResult:
    now = now_fn()
    scorecard, files, warnings = refresh_scorecard(cfg, learning_dir=learning_dir, replay_dir=replay_dir)
    active = read_active_modifiers(learning_dir)
    real_global = (scorecard or {}).get("real_global") or {}
    real_count = int(real_global.get("trade_count") or 0)

    content = build_report(scorecard=scorecard, active_modifiers=active, real_count=real_count,
                           cfg=cfg, heartbeat=heartbeat, elapsed_min=elapsed_min,
                           remaining_min=remaining_min)

    g = (scorecard or {}).get("global") or {}
    data = {
        "environment": ENVIRONMENT, "execution": EXECUTION, "broker_orders": "disabled",
        "live": "locked", "symbol": cfg.symbol, "timeframe": cfg.timeframe,
        "risk_mode": cfg.risk_mode, "horizon": cfg.horizon,
        "replay_files": (scorecard or {}).get("replay_files_count"),
        "rows": (scorecard or {}).get("rows"),
        "trades": g.get("trade_count"), "no_trade": g.get("no_trade_count"),
        "winrate": g.get("winrate"), "expectancy_points": g.get("expectancy_points"),
        "status": g.get("recommended_status"),
        "real_demo_trades": real_count, "active_modifiers": active,
        "learning_mode": "replay-dominant" if not real_count else "replay+demo",
    }

    mode = "send" if cfg.send_discord else "preview"
    sent = False
    target = None
    if cfg.send_discord:
        url = resolve_webhook() if env is None else (env.get(WEBHOOK_ENV) or "").strip() or None
        if not url:
            warnings = warnings + [
                f"--send-discord set but env {WEBHOOK_ENV} is missing - not sent (offline preview kept)"]
        else:
            result = send_fn(content, webhook_url=url, timeout=10.0)
            sent = bool(result.get("ok"))
            target = redact_webhook(url)
            if not sent:
                warnings = warnings + [f"discord send failed: {result.get('error')}"]

    res = HeartbeatResult(
        heartbeat=heartbeat, generated_at=now.isoformat(), mode=mode, sent=sent,
        target=target, content=content, data=data, warnings=list(warnings))
    _write_logs(res, out_dir, now)
    return res


# ── loop ──────────────────────────────────────────────────────────────────────────
def run_loop(cfg: HeartbeatConfig, *, out_dir: Path = DEFAULT_HEARTBEAT_DIR,
             learning_dir: Path = DEFAULT_LEARNING_DIR, replay_dir: Path = DEFAULT_REPLAY_DIR,
             now_fn: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
             sleep_fn: Callable[[int], Any] = time.sleep,
             send_fn: Callable[..., dict] = send_review) -> list[HeartbeatResult]:
    """Emit a heartbeat now, then every report interval until duration elapses.
    --once emits exactly one and returns (never sleeps)."""
    start = now_fn()
    results: list[HeartbeatResult] = []
    hb = 0
    while True:
        hb += 1
        elapsed = max(0, int((now_fn() - start).total_seconds() // 60))
        remaining = None if cfg.once else max(0, int(cfg.duration_minutes) - elapsed)
        results.append(run_one_heartbeat(
            cfg, heartbeat=hb, elapsed_min=elapsed, remaining_min=remaining,
            out_dir=out_dir, learning_dir=learning_dir, replay_dir=replay_dir,
            now_fn=now_fn, send_fn=send_fn))
        if cfg.once or elapsed >= int(cfg.duration_minutes):
            break
        sleep_fn(cfg.effective_sleep())
    return results


# ── logs ──────────────────────────────────────────────────────────────────────────
def _write_logs(res: HeartbeatResult, out_dir: Path, now: datetime) -> None:
    try:
        d = Path(out_dir)
        d.mkdir(parents=True, exist_ok=True)
        stamp = now.strftime("%Y%m%d_%H%M%S")
        named_json = d / f"heartbeat_{stamp}.json"
        latest_json = d / "heartbeat_latest.json"
        named_md = d / f"heartbeat_{stamp}.md"
        latest_md = d / "heartbeat_latest.md"
        res.paths = {"json": str(named_json), "latest_json": str(latest_json),
                     "md": str(named_md), "latest_md": str(latest_md)}
        payload = json.dumps(res.to_dict(), indent=2, default=str)
        named_json.write_text(payload, encoding="utf-8")
        latest_json.write_text(payload, encoding="utf-8")
        named_md.write_text(res.content + "\n", encoding="utf-8")
        latest_md.write_text(res.content + "\n", encoding="utf-8")
    except OSError:
        res.paths = {}
