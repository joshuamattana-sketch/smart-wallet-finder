"""
services/worker_health.py
--------------------------
LM53D — Worker health/heartbeat helper.

Pure Python, no network, no DB, no UI. Injectable clock for determinism.

Public API:
    create_worker_health_state(config=None) -> dict
    record_worker_tick(state, symbol=None, exchange=None, ok=True, error=None, now=None)
    build_worker_heartbeat(state, now=None) -> dict
"""

from __future__ import annotations

import time

_HEALTHY_WINDOW_S = 30.0


def create_worker_health_state(config=None):
    now = time.time()
    return {
        "started_at": now,
        "last_tick_at": None,
        "total_ticks": 0,
        "ok_ticks": 0,
        "error_ticks": 0,
        "last_error": None,
        "last_error_at": None,
        "symbols_seen": set(),
        "exchanges_seen": set(),
        "config_summary": dict(config) if isinstance(config, dict) else {},
    }


def record_worker_tick(state, symbol=None, exchange=None, ok=True, error=None, now=None):
    if not isinstance(state, dict):
        return
    t = now if now is not None else time.time()
    state["last_tick_at"] = t
    state["total_ticks"] = state.get("total_ticks", 0) + 1
    if ok:
        state["ok_ticks"] = state.get("ok_ticks", 0) + 1
    else:
        state["error_ticks"] = state.get("error_ticks", 0) + 1
        state["last_error"] = str(error) if error else "unknown"
        state["last_error_at"] = t
    if symbol:
        state.setdefault("symbols_seen", set()).add(str(symbol))
    if exchange:
        state.setdefault("exchanges_seen", set()).add(str(exchange))


def build_worker_heartbeat(state, now=None):
    if not isinstance(state, dict):
        return {
            "status": "starting", "uptime_seconds": 0, "last_tick_at": None,
            "total_ticks": 0, "ok_ticks": 0, "error_ticks": 0,
            "last_error": None, "symbols_seen": [], "exchanges_seen": [],
            "config_summary": {},
        }

    t = now if now is not None else time.time()
    started = state.get("started_at") if state.get("started_at") is not None else t
    last_tick = state.get("last_tick_at")
    total = state.get("total_ticks", 0)
    error_ticks = state.get("error_ticks", 0)

    if total == 0:
        status = "starting"
    elif error_ticks > 0 and state.get("last_error_at") and (t - state["last_error_at"]) < _HEALTHY_WINDOW_S:
        status = "degraded"
    elif last_tick is not None and (t - last_tick) < _HEALTHY_WINDOW_S:
        status = "healthy"
    else:
        status = "degraded"

    return {
        "status": status,
        "uptime_seconds": round(t - started, 2),
        "last_tick_at": last_tick,
        "total_ticks": total,
        "ok_ticks": state.get("ok_ticks", 0),
        "error_ticks": error_ticks,
        "last_error": state.get("last_error"),
        "symbols_seen": sorted(state.get("symbols_seen", set())),
        "exchanges_seen": sorted(state.get("exchanges_seen", set())),
        "config_summary": state.get("config_summary", {}),
    }
