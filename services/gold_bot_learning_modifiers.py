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
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LEARNING_DIR = _REPO_ROOT / "data" / "gold_bot" / "learning"
PREVIEW_FILE = "setup_modifiers.preview.json"
ACTIVE_FILE = "active_demo_modifiers.json"
EVENTS_FILE = "modifier_events.jsonl"
DEFAULT_ACTIVE_MODIFIERS_PATH = DEFAULT_LEARNING_DIR / ACTIVE_FILE

# LM86C automatic learning cycle file set (all DEMO-ONLY, all gitignored).
# The candidate is staged separately and only ever replaces ACTIVE_FILE once the
# objective comparison in gold_bot_learning_cycle.py accepts it.
CANDIDATE_FILE = "candidate_demo_modifiers.json"
BACKUP_FILE = "active_demo_modifiers.backup.json"
REJECTED_FILE = "rejected_demo_modifiers.json"
DEFAULT_EXPIRY_DAYS = 7

# Clamps (Part 1). Promotion is the tighter day-to-day bound; the hard clamp is
# an absolute safety net applied even to hand-edited files on load.
MAX_POSITIVE_MODIFIER = 8
MAX_NEGATIVE_MODIFIER = -12
HARD_MIN_MODIFIER = -20
HARD_MAX_MODIFIER = 12

DEFAULT_MIN_SAMPLES = 20

# LM87A demo safety contract: keys that must NEVER appear in an active modifier
# file (top level or per-setup). Modifiers are CONFIDENCE-ONLY - anything that
# could touch live trading, order routing, or sizing is a hard contract failure.
FORBIDDEN_MODIFIER_KEYS = ("live", "live_trading", "order_send", "volume", "lot",
                           "leverage", "bypass")

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


# ── LM86C: candidate staging / activation / rollback / expiry ─────────────────────
# These are the file primitives the automatic learning cycle uses. They keep the
# demo-only, confidence-only contract: nothing here can enable live trading, change
# volume, or bypass the macro lockout / risk gate / kill switch.

def _expires_at(now: datetime, days: int | None) -> str | None:
    """ISO expiry `now + days`, or None when days is falsy (never expires)."""
    return (now + timedelta(days=days)).isoformat() if days else None


def build_modifier_set(modifiers: dict[str, LearningModifier], *, source_scorecard: str | None,
                       min_samples: int, now: datetime, mode: str = "demo_auto_learning",
                       cycle_id: str | None = None, expires_at: str | None = None,
                       baseline_summary: dict | None = None, candidate_summary: dict | None = None,
                       decision: str | None = None, reason: str | None = None) -> dict[str, Any]:
    """
    Like build_active_payload but carries the LM86C cycle metadata (cycle_id,
    expires_at, baseline/candidate summaries, accept/reject decision + reason).
    Only ACTIVE-status modifiers are written; values stay confidence-only.
    """
    active = {s: m.to_dict() for s, m in modifiers.items() if m.status == ACTIVE}
    return {
        "generated_at": now.isoformat(),
        "source_scorecard": source_scorecard,
        "mode": mode,
        "safety": "demo_only",
        "min_samples": min_samples,
        "active_count": len(active),
        "cycle_id": cycle_id,
        "expires_at": expires_at,
        "decision": decision,
        "reason": reason,
        "baseline_summary": baseline_summary,
        "candidate_summary": candidate_summary,
        "modifiers": active,
    }


def promote_candidate(learning_dir: str | Path = DEFAULT_LEARNING_DIR, *,
                      min_samples: int = DEFAULT_MIN_SAMPLES, now: datetime | None = None,
                      cycle_id: str | None = None, expiry_days: int | None = DEFAULT_EXPIRY_DAYS,
                      write: bool = True) -> tuple[dict, dict[str, LearningModifier], list[str]]:
    """
    Promote the LM86A preview into a CANDIDATE set (candidate_demo_modifiers.json).
    This NEVER touches active_demo_modifiers.json - the candidate only becomes
    active after the cycle's objective comparison accepts it (activate_candidate).
    """
    now = now or datetime.now(timezone.utc)
    d = Path(learning_dir)
    preview, warnings = read_preview(d)
    evaluated = evaluate_preview(preview, min_samples=min_samples, now=now)
    exp = _expires_at(now, expiry_days)
    for m in evaluated.values():
        m.expires_at = exp
    source = next((m.source_scorecard for m in evaluated.values() if m.source_scorecard), None)
    payload = build_modifier_set(evaluated, source_scorecard=source, min_samples=min_samples,
                                 now=now, mode="demo_auto_learning_candidate", cycle_id=cycle_id,
                                 expires_at=exp)
    if write and preview:
        d.mkdir(parents=True, exist_ok=True)
        (d / CANDIDATE_FILE).write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return payload, evaluated, warnings


def activate_candidate(learning_dir: str | Path, candidate_payload: dict, *,
                       now: datetime | None = None, reason: str | None = None,
                       baseline_summary: dict | None = None,
                       candidate_summary: dict | None = None) -> tuple[Path, Path | None]:
    """
    Accept a candidate: back up the current active file (if any) to
    active_demo_modifiers.backup.json, then write the candidate as the new active
    set tagged accepted. Returns (active_path, backup_path_or_None).
    """
    now = now or datetime.now(timezone.utc)
    d = Path(learning_dir)
    d.mkdir(parents=True, exist_ok=True)
    active = d / ACTIVE_FILE
    backup = d / BACKUP_FILE
    backed_up: Path | None = None
    if active.exists():
        backup.write_text(active.read_text(encoding="utf-8"), encoding="utf-8")
        backed_up = backup
    payload = {**candidate_payload, "mode": "demo_auto_learning", "decision": "accepted",
               "reason": reason, "baseline_summary": baseline_summary,
               "candidate_summary": candidate_summary, "activated_at": now.isoformat()}
    active.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return active, backed_up


def write_rejected(learning_dir: str | Path, candidate_payload: dict, *, reason: str,
                   now: datetime | None = None, baseline_summary: dict | None = None,
                   candidate_summary: dict | None = None) -> Path:
    """
    Record a rejected candidate to rejected_demo_modifiers.json. Does NOT touch
    the active file - the current active modifiers are kept unchanged.
    """
    now = now or datetime.now(timezone.utc)
    d = Path(learning_dir)
    d.mkdir(parents=True, exist_ok=True)
    payload = {**candidate_payload, "decision": "rejected", "reason": reason,
               "baseline_summary": baseline_summary, "candidate_summary": candidate_summary,
               "rejected_at": now.isoformat()}
    p = d / REJECTED_FILE
    p.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return p


def rollback_active(learning_dir: str | Path = DEFAULT_LEARNING_DIR) -> tuple[bool, str]:
    """
    Restore active_demo_modifiers.backup.json -> active_demo_modifiers.json. Pure
    file restore; returns (ok, message). No backup present -> (False, message).
    """
    d = Path(learning_dir)
    active = d / ACTIVE_FILE
    backup = d / BACKUP_FILE
    if not backup.exists():
        return False, f"no backup at {backup} - nothing to roll back."
    active.write_text(backup.read_text(encoding="utf-8"), encoding="utf-8")
    return True, f"restored {active.name} from {backup.name}."


def modifiers_expired(path: str | Path = DEFAULT_ACTIVE_MODIFIERS_PATH, *,
                      now: datetime | None = None) -> tuple[bool, str | None]:
    """
    Check an active/candidate file's expires_at. Returns (expired, expires_at_iso).
    Missing file / no expiry / unreadable -> (False, expires_at_or_None). This
    patch only WARNS on expiry; it never auto-deletes a stale set.
    """
    now = now or datetime.now(timezone.utc)
    p = Path(path)
    if not p.exists():
        return False, None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False, None
    exp = data.get("expires_at") if isinstance(data, dict) else None
    if not exp:
        return False, None
    try:
        dt = datetime.fromisoformat(str(exp).replace("Z", "+00:00"))
    except ValueError:
        return False, exp
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return now > dt, exp


def contract_violations(payload: Any, *, now: datetime | None = None) -> list[str]:
    """
    LM87A: validate an active demo modifier payload against the demo-only,
    confidence-only contract. Returns a list of human-readable violations (empty
    == passes). Checks: safety == demo_only, mode == demo_auto_learning, not
    expired, no forbidden keys (top level or per-setup), and every
    confidence_modifier within the hard clamp [-20, +12]. Pure; never raises.
    """
    now = now or datetime.now(timezone.utc)
    if not isinstance(payload, dict):
        return ["payload is not a JSON object"]
    v: list[str] = []
    if payload.get("safety") != "demo_only":
        v.append(f"safety != demo_only (got {payload.get('safety')!r})")
    if payload.get("mode") != "demo_auto_learning":
        v.append(f"mode != demo_auto_learning (got {payload.get('mode')!r})")
    exp = payload.get("expires_at")
    if exp:
        try:
            dt = datetime.fromisoformat(str(exp).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if now > dt:
                v.append(f"expired at {exp}")
        except ValueError:
            v.append(f"unparseable expires_at {exp!r}")
    for k in FORBIDDEN_MODIFIER_KEYS:
        if k in payload:
            v.append(f"forbidden key '{k}' at top level")
    mods = payload.get("modifiers")
    if isinstance(mods, dict):
        for setup, e in mods.items():
            if not isinstance(e, dict):
                continue
            for k in FORBIDDEN_MODIFIER_KEYS:
                if k in e:
                    v.append(f"forbidden key '{k}' in modifier '{setup}'")
            cm = e.get("confidence_modifier")
            try:
                cmv = float(cm)
            except (TypeError, ValueError):
                v.append(f"modifier '{setup}' confidence_modifier not numeric: {cm!r}")
                continue
            if cmv < HARD_MIN_MODIFIER or cmv > HARD_MAX_MODIFIER:
                v.append(f"modifier '{setup}' confidence_modifier {cm} out of clamp "
                         f"[{HARD_MIN_MODIFIER}, {HARD_MAX_MODIFIER}]")
    return v
