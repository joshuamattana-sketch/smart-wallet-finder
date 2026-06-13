"""
services/gold_bot_discord_review_sender.py
--------------------------------------------
LM90B - Optional Discord sender for the LM90A session review digest.

Reads the already-built local review files (data/gold_bot/reviews/
session_review_latest.json / .md) and TRANSMITS a concise session review to a
Discord channel. It adds NO trading logic - it only formats + posts the digest.

Safety / secrets:
  * The webhook URL comes ONLY from the env var LUMORA_GOLD_DISCORD_WEBHOOK_URL
    (or an explicit arg) - never hardcoded, never committed, never printed in full
    (use redact_webhook()).
  * Nothing is sent unless the caller explicitly asks (the CLI requires
    --send-discord). The preview path makes no network call.
  * No MT5, no orders, no live trading. HTTP is stdlib urllib only (reuses the
    LM51B sender) - no new dependencies.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from services.discord_webhook_sender import send_discord_webhook

_REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REVIEWS_DIR = _REPO_ROOT / "data" / "gold_bot" / "reviews"
DEFAULT_REVIEW_JSON = DEFAULT_REVIEWS_DIR / "session_review_latest.json"
DEFAULT_REVIEW_MD = DEFAULT_REVIEWS_DIR / "session_review_latest.md"

WEBHOOK_ENV = "LUMORA_GOLD_DISCORD_WEBHOOK_URL"
DISCORD_CONTENT_LIMIT = 2000


# ── secrets hygiene ────────────────────────────────────────────────────────────────
def redact_webhook(url: str | None) -> str:
    """Never expose the token. Returns a safe, loggable placeholder."""
    if not url or not str(url).strip():
        return "(unset)"
    if "discord.com/api/webhooks" in url or "discordapp.com/api/webhooks" in url:
        return "https://discord.com/api/webhooks/...REDACTED"
    return "...REDACTED"


def resolve_webhook(webhook_url: str | None = None) -> str | None:
    """Explicit arg wins; else the gold-specific env var. Never echoed back."""
    if isinstance(webhook_url, str) and webhook_url.strip():
        return webhook_url.strip()
    env = os.environ.get(WEBHOOK_ENV, "")
    return env.strip() if isinstance(env, str) and env.strip() else None


# ── review loading ─────────────────────────────────────────────────────────────────
def load_review(*, review_json: str | Path = DEFAULT_REVIEW_JSON,
                review_md: str | Path | None = DEFAULT_REVIEW_MD
                ) -> tuple[dict | None, str | None, list[str]]:
    """
    Load the LM90A review JSON (required for structured fields) + optional Markdown
    excerpt. Returns (review, markdown, warnings). Missing JSON -> (None, _, [error]).
    """
    warnings: list[str] = []
    pj = Path(review_json)
    if not pj.exists():
        return None, None, [f"No session review found at {pj}. "
                            "Run run_gold_bot_session_review.py first."]
    try:
        review = json.loads(pj.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return None, None, [f"review JSON unreadable: {exc}"]
    md = None
    if review_md is not None:
        pm = Path(review_md)
        if pm.exists():
            try:
                md = pm.read_text(encoding="utf-8")
            except OSError:
                warnings.append(f"review markdown unreadable: {pm}")
        else:
            warnings.append(f"review markdown missing: {pm}")
    return review, md, warnings


# ── message formatting (concise, ASCII/console-safe) ────────────────────────────────
def format_message(review: dict, *, max_findings: int = 5, max_actions: int = 5) -> str:
    r = review or {}
    dc = r.get("decision_counts") or {}
    oc = r.get("order_counts") or {}
    outc = r.get("outcome_summary") or {}
    safe = r.get("safety_summary") or {}
    learn = r.get("learning_summary") or {}

    lines: list[str] = ["**Lumora Gold Bot Session Review**",
                        f"Session: `{r.get('session_id') or 'unknown'}`",
                        f"Mode: {r.get('mode')} | Symbol: {r.get('symbol')} | "
                        f"Risk: {r.get('risk_mode')}",
                        f"Stop: {r.get('stop_reason')}", ""]

    lines.append(f"__Decisions__: LONG {dc.get('long')} / SHORT {dc.get('short')} / "
                 f"NO_TRADE {dc.get('no_trade')}")
    lines.append(f"__Orders__: attempted {oc.get('attempted')} / sent {oc.get('sent')} / "
                 f"blocked {oc.get('blocked_by_safety')}")
    if outc.get("available"):
        lines.append(f"__Outcomes__: {outc.get('wins')}W/{outc.get('losses')}L/"
                     f"{outc.get('breakeven')}BE/{outc.get('open')}open  "
                     f"realized {outc.get('realized_pnl')}")
    else:
        lines.append("__Outcomes__: none matched (symbol/magic) this session")

    blockers = safe.get("top_blockers") or []
    blk = ", ".join(f"{b.get('reason')} x{b.get('count')}" for b in blockers[:3]) or "none"
    cooldown = (" | cooldown ACTIVE" if safe.get("cooldown_active") else "")
    lines.append(f"__Safety__: {blk}{cooldown}")

    mods = learn.get("active_modifiers") or {}
    mod_str = ", ".join(f"{s} {v:+d}" for s, v in list(mods.items())[:4]) or "none"
    cycle = learn.get("latest_cycle_event") or "n/a"
    lines.append(f"__Learning__: modifiers [{mod_str}] | cycle {cycle}")

    findings = (r.get("key_findings") or [])[:max_findings]
    if findings:
        lines += ["", "__Key findings__"] + [f"- {x}" for x in findings]
    actions = (r.get("next_actions") or [])[:max_actions]
    if actions:
        lines += ["", "__Next actions__"] + [f"- {x}" for x in actions]

    content = "\n".join(lines)
    if len(content) > DISCORD_CONTENT_LIMIT:
        content = content[:DISCORD_CONTENT_LIMIT - 20].rstrip() + "\n... (truncated)"
    return content


# ── send (reuses the LM51B stdlib urllib sender) ────────────────────────────────────
def send_review(content: str, *, webhook_url: str | None = None, timeout: float = 10.0) -> dict:
    """
    POST the review content to Discord. Returns the LM51B status dict
    {ok, status_code, error, response_text}. Never raises, never returns the URL.
    """
    url = resolve_webhook(webhook_url)
    if not url:
        return {"ok": False, "status_code": None,
                "error": f"no webhook URL (set env {WEBHOOK_ENV})", "response_text": ""}
    if not (isinstance(content, str) and content.strip()):
        return {"ok": False, "status_code": None, "error": "empty review content",
                "response_text": ""}
    return send_discord_webhook({"content": content}, webhook_url=url, timeout=timeout)
