"""Tests for live_worker_config (LM53A)."""

from services.live_worker_config import load_live_worker_config


def test_defaults():
    cfg = load_live_worker_config(env={})
    assert cfg["symbols"] == ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    assert cfg["exchange"] == "binance"
    assert cfg["timeframes"] == ["5m"]
    assert cfg["history_target"] == "supabase"
    assert cfg["history_interval"] == 10
    assert cfg["max_cells"] == 300
    assert cfg["max_walls"] == 50
    assert cfg["discord_enabled"] is False


def test_custom_env():
    env = {
        "WORKER_SYMBOLS": "HYPEUSDT",
        "WORKER_EXCHANGE": "hyperliquid",
        "WORKER_TIMEFRAMES": "1m,15m",
        "WORKER_HISTORY_TARGET": "local",
        "WORKER_HISTORY_INTERVAL": "30",
        "WORKER_MAX_CELLS": "500",
        "WORKER_MAX_WALLS": "100",
        "WORKER_DISCORD_ENABLED": "true",
    }
    cfg = load_live_worker_config(env=env)
    assert cfg["symbols"] == ["HYPEUSDT"]
    assert cfg["exchange"] == "hyperliquid"
    assert cfg["timeframes"] == ["1m", "15m"]
    assert cfg["history_interval"] == 30
    assert cfg["max_cells"] == 500
    assert cfg["max_walls"] == 100
    assert cfg["discord_enabled"] is True


def test_comma_parsing():
    cfg = load_live_worker_config(env={"WORKER_SYMBOLS": "BTC, ETH , SOL"})
    assert cfg["symbols"] == ["BTC", "ETH", "SOL"]


def test_uppercase_symbols():
    cfg = load_live_worker_config(env={"WORKER_SYMBOLS": "btcusdt, ethusdt"})
    assert cfg["symbols"] == ["BTCUSDT", "ETHUSDT"]


def test_bad_numbers_fallback():
    env = {"WORKER_HISTORY_INTERVAL": "abc", "WORKER_MAX_CELLS": "", "WORKER_MAX_WALLS": "nope"}
    cfg = load_live_worker_config(env=env)
    assert cfg["history_interval"] == 10
    assert cfg["max_cells"] == 300
    assert cfg["max_walls"] == 50


def test_empty_symbols_fallback():
    cfg = load_live_worker_config(env={"WORKER_SYMBOLS": "  , , "})
    assert cfg["symbols"] == ["BTCUSDT", "ETHUSDT", "SOLUSDT"]


def test_discord_boolean_true():
    for val in ["true", "1", "yes", "on", "TRUE", "Yes"]:
        cfg = load_live_worker_config(env={"WORKER_DISCORD_ENABLED": val})
        assert cfg["discord_enabled"] is True, f"failed for {val}"


def test_discord_boolean_false():
    for val in ["false", "0", "no", "off", "", "nah"]:
        cfg = load_live_worker_config(env={"WORKER_DISCORD_ENABLED": val})
        assert cfg["discord_enabled"] is False, f"failed for {val}"
