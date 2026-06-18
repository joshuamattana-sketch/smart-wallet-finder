"""
services/gold_bot_historical_market_data.py
---------------------------------------------
LM84A — First REAL historical market data provider: MT5 XAUUSD backfill.

Gives the Gold Bot a local XAUUSD memory base (CSV + metadata) for later
replay / learning / scoring. Read-only: it copies historical bars from a running
MT5 demo terminal via the existing connector and writes them under
``data/gold_bot/history/``. NEVER sends orders, never touches live trading.

Split so unit tests need no MT5:
  * pure helpers (bar model, CSV read/write, metadata, quality summary,
    history-dir status) operate on plain data + temp dirs;
  * ``MT5HistoricalXauusdProvider`` wires the connector for the real fetch and
    accepts an injected ``fetch_fn`` so the backfill flow is testable offline.

Generated CSV/meta files are gitignored (see .gitignore data/gold_bot/history/*).
"""

from __future__ import annotations

import csv
import io
import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from services.gold_bot_data_sources import ProviderStatus

_REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_HISTORY_DIR = _REPO_ROOT / "data" / "gold_bot" / "history"
DEFAULT_SYMBOL = "XAUUSD"
SOURCE = "mt5_demo"

SUPPORTED_TIMEFRAMES = ("M1", "M5", "M15", "H1")
_TF_MINUTES = {"M1": 1, "M5": 5, "M15": 15, "H1": 60}

CSV_COLUMNS = ["time", "open", "high", "low", "close", "tick_volume", "spread", "real_volume"]

# Latest bar within this many hours → "fresh"; older → "stale".
FRESH_WITHIN_HOURS = 48.0


@dataclass
class HistoricalBar:
    symbol: str
    timeframe: str
    time: datetime            # tz-aware UTC
    open: float
    high: float
    low: float
    close: float
    tick_volume: float | None = None
    spread: float | None = None
    real_volume: float | None = None
    source: str = SOURCE
    loaded_at: datetime | None = None

    def csv_row(self) -> dict[str, Any]:
        return {
            "time": self.time.isoformat(),
            "open": self.open, "high": self.high, "low": self.low, "close": self.close,
            "tick_volume": _num(self.tick_volume), "spread": _num(self.spread),
            "real_volume": _num(self.real_volume),
        }


def _num(v: Any) -> Any:
    return "" if v is None else v


def _parse_dt(raw: Any) -> datetime | None:
    if raw is None or raw == "":
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _to_float(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def bar_from_raw(raw: dict, *, symbol: str, timeframe: str,
                 source: str = SOURCE, loaded_at: datetime | None = None) -> HistoricalBar | None:
    """Normalize one connector candle dict into a HistoricalBar (or None if no time)."""
    t = _parse_dt(raw.get("time"))
    if t is None:
        return None
    return HistoricalBar(
        symbol=symbol, timeframe=timeframe.upper(), time=t,
        open=_to_float(raw.get("open")) or 0.0, high=_to_float(raw.get("high")) or 0.0,
        low=_to_float(raw.get("low")) or 0.0, close=_to_float(raw.get("close")) or 0.0,
        tick_volume=_to_float(raw.get("tick_volume")), spread=_to_float(raw.get("spread")),
        real_volume=_to_float(raw.get("real_volume")), source=source,
        loaded_at=loaded_at or datetime.now(timezone.utc),
    )


# ── file paths ──────────────────────────────────────────────────────────────────
def csv_path(history_dir: str | Path, symbol: str, timeframe: str) -> Path:
    return Path(history_dir) / f"{symbol}_{timeframe.upper()}.csv"


def meta_path(history_dir: str | Path, symbol: str, timeframe: str) -> Path:
    return Path(history_dir) / f"{symbol}_{timeframe.upper()}.meta.json"


# ── CSV / metadata IO ─────────────────────────────────────────────────────────────
def write_bars_csv(path: str | Path, bars: list[HistoricalBar]) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for b in bars:
            writer.writerow(b.csv_row())
    return p


def read_bars_csv(path: str | Path, *, symbol: str, timeframe: str,
                  source: str = "csv_cache") -> list[HistoricalBar]:
    p = Path(path)
    if not p.exists():
        return []
    out: list[HistoricalBar] = []
    try:
        # Read fully so a bad encoding raises HERE (decoding a streamed file object
        # only fails mid-iteration, which a bare open() guard would miss).
        raw = p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        # Corrupt/locked history file: log and return empty rather than crashing
        # with a raw traceback. The replay layer turns an empty list into a clear
        # "history file has no rows" error.
        logging.getLogger(__name__).warning("unreadable history CSV %s: %s", p, exc)
        return []
    for row in csv.DictReader(io.StringIO(raw)):
        t = _parse_dt(row.get("time"))
        if t is None:
            continue
        out.append(HistoricalBar(
            symbol=symbol, timeframe=timeframe.upper(), time=t,
            open=_to_float(row.get("open")) or 0.0, high=_to_float(row.get("high")) or 0.0,
            low=_to_float(row.get("low")) or 0.0, close=_to_float(row.get("close")) or 0.0,
            tick_volume=_to_float(row.get("tick_volume")), spread=_to_float(row.get("spread")),
            real_volume=_to_float(row.get("real_volume")), source=source,
        ))
    return out


def build_metadata(*, symbol: str, timeframe: str, requested_from: datetime,
                   requested_to: datetime, bars: list[HistoricalBar], source: str,
                   warnings: list[str] | None = None) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "timeframe": timeframe.upper(),
        "requested_from": requested_from.isoformat(),
        "requested_to": requested_to.isoformat(),
        "rows_written": len(bars),
        "first_bar_time": bars[0].time.isoformat() if bars else None,
        "last_bar_time": bars[-1].time.isoformat() if bars else None,
        "source": source,
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


# ── data quality ──────────────────────────────────────────────────────────────────
def quality_summary(bars: list[HistoricalBar], *, timeframe: str | None = None) -> dict[str, Any]:
    """Cheap integrity scan over a bar series. Pure."""
    rows = len(bars)
    seen: set[str] = set()
    duplicates = 0
    missing_or_zero = 0
    high_lt_low = 0
    non_monotonic = 0
    gaps = 0
    spreads: list[float] = []

    tf = (timeframe or (bars[0].timeframe if bars else "M1")).upper()
    step = _TF_MINUTES.get(tf, 1) * 60.0
    prev: HistoricalBar | None = None
    for b in bars:
        key = b.time.isoformat()
        if key in seen:
            duplicates += 1
        seen.add(key)
        if any(v is None or v <= 0 for v in (b.open, b.high, b.low, b.close)):
            missing_or_zero += 1
        if b.high < b.low:
            high_lt_low += 1
        if b.spread is not None:
            spreads.append(b.spread)
        if prev is not None:
            delta = (b.time - prev.time).total_seconds()
            if delta <= 0:
                non_monotonic += 1
            elif delta > step * 1.5:
                gaps += 1
        prev = b

    summary: dict[str, Any] = {
        "rows": rows,
        "duplicate_timestamps": duplicates,
        "missing_or_zero_ohlc": missing_or_zero,
        "high_lt_low": high_lt_low,
        "non_monotonic_time": non_monotonic,
        "time_gaps": gaps,
    }
    if spreads:
        summary["spread_min"] = min(spreads)
        summary["spread_max"] = max(spreads)
        summary["spread_avg"] = round(sum(spreads) / len(spreads), 2)
    summary["warnings"] = _quality_warnings(summary)
    return summary


def _quality_warnings(s: dict[str, Any]) -> list[str]:
    w = []
    if s["rows"] == 0:
        w.append("no rows.")
    if s["duplicate_timestamps"]:
        w.append(f"{s['duplicate_timestamps']} duplicate timestamp(s).")
    if s["missing_or_zero_ohlc"]:
        w.append(f"{s['missing_or_zero_ohlc']} bar(s) with missing/zero OHLC.")
    if s["high_lt_low"]:
        w.append(f"{s['high_lt_low']} bar(s) with high < low (corrupt).")
    if s["non_monotonic_time"]:
        w.append(f"{s['non_monotonic_time']} non-monotonic timestamp(s).")
    return w


def _expected_bars(timeframe: str, date_from: datetime, date_to: datetime) -> int:
    minutes = max(0.0, (date_to - date_from).total_seconds() / 60.0)
    tf_min = _TF_MINUTES.get(timeframe.upper(), 1)
    return int(minutes / tf_min)


# ── history-dir scan + provider status (pure; safe for the data-sources probe) ──
def list_history(history_dir: str | Path = DEFAULT_HISTORY_DIR,
                 symbol: str = DEFAULT_SYMBOL) -> list[dict[str, Any]]:
    """Return one entry per timeframe that has a CSV on disk (with meta if present)."""
    out: list[dict[str, Any]] = []
    for tf in SUPPORTED_TIMEFRAMES:
        cp = csv_path(history_dir, symbol, tf)
        if not cp.exists():
            continue
        meta = read_metadata(meta_path(history_dir, symbol, tf))
        out.append({"timeframe": tf, "csv": cp, "meta": meta})
    return out


def history_status(history_dir: str | Path = DEFAULT_HISTORY_DIR,
                   symbol: str = DEFAULT_SYMBOL, *, now: datetime | None = None) -> ProviderStatus:
    now = now or datetime.now(timezone.utc)
    entries = list_history(history_dir, symbol)
    if not entries:
        return ProviderStatus(
            "mt5_xauusd_history", "historical_market", "missing", freshness="none",
            message="no local history files yet; run scripts/run_gold_bot_history_backfill.py")

    last_times: list[datetime] = []
    for e in entries:
        meta = e["meta"] or {}
        lt = _parse_dt(meta.get("last_bar_time"))
        if lt is not None:
            last_times.append(lt)
    latest = max(last_times) if last_times else None
    if latest is not None:
        fresh = "fresh" if (now - latest) <= timedelta(hours=FRESH_WITHIN_HOURS) else "stale"
        latest_tf = next((e["timeframe"] for e in entries
                          if (e["meta"] or {}).get("last_bar_time") == latest.isoformat()), "?")
        msg = f"{len(entries)} file(s); latest {latest_tf} bar {latest.isoformat()}"
    else:
        fresh = "unknown"
        msg = f"{len(entries)} file(s); metadata missing last_bar_time"
    return ProviderStatus(
        "mt5_xauusd_history", "historical_market", "active", freshness=fresh,
        last_updated=latest.isoformat() if latest else None, message=msg)


# ── real provider ──────────────────────────────────────────────────────────────────
class MT5HistoricalXauusdProvider:
    """
    REAL provider: backfill XAUUSD history from a running MT5 demo terminal.
    Inject ``fetch_fn(symbol, timeframe, date_from, date_to) -> list[dict]`` to
    test the backfill flow without MT5. When ``fetch_fn`` is None the real path
    uses the MT5 demo connector's read-only ``copy_rates_range``.
    """

    name = "mt5_xauusd_history"
    category = "historical_market"

    def __init__(self, *, history_dir: str | Path = DEFAULT_HISTORY_DIR,
                 symbol: str = DEFAULT_SYMBOL, connector: Any | None = None,
                 fetch_fn: Callable[[str, str, datetime, datetime], list[dict]] | None = None):
        self.history_dir = Path(history_dir)
        self.symbol = symbol
        self._connector = connector
        self._fetch_fn = fetch_fn

    def status(self, now: datetime | None = None) -> ProviderStatus:
        return history_status(self.history_dir, self.symbol, now=now)

    def backfill(self, *, timeframes: list[str], date_from: datetime, date_to: datetime,
                 overwrite: bool = False, dry_run: bool = False,
                 printer: Callable[[str], None] = print) -> list[dict]:
        """
        Fetch + write each timeframe. dry_run never writes or connects. Existing
        files are skipped unless overwrite. Returns a result row per timeframe.
        """
        results: list[dict] = []
        use_real = self._fetch_fn is None and not dry_run
        conn = None
        symbol = self.symbol
        try:
            if use_real:
                conn, symbol = self._connect_and_resolve(printer)
            fetch = self._fetch_fn or (conn.copy_rates_range if conn is not None else None)

            for raw_tf in timeframes:
                tf = raw_tf.upper()
                cp = csv_path(self.history_dir, symbol, tf)
                mp = meta_path(self.history_dir, symbol, tf)
                if tf not in SUPPORTED_TIMEFRAMES:
                    results.append({"timeframe": tf, "status": "skipped_unsupported",
                                    "warnings": [f"unsupported timeframe {tf}"]})
                    continue
                if dry_run:
                    results.append({"timeframe": tf, "status": "planned", "csv": str(cp),
                                    "meta": str(mp), "from": date_from.isoformat(),
                                    "to": date_to.isoformat()})
                    continue
                if cp.exists() and not overwrite:
                    results.append({"timeframe": tf, "status": "skipped_exists", "csv": str(cp),
                                    "warnings": [f"{cp.name} exists; use --overwrite to replace"]})
                    continue

                raw = fetch(symbol, tf, date_from, date_to)
                loaded_at = datetime.now(timezone.utc)
                bars = [b for b in (bar_from_raw(r, symbol=symbol, timeframe=tf, loaded_at=loaded_at)
                                    for r in (raw or [])) if b is not None]
                warnings = self._range_warnings(tf, date_from, date_to, bars)
                write_bars_csv(cp, bars)
                meta = build_metadata(symbol=symbol, timeframe=tf, requested_from=date_from,
                                      requested_to=date_to, bars=bars, source=SOURCE,
                                      warnings=warnings)
                write_metadata(mp, meta)
                results.append({"timeframe": tf, "status": "written", "rows": len(bars),
                                "csv": str(cp), "meta": str(mp), "warnings": warnings})
        finally:
            if conn is not None:
                try:
                    conn.shutdown()
                except Exception:  # noqa: BLE001 - shutdown must not mask results
                    pass
        return results

    # ── real MT5 wiring (only reached when fetch_fn is None and not dry_run) ───
    def _connect_and_resolve(self, printer):
        from services.connectors.mt5_demo_connector import (
            Mt5ConnectorError, Mt5DemoConnector, ProbeResult,
        )
        conn = self._connector or Mt5DemoConnector()
        conn.connect()
        probe = ProbeResult()
        conn.read_account(probe)
        if not conn.demo_verified:
            raise Mt5ConnectorError(
                f"account trade_mode={getattr(probe, 'trade_mode_label', '?')} is not a "
                "verified DEMO account (fail closed)."
            )
        symbol = conn.discover_gold_symbol(probe, preferred=self.symbol)
        printer(f" connected: {probe.account_login}@{probe.account_server} symbol {symbol}")
        return conn, symbol

    @staticmethod
    def _range_warnings(tf, date_from, date_to, bars) -> list[str]:
        warnings: list[str] = []
        if not bars:
            warnings.append("no bars returned for range - terminal may not hold this history.")
            return warnings
        expected = _expected_bars(tf, date_from, date_to)
        if expected and len(bars) < 0.5 * expected:
            warnings.append(
                f"MT5 returned {len(bars)} bars (~{expected} naive expected) - terminal history "
                "may be limited or markets were closed (weekends/holidays).")
        q = quality_summary(bars, timeframe=tf)
        warnings.extend(q["warnings"])
        return warnings
