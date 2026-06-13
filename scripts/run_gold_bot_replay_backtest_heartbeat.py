"""
scripts/run_gold_bot_replay_backtest_heartbeat.py
--------------------------------------------------
LM98A - Long-running REPLAY / BACKTEST heartbeat. Every N minutes (default 15) it
refreshes the offline learning scorecard and prints a compact Discord progress
report. DEFAULT = preview (prints, never sends). Sending needs BOTH --send-discord
AND env LUMORA_GOLD_DISCORD_WEBHOOK_URL. Replay/offline only: no MT5 orders, no demo
session, no live, no arbitrary shell, no network unless --send-discord.

    python scripts/run_gold_bot_replay_backtest_heartbeat.py --once
    python scripts/run_gold_bot_replay_backtest_heartbeat.py --duration-minutes 60 --report-every-minutes 15
    python scripts/run_gold_bot_replay_backtest_heartbeat.py --duration-minutes 1 --report-every-minutes 1
    # send (PowerShell):
    $env:LUMORA_GOLD_DISCORD_WEBHOOK_URL = "YOUR_WEBHOOK_URL"
    python scripts/run_gold_bot_replay_backtest_heartbeat.py --send-discord
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

from services.gold_bot_replay_backtest_heartbeat import (  # noqa: E402
    DEFAULT_HEARTBEAT_DIR,
    HeartbeatConfig,
    run_loop,
)


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="run_gold_bot_replay_backtest_heartbeat",
        description="Replay/offline backtest heartbeat with Discord progress (preview by default).",
    )
    p.add_argument("--duration-minutes", type=int, default=60, dest="duration_minutes")
    p.add_argument("--report-every-minutes", type=int, default=15, dest="report_every_minutes")
    p.add_argument("--timeframe", default="M1")
    p.add_argument("--risk-mode", default="balanced", dest="risk_mode")
    p.add_argument("--horizon", type=int, default=15)
    p.add_argument("--min-samples", type=int, default=10, dest="min_samples")
    p.add_argument("--include-real-trades", action=argparse.BooleanOptionalAction, default=True,
                   dest="include_real_trades",
                   help="Blend real demo_trade_outcome events (default on). Use --no-include-real-trades to disable.")
    p.add_argument("--real-trade-weight", type=float, default=2.0, dest="real_trade_weight")
    p.add_argument("--min-real-trades", type=int, default=5, dest="min_real_trades")
    p.add_argument("--max-bars", type=int, default=None, dest="max_bars")
    p.add_argument("--send-discord", action="store_true", dest="send_discord",
                   help="POST each heartbeat to Discord (needs the env webhook). Default: preview only.")
    p.add_argument("--once", action="store_true", help="Emit one heartbeat immediately and exit.")
    p.add_argument("--sleep-seconds", type=int, default=None, dest="sleep_seconds",
                   help="Override the sleep between heartbeats (testing). Default = report interval.")
    p.add_argument("--out-dir", default=str(DEFAULT_HEARTBEAT_DIR), dest="out_dir")
    p.add_argument("--json", action="store_true", dest="json_output")
    return p.parse_args(argv)


def _cfg(args) -> HeartbeatConfig:
    return HeartbeatConfig(
        duration_minutes=args.duration_minutes, report_every_minutes=args.report_every_minutes,
        timeframe=args.timeframe, risk_mode=args.risk_mode, horizon=args.horizon,
        min_samples=args.min_samples, include_real_trades=args.include_real_trades,
        real_trade_weight=args.real_trade_weight, min_real_trades=args.min_real_trades,
        max_bars=args.max_bars, send_discord=args.send_discord, once=args.once,
        sleep_seconds=args.sleep_seconds)


def main(argv=None) -> int:
    args = parse_args(argv)
    cfg = _cfg(args)

    results = run_loop(cfg, out_dir=Path(args.out_dir))

    if args.json_output:
        print(json.dumps([r.to_dict() for r in results], indent=2, default=str))
        return 0

    for r in results:
        print("=" * 70)
        banner = ("SENT" if r.sent else
                  "PREVIEW - NOT SENT" if r.mode == "preview" else "SEND ATTEMPTED - NOT SENT")
        print(f" REPLAY BACKTEST HEARTBEAT #{r.heartbeat}   [{banner}]"
              + (f"   target {r.target}" if r.target else ""))
        print("=" * 70)
        print(r.content)
        for w in r.warnings:
            print(f"   warning - {w}")
        if r.paths.get("latest_json"):
            print(f"\n log: {r.paths['latest_json']}")
    print("\n Replay/offline heartbeat. No MT5 orders, no demo session, live locked, "
          "no webhook value printed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
