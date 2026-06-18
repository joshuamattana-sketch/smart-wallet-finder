"""
scripts/run_gold_bot_worker.py
-------------------------------
LM81A — Long-running Gold Bot worker loop (MT5 DEMO ONLY).

Continuously reads the MT5 demo terminal, builds macro context, runs the
Decision Engine V2 and journals a compact result every iteration. OBSERVE /
dry-run by default — it SENDS NOTHING. A demo order is only attempted with
--mode demo AND --auto-execute-demo AND --confirm-demo-order, on a verified
demo account, after the LM75 risk gate approves (and never during a macro
lockout or with an open XAUUSD position).

Run from repo root (Windows, MT5 running on a demo account):
    python scripts/run_gold_bot_worker.py --max-iterations 1
    python scripts/run_gold_bot_worker.py --max-iterations 5 --interval-seconds 5
    python scripts/run_gold_bot_worker.py --risk-mode scalp \
        --macro-events-file data/gold_bot/macro_events.sample.json \
        --max-iterations 5 --interval-seconds 5

Requires the MetaTrader5 package (Windows only):  pip install MetaTrader5
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from services.gold_bot_lot_calculator import RISK_MODES  # noqa: E402
from services.gold_bot_worker import GoldBotWorker, WorkerConfig  # noqa: E402


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="run_gold_bot_worker",
        description="Gold Bot worker loop (MT5 demo only; observe/dry-run by default).",
    )
    p.add_argument("--mode", choices=["observe", "demo"], default="observe",
                   help="observe = never send; demo = may send only with the execute+confirm flags.")
    p.add_argument("--environment", choices=["paper", "demo", "live"], default="demo",
                   help="Execution environment (LM93A). live is hard-locked.")
    p.add_argument("--allow-live-trading", action="store_true", dest="allow_live_trading",
                   help="No-op safety flag; live stays hard-locked in this build.")
    p.add_argument("--risk-mode", choices=list(RISK_MODES), default="balanced", dest="risk_mode")
    p.add_argument("--interval-seconds", type=float, default=10.0, dest="interval_seconds")
    p.add_argument("--max-iterations", type=int, default=None, dest="max_iterations",
                   help="Stop after N iterations (default: run until interrupted).")
    p.add_argument("--symbol", default=None, help="Gold symbol; omit to auto-discover.")
    p.add_argument("--timeframe", default="M1")
    p.add_argument("--bars", type=int, default=120)
    p.add_argument("--calendar-file", default=None, dest="calendar_file",
                   help="Normalized economic calendar JSON (preferred).")
    p.add_argument("--macro-events-file", default=None, dest="macro_events_file",
                   help="Legacy LM77A macro events JSON (fallback if --calendar-file omitted).")
    p.add_argument("--dxy-bias", choices=["rising", "falling", "flat", "unknown"],
                   default="unknown", dest="dxy_bias")
    p.add_argument("--yields-bias", choices=["rising", "falling", "flat", "unknown"],
                   default="unknown", dest="yields_bias")
    p.add_argument("--geopolitical-risk", choices=["low", "medium", "high", "unknown"],
                   default="unknown", dest="geopolitical_risk")
    p.add_argument("--auto-execute-demo", action="store_true", dest="auto_execute_demo")
    p.add_argument("--confirm-demo-order", action="store_true", dest="confirm_demo_order")
    p.add_argument("--close-on-no-trade", action="store_true", dest="close_on_no_trade",
                   help="Placeholder in V1 (surfaced, never sends a close).")
    p.add_argument("--use-learning-modifiers", action="store_true", dest="use_learning_modifiers",
                   help="Apply demo-only learned confidence modifiers (default off; never live).")
    p.add_argument("--learning-modifiers-file", default=None, dest="learning_modifiers_file",
                   help="Active demo modifiers JSON (default data/gold_bot/learning/active_demo_modifiers.json).")
    p.add_argument("--confidence-scaled-lot", action="store_true", dest="confidence_scaled_lot",
                   help="Demo-only: scale lot size by decision confidence, WITHIN the existing "
                        "risk limit (never above it). Default off.")
    p.add_argument("--lot-confidence-floor", type=float, default=0.5, dest="lot_confidence_floor",
                   help="Fraction of the risk amount used at min confidence (default 0.5; "
                        "1.0 = no scaling). Only used with --confidence-scaled-lot.")
    # LM100A demo-only basket scalp (opt-in; default off — normal path unchanged).
    p.add_argument("--basket-scalp", action="store_true", dest="basket_scalp",
                   help="Demo-only: open N same-direction legs and close them all together on "
                        "profit target / HARD loss cap / time stop. Default off. Live stays locked.")
    p.add_argument("--basket-num-positions", type=int, default=5, dest="basket_num_positions",
                   help="Base leg count (at the entry confidence floor).")
    p.add_argument("--basket-max-positions", type=int, default=0, dest="basket_max_positions",
                   help="Scale leg count up to this with confidence (0 = no scaling). E.g. 10.")
    p.add_argument("--basket-scale-in", action="store_true", dest="basket_scale_in",
                   help="Nachkaufen: add same-direction legs toward the confidence-scaled target "
                        "while a basket is open (hard loss cap still force-closes the basket).")
    p.add_argument("--basket-risk-cap-pct", type=float, default=3.0, dest="basket_risk_cap_pct",
                   help="Max TOTAL risk across the basket, %% of equity (hard entry ceiling).")
    p.add_argument("--basket-profit-target-pct", type=float, default=0.6, dest="basket_profit_target_pct",
                   help="Close ALL when aggregate basket profit reaches +this %% of equity.")
    p.add_argument("--basket-hard-loss-cap-pct", type=float, default=1.5, dest="basket_hard_loss_cap_pct",
                   help="FORCE-close ALL when aggregate basket loss reaches -this %% of equity (the brake).")
    p.add_argument("--basket-time-stop-seconds", type=float, default=60.0, dest="basket_time_stop_seconds")
    p.add_argument("--basket-cooldown-seconds-after-loss", type=float, default=60.0,
                   dest="basket_cooldown_seconds_after_loss")
    # LM101A adaptive exit (demo-only): trailing profit lock + pressure close.
    p.add_argument("--basket-lock-arm-pct", type=float, default=0.4, dest="basket_lock_arm_pct",
                   help="Arm the trailing profit lock once aggregate profit peaks at +this %% equity "
                        "(0 = disable lock).")
    p.add_argument("--basket-lock-floor-frac", type=float, default=0.0, dest="basket_lock_floor_frac",
                   help="After armed, close-all if profit retraces below this fraction of the peak "
                        "(0.0 = protect break-even; 0.1 = lock 10%% of peak).")
    p.add_argument("--basket-no-pressure-close", action="store_false", dest="basket_pressure_close",
                   help="Disable the price-action pressure close (on by default).")
    p.add_argument("--basket-pressure-min-profit-pct", type=float, default=0.1,
                   dest="basket_pressure_min_profit_pct",
                   help="Only pressure-close once at least +this %% equity in profit.")
    p.add_argument("--basket-pressure-threshold-points", type=float, default=300.0,
                   dest="basket_pressure_threshold_points",
                   help="Close-all if price-action pressure opposes the basket by >= this many points "
                        "(gold point-pressure runs ~200-300; default 300).")
    p.add_argument("--basket-no-reversal-close", action="store_false", dest="basket_reversal_close",
                   help="Disable the engine-reversal exit (on by default).")
    p.add_argument("--basket-reversal-confidence", type=float, default=70.0,
                   dest="basket_reversal_confidence",
                   help="Close-all if the engine emits an opposite signal with >= this confidence.")
    p.add_argument("--basket-pressure-confirm-bars", type=int, default=3,
                   dest="basket_pressure_confirm_bars",
                   help="Pressure must oppose for this many CONSECUTIVE reads before closing "
                        "(debounce; higher = less twitchy, ignores single dips).")
    p.add_argument("--sync-outcomes-every", type=int, default=0, dest="sync_outcomes_every",
                   help="Every N iterations (and on stop) record real demo trade outcomes from MT5 "
                        "history into the learning journal. 0 = off. Read-only history; no orders.")
    # LM103A demo-only HARD mode (separate; default off).
    p.add_argument("--hard-mode", action="store_true", dest="hard_mode",
                   help="DEMO-ONLY: lift per-trade risk to --hard-max-risk-pct (wall 10%%). Daily-loss "
                        "budget + basket loss cap still apply. Refused outside demo. Live stays locked.")
    p.add_argument("--hard-max-risk-pct", type=float, default=5.0, dest="hard_max_risk_pct",
                   help="Per-trade risk%% in hard mode (capped at the 10%% demo wall). Default 5.0.")
    p.add_argument("--hard-max-margin-pct", type=float, default=50.0, dest="hard_max_margin_pct",
                   help="Per-trade margin allowance in hard mode (%% of free margin; normal 10%%). "
                        "Physical broker margin is still the wall. Default 50.")
    p.add_argument("--basket-min-confidence", type=float, default=0.0, dest="basket_min_confidence",
                   help="Extra basket ENTRY confidence floor (0 = engine min). Set e.g. 75 to only "
                        "open on high-confidence signals.")
    p.add_argument("--min-confidence", type=float, default=0.0, dest="min_confidence_floor",
                   help="General ENTRY confidence floor for BOTH single-trade and basket (0 = engine "
                        "min). Trade like before but only on strong signals.")
    p.add_argument("--discord-session-summary", action="store_true", dest="discord_session_summary",
                   help="On stop, post a session summary (winrate / PnL / decisions) to Discord. "
                        "Webhook from --discord-webhook-url or env LUMORA_GOLD_DISCORD_WEBHOOK_URL.")
    p.add_argument("--discord-webhook-url", default=None, dest="discord_webhook_url",
                   help="Discord webhook URL (else env LUMORA_GOLD_DISCORD_WEBHOOK_URL). Never logged.")
    p.add_argument("--reset-safety-state", action="store_true", dest="reset_safety_state",
                   help="Clear the demo safety supervisor state (stale loss-streak cooldown) at startup.")
    p.add_argument("--trend-filter", action="store_true", dest="use_trend_filter",
                   help="Higher-timeframe trend filter: only LONG in an uptrend, SHORT in a "
                        "downtrend (long-SMA proxy). Cuts counter-trend scalps.")
    p.add_argument("--momentum-forward-test", action="store_true", dest="momentum_forward_test",
                   help="LM117: forward-test the backtested rule on demo — trend-filter + only "
                        "scalp_momentum + confidence<80 + ~30min time-exit (wide leg SL/TP), 1 "
                        "position, early exits off. Records outcomes. The honest forward check.")
    p.add_argument("--m15-swing-test", action="store_true", dest="m15_swing_test",
                   help="LM118: the VALIDATED M15 swing config (positive 2025 AND 2026 out-of-sample) "
                        "— timeframe M15, balanced, trend-filter, all detectors, ~7.5h time-exit "
                        "(wide leg SL), 1 position, early exits off. The real edge; forward-test on demo.")
    p.add_argument("--decision-context-file", default=None, dest="decision_context_file",
                   help="Where to log sent-order confidence/setup for outcome calibration "
                        "(default data/gold_bot/decision_context.jsonl).")
    p.add_argument("--no-status-file", action="store_true", dest="no_status_file",
                   help="Do not write data/gold_bot/worker_status.json.")
    # LM87A demo safety supervisor limits (the supervisor itself has NO off switch).
    p.add_argument("--max-open-positions", type=int, default=1, dest="max_open_positions")
    p.add_argument("--max-trades-per-hour", type=int, default=6, dest="max_trades_per_hour")
    p.add_argument("--min-seconds-between-trades", type=int, default=120,
                   dest="min_seconds_between_trades")
    p.add_argument("--max-consecutive-losses", type=int, default=3, dest="max_consecutive_losses")
    p.add_argument("--cooldown-minutes-after-loss-streak", type=int, default=30,
                   dest="cooldown_minutes_after_loss_streak")
    p.add_argument("--max-spread-points", type=float, default=None, dest="max_spread_points",
                   help="Override the per-risk-mode spread ceiling (balanced 35 / scalp 25).")
    p.add_argument("--json", action="store_true", dest="json_output")
    return p.parse_args(argv)


def _refuse_live(args) -> bool:
    if getattr(args, "environment", "demo") == "live":
        print("error: live environment is hard-locked and not implemented "
              "(LIVE_NOT_IMPLEMENTED). This tool runs demo/paper only.", file=sys.stderr)
        return True
    return False


def main(argv=None) -> int:
    args = parse_args(argv)
    if _refuse_live(args):
        return 2
    cfg = WorkerConfig(
        mode=args.mode, environment=args.environment, risk_mode=args.risk_mode,
        interval_seconds=args.interval_seconds,
        max_iterations=args.max_iterations, symbol=args.symbol, timeframe=args.timeframe,
        bars=args.bars, calendar_file=args.calendar_file,
        macro_events_file=args.macro_events_file, dxy_bias=args.dxy_bias,
        yields_bias=args.yields_bias, geopolitical_risk=args.geopolitical_risk,
        auto_execute_demo=args.auto_execute_demo, confirm_demo_order=args.confirm_demo_order,
        close_on_no_trade=args.close_on_no_trade,
        use_learning_modifiers=args.use_learning_modifiers,
        learning_modifiers_file=args.learning_modifiers_file,
        confidence_scaled_lot=args.confidence_scaled_lot,
        lot_confidence_floor=args.lot_confidence_floor,
        basket_scalp=args.basket_scalp,
        basket_num_positions=args.basket_num_positions,
        basket_max_positions=args.basket_max_positions,
        basket_scale_in=args.basket_scale_in,
        basket_risk_cap_pct=args.basket_risk_cap_pct,
        basket_profit_target_pct=args.basket_profit_target_pct,
        basket_hard_loss_cap_pct=args.basket_hard_loss_cap_pct,
        basket_time_stop_seconds=args.basket_time_stop_seconds,
        basket_cooldown_seconds_after_loss=args.basket_cooldown_seconds_after_loss,
        basket_lock_arm_pct=args.basket_lock_arm_pct,
        basket_lock_floor_frac=args.basket_lock_floor_frac,
        basket_pressure_close=args.basket_pressure_close,
        basket_pressure_min_profit_pct=args.basket_pressure_min_profit_pct,
        basket_pressure_threshold_points=args.basket_pressure_threshold_points,
        basket_pressure_confirm_bars=args.basket_pressure_confirm_bars,
        basket_reversal_close=args.basket_reversal_close,
        basket_reversal_confidence=args.basket_reversal_confidence,
        sync_outcomes_every=args.sync_outcomes_every,
        hard_mode=args.hard_mode,
        hard_max_risk_pct=args.hard_max_risk_pct,
        hard_max_margin_pct=args.hard_max_margin_pct,
        basket_min_confidence=args.basket_min_confidence,
        min_confidence_floor=args.min_confidence_floor,
        discord_session_summary=args.discord_session_summary,
        discord_webhook_url=args.discord_webhook_url,
        reset_safety_state=args.reset_safety_state,
        decision_context_file=args.decision_context_file,
        use_trend_filter=args.use_trend_filter,
        json_output=args.json_output,
        write_status=not args.no_status_file,
        max_open_positions=args.max_open_positions,
        max_trades_per_hour=args.max_trades_per_hour,
        min_seconds_between_trades=args.min_seconds_between_trades,
        max_consecutive_losses=args.max_consecutive_losses,
        cooldown_minutes_after_loss_streak=args.cooldown_minutes_after_loss_streak,
        max_spread_points=args.max_spread_points,
    )

    # LM117: assemble the backtested rule (trend-filter + scalp_momentum only +
    # confidence<80 + ~30min time-exit, 1 position, early exits off, wide disaster
    # SL) so it can be forward-tested on demo. The honest "does +71 hold forward?".
    if args.momentum_forward_test:
        cfg.use_trend_filter = True
        cfg.basket_scalp = True
        cfg.basket_num_positions = 1
        cfg.basket_max_positions = 0
        cfg.basket_scale_in = False
        cfg.basket_time_stop_seconds = 1800.0          # ~30 min hold ≈ replay h30
        cfg.basket_entry_strategy = "scalp_momentum"
        cfg.basket_max_confidence = 80.0
        cfg.basket_leg_sl_points = 1000                # wide disaster stop only
        cfg.basket_leg_tp_points = 2000
        cfg.basket_profit_target_pct = 9999.0          # never (let the time-exit close)
        cfg.basket_pressure_close = False
        cfg.basket_reversal_close = False
        cfg.basket_lock_arm_pct = 0.0                  # lock off
        if cfg.sync_outcomes_every <= 0:
            cfg.sync_outcomes_every = 100              # record outcomes for the forward check

    # LM118: the VALIDATED M15 swing config (positive 2025 AND 2026 out-of-sample).
    # M15 / balanced / trend-filter / all detectors / ~7.5h time-exit / 1 position /
    # early exits off / wide disaster SL so the time-exit dominates.
    if args.m15_swing_test:
        cfg.timeframe = "M15"
        cfg.risk_mode = "balanced"
        cfg.bars = max(cfg.bars, 200)
        cfg.use_trend_filter = True
        cfg.basket_scalp = True
        cfg.basket_num_positions = 1
        cfg.basket_max_positions = 0
        cfg.basket_scale_in = False
        cfg.basket_time_stop_seconds = 27000.0         # ~h30 on M15 (30 x 15min = 7.5h)
        cfg.basket_entry_strategy = None               # all detectors (M15 positive across all)
        cfg.basket_max_confidence = 0.0
        cfg.basket_leg_sl_points = 3000                # wide disaster stop; time-exit dominates
        cfg.basket_leg_tp_points = 6000
        cfg.basket_profit_target_pct = 9999.0
        cfg.basket_pressure_close = False
        cfg.basket_reversal_close = False
        cfg.basket_lock_arm_pct = 0.0
        if cfg.sync_outcomes_every <= 0:
            cfg.sync_outcomes_every = 50
    return GoldBotWorker(cfg).run()


if __name__ == "__main__":
    raise SystemExit(main())
