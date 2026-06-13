"""
tests/test_gold_bot_discord_review_sender.py
---------------------------------------------
LM90B - Optional Discord review sender. HTTP is mocked; no real network, no MT5,
no Discord required.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import services.gold_bot_discord_review_sender as S

_REPO = Path(__file__).resolve().parent.parent


def _review(**kw):
    base = {
        "session_id": "session_x", "mode": "demo", "symbol": "XAUUSD", "risk_mode": "scalp",
        "stop_reason": "consecutive_safety_blocks",
        "decision_counts": {"long": 3, "short": 0, "no_trade": 0, "macro_lockout": 0},
        "order_counts": {"attempted": 3, "sent": 0, "blocked_by_safety": 3,
                         "blocked_reasons": {"mt5_health_guard": 3}},
        "outcome_summary": {"available": True, "wins": 1, "losses": 1, "breakeven": 0, "open": 0,
                            "realized_pnl": 6.0},
        "safety_summary": {"top_blockers": [{"reason": "mt5_health_guard", "count": 3}],
                           "cooldown_active": False},
        "learning_summary": {"active_modifiers": {"momentum": -8, "fvg_retest": -8},
                             "latest_cycle_event": "rejected"},
        "key_findings": [f"finding {i}" for i in range(8)],
        "next_actions": [f"action {i}" for i in range(8)],
    }
    base.update(kw)
    return base


def _write_review(tmp_path, review=None, *, md=True):
    rev = review or _review()
    pj = tmp_path / "session_review_latest.json"
    pj.write_text(json.dumps(rev), encoding="utf-8")
    pm = tmp_path / "session_review_latest.md"
    if md:
        pm.write_text("# review", encoding="utf-8")
    return pj, pm


def _load_cli():
    spec = importlib.util.spec_from_file_location(
        "run_gold_bot_discord_review", _REPO / "scripts" / "run_gold_bot_discord_review.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── redaction ──────────────────────────────────────────────────────────────────────
def test_redact_webhook():
    assert S.redact_webhook("https://discord.com/api/webhooks/123/abcTOKEN") \
        == "https://discord.com/api/webhooks/...REDACTED"
    assert "TOKEN" not in S.redact_webhook("https://discord.com/api/webhooks/123/abcTOKEN")
    assert S.redact_webhook(None) == "(unset)"
    assert S.redact_webhook("") == "(unset)"


# ── loading ──────────────────────────────────────────────────────────────────────────
def test_missing_review_files_clear_error(tmp_path):
    review, md, warns = S.load_review(review_json=tmp_path / "nope.json", review_md=None)
    assert review is None and warns and "Run run_gold_bot_session_review.py first" in warns[0]


def test_load_review_ok(tmp_path):
    pj, pm = _write_review(tmp_path)
    review, md, warns = S.load_review(review_json=pj, review_md=pm)
    assert review["session_id"] == "session_x" and md.startswith("# review")


# ── message formatting ───────────────────────────────────────────────────────────────
def test_format_message_structured():
    msg = S.format_message(_review())
    assert "Lumora Gold Bot Session Review" in msg
    assert "Mode: demo | Symbol: XAUUSD | Risk: scalp" in msg
    assert "LONG 3 / SHORT 0 / NO_TRADE 0" in msg
    assert "attempted 3 / sent 0 / blocked 3" in msg
    assert "1W/1L/0BE/0open" in msg
    assert "mt5_health_guard x3" in msg
    assert "momentum -8" in msg and "cycle rejected" in msg


def test_findings_actions_truncation():
    msg = S.format_message(_review(), max_findings=5, max_actions=5)
    assert "finding 4" in msg and "finding 5" not in msg     # top 5 only
    assert "action 4" in msg and "action 5" not in msg


def test_format_message_no_outcomes():
    msg = S.format_message(_review(outcome_summary={"available": False}))
    assert "none matched" in msg


def test_content_under_discord_limit():
    big = _review(key_findings=["x" * 500 for _ in range(20)],
                  next_actions=["y" * 500 for _ in range(20)])
    msg = S.format_message(big, max_findings=20, max_actions=20)
    assert len(msg) <= S.DISCORD_CONTENT_LIMIT


# ── send (mocked HTTP) ────────────────────────────────────────────────────────────────
def test_send_requires_webhook(monkeypatch):
    monkeypatch.delenv(S.WEBHOOK_ENV, raising=False)
    res = S.send_review("hello")
    assert res["ok"] is False and S.WEBHOOK_ENV in res["error"]


def test_send_success_mocked(monkeypatch):
    captured = {}

    def fake(payload, webhook_url=None, timeout=10.0):
        captured["payload"] = payload
        captured["url"] = webhook_url
        return {"ok": True, "status_code": 204, "error": None, "response_text": ""}

    monkeypatch.setattr(S, "send_discord_webhook", fake)
    res = S.send_review("hello world", webhook_url="https://discord.com/api/webhooks/1/T")
    assert res["ok"] is True and res["status_code"] == 204
    assert captured["payload"] == {"content": "hello world"}


def test_send_http_error_mocked(monkeypatch):
    monkeypatch.setattr(S, "send_discord_webhook",
                        lambda *a, **k: {"ok": False, "status_code": 404, "error": "HTTP 404",
                                         "response_text": "not found"})
    res = S.send_review("x", webhook_url="https://discord.com/api/webhooks/1/T")
    assert res["ok"] is False and res["status_code"] == 404


def test_send_network_error_mocked(monkeypatch):
    monkeypatch.setattr(S, "send_discord_webhook",
                        lambda *a, **k: {"ok": False, "status_code": None,
                                         "error": "network error: refused", "response_text": ""})
    res = S.send_review("x", webhook_url="https://discord.com/api/webhooks/1/T")
    assert res["ok"] is False and "network error" in res["error"]


# ── CLI ───────────────────────────────────────────────────────────────────────────────
def test_cli_preview_default_no_http(tmp_path, monkeypatch, capsys):
    cli = _load_cli()
    pj, pm = _write_review(tmp_path)
    monkeypatch.setattr(S, "send_discord_webhook",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("HTTP called!")))
    rc = cli.main(["--review-json", str(pj), "--review-md", str(pm)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "PREVIEW - NOT SENT" in out and "Lumora Gold Bot Session Review" in out


def test_cli_missing_review_errors(tmp_path):
    cli = _load_cli()
    rc = cli.main(["--review-json", str(tmp_path / "nope.json")])
    assert rc == 1


def test_cli_send_requires_env(tmp_path, monkeypatch):
    cli = _load_cli()
    pj, pm = _write_review(tmp_path)
    monkeypatch.delenv(S.WEBHOOK_ENV, raising=False)
    rc = cli.main(["--review-json", str(pj), "--review-md", str(pm), "--send-discord"])
    assert rc == 2          # no env webhook


def test_cli_send_and_dry_run_conflict(tmp_path):
    cli = _load_cli()
    pj, _pm = _write_review(tmp_path)
    rc = cli.main(["--review-json", str(pj), "--send-discord", "--dry-run"])
    assert rc == 2


def test_cli_send_success_redacts_webhook(tmp_path, monkeypatch, capsys):
    cli = _load_cli()
    pj, pm = _write_review(tmp_path)
    monkeypatch.setenv(S.WEBHOOK_ENV, "https://discord.com/api/webhooks/999/SECRETTOKEN")
    monkeypatch.setattr(S, "send_discord_webhook",
                        lambda *a, **k: {"ok": True, "status_code": 204, "error": None,
                                         "response_text": ""})
    rc = cli.main(["--review-json", str(pj), "--review-md", str(pm), "--send-discord"])
    out = capsys.readouterr().out
    assert rc == 0 and "SENT" in out
    assert "SECRETTOKEN" not in out and "...REDACTED" in out


def test_cli_args_defaults():
    cli = _load_cli()
    args = cli.parse_args([])
    assert args.send_discord is False and args.dry_run is False
    assert args.max_findings == 5 and args.max_actions == 5 and args.timeout_seconds == 10.0


# ── safety: no MT5 / orders / hardcoded webhook ───────────────────────────────────────
def test_no_mt5_imported():
    assert "MetaTrader5" not in sys.modules


def test_sources_have_no_orders_or_hardcoded_webhook():
    # Shipped sources only (test fixtures legitimately use dummy discord-shaped URLs).
    for fname in ("services/gold_bot_discord_review_sender.py",
                  "scripts/run_gold_bot_discord_review.py"):
        src = (_REPO / fname).read_text(encoding="utf-8")
        for forbidden in ("MetaTrader5", ".order_send(", "send_demo_order"):
            assert forbidden not in src, f"{fname}:{forbidden}"
        # no real webhook (token after /webhooks/<id>/) committed
        assert not re.search(r"discord(?:app)?\.com/api/webhooks/\d+/[A-Za-z0-9_\-]{8,}", src), \
            f"{fname} contains a real-looking webhook URL"
