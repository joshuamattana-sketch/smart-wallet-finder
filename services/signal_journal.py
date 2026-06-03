"""
services/signal_journal.py
---------------------------
LM50 — Signal journal foundation.

Pure-Python, dependency-light layer that turns LM49 standardized signal
dicts into "journal entry" dicts. The journal is the system of record for:

  * what signals we emitted (entry, invalidation, targets, hints)
  * how each one resolved over time (outcome tracking)
  * aggregate stats for evaluating signal quality

No I/O, no Supabase, no network, no file writes. Persistence is a later
milestone — this module is the in-memory contract that future writers /
loaders / API routes will read from.

Public entry
~~~~~~~~~~~~
    create_signal_journal_entry(signal, *, created_at=None) -> dict | None
    create_signal_journal_entries(signals, *, created_at=None) -> list[dict]
    update_signal_outcome(entry, outcome) -> dict
    summarize_signal_journal(entries) -> dict

Outcome statuses
~~~~~~~~~~~~~~~~
    pending      — actionable signal awaiting price action
    target_hit   — at least one target was reached
    invalidated  — invalidation price was hit before any target
    expired      — neither hit nor invalidated within the watch window
    no_trade     — informational signal (LM49 no_trade); no outcome to track
    unknown      — explicit "we can't tell" (e.g. data gap)
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Iterable


# ── Outcome statuses ─────────────────────────────────────────────────────────

OUTCOME_PENDING     = "pending"
OUTCOME_TARGET_HIT  = "target_hit"
OUTCOME_INVALIDATED = "invalidated"
OUTCOME_EXPIRED     = "expired"
OUTCOME_NO_TRADE    = "no_trade"
OUTCOME_UNKNOWN     = "unknown"

VALID_OUTCOME_STATUSES = (
    OUTCOME_PENDING, OUTCOME_TARGET_HIT, OUTCOME_INVALIDATED,
    OUTCOME_EXPIRED, OUTCOME_NO_TRADE, OUTCOME_UNKNOWN,
)


# ── Signal-level + direction constants we recognize (mirror of LM49) ─────────

LEVEL_NO_TRADE     = "no_trade"
LEVEL_WATCH        = "watch"
LEVEL_SETUP        = "setup"
LEVEL_STRONG_SETUP = "strong_setup"

VALID_SIGNAL_LEVELS = (LEVEL_NO_TRADE, LEVEL_WATCH, LEVEL_SETUP, LEVEL_STRONG_SETUP)

DIR_LONG    = "long"
DIR_SHORT   = "short"
DIR_NEUTRAL = "neutral"

VALID_DIRECTIONS = (DIR_LONG, DIR_SHORT, DIR_NEUTRAL)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _is_number(v: object) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _valid_signal(s: object) -> bool:
    """Conservative shape check — malformed signals are skipped."""
    if not isinstance(s, dict):
        return False
    if not isinstance(s.get("signal_id"), str) or not s["signal_id"]:
        return False
    if s.get("signal_level") not in VALID_SIGNAL_LEVELS:
        return False
    if s.get("direction") not in VALID_DIRECTIONS:
        return False
    for k in ("score", "confidence",
              "entry_zone_low", "entry_zone_high", "entry_zone_mid"):
        if not _is_number(s.get(k)):
            return False
    return True


def _journal_id(signal_id: str) -> str:
    """
    Deterministic. One journal entry per signal_id. The signal_id already
    encodes (setup_id, signal_level, direction) so any level change creates
    a new signal_id and therefore a new journal entry.
    """
    h = hashlib.sha1(signal_id.encode("utf-8")).hexdigest()[:12]
    return f"journal_{h}"


def _initial_outcome_status(signal: dict) -> str:
    """no_trade signals never produce a trade; everything else starts pending."""
    if signal.get("signal_level") == LEVEL_NO_TRADE:
        return OUTCOME_NO_TRADE
    if signal.get("direction") == DIR_NEUTRAL:
        return OUTCOME_NO_TRADE
    return OUTCOME_PENDING


# ── Creation ─────────────────────────────────────────────────────────────────

def create_signal_journal_entry(
    signal: dict | None,
    *,
    created_at: str | None = None,
) -> dict | None:
    """
    Build one journal entry from an LM49 signal. Returns None for malformed
    input so callers can map+filter without crashing.
    """
    if not _valid_signal(signal):
        return None

    assert isinstance(signal, dict)  # narrowed by _valid_signal
    ts = created_at or _now_iso()
    targets = signal.get("targets") or []
    if not isinstance(targets, list):
        targets = []
    invalidation = signal.get("invalidation_price")
    if not (invalidation is None or _is_number(invalidation)):
        invalidation = None

    return {
        "journal_id":          _journal_id(signal["signal_id"]),
        "signal_id":           signal["signal_id"],
        "symbol":              signal.get("symbol", "") or "",
        "exchange":            signal.get("exchange", "") or "",
        "timeframe":           signal.get("timeframe", "") or "",
        "created_at":          ts,
        "signal_ts":           signal.get("signal_ts", "") or "",
        "setup_type":          signal.get("setup_type", "") or "",
        "direction":           signal["direction"],
        "signal_level":        signal["signal_level"],
        "score":               round(max(0.0, min(100.0, float(signal["score"]))), 3),
        "confidence":          round(max(0.0, min(1.0, float(signal["confidence"]))), 3),
        "entry_zone_low":      round(float(signal["entry_zone_low"]),  4),
        "entry_zone_high":     round(float(signal["entry_zone_high"]), 4),
        "entry_zone_mid":      round(float(signal["entry_zone_mid"]),  4),
        "invalidation_price":  invalidation,
        "targets":             list(targets),
        "reasons":             list(signal.get("reasons") or []),
        "risks":               list(signal.get("risks")   or []),
        "action_hint":         signal.get("action_hint", "") or "",
        "status":              signal.get("status", "") or "",
        # ── outcome tracking (initial state) ─────────────────────────────────
        "outcome_status":      _initial_outcome_status(signal),
        "outcome_checked_at":  None,
        "outcome_5m":          None,
        "outcome_15m":         None,
        "outcome_1h":          None,
        "max_favorable_excursion_pct": None,
        "max_adverse_excursion_pct":   None,
        "notes":               "",
        "metadata": {
            "signal_setup_id":    signal.get("setup_id"),
            "raw_score":          float(signal["score"]),
            "raw_confidence":     float(signal["confidence"]),
            "signal_metadata":    signal.get("metadata") or {},
        },
    }


def create_signal_journal_entries(
    signals: Iterable[dict] | None,
    *,
    created_at: str | None = None,
) -> list[dict]:
    """
    Build journal entries from many signals at once. Skips malformed
    signals; never raises. Output is sorted by
    (symbol, timeframe, direction, entry_zone_mid) for deterministic
    iteration.
    """
    if not signals:
        return []
    entries: list[dict] = []
    for s in signals:
        e = create_signal_journal_entry(s, created_at=created_at)
        if e is not None:
            entries.append(e)
    entries.sort(key=lambda e: (
        e["symbol"], e["timeframe"], e["direction"], e["entry_zone_mid"],
    ))
    return entries


# ── Outcome updates ──────────────────────────────────────────────────────────

# Fields a caller is allowed to set on an outcome update. Unknown keys are
# ignored so future fields can be added without breaking existing callers.
_OUTCOME_UPDATABLE_FIELDS = frozenset({
    "outcome_status",
    "outcome_checked_at",
    "outcome_5m",
    "outcome_15m",
    "outcome_1h",
    "max_favorable_excursion_pct",
    "max_adverse_excursion_pct",
    "notes",
})


def update_signal_outcome(entry: dict, outcome: dict | None) -> dict:
    """
    Return a NEW entry with outcome fields merged in. The input entry is
    never mutated. Unknown outcome fields are silently ignored. If
    `outcome_status` is provided it must be one of `VALID_OUTCOME_STATUSES`
    — otherwise we leave the existing status untouched.

    If the entry has `outcome_status="no_trade"`, status updates are
    rejected (informational entries stay informational), but excursion /
    notes can still be appended.
    """
    if not isinstance(entry, dict):
        raise TypeError(f"entry must be a dict, got {type(entry).__name__!r}")

    merged = dict(entry)  # shallow copy is fine — we replace fields wholesale
    if not isinstance(outcome, dict) or not outcome:
        return merged

    is_no_trade = merged.get("outcome_status") == OUTCOME_NO_TRADE

    for k, v in outcome.items():
        if k not in _OUTCOME_UPDATABLE_FIELDS:
            continue
        if k == "outcome_status":
            if v not in VALID_OUTCOME_STATUSES:
                continue
            if is_no_trade and v != OUTCOME_NO_TRADE:
                continue  # don't promote no_trade entries to tracked statuses
            merged["outcome_status"] = v
        elif k == "notes":
            if isinstance(v, str):
                merged["notes"] = v
        elif k in ("max_favorable_excursion_pct", "max_adverse_excursion_pct"):
            if _is_number(v):
                merged[k] = round(float(v), 4)
        elif k == "outcome_checked_at":
            if isinstance(v, str) and v:
                merged["outcome_checked_at"] = v
        else:  # outcome_5m / 15m / 1h — accept anything, caller decides shape
            merged[k] = v

    return merged


# ── Summary ──────────────────────────────────────────────────────────────────

def summarize_signal_journal(
    entries: Iterable[dict] | None,
) -> dict:
    """
    Aggregate stats over a list of journal entries. Returns a dict with:

      * total_entries (int)
      * by_direction       (dict[str,int], ordered keys)
      * by_signal_level    (dict[str,int])
      * by_outcome_status  (dict[str,int])
      * by_setup_type      (dict[str,int])
      * by_symbol          (dict[str,int])
      * actionable_count   (int — strong_setup / setup with non-no_trade outcome)
      * resolution_rate    (float 0–1 — share of pending entries that have moved)

    Sub-counters always include every valid bucket as a key (zero-filled)
    so consumers don't have to handle missing keys.
    """
    direction_keys     = list(VALID_DIRECTIONS)
    level_keys         = list(VALID_SIGNAL_LEVELS)
    outcome_keys       = list(VALID_OUTCOME_STATUSES)

    by_direction:      dict[str, int] = {k: 0 for k in direction_keys}
    by_signal_level:   dict[str, int] = {k: 0 for k in level_keys}
    by_outcome_status: dict[str, int] = {k: 0 for k in outcome_keys}
    by_setup_type:     dict[str, int] = {}
    by_symbol:         dict[str, int] = {}

    total = 0
    actionable = 0
    resolved = 0
    pending_or_resolved = 0

    if entries:
        for e in entries:
            if not isinstance(e, dict):
                continue
            # An entry must have a journal_id to be a real LM50 row — this
            # filters out empty dicts and other dict-ish junk callers might
            # pass in by accident.
            if not isinstance(e.get("journal_id"), str) or not e["journal_id"]:
                continue
            total += 1

            d = e.get("direction")
            if d in by_direction:
                by_direction[d] += 1

            lvl = e.get("signal_level")
            if lvl in by_signal_level:
                by_signal_level[lvl] += 1

            outc = e.get("outcome_status")
            if outc in by_outcome_status:
                by_outcome_status[outc] += 1

            st = e.get("setup_type") or ""
            if st:
                by_setup_type[st] = by_setup_type.get(st, 0) + 1

            sym = e.get("symbol") or ""
            if sym:
                by_symbol[sym] = by_symbol.get(sym, 0) + 1

            # actionable = level setup/strong_setup AND outcome not no_trade
            if lvl in (LEVEL_SETUP, LEVEL_STRONG_SETUP) and outc != OUTCOME_NO_TRADE:
                actionable += 1
            if outc in (OUTCOME_PENDING, OUTCOME_TARGET_HIT,
                        OUTCOME_INVALIDATED, OUTCOME_EXPIRED):
                pending_or_resolved += 1
                if outc != OUTCOME_PENDING:
                    resolved += 1

    resolution_rate = (resolved / pending_or_resolved) if pending_or_resolved else 0.0

    return {
        "total_entries":     total,
        "by_direction":      dict(sorted(by_direction.items())),
        "by_signal_level":   dict(sorted(by_signal_level.items())),
        "by_outcome_status": dict(sorted(by_outcome_status.items())),
        "by_setup_type":     dict(sorted(by_setup_type.items())),
        "by_symbol":         dict(sorted(by_symbol.items())),
        "actionable_count":  actionable,
        "resolution_rate":   round(resolution_rate, 4),
    }
