"""
services/wall_persistence_features.py
--------------------------------------
LM47 — Wall persistence feature engine.

Pure-Python aggregator that turns a list of LM46 wall events into a
list of deterministic wall feature dicts (one per persistent wall).
No I/O, no Supabase, no network — safe to call from tests, the WS
collector, a future cron job, or an API route.

Public entry
~~~~~~~~~~~~
    compute_wall_features(events, *, options=None) -> list[dict]

Grouping
~~~~~~~~
Events are grouped into walls by:
  * symbol
  * exchange
  * timeframe
  * side
  * price zone (overlapping bands OR mids within `zone_merge_pct`% of
    the group's centerline merge into the same wall)

Each group emits one feature dict with a deterministic `wall_id`
(stable across runs for the same group centroid).

Statuses
~~~~~~~~
    active     — default; no terminal event and balance of strengthening
    weakening  — last event was wall_weakened, or weakens > strengthens
    defended   — last event was wall_defended, or defenses > touches
    broken     — last event was wall_broken
    pulled     — last event was wall_pulled

Input tolerance
~~~~~~~~~~~~~~~
`events=None`, empty iterables, and individual malformed event dicts
are silently skipped. The function never raises on malformed input.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable


# ── Event types (mirror of LM46 constants) ───────────────────────────────────

ET_CREATED      = "wall_created"
ET_STRENGTHENED = "wall_strengthened"
ET_WEAKENED     = "wall_weakened"
ET_PULLED       = "wall_pulled"
ET_TOUCHED      = "wall_touched"
ET_DEFENDED     = "wall_defended"
ET_BROKEN       = "wall_broken"

VALID_EVENT_TYPES = (
    ET_CREATED, ET_STRENGTHENED, ET_WEAKENED,
    ET_PULLED, ET_TOUCHED, ET_DEFENDED, ET_BROKEN,
)


# ── Statuses ─────────────────────────────────────────────────────────────────

STATUS_ACTIVE     = "active"
STATUS_WEAKENING  = "weakening"
STATUS_DEFENDED   = "defended"
STATUS_BROKEN     = "broken"
STATUS_PULLED     = "pulled"

VALID_STATUSES = (
    STATUS_ACTIVE, STATUS_WEAKENING, STATUS_DEFENDED,
    STATUS_BROKEN, STATUS_PULLED,
)


# ── Options ──────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class WallFeatureOptions:
    """
    Tunable knobs for `compute_wall_features`.

    zone_merge_pct: events within this % of a group's centerline merge
        into that group (in addition to band overlap). 0.10 = 0.10% of
        mid price (~$100 on a $100k symbol).
    min_persistence_seconds: drop walls whose first→last span is shorter
        than this. 0 keeps all groups.
    min_confidence: drop EVENTS whose confidence is below this before
        grouping. 0 keeps all events.
    max_reasons: how many recent event `reason` strings to keep on the
        feature dict.
    """
    zone_merge_pct:          float = 0.10
    min_persistence_seconds: float = 0.0
    min_confidence:          float = 0.0
    max_reasons:             int   = 5


# ── Internal group state ─────────────────────────────────────────────────────

@dataclass
class _Group:
    symbol:    str
    exchange:  str
    timeframe: str
    side:      str
    price_low:  float
    price_high: float
    events: list[dict] = field(default_factory=list)

    @property
    def price_mid(self) -> float:
        return (self.price_low + self.price_high) / 2.0


# ── Helpers ──────────────────────────────────────────────────────────────────

def _parse_ts(ts: object) -> datetime | None:
    if not isinstance(ts, str) or not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return None


def _valid_event(e: object) -> bool:
    """Conservative shape check — events lacking required fields are skipped."""
    if not isinstance(e, dict):
        return False
    if e.get("event_type") not in VALID_EVENT_TYPES:
        return False
    if e.get("side") not in ("bid", "ask"):
        return False
    for k in ("price_low", "price_high", "price_mid"):
        v = e.get(k)
        if not isinstance(v, (int, float)):
            return False
    return True


def _band_overlap_or_close(
    g: _Group, e: dict, zone_merge_pct: float,
) -> bool:
    """Same band already; or within `zone_merge_pct`% of the group's mid."""
    e_lo = float(e["price_low"])
    e_hi = float(e["price_high"])
    if e_hi >= g.price_low and e_lo <= g.price_high:
        return True
    g_mid = g.price_mid
    if g_mid == 0:
        return False
    tolerance = abs(g_mid) * zone_merge_pct / 100.0
    return abs(float(e["price_mid"]) - g_mid) <= tolerance


def _wall_id(
    symbol: str, exchange: str, timeframe: str, side: str, centroid: float,
) -> str:
    """
    Stable short id derived from (symbol, exchange, timeframe, side, centroid).
    Rounded centroid keeps the id sticky across small price drifts.
    """
    rounded = round(centroid, 2) if abs(centroid) < 100 else round(centroid)
    base = f"{symbol}|{exchange}|{timeframe}|{side}|{rounded}"
    h = hashlib.sha1(base.encode("utf-8")).hexdigest()[:12]
    return f"wall_{h}"


def _status_for(events: list[dict]) -> str:
    if not events:
        return STATUS_ACTIVE

    last_type = events[-1].get("event_type")
    if last_type == ET_BROKEN:
        return STATUS_BROKEN
    if last_type == ET_PULLED:
        return STATUS_PULLED
    if last_type == ET_DEFENDED:
        return STATUS_DEFENDED
    if last_type == ET_WEAKENED:
        return STATUS_WEAKENING

    # Last event was created/strengthened/touched — look at counts to
    # decide between active / weakening / defended.
    counts: dict[str, int] = {}
    for ev in events:
        t = ev.get("event_type")
        counts[t] = counts.get(t, 0) + 1
    if counts.get(ET_WEAKENED, 0) > counts.get(ET_STRENGTHENED, 0):
        return STATUS_WEAKENING
    if counts.get(ET_DEFENDED, 0) > counts.get(ET_TOUCHED, 0):
        return STATUS_DEFENDED
    return STATUS_ACTIVE


def _aggregate(group: _Group, opts: WallFeatureOptions) -> dict | None:
    if not group.events:
        return None

    # Stable order: by event_ts, then event_type. Already inserted in this
    # order but resorting is cheap and removes a class of mistakes.
    events = sorted(
        group.events,
        key=lambda e: (e.get("event_ts") or "", e.get("event_type") or ""),
    )
    first_ev = events[0]
    last_ev  = events[-1]

    first_ts = _parse_ts(first_ev.get("event_ts"))
    last_ts  = _parse_ts(last_ev.get("event_ts"))
    if first_ts is not None and last_ts is not None:
        persistence_seconds = max(0.0, (last_ts - first_ts).total_seconds())
    else:
        persistence_seconds = 0.0

    strengths = [
        float(e["strength"]) for e in events
        if isinstance(e.get("strength"), (int, float))
    ]
    current_strength = strengths[-1] if strengths else 0.0
    max_strength     = max(strengths) if strengths else 0.0
    min_strength     = min(strengths) if strengths else 0.0
    first_strength   = strengths[0]   if strengths else 0.0
    strength_delta_pct = (
        round((current_strength - first_strength) / first_strength * 100.0, 3)
        if first_strength > 0 else 0.0
    )

    distances = [
        float(e["distance_to_price_pct"]) for e in events
        if isinstance(e.get("distance_to_price_pct"), (int, float))
    ]
    avg_distance = (
        round(sum(distances) / len(distances), 4) if distances else None
    )

    counts: dict[str, int] = {}
    for ev in events:
        t = ev.get("event_type")
        counts[t] = counts.get(t, 0) + 1

    confidences = [
        float(e["confidence"]) for e in events
        if isinstance(e.get("confidence"), (int, float))
    ]
    confidence = round(max(confidences), 3) if confidences else 0.0

    if confidence < opts.min_confidence:
        return None
    if persistence_seconds < opts.min_persistence_seconds:
        return None

    reasons = [
        e.get("reason", "")
        for e in events[-opts.max_reasons:]
        if isinstance(e.get("reason"), str)
    ]

    centroid = sum(float(e["price_mid"]) for e in events) / len(events)
    wall_id = _wall_id(
        group.symbol, group.exchange, group.timeframe, group.side, centroid,
    )

    return {
        "wall_id":                   wall_id,
        "symbol":                    group.symbol,
        "exchange":                  group.exchange,
        "timeframe":                 group.timeframe,
        "side":                      group.side,
        "price_low":                 round(group.price_low, 4),
        "price_high":                round(group.price_high, 4),
        "price_mid":                 round(centroid, 4),
        "first_seen_ts":             first_ev.get("event_ts"),
        "last_seen_ts":              last_ev.get("event_ts"),
        "persistence_seconds":       round(persistence_seconds, 3),
        "touch_count":               counts.get(ET_TOUCHED,      0),
        "defense_count":             counts.get(ET_DEFENDED,     0),
        "break_count":               counts.get(ET_BROKEN,       0),
        "pull_count":                counts.get(ET_PULLED,       0),
        "strengthen_count":          counts.get(ET_STRENGTHENED, 0),
        "weaken_count":              counts.get(ET_WEAKENED,     0),
        "current_strength":          round(current_strength, 3),
        "max_strength":              round(max_strength, 3),
        "min_strength":              round(min_strength, 3),
        "strength_delta_pct":        strength_delta_pct,
        "avg_distance_to_price_pct": avg_distance,
        "last_event_type":           last_ev.get("event_type"),
        "confidence":                confidence,
        "status":                    _status_for(events),
        "reasons":                   reasons,
        "metadata": {
            "event_count":       len(events),
            "event_type_counts": counts,
            "first_event_ts":    first_ev.get("event_ts"),
            "last_event_ts":     last_ev.get("event_ts"),
        },
    }


# ── Public entry ─────────────────────────────────────────────────────────────

def compute_wall_features(
    events: Iterable[dict] | None,
    *,
    options: WallFeatureOptions | None = None,
) -> list[dict]:
    """
    Group LM46 wall events into deterministic wall feature dicts.

    Returns a list sorted by (symbol, timeframe, side, price_mid).
    Tolerant of `None`, empty iterables, and malformed event dicts —
    bad entries are silently skipped; never raises.
    """
    opts = options or WallFeatureOptions()
    if not events:
        return []

    valid = [e for e in events if _valid_event(e)]
    if opts.min_confidence > 0:
        valid = [
            e for e in valid
            if not isinstance(e.get("confidence"), (int, float))
            or float(e["confidence"]) >= opts.min_confidence
        ]

    # Sort by event_ts asc (ties: event_type). Determinism across runs.
    valid.sort(key=lambda e: (e.get("event_ts") or "", e.get("event_type") or ""))

    groups: list[_Group] = []
    for e in valid:
        sym  = e.get("symbol")    or ""
        ex   = e.get("exchange")  or ""
        tf   = e.get("timeframe") or ""
        side = e["side"]

        match: _Group | None = None
        for g in groups:
            if (g.symbol, g.exchange, g.timeframe, g.side) != (sym, ex, tf, side):
                continue
            if _band_overlap_or_close(g, e, opts.zone_merge_pct):
                match = g
                break

        if match is None:
            match = _Group(
                symbol=sym, exchange=ex, timeframe=tf, side=side,
                price_low=float(e["price_low"]),
                price_high=float(e["price_high"]),
            )
            groups.append(match)
        else:
            match.price_low  = min(match.price_low,  float(e["price_low"]))
            match.price_high = max(match.price_high, float(e["price_high"]))
        match.events.append(e)

    features: list[dict] = []
    for g in groups:
        f = _aggregate(g, opts)
        if f is not None:
            features.append(f)

    features.sort(
        key=lambda f: (f["symbol"], f["timeframe"], f["side"], f["price_mid"]),
    )
    return features
