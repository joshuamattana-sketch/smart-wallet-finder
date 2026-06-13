"""
tests/test_gold_bot_learning_modifiers.py
-------------------------------------------
LM86B — Demo-only learning modifier promotion + loading. No MT5, no internet.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from services.gold_bot_learning_modifiers import (
    ACTIVE,
    HARD_MAX_MODIFIER,
    HARD_MIN_MODIFIER,
    MAX_NEGATIVE_MODIFIER,
    MAX_POSITIVE_MODIFIER,
    clamp_modifier,
    evaluate_preview,
    load_active_modifiers,
    promote,
)

NOW = datetime(2026, 6, 12, tzinfo=timezone.utc)


def _preview(**setups):
    out = {"_note": "PREVIEW"}
    out.update(setups)
    return out


def _entry(mod, samples, *, status="promising", reason="ok"):
    return {"confidence_modifier": mod, "status": status, "sample_count": samples,
            "expectancy_points": 100.0, "winrate": 0.6, "horizon": 15,
            "source_scorecard": "scorecard_X.json", "reason": reason}


def _write_preview(tmp_path, preview):
    d = tmp_path / "learning"
    d.mkdir(parents=True, exist_ok=True)
    (d / "setup_modifiers.preview.json").write_text(json.dumps(preview), encoding="utf-8")
    return d


# ── clamp ──────────────────────────────────────────────────────────────────────
def test_clamp_promotion_bounds():
    assert clamp_modifier(50) == MAX_POSITIVE_MODIFIER       # +8
    assert clamp_modifier(-50) == MAX_NEGATIVE_MODIFIER      # -12
    assert clamp_modifier(3) == 3


def test_clamp_hard_bounds_on_load():
    assert clamp_modifier(999, promotion=False) == HARD_MAX_MODIFIER     # +12
    assert clamp_modifier(-999, promotion=False) == HARD_MIN_MODIFIER    # -20
    assert clamp_modifier("bad") == 0


# ── evaluate ────────────────────────────────────────────────────────────────────
def test_evaluate_active_when_enough_samples():
    ev = evaluate_preview(_preview(momentum=_entry(5, 30)), min_samples=20, now=NOW)
    assert ev["momentum"].status == ACTIVE
    assert ev["momentum"].confidence_modifier == 5


def test_evaluate_insufficient_sample_rejected():
    ev = evaluate_preview(_preview(fvg_retest=_entry(-8, 5)), min_samples=20, now=NOW)
    assert ev["fvg_retest"].status == "insufficient_sample"
    assert ev["fvg_retest"].confidence_modifier == 0          # zeroed when not active


def test_evaluate_missing_reason_rejected():
    ev = evaluate_preview(_preview(x=_entry(5, 30, reason="")), min_samples=20, now=NOW)
    assert ev["x"].status == "rejected"


def test_evaluate_clamps_value():
    ev = evaluate_preview(_preview(big=_entry(99, 40)), min_samples=20, now=NOW)
    assert ev["big"].confidence_modifier == MAX_POSITIVE_MODIFIER


# ── promote ──────────────────────────────────────────────────────────────────────
def test_promote_writes_active_and_events(tmp_path):
    d = _write_preview(tmp_path, _preview(
        momentum=_entry(5, 30), fvg_retest=_entry(-8, 25, status="avoid"),
        scalp=_entry(5, 3)))                                  # insufficient
    payload, evaluated, warns = promote(d, min_samples=20, now=NOW)
    assert payload["mode"] == "demo_auto_learning" and payload["safety"] == "demo_only"
    assert set(payload["modifiers"]) == {"momentum", "fvg_retest"}    # scalp excluded
    assert (d / "active_demo_modifiers.json").exists()
    assert (d / "modifier_events.jsonl").exists()
    ev_line = json.loads((d / "modifier_events.jsonl").read_text().strip())
    assert "scalp" in ev_line["rejected"]


def test_promote_missing_preview_warns(tmp_path):
    payload, evaluated, warns = promote(tmp_path / "empty", min_samples=20)
    assert evaluated == {} and warns
    assert not (tmp_path / "empty" / "active_demo_modifiers.json").exists()


# ── load_active_modifiers ─────────────────────────────────────────────────────────
def test_load_active_only_active_and_clamped(tmp_path):
    d = _write_preview(tmp_path, _preview(momentum=_entry(5, 30), fvg=_entry(-8, 25, status="avoid")))
    promote(d, min_samples=20, now=NOW)
    mods, warns = load_active_modifiers(d / "active_demo_modifiers.json")
    assert warns == []
    assert "momentum" in mods and mods["momentum"]["confidence_modifier"] == 5


def test_load_missing_file_warns_no_crash(tmp_path):
    mods, warns = load_active_modifiers(tmp_path / "nope.json")
    assert mods == {} and warns and "not found" in warns[0]


def test_load_invalid_file_warns_no_crash(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{ not json", encoding="utf-8")
    mods, warns = load_active_modifiers(p)
    assert mods == {} and warns


def test_load_hard_clamps_handedited_values(tmp_path):
    p = tmp_path / "active.json"
    p.write_text(json.dumps({"modifiers": {
        "x": {"confidence_modifier": 999, "status": "active", "reason": "r"},
        "y": {"confidence_modifier": -999, "status": "active", "reason": "r"},
        "z": {"confidence_modifier": 5, "status": "inactive", "reason": "r"}}}),
        encoding="utf-8")
    mods, _w = load_active_modifiers(p)
    assert mods["x"]["confidence_modifier"] == HARD_MAX_MODIFIER
    assert mods["y"]["confidence_modifier"] == HARD_MIN_MODIFIER
    assert "z" not in mods                                    # inactive dropped


# ── safety: modifiers carry no live-trading switch ────────────────────────────────
def test_modifiers_are_demo_only_and_confidence_only(tmp_path):
    d = _write_preview(tmp_path, _preview(momentum=_entry(5, 30)))
    payload, _e, _w = promote(d, min_samples=20, now=NOW)
    blob = json.dumps(payload).lower()
    assert payload["safety"] == "demo_only"
    for forbidden in ("live", "volume", "lot", "order_send", "real"):
        assert forbidden not in blob
