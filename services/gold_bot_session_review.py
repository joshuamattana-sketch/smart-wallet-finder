"""
services/gold_bot_session_review.py
-------------------------------------
LM90A - Local session review digest for the Gold Bot (OFFLINE reporting layer).

Joins the artifacts the LM86-LM89 loop already writes - a demo session report
(LM88A), its event log, reconstructed trade outcomes (LM89A), safety events +
state (LM87A), learning events + cycle summaries (LM86A/C/89B) - into ONE
human-readable Markdown + machine-readable JSON review. This makes the bot's
autonomous demo behavior legible BEFORE any Discord/UI surface is wired.

Pure + offline: reads local JSON/JSONL only. No MT5, no orders, no HTTP,
no secrets, no strategy change. Missing inputs degrade to warnings, never crash.
The builders are pure (take parsed dicts) so unit tests use fake temp files.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DATA = _REPO_ROOT / "data" / "gold_bot"
DEFAULT_REVIEWS_DIR = _DATA / "reviews"
DEFAULT_SESSIONS_DIR = _DATA / "sessions"
DEFAULT_LEARNING_DIR = _DATA / "learning"
DEFAULT_SAFETY_DIR = _DATA / "safety"
DEFAULT_TRADE_OUTCOMES_DIR = _DATA / "trade_outcomes"
DEFAULT_SESSION_FILE = DEFAULT_SESSIONS_DIR / "session_latest.json"

_STATUS_KEYS = ("promising", "weak", "avoid", "insufficient_sample", "mixed")


# ── small IO helpers (best-effort) ─────────────────────────────────────────────────
def read_json(path: str | Path) -> tuple[dict | None, str | None]:
    p = Path(path)
    if not p.exists():
        return None, f"missing: {p}"
    try:
        return json.loads(p.read_text(encoding="utf-8")), None
    except (json.JSONDecodeError, OSError) as exc:
        return None, f"unreadable {p.name}: {exc}"


def read_jsonl(path: str | Path) -> tuple[list[dict], str | None]:
    p = Path(path)
    if not p.exists():
        return [], f"missing: {p}"
    rows: list[dict] = []
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except OSError as exc:
        return [], f"unreadable {p.name}: {exc}"
    return rows, None


def _num(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ── review model ────────────────────────────────────────────────────────────────────
@dataclass
class SessionReview:
    session_id: str | None
    generated_at: str
    session_start: str | None = None
    session_end: str | None = None
    mode: str | None = None
    symbol: str | None = None
    risk_mode: str | None = None
    learning_enabled: bool | None = None
    active_modifiers_count: int | None = None
    stop_reason: str | None = None
    duration_seconds: float | None = None
    iterations: int | None = None
    decision_counts: dict = field(default_factory=dict)
    order_counts: dict = field(default_factory=dict)
    safety_summary: dict = field(default_factory=dict)
    outcome_summary: dict = field(default_factory=dict)
    learning_summary: dict = field(default_factory=dict)
    key_findings: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    next_actions: list[str] = field(default_factory=list)
    files_used: dict = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ── Part 2: session summary ──────────────────────────────────────────────────────────
def build_session_summary(report: dict | None) -> dict:
    r = report or {}
    return {
        "available": report is not None,
        "mode": r.get("mode"), "armed": r.get("armed"),
        "session_start": r.get("started_at"), "session_end": r.get("ended_at"),
        "duration_seconds": r.get("duration_seconds"),
        "symbol": r.get("symbol"), "risk_mode": r.get("risk_mode"),
        "iterations": r.get("iterations"),
        "decisions": {"long": r.get("long_count"), "short": r.get("short_count"),
                      "no_trade": r.get("no_trade_count")},
        "macro_lockout_count": r.get("macro_lockout_count"),
        "demo_orders_attempted": r.get("demo_orders_attempted"),
        "demo_orders_sent": r.get("demo_orders_sent"),
        "blocked_by_safety_count": r.get("blocked_by_safety_count"),
        "blocked_reasons": r.get("blocked_reasons") or {},
        "stop_reason": r.get("stop_reason"),
        "starting_equity": r.get("starting_equity"), "ending_equity": r.get("ending_equity"),
        "realized_pnl": r.get("realized_pnl"),
        "learning_enabled": r.get("learning_enabled"),
        "active_modifiers_count": r.get("active_modifiers_count"),
        "outcomes_synced": r.get("outcomes_synced"),
        "outcome_sync_reason": r.get("outcome_sync_reason"),
    }


# ── Part 3: outcome summary ──────────────────────────────────────────────────────────
def build_outcome_summary(outcomes_doc: dict | None) -> dict:
    if not outcomes_doc:
        return {"available": False,
                "note": "No bot trades were matched by symbol/magic for this session."}
    outcomes = outcomes_doc.get("outcomes") or []
    summary = outcomes_doc.get("summary") or {}
    closed = [o for o in outcomes if o.get("outcome") in ("win", "loss", "breakeven")]
    pnls = [(_num(o.get("pnl")), o) for o in closed if _num(o.get("pnl")) is not None]
    largest_win = max((p for p, _ in pnls), default=None)
    largest_loss = min((p for p, _ in pnls), default=None)

    by_setup: dict[str, dict] = {}
    by_side: dict[str, dict] = {}
    exit_reasons: Counter = Counter()
    for o in outcomes:
        oc = o.get("outcome")
        exit_reasons[o.get("exit_reason") or "unknown"] += 1
        for bucket, key in ((by_setup, o.get("setup") or "unknown"),
                            (by_side, o.get("side") or "unknown")):
            b = bucket.setdefault(key, {"count": 0, "wins": 0, "losses": 0, "realized_pnl": 0.0})
            b["count"] += 1
            b["wins"] += oc == "win"
            b["losses"] += oc == "loss"
            b["realized_pnl"] = round(b["realized_pnl"] + (_num(o.get("pnl")) or 0.0), 2)

    open_count = summary.get("open", sum(o.get("outcome") == "open" for o in outcomes))
    return {
        "available": True,
        "count": summary.get("count", len(outcomes)),
        "wins": summary.get("wins", sum(o.get("outcome") == "win" for o in outcomes)),
        "losses": summary.get("losses", sum(o.get("outcome") == "loss" for o in outcomes)),
        "breakeven": summary.get("breakeven", sum(o.get("outcome") == "breakeven" for o in outcomes)),
        "open": open_count,
        "realized_pnl": summary.get("realized_pnl",
                                    round(sum(p for p, _ in pnls), 2) if pnls else 0.0),
        "largest_win": largest_win, "largest_loss": largest_loss,
        "by_setup": by_setup, "by_side": by_side, "exit_reasons": dict(exit_reasons),
        "open_warning": (f"{open_count} open trade(s) still running" if open_count else None),
    }


# ── Part 4: safety summary ───────────────────────────────────────────────────────────
def build_safety_summary(safety_events: list[dict], safety_state: dict | None, *,
                         now: datetime) -> dict:
    events = safety_events or []
    blocking = [e for e in events if not e.get("allowed", True)]
    reasons = Counter(e.get("reason") for e in blocking)
    cooldown_until = (safety_state or {}).get("cooldown_until")
    cooldown_active = False
    if cooldown_until:
        try:
            dt = datetime.fromisoformat(str(cooldown_until).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            cooldown_active = now < dt
        except ValueError:
            cooldown_active = False
    return {
        "available": bool(events) or safety_state is not None,
        "total_events": len(events),
        "critical_count": sum(e.get("severity") == "critical" for e in events),
        "block_count": sum(e.get("severity") == "block" for e in events),
        "warning_count": sum(e.get("severity") == "warning" for e in events),
        "top_blockers": [{"reason": r, "count": c} for r, c in reasons.most_common(5)],
        "kill_switch_events": reasons.get("kill_switch", 0),
        "spread_guard_blocks": reasons.get("spread_guard", 0),
        "mt5_health_blocks": reasons.get("mt5_health_guard", 0),
        "drawdown_blocks": reasons.get("daily_drawdown_guard", 0),
        "loss_streak_events": reasons.get("loss_streak_cooldown", 0),
        "consecutive_losses": (safety_state or {}).get("consecutive_losses"),
        "cooldown_until": cooldown_until, "cooldown_active": cooldown_active,
    }


# ── Part 5: learning summary ─────────────────────────────────────────────────────────
def build_learning_summary(*, learning_events: list[dict], cycle_events: list[dict],
                           latest_cycle: dict | None, active_modifiers: dict | None,
                           scorecard: dict | None) -> dict:
    demo_outcomes = sum(e.get("event") == "demo_trade_outcome" for e in (learning_events or []))
    setup_status: dict[str, int] = {k: 0 for k in _STATUS_KEYS}
    contradictions: list[str] = []
    sc_status = None
    if scorecard:
        sc_status = (scorecard.get("global") or {}).get("recommended_status")
        for s, v in (scorecard.get("by_setup") or {}).items():
            st = v.get("recommended_status_combined") or v.get("recommended_status")
            if st in setup_status:
                setup_status[st] += 1
            if v.get("real_contradicts_replay"):
                contradictions.append(s)

    mods = (active_modifiers or {}).get("modifiers") or {}
    cycle = latest_cycle or {}
    if not cycle and cycle_events:
        last = cycle_events[-1]
        cycle = {"accepted": last.get("event") == "accepted", "reason": last.get("reason"),
                 "cycle_id": last.get("cycle_id"), "event": last.get("event")}
    return {
        "available": bool(scorecard or active_modifiers or cycle_events or learning_events),
        "scorecard_status": sc_status,
        "active_modifiers_count": (active_modifiers or {}).get("active_count", len(mods)),
        "active_modifiers": {s: e.get("confidence_modifier") for s, e in mods.items()
                             if isinstance(e, dict)},
        "modifiers_expires_at": (active_modifiers or {}).get("expires_at"),
        "latest_cycle_event": cycle.get("event") or (
            "accepted" if cycle.get("accepted") else "rejected" if cycle else None),
        "latest_cycle_reason": cycle.get("reason"),
        "real_trades_used": cycle.get("real_trades_used", scorecard.get("include_real_trades")
                                      if scorecard else None),
        "real_trade_count": cycle.get("real_trade_count", demo_outcomes),
        "demo_trade_outcome_events": demo_outcomes,
        "setup_status_breakdown": setup_status,
        "real_contradicts_replay": contradictions,
    }


# ── Part 6/7: findings + next actions (derived only, no hallucination) ───────────────
def derive_key_findings(sess: dict, outc: dict, safe: dict, learn: dict) -> list[str]:
    f: list[str] = []
    if sess.get("available"):
        if sess.get("mode") == "observe" or sess.get("armed") is False:
            f.append("No demo orders were sent because the session was observe-only.")
        elif sess.get("demo_orders_sent") == 0 and (sess.get("blocked_by_safety_count") or 0) > 0:
            top = (safe.get("top_blockers") or [{}])[0].get("reason", "safety")
            extra = " (likely stale tick / market closed)" if top == "mt5_health_guard" else ""
            f.append(f"Armed demo session sent no orders; blocked by {top}{extra}.")
        elif (sess.get("demo_orders_sent") or 0) > 0:
            f.append(f"Armed demo session sent {sess['demo_orders_sent']} demo order(s).")
    for setup, mod in list((learn.get("active_modifiers") or {}).items())[:4]:
        if mod:
            f.append(f"{setup} confidence is adjusted by learning modifier {mod:+d} (demo-only).")
    if outc.get("available"):
        f.append(f"Demo outcomes: {outc.get('count')} trade(s) "
                 f"{outc.get('wins')}W/{outc.get('losses')}L/{outc.get('breakeven')}BE, "
                 f"realized {outc.get('realized_pnl')}.")
        if outc.get("open_warning"):
            f.append(outc["open_warning"] + ".")
    elif sess.get("armed"):
        f.append("No bot trades were matched by symbol/magic for this session.")
    if (learn.get("real_trade_count") or 0) == 0:
        f.append("No real demo outcomes yet; learning is still replay-dominant.")
    if learn.get("latest_cycle_event") == "rejected":
        f.append(f"Latest learning candidate was rejected: {learn.get('latest_cycle_reason')}")
    elif learn.get("latest_cycle_event") == "accepted":
        f.append(f"Latest learning candidate was accepted: {learn.get('latest_cycle_reason')}")
    if learn.get("real_contradicts_replay"):
        f.append("Real demo contradicts replay for: "
                 + ", ".join(learn["real_contradicts_replay"][:5]) + " (small sample).")
    if safe.get("cooldown_active"):
        f.append(f"Loss-streak cooldown is active until {safe.get('cooldown_until')}.")
    return f


def derive_next_actions(sess: dict, outc: dict, safe: dict, learn: dict, *,
                        modifiers_expired: bool) -> list[str]:
    a: list[str] = []
    if not outc.get("available") or (outc.get("count") or 0) == 0:
        a.append("Run a short confirmed demo session when the market is open "
                 "(run_gold_bot_demo_session.py --confirm-demo-session).")
    if (safe.get("block_count", 0) + safe.get("critical_count", 0)) >= 3:
        a.append("Check MT5 tick freshness / spread / session timing (many safety blocks).")
    if modifiers_expired:
        a.append("Refresh learning modifiers (run_gold_bot_learning_cycle.py).")
    if (outc.get("losses") or 0) > 0 or (_num(sess.get("realized_pnl")) or 0) < 0:
        a.append("Let the supervisor cooldown complete; rerun the learning cycle with "
                 "--include-real-trades.")
    if not learn.get("available") or learn.get("latest_cycle_event") is None:
        a.append("Run the LM86C learning cycle (run_gold_bot_learning_cycle.py).")
    if learn.get("scorecard_status") is None:
        a.append("Run the LM86A scorecard (run_gold_bot_learning_scorecard.py).")
    return a


# ── build ─────────────────────────────────────────────────────────────────────────────
def build_review(*, session_report: dict | None, outcomes_doc: dict | None = None,
                 safety_events: list[dict] | None = None, safety_state: dict | None = None,
                 learning_events: list[dict] | None = None, cycle_events: list[dict] | None = None,
                 latest_cycle: dict | None = None, active_modifiers: dict | None = None,
                 scorecard: dict | None = None, files_used: dict | None = None,
                 warnings: list[str] | None = None, now: datetime | None = None) -> SessionReview:
    now = now or datetime.now(timezone.utc)
    sess = build_session_summary(session_report)
    outc = build_outcome_summary(outcomes_doc)
    safe = build_safety_summary(safety_events or [], safety_state, now=now)
    learn = build_learning_summary(
        learning_events=learning_events or [], cycle_events=cycle_events or [],
        latest_cycle=latest_cycle, active_modifiers=active_modifiers, scorecard=scorecard)

    modifiers_expired = False
    exp = learn.get("modifiers_expires_at")
    if exp:
        try:
            dt = datetime.fromisoformat(str(exp).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            modifiers_expired = now > dt
        except ValueError:
            modifiers_expired = False

    findings = derive_key_findings(sess, outc, safe, learn)
    actions = derive_next_actions(sess, outc, safe, learn, modifiers_expired=modifiers_expired)

    return SessionReview(
        session_id=(session_report or {}).get("session_id"),
        generated_at=now.isoformat(),
        session_start=sess["session_start"], session_end=sess["session_end"],
        mode=sess["mode"], symbol=sess["symbol"], risk_mode=sess["risk_mode"],
        learning_enabled=sess["learning_enabled"],
        active_modifiers_count=sess["active_modifiers_count"],
        stop_reason=sess["stop_reason"], duration_seconds=sess["duration_seconds"],
        iterations=sess["iterations"],
        decision_counts={**sess["decisions"], "macro_lockout": sess["macro_lockout_count"]},
        order_counts={"attempted": sess["demo_orders_attempted"], "sent": sess["demo_orders_sent"],
                      "blocked_by_safety": sess["blocked_by_safety_count"],
                      "blocked_reasons": sess["blocked_reasons"]},
        safety_summary=safe, outcome_summary=outc, learning_summary=learn,
        key_findings=findings, warnings=list(warnings or []), next_actions=actions,
        files_used=files_used or {})


# ── Part 8: Markdown ─────────────────────────────────────────────────────────────────
def _row(label: str, value: Any) -> str:
    return f"| {label} | {value} |"


def render_markdown(review: SessionReview) -> str:
    s, o = review.outcome_summary, review.order_counts
    safe, learn = review.safety_summary, review.learning_summary
    dc = review.decision_counts
    L: list[str] = ["# Lumora Gold Bot Session Review", ""]
    L.append(f"**Session** `{review.session_id or 'unknown'}`  -  generated {review.generated_at}")
    L.append("")
    L += ["## Summary", "", "| Field | Value |", "| --- | --- |",
          _row("Mode", review.mode), _row("Symbol / risk", f"{review.symbol} / {review.risk_mode}"),
          _row("Window", f"{review.session_start} -> {review.session_end}"),
          _row("Duration (s)", review.duration_seconds), _row("Iterations", review.iterations),
          _row("Stop reason", review.stop_reason),
          _row("Learning", f"{review.learning_enabled} ({review.active_modifiers_count} modifiers)"),
          ""]
    L += ["## Decisions", "", "| LONG | SHORT | NO_TRADE | macro_lockout |", "| --- | --- | --- | --- |",
          f"| {dc.get('long')} | {dc.get('short')} | {dc.get('no_trade')} | {dc.get('macro_lockout')} |",
          ""]
    L += ["## Orders & Outcomes", "", "| Metric | Value |", "| --- | --- |",
          _row("Orders attempted", o.get("attempted")), _row("Orders sent", o.get("sent")),
          _row("Blocked by safety", o.get("blocked_by_safety")),
          _row("Blocked reasons", o.get("blocked_reasons") or "-")]
    if s.get("available"):
        L += [_row("Outcomes", f"{s.get('count')} ({s.get('wins')}W/{s.get('losses')}L/"
                               f"{s.get('breakeven')}BE/{s.get('open')}open)"),
              _row("Realized PnL", s.get("realized_pnl")),
              _row("Largest win / loss", f"{s.get('largest_win')} / {s.get('largest_loss')}"),
              _row("Exit reasons", s.get("exit_reasons") or "-")]
    else:
        L.append(_row("Outcomes", s.get("note", "none")))
    L.append("")
    L += ["## Safety", "", "| Metric | Value |", "| --- | --- |",
          _row("Events (crit/block/warn)",
               f"{safe.get('critical_count')}/{safe.get('block_count')}/{safe.get('warning_count')}"),
          _row("Top blockers", ", ".join(f"{b['reason']}x{b['count']}"
                                          for b in safe.get("top_blockers", [])) or "-"),
          _row("Consecutive losses", safe.get("consecutive_losses")),
          _row("Cooldown", f"{'ACTIVE until ' + str(safe.get('cooldown_until')) if safe.get('cooldown_active') else 'none'}"),
          ""]
    L += ["## Learning", "", "| Metric | Value |", "| --- | --- |",
          _row("Scorecard status", learn.get("scorecard_status")),
          _row("Active modifiers", learn.get("active_modifiers") or "-"),
          _row("Latest cycle", f"{learn.get('latest_cycle_event')} - {learn.get('latest_cycle_reason')}"),
          _row("Real demo outcomes", f"{learn.get('real_trade_count') or 0} trades"
               + ("; replay-dominant" if not learn.get('real_trade_count') else "; included in learning")),
          _row("Setup status", learn.get("setup_status_breakdown")),
          ""]
    L += ["## Key Findings", ""] + ([f"- {x}" for x in review.key_findings] or ["- (none)"]) + [""]
    L += ["## Next Actions", ""] + ([f"- {x}" for x in review.next_actions] or ["- (none)"]) + [""]
    L += ["## Files Used", ""] + [f"- {k}: {v}" for k, v in review.files_used.items()] + [""]
    L += ["## Warnings", ""] + ([f"- {x}" for x in review.warnings] or ["- (none)"]) + [""]
    return "\n".join(str(x) for x in L)


# ── write ─────────────────────────────────────────────────────────────────────────────
def write_review(out_dir: str | Path, review: SessionReview, markdown: str) -> dict[str, Path]:
    d = Path(out_dir)
    d.mkdir(parents=True, exist_ok=True)
    sid = review.session_id or "unknown"
    md = d / f"session_review_{sid}.md"
    js = d / f"session_review_{sid}.json"
    md_latest = d / "session_review_latest.md"
    js_latest = d / "session_review_latest.json"
    blob = json.dumps(review.to_dict(), indent=2, default=str)
    md.write_text(markdown, encoding="utf-8")
    md_latest.write_text(markdown, encoding="utf-8")
    js.write_text(blob, encoding="utf-8")
    js_latest.write_text(blob, encoding="utf-8")
    return {"markdown": md, "json": js, "markdown_latest": md_latest, "json_latest": js_latest}
