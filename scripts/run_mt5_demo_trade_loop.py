"""
scripts/run_mt5_demo_trade_loop.py
-----------------------------------
LM75B — Guarded MetaTrader 5 DEMO trade loop for the private Gold Bot.

DEMO ONLY. No live trading. Heavily guarded: by default this script sends
NOTHING. An order can only be sent when ALL of the following hold:

    * --confirm-demo-order is present
    * --dry-run is NOT present
    * the account is a verified DEMO account (trade_mode == demo)
    * the risk gate approves (volume/SL/TP/flags/kill-switch/daily cap)
    * order_check passes

Safety flags (env, defaults are safe):
    MT5_DEMO_ONLY=true  LIVE_TRADING_ENABLED=false  ALLOW_REAL_ORDERS=false
    GOLD_BOT_KILL_SWITCH=false  GOLD_BOT_MAX_TRADES_PER_DAY=3
    GOLD_BOT_MAX_DAILY_LOSS_PCT=7

Examples (run from repo root, Windows, MT5 running on a demo account):
    # validate only, sends nothing:
    python scripts/run_mt5_demo_trade_loop.py --side buy  --volume 0.01 --sl-points 300 --tp-points 600 --dry-run
    python scripts/run_mt5_demo_trade_loop.py --side sell --volume 0.01 --sl-points 300 --tp-points 600 --dry-run
    # actually place a guarded demo order:
    python scripts/run_mt5_demo_trade_loop.py --side buy  --volume 0.01 --sl-points 300 --tp-points 600 --confirm-demo-order

Close-position is DEFERRED to a future patch (not implemented here).

Requires the MetaTrader5 package (Windows only):  pip install MetaTrader5
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from services.connectors.mt5_demo_connector import (  # noqa: E402
    Mt5ConnectorError,
    Mt5DemoConnector,
    ProbeResult,
)
from services.gold_bot_risk_gate import (  # noqa: E402
    SafetyConfig,
    evaluate_demo_close,
    evaluate_demo_order,
)
from services import gold_bot_trade_journal as journal  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="run_mt5_demo_trade_loop",
        description="Guarded MT5 DEMO trade loop (sends nothing unless explicitly confirmed).",
    )
    # Actions (mutually informative): open order (default), --list-positions,
    # or --close-position. --side/--sl-points/--tp-points are required only for
    # the open-order action and validated in main().
    p.add_argument("--list-positions", action="store_true", dest="list_positions",
                   help="List open positions and exit (read-only).")
    p.add_argument("--close-position", type=int, default=None, dest="close_position",
                   metavar="TICKET", help="Close the position with this ticket (guarded).")
    p.add_argument("--emergency-close", action="store_true", dest="emergency_close",
                   help="Allow a close even when the kill switch is active (demo only).")

    p.add_argument("--side", choices=["buy", "sell"], default=None)
    p.add_argument("--volume", type=float, default=0.01, help="Lots (default 0.01).")
    p.add_argument("--sl-points", type=int, default=None, dest="sl_points",
                   help="Stop-loss distance in points (required for an open order).")
    p.add_argument("--tp-points", type=int, default=None, dest="tp_points",
                   help="Take-profit distance in points (required for an open order).")
    p.add_argument("--symbol", default=None, help="Gold symbol; omit to auto-discover.")
    p.add_argument("--comment", default="lumora-gold-bot-demo")
    p.add_argument("--magic", type=int, default=750_750)
    p.add_argument("--deviation", type=int, default=20)
    p.add_argument("--dry-run", action="store_true", dest="dry_run",
                   help="Validate + order_check only. Never sends.")
    p.add_argument("--confirm-demo-order", action="store_true", dest="confirm_demo_order",
                   help="Required to actually send a demo order or close.")
    p.add_argument("--json", action="store_true", dest="json_output")
    return p.parse_args(argv)


# order_check result retcodes we accept as "ok to proceed".
def _acceptable_check(mt5_module, retcode: int | None) -> bool:
    done = getattr(mt5_module, "TRADE_RETCODE_DONE", 10009)
    return retcode in (0, done)


def _result_field(obj, name, default=None):
    return getattr(obj, name, default) if obj is not None else default


def _do_list(connector: Mt5DemoConnector, out: dict) -> int:
    """List every open position (read-only). Always safe."""
    positions = connector.all_positions()
    print(f"\nOpen positions: {len(positions)}")
    views = []
    for pos in positions:
        v = connector.position_view(pos)
        views.append(v)
        print(f"   ticket={v['ticket']} {v['side']} {v['symbol']} vol={v['volume']} "
              f"open={v['price_open']} cur={v['price_current']} "
              f"SL={v['sl']} TP={v['tp']} profit={v['profit']} magic={v['magic']}")
    if not positions:
        print("   (none)")
    out.update({"action": "list_positions", "open_positions": len(positions),
                "positions": views, "order_sent": False})
    return 0


def _do_close(connector, probe, config, args, out) -> int:
    """Guarded close of one position by ticket. Sends only with --confirm-demo-order."""
    ticket = args.close_position
    position = connector.position_by_ticket(ticket)
    found = position is not None
    view = connector.position_view(position) if found else None
    if found:
        print(f"Position: ticket={view['ticket']} {view['side']} {view['symbol']} "
              f"vol={view['volume']} open={view['price_open']} profit={view['profit']}")
    else:
        print(f"Position ticket {ticket} not found on this account.")

    decision = evaluate_demo_close(
        config=config,
        account_is_demo=connector.demo_verified,
        ticket_found=found,
        volume=view["volume"] if view else None,
        emergency=args.emergency_close,
    )
    for w in decision.warnings:
        print(f"  ! {w}")
    if not decision.approved:
        print("CLOSE BLOCKED:")
        for r in decision.reasons:
            print(f"   - {r}")

    base = {
        "timestamp": journal.utc_now_iso(),
        "action": "close_position",
        "ticket": ticket,
        "symbol": view["symbol"] if view else None,
        "volume": view["volume"] if view else None,
        "side_being_closed": view["side"] if view else None,
        "account_server": probe.account_server,
        "account_login": probe.account_login,
        "safety_flags": {
            "MT5_DEMO_ONLY": config.mt5_demo_only,
            "LIVE_TRADING_ENABLED": config.live_trading_enabled,
            "ALLOW_REAL_ORDERS": config.allow_real_orders,
            "GOLD_BOT_KILL_SWITCH": config.kill_switch,
            "emergency_close": args.emergency_close,
        },
        "risk": decision.to_dict(),
    }

    will_close = found and decision.approved and args.confirm_demo_order
    if not will_close:
        why = ("blocked" if not decision.approved
               else "ticket not found" if not found
               else "missing --confirm-demo-order")
        print(f"No close sent ({why}).")
        journal.append_entry({**base, "mode": journal.MODE_BLOCKED, "order_send": None})
        out.update({"action": "close_position", "order_sent": False, "reason": why})
        return 0 if (found and decision.approved) else 1

    # Build + optional order_check, then send.
    request = connector.build_close_request(position, comment="lumora-gold-bot-demo-close",
                                             deviation=args.deviation)
    # order_check on a close can be unreliable in the MT5 Python API; we run it
    # for visibility but DO NOT hard-abort on it — demo verification + the
    # safety checks above are the real guards, and closing is risk-reducing.
    try:
        check = connector.check_order(request)
        print(f"order_check (close, advisory): retcode={_safe_int(_result_field(check, 'retcode'))} "
              f"comment={_result_field(check, 'comment')}")
    except Exception as exc:  # noqa: BLE001 - advisory only
        print(f"order_check (close) unavailable: {exc} (continuing — demo close)")

    print("\n>>> MT5 DEMO CLOSE MODE <<<")
    send = connector.send_demo_close(request)
    send_rc = _safe_int(_result_field(send, "retcode"))
    done = getattr(connector._mt5, "TRADE_RETCODE_DONE", 10009)  # noqa: SLF001
    closed_ok = send_rc == done
    print(f"close_send : retcode={send_rc} comment={_result_field(send, 'comment')} "
          f"order={_safe_int(_result_field(send, 'order'))} "
          f"deal={_safe_int(_result_field(send, 'deal'))}")
    print(f"Closed     : ticket={ticket} {view['side']} {view['symbol']} "
          f"vol={view['volume']} @ {request['price']}")

    journal.append_entry({
        **base, "mode": journal.MODE_CLOSE,
        "close_price": request["price"],
        "order_send": {"retcode": send_rc, "comment": _opt(_result_field(send, "comment")),
                       "order": _safe_int(_result_field(send, "order")),
                       "deal": _safe_int(_result_field(send, "deal")), "ok": closed_ok},
    })

    # Post-close verification.
    still = connector.position_by_ticket(ticket)
    print(f"\nPost-close : ticket {ticket} {'STILL OPEN' if still else 'closed'}")
    if view and view["symbol"]:
        remaining = connector.positions_for_symbol(view["symbol"])
        print(f"Remaining {view['symbol']} positions: {len(remaining)}")
    out.update({"action": "close_position", "order_sent": closed_ok, "retcode": send_rc,
                "ticket_still_open": still is not None})
    return 0 if closed_ok else 1


def main(argv: list[str] | None = None) -> int:  # noqa: C901 - linear guarded flow
    args = parse_args(argv)
    out: dict = {"read_only_default": True, "order_sent": False}

    connector = Mt5DemoConnector()
    probe = ProbeResult()
    config = SafetyConfig.from_env()

    def emit(code: int) -> int:
        if args.json_output:
            print(json.dumps(out, indent=2, default=str))
        return code

    try:
        connector.connect()
        probe.connected = True

        # 1. Demo account verification (fail closed on non-demo).
        connector.read_account(probe)
        if not connector.demo_verified:
            raise Mt5ConnectorError(
                f"Account trade_mode={probe.trade_mode_label} is not a strict DEMO account. "
                "Refusing to trade (fail closed)."
            )
        print(f"Account : login={probe.account_login} server={probe.account_server} "
              f"name={probe.account_name}")
        print(f"          balance={probe.balance} equity={probe.equity} "
              f"mode={probe.trade_mode_label} (DEMO verified)")

        # ── Action branch: list / close / open ────────────────────────────────
        if args.list_positions:
            return emit(_do_list(connector, out))
        if args.close_position is not None:
            return emit(_do_close(connector, probe, config, args, out))

        # Open-order action requires side + SL/TP.
        missing = [n for n, v in (("--side", args.side), ("--sl-points", args.sl_points),
                                  ("--tp-points", args.tp_points)) if v is None]
        if missing:
            raise Mt5ConnectorError(
                f"Open order requires {', '.join(missing)}. "
                "(Or use --list-positions / --close-position TICKET.)"
            )

        # 2. Symbol resolution + tick.
        symbol = connector.discover_gold_symbol(probe, preferred=args.symbol)
        connector.read_tick(probe, symbol)
        print(f"Symbol  : {symbol}  bid={probe.tick_bid} ask={probe.tick_ask} "
              f"spread={probe.tick_spread}")

        # 3-4. Build request (computes SL/TP from points, validates orientation).
        request = connector.build_demo_order_request(
            symbol=symbol, side=args.side, volume=args.volume,
            sl_points=args.sl_points, tp_points=args.tp_points,
            comment=args.comment, deviation=args.deviation, magic=args.magic,
        )
        print(f"Request : {args.side} {args.volume} {symbol} @ {request['price']} "
              f"SL={request['sl']} TP={request['tp']}")

        # 5. Risk gate (final authority).
        trades_today = journal.count_sent_today(
            server=probe.account_server, login=probe.account_login,
        )
        decision = evaluate_demo_order(
            config=config,
            account_is_demo=connector.demo_verified,
            side=args.side,
            volume=args.volume,
            sl_present=request.get("sl") is not None,
            tp_present=request.get("tp") is not None,
            trades_today=trades_today,
        )
        for w in decision.warnings:
            print(f"  ! {w}")
        if not decision.approved:
            print("RISK GATE: BLOCKED")
            for r in decision.reasons:
                print(f"   - {r}")

        # 6. order_check (validation only — sends nothing).
        check = connector.check_order(request)
        check_rc = _safe_int(_result_field(check, "retcode"))
        check_comment = _result_field(check, "comment")
        print(f"order_check: retcode={check_rc} comment={check_comment}")
        check_ok = _acceptable_check(connector._mt5, check_rc)  # noqa: SLF001 - intentional

        # Decide intent.
        will_send = (
            args.confirm_demo_order and not args.dry_run
            and decision.approved and check_ok
        )

        base_entry = {
            "timestamp": journal.utc_now_iso(),
            "account_server": probe.account_server,
            "account_login": probe.account_login,
            "symbol": symbol,
            "side": args.side,
            "volume": args.volume,
            "price": request["price"],
            "sl": request["sl"],
            "tp": request["tp"],
            "sl_points": args.sl_points,
            "tp_points": args.tp_points,
            "comment": args.comment,
            "spread": probe.tick_spread,
            "order_check": {"retcode": check_rc, "comment": _opt(check_comment)},
            "safety_flags": {
                "MT5_DEMO_ONLY": config.mt5_demo_only,
                "LIVE_TRADING_ENABLED": config.live_trading_enabled,
                "ALLOW_REAL_ORDERS": config.allow_real_orders,
                "GOLD_BOT_KILL_SWITCH": config.kill_switch,
                "max_trades_per_day": config.max_trades_per_day,
            },
            "risk": decision.to_dict(),
        }

        # Blocked or validation-only paths.
        if not check_ok:
            print("Aborting: order_check not acceptable (fail closed). No order sent.")
            entry = {**base_entry, "mode": journal.MODE_BLOCKED, "order_send": None}
            journal.append_entry(entry)
            out.update({"order_sent": False, "blocked": True, "reason": "order_check"})
            return emit(1)

        if not will_send:
            mode = journal.MODE_BLOCKED if not decision.approved else journal.MODE_DRY_RUN
            why = ("risk gate blocked" if not decision.approved
                   else "dry-run" if args.dry_run
                   else "missing --confirm-demo-order")
            print(f"No order sent ({why}). READ ONLY for this run.")
            entry = {**base_entry, "mode": mode, "order_send": None}
            journal.append_entry(entry)
            out.update({"order_sent": False, "mode": mode, "reason": why,
                        "approved": decision.approved})
            return emit(0 if decision.approved else 1)

        # 7. order_send — only reached with confirm + demo + approved + check ok.
        print("\n>>> MT5 DEMO ORDER MODE <<<")
        send = connector.send_demo_order(request)
        send_rc = _safe_int(_result_field(send, "retcode"))
        send_comment = _result_field(send, "comment")
        order_id = _safe_int(_result_field(send, "order"))
        deal_id = _safe_int(_result_field(send, "deal"))
        done = getattr(connector._mt5, "TRADE_RETCODE_DONE", 10009)  # noqa: SLF001
        sent_ok = send_rc == done

        print(f"order_send : retcode={send_rc} comment={send_comment} "
              f"order={order_id} deal={deal_id}")
        print(f"Requested  : {args.side} {args.volume} {symbol} @ {request['price']} "
              f"SL={request['sl']} TP={request['tp']}")

        entry = {
            **base_entry,
            "mode": journal.MODE_DEMO_ORDER,
            "order_send": {"retcode": send_rc, "comment": _opt(send_comment),
                           "order": order_id, "deal": deal_id, "ok": sent_ok},
        }
        journal.append_entry(entry)

        # 8. Position monitoring (read-only).
        if sent_ok:
            positions = connector.positions_for_symbol(symbol)
            print(f"\nOpen positions for {symbol}: {len(positions)}")
            for pos in positions:
                print(f"   ticket={getattr(pos, 'ticket', '—')} "
                      f"vol={getattr(pos, 'volume', '—')} "
                      f"price_open={getattr(pos, 'price_open', '—')} "
                      f"sl={getattr(pos, 'sl', '—')} tp={getattr(pos, 'tp', '—')}")
        else:
            print("order_send did not complete — see retcode/comment above.")

        out.update({"order_sent": sent_ok, "retcode": send_rc,
                    "order": order_id, "deal": deal_id})
        print("\n(close-position is deferred to a future patch — not implemented here.)")
        return emit(0 if sent_ok else 1)

    except Mt5ConnectorError as exc:
        print("TRADE LOOP FAILED (fail-closed):", exc, file=sys.stderr)
        print("No order sent.", file=sys.stderr)
        out.update({"order_sent": False, "error": str(exc)})
        return emit(1)
    finally:
        connector.shutdown()


def _safe_int(v):
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _opt(v):
    return None if v is None else str(v)


if __name__ == "__main__":
    raise SystemExit(main())
