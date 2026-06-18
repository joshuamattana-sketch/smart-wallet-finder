"""
tests/test_gold_bot_macro_history.py
--------------------------------------
LM84B — Pure tests for the macro history import layer. No internet, no MT5.
Uses temp CSVs + temp dirs.
"""

from __future__ import annotations

from datetime import datetime, timezone

from services.gold_bot_macro_history import (
    build_macro_metadata,
    import_csv,
    load_macro_csv,
    macro_csv_path,
    macro_market_statuses,
    macro_meta_path,
    quality_summary,
    read_metadata,
)

NOW = datetime(2026, 6, 12, 13, 0, 0, tzinfo=timezone.utc)

_OHLC = """time,open,high,low,close
2026-06-01,98.10,98.62,97.95,98.41
2026-06-02,98.41,98.70,98.20,98.55
2026-06-03,98.55,98.58,97.80,97.92
"""

_VALUE = """time,value
2026-06-01,4.21
2026-06-02,4.23
2026-06-03,4.18
"""


def test_load_macro_csv_unreadable_file_degrades_to_warning(tmp_path):
    # A corrupt (bad-encoding) macro CSV must degrade to ([], [warning]) rather than
    # crash the data-source probe with a raw UnicodeDecodeError.
    bad = tmp_path / "DXY_D1.csv"
    bad.write_bytes(b"\xff\xfe time,close \x80\x81 not utf-8")
    bars, warnings = load_macro_csv(bad, symbol="DXY", timeframe="D1")
    assert bars == []
    assert any("unreadable" in w for w in warnings)


def _write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


# ── parsing / normalization ───────────────────────────────────────────────────────
def test_parse_ohlc_csv(tmp_path):
    bars, warns = load_macro_csv(_write(tmp_path, "dxy.csv", _OHLC),
                                 symbol="DXY", timeframe="D1")
    assert warns == []
    assert len(bars) == 3
    assert bars[0].time == datetime(2026, 6, 1, tzinfo=timezone.utc)
    assert bars[0].open == 98.10 and bars[0].close == 98.41
    assert bars[0].value is None


def test_parse_value_only_csv(tmp_path):
    bars, warns = load_macro_csv(_write(tmp_path, "us10y.csv", _VALUE),
                                 symbol="US10Y", timeframe="D1")
    assert len(bars) == 3
    b = bars[0]
    assert b.value == 4.21
    assert b.close == 4.21          # close = value when only value present
    assert b.open is None and b.high is None and b.low is None


def test_malformed_rows_skipped(tmp_path):
    text = "time,value\n2026-06-01,4.21\nbadtime,4.3\n2026-06-02,\n2026-06-03,4.25\n"
    bars, warns = load_macro_csv(_write(tmp_path, "x.csv", text), symbol="US10Y", timeframe="D1")
    assert len(bars) == 2          # bad time + missing value skipped
    assert len(warns) == 2


def test_no_close_or_value_column(tmp_path):
    bars, warns = load_macro_csv(_write(tmp_path, "x.csv", "time,foo\n2026-06-01,1\n"),
                                 symbol="DXY", timeframe="D1")
    assert bars == [] and warns


# ── metadata ────────────────────────────────────────────────────────────────────────
def test_metadata_fields(tmp_path):
    bars, _ = load_macro_csv(_write(tmp_path, "dxy.csv", _OHLC), symbol="DXY", timeframe="D1")
    meta = build_macro_metadata(symbol="DXY", timeframe="D1", source="manual_csv",
                                input_file="dxy.csv", bars=bars, warnings=[])
    assert meta["rows_written"] == 3
    assert meta["first_time"] == bars[0].time.isoformat()
    assert meta["last_time"] == bars[-1].time.isoformat()
    assert meta["symbol"] == "DXY" and meta["source"] == "manual_csv"


# ── quality ───────────────────────────────────────────────────────────────────────
def test_quality_clean(tmp_path):
    bars, _ = load_macro_csv(_write(tmp_path, "dxy.csv", _OHLC), symbol="DXY", timeframe="D1")
    q = quality_summary(bars)
    assert q["duplicate_timestamps"] == 0 and q["missing_close"] == 0
    assert q["high_lt_low"] == 0 and q["non_monotonic_time"] == 0
    assert q["warnings"] == []


def test_quality_detects_problems(tmp_path):
    # dup 06-02, high<low on 06-03, non-monotonic (06-01 after 06-02)
    text = ("time,open,high,low,close\n"
            "2026-06-02,1,2,0.5,1.5\n"
            "2026-06-02,1,2,0.5,1.5\n"          # duplicate
            "2026-06-03,1,0.5,2.0,1.5\n"        # high < low
            "2026-06-01,1,2,0.5,1.5\n")         # goes backwards
    bars, _ = load_macro_csv(_write(tmp_path, "x.csv", text), symbol="DXY", timeframe="D1")
    q = quality_summary(bars)
    assert q["duplicate_timestamps"] == 1
    assert q["high_lt_low"] == 1
    assert q["non_monotonic_time"] == 2   # the duplicate (delta 0) + the backwards row
    assert q["warnings"]


# ── import flow ─────────────────────────────────────────────────────────────────────
def test_dry_run_writes_nothing(tmp_path):
    inp = _write(tmp_path, "dxy.csv", _OHLC)
    out = tmp_path / "out"
    res = import_csv(input_file=inp, symbol="DXY", timeframe="D1", out_dir=out, dry_run=True)
    assert res["status"] == "planned" and res["rows"] == 3
    assert not macro_csv_path(out, "DXY", "D1").exists()


def test_import_writes_csv_and_meta(tmp_path):
    inp = _write(tmp_path, "dxy.csv", _OHLC)
    out = tmp_path / "out"
    res = import_csv(input_file=inp, symbol="DXY", timeframe="D1", out_dir=out)
    assert res["status"] == "written" and res["rows"] == 3
    assert macro_csv_path(out, "DXY", "D1").exists()
    assert read_metadata(macro_meta_path(out, "DXY", "D1"))["rows_written"] == 3


def test_no_overwrite_protection(tmp_path):
    inp = _write(tmp_path, "dxy.csv", _OHLC)
    out = tmp_path / "out"
    import_csv(input_file=inp, symbol="DXY", timeframe="D1", out_dir=out)
    again = import_csv(input_file=inp, symbol="DXY", timeframe="D1", out_dir=out)
    assert again["status"] == "skipped_exists"
    forced = import_csv(input_file=inp, symbol="DXY", timeframe="D1", out_dir=out, overwrite=True)
    assert forced["status"] == "written"


def test_missing_input(tmp_path):
    res = import_csv(input_file=tmp_path / "nope.csv", symbol="DXY", timeframe="D1",
                     out_dir=tmp_path / "out")
    assert res["status"] == "input_missing"


# ── data-source statuses ─────────────────────────────────────────────────────────────
def test_statuses_all_missing_when_empty(tmp_path):
    sts = {s.name: s for s in macro_market_statuses(tmp_path, now=NOW)}
    assert sts["dxy_history"].status == "missing"
    assert sts["us_yields_history"].status == "missing"
    assert sts["vix_history"].status == "missing"
    assert all(s.category == "macro_market" for s in sts.values())


def test_dxy_active_after_import(tmp_path):
    inp = _write(tmp_path, "dxy.csv", _OHLC)
    out = tmp_path / "macro"
    import_csv(input_file=inp, symbol="DXY", timeframe="D1", out_dir=out)
    # last sample bar 2026-06-03; treat 'now' close to it so it's fresh
    sts = {s.name: s for s in macro_market_statuses(out, now=datetime(2026, 6, 5, tzinfo=timezone.utc))}
    assert sts["dxy_history"].status == "active"
    assert sts["dxy_history"].freshness == "fresh"
    assert sts["us_yields_history"].status == "missing"
    assert sts["vix_history"].status == "missing"


def test_yields_active_with_either_tenor(tmp_path):
    inp = _write(tmp_path, "us10y.csv", _VALUE)
    out = tmp_path / "macro"
    import_csv(input_file=inp, symbol="US10Y", timeframe="D1", out_dir=out)
    sts = {s.name: s for s in macro_market_statuses(out, now=datetime(2026, 6, 5, tzinfo=timezone.utc))}
    assert sts["us_yields_history"].status == "active"
    assert "US10Y" in sts["us_yields_history"].message
