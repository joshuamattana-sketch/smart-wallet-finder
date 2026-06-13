"""
tests/test_gold_bot_learning_output_truth.py
----------------------------------------------
LM97A - Truthful learning output (copy only). Guards the wording fix: the
scorecard / modifier probe / session review must clearly distinguish PREVIEW
(read-only, not active) from ACTIVE modifiers (used only with
--use-learning-modifiers), state replay-dominance when there are 0 real demo
trades, and never claim modifiers are "not wired into the decision engine".
No strategy/math change, no auto-promote, no live, no UI/API/Heatmap change.
"""

from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
SCORECARD = _ROOT / "scripts" / "run_gold_bot_learning_scorecard.py"
PROBE = _ROOT / "scripts" / "run_gold_bot_learning_modifiers_probe.py"
REVIEW = _ROOT / "services" / "gold_bot_session_review.py"
JOURNAL = _ROOT / "services" / "gold_bot_learning_journal.py"
PANEL = _ROOT / "lumora-web" / "components" / "gold-bot" / "GoldBotStatusPanel.tsx"
TOUCHED = (SCORECARD, PROBE, REVIEW, JOURNAL)


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


# ── scorecard wording ───────────────────────────────────────────────────────────────
def test_scorecard_removes_misleading_live_impact():
    src = _read(SCORECARD)
    assert "not wired into the decision engine" not in src
    assert "live impact" not in src.lower()


def test_scorecard_truthful_impact_block():
    src = _read(SCORECARD)
    assert "read-only preview" in src
    assert "--use-learning-modifiers" in src
    assert "setup_modifiers.preview.json, not active" in src
    assert "active_demo_modifiers.json" in src
    # 0 real demo trades -> replay-dominant message exists
    assert "0 trades - learning is replay-dominant" in src
    assert "replay-dominant" in src
    # real-trade branch keeps the weighted wording
    assert "trades included with weight" in src
    assert "live trading      : locked" in src


# ── modifier probe wording ────────────────────────────────────────────────────────
def test_modifier_probe_clarifies_preview_vs_active():
    src = _read(PROBE)
    assert "NOT active unless promoted" in src
    assert "preview only - not active unless promoted" in src
    # active set is described as what decisions use with the flag
    assert "--use-learning-modifiers" in src


def test_modifier_probe_does_not_auto_promote():
    src = _read(PROBE)
    # promotion only happens when --promote is passed (write=args.promote)
    assert "write=args.promote" in src
    assert "write=True" not in src
    # math display unchanged (no threshold/clamp edit)
    assert "clamp +8/-12 (hard -20/+12)" in src


# ── session review wording ──────────────────────────────────────────────────────────
def test_session_review_real_demo_wording_clear():
    src = _read(REVIEW)
    assert "Real demo outcomes" in src
    assert "replay-dominant" in src
    # the confusing "True (0 trades)" form is gone
    assert "Real demo used" not in src
    assert "real_trades_used')} (" not in src


# ── journal docstring truthful ──────────────────────────────────────────────────────
def test_journal_docstring_truthful():
    src = _read(JOURNAL)
    assert "deliberately NOT wired into the decision engine or worker" not in src
    assert "never read by the decision engine" in src
    assert "--use-learning-modifiers" in src


# ── no live / no heatmap in touched output files ────────────────────────────────────
def test_touched_files_no_live_enable_or_heatmap():
    for p in TOUCHED:
        src = _read(p)
        assert "--allow-live-trading" not in src, f"{p.name} must not enable live"
        assert "heatmap" not in src.lower(), f"{p.name} must not touch heatmap"


# ── UI unchanged: no misleading learning text, panel still read-only ────────────────
def test_status_panel_has_no_misleading_learning_text():
    src = _read(PANEL)
    assert "not wired" not in src.lower()
    assert "live impact" not in src.lower()
    # the read-only panel copy is intact (no layout change here)
    assert "Read-only status. No trading controls" in src
