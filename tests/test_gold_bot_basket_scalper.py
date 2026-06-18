"""
tests/test_gold_bot_basket_scalper.py
--------------------------------------
LM100A — Tests for the pure basket scalp logic AND the worker basket iteration
(fully faked MT5 connector; no terminal, no network, no real orders).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from services.gold_bot_basket_scalper import (
    CLOSE_ENGINE_REVERSAL,
    CLOSE_HARD_LOSS,
    CLOSE_PRESSURE_FLIP,
    CLOSE_PROFIT_LOCK,
    CLOSE_PROFIT_TARGET,
    CLOSE_TIME_STOP,
    BasketConfig,
    aggregate_profit,
    basket_side,
    cap_basket_positions,
    decide_basket_action,
    price_action_pressure,
    scaled_position_count,
)
from services.gold_bot_risk_gate import SafetyConfig
from services.gold_bot_worker import GoldBotWorker, WorkerConfig

NOW = datetime(2026, 6, 16, 13, 0, 0, tzinfo=timezone.utc)
CFG = BasketConfig(num_positions=5, basket_risk_cap_pct=3.0, profit_target_pct=0.6,
                   hard_loss_cap_pct=1.5, time_stop_seconds=60.0)


# ── pure logic ─────────────────────────────────────────────────────────────────
def test_aggregate_profit_sums_positions():
    assert aggregate_profit([{"profit": 1.5}, {"profit": -0.5}, {"profit": 2.0}]) == 3.0
    assert aggregate_profit([]) == 0.0


def test_cap_limits_legs_to_risk_cap():
    # equity 10000, cap 3% = 300; 10 risk/leg → 30 max, request 5 → 5
    assert cap_basket_positions(5, 10.0, 10000.0, 3.0) == 5
    # 80 risk/leg → cap 300 allows only 3 even though 5 requested
    assert cap_basket_positions(5, 80.0, 10000.0, 3.0) == 3
    # one leg already breaks the cap → 0
    assert cap_basket_positions(5, 400.0, 10000.0, 3.0) == 0
    assert cap_basket_positions(5, 10.0, 0.0, 3.0) == 0


def test_scaled_position_count():
    assert scaled_position_count(50, min_confidence=50, base_positions=5, max_positions=10) == 5
    assert scaled_position_count(100, min_confidence=50, base_positions=5, max_positions=10) == 10
    assert scaled_position_count(75, min_confidence=50, base_positions=5, max_positions=10) == 8
    assert scaled_position_count(90, min_confidence=50, base_positions=5, max_positions=0) == 5  # off


def test_open_action_scales_legs_with_confidence():
    cfg = BasketConfig(num_positions=5, max_positions=10)
    low = decide_basket_action(open_positions=[], equity=10000.0, now=NOW, opened_at=None,
                               signal_decision="LONG", signal_confidence=50, min_confidence=50, cfg=cfg)
    high = decide_basket_action(open_positions=[], equity=10000.0, now=NOW, opened_at=None,
                                signal_decision="LONG", signal_confidence=100, min_confidence=50, cfg=cfg)
    assert low.kind == "open" and low.num_positions == 5
    assert high.kind == "open" and high.num_positions == 10


def test_scale_in_adds_toward_target():
    cfg = BasketConfig(num_positions=2, max_positions=8, scale_in=True)
    pos = [{"profit": 1.0, "side": "buy"}, {"profit": 1.0, "side": "buy"}]   # 2 LONG open
    a = decide_basket_action(open_positions=pos, equity=10000.0, now=NOW, opened_at=NOW,
                             signal_decision="LONG", signal_confidence=100, min_confidence=50, cfg=cfg)
    assert a.kind == "add" and a.num_positions == 6                          # target 8 - 2 open


def test_no_scale_in_when_disabled():
    cfg = BasketConfig(num_positions=2, max_positions=8, scale_in=False)
    pos = [{"profit": 1.0, "side": "buy"}]
    a = decide_basket_action(open_positions=pos, equity=10000.0, now=NOW, opened_at=NOW,
                             signal_decision="LONG", signal_confidence=100, min_confidence=50, cfg=cfg)
    assert a.kind == "hold"


def test_open_when_flat_and_signal():
    a = decide_basket_action(open_positions=[], equity=10000.0, now=NOW, opened_at=None,
                             signal_decision="LONG", signal_confidence=70, min_confidence=50, cfg=CFG)
    assert a.kind == "open" and a.direction == "LONG" and a.num_positions == 5


def test_no_open_when_signal_below_min_or_no_trade():
    assert decide_basket_action(open_positions=[], equity=10000.0, now=NOW, opened_at=None,
                                signal_decision="LONG", signal_confidence=40, min_confidence=50,
                                cfg=CFG).kind == "none"
    assert decide_basket_action(open_positions=[], equity=10000.0, now=NOW, opened_at=None,
                                signal_decision="NO_TRADE", signal_confidence=0, min_confidence=50,
                                cfg=CFG).kind == "none"


def test_cooldown_blocks_open():
    a = decide_basket_action(open_positions=[], equity=10000.0, now=NOW, opened_at=None,
                             signal_decision="LONG", signal_confidence=90, min_confidence=50,
                             cfg=CFG, in_cooldown=True)
    assert a.kind == "none" and "cooldown" in a.reason


def test_hold_when_open_within_thresholds():
    pos = [{"profit": 1.0}, {"profit": -0.5}]   # +0.5 total, far from +60 target / -150 cap
    a = decide_basket_action(open_positions=pos, equity=10000.0, now=NOW, opened_at=NOW,
                             signal_decision="LONG", signal_confidence=90, min_confidence=50, cfg=CFG)
    assert a.kind == "hold"


def test_close_all_on_profit_target():
    pos = [{"profit": 40.0}, {"profit": 25.0}]   # +65 >= 0.6% of 10000 = 60
    a = decide_basket_action(open_positions=pos, equity=10000.0, now=NOW, opened_at=NOW,
                             signal_decision="LONG", signal_confidence=90, min_confidence=50, cfg=CFG)
    assert a.kind == "close_all" and a.reason == CLOSE_PROFIT_TARGET


def test_close_all_on_hard_loss_cap():
    pos = [{"profit": -100.0}, {"profit": -60.0}]   # -160 <= -1.5% of 10000 = -150
    a = decide_basket_action(open_positions=pos, equity=10000.0, now=NOW, opened_at=NOW,
                             signal_decision="LONG", signal_confidence=90, min_confidence=50, cfg=CFG)
    assert a.kind == "close_all" and a.reason == CLOSE_HARD_LOSS


def test_close_all_on_time_stop():
    pos = [{"profit": 1.0}]
    a = decide_basket_action(open_positions=pos, equity=10000.0, now=NOW,
                             opened_at=NOW - timedelta(seconds=61),
                             signal_decision="LONG", signal_confidence=90, min_confidence=50, cfg=CFG)
    assert a.kind == "close_all" and a.reason == CLOSE_TIME_STOP


# ── LM101A pressure proxy + adaptive exits ───────────────────────────────────────
def test_price_action_pressure_sign():
    rising = [{"open": i - 1, "high": i + 0.5, "low": i - 1.5, "close": float(i)}
              for i in range(100, 110)]
    falling = [{"open": i + 1, "high": i + 1.5, "low": i - 0.5, "close": float(i)}
               for i in range(110, 100, -1)]
    assert price_action_pressure(rising, 0.01) > 0      # buyers
    assert price_action_pressure(falling, 0.01) < 0     # sellers
    assert price_action_pressure([], 0.01) == 0.0


def test_basket_side():
    assert basket_side([{"side": "buy"}, {"side": "buy"}]) == "LONG"
    assert basket_side([{"side": "sell"}]) == "SHORT"
    assert basket_side([{"side": "buy"}, {"side": "sell"}]) == "MIXED"


def test_profit_lock_arms_and_closes_on_retrace():
    cfg = BasketConfig(lock_arm_pct=0.4, lock_floor_frac=0.0)   # arm at +40, floor break-even
    pos = [{"profit": -1.0, "side": "buy"}]                     # retraced to red
    a = decide_basket_action(open_positions=pos, equity=10000.0, now=NOW, opened_at=NOW,
                             signal_decision="LONG", signal_confidence=90, min_confidence=50,
                             cfg=cfg, peak_profit=50.0)          # peaked at +50 → armed
    assert a.kind == "close_all" and a.reason == CLOSE_PROFIT_LOCK


def test_profit_lock_holds_above_floor():
    cfg = BasketConfig(lock_arm_pct=0.4, lock_floor_frac=0.1)   # floor = 10% of peak
    pos = [{"profit": 30.0, "side": "buy"}]                     # peak 100 → floor 10; 30 > 10
    a = decide_basket_action(open_positions=pos, equity=10000.0, now=NOW, opened_at=NOW,
                             signal_decision="LONG", signal_confidence=90, min_confidence=50,
                             cfg=cfg, peak_profit=100.0)
    assert a.kind == "hold"


def test_pressure_flip_closes_when_in_profit_and_opposed():
    cfg = BasketConfig(pressure_close=True, pressure_min_profit_pct=0.1,
                       pressure_threshold_points=100.0, pressure_confirm_bars=3)
    pos = [{"profit": 20.0, "side": "buy"}]                     # LONG, +20 (>= 0.1% of 10000=10)
    a = decide_basket_action(open_positions=pos, equity=10000.0, now=NOW, opened_at=NOW,
                             signal_decision="LONG", signal_confidence=90, min_confidence=50,
                             cfg=cfg, pressure=-150.0, pressure_against_streak=3)
    assert a.kind == "close_all" and a.reason == CLOSE_PRESSURE_FLIP


def test_engine_reversal_closes_on_strong_opposite_signal():
    cfg = BasketConfig(reversal_close=True, reversal_confidence=70.0)
    pos = [{"profit": 5.0, "side": "buy"}]                      # LONG basket
    a = decide_basket_action(open_positions=pos, equity=10000.0, now=NOW, opened_at=NOW,
                             signal_decision="SHORT", signal_confidence=85, min_confidence=50, cfg=cfg)
    assert a.kind == "close_all" and a.reason == CLOSE_ENGINE_REVERSAL


def test_engine_reversal_ignores_weak_or_same_direction():
    cfg = BasketConfig(reversal_close=True, reversal_confidence=70.0)
    pos = [{"profit": 5.0, "side": "buy"}]
    weak = decide_basket_action(open_positions=pos, equity=10000.0, now=NOW, opened_at=NOW,
                                signal_decision="SHORT", signal_confidence=60, min_confidence=50, cfg=cfg)
    assert weak.kind == "hold"                                  # 60 < 70
    same = decide_basket_action(open_positions=pos, equity=10000.0, now=NOW, opened_at=NOW,
                                signal_decision="LONG", signal_confidence=95, min_confidence=50, cfg=cfg)
    assert same.kind == "hold"                                  # same direction → not a reversal


def test_engine_reversal_disabled():
    cfg = BasketConfig(reversal_close=False, reversal_confidence=70.0)
    pos = [{"profit": 5.0, "side": "buy"}]
    a = decide_basket_action(open_positions=pos, equity=10000.0, now=NOW, opened_at=NOW,
                             signal_decision="SHORT", signal_confidence=95, min_confidence=50, cfg=cfg)
    assert a.kind == "hold"


def test_pressure_flip_debounced_until_confirmed():
    # Opposing pressure + in profit, but streak below confirm_bars → HOLD (no twitch).
    cfg = BasketConfig(pressure_close=True, pressure_min_profit_pct=0.1,
                       pressure_threshold_points=100.0, pressure_confirm_bars=3)
    pos = [{"profit": 20.0, "side": "buy"}]
    held = decide_basket_action(open_positions=pos, equity=10000.0, now=NOW, opened_at=NOW,
                                signal_decision="LONG", signal_confidence=90, min_confidence=50,
                                cfg=cfg, pressure=-150.0, pressure_against_streak=2)
    assert held.kind == "hold"
    closed = decide_basket_action(open_positions=pos, equity=10000.0, now=NOW, opened_at=NOW,
                                  signal_decision="LONG", signal_confidence=90, min_confidence=50,
                                  cfg=cfg, pressure=-150.0, pressure_against_streak=3)
    assert closed.kind == "close_all" and closed.reason == CLOSE_PRESSURE_FLIP


def test_pressure_flip_ignored_when_confirming_or_flat_profit():
    cfg = BasketConfig(pressure_close=True, pressure_min_profit_pct=0.1,
                       pressure_threshold_points=100.0)
    # buy pressure confirms a LONG → no close
    confirm = decide_basket_action(open_positions=[{"profit": 20.0, "side": "buy"}], equity=10000.0,
                                   now=NOW, opened_at=NOW, signal_decision="LONG",
                                   signal_confidence=90, min_confidence=50, cfg=cfg, pressure=150.0)
    assert confirm.kind == "hold"
    # opposing pressure but barely in profit (< min) → no pressure close
    tiny = decide_basket_action(open_positions=[{"profit": 2.0, "side": "buy"}], equity=10000.0,
                                now=NOW, opened_at=NOW, signal_decision="LONG", signal_confidence=90,
                                min_confidence=50, cfg=cfg, pressure=-300.0)
    assert tiny.kind == "hold"


# ── faked connector for worker basket tests ─────────────────────────────────────
class _Ret:
    def __init__(self, retcode=10009):
        self.retcode = retcode


class _Mt5:
    TRADE_RETCODE_DONE = 10009


class _Pos:
    def __init__(self, ticket, ptype=0, profit=0.0, volume=0.02, symbol="XAUUSD"):
        self.ticket = ticket
        self.type = ptype
        self.profit = profit
        self.volume = volume
        self.symbol = symbol
        self.price_open = 2378.0
        self.price_current = 2378.0
        self.sl = 2375.0
        self.tp = 2381.0
        self.magic = 810810
        self.comment = "lumora-gold-bot-basket"


class FakeBasketConnector:
    """Rising candles → LONG. Tracks a mutable list of open positions; sends append,
    closes remove. estimate_sl_loss is flat (small) so the risk gate approves."""

    def __init__(self, *, demo=True, positions=None, new_profit=0.0, deals=None,
                 profit_schedule=None, candles=None, sl_loss=5.0):
        self.demo_verified = demo
        self._sl_loss = sl_loss
        self._positions: list[_Pos] = list(positions or [])
        self._mt5 = _Mt5()
        self.sent_orders: list[dict] = []
        self.closed_tickets: list[int] = []
        self._next_ticket = 1000
        self._new_profit = new_profit
        self._deals = list(deals or [])
        self._profit_schedule = list(profit_schedule) if profit_schedule else None
        self._pf_calls = 0
        self._candles = candles
        self.deal_history_calls = 0
        self.shutdown_called = False

    def deal_history(self, from_time, to_time):
        self.deal_history_calls += 1
        return list(self._deals)

    @staticmethod
    def _rising(n=40, start=2300.0, step=2.0):
        return [{"time": "2026-06-16T13:00:00+00:00", "open": (start + i * step) - 1,
                 "high": (start + i * step) + 0.5, "low": (start + i * step) - 1.5,
                 "close": start + i * step} for i in range(n)]

    def connect(self):
        pass

    def shutdown(self):
        self.shutdown_called = True

    def read_account(self, probe):
        probe.account_login = 108411849
        probe.account_server = "MetaQuotes-Demo"
        probe.trade_mode_label = "demo" if self.demo_verified else "real"

    def discover_gold_symbol(self, probe, preferred=None):
        return preferred or "XAUUSD"

    def read_tick(self, probe, symbol):
        probe.tick_bid = 2378.10
        probe.tick_ask = 2378.22
        probe.tick_spread = 0.12

    def symbol_metadata(self, symbol):
        return {"point": 0.01, "volume_min": 0.01, "volume_step": 0.01, "volume_max": 100.0}

    def recent_candles(self, symbol, timeframe, bars):
        return self._candles if self._candles is not None else self._rising()

    def positions_for_symbol(self, symbol):
        if self._profit_schedule and self._positions:
            idx = min(self._pf_calls, len(self._profit_schedule) - 1)
            for p in self._positions:
                p.profit = self._profit_schedule[idx]
            self._pf_calls += 1
        return list(self._positions)

    def position_view(self, position):
        return {"ticket": position.ticket, "symbol": position.symbol,
                "side": "buy" if position.type == 0 else "sell", "volume": position.volume,
                "profit": position.profit, "magic": position.magic}

    def position_by_ticket(self, ticket):
        return next((p for p in self._positions if p.ticket == ticket), None)

    def read_history_report(self, probe, symbol=None):
        probe.history_windows = [{"label": "today", "profit_sum": 0.0}]

    def compute_levels(self, symbol, side, sl_points, tp_points):
        return {"order_type": 0, "price": 2378.22, "sl": 2375.22}

    def account_snapshot(self):
        return {"equity": 10000.0, "margin_free": 9000.0}

    def estimate_sl_loss(self, *, order_type, symbol, volume, entry, sl):
        return self._sl_loss

    def calc_margin(self, *, order_type, symbol, volume, price):
        return 50.0

    def build_demo_order_request(self, **kw):
        return dict(kw)

    def check_order(self, request):
        return _Ret(10009)

    def send_demo_order(self, request):
        self.sent_orders.append(request)
        self._positions.append(_Pos(self._next_ticket, profit=self._new_profit))
        self._next_ticket += 1
        return _Ret(10009)

    def build_close_request(self, position):
        return {"position": position.ticket}

    def send_demo_close(self, request):
        tkt = request["position"]
        self._positions = [p for p in self._positions if p.ticket != tkt]
        self.closed_tickets.append(tkt)
        return _Ret(10009)


def _worker(cfg, conn, tmp_path):
    return GoldBotWorker(
        cfg, connector=conn, safety=SafetyConfig(),
        journal_path=tmp_path / "j.jsonl", status_path=tmp_path / "s.json",
        safety_state_path=tmp_path / "ss.json", safety_events_path=tmp_path / "se.jsonl",
        sleep_fn=lambda s: None, now_fn=lambda: NOW, printer=lambda *_a: None)


def _basket_cfg(**kw):
    base = dict(risk_mode="scalp", max_iterations=1, interval_seconds=0, basket_scalp=True,
                basket_num_positions=5, basket_risk_cap_pct=3.0, basket_profit_target_pct=0.6,
                basket_hard_loss_cap_pct=1.5, basket_time_stop_seconds=60.0)
    base.update(kw)
    return WorkerConfig(**base)


# ── worker basket behavior ───────────────────────────────────────────────────────
def test_basket_observe_simulates_no_orders(tmp_path):
    conn = FakeBasketConnector()
    w = _worker(_basket_cfg(mode="observe"), conn, tmp_path)
    w.run()
    assert conn.sent_orders == []
    b = w.iterations[0]["basket"]
    assert b["action"] == "open" and b["planned_count"] == 5 and b["opened_count"] == 0
    assert w.iterations[0]["execution_status"] == "simulated_basket_open"
    assert w.iterations[0]["order_sent"] is False


def test_basket_demo_opens_five_legs(tmp_path):
    conn = FakeBasketConnector()
    w = _worker(_basket_cfg(mode="demo", auto_execute_demo=True, confirm_demo_order=True), conn, tmp_path)
    w.run()
    assert len(conn.sent_orders) == 5
    b = w.iterations[0]["basket"]
    assert b["action"] == "open" and b["opened_count"] == 5
    assert w._basket_opened_at == NOW


def test_basket_closes_all_on_profit(tmp_path):
    # Pre-load 5 winning legs: +65 total >= 0.6% of 10000 = 60 → close all.
    pos = [_Pos(500 + i, profit=13.0) for i in range(5)]
    conn = FakeBasketConnector(positions=pos)
    w = _worker(_basket_cfg(mode="demo", auto_execute_demo=True, confirm_demo_order=True), conn, tmp_path)
    w.run()
    assert len(conn.closed_tickets) == 5
    b = w.iterations[0]["basket"]
    assert b["action"] == "close_all" and b["closed_count"] == 5
    assert w.iterations[0]["execution_status"].startswith("basket_closed:profit_target")


def test_basket_hard_loss_closes_and_sets_cooldown(tmp_path):
    # -160 total <= -1.5% of 10000 = -150 → force close + cooldown.
    pos = [_Pos(600 + i, profit=-32.0) for i in range(5)]
    conn = FakeBasketConnector(positions=pos)
    w = _worker(_basket_cfg(mode="demo", auto_execute_demo=True, confirm_demo_order=True,
                            basket_cooldown_seconds_after_loss=90.0), conn, tmp_path)
    w.run()
    assert len(conn.closed_tickets) == 5
    assert w.iterations[0]["execution_status"].startswith("basket_closed:hard_loss_cap")
    assert w._basket_cooldown_until == NOW + timedelta(seconds=90.0)


def test_basket_entry_strategy_gate_blocks(tmp_path):
    # Gate to a strategy the signal won't be → entry filtered, no orders.
    conn = FakeBasketConnector()
    w = _worker(_basket_cfg(mode="demo", auto_execute_demo=True, confirm_demo_order=True,
                            basket_entry_strategy="no_such_strategy"), conn, tmp_path)
    w.run()
    assert conn.sent_orders == []
    assert w.iterations[0]["execution_status"] == "basket_entry_filtered"


def test_basket_max_confidence_gate_blocks(tmp_path):
    # Confidence ceiling of 1 → every signal is >= 1 → filtered.
    conn = FakeBasketConnector()
    w = _worker(_basket_cfg(mode="demo", auto_execute_demo=True, confirm_demo_order=True,
                            basket_max_confidence=1.0), conn, tmp_path)
    w.run()
    assert conn.sent_orders == []
    assert w.iterations[0]["execution_status"] == "basket_entry_filtered"


def test_basket_leg_sltp_override_applied(tmp_path):
    # Wide leg SL/TP override should appear on the sent order (time-exit setup).
    conn = FakeBasketConnector()
    w = _worker(_basket_cfg(mode="demo", auto_execute_demo=True, confirm_demo_order=True,
                            basket_leg_sl_points=1000, basket_leg_tp_points=2000), conn, tmp_path)
    w.run()
    assert len(conn.sent_orders) >= 1
    assert conn.sent_orders[0]["sl_points"] == 1000
    assert conn.sent_orders[0]["tp_points"] == 2000


def test_basket_open_failed_surfaces_leg_reason(tmp_path):
    # Huge per-leg SL loss → risk gate blocks every leg → status names the reason.
    conn = FakeBasketConnector(sl_loss=1_000_000.0)
    w = _worker(_basket_cfg(mode="demo", auto_execute_demo=True, confirm_demo_order=True), conn, tmp_path)
    w.run()
    assert conn.sent_orders == []
    assert w.iterations[0]["execution_status"] == "basket_open_failed:risk_blocked"


def test_basket_risk_cap_blocks_when_leg_too_big(tmp_path):
    # Cap 0.04% of 10000 = 4; one leg risks ~10 (scalp 0.10%) → 0 legs allowed.
    conn = FakeBasketConnector()
    w = _worker(_basket_cfg(mode="demo", auto_execute_demo=True, confirm_demo_order=True,
                            basket_risk_cap_pct=0.04), conn, tmp_path)
    w.run()
    assert conn.sent_orders == []
    assert w.iterations[0]["execution_status"] == "basket_risk_cap_blocked"


def test_basket_default_off_uses_normal_path(tmp_path):
    # Without basket_scalp the iteration has no 'basket' block (normal path).
    conn = FakeBasketConnector()
    w = _worker(WorkerConfig(mode="observe", risk_mode="scalp", max_iterations=1, interval_seconds=0),
                conn, tmp_path)
    w.run()
    assert "basket" not in w.iterations[0]


# ── LM89 outcome sync wiring (demo-only, read-only history) ──────────────────────
class _Deal:
    def __init__(self, *, position_id, ptype, entry, price, profit=0.0, comment="",
                 magic=810810, symbol="XAUUSD", volume=0.02, ts=1_700_000_000):
        self.position_id = position_id
        self.order = position_id
        self.ticket = position_id * 10 + entry
        self.type = ptype
        self.entry = entry
        self.price = price
        self.profit = profit
        self.comment = comment
        self.magic = magic
        self.symbol = symbol
        self.volume = volume
        self.time = ts
        self.sl = 0.0
        self.tp = 0.0
        self.commission = 0.0
        self.swap = 0.0


def _falling(n=40, start=2400.0, step=2.0):
    return [{"time": "2026-06-16T13:00:00+00:00", "open": (start - i * step) + 1,
             "high": (start - i * step) + 1.5, "low": (start - i * step) - 0.5,
             "close": start - i * step} for i in range(n)]


def test_basket_pressure_close_debounced_then_fires_worker(tmp_path):
    # LONG in profit, sustained sell pressure (falling candles). confirm_bars=3:
    # iter1/2 hold (streak 1/2), iter3 confirmed → pressure close. No twitch.
    pos = [_Pos(800, ptype=0, profit=20.0)]
    conn = FakeBasketConnector(positions=pos, profit_schedule=[20.0, 20.0, 20.0],
                               candles=_falling())
    # Disable the engine-reversal exit so this isolates the pressure debounce path
    # (falling candles would otherwise trigger an engine SHORT reversal first).
    w = _worker(_basket_cfg(mode="demo", auto_execute_demo=True, confirm_demo_order=True,
                            max_iterations=3, basket_pressure_confirm_bars=3,
                            basket_lock_arm_pct=0.0, basket_reversal_close=False), conn, tmp_path)
    w.run()
    assert w.iterations[0]["basket"]["action"] == "hold"
    assert w.iterations[1]["basket"]["action"] == "hold"
    assert w.iterations[2]["basket"]["reason"] == "pressure_flip"
    assert len(conn.closed_tickets) == 1


def test_basket_scale_in_adds_legs_worker(tmp_path):
    # 2 LONG legs open + rising candles (engine LONG, high conf) + scale_in → ADD.
    pos = [_Pos(900, ptype=0, profit=0.0), _Pos(901, ptype=0, profit=0.0)]
    conn = FakeBasketConnector(positions=pos)
    w = _worker(_basket_cfg(mode="demo", auto_execute_demo=True, confirm_demo_order=True,
                            max_iterations=1, basket_num_positions=2, basket_max_positions=6,
                            basket_scale_in=True), conn, tmp_path)
    w.run()
    e = w.iterations[0]
    assert e["basket"]["action"] == "add"
    assert e["execution_status"] == "basket_added"
    assert len(conn.sent_orders) >= 1


def test_basket_engine_reversal_closes_worker(tmp_path):
    # LONG basket open, falling candles → engine emits strong SHORT → reversal close.
    pos = [_Pos(820, ptype=0, profit=5.0)]
    conn = FakeBasketConnector(positions=pos, profit_schedule=[5.0], candles=_falling())
    w = _worker(_basket_cfg(mode="demo", auto_execute_demo=True, confirm_demo_order=True,
                            max_iterations=1, basket_lock_arm_pct=0.0), conn, tmp_path)
    w.run()
    e = w.iterations[0]
    assert e["decision"] == "SHORT"                       # engine flipped vs the LONG basket
    assert e["basket"]["reason"] == "engine_reversal"
    assert len(conn.closed_tickets) == 1


def test_basket_profit_lock_closes_on_retrace_worker(tmp_path):
    # iter1 peaks at +50 (arms lock), iter2 retraces to red → trailing lock closes all.
    pos = [_Pos(700, profit=50.0)]
    conn = FakeBasketConnector(positions=pos, profit_schedule=[50.0, -1.0])
    w = _worker(_basket_cfg(mode="demo", auto_execute_demo=True, confirm_demo_order=True,
                            max_iterations=2), conn, tmp_path)
    w.run()
    assert w.iterations[0]["basket"]["action"] == "hold"
    assert w.iterations[1]["basket"]["reason"] == "profit_lock"
    assert len(conn.closed_tickets) == 1
    assert w.iterations[1]["execution_status"].startswith("basket_closed:profit_lock")


def test_decision_context_join_attaches_confidence(tmp_path):
    import json
    from services.gold_bot_trade_outcomes import load_decision_context, reconstruct_outcomes
    ctx = tmp_path / "dc.jsonl"
    ctx.write_text(json.dumps({"position_id": 900, "confidence": 82, "setup": "fvg_retest",
                               "side": "SHORT", "risk_mode": "scalp"}) + "\n", encoding="utf-8")
    enrich = load_decision_context(ctx)
    assert enrich[900]["confidence"] == 82
    deals = [_Deal(position_id=900, ptype=1, entry=0, price=4300.0),                  # SELL entry
             _Deal(position_id=900, ptype=0, entry=1, price=4310.0, profit=-20.0,     # close (loss)
                   comment="[sl]")]
    outs = reconstruct_outcomes(deals, symbol="XAUUSD", magic=810810, enrich=enrich)
    assert len(outs) == 1
    assert outs[0].confidence == 82            # confidence joined onto the closed trade
    assert outs[0].setup == "fvg_retest"


def _loss_deals(n=3):
    deals = []
    for i in range(n):
        pid = 500 + i
        deals += [_Deal(position_id=pid, ptype=1, entry=0, price=4300.0),                 # SELL entry
                  _Deal(position_id=pid, ptype=0, entry=1, price=4310.0, profit=-20.0,     # BUY close (loss)
                        comment="[sl]")]
    return deals


def test_periodic_sync_does_not_inflate_loss_streak(tmp_path):
    # Repeated history sync must NOT re-feed the same losses into the live
    # supervisor (that froze trading via an ever-extending loss-streak cooldown).
    conn = FakeBasketConnector(deals=_loss_deals(3))
    cfg = _basket_cfg(mode="observe", sync_outcomes_every=1, max_iterations=3)
    cfg.outcomes_dir = str(tmp_path / "o")
    cfg.outcomes_learning_dir = str(tmp_path / "l")
    w = _worker(cfg, conn, tmp_path)
    w.run()
    assert conn.deal_history_calls >= 1
    assert all(e["safety"].get("cooldown_until") is None for e in w.iterations)


def test_outcome_sync_off_by_default_no_history_read(tmp_path):
    conn = FakeBasketConnector()
    w = _worker(_basket_cfg(mode="observe"), conn, tmp_path)
    w.run()
    assert conn.deal_history_calls == 0          # sync_outcomes_every default 0 → never reads


def test_outcome_sync_records_demo_outcomes(tmp_path):
    # One closed SELL position in history → reconstructed + written to the learning feed.
    deals = [
        _Deal(position_id=900, ptype=1, entry=0, price=4335.0),               # SELL entry
        _Deal(position_id=900, ptype=0, entry=1, price=4330.0, profit=10.0,   # BUY close (win)
              comment="[tp 4330]"),
    ]
    conn = FakeBasketConnector(deals=deals)
    out_dir = tmp_path / "outcomes"
    learn_dir = tmp_path / "learning"
    cfg = _basket_cfg(mode="observe", sync_outcomes_every=1)
    cfg.outcomes_dir = str(out_dir)
    cfg.outcomes_learning_dir = str(learn_dir)
    w = _worker(cfg, conn, tmp_path)
    w.run()
    assert conn.deal_history_calls >= 1
    assert (out_dir / "outcomes_latest.json").exists()
    assert (learn_dir / "learning_events.jsonl").exists()
