"""
services/gold_bot_trade_journal.py
-----------------------------------
LM75B — Local JSONL journal for guarded MT5 demo trade attempts.

Append-only, one JSON object per line (same pattern as the whale event
journal). Records EVERY attempt — dry runs, blocked attempts and sent demo
orders alike — so the trade loop leaves an honest trail. No network, no DB.

Generated journal files are not tracked; the default path lives under
`data/gold_bot/` which is created on first write.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

# Repo-root-relative default (this file is services/…).
_REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_JOURNAL_PATH = _REPO_ROOT / "data" / "gold_bot" / "demo_trade_journal.jsonl"
# LM76A — decision engine runs are journaled separately from order attempts.
DECISION_JOURNAL_PATH = _REPO_ROOT / "data" / "gold_bot" / "decision_journal.jsonl"

# Attempt modes.
MODE_DRY_RUN = "dry_run"
MODE_BLOCKED = "blocked"
MODE_DEMO_ORDER = "demo_order"
MODE_CLOSE = "close_position"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_entry(entry: dict[str, Any], path: str | os.PathLike[str] | None = None) -> Path:
    """Append one entry as a JSON line. Creates the directory on first write."""
    target = Path(path) if path is not None else DEFAULT_JOURNAL_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, default=str) + "\n")
    return target


def read_entries(path: str | os.PathLike[str] | None = None) -> list[dict[str, Any]]:
    """Read all entries. Missing file → empty list. Bad lines are skipped."""
    target = Path(path) if path is not None else DEFAULT_JOURNAL_PATH
    if not target.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in target.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def count_sent_today(
    *,
    server: str | None,
    login: int | None,
    path: str | os.PathLike[str] | None = None,
    now: datetime | None = None,
    entries: Iterable[dict[str, Any]] | None = None,
) -> int:
    """
    Count SENT demo orders (mode == demo_order) for this account on the current
    UTC day. Used by the risk gate's daily-trade-cap check. Blocked/dry-run
    attempts do not count.
    """
    today = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).date().isoformat()
    rows = list(entries) if entries is not None else read_entries(path)
    n = 0
    for e in rows:
        if e.get("mode") != MODE_DEMO_ORDER:
            continue
        if server is not None and e.get("account_server") != server:
            continue
        if login is not None and e.get("account_login") != login:
            continue
        ts = str(e.get("timestamp", ""))
        if ts[:10] == today:
            n += 1
    return n
