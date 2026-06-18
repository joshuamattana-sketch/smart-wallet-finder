"""
tests/test_gold_bot_learning_journal.py
-----------------------------------------
LM86A — Pattern scoring / learning journal tests. No MT5, no internet.
Synthetic replay JSONL in temp dirs.
"""

from __future__ import annotations

import json
import sys

from services.gold_bot_learning_journal import (
    LEARNING_MODIFIERS_LIVE,
    build_scorecard,
    build_setup_modifiers_preview,
    load_replay_rows,
    recommended_status,
    write_scorecard,
)

MACRO = {"dxy_bias": "rising", "yields_bias": "falling", "risk_bias": "neutral", "vix_bias": "flat"}


def _score(h, dr, outcome):
    return {"horizon": h, "bars_available": h, "ret_points": dr, "dir_return_points": dr,
            "mfe_points": max(dr, 0.0) + 50, "mae_points": max(-dr, 0.0) + 50,
            "tp_hit": outcome == "win", "sl_hit": outcome == "loss", "outcome": outcome}


def _row(strategy, decision, conf, dr, outcome, *, tf="M1", macro=None,
         time="2026-06-01T13:00:00+00:00"):
    return {"replay_id": "r", "step": 0, "time": time, "symbol": "XAUUSD", "timeframe": tf,
            "current_close": 2300.0, "decision": decision, "strategy": strategy,
            "confidence": conf, "reasons": [], "blockers": [], "warnings": [],
            "macro": macro if macro is not None else dict(MACRO),
            "score": {"15": _score(15, dr, outcome)}}


def _make_replay(tmp_path, rows, *, risk_mode="balanced"):
    d = tmp_path / "replay"
    d.mkdir(parents=True, exist_ok=True)
    jl = d / "replay_XAUUSD_M1_20260612_001.jsonl"
    jl.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    (d / "replay_XAUUSD_M1_20260612_001.summary.json").write_text(
        json.dumps({"symbol": "XAUUSD", "timeframe": "M1", "risk_mode": risk_mode}),
        encoding="utf-8")
    return d


def _dataset():
    rows = []
    rows += [_row("momentum", "LONG", 75, 200.0, "win") for _ in range(25)]      # promising
    rows += [_row("fvg_retest", "SHORT", 55, -200.0, "loss") for _ in range(25)]  # avoid
    rows += [_row("breakout_retest", "LONG", 60, 10.0, "neutral") for _ in range(5)]  # insufficient
    rows += [_row("no_trade", "NO_TRADE", 0, 300.0, "no_trade") for _ in range(10)]  # missed moves
    return rows


# ── loading ──────────────────────────────────────────────────────────────────────
def test_load_replay_rows_skips_unreadable_file(tmp_path):
    # One corrupt replay .jsonl must not crash the whole learning build — it is
    # skipped with a warning (the sibling summary read is already guarded).
    d = tmp_path / "replay"
    d.mkdir(parents=True, exist_ok=True)
    (d / "replay_XAUUSD_M1_bad.jsonl").write_bytes(b"\xff\xfe not utf-8 \x80\x81")
    rows, files, warns = load_replay_rows(d, symbol="XAUUSD", timeframe="M1")
    assert rows == []
    assert any("unreadable" in w for w in warns)


def test_load_rows_enriches_risk_and_session(tmp_path):
    d = _make_replay(tmp_path, _dataset(), risk_mode="balanced")
    rows, files, warns = load_replay_rows(d)
    assert len(rows) == 65 and files
    assert all(r["risk_mode"] == "balanced" for r in rows)
    assert all(r["session"] == "NewYork" for r in rows)   # 13:00 UTC


def test_load_missing_fields_handled(tmp_path):
    d = tmp_path / "replay"
    d.mkdir()
    (d / "x.jsonl").write_text(
        json.dumps({"decision": "LONG", "strategy": "momentum"}) + "\n"   # no score/conf/time
        + "not json\n", encoding="utf-8")
    rows, files, warns = load_replay_rows(d)
    assert len(rows) == 1
    assert any("bad JSON" in w for w in warns)
    sc = build_scorecard(rows, horizon=15, min_samples=1)   # must not crash
    assert sc["rows"] == 1


def test_no_replay_files_reports_warning(tmp_path):
    rows, files, warns = load_replay_rows(tmp_path / "nope")
    assert rows == [] and files == []
    assert warns and "not found" in warns[0]


def test_filter_by_risk_mode(tmp_path):
    d = _make_replay(tmp_path, _dataset(), risk_mode="scalp")
    rows, _f, _w = load_replay_rows(d, risk_mode="balanced")
    assert rows == []
    rows2, _f2, _w2 = load_replay_rows(d, risk_mode="scalp")
    assert len(rows2) == 65


# ── recommended_status logic ──────────────────────────────────────────────────────
def test_recommended_status_rules():
    assert recommended_status(5, 100.0, 0.9, 20) == "insufficient_sample"
    assert recommended_status(30, 120.0, 0.6, 20) == "promising"
    assert recommended_status(30, -120.0, 0.4, 20) == "avoid"
    assert recommended_status(30, 5.0, 0.6, 20) == "weak"          # |exp| small
    assert recommended_status(30, 80.0, 0.47, 20) == "weak"        # winrate 0.45-0.50
    assert recommended_status(30, None, None, 20) == "mixed"


# ── scorecard aggregation ─────────────────────────────────────────────────────────
def test_scorecard_setup_statuses(tmp_path):
    rows, _f, warns = load_replay_rows(_make_replay(tmp_path, _dataset()))
    sc = build_scorecard(rows, horizon=15, min_samples=20, warnings=warns)
    bs = sc["by_setup"]
    assert bs["momentum"]["recommended_status"] == "promising"
    assert bs["momentum"]["expectancy_points"] == 200.0
    assert bs["momentum"]["winrate"] == 1.0
    assert bs["momentum"]["trade_count"] == 25
    assert bs["fvg_retest"]["recommended_status"] == "avoid"
    assert bs["breakout_retest"]["recommended_status"] == "insufficient_sample"


def test_confidence_buckets(tmp_path):
    rows, _f, _w = load_replay_rows(_make_replay(tmp_path, _dataset()))
    sc = build_scorecard(rows, horizon=15, min_samples=20)
    cb = sc["confidence_buckets"]
    assert "70-79" in cb and cb["70-79"]["trade_count"] == 25      # momentum conf 75
    assert "50-59" in cb and cb["50-59"]["trade_count"] == 25      # fvg conf 55
    assert "0-39" in cb                                            # NO_TRADE conf 0


def test_direction_timeframe_risk_slices(tmp_path):
    rows, _f, _w = load_replay_rows(_make_replay(tmp_path, _dataset()))
    sc = build_scorecard(rows, horizon=15, min_samples=20)
    assert set(sc["direction"]) == {"LONG", "SHORT"}              # NO_TRADE dropped
    assert sc["direction"]["LONG"]["trade_count"] == 30           # momentum + breakout
    assert "M1" in sc["by_timeframe"]
    assert "balanced" in sc["by_risk_mode"]
    assert "NewYork" in sc["by_session"]


def test_macro_slices_with_unknown_fallback(tmp_path):
    rows = _dataset()
    rows.append(_row("momentum", "LONG", 75, 100.0, "win", macro={}))   # missing macro dims
    d = _make_replay(tmp_path, rows)
    loaded, _f, _w = load_replay_rows(d)
    sc = build_scorecard(loaded, horizon=15, min_samples=20)
    assert "rising" in sc["macro"]["dxy_bias"]
    assert "unknown" in sc["macro"]["dxy_bias"]                   # the empty-macro row


def test_no_trade_missed_analysis(tmp_path):
    rows, _f, _w = load_replay_rows(_make_replay(tmp_path, _dataset()))
    sc = build_scorecard(rows, horizon=15, min_samples=20, missed_threshold=150.0)
    nt = sc["no_trade_missed"]["15"]
    assert nt["count"] == 10
    assert nt["missed_large_moves"] == 10                         # raw 300 > 150
    assert nt["avg_raw_move_points"] == 300.0


def test_top_and_weak_avoid_lists(tmp_path):
    rows, _f, _w = load_replay_rows(_make_replay(tmp_path, _dataset()))
    sc = build_scorecard(rows, horizon=15, min_samples=20, top=5)
    tops = [t["setup"] for t in sc["top_setups_by_expectancy"]]
    assert tops[0] == "momentum"                                 # highest expectancy
    assert "fvg_retest" in sc["weak_or_avoid_setups"]


# ── modifiers preview (NOT live) ──────────────────────────────────────────────────
def test_modifiers_preview_is_preview_only(tmp_path):
    assert LEARNING_MODIFIERS_LIVE is False
    rows, _f, _w = load_replay_rows(_make_replay(tmp_path, _dataset()))
    sc = build_scorecard(rows, horizon=15, min_samples=20)
    preview = build_setup_modifiers_preview(sc)
    assert "_note" in preview and "not read by live" in preview["_note"].lower()
    assert preview["momentum"]["confidence_modifier"] == 5
    assert preview["fvg_retest"]["confidence_modifier"] == -8


def test_learning_not_imported_by_decision_engine():
    # The live decision engine must not depend on the learning layer.
    import services.gold_bot_decision_engine as eng
    src = open(eng.__file__, encoding="utf-8").read()
    assert "gold_bot_learning_journal" not in src


# ── output ─────────────────────────────────────────────────────────────────────────
def test_write_scorecard_creates_files(tmp_path):
    rows, _f, _w = load_replay_rows(_make_replay(tmp_path, _dataset()))
    sc = build_scorecard(rows, horizon=15, min_samples=20)
    out = tmp_path / "learning"
    paths = write_scorecard(out, sc, symbol="XAUUSD", timeframe="M1", risk_mode="balanced")
    assert paths["named"].exists() and paths["latest"].exists()
    assert paths["preview"].exists() and paths["events"].exists()
    latest = json.loads(paths["latest"].read_text(encoding="utf-8"))
    assert latest["horizon"] == 15
    assert "MetaTrader5" not in sys.modules


def test_dry_run_writes_nothing(tmp_path):
    import scripts.run_gold_bot_learning_scorecard as L
    d = _make_replay(tmp_path, _dataset())
    out = tmp_path / "learning"
    rc = L.main(["--replay-dir", str(d), "--out-dir", str(out),
                 "--horizon", "15", "--min-samples", "20", "--dry-run"])
    assert rc == 0
    assert not out.exists() or not any(out.iterdir())


def test_cli_no_replay_files_errors(tmp_path):
    import scripts.run_gold_bot_learning_scorecard as L
    rc = L.main(["--replay-dir", str(tmp_path / "empty"), "--out-dir", str(tmp_path / "out")])
    assert rc == 1


# ── LM89B: real demo-trade blending into the scorecard ──────────────────────────────
def test_build_scorecard_blends_real_stats(tmp_path):
    from services.gold_bot_learning_journal import build_real_trade_stats
    rows = [_row("momentum", "LONG", 75, 200.0, "win") for _ in range(25)]   # replay promising
    real_outcomes = [{"setup": "momentum", "outcome": "loss", "pnl": -30.0, "pnl_points": -30.0,
                      "risk_mode": "scalp", "side": "LONG", "confidence": 75, "_tkey": ""}
                     for _ in range(10)]
    real = build_real_trade_stats(real_outcomes, min_real_trades=5)
    sc = build_scorecard(rows, horizon=15, min_samples=10, real_stats=real, real_trade_weight=2.0)
    v = sc["by_setup"]["momentum"]
    assert sc["include_real_trades"] is True and sc["real_trade_weight"] == 2.0
    assert v["replay_trade_count"] == 25 and v["real_trade_count"] == 10
    assert v["combined_expectancy"] < v["expectancy_points"]   # demo losses pull it down
    assert "recommended_status_combined" in v
    preview = build_setup_modifiers_preview(sc, source_scorecard="x.json")
    assert "combined replay+demo" in preview["momentum"]["reason"]
