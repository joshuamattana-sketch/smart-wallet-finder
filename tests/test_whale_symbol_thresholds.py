"""
tests/test_whale_symbol_thresholds.py
--------------------------------------
LM63D — Tests for per-symbol whale notional thresholds.
"""

from __future__ import annotations

import pytest

from services.whale_symbol_thresholds import (
    DEFAULT_THRESHOLDS,
    SYMBOL_THRESHOLDS,
    THRESHOLD_FIELDS,
    get_whale_thresholds_for_symbol,
)


# ── Built-in presets ─────────────────────────────────────────────────────────

class TestKnownSymbols:
    @pytest.mark.parametrize(
        "symbol, expected",
        [
            ("BTCUSDT",  {"min_notional_usd": 250_000.0, "high_notional_usd": 750_000.0,
                          "extreme_notional_usd": 2_000_000.0, "min_confidence": 0.6}),
            ("ETHUSDT",  {"min_notional_usd":  75_000.0, "high_notional_usd": 250_000.0,
                          "extreme_notional_usd": 1_000_000.0, "min_confidence": 0.6}),
            ("SOLUSDT",  {"min_notional_usd":  50_000.0, "high_notional_usd": 150_000.0,
                          "extreme_notional_usd":   500_000.0, "min_confidence": 0.6}),
            ("BNBUSDT",  {"min_notional_usd":  75_000.0, "high_notional_usd": 250_000.0,
                          "extreme_notional_usd":   750_000.0, "min_confidence": 0.6}),
            ("LINKUSDT", {"min_notional_usd":  25_000.0, "high_notional_usd": 100_000.0,
                          "extreme_notional_usd":   300_000.0, "min_confidence": 0.6}),
            ("DOGEUSDT", {"min_notional_usd":  25_000.0, "high_notional_usd": 100_000.0,
                          "extreme_notional_usd":   300_000.0, "min_confidence": 0.6}),
        ],
    )
    def test_returns_built_in_preset(self, symbol, expected):
        assert get_whale_thresholds_for_symbol(symbol) == expected

    def test_returned_dict_has_all_fields(self):
        for sym in SYMBOL_THRESHOLDS:
            result = get_whale_thresholds_for_symbol(sym)
            assert set(result) == THRESHOLD_FIELDS

    def test_btc_threshold_higher_than_doge_threshold(self):
        # Sanity: bigger market → higher whale floor.
        btc = get_whale_thresholds_for_symbol("BTCUSDT")
        doge = get_whale_thresholds_for_symbol("DOGEUSDT")
        assert btc["min_notional_usd"] > doge["min_notional_usd"]
        assert btc["extreme_notional_usd"] > doge["extreme_notional_usd"]


# ── Fallback ──────────────────────────────────────────────────────────────────

class TestFallback:
    def test_unknown_symbol_returns_default(self):
        assert get_whale_thresholds_for_symbol("FOOBAR") == dict(DEFAULT_THRESHOLDS)

    def test_empty_symbol_returns_default(self):
        assert get_whale_thresholds_for_symbol("") == dict(DEFAULT_THRESHOLDS)
        assert get_whale_thresholds_for_symbol("   ") == dict(DEFAULT_THRESHOLDS)

    def test_non_string_symbol_returns_default(self):
        assert get_whale_thresholds_for_symbol(None) == dict(DEFAULT_THRESHOLDS)
        assert get_whale_thresholds_for_symbol(123) == dict(DEFAULT_THRESHOLDS)
        assert get_whale_thresholds_for_symbol(["BTCUSDT"]) == dict(DEFAULT_THRESHOLDS)

    def test_default_contains_all_fields(self):
        assert set(DEFAULT_THRESHOLDS) == THRESHOLD_FIELDS


# ── Case handling ─────────────────────────────────────────────────────────────

class TestUppercaseHandling:
    def test_lowercase_symbol(self):
        assert get_whale_thresholds_for_symbol("btcusdt") \
            == get_whale_thresholds_for_symbol("BTCUSDT")

    def test_mixed_case_symbol(self):
        assert get_whale_thresholds_for_symbol("EthUsdt") \
            == get_whale_thresholds_for_symbol("ETHUSDT")

    def test_whitespace_stripped(self):
        assert get_whale_thresholds_for_symbol("  solusdt  ") \
            == get_whale_thresholds_for_symbol("SOLUSDT")


# ── Overrides ─────────────────────────────────────────────────────────────────

class TestOverrides:
    def test_full_override(self):
        overrides = {
            "BTCUSDT": {
                "min_notional_usd":     999_000.0,
                "high_notional_usd":    9_000_000.0,
                "extreme_notional_usd": 99_000_000.0,
                "min_confidence":       0.95,
            }
        }
        result = get_whale_thresholds_for_symbol("BTCUSDT", overrides)
        assert result["min_notional_usd"] == 999_000.0
        assert result["min_confidence"] == 0.95

    def test_partial_override_merges_with_preset(self):
        # Only bump BTC's min_notional. Other fields stay on the preset.
        overrides = {"BTCUSDT": {"min_notional_usd": 1_000_000.0}}
        result = get_whale_thresholds_for_symbol("BTCUSDT", overrides)
        assert result["min_notional_usd"]     == 1_000_000.0
        assert result["high_notional_usd"]    == 750_000.0    # from preset
        assert result["extreme_notional_usd"] == 2_000_000.0  # from preset
        assert result["min_confidence"]       == 0.6          # from preset

    def test_override_for_unknown_symbol_uses_default_then_override(self):
        overrides = {"FOOBAR": {"min_confidence": 0.85}}
        result = get_whale_thresholds_for_symbol("FOOBAR", overrides)
        assert result["min_confidence"]       == 0.85
        assert result["min_notional_usd"]     == DEFAULT_THRESHOLDS["min_notional_usd"]
        assert result["extreme_notional_usd"] == DEFAULT_THRESHOLDS["extreme_notional_usd"]

    def test_override_case_normalised(self):
        overrides = {"BTCUSDT": {"min_notional_usd": 1.0}}
        # Lower-case input symbol must still pick up the upper-cased override.
        result = get_whale_thresholds_for_symbol("btcusdt", overrides)
        assert result["min_notional_usd"] == 1.0

    def test_override_ignores_unknown_keys(self):
        overrides = {"BTCUSDT": {"banana_threshold": 42, "min_notional_usd": 5.0}}
        result = get_whale_thresholds_for_symbol("BTCUSDT", overrides)
        assert result["min_notional_usd"] == 5.0
        assert "banana_threshold" not in result

    def test_override_with_non_numeric_value_is_ignored(self):
        overrides = {"BTCUSDT": {"min_notional_usd": "not a number"}}
        result = get_whale_thresholds_for_symbol("BTCUSDT", overrides)
        # Falls through to the BTC preset, not blown up.
        assert result["min_notional_usd"] == 250_000.0

    def test_none_overrides_uses_built_in_preset(self):
        assert (
            get_whale_thresholds_for_symbol("BTCUSDT", overrides=None)
            == get_whale_thresholds_for_symbol("BTCUSDT")
        )

    def test_overrides_does_not_mutate_built_in_preset(self):
        before = dict(SYMBOL_THRESHOLDS["BTCUSDT"])
        get_whale_thresholds_for_symbol(
            "BTCUSDT", overrides={"BTCUSDT": {"min_notional_usd": 1.0}},
        )
        after = dict(SYMBOL_THRESHOLDS["BTCUSDT"])
        assert before == after
