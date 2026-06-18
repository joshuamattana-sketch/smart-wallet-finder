"""
tests/test_gold_bot_worker.py
------------------------------
LM81A — Worker loop tests with a fully faked MT5 connector. No real terminal,
no network, no orders. Verifies safety posture, looping, journaling and the
guarded execution gate.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

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

    def __init__(self, *, demo=True, open_positions=0, candles=None, send_retcode=10009, margin=50.0):
        self.demo_verified = demo
        self._open = open_positions
        self._candles = candles or self._rising()
        self._mt5 = _Mt5()
        self.sent_orders: list[dict] = []
        self.shutdown_called = False
        self._send_retcode = send_retcode
        self._margin = margin

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
        return self._margin

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
        safety_state_path=tmp_path / "safety_state.json",
        safety_events_path=tmp_path / "safety_events.jsonl",
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


def test_demo_fails_closed_when_account_read_fails(tmp_path):
    # Fail closed: if the account snapshot raises (equity unreadable), the worker
    # must NOT mask it as equity 0.0 and size on a zeroed budget — it must skip
    # execution and send nothing.
    conn = FakeConnector()

    def _raise():
        raise RuntimeError("terminal disconnected")

    conn.account_snapshot = _raise
    cfg = WorkerConfig(mode="demo", risk_mode="scalp", max_iterations=1, interval_seconds=0,
                       auto_execute_demo=True, confirm_demo_order=True)
    w = _worker(cfg, conn, tmp_path)
    w.run()
    assert conn.sent_orders == []
    assert w.iterations[0]["execution_status"] == "account_unavailable"
    assert w.iterations[0]["order_sent"] is False


def test_kill_switch_blocks_demo_order(tmp_path):
    # Kill switch is now caught by the safety supervisor BEFORE the risk gate.
    conn = FakeConnector()
    cfg = WorkerConfig(mode="demo", max_iterations=1, interval_seconds=0,
                       auto_execute_demo=True, confirm_demo_order=True)
    w = _worker(cfg, conn, tmp_path, safety=SafetyConfig(kill_switch=True))
    w.run()
    assert conn.sent_orders == []
    e = w.iterations[0]
    assert e["execution_status"] == "blocked_by_safety_supervisor"
    assert e["safety"]["reason"] == "kill_switch"
    assert e["safety"]["severity"] == "critical"


def test_worker_journal_carries_safety_decision(tmp_path):
    conn = FakeConnector()
    w = _worker(WorkerConfig(max_iterations=1, interval_seconds=0), conn, tmp_path)
    w.run()
    sf = w.iterations[0]["safety"]
    assert sf["allowed"] is True and sf["severity"] == "info"     # observe, all clear
    assert "continue_observe" in sf["actions"]


def test_worker_config_exposes_safety_options(tmp_path):
    cfg = WorkerConfig(max_open_positions=2, max_trades_per_hour=10,
                       min_seconds_between_trades=60, max_consecutive_losses=5,
                       cooldown_minutes_after_loss_streak=15, max_spread_points=40.0)
    sc = cfg.supervisor_config()
    assert sc.max_open_positions == 2 and sc.max_trades_per_hour == 10
    assert sc.min_seconds_between_trades == 60 and sc.max_consecutive_losses == 5
    assert sc.cooldown_minutes_after_loss_streak == 15 and sc.max_spread_points == 40.0
    assert not hasattr(WorkerConfig(), "disable_safety_supervisor")   # no off switch


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
        safety_state_path=tmp_path / "safety_state.json",
        safety_events_path=tmp_path / "safety_events.jsonl",
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
        safety_state_path=tmp_path / "safety_state.json",
        safety_events_path=tmp_path / "safety_events.jsonl",
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


def _valid_modifier_file(tmp_path, *, mod=4, expires_at="2026-12-31T00:00:00+00:00"):
    """A demo modifier file that PASSES the LM87A safety contract."""
    import json as _json
    mf = tmp_path / "active_demo_modifiers.json"
    mods = {s: {"setup": s, "confidence_modifier": mod, "status": "active", "reason": "x"}
            for s in ("momentum", "scalp_momentum", "scalp_retest", "liquidity_sweep_reclaim")}
    mf.write_text(_json.dumps({"safety": "demo_only", "mode": "demo_auto_learning",
                               "expires_at": expires_at, "modifiers": mods}), encoding="utf-8")
    return mf


def test_worker_applies_learning_modifier_in_observe(tmp_path):
    conn = FakeConnector()
    mf = _valid_modifier_file(tmp_path)
    cfg = WorkerConfig(mode="observe", risk_mode="scalp", max_iterations=1, interval_seconds=0,
                       use_learning_modifiers=True, learning_modifiers_file=str(mf))
    w = _worker(cfg, conn, tmp_path)
    w.run()
    e = w.iterations[0]
    assert conn.sent_orders == []
    assert e["decision"] in ("LONG", "SHORT")
    assert e["learning"].get("learning_mode") == "observe"
    assert e["learning"]["learning_modifier"] == 4
    assert w._learning_safety["allowed"] is True


def test_worker_disables_learning_on_expired_contract(tmp_path):
    # Expired file → supervisor disables learning; worker keeps running, no modifier applied.
    conn = FakeConnector()
    mf = _valid_modifier_file(tmp_path, expires_at="2020-01-01T00:00:00+00:00")
    cfg = WorkerConfig(mode="observe", risk_mode="scalp", max_iterations=1, interval_seconds=0,
                       use_learning_modifiers=True, learning_modifiers_file=str(mf))
    w = _worker(cfg, conn, tmp_path)
    assert w.run() == 0
    assert w._learning_safety["allowed"] is False
    assert w._learning_modifiers == {}
    assert not w.iterations[0]["learning"]    # no modifier applied (empty dict)


# ── LM99A confidence-scaled lot (demo-only, default off) ───────────────────────
def test_confidence_scaled_lot_off_by_default(tmp_path):
    # Default off → the risk payload carries NO confidence-scaling fields.
    conn = FakeConnector()
    w = _worker(WorkerConfig(max_iterations=1, interval_seconds=0), conn, tmp_path)
    w.run()
    risk = w.iterations[0]["risk"]
    assert risk is not None                       # observe still sizes/risk-checks
    assert "confidence_risk_fraction" not in risk
    assert WorkerConfig().confidence_scaled_lot is False


def test_confidence_scaled_lot_surfaces_fraction_in_observe(tmp_path):
    # Enabled in observe → fraction recorded, within (floor, 1.0], still no orders.
    conn = FakeConnector()
    cfg = WorkerConfig(mode="observe", risk_mode="scalp", max_iterations=1, interval_seconds=0,
                       confidence_scaled_lot=True, lot_confidence_floor=0.5)
    w = _worker(cfg, conn, tmp_path)
    w.run()
    assert conn.sent_orders == []
    risk = w.iterations[0]["risk"]
    assert risk["confidence_scaled_lot"] is True
    assert 0.5 <= risk["confidence_risk_fraction"] <= 1.0


def test_hard_mode_raises_risk_pct(tmp_path):
    conn = FakeConnector()
    cfg = WorkerConfig(mode="demo", risk_mode="scalp", max_iterations=1, interval_seconds=0,
                       auto_execute_demo=True, confirm_demo_order=True,
                       hard_mode=True, hard_max_risk_pct=5.0)
    w = _worker(cfg, conn, tmp_path)
    w.run()
    assert w.iterations[0]["execution_status"] == "demo_order_sent"
    assert w.iterations[0]["risk"]["info"]["risk_pct"] == 5.0   # vs scalp default 0.10


def test_hard_mode_refused_outside_demo(tmp_path):
    conn = FakeConnector()
    cfg = WorkerConfig(mode="observe", environment="live", max_iterations=1, interval_seconds=0,
                       hard_mode=True)
    w = _worker(cfg, conn, tmp_path)
    assert w.run() == 2                # critical safety stop (hard mode is demo-only)
    assert w.iterations == []


def test_hard_mode_off_by_default(tmp_path):
    assert WorkerConfig().hard_mode is False


def test_session_summary_text_has_winrate_and_pnl(tmp_path):
    conn = FakeConnector()
    w = _worker(WorkerConfig(mode="demo", risk_mode="scalp"), conn, tmp_path)
    w._symbol = "XAUUSD"
    w._started_at = NOW
    w.iterations = [
        {"decision": "LONG", "order_sent": True, "execution_status": "demo_order_sent"},
        {"decision": "SHORT", "order_sent": False, "execution_status": "risk_blocked"},
        {"decision": "NO_TRADE", "order_sent": False, "execution_status": "no_trade"},
    ]
    txt = w._build_session_summary_text(
        {"synced": True, "wins": 3, "losses": 1, "breakeven": 0, "realized_pnl": 42.5})
    assert "winrate 75%" in txt
    assert "PnL 42.5" in txt
    assert "LONG 1 / SHORT 1 / NO_TRADE 1" in txt


def test_discord_summary_off_by_default():
    assert WorkerConfig().discord_session_summary is False


def test_discord_summary_skips_without_webhook(tmp_path, monkeypatch):
    # No webhook configured → no network, no exception (fail-soft).
    monkeypatch.delenv("LUMORA_GOLD_DISCORD_WEBHOOK_URL", raising=False)
    conn = FakeConnector()
    w = _worker(WorkerConfig(discord_session_summary=True), conn, tmp_path)
    w.iterations = []
    w._maybe_send_discord_summary({"synced": False})   # must not raise


def test_decision_context_recorded_on_send(tmp_path):
    import json
    conn = FakeConnector()
    ctx = tmp_path / "decision_context.jsonl"
    cfg = WorkerConfig(mode="demo", risk_mode="scalp", max_iterations=1, interval_seconds=0,
                       auto_execute_demo=True, confirm_demo_order=True,
                       decision_context_file=str(ctx))
    w = _worker(cfg, conn, tmp_path)
    w.run()
    assert w.iterations[0]["execution_status"] == "demo_order_sent"
    rows = [json.loads(ln) for ln in ctx.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert rows and rows[0]["position_id"] == 111            # FakeConnector send.order
    assert rows[0]["confidence"] == w.iterations[0]["confidence"]
    assert rows[0]["side"] == "LONG"


def test_reset_safety_state_clears_stale_cooldown(tmp_path):
    import json
    sp = tmp_path / "safety_state.json"
    future = (NOW + timedelta(hours=1)).isoformat()
    payload = {"recent_trades": [], "consecutive_losses": 3, "cooldown_until": future,
               "last_trade_at": None}

    # without reset → the stale cooldown blocks the order
    sp.write_text(json.dumps(payload), encoding="utf-8")
    blocked = _worker(WorkerConfig(mode="demo", risk_mode="scalp", max_iterations=1, interval_seconds=0,
                                   auto_execute_demo=True, confirm_demo_order=True), FakeConnector(), tmp_path)
    blocked.run()
    assert blocked.iterations[0]["safety"]["reason"] == "loss_streak_cooldown"

    # with reset → cooldown cleared, order sent
    sp.write_text(json.dumps(payload), encoding="utf-8")
    ok = _worker(WorkerConfig(mode="demo", risk_mode="scalp", max_iterations=1, interval_seconds=0,
                              auto_execute_demo=True, confirm_demo_order=True,
                              reset_safety_state=True), FakeConnector(), tmp_path)
    ok.run()
    assert ok.iterations[0]["execution_status"] == "demo_order_sent"


def test_min_confidence_floor_blocks_single_trade(tmp_path):
    # Floor above the signal confidence → single-trade path stands aside, no order.
    conn = FakeConnector()
    high = _worker(WorkerConfig(mode="demo", risk_mode="scalp", max_iterations=1, interval_seconds=0,
                                auto_execute_demo=True, confirm_demo_order=True,
                                min_confidence_floor=101.0), conn, tmp_path)
    high.run()
    assert conn.sent_orders == []
    assert high.iterations[0]["execution_status"] == "below_confidence_floor"
    # floor 0 (default) → trades as before
    conn2 = FakeConnector()
    low = _worker(WorkerConfig(mode="demo", risk_mode="scalp", max_iterations=1, interval_seconds=0,
                               auto_execute_demo=True, confirm_demo_order=True), conn2, tmp_path)
    low.run()
    assert low.iterations[0]["execution_status"] == "demo_order_sent"


def test_min_confidence_floor_feeds_basket_entry(tmp_path):
    conn = FakeConnector()
    w = _worker(WorkerConfig(risk_mode="scalp", basket_scalp=True, min_confidence_floor=80.0), conn, tmp_path)
    assert w._basket_entry_floor(50) == 80


def test_hard_mode_helpers(tmp_path):
    from services.gold_bot_risk_gate import MAX_MARGIN_PCT_PER_TRADE
    conn = FakeConnector()
    hard = _worker(WorkerConfig(hard_mode=True, hard_max_margin_pct=60.0,
                                basket_min_confidence=75.0, risk_mode="scalp"), conn, tmp_path)
    assert hard._max_margin_pct() == 60.0
    assert hard._basket_entry_floor(50) == 75            # user floor wins
    normal = _worker(WorkerConfig(risk_mode="scalp"), conn, tmp_path)
    assert normal._max_margin_pct() == MAX_MARGIN_PCT_PER_TRADE
    assert normal._basket_entry_floor(50) == 50          # no extra floor


def test_big_margin_blocks_normal_but_passes_in_hard_mode(tmp_path):
    # Margin 5000 vs free 9000: normal 10% allows 900 → blocked; hard 60% allows 5400 → ok.
    blocked = _worker(WorkerConfig(mode="demo", risk_mode="scalp", max_iterations=1, interval_seconds=0,
                                   auto_execute_demo=True, confirm_demo_order=True),
                      FakeConnector(margin=5000.0), tmp_path)
    blocked.run()
    assert blocked.iterations[0]["execution_status"] == "risk_blocked"

    conn = FakeConnector(margin=5000.0)
    hard = _worker(WorkerConfig(mode="demo", risk_mode="scalp", max_iterations=1, interval_seconds=0,
                                auto_execute_demo=True, confirm_demo_order=True,
                                hard_mode=True, hard_max_margin_pct=60.0), conn, tmp_path)
    hard.run()
    assert hard.iterations[0]["execution_status"] == "demo_order_sent"
    assert len(conn.sent_orders) == 1


def test_hard_basket_cap_warning_when_per_leg_exceeds_cap(tmp_path):
    conn = FakeConnector()
    # per-leg 5% > basket cap 3% → basket can never open; warning fires.
    bad = _worker(WorkerConfig(mode="demo", risk_mode="scalp", basket_scalp=True, hard_mode=True,
                               hard_max_risk_pct=5.0, basket_risk_cap_pct=3.0,
                               basket_num_positions=5), conn, tmp_path)
    msg = bad._hard_basket_cap_warning()
    assert msg is not None and "25" in msg          # suggests >= 5% x 5 legs
    # cap raised to fit → no warning
    ok = _worker(WorkerConfig(mode="demo", risk_mode="scalp", basket_scalp=True, hard_mode=True,
                              hard_max_risk_pct=5.0, basket_risk_cap_pct=25.0,
                              basket_num_positions=5), conn, tmp_path)
    assert ok._hard_basket_cap_warning() is None
    # not in hard+basket mode → no warning
    assert _worker(WorkerConfig(), conn, tmp_path)._hard_basket_cap_warning() is None


def test_confidence_scaled_lot_still_sends_demo_order(tmp_path):
    # The scaled-down sizing must not break the guarded demo send path.
    conn = FakeConnector()
    cfg = WorkerConfig(mode="demo", risk_mode="scalp", max_iterations=1, interval_seconds=0,
                       auto_execute_demo=True, confirm_demo_order=True,
                       confidence_scaled_lot=True, lot_confidence_floor=0.5)
    w = _worker(cfg, conn, tmp_path)
    w.run()
    assert len(conn.sent_orders) == 1
    e = w.iterations[0]
    assert e["execution_status"] == "demo_order_sent"
    assert e["risk"]["confidence_scaled_lot"] is True
