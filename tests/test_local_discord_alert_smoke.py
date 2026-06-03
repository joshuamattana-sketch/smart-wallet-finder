"""Tests for local_discord_alert_smoke (LM56)."""

from services.local_discord_alert_smoke import run_local_discord_alert_smoke


def _signal(signal_level="strong_setup", score=85.0, confidence=0.9, **kw):
    base = {
        "symbol": "BTCUSDT",
        "exchange": "binance_spot",
        "timeframe": "5m",
        "setup_type": "long_absorption",
        "direction": "long",
        "signal_level": signal_level,
        "score": score,
        "confidence": confidence,
        "status": "active",
    }
    base.update(kw)
    return base


def test_strong_signal_builds_payload():
    result = run_local_discord_alert_smoke(_signal())
    assert result["should_send"] is True
    assert result["payload"] is not None
    assert "content" in result["payload"]
    assert "embeds" in result["payload"]


def test_watch_signal_blocked_by_default():
    result = run_local_discord_alert_smoke(_signal(signal_level="watch", score=50.0))
    assert result["should_send"] is False
    assert result["payload"] is None
    assert result["summary"]["filtered"] == 1


def test_send_false_does_not_call_webhook():
    calls = []
    def _spy(*a, **k):
        calls.append(1)
        return {"ok": True}
    result = run_local_discord_alert_smoke(
        _signal(), {"send": False}, sender=_spy,
    )
    assert result["should_send"] is True
    assert len(calls) == 0
    assert result["send_result"] is None


def test_send_true_calls_mocked_sender():
    calls = []
    def _mock_sender(payload, webhook_url=None, **k):
        calls.append({"payload": payload, "url": webhook_url})
        return {"ok": True, "status": 200}
    result = run_local_discord_alert_smoke(
        _signal(),
        {"send": True, "webhook_url": "https://discord.test/hook"},
        sender=_mock_sender,
    )
    assert result["should_send"] is True
    assert len(calls) == 1
    assert calls[0]["url"] == "https://discord.test/hook"
    assert result["send_result"]["ok"] is True
    assert result["summary"]["sent"] == 1


def test_missing_input_safe():
    r = run_local_discord_alert_smoke(None)
    assert r["should_send"] is False
    assert r["filter_reason"] == "invalid input"

    r2 = run_local_discord_alert_smoke({})
    assert r2["should_send"] is False

    r3 = run_local_discord_alert_smoke("bad")
    assert r3["should_send"] is False


def test_summary_counts_correct():
    r_blocked = run_local_discord_alert_smoke(_signal(signal_level="watch", score=40.0))
    assert r_blocked["summary"]["filtered"] == 1
    assert r_blocked["summary"]["formatted"] == 0
    assert r_blocked["summary"]["sent"] == 0

    r_formatted = run_local_discord_alert_smoke(_signal())
    assert r_formatted["summary"]["formatted"] == 1
    assert r_formatted["summary"]["sent"] == 0

    def _ok_sender(p, **k):
        return {"ok": True}
    r_sent = run_local_discord_alert_smoke(
        _signal(), {"send": True}, sender=_ok_sender,
    )
    assert r_sent["summary"]["sent"] == 1
    assert r_sent["summary"]["errors"] == 0
