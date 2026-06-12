"""
tests/connectors/test_mt5_demo_connector.py
--------------------------------------------
LM75A — Deterministic tests for the read-only MT5 demo connector.

No real MT5 terminal is required: a fake mt5-like module is injected. These
tests prove the connector reads demo data, fails closed on real/unreadable
accounts, discovers gold symbols, and never exposes an order path.
"""

from __future__ import annotations

import pytest

from services.connectors import mt5_demo_connector as mod
from services.connectors.mt5_demo_connector import (
    Mt5ConnectorError,
    Mt5DemoConnector,
    run_probe,
)


# ── Fake MT5 module ───────────────────────────────────────────────────────────
class _Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class FakeMt5:
    """Minimal MetaTrader5-shaped stub for injection."""

    TIMEFRAME_M1 = 1
    TIMEFRAME_M5 = 5
    TIMEFRAME_M15 = 15
    TIMEFRAME_M30 = 30
    TIMEFRAME_H1 = 16385
    TIMEFRAME_H4 = 16388
    TIMEFRAME_D1 = 16408

    def __init__(self, *, trade_mode=0, account=True, symbols=("XAUUSD",),
                 candles=10, tick=True, init_ok=True):
        self._trade_mode = trade_mode
        self._account = account
        self._symbols = list(symbols)
        self._candles = candles
        self._tick = tick
        self._init_ok = init_ok
        self.shutdown_called = False
        self.selected: list[str] = []

    def initialize(self):
        return self._init_ok

    def shutdown(self):
        self.shutdown_called = True

    def last_error(self):
        return (1, "fake error")

    def account_info(self):
        if not self._account:
            return None
        return _Obj(login=5_000_111, server="MetaQuotes-Demo", name="Demo User",
                    currency="USD", trade_mode=self._trade_mode, balance=10000.0,
                    equity=10000.0, margin=0.0, margin_free=10000.0)

    def symbol_info(self, name):
        return _Obj(name=name) if name in self._symbols else None

    def symbol_select(self, name, enable):
        if name in self._symbols:
            self.selected.append(name)
            return True
        return False

    def symbols_get(self):
        return [_Obj(name=n) for n in self._symbols]

    def copy_rates_from_pos(self, symbol, tf, start, count):
        if self._candles <= 0:
            return []
        n = min(count, self._candles)
        # (time, open, high, low, close, ...) tuples — index access path.
        base = 1_700_000_000
        return [(base + i * 60, 2380.0 + i, 2381.0 + i, 2379.0 + i, 2380.5 + i)
                for i in range(n)]

    def symbol_info_tick(self, symbol):
        if not self._tick:
            return None
        return _Obj(bid=2380.5, ask=2380.8, time=1_700_000_600)

    def positions_get(self):
        return []

    def history_deals_get(self, frm, to):
        return [_Obj(ticket=1), _Obj(ticket=2)]


# ── Happy path ────────────────────────────────────────────────────────────────
def test_probe_reads_demo_account_and_candles():
    fake = FakeMt5(trade_mode=0, symbols=("XAUUSD",), candles=50)
    result = run_probe(Mt5DemoConnector(fake), symbol="XAUUSD", timeframe="M1", bars=50)

    assert result.connected is True
    assert result.is_demo is True
    assert result.trade_mode_label == "demo"
    assert result.account_login == 5_000_111
    assert result.selected_symbol == "XAUUSD"
    assert result.symbol_discovery == "candidate"
    assert result.bars_returned == 50
    assert result.last_candle is not None
    assert result.tick_spread == pytest.approx(0.3, abs=1e-6)
    assert result.open_positions == 0
    assert result.history_deals == 2
    # Read-only invariants.
    assert result.read_only is True
    assert result.orders_sent == 0
    assert fake.shutdown_called is True


def test_safety_flags_are_safe_by_default():
    assert mod.MT5_DEMO_ONLY is True
    assert mod.LIVE_TRADING_ENABLED is False
    assert mod.ALLOW_REAL_ORDERS is False


def test_no_order_path_exposed():
    # The connector must expose no order-sending surface.
    connector = Mt5DemoConnector(FakeMt5())
    for forbidden in ("order_send", "order_check", "buy", "sell", "send_order"):
        assert not hasattr(connector, forbidden)


# ── Fail-closed conditions ────────────────────────────────────────────────────
def test_real_account_fails_closed():
    fake = FakeMt5(trade_mode=2)  # real
    with pytest.raises(Mt5ConnectorError, match="NOT a demo"):
        run_probe(Mt5DemoConnector(fake), symbol="XAUUSD")
    assert fake.shutdown_called is True  # still cleaned up


def test_missing_account_info_fails_closed():
    fake = FakeMt5(account=False)
    with pytest.raises(Mt5ConnectorError, match="account_info"):
        run_probe(Mt5DemoConnector(fake))
    assert fake.shutdown_called is True


def test_initialize_failure_fails_closed():
    fake = FakeMt5(init_ok=False)
    with pytest.raises(Mt5ConnectorError, match="initialize"):
        run_probe(Mt5DemoConnector(fake))


def test_no_candles_fails_closed():
    fake = FakeMt5(candles=0)
    with pytest.raises(Mt5ConnectorError, match="No candles"):
        run_probe(Mt5DemoConnector(fake), symbol="XAUUSD")


def test_no_gold_symbol_fails_closed():
    fake = FakeMt5(symbols=("EURUSD", "USDJPY"))
    with pytest.raises(Mt5ConnectorError, match="gold symbol"):
        run_probe(Mt5DemoConnector(fake))


# ── Discovery paths ───────────────────────────────────────────────────────────
def test_symbol_discovery_via_scan():
    # No candidate matches exactly, but a scan finds an XAU symbol.
    fake = FakeMt5(symbols=("XAUUSD.raw",))
    result = run_probe(Mt5DemoConnector(fake))
    assert result.selected_symbol == "XAUUSD.raw"
    assert result.symbol_discovery == "scan"


def test_contest_account_allowed_with_warning():
    fake = FakeMt5(trade_mode=1)  # contest
    result = run_probe(Mt5DemoConnector(fake), symbol="XAUUSD")
    assert result.is_demo is False
    assert result.trade_mode_label == "contest"
    assert any("CONTEST" in w for w in result.warnings)


# ── Optional reads degrade gracefully ─────────────────────────────────────────
def test_tick_unavailable_warns_but_continues():
    fake = FakeMt5(tick=False)
    result = run_probe(Mt5DemoConnector(fake), symbol="XAUUSD")
    assert result.tick_bid is None
    assert any("tick unavailable" in w for w in result.warnings)
    assert result.bars_returned == 10  # candles still read
