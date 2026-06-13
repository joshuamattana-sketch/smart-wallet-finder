"""
services/gold_bot_learning_modifiers.py
-----------------------------------------
LM86B - Demo-only auto learning modifiers for the Gold Bot.

Promotes the LM86A preview modifiers (`setup_modifiers.preview.json`) into an
ACTIVE demo modifier set (`active_demo_modifiers.json`) that the decision
engine / replay / worker may optionally consume. This is DEMO-ONLY autonomy:
no per-setup owner approval, but hard safety boundaries remain - modifiers only
nudge CONFIDENCE / decision gating. They can NEVER enable live trading, bypass
the macro lockout, the kill switch, the daily-loss / margin / risk gate, or
change volume.

Pure + offline: no MT5, no orders, no network. Values are clamped twice - a
promotion clamp ([-12, +8]) and an absolute hard clamp ([-20, +12]).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LEARNING_DIR = _REPO_ROOT / "data" / "gold_bot" / "learning"
PREVIEW_FILE = "setup_modifiers.preview.json"
ACTIVE_FILE = "active_demo_modifiers.json"
EVENTS_FILE = "modifier_events.jsonl"
DEFAULT_ACTIVE_MODIFIERS_PATH = DEFAULT_LEARNING_DIR / ACTIVE_FILE

# Clamps (Part 1). Promotion is the tighter day-to-day bound; the hard clamp is
# an absolute safety net applied even to hand-edited files on load.
MAX_POSITIVE_MODIFIER = 8
MAX_NEGATIVE_MODIFIER = -12
HARD_MIN_MODIFIER = -20
HARD_MAX_MODIFIER = 12

DEFAULT_MIN_SAMPLES = 20

# Statuses
ACTIVE = "active"
INACTIVE = "inactive"
REJECTED = "rejected"
INSUFFICIENT = "insufficient_sample"


def clamp_modifier(value: Any, *, promotion: bool = True) -> int:
    """Round to int, apply the promotion clamp (optional) then the hard clamp."""
    try:
        v = int(round(float(value)))
    except (TypeError, ValueError):
        return 0
    if promotion:
        v = max(MAX_NEGATIVE_MODIFIER, min(MAX_POSITIVE_MODIFIER, v))
    return max(HARD_MIN_MODIFIER, min(HARD_MAX_MODIFIER, v))


@dataclass
class LearningModifier:
    setup: str
    confidence_modifier: int
    status: str                        # active | inactive | rejected | insufficient_sample
    reason: str
    source_scorecard: str | None = None
    horizon: int | None = None
    sample_count: int | None = None
    expectancy_points: float | None = None
    winrate: float | None = None
    generated_at: str | None = None
    expires_at: str | None = None
    applied_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ── evaluation (pure) ───────────────────────────────────────────────────────────
def evaluate_preview(preview: dict, *, min_samples: int = DEFAULT_MIN_SAMPLES,
                     now: datetime | None = None) -> dict[str, LearningModifier]:
    """
    Validate + clamp each preview entry into a LearningModifier with a status.
    No approval prompt. Entries are rejected (sample too low / missing reason)
    rather than dropped, so the decision is auditable.
    """
    now = now or datetime.now(timezone.utc)
    out: dict[str, LearningModifier] = {}
    for setup, e in (preview or {}).items():
        if setup.startswith("_") or not isinstance(e, dict):
            continue
        reason = e.get("reason")
        sample = e.get("sample_count")
        value = clamp_modifier(e.get("confidence_modifier", 0), promotion=True)
        if not reason:
            status, value = REJECTED, 0
            reason = "rejected: missing reason"
        elif sample is None or sample < min_samples:
            status, value = INSUFFICIENT, 0
        else:
            status = ACTIVE
        out[setup] = LearningModifier(
            setup=setup, confidence_modifier=value, status=status, reason=reason,
            source_scorecard=e.get("source_scorecard"), horizon=e.get("horizon"),
            sample_count=sample, expectancy_points=e.get("expectancy_points"),
            winrate=e.get("winrate"), generated_at=now.isoformat(),
        )
    return out


# ── file IO ────────────────────────────────────────────────────────────────────
def read_preview(learning_dir: str | Path = DEFAULT_LEARNING_DIR) -> tuple[dict, list[str]]:
    p = Path(learning_dir) / PREVIEW_FILE
    if not p.exists():
        return {}, [f"preview not found: {p} - run scripts/run_gold_bot_learning_scorecard.py first."]
    try:
        return json.loads(p.read_text(encoding="utf-8")), []
    except (json.JSONDecodeError, OSError) as exc:
        return {}, [f"preview unreadable: {exc}"]


def build_active_payload(modifiers: dict[str, LearningModifier], *, source_scorecard: str | None,
                         min_samples: int, now: datetime) -> dict[str, Any]:
    active = {s: m.to_dict() for s, m in modifiers.items() if m.status == ACTIVE}
    return {
        "generated_at": now.isoformat(),
        "source_scorecard": source_scorecard,
        "mode": "demo_auto_learning",
        "safety": "demo_only",
        "min_samples": min_samples,
        "active_count": len(active),
        "modifiers": active,
    }


def promote(learning_dir: str | Path = DEFAULT_LEARNING_DIR, *,
            min_samples: int = DEFAULT_MIN_SAMPLES, now: datetime | None = None,
            write: bool = True) -> tuple[dict, dict[str, LearningModifier], list[str]]:
    """
    Promote preview → active_demo_modifiers.json (demo-only). Returns
    (active_payload, evaluated, warnings). With write=False it evaluates only
    (used by the probe's non-promote view). No approval required.
    """
    now = now or datetime.now(timezone.utc)
    d = Path(learning_dir)
    preview, warnings = read_preview(d)
    evaluated = evaluate_preview(preview, min_samples=min_samples, now=now)
    source = next((m.source_scorecard for m in evaluated.values() if m.source_scorecard), None)
    payload = build_active_payload(evaluated, source_scorecard=source, min_samples=min_samples, now=now)

    if write and preview:
        d.mkdir(parents=True, exist_ok=True)
        (d / ACTIVE_FILE).write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        with (d / EVENTS_FILE).open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "generated_at": now.isoformat(), "min_samples": min_samples,
                "source_scorecard": source, "active_count": payload["active_count"],
                "active": {s: m.confidence_modifier for s, m in evaluated.items() if m.status == ACTIVE},
                "rejected": [s for s, m in evaluated.items() if m.status in (REJECTED, INSUFFICIENT)],
            }, default=str) + "\n")
    return payload, evaluated, warnings


def load_active_modifiers(path: str | Path = DEFAULT_ACTIVE_MODIFIERS_PATH
                          ) -> tuple[dict[str, dict], list[str]]:
    """
    Load active demo modifiers for the decision engine. Returns (modifiers, warnings)
    where modifiers maps setup -> {confidence_modifier(clamped), reason, ...}. Missing
    or invalid file → ({}, [warning]) - callers continue WITHOUT modifiers.
    """
    p = Path(path)
    if not p.exists():
        return {}, [f"learning modifiers file not found: {path} - continuing without modifiers."]
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return {}, [f"learning modifiers file unreadable: {exc} - continuing without modifiers."]

    raw = data.get("modifiers", data) if isinstance(data, dict) else None
    if not isinstance(raw, dict):
        return {}, ["learning modifiers file has no 'modifiers' object - continuing without."]
    out: dict[str, dict] = {}
    for setup, e in raw.items():
        if setup.startswith("_") or not isinstance(e, dict):
            continue
        if e.get("status", ACTIVE) != ACTIVE:
            continue
        out[setup] = {**e, "confidence_modifier": clamp_modifier(e.get("confidence_modifier", 0),
                                                                 promotion=False)}
    return out, []
