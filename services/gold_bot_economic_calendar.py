"""
services/gold_bot_economic_calendar.py
----------------------------------------
LM83A — Provider-neutral economic calendar layer for the Gold Bot.

Normalizes raw calendar entries (CPI / NFP / FOMC / ...) into a single
``EconomicEvent`` shape the macro/news context layer can consume, regardless of
where they came from. This patch ships ONE real provider — a local JSON file —
plus clearly-marked placeholders for future providers. No paid API, no secrets,
no scraping. Pure + deterministic given (raw events, now).

Provider architecture:
  * LocalJsonEconomicCalendarProvider  — REAL: reads a local/sample JSON file.
  * FutureApiEconomicCalendarProvider  — placeholder (raises/returns empty; no
    network, no API key in this build).
  * ManualImportProvider               — placeholder for hand-curated events.

The macro context layer (gold_bot_macro_context) calls into here via the
unified loader and keeps the lockout/watch/post-event rules. This module never
imports the macro layer (no cycle) and never touches MT5.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from services.gold_bot_data_sources import ProviderStatus

DEFAULT_SAMPLE_PATH = "data/gold_bot/economic_calendar.sample.json"
DEFAULT_MANUAL_PATH = "data/gold_bot/economic_calendar.manual.json"

# Canonical event types that matter for XAUUSD.
EVENT_TYPES = (
    "CPI", "PPI", "NFP", "FOMC", "Fed Speech", "Jobless Claims", "Retail Sales",
    "PMI", "GDP", "Interest Rate Decision", "Treasury Auction", "Other",
)

# Substring → canonical type (case-insensitive, checked against type + title).
_TYPE_ALIASES = {
    "non-farm": "NFP", "nonfarm": "NFP", "non farm": "NFP", "payroll": "NFP", "nfp": "NFP",
    "cpi": "CPI", "consumer price": "CPI", "inflation": "CPI",
    "ppi": "PPI", "producer price": "PPI",
    "fomc": "FOMC", "federal open market": "FOMC",
    "fed chair": "Fed Speech", "fed speech": "Fed Speech", "powell": "Fed Speech",
    "fed governor": "Fed Speech", "speaks": "Fed Speech",
    "jobless": "Jobless Claims", "initial claims": "Jobless Claims",
    "retail sales": "Retail Sales",
    "pmi": "PMI", "purchasing managers": "PMI",
    "gdp": "GDP", "gross domestic": "GDP",
    "interest rate": "Interest Rate Decision", "rate decision": "Interest Rate Decision",
    "treasury auction": "Treasury Auction", "bond auction": "Treasury Auction",
}

# Events treated as MAJOR risk for gold (USD, high impact in these families).
_GOLD_MAJOR_TYPES = ("CPI", "NFP", "FOMC", "Fed Speech", "Interest Rate Decision", "PPI")

_VALID_IMPACTS = ("low", "medium", "high")


@dataclass
class EconomicEvent:
    event_id: str
    title: str
    event_type: str                 # one of EVENT_TYPES
    currency: str                   # USD | EUR | GBP | ...
    impact: str                     # low | medium | high
    scheduled_at: datetime          # tz-aware UTC
    country: str | None = None
    previous: Any | None = None
    forecast: Any | None = None
    actual: Any | None = None
    source: str = "local_json"
    source_url: str | None = None
    raw_payload: dict | None = None
    tags: list[str] = field(default_factory=list)

    def minutes_until(self, now: datetime) -> float:
        return (self.scheduled_at - now).total_seconds() / 60.0

    def is_gold_major(self) -> bool:
        return self.currency == "USD" and self.impact == "high" and self.event_type in _GOLD_MAJOR_TYPES

    def to_macro_event_dict(self) -> dict[str, Any]:
        """Shape consumed by gold_bot_macro_context.build_macro_context."""
        return {
            "name": self.title,
            "type": self.event_type,
            "currency": self.currency,
            "impact": self.impact,
            "time": self.scheduled_at.isoformat(),
        }

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["scheduled_at"] = self.scheduled_at.isoformat()
        return d


# ── normalization ─────────────────────────────────────────────────────────────
def normalize_event_type(raw_type: str | None, title: str | None) -> str:
    blob = f"{raw_type or ''} {title or ''}".lower()
    # exact canonical first
    if raw_type:
        for t in EVENT_TYPES:
            if raw_type.strip().lower() == t.lower():
                return t
    for needle, canonical in _TYPE_ALIASES.items():
        if needle in blob:
            return canonical
    return "Other"


def _resolve_scheduled_at(raw: dict, now: datetime) -> datetime | None:
    """Absolute ISO (scheduled_at/time/date) OR relative 'minutes_from_now'."""
    if "minutes_from_now" in raw:
        try:
            return now + timedelta(minutes=float(raw["minutes_from_now"]))
        except (TypeError, ValueError):
            return None
    for key in ("scheduled_at", "time", "date", "datetime"):
        val = raw.get(key)
        if not val:
            continue
        try:
            dt = datetime.fromisoformat(str(val).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            continue
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
    return None


def _make_event_id(raw: dict, title: str, scheduled_at: datetime, currency: str) -> str:
    if raw.get("event_id"):
        return str(raw["event_id"])
    seed = f"{title}|{currency}|{scheduled_at.isoformat()}"
    return "ev_" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]


def normalize_event(raw: dict, now: datetime, *, source: str = "local_json") -> tuple[EconomicEvent | None, str | None]:
    """
    Normalize one raw entry. Returns (event, None) or (None, warning) when a
    required field (title / currency / impact / time) is missing or invalid.
    """
    if not isinstance(raw, dict):
        return None, f"skipped non-object calendar entry: {raw!r}."
    title = raw.get("title") or raw.get("name")
    if not title:
        return None, f"skipped event with no title: {raw!r}."
    currency = str(raw.get("currency") or "").upper()
    if not currency:
        return None, f"skipped '{title}' — missing currency."
    impact = str(raw.get("impact") or "").lower()
    if impact not in _VALID_IMPACTS:
        return None, f"skipped '{title}' — impact must be low|medium|high (got {raw.get('impact')!r})."
    scheduled_at = _resolve_scheduled_at(raw, now)
    if scheduled_at is None:
        return None, f"skipped '{title}' — no usable scheduled time."

    event_type = normalize_event_type(raw.get("type") or raw.get("event_type"), title)
    tags = list(raw.get("tags") or [])
    ev = EconomicEvent(
        event_id=_make_event_id(raw, title, scheduled_at, currency),
        title=title, event_type=event_type, currency=currency, impact=impact,
        scheduled_at=scheduled_at, country=raw.get("country"),
        previous=raw.get("previous"), forecast=raw.get("forecast"), actual=raw.get("actual"),
        source=raw.get("source") or source, source_url=raw.get("source_url"),
        raw_payload=raw.get("raw_payload"), tags=tags,
    )
    if ev.is_gold_major() and "gold_major" not in ev.tags:
        ev.tags.append("gold_major")
    return ev, None


# ── filtering / sorting ────────────────────────────────────────────────────────
def sort_events(events: list[EconomicEvent]) -> list[EconomicEvent]:
    return sorted(events, key=lambda e: e.scheduled_at)


def filter_events(
    events: list[EconomicEvent],
    *,
    now: datetime,
    window_hours: float | None = None,
    currency: str | None = None,
    impact: str | None = None,
    include_past_minutes: float = 30.0,
) -> list[EconomicEvent]:
    """
    Filter by currency / impact / forward time window. Recently-passed events
    within ``include_past_minutes`` are kept (post-event windows still matter).
    """
    out = []
    cur = currency.upper() if currency else None
    imp = impact.lower() if impact else None
    for e in events:
        if cur and e.currency != cur:
            continue
        if imp and e.impact != imp:
            continue
        delta_min = e.minutes_until(now)
        if delta_min < -abs(include_past_minutes):
            continue
        if window_hours is not None and delta_min > window_hours * 60.0:
            continue
        out.append(e)
    return sort_events(out)


def next_high_impact(events: list[EconomicEvent], *, now: datetime,
                     currency: str | None = "USD") -> EconomicEvent | None:
    cur = currency.upper() if currency else None
    upcoming = [e for e in sort_events(events)
                if e.impact == "high" and e.minutes_until(now) >= 0
                and (cur is None or e.currency == cur)]
    return upcoming[0] if upcoming else None


# ── providers ──────────────────────────────────────────────────────────────────
class EconomicCalendarProvider:
    """Base provider. fetch() → (events, source_mode, warnings)."""

    name = "base"

    def fetch(self, now: datetime | None = None) -> tuple[list[EconomicEvent], str, list[str]]:
        raise NotImplementedError


class LocalJsonEconomicCalendarProvider(EconomicCalendarProvider):
    """REAL provider: load + normalize events from a local/sample JSON file."""

    name = "local_json"
    source_label = "local_json"
    active_label = "active"            # local sample is the working source
    category = "economic_calendar"

    def __init__(self, path: str | Path | None):
        self.path = path

    def fetch(self, now: datetime | None = None) -> tuple[list[EconomicEvent], str, list[str]]:
        events, _src, warnings = load_calendar_events(self.path, now=now)
        return events, self.source_label, warnings

    def status(self, now: datetime | None = None) -> ProviderStatus:
        now = now or datetime.now(timezone.utc)
        p = Path(self.path) if self.path else None
        if p is None or not p.exists():
            return ProviderStatus(
                self.source_label, self.category, "missing", freshness="none",
                message=f"calendar file not found: {self.path}")
        try:
            events, _src, warnings = self.fetch(now=now)
            last = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc).isoformat()
        except OSError as exc:
            return ProviderStatus(self.source_label, self.category, "error",
                                  freshness="unknown", message=str(exc))
        if not events:
            return ProviderStatus(self.source_label, self.category, self.active_label,
                                  freshness="none", last_updated=last,
                                  message="file present but no usable events", warnings=warnings)
        upcoming = [e for e in events if e.minutes_until(now) >= -30]
        return ProviderStatus(
            self.source_label, self.category, self.active_label,
            freshness="fresh" if upcoming else "stale", last_updated=last,
            message=f"{len(events)} events ({len(upcoming)} upcoming)", warnings=warnings)


class ManualJsonEconomicCalendarProvider(LocalJsonEconomicCalendarProvider):
    """
    Manual JSON calendar — a TEMPORARY FREE FALLBACK for hand-pasted events.
    Same parsing/normalization as the local provider, but labels its source
    ``manual_json``, reports status ``fallback`` and emits a reminder warning
    that this is not the long-term automatic source.
    """

    name = "manual_json"
    source_label = "manual_json"
    active_label = "fallback"

    def fetch(self, now: datetime | None = None) -> tuple[list[EconomicEvent], str, list[str]]:
        events, _src, warnings = load_calendar_events(self.path, now=now)
        if events:
            warnings = ["manual_json is a temporary fallback - replace with an automatic "
                        "provider when available."] + warnings
        return events, self.source_label, warnings


def resolve_calendar_provider(path: str | Path | None) -> LocalJsonEconomicCalendarProvider:
    """Pick the right file provider by path: a 'manual' file → ManualJson, else Local."""
    name = Path(path).name.lower() if path else ""
    if "manual" in name:
        return ManualJsonEconomicCalendarProvider(path)
    return LocalJsonEconomicCalendarProvider(path)


class FutureApiEconomicCalendarProvider(EconomicCalendarProvider):
    """
    PLACEHOLDER for a future real economic-calendar API (e.g. a paid feed).
    Intentionally NOT implemented here: no network call, no API key, no secret.
    Wire a concrete client in a later patch.
    """

    name = "future_api"

    def __init__(self, *, base_url: str | None = None, api_key_env: str | None = None):
        self.base_url = base_url
        self.api_key_env = api_key_env  # NAME of an env var to read later — never a secret value

    def fetch(self, now: datetime | None = None) -> tuple[list[EconomicEvent], str, list[str]]:
        return [], "none", [
            "FutureApiEconomicCalendarProvider is a placeholder — no real API in this build."
        ]


class ManualImportProvider(EconomicCalendarProvider):
    """PLACEHOLDER for hand-curated EconomicEvent objects (e.g. pasted by the user)."""

    name = "manual_import"

    def __init__(self, events: list[EconomicEvent] | None = None):
        self._events = events or []

    def fetch(self, now: datetime | None = None) -> tuple[list[EconomicEvent], str, list[str]]:
        return sort_events(list(self._events)), "manual_import", []


# ── local JSON loader (fail-soft) ──────────────────────────────────────────────
def load_calendar_events(
    path: str | Path | None, *, now: datetime | None = None,
) -> tuple[list[EconomicEvent], str, list[str]]:
    """
    Load + normalize a local economic calendar JSON file. Returns
    (events, source_mode, warnings). Missing/unreadable/wrong-shape → ([],
    "none", [warn]). Malformed individual events are skipped with a warning.
    Events are sorted by scheduled_at.
    """
    now = now or datetime.now(timezone.utc)
    if not path:
        return [], "none", []
    p = Path(path)
    if not p.exists():
        return [], "none", [f"economic calendar file not found: {path} (continuing macro-neutral)."]
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, ValueError) as exc:
        return [], "none", [f"economic calendar file unreadable: {exc} (continuing macro-neutral)."]

    if isinstance(data, dict):
        raw_events = data.get("events", [])
    else:
        raw_events = data
    if not isinstance(raw_events, list):
        return [], "none", ["economic calendar file has no 'events' list (continuing macro-neutral)."]

    events: list[EconomicEvent] = []
    warnings: list[str] = []
    for raw in raw_events:
        ev, warn = normalize_event(raw, now)
        if ev is not None:
            events.append(ev)
        elif warn:
            warnings.append(warn)
    return sort_events(events), "local_json", warnings
