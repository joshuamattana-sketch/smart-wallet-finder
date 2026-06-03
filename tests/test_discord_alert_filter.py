"""
tests/test_discord_alert_filter.py
-----------------------------------
LM51C — Discord alert filter tests.

Pure-function tests. No network, no Supabase.
"""

from __future__ import annotations

from services.discord_alert_filter import (
    DiscordAlertFilterOptions,
    should_send_discord_alert,
)


def _signal(
    *,
    symbol: str = "BTCUSDT",
    exchange: str = "binance_spot",
    timeframe: str = "5m",
    setup_type: str = "long_absorption",
    direction: str = "long",
    signal_level: str = "strong_setup",
    score: float = 82.0,
    confidence: float = 0.88,
    status: str = "active",
) -> dict:
    return {
        "symbol":       symbol,
        "exchange":     exchange,
        "timeframe":    timeframe,
        "setup_type":   setup_type,
        "direction":    direction,
        "signal_level": signal_level,
        "score":        score,
        "confidence":   confidence,
        "status":       status,
    }


# ── strong_setup ─────────────────────────────────────────────────────────────

class TestStrongSetup:

    def test_strong_setup_always_sends(self):
        # Even a barely-passing score / confidence still sends at this level.
        r = should_send_discord_alert(_signal(
            signal_level="strong_setup", score=70.0, confidence=0.60,
        ))
        assert r["should_send"]  is True
        assert r["reason"]       == "strong_setup_auto_send"
        assert r["signal_level"] == "strong_setup"


# ── setup with thresholds ───────────────────────────────────────────────────

class TestSetupWithThresholds:

    def test_setup_above_thresholds_sends(self):
        r = should_send_discord_alert(_signal(
            signal_level="setup", score=72.0, confidence=0.75,
        ))
        assert r["should_send"] is True
        assert r["reason"]      == "setup_above_thresholds"

    def test_setup_below_score_blocks(self):
        r = should_send_discord_alert(_signal(
            signal_level="setup", score=55.0, confidence=0.80,
        ))
        assert r["should_send"] is False
        assert r["reason"]      == "setup_low_score"

    def test_setup_low_confidence_blocks(self):
        r = should_send_discord_alert(_signal(
            signal_level="setup", score=80.0, confidence=0.40,
        ))
        assert r["should_send"] is False
        assert r["reason"]      == "setup_low_confidence"

    def test_setup_custom_thresholds(self):
        # Loosen thresholds so a 55/0.4 setup goes through.
        opts = DiscordAlertFilterOptions(min_score=50.0, min_confidence=0.30)
        r = should_send_discord_alert(_signal(
            signal_level="setup", score=55.0, confidence=0.40,
        ), options=opts)
        assert r["should_send"] is True


# ── watch ────────────────────────────────────────────────────────────────────

class TestWatch:

    def test_watch_blocked_by_default(self):
        r = should_send_discord_alert(_signal(
            signal_level="watch", score=35.0, confidence=0.70,
        ))
        assert r["should_send"] is False
        assert r["reason"]      == "watch_disabled"

    def test_watch_allowed_when_option_enabled(self):
        opts = DiscordAlertFilterOptions(send_watch=True)
        r = should_send_discord_alert(_signal(
            signal_level="watch", score=35.0, confidence=0.70,
        ), options=opts)
        assert r["should_send"] is True
        assert r["reason"]      == "watch_enabled"


# ── no_trade ─────────────────────────────────────────────────────────────────

class TestNoTrade:

    def test_no_trade_blocked_by_default(self):
        r = should_send_discord_alert(_signal(
            signal_level="no_trade", direction="neutral",
            score=0.0, confidence=0.0, status="no_trade",
        ))
        assert r["should_send"] is False
        assert r["reason"]      == "no_trade_disabled"

    def test_no_trade_allowed_when_option_enabled(self):
        opts = DiscordAlertFilterOptions(send_no_trade=True)
        r = should_send_discord_alert(_signal(
            signal_level="no_trade", direction="neutral",
            score=0.0, confidence=0.0, status="no_trade",
        ), options=opts)
        assert r["should_send"] is True
        assert r["reason"]      == "no_trade_enabled"


# ── invalidated ─────────────────────────────────────────────────────────────

class TestInvalidated:

    def test_invalidated_setup_blocked_even_at_strong_level(self):
        r = should_send_discord_alert(_signal(
            signal_level="strong_setup", score=82.0, confidence=0.88,
            status="invalidated",
        ))
        assert r["should_send"] is False
        assert r["reason"]      == "setup_invalidated"


# ── allowed_symbols / blocked_symbols ───────────────────────────────────────

class TestSymbolFilters:

    def test_allowed_symbols_allows_match(self):
        opts = DiscordAlertFilterOptions(
            allowed_symbols=("BTCUSDT", "ETHUSDT"),
        )
        r = should_send_discord_alert(_signal(symbol="BTCUSDT"), options=opts)
        assert r["should_send"] is True

    def test_allowed_symbols_blocks_non_match(self):
        opts = DiscordAlertFilterOptions(
            allowed_symbols=("ETHUSDT", "SOLUSDT"),
        )
        r = should_send_discord_alert(_signal(symbol="BTCUSDT"), options=opts)
        assert r["should_send"] is False
        assert r["reason"]      == "symbol_not_allowed"

    def test_allowed_symbols_case_insensitive(self):
        opts = DiscordAlertFilterOptions(allowed_symbols=("btcusdt",))
        r = should_send_discord_alert(_signal(symbol="BTCUSDT"), options=opts)
        assert r["should_send"] is True

    def test_blocked_symbols_blocks_match(self):
        opts = DiscordAlertFilterOptions(blocked_symbols=("BTCUSDT",))
        r = should_send_discord_alert(_signal(symbol="BTCUSDT"), options=opts)
        assert r["should_send"] is False
        assert r["reason"]      == "symbol_blocked"

    def test_blocked_symbols_does_not_affect_other_symbols(self):
        opts = DiscordAlertFilterOptions(blocked_symbols=("BTCUSDT",))
        r = should_send_discord_alert(_signal(symbol="ETHUSDT"), options=opts)
        assert r["should_send"] is True

    def test_blocked_wins_over_allowed(self):
        # If a symbol appears in BOTH lists the block should win — safer default.
        opts = DiscordAlertFilterOptions(
            allowed_symbols=("BTCUSDT",),
            blocked_symbols=("BTCUSDT",),
        )
        r = should_send_discord_alert(_signal(symbol="BTCUSDT"), options=opts)
        assert r["should_send"] is False
        assert r["reason"]      == "symbol_blocked"


# ── deterministic cooldown_key ──────────────────────────────────────────────

class TestCooldownKey:

    def test_same_signal_same_cooldown_key(self):
        a = should_send_discord_alert(_signal())["cooldown_key"]
        b = should_send_discord_alert(_signal())["cooldown_key"]
        assert a == b
        assert a.startswith("cooldown_")
        assert len(a) == len("cooldown_") + 16

    def test_different_market_different_cooldown_key(self):
        a = should_send_discord_alert(_signal(symbol="BTCUSDT"))["cooldown_key"]
        b = should_send_discord_alert(_signal(symbol="ETHUSDT"))["cooldown_key"]
        assert a != b

    def test_different_direction_different_cooldown_key(self):
        a = should_send_discord_alert(_signal(direction="long"))["cooldown_key"]
        b = should_send_discord_alert(_signal(direction="short"))["cooldown_key"]
        assert a != b

    def test_cooldown_key_present_even_when_blocked(self):
        # Symbol blocked but cooldown_key still derived from input fields.
        opts = DiscordAlertFilterOptions(blocked_symbols=("BTCUSDT",))
        r = should_send_discord_alert(_signal(symbol="BTCUSDT"), options=opts)
        assert r["should_send"]  is False
        assert r["cooldown_key"] != ""

    def test_cooldown_key_empty_on_invalid_input(self):
        r = should_send_discord_alert(None)
        assert r["should_send"]  is False
        assert r["cooldown_key"] == ""


# ── missing / partial input ─────────────────────────────────────────────────

class TestMissingInput:

    def test_none_input(self):
        r = should_send_discord_alert(None)
        assert r["should_send"]  is False
        assert r["reason"]       == "invalid_input"
        assert r["cooldown_key"] == ""

    def test_non_dict_input(self):
        r = should_send_discord_alert("nope")  # type: ignore[arg-type]
        assert r["should_send"] is False
        assert r["reason"]      == "invalid_input"

    def test_missing_symbol(self):
        bad = _signal()
        del bad["symbol"]
        r = should_send_discord_alert(bad)
        assert r["should_send"]  is False
        assert r["reason"]       == "missing_symbol"
        assert r["cooldown_key"] == ""

    def test_empty_dict(self):
        r = should_send_discord_alert({})
        assert r["should_send"] is False
        assert r["reason"]      == "missing_symbol"

    def test_unknown_signal_level(self):
        r = should_send_discord_alert(_signal(signal_level="bogus"))
        assert r["should_send"] is False
        assert r["reason"]      == "unknown_signal_level"

    def test_score_and_confidence_clamped(self):
        r = should_send_discord_alert(_signal(score=500.0, confidence=2.5))
        assert 0.0 <= r["score"]      <= 100.0
        assert 0.0 <= r["confidence"] <= 1.0


# ── deterministic output shape ──────────────────────────────────────────────

class TestDeterministicShape:

    def test_required_keys_always_present(self):
        for input_ in (
            None,
            "bad",
            {},
            _signal(),
            _signal(signal_level="watch"),
            _signal(signal_level="no_trade", direction="neutral"),
        ):
            r = should_send_discord_alert(input_)  # type: ignore[arg-type]
            assert set(r.keys()) == {
                "should_send", "reason", "signal_level",
                "score", "confidence", "cooldown_key",
            }

    def test_same_input_same_output(self):
        sig = _signal()
        a = should_send_discord_alert(sig)
        b = should_send_discord_alert(sig)
        assert a == b
