"""
services/gold_bot_worker.py
----------------------------
LM81A — Long-running Gold Bot worker loop (MT5 DEMO ONLY).

Turns the one-shot decision probe (LM76/LM77) into a continuous loop. Each
iteration reads the MT5 demo terminal, builds the macro/news context, runs the
Decision Engine V2 and journals a compact result. It is OBSERVE / dry-run by
default and SENDS NOTHING. A demo order is only ever attempted when ALL of:

    * --mode demo
    * --auto-execute-demo
    * --confirm-demo-order
    * account is a verified DEMO account
    * the LM75 risk gate approves
    * no macro lockout, no open XAUUSD position (no stacking)
    * kill switch / live flags are off

Critical safety problems (non-demo account, live-trading flags, MT5 unavailable
for repeated iterations) STOP the worker fail-closed. Ordinary per-iteration
errors are logged and the loop continues.

This module imports no MetaTrader5 at module load (the connector lazy-imports it
at connect()), so it stays test-friendly: a fake connector can be injected.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from services.connectors.mt5_demo_connector import (
    Mt5ConnectorError,
    Mt5DemoConnector,
    ProbeResult,
)
from services.gold_bot_decision_engine import decide
from services.gold_bot_lot_calculator import calc_auto_volume, resolve_risk_pct
from services.gold_bot_macro_context import build_macro_context, load_calendar_or_macro
from services.gold_bot_risk_gate import SafetyConfig, evaluate_risk_plan
from services import gold_bot_trade_journal as journal

_REPO_ROOT = Path(__file__).resolve().parent.parent
WORKER_JOURNAL_PATH = _REPO_ROOT / "data" / "gold_bot" / "worker_journal.jsonl"
WORKER_STATUS_PATH = _REPO_ROOT / "data" / "gold_bot" / "worker_status.json"

WORKER_MAGIC = 810_810
DEFAULT_INTERVAL_SECONDS = 10.0
MAX_CONSECUTIVE_FAILURES = 5


class CriticalSafetyError(Exception):
    """Raised when the worker must stop fail-closed (never recoverable in-loop)."""


@dataclass
class WorkerConfig:
    mode: str = "observe"                 # observe | demo
    risk_mode: str = "balanced"
    interval_seconds: float = DEFAULT_INTERVAL_SECONDS
    max_iterations: int | None = None
    symbol: str | None = None             # None → auto-discover
    timeframe: str = "M1"
    bars: int = 120
    calendar_file: str | None = None
    macro_events_file: str | None = None
    dxy_bias: str = "unknown"
    yields_bias: str = "unknown"
    geopolitical_risk: str = "unknown"
    auto_execute_demo: bool = False
    confirm_demo_order: bool = False
    close_on_no_trade: bool = False       # placeholder in V1 (see _run_iteration)
    use_learning_modifiers: bool = False  # LM86B demo-only confidence learning (default off)
    learning_modifiers_file: str | None = None
    json_output: bool = False
    write_status: bool = True


class GoldBotWorker:
    """The loop. Inject `connector` / `sleep_fn` / `now_fn` for tests."""

    def __init__(
        self,
        cfg: WorkerConfig,
        *,
        safety: SafetyConfig | None = None,
        connector: Any | None = None,
        journal_path: Path | str = WORKER_JOURNAL_PATH,
        status_path: Path | str = WORKER_STATUS_PATH,
        sleep_fn: Callable[[float], None] = time.sleep,
        now_fn: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        printer: Callable[[str], None] = print,
        max_consecutive_failures: int = MAX_CONSECUTIVE_FAILURES,
    ) -> None:
        self.cfg = cfg
        self.safety = safety if safety is not None else SafetyConfig.from_env()
        self._injected_connector = connector
        self.journal_path = Path(journal_path)
        self.status_path = Path(status_path)
        self._sleep = sleep_fn
        self._now = now_fn
        self._print = printer
        self.max_consecutive_failures = max_consecutive_failures

        self._symbol: str | None = None
        self._connected = False
        self._macro_events: list[dict] = []
        self._macro_source = "none"
        self._macro_warns: list[str] = []
        self._learning_modifiers: dict = {}
        self._learning_warns: list[str] = []
        self.iterations: list[dict] = []   # in-memory record (handy for tests)

        # Last-known snapshot, so 'stopped'/'error' status keeps real values.
        self._last_decision: str | None = None
        self._last_open: int | None = None
        self._last_pnl: float | None = None
        self._last_macro_state: str | None = None

    # ── public entry ─────────────────────────────────────────────────────────
    def run(self) -> int:
        self._print_banner()
        connector = None
        consecutive_failures = 0
        i = 0
        try:
            self._preflight_safety()                   # may raise CriticalSafetyError
            self._macro_events, self._macro_source, self._macro_warns = load_calendar_or_macro(
                calendar_file=self.cfg.calendar_file,
                macro_events_file=self.cfg.macro_events_file, now=self._now(),
            )
            self._load_learning_modifiers()
            connector = self._injected_connector or Mt5DemoConnector()
            probe = ProbeResult()
            self._write_status("running")

            while self.cfg.max_iterations is None or i < self.cfg.max_iterations:
                i += 1
                try:
                    entry = self._run_iteration(connector, probe, i)
                    self.iterations.append(entry)
                    consecutive_failures = 0
                except CriticalSafetyError:
                    raise
                except Mt5ConnectorError as exc:
                    consecutive_failures += 1
                    self._connected = False
                    self._log_error(i, exc, consecutive_failures)
                    if consecutive_failures >= self.max_consecutive_failures:
                        raise CriticalSafetyError(
                            f"MT5 unavailable for {consecutive_failures} consecutive iterations "
                            "(fail closed)."
                        )
                except Exception as exc:                # non-critical: log + keep looping
                    consecutive_failures += 1
                    self._log_error(i, exc, consecutive_failures)
                    if consecutive_failures >= self.max_consecutive_failures:
                        raise CriticalSafetyError(
                            f"{consecutive_failures} consecutive iteration errors (fail closed)."
                        )

                if self.cfg.max_iterations is not None and i >= self.cfg.max_iterations:
                    break
                self._sleep(self.cfg.interval_seconds)

            self._write_status("stopped")
            self._print(f" Worker stopped after {i} iteration(s).")
            return 0
        except CriticalSafetyError as exc:
            self._print(f"\n!! CRITICAL SAFETY STOP: {exc}")
            self._write_status("error", error=str(exc))
            return 2
        except KeyboardInterrupt:
            self._print("\n Worker interrupted — stopping.")
            self._write_status("stopped")
            return 0
        finally:
            if connector is not None:
                try:
                    connector.shutdown()
                except Exception:  # noqa: BLE001 - shutdown must never mask the real result
                    pass

    # ── one iteration ─────────────────────────────────────────────────────────
    def _run_iteration(self, connector: Any, probe: ProbeResult, idx: int) -> dict:
        if not self._connected:
            connector.connect()
            self._connected = True

        connector.read_account(probe)
        if not connector.demo_verified:
            raise CriticalSafetyError(
                f"account trade_mode={getattr(probe, 'trade_mode_label', '?')} is not a "
                "verified DEMO account (fail closed)."
            )

        symbol = self._symbol or connector.discover_gold_symbol(probe, preferred=self.cfg.symbol)
        self._symbol = symbol
        connector.read_tick(probe, symbol)
        meta = connector.symbol_metadata(symbol)
        point = meta.get("point") or 0.01
        spread_points = (probe.tick_spread / point) if probe.tick_spread is not None else 0.0
        candles = connector.recent_candles(symbol, self.cfg.timeframe, self.cfg.bars)
        open_xau = len(connector.positions_for_symbol(symbol))
        today_pnl = self._read_today_pnl(connector, probe, symbol)

        macro = build_macro_context(
            self._now(), self._macro_events, self._macro_source,
            dxy_bias=self.cfg.dxy_bias, yields_bias=self.cfg.yields_bias,
            geopolitical_risk=self.cfg.geopolitical_risk, extra_warnings=list(self._macro_warns),
        )

        idea = decide(
            candles, symbol=symbol, timeframe=self.cfg.timeframe.upper(),
            risk_mode=self.cfg.risk_mode, spread_points=spread_points, point=point,
            has_open_position=open_xau > 0, macro=macro,
            use_learning_modifiers=self.cfg.use_learning_modifiers,
            learning_modifiers=self._learning_modifiers,
            learning_mode=("demo" if self.cfg.mode == "demo" else "observe"),
        )

        exec_status, risk_dec, order_sent = self._maybe_execute(
            connector, idea, symbol, meta, point, today_pnl
        )

        # close_on_no_trade is a recognised PLACEHOLDER in worker V1: no close is
        # ever sent here. It is surfaced honestly rather than silently ignored.
        note = None
        if self.cfg.close_on_no_trade and idea.decision == "NO_TRADE" and open_xau > 0:
            note = "close_on_no_trade requested but not wired in worker V1 (placeholder)."

        ts = self._now().isoformat()
        entry = {
            "timestamp": ts,
            "iteration": idx,
            "mode": self.cfg.mode,
            "risk_mode": self.cfg.risk_mode,
            "symbol": symbol,
            "timeframe": self.cfg.timeframe.upper(),
            "bid": probe.tick_bid,
            "ask": probe.tick_ask,
            "spread_points": round(spread_points, 1),
            "session": idea.session,
            "decision": idea.decision,
            "strategy": idea.strategy,
            "confidence": idea.confidence,
            "learning": idea.learning,
            "macro_event_state": macro.event_risk_state,
            "macro_bias": macro.macro_bias,
            "macro_next_event": macro.next_event_name,
            "macro_minutes_to_event": macro.minutes_to_next_event,
            "reasons": idea.reasons,
            "warnings": idea.warnings,
            "blockers": idea.blockers,
            "open_positions": open_xau,
            "today_pnl": today_pnl,
            "execution_status": exec_status,
            "order_sent": order_sent,
            "risk": risk_dec,
            "note": note,
            "account_server": probe.account_server,
            "account_login": probe.account_login,
        }
        journal.append_entry(entry, self.journal_path)
        self._print_iteration(entry, idea)
        self._last_decision = idea.decision
        self._last_open = open_xau
        self._last_pnl = today_pnl
        self._last_macro_state = macro.event_risk_state
        self._write_status("running")
        return entry

    # ── execution (guarded; mirrors the probe's sizing + risk path) ───────────
    def _maybe_execute(
        self, connector: Any, idea: Any, symbol: str, meta: dict, point: float,
        today_pnl: float | None,
    ) -> tuple[str, dict | None, bool]:
        if idea.decision not in ("LONG", "SHORT") or not idea.should_execute_demo:
            return ("no_trade", None, False)

        side = "buy" if idea.decision == "LONG" else "sell"
        levels = connector.compute_levels(symbol, side, idea.sl_points, idea.tp_points)
        order_type, entry_price, sl = levels["order_type"], levels["price"], levels["sl"]
        acct = connector.account_snapshot()
        equity = acct.get("equity") or 0.0
        rp = resolve_risk_pct(mode=self.cfg.risk_mode, override_pct=None, allow_high_demo_risk=False)
        target = equity * rp.pct / 100.0

        def _loss(v: float):
            return connector.estimate_sl_loss(
                order_type=order_type, symbol=symbol, volume=v, entry=entry_price, sl=sl
            )

        lot = calc_auto_volume(
            target_risk_amount=target, loss_at_volume=_loss,
            volume_min=meta.get("volume_min") or 0.01,
            volume_step=meta.get("volume_step") or 0.01,
            volume_max=meta.get("volume_max") or 100.0,
        )
        if lot is None:
            return ("sizing_failed", None, False)

        est_loss = _loss(lot.volume)
        margin = connector.calc_margin(
            order_type=order_type, symbol=symbol, volume=lot.volume, price=entry_price
        )
        risk_dec = evaluate_risk_plan(
            config=self.safety, account_is_demo=connector.demo_verified, side=side,
            volume=lot.volume, sl_present=True, tp_present=True, est_sl_loss=est_loss,
            require_risk_calc=True, margin_required=margin, free_margin=acct.get("margin_free"),
            equity=equity, daily_realized_pnl=today_pnl or 0.0, trades_today=0, risk_pct=rp.pct,
        )

        will_send = (self.cfg.mode == "demo" and self.cfg.auto_execute_demo
                     and self.cfg.confirm_demo_order)
        if not will_send:
            status = ("simulated_opportunity" if self.cfg.mode == "observe"
                      else "demo_blocked_missing_flags")
            return (status, risk_dec.to_dict(), False)
        if not risk_dec.approved:
            return ("risk_blocked", risk_dec.to_dict(), False)

        request = connector.build_demo_order_request(
            symbol=symbol, side=side, volume=lot.volume,
            sl_points=idea.sl_points, tp_points=idea.tp_points,
            comment="lumora-gold-bot-worker", deviation=20, magic=WORKER_MAGIC,
        )
        check = connector.check_order(request)
        check_done = getattr(getattr(connector, "_mt5", None), "TRADE_RETCODE_DONE", 10009)
        if getattr(check, "retcode", None) not in (0, check_done):
            return ("order_check_rejected", risk_dec.to_dict(), False)
        send = connector.send_demo_order(request)
        sent_ok = getattr(send, "retcode", None) == check_done
        return ("demo_order_sent" if sent_ok else "demo_order_failed", risk_dec.to_dict(), sent_ok)

    # ── helpers ────────────────────────────────────────────────────────────────
    def _load_learning_modifiers(self) -> None:
        """Load demo-only learning modifiers when enabled (default off). Fail-soft."""
        self._learning_modifiers, self._learning_warns = {}, []
        if not self.cfg.use_learning_modifiers:
            return
        from services.gold_bot_learning_modifiers import (
            DEFAULT_ACTIVE_MODIFIERS_PATH, load_active_modifiers,
        )
        path = self.cfg.learning_modifiers_file or DEFAULT_ACTIVE_MODIFIERS_PATH
        self._learning_modifiers, self._learning_warns = load_active_modifiers(path)
        for w in self._learning_warns:
            self._print(f"[learning] warning - {w}")
        if self._learning_modifiers:
            self._print(f"[learning] {len(self._learning_modifiers)} demo modifier(s) active "
                        f"(confidence-only).")

    def _read_today_pnl(self, connector: Any, probe: ProbeResult, symbol: str) -> float | None:
        """Best-effort: history read must never break the loop."""
        try:
            connector.read_history_report(probe, symbol=symbol)
        except Exception:  # noqa: BLE001 - pnl snapshot is informational
            return None
        windows = getattr(probe, "history_windows", None) or []
        today = next((w for w in windows if w.get("label") == "today"), None)
        return (today or {}).get("profit_sum") if today else None

    def _execution_label(self) -> str:
        if self.cfg.mode != "demo":
            return "observe (no orders)"
        if self.cfg.auto_execute_demo and self.cfg.confirm_demo_order:
            return "demo execution ARMED (--auto-execute-demo --confirm-demo-order)"
        return "demo (orders blocked: missing --auto-execute-demo / --confirm-demo-order)"

    # ── output ─────────────────────────────────────────────────────────────────
    def _print_banner(self) -> None:
        cfg = self.cfg
        maxit = "∞" if cfg.max_iterations is None else str(cfg.max_iterations)
        self._print("=" * 64)
        self._print(" GOLD BOT WORKER   (MT5 DEMO ONLY - NEVER LIVE)")
        self._print("=" * 64)
        self._print(f" mode         : {cfg.mode}")
        self._print(f" risk-mode    : {cfg.risk_mode}    timeframe {cfg.timeframe}  bars {cfg.bars}")
        self._print(f" interval     : {cfg.interval_seconds}s    max-iterations {maxit}")
        self._print(f" execution    : {self._execution_label()}")
        self._print(f" live trading : NEVER    demo-only {self.safety.mt5_demo_only}    "
                    f"kill-switch {self.safety.kill_switch}")
        self._print(f" calendar     : {cfg.calendar_file or '(none)'}")
        if cfg.calendar_file:
            from services.gold_bot_economic_calendar import resolve_calendar_provider
            ps = resolve_calendar_provider(cfg.calendar_file).status(self._now())
            self._print(f" calendar stat: {ps.name} [{ps.status}] freshness {ps.freshness} - {ps.message}")
        self._print(f" macro events : {cfg.macro_events_file or '(none)'}")
        self._print(f" biases       : DXY {cfg.dxy_bias} | Yields {cfg.yields_bias} | "
                    f"Geo {cfg.geopolitical_risk}")
        learn_mode = "demo" if cfg.mode == "demo" else "observe"
        self._print(f" learning     : {'enabled' if cfg.use_learning_modifiers else 'disabled'}"
                    f"  (demo-only, confidence-only)")
        if cfg.use_learning_modifiers:
            self._print(f" modifier file: {cfg.learning_modifiers_file or '(default active_demo_modifiers.json)'}")
            self._print(f" learning mode: {learn_mode}    demo-only true")
        self._print(f" journal      : {self.journal_path}")
        if self.safety.kill_switch:
            self._print(" WARNING      : GOLD_BOT_KILL_SWITCH active — all orders blocked.")
        self._print("=" * 64)

    def _print_iteration(self, e: dict, idea: Any) -> None:
        ts = str(e["timestamp"])[11:19]
        self._print(
            f"[HB] i={e['iteration']:>3} {ts}Z {e['symbol']} {e['bid']}/{e['ask']} "
            f"sp{e['spread_points']}pt {e['session']} | {e['decision']} [{e['strategy']}] "
            f"c{e['confidence']} | macro:{e['macro_event_state']} | pos:{e['open_positions']} | "
            f"{e['execution_status']} | {self.cfg.mode}"
        )
        for b in idea.blockers:
            self._print(f"      blocker - {b}")
        if idea.learning:
            lr = idea.learning
            self._print(f"      learning- conf {lr['original_confidence']} "
                        f"{lr['learning_modifier']:+d} -> {lr['final_confidence']} "
                        f"({lr['learning_mode']})")
        if e["risk"] is not None:
            rd = e["risk"]
            self._print(f"      risk    - {'APPROVED' if rd['approved'] else 'BLOCKED'} "
                        f"{rd.get('info', {})}")
        if e["note"]:
            self._print(f"      note    - {e['note']}")
        if self.cfg.json_output:
            self._print(json.dumps(e, default=str))

    def _log_error(self, idx: int, exc: Exception, consecutive: int) -> None:
        self._print(f"[ERR] iteration {idx} failed ({consecutive}/{self.max_consecutive_failures}): "
                    f"{type(exc).__name__}: {exc}")

    # ── safety / status ────────────────────────────────────────────────────────
    def _preflight_safety(self) -> None:
        """Refuse to even start if any live-trading posture is detected."""
        s = self.safety
        if not s.mt5_demo_only:
            raise CriticalSafetyError("MT5_DEMO_ONLY is disabled — refusing to start (demo-only tool).")
        if s.live_trading_enabled:
            raise CriticalSafetyError("LIVE_TRADING_ENABLED is true — refusing to start (no live trading).")
        if s.allow_real_orders:
            raise CriticalSafetyError("ALLOW_REAL_ORDERS is true — refusing to start (real orders never allowed).")
        if self.cfg.mode not in ("observe", "demo"):
            raise CriticalSafetyError(f"unknown mode '{self.cfg.mode}' (expected observe|demo).")

    def _write_status(self, worker_status: str, **fields: Any) -> None:
        if not self.cfg.write_status:
            return
        payload = {
            "worker_status": worker_status,
            "last_heartbeat_at": self._now().isoformat(),
            "mode": self.cfg.mode,
            "risk_mode": self.cfg.risk_mode,
            "symbol": self._symbol or self.cfg.symbol,
            "last_decision": self._last_decision,
            "open_positions": self._last_open,
            "today_pnl": self._last_pnl,
            "macro_event_state": self._last_macro_state,
        }
        if "error" in fields:
            payload["error"] = fields["error"]
        try:
            self.status_path.parent.mkdir(parents=True, exist_ok=True)
            self.status_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        except OSError:
            pass  # status file is best-effort; never break the loop
