"""
tests/test_gold_bot_learning_cycle.py
--------------------------------------
LM86C - Automatic demo-only learning cycle. No MT5, no internet, temp dirs only.

The replay + scorecard steps are injected with fakes so the whole cycle runs
offline against deterministic summary data.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from services.gold_bot_learning_cycle import (
    CYCLE_EVENTS_FILE,
    compare_summaries,
    extract_summary,
    run_cycle,
    run_rollback,
)
from services.gold_bot_learning_modifiers import (
    ACTIVE_FILE,
    BACKUP_FILE,
    CANDIDATE_FILE,
    REJECTED_FILE,
    promote_candidate,
)

NOW = datetime(2026, 6, 13, tzinfo=timezone.utc)
_REPO = Path(__file__).resolve().parent.parent

# A preview with one high-sample "avoid" setup so promote_candidate yields an
# ACTIVE candidate modifier (confidence-only, negative nudge).
_PREVIEW = {
    "_note": "PREVIEW",
    "momentum": {
        "setup": "momentum", "confidence_modifier": -8, "status": "avoid",
        "sample_count": 300, "expectancy_points": -76.0, "winrate": 0.22, "horizon": 15,
        "source_scorecard": "scorecard_X.json",
        "reason": "avoid: expectancy -76.0pt at horizon 15 over 300 samples",
    },
}


def _summary(*, h=15, win, loss, neutral=0, no_data=0, no_trade=150, avg, used_learning=False):
    trades = win + loss + neutral + no_data
    long = trades // 2
    return {
        "symbol": "XAUUSD", "timeframe": "M1", "risk_mode": "balanced",
        "used_learning_modifiers": used_learning,
        "decisions": {"long": long, "short": trades - long, "no_trade": no_trade},
        "avg_confidence": 55.0,
        "by_horizon": {str(h): {"win": win, "loss": loss, "neutral": neutral, "no_data": no_data,
                                "no_trade": no_trade, "avg_trade_return_points": avg}},
        "top_setups": [{"strategy": "fvg_retest", "count": 10}],
        "bars_processed": trades + no_trade, "replay_id": "r_learn" if used_learning else "r_base",
    }


# Real LM85A-observed numbers: learning made replay WORSE at h15.
BASELINE = _summary(win=86, loss=230, neutral=34, avg=-41.1)
WORSE = _summary(win=77, loss=211, neutral=29, avg=-49.8, used_learning=True)
BETTER = _summary(win=140, loss=200, neutral=30, avg=-15.0, used_learning=True)
COLLAPSE = _summary(win=40, loss=45, neutral=5, no_trade=400, avg=-5.0, used_learning=True)  # +exp, few trades


def _run(tmp_path, baseline, candidate, *, preexisting_active=None, **kw):
    ldir = tmp_path / "learning"
    ldir.mkdir(parents=True, exist_ok=True)
    if preexisting_active is not None:
        (ldir / ACTIVE_FILE).write_text(json.dumps(preexisting_active), encoding="utf-8")

    def replay_runner(*, use_learning, modifiers_file):
        return candidate if use_learning else baseline

    def scorecard_runner():
        (ldir / "setup_modifiers.preview.json").write_text(json.dumps(_PREVIEW), encoding="utf-8")

    result = run_cycle(learning_dir=ldir, replay_out_dir=tmp_path / "replay",
                       replay_runner=replay_runner, scorecard_runner=scorecard_runner,
                       now=NOW, **kw)
    return result, ldir


# ── extract_summary ───────────────────────────────────────────────────────────────
def test_extract_summary_basic():
    v = extract_summary(BASELINE, 15)
    assert v["no_data"] is False
    assert v["trade_count"] == 350            # 86+230+34
    assert v["expectancy_points"] == -41.1
    assert v["winrate"] == round(86 / (86 + 230), 3)


def test_extract_summary_missing_horizon_is_no_data():
    assert extract_summary(BASELINE, 999)["no_data"] is True
    assert extract_summary(None, 15)["no_data"] is True
    assert extract_summary({}, 15)["no_data"] is True


# ── compare_summaries (pure) ───────────────────────────────────────────────────────
def test_compare_accepts_improved_expectancy():
    cmp = compare_summaries(BASELINE, BETTER, horizon=15)
    assert cmp["accepted"] is True
    assert cmp["expectancy_improvement"] > 10
    assert cmp["checks"]["expectancy_improved"] and cmp["checks"]["min_trades"]
    assert "accepted" in cmp["reason"]


def test_compare_rejects_worse_expectancy():
    cmp = compare_summaries(BASELINE, WORSE, horizon=15)
    assert cmp["accepted"] is False
    assert cmp["checks"]["expectancy_improved"] is False
    assert "rejected" in cmp["reason"]


def test_compare_rejects_trade_count_collapse():
    # Expectancy improves strongly, but candidate trades collapse below the ratio.
    cmp = compare_summaries(BASELINE, COLLAPSE, horizon=15)
    assert cmp["accepted"] is False
    assert cmp["checks"]["expectancy_improved"] is True
    assert cmp["checks"]["trade_count_kept"] is False
    assert "trade count collapsed" in cmp["reason"]


def test_compare_handles_missing_summaries_safely():
    for base, cand in ((None, BETTER), (BASELINE, None), ({}, {}), (None, None)):
        cmp = compare_summaries(base, cand, horizon=15)
        assert cmp["accepted"] is False
        assert "no scored trades" in cmp["reason"]


def test_compare_respects_min_improvement_threshold():
    near = _summary(win=90, loss=230, neutral=34, avg=-35.0, used_learning=True)  # +6.1pt only
    assert compare_summaries(BASELINE, near, horizon=15, min_improvement_points=10)["accepted"] is False
    assert compare_summaries(BASELINE, near, horizon=15, min_improvement_points=5)["accepted"] is True


# ── candidate staging never overwrites active ──────────────────────────────────────
def test_candidate_does_not_overwrite_active(tmp_path):
    ldir = tmp_path / "learning"
    ldir.mkdir()
    (ldir / "setup_modifiers.preview.json").write_text(json.dumps(_PREVIEW), encoding="utf-8")
    payload, evaluated, warns = promote_candidate(ldir, min_samples=10, now=NOW, cycle_id="cycle_x")
    assert (ldir / CANDIDATE_FILE).exists()
    assert not (ldir / ACTIVE_FILE).exists()          # candidate staged, active untouched
    assert payload["mode"] == "demo_auto_learning_candidate"
    assert "momentum" in payload["modifiers"]


# ── accepted cycle ──────────────────────────────────────────────────────────────────
def test_accepted_cycle_backs_up_and_replaces_active(tmp_path):
    sentinel = {"marker": "OLD", "modifiers": {}}
    result, ldir = _run(tmp_path, BASELINE, BETTER, preexisting_active=sentinel)
    assert result.accepted is True
    # old active was backed up verbatim, then replaced
    assert json.loads((ldir / BACKUP_FILE).read_text()) == sentinel
    active = json.loads((ldir / ACTIVE_FILE).read_text())
    assert active.get("marker") != "OLD"
    assert active["decision"] == "accepted"
    assert active["mode"] == "demo_auto_learning"
    assert "momentum" in active["modifiers"]
    assert not (ldir / REJECTED_FILE).exists()


def test_accepted_active_is_demo_only_and_confidence_only(tmp_path):
    result, ldir = _run(tmp_path, BASELINE, BETTER)
    blob = (ldir / ACTIVE_FILE).read_text().lower()
    assert '"safety": "demo_only"' in blob
    for forbidden in ("order_send", "live_trading", '"volume"', '"lot"', "metatrader5"):
        assert forbidden not in blob


# ── rejected cycle ──────────────────────────────────────────────────────────────────
def test_rejected_cycle_keeps_active_writes_rejected(tmp_path):
    sentinel = {"marker": "KEEP", "modifiers": {}}
    result, ldir = _run(tmp_path, BASELINE, WORSE, preexisting_active=sentinel)
    assert result.accepted is False
    assert json.loads((ldir / ACTIVE_FILE).read_text()) == sentinel   # unchanged
    assert not (ldir / BACKUP_FILE).exists()                          # no backup on reject
    rejected = json.loads((ldir / REJECTED_FILE).read_text())
    assert rejected["decision"] == "rejected"
    assert "momentum" in rejected["modifiers"]


def test_cycle_writes_summary_and_event(tmp_path):
    result, ldir = _run(tmp_path, BASELINE, WORSE)
    summary_path = Path(result.cycle_summary_path)
    assert summary_path.exists() and summary_path.parent.name == "cycles"
    payload = json.loads(summary_path.read_text())
    assert payload["safety"] == "demo_only"
    assert payload["accepted"] is False
    events = (ldir / "cycles" / CYCLE_EVENTS_FILE).read_text().strip().splitlines()
    assert json.loads(events[-1])["event"] == "rejected"


# ── rollback ────────────────────────────────────────────────────────────────────────
def test_rollback_restores_backup(tmp_path):
    ldir = tmp_path / "learning"
    ldir.mkdir()
    (ldir / ACTIVE_FILE).write_text(json.dumps({"marker": "NEW"}), encoding="utf-8")
    (ldir / BACKUP_FILE).write_text(json.dumps({"marker": "OLD"}), encoding="utf-8")
    ok, message = run_rollback(ldir, now=NOW)
    assert ok is True
    assert json.loads((ldir / ACTIVE_FILE).read_text()) == {"marker": "OLD"}
    events = (ldir / "cycles" / CYCLE_EVENTS_FILE).read_text().strip().splitlines()
    assert json.loads(events[-1])["event"] == "rollback"


def test_rollback_without_backup_is_safe_noop(tmp_path):
    ldir = tmp_path / "learning"
    ldir.mkdir()
    ok, message = run_rollback(ldir, now=NOW)
    assert ok is False and "nothing to roll back" in message


# ── expiry metadata ──────────────────────────────────────────────────────────────────
def test_expiry_metadata_present_on_accept(tmp_path):
    result, ldir = _run(tmp_path, BASELINE, BETTER, expiry_days=7)
    active = json.loads((ldir / ACTIVE_FILE).read_text())
    assert active["cycle_id"] == result.cycle_id
    assert active["expires_at"]                       # set, non-null
    assert active["expires_at"].startswith("2026-06-20")   # NOW + 7 days
    for mod in active["modifiers"].values():
        assert "expires_at" in mod and "generated_at" in mod


# ── dry-run ──────────────────────────────────────────────────────────────────────────
def test_dry_run_writes_nothing(tmp_path):
    ldir = tmp_path / "learning"
    ldir.mkdir()
    result = run_cycle(learning_dir=ldir, replay_out_dir=tmp_path / "replay",
                       history_dir=tmp_path / "nohist", dry_run=True, now=NOW)
    assert result.dry_run is True
    assert result.planned_steps
    # nothing written: no candidate/active/rejected/cycles
    assert not (ldir / CANDIDATE_FILE).exists()
    assert not (ldir / ACTIVE_FILE).exists()
    assert not (ldir / REJECTED_FILE).exists()
    assert not (ldir / "cycles").exists()


# ── safety: no MT5 / orders / network ────────────────────────────────────────────────
def test_no_mt5_imported_during_injected_cycle(tmp_path):
    _run(tmp_path, BASELINE, WORSE)
    assert "MetaTrader5" not in sys.modules


def test_service_sources_have_no_mt5_orders_or_http():
    for fname in ("gold_bot_learning_cycle.py", "gold_bot_learning_modifiers.py"):
        src = (_REPO / "services" / fname).read_text(encoding="utf-8")
        for forbidden in ("MetaTrader5", "order_send", "import requests", "urllib", "socket("):
            assert forbidden not in src, f"{fname} must not reference {forbidden}"


# ── CLI argument defaults ─────────────────────────────────────────────────────────────
def _load_cli():
    spec = importlib.util.spec_from_file_location(
        "run_gold_bot_learning_cycle", _REPO / "scripts" / "run_gold_bot_learning_cycle.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_cli_args_parse_defaults():
    cli = _load_cli()
    args = cli.parse_args([])
    assert args.symbol == "XAUUSD"
    assert args.timeframe == "M1"
    assert args.risk_mode == "balanced"
    assert args.max_bars == 500
    assert args.horizon == 15
    assert args.min_samples == 10
    assert args.min_trades == 30
    assert args.min_improvement_points == 10.0
    assert args.min_trade_count_ratio == 0.5
    assert args.dry_run is False and args.rollback is False


def test_cli_args_parse_overrides():
    cli = _load_cli()
    args = cli.parse_args(["--horizon", "30", "--min-improvement-points", "25",
                           "--rollback", "--dry-run"])
    assert args.horizon == 30
    assert args.min_improvement_points == 25.0
    assert args.rollback is True and args.dry_run is True
