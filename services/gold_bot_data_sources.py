"""
services/gold_bot_data_sources.py
----------------------------------
LM83A (part 2) - Provider-neutral data source architecture for the Gold Bot.

Defines a single ``ProviderStatus`` reporting model plus the registry of data
sources the bot can draw on: the REAL local/manual economic calendar providers
(implemented in gold_bot_economic_calendar) and a set of clearly-marked
PLACEHOLDER providers for future automatic feeds (Finnhub / TradingEconomics /
MT5 calendar export / GDELT / FRED / yfinance / MT5+DXY+yields+VIX history).

HARD RULES for this patch:
  * No external HTTP calls anywhere. Placeholders return status only.
  * No API keys, no secrets. Placeholders may store the NAME of a future env
    var, never a value.
  * Manual JSON is a TEMPORARY free fallback, not the long-term source.

This module is stdlib-only and never imports MT5. ``ProviderStatus`` lives here
(zero deps) so the economic-calendar module can import it without a cycle; the
overview builder lazy-imports the calendar providers.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any

# ── status / category vocab ───────────────────────────────────────────────────
PROVIDER_STATUSES = ("active", "fallback", "placeholder", "missing", "error")
CATEGORIES = ("economic_calendar", "historical_market", "macro_market", "news", "manual")
FRESHNESS = ("fresh", "stale", "none", "unknown")

# Default calendar file locations (repo-root-relative).
DEFAULT_SAMPLE_CALENDAR = "data/gold_bot/economic_calendar.sample.json"
DEFAULT_MANUAL_CALENDAR = "data/gold_bot/economic_calendar.manual.json"


@dataclass
class ProviderStatus:
    name: str
    category: str                       # one of CATEGORIES
    status: str                         # one of PROVIDER_STATUSES
    freshness: str = "unknown"          # fresh | stale | none | unknown
    last_updated: str | None = None     # ISO ts of underlying data, if known
    message: str = ""
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def line(self) -> str:
        ts = f" updated {self.last_updated}" if self.last_updated else ""
        return (f"{self.name:<22} {self.category:<18} {self.status:<11} "
                f"{self.freshness:<7}{ts}  {self.message}")


# ── placeholder providers (NO network, status-only) ───────────────────────────
@dataclass(frozen=True)
class _PlaceholderSpec:
    name: str
    category: str
    message: str


class PlaceholderProvider:
    """
    Base for every not-yet-implemented source. ``status()`` always reports
    ``placeholder``; ``fetch()`` returns no events and NEVER makes a network
    call. Concrete subclasses only set ``spec``.
    """

    spec: _PlaceholderSpec = _PlaceholderSpec("placeholder", "economic_calendar", "placeholder.")

    def status(self, now: datetime | None = None) -> ProviderStatus:
        return ProviderStatus(
            name=self.spec.name, category=self.spec.category, status="placeholder",
            freshness="none", message=self.spec.message,
        )

    def fetch(self, now: datetime | None = None):
        # Intentionally inert: no HTTP, no file, no MT5. Returns the placeholder note.
        return [], "placeholder", [self.spec.message]


# economic calendar - future automatic feeds
class MT5CalendarExportProvider(PlaceholderProvider):
    spec = _PlaceholderSpec(
        "mt5_calendar_export", "economic_calendar",
        "Reads a future CSV/JSON exported from the MT5/MQL5 Economic Calendar - "
        "export script not built yet; no HTTP.")


class FinnhubEconomicCalendarProvider(PlaceholderProvider):
    spec = _PlaceholderSpec(
        "finnhub", "economic_calendar",
        "Finnhub economic calendar - placeholder; no API key, no HTTP in this build "
        "(future env: FINNHUB_API_KEY).")


class TradingEconomicsCalendarProvider(PlaceholderProvider):
    spec = _PlaceholderSpec(
        "trading_economics", "economic_calendar",
        "TradingEconomics calendar - placeholder; no API key, no HTTP in this build "
        "(future env: TRADING_ECONOMICS_KEY).")


# news
class GdeltNewsProvider(PlaceholderProvider):
    spec = _PlaceholderSpec(
        "gdelt", "news",
        "GDELT global news - placeholder; no HTTP in this build.")


class RssNewsProvider(PlaceholderProvider):
    spec = _PlaceholderSpec(
        "rss", "news",
        "Generic RSS headlines - placeholder; no HTTP in this build.")


# macro market
class FredMacroProvider(PlaceholderProvider):
    spec = _PlaceholderSpec(
        "fred", "macro_market",
        "FRED macro series (DXY/yields/CPI) - placeholder; no API key, no HTTP "
        "(future env: FRED_API_KEY).")


class YFinanceMacroProvider(PlaceholderProvider):
    spec = _PlaceholderSpec(
        "yfinance", "macro_market",
        "yfinance macro (DXY/^TNX/^VIX) - placeholder; no HTTP in this build.")


# historical market — MT5 XAUUSD is REAL as of LM84A (status from
# gold_bot_historical_market_data.history_status). Macro DXY/US-yields/VIX are
# REAL as of LM84B (status from gold_bot_macro_history.macro_market_statuses).
# FRED + yfinance remain external-fetch placeholders.

# Order matters only for display.
PLACEHOLDER_PROVIDERS = (
    MT5CalendarExportProvider, FinnhubEconomicCalendarProvider, TradingEconomicsCalendarProvider,
    FredMacroProvider, YFinanceMacroProvider,
    GdeltNewsProvider, RssNewsProvider,
)


# ── overview registry ──────────────────────────────────────────────────────────
def build_data_source_overview(
    *,
    calendar_file: str | None = None,
    manual_file: str | None = None,
    history_dir: str | None = None,
    macro_history_dir: str | None = None,
    now: datetime | None = None,
) -> list[ProviderStatus]:
    """
    Full data-source status snapshot: real local + manual economic calendars, the
    real MT5 XAUUSD history, the real macro (DXY/US-yields/VIX) history, then the
    remaining external-fetch placeholders. No external calls. Lazy-imports the
    real providers to avoid an import cycle.
    """
    now = now or datetime.now(timezone.utc)
    from services.gold_bot_economic_calendar import (
        LocalJsonEconomicCalendarProvider,
        ManualJsonEconomicCalendarProvider,
    )
    from services.gold_bot_historical_market_data import DEFAULT_HISTORY_DIR, history_status
    from services.gold_bot_macro_history import DEFAULT_MACRO_HISTORY_DIR, macro_market_statuses

    statuses: list[ProviderStatus] = [
        LocalJsonEconomicCalendarProvider(calendar_file or DEFAULT_SAMPLE_CALENDAR).status(now),
        ManualJsonEconomicCalendarProvider(manual_file or DEFAULT_MANUAL_CALENDAR).status(now),
        history_status(history_dir or DEFAULT_HISTORY_DIR, now=now),
    ]
    statuses.extend(macro_market_statuses(macro_history_dir or DEFAULT_MACRO_HISTORY_DIR, now=now))
    for cls in PLACEHOLDER_PROVIDERS:
        statuses.append(cls().status(now))
    return statuses


def group_by_category(statuses: list[ProviderStatus]) -> dict[str, list[ProviderStatus]]:
    out: dict[str, list[ProviderStatus]] = {c: [] for c in CATEGORIES}
    for s in statuses:
        out.setdefault(s.category, []).append(s)
    return {k: v for k, v in out.items() if v}
