"""
services/whale_event_supabase_writer.py
----------------------------------------
LM63H — Supabase writer for whale_events (LM63G schema).

Pure Python. NO Discord, NO frontend, NO local files.

Insert one whale event row at a time into public.whale_events via the
Supabase PostgREST endpoint. Uses the service-role key (read from env if
not passed explicitly) and the `on_conflict=whale_event_id` /
`resolution=ignore-duplicates` Prefer header so a duplicate
`whale_event_id` never errors out — the partial unique index on
whale_events makes this idempotent.

The HTTP transport is dependency-injected via the `requester` kwarg so
tests can drive every code path with zero network.

Public API:
    build_whale_event_supabase_row(event, meta=None) -> dict | None
    write_whale_event_to_supabase(event, supabase_url=None,
                                  service_role_key=None, meta=None,
                                  *, table="whale_events",
                                  requester=None, env=None,
                                  timeout=8.0) -> dict
"""

from __future__ import annotations

import json
import os
from typing import Any, Callable, Mapping

import requests

WHALE_EVENTS_TABLE = "whale_events"
DEFAULT_TIMEOUT_S = 8.0

# Postgres unique-violation SQLSTATE — surfaces as part of PostgREST 4xx bodies.
_PG_UNIQUE_VIOLATION = "23505"

# Columns mapped 1:1 from the event dict onto the whale_events row.
# `payload` is built separately (event + meta wrapper).
_STR_COLUMNS: tuple[str, ...] = (
    "whale_event_id",
    "source_type",
    "symbol",
    "exchange",
    "chain",
    "side",
    "severity",
    "reason",
    "event_ts",
    "wallet",
    "tx_hash",
)
_NUM_COLUMNS: tuple[str, ...] = (
    "amount",
    "price",
    "notional_usd",
    "confidence",
)


# ── Row builder ───────────────────────────────────────────────────────────────

def _safe_str(v: Any) -> str | None:
    if v is None:
        return None
    if isinstance(v, str):
        return v
    return str(v)


def _safe_num(v: Any) -> float | None:
    if v is None:
        return None
    if isinstance(v, bool):
        return None  # bools coerce to numbers in Python; never want that here
    try:
        out = float(v)
    except (TypeError, ValueError):
        return None
    return out if (out == out) else None  # filter NaN (NaN != NaN)


def _wrap_meta(meta: Any) -> Any:
    """Mirror the journal's meta-coercion: dict→dict, None→None, else wrap."""
    if meta is None:
        return None
    if isinstance(meta, dict):
        return meta
    return {"value": meta}


def build_whale_event_supabase_row(event: Any, meta: Any = None) -> dict | None:
    """
    Build a PostgREST-ready row dict for the whale_events table from a
    detect_whale_events output. Returns None when the input is unusable
    (non-dict or missing required `symbol`).

    `payload` carries the full original event + optional meta so the row
    stays forward-compatible if new columns are added later.
    """
    if not isinstance(event, dict):
        return None
    symbol = _safe_str(event.get("symbol"))
    if not symbol:
        return None

    row: dict[str, Any] = {}
    for col in _STR_COLUMNS:
        row[col] = _safe_str(event.get(col))
    for col in _NUM_COLUMNS:
        row[col] = _safe_num(event.get(col))

    # Always overwrite symbol with the validated value.
    row["symbol"] = symbol

    row["payload"] = {
        "event": dict(event),       # copy so caller can't mutate the row's view
        "meta":  _wrap_meta(meta),
    }
    return row


# ── HTTP writer ───────────────────────────────────────────────────────────────

def _resolve_env(supabase_url: str | None,
                 service_role_key: str | None,
                 env: Mapping[str, str] | None) -> tuple[str, str]:
    src = env if env is not None else os.environ
    url = supabase_url or src.get("SUPABASE_URL", "")
    key = service_role_key or src.get("SUPABASE_SERVICE_ROLE_KEY", "")
    return url.strip(), key.strip()


def _build_endpoint(url: str, table: str) -> str:
    base = url.rstrip("/")
    return f"{base}/rest/v1/{table}?on_conflict=whale_event_id"


def _build_headers(key: str) -> dict[str, str]:
    return {
        "apikey":        key,
        "Authorization": f"Bearer {key}",
        "Content-Type":  "application/json",
        # `resolution=ignore-duplicates` makes the partial-unique-index conflict
        # on whale_event_id a successful no-op rather than a 409.
        "Prefer":        "return=minimal,resolution=ignore-duplicates",
    }


def write_whale_event_to_supabase(
    event: Any,
    supabase_url: str | None = None,
    service_role_key: str | None = None,
    meta: Any = None,
    *,
    table: str = WHALE_EVENTS_TABLE,
    requester: Callable[..., Any] | None = None,
    env: Mapping[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT_S,
) -> dict:
    """
    Insert one whale event row into Supabase. NEVER raises — every error
    path returns a dict.

    Returns one of:
        {"ok": True}
        {"ok": True, "duplicate": True}                      # idempotent retry
        {"ok": False, "error": "...", "status": int|None}    # everything else

    Args:
        event:              Whale event dict from detect_whale_events.
        supabase_url:       Override env SUPABASE_URL (rarely needed in prod).
        service_role_key:   Override env SUPABASE_SERVICE_ROLE_KEY.
        meta:               Optional context dict (filter result, send result…).
        table:              Default "whale_events". Override for tests.
        requester:          Optional callable matching `requests.post(...)` for
                            test injection. Defaults to `requests.post`.
        env:                Optional env mapping (defaults to os.environ).
        timeout:            HTTP timeout in seconds. Default 8.
    """
    url, key = _resolve_env(supabase_url, service_role_key, env)
    if not url or not key:
        missing = []
        if not url: missing.append("SUPABASE_URL")
        if not key: missing.append("SUPABASE_SERVICE_ROLE_KEY")
        return {
            "ok":     False,
            "error":  f"missing {', '.join(missing)}",
            "status": None,
        }

    row = build_whale_event_supabase_row(event, meta=meta)
    if row is None:
        return {
            "ok":     False,
            "error":  "invalid event (not a dict or missing symbol)",
            "status": None,
        }

    endpoint = _build_endpoint(url, table)
    headers  = _build_headers(key)
    body     = json.dumps([row], default=str)  # default=str: timestamps etc.

    req = requester or requests.post
    try:
        resp = req(endpoint, data=body, headers=headers, timeout=timeout)
    except Exception as exc:                # pragma: no cover - exercised in tests
        return {"ok": False, "error": f"network error: {exc}", "status": None}

    status = getattr(resp, "status_code", None)

    # Successful insert (or merge-noop with return=minimal).
    if status in (200, 201, 204):
        return {"ok": True}

    # Some PostgREST configurations still surface conflicts as 409 even with
    # resolution=ignore-duplicates — treat that as a clean idempotent retry.
    if status == 409:
        return {"ok": True, "duplicate": True}

    # Inspect the body for a Postgres unique-violation hint as a last resort.
    body_text = ""
    try:
        text_attr = getattr(resp, "text", "") or ""
        body_text = str(text_attr)[:500]
    except Exception:
        body_text = ""
    if _PG_UNIQUE_VIOLATION in body_text or "duplicate key" in body_text.lower():
        return {"ok": True, "duplicate": True}

    return {
        "ok":     False,
        "error":  body_text or f"HTTP {status}",
        "status": status,
    }


__all__ = [
    "WHALE_EVENTS_TABLE",
    "DEFAULT_TIMEOUT_S",
    "build_whale_event_supabase_row",
    "write_whale_event_to_supabase",
]
