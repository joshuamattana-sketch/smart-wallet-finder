"""
services/connectors/mt5_demo_connector.py
------------------------------------------
LM75A/LM75B — MetaTrader 5 demo connector for the private Gold Bot.

PURPOSE
    Connect to a *running, logged-in* MT5 terminal and read demo account +
    XAUUSD data (LM75A), plus GUARDED demo-only order helpers (LM75B).

SAFETY — this module treats MT5 as dangerous even in demo mode:
    * Read methods (account/symbol/candles/tick/positions/history) send nothing.
    * The ONLY order-capable method is `send_demo_order`. It refuses unless
      `read_account()` proved a strict DEMO account (trade_mode == 0). This is
      the LAST line of defense — the trade loop also enforces a CLI confirm
      flag, kill switch, LIVE/REAL flags, a risk gate and order_check BEFORE it
      is ever reached. `run_probe()` (LM75A) never touches the order path.
    * Fails CLOSED. Missing account info, a non-demo account, an unselectable
      symbol or zero candles each raise Mt5ConnectorError.
    * Safety flags default to the safe position:
          MT5_DEMO_ONLY        = True
          LIVE_TRADING_ENABLED = False
          ALLOW_REAL_ORDERS    = False

DESIGN
    The MetaTrader5 package is Windows-only and need not be installed for this
    module to import (so it stays test-friendly and CI-safe). The real package
    is lazy-imported at connect() time, OR an mt5-like module can be injected
    for tests. No automated test requires a real terminal.

    Run via scripts/run_mt5_demo_connector_probe.py (read-only) or
    scripts/run_mt5_demo_trade_loop.py (guarded demo orders).
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
    # LM75C-fix: per-window deal/order report (today / 7d / 30d) and, with
    # --history-debug, compact recent-deal rows.
    history_windows: list[dict[str, Any]] = field(default_factory=list)
    history_recent: list[dict[str, Any]] = field(default_factory=list)

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
        # Set True only after read_account proves trade_mode == demo (strict).
        # send_demo_order refuses to act unless this is True (defense in depth).
        self._demo_verified = False

    @property
    def demo_verified(self) -> bool:
        return self._demo_verified

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
        # Ordering requires a STRICT demo account (trade_mode == 0). Contest
        # accounts may be read but never receive demo orders from this tool.
        self._demo_verified = trade_mode == 0

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
        # If the symbol is already shown in Market Watch, quotes/rates already
        # flow and it is usable as-is. mt5.symbol_select(name, True) returns
        # False for an already-visible symbol (it is a no-op), so we must NOT
        # treat that False as "unselectable" — otherwise a perfectly tradable,
        # ticking symbol gets rejected (e.g. after a "Show All" in Market Watch).
        if getattr(info, "visible", False):
            return True
        # Otherwise add it to Market Watch so quotes/rates start flowing.
        try:
            return bool(mt5.symbol_select(name, True))
        except Exception:
            return False

    def recent_candles(self, symbol: str, timeframe: str, bars: int) -> list[dict[str, Any]]:
        """
        Read recent candles as normalized dicts (read-only). Returns oldest →
        newest. Fails closed if none are returned (decision engine needs data).
        """
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
        if rates is None or len(rates) == 0:
            raise Mt5ConnectorError(
                f"No candles returned for {symbol} {timeframe} ({self._last_error()}). (fail closed)."
            )
        return [{
            "time": _iso_from_epoch(_rate_field(r, "time", 0)),
            "open": _safe_float(_rate_field(r, "open", 1)),
            "high": _safe_float(_rate_field(r, "high", 2)),
            "low": _safe_float(_rate_field(r, "low", 3)),
            "close": _safe_float(_rate_field(r, "close", 4)),
        } for r in rates]

    def copy_rates_range(self, symbol: str, timeframe: str,
                         date_from: datetime, date_to: datetime) -> list[dict[str, Any]]:
        """
        Read-only historical bars in [date_from, date_to] (tz-aware UTC) as
        normalized dicts including tick_volume / spread / real_volume. Returns
        oldest → newest and may be EMPTY (a range can legitimately have no bars,
        or the terminal may only hold limited history) — the caller decides. No
        orders, never writes. Raises Mt5ConnectorError only on a hard MT5 fault.
        """
        mt5 = self._mt5
        tf_attr = _TIMEFRAME_ATTR.get(timeframe.upper())
        if tf_attr is None:
            raise Mt5ConnectorError(
                f"Unknown timeframe '{timeframe}'. Supported: {', '.join(_TIMEFRAME_ATTR)}."
            )
        tf_const = getattr(mt5, tf_attr, None)
        if tf_const is None:
            raise Mt5ConnectorError(f"MT5 module is missing constant {tf_attr}.")
        rates = mt5.copy_rates_range(symbol, tf_const, date_from, date_to)
        if rates is None:
            raise Mt5ConnectorError(
                f"copy_rates_range returned None for {symbol} {timeframe} "
                f"({self._last_error()})."
            )
        return [{
            "time": _iso_from_epoch(_rate_field(r, "time", 0)),
            "open": _safe_float(_rate_field(r, "open", 1)),
            "high": _safe_float(_rate_field(r, "high", 2)),
            "low": _safe_float(_rate_field(r, "low", 3)),
            "close": _safe_float(_rate_field(r, "close", 4)),
            "tick_volume": _safe_float(_rate_field(r, "tick_volume", 5)),
            "spread": _safe_float(_rate_field(r, "spread", 6)),
            "real_volume": _safe_float(_rate_field(r, "real_volume", 7)),
        } for r in rates]

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

    # ── deal / order history (LM75C-fix — robust, multi-window) ──────────────
    def deal_history(self, date_from: datetime, date_to: datetime) -> list[Any]:
        """All deals in [date_from, date_to]. Empty list on any problem."""
        getter = getattr(self._mt5, "history_deals_get", None)
        if not callable(getter):
            return []
        try:
            deals = getter(date_from, date_to)
        except Exception:
            return []
        return list(deals) if deals else []

    def order_history(self, date_from: datetime, date_to: datetime) -> list[Any]:
        """All history orders in [date_from, date_to]. Empty list on any problem."""
        getter = getattr(self._mt5, "history_orders_get", None)
        if not callable(getter):
            return []
        try:
            orders = getter(date_from, date_to)
        except Exception:
            return []
        return list(orders) if orders else []

    def summarize_deals(self, deals: list[Any], symbol: str | None = None) -> dict[str, Any]:
        """
        Count deals defensively. `entry`/`exit` use MT5 DEAL_ENTRY_IN/OUT; only
        real trade deals (type buy/sell) contribute to symbol counts and PnL —
        balance/credit deals (type >= 2) are excluded from the trade sums but
        still counted in `total`.
        """
        mt5 = self._mt5
        entry_in = getattr(mt5, "DEAL_ENTRY_IN", 0)
        entry_out = getattr(mt5, "DEAL_ENTRY_OUT", 1)
        deal_buy = getattr(mt5, "DEAL_TYPE_BUY", 0)
        deal_sell = getattr(mt5, "DEAL_TYPE_SELL", 1)

        total = len(deals)
        sym_deals = 0
        n_entry = 0
        n_exit = 0
        profit_sum = 0.0
        commission_sum = 0.0
        swap_sum = 0.0
        for d in deals:
            dtype = _safe_int(getattr(d, "type", None))
            is_trade = dtype in (deal_buy, deal_sell)
            dsym = _opt_str(getattr(d, "symbol", None))
            if symbol is not None and dsym != symbol:
                continue
            if dsym:
                sym_deals += 1
            entry = _safe_int(getattr(d, "entry", None))
            if entry == entry_in:
                n_entry += 1
            elif entry == entry_out:
                n_exit += 1
            if is_trade:
                profit_sum += _safe_float(getattr(d, "profit", None)) or 0.0
                commission_sum += _safe_float(getattr(d, "commission", None)) or 0.0
                swap_sum += _safe_float(getattr(d, "swap", None)) or 0.0
        return {
            "total": total,
            "symbol_deals": sym_deals,
            "entry_deals": n_entry,
            "exit_deals": n_exit,
            "profit_sum": round(profit_sum, 2),
            "commission_sum": round(commission_sum, 2),
            "swap_sum": round(swap_sum, 2),
        }

    def deal_view(self, deal: Any) -> dict[str, Any]:
        """Compact deal row for --history-debug."""
        mt5 = self._mt5
        dtype = _safe_int(getattr(deal, "type", None))
        type_label = ("buy" if dtype == getattr(mt5, "DEAL_TYPE_BUY", 0)
                      else "sell" if dtype == getattr(mt5, "DEAL_TYPE_SELL", 1)
                      else f"type{dtype}")
        entry = _safe_int(getattr(deal, "entry", None))
        entry_label = ("in" if entry == getattr(mt5, "DEAL_ENTRY_IN", 0)
                       else "out" if entry == getattr(mt5, "DEAL_ENTRY_OUT", 1)
                       else str(entry))
        return {
            "ticket": _safe_int(getattr(deal, "ticket", None)),
            "order": _safe_int(getattr(deal, "order", None)),
            "time": _iso_from_epoch(getattr(deal, "time", None)),
            "symbol": _opt_str(getattr(deal, "symbol", None)),
            "type": type_label,
            "entry": entry_label,
            "volume": _safe_float(getattr(deal, "volume", None)),
            "price": _safe_float(getattr(deal, "price", None)),
            "profit": _safe_float(getattr(deal, "profit", None)),
            "commission": _safe_float(getattr(deal, "commission", None)),
            "swap": _safe_float(getattr(deal, "swap", None)),
            "comment": _opt_str(getattr(deal, "comment", None)),
        }

    def read_history(self, result: ProbeResult, days: int = 7) -> None:
        """Back-compat shim — delegates to the multi-window report (7d total)."""
        self.read_history_report(result, symbol=result.selected_symbol)

    def read_history_report(
        self,
        result: ProbeResult,
        *,
        symbol: str | None = None,
        debug: bool = False,
    ) -> None:
        """
        Query deals + orders across today / 7d / 30d windows and fill
        result.history_windows. Timezone-explicit: all bounds are tz-aware UTC,
        and `date_to` is padded +1 day so a broker server clock that runs ahead
        of UTC never excludes a just-closed deal. With debug, fills
        result.history_recent with compact rows from the widest window.
        """
        if not callable(getattr(self._mt5, "history_deals_get", None)):
            result.warnings.append("history unavailable: history_deals_get not present")
            return

        now = datetime.now(timezone.utc)
        to = now + timedelta(days=1)  # pad future for server-time-ahead brokers
        start_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        windows = [
            ("today", start_today, to),
            ("7d", now - timedelta(days=7), to),
            ("30d", now - timedelta(days=30), to),
        ]

        widest_deals: list[Any] = []
        for label, frm, win_to in windows:
            deals = self.deal_history(frm, win_to)
            orders = self.order_history(frm, win_to)
            summary = self.summarize_deals(deals, symbol=symbol)
            result.history_windows.append({
                "label": label,
                "from": frm.isoformat(),
                "to": win_to.isoformat(),
                "deal_total": summary["total"],
                "symbol_deals": summary["symbol_deals"],
                "entry_deals": summary["entry_deals"],
                "exit_deals": summary["exit_deals"],
                "profit_sum": summary["profit_sum"],
                "commission_sum": summary["commission_sum"],
                "swap_sum": summary["swap_sum"],
                "order_total": len(orders),
            })
            if label == "30d":
                widest_deals = deals

        # Back-compat fields (7d window).
        seven = next((w for w in result.history_windows if w["label"] == "7d"), None)
        if seven:
            result.history_days = 7
            result.history_deals = seven["deal_total"]

        if debug and widest_deals:
            recent = sorted(
                widest_deals,
                key=lambda d: _safe_float(getattr(d, "time", None)) or 0.0,
                reverse=True,
            )[:20]
            result.history_recent = [self.deal_view(d) for d in recent]

    # ── demo order helpers (LM75B — guarded, demo account only) ──────────────
    # These are the ONLY order-capable methods. They refuse to act unless
    # read_account() proved a strict demo account (self._demo_verified). The
    # higher-level safety (CLI confirm flag, kill switch, LIVE/REAL flags, risk
    # gate, order_check acceptance) is enforced by the caller BEFORE
    # send_demo_order is ever reached — this is the last line of defense, not
    # the only one.

    def symbol_point(self, symbol: str) -> float:
        """Point size for SL/TP math. Raises if unavailable (fail closed)."""
        mt5 = self._mt5
        info = mt5.symbol_info(symbol)
        point = _safe_float(getattr(info, "point", None)) if info is not None else None
        if point is None or point <= 0:
            raise Mt5ConnectorError(f"Cannot read point size for {symbol} (fail closed).")
        return point

    def current_prices(self, symbol: str) -> tuple[float, float]:
        """(bid, ask) for the symbol. Raises if unavailable (fail closed)."""
        mt5 = self._mt5
        tick = mt5.symbol_info_tick(symbol)
        bid = _safe_float(getattr(tick, "bid", None)) if tick is not None else None
        ask = _safe_float(getattr(tick, "ask", None)) if tick is not None else None
        if bid is None or ask is None:
            raise Mt5ConnectorError(f"Cannot read bid/ask for {symbol} (fail closed).")
        return bid, ask

    def compute_levels(self, symbol: str, side: str, sl_points: int, tp_points: int) -> dict[str, Any]:
        """
        Entry/SL/TP prices + order type from point offsets, validated for
        orientation. No volume needed — used by both the request builder and the
        auto-volume risk math. Fails closed on bad side / missing SL-TP.
        """
        mt5 = self._mt5
        side_l = side.lower()
        if side_l not in ("buy", "sell"):
            raise Mt5ConnectorError(f"side must be buy/sell, got '{side}'.")
        if not (sl_points and sl_points > 0) or not (tp_points and tp_points > 0):
            raise Mt5ConnectorError("SL and TP are required and must be positive (fail closed).")

        point = self.symbol_point(symbol)
        bid, ask = self.current_prices(symbol)
        if side_l == "buy":
            order_type = mt5.ORDER_TYPE_BUY
            price = ask
            sl = price - sl_points * point
            tp = price + tp_points * point
            if not (sl < price < tp):
                raise Mt5ConnectorError("Buy SL/TP inverted (need SL < price < TP).")
        else:
            order_type = mt5.ORDER_TYPE_SELL
            price = bid
            sl = price + sl_points * point
            tp = price - tp_points * point
            if not (tp < price < sl):
                raise Mt5ConnectorError("Sell SL/TP inverted (need TP < price < SL).")

        digits = _safe_int(getattr(mt5.symbol_info(symbol), "digits", None)) or 5
        return {"order_type": order_type, "side": side_l, "digits": digits,
                "price": round(price, digits), "sl": round(sl, digits), "tp": round(tp, digits)}

    def build_demo_order_request(
        self,
        *,
        symbol: str,
        side: str,
        volume: float,
        sl_points: int,
        tp_points: int,
        comment: str = "lumora-gold-bot-demo",
        deviation: int = 20,
        magic: int = 750_750,
    ) -> dict[str, Any]:
        """
        Build an MT5 market-order request with SL/TP derived from point offsets.
        SL/TP are mandatory and validated for correct orientation. Pure build —
        nothing is sent here.
        """
        mt5 = self._mt5
        levels = self.compute_levels(symbol, side, sl_points, tp_points)
        return {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(volume),
            "type": levels["order_type"],
            "price": levels["price"],
            "sl": levels["sl"],
            "tp": levels["tp"],
            "deviation": deviation,
            "magic": magic,
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": getattr(mt5, "ORDER_FILLING_IOC", 1),
        }

    # ── account / symbol risk metadata + margin/profit calc (LM75D) ──────────
    def account_snapshot(self) -> dict[str, Any]:
        """Equity/balance/leverage/free-margin/currency (read-only). Fail closed if absent."""
        info = self._mt5.account_info()
        if info is None:
            raise Mt5ConnectorError("account_info() unavailable for risk math (fail closed).")
        return {
            "balance": _safe_float(getattr(info, "balance", None)),
            "equity": _safe_float(getattr(info, "equity", None)),
            "leverage": _safe_int(getattr(info, "leverage", None)),
            "margin_free": _safe_float(getattr(info, "margin_free", None)),
            "currency": _opt_str(getattr(info, "currency", None)),
        }

    def symbol_metadata(self, symbol: str) -> dict[str, Any]:
        """Contract/volume/tick metadata for risk + margin math. Fail closed if absent."""
        info = self._mt5.symbol_info(symbol)
        if info is None:
            raise Mt5ConnectorError(f"symbol_info({symbol}) unavailable for risk math (fail closed).")
        return {
            "point": _safe_float(getattr(info, "point", None)),
            "digits": _safe_int(getattr(info, "digits", None)),
            "contract_size": _safe_float(getattr(info, "trade_contract_size", None)),
            "volume_min": _safe_float(getattr(info, "volume_min", None)),
            "volume_step": _safe_float(getattr(info, "volume_step", None)),
            "volume_max": _safe_float(getattr(info, "volume_max", None)),
            "tick_size": _safe_float(getattr(info, "trade_tick_size", None)),
            "tick_value": _safe_float(getattr(info, "trade_tick_value", None)),
            "margin_initial": _safe_float(getattr(info, "margin_initial", None)),
        }

    def calc_margin(self, *, order_type: int, symbol: str, volume: float, price: float) -> float | None:
        """mt5.order_calc_margin → required margin, or None if unavailable."""
        fn = getattr(self._mt5, "order_calc_margin", None)
        if not callable(fn):
            return None
        try:
            m = fn(order_type, symbol, volume, price)
        except Exception:
            return None
        return _safe_float(m)

    def calc_profit(
        self, *, order_type: int, symbol: str, volume: float, price_open: float, price_close: float
    ) -> float | None:
        """mt5.order_calc_profit → profit (negative = loss), or None if unavailable."""
        fn = getattr(self._mt5, "order_calc_profit", None)
        if not callable(fn):
            return None
        try:
            p = fn(order_type, symbol, volume, price_open, price_close)
        except Exception:
            return None
        return _safe_float(p)

    def estimate_sl_loss(
        self, *, order_type: int, symbol: str, volume: float, entry: float, sl: float
    ) -> float | None:
        """Absolute estimated loss if price hits SL, via order_calc_profit. None if unavailable."""
        profit = self.calc_profit(order_type=order_type, symbol=symbol, volume=volume,
                                  price_open=entry, price_close=sl)
        if profit is None:
            return None
        return abs(profit) if profit < 0 else 0.0

    def check_order(self, request: dict[str, Any]) -> Any:
        """Run MT5 order_check (validation only — sends nothing)."""
        return self._mt5.order_check(request)

    def send_demo_order(self, request: dict[str, Any]) -> Any:
        """
        Send a market order. LAST-LINE guard: refuses unless read_account proved
        a strict demo account. The caller must have already passed the risk
        gate, confirm flag, kill switch and order_check — this method does not
        re-derive those, it only blocks non-demo accounts.
        """
        if not self._demo_verified:
            raise Mt5ConnectorError(
                "send_demo_order refused: demo account not verified. "
                "read_account() must prove trade_mode == demo first (fail closed)."
            )
        return self._mt5.order_send(request)

    def positions_for_symbol(self, symbol: str) -> list[Any]:
        """Open positions for one symbol (read-only)."""
        mt5 = self._mt5
        try:
            positions = mt5.positions_get(symbol=symbol)
        except TypeError:
            positions = mt5.positions_get()
        except Exception:
            return []
        if positions is None:
            return []
        return [p for p in positions if _opt_str(getattr(p, "symbol", None)) == symbol]

    # ── position management + close (LM75C — guarded, demo account only) ──────
    def all_positions(self) -> list[Any]:
        """Every open position (read-only)."""
        mt5 = self._mt5
        try:
            positions = mt5.positions_get()
        except Exception:
            return []
        return list(positions) if positions else []

    def position_by_ticket(self, ticket: int) -> Any | None:
        """Find one open position by ticket (read-only). None if not found."""
        mt5 = self._mt5
        getter = getattr(mt5, "positions_get", None)
        if callable(getter):
            try:
                rows = getter(ticket=ticket)
                if rows:
                    return rows[0]
            except TypeError:
                pass  # older signature without ticket= kwarg
            except Exception:
                return None
        for p in self.all_positions():
            if _safe_int(getattr(p, "ticket", None)) == ticket:
                return p
        return None

    def position_view(self, position: Any) -> dict[str, Any]:
        """Read-only summary dict of a position for printing/journaling."""
        ptype = _safe_int(getattr(position, "type", None))
        side = "buy" if ptype == 0 else "sell" if ptype == 1 else "unknown"
        symbol = _opt_str(getattr(position, "symbol", None))
        cur_bid = cur_ask = None
        if symbol:
            try:
                cur_bid, cur_ask = self.current_prices(symbol)
            except Mt5ConnectorError:
                pass
        return {
            "ticket": _safe_int(getattr(position, "ticket", None)),
            "symbol": symbol,
            "side": side,
            "volume": _safe_float(getattr(position, "volume", None)),
            "price_open": _safe_float(getattr(position, "price_open", None)),
            "price_current": _safe_float(getattr(position, "price_current", None)),
            "current_bid": cur_bid,
            "current_ask": cur_ask,
            "sl": _safe_float(getattr(position, "sl", None)),
            "tp": _safe_float(getattr(position, "tp", None)),
            "profit": _safe_float(getattr(position, "profit", None)),
            "magic": _safe_int(getattr(position, "magic", None)),
            "comment": _opt_str(getattr(position, "comment", None)),
        }

    def build_close_request(
        self,
        position: Any,
        *,
        comment: str = "lumora-gold-bot-demo-close",
        deviation: int = 20,
    ) -> dict[str, Any]:
        """
        Build an MT5 close request for an open position: opposite order type at
        the matching price (close BUY at bid, close SELL at ask), using the
        position's exact ticket/symbol/volume. Pure build — nothing is sent.
        """
        mt5 = self._mt5
        ptype = _safe_int(getattr(position, "type", None))
        symbol = _opt_str(getattr(position, "symbol", None))
        volume = _safe_float(getattr(position, "volume", None))
        ticket = _safe_int(getattr(position, "ticket", None))
        if symbol is None or ticket is None:
            raise Mt5ConnectorError("Position is missing symbol/ticket (fail closed).")
        if not (volume and volume > 0):
            raise Mt5ConnectorError("Position volume must be positive (fail closed).")
        if ptype not in (0, 1):
            raise Mt5ConnectorError(f"Unknown position type {ptype} (fail closed).")

        bid, ask = self.current_prices(symbol)
        digits = _safe_int(getattr(mt5.symbol_info(symbol), "digits", None)) or 5
        if ptype == 0:  # closing a BUY → SELL at bid
            close_type = mt5.ORDER_TYPE_SELL
            price = bid
        else:           # closing a SELL → BUY at ask
            close_type = mt5.ORDER_TYPE_BUY
            price = ask

        magic = _safe_int(getattr(position, "magic", None)) or 750_750
        return {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(volume),
            "type": close_type,
            "position": ticket,
            "price": round(price, digits),
            "deviation": deviation,
            "magic": magic,
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": getattr(mt5, "ORDER_FILLING_IOC", 1),
        }

    def send_demo_close(self, request: dict[str, Any]) -> Any:
        """
        Send a close order. LAST-LINE guard: refuses unless read_account proved a
        strict demo account. The caller enforces confirm flag / kill switch /
        live flags BEFORE calling this.
        """
        if not self._demo_verified:
            raise Mt5ConnectorError(
                "send_demo_close refused: demo account not verified. "
                "read_account() must prove trade_mode == demo first (fail closed)."
            )
        return self._mt5.order_send(request)


# ── orchestration ─────────────────────────────────────────────────────────────
def run_probe(
    connector: Mt5DemoConnector,
    *,
    symbol: str | None = None,
    timeframe: str = "M1",
    bars: int = 100,
    history_debug: bool = False,
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
        connector.read_history_report(result, symbol=selected, debug=history_debug)
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
