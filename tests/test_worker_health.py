"""Tests for worker_health (LM53D)."""

from services.worker_health import (
    create_worker_health_state,
    record_worker_tick,
    build_worker_heartbeat,
)


def test_initial_state():
    s = create_worker_health_state({"symbols": ["BTC"]})
    assert s["total_ticks"] == 0
    assert s["ok_ticks"] == 0
    assert s["error_ticks"] == 0
    assert s["last_tick_at"] is None
    assert s["last_error"] is None
    assert s["symbols_seen"] == set()
    assert s["config_summary"] == {"symbols": ["BTC"]}


def test_record_ok_tick():
    s = create_worker_health_state()
    record_worker_tick(s, symbol="BTCUSDT", ok=True, now=100.0)
    assert s["total_ticks"] == 1
    assert s["ok_ticks"] == 1
    assert s["error_ticks"] == 0
    assert s["last_tick_at"] == 100.0


def test_record_error_tick():
    s = create_worker_health_state()
    record_worker_tick(s, ok=False, error="timeout", now=200.0)
    assert s["total_ticks"] == 1
    assert s["ok_ticks"] == 0
    assert s["error_ticks"] == 1
    assert s["last_error"] == "timeout"


def test_symbols_exchanges_tracked():
    s = create_worker_health_state()
    record_worker_tick(s, symbol="BTCUSDT", exchange="binance", now=1.0)
    record_worker_tick(s, symbol="ETHUSDT", exchange="binance", now=2.0)
    record_worker_tick(s, symbol="BTCUSDT", exchange="hyperliquid", now=3.0)
    assert s["symbols_seen"] == {"BTCUSDT", "ETHUSDT"}
    assert s["exchanges_seen"] == {"binance", "hyperliquid"}


def test_heartbeat_starting():
    s = create_worker_health_state()
    s["started_at"] = 0.0
    hb = build_worker_heartbeat(s, now=5.0)
    assert hb["status"] == "starting"
    assert hb["uptime_seconds"] == 5.0
    assert hb["total_ticks"] == 0


def test_heartbeat_healthy():
    s = create_worker_health_state()
    s["started_at"] = 0.0
    record_worker_tick(s, symbol="BTCUSDT", ok=True, now=10.0)
    hb = build_worker_heartbeat(s, now=15.0)
    assert hb["status"] == "healthy"
    assert hb["total_ticks"] == 1
    assert hb["symbols_seen"] == ["BTCUSDT"]


def test_heartbeat_degraded():
    s = create_worker_health_state()
    s["started_at"] = 0.0
    record_worker_tick(s, ok=False, error="ws disconnect", now=10.0)
    hb = build_worker_heartbeat(s, now=15.0)
    assert hb["status"] == "degraded"
    assert hb["last_error"] == "ws disconnect"


def test_deterministic_now():
    s = create_worker_health_state()
    s["started_at"] = 100.0
    record_worker_tick(s, ok=True, now=110.0)
    hb1 = build_worker_heartbeat(s, now=120.0)
    hb2 = build_worker_heartbeat(s, now=120.0)
    assert hb1 == hb2
    assert hb1["uptime_seconds"] == 20.0


def test_missing_input_safe():
    hb = build_worker_heartbeat(None)
    assert hb["status"] == "starting"

    record_worker_tick(None)  # should not raise

    s = create_worker_health_state(None)
    assert s["config_summary"] == {}
