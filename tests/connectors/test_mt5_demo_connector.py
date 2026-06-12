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
    ProbeResult,
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

    # Order constants (LM75B)
    TRADE_ACTION_DEAL = 1
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    ORDER_TIME_GTC = 0
    ORDER_FILLING_IOC = 1
    TRADE_RETCODE_DONE = 10009

    POSITION_TYPE_BUY = 0
    POSITION_TYPE_SELL = 1

    # Deal constants (LM75C-fix)
    DEAL_TYPE_BUY = 0
    DEAL_TYPE_SELL = 1
    DEAL_ENTRY_IN = 0
    DEAL_ENTRY_OUT = 1

    def __init__(self, *, trade_mode=0, account=True, symbols=("XAUUSD",),
                 candles=10, tick=True, init_ok=True, point=0.01,
                 send_retcode=10009, positions=None, deals=None, orders=None):
        self._trade_mode = trade_mode
        self._account = account
        self._symbols = list(symbols)
        self._candles = candles
        self._tick = tick
        self._init_ok = init_ok
        self._point = point
        self._send_retcode = send_retcode
        self._positions = list(positions) if positions else []
        # Default: two generic deals (back-compat with the read-only probe test).
        self._deals = list(deals) if deals is not None else [_Obj(ticket=1), _Obj(ticket=2)]
        self._orders = list(orders) if orders is not None else []
        self.shutdown_called = False
        self.selected: list[str] = []
        self.sent_requests: list[dict] = []  # records every order_send call

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
        return _Obj(name=name, point=self._point, digits=2) if name in self._symbols else None

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

    def positions_get(self, symbol=None, ticket=None):
        rows = self._positions
        if ticket is not None:
            rows = [p for p in rows if getattr(p, "ticket", None) == ticket]
        if symbol is not None:
            rows = [p for p in rows if getattr(p, "symbol", None) == symbol]
        return list(rows)

    def history_deals_get(self, frm, to):
        return list(self._deals)

    def history_orders_get(self, frm, to):
        return list(self._orders)

    # ── order surface (LM75B) ────────────────────────────────────────────────
    def order_check(self, request):
        return _Obj(retcode=self.TRADE_RETCODE_DONE, comment="Done")

    def order_send(self, request):
        self.sent_requests.append(request)
        return _Obj(retcode=self._send_retcode, comment="Done",
                    order=111, deal=222)


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


def test_send_demo_order_refuses_without_demo_verification():
    # LM75B: the only order-capable method refuses unless read_account proved demo.
    connector = Mt5DemoConnector(FakeMt5())
    connector.connect()
    assert connector.demo_verified is False  # read_account not called yet
    with pytest.raises(Mt5ConnectorError, match="demo account not verified"):
        connector.send_demo_order({"symbol": "XAUUSD"})


def test_build_demo_order_request_buy_orientation():
    connector = Mt5DemoConnector(FakeMt5(point=0.01))
    connector.connect()
    req = connector.build_demo_order_request(
        symbol="XAUUSD", side="buy", volume=0.01, sl_points=300, tp_points=600)
    assert req["sl"] < req["price"] < req["tp"]  # buy: SL below, TP above
    assert req["volume"] == 0.01


def test_build_demo_order_request_sell_orientation():
    connector = Mt5DemoConnector(FakeMt5(point=0.01))
    connector.connect()
    req = connector.build_demo_order_request(
        symbol="XAUUSD", side="sell", volume=0.01, sl_points=300, tp_points=600)
    assert req["tp"] < req["price"] < req["sl"]  # sell: TP below, SL above


def test_build_demo_order_request_requires_sl_tp():
    connector = Mt5DemoConnector(FakeMt5())
    connector.connect()
    with pytest.raises(Mt5ConnectorError, match="SL and TP are required"):
        connector.build_demo_order_request(
            symbol="XAUUSD", side="buy", volume=0.01, sl_points=0, tp_points=600)


def test_send_demo_order_works_after_demo_verified():
    fake = FakeMt5(trade_mode=0)
    connector = Mt5DemoConnector(fake)
    connector.connect()
    connector.read_account(ProbeResult())  # proves demo → demo_verified True
    assert connector.demo_verified is True
    req = connector.build_demo_order_request(
        symbol="XAUUSD", side="buy", volume=0.01, sl_points=300, tp_points=600)
    res = connector.send_demo_order(req)
    assert res.retcode == fake.TRADE_RETCODE_DONE
    assert len(fake.sent_requests) == 1


def test_contest_account_cannot_send_orders():
    # Contest is readable but NOT strict-demo, so ordering stays blocked.
    fake = FakeMt5(trade_mode=1)
    connector = Mt5DemoConnector(fake)
    connector.connect()
    connector.read_account(ProbeResult())
    assert connector.demo_verified is False
    with pytest.raises(Mt5ConnectorError, match="demo account not verified"):
        connector.send_demo_order({"symbol": "XAUUSD"})


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


# ── LM75C: position listing + close ───────────────────────────────────────────
def _pos(ticket=5001, ptype=0, symbol="XAUUSD", volume=0.01):
    return _Obj(ticket=ticket, type=ptype, symbol=symbol, volume=volume,
                price_open=2380.0, price_current=2381.0, sl=2377.0, tp=2386.0,
                profit=1.0, magic=750_750, comment="lumora-gold-bot-demo")


def test_all_positions_and_by_ticket():
    fake = FakeMt5(positions=[_pos(ticket=1), _pos(ticket=2, ptype=1)])
    c = Mt5DemoConnector(fake)
    c.connect()
    assert len(c.all_positions()) == 2
    assert c.position_by_ticket(2) is not None
    assert c.position_by_ticket(999) is None


def test_build_close_request_for_buy_uses_sell_at_bid():
    fake = FakeMt5(positions=[_pos(ticket=10, ptype=0)])
    c = Mt5DemoConnector(fake)
    c.connect()
    pos = c.position_by_ticket(10)
    req = c.build_close_request(pos)
    assert req["type"] == fake.ORDER_TYPE_SELL       # close BUY → SELL
    assert req["price"] == 2380.5                     # bid
    assert req["position"] == 10
    assert req["volume"] == 0.01


def test_build_close_request_for_sell_uses_buy_at_ask():
    fake = FakeMt5(positions=[_pos(ticket=11, ptype=1)])
    c = Mt5DemoConnector(fake)
    c.connect()
    req = c.build_close_request(c.position_by_ticket(11))
    assert req["type"] == fake.ORDER_TYPE_BUY        # close SELL → BUY
    assert req["price"] == 2380.8                     # ask


def test_send_demo_close_refuses_without_demo_verification():
    c = Mt5DemoConnector(FakeMt5(positions=[_pos()]))
    c.connect()
    with pytest.raises(Mt5ConnectorError, match="demo account not verified"):
        c.send_demo_close({"symbol": "XAUUSD"})


def test_send_demo_close_works_after_demo_verified():
    fake = FakeMt5(trade_mode=0, positions=[_pos(ticket=20)])
    c = Mt5DemoConnector(fake)
    c.connect()
    c.read_account(ProbeResult())
    req = c.build_close_request(c.position_by_ticket(20))
    res = c.send_demo_close(req)
    assert res.retcode == fake.TRADE_RETCODE_DONE
    assert len(fake.sent_requests) == 1


# ── LM75C-fix: deal/order history ─────────────────────────────────────────────
def _deal(ticket, *, symbol="XAUUSD", dtype=0, entry=1, volume=0.01,
          price=2380.0, profit=-2.58, commission=0.0, swap=0.0, t=1_700_000_000):
    return _Obj(ticket=ticket, order=ticket + 1, time=t, symbol=symbol, type=dtype,
                entry=entry, volume=volume, price=price, profit=profit,
                commission=commission, swap=swap, comment="lumora-gold-bot-demo")


def test_history_report_fills_windows_and_counts():
    deals = [
        _deal(1, dtype=0, entry=0, profit=0.0),     # entry buy
        _deal(2, dtype=1, entry=1, profit=-2.58),   # exit sell, the loss
        _Obj(ticket=3, type=2, entry=0, symbol=None),  # balance op (excluded from PnL)
    ]
    fake = FakeMt5(deals=deals, orders=[_Obj(ticket=10), _Obj(ticket=11)])
    result = run_probe(Mt5DemoConnector(fake), symbol="XAUUSD")

    assert len(result.history_windows) == 3
    seven = next(w for w in result.history_windows if w["label"] == "7d")
    assert seven["deal_total"] == 3
    assert seven["symbol_deals"] == 2          # only the two XAUUSD deals
    assert seven["entry_deals"] == 1           # deal1 is DEAL_ENTRY_IN (deal3 filtered by symbol)
    assert seven["exit_deals"] == 1
    assert seven["profit_sum"] == pytest.approx(-2.58)
    assert seven["order_total"] == 2
    # back-compat field still set
    assert result.history_deals == 3


def test_history_debug_fills_recent_rows():
    fake = FakeMt5(deals=[_deal(7, profit=-2.58)])
    result = run_probe(Mt5DemoConnector(fake), symbol="XAUUSD", history_debug=True)
    assert len(result.history_recent) == 1
    row = result.history_recent[0]
    assert row["ticket"] == 7
    assert row["symbol"] == "XAUUSD"
    assert row["entry"] == "out"
    assert row["profit"] == pytest.approx(-2.58)


def test_history_windows_are_padded_into_future():
    # date_to must be > now so a server clock ahead of UTC can't exclude deals.
    import datetime as dt
    fake = FakeMt5()
    result = run_probe(Mt5DemoConnector(fake))
    now = dt.datetime.now(dt.timezone.utc)
    for w in result.history_windows:
        assert dt.datetime.fromisoformat(w["to"]) > now
