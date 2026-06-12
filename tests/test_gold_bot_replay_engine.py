"""
tests/test_gold_bot_replay_engine.py
--------------------------------------
LM85A — Replay engine tests. No MT5, no internet. Fake CSVs + temp dirs.
Proves the no-lookahead contract and forward scoring.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from services.gold_bot_historical_market_data import HistoricalBar, write_bars_csv, csv_path
from services.gold_bot_macro_history import import_csv as macro_import
from services.gold_bot_replay_engine import (
    MacroSeries,
    ReplayClock,
    ReplayError,
    run_replay,
    score_horizon,
)

T0 = datetime(2026, 6, 1, 0, 0, 0, tzinfo=timezone.utc)


def _bars(n, *, start=2300.0, step=1.0, tf="M1"):
    out = []
    for i in range(n):
        c = start + i * step
        out.append(HistoricalBar(symbol="XAUUSD", timeframe=tf, time=T0 + timedelta(minutes=i),
                                 open=c - 0.5, high=c + 0.5, low=c - 1.0, close=c,
                                 tick_volume=100, spread=12, real_volume=0))
    return out


def _write_history(tmp_path, bars, tf="M1"):
    write_bars_csv(csv_path(tmp_path, "XAUUSD", tf), bars)
    return tmp_path


# ── ReplayClock ────────────────────────────────────────────────────────────────
def test_clock_iterates_chronologically():
    clock = ReplayClock(_bars(30), warmup_bars=10, max_bars=None)
    steps = list(clock)
    times = [s.time for s in steps]
    assert times == sorted(times)
    assert steps[0].index == 10                 # first scored after warmup
    assert steps[-1].index == 29


def test_visible_bars_never_include_future():
    clock = ReplayClock(_bars(40), warmup_bars=5)
    for step in clock:
        assert all(b.time <= step.time for b in step.visible_bars)
        assert step.visible_bars[-1].time == step.time
        # nothing strictly after the current time leaked in
        assert max(b.time for b in step.visible_bars) == step.current_bar.time


def test_warmup_and_max_bars():
    steps = list(ReplayClock(_bars(50), warmup_bars=20, max_bars=5))
    assert len(steps) == 5
    assert steps[0].index == 20


def test_from_to_filtering():
    bars = _bars(60)
    frm = T0 + timedelta(minutes=30)
    to = T0 + timedelta(minutes=40)
    steps = list(ReplayClock(bars, warmup_bars=5, from_time=frm, to_time=to))
    assert steps[0].time >= frm
    assert steps[-1].time <= to
    assert all(frm <= s.time <= to for s in steps)


# ── Macro as-of (causal) ────────────────────────────────────────────────────────
def _macro(tmp_path):
    # DXY rising daily series across the replay window.
    rows = "time,close\n" + "".join(
        f"{(datetime(2026,6,1)+timedelta(days=i)).date()},{98.0 + i*0.2}\n" for i in range(5))
    inp = tmp_path / "dxy.csv"
    inp.write_text(rows, encoding="utf-8")
    out = tmp_path / "macro"
    macro_import(input_file=inp, symbol="DXY", timeframe="D1", out_dir=out)
    return out


def test_macro_as_of_never_uses_future_row(tmp_path):
    macro = MacroSeries.load(_macro(tmp_path))
    s = macro.series["DXY"]
    # as-of a time between day 2 and day 3 → must return day 2's value, not day 3.
    t = datetime(2026, 6, 3, 5, 0, tzinfo=timezone.utc)
    i = s.as_of_index(t)
    assert s.times[i] <= t
    assert all(tm <= t for tm in s.times[: i + 1])
    assert s.times[i + 1] > t                    # the next row is in the future, excluded


def test_macro_snapshot_close_is_as_of(tmp_path):
    macro = MacroSeries.load(_macro(tmp_path))
    snap = macro.snapshot(datetime(2026, 6, 3, 12, 0, tzinfo=timezone.utc))
    assert snap["dxy_close"] == 98.0 + 2 * 0.2   # day index 2 (06-03)
    assert snap["dxy_bias"] in ("rising", "falling", "flat", "unknown")


def test_missing_macro_is_unknown_no_crash(tmp_path):
    macro = MacroSeries.load(tmp_path / "empty_macro")  # nonexistent dir
    snap = macro.snapshot(T0)
    assert snap["dxy_close"] is None
    assert snap["dxy_bias"] == "unknown"
    assert macro.warnings


# ── forward scoring ──────────────────────────────────────────────────────────────
def test_long_scoring_positive_when_price_rises():
    bars = _bars(20)                              # strictly rising 1pt/bar → +100 points/bar
    sc = score_horizon(bars, 5, decision="LONG", horizon=5, sl_points=300, tp_points=600)
    assert sc["dir_return_points"] > 0
    assert sc["mfe_points"] >= sc["dir_return_points"]
    assert sc["outcome"] in ("win", "neutral")    # rising helps a LONG


def test_short_scoring_loses_when_price_rises():
    bars = _bars(20)
    sc = score_horizon(bars, 5, decision="SHORT", horizon=5, sl_points=300, tp_points=600)
    assert sc["dir_return_points"] < 0            # rising price hurts a SHORT


def test_no_trade_not_counted_as_win_loss():
    bars = _bars(20)
    sc = score_horizon(bars, 5, decision="NO_TRADE", horizon=5, sl_points=None, tp_points=None)
    assert sc["outcome"] == "no_trade"
    assert "tp_hit" not in sc


def test_no_data_when_no_future_bars():
    bars = _bars(10)
    sc = score_horizon(bars, 9, decision="LONG", horizon=5, sl_points=300, tp_points=600)
    assert sc["outcome"] == "no_data"
    assert sc["bars_available"] == 0


def test_tp_hit_is_win():
    # craft a bar whose future high reaches TP quickly
    bars = _bars(10)
    bars[6].high = bars[5].close + 600 * 0.01 + 1   # > entry + tp
    sc = score_horizon(bars, 5, decision="LONG", horizon=5, sl_points=300, tp_points=600)
    assert sc["tp_hit"] is True and sc["outcome"] == "win"


# ── full replay run ──────────────────────────────────────────────────────────────
def test_dry_run_writes_no_files(tmp_path):
    _write_history(tmp_path, _bars(200))
    out = tmp_path / "replay"
    res = run_replay(history_dir=tmp_path, macro_history_dir=tmp_path / "nomacro",
                     out_dir=out, warmup_bars=30, max_bars=50, dry_run=True)
    assert res.summary["mode"] == "dry_run"
    assert res.jsonl_path is None
    assert not out.exists() or not any(out.iterdir())


def test_run_writes_jsonl_and_summary(tmp_path):
    _write_history(tmp_path, _bars(200))
    out = tmp_path / "replay"
    res = run_replay(history_dir=tmp_path, macro_history_dir=_macro(tmp_path),
                     out_dir=out, warmup_bars=30, max_bars=40, horizons=(5, 15))
    assert res.jsonl_path.exists() and res.summary_path.exists()
    lines = res.jsonl_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 40
    first = json.loads(lines[0])
    assert first["forward_scoring_uses_future_after_decision"] is True
    assert first["no_lookahead_visible_bars_count"] >= 1
    assert "5" in first["score"] and "15" in first["score"]
    s = res.summary
    assert s["bars_processed"] == 40
    total = s["decisions"]["long"] + s["decisions"]["short"] + s["decisions"]["no_trade"]
    assert total == 40
    assert s["calls_mt5"] is False and s["no_lookahead"] is True


def test_missing_history_raises_with_hint(tmp_path):
    try:
        run_replay(history_dir=tmp_path / "empty", out_dir=tmp_path / "r")
        assert False, "expected ReplayError"
    except ReplayError as exc:
        assert "backfill" in str(exc).lower()


def test_replay_does_not_import_mt5(tmp_path):
    # The MT5 package must never be imported by a replay run.
    import sys
    _write_history(tmp_path, _bars(160))
    sys.modules.pop("MetaTrader5", None)
    run_replay(history_dir=tmp_path, macro_history_dir=tmp_path / "nomacro",
               out_dir=tmp_path / "replay", warmup_bars=30, max_bars=20)
    assert "MetaTrader5" not in sys.modules
