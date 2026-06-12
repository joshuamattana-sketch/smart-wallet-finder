"""
tests/test_gold_bot_data_sources.py
-------------------------------------
LM83A (part 2) — Provider status model + data source registry tests.
No MT5, no HTTP. Placeholders must stay inert.
"""

from __future__ import annotations

from datetime import datetime, timezone

from services.gold_bot_data_sources import (
    CATEGORIES,
    PLACEHOLDER_PROVIDERS,
    PROVIDER_STATUSES,
    FinnhubEconomicCalendarProvider,
    GdeltNewsProvider,
    MT5HistoricalXauusdProvider,
    ProviderStatus,
    build_data_source_overview,
    group_by_category,
)

NOW = datetime(2026, 6, 12, 13, 0, 0, tzinfo=timezone.utc)


# ── status model ────────────────────────────────────────────────────────────────
def test_provider_status_to_dict():
    s = ProviderStatus("x", "news", "placeholder", message="hi")
    d = s.to_dict()
    assert d["name"] == "x" and d["category"] == "news" and d["status"] == "placeholder"
    assert d["warnings"] == []


def test_status_and_category_vocab():
    assert "active" in PROVIDER_STATUSES and "fallback" in PROVIDER_STATUSES
    assert "placeholder" in PROVIDER_STATUSES and "missing" in PROVIDER_STATUSES
    assert set(CATEGORIES) >= {"economic_calendar", "historical_market", "macro_market", "news"}


# ── placeholders are inert (no HTTP, no events) ──────────────────────────────────
def test_all_placeholders_return_placeholder_status():
    for cls in PLACEHOLDER_PROVIDERS:
        st = cls().status(NOW)
        assert st.status == "placeholder"
        assert st.freshness == "none"
        assert st.message


def test_placeholder_fetch_makes_no_call_and_returns_empty():
    events, src, warns = FinnhubEconomicCalendarProvider().fetch(now=NOW)
    assert events == [] and src == "placeholder"
    assert warns and "placeholder" in warns[0].lower()
    # historical + news placeholders behave the same
    assert MT5HistoricalXauusdProvider().fetch(now=NOW)[0] == []
    assert GdeltNewsProvider().fetch(now=NOW)[0] == []


# ── overview registry ────────────────────────────────────────────────────────────
def test_overview_includes_real_and_placeholder():
    statuses = build_data_source_overview(
        calendar_file="data/gold_bot/economic_calendar.sample.json",
        manual_file="data/gold_bot/economic_calendar.manual.json", now=NOW)
    by_name = {s.name: s for s in statuses}
    assert by_name["local_json"].status == "active"
    assert by_name["manual_json"].status == "fallback"
    assert by_name["finnhub"].status == "placeholder"
    assert by_name["mt5_xauusd_history"].status == "placeholder"
    # at least one of each placeholder category present
    cats = {s.category for s in statuses}
    assert {"economic_calendar", "historical_market", "macro_market", "news"} <= cats


def test_overview_missing_files_report_missing():
    statuses = build_data_source_overview(
        calendar_file="data/gold_bot/nope_sample.json",
        manual_file="data/gold_bot/nope_manual.json", now=NOW)
    by_name = {s.name: s for s in statuses}
    assert by_name["local_json"].status == "missing"
    assert by_name["manual_json"].status == "missing"


def test_group_by_category():
    statuses = build_data_source_overview(now=NOW)
    grouped = group_by_category(statuses)
    assert "economic_calendar" in grouped
    assert all(s.category == "news" for s in grouped.get("news", []))
