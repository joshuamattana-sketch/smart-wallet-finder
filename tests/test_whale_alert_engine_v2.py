"""Tests for detect_whale_events (v2 minimal whale alert engine)."""

import pytest
from services.whale_alert_engine import detect_whale_events

EXPECTED_FIELDS = {
    "whale_event_id", "event_ts", "source_type", "symbol", "chain",
    "exchange", "side", "amount", "price", "notional_usd", "wallet",
    "tx_hash", "severity", "confidence", "reason", "metadata",
}


def _trade(notional=200_000, symbol="BTCUSDT", **kw):
    base = {
        "source_type": "trade",
        "symbol": symbol,
        "chain": "",
        "exchange": "binance",
        "side": "buy",
        "amount": 3.0,
        "price": 67000.0,
        "notional_usd": notional,
        "wallet": "0xabc",
        "tx_hash": "hash123",
        "event_ts": "2026-06-04T00:00:00Z",
    }
    base.update(kw)
    return base


def _transfer(notional=200_000, symbol="ETH", **kw):
    base = {
        "source_type": "transfer",
        "symbol": symbol,
        "chain": "ethereum",
        "exchange": "",
        "side": "",
        "amount": 100.0,
        "price": 3500.0,
        "notional_usd": notional,
        "wallet": "0xdef",
        "tx_hash": "txhash456",
        "event_ts": "2026-06-04T00:01:00Z",
    }
    base.update(kw)
    return base


def test_detects_large_trade():
    results = detect_whale_events([_trade(notional=200_000)])
    assert len(results) == 1
    assert results[0]["source_type"] == "trade"
    assert results[0]["symbol"] == "BTCUSDT"


def test_detects_large_transfer():
    results = detect_whale_events([_transfer(notional=200_000)])
    assert len(results) == 1
    assert results[0]["source_type"] == "transfer"


def test_ignores_small_item():
    results = detect_whale_events([_trade(notional=50_000)])
    assert len(results) == 0


def test_severity_notable():
    results = detect_whale_events([_trade(notional=200_000)])
    assert results[0]["severity"] == "notable"


def test_severity_high():
    results = detect_whale_events([_trade(notional=600_000)])
    assert results[0]["severity"] == "high"


def test_severity_extreme():
    results = detect_whale_events([_trade(notional=2_000_000)])
    assert results[0]["severity"] == "extreme"


def test_allowed_symbols():
    items = [_trade(symbol="BTCUSDT"), _trade(symbol="ETHUSDT")]
    results = detect_whale_events(items, {"allowed_symbols": ["BTCUSDT"]})
    assert len(results) == 1
    assert results[0]["symbol"] == "BTCUSDT"


def test_blocked_symbols():
    items = [_trade(symbol="BTCUSDT"), _trade(symbol="ETHUSDT")]
    results = detect_whale_events(items, {"blocked_symbols": ["BTCUSDT"]})
    assert len(results) == 1
    assert results[0]["symbol"] == "ETHUSDT"


def test_deterministic_whale_event_id():
    item = _trade(notional=300_000)
    r1 = detect_whale_events([item])
    r2 = detect_whale_events([item])
    assert r1[0]["whale_event_id"] == r2[0]["whale_event_id"]
    assert len(r1[0]["whale_event_id"]) == 16


def test_missing_input_safe():
    results = detect_whale_events([{}])
    assert results == []

    results = detect_whale_events([{"notional_usd": 200_000}])
    assert len(results) == 1

    assert detect_whale_events(None) == []
    assert detect_whale_events([]) == []


def test_deterministic_output_shape():
    results = detect_whale_events([_trade(), _transfer()])
    assert len(results) == 2
    for r in results:
        assert set(r.keys()) == EXPECTED_FIELDS
        assert isinstance(r["whale_event_id"], str)
        assert isinstance(r["notional_usd"], float)
        assert isinstance(r["metadata"], dict)
