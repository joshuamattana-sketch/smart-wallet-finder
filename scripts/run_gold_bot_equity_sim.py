"""
scripts/run_gold_bot_equity_sim.py
-----------------------------------
LM110A - Equity-curve / risk-of-ruin simulator (RESEARCH-ONLY).

Runs a cost-aware replay, then compounds the per-trade realized returns into an
account equity curve under one or more risk-% sizing rules. Shows final balance,
max drawdown and whether each sizing RUINS the account. Pure offline analysis:
no MT5, no orders, no live. Demonstrates from real data why large per-trade risk
(e.g. 80%) blows the account.

    python scripts/run_gold_bot_equity_sim.py --risk-mode scalp --horizon 30 \
        --sl-points 1000 --tp-points 2000 --spread-cost --risk-pcts 1,2,10,80
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from services.gold_bot_equity_sim import extract_realized, simulate_equity  # noqa: E402
from services.gold_bot_lot_calculator import RISK_MODES  # noqa: E402
from services.gold_bot_replay_engine import ReplayError, run_replay  # noqa: E402


def parse_args(argv=None):
    p = argparse.ArgumentParser(prog="run_gold_bot_equity_sim",
                                description="Equity / risk-of-ruin simulation from a replay.")
    p.add_argument("--symbol", default="XAUUSD")
    p.add_argument("--timeframe", default="M1")
    p.add_argument("--risk-mode", choices=list(RISK_MODES), default="scalp", dest="risk_mode")
    p.add_argument("--max-bars", type=int, default=7000, dest="max_bars")
    p.add_argument("--horizon", type=int, default=30)
    p.add_argument("--sl-points", type=int, default=1000, dest="sl_points",
                   help="SL distance the position size is based on (also used for scoring exits).")
    p.add_argument("--tp-points", type=int, default=2000, dest="tp_points")
    p.add_argument("--spread-cost", action="store_true", dest="spread_cost")
    p.add_argument("--cost-points", type=float, default=0.0, dest="cost_points")
    p.add_argument("--max-spread-points", type=float, default=None, dest="max_spread_points")
    p.add_argument("--trend-filter", action="store_true", dest="use_trend_filter")
    p.add_argument("--start-balance", type=float, default=10000.0, dest="start_balance")
    p.add_argument("--risk-pcts", default="1,2,10,80", dest="risk_pcts",
                   help="Comma list of per-trade risk %% to compare (e.g. 1,2,10,80).")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        res = run_replay(
            symbol=args.symbol, timeframe=args.timeframe, history_dir=_REPO_ROOT / "data" / "gold_bot" / "history",
            macro_history_dir=_REPO_ROOT / "data" / "gold_bot" / "macro_history",
            out_dir=_REPO_ROOT / "data" / "gold_bot" / "replay", warmup_bars=120, max_bars=args.max_bars,
            risk_mode=args.risk_mode, horizons=(args.horizon,), spread_cost=args.spread_cost,
            cost_points=args.cost_points, max_spread_points=args.max_spread_points,
            sl_points_override=args.sl_points, tp_points_override=args.tp_points,
            use_trend_filter=args.use_trend_filter)
    except ReplayError as exc:
        print(f"EQUITY SIM FAILED: {exc}", file=sys.stderr)
        return 1

    realized = extract_realized(res.rows, args.horizon)
    n_trades = sum(1 for r in realized if r is not None)
    risk_pcts = [float(x) for x in args.risk_pcts.split(",") if x.strip()]

    print("=" * 78)
    print(" GOLD BOT EQUITY / RISK-OF-RUIN SIM   research-only")
    print("=" * 78)
    print(f" {args.symbol} {args.timeframe} {args.risk_mode} | horizon h{args.horizon} | "
          f"SL {args.sl_points} TP {args.tp_points} | start {args.start_balance:.0f}")
    print(f" trades: {n_trades}  (spread_cost={args.spread_cost})")
    print(f"\n {'risk/trade':>10} {'final':>12} {'return':>10} {'maxDD':>8} {'ruin':>16} {'maxLossStreak':>14}")
    for rp in risk_pcts:
        r = simulate_equity(realized, sl_points=args.sl_points, risk_pct=rp,
                            start_balance=args.start_balance)
        ruin = f"YES @trade {r.ruin_at_trade}" if r.ruined else "no"
        print(f" {rp:>9.0f}% {r.final_balance:>12.0f} {r.return_pct:>9.0f}% "
              f"{r.max_drawdown_pct:>7.0f}% {ruin:>16} {r.longest_loss_streak:>14}")
    print("\n Research-only. No money, no orders. Large per-trade risk = ruin even on a "
          "positive sequence.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
