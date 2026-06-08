"""
services/whale_event_journal.py
--------------------------------
LM63E — Local append-only JSONL journal for whale events.

Pure Python. NO Supabase, NO Discord, NO frontend, NO secrets.

Each journal row is one JSON object on its own line:
    {
      "event":      { ...compact whale event dict... },
      "meta":       { ...optional caller-supplied context... },
      "written_at": "2026-06-08T12:34:56.789012+00:00"
    }

Public API:
    compact_whale_event_for_journal(event) -> dict | None
    append_whale_event_journal(path, event, meta=None) -> bool
    read_whale_event_journal(path, limit=100) -> list[dict]
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Fields kept from a whale event when written into the journal.
COMPACT_EVENT_FIELDS: tuple[str, ...] = (
    "whale_event_id",
    "source_type",
    "symbol",
    "exchange",
    "side",
    "amount",
    "price",
    "notional_usd",
    "severity",
    "confidence",
    "reason",
    "event_ts",
    "wallet",
    "tx_hash",
    "metadata",
)

DEFAULT_READ_LIMIT = 100


# ── Compaction ────────────────────────────────────────────────────────────────

def compact_whale_event_for_journal(event: Any) -> dict | None:
    """
    Return a JSON-safe compact dict suitable for storage. Returns None if
    `event` is not a dict (defensive — keeps the journal clean).

    Unknown fields are dropped. Missing known fields are omitted (not set
    to None) so downstream readers can tell what was actually carried.
    """
    if not isinstance(event, dict):
        return None
    return {k: event[k] for k in COMPACT_EVENT_FIELDS if k in event}


# ── Append ────────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_whale_event_journal(
    path: str | os.PathLike,
    event: Any,
    meta: Any = None,
) -> bool:
    """
    Append one whale event row to `path` (JSONL).

    Creates the parent directory if needed. Returns False (and does
    nothing) when:
        - `path` is falsy / not a string-like value
        - `event` is not a dict / has no compactable shape

    Returns True on a successful write. Never raises on filesystem
    errors — the caller's whale pipeline must keep running even if the
    journal can't be written.
    """
    if not path:
        return False
    if not isinstance(event, dict):
        return False

    compact = compact_whale_event_for_journal(event)
    if not compact:
        return False

    row: dict[str, Any] = {
        "event":      compact,
        "meta":       meta if isinstance(meta, dict) else (None if meta is None else {"value": meta}),
        "written_at": _now_iso(),
    }

    try:
        p = Path(path)
        if p.parent and not p.parent.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
        # Open in text-append mode with UTF-8 — newline-friendly JSONL.
        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, sort_keys=True, ensure_ascii=False))
            fh.write("\n")
    except (OSError, TypeError, ValueError):
        return False
    return True


# ── Read (newest first) ───────────────────────────────────────────────────────

def read_whale_event_journal(
    path: str | os.PathLike,
    limit: int = DEFAULT_READ_LIMIT,
) -> list[dict]:
    """
    Return up to `limit` parsed journal rows, **newest first** (i.e. the
    last line in the file appears at index 0 of the result).

    Missing files return an empty list. Lines that fail to parse as JSON
    objects are skipped silently. `limit` <= 0 returns [].
    """
    if not path or limit is None or limit <= 0:
        return []

    try:
        p = Path(path)
    except TypeError:
        return []
    if not p.exists() or not p.is_file():
        return []

    try:
        with p.open("r", encoding="utf-8") as fh:
            raw_lines = fh.readlines()
    except OSError:
        return []

    # Newest-first: iterate the file in reverse, parse, stop after limit.
    out: list[dict] = []
    for line in reversed(raw_lines):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(obj, dict):
            continue
        out.append(obj)
        if len(out) >= limit:
            break
    return out


__all__ = [
    "COMPACT_EVENT_FIELDS",
    "DEFAULT_READ_LIMIT",
    "append_whale_event_journal",
    "compact_whale_event_for_journal",
    "read_whale_event_journal",
]
