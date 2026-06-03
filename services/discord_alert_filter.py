"""
services/discord_alert_filter.py
---------------------------------
LM51C — Discord alert filter.

Pure-Python decision helper that says whether an LM49 signal (or LM50
journal entry — same surface) should be sent to Discord. No I/O, no
network, no UI.

Public entry
~~~~~~~~~~~~
    should_send_discord_alert(signal_or_journal_entry, options=None) -> dict

Returns:

    {
        "should_send":  bool,
        "reason":       str,    # short machine-friendly reason code
        "signal_level": str,
        "score":        float,  # 0.0 when missing
        "confidence":   float,  # 0.0 when missing
        "cooldown_key": str,    # deterministic; empty on invalid input
    }

Decision rules (in order)
~~~~~~~~~~~~~~~~~~~~~~~~~
1. Invalid input (non-dict or missing symbol) → block.
2. Symbol in `blocked_symbols`               → block.
3. `allowed_symbols` set AND symbol not in it → block.
4. setup status == "invalidated"              → block.
5. signal_level == "no_trade"  → send iff `send_no_trade`.
6. signal_level == "watch"     → send iff `send_watch`.
7. signal_level == "strong_setup" → send (auto).
8. signal_level == "setup" → send iff score ≥ `min_score`
   AND confidence ≥ `min_confidence`.
9. Anything else → block (unknown level).

The function is fully deterministic and never raises.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any


# ── Signal levels we recognize ───────────────────────────────────────────────

LEVEL_NO_TRADE     = "no_trade"
LEVEL_WATCH        = "watch"
LEVEL_SETUP        = "setup"
LEVEL_STRONG_SETUP = "strong_setup"

VALID_SIGNAL_LEVELS = (
    LEVEL_NO_TRADE, LEVEL_WATCH, LEVEL_SETUP, LEVEL_STRONG_SETUP,
)


# ── Options ──────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class DiscordAlertFilterOptions:
    """
    Tunable knobs. Defaults are conservative: strong_setup sends; setup
    needs score ≥ 70 AND confidence ≥ 0.6; watch and no_trade are silent
    unless explicitly enabled.

    `allowed_symbols` / `blocked_symbols` are case-insensitive. When
    `allowed_symbols` is non-empty, ONLY those symbols are allowed.
    """
    send_watch:       bool                = False
    send_no_trade:    bool                = False
    min_score:        float               = 70.0
    min_confidence:   float               = 0.60
    allowed_symbols:  tuple[str, ...] | None = None
    blocked_symbols:  tuple[str, ...] | None = None


# ── Helpers ──────────────────────────────────────────────────────────────────

def _is_number(v: object) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _safe_str(v: object, *, default: str = "") -> str:
    return v if isinstance(v, str) else default


def _num(v: object, *, default: float = 0.0) -> float:
    if _is_number(v):
        return float(v)
    return default


def _cooldown_key(
    symbol: str, exchange: str, timeframe: str,
    setup_type: str, direction: str,
) -> str:
    """Deterministic short hash of the dedupe tuple."""
    base = f"{symbol}|{exchange}|{timeframe}|{setup_type}|{direction}"
    h = hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]
    return f"cooldown_{h}"


def _normalize_symbol_list(syms: Any) -> tuple[str, ...] | None:
    if syms is None:
        return None
    if not isinstance(syms, (list, tuple, set, frozenset)):
        return None
    out = tuple(sorted({
        s.strip().upper()
        for s in syms
        if isinstance(s, str) and s.strip()
    }))
    return out if out else None


def _result(
    *, should_send: bool, reason: str,
    level: str, score: float, confidence: float,
    cooldown_key: str,
) -> dict:
    return {
        "should_send":  bool(should_send),
        "reason":       reason,
        "signal_level": level,
        "score":        round(max(0.0, min(100.0, score)), 3),
        "confidence":   round(max(0.0, min(1.0,  confidence)), 3),
        "cooldown_key": cooldown_key,
    }


# ── Public entry ─────────────────────────────────────────────────────────────

def should_send_discord_alert(
    signal_or_journal_entry: Any,
    options: DiscordAlertFilterOptions | None = None,
) -> dict:
    """
    Decide whether to send an alert for the given LM49 signal or LM50
    journal entry. Never raises. The output dict is fully deterministic
    for the same input.
    """
    opts = options or DiscordAlertFilterOptions()

    # ── 1. Input shape ──────────────────────────────────────────────────────
    if not isinstance(signal_or_journal_entry, dict):
        return _result(
            should_send=False, reason="invalid_input",
            level="", score=0.0, confidence=0.0, cooldown_key="",
        )

    s = signal_or_journal_entry
    symbol     = _safe_str(s.get("symbol")).strip().upper()
    exchange   = _safe_str(s.get("exchange"))
    timeframe  = _safe_str(s.get("timeframe"))
    setup_type = _safe_str(s.get("setup_type"))
    direction  = _safe_str(s.get("direction"))
    level      = _safe_str(s.get("signal_level"))
    status     = _safe_str(s.get("status"))
    score      = _num(s.get("score"))
    confidence = _num(s.get("confidence"))

    if not symbol:
        return _result(
            should_send=False, reason="missing_symbol",
            level=level, score=score, confidence=confidence, cooldown_key="",
        )

    cooldown = _cooldown_key(symbol, exchange, timeframe, setup_type, direction)

    # ── 2. Block list ───────────────────────────────────────────────────────
    blocked = _normalize_symbol_list(opts.blocked_symbols)
    if blocked is not None and symbol in blocked:
        return _result(
            should_send=False, reason="symbol_blocked",
            level=level, score=score, confidence=confidence,
            cooldown_key=cooldown,
        )

    # ── 3. Allow list ───────────────────────────────────────────────────────
    allowed = _normalize_symbol_list(opts.allowed_symbols)
    if allowed is not None and symbol not in allowed:
        return _result(
            should_send=False, reason="symbol_not_allowed",
            level=level, score=score, confidence=confidence,
            cooldown_key=cooldown,
        )

    # ── 4. Invalidated setups are silent regardless of level ────────────────
    if status == "invalidated":
        return _result(
            should_send=False, reason="setup_invalidated",
            level=level, score=score, confidence=confidence,
            cooldown_key=cooldown,
        )

    # ── 5. no_trade ─────────────────────────────────────────────────────────
    if level == LEVEL_NO_TRADE:
        if opts.send_no_trade:
            return _result(
                should_send=True, reason="no_trade_enabled",
                level=level, score=score, confidence=confidence,
                cooldown_key=cooldown,
            )
        return _result(
            should_send=False, reason="no_trade_disabled",
            level=level, score=score, confidence=confidence,
            cooldown_key=cooldown,
        )

    # ── 6. watch ────────────────────────────────────────────────────────────
    if level == LEVEL_WATCH:
        if opts.send_watch:
            return _result(
                should_send=True, reason="watch_enabled",
                level=level, score=score, confidence=confidence,
                cooldown_key=cooldown,
            )
        return _result(
            should_send=False, reason="watch_disabled",
            level=level, score=score, confidence=confidence,
            cooldown_key=cooldown,
        )

    # ── 7. strong_setup ─────────────────────────────────────────────────────
    if level == LEVEL_STRONG_SETUP:
        return _result(
            should_send=True, reason="strong_setup_auto_send",
            level=level, score=score, confidence=confidence,
            cooldown_key=cooldown,
        )

    # ── 8. setup — must clear score AND confidence thresholds ───────────────
    if level == LEVEL_SETUP:
        if score < opts.min_score:
            return _result(
                should_send=False, reason="setup_low_score",
                level=level, score=score, confidence=confidence,
                cooldown_key=cooldown,
            )
        if confidence < opts.min_confidence:
            return _result(
                should_send=False, reason="setup_low_confidence",
                level=level, score=score, confidence=confidence,
                cooldown_key=cooldown,
            )
        return _result(
            should_send=True, reason="setup_above_thresholds",
            level=level, score=score, confidence=confidence,
            cooldown_key=cooldown,
        )

    # ── 9. Unknown level → silent ───────────────────────────────────────────
    return _result(
        should_send=False, reason="unknown_signal_level",
        level=level, score=score, confidence=confidence,
        cooldown_key=cooldown,
    )
