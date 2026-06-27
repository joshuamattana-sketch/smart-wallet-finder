"""
tests/test_gold_bot_signal_logger.py
------------------------------------
LM87A — Forward signal logger tests. No MT5, no internet. Fake CSVs + temp dirs.
Proves: preset RR scaling, no-lookahead scoring (only bars AFTER the signal),
deterministic win/loss/partial outcomes, idempotent logging, NO_TRADE handling,
and the offline/no-MT5 contract.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from services.gold_bot_historical_market_data import (
    HistoricalBar,
    csv_path,
    write_bars_csv,
)
from services.gold_bot_signal_logger import (
    build_track_record,
    log_new_signals,
    read_signals,
    run_signal_logger,
    score_open_signals,
    signals_path,
    summary_path,
)
from services.gold_bot_signal_presets import (
    PRESETS,
    get_preset,
    resolve_preset_points,
)

T0 = datetime(2026, 6, 1, 0, 0, 0, tzinfo=timezone.utc)
POINT = 0.01


def _bar(minute, *, high, low, close=None, open_=None, tf="M15"):
    c = close if close is not None else (high + low) / 2
    return HistoricalBar(
        symbol="XAUUSD", timeframe=tf, time=T0 + timedelta(minutes=minute),
        open=open_ if open_ is not None else c, high=high, low=low, close=c,
        tick_volume=100, spread=12, real_volume=0)


def _ramp_bars(n, *, start=2300.0, step=1.0, tf="M15"):
    """Monotonic up-ramp — enough bars to clear warmup; mostly NO_TRADE."""
    out = []
    for i in range(n):
        c = start + i * step
        out.append(HistoricalBar(symbol="XAUUSD", timeframe=tf,
                                 time=T0 + timedelta(minutes=i),
                                 open=c - 0.5, high=c + 0.5, low=c - 1.0, close=c,
                                 tick_volume=100, spread=12, real_volume=0))
    return out


def _write_signal(spath, rec):
    spath.parent.mkdir(parents=True, exist_ok=True)
    with spath.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, default=str) + "\n")


def _open_long(bar_minute=0, *, entry=2300.0, sl_points=300):
    return {
        "signal_id": f"XAUUSD_M15_{bar_minute}", "logged_at": T0.isoformat(),
        "bar_time": (T0 + timedelta(minutes=bar_minute)).isoformat(),
        "symbol": "XAUUSD", "timeframe": "M15", "risk_mode": "balanced",
        "decision": "LONG", "strategy": "momentum", "confidence": 70,
        "entry_reference_price": entry, "sl_points": sl_points, "tp_points": 600,
        "session": "London", "regime": "trend", "reasons": [], "blockers": [],
        "warnings": [], "macro": {}, "status": "open", "scored_at": None,
        "bars_forward": 0, "outcomes": {}, "no_lookahead": True, "calls_mt5": False,
    }


# ── presets ──────────────────────────────────────────────────────────────────────
def test_preset_rr_scaling_balanced_sl():
    # SL 300 (=1R). conservative tp1=1R=300, tp2=2R=600. balanced 2R=600. runner 3R=900.
    assert resolve_preset_points(get_preset("conservative"), 300) == (300, 600)
    assert resolve_preset_points(get_preset("balanced"), 300) == (None, 600)
    assert resolve_preset_points(get_preset("runner"), 300) == (None, 900)


def test_preset_rr_scaling_scalp_sl():
    # SL 120 -> same R multiples auto-scale: conservative (120, 240), runner 360.
    assert resolve_preset_points(get_preset("conservative"), 120) == (120, 240)
    assert resolve_preset_points(get_preset("runner"), 120) == (None, 360)


def test_unknown_preset_raises():
    try:
        get_preset("yolo")
    except KeyError as e:
        assert "yolo" in str(e)
    else:
        raise AssertionError("expected KeyError for unknown preset")


# ── scoring: deterministic outcomes ───────────────────────────────────────────────
def test_winning_long_all_presets_win(tmp_path):
    # Monotonic rise past runner's 3R (2309) -> every preset takes its target.
    bars = [_bar(0, high=2300.5, low=2299.5, close=2300.0)]  # the entry bar itself
    for i, hi in enumerate([2304, 2307, 2310], start=1):
        bars.append(_bar(i, high=hi, low=hi - 1.0, close=hi - 0.5))
    write_bars_csv(csv_path(tmp_path, "XAUUSD", "M15"), bars)
    spath = signals_path(tmp_path, "XAUUSD", "M15")
    _write_signal(spath, _open_long(0, entry=2300.0, sl_points=300))

    # 3 forward bars only: force resolution at end of available data.
    closed, _ = score_open_signals(symbol="XAUUSD", timeframe="M15",
                                   history_dir=tmp_path, signals_dir=tmp_path,
                                   max_forward_bars=3)
    assert closed == 1
    rec = read_signals(spath)[0]
    assert rec["status"] == "closed"
    o = rec["outcomes"]
    assert o["balanced"]["outcome"] == "win" and o["balanced"]["realized_points"] == 600.0
    assert o["runner"]["outcome"] == "win" and o["runner"]["realized_points"] == 900.0
    # conservative: 50% at 1R + 50% at 2R = 450
    assert o["conservative"]["outcome"] == "win" and o["conservative"]["realized_points"] == 450.0


def test_losing_long_all_presets_loss(tmp_path):
    # Drops straight through SL (2297) before any TP -> all presets -SL.
    bars = [_bar(0, high=2300.5, low=2299.5, close=2300.0)]
    for i, lo in enumerate([2298, 2296, 2294], start=1):
        bars.append(_bar(i, high=lo + 1.0, low=lo, close=lo + 0.5))
    write_bars_csv(csv_path(tmp_path, "XAUUSD", "M15"), bars)
    spath = signals_path(tmp_path, "XAUUSD", "M15")
    _write_signal(spath, _open_long(0, entry=2300.0, sl_points=300))

    score_open_signals(symbol="XAUUSD", timeframe="M15",
                       history_dir=tmp_path, signals_dir=tmp_path, max_forward_bars=3)
    o = read_signals(spath)[0]["outcomes"]
    # bracket presets all stop out; swing has no SL so it is scored separately below
    for name in ("conservative", "balanced", "runner"):
        assert o[name]["outcome"] == "loss"
        assert o[name]["realized_points"] == -300.0


def test_partial_preset_tp1_then_sl_diverges(tmp_path):
    # Hits 1R (2303) on bar 1, then SL (2297) on bar 2; never reaches 2R/3R.
    bars = [
        _bar(0, high=2300.5, low=2299.5, close=2300.0),
        _bar(1, high=2304.0, low=2301.0, close=2302.0),   # tp1 (2303) hit, no SL
        _bar(2, high=2298.0, low=2296.0, close=2297.0),   # SL (2297) hit
    ]
    write_bars_csv(csv_path(tmp_path, "XAUUSD", "M15"), bars)
    spath = signals_path(tmp_path, "XAUUSD", "M15")
    _write_signal(spath, _open_long(0, entry=2300.0, sl_points=300))

    score_open_signals(symbol="XAUUSD", timeframe="M15",
                       history_dir=tmp_path, signals_dir=tmp_path, max_forward_bars=2)
    o = read_signals(spath)[0]["outcomes"]
    # conservative banked 1R on half, lost 1R on half -> net 0 (neutral)
    assert o["conservative"]["exit_reason"] == "tp1_then_sl"
    assert o["conservative"]["realized_points"] == 0.0
    # single-target presets just lose
    assert o["balanced"]["outcome"] == "loss"
    assert o["runner"]["outcome"] == "loss"


def test_swing_time_exit_holds_through_stop_and_diverges(tmp_path):
    # Price dips below the 1R stop on bar 1, then rises for the rest of the hold.
    # Bracket presets stop out at -1R; the swing preset has NO stop, holds 30 bars,
    # and exits at market in profit. This is the validated-edge divergence.
    bars = [_bar(0, high=2300.5, low=2299.5, close=2300.0),
            _bar(1, high=2300.2, low=2296.0, close=2299.0)]   # dips through SL (2297)
    for i in range(2, 33):
        c = 2300.0 + (i - 1) * 1.0
        bars.append(_bar(i, high=c + 0.5, low=c - 0.5, close=c))
    write_bars_csv(csv_path(tmp_path, "XAUUSD", "M15"), bars)
    spath = signals_path(tmp_path, "XAUUSD", "M15")
    _write_signal(spath, _open_long(0, entry=2300.0, sl_points=300))

    closed, _ = score_open_signals(symbol="XAUUSD", timeframe="M15",
                                   history_dir=tmp_path, signals_dir=tmp_path)
    assert closed == 1
    o = read_signals(spath)[0]["outcomes"]
    assert o["balanced"]["outcome"] == "loss"          # stopped out at -1R
    assert o["swing"]["exit_reason"] == "hold"          # held to time, no stop
    assert o["swing"]["sl_points"] is None
    assert o["swing"]["outcome"] == "win"               # exited in profit
    assert o["swing"]["hold_bars"] == 30


def test_cost_points_netted_from_realized(tmp_path):
    # Winning long: balanced grosses +600 (2R); a 50-point round-trip cost nets +550.
    bars = [_bar(0, high=2300.5, low=2299.5, close=2300.0)]
    for i, hi in enumerate([2304, 2307, 2310], start=1):
        bars.append(_bar(i, high=hi, low=hi - 1.0, close=hi - 0.5))
    write_bars_csv(csv_path(tmp_path, "XAUUSD", "M15"), bars)
    spath = signals_path(tmp_path, "XAUUSD", "M15")
    _write_signal(spath, _open_long(0, entry=2300.0, sl_points=300))

    score_open_signals(symbol="XAUUSD", timeframe="M15", history_dir=tmp_path,
                       signals_dir=tmp_path, max_forward_bars=3, cost_points=50.0)
    o = read_signals(spath)[0]["outcomes"]
    assert o["balanced"]["realized_points"] == 550.0
    assert o["balanced"]["cost_points"] == 50.0
    assert o["balanced"]["outcome"] == "win"


def test_guarded_swing_stops_where_pure_swing_holds(tmp_path):
    # Dips below the guarded swing's 3R stop (2291) on bar 1, then recovers.
    # Pure swing (no stop) holds to profit; guarded swing takes the -3R stop.
    bars = [_bar(0, high=2300.5, low=2299.5, close=2300.0),
            _bar(1, high=2300.0, low=2290.0, close=2299.0)]   # low 2290 < 3R stop 2291
    for i in range(2, 33):
        c = 2300.0 + (i - 1) * 1.0
        bars.append(_bar(i, high=c + 0.5, low=c - 0.5, close=c))
    write_bars_csv(csv_path(tmp_path, "XAUUSD", "M15"), bars)
    spath = signals_path(tmp_path, "XAUUSD", "M15")
    _write_signal(spath, _open_long(0, entry=2300.0, sl_points=300))

    score_open_signals(symbol="XAUUSD", timeframe="M15",
                       history_dir=tmp_path, signals_dir=tmp_path)
    o = read_signals(spath)[0]["outcomes"]
    assert o["swing"]["outcome"] == "win" and o["swing"]["exit_reason"] == "hold"
    assert o["swing_guarded"]["exit_reason"] == "sl"
    assert o["swing_guarded"]["realized_points"] == -900.0
    assert o["swing_guarded"]["sl_points"] == 900  # 3R on a 300-point base


def test_no_lookahead_ignores_bars_before_entry(tmp_path):
    # A huge spike BEFORE the entry bar must not score the signal. After the entry
    # bar there is only flat price -> not resolved -> stays open.
    bars = [
        _bar(0, high=2400.0, low=2399.0, close=2399.5),   # pre-entry spike (way past TP)
        _bar(1, high=2300.5, low=2299.5, close=2300.0),   # the entry bar
        _bar(2, high=2300.4, low=2299.6, close=2300.0),   # after: flat, no TP/SL
    ]
    write_bars_csv(csv_path(tmp_path, "XAUUSD", "M15"), bars)
    spath = signals_path(tmp_path, "XAUUSD", "M15")
    _write_signal(spath, _open_long(1, entry=2300.0, sl_points=300))  # entry at minute 1

    closed, _ = score_open_signals(symbol="XAUUSD", timeframe="M15",
                                   history_dir=tmp_path, signals_dir=tmp_path,
                                   max_forward_bars=192)
    assert closed == 0  # the pre-entry spike was correctly ignored
    assert read_signals(spath)[0]["status"] == "open"


def test_expiry_exit_marks_closed(tmp_path):
    # Flat price after entry, but max_forward_bars=1 -> forced expiry exit.
    bars = [
        _bar(0, high=2300.5, low=2299.5, close=2300.0),
        _bar(1, high=2300.6, low=2299.4, close=2300.3),   # tiny up move, no TP/SL
    ]
    write_bars_csv(csv_path(tmp_path, "XAUUSD", "M15"), bars)
    spath = signals_path(tmp_path, "XAUUSD", "M15")
    _write_signal(spath, _open_long(0, entry=2300.0, sl_points=300))

    closed, _ = score_open_signals(symbol="XAUUSD", timeframe="M15",
                                   history_dir=tmp_path, signals_dir=tmp_path,
                                   max_forward_bars=1)
    assert closed == 1
    o = read_signals(spath)[0]["outcomes"]
    assert o["balanced"]["exit_reason"] == "expired"
    # +30 points mark-to-market (2300.3 - 2300.0 = 0.30 = 30 pts)
    assert o["balanced"]["realized_points"] == 30.0


def test_void_signal_when_entry_missing(tmp_path):
    bars = [_bar(0, high=2300.5, low=2299.5, close=2300.0),
            _bar(1, high=2305.0, low=2304.0, close=2304.5)]
    write_bars_csv(csv_path(tmp_path, "XAUUSD", "M15"), bars)
    spath = signals_path(tmp_path, "XAUUSD", "M15")
    bad = _open_long(0)
    bad["entry_reference_price"] = None
    _write_signal(spath, bad)
    score_open_signals(symbol="XAUUSD", timeframe="M15",
                       history_dir=tmp_path, signals_dir=tmp_path)
    assert read_signals(spath)[0]["status"] == "void"


# ── logging: idempotency + structure ──────────────────────────────────────────────
def test_log_new_signals_idempotent_and_skips_forming_bar(tmp_path):
    bars = _ramp_bars(160)
    write_bars_csv(csv_path(tmp_path, "XAUUSD", "M15"), bars)
    new1, _ = log_new_signals(symbol="XAUUSD", timeframe="M15", history_dir=tmp_path,
                              macro_history_dir=tmp_path / "nomacro", signals_dir=tmp_path,
                              warmup_bars=120, now=T0)
    assert len(new1) > 0
    # the newest (forming) bar must not be logged
    last_time = bars[-1].time.isoformat()
    assert all(r["bar_time"] != last_time for r in new1)
    # re-run -> nothing new (idempotent)
    new2, _ = log_new_signals(symbol="XAUUSD", timeframe="M15", history_dir=tmp_path,
                              macro_history_dir=tmp_path / "nomacro", signals_dir=tmp_path,
                              warmup_bars=120, now=T0)
    assert new2 == []
    # every record carries the no-lookahead / no-MT5 markers
    for r in read_signals(signals_path(tmp_path, "XAUUSD", "M15")):
        assert r["no_lookahead"] is True and r["calls_mt5"] is False
        assert r["status"] in ("open", "no_trade")


def test_no_trade_signals_not_scored(tmp_path):
    spath = signals_path(tmp_path, "XAUUSD", "M15")
    nt = _open_long(0)
    nt["decision"] = "NO_TRADE"
    nt["status"] = "no_trade"
    nt["entry_reference_price"] = None
    nt["sl_points"] = None
    _write_signal(spath, nt)
    bars = [_bar(0, high=2300.5, low=2299.5), _bar(1, high=2310.0, low=2309.0)]
    write_bars_csv(csv_path(tmp_path, "XAUUSD", "M15"), bars)
    closed, _ = score_open_signals(symbol="XAUUSD", timeframe="M15",
                                   history_dir=tmp_path, signals_dir=tmp_path)
    assert closed == 0
    assert read_signals(spath)[0]["status"] == "no_trade"


# ── track record + orchestrator ───────────────────────────────────────────────────
def test_build_track_record_aggregates():
    signals = [
        {"status": "closed", "outcomes": {
            "balanced": {"outcome": "win", "realized_points": 600.0}}},
        {"status": "closed", "outcomes": {
            "balanced": {"outcome": "loss", "realized_points": -300.0}}},
        {"status": "no_trade", "outcomes": {}},
        {"status": "open", "outcomes": {}},
    ]
    tr = build_track_record(signals)
    b = tr["per_preset"]["balanced"]
    assert b["trades"] == 2 and b["wins"] == 1 and b["losses"] == 1
    assert b["win_rate_pct"] == 50.0
    assert b["total_realized_points"] == 300.0
    assert b["expectancy_points"] == 150.0
    assert tr["by_status"]["no_trade"] == 1 and tr["by_status"]["open"] == 1


def test_run_signal_logger_writes_files(tmp_path):
    bars = _ramp_bars(160)
    write_bars_csv(csv_path(tmp_path, "XAUUSD", "M15"), bars)
    res = run_signal_logger(symbol="XAUUSD", timeframe="M15", history_dir=tmp_path,
                            macro_history_dir=tmp_path / "nomacro", signals_dir=tmp_path,
                            warmup_bars=120, now=T0)
    assert res.signals_path.exists()
    assert res.summary_path.exists()
    s = json.loads(res.summary_path.read_text(encoding="utf-8"))
    assert s["no_lookahead"] is True and s["calls_mt5"] is False
    assert "per_preset" in s and set(s["per_preset"]) == set(PRESETS)
