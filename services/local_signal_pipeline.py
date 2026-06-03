"""
services/local_signal_pipeline.py
----------------------------------
LM55 — Local smoke pipeline connecting the pure Python signal engines.

Flow: wall_events -> wall_features -> setups -> signals -> journal.
NO UI, NO API, NO DB, NO network.

Public entry:
    run_local_signal_pipeline(previous_walls, current_walls, options=None) -> dict
"""

from __future__ import annotations

from services.liquidity_wall_events import detect_wall_events
from services.wall_persistence_features import compute_wall_features
from services.setup_classifier import classify_setups
from services.signal_builder import build_signals
from services.signal_journal import (
    create_signal_journal_entries,
    summarize_signal_journal,
)


def run_local_signal_pipeline(previous_walls, current_walls, options=None):
    """
    Run the full local signal pipeline from wall snapshots to journal entries.

    Returns dict with events, features, setups, signals, journal_entries, summary.
    """
    opts = options or {}
    symbol = str(opts.get("symbol", "") or "")
    exchange = str(opts.get("exchange", "binance_spot") or "binance_spot")
    timeframe = str(opts.get("timeframe", "") or "")
    current_price = opts.get("current_price")

    events = detect_wall_events(
        previous_walls=previous_walls,
        current_walls=current_walls,
        symbol=symbol,
        exchange=exchange,
        timeframe=timeframe,
        current_price=current_price,
    )

    features = compute_wall_features(events)
    setups = classify_setups(features)
    signals = build_signals(setups)
    journal_entries = create_signal_journal_entries(signals)
    summary = summarize_signal_journal(journal_entries)

    return {
        "events": events,
        "features": features,
        "setups": setups,
        "signals": signals,
        "journal_entries": journal_entries,
        "summary": summary,
    }
