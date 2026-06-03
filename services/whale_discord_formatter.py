"""
services/whale_discord_formatter.py
------------------------------------
LM52B — Discord alert formatter for whale events.

Turns LM52A whale event dicts into Discord-ready webhook payloads.
NO network, NO webhook calls, NO secrets — only shapes the payload.

Public entry:
    format_whale_discord_alert(whale_event) -> dict | None
"""

from __future__ import annotations

from typing import Any

# Embed colors by severity
_SEVERITY_COLORS = {
    "info":     0x6B7280,
    "notable":  0x3B82F6,
    "high":     0xF59E0B,
    "extreme":  0xEF4444,
}

_SEVERITY_EMOJI = {
    "info":     "ℹ️",
    "notable":  "🔵",
    "high":     "🟡",
    "extreme":  "🔴",
}


def format_whale_discord_alert(whale_event: Any) -> dict | None:
    """
    Format a whale event dict into a Discord webhook payload.

    Returns dict with ``content`` and ``embeds``, or None for
    unrecoverably malformed input.
    """
    if not isinstance(whale_event, dict):
        return None

    symbol = str(whale_event.get("symbol", "") or "")
    if not symbol:
        return None

    severity    = str(whale_event.get("severity", "info") or "info")
    source_type = str(whale_event.get("source_type", "unknown") or "unknown")
    chain       = str(whale_event.get("chain", "") or "")
    exchange    = str(whale_event.get("exchange", "") or "")
    side        = str(whale_event.get("side", "") or "")
    amount      = whale_event.get("amount", 0) or 0
    price       = whale_event.get("price", 0) or 0
    notional    = whale_event.get("notional_usd", 0) or 0
    wallet      = str(whale_event.get("wallet", "") or "")
    tx_hash     = str(whale_event.get("tx_hash", "") or "")
    confidence  = whale_event.get("confidence", 0) or 0
    reason      = str(whale_event.get("reason", "") or "")

    emoji = _SEVERITY_EMOJI.get(severity, "ℹ️")
    color = _SEVERITY_COLORS.get(severity, 0x6B7280)

    title = f"{emoji} Whale {source_type.title()}: {symbol}"
    description = reason if reason else f"Large {source_type} detected for {symbol}"

    notional_str = f"${float(notional):,.0f}"

    fields = []
    fields.append({"name": "Symbol", "value": symbol, "inline": True})
    if chain:
        fields.append({"name": "Chain", "value": chain, "inline": True})
    if exchange:
        fields.append({"name": "Exchange", "value": exchange, "inline": True})
    if side:
        fields.append({"name": "Side", "value": side, "inline": True})
    fields.append({"name": "Amount", "value": str(amount), "inline": True})
    if float(price) > 0:
        fields.append({"name": "Price", "value": f"${float(price):,.2f}", "inline": True})
    fields.append({"name": "Notional USD", "value": notional_str, "inline": True})
    fields.append({"name": "Severity", "value": severity.upper(), "inline": True})
    if float(confidence) > 0:
        fields.append({"name": "Confidence", "value": f"{float(confidence):.0%}", "inline": True})
    if wallet:
        display_wallet = wallet if len(wallet) <= 12 else f"{wallet[:6]}...{wallet[-4:]}"
        fields.append({"name": "Wallet", "value": display_wallet, "inline": True})
    if tx_hash:
        display_tx = tx_hash if len(tx_hash) <= 12 else f"{tx_hash[:6]}...{tx_hash[-4:]}"
        fields.append({"name": "Tx Hash", "value": display_tx, "inline": True})

    embed = {
        "title": title,
        "description": description,
        "color": color,
        "fields": fields,
        "footer": {"text": f"Whale Alert | {severity.upper()} | {source_type}"},
    }

    content = f"{emoji} **Whale {source_type.title()}** — {symbol} — {notional_str}"

    return {"content": content, "embeds": [embed]}
