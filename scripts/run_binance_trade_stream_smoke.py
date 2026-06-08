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
import os
import sys
import time
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
from services.whale_symbol_thresholds import (                        # noqa: E402
    DEFAULT_THRESHOLDS,
    get_whale_thresholds_for_symbol,
)
from services.whale_event_journal import append_whale_event_journal   # noqa: E402
from services.whale_event_supabase_writer import (                    # noqa: E402
    write_whale_event_to_supabase,
)


DEFAULT_SYMBOLS       = "BTCUSDT,ETHUSDT,SOLUSDT"
DEFAULT_MIN_NOTIONAL  = 250_000.0       # global fallback when --no-use-symbol-thresholds
DEFAULT_MAX_EVENTS    = 10
DEFAULT_MIN_CONFIDENCE = 0.6            # global fallback when --no-use-symbol-thresholds


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
        "--min-notional", type=float, default=None,
        dest="min_notional",
        help=("Minimum trade notional in USD to qualify as a whale event. "
              "When set, overrides the per-symbol threshold for every "
              "symbol. When omitted, falls back to per-symbol thresholds "
              "(LM63D) or the global fallback "
              f"(${int(DEFAULT_MIN_NOTIONAL):,}) if "
              "--no-use-symbol-thresholds is set."),
    )
    parser.add_argument(
        "--max-events", type=int, default=None,
        dest="max_events",
        help=(f"Stop after N produced whale events. When not provided, the "
              f"default is {DEFAULT_MAX_EVENTS} unless --forever is set, in "
              f"which case the cap is disabled. 0 or negative disables the "
              f"cap explicitly. --forever + --max-events N respects N."),
    )
    parser.add_argument(
        "--min-confidence", type=float, default=None,
        dest="min_confidence",
        help=("Minimum event confidence in [0, 1]. Events below this are "
              "flagged and never sent to Discord. When set, overrides "
              "per-symbol thresholds; otherwise per-symbol values (LM63D) "
              f"apply, or the global fallback ({DEFAULT_MIN_CONFIDENCE}) "
              "if --no-use-symbol-thresholds."),
    )
    parser.add_argument(
        "--use-symbol-thresholds", "--no-use-symbol-thresholds",
        action=argparse.BooleanOptionalAction, default=True,
        dest="use_symbol_thresholds",
        help=("Apply per-symbol whale notional + confidence thresholds "
              "from services/whale_symbol_thresholds.py (default: on). "
              "Use --no-use-symbol-thresholds to fall back to global "
              "defaults for every symbol."),
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
    parser.add_argument(
        "--journal-path", default="", dest="journal_path",
        help=("Optional path to an append-only JSONL whale-event journal. "
              "Used when --target is jsonl or both, or as a back-compat "
              "shortcut: any non-empty value enables JSONL writes."),
    )
    parser.add_argument(
        "--target", default="stdout",
        choices=["stdout", "jsonl", "supabase", "both"],
        dest="target",
        help=("Where to persist whale events. stdout (default): print only — "
              "no journal, no Supabase. jsonl: also append to --journal-path. "
              "supabase: also insert into the whale_events table (requires "
              "SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY in the env). both: "
              "jsonl + supabase."),
    )
    parser.add_argument(
        "--forever", action="store_true", default=False, dest="forever",
        help=("Worker mode: run until SIGINT/Ctrl+C. Disables the default "
              "--max-events cap (an explicit --max-events still wins)."),
    )
    parser.add_argument(
        "--heartbeat-interval", type=float, default=60.0,
        dest="heartbeat_interval",
        help=("Seconds between heartbeat summary lines on stderr. 0 disables "
              "heartbeat logging (default: 60)."),
    )
    parser.add_argument(
        "--use-env-config", action="store_true", default=False,
        dest="use_env_config",
        help=("Read worker config from environment variables: WORKER_SYMBOLS, "
              "WHALE_WORKER_MIN_NOTIONAL, WHALE_WORKER_TARGET, "
              "WHALE_WORKER_FOREVER. Explicit CLI flags always win."),
    )
    return parser.parse_args(argv)


# ── Env config loader (LM63J) ────────────────────────────────────────────────

_TRUTHY = frozenset({"true", "1", "yes", "on"})


def apply_env_config(args: argparse.Namespace, *,
                     env: dict | None = None,
                     argv: list[str] | None = None) -> argparse.Namespace:
    """
    Apply WORKER_* / WHALE_WORKER_* env vars onto an argparse Namespace,
    but only for flags the user did NOT pass explicitly on the command line.

    Returns the (possibly mutated) Namespace for convenience. No-op when
    `args.use_env_config` is falsy.
    """
    if not getattr(args, "use_env_config", False):
        return args
    src = env if env is not None else os.environ
    explicit = {a.lstrip("-").replace("-", "_")
                for a in (argv if argv is not None else sys.argv[1:])
                if a.startswith("--")}

    sym = src.get("WORKER_SYMBOLS", "").strip()
    if sym and "symbols" not in explicit:
        args.symbols = sym

    mn = src.get("WHALE_WORKER_MIN_NOTIONAL", "").strip()
    if mn and "min_notional" not in explicit:
        try:
            args.min_notional = float(mn)
        except ValueError:
            pass  # leave default; bad env values are ignored

    tgt = src.get("WHALE_WORKER_TARGET", "").strip()
    if tgt and "target" not in explicit:
        if tgt in ("stdout", "jsonl", "supabase", "both"):
            args.target = tgt

    forever = src.get("WHALE_WORKER_FOREVER", "").strip().lower()
    if forever and "forever" not in explicit:
        if forever in _TRUTHY:
            args.forever = True

    return args


# ── Pipeline ──────────────────────────────────────────────────────────────────

def supabase_env_ready(env: dict | None = None) -> tuple[bool, str]:
    """
    Return (ok, error_msg). `ok=True` when SUPABASE_URL and
    SUPABASE_SERVICE_ROLE_KEY are both present and non-empty.
    """
    src = env if env is not None else os.environ
    url = (src.get("SUPABASE_URL", "") or "").strip()
    key = (src.get("SUPABASE_SERVICE_ROLE_KEY", "") or "").strip()
    missing: list[str] = []
    if not url: missing.append("SUPABASE_URL")
    if not key: missing.append("SUPABASE_SERVICE_ROLE_KEY")
    if missing:
        return False, f"missing {', '.join(missing)}"
    return True, ""


def resolve_max_events(args: argparse.Namespace) -> Optional[int]:
    """
    Compute the effective max_events cap given --forever and --max-events.

    Rules:
      - Explicit --max-events N (N > 0) → cap = N
      - Explicit --max-events <= 0      → cap disabled (None)
      - Omitted + --forever             → cap disabled (None)
      - Omitted + no --forever          → cap = DEFAULT_MAX_EVENTS (10)
    """
    explicit = args.max_events
    if explicit is not None:
        return explicit if explicit > 0 else None
    return None if getattr(args, "forever", False) else DEFAULT_MAX_EVENTS


def format_heartbeat(counters: dict, uptime_seconds: float) -> str:
    """One-line summary used both by the periodic worker tick and the end log."""
    return (
        f"heartbeat · uptime={uptime_seconds:.0f}s · "
        f"seen={counters.get('seen', 0)} "
        f"events={counters.get('events', 0)} "
        f"sendable={counters.get('sendable', 0)} "
        f"sent={counters.get('sent', 0)} "
        f"supabase_writes={counters.get('supabase_writes', 0)} "
        f"supabase_duplicates={counters.get('supabase_duplicates', 0)} "
        f"supabase_failures={counters.get('supabase_failures', 0)} "
        f"journaled={counters.get('journaled', 0)} "
        f"journal_failures={counters.get('journal_failures', 0)}"
    )


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
    supabase_writer: Callable[..., dict] = write_whale_event_to_supabase,
    print_fn: Callable[[str], None] = print,
    err_fn: Optional[Callable[[str], None]] = None,
    env: Optional[dict] = None,
    now: Callable[[], float] = time.monotonic,
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
        "journaled":              0,
        "journal_failures":       0,
        "supabase_writes":        0,
        "supabase_duplicates":    0,
        "supabase_failures":      0,
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

    if args.min_notional is not None and args.min_notional < 0:
        err_fn("error: --min-notional must be >= 0")
        counters["stopped_reason"] = "bad_min_notional"
        return counters
    if args.min_confidence is not None and not (0.0 <= args.min_confidence <= 1.0):
        err_fn("error: --min-confidence must be in [0, 1]")
        counters["stopped_reason"] = "bad_min_confidence"
        return counters

    # Hard guard: Discord send requires a webhook URL. Never crash; return cleanly.
    if args.send_discord and not args.discord_webhook_url:
        err_fn("error: --send-discord set but --discord-webhook-url is empty; "
               "refusing to send")
        counters["stopped_reason"] = "missing_webhook"
        return counters

    # Resolve target → effective sinks. The journal-path flag alone enables
    # journaling for back-compat with LM63E (target='stdout' + journal-path
    # still writes JSONL). Supabase requires an explicit target.
    target = getattr(args, "target", "stdout")
    journal_enabled  = bool(args.journal_path) or target in ("jsonl", "both")
    supabase_enabled = target in ("supabase", "both")

    if target in ("jsonl", "both") and not args.journal_path:
        err_fn("error: --target jsonl|both requires --journal-path")
        counters["stopped_reason"] = "missing_journal_path"
        return counters

    # LM63J: when Supabase is requested, verify env BEFORE we open a websocket.
    if supabase_enabled:
        ok, msg = supabase_env_ready(env)
        if not ok:
            err_fn(f"error: --target {target} requires {msg}")
            counters["stopped_reason"] = "missing_supabase_env"
            return counters

    max_events_cap = resolve_max_events(args)
    heartbeat_interval = float(getattr(args, "heartbeat_interval", 60.0) or 0.0)
    started_at = now()
    last_heartbeat_at: float = started_at

    def _resolve_thresholds_for(symbol: str) -> dict:
        """
        Per-event threshold resolution.

        Priority (highest first):
            1. Explicit CLI override (--min-notional / --min-confidence)
            2. Per-symbol preset from whale_symbol_thresholds (when
               --use-symbol-thresholds is on, default)
            3. Global fallback DEFAULT_THRESHOLDS
        """
        if args.use_symbol_thresholds:
            base = get_whale_thresholds_for_symbol(symbol)
        else:
            base = dict(DEFAULT_THRESHOLDS)
            base["min_notional_usd"] = DEFAULT_MIN_NOTIONAL
            base["min_confidence"]   = DEFAULT_MIN_CONFIDENCE
        if args.min_notional is not None:
            base["min_notional_usd"] = float(args.min_notional)
        if args.min_confidence is not None:
            base["min_confidence"]   = float(args.min_confidence)
        return base

    # Startup banner: describe the threshold mode honestly.
    if args.use_symbol_thresholds and args.min_notional is None and args.min_confidence is None:
        threshold_label = "per-symbol thresholds (LM63D)"
    elif args.use_symbol_thresholds:
        overrides = []
        if args.min_notional is not None:
            overrides.append(f"min_notional=${args.min_notional:,.0f}")
        if args.min_confidence is not None:
            overrides.append(f"min_confidence={args.min_confidence:.2f}")
        threshold_label = "per-symbol thresholds · CLI override: " + ", ".join(overrides)
    else:
        mn = args.min_notional if args.min_notional is not None else DEFAULT_MIN_NOTIONAL
        mc = args.min_confidence if args.min_confidence is not None else DEFAULT_MIN_CONFIDENCE
        threshold_label = f"global min_notional=${mn:,.0f} · min_confidence={mc:.2f}"

    err_fn(
        "binance aggTrade smoke runner starting "
        f"· symbols={','.join(valid)} · {threshold_label} "
        f"· max_events={max_events_cap if max_events_cap is not None else '∞'} "
        f"· forever={'YES' if getattr(args, 'forever', False) else 'no'} "
        f"· heartbeat={heartbeat_interval:.0f}s "
        f"· send_discord={'YES' if args.send_discord else 'no'} "
        f"· target={target} "
        f"· journal={args.journal_path or 'off'} "
        f"· supabase={'on' if supabase_enabled else 'off'}"
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

            # Worker heartbeat — periodic stderr summary, never crashes the loop.
            if heartbeat_interval > 0:
                t = now()
                if (t - last_heartbeat_at) >= heartbeat_interval:
                    err_fn(format_heartbeat(counters, t - started_at))
                    last_heartbeat_at = t

            item_sym = str(item.get("symbol", ""))
            thresholds = _resolve_thresholds_for(item_sym)
            sym_min_notional   = float(thresholds["min_notional_usd"])
            sym_min_confidence = float(thresholds["min_confidence"])

            notional = float(item.get("notional_usd", 0) or 0)
            if notional < sym_min_notional:
                counters["below_threshold"] += 1
                continue

            # Threshold the engine to the same notional floor — `detect_whale_events`
            # is also responsible for severity classification.
            events = detect_whale_events(
                [item],
                options={"min_notional_usd": sym_min_notional},
            )
            if not events:
                # Engine rejected (e.g. allowed/blocked lists) — count as below threshold.
                counters["below_threshold"] += 1
                continue

            for ev in events:
                counters["events"] += 1

                filter_result = should_send_whale_alert(
                    ev, options={"min_confidence": sym_min_confidence}
                )
                should_send = bool(filter_result.get("should_send"))
                conf = float(ev.get("confidence", 0) or 0)
                blocked_low_conf = should_send and conf < sym_min_confidence
                if blocked_low_conf:
                    counters["blocked_low_confidence"] += 1

                print_fn(_fmt_event_line(ev, filter_result, blocked_low_conf))

                send_result: dict | None = None
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
                                send_result = sender(
                                    payload, webhook_url=args.discord_webhook_url,
                                )
                            except Exception as exc:  # pragma: no cover - defensive
                                counters["send_failures"] += 1
                                err_fn(f"  webhook send failed: {exc}")
                                send_result = {"ok": False, "error": str(exc)}
                            else:
                                if isinstance(send_result, dict) and send_result.get("ok"):
                                    counters["sent"] += 1
                                else:
                                    counters["send_failures"] += 1
                                    err_fn(f"  webhook send returned: {send_result!r}")

                # Build the journal/Supabase meta once — both sinks share it.
                event_meta = {
                    "should_send":      should_send,
                    "filter_reason":    str(filter_result.get("reason") or ""),
                    "blocked_low_conf": blocked_low_conf,
                    "sent_attempted":   bool(args.send_discord and sendable),
                }
                if send_result is not None:
                    event_meta["send_result"] = send_result

                # Sink 1: JSONL journal (LM63E)
                if journal_enabled and args.journal_path:
                    ok = append_whale_event_journal(
                        args.journal_path, ev, meta=event_meta,
                    )
                    if ok:
                        counters["journaled"] += 1
                    else:
                        counters["journal_failures"] += 1
                        err_fn(f"  journal append failed for {ev.get('symbol')}")

                # Sink 2: Supabase whale_events (LM63H)
                if supabase_enabled:
                    try:
                        sb_result = supabase_writer(ev, meta=event_meta)
                    except Exception as exc:  # pragma: no cover - defensive
                        counters["supabase_failures"] += 1
                        err_fn(f"  supabase write raised: {exc}")
                    else:
                        if isinstance(sb_result, dict) and sb_result.get("ok"):
                            if sb_result.get("duplicate"):
                                counters["supabase_duplicates"] += 1
                            else:
                                counters["supabase_writes"] += 1
                        else:
                            counters["supabase_failures"] += 1
                            err_fn(
                                f"  supabase write failed for {ev.get('symbol')}: "
                                f"{sb_result!r}"
                            )

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
    apply_env_config(args, argv=argv if argv is not None else sys.argv[1:])
    counters = run_pipeline(args=args)

    print(
        "\n  summary: "
        f"seen={counters['seen']} "
        f"events={counters['events']} "
        f"sendable={counters['sendable']} "
        f"sent={counters['sent']} "
        f"send_failures={counters['send_failures']} "
        f"blocked_low_conf={counters['blocked_low_confidence']} "
        f"journaled={counters['journaled']} "
        f"journal_failures={counters['journal_failures']} "
        f"supabase_writes={counters['supabase_writes']} "
        f"supabase_duplicates={counters['supabase_duplicates']} "
        f"supabase_failures={counters['supabase_failures']} "
        f"stopped={counters['stopped_reason']}",
        file=sys.stderr,
        flush=True,
    )
    # Reasonable exit codes: 0 normal, 2 for config errors so CI can flag.
    config_errors = {
        "no_symbols", "no_valid_symbols", "bad_min_notional",
        "bad_min_confidence", "missing_webhook", "missing_journal_path",
        "missing_supabase_env",
    }
    return 2 if counters["stopped_reason"] in config_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
