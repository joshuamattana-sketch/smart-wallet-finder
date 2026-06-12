"""
services/gold_bot_macro_context.py
-----------------------------------
LM77A — Gold Bot macro / news / event context layer V1 (pure, file-based).

This is the FIRST external-context awareness for the decision engine. It does
NOT call any paid API, does NOT scrape the web and does NOT trade. It builds a
structured ``MacroContext`` from:

  * a local/sample JSON event file (CPI / NFP / FOMC / Fed Speech / ...), and
  * simple CLI-supplied placeholder biases (DXY / yields / geopolitical risk).

The decision engine consumes the ``MacroContext`` and can:
  * force NO_TRADE during a high-impact USD event lockout window,
  * reduce confidence on watch / post-event windows (stricter for scalp),
  * nudge confidence with DXY / yields / geopolitical placeholders.

Everything here is deterministic given (now, events, biases). No MT5, no I/O
beyond reading the optional events file. Missing/invalid file → macro-neutral
context with a warning, never a crash.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# ── Event risk windows (configurable defaults, not buried deep) ───────────────
LOCKOUT_BEFORE_MIN = 30      # high-impact USD event this many min BEFORE release → lockout
POST_EVENT_AFTER_MIN = 15    # high-impact event this many min AFTER release → post_event
MEDIUM_WATCH_MIN = 15        # medium-impact event within this many min (either side) → watch
NEARBY_MIN = 60              # high-impact within this many min → high_impact_event_nearby flag

# Event-state → baseline (non-directional) confidence modifier applied to a
# would-be LONG/SHORT. Negative = more cautious.
STATE_CONF_MODIFIER = {"lockout": -20, "post_event": -15, "watch": -10, "clear": 0}

# Per-falling-factor directional nudge (DXY/yields). Each "falling" factor helps
# gold longs; each "rising" factor hurts them. Mirrored for shorts.
BIAS_FACTOR_POINTS = 6
GEO_LONG_BOOST = 4           # high geopolitical risk → safe-haven bid aids longs

_IMPACTS = ("low", "medium", "high")
_CURRENCIES = ("USD", "EUR", "GBP")
_KNOWN_TYPES = ("CPI", "NFP", "FOMC", "Fed Speech", "PPI", "Jobless Claims", "PMI", "GDP")


@dataclass
class MacroContext:
    timestamp: str
    source_mode: str                       # sample | local_file | none
    active_session: str
    high_impact_event_nearby: bool = False
    next_event_name: str | None = None
    next_event_time: str | None = None
    minutes_to_next_event: int | None = None
    event_impact: str = "unknown"          # low | medium | high | unknown
    event_currency: str = "unknown"        # USD | EUR | GBP | unknown
    event_type: str = "Other"              # CPI | NFP | FOMC | Fed Speech | PPI | ...
    event_risk_state: str = "clear"        # clear | watch | lockout | post_event
    macro_bias: str = "unknown"            # gold_bullish | gold_bearish | neutral | unknown
    dxy_bias: str = "unknown"              # rising | falling | flat | unknown
    yields_bias: str = "unknown"           # rising | falling | flat | unknown
    geopolitical_risk: str = "unknown"     # low | medium | high | unknown
    confidence_modifier: int = 0           # event-based baseline modifier (non-directional)
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def human_lines(self) -> list[str]:
        """Lines for the probe's 'Macro Context' section."""
        lines = [f"   source       : {self.source_mode}"]
        if self.next_event_name:
            m = self.minutes_to_next_event or 0
            when = f"in {m}m" if m >= 0 else f"{-m}m ago"
            lines.append(f"   next event   : {self.next_event_name} {when}, "
                         f"{self.event_impact} impact {self.event_currency} [{self.event_type}]")
        else:
            lines.append("   next event   : none")
        lines.append(f"   event state  : {self.event_risk_state}")
        lines.append(f"   macro bias   : {self.macro_bias}  "
                     f"(DXY {self.dxy_bias} | Yields {self.yields_bias} | Geo {self.geopolitical_risk})")
        lines.append(f"   conf modifier: {self.confidence_modifier:+d}")
        for w in self.warnings:
            lines.append(f"   warning   - {w}")
        for b in self.blockers:
            lines.append(f"   blocker   - {b}")
        return lines


# ── session helper (kept local; mirrors the decision engine's UTC bands) ──────
def session_from_dt(dt: datetime) -> str:
    h = dt.astimezone(timezone.utc).hour
    if 0 <= h < 7:
        return "Asia"
    if 7 <= h < 12:
        return "London"
    if 12 <= h < 21:
        return "NewYork"
    return "Off-session"


# ── event file loading (fail-soft) ────────────────────────────────────────────
def load_macro_events(path: str | None) -> tuple[list[dict], str, list[str]]:
    """
    Load local/sample macro events. Returns (events, source_mode, warnings).

    Missing path / missing file / unreadable / wrong shape → ([], "none", [warn]).
    Never raises. ``source_mode`` is taken from the file's declared "source_mode"
    (the bundled sample declares "sample"); otherwise "local_file".
    """
    if not path:
        return [], "none", []
    p = Path(path)
    if not p.exists():
        return [], "none", [f"macro events file not found: {path} (continuing macro-neutral)."]
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, ValueError) as exc:
        return [], "none", [f"macro events file unreadable: {exc} (continuing macro-neutral)."]

    if isinstance(data, dict):
        events = data.get("events", [])
        declared = data.get("source_mode")
    else:
        events, declared = data, None
    if not isinstance(events, list):
        return [], "none", ["macro events file has no 'events' list (continuing macro-neutral)."]
    source = declared if declared in ("sample", "local_file") else "local_file"
    return events, source, []


def _event_dt(ev: dict, now: datetime) -> datetime | None:
    """Resolve an event time. Supports absolute ISO 'time' or relative 'minutes_from_now'."""
    if "minutes_from_now" in ev:
        try:
            return now + timedelta(minutes=float(ev["minutes_from_now"]))
        except (TypeError, ValueError):
            return None
    raw = ev.get("time")
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw)
    except (TypeError, ValueError):
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def classify_event_state(impact: str, currency: str, minutes_delta: float) -> tuple[str, int]:
    """
    Pure event-risk classifier. ``minutes_delta`` > 0 means upcoming, < 0 passed.
    Returns (state, severity) where severity orders lockout>post_event>watch>clear.
    """
    impact = (impact or "unknown").lower()
    currency = (currency or "unknown").upper()
    if impact == "high":
        if 0 <= minutes_delta <= LOCKOUT_BEFORE_MIN:
            return ("lockout", 3) if currency == "USD" else ("watch", 1)
        if -POST_EVENT_AFTER_MIN <= minutes_delta < 0:
            return ("post_event", 2)
        return ("clear", 0)
    if impact == "medium":
        if -MEDIUM_WATCH_MIN <= minutes_delta <= MEDIUM_WATCH_MIN:
            return ("watch", 1)
        return ("clear", 0)
    # low / unknown impact → informational only.
    return ("clear", 0)


def derive_macro_bias(dxy_bias: str, yields_bias: str, geopolitical_risk: str) -> str:
    """gold_bullish | gold_bearish | neutral | unknown from placeholder biases."""
    score = 0
    known = False
    for b in (dxy_bias, yields_bias):
        if b == "rising":
            score -= 1; known = True       # stronger USD/yields → gold bearish
        elif b == "falling":
            score += 1; known = True
        elif b == "flat":
            known = True
    if geopolitical_risk == "high":
        score += 1; known = True           # safe-haven bid → gold bullish lean
    elif geopolitical_risk in ("low", "medium"):
        known = True
    if not known:
        return "unknown"
    if score > 0:
        return "gold_bullish"
    if score < 0:
        return "gold_bearish"
    return "neutral"


def macro_directional_adjustment(macro: MacroContext, decision: str) -> tuple[int, list[str]]:
    """
    Direction-specific confidence nudge from DXY/yields/geo placeholders.
    Returns (delta, reasons). Simple & explainable: each 'falling' factor helps
    gold LONGs, each 'rising' factor hurts them; mirrored for SHORTs.
    """
    reasons: list[str] = []
    pressure = 0
    for b in (macro.dxy_bias, macro.yields_bias):
        if b == "rising":
            pressure -= 1
        elif b == "falling":
            pressure += 1
    delta = 0
    if pressure != 0 and decision in ("LONG", "SHORT"):
        d = pressure * BIAS_FACTOR_POINTS if decision == "LONG" else -pressure * BIAS_FACTOR_POINTS
        delta += d
        verb = "supports" if d > 0 else "pressures"
        reasons.append(f"DXY {macro.dxy_bias} / Yields {macro.yields_bias} {verb} {decision} ({d:+d}).")
    if macro.geopolitical_risk == "high":
        if decision == "LONG":
            delta += GEO_LONG_BOOST
            reasons.append(f"geopolitical risk high — safe-haven bid aids LONG (+{GEO_LONG_BOOST}).")
        elif decision == "SHORT":
            reasons.append("geopolitical risk high — safe-haven bid may squeeze SHORT.")
    return delta, reasons


def build_macro_context(
    now: datetime,
    events: list[dict],
    source_mode: str,
    *,
    dxy_bias: str = "unknown",
    yields_bias: str = "unknown",
    geopolitical_risk: str = "unknown",
    extra_warnings: list[str] | None = None,
) -> MacroContext:
    """
    Assemble a MacroContext from resolved events + placeholder biases. Pure.

    The 'driver' event is the most severe active window (lockout>post_event>
    watch); ties broken by nearest in time. If nothing is active, the soonest
    upcoming event (else most recent past) is shown for context only.
    """
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    warnings = list(extra_warnings or [])

    ctx = MacroContext(
        timestamp=now.isoformat(),
        source_mode=source_mode,
        active_session=session_from_dt(now),
        dxy_bias=dxy_bias, yields_bias=yields_bias, geopolitical_risk=geopolitical_risk,
        macro_bias=derive_macro_bias(dxy_bias, yields_bias, geopolitical_risk),
        warnings=warnings,
    )

    # Resolve + classify every event.
    scored: list[tuple[dict, float, str, int]] = []
    for ev in events or []:
        dt = _event_dt(ev, now)
        if dt is None:
            warnings.append(f"skipped event with no usable time: {ev.get('name', ev)!r}.")
            continue
        delta = (dt - now).total_seconds() / 60.0
        state, severity = classify_event_state(ev.get("impact"), ev.get("currency"), delta)
        scored.append((ev, delta, state, severity))

    if not scored:
        # No usable events: macro-neutral except for any placeholder biases.
        ctx.reasons.append("no usable macro events — event risk clear, biases only.")
        _append_bias_reasons(ctx)
        return ctx

    active = [s for s in scored if s[3] > 0]
    if active:
        driver = max(active, key=lambda s: (s[3], -abs(s[1])))
    else:
        upcoming = [s for s in scored if s[1] >= 0]
        driver = min(upcoming, key=lambda s: s[1]) if upcoming else max(scored, key=lambda s: s[1])

    ev, delta, state, _severity = driver
    impact = (ev.get("impact") or "unknown").lower()
    currency = (ev.get("currency") or "unknown").upper()
    etype = ev.get("type") or "Other"
    minutes = int(round(delta))

    ctx.next_event_name = ev.get("name") or etype
    ctx.next_event_time = _event_dt(ev, now).isoformat()
    ctx.minutes_to_next_event = minutes
    ctx.event_impact = impact if impact in _IMPACTS else "unknown"
    ctx.event_currency = currency if currency in _CURRENCIES else "unknown"
    ctx.event_type = etype if etype in _KNOWN_TYPES else "Other"
    ctx.event_risk_state = state
    ctx.high_impact_event_nearby = bool(
        impact == "high" and -POST_EVENT_AFTER_MIN <= delta <= NEARBY_MIN
    )
    ctx.confidence_modifier = STATE_CONF_MODIFIER.get(state, 0)

    when = f"in {minutes}m" if minutes >= 0 else f"{-minutes}m ago"
    ctx.reasons.append(f"next event: {ctx.next_event_name} {when}, {impact} impact {currency}.")

    if state == "lockout":
        msg = (f"High-impact {currency} {etype} lockout window active "
               f"({when}).")
        ctx.blockers.append(msg)
        ctx.warnings.append(f"High-impact {currency} event nearby ({etype}).")
    elif state == "post_event":
        ctx.warnings.append(f"Post-event window after {currency} {etype} — volatile.")
    elif state == "watch":
        ctx.warnings.append(f"{impact.capitalize()}-impact {currency} {etype} nearby — watch.")

    _append_bias_reasons(ctx)
    return ctx


def _append_bias_reasons(ctx: MacroContext) -> None:
    if ctx.macro_bias not in ("unknown",):
        ctx.reasons.append(
            f"macro bias {ctx.macro_bias} (DXY {ctx.dxy_bias}, yields {ctx.yields_bias}, "
            f"geo {ctx.geopolitical_risk}).")
    if ctx.geopolitical_risk == "high":
        ctx.warnings.append("High geopolitical risk — gold safe-haven bid but elevated volatility.")
