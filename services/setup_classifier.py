"""
services/setup_classifier.py
-----------------------------
LM48 — Setup classifier v1.

Pure-Python classifier that turns LM47 wall persistence features into
deterministic trading setup candidates. No I/O, no Supabase, no network.

Public entry
~~~~~~~~~~~~
    classify_setups(features, *, options=None) -> list[dict]

Setup types
~~~~~~~~~~~
    long_absorption     — strong defended/active bid wall (price floor)
    short_rejection     — strong defended/active ask wall (price ceiling)
    breakout_pressure   — strong opposite wall weakening / pulled / broken
    liquidity_trap_risk — broken wall after defenses, OR conflicting walls
    no_trade            — features present but nothing actionable

Directions: "long" | "short" | "neutral".
Statuses:   "candidate" | "confirmed" | "invalidated" | "no_trade".

Determinism
~~~~~~~~~~~
* Output sorted by (symbol, timeframe, setup_type, direction, price_zone_mid).
* setup_id is a stable hash of (symbol, exchange, timeframe, setup_type,
  primary_wall_id).
* `None` / empty / malformed inputs return `[]` without raising.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Iterable


# ── Setup types ──────────────────────────────────────────────────────────────

ST_LONG_ABSORPTION      = "long_absorption"
ST_SHORT_REJECTION      = "short_rejection"
ST_BREAKOUT_PRESSURE    = "breakout_pressure"
ST_LIQUIDITY_TRAP_RISK  = "liquidity_trap_risk"
ST_NO_TRADE             = "no_trade"

VALID_SETUP_TYPES = (
    ST_LONG_ABSORPTION, ST_SHORT_REJECTION, ST_BREAKOUT_PRESSURE,
    ST_LIQUIDITY_TRAP_RISK, ST_NO_TRADE,
)

# ── Directions ───────────────────────────────────────────────────────────────

DIR_LONG     = "long"
DIR_SHORT    = "short"
DIR_NEUTRAL  = "neutral"

VALID_DIRECTIONS = (DIR_LONG, DIR_SHORT, DIR_NEUTRAL)

# ── Statuses ─────────────────────────────────────────────────────────────────

STATUS_CANDIDATE   = "candidate"
STATUS_CONFIRMED   = "confirmed"
STATUS_INVALIDATED = "invalidated"
STATUS_NO_TRADE    = "no_trade"

VALID_STATUSES = (STATUS_CANDIDATE, STATUS_CONFIRMED,
                  STATUS_INVALIDATED, STATUS_NO_TRADE)

# ── LM47 feature status mirrors (avoid hard import coupling) ─────────────────

FS_ACTIVE     = "active"
FS_WEAKENING  = "weakening"
FS_DEFENDED   = "defended"
FS_BROKEN     = "broken"
FS_PULLED     = "pulled"


# ── Options ──────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SetupClassifierOptions:
    """
    Tunable thresholds. Defaults are conservative so the classifier doesn't
    emit actionable setups on noise.
    """
    min_confidence:          float = 0.40    # wall must be at least this confident
    min_score:               float = 35.0    # drop setups scoring below this
    strong_wall_strength:    float = 60.0    # 0–100; min current/max strength to qualify
    min_persistence_seconds: float = 30.0    # wall must have existed this long
    near_price_distance_pct: float = 0.50    # avg distance to price below this = "near"
    conflict_strength_pct:   float = 30.0    # bid vs ask strength within X% → trap risk
    trap_min_history_count:  int   = 2       # touches+defenses needed for failed-defense trap


# ── Helpers ──────────────────────────────────────────────────────────────────

def _is_number(v: object) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _valid_feature(f: object) -> bool:
    """Conservative shape check; missing/garbage features are skipped."""
    if not isinstance(f, dict):
        return False
    if f.get("side") not in ("bid", "ask"):
        return False
    for k in ("price_low", "price_high", "price_mid",
              "current_strength", "max_strength", "persistence_seconds",
              "confidence"):
        if not _is_number(f.get(k)):
            return False
    return True


def _setup_id(
    symbol: str, exchange: str, timeframe: str,
    setup_type: str, primary_wall_id: str | None,
) -> str:
    base = f"{symbol}|{exchange}|{timeframe}|{setup_type}|{primary_wall_id or '-'}"
    h = hashlib.sha1(base.encode("utf-8")).hexdigest()[:12]
    return f"setup_{h}"


def _base_score(f: dict) -> float:
    """
    0–100 score blending confidence (40%), persistence (30%), strength (30%).
    Persistence saturates at 60s; strength uses current_strength.
    """
    conf  = float(f.get("confidence") or 0.0)
    pers  = float(f.get("persistence_seconds") or 0.0)
    strn  = float(f.get("current_strength") or 0.0)
    persistence_factor = min(pers / 60.0, 1.0)
    strength_factor    = max(0.0, min(strn / 100.0, 1.0))
    confidence_factor  = max(0.0, min(conf, 1.0))
    score = (
        confidence_factor * 0.40
        + persistence_factor * 0.30
        + strength_factor * 0.30
    ) * 100.0
    return max(0.0, min(100.0, score))


def _setup_confidence(score: float, wall_confidence: float) -> float:
    """
    Setup confidence (0–1) is a weighted mix of normalized score (70%)
    and the underlying wall confidence (30%).
    """
    return max(0.0, min(1.0,
        (score / 100.0) * 0.70 + max(0.0, min(1.0, wall_confidence)) * 0.30,
    ))


def _is_near_price(f: dict, near_pct: float) -> bool:
    """Treat unknown distance (no current_price during event window) as 'near'."""
    d = f.get("avg_distance_to_price_pct")
    if not _is_number(d):
        return True
    return float(d) <= near_pct


def _qualifies_min(f: dict, opts: SetupClassifierOptions) -> bool:
    """Common min-threshold gate for all actionable setups."""
    return (
        float(f.get("confidence") or 0.0) >= opts.min_confidence
        and float(f.get("persistence_seconds") or 0.0) >= opts.min_persistence_seconds
    )


def _ordered_seen_ts(features: list[dict]) -> str:
    """Pick a deterministic setup_ts (the most recent last_seen_ts)."""
    candidates = [
        f.get("last_seen_ts") for f in features
        if isinstance(f.get("last_seen_ts"), str)
    ]
    return max(candidates) if candidates else ""


# ── Per-setup builders ───────────────────────────────────────────────────────

def _make_setup(
    *,
    setup_type: str,
    direction: str,
    symbol: str, exchange: str, timeframe: str, setup_ts: str,
    primary_wall: dict | None,
    related_walls: list[dict] | None,
    score: float,
    confidence: float,
    status: str,
    reasons: list[str],
    risks: list[str],
    metadata: dict | None = None,
) -> dict:
    primary_id = primary_wall.get("wall_id") if primary_wall else None
    related_ids = [w.get("wall_id") for w in (related_walls or [])
                   if isinstance(w, dict) and w.get("wall_id")]
    if primary_wall is not None:
        zone_low  = float(primary_wall.get("price_low")  or 0.0)
        zone_high = float(primary_wall.get("price_high") or 0.0)
        zone_mid  = float(primary_wall.get("price_mid")  or 0.0)
    else:
        zone_low = zone_high = zone_mid = 0.0
    return {
        "setup_id":         _setup_id(symbol, exchange, timeframe, setup_type, primary_id),
        "symbol":           symbol,
        "exchange":         exchange,
        "timeframe":        timeframe,
        "setup_ts":         setup_ts,
        "setup_type":       setup_type,
        "direction":        direction,
        "score":            round(max(0.0, min(100.0, score)), 3),
        "confidence":       round(max(0.0, min(1.0,  confidence)), 3),
        "price_zone_low":   round(zone_low,  4),
        "price_zone_high":  round(zone_high, 4),
        "price_zone_mid":   round(zone_mid,  4),
        "primary_wall_id":  primary_id,
        "related_wall_ids": related_ids,
        "reasons":          reasons,
        "risks":            risks,
        "status":           status,
        "metadata":         metadata or {},
    }


def _absorption_status(feature_status: str) -> str:
    if feature_status == FS_DEFENDED:
        return STATUS_CONFIRMED
    if feature_status == FS_BROKEN:
        return STATUS_INVALIDATED
    return STATUS_CANDIDATE


def _breakout_status(feature_status: str) -> str:
    if feature_status == FS_BROKEN:
        return STATUS_CONFIRMED
    return STATUS_CANDIDATE


def _build_long_absorption(f: dict, opts: SetupClassifierOptions, setup_ts: str) -> dict | None:
    if f.get("side") != "bid":
        return None
    if f.get("status") not in (FS_DEFENDED, FS_ACTIVE):
        return None
    if not _qualifies_min(f, opts):
        return None
    if float(f.get("current_strength") or 0.0) < opts.strong_wall_strength:
        return None

    score = _base_score(f)
    score += 5.0 * int(f.get("defense_count") or 0)
    score -= 5.0 * int(f.get("weaken_count")  or 0)
    if f.get("status") == FS_DEFENDED:
        score += 5.0
    score = max(0.0, min(100.0, score))
    if score < opts.min_score:
        return None

    conf = _setup_confidence(score, float(f.get("confidence") or 0.0))
    reasons = [
        f"bid wall at {f.get('price_mid')} with strength {f.get('current_strength')}",
        f"persistence {f.get('persistence_seconds')}s, status {f.get('status')}",
    ]
    if f.get("defense_count"):
        reasons.append(f"{f['defense_count']} prior defenses on this level")
    risks: list[str] = []
    if f.get("weaken_count"):
        risks.append(f"{f['weaken_count']} weakening events seen")
    if not _is_near_price(f, opts.near_price_distance_pct):
        risks.append("wall not consistently near price during its lifetime")

    return _make_setup(
        setup_type=ST_LONG_ABSORPTION,
        direction=DIR_LONG,
        symbol=f.get("symbol", ""), exchange=f.get("exchange", ""),
        timeframe=f.get("timeframe", ""), setup_ts=setup_ts,
        primary_wall=f, related_walls=None,
        score=score, confidence=conf,
        status=_absorption_status(f.get("status", "")),
        reasons=reasons, risks=risks,
        metadata={
            "feature_status":  f.get("status"),
            "defense_count":   f.get("defense_count"),
            "touch_count":     f.get("touch_count"),
            "weaken_count":    f.get("weaken_count"),
            "current_strength": f.get("current_strength"),
        },
    )


def _build_short_rejection(f: dict, opts: SetupClassifierOptions, setup_ts: str) -> dict | None:
    if f.get("side") != "ask":
        return None
    if f.get("status") not in (FS_DEFENDED, FS_ACTIVE):
        return None
    if not _qualifies_min(f, opts):
        return None
    if float(f.get("current_strength") or 0.0) < opts.strong_wall_strength:
        return None

    score = _base_score(f)
    score += 5.0 * int(f.get("defense_count") or 0)
    score -= 5.0 * int(f.get("weaken_count")  or 0)
    if f.get("status") == FS_DEFENDED:
        score += 5.0
    score = max(0.0, min(100.0, score))
    if score < opts.min_score:
        return None

    conf = _setup_confidence(score, float(f.get("confidence") or 0.0))
    reasons = [
        f"ask wall at {f.get('price_mid')} with strength {f.get('current_strength')}",
        f"persistence {f.get('persistence_seconds')}s, status {f.get('status')}",
    ]
    if f.get("defense_count"):
        reasons.append(f"{f['defense_count']} prior defenses on this level")
    risks: list[str] = []
    if f.get("weaken_count"):
        risks.append(f"{f['weaken_count']} weakening events seen")
    if not _is_near_price(f, opts.near_price_distance_pct):
        risks.append("wall not consistently near price during its lifetime")

    return _make_setup(
        setup_type=ST_SHORT_REJECTION,
        direction=DIR_SHORT,
        symbol=f.get("symbol", ""), exchange=f.get("exchange", ""),
        timeframe=f.get("timeframe", ""), setup_ts=setup_ts,
        primary_wall=f, related_walls=None,
        score=score, confidence=conf,
        status=_absorption_status(f.get("status", "")),
        reasons=reasons, risks=risks,
        metadata={
            "feature_status":  f.get("status"),
            "defense_count":   f.get("defense_count"),
            "touch_count":     f.get("touch_count"),
            "weaken_count":    f.get("weaken_count"),
            "current_strength": f.get("current_strength"),
        },
    )


def _build_breakout_pressure(f: dict, opts: SetupClassifierOptions, setup_ts: str) -> dict | None:
    if f.get("status") not in (FS_BROKEN, FS_PULLED, FS_WEAKENING):
        return None
    if float(f.get("max_strength") or 0.0) < opts.strong_wall_strength:
        return None
    if not _qualifies_min(f, opts):
        return None

    # Direction inference: a broken BID floor → short pressure (price fell);
    # a broken ASK ceiling → long pressure (price rose). Pulled / weakening
    # don't carry a clean direction → neutral.
    side = f.get("side")
    status = f.get("status")
    if status == FS_BROKEN:
        direction = DIR_SHORT if side == "bid" else DIR_LONG
    else:
        direction = DIR_NEUTRAL

    score = _base_score(f)
    score += 10.0 * int(f.get("break_count") or 0)
    score += 5.0  * int(f.get("pull_count")  or 0)
    # Use max_strength to reward walls that were genuinely significant.
    score += 0.1 * float(f.get("max_strength") or 0.0)
    score = max(0.0, min(100.0, score))
    if score < opts.min_score:
        return None

    conf = _setup_confidence(score, float(f.get("confidence") or 0.0))
    reasons = [
        f"{side} wall at {f.get('price_mid')} now {status}",
        f"prior max strength {f.get('max_strength')}, persistence {f.get('persistence_seconds')}s",
    ]
    if f.get("break_count"):
        reasons.append(f"{f['break_count']} break events")
    risks: list[str] = ["breakouts can fail; confirm with follow-through"]
    if status == FS_PULLED:
        risks.append("wall was pulled, not necessarily a breakout — direction is neutral")

    return _make_setup(
        setup_type=ST_BREAKOUT_PRESSURE,
        direction=direction,
        symbol=f.get("symbol", ""), exchange=f.get("exchange", ""),
        timeframe=f.get("timeframe", ""), setup_ts=setup_ts,
        primary_wall=f, related_walls=None,
        score=score, confidence=conf,
        status=_breakout_status(f.get("status", "")),
        reasons=reasons, risks=risks,
        metadata={
            "feature_status": status,
            "side":           side,
            "max_strength":   f.get("max_strength"),
            "break_count":    f.get("break_count"),
            "pull_count":     f.get("pull_count"),
        },
    )


def _build_failed_defense_trap(f: dict, opts: SetupClassifierOptions, setup_ts: str) -> dict | None:
    """
    Trigger A for liquidity_trap_risk: a wall that was broken/pulled AFTER
    several touches/defenses — i.e. a level that looked strong but ultimately
    failed. High trap potential for late traders.
    """
    if f.get("status") not in (FS_BROKEN, FS_PULLED):
        return None
    if not _qualifies_min(f, opts):
        return None
    history_count = int(f.get("defense_count") or 0) + int(f.get("touch_count") or 0)
    if history_count < opts.trap_min_history_count:
        return None

    score = _base_score(f)
    score += 5.0 * history_count
    score += 5.0 * int(f.get("break_count") or 0)
    score = max(0.0, min(100.0, score))
    if score < opts.min_score:
        return None

    conf = _setup_confidence(score, float(f.get("confidence") or 0.0))
    reasons = [
        f"{f.get('side')} wall at {f.get('price_mid')} {f.get('status')} after "
        f"{history_count} prior tests",
    ]
    if f.get("break_count"):
        reasons.append("multiple break events on this level")
    risks = [
        "wall failed despite repeated defenses — high trap potential",
        "do not chase reversion until structure rebuilds",
    ]
    return _make_setup(
        setup_type=ST_LIQUIDITY_TRAP_RISK,
        direction=DIR_NEUTRAL,
        symbol=f.get("symbol", ""), exchange=f.get("exchange", ""),
        timeframe=f.get("timeframe", ""), setup_ts=setup_ts,
        primary_wall=f, related_walls=None,
        score=score, confidence=conf,
        status=STATUS_CANDIDATE,
        reasons=reasons, risks=risks,
        metadata={
            "trigger":         "failed_defense",
            "feature_status":  f.get("status"),
            "defense_count":   f.get("defense_count"),
            "touch_count":     f.get("touch_count"),
            "break_count":     f.get("break_count"),
        },
    )


def _build_conflict_trap(
    bid_anchor: dict | None,
    ask_anchor: dict | None,
    opts: SetupClassifierOptions,
    setup_ts: str,
) -> dict | None:
    """
    Trigger B for liquidity_trap_risk: a qualifying bid wall AND a
    qualifying ask wall exist with similar strength — a range / chop
    environment where fake breaks in either direction are likely.
    """
    if bid_anchor is None or ask_anchor is None:
        return None
    bid_s = float(bid_anchor.get("current_strength") or 0.0)
    ask_s = float(ask_anchor.get("current_strength") or 0.0)
    if max(bid_s, ask_s) <= 0:
        return None
    diff_pct = abs(bid_s - ask_s) / max(bid_s, ask_s) * 100.0
    if diff_pct > opts.conflict_strength_pct:
        return None

    # Combined score: average base score + bonus for proximity in strength.
    avg_score = (_base_score(bid_anchor) + _base_score(ask_anchor)) / 2.0
    avg_score += max(0.0, 10.0 - diff_pct / 3.0)
    avg_score = max(0.0, min(100.0, avg_score))
    if avg_score < opts.min_score:
        return None

    primary = bid_anchor if bid_s >= ask_s else ask_anchor
    other   = ask_anchor if bid_s >= ask_s else bid_anchor
    conf = _setup_confidence(
        avg_score,
        (float(bid_anchor.get("confidence") or 0.0)
         + float(ask_anchor.get("confidence") or 0.0)) / 2.0,
    )
    reasons = [
        f"bid wall strength {bid_s} vs ask wall strength {ask_s} "
        f"(within {diff_pct:.1f}% of each other)",
        "balanced walls suggest range; fake breakouts likely",
    ]
    risks = [
        "neither side has clear control",
        "stops sit on the obvious side — trap potential",
    ]
    return _make_setup(
        setup_type=ST_LIQUIDITY_TRAP_RISK,
        direction=DIR_NEUTRAL,
        symbol=primary.get("symbol", ""), exchange=primary.get("exchange", ""),
        timeframe=primary.get("timeframe", ""), setup_ts=setup_ts,
        primary_wall=primary, related_walls=[other],
        score=avg_score, confidence=conf,
        status=STATUS_CANDIDATE,
        reasons=reasons, risks=risks,
        metadata={
            "trigger":         "balanced_walls",
            "bid_strength":    bid_s,
            "ask_strength":    ask_s,
            "diff_pct":        round(diff_pct, 3),
        },
    )


# ── Public entry ─────────────────────────────────────────────────────────────

def classify_setups(
    features: Iterable[dict] | None,
    *,
    options: SetupClassifierOptions | None = None,
) -> list[dict]:
    """
    Classify LM47 wall persistence features into trading setup candidates.

    Returns a deterministic list of setup dicts (possibly empty). Never
    raises on `None` / malformed input — bad feature dicts are skipped.
    """
    opts = options or SetupClassifierOptions()
    if not features:
        return []

    valid = [f for f in features if _valid_feature(f)]
    if not valid:
        return []

    # Group by market: (symbol, exchange, timeframe).
    markets: dict[tuple[str, str, str], list[dict]] = {}
    for f in valid:
        key = (
            f.get("symbol", "") or "",
            f.get("exchange", "") or "",
            f.get("timeframe", "") or "",
        )
        markets.setdefault(key, []).append(f)

    all_setups: list[dict] = []
    for (sym, ex, tf), feats in markets.items():
        setup_ts = _ordered_seen_ts(feats)

        # Per-wall candidates.
        market_setups: list[dict] = []
        for f in feats:
            for builder in (_build_long_absorption,
                            _build_short_rejection,
                            _build_breakout_pressure,
                            _build_failed_defense_trap):
                setup = builder(f, opts, setup_ts)
                if setup is not None:
                    market_setups.append(setup)

        # Conflict trap: needs strongest qualifying bid anchor + ask anchor.
        bid_anchors = [
            f for f in feats
            if f.get("side") == "bid"
            and f.get("status") in (FS_DEFENDED, FS_ACTIVE)
            and float(f.get("current_strength") or 0.0) >= opts.strong_wall_strength
            and _qualifies_min(f, opts)
        ]
        ask_anchors = [
            f for f in feats
            if f.get("side") == "ask"
            and f.get("status") in (FS_DEFENDED, FS_ACTIVE)
            and float(f.get("current_strength") or 0.0) >= opts.strong_wall_strength
            and _qualifies_min(f, opts)
        ]
        if bid_anchors and ask_anchors:
            bid_anchor = max(bid_anchors, key=lambda x: float(x.get("current_strength") or 0.0))
            ask_anchor = max(ask_anchors, key=lambda x: float(x.get("current_strength") or 0.0))
            ct = _build_conflict_trap(bid_anchor, ask_anchor, opts, setup_ts)
            if ct is not None:
                market_setups.append(ct)

        if not market_setups:
            # Emit no_trade so callers can record that we inspected this
            # market but nothing qualified.
            market_setups.append(_make_setup(
                setup_type=ST_NO_TRADE,
                direction=DIR_NEUTRAL,
                symbol=sym, exchange=ex, timeframe=tf, setup_ts=setup_ts,
                primary_wall=None, related_walls=feats,
                score=0.0, confidence=0.0,
                status=STATUS_NO_TRADE,
                reasons=["no wall feature met actionable thresholds"],
                risks=["features present but score/strength/persistence too low"],
                metadata={
                    "feature_count":      len(feats),
                    "feature_statuses":   sorted({f.get("status", "") for f in feats}),
                },
            ))

        all_setups.extend(market_setups)

    all_setups.sort(key=lambda s: (
        s["symbol"], s["timeframe"], s["setup_type"],
        s["direction"], s["price_zone_mid"],
    ))
    return all_setups
