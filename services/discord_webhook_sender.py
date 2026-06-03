"""
services/discord_webhook_sender.py
-----------------------------------
LM51B — Discord webhook sender.

Sends LM51A-formatted webhook payloads to a Discord channel. Stdlib only
(urllib). The webhook URL is read from the env (`DISCORD_WEBHOOK_URL`)
unless an explicit URL is passed — never hardcoded.

Public entry
~~~~~~~~~~~~
    send_discord_webhook(payload, webhook_url=None, timeout=10) -> dict

Returns a small status dict and never raises:

    {
        "ok":           bool,        # True on 2xx
        "status_code":  int | None,  # HTTP status from Discord (None on local fail)
        "error":        str | None,  # short safe message on failure
        "response_text": str,        # truncated response body (≤400 chars)
    }

Failure modes covered:
- payload is None or not a dict → ok=False, error="invalid payload"
- payload is empty (no content / no embeds) → ok=False
- webhook_url is None AND env DISCORD_WEBHOOK_URL is missing → ok=False
- network / DNS / timeout → ok=False with the exception message
- 4xx / 5xx response → ok=False with HTTP status surfaced
- 200 / 204 → ok=True

Secrets handling:
- The webhook URL is read from env or the caller's arg. It is NEVER
  logged, NEVER returned in the response dict, NEVER printed.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any


# ── Constants ────────────────────────────────────────────────────────────────

ENV_WEBHOOK_URL = "DISCORD_WEBHOOK_URL"
_RESPONSE_TEXT_MAX = 400


# ── Helpers ──────────────────────────────────────────────────────────────────

def _resolve_webhook_url(webhook_url: str | None) -> str | None:
    """Explicit arg wins; otherwise read from env. Never echoed back."""
    if isinstance(webhook_url, str) and webhook_url.strip():
        return webhook_url.strip()
    env_val = os.environ.get(ENV_WEBHOOK_URL, "")
    if isinstance(env_val, str) and env_val.strip():
        return env_val.strip()
    return None


def _valid_payload(payload: Any) -> bool:
    """Discord requires at least content or embeds."""
    if not isinstance(payload, dict):
        return False
    has_content = isinstance(payload.get("content"), str) and payload["content"].strip()
    has_embeds  = isinstance(payload.get("embeds"), list) and payload["embeds"]
    return bool(has_content or has_embeds)


def _safe_truncate(text: str, *, limit: int = _RESPONSE_TEXT_MAX) -> str:
    if not isinstance(text, str):
        return ""
    return text if len(text) <= limit else text[:limit]


def _result(
    *, ok: bool,
    status_code: int | None,
    error: str | None,
    response_text: str = "",
) -> dict:
    return {
        "ok":            bool(ok),
        "status_code":   status_code,
        "error":         error,
        "response_text": _safe_truncate(response_text),
    }


# ── Public entry ─────────────────────────────────────────────────────────────

def send_discord_webhook(
    payload: dict | None,
    webhook_url: str | None = None,
    timeout: float = 10.0,
) -> dict:
    """
    POST a Discord webhook payload (from LM51A) and return a status dict.

    Never raises. Never prints / returns the webhook URL.
    """
    if not _valid_payload(payload):
        return _result(
            ok=False, status_code=None,
            error="invalid payload (missing content/embeds)",
        )

    url = _resolve_webhook_url(webhook_url)
    if not url:
        return _result(
            ok=False, status_code=None,
            error=f"no webhook URL (pass webhook_url= or set env {ENV_WEBHOOK_URL})",
        )

    try:
        body = json.dumps(payload).encode("utf-8")
    except (TypeError, ValueError) as exc:
        return _result(
            ok=False, status_code=None,
            error=f"failed to serialize payload: {exc}",
        )

    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "User-Agent":   "Lumora-Webhook-Sender/1.0 (+lm51b)",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = getattr(resp, "status", None)
            try:
                raw = resp.read()
                text = raw.decode("utf-8", errors="replace") if raw else ""
            except Exception:
                text = ""
            ok = isinstance(status, int) and 200 <= status < 300
            return _result(
                ok=ok,
                status_code=status,
                error=None if ok else f"HTTP {status}",
                response_text=text,
            )
    except urllib.error.HTTPError as exc:
        # Server replied with a non-2xx status; preserve the code + a short
        # snippet of the body (Discord error messages are short JSON dicts).
        try:
            text = exc.read().decode("utf-8", errors="replace")
        except Exception:
            text = ""
        return _result(
            ok=False,
            status_code=exc.code,
            error=f"HTTP {exc.code}",
            response_text=text,
        )
    except urllib.error.URLError as exc:
        # DNS, refused connection, etc.
        reason = getattr(exc, "reason", exc)
        return _result(
            ok=False, status_code=None,
            error=f"network error: {reason}",
        )
    except TimeoutError as exc:
        return _result(
            ok=False, status_code=None,
            error=f"timeout: {exc}",
        )
    except Exception as exc:  # pragma: no cover - defensive
        return _result(
            ok=False, status_code=None,
            error=f"unexpected error: {type(exc).__name__}: {exc}",
        )
