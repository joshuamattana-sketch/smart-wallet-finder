"""
tests/test_gold_bot_economic_calendar.py
------------------------------------------
LM83A — Pure tests for the provider-neutral economic calendar layer.
No MT5, no network. Times relative to a fixed ``now``.
"""

from __future__ import annotations

from datetime import datetime, timezone

from services.gold_bot_economic_calendar import (
    EconomicEvent,
    FutureApiEconomicCalendarProvider,
    LocalJsonEconomicCalendarProvider,
    ManualImportProvider,
    ManualJsonEconomicCalendarProvider,
    filter_events,
    load_calendar_events,
    next_high_impact,
    normalize_event,
    normalize_event_type,
    resolve_calendar_provider,
    sort_events,
)
from services.gold_bot_macro_context import (
    build_macro_context,
    classify_event_state,
    load_calendar_or_macro,
)

NOW = datetime(2026, 6, 12, 13, 0, 0, tzinfo=timezone.utc)


def _raw(title, currency, impact, minutes, etype=None):
    r = {"title": title, "currency": currency, "impact": impact, "minutes_from_now": minutes}
    if etype:
        r["type"] = etype
    return r


# ── parsing / normalization ─────────────────────────────────────────────────────
def test_parses_valid_event():
    ev, warn = normalize_event(_raw("US CPI (MoM)", "usd", "high", 22, "CPI"), NOW)
    assert warn is None
    assert ev.title == "US CPI (MoM)"
    assert ev.currency == "USD"          # upper-normalized
    assert ev.impact == "high"
    assert ev.event_type == "CPI"
    assert ev.scheduled_at == datetime(2026, 6, 12, 13, 22, tzinfo=timezone.utc)
    assert ev.event_id


def test_event_type_inferred_from_title():
    assert normalize_event_type(None, "US Non-Farm Payrolls") == "NFP"
    assert normalize_event_type(None, "FOMC Statement") == "FOMC"
    assert normalize_event_type("Initial Jobless Claims", None) == "Jobless Claims"
    assert normalize_event_type("something weird", "random text") == "Other"


def test_gold_major_tag_applied():
    ev, _ = normalize_event(_raw("US CPI", "USD", "high", 30, "CPI"), NOW)
    assert ev.is_gold_major() is True
    assert "gold_major" in ev.tags
    eur, _ = normalize_event(_raw("EZ CPI", "EUR", "high", 30, "CPI"), NOW)
    assert eur.is_gold_major() is False


def test_malformed_events_ignored_with_warning():
    assert normalize_event({"currency": "USD", "impact": "high", "minutes_from_now": 5}, NOW)[0] is None
    assert normalize_event(_raw("No currency", "", "high", 5), NOW)[0] is None
    assert normalize_event(_raw("Bad impact", "USD", "huge", 5), NOW)[0] is None
    assert normalize_event({"title": "No time", "currency": "USD", "impact": "low"}, NOW)[0] is None
    ev, warn = normalize_event(_raw("Bad impact", "USD", "huge", 5), NOW)
    assert ev is None and "impact" in warn


# ── sorting / filtering ──────────────────────────────────────────────────────────
def _events():
    raws = [
        _raw("CPI", "USD", "high", 22, "CPI"),
        _raw("Jobless", "USD", "medium", 75, "Jobless Claims"),
        _raw("ECB CPI", "EUR", "high", 200, "CPI"),
        _raw("Old NFP", "USD", "high", -120, "NFP"),
    ]
    return [normalize_event(r, NOW)[0] for r in raws]


def test_events_sorted_by_time():
    evs = sort_events(_events())
    times = [e.scheduled_at for e in evs]
    assert times == sorted(times)
    assert evs[0].title == "Old NFP"     # earliest (in the past)


def test_filter_by_currency_and_impact():
    usd_high = filter_events(_events(), now=NOW, currency="USD", impact="high")
    assert [e.title for e in usd_high] == ["CPI"]   # Old NFP dropped by window past-cutoff


def test_filter_by_window():
    within_1h = filter_events(_events(), now=NOW, window_hours=1.0)
    titles = {e.title for e in within_1h}
    assert "CPI" in titles                # 22m
    assert "Jobless" not in titles        # 75m > 60m


def test_next_high_impact_usd():
    nxt = next_high_impact(_events(), now=NOW, currency="USD")
    assert nxt is not None and nxt.title == "CPI"


# ── event-risk states via macro classifier ──────────────────────────────────────
def test_high_cpi_in_22m_is_lockout():
    ev, _ = normalize_event(_raw("US CPI", "USD", "high", 22, "CPI"), NOW)
    state, _ = classify_event_state(ev.impact, ev.currency, ev.minutes_until(NOW))
    assert state == "lockout"


def test_high_event_far_away_is_clear():
    ev, _ = normalize_event(_raw("US NFP", "USD", "high", 600, "NFP"), NOW)
    state, _ = classify_event_state(ev.impact, ev.currency, ev.minutes_until(NOW))
    assert state == "clear"


def test_medium_event_nearby_is_watch():
    ev, _ = normalize_event(_raw("Jobless", "USD", "medium", 10, "Jobless Claims"), NOW)
    state, _ = classify_event_state(ev.impact, ev.currency, ev.minutes_until(NOW))
    assert state == "watch"


# ── file loader (fail-soft) ──────────────────────────────────────────────────────
def test_missing_file_warns_no_crash():
    events, source, warns = load_calendar_events("data/gold_bot/does_not_exist.json", now=NOW)
    assert events == [] and source == "none"
    assert warns and "not found" in warns[0]


def test_loads_bundled_sample_calendar():
    events, source, warns = load_calendar_events(
        "data/gold_bot/economic_calendar.sample.json", now=NOW)
    assert source == "local_json"
    assert any(e.event_type == "CPI" and e.currency == "USD" for e in events)
    assert events == sort_events(events)


# ── providers ─────────────────────────────────────────────────────────────────────
def test_local_provider_fetch():
    evs, src, _ = LocalJsonEconomicCalendarProvider(
        "data/gold_bot/economic_calendar.sample.json").fetch(now=NOW)
    assert src == "local_json" and evs


def test_future_api_provider_is_placeholder():
    evs, src, warns = FutureApiEconomicCalendarProvider().fetch(now=NOW)
    assert evs == [] and src == "none"
    assert any("placeholder" in w.lower() for w in warns)


def test_manual_import_provider():
    ev = EconomicEvent(event_id="x", title="Manual", event_type="CPI", currency="USD",
                       impact="high", scheduled_at=NOW)
    evs, src, _ = ManualImportProvider([ev]).fetch(now=NOW)
    assert src == "manual_import" and evs[0].title == "Manual"


# ── local + manual JSON providers & status ────────────────────────────────────────
def test_local_provider_status_active_on_sample():
    st = LocalJsonEconomicCalendarProvider("data/gold_bot/economic_calendar.sample.json").status(NOW)
    assert st.name == "local_json" and st.status == "active"
    assert st.freshness in ("fresh", "stale")
    assert st.last_updated


def test_local_provider_status_missing():
    st = LocalJsonEconomicCalendarProvider("data/gold_bot/does_not_exist.json").status(NOW)
    assert st.status == "missing" and st.freshness == "none"


def test_manual_json_provider_labels_and_warns():
    prov = ManualJsonEconomicCalendarProvider("data/gold_bot/economic_calendar.manual.json")
    evs, src, warns = prov.fetch(now=NOW)
    assert src == "manual_json"
    assert evs                                  # manual sample has events
    assert any("temporary fallback" in w.lower() for w in warns)
    st = prov.status(NOW)
    assert st.name == "manual_json" and st.status == "fallback"


def test_resolve_calendar_provider_picks_by_name():
    assert isinstance(
        resolve_calendar_provider("data/gold_bot/economic_calendar.manual.json"),
        ManualJsonEconomicCalendarProvider)
    p = resolve_calendar_provider("data/gold_bot/economic_calendar.sample.json")
    assert isinstance(p, LocalJsonEconomicCalendarProvider)
    assert not isinstance(p, ManualJsonEconomicCalendarProvider)


# ── macro context integration ─────────────────────────────────────────────────────
def test_macro_context_consumes_calendar():
    dicts, source, warns = load_calendar_or_macro(
        calendar_file="data/gold_bot/economic_calendar.sample.json", now=NOW)
    assert source == "economic_calendar:local_json"
    ctx = build_macro_context(NOW, dicts, source)
    assert ctx.event_risk_state == "lockout"      # sample CPI is 22m out
    assert ctx.event_type == "CPI"
    assert ctx.blockers


def test_macro_context_falls_back_to_macro_events():
    dicts, source, warns = load_calendar_or_macro(
        macro_events_file="data/gold_bot/macro_events.sample.json", now=NOW)
    assert source in ("sample", "local_file")
