"""
tests/test_gold_bot_worker.py
------------------------------
LM81A — Worker loop tests with a fully faked MT5 connector. No real terminal,
no network, no orders. Verifies safety posture, looping, journaling and the
guarded execution gate.
"""

from __future__ import annotations

from datetime import datetime, timezone

from services.gold_bot_risk_gate import SafetyConfig
from services.gold_bot_worker import GoldBotWorker, WorkerConfig

NOW = datetime(2026, 6, 12, 13, 0, 0, tzinfo=timezone.utc)


# ── fakes ──────────────────────────────────────────────────────────────────────
class _Ret:
    def __init__(self, retcode=10009, order=111, deal=222):
        self.retcode = retcode
        self.order = order
        self.deal = deal


class _Mt5:
    TRADE_RETCODE_DONE = 10009


class FakeConnector:
    """Canned MT5 demo terminal. Rising candles → technical LONG by default."""

    def __init__(self, *, demo=True, open_positions=0, candles=None, send_retcode=10009):
        self.demo_verified = demo
        self._open = open_positions
        self._candles = candles or self._rising()
        self._mt5 = _Mt5()
        self.sent_orders: list[dict] = []
        self.shutdown_called = False
        self._send_retcode = send_retcode

    @staticmethod
    def _rising(n=40, start=2300.0, step=2.0):
        out = []
        for i in range(n):
            c = start + i * step
            out.append({"time": "2026-06-12T13:00:00+00:00",
                        "open": c - 1, "high": c + 0.5, "low": c - 1.5, "close": c})
        return out

    def connect(self):
        pass

    def shutdown(self):
        self.shutdown_called = True

    def read_account(self, probe):
        probe.account_login = 5000123
        probe.account_server = "Demo-Server"
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
        return self._candles

    def positions_for_symbol(self, symbol):
        return [object()] * self._open

    def read_history_report(self, probe, symbol=None):
        probe.history_windows = [{"label": "today", "profit_sum": 0.0}]

    # execution path
    def compute_levels(self, symbol, side, sl_points, tp_points):
        return {"order_type": 0, "price": 2378.22, "sl": 2375.22}

    def account_snapshot(self):
        return {"equity": 10000.0, "margin_free": 9000.0}

    def estimate_sl_loss(self, *, order_type, symbol, volume, entry, sl):
        return 5.0

    def calc_margin(self, *, order_type, symbol, volume, price):
        return 50.0

    def build_demo_order_request(self, **kw):
        return dict(kw)

    def check_order(self, request):
        return _Ret(retcode=10009)

    def send_demo_order(self, request):
        self.sent_orders.append(request)
        return _Ret(retcode=self._send_retcode)


def _worker(cfg, conn, tmp_path, safety=None):
    return GoldBotWorker(
        cfg, connector=conn, safety=safety or SafetyConfig(),
        journal_path=tmp_path / "worker_journal.jsonl",
        status_path=tmp_path / "worker_status.json",
        sleep_fn=lambda s: None, now_fn=lambda: NOW, printer=lambda *_a: None,
    )


def _lockout_macro_file(tmp_path):
    f = tmp_path / "events.json"
    f.write_text('{"source_mode":"sample","events":[{"name":"US CPI","type":"CPI",'
                 '"currency":"USD","impact":"high","minutes_from_now":20}]}', encoding="utf-8")
    return str(f)


# ── observe mode never sends ───────────────────────────────────────────────────
def test_observe_default_sends_nothing(tmp_path):
    conn = FakeConnector()
    w = _worker(WorkerConfig(max_iterations=3, interval_seconds=0), conn, tmp_path)
    assert w.run() == 0
    assert conn.sent_orders == []
    assert len(w.iterations) == 3
    assert w.iterations[0]["decision"] == "LONG"
    assert w.iterations[0]["execution_status"] == "simulated_opportunity"


def test_observe_ignores_execute_flags(tmp_path):
    conn = FakeConnector()
    cfg = WorkerConfig(mode="observe", max_iterations=1, interval_seconds=0,
                       auto_execute_demo=True, confirm_demo_order=True)
    w = _worker(cfg, conn, tmp_path)
    w.run()
    assert conn.sent_orders == []
    assert w.iterations[0]["execution_status"] == "simulated_opportunity"


# ── demo mode requires explicit flags ──────────────────────────────────────────
def test_demo_without_flags_blocks(tmp_path):
    conn = FakeConnector()
    cfg = WorkerConfig(mode="demo", max_iterations=1, interval_seconds=0)
    w = _worker(cfg, conn, tmp_path)
    w.run()
    assert conn.sent_orders == []
    assert w.iterations[0]["execution_status"] == "demo_blocked_missing_flags"


def test_demo_with_flags_sends_order(tmp_path):
    conn = FakeConnector()
    cfg = WorkerConfig(mode="demo", risk_mode="scalp", max_iterations=1, interval_seconds=0,
                       auto_execute_demo=True, confirm_demo_order=True)
    w = _worker(cfg, conn, tmp_path)
    w.run()
    assert len(conn.sent_orders) == 1
    assert w.iterations[0]["execution_status"] == "demo_order_sent"
    assert w.iterations[0]["order_sent"] is True


def test_kill_switch_blocks_demo_order(tmp_path):
    conn = FakeConnector()
    cfg = WorkerConfig(mode="demo", max_iterations=1, interval_seconds=0,
                       auto_execute_demo=True, confirm_demo_order=True)
    w = _worker(cfg, conn, tmp_path, safety=SafetyConfig(kill_switch=True))
    w.run()
    assert conn.sent_orders == []
    assert w.iterations[0]["execution_status"] == "risk_blocked"


# ── macro lockout blocks new trades ────────────────────────────────────────────
def test_macro_lockout_blocks_trade(tmp_path):
    conn = FakeConnector()
    cfg = WorkerConfig(mode="demo", max_iterations=1, interval_seconds=0,
                       auto_execute_demo=True, confirm_demo_order=True,
                       macro_events_file=_lockout_macro_file(tmp_path))
    w = _worker(cfg, conn, tmp_path)
    w.run()
    assert conn.sent_orders == []
    e = w.iterations[0]
    assert e["decision"] == "NO_TRADE"
    assert e["strategy"] == "macro_lockout"
    assert e["macro_event_state"] == "lockout"


# ── no position stacking ───────────────────────────────────────────────────────
def test_open_position_no_stack(tmp_path):
    conn = FakeConnector(open_positions=1)
    cfg = WorkerConfig(mode="demo", max_iterations=1, interval_seconds=0,
                       auto_execute_demo=True, confirm_demo_order=True)
    w = _worker(cfg, conn, tmp_path)
    w.run()
    assert conn.sent_orders == []
    e = w.iterations[0]
    assert e["decision"] == "NO_TRADE"
    assert e["open_positions"] == 1


# ── critical safety: non-demo account stops worker ─────────────────────────────
def test_non_demo_account_stops_fail_closed(tmp_path):
    conn = FakeConnector(demo=False)
    cfg = WorkerConfig(max_iterations=3, interval_seconds=0)
    w = _worker(cfg, conn, tmp_path)
    rc = w.run()
    assert rc == 2                       # critical safety stop exit code
    assert conn.sent_orders == []
    assert w.iterations == []            # never completed an iteration


def test_live_flag_refuses_to_start(tmp_path):
    conn = FakeConnector()
    cfg = WorkerConfig(max_iterations=1, interval_seconds=0)
    w = _worker(cfg, conn, tmp_path, safety=SafetyConfig(live_trading_enabled=True))
    assert w.run() == 2
    assert w.iterations == []


# ── journaling + status ────────────────────────────────────────────────────────
def test_journal_and_status_written(tmp_path):
    import json
    from services import gold_bot_trade_journal as journal
    conn = FakeConnector()
    jp = tmp_path / "worker_journal.jsonl"
    sp = tmp_path / "worker_status.json"
    w = GoldBotWorker(
        WorkerConfig(max_iterations=2, interval_seconds=0), connector=conn,
        safety=SafetyConfig(), journal_path=jp, status_path=sp,
        sleep_fn=lambda s: None, now_fn=lambda: NOW, printer=lambda *_a: None,
    )
    w.run()
    rows = journal.read_entries(jp)
    assert len(rows) == 2
    assert rows[0]["mode"] == "observe"
    status = json.loads(sp.read_text(encoding="utf-8"))
    assert status["worker_status"] == "stopped"
    assert status["last_decision"] == "LONG"


def test_max_iterations_respected(tmp_path):
    conn = FakeConnector()
    sleeps = []
    w = GoldBotWorker(
        WorkerConfig(max_iterations=4, interval_seconds=5), connector=conn,
        safety=SafetyConfig(), journal_path=tmp_path / "j.jsonl",
        status_path=tmp_path / "s.json",
        sleep_fn=lambda s: sleeps.append(s), now_fn=lambda: NOW, printer=lambda *_a: None,
    )
    w.run()
    assert len(w.iterations) == 4
    # sleeps happen between iterations, not after the last one.
    assert len(sleeps) == 3


# ── learning modifiers (LM86B, demo-only) ──────────────────────────────────────
def test_worker_accepts_learning_flags_observe_no_orders(tmp_path):
    # Missing modifier file → warning, no crash; observe still sends nothing.
    conn = FakeConnector()
    cfg = WorkerConfig(mode="observe", max_iterations=1, interval_seconds=0,
                       use_learning_modifiers=True,
                       learning_modifiers_file=str(tmp_path / "nope.json"))
    w = _worker(cfg, conn, tmp_path)
    assert w.run() == 0
    assert conn.sent_orders == []
    assert w.iterations[0]["decision"] == "LONG"


def test_worker_applies_learning_modifier_in_observe(tmp_path):
    import json as _json
    conn = FakeConnector()
    mf = tmp_path / "active_demo_modifiers.json"
    mods = {s: {"confidence_modifier": 4, "status": "active", "reason": "x"}
            for s in ("momentum", "scalp_momentum", "scalp_retest", "liquidity_sweep_reclaim")}
    mf.write_text(_json.dumps({"modifiers": mods}), encoding="utf-8")
    cfg = WorkerConfig(mode="observe", risk_mode="scalp", max_iterations=1, interval_seconds=0,
                       use_learning_modifiers=True, learning_modifiers_file=str(mf))
    w = _worker(cfg, conn, tmp_path)
    w.run()
    e = w.iterations[0]
    assert conn.sent_orders == []
    assert e["decision"] in ("LONG", "SHORT")
    assert e["learning"].get("learning_mode") == "observe"
    assert e["learning"]["learning_modifier"] == 4
