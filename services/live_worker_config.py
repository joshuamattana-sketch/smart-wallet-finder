"""
services/live_worker_config.py
-------------------------------
LM53A — Config helper for the existing heatmap worker.

Reads env vars (from a dict or os.environ) and returns a validated
config dict. NO network, NO UI, NO API.

Public entry:
    load_live_worker_config(env=None) -> dict
"""

from __future__ import annotations

import os

_TRUTHY = frozenset({"true", "1", "yes", "on"})

_DEFAULTS = {
    "WORKER_SYMBOLS": "BTCUSDT,ETHUSDT,SOLUSDT",
    "WORKER_EXCHANGE": "binance",
    "WORKER_TIMEFRAMES": "5m",
    "WORKER_HISTORY_TARGET": "supabase",
    "WORKER_HISTORY_INTERVAL": "10",
    "WORKER_MAX_CELLS": "300",
    "WORKER_MAX_WALLS": "50",
    "WORKER_DISCORD_ENABLED": "false",
}


def _get(env, key):
    val = env.get(key, "")
    if val is None or str(val).strip() == "":
        return _DEFAULTS[key]
    return str(val).strip()


def _parse_int(raw, default):
    try:
        return int(raw)
    except (ValueError, TypeError):
        return default


def _parse_csv_upper(raw):
    parts = [s.strip().upper() for s in raw.split(",") if s.strip()]
    return parts


def load_live_worker_config(env=None):
    """Load and validate heatmap worker config from env vars."""
    src = env if env is not None else os.environ

    symbols = _parse_csv_upper(_get(src, "WORKER_SYMBOLS"))
    if not symbols:
        symbols = _parse_csv_upper(_DEFAULTS["WORKER_SYMBOLS"])

    timeframes = [s.strip() for s in _get(src, "WORKER_TIMEFRAMES").split(",") if s.strip()]

    return {
        "symbols": symbols,
        "exchange": _get(src, "WORKER_EXCHANGE"),
        "timeframes": timeframes,
        "history_target": _get(src, "WORKER_HISTORY_TARGET"),
        "history_interval": _parse_int(_get(src, "WORKER_HISTORY_INTERVAL"), 10),
        "max_cells": _parse_int(_get(src, "WORKER_MAX_CELLS"), 300),
        "max_walls": _parse_int(_get(src, "WORKER_MAX_WALLS"), 50),
        "discord_enabled": _get(src, "WORKER_DISCORD_ENABLED").lower() in _TRUTHY,
    }
