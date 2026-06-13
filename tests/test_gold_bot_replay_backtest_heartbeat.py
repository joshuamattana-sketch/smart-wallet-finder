"""
tests/test_gold_bot_replay_backtest_heartbeat.py
-------------------------------------------------
LM98A - Replay/backtest heartbeat. Offline; Discord + clock + sleep are injected.
No network, no MT5, no real replay data needed (a fixture scorecard drives the
message tests; the run path uses empty tmp dirs).
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from services.gold_bot_replay_backtest_heartbeat import (
    DEFAULT_HEARTBEAT_DIR,
    SAFETY_LINE,
    WEBHOOK_ENV,
    HeartbeatConfig,
    build_report,
    run_loop,
    run_one_heartbeat,
)

NOW = datetime(2026, 6, 13, 12, 0, 0, tzinfo=timezone.utc)
_REPO = Path(__file__).resolve().parent.parent

FIXTURE_SCORECARD = {
    "rows": 17900,
    "horizon": 15,
    "replay_files_count": 37,
    "global": {"trade_count": 11926, "no_trade_count": 5974, "winrate": 0.27,
               "expectancy_points": -45.8, "recommended_status": "avoid"},
    "top_setups_by_expectancy": [
        {"setup": "liquidity_sweep_reclaim", "expectancy_points": 14.9, "winrate": 0.31, "trade_count": 746},
        {"setup": "breakout_retest", "expectancy_points": -26.2, "winrate": 0.28, "trade_count": 954},
        {"setup": "momentum", "expectancy_points": -49.0, "winrate": 0.26, "trade_count": 4336},
    ],
    "weak_or_avoid_setups": ["breakout_retest", "fvg_retest", "liquidity_sweep_reclaim", "momentum"],
    "confidence_buckets": {
        "70-79": {"trade_count": 2226, "winrate": 0.28, "expectancy_points": -33.0},
        "80-100": {"trade_count": 4767, "winrate": 0.26, "expectancy_points": -3.4},
    },
    "real_global": {"trade_count": 0},
}
ACTIVE = {"breakout_retest": -8, "fvg_retest": -8, "momentum": -8}


def _boom_send(*a, **k):
    raise AssertionError("Discord send called when it must not be")


# ── report content ──────────────────────────────────────────────────────────────────
def test_report_has_replay_only_safety_and_framing():
    msg = build_report(scorecard=FIXTURE_SCORECARD, active_modifiers=ACTIVE, real_count=0,
                       cfg=HeartbeatConfig(), heartbeat=2, elapsed_min=15, remaining_min=45)
    assert "Lumora Replay Backtest" in msg
    assert "replay/offline" in msg
    assert SAFETY_LINE in msg
    assert "No MT5 orders, no demo session, live locked." in msg


def test_report_has_replay_stats_from_fixture():
    msg = build_report(scorecard=FIXTURE_SCORECARD, active_modifiers=ACTIVE, real_count=0,
                       cfg=HeartbeatConfig(), heartbeat=2, elapsed_min=15, remaining_min=45)
    assert "37 files" in msg
    assert "11,926 trades" in msg and "5,974 no-trade" in msg
    assert "winrate 27%" in msg
    assert "expectancy -45.8pt" in msg and "status avoid" in msg
    assert "liquidity_sweep_reclaim +14.9pt / 746 trades" in msg
    assert "momentum -49.0pt / 4,336 trades" in msg


def test_report_shows_active_modifiers():
    msg = build_report(scorecard=FIXTURE_SCORECARD, active_modifiers=ACTIVE, real_count=0,
                       cfg=HeartbeatConfig(), heartbeat=1, elapsed_min=0, remaining_min=60)
    assert "Active modifiers: breakout_retest -8, fvg_retest -8, momentum -8" in msg


def test_report_zero_real_demo_is_replay_dominant():
    msg = build_report(scorecard=FIXTURE_SCORECARD, active_modifiers=ACTIVE, real_count=0,
                       cfg=HeartbeatConfig(), heartbeat=1, elapsed_min=0, remaining_min=60)
    assert "replay-dominant" in msg and "real demo trades 0" in msg


def test_report_with_real_demo_shows_blend():
    msg = build_report(scorecard=FIXTURE_SCORECARD, active_modifiers=ACTIVE, real_count=5,
                       cfg=HeartbeatConfig(), heartbeat=1, elapsed_min=0, remaining_min=60)
    assert "replay+demo" in msg and "real demo trades 5" in msg


def test_report_no_replay_data_branch():
    msg = build_report(scorecard=None, active_modifiers=ACTIVE, real_count=0,
                       cfg=HeartbeatConfig(), heartbeat=1, elapsed_min=0, remaining_min=60)
    assert "No replay data yet" in msg and SAFETY_LINE in msg


# ── send gating (clock/dirs injected; empty tmp -> no real replay) ──────────────────
def _one(tmp_path, cfg, *, env=None, send_fn=_boom_send):
    return run_one_heartbeat(
        cfg, heartbeat=1, elapsed_min=0, remaining_min=None,
        out_dir=tmp_path / "hb", learning_dir=tmp_path / "learn", replay_dir=tmp_path / "replay",
        now_fn=lambda: NOW, send_fn=send_fn, env=env)


def test_default_preview_does_not_send(tmp_path):
    res = _one(tmp_path, HeartbeatConfig(once=True))     # send_discord False
    assert res.mode == "preview" and res.sent is False
    assert "replay/offline" in res.content and "live locked" in res.content


def test_send_without_env_fails_safely(tmp_path):
    res = _one(tmp_path, HeartbeatConfig(once=True, send_discord=True), env={})
    assert res.sent is False
    assert any(WEBHOOK_ENV in w for w in res.warnings)   # clear message, no exception


def test_send_with_env_calls_sender_and_redacts(tmp_path):
    sent_payloads = []

    def fake_send(content, *, webhook_url=None, timeout=10.0):
        sent_payloads.append((content, webhook_url))
        return {"ok": True, "status_code": 204, "error": None}

    env = {WEBHOOK_ENV: "https://discord.com/api/webhooks/123/TOPSECRET"}
    res = _one(tmp_path, HeartbeatConfig(once=True, send_discord=True), env=env, send_fn=fake_send)
    assert res.sent is True
    assert "TOPSECRET" not in (res.target or "") and "REDACTED" in (res.target or "")
    # the secret never lands in the persisted log
    import json
    blob = json.dumps(res.to_dict())
    assert "TOPSECRET" not in blob


def test_generated_paths_under_replay_heartbeat(tmp_path):
    res = _one(tmp_path, HeartbeatConfig(once=True))
    assert Path(res.paths["latest_json"]).exists()
    assert Path(res.paths["latest_md"]).exists()
    assert Path(res.paths["json"]).name.startswith("heartbeat_")
    # the production default dir is under data/gold_bot/replay_heartbeat
    assert str(DEFAULT_HEARTBEAT_DIR).replace("\\", "/").endswith("data/gold_bot/replay_heartbeat")


# ── loop control ────────────────────────────────────────────────────────────────────
def test_once_emits_one_and_never_sleeps(tmp_path):
    def boom_sleep(_):
        raise AssertionError("slept on --once")
    res = run_loop(HeartbeatConfig(once=True), out_dir=tmp_path / "hb",
                   learning_dir=tmp_path / "l", replay_dir=tmp_path / "r",
                   now_fn=lambda: NOW, sleep_fn=boom_sleep, send_fn=_boom_send)
    assert len(res) == 1 and res[0].sent is False


def test_zero_duration_stops_after_one_no_sleep(tmp_path):
    def boom_sleep(_):
        raise AssertionError("slept when duration already elapsed")
    res = run_loop(HeartbeatConfig(once=False, duration_minutes=0), out_dir=tmp_path / "hb",
                   learning_dir=tmp_path / "l", replay_dir=tmp_path / "r",
                   now_fn=lambda: NOW, sleep_fn=boom_sleep, send_fn=_boom_send)
    assert len(res) == 1


# ── source safety ───────────────────────────────────────────────────────────────────
def test_source_has_no_orders_demo_or_live():
    svc = (_REPO / "services" / "gold_bot_replay_backtest_heartbeat.py").read_text(encoding="utf-8")
    cli = (_REPO / "scripts" / "run_gold_bot_replay_backtest_heartbeat.py").read_text(encoding="utf-8")
    for blob in (svc, cli):
        for forbidden in ("order_send", "send_demo_order", "confirm-demo-session",
                          "--auto-execute", "--allow-live-trading", "import MetaTrader5"):
            assert forbidden not in blob, f"heartbeat must not contain {forbidden}"
        assert "heatmap" not in blob.lower()


def test_gitignore_has_replay_heartbeat():
    gi = (_REPO / ".gitignore").read_text(encoding="utf-8")
    assert "data/gold_bot/replay_heartbeat/*.json" in gi
    assert "data/gold_bot/replay_heartbeat/*.md" in gi
