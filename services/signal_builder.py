"""
services/signal_builder.py
---------------------------
LM49 — Signal object builder v1.

Pure-Python builder that turns LM48 setup candidates into standardized
trading signal dicts. No I/O, no Supabase, no network — safe to call
from tests, the WS collector, a cron job, or an API route.

Public entry
~~~~~~~~~~~~
    build_signals(setups, *, options=None) -> list[dict]

Each input setup produces exactly one signal. Setup `no_trade` rows
become `no_trade` signals (so callers can record that a market was
inspected and decided against).

Signal levels (derived from setup score + confidence):
    no_trade      — below `watch_score` or below `min_confidence`
    watch         — `watch_score` ≤ score < `setup_score`
    setup         — `setup_score` ≤ score < `strong_setup_score`
    strong_setup  — score ≥ `strong_setup_score`

Statuses:
    active        — actionable level (setup / strong_setup) and not invalidated
    waiting       — watch level OR neutral direction
    invalidated   — underlying setup status == "invalidated"
    no_trade      — setup_type == "no_trade" OR level == "no_trade"

Determinism
~~~~~~~~~~~
* Output sorted by (symbol, timeframe, setup_type, direction, entry_zone_mid).
* `signal_id` is a stable hash of (setup_id, signal_level, direction).
* `None` / empty / malformed inputs return `[]` and never raise.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Iterable


# ── Direction constants (mirror of LM48) ─────────────────────────────────────

DIR_LONG    = "long"
DIR_SHORT   = "short"
DIR_NEUTRAL = "neutral"

VALID_DIRECTIONS = (DIR_LONG, DIR_SHORT, DIR_NEUTRAL)

# ── Signal levels ────────────────────────────────────────────────────────────

LEVEL_NO_TRADE     = "no_trade"
LEVEL_WATCH        = "watch"
LEVEL_SETUP        = "setup"
LEVEL_STRONG_SETUP = "strong_setup"

VALID_SIGNAL_LEVELS = (
    LEVEL_NO_TRADE, LEVEL_WATCH, LEVEL_SETUP, LEVEL_STRONG_SETUP,
)

# ── Signal statuses ──────────────────────────────────────────────────────────

STATUS_ACTIVE      = "active"
STATUS_WAITING     = "waiting"
STATUS_NO_TRADE    = "no_trade"
STATUS_INVALIDATED = "invalidated"

VALID_STATUSES = (
    STATUS_ACTIVE, STATUS_WAITING, STATUS_NO_TRADE, STATUS_INVALIDATED,
)

# ── Action hints (free-text but constrained) ─────────────────────────────────

HINT_WAIT_FOR_CONFIRMATION = "wait_for_confirmation"
HINT_WAIT_FOR_RETEST       = "wait_for_retest"
HINT_MONITOR_ONLY          = "monitor_only"
HINT_AVOID_TRADE           = "avoid_trade"

VALID_ACTION_HINTS = (
    HINT_WAIT_FOR_CONFIRMATION, HINT_WAIT_FOR_RETEST,
    HINT_MONITOR_ONLY, HINT_AVOID_TRADE,
)

# ── Setup-type and setup-status constants we recognize (LM48 surface) ────────

ST_LONG_ABSORPTION     = "long_absorption"
ST_SHORT_REJECTION     = "short_rejection"
ST_BREAKOUT_PRESSURE   = "breakout_pressure"
ST_LIQUIDITY_TRAP_RISK = "liquidity_trap_risk"
ST_NO_TRADE            = "no_trade"

SUS_CANDIDATE   = "candidate"
SUS_CONFIRMED   = "confirmed"
SUS_INVALIDATED = "invalidated"
SUS_NO_TRADE    = "no_trade"


# ── Options ──────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SignalBuilderOptions:
    """Tunable thresholds for `build_signals`."""
    watch_score:             float = 30.0
    setup_score:             float = 50.0
    strong_setup_score:      float = 70.0
    min_confidence:          float = 0.40
    target_r_multiple_1:     float = 1.5
    target_r_multiple_2:     float = 3.0
    invalidation_buffer_pct: float = 0.20   # % of price; placed outside zone edge


# ── Helpers ──────────────────────────────────────────────────────────────────

def _is_number(v: object) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _valid_setup(s: object) -> bool:
    """Conservative shape check — malformed setups are skipped."""
    if not isinstance(s, dict):
        return False
    if not isinstance(s.get("setup_id"), str) or not s["setup_id"]:
        return False
    if s.get("setup_type") not in (ST_LONG_ABSORPTION, ST_SHORT_REJECTION,
                                    ST_BREAKOUT_PRESSURE, ST_LIQUIDITY_TRAP_RISK,
                                    ST_NO_TRADE):
        return False
    if s.get("direction") not in VALID_DIRECTIONS:
        return False
    for k in ("score", "confidence",
              "price_zone_low", "price_zone_high", "price_zone_mid"):
        if not _is_number(s.get(k)):
            return False
    return True


def _signal_id(setup_id: str, level: str, direction: str) -> str:
    base = f"{setup_id}|{level}|{direction}"
    h = hashlib.sha1(base.encode("utf-8")).hexdigest()[:12]
    return f"sig_{h}"


def _level_for(score: float, confidence: float, opts: SignalBuilderOptions) -> str:
    """Map (score, confidence) to one of the four signal levels."""
    if confidence < opts.min_confidence:
        return LEVEL_NO_TRADE
    if score >= opts.strong_setup_score:
        return LEVEL_STRONG_SETUP
    if score >= opts.setup_score:
        return LEVEL_SETUP
    if score >= opts.watch_score:
        return LEVEL_WATCH
    return LEVEL_NO_TRADE


def _action_hint_for(level: str, direction: str, setup_type: str) -> str:
    """
    Pick a human-readable hint. Directional strong_setup retest-style for
    defended/rejected walls, confirmation-style for breakouts. Neutral and
    sub-actionable levels get monitor/avoid.
    """
    if level == LEVEL_NO_TRADE:
        return HINT_AVOID_TRADE
    if direction == DIR_NEUTRAL or setup_type == ST_LIQUIDITY_TRAP_RISK:
        return HINT_MONITOR_ONLY
    if level == LEVEL_WATCH:
        return HINT_MONITOR_ONLY
    if level == LEVEL_STRONG_SETUP and setup_type in (
        ST_LONG_ABSORPTION, ST_SHORT_REJECTION,
    ):
        # A strong defended floor/ceiling is best entered on a retest.
        return HINT_WAIT_FOR_RETEST
    return HINT_WAIT_FOR_CONFIRMATION


def _status_for(
    level: str, direction: str, setup_status: str,
) -> str:
    if setup_status == SUS_INVALIDATED:
        return STATUS_INVALIDATED
    if level == LEVEL_NO_TRADE:
        return STATUS_NO_TRADE
    if direction == DIR_NEUTRAL:
        return STATUS_WAITING
    if level == LEVEL_WATCH:
        return STATUS_WAITING
    return STATUS_ACTIVE


def _zone_geometry(
    direction: str,
    zone_low: float, zone_high: float, zone_mid: float,
    opts: SignalBuilderOptions,
) -> tuple[float | None, list[float]]:
    """
    Compute (invalidation_price, [target_1, target_2]) for an actionable
    directional signal. Returns (None, []) for neutral / unbounded zones.
    """
    if direction not in (DIR_LONG, DIR_SHORT):
        return None, []
    if zone_high <= zone_low:
        return None, []

    buf = abs(zone_mid) * opts.invalidation_buffer_pct / 100.0
    if direction == DIR_LONG:
        invalidation = zone_low - buf
        r = max(0.0, zone_mid - invalidation)
        if r <= 0:
            return invalidation, []
        targets = [
            round(zone_mid + r * opts.target_r_multiple_1, 4),
            round(zone_mid + r * opts.target_r_multiple_2, 4),
        ]
    else:  # short
        invalidation = zone_high + buf
        r = max(0.0, invalidation - zone_mid)
        if r <= 0:
            return invalidation, []
        targets = [
            round(zone_mid - r * opts.target_r_multiple_1, 4),
            round(zone_mid - r * opts.target_r_multiple_2, 4),
        ]
    return round(invalidation, 4), targets


# ── Public entry ─────────────────────────────────────────────────────────────

def build_signals(
    setups: Iterable[dict] | None,
    *,
    options: SignalBuilderOptions | None = None,
) -> list[dict]:
    """
    Turn LM48 setup candidates into standardized signal dicts. One signal
    per valid setup (including `no_trade` setups). Tolerant of malformed
    input — never raises.
    """
    opts = options or SignalBuilderOptions()
    if not setups:
        return []

    valid = [s for s in setups if _valid_setup(s)]
    if not valid:
        return []

    signals: list[dict] = []
    for s in valid:
        setup_id      = s["setup_id"]
        setup_type    = s["setup_type"]
        setup_status  = s.get("status") or ""
        direction     = s["direction"]
        score         = float(s.get("score") or 0.0)
        confidence    = float(s.get("confidence") or 0.0)
        zone_low      = float(s.get("price_zone_low")  or 0.0)
        zone_high     = float(s.get("price_zone_high") or 0.0)
        zone_mid      = float(s.get("price_zone_mid")  or 0.0)
        setup_ts      = s.get("setup_ts") or ""
        primary_wall  = s.get("primary_wall_id")
        related_walls = s.get("related_wall_ids") or []
        reasons       = list(s.get("reasons") or [])
        risks         = list(s.get("risks")   or [])

        # no_trade setups always map to no_trade signals — bypass score/conf
        # mapping entirely so a no_trade setup never gets a watch label.
        if setup_type == ST_NO_TRADE or setup_status == SUS_NO_TRADE:
            level     = LEVEL_NO_TRADE
            sig_dir   = DIR_NEUTRAL
            inval, targets = None, []
            action    = HINT_AVOID_TRADE
            status    = STATUS_NO_TRADE
        else:
            level = _level_for(score, confidence, opts)
            if level == LEVEL_NO_TRADE:
                sig_dir = DIR_NEUTRAL
                inval, targets = None, []
            else:
                sig_dir = direction
                if direction == DIR_NEUTRAL:
                    inval, targets = None, []
                else:
                    inval, targets = _zone_geometry(
                        direction, zone_low, zone_high, zone_mid, opts,
                    )
            action = _action_hint_for(level, sig_dir, setup_type)
            status = _status_for(level, sig_dir, setup_status)

        signal = {
            "signal_id":          _signal_id(setup_id, level, sig_dir),
            "symbol":             s.get("symbol", "") or "",
            "exchange":           s.get("exchange", "") or "",
            "timeframe":          s.get("timeframe", "") or "",
            "signal_ts":          setup_ts,
            "setup_id":           setup_id,
            "setup_type":         setup_type,
            "direction":          sig_dir,
            "signal_level":       level,
            "score":              round(max(0.0, min(100.0, score)), 3),
            "confidence":         round(max(0.0, min(1.0, confidence)), 3),
            "entry_zone_low":     round(zone_low,  4),
            "entry_zone_high":    round(zone_high, 4),
            "entry_zone_mid":     round(zone_mid,  4),
            "invalidation_price": inval,
            "targets":            targets,
            "reasons":            reasons,
            "risks":              risks,
            "action_hint":        action,
            "status":             status,
            "metadata": {
                "setup_status":      setup_status,
                "primary_wall_id":   primary_wall,
                "related_wall_ids":  list(related_walls),
                "raw_score":         score,
                "raw_confidence":    confidence,
            },
        }
        signals.append(signal)

    signals.sort(key=lambda x: (
        x["symbol"], x["timeframe"], x["setup_type"],
        x["direction"], x["entry_zone_mid"],
    ))
    return signals
