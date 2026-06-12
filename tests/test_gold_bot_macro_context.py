"""
tests/test_gold_bot_macro_context.py
--------------------------------------
LM77A — Pure tests for the Gold Bot macro/news/event context layer.
No MT5, no network. Times are built relative to a fixed ``now``.
"""

from __future__ import annotations

from datetime import datetime, timezone

from services.gold_bot_macro_context import (
    build_macro_context,
    classify_event_state,
    derive_macro_bias,
    load_macro_events,
    macro_directional_adjustment,
)

NOW = datetime(2026, 6, 12, 13, 0, 0, tzinfo=timezone.utc)


def _ev(name, etype, currency, impact, minutes_from_now):
    return {"name": name, "type": etype, "currency": currency,
            "impact": impact, "minutes_from_now": minutes_from_now}


# ── event-risk window classification ──────────────────────────────────────────
def test_high_usd_event_in_20m_is_lockout():
    state, sev = classify_event_state("high", "USD", 20)
    assert state == "lockout" and sev == 3


def test_high_event_10m_after_is_post_event():
    state, _ = classify_event_state("high", "USD", -10)
    assert state == "post_event"


def test_medium_event_in_10m_is_watch():
    state, _ = classify_event_state("medium", "USD", 10)
    assert state == "watch"


def test_low_event_is_clear():
    assert classify_event_state("low", "USD", 5)[0] == "clear"


def test_high_non_usd_in_window_is_watch_not_lockout():
    assert classify_event_state("high", "EUR", 20)[0] == "watch"


def test_high_event_far_away_is_clear():
    assert classify_event_state("high", "USD", 120)[0] == "clear"


# ── full context build ────────────────────────────────────────────────────────
def test_build_context_high_usd_cpi_lockout():
    events = [_ev("US CPI", "CPI", "USD", "high", 22),
              _ev("NFP", "NFP", "USD", "high", 5000)]
    ctx = build_macro_context(NOW, events, "sample")
    assert ctx.event_risk_state == "lockout"
    assert ctx.event_type == "CPI"
    assert ctx.event_currency == "USD"
    assert ctx.minutes_to_next_event == 22
    assert ctx.confidence_modifier == -20
    assert ctx.high_impact_event_nearby is True
    assert ctx.blockers  # lockout blocker present


def test_build_context_picks_most_severe_driver():
    # A medium watch event is sooner, but the high-impact lockout must drive.
    events = [_ev("Jobless Claims", "Jobless Claims", "USD", "medium", 5),
              _ev("CPI", "CPI", "USD", "high", 25)]
    ctx = build_macro_context(NOW, events, "sample")
    assert ctx.event_risk_state == "lockout"
    assert ctx.event_type == "CPI"


def test_build_context_no_events_is_neutral():
    ctx = build_macro_context(NOW, [], "none")
    assert ctx.event_risk_state == "clear"
    assert ctx.next_event_name is None
    assert ctx.confidence_modifier == 0
    assert ctx.macro_bias == "unknown"


# ── DXY / yields / geopolitical placeholders ──────────────────────────────────
def test_dxy_yields_rising_is_gold_bearish():
    assert derive_macro_bias("rising", "rising", "unknown") == "gold_bearish"


def test_dxy_yields_falling_is_gold_bullish():
    assert derive_macro_bias("falling", "falling", "unknown") == "gold_bullish"


def test_geopolitical_high_leans_bullish():
    assert derive_macro_bias("unknown", "unknown", "high") == "gold_bullish"


def test_directional_rising_penalises_long_boosts_short():
    ctx = build_macro_context(NOW, [], "none", dxy_bias="rising", yields_bias="rising")
    long_delta, _ = macro_directional_adjustment(ctx, "LONG")
    short_delta, _ = macro_directional_adjustment(ctx, "SHORT")
    assert long_delta < 0          # headwind for gold longs
    assert short_delta > 0         # tailwind for gold shorts
    assert long_delta == -short_delta


def test_directional_falling_helps_long():
    ctx = build_macro_context(NOW, [], "none", dxy_bias="falling", yields_bias="falling")
    long_delta, _ = macro_directional_adjustment(ctx, "LONG")
    assert long_delta > 0


def test_geopolitical_high_adds_long_boost_and_warning():
    ctx = build_macro_context(NOW, [], "none", geopolitical_risk="high")
    delta, reasons = macro_directional_adjustment(ctx, "LONG")
    assert delta > 0
    assert any("geopolitical" in r.lower() for r in reasons)
    assert any("geopolitical" in w.lower() for w in ctx.warnings)


# ── file loading (fail-soft) ──────────────────────────────────────────────────
def test_missing_file_returns_none_source_with_warning():
    events, source, warns = load_macro_events("data/gold_bot/does_not_exist.json")
    assert events == [] and source == "none"
    assert warns and "not found" in warns[0]


def test_no_path_is_quiet_none():
    events, source, warns = load_macro_events(None)
    assert events == [] and source == "none" and warns == []


def test_loads_bundled_sample_file():
    events, source, warns = load_macro_events("data/gold_bot/macro_events.sample.json")
    assert source == "sample"
    assert warns == []
    assert any(e.get("type") == "CPI" for e in events)
