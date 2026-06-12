"""
tests/test_gold_bot_historical_market_data.py
-----------------------------------------------
LM84A — Pure tests for the historical market data layer. No MT5: backfill uses
an injected fetch_fn, everything else uses fake bars + temp dirs.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from services.gold_bot_historical_market_data import (
    HistoricalBar,
    MT5HistoricalXauusdProvider,
    build_metadata,
    csv_path,
    history_status,
    meta_path,
    quality_summary,
    read_bars_csv,
    read_metadata,
    write_bars_csv,
    write_metadata,
)

NOW = datetime(2026, 6, 12, 13, 0, 0, tzinfo=timezone.utc)


def _bar(minute, o=2300.0, h=2301.0, l=2299.0, c=2300.5, spread=12):
    return HistoricalBar(
        symbol="XAUUSD", timeframe="M1", time=NOW + timedelta(minutes=minute),
        open=o, high=h, low=l, close=c, tick_volume=100, spread=spread, real_volume=0,
        source="mt5_demo", loaded_at=NOW,
    )


def _series(n=10):
    return [_bar(i, c=2300.0 + i) for i in range(n)]


def _raw_series(n=5):
    return [{
        "time": (NOW + timedelta(minutes=i)).isoformat(),
        "open": 2300.0 + i, "high": 2301.0 + i, "low": 2299.0 + i, "close": 2300.5 + i,
        "tick_volume": 50 + i, "spread": 10 + i, "real_volume": 0,
    } for i in range(n)]


# ── CSV write/read round-trip ────────────────────────────────────────────────────
def test_csv_write_read_roundtrip(tmp_path):
    p = tmp_path / "XAUUSD_M1.csv"
    write_bars_csv(p, _series(6))
    back = read_bars_csv(p, symbol="XAUUSD", timeframe="M1")
    assert len(back) == 6
    assert back[0].time == NOW
    assert back[-1].close == 2305.0
    assert back[0].spread == 12


def test_read_missing_csv_is_empty(tmp_path):
    assert read_bars_csv(tmp_path / "nope.csv", symbol="XAUUSD", timeframe="M1") == []


# ── metadata ──────────────────────────────────────────────────────────────────────
def test_metadata_build_and_roundtrip(tmp_path):
    bars = _series(4)
    meta = build_metadata(symbol="XAUUSD", timeframe="M1", requested_from=NOW - timedelta(days=1),
                          requested_to=NOW, bars=bars, source="mt5_demo", warnings=["w"])
    assert meta["rows_written"] == 4
    assert meta["first_bar_time"] == bars[0].time.isoformat()
    assert meta["last_bar_time"] == bars[-1].time.isoformat()
    mp = tmp_path / "XAUUSD_M1.meta.json"
    write_metadata(mp, meta)
    assert read_metadata(mp)["rows_written"] == 4


# ── quality summary ──────────────────────────────────────────────────────────────
def test_quality_clean_series():
    q = quality_summary(_series(10), timeframe="M1")
    assert q["duplicate_timestamps"] == 0
    assert q["missing_or_zero_ohlc"] == 0
    assert q["high_lt_low"] == 0
    assert q["non_monotonic_time"] == 0
    assert q["warnings"] == []
    assert q["spread_avg"] == 12


def test_quality_detects_duplicates_and_bad_ohlc():
    bars = _series(5)
    bars.append(_bar(4))                       # duplicate timestamp (minute 4)
    bars.append(_bar(5, o=0.0))                # zero open
    bars.append(_bar(6, h=2290.0, l=2305.0))   # high < low
    q = quality_summary(bars, timeframe="M1")
    assert q["duplicate_timestamps"] == 1
    assert q["missing_or_zero_ohlc"] >= 1
    assert q["high_lt_low"] == 1
    assert q["warnings"]


def test_quality_detects_gaps():
    bars = [_bar(0), _bar(1), _bar(60)]        # 59-min jump → gap
    q = quality_summary(bars, timeframe="M1")
    assert q["time_gaps"] == 1


# ── backfill via injected fetch_fn (no MT5) ──────────────────────────────────────
def _provider(tmp_path, **kw):
    return MT5HistoricalXauusdProvider(
        history_dir=tmp_path, symbol="XAUUSD",
        fetch_fn=lambda sym, tf, dfrom, dto: _raw_series(5), **kw)


def test_backfill_writes_csv_and_meta(tmp_path):
    res = _provider(tmp_path).backfill(
        timeframes=["M1", "M5"], date_from=NOW - timedelta(days=1), date_to=NOW,
        printer=lambda *_: None)
    assert all(r["status"] == "written" for r in res)
    assert csv_path(tmp_path, "XAUUSD", "M1").exists()
    assert meta_path(tmp_path, "XAUUSD", "M1").exists()
    assert read_metadata(meta_path(tmp_path, "XAUUSD", "M1"))["rows_written"] == 5


def test_dry_run_writes_nothing(tmp_path):
    res = _provider(tmp_path).backfill(
        timeframes=["M1"], date_from=NOW - timedelta(days=1), date_to=NOW,
        dry_run=True, printer=lambda *_: None)
    assert res[0]["status"] == "planned"
    assert not csv_path(tmp_path, "XAUUSD", "M1").exists()


def test_no_overwrite_skips_existing(tmp_path):
    prov = _provider(tmp_path)
    prov.backfill(timeframes=["M1"], date_from=NOW - timedelta(days=1), date_to=NOW,
                  printer=lambda *_: None)
    res = prov.backfill(timeframes=["M1"], date_from=NOW - timedelta(days=1), date_to=NOW,
                        overwrite=False, printer=lambda *_: None)
    assert res[0]["status"] == "skipped_exists"
    res2 = prov.backfill(timeframes=["M1"], date_from=NOW - timedelta(days=1), date_to=NOW,
                         overwrite=True, printer=lambda *_: None)
    assert res2[0]["status"] == "written"


def test_backfill_empty_range_warns_no_crash(tmp_path):
    prov = MT5HistoricalXauusdProvider(
        history_dir=tmp_path, symbol="XAUUSD", fetch_fn=lambda *a: [])
    res = prov.backfill(timeframes=["M1"], date_from=NOW - timedelta(days=1), date_to=NOW,
                        printer=lambda *_: None)
    assert res[0]["status"] == "written" and res[0]["rows"] == 0
    assert any("no bars" in w.lower() for w in res[0]["warnings"])


def test_unsupported_timeframe_skipped(tmp_path):
    res = _provider(tmp_path).backfill(
        timeframes=["M3"], date_from=NOW - timedelta(days=1), date_to=NOW,
        printer=lambda *_: None)
    assert res[0]["status"] == "skipped_unsupported"


# ── provider status from files ────────────────────────────────────────────────────
def test_status_missing_when_empty(tmp_path):
    st = history_status(tmp_path, "XAUUSD", now=NOW)
    assert st.status == "missing" and st.freshness == "none"


def test_status_active_after_backfill(tmp_path):
    # backfill bars are at NOW.. so last_bar_time is fresh relative to NOW.
    _provider(tmp_path).backfill(timeframes=["M1"], date_from=NOW - timedelta(days=1),
                                 date_to=NOW, printer=lambda *_: None)
    st = history_status(tmp_path, "XAUUSD", now=NOW + timedelta(minutes=10))
    assert st.status == "active"
    assert st.freshness == "fresh"
    assert "M1" in st.message


def test_status_stale_when_old(tmp_path):
    _provider(tmp_path).backfill(timeframes=["M1"], date_from=NOW - timedelta(days=1),
                                 date_to=NOW, printer=lambda *_: None)
    st = history_status(tmp_path, "XAUUSD", now=NOW + timedelta(days=10))
    assert st.status == "active" and st.freshness == "stale"
