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
from dataclasses import replace
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
    evaluate_risk_plan,
)
from services.gold_bot_lot_calculator import (  # noqa: E402
    RISK_MODES,
    calc_auto_volume,
    resolve_risk_pct,
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
    p.add_argument("--emergency-close-demo", action="store_true", dest="emergency_close_demo",
                   help="Alias of --emergency-close (demo-only kill-switch override for closes).")

    p.add_argument("--side", choices=["buy", "sell"], default=None)
    p.add_argument("--volume", type=float, default=0.01, help="Manual lots (default 0.01).")
    p.add_argument("--auto-volume", action="store_true", dest="auto_volume",
                   help="Size volume from risk (equity x risk%% / SL loss) instead of --volume.")
    p.add_argument("--risk-mode", choices=list(RISK_MODES), default="balanced", dest="risk_mode",
                   help="Risk posture: safe 0.25%% / balanced 0.50%% / aggressive 1.0%% / experimental 0.10%%.")
    p.add_argument("--risk-pct", type=float, default=None, dest="risk_pct",
                   help="Override risk-per-trade percent (capped 1.0%%, or 2.0%% with --allow-high-demo-risk).")
    p.add_argument("--allow-high-demo-risk", action="store_true", dest="allow_high_demo_risk",
                   help="Raise the risk-pct cap to 2.0%% (demo only).")
    p.add_argument("--max-trades-per-day", type=int, default=None, dest="max_trades_per_day",
                   help="Optional daily trade cap. Omit for high-activity mode (no cap).")
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
    views = [connector.position_view(p) for p in positions]
    xau = [v for v in views if v["symbol"] and "XAU" in v["symbol"].upper()]
    print(f"\nOpen positions: {len(positions)}  (XAUUSD: {len(xau)})")
    for v in views:
        print(f"   ticket={v['ticket']} {v['side']} {v['symbol']} vol={v['volume']} "
              f"open={v['price_open']} cur={v['price_current']} "
              f"SL={v['sl']} TP={v['tp']} profit={v['profit']} "
              f"magic={v['magic']} '{v['comment']}'")
    if not positions:
        print("   (none)")
    out.update({"action": "list_positions", "open_positions": len(positions),
                "xau_positions": len(xau), "positions": views, "order_sent": False})
    return 0


def _do_close(connector, probe, config, args, out) -> int:  # noqa: C901 - guarded flow
    """Guarded close by ticket. Dry-run previews; confirm sends; demo only."""
    ticket = args.close_position
    emergency = args.emergency_close or args.emergency_close_demo
    position = connector.position_by_ticket(ticket)
    found = position is not None
    view = connector.position_view(position) if found else None
    if found:
        print(f"Position: ticket={view['ticket']} {view['side']} {view['symbol']} "
              f"vol={view['volume']} open={view['price_open']} cur={view['price_current']} "
              f"profit={view['profit']}")
    else:
        print(f"Position ticket {ticket} not found on this account.")

    decision = evaluate_demo_close(
        config=config, account_is_demo=connector.demo_verified,
        ticket_found=found, volume=view["volume"] if view else None, emergency=emergency,
    )
    for w in decision.warnings:
        print(f"  ! {w}")

    base = {
        "timestamp": journal.utc_now_iso(),
        "action": "close_position",
        "ticket": ticket,
        "symbol": view["symbol"] if view else None,
        "volume": view["volume"] if view else None,
        "side_being_closed": view["side"] if view else None,
        "profit_before": view["profit"] if view else None,
        "account_server": probe.account_server,
        "account_login": probe.account_login,
        "safety_flags": {
            "MT5_DEMO_ONLY": config.mt5_demo_only,
            "LIVE_TRADING_ENABLED": config.live_trading_enabled,
            "ALLOW_REAL_ORDERS": config.allow_real_orders,
            "GOLD_BOT_KILL_SWITCH": config.kill_switch,
            "emergency_close": emergency,
        },
        "risk": decision.to_dict(),
    }

    # Ticket must exist to build anything.
    if not found:
        print("No close sent (ticket not found).")
        journal.append_entry({**base, "mode": journal.MODE_BLOCKED, "order_send": None})
        out.update({"action": "close_position", "order_sent": False, "reason": "ticket not found"})
        return 1

    # Build the close request + advisory order_check (used by both paths).
    request = connector.build_close_request(position, comment="lumora-gold-bot-demo-close",
                                             deviation=args.deviation)
    try:
        check = connector.check_order(request)
        print(f"order_check (close, advisory): retcode={_safe_int(_result_field(check, 'retcode'))} "
              f"comment={_result_field(check, 'comment')}")
    except Exception as exc:  # noqa: BLE001 - advisory only
        print(f"order_check (close) unavailable: {exc} (continuing — demo close)")

    # Close DRY RUN — build + preview, never send.
    if args.dry_run:
        print(f"\nDRY RUN — would close ticket {ticket}: {request.get('volume')} "
              f"{view['symbol']} via {'SELL' if view['side'] == 'buy' else 'BUY'} @ {request['price']}")
        print("No order sent (dry-run).")
        journal.append_entry({**base, "mode": journal.MODE_DRY_RUN, "close_price": request["price"],
                              "order_send": None})
        out.update({"action": "close_position", "order_sent": False, "mode": "dry_run"})
        return 0

    if not decision.approved:
        print("CLOSE BLOCKED:")
        for r in decision.reasons:
            print(f"   - {r}")
        journal.append_entry({**base, "mode": journal.MODE_BLOCKED, "order_send": None})
        out.update({"action": "close_position", "order_sent": False, "reason": "blocked"})
        return 1

    if not args.confirm_demo_order:
        print("No close sent (missing --confirm-demo-order).")
        journal.append_entry({**base, "mode": journal.MODE_BLOCKED, "order_send": None})
        out.update({"action": "close_position", "order_sent": False,
                    "reason": "missing --confirm-demo-order"})
        return 1

    # Send.
    print("\n>>> MT5 DEMO CLOSE MODE <<<")
    send = connector.send_demo_close(request)
    send_rc = _safe_int(_result_field(send, "retcode"))
    done = getattr(connector._mt5, "TRADE_RETCODE_DONE", 10009)  # noqa: SLF001
    closed_ok = send_rc == done
    print(f"close_send : retcode={send_rc} comment={_result_field(send, 'comment')} "
          f"order={_safe_int(_result_field(send, 'order'))} "
          f"deal={_safe_int(_result_field(send, 'deal'))}")
    print(f"Closed     : ticket={ticket} {view['side']} {view['symbol']} "
          f"vol={view['volume']} @ {request['price']}  profit_before={view['profit']}")

    journal.append_entry({
        **base, "mode": journal.MODE_CLOSE, "close_price": request["price"],
        "order_send": {"retcode": send_rc, "comment": _opt(_result_field(send, "comment")),
                       "order": _safe_int(_result_field(send, "order")),
                       "deal": _safe_int(_result_field(send, "deal")), "ok": closed_ok},
    })

    # Post-close verification: ticket status, remaining, balance/equity, today PnL.
    still = connector.position_by_ticket(ticket)
    print(f"\nPost-close : ticket {ticket} {'STILL OPEN' if still else 'closed'}")
    if view and view["symbol"]:
        remaining = connector.positions_for_symbol(view["symbol"])
        print(f"Remaining {view['symbol']} positions: {len(remaining)}")
    try:
        acct = connector.account_snapshot()
        print(f"Account    : balance={acct['balance']} equity={acct['equity']}")
        connector.read_history_report(probe, symbol=view["symbol"] if view else None)
        today = next((w for w in probe.history_windows if w["label"] == "today"), None)
        if today:
            print(f"Today PnL  : {today['profit_sum']} (XAU deals {today['symbol_deals']})")
    except Exception as exc:  # noqa: BLE001 - reporting only
        print(f"  ! post-close report unavailable: {exc}")

    out.update({"action": "close_position", "order_sent": closed_ok, "retcode": send_rc,
                "ticket_still_open": still is not None})
    return 0 if closed_ok else 1


def main(argv: list[str] | None = None) -> int:  # noqa: C901 - linear guarded flow
    args = parse_args(argv)
    out: dict = {"read_only_default": True, "order_sent": False}

    connector = Mt5DemoConnector()
    probe = ProbeResult()
    config = SafetyConfig.from_env()
    # Explicit --max-trades-per-day overrides; otherwise high-activity (no cap).
    if args.max_trades_per_day is not None:
        config = replace(config, max_trades_per_day=args.max_trades_per_day)

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

        # 3. Price levels (entry/SL/TP) — needed before volume for risk sizing.
        levels = connector.compute_levels(symbol, args.side, args.sl_points, args.tp_points)
        order_type = levels["order_type"]
        entry, sl, tp = levels["price"], levels["sl"], levels["tp"]

        # 4. Account + symbol risk metadata.
        acct = connector.account_snapshot()
        meta = connector.symbol_metadata(symbol)
        equity = acct["equity"] or 0.0

        # 5. Resolve risk percent (mode default or override, capped).
        rp = resolve_risk_pct(mode=args.risk_mode, override_pct=args.risk_pct,
                              allow_high_demo_risk=args.allow_high_demo_risk)
        for w in rp.warnings:
            print(f"  ! {w}")
        if rp.pct <= 0:
            raise Mt5ConnectorError("Resolved risk-pct is 0 — cannot size (fail closed).")
        target_risk_amount = equity * rp.pct / 100.0

        def _loss_at(v: float) -> float | None:
            return connector.estimate_sl_loss(order_type=order_type, symbol=symbol,
                                              volume=v, entry=entry, sl=sl)

        # 6. Volume: auto (risk-derived) or manual.
        lot_plan = None
        if args.auto_volume:
            lot_plan = calc_auto_volume(
                target_risk_amount=target_risk_amount, loss_at_volume=_loss_at,
                volume_min=meta["volume_min"] or 0.01,
                volume_step=meta["volume_step"] or 0.01,
                volume_max=meta["volume_max"] or 100.0,
            )
            if lot_plan is None:
                raise Mt5ConnectorError(
                    "Auto-volume could not size the trade (order_calc_profit/metadata "
                    "unavailable). Fail closed — no order."
                )
            for w in lot_plan.warnings:
                print(f"  ! {w}")
            volume = lot_plan.volume
        else:
            volume = args.volume

        # 7. Estimated SL loss + margin at the chosen volume.
        est_sl_loss = _loss_at(volume)
        margin_required = connector.calc_margin(order_type=order_type, symbol=symbol,
                                                volume=volume, price=entry)
        est_sl_loss_pct = (est_sl_loss / equity * 100.0) if (est_sl_loss and equity) else None

        # 8. Daily realized PnL + trades today (LM75C history).
        connector.read_history_report(probe, symbol=symbol)
        today = next((w for w in probe.history_windows if w["label"] == "today"), None)
        daily_pnl = (today or {}).get("profit_sum", 0.0) or 0.0
        trades_today = (today or {}).get("entry_deals", 0) or 0

        # 9. Build request + full risk-plan decision (final authority).
        request = connector.build_demo_order_request(
            symbol=symbol, side=args.side, volume=volume,
            sl_points=args.sl_points, tp_points=args.tp_points,
            comment=args.comment, deviation=args.deviation, magic=args.magic,
        )
        decision = evaluate_risk_plan(
            config=config, account_is_demo=connector.demo_verified, side=args.side,
            volume=volume, sl_present=request.get("sl") is not None,
            tp_present=request.get("tp") is not None, est_sl_loss=est_sl_loss,
            require_risk_calc=args.auto_volume, margin_required=margin_required,
            free_margin=acct["margin_free"], equity=equity,
            daily_realized_pnl=daily_pnl, trades_today=trades_today, risk_pct=rp.pct,
        )
        budget = decision.info.get("remaining_daily_budget")

        # Risk panel.
        print("\n Risk Plan")
        print(f"   Equity / Balance : {acct['equity']} / {acct['balance']}  "
              f"free margin {acct['margin_free']}")
        print(f"   Risk mode / pct  : {args.risk_mode} / {rp.pct}%  "
              f"({'AUTO' if args.auto_volume else 'manual'} volume)")
        print(f"   Target risk      : {round(target_risk_amount, 2)} {acct['currency'] or ''}")
        print(f"   Entry/SL/TP      : {entry} / {sl} / {tp}")
        print(f"   Volume           : {volume}")
        print(f"   Est. SL loss     : {est_sl_loss} "
              f"({round(est_sl_loss_pct, 3) if est_sl_loss_pct is not None else '-'}%)")
        print(f"   Margin required  : {margin_required}  "
              f"(allowed {decision.info.get('margin_allowed', '-')})")
        print(f"   Daily PnL today  : {round(daily_pnl, 2)}  remaining budget {budget}")
        if config.max_trades_per_day is None:
            freq = "experimental-scalp" if args.risk_mode == "scalp" else "high-activity"
            print(f"   Frequency mode   : {freq} (trade cap disabled)")
            print(f"   Trades today     : {trades_today} / unlimited")
        else:
            print("   Frequency mode   : capped")
            print(f"   Trades today     : {trades_today} / {config.max_trades_per_day}")
        print(f"   Demo only        : {config.mt5_demo_only}")
        for w in decision.warnings:
            print(f"  ! {w}")
        print(f"   RISK DECISION    : {'APPROVED' if decision.approved else 'BLOCKED'}")
        if not decision.approved:
            for r in decision.reasons:
                print(f"     - {r}")

        # 10. order_check (validation only — sends nothing).
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
            "volume": volume,
            "price": request["price"],
            "sl": request["sl"],
            "tp": request["tp"],
            "sl_points": args.sl_points,
            "tp_points": args.tp_points,
            "comment": args.comment,
            "spread": probe.tick_spread,
            "risk_mode": args.risk_mode,
            "risk_pct": rp.pct,
            "auto_volume": args.auto_volume,
            "target_risk_amount": round(target_risk_amount, 2),
            "estimated_sl_loss": est_sl_loss,
            "estimated_margin": margin_required,
            "daily_pnl_today": round(daily_pnl, 2),
            "remaining_daily_budget": budget,
            "trades_today": trades_today,
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
