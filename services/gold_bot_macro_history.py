"""
services/gold_bot_macro_history.py
-----------------------------------
LM84B — Macro historical data import layer (offline CSV bootstrap).

Lets DXY / US10Y / US02Y / VIX be stored locally from FREE manually-downloaded
CSVs, normalized into one ``MacroBar`` shape under data/gold_bot/macro_history/.
This is the FIRST no-API bootstrap: NO HTTP, NO yfinance/FRED, NO scraping, NO
secrets. Later patches (LM84C/LM84D) can add automatic fetchers behind the same
normalized CSV + ``ProviderStatus`` contract.

Accepts two common input shapes:
  * Format A (OHLC):  time,open,high,low,close
  * Format B (value): time,value
Both normalize into rows with ``close`` always set (close = value when only a
value column is present); OHLC stays None for value-only series.

Pure + deterministic: unit tests need no internet and no MT5. Generated
CSV/meta files are gitignored; only README + samples/*.sample.csv are tracked.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from services.gold_bot_data_sources import ProviderStatus

_REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MACRO_HISTORY_DIR = _REPO_ROOT / "data" / "gold_bot" / "macro_history"
DEFAULT_SOURCE = "manual_csv"

MACRO_INSTRUMENTS = ("DXY", "US10Y", "US02Y", "VIX")
SUPPORTED_TIMEFRAMES = ("D1", "H1")
CSV_COLUMNS = ["time", "open", "high", "low", "close", "value"]

# Instrument grouping for the three data-source statuses.
YIELD_SYMBOLS = ("US10Y", "US02Y")

# Latest bar within this many days → "fresh" (daily macro data).
FRESH_WITHIN_DAYS = 14.0


@dataclass
class MacroBar:
    symbol: str
    timeframe: str
    time: datetime                 # tz-aware UTC
    close: float
    open: float | None = None
    high: float | None = None
    low: float | None = None
    value: float | None = None
    source: str = DEFAULT_SOURCE
    loaded_at: datetime | None = None

    def csv_row(self) -> dict[str, Any]:
        return {
            "time": self.time.isoformat(),
            "open": _num(self.open), "high": _num(self.high), "low": _num(self.low),
            "close": self.close, "value": _num(self.value),
        }


def _num(v: Any) -> Any:
    return "" if v is None else v


def _to_float(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _parse_dt(raw: Any) -> datetime | None:
    """Accept 'YYYY-MM-DD' or full ISO. Date-only → UTC midnight."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


# ── paths ──────────────────────────────────────────────────────────────────────
def macro_csv_path(history_dir: str | Path, symbol: str, timeframe: str) -> Path:
    return Path(history_dir) / f"{symbol.upper()}_{timeframe.upper()}.csv"


def macro_meta_path(history_dir: str | Path, symbol: str, timeframe: str) -> Path:
    return Path(history_dir) / f"{symbol.upper()}_{timeframe.upper()}.meta.json"


# ── parse / normalize ──────────────────────────────────────────────────────────
def load_macro_csv(path: str | Path, *, symbol: str, timeframe: str,
                   source: str = DEFAULT_SOURCE,
                   loaded_at: datetime | None = None) -> tuple[list[MacroBar], list[str]]:
    """
    Parse an OHLC or value-only CSV into normalized MacroBars. Malformed rows are
    skipped with warnings; rows are returned in file order. Never raises on bad
    rows (only on an unreadable file).
    """
    p = Path(path)
    loaded_at = loaded_at or datetime.now(timezone.utc)
    bars: list[MacroBar] = []
    warnings: list[str] = []
    with p.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        cols = {(c or "").strip().lower(): c for c in (reader.fieldnames or [])}
        time_key = cols.get("time") or cols.get("date")
        if time_key is None:
            return [], ["CSV has no 'time'/'date' column."]
        has_close = "close" in cols
        has_value = "value" in cols
        if not (has_close or has_value):
            return [], ["CSV has neither 'close' nor 'value' column."]
        for i, row in enumerate(reader, start=2):
            t = _parse_dt(row.get(time_key))
            if t is None:
                warnings.append(f"row {i}: unparseable time {row.get(time_key)!r} — skipped.")
                continue
            value = _to_float(row.get(cols["value"])) if has_value else None
            close = _to_float(row.get(cols["close"])) if has_close else value
            if close is None:
                close = value
            if close is None:
                warnings.append(f"row {i}: missing close/value — skipped.")
                continue
            bars.append(MacroBar(
                symbol=symbol.upper(), timeframe=timeframe.upper(), time=t, close=close,
                open=_to_float(row.get(cols["open"])) if "open" in cols else None,
                high=_to_float(row.get(cols["high"])) if "high" in cols else None,
                low=_to_float(row.get(cols["low"])) if "low" in cols else None,
                value=value if has_value else None, source=source, loaded_at=loaded_at,
            ))
    return bars, warnings


def write_macro_csv(path: str | Path, bars: list[MacroBar]) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        w.writeheader()
        for b in bars:
            w.writerow(b.csv_row())
    return p


def read_macro_csv(path: str | Path, *, symbol: str, timeframe: str,
                   source: str = "csv_cache") -> list[MacroBar]:
    p = Path(path)
    if not p.exists():
        return []
    bars, _ = load_macro_csv(p, symbol=symbol, timeframe=timeframe, source=source)
    return bars


# ── metadata ────────────────────────────────────────────────────────────────────
def build_macro_metadata(*, symbol: str, timeframe: str, source: str, input_file: str,
                         bars: list[MacroBar], warnings: list[str] | None = None) -> dict[str, Any]:
    return {
        "symbol": symbol.upper(),
        "timeframe": timeframe.upper(),
        "source": source,
        "input_file": input_file,
        "rows_written": len(bars),
        "first_time": bars[0].time.isoformat() if bars else None,
        "last_time": bars[-1].time.isoformat() if bars else None,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "warnings": list(warnings or []),
    }


def write_metadata(path: str | Path, meta: dict) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")
    return p


def read_metadata(path: str | Path) -> dict | None:
    p = Path(path)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


# ── quality ───────────────────────────────────────────────────────────────────────
def quality_summary(bars: list[MacroBar]) -> dict[str, Any]:
    rows = len(bars)
    seen: set[str] = set()
    duplicates = missing_close = high_lt_low = non_monotonic = gaps = 0
    prev: MacroBar | None = None
    deltas: list[float] = []
    for b in bars:
        key = b.time.isoformat()
        if key in seen:
            duplicates += 1
        seen.add(key)
        if b.close is None:
            missing_close += 1
        if b.high is not None and b.low is not None and b.high < b.low:
            high_lt_low += 1
        if prev is not None:
            d = (b.time - prev.time).total_seconds()
            if d <= 0:
                non_monotonic += 1
            else:
                deltas.append(d)
        prev = b
    if deltas:
        median = sorted(deltas)[len(deltas) // 2]
        gaps = sum(1 for d in deltas if d > median * 1.5)
    summary = {
        "rows": rows, "duplicate_timestamps": duplicates, "missing_close": missing_close,
        "high_lt_low": high_lt_low, "non_monotonic_time": non_monotonic, "time_gaps": gaps,
    }
    summary["warnings"] = _quality_warnings(summary)
    return summary


def _quality_warnings(s: dict[str, Any]) -> list[str]:
    w = []
    if s["rows"] == 0:
        w.append("no rows.")
    if s["duplicate_timestamps"]:
        w.append(f"{s['duplicate_timestamps']} duplicate timestamp(s).")
    if s["missing_close"]:
        w.append(f"{s['missing_close']} row(s) missing close/value.")
    if s["high_lt_low"]:
        w.append(f"{s['high_lt_low']} OHLC row(s) with high < low.")
    if s["non_monotonic_time"]:
        w.append(f"{s['non_monotonic_time']} non-monotonic timestamp(s).")
    return w


# ── import ──────────────────────────────────────────────────────────────────────
def import_csv(*, input_file: str | Path, symbol: str, timeframe: str,
               out_dir: str | Path = DEFAULT_MACRO_HISTORY_DIR, source: str = DEFAULT_SOURCE,
               overwrite: bool = False, dry_run: bool = False,
               now: datetime | None = None) -> dict[str, Any]:
    """Validate + normalize one macro CSV → CSV/meta under out_dir. dry_run writes nothing."""
    now = now or datetime.now(timezone.utc)
    cp = macro_csv_path(out_dir, symbol, timeframe)
    mp = macro_meta_path(out_dir, symbol, timeframe)
    inp = Path(input_file)
    if not inp.exists():
        return {"status": "input_missing", "csv": str(cp),
                "warnings": [f"input file not found: {input_file}"]}

    bars, warnings = load_macro_csv(inp, symbol=symbol, timeframe=timeframe,
                                    source=source, loaded_at=now)
    warnings = warnings + quality_summary(bars)["warnings"]

    if dry_run:
        return {"status": "planned", "rows": len(bars), "csv": str(cp), "meta": str(mp),
                "warnings": warnings}
    if not bars:
        return {"status": "invalid", "rows": 0, "csv": str(cp),
                "warnings": warnings or ["no valid rows parsed."]}
    if cp.exists() and not overwrite:
        return {"status": "skipped_exists", "csv": str(cp),
                "warnings": [f"{cp.name} exists; use --overwrite to replace."]}

    write_macro_csv(cp, bars)
    meta = build_macro_metadata(symbol=symbol, timeframe=timeframe, source=source,
                                input_file=str(inp), bars=bars, warnings=warnings)
    write_metadata(mp, meta)
    return {"status": "written", "rows": len(bars), "csv": str(cp), "meta": str(mp),
            "warnings": warnings}


# ── history-dir scan + per-instrument provider status (pure) ──────────────────────
def list_macro_history(history_dir: str | Path = DEFAULT_MACRO_HISTORY_DIR,
                       timeframe: str = "D1") -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for sym in MACRO_INSTRUMENTS:
        cp = macro_csv_path(history_dir, sym, timeframe)
        if not cp.exists():
            continue
        out.append({"symbol": sym, "timeframe": timeframe.upper(), "csv": cp,
                    "meta": read_metadata(macro_meta_path(history_dir, sym, timeframe))})
    return out


def _status_for(name: str, symbols: tuple[str, ...], history_dir: str | Path,
                now: datetime, missing_msg: str, timeframe: str = "D1") -> ProviderStatus:
    present: list[tuple[str, datetime | None, int | None]] = []
    for sym in symbols:
        cp = macro_csv_path(history_dir, sym, timeframe)
        if not cp.exists():
            continue
        meta = read_metadata(macro_meta_path(history_dir, sym, timeframe)) or {}
        present.append((sym, _parse_dt(meta.get("last_time")), meta.get("rows_written")))
    if not present:
        return ProviderStatus(name, "macro_market", "missing", freshness="none", message=missing_msg)

    last_times = [lt for _s, lt, _r in present if lt is not None]
    latest = max(last_times) if last_times else None
    if latest is not None:
        fresh = "fresh" if (now - latest) <= timedelta(days=FRESH_WITHIN_DAYS) else "stale"
    else:
        fresh = "unknown"
    detail = ", ".join(f"{s}_{timeframe}{(' rows=' + str(r)) if r is not None else ''}"
                       for s, _lt, r in present)
    msg = f"{detail}" + (f"; latest {latest.isoformat()}" if latest else "")
    return ProviderStatus(name, "macro_market", "active", freshness=fresh,
                          last_updated=latest.isoformat() if latest else None, message=msg)


def macro_market_statuses(history_dir: str | Path = DEFAULT_MACRO_HISTORY_DIR,
                          *, now: datetime | None = None) -> list[ProviderStatus]:
    now = now or datetime.now(timezone.utc)
    return [
        _status_for("dxy_history", ("DXY",), history_dir, now,
                    "no DXY local macro history yet; import with run_gold_bot_macro_history_import.py"),
        _status_for("us_yields_history", YIELD_SYMBOLS, history_dir, now,
                    "no US10Y/US02Y local macro history yet; import with run_gold_bot_macro_history_import.py"),
        _status_for("vix_history", ("VIX",), history_dir, now,
                    "no VIX local macro history yet; import with run_gold_bot_macro_history_import.py"),
    ]
