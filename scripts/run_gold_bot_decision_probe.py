"""
scripts/run_gold_bot_decision_probe.py
----------------------------------------
LM76A — Gold Bot decision engine V1 probe.

Reads live XAUUSD data from the MT5 demo terminal, runs the pure decision
engine and prints a structured LONG / SHORT / NO_TRADE idea with reasons. By
default it is DECISION-ONLY and dry-run: it sends nothing. Demo execution
requires BOTH --auto-execute-demo and --confirm-demo-order, and even then only
on a verified demo account, with no open XAUUSD position, after the existing
LM75D risk/margin gate approves.

Run from repo root (Windows, MT5 running on a demo account):
    python scripts/run_gold_bot_decision_probe.py --risk-mode balanced --dry-run
    python scripts/run_gold_bot_decision_probe.py --risk-mode scalp --dry-run
    python scripts/run_gold_bot_decision_probe.py --risk-mode scalp --auto-execute-demo --confirm-demo-order

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
from services.gold_bot_decision_engine import decide  # noqa: E402
from services.gold_bot_lot_calculator import (  # noqa: E402
    RISK_MODES,
    calc_auto_volume,
    resolve_risk_pct,
)
from services.gold_bot_risk_gate import SafetyConfig, evaluate_risk_plan  # noqa: E402
from services import gold_bot_trade_journal as journal  # noqa: E402


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="run_gold_bot_decision_probe",
        description="Gold Bot decision engine V1 (decision-only by default; demo execution heavily guarded).",
    )
    p.add_argument("--symbol", default=None, help="Gold symbol; omit to auto-discover.")
    p.add_argument("--timeframe", default="M1", help="Candle timeframe (default M1).")
    p.add_argument("--bars", type=int, default=120, help="Candles to read (default 120).")
    p.add_argument("--risk-mode", choices=list(RISK_MODES), default="balanced", dest="risk_mode")
    p.add_argument("--dry-run", action="store_true", dest="dry_run",
                   help="Decision + risk plan only (default behavior; never sends).")
    p.add_argument("--confirm-demo-order", action="store_true", dest="confirm_demo_order")
    p.add_argument("--auto-execute-demo", action="store_true", dest="auto_execute_demo",
                   help="Permit a demo order from the decision (needs --confirm-demo-order too).")
    p.add_argument("--json", action="store_true", dest="json_output")
    return p.parse_args(argv)


def main(argv=None) -> int:  # noqa: C901 - linear guarded flow
    args = parse_args(argv)
    out: dict = {"decision_only_default": True, "order_sent": False}
    connector = Mt5DemoConnector()
    probe = ProbeResult()
    config = SafetyConfig.from_env()

    def emit(code: int) -> int:
        if args.json_output:
            print(json.dumps(out, indent=2, default=str))
        return code

    try:
        connector.connect()
        connector.read_account(probe)
        if not connector.demo_verified:
            raise Mt5ConnectorError(
                f"Account trade_mode={probe.trade_mode_label} is not a strict DEMO account (fail closed)."
            )
        symbol = connector.discover_gold_symbol(probe, preferred=args.symbol)
        connector.read_tick(probe, symbol)
        meta = connector.symbol_metadata(symbol)
        point = meta["point"] or 0.01
        spread_points = (probe.tick_spread / point) if (probe.tick_spread is not None) else 0.0
        candles = connector.recent_candles(symbol, args.timeframe, args.bars)
        open_xau = len(connector.positions_for_symbol(symbol))

        idea = decide(
            candles, symbol=symbol, timeframe=args.timeframe.upper(), risk_mode=args.risk_mode,
            spread_points=spread_points, point=point, has_open_position=open_xau > 0,
        )

        # ── Print ─────────────────────────────────────────────────────────────
        print("=" * 64)
        print(" GOLD BOT DECISION ENGINE V1   (DEMO ONLY)")
        print("=" * 64)
        print(f" Account     : {probe.account_login}@{probe.account_server} "
              f"(DEMO {connector.demo_verified})")
        print(f" Symbol/TF   : {symbol} / {args.timeframe.upper()}   bars={len(candles)}")
        print(f" Price/Spread: {probe.tick_bid}/{probe.tick_ask}  spread {round(spread_points,1)}pt")
        if idea.market_state:
            from services.gold_bot_decision_engine import MarketState
            print(f" Market      : {MarketState(**idea.market_state).summary()}")
        print(f" Open XAUUSD : {open_xau}")
        print(f"\n DECISION    : {idea.decision}   [{idea.strategy}]  confidence {idea.confidence}")
        print(f" Risk mode   : {idea.risk_mode}")
        if idea.sl_points is not None:
            print(f" SL/TP sugg. : {idea.sl_points} / {idea.tp_points} pts  "
                  f"(entry ref {idea.entry_reference_price})")
        for r in idea.reasons:
            print(f"   reason  - {r}")
        for b in idea.blockers:
            print(f"   blocker - {b}")

        # ── Execution path (only for LONG/SHORT) ──────────────────────────────
        exec_status = "decision only"
        risk_decision = None
        if idea.decision in ("LONG", "SHORT") and idea.should_execute_demo:
            side = "buy" if idea.decision == "LONG" else "sell"
            levels = connector.compute_levels(symbol, side, idea.sl_points, idea.tp_points)
            order_type, entry, sl = levels["order_type"], levels["price"], levels["sl"]
            acct = connector.account_snapshot()
            equity = acct["equity"] or 0.0
            rp = resolve_risk_pct(mode=args.risk_mode, override_pct=None, allow_high_demo_risk=False)
            target = equity * rp.pct / 100.0

            def _loss(v):
                return connector.estimate_sl_loss(order_type=order_type, symbol=symbol,
                                                 volume=v, entry=entry, sl=sl)

            lot = calc_auto_volume(target_risk_amount=target, loss_at_volume=_loss,
                                   volume_min=meta["volume_min"] or 0.01,
                                   volume_step=meta["volume_step"] or 0.01,
                                   volume_max=meta["volume_max"] or 100.0)
            if lot is None:
                print("\n Execution   : risk sizing failed — no order (fail closed).")
                exec_status = "demo execution blocked"
            else:
                est_loss = _loss(lot.volume)
                margin = connector.calc_margin(order_type=order_type, symbol=symbol,
                                               volume=lot.volume, price=entry)
                connector.read_history_report(probe, symbol=symbol)
                today = next((w for w in probe.history_windows if w["label"] == "today"), None)
                daily_pnl = (today or {}).get("profit_sum", 0.0) or 0.0
                risk_decision = evaluate_risk_plan(
                    config=config, account_is_demo=connector.demo_verified, side=side,
                    volume=lot.volume, sl_present=True, tp_present=True, est_sl_loss=est_loss,
                    require_risk_calc=True, margin_required=margin, free_margin=acct["margin_free"],
                    equity=equity, daily_realized_pnl=daily_pnl, trades_today=0, risk_pct=rp.pct,
                )
                print(f"\n Risk plan   : vol {lot.volume}  est SL loss {est_loss} "
                      f"({rp.pct}%)  margin {margin}  budget {risk_decision.info.get('remaining_daily_budget')}")
                print(f" Risk gate   : {'APPROVED' if risk_decision.approved else 'BLOCKED'}")
                for r in risk_decision.reasons:
                    print(f"   - {r}")

                will_execute = (args.auto_execute_demo and args.confirm_demo_order
                                and not args.dry_run and risk_decision.approved)
                if will_execute:
                    request = connector.build_demo_order_request(
                        symbol=symbol, side=side, volume=lot.volume,
                        sl_points=idea.sl_points, tp_points=idea.tp_points,
                        comment="lumora-gold-bot-decision", deviation=20, magic=760_760)
                    check = connector.check_order(request)
                    check_done = getattr(connector._mt5, "TRADE_RETCODE_DONE", 10009)  # noqa: SLF001
                    if getattr(check, "retcode", None) in (0, check_done):
                        print("\n>>> MT5 DEMO ORDER MODE (decision) <<<")
                        send = connector.send_demo_order(request)
                        sent_ok = getattr(send, "retcode", None) == check_done
                        print(f" order_send  : retcode={getattr(send, 'retcode', None)} "
                              f"order={getattr(send, 'order', None)} deal={getattr(send, 'deal', None)}")
                        exec_status = "demo execution sent" if sent_ok else "demo execution failed"
                        out["order_sent"] = sent_ok
                    else:
                        print("\n order_check not acceptable — no order (fail closed).")
                        exec_status = "demo execution blocked"
                else:
                    why = ("dry-run" if args.dry_run
                           else "risk gate blocked" if not risk_decision.approved
                           else "missing --auto-execute-demo / --confirm-demo-order")
                    print(f"\n Execution   : not sent ({why}).")
                    exec_status = "demo execution blocked"

        print(f"\n Status      : {exec_status}")

        # ── Journal ───────────────────────────────────────────────────────────
        journal.append_entry({
            **idea.to_dict(),
            "account_server": probe.account_server,
            "account_login": probe.account_login,
            "dry_run": args.dry_run,
            "auto_execute_demo": args.auto_execute_demo,
            "confirm_demo_order": args.confirm_demo_order,
            "execution_status": exec_status,
            "risk": risk_decision.to_dict() if risk_decision else None,
        }, journal.DECISION_JOURNAL_PATH)

        out.update({"decision": idea.decision, "strategy": idea.strategy,
                    "confidence": idea.confidence, "status": exec_status})
        return emit(0)

    except Mt5ConnectorError as exc:
        print("DECISION PROBE FAILED (fail-closed):", exc, file=sys.stderr)
        out["error"] = str(exc)
        return emit(1)
    finally:
        connector.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
