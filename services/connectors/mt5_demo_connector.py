"""
services/connectors/mt5_demo_connector.py
------------------------------------------
LM75A — Read-only MetaTrader 5 demo connector probe for the private Gold Bot.

PURPOSE
    Verify that Python can connect to a *running, logged-in* MT5 terminal and
    read demo account + XAUUSD data. Nothing more.

SAFETY — this module treats MT5 as dangerous even in demo mode:
    * READ ONLY. There is no order_send / order_check / trade call anywhere in
      this file. Grep it: the strings "order_send" and "order_check" appear
      only in this banner.
    * Fails CLOSED. If account info cannot be read, or the account is not
      provably a demo account, the probe raises Mt5ConnectorError and reads
      nothing further.
    * Safety flags default to the safe position and are asserted, never used to
      enable trading (there is no trading path to enable):
          MT5_DEMO_ONLY        = True
          LIVE_TRADING_ENABLED = False
          ALLOW_REAL_ORDERS    = False

DESIGN
    The MetaTrader5 package is Windows-only and need not be installed for this
    module to import (so it stays test-friendly and CI-safe). The real package
    is lazy-imported at connect() time, OR an mt5-like module can be injected
    for tests. No automated test requires a real terminal.

    Run via scripts/run_mt5_demo_connector_probe.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from typing import Any

# ── Safety posture (defaults are the safe position; never flipped here) ───────
MT5_DEMO_ONLY = True
LIVE_TRADING_ENABLED = False
ALLOW_REAL_ORDERS = False

# Gold symbol candidates, tried in order before a broad XAU/GOLD scan.
GOLD_SYMBOL_CANDIDATES = (
    "XAUUSD",
    "GOLD",
    "XAUUSDm",
    "XAUUSD.a",
    "XAUUSD.",
    "XAUUSD.pro",
)
GOLD_SCAN_SUBSTRINGS = ("XAU", "GOLD")

# Default timeframe name → resolved against the live module's constants.
_TIMEFRAME_ATTR = {
    "M1": "TIMEFRAME_M1",
    "M5": "TIMEFRAME_M5",
    "M15": "TIMEFRAME_M15",
    "M30": "TIMEFRAME_M30",
    "H1": "TIMEFRAME_H1",
    "H4": "TIMEFRAME_H4",
    "D1": "TIMEFRAME_D1",
}

# account_info().trade_mode integer → label. MT5 convention:
#   0 = demo, 1 = contest, 2 = real.
_TRADE_MODE_LABEL = {0: "demo", 1: "contest", 2: "real"}
# Modes we consider safe to read from. Contest accounts are still non-real
# practice accounts, so reading is allowed; only "real" fails closed.
_SAFE_TRADE_MODES = {0, 1}


class Mt5ConnectorError(Exception):
    """Raised on any fail-closed condition (init, account, demo proof, symbol, candles)."""


@dataclass
class ProbeResult:
    """Everything the read-only probe could collect. Optional parts may be None."""

    read_only: bool = True
    orders_sent: int = 0  # always 0 — there is no order path
    connected: bool = False

    # account
    account_login: int | None = None
    account_server: str | None = None
    account_name: str | None = None
    account_currency: str | None = None
    trade_mode_raw: int | None = None
    trade_mode_label: str | None = None
    is_demo: bool | None = None
    balance: float | None = None
    equity: float | None = None
    margin: float | None = None
    margin_free: float | None = None

    # symbol
    selected_symbol: str | None = None
    symbol_discovery: str | None = None  # "candidate" | "scan"

    # tick / spread
    tick_bid: float | None = None
    tick_ask: float | None = None
    tick_spread: float | None = None
    tick_time: str | None = None

    # candles
    timeframe: str | None = None
    bars_requested: int | None = None
    bars_returned: int | None = None
    last_candle: dict[str, Any] | None = None

    # positions / history (optional)
    open_positions: int | None = None
    history_deals: int | None = None
    history_days: int | None = None

    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class Mt5DemoConnector:
    """
    Read-only wrapper around a MetaTrader5-like module.

    Pass `mt5_module` to inject a fake for tests; leave it None to lazy-import
    the real `MetaTrader5` package at connect() time.
    """

    def __init__(self, mt5_module: Any | None = None) -> None:
        self._mt5 = mt5_module
        self._injected = mt5_module is not None
        self._connected = False

    # ── lifecycle ────────────────────────────────────────────────────────────
    def _ensure_module(self) -> Any:
        if self._mt5 is not None:
            return self._mt5
        try:
            import MetaTrader5 as mt5  # type: ignore  # lazy, Windows-only
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise Mt5ConnectorError(
                "MetaTrader5 package not installed. Run:  pip install MetaTrader5  "
                "(Windows only; requires a running, logged-in MT5 terminal)."
            ) from exc
        self._mt5 = mt5
        return mt5

    def connect(self) -> None:
        """Initialize the terminal connection. Fails closed."""
        mt5 = self._ensure_module()
        ok = mt5.initialize()
        if not ok:
            err = self._last_error()
            raise Mt5ConnectorError(f"MT5 initialize() failed: {err}")
        self._connected = True

    def shutdown(self) -> None:
        """Close the connection cleanly. Safe to call even if never connected."""
        if self._mt5 is not None and self._connected:
            try:
                self._mt5.shutdown()
            finally:
                self._connected = False

    def _last_error(self) -> Any:
        mt5 = self._mt5
        getter = getattr(mt5, "last_error", None)
        if callable(getter):
            try:
                return getter()
            except Exception:  # pragma: no cover - defensive
                return "unknown"
        return "unknown"

    # ── account (fail closed) ────────────────────────────────────────────────
    def read_account(self, result: ProbeResult) -> None:
        """
        Read account info and PROVE the account is non-real. Raises if the info
        is missing or the account is a real/live account (fail closed).
        """
        mt5 = self._mt5
        info = mt5.account_info()
        if info is None:
            raise Mt5ConnectorError(
                f"account_info() returned None — cannot read account ({self._last_error()}). "
                "Refusing to continue (fail closed)."
            )

        trade_mode = _safe_int(getattr(info, "trade_mode", None))
        label = _TRADE_MODE_LABEL.get(trade_mode, "unknown") if trade_mode is not None else "unknown"

        result.account_login = _safe_int(getattr(info, "login", None))
        result.account_server = _opt_str(getattr(info, "server", None))
        result.account_name = _opt_str(getattr(info, "name", None))
        result.account_currency = _opt_str(getattr(info, "currency", None))
        result.trade_mode_raw = trade_mode
        result.trade_mode_label = label
        result.balance = _safe_float(getattr(info, "balance", None))
        result.equity = _safe_float(getattr(info, "equity", None))
        result.margin = _safe_float(getattr(info, "margin", None))
        result.margin_free = _safe_float(getattr(info, "margin_free", None))

        # Fail closed on real or unprovable account type.
        if trade_mode is None:
            result.is_demo = None
            raise Mt5ConnectorError(
                "Account trade_mode could not be read — cannot prove this is a demo "
                "account. Refusing to continue (fail closed)."
            )
        if trade_mode not in _SAFE_TRADE_MODES:
            result.is_demo = False
            raise Mt5ConnectorError(
                f"Account trade_mode={trade_mode} ({label}) is NOT a demo/contest account. "
                "MT5_DEMO_ONLY is enforced — refusing to read from a live account (fail closed)."
            )
        result.is_demo = trade_mode == 0
        if trade_mode == 1:
            result.warnings.append("Account is a CONTEST account (non-real); reading allowed.")

    # ── symbol discovery ─────────────────────────────────────────────────────
    def discover_gold_symbol(self, result: ProbeResult, preferred: str | None = None) -> str:
        """
        Select a tradable gold symbol. Tries `preferred`, then known candidates,
        then a broad XAU/GOLD scan. Fails closed if nothing selectable is found.
        """
        mt5 = self._mt5

        ordered: list[str] = []
        if preferred:
            ordered.append(preferred)
        ordered.extend(c for c in GOLD_SYMBOL_CANDIDATES if c != preferred)

        for name in ordered:
            if self._try_select(name):
                result.selected_symbol = name
                result.symbol_discovery = "candidate"
                return name

        # Broad scan of the symbol catalog.
        symbols_get = getattr(mt5, "symbols_get", None)
        if callable(symbols_get):
            try:
                catalog = symbols_get() or []
            except Exception:
                catalog = []
            for sym in catalog:
                sym_name = _opt_str(getattr(sym, "name", None))
                if not sym_name:
                    continue
                upper = sym_name.upper()
                if any(sub in upper for sub in GOLD_SCAN_SUBSTRINGS):
                    if self._try_select(sym_name):
                        result.selected_symbol = sym_name
                        result.symbol_discovery = "scan"
                        return sym_name

        raise Mt5ConnectorError(
            "No selectable gold symbol found (tried candidates and XAU/GOLD scan). "
            "Is XAUUSD visible in this MT5 account? (fail closed)"
        )

    def _try_select(self, name: str) -> bool:
        mt5 = self._mt5
        info = mt5.symbol_info(name)
        if info is None:
            return False
        # Make sure it's visible in Market Watch so quotes/rates flow.
        try:
            return bool(mt5.symbol_select(name, True))
        except Exception:
            return False

    # ── candles (fail closed: at least one bar required) ─────────────────────
    def read_candles(self, result: ProbeResult, symbol: str, timeframe: str, bars: int) -> None:
        mt5 = self._mt5
        tf_attr = _TIMEFRAME_ATTR.get(timeframe.upper())
        if tf_attr is None:
            raise Mt5ConnectorError(
                f"Unknown timeframe '{timeframe}'. Supported: {', '.join(_TIMEFRAME_ATTR)}."
            )
        tf_const = getattr(mt5, tf_attr, None)
        if tf_const is None:
            raise Mt5ConnectorError(f"MT5 module is missing constant {tf_attr}.")

        rates = mt5.copy_rates_from_pos(symbol, tf_const, 0, bars)
        result.timeframe = timeframe.upper()
        result.bars_requested = bars
        if rates is None or len(rates) == 0:
            raise Mt5ConnectorError(
                f"No candles returned for {symbol} {timeframe} ({self._last_error()}). "
                "Refusing to continue (fail closed)."
            )
        result.bars_returned = len(rates)
        last = rates[-1]
        result.last_candle = {
            "time": _iso_from_epoch(_rate_field(last, "time", 0)),
            "open": _safe_float(_rate_field(last, "open", 1)),
            "high": _safe_float(_rate_field(last, "high", 2)),
            "low": _safe_float(_rate_field(last, "low", 3)),
            "close": _safe_float(_rate_field(last, "close", 4)),
        }

    # ── optional reads (warn + continue, never fatal) ────────────────────────
    def read_tick(self, result: ProbeResult, symbol: str) -> None:
        mt5 = self._mt5
        try:
            tick = mt5.symbol_info_tick(symbol)
        except Exception as exc:
            result.warnings.append(f"tick unavailable: {exc}")
            return
        if tick is None:
            result.warnings.append("tick unavailable: symbol_info_tick returned None")
            return
        bid = _safe_float(getattr(tick, "bid", None))
        ask = _safe_float(getattr(tick, "ask", None))
        result.tick_bid = bid
        result.tick_ask = ask
        if bid is not None and ask is not None:
            result.tick_spread = round(ask - bid, 5)
        t = getattr(tick, "time", None)
        result.tick_time = _iso_from_epoch(t) if t is not None else None

    def read_positions(self, result: ProbeResult) -> None:
        mt5 = self._mt5
        try:
            positions = mt5.positions_get()
        except Exception as exc:
            result.warnings.append(f"positions unavailable: {exc}")
            return
        result.open_positions = 0 if positions is None else len(positions)

    def read_history(self, result: ProbeResult, days: int = 7) -> None:
        mt5 = self._mt5
        getter = getattr(mt5, "history_deals_get", None)
        if not callable(getter):
            result.warnings.append("history unavailable: history_deals_get not present")
            return
        now = datetime.now(timezone.utc)
        frm = now - timedelta(days=days)
        try:
            deals = getter(frm, now)
        except Exception as exc:
            result.warnings.append(f"history unavailable: {exc}")
            return
        result.history_days = days
        result.history_deals = 0 if deals is None else len(deals)


# ── orchestration ─────────────────────────────────────────────────────────────
def run_probe(
    connector: Mt5DemoConnector,
    *,
    symbol: str | None = None,
    timeframe: str = "M1",
    bars: int = 100,
) -> ProbeResult:
    """
    Run the full read-only probe. Mandatory steps fail closed (raise
    Mt5ConnectorError); optional steps (tick/positions/history) warn and
    continue. The connection is always shut down. NO ORDERS ARE SENT.
    """
    # Defense in depth: this function must never run with trading enabled.
    assert MT5_DEMO_ONLY is True
    assert LIVE_TRADING_ENABLED is False
    assert ALLOW_REAL_ORDERS is False

    result = ProbeResult()
    try:
        connector.connect()
        result.connected = True

        # Mandatory, fail-closed steps.
        connector.read_account(result)
        selected = connector.discover_gold_symbol(result, preferred=symbol)
        connector.read_candles(result, selected, timeframe, bars)

        # Optional steps — warn and continue.
        connector.read_tick(result, selected)
        connector.read_positions(result)
        connector.read_history(result)
    finally:
        connector.shutdown()

    return result


# ── small safe coercions ──────────────────────────────────────────────────────
def _safe_int(v: Any) -> int | None:
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _safe_float(v: Any) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _opt_str(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _rate_field(rate: Any, name: str, index: int) -> Any:
    """MT5 rates are numpy structured rows (name access) or tuples (index)."""
    try:
        return rate[name]
    except (KeyError, IndexError, TypeError, ValueError):
        try:
            return rate[index]
        except (IndexError, TypeError, KeyError):
            return None


def _iso_from_epoch(epoch: Any) -> str | None:
    e = _safe_float(epoch)
    if e is None:
        return None
    try:
        return datetime.fromtimestamp(e, tz=timezone.utc).isoformat()
    except (OverflowError, OSError, ValueError):
        return None
