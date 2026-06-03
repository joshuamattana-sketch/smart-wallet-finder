"""
services/discord_alert_formatter.py
------------------------------------
LM51A — Discord alert formatter.

Pure-Python formatter that turns LM49 signal dicts (or LM50 journal
entries, which share the same surface) into Discord-ready webhook
payloads. NO network, NO webhook calls, NO secrets — this module only
*shapes* the payload. The actual send/webhook URL handling belongs to
a later patch.

Public entry
~~~~~~~~~~~~
    format_discord_signal_alert(signal_or_journal_entry) -> dict | None

Returns a Discord webhook payload dict with keys ``content`` and
``embeds``. ``None`` is returned for unrecoverably malformed input
(non-dict, or missing the minimum identifying field ``symbol``).
"""

from __future__ import annotations

from typing import Any


# ── Discord embed colors (decimal RGB) ───────────────────────────────────────

COLOR_LONG     = 0x22C55E   # green
COLOR_SHORT    = 0xEF4444   # red
COLOR_NEUTRAL  = 0x6B7280   # slate
COLOR_NO_TRADE = 0x9CA3AF   # lighter slate

# Compact emoji map keyed by direction.
_DIRECTION_EMOJI = {
    "long":    "🟢",
    "short":   "🔴",
    "neutral": "⚪",
}

# Plain-language names for direction (UI-friendly, never None).
_DIRECTION_LABEL = {
    "long":    "LONG",
    "short":   "SHORT",
    "neutral": "NEUTRAL",
}


# ── Helpers ──────────────────────────────────────────────────────────────────

def _is_number(v: object) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _safe_str(v: object, *, default: str = "") -> str:
    if isinstance(v, str):
        return v
    return default


def _fmt_price(v: object) -> str:
    """Render a USD price with thousands separator. Falls back to '—'."""
    if _is_number(v):
        return f"${float(v):,.4f}".rstrip("0").rstrip(".")
    return "—"


def _fmt_pct(v: object) -> str:
    """Render a 0-100 score as 'NN.N'. Falls back to '—'."""
    if _is_number(v):
        return f"{float(v):.1f}"
    return "—"


def _fmt_conf(v: object) -> str:
    """Render a 0-1 confidence as a percent string."""
    if _is_number(v):
        return f"{float(v) * 100:.1f}%"
    return "—"


def _direction_color(direction: str, signal_level: str) -> int:
    if signal_level == "no_trade":
        return COLOR_NO_TRADE
    if direction == "long":
        return COLOR_LONG
    if direction == "short":
        return COLOR_SHORT
    return COLOR_NEUTRAL


def _direction_emoji(direction: str) -> str:
    return _DIRECTION_EMOJI.get(direction, "⚪")


def _direction_label(direction: str) -> str:
    return _DIRECTION_LABEL.get(direction, "NEUTRAL")


def _format_reasons(reasons: Any) -> str:
    """Join a reasons list as bullet points. Falls back to a dash."""
    if isinstance(reasons, list) and reasons:
        items = [_safe_str(r).strip() for r in reasons if isinstance(r, str) and r.strip()]
        if items:
            return "\n".join(f"• {r}" for r in items)
    return "—"


def _format_targets(targets: Any) -> str:
    if isinstance(targets, list) and targets:
        return ", ".join(_fmt_price(t) for t in targets if _is_number(t)) or "—"
    return "—"


def _is_no_trade(level: str, status: str, outcome: str) -> bool:
    return (
        level == "no_trade"
        or status == "no_trade"
        or outcome == "no_trade"
    )


# ── Public entry ─────────────────────────────────────────────────────────────

def format_discord_signal_alert(
    signal_or_journal_entry: Any,
) -> dict | None:
    """
    Build a Discord webhook payload (``content`` + ``embeds``) from an LM49
    signal or LM50 journal entry. Returns None for unrecoverably malformed
    input. Never raises.

    The resulting payload is deterministic — identical input always
    produces an identical dict (same field order, same strings).
    """
    if not isinstance(signal_or_journal_entry, dict):
        return None
    s = signal_or_journal_entry
    symbol = _safe_str(s.get("symbol")).strip()
    if not symbol:
        return None

    exchange   = _safe_str(s.get("exchange"))
    timeframe  = _safe_str(s.get("timeframe"))
    direction  = _safe_str(s.get("direction"),    default="neutral").lower()
    setup_type = _safe_str(s.get("setup_type"))
    signal_lvl = _safe_str(s.get("signal_level"), default="no_trade")
    status     = _safe_str(s.get("status"))
    outcome    = _safe_str(s.get("outcome_status"))
    action     = _safe_str(s.get("action_hint"))
    signal_id  = _safe_str(s.get("signal_id"))
    setup_id   = _safe_str(s.get("setup_id"))
    signal_ts  = _safe_str(s.get("signal_ts"))

    # Numeric values (defensive).
    score      = s.get("score")
    confidence = s.get("confidence")

    # Entry geometry.
    entry_low  = s.get("entry_zone_low")
    entry_high = s.get("entry_zone_high")
    entry_mid  = s.get("entry_zone_mid")
    invalidation = s.get("invalidation_price")
    targets    = s.get("targets") or []
    reasons    = s.get("reasons") or []
    risks      = s.get("risks")   or []

    no_trade = _is_no_trade(signal_lvl, status, outcome)

    # ── Content (short summary line above the embed) ─────────────────────────
    if no_trade:
        content = f"⚪ no-trade snapshot · {symbol}"
        if timeframe:
            content += f" · {timeframe}"
    else:
        content = (
            f"{_direction_emoji(direction)} "
            f"{signal_lvl.replace('_', ' ').upper()} · "
            f"{_direction_label(direction)} {symbol}"
        )
        if timeframe:
            content += f" · {timeframe}"

    # ── Title + description ──────────────────────────────────────────────────
    if no_trade:
        title = f"{symbol} · {timeframe or '—'} · no-trade"
    else:
        title = (
            f"{symbol} · {timeframe or '—'} · "
            f"{signal_lvl.replace('_', ' ')} {_direction_label(direction)}"
        )

    description_lines: list[str] = []
    if setup_type:
        description_lines.append(f"**Setup type:** `{setup_type}`")
    if action:
        description_lines.append(f"**Action hint:** `{action}`")
    if exchange:
        description_lines.append(f"**Exchange:** `{exchange}`")
    if status:
        description_lines.append(f"**Status:** `{status}`")
    if outcome and outcome != "no_trade":
        description_lines.append(f"**Outcome:** `{outcome}`")
    description = "\n".join(description_lines) if description_lines else "—"

    # ── Fields ───────────────────────────────────────────────────────────────
    fields: list[dict] = [
        {"name": "Score",      "value": _fmt_pct(score),       "inline": True},
        {"name": "Confidence", "value": _fmt_conf(confidence), "inline": True},
        {"name": "Direction",  "value": _direction_label(direction), "inline": True},
    ]

    if not no_trade:
        zone_value = (
            f"low {_fmt_price(entry_low)}\n"
            f"mid {_fmt_price(entry_mid)}\n"
            f"high {_fmt_price(entry_high)}"
        )
        fields.extend([
            {"name": "Entry zone",    "value": zone_value,                "inline": True},
            {"name": "Invalidation",  "value": _fmt_price(invalidation),  "inline": True},
            {"name": "Targets",       "value": _format_targets(targets),  "inline": True},
        ])

    # Reasons and risks always appear (with '—' fallback) so the embed
    # shape is constant — easier for downstream consumers to test.
    fields.append({
        "name":   "Reasons",
        "value":  _format_reasons(reasons),
        "inline": False,
    })
    fields.append({
        "name":   "Risks",
        "value":  _format_reasons(risks),
        "inline": False,
    })

    # ── Footer ───────────────────────────────────────────────────────────────
    footer_parts: list[str] = ["Lumora"]
    if setup_id:
        footer_parts.append(f"setup={setup_id}")
    if signal_id:
        footer_parts.append(f"signal={signal_id}")
    if signal_ts:
        footer_parts.append(signal_ts)
    footer = {"text": " · ".join(footer_parts)}

    embed = {
        "title":       title,
        "description": description,
        "color":       _direction_color(direction, signal_lvl),
        "fields":      fields,
        "footer":      footer,
    }
    return {"content": content, "embeds": [embed]}
