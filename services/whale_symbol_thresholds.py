"""
services/whale_symbol_thresholds.py
------------------------------------
LM63D — Per-symbol whale notional thresholds.

Different markets generate different "whale" notionals. A $250k BTC trade
is routine; a $250k LINK trade is an event. This module provides per-symbol
thresholds (with a safe default fallback) and a single lookup helper.

No network, no Supabase, no I/O. Pure data + a thin getter.

Public API:
    get_whale_thresholds_for_symbol(symbol, overrides=None) -> dict
    DEFAULT_THRESHOLDS      (read-only constant)
    SYMBOL_THRESHOLDS       (read-only constant)
"""

from __future__ import annotations

from typing import Any, Mapping

# Fields returned by get_whale_thresholds_for_symbol.
THRESHOLD_FIELDS: frozenset[str] = frozenset({
    "min_notional_usd",
    "high_notional_usd",
    "extreme_notional_usd",
    "min_confidence",
})


# ── Defaults ──────────────────────────────────────────────────────────────────

DEFAULT_THRESHOLDS: Mapping[str, float] = {
    "min_notional_usd":     100_000.0,
    "high_notional_usd":    500_000.0,
    "extreme_notional_usd": 1_000_000.0,
    "min_confidence":       0.6,
}


# Per-symbol presets. Anything not listed here falls back to DEFAULT_THRESHOLDS.
SYMBOL_THRESHOLDS: Mapping[str, Mapping[str, float]] = {
    "BTCUSDT":  {"min_notional_usd": 250_000.0, "high_notional_usd": 750_000.0,
                 "extreme_notional_usd": 2_000_000.0, "min_confidence": 0.6},
    "ETHUSDT":  {"min_notional_usd":  75_000.0, "high_notional_usd": 250_000.0,
                 "extreme_notional_usd": 1_000_000.0, "min_confidence": 0.6},
    "SOLUSDT":  {"min_notional_usd":  50_000.0, "high_notional_usd": 150_000.0,
                 "extreme_notional_usd":   500_000.0, "min_confidence": 0.6},
    "BNBUSDT":  {"min_notional_usd":  75_000.0, "high_notional_usd": 250_000.0,
                 "extreme_notional_usd":   750_000.0, "min_confidence": 0.6},
    "LINKUSDT": {"min_notional_usd":  25_000.0, "high_notional_usd": 100_000.0,
                 "extreme_notional_usd":   300_000.0, "min_confidence": 0.6},
    "DOGEUSDT": {"min_notional_usd":  25_000.0, "high_notional_usd": 100_000.0,
                 "extreme_notional_usd":   300_000.0, "min_confidence": 0.6},
}


# ── Public lookup ─────────────────────────────────────────────────────────────

def get_whale_thresholds_for_symbol(
    symbol: Any,
    overrides: Mapping[str, Mapping[str, float]] | None = None,
) -> dict:
    """
    Return whale thresholds for `symbol` as a plain (mutable) dict.

    Resolution order:
        1. `overrides[symbol_upper]` (if provided)         — caller-supplied
        2. `SYMBOL_THRESHOLDS[symbol_upper]`               — built-in preset
        3. `DEFAULT_THRESHOLDS`                            — safe fallback

    Per-field merging: when a tier provides a partial dict, missing fields
    fall through to the next tier. The returned dict always contains every
    field in `THRESHOLD_FIELDS`.

    Args:
        symbol:    Trading symbol (any case; non-string returns defaults).
        overrides: Optional mapping of `{symbol_upper: {field: value, ...}}`
                   that wins over the built-in preset.

    Returns:
        Plain dict with keys: ``min_notional_usd``, ``high_notional_usd``,
        ``extreme_notional_usd``, ``min_confidence``. All floats.
    """
    # Start from defaults so missing fields always have a value.
    result: dict = dict(DEFAULT_THRESHOLDS)

    if not isinstance(symbol, str):
        return result
    sym = symbol.strip().upper()
    if not sym:
        return result

    preset = SYMBOL_THRESHOLDS.get(sym)
    if preset:
        result.update(_filter_threshold_fields(preset))

    if overrides:
        override = overrides.get(sym)
        if isinstance(override, Mapping):
            result.update(_filter_threshold_fields(override))

    return result


def _filter_threshold_fields(src: Mapping[str, Any]) -> dict:
    """Keep only known threshold fields and coerce to float."""
    out: dict = {}
    for key in THRESHOLD_FIELDS:
        if key in src:
            try:
                out[key] = float(src[key])
            except (TypeError, ValueError):
                # Skip non-numeric overrides — fall back to defaults.
                continue
    return out


__all__ = [
    "DEFAULT_THRESHOLDS",
    "SYMBOL_THRESHOLDS",
    "THRESHOLD_FIELDS",
    "get_whale_thresholds_for_symbol",
]
