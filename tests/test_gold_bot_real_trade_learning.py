"""
tests/test_gold_bot_real_trade_learning.py
--------------------------------------------
LM89B - Real demo-trade ingestion into learning. Fake learning_events.jsonl;
no MT5, no internet.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from services.gold_bot_learning_journal import (
    build_real_trade_stats,
    build_setup_modifiers_preview,
    load_demo_trade_outcomes,
    merge_real_into_scorecard,
    _blend,
)

_REPO = Path(__file__).resolve().parent.parent


def _ev(**kw):
    base = {"event": "demo_trade_outcome", "source": "mt5_demo", "trade_id": 1,
            "setup": "momentum", "side": "LONG", "confidence": 75, "learning_modifier": -8,
            "risk_mode": "scalp", "pnl": 10.0, "pnl_points": 100.0, "outcome": "win",
            "exit_reason": "tp", "session_id": "s", "recorded_at": "2026-06-13T12:00:00+00:00"}
    base.update(kw)
    return base


def _write(tmp_path, rows, name="learning_events.jsonl"):
    p = tmp_path / name
    p.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    return p


# ── parsing / filtering ─────────────────────────────────────────────────────────
def test_parse_demo_outcome_events(tmp_path):
    p = _write(tmp_path, [_ev(trade_id=1), _ev(trade_id=2, outcome="loss", pnl=-5.0),
                          {"event": "scorecard_built", "trade_id": 9}])   # non-outcome ignored
    outs, warns, dups = load_demo_trade_outcomes(p)
    assert len(outs) == 2 and dups == 0


def test_duplicate_trade_id_ignored(tmp_path):
    p = _write(tmp_path, [_ev(trade_id=1), _ev(trade_id=1, pnl=99.0), _ev(trade_id=2)])
    outs, warns, dups = load_demo_trade_outcomes(p)
    assert {o["trade_id"] for o in outs} == {1, 2} and dups == 1


def test_open_unknown_ignored_by_default(tmp_path):
    p = _write(tmp_path, [_ev(trade_id=1, outcome="open"), _ev(trade_id=2, outcome="unknown"),
                          _ev(trade_id=3, outcome="win")])
    assert len(load_demo_trade_outcomes(p)[0]) == 1
    assert len(load_demo_trade_outcomes(p, include_open=True)[0]) == 3


def test_non_demo_source_ignored(tmp_path):
    p = _write(tmp_path, [_ev(trade_id=1), _ev(trade_id=2, source="backtest")])
    assert {o["trade_id"] for o in load_demo_trade_outcomes(p)[0]} == {1}


def test_missing_fields_graceful(tmp_path):
    p = _write(tmp_path, [{"event": "demo_trade_outcome", "source": "mt5_demo", "trade_id": 7,
                           "outcome": "loss"}])
    o = load_demo_trade_outcomes(p)[0][0]
    assert o["setup"] == "unknown" and o["confidence"] is None and o["pnl"] is None


# ── stats ────────────────────────────────────────────────────────────────────────
def test_by_setup_and_risk_mode_stats(tmp_path):
    rows = [_ev(trade_id=1, setup="momentum", outcome="win", pnl=10, pnl_points=100),
            _ev(trade_id=2, setup="momentum", outcome="loss", pnl=-6, pnl_points=-60),
            _ev(trade_id=3, setup="fvg_retest", risk_mode="balanced", outcome="loss", pnl=-4)]
    outs = load_demo_trade_outcomes(_write(tmp_path, rows))[0]
    stats = build_real_trade_stats(outs, min_real_trades=5)
    mom = stats["by_setup"]["momentum"]
    assert mom["trade_count"] == 2 and mom["win_count"] == 1 and mom["winrate"] == 0.5
    assert mom["realized_pnl"] == 4.0 and mom["avg_pnl_points"] == 20.0
    assert "scalp" in stats["by_risk_mode"] and "balanced" in stats["by_risk_mode"]


def test_min_real_trades_sample_guard(tmp_path):
    rows = [_ev(trade_id=i) for i in range(3)]
    stats = build_real_trade_stats(load_demo_trade_outcomes(_write(tmp_path, rows))[0],
                                   min_real_trades=5)
    assert stats["global"]["sample_quality"] == "insufficient"
    assert stats["global"]["trade_count"] == 3


def test_loss_streak_max(tmp_path):
    rows = [_ev(trade_id=1, outcome="loss", recorded_at="2026-06-13T12:00:01"),
            _ev(trade_id=2, outcome="loss", recorded_at="2026-06-13T12:00:02"),
            _ev(trade_id=3, outcome="win", recorded_at="2026-06-13T12:00:03"),
            _ev(trade_id=4, outcome="loss", recorded_at="2026-06-13T12:00:04")]
    stats = build_real_trade_stats(load_demo_trade_outcomes(_write(tmp_path, rows))[0])
    assert stats["global"]["loss_streak_max"] == 2


# ── blending ──────────────────────────────────────────────────────────────────────
def test_blend_basic():
    # replay -40 over 445, real +20 over 8, weight 2 -> ~-37.9 (still near replay)
    combined = _blend(-40.0, 445, 20.0, 8, 2.0)
    assert -40 < combined < -35


def test_real_weight_does_not_dominate_small_sample(tmp_path):
    sc = {"min_samples": 20, "by_setup": {
        "momentum": {"trade_count": 445, "expectancy_points": -40.0, "winrate": 0.33,
                     "recommended_status": "avoid"}}}
    rows = [_ev(trade_id=i, setup="momentum", outcome="win", pnl=20, pnl_points=20) for i in range(8)]
    real = build_real_trade_stats(load_demo_trade_outcomes(_write(tmp_path, rows))[0])
    merge_real_into_scorecard(sc, real, real_trade_weight=2.0)
    v = sc["by_setup"]["momentum"]
    assert v["replay_trade_count"] == 445 and v["real_trade_count"] == 8
    assert v["combined_expectancy"] < 0                           # not flipped by 8 demo wins
    assert abs(v["combined_expectancy"] - (-40)) < abs(v["combined_expectancy"] - 20)
    assert v["real_contradicts_replay"] is True
    assert v["recommended_status_combined"] == "avoid"


def test_combined_status_used_in_scorecard_flag(tmp_path):
    sc = {"min_samples": 20, "by_setup": {
        "momentum": {"trade_count": 30, "expectancy_points": -40.0, "winrate": 0.33,
                     "recommended_status": "avoid"}}}
    real = build_real_trade_stats([])
    merge_real_into_scorecard(sc, real, real_trade_weight=2.0)
    assert sc["include_real_trades"] is True and sc["real_trade_weight"] == 2.0
    assert sc["by_setup"]["momentum"]["real_trade_count"] == 0


# ── modifier preview reasons ────────────────────────────────────────────────────────
def test_modifier_reason_includes_real_demo(tmp_path):
    sc = {"horizon": 15, "min_samples": 20, "by_setup": {
        "momentum": {"trade_count": 445, "expectancy_points": -40.0, "winrate": 0.33,
                     "recommended_status": "avoid"}}}
    rows = [_ev(trade_id=i, setup="momentum", outcome="loss", pnl=-12, pnl_points=-12)
            for i in range(8)]
    real = build_real_trade_stats(load_demo_trade_outcomes(_write(tmp_path, rows))[0])
    merge_real_into_scorecard(sc, real, real_trade_weight=2.0)
    preview = build_setup_modifiers_preview(sc, source_scorecard="sc.json")
    reason = preview["momentum"]["reason"]
    assert "combined replay+demo" in reason
    assert "demo exp -12.0pt over 8" in reason
    assert preview["momentum"]["real_trade_count"] == 8


def test_modifier_reason_warns_on_contradiction_small_sample(tmp_path):
    sc = {"horizon": 15, "min_samples": 20, "by_setup": {
        "momentum": {"trade_count": 445, "expectancy_points": -40.0, "winrate": 0.33,
                     "recommended_status": "avoid"}}}
    rows = [_ev(trade_id=i, setup="momentum", outcome="win", pnl=30, pnl_points=30)
            for i in range(3)]                                   # tiny + contradicts
    real = build_real_trade_stats(load_demo_trade_outcomes(_write(tmp_path, rows))[0],
                                  min_real_trades=20)
    merge_real_into_scorecard(sc, real, real_trade_weight=2.0)
    preview = build_setup_modifiers_preview(sc, source_scorecard="sc.json")
    assert "real demo contradicts replay - sample small" in preview["momentum"]["reason"]


# ── no data is safe ──────────────────────────────────────────────────────────────────
def test_no_real_outcomes_is_safe(tmp_path):
    outs, warns, dups = load_demo_trade_outcomes(tmp_path / "missing.jsonl")
    assert outs == [] and warns and dups == 0
    stats = build_real_trade_stats(outs)
    assert stats["global"]["trade_count"] == 0


def test_generated_files_gitignored():
    gi = (_REPO / ".gitignore").read_text(encoding="utf-8")
    assert "real_trade_" in gi


# ── probe CLI ──────────────────────────────────────────────────────────────────────
def _load_probe():
    spec = importlib.util.spec_from_file_location(
        "run_gold_bot_real_trade_learning_probe",
        _REPO / "scripts" / "run_gold_bot_real_trade_learning_probe.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_probe_runs_with_no_outcomes(tmp_path, capsys):
    probe = _load_probe()
    rc = probe.main(["--learning-events-file", str(tmp_path / "none.jsonl")])
    assert rc == 0
    assert "No demo_trade_outcome events found yet" in capsys.readouterr().out


def test_probe_aggregates_and_json(tmp_path, capsys):
    probe = _load_probe()
    p = _write(tmp_path, [_ev(trade_id=1, outcome="win"), _ev(trade_id=2, outcome="loss", pnl=-5)])
    rc = probe.main(["--learning-events-file", str(p), "--min-real-trades", "1", "--json"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["enough_for_learning"] is True
    assert out["stats"]["global"]["trade_count"] == 2


def test_probe_args_defaults():
    probe = _load_probe()
    args = probe.parse_args([])
    assert args.min_real_trades == 5 and args.include_open is False and args.json_output is False
