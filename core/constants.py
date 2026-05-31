"""
core/constants.py
-----------------
Shared constants for the Pro Trading Terminal.

Rules:
- No Streamlit imports.
- No network calls.
- No external dependencies.
- No mutable defaults. All collections are tuples or frozensets.
- Add new constants here. Never hardcode magic values in app.py or ui/.
"""

# ── Chains ────────────────────────────────────────────────────────────────────

SUPPORTED_CHAINS: tuple[str, ...] = (
    "solana",
    "ethereum",
    "bsc",
    "base",
    "arbitrum",
    "optimism",
    "polygon",
    "avalanche",
)

CHAIN_DISPLAY_NAMES: dict[str, str] = {
    "solana":    "Solana",
    "ethereum":  "Ethereum",
    "bsc":       "BNB Chain",
    "base":      "Base",
    "arbitrum":  "Arbitrum",
    "optimism":  "Optimism",
    "polygon":   "Polygon",
    "avalanche": "Avalanche",
}


# ── Market types ──────────────────────────────────────────────────────────────

MARKET_TYPES: tuple[str, ...] = (
    "spot",
    "perp",
    "futures",
    "option",
)


# ── Pro Terminal — default markets ────────────────────────────────────────────
# These are the markets shown by default in the Pro Terminal command center.
# Symbol format: BASE + QUOTE, no separator (Binance/Bybit standard).

DEFAULT_PRO_MARKETS: tuple[str, ...] = (
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "HYPEUSDT",
)

# Extended watchable markets (user can add from these)
WATCHABLE_PRO_MARKETS: tuple[str, ...] = (
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "HYPEUSDT",
    "BNBUSDT",
    "XRPUSDT",
    "ADAUSDT",
    "AVAXUSDT",
    "DOTUSDT",
    "LINKUSDT",
    "ARBUSDT",
    "OPUSDT",
    "INJUSDT",
    "SUIUSDT",
    "APTUSDT",
)


# ── Feature flags ─────────────────────────────────────────────────────────────
# Runtime-readable flags. Can be overridden by environment variables.
# Values here are the defaults when no env var is set.

FEATURE_FLAGS: dict[str, bool] = {
    "pro_terminal":        False,   # Phase 3: live orderbook + market structure terminal
    "meme_alpha":          True,    # Beta: Solana smart wallet + token discovery
    "paper_trading":       True,    # Paper trading simulation
    "telegram_alerts":     False,   # Telegram push notifications
    "auto_copy_signals":   False,   # Automated copy trading signals
    "pattern_engine":      False,   # Phase 5: early buyer pattern detection
    "multi_user":          False,   # Phase 6: per-user data isolation
    "demo_mode":           False,   # Phase 6: read-only demo with fake data
    "admin_panel":         False,   # Admin usage overview
    "export_csv":          False,   # CSV export for watchlist/trades/signals
}


# ── Plans ─────────────────────────────────────────────────────────────────────

PLAN_IDS: dict[str, str] = {
    "free":  "free",
    "beta":  "beta",    # Current access level for test users
    "pro":   "pro",     # Phase 4: Pro Terminal access
    "alpha": "alpha",   # Phase 5: Full Pro + Meme Alpha access
    "admin": "admin",   # Internal admin access
}

# Features accessible per plan (feature_flag_key → minimum plan required)
PLAN_FEATURES: dict[str, str] = {
    "meme_alpha":        "beta",
    "paper_trading":     "beta",
    "pro_terminal":      "pro",
    "auto_copy_signals": "pro",
    "telegram_alerts":   "pro",
    "pattern_engine":    "alpha",
    "multi_user":        "admin",
    "admin_panel":       "admin",
}

# Plan hierarchy for gating checks (higher index = higher access)
PLAN_HIERARCHY: tuple[str, ...] = ("free", "beta", "pro", "alpha", "admin")


# ── Signal levels ─────────────────────────────────────────────────────────────
# Used by services/signal_engine.py and services/pro/setup_score.py

SIGNAL_LEVELS: dict[str, int] = {
    "strong_buy":  5,
    "buy":         4,
    "watch":       3,
    "neutral":     2,
    "avoid":       1,
    "strong_sell": 0,
}

SIGNAL_DISPLAY: dict[str, str] = {
    "strong_buy":  "Strong Buy",
    "buy":         "Buy",
    "watch":       "Watch",
    "neutral":     "Neutral",
    "avoid":       "Avoid",
    "strong_sell": "Strong Sell",
}

SIGNAL_COLORS: dict[str, str] = {
    "strong_buy":  "#22c55e",
    "buy":         "#4ade80",
    "watch":       "#fbbf24",
    "neutral":     "#94a3b8",
    "avoid":       "#f87171",
    "strong_sell": "#ef4444",
}


# ── Risk levels ───────────────────────────────────────────────────────────────

RISK_LEVELS: dict[str, int] = {
    "low":     1,
    "medium":  2,
    "high":    3,
    "extreme": 4,
}

RISK_DISPLAY: dict[str, str] = {
    "low":     "Low Risk",
    "medium":  "Medium Risk",
    "high":    "High Risk",
    "extreme": "Extreme Risk",
}

RISK_COLORS: dict[str, str] = {
    "low":     "#4ade80",
    "medium":  "#fbbf24",
    "high":    "#f87171",
    "extreme": "#ef4444",
}


# ── Wallet scoring thresholds ─────────────────────────────────────────────────
# Used by services/wallet_scorer.py

WALLET_SCORE_THRESHOLDS: dict[str, int] = {
    "alpha_scout":  80,   # >= 80: Alpha Scout — copy candidate
    "worth_watch":  65,   # >= 65: Worth watching
    "paper_first":  45,   # >= 45: Paper trade first
    "needs_proof":   0,   # < 45:  Needs more proof
}

WALLET_VERDICT_LABELS: dict[str, str] = {
    "alpha_scout": "Alpha Scout",
    "worth_watch": "Worth watching",
    "paper_first": "Paper trade first",
    "needs_proof": "Needs more proof",
}


# ── Timing ────────────────────────────────────────────────────────────────────

DEFAULT_CACHE_TTL_SECONDS: int = 30           # Default API cache TTL
DEFAULT_AUTO_REFRESH_MS: int = 2_000          # Default auto-refresh interval (ms)
DEFAULT_PAPER_TRADE_REFRESH_MS: int = 2_000   # Paper Trading live P/L refresh


# ── Limits ────────────────────────────────────────────────────────────────────

MAX_WATCHLIST_WALLETS: int = 50
MAX_RECENT_WALLETS: int = 20
MAX_DISCOVERY_RESULTS: int = 15
MAX_PAPER_TRADES: int = 20
MAX_JOURNAL_ENTRIES: int = 100
MAX_NOTE_LENGTH: int = 1_000
MAX_LABEL_LENGTH: int = 80


if __name__ == "__main__":
    # Sanity checks
    assert "solana" in SUPPORTED_CHAINS
    assert "BTCUSDT" in DEFAULT_PRO_MARKETS
    assert "HYPEUSDT" in DEFAULT_PRO_MARKETS
    assert all(k in PLAN_HIERARCHY for k in PLAN_IDS.values())
    assert all(v in PLAN_HIERARCHY for v in PLAN_FEATURES.values())
    assert set(SIGNAL_LEVELS.keys()) == set(SIGNAL_DISPLAY.keys()) == set(SIGNAL_COLORS.keys())
    assert set(RISK_LEVELS.keys()) == set(RISK_DISPLAY.keys()) == set(RISK_COLORS.keys())
    assert WALLET_SCORE_THRESHOLDS["alpha_scout"] > WALLET_SCORE_THRESHOLDS["worth_watch"]
    print("core/constants.py — all assertions passed.")
