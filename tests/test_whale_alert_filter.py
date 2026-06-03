"""Tests for whale_alert_filter (LM52C)."""

from services.whale_alert_filter import should_send_whale_alert


def _evt(severity="notable", notional=300_000, confidence=0.8, **kw):
    base = {
        "source_type": "trade", "symbol": "BTCUSDT", "chain": "bitcoin",
        "exchange": "binance", "side": "buy", "wallet": "0xabc",
        "severity": severity, "notional_usd": notional, "confidence": confidence,
    }
    base.update(kw)
    return base


def test_sends_extreme():
    r = should_send_whale_alert(_evt(severity="extreme", notional=50_000, confidence=0.1))
    assert r["should_send"] is True


def test_sends_high_above_thresholds():
    r = should_send_whale_alert(_evt(severity="high", notional=600_000, confidence=0.7))
    assert r["should_send"] is True


def test_blocks_high_low_confidence():
    r = should_send_whale_alert(_evt(severity="high", notional=600_000, confidence=0.5))
    assert r["should_send"] is False


def test_sends_notable_above_thresholds():
    r = should_send_whale_alert(_evt(severity="notable", notional=300_000, confidence=0.8))
    assert r["should_send"] is True


def test_blocks_info_by_default():
    r = should_send_whale_alert(_evt(severity="info", notional=500_000, confidence=0.9))
    assert r["should_send"] is False


def test_allows_info_if_option():
    r = should_send_whale_alert(
        _evt(severity="info", notional=500_000, confidence=0.9),
        {"send_info": True},
    )
    assert r["should_send"] is True


def test_allowed_symbols():
    r = should_send_whale_alert(_evt(symbol="ETHUSDT"), {"allowed_symbols": ["BTCUSDT"]})
    assert r["should_send"] is False


def test_blocked_symbols():
    r = should_send_whale_alert(_evt(symbol="BTCUSDT"), {"blocked_symbols": ["BTCUSDT"]})
    assert r["should_send"] is False


def test_allowed_chains():
    r = should_send_whale_alert(_evt(chain="ethereum"), {"allowed_chains": ["bitcoin"]})
    assert r["should_send"] is False


def test_blocked_chains():
    r = should_send_whale_alert(_evt(chain="bitcoin"), {"blocked_chains": ["bitcoin"]})
    assert r["should_send"] is False


def test_deterministic_cooldown_key():
    e = _evt()
    r1 = should_send_whale_alert(e)
    r2 = should_send_whale_alert(e)
    assert r1["cooldown_key"] == r2["cooldown_key"]
    assert len(r1["cooldown_key"]) == 12


def test_missing_input_safe():
    r = should_send_whale_alert(None)
    assert r["should_send"] is False
    r = should_send_whale_alert({})
    assert r["should_send"] is False
    r = should_send_whale_alert({"severity": "extreme", "symbol": "X"})
    assert r["should_send"] is True
