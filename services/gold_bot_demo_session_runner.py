"""
services/gold_bot_demo_session_runner.py
------------------------------------------
LM88A - Bounded DEMO auto-session runner for the Gold Bot.

Composes the existing pieces - GoldBotWorker (decision engine V2 + guarded demo
execution), the LM86B demo learning modifiers, and the LM87A always-on safety
supervisor - into a single CONTROLLED MT5 demo trading session with hard limits:

    * wall-clock duration         (duration_minutes)
    * max iterations / max trades
    * max runtime loss %          (session drawdown stop)
    * automatic stop on critical / repeated safety blocks
    * a full session report (JSON) + an event log (JSONL)

SAFETY POSTURE (unchanged + reinforced):
  * DEMO ONLY, NEVER LIVE. No live-trading flags exist here.
  * The session sends NO orders unless explicitly armed with confirm_demo_session,
    AND the worker's own demo guards (--mode demo / --auto-execute-demo /
    --confirm-demo-order, verified demo account, risk gate, supervisor) still apply.
  * The LM87A safety supervisor ALWAYS runs - this runner cannot turn it off and
    actively stops the session when it blocks critically or repeatedly.
  * No strategy logic is duplicated - it all lives in the worker.

Pure orchestration: no MT5 import here, no HTTP, no secrets. The worker is
injectable (worker_factory) so tests drive whole sessions with fake iterations -
no MT5, no internet.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from services.gold_bot_worker import GoldBotWorker, WorkerConfig

_REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SESSIONS_DIR = _REPO_ROOT / "data" / "gold_bot" / "sessions"

# Stop thresholds the session owns (the worker/supervisor own the per-order gates).
CONSECUTIVE_SAFETY_BLOCK_STOP = 3

# Execution statuses that mean "the worker tried to act on a directional idea".
_ATTEMPT_STATUSES = {"demo_order_sent", "demo_order_failed", "order_check_rejected",
                     "risk_blocked", "blocked_by_safety_supervisor"}
_SENT_STATUS = "demo_order_sent"
_SAFETY_BLOCK_STATUS = "blocked_by_safety_supervisor"


@dataclass
class DemoSessionConfig:
    symbol: str = "XAUUSD"
    risk_mode: str = "scalp"
    timeframe: str = "M1"
    interval_seconds: float = 5.0
    duration_minutes: float = 30.0
    max_iterations: int | None = None
    max_trades: int = 10
    max_runtime_loss_pct: float = 3.0
    use_learning_modifiers: bool = True
    calendar_file: str | None = None
    macro_events_file: str | None = None
    dry_run: bool = False
    confirm_demo_session: bool = False

    @property
    def armed(self) -> bool:
        """Demo orders are only ever possible when explicitly confirmed (and not dry-run)."""
        return bool(self.confirm_demo_session and not self.dry_run)


@dataclass
class SessionResult:
    report: dict
    report_path: Path | None = None
    events_path: Path | None = None
    latest_path: Path | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"report": self.report,
                "report_path": str(self.report_path) if self.report_path else None,
                "events_path": str(self.events_path) if self.events_path else None,
                "latest_path": str(self.latest_path) if self.latest_path else None}


class DemoSessionRunner:
    """Runs one bounded demo session. Inject `worker_factory` (tests) or `connector`."""

    def __init__(self, cfg: DemoSessionConfig, *,
                 worker_factory: Callable[[WorkerConfig, Callable[[dict], str | None]], Any] | None = None,
                 connector: Any | None = None, sessions_dir: Path | str = DEFAULT_SESSIONS_DIR,
                 now_fn: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
                 printer: Callable[[str], None] = print) -> None:
        self.cfg = cfg
        self._worker_factory = worker_factory
        self._connector = connector
        self.sessions_dir = Path(sessions_dir)
        self._now = now_fn
        self._print = printer
        self._events_fh = None
        self._session_id = ""
        self._stop_reason: str | None = None
        self._agg = self._fresh_agg()
        self._warnings: list[str] = []

    # ── aggregation state ──────────────────────────────────────────────────────
    @staticmethod
    def _fresh_agg() -> dict[str, Any]:
        return {"iterations": 0, "long": 0, "short": 0, "no_trade": 0,
                "orders_attempted": 0, "orders_sent": 0, "blocked_by_safety": 0,
                "macro_lockout": 0, "blocked_reasons": {}, "consecutive_blocks": 0,
                "starting_equity": None, "ending_equity": None, "last_pnl": None}

    # ── public entry ────────────────────────────────────────────────────────────
    def run(self) -> SessionResult:
        started = self._now()
        self._session_id = "session_" + started.strftime("%Y%m%d_%H%M%S")
        armed = self.cfg.armed
        self._print_banner(armed)

        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        events_path = self.sessions_dir / f"{self._session_id}.jsonl"
        self._events_fh = events_path.open("w", encoding="utf-8")

        worker_cfg = self._build_worker_config(armed)
        self._emit("session_start", {
            "symbol": self.cfg.symbol, "risk_mode": self.cfg.risk_mode,
            "mode": worker_cfg.mode, "armed": armed,
            "duration_minutes": self.cfg.duration_minutes, "max_trades": self.cfg.max_trades,
            "max_iterations": self.cfg.max_iterations,
            "use_learning_modifiers": self.cfg.use_learning_modifiers,
            "max_runtime_loss_pct": self.cfg.max_runtime_loss_pct,
        })
        if not armed:
            self._warnings.append("not armed (no --confirm-demo-session): observe only, NO orders sent.")

        deadline_s = self.cfg.duration_minutes * 60.0
        hook = self._make_hook(started, deadline_s)
        factory = self._worker_factory or self._default_worker_factory
        worker = factory(worker_cfg, hook)

        try:
            worker.run()
        except KeyboardInterrupt:
            self._stop_reason = "keyboard_interrupt"

        ended = self._now()
        stop_reason = (self._stop_reason or getattr(worker, "stop_reason", None)
                       or ("max_iterations_reached" if worker_cfg.max_iterations else "session_complete"))
        report = self._build_report(worker, worker_cfg, started, ended, stop_reason)
        self._emit("session_stop", {"stop_reason": stop_reason,
                                    "iterations": self._agg["iterations"],
                                    "orders_sent": self._agg["orders_sent"]})
        if self._events_fh is not None:
            self._events_fh.close()
            self._events_fh = None

        report_path = self.sessions_dir / f"{self._session_id}.json"
        latest_path = self.sessions_dir / "session_latest.json"
        payload = json.dumps(report, indent=2, default=str)
        report_path.write_text(payload, encoding="utf-8")
        latest_path.write_text(payload, encoding="utf-8")

        self._print_summary(report, report_path)
        return SessionResult(report=report, report_path=report_path,
                             events_path=events_path, latest_path=latest_path)

    # ── worker wiring ────────────────────────────────────────────────────────────
    def _build_worker_config(self, armed: bool) -> WorkerConfig:
        return WorkerConfig(
            mode=("demo" if armed else "observe"), risk_mode=self.cfg.risk_mode,
            interval_seconds=self.cfg.interval_seconds, max_iterations=self.cfg.max_iterations,
            symbol=self.cfg.symbol, timeframe=self.cfg.timeframe,
            calendar_file=self.cfg.calendar_file, macro_events_file=self.cfg.macro_events_file,
            auto_execute_demo=armed, confirm_demo_order=armed,
            use_learning_modifiers=self.cfg.use_learning_modifiers,
            write_status=True,
        )

    def _default_worker_factory(self, worker_cfg: WorkerConfig,
                                hook: Callable[[dict], str | None]) -> GoldBotWorker:
        return GoldBotWorker(worker_cfg, connector=self._connector, iteration_hook=hook,
                             now_fn=self._now, printer=self._print)

    # ── per-iteration hook: events + counters + stop conditions ──────────────────
    def _make_hook(self, started: datetime, deadline_s: float) -> Callable[[dict], str | None]:
        def hook(entry: dict) -> str | None:
            a = self._agg
            a["iterations"] += 1
            decision = entry.get("decision")
            if decision == "LONG":
                a["long"] += 1
            elif decision == "SHORT":
                a["short"] += 1
            else:
                a["no_trade"] += 1
            if entry.get("strategy") == "macro_lockout" or entry.get("macro_event_state") == "lockout":
                a["macro_lockout"] += 1

            eq = entry.get("equity")
            if eq is not None:
                if a["starting_equity"] is None:
                    a["starting_equity"] = eq
                a["ending_equity"] = eq
            if entry.get("today_pnl") is not None:
                a["last_pnl"] = entry.get("today_pnl")

            status = entry.get("execution_status")
            safety = entry.get("safety") or {}
            if status in _ATTEMPT_STATUSES:
                a["orders_attempted"] += 1
            if status == _SENT_STATUS:
                a["orders_sent"] += 1
            is_block = status == _SAFETY_BLOCK_STATUS
            if is_block:
                a["blocked_by_safety"] += 1
                a["consecutive_blocks"] += 1
                reason = safety.get("reason", "unknown")
                a["blocked_reasons"][reason] = a["blocked_reasons"].get(reason, 0) + 1
            else:
                a["consecutive_blocks"] = 0

            # ── event rows ──
            self._emit("heartbeat", {
                "iteration": a["iterations"], "decision": decision,
                "strategy": entry.get("strategy"), "confidence": entry.get("confidence"),
                "execution_status": status, "open_positions": entry.get("open_positions"),
                "equity": eq, "today_pnl": entry.get("today_pnl"),
                "safety_severity": safety.get("severity")})
            self._emit("decision", {"iteration": a["iterations"], "decision": decision,
                                    "strategy": entry.get("strategy"),
                                    "confidence": entry.get("confidence"),
                                    "reasons": entry.get("reasons")})
            if status in _ATTEMPT_STATUSES:
                self._emit("order_attempt", {"iteration": a["iterations"], "status": status,
                                             "decision": decision})
            if status == _SENT_STATUS:
                self._emit("order_sent", {"iteration": a["iterations"], "decision": decision})
            if is_block:
                self._emit("safety_block", {"iteration": a["iterations"],
                                            "reason": safety.get("reason"),
                                            "severity": safety.get("severity"),
                                            "cooldown_until": safety.get("cooldown_until")})

            # ── stop conditions (critical first) ──
            if is_block and safety.get("severity") == "critical":
                return self._stop("critical_safety")
            loss_pct = self._runtime_loss_pct()
            if loss_pct is not None and loss_pct >= self.cfg.max_runtime_loss_pct:
                return self._stop("runtime_loss_limit")
            if a["orders_sent"] >= self.cfg.max_trades:
                return self._stop("max_trades_reached")
            if a["consecutive_blocks"] >= CONSECUTIVE_SAFETY_BLOCK_STOP:
                return self._stop("consecutive_safety_blocks")
            if (self._now() - started).total_seconds() >= deadline_s:
                return self._stop("duration_reached")
            return None

        return hook

    def _stop(self, reason: str) -> str:
        self._stop_reason = reason
        return reason

    def _runtime_loss_pct(self) -> float | None:
        a = self._agg
        s, e = a["starting_equity"], a["ending_equity"]
        if s and s > 0 and e is not None:
            return round(max(0.0, s - e) / s * 100.0, 2)
        # equity unavailable: fall back to realized pnl vs starting equity
        if s and s > 0 and a["last_pnl"] is not None:
            return round(max(0.0, -a["last_pnl"]) / s * 100.0, 2)
        return None

    # ── report ────────────────────────────────────────────────────────────────────
    def _build_report(self, worker: Any, worker_cfg: WorkerConfig, started: datetime,
                      ended: datetime, stop_reason: str) -> dict[str, Any]:
        a = self._agg
        learning_safety = getattr(worker, "_learning_safety", None)
        active_mods = len(getattr(worker, "_learning_modifiers", {}) or {})
        realized = a["last_pnl"]
        if realized is None and a["starting_equity"] is not None and a["ending_equity"] is not None:
            realized = round(a["ending_equity"] - a["starting_equity"], 2)
        warnings = list(self._warnings)
        warnings += list(getattr(worker, "_learning_warns", []) or [])
        return {
            "session_id": self._session_id,
            "mode": worker_cfg.mode, "armed": self.cfg.armed,
            "safety_supervisor": "always_on",
            "live_trading": "never",
            "started_at": started.isoformat(), "ended_at": ended.isoformat(),
            "duration_seconds": round((ended - started).total_seconds(), 1),
            "symbol": self.cfg.symbol, "risk_mode": self.cfg.risk_mode,
            "timeframe": self.cfg.timeframe,
            "learning_enabled": bool(self.cfg.use_learning_modifiers),
            "learning_contract_ok": (learning_safety or {}).get("allowed"),
            "active_modifiers_count": active_mods,
            "iterations": a["iterations"],
            "decisions": {"long": a["long"], "short": a["short"], "no_trade": a["no_trade"]},
            "long_count": a["long"], "short_count": a["short"], "no_trade_count": a["no_trade"],
            "macro_lockout_count": a["macro_lockout"],
            "demo_orders_attempted": a["orders_attempted"],
            "demo_orders_sent": a["orders_sent"],
            "blocked_by_safety_count": a["blocked_by_safety"],
            "blocked_reasons": a["blocked_reasons"],
            "starting_equity": a["starting_equity"], "ending_equity": a["ending_equity"],
            "realized_pnl": realized,
            "runtime_loss_pct": self._runtime_loss_pct(),
            "stop_reason": stop_reason,
            "limits": {"duration_minutes": self.cfg.duration_minutes,
                       "max_iterations": self.cfg.max_iterations,
                       "max_trades": self.cfg.max_trades,
                       "max_runtime_loss_pct": self.cfg.max_runtime_loss_pct},
            "warnings": warnings,
            "generated_at": self._now().isoformat(),
        }

    # ── output ──────────────────────────────────────────────────────────────────
    def _emit(self, event: str, data: dict) -> None:
        if self._events_fh is None:
            return
        line = {"recorded_at": self._now().isoformat(), "session_id": self._session_id,
                "event": event, **data}
        try:
            self._events_fh.write(json.dumps(line, default=str) + "\n")
        except (OSError, ValueError):
            pass  # event log is best-effort; never break the session

    def _print_banner(self, armed: bool) -> None:
        self._print("=" * 64)
        self._print(" GOLD BOT DEMO AUTO-SESSION")
        self._print("   MT5 DEMO ONLY      NEVER LIVE")
        self._print("   SAFETY SUPERVISOR ALWAYS ON")
        self._print("   LEARNING CONFIDENCE-ONLY")
        self._print("=" * 64)
        self._print(f" symbol/TF    : {self.cfg.symbol} / {self.cfg.timeframe}   risk {self.cfg.risk_mode}")
        self._print(f" duration     : {self.cfg.duration_minutes} min   interval {self.cfg.interval_seconds}s"
                    f"   max-trades {self.cfg.max_trades}   max-iter {self.cfg.max_iterations}")
        self._print(f" learning     : {'enabled' if self.cfg.use_learning_modifiers else 'disabled'}"
                    f" (demo-only, confidence-only)")
        if armed:
            self._print(" execution    : DEMO ARMED (--confirm-demo-session) - orders may be sent on the")
            self._print("                demo account, still gated by worker demo flags + risk gate + supervisor.")
        else:
            self._print(" execution    : OBSERVE ONLY - no --confirm-demo-session, NO orders will be sent.")
        self._print("=" * 64)

    def _print_summary(self, report: dict, report_path: Path) -> None:
        d = report
        self._print(f"\n session ended: {d['stop_reason']}   ({d['duration_seconds']}s, "
                    f"{d['iterations']} iteration(s))")
        self._print(f" decisions    : LONG {d['long_count']}  SHORT {d['short_count']}  "
                    f"NO_TRADE {d['no_trade_count']}  macro_lockout {d['macro_lockout_count']}")
        self._print(f" demo orders  : attempted {d['demo_orders_attempted']}  sent {d['demo_orders_sent']}"
                    f"   blocked_by_safety {d['blocked_by_safety_count']} {d['blocked_reasons'] or ''}")
        self._print(f" equity       : start {d['starting_equity']}  end {d['ending_equity']}  "
                    f"realized {d['realized_pnl']}  runtime_loss {d['runtime_loss_pct']}%")
        for w in d["warnings"]:
            self._print(f"   warning - {w}")
        self._print(f" report       : {report_path}")
        self._print(f"                {self.sessions_dir / 'session_latest.json'}")
        self._print(" demo-only: never live, supervisor always on, learning confidence-only, "
                    "orders need --confirm-demo-session + the worker demo flags.")
