"""
scripts/run_binance_trade_stream_smoke.py
------------------------------------------
LM63B/C — Smoke runner for the Binance Spot aggTrade collector + the local
whale alert pipeline (event detection → filter → Discord formatter →
optional webhook send).

Pipeline:
    aggTrade WS message
      → parse_agg_trade_message
      → normalize_agg_trade_to_whale_input
      → (drop if notional_usd < --min-notional)
      → detect_whale_events
      → should_send_whale_alert
      → format_whale_discord_alert    (when sendable)
      → send_discord_webhook          (only when --send-discord is set
                                       AND --discord-webhook-url is supplied)

Defaults are safe:
    --send-discord defaults to False (no network beyond the public Binance WS)
    --max-events defaults to 10
    --min-confidence defaults to 0.6
    --print-payload defaults to False
    NO Supabase. NO secrets required for read-only use.

Usage:
    # Just observe — no Discord, stops after 10 sendable events:
    python scripts/run_binance_trade_stream_smoke.py \\
        --symbols BTCUSDT,ETHUSDT,SOLUSDT --min-notional 250000

    # With Discord (need a real webhook URL):
    python scripts/run_binance_trade_stream_smoke.py \\
        --send-discord --discord-webhook-url https://discord.com/api/...

Requires `pip install websocket-client` for the live WS transport.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

# Make the repo root importable when run directly.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from services.connectors.binance_trade_stream import (  # noqa: E402
    is_valid_binance_symbol,
    iter_binance_aggtrades,
)
from services.whale_alert_engine import detect_whale_events           # noqa: E402
from services.whale_alert_filter import should_send_whale_alert       # noqa: E402
from services.whale_discord_formatter import format_whale_discord_alert  # noqa: E402
from services.discord_webhook_sender import send_discord_webhook      # noqa: E402


DEFAULT_SYMBOLS       = "BTCUSDT,ETHUSDT,SOLUSDT"
DEFAULT_MIN_NOTIONAL  = 250_000.0
DEFAULT_MAX_EVENTS    = 10
DEFAULT_MIN_CONFIDENCE = 0.6


# ── CLI parsing ───────────────────────────────────────────────────────────────

def _split_symbols(raw: str) -> list[str]:
    return [s.strip().upper() for s in raw.split(",") if s.strip()]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="run_binance_trade_stream_smoke",
        description=(
            "Stream Binance Spot aggTrade fills, build whale events, run the "
            "filter, format Discord payloads, and (optionally) POST them. "
            "Safe defaults: no Discord send, no Supabase."
        ),
    )
    parser.add_argument(
        "--symbols", default=DEFAULT_SYMBOLS,
        help=f"Comma-separated symbols (default: {DEFAULT_SYMBOLS}).",
    )
    parser.add_argument(
        "--min-notional", type=float, default=DEFAULT_MIN_NOTIONAL,
        dest="min_notional",
        help=(f"Minimum trade notional in USD to qualify as a whale event "
              f"(default: ${int(DEFAULT_MIN_NOTIONAL):,})."),
    )
    parser.add_argument(
        "--max-events", type=int, default=DEFAULT_MAX_EVENTS,
        dest="max_events",
        help=(f"Stop after N produced whale events (default: "
              f"{DEFAULT_MAX_EVENTS}). 0 or negative disables the cap."),
    )
    parser.add_argument(
        "--min-confidence", type=float, default=DEFAULT_MIN_CONFIDENCE,
        dest="min_confidence",
        help=(f"Minimum event confidence in [0, 1]. Events below this are "
              f"flagged and never sent to Discord (default: "
              f"{DEFAULT_MIN_CONFIDENCE})."),
    )
    parser.add_argument(
        "--send-discord", action="store_true", default=False,
        dest="send_discord",
        help=("Actually POST sendable events to the Discord webhook. "
              "Requires --discord-webhook-url. Default: off."),
    )
    parser.add_argument(
        "--discord-webhook-url", default="", dest="discord_webhook_url",
        help=("Discord webhook URL. Required when --send-discord is set. "
              "Pass via shell env, never commit it."),
    )
    parser.add_argument(
        "--print-payload", action="store_true", default=False,
        dest="print_payload",
        help=("Print the formatted Discord payload (JSON) after each "
              "sendable event."),
    )
    return parser.parse_args(argv)


# ── Pipeline ──────────────────────────────────────────────────────────────────

def _fmt_event_line(item: dict, filter_result: dict, blocked_low_conf: bool) -> str:
    """Build the one-line human-readable summary printed per event."""
    sym  = str(item.get("symbol", "?"))
    side = str(item.get("side", "?")).upper()
    notional = float(item.get("notional_usd", 0) or 0)
    severity = str(filter_result.get("severity") or item.get("severity") or "—")
    conf = float(item.get("confidence", 0) or 0)
    should_send = bool(filter_result.get("should_send"))
    reason = str(filter_result.get("reason") or "")
    sendable = should_send and not blocked_low_conf
    flag = "YES" if sendable else "no "
    extra = ""
    if should_send and blocked_low_conf:
        extra = "  [blocked: below --min-confidence]"
    return (
        f"{sym:>9} {side:<4} ${notional:>14,.0f}  "
        f"{severity:<8} conf {conf:.2f}  send={flag}  reason='{reason}'{extra}"
    )


def run_pipeline(
    *,
    args: argparse.Namespace,
    message_iter: Optional[Iterable[Any]] = None,
    sender: Callable[..., dict] = send_discord_webhook,
    print_fn: Callable[[str], None] = print,
    err_fn: Optional[Callable[[str], None]] = None,
) -> dict:
    """
    Drive the aggTrade → whale → filter → [Discord] pipeline.

    Network-free when ``message_iter`` is provided. The Discord sender is
    dependency-injected so tests can assert it was (or wasn't) called.

    Args:
        args:         Result of ``parse_args``.
        message_iter: Optional pre-supplied iterable of raw WS frames
                      (str/bytes/dict). When None, the real Binance WS
                      is opened lazily.
        sender:       Callable matching ``send_discord_webhook`` signature
                      ``(payload, webhook_url=...) -> {"ok": bool, ...}``.
        print_fn:     Where to write human-readable event lines.
        err_fn:       Where to write diagnostic / error lines. Defaults
                      to stderr.

    Returns:
        Counters: ``{seen, parsed, below_threshold, events, sendable,
        sent, send_failures, blocked_low_confidence, stopped_reason}``.
    """
    if err_fn is None:
        def err_fn(msg: str) -> None:    # type: ignore[misc]
            print(msg, file=sys.stderr, flush=True)

    counters: dict[str, Any] = {
        "seen":                   0,
        "parsed":                 0,
        "below_threshold":        0,
        "events":                 0,
        "sendable":               0,
        "sent":                   0,
        "send_failures":          0,
        "blocked_low_confidence": 0,
        "stopped_reason":         "exhausted",
    }

    # Resolve and validate symbols
    raw_symbols = _split_symbols(args.symbols)
    if not raw_symbols:
        err_fn("error: --symbols cannot be empty")
        counters["stopped_reason"] = "no_symbols"
        return counters

    valid = [s for s in raw_symbols if is_valid_binance_symbol(s)]
    skipped = [s for s in raw_symbols if s not in valid]
    if skipped:
        err_fn(f"  skipping invalid symbols: {', '.join(skipped)}")
    if not valid:
        err_fn("error: no valid Binance Spot symbols supplied "
               "(expect A-Z/0-9, 3-12 chars)")
        counters["stopped_reason"] = "no_valid_symbols"
        return counters

    if args.min_notional < 0:
        err_fn("error: --min-notional must be >= 0")
        counters["stopped_reason"] = "bad_min_notional"
        return counters
    if not (0.0 <= args.min_confidence <= 1.0):
        err_fn("error: --min-confidence must be in [0, 1]")
        counters["stopped_reason"] = "bad_min_confidence"
        return counters

    # Hard guard: Discord send requires a webhook URL. Never crash; return cleanly.
    if args.send_discord and not args.discord_webhook_url:
        err_fn("error: --send-discord set but --discord-webhook-url is empty; "
               "refusing to send")
        counters["stopped_reason"] = "missing_webhook"
        return counters

    max_events_cap = int(args.max_events) if args.max_events and args.max_events > 0 else None

    err_fn(
        "binance aggTrade smoke runner starting "
        f"· symbols={','.join(valid)} · min_notional=${args.min_notional:,.0f} "
        f"· min_confidence={args.min_confidence:.2f} "
        f"· max_events={max_events_cap if max_events_cap is not None else '∞'} "
        f"· send_discord={'YES' if args.send_discord else 'no'}"
    )

    try:
        stream = iter_binance_aggtrades(valid, message_iter=message_iter, progress=err_fn)
    except (ValueError, RuntimeError) as exc:
        err_fn(f"error: {exc}")
        counters["stopped_reason"] = "stream_error"
        return counters

    try:
        for item in stream:
            counters["seen"] += 1
            counters["parsed"] += 1

            notional = float(item.get("notional_usd", 0) or 0)
            if notional < args.min_notional:
                counters["below_threshold"] += 1
                continue

            # Threshold the engine to the same notional floor — `detect_whale_events`
            # is also responsible for severity classification.
            events = detect_whale_events(
                [item],
                options={"min_notional_usd": args.min_notional},
            )
            if not events:
                # Engine rejected (e.g. allowed/blocked lists) — count as below threshold.
                counters["below_threshold"] += 1
                continue

            for ev in events:
                counters["events"] += 1

                filter_result = should_send_whale_alert(
                    ev, options={"min_confidence": args.min_confidence}
                )
                should_send = bool(filter_result.get("should_send"))
                conf = float(ev.get("confidence", 0) or 0)
                blocked_low_conf = should_send and conf < args.min_confidence
                if blocked_low_conf:
                    counters["blocked_low_confidence"] += 1

                print_fn(_fmt_event_line(ev, filter_result, blocked_low_conf))

                sendable = should_send and not blocked_low_conf
                if sendable:
                    counters["sendable"] += 1
                    payload = format_whale_discord_alert(ev)
                    if payload is None:
                        err_fn(f"  format failed for {ev.get('symbol')} — skipping")
                    else:
                        if args.print_payload:
                            print_fn(json.dumps(payload, sort_keys=True))
                        if args.send_discord:
                            try:
                                result = sender(
                                    payload, webhook_url=args.discord_webhook_url,
                                )
                            except Exception as exc:  # pragma: no cover - defensive
                                counters["send_failures"] += 1
                                err_fn(f"  webhook send failed: {exc}")
                            else:
                                if isinstance(result, dict) and result.get("ok"):
                                    counters["sent"] += 1
                                else:
                                    counters["send_failures"] += 1
                                    err_fn(f"  webhook send returned: {result!r}")

                if max_events_cap is not None and counters["events"] >= max_events_cap:
                    counters["stopped_reason"] = "max_events"
                    return counters

    except KeyboardInterrupt:
        err_fn("interrupted — stopping cleanly")
        counters["stopped_reason"] = "interrupted"

    return counters


# ── Entry point ───────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    counters = run_pipeline(args=args)

    print(
        "\n  summary: "
        f"seen={counters['seen']} "
        f"events={counters['events']} "
        f"sendable={counters['sendable']} "
        f"sent={counters['sent']} "
        f"send_failures={counters['send_failures']} "
        f"blocked_low_conf={counters['blocked_low_confidence']} "
        f"stopped={counters['stopped_reason']}",
        file=sys.stderr,
        flush=True,
    )
    # Reasonable exit codes: 0 normal, 2 for config errors so CI can flag.
    config_errors = {
        "no_symbols", "no_valid_symbols", "bad_min_notional",
        "bad_min_confidence", "missing_webhook",
    }
    return 2 if counters["stopped_reason"] in config_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
