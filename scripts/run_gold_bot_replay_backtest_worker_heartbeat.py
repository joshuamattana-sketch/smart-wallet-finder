"""
scripts/run_gold_bot_replay_backtest_worker_heartbeat.py
---------------------------------------------------------
LM98B - REPLAY/BACKTEST WORKER heartbeat. While the market is closed, runs new
no-lookahead replay jobs across a timeframe/risk/horizon plan, refreshes the
scorecard, and reports replay-data GROWTH + performance every N minutes. Preview
by default; sends only with --send-discord + a valid LUMORA_GOLD_DISCORD_WEBHOOK_URL.
Replay/offline only: no MT5 orders, no demo session, no live, no arbitrary shell.

    python scripts/run_gold_bot_replay_backtest_worker_heartbeat.py --dry-run-plan
    python scripts/run_gold_bot_replay_backtest_worker_heartbeat.py --once --timeframes M1 --risk-modes scalp --horizons 15 --max-bars 1000
    python scripts/run_gold_bot_replay_backtest_worker_heartbeat.py --duration-minutes 240 --report-every-minutes 15 --job-every-minutes 15 --timeframes M1,M5 --risk-modes balanced,scalp --horizons 15,30 --max-bars 1000
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from services.gold_bot_replay_backtest_worker_heartbeat import (  # noqa: E402
    DEFAULT_WORKER_DIR,
    WorkerConfig,
    build_plan,
    format_plan,
    run_loop,
)


def _csv(s: str) -> tuple[str, ...]:
    return tuple(x.strip() for x in str(s).split(",") if x.strip())


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="run_gold_bot_replay_backtest_worker_heartbeat",
        description="Offline replay/backtest worker with Discord growth heartbeats (preview by default).",
    )
    p.add_argument("--duration-minutes", type=int, default=60, dest="duration_minutes")
    p.add_argument("--report-every-minutes", type=int, default=15, dest="report_every_minutes")
    p.add_argument("--job-every-minutes", type=int, default=15, dest="job_every_minutes")
    p.add_argument("--timeframes", default="M1,M5")
    p.add_argument("--risk-modes", default="balanced,scalp", dest="risk_modes")
    p.add_argument("--horizons", default="15,30")
    p.add_argument("--max-bars", type=int, default=1000, dest="max_bars")
    p.add_argument("--min-samples", type=int, default=10, dest="min_samples")
    p.add_argument("--include-real-trades", action=argparse.BooleanOptionalAction, default=True,
                   dest="include_real_trades")
    p.add_argument("--real-trade-weight", type=float, default=2.0, dest="real_trade_weight")
    p.add_argument("--min-real-trades", type=int, default=5, dest="min_real_trades")
    p.add_argument("--send-discord", action="store_true", dest="send_discord")
    p.add_argument("--once", action="store_true")
    p.add_argument("--dry-run-plan", action="store_true", dest="dry_run_plan")
    p.add_argument("--sleep-seconds", type=int, default=None, dest="sleep_seconds")
    p.add_argument("--out-dir", default=str(DEFAULT_WORKER_DIR), dest="out_dir")
    p.add_argument("--json", action="store_true", dest="json_output")
    return p.parse_args(argv)


def _cfg(args) -> WorkerConfig:
    return WorkerConfig(
        duration_minutes=args.duration_minutes, report_every_minutes=args.report_every_minutes,
        job_every_minutes=args.job_every_minutes, timeframes=_csv(args.timeframes),
        risk_modes=_csv(args.risk_modes), horizons=tuple(int(h) for h in _csv(args.horizons)),
        max_bars=args.max_bars, min_samples=args.min_samples,
        include_real_trades=args.include_real_trades, real_trade_weight=args.real_trade_weight,
        min_real_trades=args.min_real_trades, send_discord=args.send_discord, once=args.once,
        dry_run_plan=args.dry_run_plan, sleep_seconds=args.sleep_seconds)


def main(argv=None) -> int:
    args = parse_args(argv)
    cfg = _cfg(args)
    plan = build_plan(cfg)

    if args.dry_run_plan:
        if args.json_output:
            print(json.dumps({"plan": [j.label for j in plan]}, indent=2))
        else:
            print("=" * 70)
            print(" REPLAY BACKTEST WORKER   (DRY-RUN PLAN - no jobs run)")
            print("=" * 70)
            print(format_plan(plan))
            print("\n Replay worker only. No MT5 orders, no demo session, live locked.")
        return 0

    results = run_loop(cfg, out_dir=Path(args.out_dir))

    if args.json_output:
        print(json.dumps([r.to_dict() for r in results], indent=2, default=str))
        return 0

    for r in results:
        print("=" * 70)
        banner = ("SENT" if r.sent else
                  "PREVIEW - NOT SENT" if r.mode == "preview" else "SEND ATTEMPTED - NOT SENT")
        print(f" REPLAY WORKER CYCLE #{r.cycle}   [{banner}]" + (f"   target {r.target}" if r.target else ""))
        print("=" * 70)
        print(r.content)
        for w in r.warnings:
            print(f"   warning - {w}")
        if r.paths.get("latest_json"):
            print(f"\n log: {r.paths['latest_json']}")
    print("\n Replay/offline worker. No MT5 orders, no demo session, live locked, "
          "no webhook value printed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
