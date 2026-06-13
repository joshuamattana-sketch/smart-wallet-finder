"""
scripts/run_gold_bot_discord_review.py
----------------------------------------
LM90B - Preview / send the LM90A Gold Bot session review to Discord.

DEFAULT = preview only (prints the message, makes NO network call). Sending
requires BOTH --send-discord AND the env var LUMORA_GOLD_DISCORD_WEBHOOK_URL.
The webhook URL is never printed in full (redacted). No MT5, no orders.

Run from repo root:
    # preview only (no send, no env needed):
    python scripts/run_gold_bot_discord_review.py

    # send intentionally (PowerShell):
    $env:LUMORA_GOLD_DISCORD_WEBHOOK_URL = "YOUR_WEBHOOK_URL"
    python scripts/run_gold_bot_discord_review.py --send-discord
    Remove-Item Env:LUMORA_GOLD_DISCORD_WEBHOOK_URL
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from services.gold_bot_discord_review_sender import (  # noqa: E402
    DEFAULT_REVIEW_JSON,
    DEFAULT_REVIEW_MD,
    WEBHOOK_ENV,
    format_message,
    load_review,
    redact_webhook,
    resolve_webhook,
    send_review,
)


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="run_gold_bot_discord_review",
        description="Preview/send the Gold Bot session review to Discord (preview by default).",
    )
    p.add_argument("--review-md", default=str(DEFAULT_REVIEW_MD), dest="review_md")
    p.add_argument("--review-json", default=str(DEFAULT_REVIEW_JSON), dest="review_json")
    p.add_argument("--send-discord", action="store_true", dest="send_discord",
                   help="Actually POST to Discord (requires the env webhook). Default: preview only.")
    p.add_argument("--dry-run", action="store_true", dest="dry_run",
                   help="Force preview only (never sends, even with --send-discord).")
    p.add_argument("--max-findings", type=int, default=5, dest="max_findings")
    p.add_argument("--max-actions", type=int, default=5, dest="max_actions")
    p.add_argument("--timeout-seconds", type=float, default=10.0, dest="timeout_seconds")
    p.add_argument("--json", action="store_true", dest="json_output")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)

    if args.send_discord and args.dry_run:
        print("error: pass either --send-discord OR --dry-run, not both.", file=sys.stderr)
        return 2

    review, markdown, warnings = load_review(review_json=args.review_json, review_md=args.review_md)
    if review is None:
        print(warnings[0] if warnings else "No session review found.", file=sys.stderr)
        return 1

    content = format_message(review, max_findings=args.max_findings, max_actions=args.max_actions)
    will_send = args.send_discord and not args.dry_run

    if not will_send:
        if args.json_output:
            print(json.dumps({"mode": "preview", "sent": False, "content": content,
                              "warnings": warnings}, indent=2))
        else:
            print("=" * 70)
            print(" GOLD BOT DISCORD REVIEW   (PREVIEW - NOT SENT)")
            print("=" * 70)
            for w in warnings:
                print(f"   warning - {w}")
            print(content)
            print("\n" + "=" * 70)
            print(f" Preview only. To send: --send-discord with env {WEBHOOK_ENV} set.")
            print(" No network call was made. No MT5, no orders.")
        return 0

    # ── send path ──────────────────────────────────────────────────────────────
    url = resolve_webhook()
    if not url:
        print(f"error: --send-discord requires the env var {WEBHOOK_ENV} "
              "(never commit it).", file=sys.stderr)
        return 2

    result = send_review(content, webhook_url=url, timeout=args.timeout_seconds)
    target = redact_webhook(url)
    if args.json_output:
        print(json.dumps({"mode": "send", "sent": result.get("ok"), "target": target,
                          "status_code": result.get("status_code"), "error": result.get("error")},
                         indent=2))
        return 0 if result.get("ok") else 1

    print(f" target  : {target}")
    if result.get("ok"):
        print(f" SENT    : Discord accepted the review (HTTP {result.get('status_code')}).")
        return 0
    print(f" FAILED  : {result.get('error')} (HTTP {result.get('status_code')}).", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
