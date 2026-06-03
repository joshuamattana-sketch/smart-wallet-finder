"""
services/local_end_to_end_status.py
------------------------------------
LM58 — Local end-to-end status helper.

Checks that the main local building blocks are wired and usable.
NO UI, NO API, NO DB, NO network.

Public entry:
    run_local_end_to_end_status(options=None) -> dict
"""

from __future__ import annotations


def _check(name, fn):
    try:
        details = fn()
        return {"ok": True, "name": name, "details": details, "error": None}
    except Exception as exc:
        return {"ok": False, "name": name, "details": None, "error": str(exc)}


def _check_worker_config():
    from services.live_worker_config import load_live_worker_config
    cfg = load_live_worker_config(env={})
    assert isinstance(cfg, dict)
    assert len(cfg["symbols"]) > 0
    return {"symbols": cfg["symbols"], "exchange": cfg["exchange"]}


def _check_signal_pipeline():
    from services.local_signal_pipeline import run_local_signal_pipeline
    wall = {
        "side": "bid", "priceMin": 67000, "priceMax": 67200,
        "centerPrice": 67100, "strengthScore": 80.0,
        "totalUsd": 1_000_000, "maxIntensity": 90, "bucketCount": 5,
    }
    result = run_local_signal_pipeline([wall], [wall])
    assert isinstance(result, dict)
    assert "events" in result
    return {"keys": list(result.keys())}


def _check_discord_signal_smoke():
    from services.local_discord_alert_smoke import run_local_discord_alert_smoke
    signal = {
        "symbol": "BTCUSDT", "exchange": "binance_spot", "timeframe": "5m",
        "setup_type": "long_absorption", "direction": "long",
        "signal_level": "strong_setup", "score": 85.0, "confidence": 0.9,
        "status": "active",
    }
    result = run_local_discord_alert_smoke(signal)
    assert isinstance(result, dict)
    assert "should_send" in result
    return {"should_send": result["should_send"]}


def _check_whale_discord_smoke():
    from services.local_whale_discord_smoke import run_local_whale_discord_smoke
    whale = {
        "source_type": "trade", "symbol": "BTCUSDT", "severity": "extreme",
        "notional_usd": 2_000_000, "confidence": 0.8, "exchange": "binance",
    }
    result = run_local_whale_discord_smoke(whale)
    assert isinstance(result, dict)
    assert "should_send" in result
    return {"should_send": result["should_send"]}


_CHECKS = [
    ("worker_config", _check_worker_config),
    ("signal_pipeline", _check_signal_pipeline),
    ("discord_signal_smoke", _check_discord_signal_smoke),
    ("whale_discord_smoke", _check_whale_discord_smoke),
]


def run_local_end_to_end_status(options=None):
    """Run all local status checks and return overall status."""
    checks = [_check(name, fn) for name, fn in _CHECKS]
    ok_count = sum(1 for c in checks if c["ok"])
    fail_count = len(checks) - ok_count
    status = "ready" if fail_count == 0 else "degraded"

    return {
        "status": status,
        "checks": checks,
        "summary": {
            "total": len(checks),
            "ok": ok_count,
            "failed": fail_count,
        },
    }
