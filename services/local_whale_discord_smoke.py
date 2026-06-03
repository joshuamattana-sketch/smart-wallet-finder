"""
services/local_whale_discord_smoke.py
--------------------------------------
LM57 — Local smoke helper connecting whale events to whale alert filter,
whale Discord formatter, and webhook sender.

NO UI, NO API. Network only when options.send=True.

Public entry:
    run_local_whale_discord_smoke(whale_event, options=None) -> dict
"""

from __future__ import annotations

from typing import Any

from services.whale_alert_filter import should_send_whale_alert
from services.whale_discord_formatter import format_whale_discord_alert
from services.discord_webhook_sender import send_discord_webhook


def run_local_whale_discord_smoke(
    whale_event: Any,
    options: dict | None = None,
    *,
    sender=send_discord_webhook,
) -> dict:
    """
    Run whale event through filter -> formatter -> optional sender.

    options:
        send        (bool) — POST to Discord. Default False.
        webhook_url (str)  — Discord webhook URL (required if send=True).
    """
    opts = options or {}
    do_send = bool(opts.get("send", False))
    webhook_url = opts.get("webhook_url")

    result = {
        "should_send": False,
        "filter_reason": "",
        "payload": None,
        "send_result": None,
        "summary": {"filtered": 0, "formatted": 0, "sent": 0, "errors": 0},
    }

    if not isinstance(whale_event, dict):
        result["filter_reason"] = "invalid input"
        result["summary"]["filtered"] = 1
        return result

    filter_out = should_send_whale_alert(whale_event)
    should_send = filter_out.get("should_send", False)
    result["should_send"] = should_send
    result["filter_reason"] = filter_out.get("reason", "")

    if not should_send:
        result["summary"]["filtered"] = 1
        return result

    payload = format_whale_discord_alert(whale_event)
    result["payload"] = payload

    if payload is not None:
        result["summary"]["formatted"] = 1

    if do_send and payload is not None:
        send_out = sender(payload, webhook_url=webhook_url)
        result["send_result"] = send_out
        if send_out.get("ok"):
            result["summary"]["sent"] = 1
        else:
            result["summary"]["errors"] = 1

    return result
