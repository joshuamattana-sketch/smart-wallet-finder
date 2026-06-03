"""
tests/test_discord_alert_formatter.py
--------------------------------------
LM51A — Discord alert formatter tests.

Pure-function tests. No network, no Supabase, no webhook calls.
Deterministic output is asserted by comparing two calls with the same
input.
"""

from __future__ import annotations

from services.discord_alert_formatter import (
    COLOR_LONG,
    COLOR_NO_TRADE,
    COLOR_SHORT,
    format_discord_signal_alert,
)


# ── Signal fixture ──────────────────────────────────────────────────────────

def _signal(
    *,
    signal_id: str = "sig_test_0001",
    symbol: str = "BTCUSDT",
    exchange: str = "binance_spot",
    timeframe: str = "5m",
    signal_ts: str = "2026-06-01T12:00:00+00:00",
    setup_id: str = "setup_test_0001",
    setup_type: str = "long_absorption",
    direction: str = "long",
    signal_level: str = "strong_setup",
    score: float = 82.0,
    confidence: float = 0.88,
    entry_zone_low: float = 67000.0,
    entry_zone_high: float = 67010.0,
    entry_zone_mid: float | None = None,
    invalidation_price: float | None = 66865.99,
    targets: list[float] | None = None,
    reasons: list[str] | None = None,
    risks: list[str] | None = None,
    action_hint: str = "wait_for_retest",
    status: str = "active",
    outcome_status: str = "",
) -> dict:
    mid = entry_zone_mid if entry_zone_mid is not None else (entry_zone_low + entry_zone_high) / 2.0
    return {
        "signal_id":          signal_id,
        "symbol":             symbol,
        "exchange":           exchange,
        "timeframe":          timeframe,
        "signal_ts":          signal_ts,
        "setup_id":           setup_id,
        "setup_type":         setup_type,
        "direction":          direction,
        "signal_level":       signal_level,
        "score":              score,
        "confidence":         confidence,
        "entry_zone_low":     entry_zone_low,
        "entry_zone_high":    entry_zone_high,
        "entry_zone_mid":     mid,
        "invalidation_price": invalidation_price,
        "targets":            targets if targets is not None else [67215.0, 67425.0],
        "reasons":            reasons if reasons is not None else [
            "defended bid wall at 67005 with strength 82",
            "persistence 240s, status defended",
        ],
        "risks":              risks if risks is not None else [
            "one weakening event seen",
        ],
        "action_hint":        action_hint,
        "status":             status,
        "outcome_status":     outcome_status,
    }


def _find_field(embed: dict, name: str) -> dict | None:
    for f in embed["fields"]:
        if f["name"] == name:
            return f
    return None


# ── long signal ─────────────────────────────────────────────────────────────

class TestLongSignalAlert:

    def test_long_signal_payload_shape(self):
        out = format_discord_signal_alert(_signal(direction="long"))
        assert isinstance(out, dict)
        assert "content"  in out and isinstance(out["content"], str)
        assert "embeds"   in out and isinstance(out["embeds"], list)
        assert len(out["embeds"]) == 1

    def test_long_signal_content_mentions_long(self):
        out = format_discord_signal_alert(_signal(direction="long"))
        assert "LONG"    in out["content"]
        assert "BTCUSDT" in out["content"]
        assert "5m"      in out["content"]

    def test_long_signal_green_color(self):
        out = format_discord_signal_alert(_signal(direction="long"))
        embed = out["embeds"][0]
        assert embed["color"] == COLOR_LONG

    def test_long_signal_includes_entry_invalidation_targets(self):
        out = format_discord_signal_alert(_signal(direction="long"))
        embed = out["embeds"][0]
        # Required directional fields present.
        assert _find_field(embed, "Entry zone")   is not None
        assert _find_field(embed, "Invalidation") is not None
        assert _find_field(embed, "Targets")      is not None
        # Targets field shows the formatted prices (comma-grouped).
        targets_field = _find_field(embed, "Targets")
        assert "67,215" in targets_field["value"]
        assert "67,425" in targets_field["value"]


# ── short signal ────────────────────────────────────────────────────────────

class TestShortSignalAlert:

    def test_short_signal_red_color(self):
        out = format_discord_signal_alert(_signal(
            signal_id="sig_short", direction="short", setup_type="short_rejection",
            entry_zone_low=67500, entry_zone_high=67510,
            invalidation_price=67644.02, targets=[67294.97, 66985.0],
        ))
        embed = out["embeds"][0]
        assert embed["color"] == COLOR_SHORT
        assert "SHORT" in out["content"]

    def test_short_signal_targets_below_entry(self):
        out = format_discord_signal_alert(_signal(
            direction="short",
            entry_zone_low=67500, entry_zone_high=67510,
            invalidation_price=67644.02,
            targets=[67294.97, 66985.0],
        ))
        embed = out["embeds"][0]
        targets_field = _find_field(embed, "Targets")
        assert "67,294" in targets_field["value"]
        assert "66,985" in targets_field["value"]


# ── no_trade signal ────────────────────────────────────────────────────────

class TestNoTradeAlert:

    def test_no_trade_payload_shape(self):
        out = format_discord_signal_alert(_signal(
            signal_level="no_trade", direction="neutral", status="no_trade",
            score=0.0, confidence=0.0, invalidation_price=None, targets=[],
            action_hint="avoid_trade",
        ))
        embed = out["embeds"][0]
        # No-trade uses the muted color.
        assert embed["color"] == COLOR_NO_TRADE
        # No-trade content avoids LONG/SHORT.
        assert "LONG"  not in out["content"]
        assert "SHORT" not in out["content"]
        assert "no-trade" in out["content"]
        # No-trade omits directional geometry fields.
        assert _find_field(embed, "Entry zone")   is None
        assert _find_field(embed, "Invalidation") is None
        assert _find_field(embed, "Targets")      is None


# ── missing / partial input ────────────────────────────────────────────────

class TestMissingInputSafe:

    def test_none_returns_none(self):
        assert format_discord_signal_alert(None) is None

    def test_non_dict_returns_none(self):
        assert format_discord_signal_alert("nope") is None      # type: ignore[arg-type]
        assert format_discord_signal_alert(42)     is None      # type: ignore[arg-type]
        assert format_discord_signal_alert([{"x": 1}]) is None  # type: ignore[arg-type]

    def test_empty_dict_returns_none(self):
        # Symbol is required at minimum.
        assert format_discord_signal_alert({}) is None

    def test_missing_symbol_returns_none(self):
        bad = _signal()
        del bad["symbol"]
        assert format_discord_signal_alert(bad) is None

    def test_partial_signal_still_formats(self):
        # Symbol is present; everything else missing or sparse.
        partial = {
            "symbol":       "ETHUSDT",
            "signal_level": "watch",
            "direction":    "long",
        }
        out = format_discord_signal_alert(partial)
        assert out is not None
        embed = out["embeds"][0]
        # No crash on missing entry zone — falls back to '—'.
        ez = _find_field(embed, "Entry zone")
        assert ez is not None
        # Reasons/risks default to '—'.
        assert _find_field(embed, "Reasons")["value"] == "—"
        assert _find_field(embed, "Risks")["value"]   == "—"


# ── deterministic output shape ─────────────────────────────────────────────

class TestDeterministic:

    def test_same_input_identical_output(self):
        sig = _signal()
        a = format_discord_signal_alert(sig)
        b = format_discord_signal_alert(sig)
        assert a == b

    def test_required_embed_fields_present(self):
        out = format_discord_signal_alert(_signal())
        embed = out["embeds"][0]
        for key in ("title", "description", "fields", "footer"):
            assert key in embed
        assert isinstance(embed["title"],       str)
        assert isinstance(embed["description"], str)
        assert isinstance(embed["fields"],      list)
        assert isinstance(embed["footer"],      dict)
        # Footer always carries 'text'.
        assert "text" in embed["footer"]
        # Score/Confidence/Direction are always-present columns.
        assert _find_field(embed, "Score")      is not None
        assert _find_field(embed, "Confidence") is not None
        assert _find_field(embed, "Direction")  is not None

    def test_field_values_are_strings(self):
        out = format_discord_signal_alert(_signal())
        for field in out["embeds"][0]["fields"]:
            assert isinstance(field["name"],  str)
            assert isinstance(field["value"], str)
            assert isinstance(field["inline"], bool)


# ── reasons / risks included ───────────────────────────────────────────────

class TestReasonsAndRisks:

    def test_reasons_rendered_as_bullets(self):
        out = format_discord_signal_alert(_signal(
            reasons=["A reason", "Another reason"],
            risks=["A risk"],
        ))
        reasons = _find_field(out["embeds"][0], "Reasons")
        risks   = _find_field(out["embeds"][0], "Risks")
        assert "• A reason"       in reasons["value"]
        assert "• Another reason" in reasons["value"]
        assert "• A risk"         in risks["value"]

    def test_empty_lists_fall_back_to_dash(self):
        out = format_discord_signal_alert(_signal(reasons=[], risks=[]))
        reasons = _find_field(out["embeds"][0], "Reasons")
        risks   = _find_field(out["embeds"][0], "Risks")
        assert reasons["value"] == "—"
        assert risks["value"]   == "—"

    def test_non_string_entries_filtered_out(self):
        out = format_discord_signal_alert(_signal(
            reasons=["good", 5, None, "also good"],  # type: ignore[list-item]
        ))
        reasons = _find_field(out["embeds"][0], "Reasons")
        # Only the two strings make it through.
        assert "• good"      in reasons["value"]
        assert "• also good" in reasons["value"]
        # Stray "5" or "None" must NOT appear as bullets.
        assert "• 5"    not in reasons["value"]
        assert "• None" not in reasons["value"]
