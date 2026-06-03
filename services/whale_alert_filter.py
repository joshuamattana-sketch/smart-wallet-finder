"""
services/whale_alert_filter.py
-------------------------------
LM52C — Whale alert filter.

Decides whether a LM52A whale event dict should be sent to Discord.
NO network, NO webhook, NO secrets, NO UI.

Public entry:
    should_send_whale_alert(whale_event, options=None) -> dict
"""

from __future__ import annotations

import hashlib
from typing import Any

_DEFAULT_OPTIONS = {
    "send_info": False,
    "min_notional_usd": 250_000,
    "min_confidence": 0.6,
    "allowed_symbols": None,
    "blocked_symbols": None,
    "allowed_chains": None,
    "blocked_chains": None,
}


def _make_cooldown_key(source_type, symbol, chain, exchange, side, wallet):
    raw = f"{source_type}|{symbol}|{chain}|{exchange}|{side}|{wallet}"
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


def should_send_whale_alert(whale_event: Any, options: dict | None = None) -> dict:
    """
    Decide if a whale event should be sent to Discord.

    Returns a dict with should_send, reason, severity, notional_usd,
    confidence, and cooldown_key.
    """
    base = {"should_send": False, "reason": "", "severity": "",
            "notional_usd": 0.0, "confidence": 0.0, "cooldown_key": ""}

    if not isinstance(whale_event, dict):
        base["reason"] = "invalid input"
        return base

    opts = dict(_DEFAULT_OPTIONS)
    if options:
        opts.update(options)

    severity   = str(whale_event.get("severity", "info") or "info")
    notional   = float(whale_event.get("notional_usd", 0) or 0)
    confidence = float(whale_event.get("confidence", 0) or 0)
    symbol     = str(whale_event.get("symbol", "") or "")
    chain      = str(whale_event.get("chain", "") or "")
    exchange   = str(whale_event.get("exchange", "") or "")
    side       = str(whale_event.get("side", "") or "")
    wallet     = str(whale_event.get("wallet", "") or "")
    source_type = str(whale_event.get("source_type", "unknown") or "unknown")

    cooldown_key = _make_cooldown_key(source_type, symbol, chain, exchange, side, wallet)
    base.update(severity=severity, notional_usd=notional,
                confidence=confidence, cooldown_key=cooldown_key)

    # Symbol / chain filters
    allowed_sym = opts.get("allowed_symbols")
    if allowed_sym and symbol not in allowed_sym:
        base["reason"] = f"symbol {symbol} not in allowed list"
        return base
    blocked_sym = opts.get("blocked_symbols")
    if blocked_sym and symbol in blocked_sym:
        base["reason"] = f"symbol {symbol} is blocked"
        return base
    allowed_ch = opts.get("allowed_chains")
    if allowed_ch and chain not in allowed_ch:
        base["reason"] = f"chain {chain} not in allowed list"
        return base
    blocked_ch = opts.get("blocked_chains")
    if blocked_ch and chain in blocked_ch:
        base["reason"] = f"chain {chain} is blocked"
        return base

    min_notional = float(opts["min_notional_usd"])
    min_conf = float(opts["min_confidence"])

    if severity == "extreme":
        base["should_send"] = True
        base["reason"] = "extreme severity always sent"
        return base

    if severity == "high":
        if notional >= 500_000 and confidence >= 0.6:
            base["should_send"] = True
            base["reason"] = "high severity above thresholds"
        else:
            base["reason"] = "high severity below thresholds"
        return base

    if severity == "notable":
        if notional >= min_notional and confidence >= 0.7:
            base["should_send"] = True
            base["reason"] = "notable severity above thresholds"
        else:
            base["reason"] = "notable severity below thresholds"
        return base

    # info
    if opts["send_info"]:
        if notional >= min_notional and confidence >= min_conf:
            base["should_send"] = True
            base["reason"] = "info sent (option enabled)"
        else:
            base["reason"] = "info below thresholds"
    else:
        base["reason"] = "info severity not sent by default"
    return base
