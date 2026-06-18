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
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from services.connectors.mt5_demo_connector import (
    Mt5ConnectorError,
    Mt5DemoConnector,
    ProbeResult,
)
from services.gold_bot_decision_engine import MIN_CONFIDENCE, decide
from services.gold_bot_execution_environment import (
    build_execution_context,
    describe_execution_context,
)
from services.gold_bot_demo_safety_supervisor import (
    DEFAULT_EVENTS_PATH as SAFETY_EVENTS_PATH,
    DEFAULT_STATE_PATH as SAFETY_STATE_PATH,
    DemoSafetySupervisor,
    SafetyExecContext,
    SupervisorConfig,
)
from services.gold_bot_lot_calculator import (
    DEFAULT_LOT_CONFIDENCE_FLOOR,
    calc_auto_volume,
    confidence_risk_fraction,
    resolve_risk_pct,
)
from services.gold_bot_basket_scalper import (
    ADD,
    CLOSE_ALL,
    CLOSE_HARD_LOSS,
    HOLD,
    OPEN,
    BasketConfig,
    aggregate_profit,
    basket_side,
    cap_basket_positions,
    decide_basket_action,
    pressure_opposes,
    price_action_pressure,
)
from services.gold_bot_macro_context import build_macro_context, load_calendar_or_macro
from services.gold_bot_risk_gate import MAX_MARGIN_PCT_PER_TRADE, SafetyConfig, evaluate_risk_plan
from services import gold_bot_trade_journal as journal

_REPO_ROOT = Path(__file__).resolve().parent.parent
WORKER_JOURNAL_PATH = _REPO_ROOT / "data" / "gold_bot" / "worker_journal.jsonl"
WORKER_STATUS_PATH = _REPO_ROOT / "data" / "gold_bot" / "worker_status.json"
# LM108A: per-sent-order decision context (position_id -> confidence/setup) so the
# outcome sync can attach the engine confidence to each closed trade for calibration.
DECISION_CONTEXT_PATH = _REPO_ROOT / "data" / "gold_bot" / "decision_context.jsonl"

WORKER_MAGIC = 810_810
DEFAULT_INTERVAL_SECONDS = 10.0
MAX_CONSECUTIVE_FAILURES = 5


class CriticalSafetyError(Exception):
    """Raised when the worker must stop fail-closed (never recoverable in-loop)."""


@dataclass
class WorkerConfig:
    mode: str = "observe"                 # observe | demo (legacy; maps to environment/execution_mode)
    environment: str = "demo"             # LM93A: paper | demo | live (live hard-locked)
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
    # LM99A demo-only: scale lot size by decision confidence, but only WITHIN the
    # resolved risk-pct (fraction in (0,1] — never raises risk above the gate).
    confidence_scaled_lot: bool = False
    lot_confidence_floor: float = DEFAULT_LOT_CONFIDENCE_FLOOR
    # LM100A demo-only basket scalp (opt-in; default off → normal path unchanged).
    # Opens N same-direction legs and closes them all together on profit target /
    # HARD loss cap / time stop. Live stays locked; risk gate runs per leg.
    basket_scalp: bool = False
    basket_num_positions: int = 5
    basket_max_positions: int = 0          # 0 = no confidence scaling; else up to this
    basket_scale_in: bool = False          # nachkaufen toward the scaled target while open
    basket_risk_cap_pct: float = 3.0
    basket_profit_target_pct: float = 0.6
    basket_hard_loss_cap_pct: float = 1.5
    basket_time_stop_seconds: float = 60.0
    basket_allow_flip: bool = True
    basket_cooldown_seconds_after_loss: float = 60.0
    # LM101A adaptive basket exit (demo-only): trailing profit lock + price-action
    # pressure close. These only ever close EARLIER, never raise risk.
    basket_lock_arm_pct: float = 0.4
    basket_lock_floor_frac: float = 0.0
    basket_pressure_close: bool = True
    basket_pressure_min_profit_pct: float = 0.1
    basket_pressure_threshold_points: float = 300.0
    basket_pressure_confirm_bars: int = 3
    basket_reversal_close: bool = True
    basket_reversal_confidence: float = 70.0
    # LM89 demo-only: every N iterations (and on stop) record real demo trade
    # outcomes (read-only MT5 history by magic) into the learning journal +
    # supervisor loss-streak. 0 = off (no history read). Never sends orders.
    sync_outcomes_every: int = 0
    outcomes_dir: str | None = None
    outcomes_learning_dir: str | None = None
    # LM103A demo-only HARD mode: lifts per-trade risk to hard_max_risk_pct (capped
    # by HARD_DEMO_MAX_RISK_PCT). Demo-only; the daily-loss budget + basket loss cap
    # still bound it; live stays locked. Default off → normal sizing unchanged.
    hard_mode: bool = False
    hard_max_risk_pct: float = 5.0
    # Hard mode lifts the per-trade margin allowance (normal 10% of free margin)
    # so bigger aggressive legs can go through; physical broker margin is still the
    # ultimate wall. Demo-only (hard_mode is demo-only).
    hard_max_margin_pct: float = 50.0
    # Extra basket ENTRY confidence floor (0 = use the engine min). Set e.g. 75 to
    # only open on high-confidence signals.
    basket_min_confidence: float = 0.0
    # General ENTRY confidence floor for BOTH the single-trade path and the basket
    # (0 = engine min). "Trade like the beginning but only strong signals."
    min_confidence_floor: float = 0.0
    # Higher-timeframe trend filter (only trade with the long-SMA trend). Default off.
    use_trend_filter: bool = False
    # LM117 momentum forward-test gates (basket path): only open on a specific
    # strategy / below a confidence ceiling, with overridden (wide) leg SL/TP so the
    # time-exit dominates instead of tight SL/TP. All default off / None.
    basket_entry_strategy: str | None = None
    basket_max_confidence: float = 0.0
    basket_leg_sl_points: int | None = None
    basket_leg_tp_points: int | None = None
    # LM106A: on stop, post a session summary (winrate / PnL / decisions) to Discord.
    # Opt-in; webhook from --discord-webhook-url or env LUMORA_GOLD_DISCORD_WEBHOOK_URL.
    discord_session_summary: bool = False
    discord_webhook_url: str | None = None
    # Clear the demo safety supervisor state (loss-streak cooldown) at startup. Use
    # when a stale cooldown from a previous run is blocking. Demo-only state file.
    reset_safety_state: bool = False
    # LM108A: file linking each sent order's position_id to its engine confidence/
    # setup, so the outcome sync can enrich closed trades for calibration.
    decision_context_file: str | None = None
    json_output: bool = False
    write_status: bool = True
    # LM87A demo safety supervisor limits (no off switch — supervisor always runs).
    max_open_positions: int = 1
    max_trades_per_hour: int = 6
    min_seconds_between_trades: int = 120
    max_consecutive_losses: int = 3
    cooldown_minutes_after_loss_streak: int = 30
    max_spread_points: float | None = None   # None -> per-risk-mode ceiling

    def supervisor_config(self) -> SupervisorConfig:
        # In basket mode the supervisor must allow up to the basket size open at
        # once (the basket is gated as a unit). Otherwise the per-position cap
        # stands. Every other supervisor guard is unchanged.
        max_open = (max(self.basket_num_positions, self.basket_max_positions)
                    if self.basket_scalp else self.max_open_positions)
        return SupervisorConfig(
            max_open_positions=max_open,
            max_trades_per_hour=self.max_trades_per_hour,
            min_seconds_between_trades=self.min_seconds_between_trades,
            max_consecutive_losses=self.max_consecutive_losses,
            cooldown_minutes_after_loss_streak=self.cooldown_minutes_after_loss_streak,
            max_spread_points=self.max_spread_points,
            # Basket mode intentionally stacks (N legs); the open-count cap + basket
            # risk cap are the controls, so the per-position no-stacking guard is off.
            allow_stacking=self.basket_scalp,
        )

    def basket_config(self) -> BasketConfig:
        return BasketConfig(
            num_positions=self.basket_num_positions,
            max_positions=self.basket_max_positions,
            scale_in=self.basket_scale_in,
            basket_risk_cap_pct=self.basket_risk_cap_pct,
            profit_target_pct=self.basket_profit_target_pct,
            hard_loss_cap_pct=self.basket_hard_loss_cap_pct,
            time_stop_seconds=self.basket_time_stop_seconds,
            allow_flip=self.basket_allow_flip,
            cooldown_seconds_after_loss=self.basket_cooldown_seconds_after_loss,
            lock_arm_pct=self.basket_lock_arm_pct,
            lock_floor_frac=self.basket_lock_floor_frac,
            pressure_close=self.basket_pressure_close,
            pressure_min_profit_pct=self.basket_pressure_min_profit_pct,
            pressure_threshold_points=self.basket_pressure_threshold_points,
            pressure_confirm_bars=self.basket_pressure_confirm_bars,
            reversal_close=self.basket_reversal_close,
            reversal_confidence=self.basket_reversal_confidence,
        )


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
        supervisor: DemoSafetySupervisor | None = None,
        safety_state_path: Path | str = SAFETY_STATE_PATH,
        safety_events_path: Path | str = SAFETY_EVENTS_PATH,
        iteration_hook: Callable[[dict], str | None] | None = None,
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
        # LM87A: the demo safety supervisor ALWAYS runs — there is no off switch.
        self.supervisor = supervisor or DemoSafetySupervisor(
            cfg.supervisor_config(), state_path=safety_state_path, events_path=safety_events_path)
        self._learning_safety: dict | None = None
        # LM88A: optional per-iteration hook. Called after each entry is journaled;
        # if it returns a truthy reason the loop stops gracefully (session bounds).
        self._iteration_hook = iteration_hook
        self.stop_reason: str | None = None

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

        # LM100A basket scalp state (demo-only, opt-in).
        self._basket_opened_at: datetime | None = None
        self._basket_direction: str | None = None
        self._basket_cooldown_until: datetime | None = None
        self._basket_peak_profit: float = 0.0   # LM101A trailing-lock peak
        self._pressure_against_count: int = 0   # LM101B pressure debounce streak
        # LM89 outcome-sync window anchor.
        self._started_at: datetime | None = None

    # ── public entry ─────────────────────────────────────────────────────────
    def run(self) -> int:
        self._print_banner()
        connector = None
        consecutive_failures = 0
        i = 0
        try:
            self._preflight_safety()                   # may raise CriticalSafetyError
            if self.cfg.reset_safety_state:
                self._reset_safety_state()
            self._macro_events, self._macro_source, self._macro_warns = load_calendar_or_macro(
                calendar_file=self.cfg.calendar_file,
                macro_events_file=self.cfg.macro_events_file, now=self._now(),
            )
            self._load_learning_modifiers()
            connector = self._injected_connector or Mt5DemoConnector()
            probe = ProbeResult()
            self._started_at = self._now()
            self._write_status("running")

            while self.cfg.max_iterations is None or i < self.cfg.max_iterations:
                i += 1
                try:
                    entry = self._run_iteration(connector, probe, i)
                    self.iterations.append(entry)
                    consecutive_failures = 0
                    self._maybe_sync_outcomes(connector, iteration=i)
                    if self._iteration_hook is not None:
                        reason = self._iteration_hook(entry)
                        if reason:
                            self.stop_reason = reason
                            break
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

            sync_res = self._maybe_sync_outcomes(connector, force=True)
            self._maybe_send_discord_summary(sync_res)
            self._write_status("stopped")
            self._print(f" Worker stopped after {i} iteration(s).")
            return 0
        except CriticalSafetyError as exc:
            self._print(f"\n!! CRITICAL SAFETY STOP: {exc}")
            self._write_status("error", error=str(exc))
            return 2
        except KeyboardInterrupt:
            self._print("\n Worker interrupted — stopping.")
            sync_res = self._maybe_sync_outcomes(connector, force=True)
            self._maybe_send_discord_summary(sync_res)
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
        if self.cfg.basket_scalp:
            return self._run_basket_iteration(connector, probe, idx)
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
            use_learning_modifiers=bool(self.cfg.use_learning_modifiers and self._learning_modifiers),
            learning_modifiers=self._learning_modifiers,
            learning_mode=("demo" if self.cfg.mode == "demo" else "observe"),
            use_trend_filter=self.cfg.use_trend_filter,
        )

        # ── LM87A demo safety supervisor: runs every iteration (no off switch) ──
        acct = self._safe_account_snapshot(connector)
        ec = self._exec_context(connector)
        safety_dec = self.supervisor.evaluate_execution(SafetyExecContext(
            now=self._now(), risk_mode=self.cfg.risk_mode,
            account_is_demo=bool(connector.demo_verified), symbol_selected=bool(symbol),
            open_positions=open_xau, spread_points=spread_points,
            equity=acct.get("equity"), free_margin=acct.get("margin_free"),
            daily_realized_pnl=today_pnl, tick_fresh=self._tick_fresh(probe),
            kill_switch=self.safety.kill_switch,
            macro_lockout=(macro.event_risk_state == "lockout"), decision=idea.decision,
            environment=ec.environment, execution_mode=ec.mode, account_type=ec.account_type,
            live_locked=True,
        ))

        exec_status, risk_dec, order_sent = self._maybe_execute(
            connector, idea, symbol, meta, point, today_pnl, safety_dec, acct
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
            "equity": (acct or {}).get("equity"),
            "execution_context": self._exec_context(connector).to_dict(),
            "execution_status": exec_status,
            "order_sent": order_sent,
            "risk": risk_dec,
            "safety": safety_dec.to_dict(),
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

    def _reset_safety_state(self) -> None:
        """Clear the supervisor state file (loss-streak cooldown) at startup. load_state()
        reads fresh, so removing the file resets the cooldown. Demo-only; never raises."""
        try:
            p = Path(self.supervisor.state_path)
            if p.exists():
                p.unlink()
            reset = getattr(self.supervisor, "reset_state", None)
            if callable(reset):
                reset()
            self._print("[safety] state reset — loss-streak cooldown cleared.")
        except OSError as exc:
            self._print(f"[safety] state reset failed: {exc}")

    def _hard_basket_cap_warning(self) -> str | None:
        """Warn when hard-mode per-trade risk exceeds the basket cap → basket can
        never open (cap_basket_positions returns 0). Returns the message or None."""
        if not (self.cfg.hard_mode and self.cfg.basket_scalp):
            return None
        per_leg, cap = self.cfg.hard_max_risk_pct, self.cfg.basket_risk_cap_pct
        if per_leg > cap:
            need = round(per_leg * self.cfg.basket_num_positions, 1)
            return (f"hard per-trade risk {per_leg}% > basket cap {cap}% — basket will NOT open. "
                    f"Raise --basket-risk-cap-pct to >= {need} ({per_leg}% x {self.cfg.basket_num_positions} "
                    f"legs) or lower --hard-max-risk-pct.")
        return None

    def _record_decision_context(self, send: Any, idea: Any, side: str) -> None:
        """LM108A: append {position_id -> confidence/setup/side} for a SENT order, so
        the outcome sync attaches confidence to the closed trade. Never raises."""
        pid = getattr(send, "order", None) or getattr(send, "deal", None)
        if pid is None:
            return
        row = {
            "position_id": pid,
            "confidence": idea.confidence,
            "setup": idea.strategy,
            "side": "LONG" if side == "buy" else "SHORT",
            "risk_mode": self.cfg.risk_mode,
            "learning_modifier": (idea.learning or {}).get("learning_modifier"),
            "recorded_at": self._now().isoformat(),
        }
        path = Path(self.cfg.decision_context_file or DECISION_CONTEXT_PATH)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, default=str) + "\n")
        except OSError:
            pass  # context logging is best-effort; never break the loop

    def _resolve_risk(self):
        """Per-trade risk%. LM103A hard mode lifts the ceiling (demo-only); the
        daily-loss budget in the risk gate still bounds the actual order."""
        if self.cfg.hard_mode:
            return resolve_risk_pct(mode=self.cfg.risk_mode, override_pct=self.cfg.hard_max_risk_pct,
                                    allow_high_demo_risk=True, hard_demo=True)
        return resolve_risk_pct(mode=self.cfg.risk_mode, override_pct=None, allow_high_demo_risk=False)

    def _max_margin_pct(self) -> float:
        """Per-trade margin allowance. Hard mode lifts it (demo-only); broker
        physical margin remains the ultimate wall."""
        return self.cfg.hard_max_margin_pct if self.cfg.hard_mode else MAX_MARGIN_PCT_PER_TRADE

    def _basket_entry_floor(self, engine_min_conf: int) -> int:
        """Effective basket ENTRY confidence: the highest of the engine minimum,
        --basket-min-confidence and the general --min-confidence floor."""
        return int(max(engine_min_conf, self.cfg.basket_min_confidence, self.cfg.min_confidence_floor))

    # ── execution (guarded; mirrors the probe's sizing + risk path) ───────────
    def _maybe_execute(
        self, connector: Any, idea: Any, symbol: str, meta: dict, point: float,
        today_pnl: float | None, safety_dec: Any, acct: dict,
    ) -> tuple[str, dict | None, bool]:
        if idea.decision not in ("LONG", "SHORT") or not idea.should_execute_demo:
            return ("no_trade", None, False)
        if self.cfg.min_confidence_floor and idea.confidence < self.cfg.min_confidence_floor:
            return ("below_confidence_floor", None, False)

        will_send = (self.cfg.mode == "demo" and self.cfg.auto_execute_demo
                     and self.cfg.confirm_demo_order)

        # The demo safety supervisor has VETO authority over any actual send. It
        # never overrides observe (which sends nothing anyway) but is recorded.
        if will_send and not safety_dec.allowed:
            self.supervisor.record_event(safety_dec, now=self._now(), context="execution_preflight")
            return ("blocked_by_safety_supervisor", None, False)   # detail in entry["safety"]

        side = "buy" if idea.decision == "LONG" else "sell"
        levels = connector.compute_levels(symbol, side, idea.sl_points, idea.tp_points)
        order_type, entry_price, sl = levels["order_type"], levels["price"], levels["sl"]
        # Fail closed: a failed account read must NOT be masked as equity 0.0 — that
        # silently zeroes the daily-loss budget. Missing/non-positive equity = stop.
        equity = (acct or {}).get("equity")
        if not isinstance(equity, (int, float)) or equity <= 0:
            self._print("[risk] equity unavailable/non-positive — execution skipped (fail closed)")
            return ("account_unavailable", None, False)
        rp = self._resolve_risk()
        target = equity * rp.pct / 100.0

        # LM99A: optionally scale the RISK AMOUNT by decision confidence. The
        # fraction is in (0,1], so this only ever sizes DOWN from the resolved
        # risk-pct — the risk gate below remains the hard ceiling. Default off.
        conf_fraction = 1.0
        if self.cfg.confidence_scaled_lot:
            min_conf = MIN_CONFIDENCE.get(self.cfg.risk_mode.lower(), 55)
            conf_fraction = confidence_risk_fraction(
                idea.confidence, min_confidence=min_conf,
                floor_fraction=self.cfg.lot_confidence_floor)
            target = target * conf_fraction

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
            require_risk_calc=True, margin_required=margin, free_margin=(acct or {}).get("margin_free"),
            equity=equity, daily_realized_pnl=today_pnl, trades_today=0, risk_pct=rp.pct,
            max_margin_pct=self._max_margin_pct(),
        )

        risk_payload = risk_dec.to_dict()
        if self.cfg.confidence_scaled_lot:
            risk_payload["confidence_scaled_lot"] = True
            risk_payload["confidence_risk_fraction"] = round(conf_fraction, 3)

        if not will_send:
            status = ("simulated_opportunity" if self.cfg.mode == "observe"
                      else "demo_blocked_missing_flags")
            return (status, risk_payload, False)
        if not risk_dec.approved:
            return ("risk_blocked", risk_payload, False)

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
        if sent_ok:
            self.supervisor.register_trade_sent(now=self._now())   # feed the frequency guard
            self._record_decision_context(send, idea, side)
        return ("demo_order_sent" if sent_ok else "demo_order_failed", risk_payload, sent_ok)

    # ── LM100A basket scalp iteration (demo-only, opt-in) ──────────────────────
    def _run_basket_iteration(self, connector: Any, probe: ProbeResult, idx: int) -> dict:
        """
        Basket lifecycle: when flat + a fresh engine LONG/SHORT signal, open N
        same-direction legs; while open, hold until the basket hits its profit
        target / HARD loss cap / time stop, then close them all together. The
        engine is consulted with has_open_position=False only for DIRECTION; the
        basket owns hold/close. Macro lockout naturally blocks new opens (the
        engine forces NO_TRADE), closing is always allowed (it reduces risk).
        """
        if not self._connected:
            connector.connect()
            self._connected = True

        connector.read_account(probe)
        if not connector.demo_verified:
            raise CriticalSafetyError(
                f"account trade_mode={getattr(probe, 'trade_mode_label', '?')} is not a "
                "verified DEMO account (fail closed).")

        symbol = self._symbol or connector.discover_gold_symbol(probe, preferred=self.cfg.symbol)
        self._symbol = symbol
        connector.read_tick(probe, symbol)
        meta = connector.symbol_metadata(symbol)
        point = meta.get("point") or 0.01
        spread_points = (probe.tick_spread / point) if probe.tick_spread is not None else 0.0
        candles = connector.recent_candles(symbol, self.cfg.timeframe, self.cfg.bars)
        positions = [connector.position_view(p) for p in connector.positions_for_symbol(symbol)]
        open_n = len(positions)
        today_pnl = self._read_today_pnl(connector, probe, symbol)
        acct = self._safe_account_snapshot(connector)
        equity = (acct or {}).get("equity") or 0.0
        now = self._now()

        macro = build_macro_context(
            now, self._macro_events, self._macro_source,
            dxy_bias=self.cfg.dxy_bias, yields_bias=self.cfg.yields_bias,
            geopolitical_risk=self.cfg.geopolitical_risk, extra_warnings=list(self._macro_warns))

        idea = decide(
            candles, symbol=symbol, timeframe=self.cfg.timeframe.upper(),
            risk_mode=self.cfg.risk_mode, spread_points=spread_points, point=point,
            has_open_position=False, macro=macro,
            use_learning_modifiers=bool(self.cfg.use_learning_modifiers and self._learning_modifiers),
            learning_modifiers=self._learning_modifiers,
            learning_mode=("demo" if self.cfg.mode == "demo" else "observe"),
            use_trend_filter=self.cfg.use_trend_filter)

        min_conf = self._basket_entry_floor(MIN_CONFIDENCE.get(self.cfg.risk_mode.lower(), 55))
        cfg = self.cfg.basket_config()
        in_cooldown = self._basket_cooldown_until is not None and now < self._basket_cooldown_until
        agg = aggregate_profit(positions)
        pressure = price_action_pressure(candles, point)
        # Track profit peak (trailing lock) + consecutive opposing-pressure reads
        # (debounce, so a single tick down never closes). Reset when flat.
        if positions:
            self._basket_peak_profit = max(self._basket_peak_profit, agg)
            if pressure_opposes(basket_side(positions), pressure, cfg.pressure_threshold_points):
                self._pressure_against_count += 1
            else:
                self._pressure_against_count = 0
        else:
            self._basket_peak_profit = 0.0
            self._pressure_against_count = 0
        action = decide_basket_action(
            open_positions=positions, equity=equity, now=now, opened_at=self._basket_opened_at,
            signal_decision=idea.decision, signal_confidence=idea.confidence,
            min_confidence=min_conf, cfg=cfg, in_cooldown=in_cooldown,
            peak_profit=self._basket_peak_profit, pressure=pressure,
            pressure_against_streak=self._pressure_against_count)

        ec = self._exec_context(connector)
        safety_dec = self.supervisor.evaluate_execution(SafetyExecContext(
            now=now, risk_mode=self.cfg.risk_mode, account_is_demo=bool(connector.demo_verified),
            symbol_selected=bool(symbol), open_positions=open_n, spread_points=spread_points,
            equity=acct.get("equity"), free_margin=acct.get("margin_free"),
            daily_realized_pnl=today_pnl, tick_fresh=self._tick_fresh(probe),
            kill_switch=self.safety.kill_switch,
            macro_lockout=(macro.event_risk_state == "lockout"), decision=idea.decision,
            environment=ec.environment, execution_mode=ec.mode, account_type=ec.account_type,
            live_locked=True))

        will_send = (self.cfg.mode == "demo" and self.cfg.auto_execute_demo
                     and self.cfg.confirm_demo_order)
        order_count = closed_count = planned = 0
        exec_status = "basket_none"

        if action.kind == CLOSE_ALL:
            closed_count, close_status = self._close_all_positions(connector, symbol, positions, will_send)
            if will_send and closed_count > 0:
                self._basket_opened_at = None
                self._basket_direction = None
                self._basket_peak_profit = 0.0
                self._pressure_against_count = 0
            if action.reason == CLOSE_HARD_LOSS:
                self._basket_cooldown_until = now + timedelta(seconds=cfg.cooldown_seconds_after_loss)
            exec_status = f"{close_status}:{action.reason}"
        elif action.kind == OPEN:
            # LM117 forward-test gates: only the chosen strategy, below the conf ceiling.
            entry_ok = ((not self.cfg.basket_entry_strategy
                         or idea.strategy == self.cfg.basket_entry_strategy)
                        and (self.cfg.basket_max_confidence <= 0
                             or idea.confidence < self.cfg.basket_max_confidence))
            if not entry_ok:
                exec_status = "basket_entry_filtered"
            elif will_send and not safety_dec.allowed:
                self.supervisor.record_event(safety_dec, now=now, context="basket_open_preflight")
                exec_status = "blocked_by_safety_supervisor"
            else:
                order_count, planned, exec_status = self._open_basket(
                    connector, idea, symbol, meta, point, today_pnl, acct, cfg, will_send,
                    requested=action.num_positions)
                if will_send and order_count > 0:
                    self._basket_opened_at = now
                    self._basket_direction = action.direction
                    self._basket_peak_profit = 0.0
                    self._pressure_against_count = 0
        elif action.kind == ADD:
            # Scale-in: add legs to the SAME open basket. Keep opened_at/peak (it is
            # the same basket growing); the risk cap + per-leg risk gate bound it.
            if will_send and not safety_dec.allowed:
                self.supervisor.record_event(safety_dec, now=now, context="basket_add_preflight")
                exec_status = "blocked_by_safety_supervisor"
            else:
                order_count, planned, exec_status = self._open_basket(
                    connector, idea, symbol, meta, point, today_pnl, acct, cfg, will_send,
                    requested=action.num_positions, already_open=open_n)
                if exec_status == "basket_opened":
                    exec_status = "basket_added"
        elif action.kind == HOLD:
            exec_status = "basket_hold"

        entry = {
            "timestamp": now.isoformat(), "iteration": idx, "mode": self.cfg.mode,
            "risk_mode": self.cfg.risk_mode, "symbol": symbol, "timeframe": self.cfg.timeframe.upper(),
            "bid": probe.tick_bid, "ask": probe.tick_ask, "spread_points": round(spread_points, 1),
            "session": idea.session, "decision": idea.decision, "strategy": idea.strategy,
            "confidence": idea.confidence, "learning": idea.learning,
            "macro_event_state": macro.event_risk_state, "macro_bias": macro.macro_bias,
            "macro_next_event": macro.next_event_name, "macro_minutes_to_event": macro.minutes_to_next_event,
            "reasons": idea.reasons, "warnings": idea.warnings, "blockers": idea.blockers,
            "open_positions": open_n, "today_pnl": today_pnl, "equity": (acct or {}).get("equity"),
            "execution_context": ec.to_dict(), "execution_status": exec_status,
            "order_sent": order_count > 0, "safety": safety_dec.to_dict(),
            "account_server": probe.account_server, "account_login": probe.account_login,
            "basket": {
                "action": action.kind, "reason": action.reason, "direction": action.direction,
                "aggregate_profit": agg, "peak_profit": self._basket_peak_profit,
                "pressure": pressure, "pressure_against_count": self._pressure_against_count,
                "open_positions": open_n, "opened_count": order_count,
                "planned_count": planned, "closed_count": closed_count, "in_cooldown": in_cooldown,
                "cfg": {"num_positions": cfg.num_positions, "risk_cap_pct": cfg.basket_risk_cap_pct,
                        "profit_target_pct": cfg.profit_target_pct,
                        "hard_loss_cap_pct": cfg.hard_loss_cap_pct,
                        "time_stop_seconds": cfg.time_stop_seconds,
                        "lock_arm_pct": cfg.lock_arm_pct, "lock_floor_frac": cfg.lock_floor_frac,
                        "pressure_close": cfg.pressure_close,
                        "pressure_threshold_points": cfg.pressure_threshold_points},
            },
        }
        journal.append_entry(entry, self.journal_path)
        self._print_basket_iteration(entry)
        self._last_decision = idea.decision
        self._last_open = open_n
        self._last_pnl = today_pnl
        self._last_macro_state = macro.event_risk_state
        self._write_status("running")
        return entry

    def _open_basket(self, connector: Any, idea: Any, symbol: str, meta: dict, point: float,
                     today_pnl: float | None, acct: dict, cfg: BasketConfig,
                     will_send: bool, *, requested: int, already_open: int = 0
                     ) -> tuple[int, int, str]:
        """Size one leg's risk, cap the requested leg count by the basket risk cap
        (accounting for already-open legs, so scale-in respects the total cap), then
        send (or simulate) each leg. Returns (sent_count, planned_count, status)."""
        equity = (acct or {}).get("equity") or 0.0
        rp = self._resolve_risk()
        conf_fraction = 1.0
        if self.cfg.confidence_scaled_lot:
            min_conf = MIN_CONFIDENCE.get(self.cfg.risk_mode.lower(), 55)
            conf_fraction = confidence_risk_fraction(
                idea.confidence, min_confidence=min_conf, floor_fraction=self.cfg.lot_confidence_floor)
        per_leg_target = equity * rp.pct / 100.0 * conf_fraction
        # Total legs the cap allows (existing + requested), then how many MORE fit.
        cap_total = cap_basket_positions(requested + already_open, per_leg_target, equity,
                                         cfg.basket_risk_cap_pct)
        n = max(0, min(requested, cap_total - already_open))
        if n <= 0:
            return (0, 0, "basket_risk_cap_blocked")
        if not will_send:
            status = "simulated_basket_open" if self.cfg.mode == "observe" else "demo_blocked_missing_flags"
            return (0, n, status)
        sent = 0
        leg_fail: str | None = None
        for _ in range(n):
            ok, st, _rd = self._size_and_send_leg(
                connector, idea, symbol, meta, per_leg_target, today_pnl, acct)
            if ok:
                sent += 1
            elif leg_fail is None:
                leg_fail = st
        if sent > 0:
            self.supervisor.register_trade_sent(now=self._now())   # one frequency slot per basket
            return (sent, n, "basket_opened")
        # Surface WHY every leg failed (risk_blocked / order_check_rejected / sizing_failed)
        # so a blocked basket is debuggable instead of a generic failure.
        return (0, n, f"basket_open_failed:{leg_fail or 'unknown'}")

    def _size_and_send_leg(self, connector: Any, idea: Any, symbol: str, meta: dict,
                           target_risk: float, today_pnl: float | None, acct: dict
                           ) -> tuple[bool, str, dict | None]:
        """Size + risk-gate + send ONE leg (mirrors _maybe_execute's sizing path)."""
        side = "buy" if idea.decision == "LONG" else "sell"
        # Optional wide leg SL/TP (LM117) so a time-exit dominates over tight SL/TP.
        sl_pts = self.cfg.basket_leg_sl_points or idea.sl_points
        tp_pts = self.cfg.basket_leg_tp_points or idea.tp_points
        levels = connector.compute_levels(symbol, side, sl_pts, tp_pts)
        order_type, entry_price, sl = levels["order_type"], levels["price"], levels["sl"]
        # Fail closed: failed account read must not become equity 0.0 (see _maybe_execute).
        equity = (acct or {}).get("equity")
        if not isinstance(equity, (int, float)) or equity <= 0:
            return (False, "account_unavailable", None)

        def _loss(v: float):
            return connector.estimate_sl_loss(
                order_type=order_type, symbol=symbol, volume=v, entry=entry_price, sl=sl)

        lot = calc_auto_volume(
            target_risk_amount=target_risk, loss_at_volume=_loss,
            volume_min=meta.get("volume_min") or 0.01, volume_step=meta.get("volume_step") or 0.01,
            volume_max=meta.get("volume_max") or 100.0)
        if lot is None:
            return (False, "sizing_failed", None)
        est_loss = _loss(lot.volume)
        margin = connector.calc_margin(order_type=order_type, symbol=symbol, volume=lot.volume,
                                       price=entry_price)
        rp_pct = self._resolve_risk().pct
        risk_dec = evaluate_risk_plan(
            config=self.safety, account_is_demo=connector.demo_verified, side=side,
            volume=lot.volume, sl_present=True, tp_present=True, est_sl_loss=est_loss,
            require_risk_calc=True, margin_required=margin, free_margin=(acct or {}).get("margin_free"),
            equity=equity, daily_realized_pnl=today_pnl, trades_today=0, risk_pct=rp_pct,
            max_margin_pct=self._max_margin_pct())
        if not risk_dec.approved:
            return (False, "risk_blocked", risk_dec.to_dict())
        request = connector.build_demo_order_request(
            symbol=symbol, side=side, volume=lot.volume, sl_points=sl_pts,
            tp_points=tp_pts, comment="lumora-gold-bot-basket", deviation=20, magic=WORKER_MAGIC)
        check = connector.check_order(request)
        check_done = getattr(getattr(connector, "_mt5", None), "TRADE_RETCODE_DONE", 10009)
        if getattr(check, "retcode", None) not in (0, check_done):
            return (False, "order_check_rejected", risk_dec.to_dict())
        send = connector.send_demo_order(request)
        sent_ok = getattr(send, "retcode", None) == check_done
        if sent_ok:
            self._record_decision_context(send, idea, side)
        return (sent_ok, "demo_order_sent" if sent_ok else "demo_order_failed", risk_dec.to_dict())

    def _close_all_positions(self, connector: Any, symbol: str, positions: list[dict],
                             will_send: bool) -> tuple[int, str]:
        """Close every open leg (opposite-side demo close). Returns (closed, status)."""
        if not will_send:
            return (0, "simulated_basket_close")
        check_done = getattr(getattr(connector, "_mt5", None), "TRADE_RETCODE_DONE", 10009)
        closed = 0
        for pv in positions:
            ticket = pv.get("ticket")
            pos = connector.position_by_ticket(ticket) if ticket is not None else None
            if pos is None:
                continue
            request = connector.build_close_request(pos)
            res = connector.send_demo_close(request)
            if getattr(res, "retcode", None) == check_done:
                closed += 1
        return (closed, "basket_closed" if closed > 0 else "basket_close_failed")

    def _print_basket_iteration(self, e: dict) -> None:
        ts = str(e["timestamp"])[11:19]
        b = e["basket"]
        self._print(
            f"[BK] i={e['iteration']:>3} {ts}Z {e['symbol']} {e['bid']}/{e['ask']} "
            f"sp{e['spread_points']}pt {e['session']} | {b['action']} ({b['reason']}) | "
            f"pos:{b['open_positions']} pnl:{b['aggregate_profit']} peak:{b['peak_profit']} "
            f"prs:{b['pressure']} | open:{b['opened_count']}/{b['planned_count']} "
            f"close:{b['closed_count']} | {e['execution_status']} | {self.cfg.mode}")
        if self.cfg.json_output:
            self._print(json.dumps(e, default=str))

    # ── supervisor input helpers ───────────────────────────────────────────────
    def _safe_account_snapshot(self, connector: Any) -> dict:
        """Equity/free-margin for the supervisor; never breaks the loop if absent.

        On failure returns {} so downstream equity/free-margin read as None and the
        risk gate fails closed — but logs it (a silent {} hid account-read failures).
        """
        try:
            return connector.account_snapshot() or {}
        except Exception as exc:  # noqa: BLE001 - read failed → empty so callers fail closed
            self._print(f"[risk] account snapshot failed: {exc} — equity/free-margin unavailable")
            return {}

    def _tick_fresh(self, probe: ProbeResult) -> bool:
        """True if the last tick is recent (or its time is unknown — fail open on info)."""
        from services.gold_bot_demo_safety_supervisor import TICK_STALE_SECONDS, _parse_iso
        t = _parse_iso(getattr(probe, "tick_time", None))
        if t is None:
            return True
        return (self._now() - t).total_seconds() <= TICK_STALE_SECONDS

    # ── helpers ────────────────────────────────────────────────────────────────
    def _load_learning_modifiers(self) -> None:
        """
        Load demo-only learning modifiers when enabled (default off). Fail-soft.
        The safety supervisor validates the file against the demo contract FIRST;
        an invalid/expired/forbidden file disables learning for this run (in-memory
        only — files are never deleted here).
        """
        self._learning_modifiers, self._learning_warns = {}, []
        if not self.cfg.use_learning_modifiers:
            return
        from services.gold_bot_learning_modifiers import (
            DEFAULT_ACTIVE_MODIFIERS_PATH, load_active_modifiers,
        )
        path = self.cfg.learning_modifiers_file or DEFAULT_ACTIVE_MODIFIERS_PATH

        decision = self.supervisor.evaluate_learning(path, enabled=True, now=self._now())
        self._learning_safety = decision.to_dict()
        if not decision.allowed:
            self.supervisor.record_event(decision, now=self._now(), context="learning_contract")
            self._print(f"[learning] DISABLED by safety supervisor — {decision.reason}")
            for vio in decision.details.get("violations", []):
                self._print(f"           contract - {vio}")
            return

        self._learning_modifiers, self._learning_warns = load_active_modifiers(path)
        for w in self._learning_warns:
            self._print(f"[learning] warning - {w}")
        if self._learning_modifiers:
            self._print(f"[learning] {len(self._learning_modifiers)} demo modifier(s) active "
                        f"(confidence-only, contract OK).")

    def _read_today_pnl(self, connector: Any, probe: ProbeResult, symbol: str) -> float | None:
        """Today's realized PnL for the daily-loss budget.

        Returns None ONLY when the history read itself fails — an UNKNOWN value the
        risk gate must fail closed on, never a silent 0.0 that fakes an intact
        budget. When the read succeeds but there are simply no trades today,
        realized PnL is genuinely 0.0 (so the first trade of the day still passes).
        """
        try:
            connector.read_history_report(probe, symbol=symbol)
        except Exception as exc:  # noqa: BLE001 - read failed → unknown, do not mask as 0.0
            self._print(f"[risk] today-PnL read failed: {exc} — treating as unknown (fail closed)")
            return None
        windows = getattr(probe, "history_windows", None) or []
        today = next((w for w in windows if w.get("label") == "today"), None)
        if today is None:
            return 0.0  # successful read, no trades today → realized PnL is zero
        val = today.get("profit_sum")
        return val if val is not None else 0.0

    def _maybe_sync_outcomes(self, connector: Any, *, iteration: int | None = None,
                             force: bool = False) -> None:
        """
        LM89 demo-only: reconstruct real demo trade outcomes from MT5 history (by
        WORKER_MAGIC) into the learning journal + supervisor loss-streak. Off
        unless sync_outcomes_every > 0. READ-ONLY history; never sends an order;
        the loss-streak update can only tighten the guard, never loosen it.
        """
        # Run when periodic sync is on; also force a final sync on stop when the
        # Discord summary is enabled (so winrate/PnL are available). Returns the
        # sync result dict (or None).
        want = self.cfg.sync_outcomes_every > 0 or (force and self.cfg.discord_session_summary)
        if connector is None or not want:
            return None
        if not force:
            if (self.cfg.sync_outcomes_every <= 0 or iteration is None
                    or iteration % self.cfg.sync_outcomes_every != 0):
                return None
        if not hasattr(connector, "deal_history"):
            return None
        from services.gold_bot_trade_outcomes import (
            DEFAULT_LEARNING_DIR, DEFAULT_OUTCOMES_DIR, DEFAULT_SYMBOL,
            load_decision_context, sync_session_outcomes,
        )
        now = self._now()
        frm = (self._started_at or now) - timedelta(minutes=5)
        enrich = load_decision_context(self.cfg.decision_context_file or DECISION_CONTEXT_PATH)
        try:
            # supervisor=None on purpose: this periodic sync is for RECORDING
            # (learning journal). Feeding the supervisor here re-replayed the same
            # closed losses every sync, inflating the loss-streak and endlessly
            # extending the cooldown — a bug that froze trading. The loss-streak
            # guard is not driven by repeated history replay.
            res = sync_session_outcomes(
                symbol=self._symbol or DEFAULT_SYMBOL, magic=WORKER_MAGIC,
                from_time=frm, to_time=now + timedelta(minutes=1),
                out_dir=self.cfg.outcomes_dir or DEFAULT_OUTCOMES_DIR,
                learning_dir=self.cfg.outcomes_learning_dir or DEFAULT_LEARNING_DIR,
                supervisor=None, connector=connector, write=True, now=now, enrich=enrich)
        except Exception as exc:  # noqa: BLE001 - outcome sync must never break the loop
            self._print(f"[outcomes] sync skipped: {exc}")
            return None
        if res.get("synced"):
            self._print(f"[outcomes] synced {res.get('outcomes_count')} "
                        f"(W{res.get('wins')}/L{res.get('losses')}/open{res.get('open')}) "
                        f"journaled {res.get('journaled')} rows")
        else:
            self._print(f"[outcomes] not synced: {res.get('reason')}")
        return res

    def _build_session_summary_text(self, sync_res: dict | None) -> str:
        """Concise session summary (decisions / orders / winrate / PnL) for Discord."""
        its = self.iterations
        longs = sum(1 for e in its if e.get("decision") == "LONG")
        shorts = sum(1 for e in its if e.get("decision") == "SHORT")
        no_trade = sum(1 for e in its if e.get("decision") == "NO_TRADE")
        sent = sum(1 for e in its if e.get("order_sent"))
        blocked = sum(1 for e in its if "block" in str(e.get("execution_status", "")))
        sr = sync_res or {}
        wins, losses, be = sr.get("wins"), sr.get("losses"), sr.get("breakeven")
        pnl = sr.get("realized_pnl")
        wl = (wins or 0) + (losses or 0)
        winrate = f"{(wins / wl * 100):.0f}%" if wl else "n/a"
        dur = ""
        if self._started_at:
            secs = int((self._now() - self._started_at).total_seconds())
            dur = f"{secs // 60}m{secs % 60}s"
        flags = "".join([" | HARD" if self.cfg.hard_mode else "",
                         " | basket" if self.cfg.basket_scalp else ""])
        lines = [
            "**Gold Bot — Session Summary**",
            f"Mode: {self.cfg.mode} | {self._symbol or self.cfg.symbol} | risk {self.cfg.risk_mode}{flags}",
            f"Duration: {dur or 'n/a'} | iterations: {len(its)}",
            f"Decisions: LONG {longs} / SHORT {shorts} / NO_TRADE {no_trade}",
            f"Orders sent: {sent} | blocked: {blocked}",
            f"Outcomes: {wins or 0}W / {losses or 0}L / {be or 0}BE | winrate {winrate} | PnL {pnl}",
        ]
        if not (sync_res and sync_res.get("synced")):
            lines.append("(outcomes unavailable — needs MT5 demo history sync)")
        return "\n".join(lines)

    def _maybe_send_discord_summary(self, sync_res: dict | None) -> None:
        """Post the session summary to Discord on stop (opt-in). Never raises; the
        webhook is read from --discord-webhook-url or the env var, never logged."""
        if not self.cfg.discord_session_summary:
            return
        try:
            from services.gold_bot_discord_review_sender import resolve_webhook, send_review
        except Exception as exc:  # noqa: BLE001
            self._print(f"[discord] summary skipped (import): {exc}")
            return
        if not resolve_webhook(self.cfg.discord_webhook_url):
            self._print("[discord] summary skipped — no webhook "
                        "(set env LUMORA_GOLD_DISCORD_WEBHOOK_URL or --discord-webhook-url).")
            return
        try:
            content = self._build_session_summary_text(sync_res)
            res = send_review(content, webhook_url=self.cfg.discord_webhook_url)
        except Exception as exc:  # noqa: BLE001 - never let the summary break shutdown
            self._print(f"[discord] summary failed: {exc}")
            return
        self._print("[discord] session summary sent." if res.get("ok")
                    else f"[discord] summary failed: {res.get('error')}")

    def _execution_label(self) -> str:
        if self.cfg.mode != "demo":
            return "observe (no orders)"
        if self.cfg.auto_execute_demo and self.cfg.confirm_demo_order:
            return "demo execution ARMED (--auto-execute-demo --confirm-demo-order)"
        return "demo (orders blocked: missing --auto-execute-demo / --confirm-demo-order)"

    def _exec_context(self, connector: Any | None = None):
        """LM93A execution-environment framing (demo only; live hard-locked)."""
        acct = ({"demo_verified": getattr(connector, "demo_verified", None)}
                if connector is not None else None)
        return build_execution_context(self.cfg.environment, self.cfg.mode, account_info=acct)

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
        self._print(f" live trading : LOCKED   demo-only {self.safety.mt5_demo_only}    "
                    f"kill-switch {self.safety.kill_switch}")
        self._print(f" execution    : {describe_execution_context(self._exec_context())}")
        sc = self.supervisor.config
        self._print(f" safety super : ALWAYS ON (no off switch)  max-open {sc.max_open_positions}  "
                    f"<={sc.max_trades_per_hour}/h  gap {sc.min_seconds_between_trades}s  "
                    f"loss-streak {sc.max_consecutive_losses}->{sc.cooldown_minutes_after_loss_streak}m")
        self._print(f" calendar     : {cfg.calendar_file or '(none)'}")
        if cfg.calendar_file:
            from services.gold_bot_economic_calendar import resolve_calendar_provider
            ps = resolve_calendar_provider(cfg.calendar_file).status(self._now())
            self._print(f" calendar stat: {ps.name} [{ps.status}] freshness {ps.freshness} - {ps.message}")
        self._print(f" macro events : {cfg.macro_events_file or '(none)'}")
        self._print(f" biases       : DXY {cfg.dxy_bias} | Yields {cfg.yields_bias} | "
                    f"Geo {cfg.geopolitical_risk}")
        if cfg.hard_mode:
            self._print(f" HARD MODE    : ON  per-trade risk up to {cfg.hard_max_risk_pct}% (wall 10%)  "
                        f"margin/trade up to {cfg.hard_max_margin_pct}%  (DEMO-ONLY) — daily-loss "
                        f"budget + loss caps + physical margin still apply")
        if cfg.basket_scalp and cfg.basket_min_confidence > 0:
            self._print(f" basket entry : confidence floor {cfg.basket_min_confidence:.0f}")
        if cfg.basket_scalp:
            legs = (f"{cfg.basket_num_positions}-{cfg.basket_max_positions} legs (conf-scaled)"
                    if cfg.basket_max_positions > cfg.basket_num_positions
                    else f"{cfg.basket_num_positions} legs")
            scalein = "  scale-in ON" if cfg.basket_scale_in else ""
            self._print(f" basket scalp : ON  {legs}{scalein}  cap {cfg.basket_risk_cap_pct}%  "
                        f"+target {cfg.basket_profit_target_pct}%  HARD-stop -{cfg.basket_hard_loss_cap_pct}%  "
                        f"time {cfg.basket_time_stop_seconds}s  (DEMO-ONLY)")
        cap_warn = self._hard_basket_cap_warning()
        if cap_warn:
            self._print(f" WARNING      : {cap_warn}")
        learn_mode = "demo" if cfg.mode == "demo" else "observe"
        self._print(f" learning     : {'enabled' if cfg.use_learning_modifiers else 'disabled'}"
                    f"  (demo-only, confidence-only)")
        if cfg.use_learning_modifiers:
            self._print(f" modifier file: {cfg.learning_modifiers_file or '(default active_demo_modifiers.json)'}")
            self._print(f" learning mode: {learn_mode}    demo-only true")
        if cfg.discord_session_summary:
            from services.gold_bot_discord_review_sender import resolve_webhook
            wh = "configured" if resolve_webhook(cfg.discord_webhook_url) else "NO WEBHOOK SET"
            self._print(f" discord      : session summary on stop ({wh})")
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
        sf = e.get("safety")
        if sf and (not sf["allowed"] or sf["severity"] != "info"):
            cd = f" cooldown_until {sf['cooldown_until']}" if sf.get("cooldown_until") else ""
            self._print(f"      safety  - {sf['severity'].upper()} {sf['reason']}{cd}")
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
        if self.cfg.hard_mode and self.cfg.environment != "demo":
            raise CriticalSafetyError(
                "hard_mode is demo-only and refused outside the demo environment (fail closed).")

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
            "stop_reason": self.stop_reason,
        }
        if "error" in fields:
            payload["error"] = fields["error"]
        try:
            self.status_path.parent.mkdir(parents=True, exist_ok=True)
            self.status_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        except OSError:
            pass  # status file is best-effort; never break the loop
