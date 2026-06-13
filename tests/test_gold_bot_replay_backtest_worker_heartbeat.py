"""
tests/test_gold_bot_replay_backtest_worker_heartbeat.py
--------------------------------------------------------
LM98B - Replay/backtest worker. Offline; the replay job runner, clock, sleep and
Discord sender are all injected. No real replay, no network, no MT5. A fixture
scorecard + before/after stats drive the report; the run path uses empty tmp dirs.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from services.gold_bot_replay_backtest_worker_heartbeat import (
    DEFAULT_WORKER_DIR,
    WORKER_SAFETY_LINE,
    WEBHOOK_ENV,
    ReplayJob,
    WorkerConfig,
    build_plan,
    build_worker_report,
    format_plan,
    run_loop,
    run_one_cycle,
)

NOW = datetime(2026, 6, 13, 12, 0, 0, tzinfo=timezone.utc)
_REPO = Path(__file__).resolve().parent.parent

SCORECARD = {
    "rows": 18900, "horizon": 15, "replay_files_count": 38,
    "global": {"trade_count": 12540, "no_trade_count": 6360, "winrate": 0.27,
               "expectancy_points": -43.2, "recommended_status": "avoid"},
    "top_setups_by_expectancy": [
        {"setup": "liquidity_sweep_reclaim", "expectancy_points": 15.4, "trade_count": 790},
        {"setup": "breakout_retest", "expectancy_points": -24.9, "trade_count": 1020},
        {"setup": "momentum", "expectancy_points": -48.1, "trade_count": 4500},
    ],
    "weak_or_avoid_setups": ["breakout_retest", "fvg_retest", "momentum"],
    "real_global": {"trade_count": 0},
}
BEFORE = {"files": 36, "rows": 17700, "trades": 11776, "no_trade": 5924}
AFTER = {"files": 38, "rows": 18900, "trades": 12540, "no_trade": 6360}
ACTIVE = {"breakout_retest": -8, "fvg_retest": -8, "momentum": -8}
JOB = ReplayJob("M1", "scalp", 15, 1000)


def _boom_send(*a, **k):
    raise AssertionError("Discord send called when it must not be")


def _ok_job(job):
    return True, None


# ── plan ──────────────────────────────────────────────────────────────────────────
def test_build_plan_combinations():
    cfg = WorkerConfig(timeframes=("M1", "M5"), risk_modes=("balanced", "scalp"),
                       horizons=(15, 30), max_bars=1000)
    plan = build_plan(cfg)
    assert len(plan) == 8
    assert any(j.label == "M1 / balanced / h15 / 1000 bars" for j in plan)
    assert "8 jobs" in format_plan(plan)


def test_dry_run_plan_runs_no_jobs(tmp_path):
    def boom_job(job):
        raise AssertionError("job ran during dry-run-plan")
    res = run_loop(WorkerConfig(dry_run_plan=True), out_dir=tmp_path / "w",
                   learning_dir=tmp_path / "l", replay_dir=tmp_path / "r",
                   now_fn=lambda: NOW, sleep_fn=lambda _: None,
                   run_job_fn=boom_job, send_fn=_boom_send)
    assert res == []


# ── report ──────────────────────────────────────────────────────────────────────
def test_report_has_worker_framing_and_growth():
    msg = build_worker_report(scorecard=SCORECARD, before=BEFORE, after=AFTER,
                              active_modifiers=ACTIVE, real_count=0, cfg=WorkerConfig(),
                              job=JOB, cycle=3, elapsed_min=30, remaining_min=30, job_ok=True)
    assert "Lumora Replay Worker" in msg
    assert "replay/offline worker" in msg
    assert "Current job: M1 / scalp / h15 / 1000 bars" in msg
    assert "Replay growth:" in msg
    assert "Files 36 -> 38 (+2)" in msg
    assert "Rows 17,700 -> 18,900 (+1,200)" in msg
    assert "Trades 11,776 -> 12,540 (+764)" in msg
    assert "No-trade 5,924 -> 6,360 (+436)" in msg


def test_report_has_performance_modifiers_and_safety():
    msg = build_worker_report(scorecard=SCORECARD, before=BEFORE, after=AFTER,
                              active_modifiers=ACTIVE, real_count=0, cfg=WorkerConfig(),
                              job=JOB, cycle=1, elapsed_min=0, remaining_min=60, job_ok=True)
    assert "Winrate 27% | Expectancy -43.2pt | Status avoid" in msg
    assert "liquidity_sweep_reclaim +15.4pt / 790 trades" in msg
    assert "Active modifiers: breakout_retest -8, fvg_retest -8, momentum -8" in msg
    assert "replay-dominant" in msg and "real demo trades 0" in msg
    assert WORKER_SAFETY_LINE in msg
    assert "No MT5 orders, no demo session, live locked." in msg


# ── cycle / loop (injected job runner; empty tmp -> scorecard None) ─────────────────
def _cycle(tmp_path, cfg, *, env=None, send_fn=_boom_send, run_job_fn=_ok_job):
    return run_one_cycle(cfg, job=JOB, cycle=1, elapsed_min=0, remaining_min=None,
                         before_stats=BEFORE, out_dir=tmp_path / "w",
                         learning_dir=tmp_path / "l", replay_dir=tmp_path / "r",
                         now_fn=lambda: NOW, run_job_fn=run_job_fn, send_fn=send_fn, env=env)


def test_once_runs_one_job_and_one_heartbeat(tmp_path):
    calls = []

    def count_job(job):
        calls.append(job.label)
        return True, None

    def boom_sleep(_):
        raise AssertionError("slept on --once")

    cfg = WorkerConfig(once=True, timeframes=("M1",), risk_modes=("scalp",), horizons=(15,))
    res = run_loop(cfg, out_dir=tmp_path / "w", learning_dir=tmp_path / "l", replay_dir=tmp_path / "r",
                   now_fn=lambda: NOW, sleep_fn=boom_sleep, run_job_fn=count_job, send_fn=_boom_send)
    assert len(res) == 1 and len(calls) == 1
    assert res[0].sent is False and res[0].mode == "preview"


def test_default_does_not_send(tmp_path):
    res = _cycle(tmp_path, WorkerConfig(once=True))   # send_discord False
    assert res.mode == "preview" and res.sent is False
    assert "replay/offline worker" in res.content and "live locked" in res.content


def test_send_without_env_fails_safely(tmp_path):
    res = _cycle(tmp_path, WorkerConfig(once=True, send_discord=True), env={})
    assert res.sent is False
    assert any(WEBHOOK_ENV in w for w in res.warnings)


def test_invalid_webhook_fails_safely(tmp_path):
    res = _cycle(tmp_path, WorkerConfig(once=True, send_discord=True),
                 env={WEBHOOK_ENV: "http://evil.example.com/x"})   # not a discord webhook
    assert res.sent is False
    assert any("valid Discord webhook" in w for w in res.warnings)


def test_send_with_valid_env_redacts(tmp_path):
    payloads = []

    def fake_send(content, *, webhook_url=None, timeout=10.0):
        payloads.append(webhook_url)
        return {"ok": True, "status_code": 204, "error": None}

    env = {WEBHOOK_ENV: "https://discord.com/api/webhooks/123/TOPSECRET"}
    res = _cycle(tmp_path, WorkerConfig(once=True, send_discord=True), env=env, send_fn=fake_send)
    assert res.sent is True
    assert "TOPSECRET" not in (res.target or "") and "REDACTED" in (res.target or "")
    import json
    assert "TOPSECRET" not in json.dumps(res.to_dict())


def test_artifacts_under_replay_worker(tmp_path):
    res = _cycle(tmp_path, WorkerConfig(once=True))
    assert Path(res.paths["latest_json"]).exists()
    assert Path(res.paths["events"]).exists()           # worker_events.jsonl
    assert Path(res.paths["json"]).name.startswith("worker_")
    assert str(DEFAULT_WORKER_DIR).replace("\\", "/").endswith("data/gold_bot/replay_worker")


# ── source safety ───────────────────────────────────────────────────────────────────
def test_source_no_orders_no_shell_no_live():
    svc = (_REPO / "services" / "gold_bot_replay_backtest_worker_heartbeat.py").read_text(encoding="utf-8")
    cli = (_REPO / "scripts" / "run_gold_bot_replay_backtest_worker_heartbeat.py").read_text(encoding="utf-8")
    for blob in (svc, cli):
        for forbidden in ("order_send", "send_demo_order", "confirm-demo-session",
                          "--allow-live-trading", "import MetaTrader5", "shell=True", "import subprocess"):
            assert forbidden not in blob, f"worker must not contain {forbidden}"
        assert "heatmap" not in blob.lower()


def test_gitignore_has_replay_worker():
    gi = (_REPO / ".gitignore").read_text(encoding="utf-8")
    assert "data/gold_bot/replay_worker/*.json" in gi
    assert "data/gold_bot/replay_worker/*.jsonl" in gi
    assert "data/gold_bot/replay_worker/*.md" in gi
