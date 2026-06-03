"""Tests for whale_discord_formatter (LM52B)."""

import pytest
from services.whale_discord_formatter import format_whale_discord_alert


def _trade(**kw):
    base = {
        "source_type": "trade",
        "symbol": "BTCUSDT",
        "chain": "",
        "exchange": "binance",
        "side": "buy",
        "amount": 3.0,
        "price": 67000.0,
        "notional_usd": 200_000,
        "wallet": "0xabcdef123456",
        "tx_hash": "hash1234567890ab",
        "severity": "notable",
        "confidence": 0.8,
        "reason": "trade of BTCUSDT worth $200,000",
    }
    base.update(kw)
    return base


def _transfer(**kw):
    base = {
        "source_type": "transfer",
        "symbol": "ETH",
        "chain": "ethereum",
        "exchange": "",
        "side": "",
        "amount": 100.0,
        "price": 3500.0,
        "notional_usd": 350_000,
        "wallet": "0xdef456789012",
        "tx_hash": "txhash456789abcd",
        "severity": "notable",
        "confidence": 0.8,
        "reason": "transfer of ETH worth $350,000",
    }
    base.update(kw)
    return base


def test_large_trade_alert():
    result = format_whale_discord_alert(_trade())
    assert result is not None
    assert "content" in result
    assert "embeds" in result
    assert "BTCUSDT" in result["content"]
    embed = result["embeds"][0]
    assert "BTCUSDT" in embed["title"]
    assert embed["footer"]["text"]


def test_large_transfer_alert():
    result = format_whale_discord_alert(_transfer())
    assert result is not None
    assert "ETH" in result["content"]
    embed = result["embeds"][0]
    assert "Transfer" in embed["title"]
    field_names = [f["name"] for f in embed["fields"]]
    assert "Chain" in field_names


def test_extreme_severity_alert():
    result = format_whale_discord_alert(_trade(severity="extreme", notional_usd=2_000_000))
    embed = result["embeds"][0]
    assert embed["color"] == 0xEF4444
    assert "EXTREME" in embed["footer"]["text"]


def test_missing_input_safe():
    assert format_whale_discord_alert(None) is None
    assert format_whale_discord_alert("bad") is None
    assert format_whale_discord_alert({}) is None
    assert format_whale_discord_alert({"symbol": ""}) is None

    result = format_whale_discord_alert({"symbol": "BTC", "notional_usd": 100_000})
    assert result is not None
    assert "BTC" in result["content"]


def test_deterministic_output_shape():
    result = format_whale_discord_alert(_trade())
    assert set(result.keys()) == {"content", "embeds"}
    assert isinstance(result["content"], str)
    assert isinstance(result["embeds"], list)
    assert len(result["embeds"]) == 1
    embed = result["embeds"][0]
    assert "title" in embed
    assert "description" in embed
    assert "fields" in embed
    assert "footer" in embed
    assert isinstance(embed["fields"], list)
    assert all("name" in f and "value" in f for f in embed["fields"])


def test_reason_included():
    reason = "trade of BTCUSDT worth $200,000"
    result = format_whale_discord_alert(_trade(reason=reason))
    assert result["embeds"][0]["description"] == reason
