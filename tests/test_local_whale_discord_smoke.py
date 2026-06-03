"""Tests for local_whale_discord_smoke (LM57)."""

from services.local_whale_discord_smoke import run_local_whale_discord_smoke


def _whale(severity="extreme", notional=2_000_000, confidence=0.8, **kw):
    base = {
        "source_type": "trade",
        "symbol": "BTCUSDT",
        "chain": "",
        "exchange": "binance",
        "side": "buy",
        "amount": 30.0,
        "price": 67000.0,
        "notional_usd": notional,
        "wallet": "0xabc123def456",
        "tx_hash": "hash789abcdef012",
        "severity": severity,
        "confidence": confidence,
        "reason": f"trade of BTCUSDT worth ${notional:,}",
    }
    base.update(kw)
    return base


def test_extreme_whale_builds_payload():
    result = run_local_whale_discord_smoke(_whale(severity="extreme"))
    assert result["should_send"] is True
    assert result["payload"] is not None
    assert "content" in result["payload"]
    assert "embeds" in result["payload"]


def test_info_whale_blocked_by_default():
    result = run_local_whale_discord_smoke(_whale(severity="info", notional=50_000))
    assert result["should_send"] is False
    assert result["payload"] is None
    assert result["summary"]["filtered"] == 1


def test_send_false_does_not_call_webhook():
    calls = []
    def _spy(*a, **k):
        calls.append(1)
        return {"ok": True}
    result = run_local_whale_discord_smoke(
        _whale(), {"send": False}, sender=_spy,
    )
    assert result["should_send"] is True
    assert len(calls) == 0
    assert result["send_result"] is None


def test_send_true_calls_mocked_sender():
    calls = []
    def _mock(payload, webhook_url=None, **k):
        calls.append({"payload": payload, "url": webhook_url})
        return {"ok": True, "status": 200}
    result = run_local_whale_discord_smoke(
        _whale(),
        {"send": True, "webhook_url": "https://discord.test/hook"},
        sender=_mock,
    )
    assert result["should_send"] is True
    assert len(calls) == 1
    assert calls[0]["url"] == "https://discord.test/hook"
    assert result["send_result"]["ok"] is True
    assert result["summary"]["sent"] == 1


def test_missing_input_safe():
    r = run_local_whale_discord_smoke(None)
    assert r["should_send"] is False
    assert r["filter_reason"] == "invalid input"

    r2 = run_local_whale_discord_smoke({})
    assert r2["should_send"] is False

    r3 = run_local_whale_discord_smoke("bad")
    assert r3["should_send"] is False


def test_summary_counts_correct():
    r_blocked = run_local_whale_discord_smoke(_whale(severity="info", notional=50_000))
    assert r_blocked["summary"]["filtered"] == 1
    assert r_blocked["summary"]["formatted"] == 0
    assert r_blocked["summary"]["sent"] == 0

    r_fmt = run_local_whale_discord_smoke(_whale())
    assert r_fmt["summary"]["formatted"] == 1
    assert r_fmt["summary"]["sent"] == 0

    def _ok(p, **k):
        return {"ok": True}
    r_sent = run_local_whale_discord_smoke(
        _whale(), {"send": True}, sender=_ok,
    )
    assert r_sent["summary"]["sent"] == 1
    assert r_sent["summary"]["errors"] == 0
