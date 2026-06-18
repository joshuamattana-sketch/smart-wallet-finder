"""
services/gold_bot_tactic_library.py
-------------------------------------
LM98C - Structured library of known XAUUSD tactics (RESEARCH-ONLY).

Loads + validates the tactic library JSON (default the committed sample template,
or a gitignored data/gold_bot/tactics/*.manual.json override), and groups tactics
into those MAPPED to existing replay setup tags vs research_only / not_implemented.

It is pure config + validation: NO trading, NO MT5, NO orders, NO network. A
tactic's status stays research_only - nothing here enables demo or live execution.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LIBRARY_PATH = _REPO_ROOT / "docs" / "gold_bot" / "templates" / "tactic_library.sample.json"
DEFAULT_TACTICS_DIR = _REPO_ROOT / "data" / "gold_bot" / "tactics"

# Setups the LM85A replay engine actually emits in row["strategy"] (for mapping).
KNOWN_REPLAY_SETUPS = (
    "liquidity_sweep_reclaim", "fvg_retest", "breakout_retest", "momentum",
    "scalp_momentum", "scalp_retest",
)

REQUIRED_FIELDS = (
    "id", "name", "category", "description", "allowed_timeframes", "preferred_horizons",
    "setup_tags", "entry_logic_summary", "invalidation_summary", "target_summary",
    "filters", "no_trade_conditions", "replay_mapping", "status",
)


def validate_tactic(t: dict) -> list[str]:
    """Return a list of schema issues for one tactic ([] = valid)."""
    issues: list[str] = []
    if not isinstance(t, dict):
        return ["tactic is not an object"]
    for f in REQUIRED_FIELDS:
        if f not in t:
            issues.append(f"missing field '{f}'")
    rm = t.get("replay_mapping")
    if not isinstance(rm, dict) or "status" not in rm:
        issues.append("replay_mapping must be an object with a 'status'")
    elif rm["status"] not in ("mapped", "research_only", "not_implemented_yet"):
        issues.append(f"replay_mapping.status invalid: {rm.get('status')}")
    if t.get("status") not in (None, "research_only", "candidate", "active"):
        issues.append(f"unexpected status '{t.get('status')}' (expected research_only here)")
    return issues


def resolve_library_path(path: str | Path | None = None) -> Path:
    """Explicit path wins; else a manual override in data/gold_bot/tactics; else the sample."""
    if path:
        return Path(path)
    manual = DEFAULT_TACTICS_DIR / "tactic_library.manual.json"
    return manual if manual.exists() else DEFAULT_LIBRARY_PATH


def load_library(path: str | Path | None = None) -> tuple[list[dict], dict, list[str]]:
    """Load + validate. Returns (tactics, meta, warnings). Never raises on bad files."""
    p = resolve_library_path(path)
    warnings: list[str] = []
    if not p.exists():
        return [], {"path": str(p)}, [f"tactic library not found: {p}"]
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return [], {"path": str(p)}, [f"tactic library unreadable: {exc}"]
    tactics = doc.get("tactics") or []
    valid: list[dict] = []
    for t in tactics:
        issues = validate_tactic(t)
        if issues:
            warnings.append(f"tactic '{t.get('id', '?')}' invalid: {'; '.join(issues)}")
            continue
        valid.append(t)
    meta = {"path": str(p), "version": doc.get("version"), "symbol": doc.get("symbol"),
            "count": len(valid)}
    return valid, meta, warnings


def mapping_status(tactic: dict, *, known_setups: tuple[str, ...] = KNOWN_REPLAY_SETUPS) -> str:
    """mapped only if replay_mapping.status==mapped AND its setup tags exist in replay."""
    rm = tactic.get("replay_mapping") or {}
    if rm.get("status") != "mapped":
        return rm.get("status") or "research_only"
    tags = rm.get("setup_tags") or []
    if tags and all(tag in known_setups for tag in tags):
        return "mapped"
    return "research_only"


def group_tactics(tactics: list[dict], *, known_setups: tuple[str, ...] = KNOWN_REPLAY_SETUPS
                  ) -> dict[str, list[dict]]:
    """Group into mapped / research_only / not_implemented_yet."""
    out: dict[str, list[dict]] = {"mapped": [], "research_only": [], "not_implemented_yet": []}
    for t in tactics:
        st = mapping_status(t, known_setups=known_setups)
        if st == "mapped":
            out["mapped"].append(t)
        elif st == "not_implemented_yet":
            out["not_implemented_yet"].append(t)
        else:
            out["research_only"].append(t)
    return out


def mapped_setup_tags(tactics: list[dict], *, known_setups: tuple[str, ...] = KNOWN_REPLAY_SETUPS
                      ) -> dict[str, str]:
    """{setup_tag: tactic_id} for tactics that map to a real replay setup."""
    out: dict[str, str] = {}
    for t in tactics:
        if mapping_status(t, known_setups=known_setups) != "mapped":
            continue
        for tag in (t.get("replay_mapping") or {}).get("setup_tags") or []:
            out.setdefault(tag, t["id"])
    return out
