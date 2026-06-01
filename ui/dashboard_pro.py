"""
ui/dashboard_pro.py
--------------------
Pro Market Overview Dashboard — Command Center MVP.

Renders a full dashboard page using demo/sample data.
No live API calls in this file.

Sections:
  1. Header strip
  2. Market KPIs
  3. Heatmap (with "Open in Pro Terminal" buttons per symbol)
  4. Market Stats
  5. Top Pro Setups (with "Open in Pro Terminal" per setup)
  6. Whale Alerts placeholder
  7. Meme Alpha Beta Preview

Interactivity:
  Clicking "Open in Pro Terminal" for any symbol stores the symbol in
  st.session_state["pro_selected_symbol"] and navigates to Pro Terminal.
"""

from __future__ import annotations

import streamlit as st

from ui.components.market_cards import render_market_kpi_cards, render_market_stat_cards
from ui.components.market_heatmap import render_market_heatmap

# Scanner — guarded: dashboard must work even if services/ not deployed
try:
    from services.pro_market_scanner import scan_markets as _scan_markets
    _SCANNER_AVAILABLE = True
except Exception:
    _SCANNER_AVAILABLE = False
    def _scan_markets(symbols=None):
        return []

# ── CSS ───────────────────────────────────────────────────────────────────────

_CSS = """<style>
.dash-title {
    font-size: 26px; font-weight: 700; color: #f5f5f7;
    padding: 22px 0 2px; letter-spacing: -.01em;
}
.dash-sub { font-size: 14px; color: #5a5b62; margin-bottom: 20px; }
.dash-badge {
    display: inline-block; padding: 4px 12px;
    border-radius: 20px; font-size: 11px; font-weight: 700;
}
.dash-badge.demo {
    background: rgba(251,191,36,.12); color: #fbbf24;
    border: 1px solid rgba(251,191,36,.28);
}
.dash-section-label {
    font-size: 10px; font-weight: 600; color: #3a3b42;
    letter-spacing: .09em; text-transform: uppercase;
    margin: 20px 0 10px;
}
.setup-card {
    background: #1a1b1f; border: 1px solid #2a2b30;
    border-radius: 14px; padding: 14px 16px;
}
.setup-card.strong { border-color: rgba(124,92,252,.40); }
.setup-card.watch  { border-color: rgba(251,191,36,.30); }
.setup-top {
    display: flex; justify-content: space-between;
    align-items: flex-start; margin-bottom: 8px;
}
.setup-sym  { font-size: 16px; font-weight: 700; color: #f5f5f7; }
.setup-type { font-size: 11px; color: #5a5b62; margin-top: 2px; }
.setup-score {
    font-size: 22px; font-weight: 700; color: #a78bfa;
    text-align: right; line-height: 1;
}
.setup-score-lbl { font-size: 10px; color: #4a4b52; text-align: right; }
.setup-reason { font-size: 12px; color: #9090a0; line-height: 1.4; margin-bottom: 8px; }
.setup-tags { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 10px; }
.setup-tag {
    display: inline-block; padding: 2px 8px; border-radius: 7px;
    font-size: 10px; font-weight: 600;
    background: rgba(124,92,252,.12); color: #a78bfa;
    border: 1px solid rgba(124,92,252,.22);
}
.setup-tag.g {
    background: rgba(34,197,94,.10); color: #4ade80;
    border-color: rgba(34,197,94,.22);
}
.setup-tag.y {
    background: rgba(251,191,36,.10); color: #fbbf24;
    border-color: rgba(251,191,36,.22);
}
.setup-tag.r {
    background: rgba(239,68,68,.10); color: #f87171;
    border-color: rgba(239,68,68,.22);
}
.whale-feed {
    background: #1a1b1f; border: 1px solid #2a2b30;
    border-radius: 12px; overflow: hidden;
}
.whale-row {
    display: flex; align-items: center; gap: 12px;
    padding: 10px 14px; border-bottom: 1px solid #23242a; font-size: 12px;
}
.whale-row:last-child { border-bottom: none; }
.whale-icon { font-size: 16px; flex-shrink: 0; }
.whale-text { flex: 1; color: #c0c0c8; line-height: 1.35; }
.whale-text b { color: #f5f5f7; }
.whale-time { font-size: 10px; color: #3a3b42; white-space: nowrap; }
.alpha-preview {
    background: linear-gradient(135deg,rgba(124,92,252,.10),rgba(18,19,22,.98));
    border: 1px solid rgba(124,92,252,.30); border-radius: 14px;
    padding: 18px 20px;
}
.alpha-preview-title {
    font-size: 15px; font-weight: 700; color: #a78bfa; margin-bottom: 4px;
}
.alpha-preview-sub {
    font-size: 13px; color: #5a5b62; margin-bottom: 12px; line-height: 1.45;
}
.alpha-stat-row { display: flex; gap: 20px; flex-wrap: wrap; margin-bottom: 14px; }
.alpha-stat { display: flex; flex-direction: column; }
.alpha-stat span { font-size: 10px; color: #4a4b52; text-transform: uppercase; }
.alpha-stat b { font-size: 16px; font-weight: 600; color: #c0c0c8; }
.dash-divider { height: 1px; background: #23242a; margin: 8px 0; }
</style>"""


# ── Demo data ─────────────────────────────────────────────────────────────────

_KPI_CARDS = [
    {"label": "Bitcoin",         "value": "$67,420", "color": "g",
     "sub": "+1.4% today",       "sub_color": "g",   "icon": "₿"},
    {"label": "Global 24h Vol",  "value": "$112.4B", "color": "",
     "sub": "vs $98.1B yesterday","sub_color": "g",  "icon": "📊"},
    {"label": "Fear & Greed",    "value": "72 — Greed","color": "y",
     "sub": "Up from 68",        "sub_color": "",    "icon": "🌡"},
    {"label": "BTC Dominance",   "value": "52.4%",   "color": "",
     "sub": "-0.3% from yesterday","sub_color": "r", "icon": "⚡"},
]

# symbol -> Binance ticker (used for Pro Terminal navigation)
_HEATMAP_ITEMS = [
    {"symbol": "BTC",  "ticker": "BTCUSDT",  "price": 67_420.0,  "change_pct":  1.42, "setup_score": 78, "market_type": "spot"},
    {"symbol": "ETH",  "ticker": "ETHUSDT",  "price":  3_512.5,  "change_pct":  0.87, "setup_score": 64, "market_type": "spot"},
    {"symbol": "SOL",  "ticker": "SOLUSDT",  "price":    174.3,  "change_pct":  3.21, "setup_score": 82, "market_type": "spot"},
    {"symbol": "HYPE", "ticker": "HYPEUSDT", "price":     28.14, "change_pct":  5.60, "setup_score": 91, "market_type": "perp"},
    {"symbol": "BNB",  "ticker": "BNBUSDT",  "price":    612.8,  "change_pct": -0.34, "setup_score": 42, "market_type": "spot"},
    {"symbol": "ARB",  "ticker": "ARBUSDT",  "price":      1.18, "change_pct": -2.10, "setup_score": 35, "market_type": "perp"},
    {"symbol": "INJ",  "ticker": "INJUSDT",  "price":     24.55, "change_pct":  1.95, "setup_score": 58, "market_type": "spot"},
    {"symbol": "SUI",  "ticker": "SUIUSDT",  "price":      1.74, "change_pct": -0.80, "setup_score": 47, "market_type": "spot"},
]

_MARKET_STATS = [
    {"label": "BTC Futures OI",     "value": "$18.2B",    "color": ""},
    {"label": "ETH Futures OI",     "value": "$9.4B",     "color": ""},
    {"label": "Total Liquidations", "value": "$142M 24h", "color": "r"},
    {"label": "Long / Short Ratio", "value": "54% / 46%", "color": "g"},
    {"label": "SOL Perp Funding",   "value": "+0.012%",   "color": "g"},
    {"label": "HYPE Perp Funding",  "value": "+0.031%",   "color": "y"},
    {"label": "Stablecoin Supply",  "value": "$162B",     "color": ""},
    {"label": "Active Addresses",   "value": "1.24M",     "color": ""},
]

_TOP_SETUPS = [
    {
        "symbol":  "HYPEUSDT",
        "display": "HYPE",
        "type":    "Perp / Break of structure",
        "score":   91,
        "reason":  "Strong bid-side imbalance (+0.71) with $8.4M bid wall at key "
                   "structure level. High liquidity score (88/100). Funding neutral.",
        "tags":    [("BOS", ""), ("Bid Wall", "g"), ("High Liq", "g"), ("Perp", "")],
        "tier":    "strong",
    },
    {
        "symbol":  "SOLUSDT",
        "display": "SOL",
        "type":    "Spot / Momentum continuation",
        "score":   82,
        "reason":  "Clean breakout above $170 with expanding volume. Ask walls "
                   "absorbed at $174 resistance. Early wallets accumulating.",
        "tags":    [("Breakout", "g"), ("Vol+", "g"), ("Alpha", ""), ("Spot", "")],
        "tier":    "strong",
    },
    {
        "symbol":  "INJUSDT",
        "display": "INJ",
        "type":    "Spot / Range compression",
        "score":   58,
        "reason":  "Tight spread (0.018%) and balanced book. Watching for directional "
                   "break above $25.2. Insufficient confluence for strong signal.",
        "tags":    [("Range", "y"), ("Watch", "y"), ("Spot", "")],
        "tier":    "watch",
    },
]

_WHALE_ALERTS = [
    {"icon": "🐳", "text": "<b>2,840 BTC</b> moved from unknown wallet to Binance hot wallet",    "time": "4 min ago"},
    {"icon": "💸", "text": "<b>$48M USDC</b> minted on Ethereum — Tether Treasury",               "time": "11 min ago"},
    {"icon": "🔴", "text": "<b>120,000 SOL</b> ($20.9M) transferred to exchange — possible sell", "time": "22 min ago"},
    {"icon": "🐳", "text": "<b>9,500 ETH</b> withdrawn from Coinbase to cold wallet",             "time": "38 min ago"},
    {"icon": "💡", "text": "<b>$12.4M HYPE</b> opened as long on Hyperliquid perp",              "time": "51 min ago"},
]

# Symbols available in Pro Terminal's Binance connector
_TERMINAL_SYMBOLS = {"BTCUSDT", "ETHUSDT", "SOLUSDT"}


# ── Navigation helper ─────────────────────────────────────────────────────────

def _open_in_terminal(ticker: str, key: str) -> None:
    """Render an 'Open in Pro Terminal' button. On click, stores symbol and navigates."""
    if st.button("Open in Pro Terminal", key=key, use_container_width=True):
        st.session_state["pro_selected_symbol"] = ticker
        st.session_state["main_navigation"] = "Pro Terminal"
        st.rerun()


# ── Section renderers ─────────────────────────────────────────────────────────

def _render_header() -> None:
    st.markdown(
        '<div class="dash-title">Command Center</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="dash-sub">'
        'Pro market overview — BTC, ETH, SOL, HYPE. '
        '<span class="dash-badge demo">DEMO DATA</span>'
        '</div>',
        unsafe_allow_html=True,
    )


def _render_heatmap_with_buttons(items: list[dict]) -> None:
    """Render heatmap tiles + Open in Pro Terminal button per symbol row."""
    # Pass items to the heatmap component (it renders the coloured grid)
    render_market_heatmap(items)

    # Button row — one button per symbol that Terminal supports
    st.markdown(
        '<div class="dash-section-label">Open symbol in Pro Terminal</div>',
        unsafe_allow_html=True,
    )
    btn_items = [i for i in items if i["ticker"] in _TERMINAL_SYMBOLS]
    extra_items = [i for i in items if i["ticker"] not in _TERMINAL_SYMBOLS]

    cols = st.columns(len(btn_items) + len(extra_items))
    idx = 0
    for item in btn_items:
        with cols[idx]:
            _open_in_terminal(item["ticker"], key=f"hm_open_{item['ticker']}")
            st.caption(item["symbol"])
        idx += 1
    for item in extra_items:
        with cols[idx]:
            st.button(
                f"{item['symbol']} (no live data)",
                key=f"hm_na_{item['ticker']}",
                disabled=True,
                use_container_width=True,
            )
            st.caption("Not on Binance")
        idx += 1



def _signals_to_setup_cards(signals) -> list[dict]:
    """Convert ProSetupSignal objects to the dict format _render_setup_cards expects."""
    cards = []
    for sig in signals:
        score = sig.score
        risk  = sig.risk_level   # "low" / "medium" / "high" / "extreme"
        level = sig.signal_level  # "strong_buy" / "buy" / "watch" / "neutral" / "avoid"

        # Tier drives border colour on the card
        if score >= 75:
            tier = "strong"
        elif score >= 50:
            tier = "watch"
        else:
            tier = ""

        # Tags: signal level + risk + market_type
        _risk_cls = {"low": "g", "medium": "y", "high": "r", "extreme": "r"}.get(risk, "")
        _lvl_cls  = {"strong_buy": "g", "buy": "g", "watch": "y",
                     "neutral": "", "avoid": "r", "strong_sell": "r"}.get(level, "")
        tags = [
            (level.replace("_", " ").title(), _lvl_cls),
            (f"{risk.title()} risk", _risk_cls),
            (sig.market_type.upper(), ""),
        ]

        # Display symbol: strip USDT suffix for readability
        display = sig.symbol.replace("USDT", "").replace("USD", "") or sig.symbol

        # Terminal symbol: only BTCUSDT / ETHUSDT / SOLUSDT go to live Binance
        terminal_sym = sig.symbol if sig.symbol in _TERMINAL_SYMBOLS else ""

        cards.append({
            "symbol":  terminal_sym or sig.symbol,
            "display": display,
            "type":    f"{sig.market_type.capitalize()} / {level.replace('_', ' ').title()}",
            "score":   int(score),
            "reason":  sig.reason[:180] if sig.reason else "No reason available.",
            "tags":    tags,
            "tier":    tier,
        })
    return cards

def _render_setup_cards(setups: list[dict]) -> None:
    cols = st.columns(len(setups))
    for col, s in zip(cols, setups):
        with col:
            tags_html = "".join(
                f'<span class="setup-tag {cls}">{name}</span>'
                for name, cls in s["tags"]
            )
            st.markdown(
                f'<div class="setup-card {s["tier"]}">'
                f'<div class="setup-top">'
                f'<div>'
                f'<div class="setup-sym">{s["display"]}</div>'
                f'<div class="setup-type">{s["type"]}</div>'
                f'</div>'
                f'<div>'
                f'<div class="setup-score">{s["score"]}</div>'
                f'<div class="setup-score-lbl">score</div>'
                f'</div>'
                f'</div>'
                f'<div class="setup-reason">{s["reason"]}</div>'
                f'<div class="setup-tags">{tags_html}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
            # "Open in Pro Terminal" — only for supported Binance symbols
            if s["symbol"] in _TERMINAL_SYMBOLS:
                _open_in_terminal(s["symbol"], key=f"setup_open_{s['symbol']}")
            else:
                st.caption(f"{s['display']}: no live Binance data")


def _render_whale_feed(alerts: list[dict]) -> None:
    rows_html = "".join(
        f'<div class="whale-row">'
        f'<span class="whale-icon">{a["icon"]}</span>'
        f'<span class="whale-text">{a["text"]}</span>'
        f'<span class="whale-time">{a["time"]}</span>'
        f'</div>'
        for a in alerts
    )
    st.markdown(
        f'<div class="whale-feed">{rows_html}</div>',
        unsafe_allow_html=True,
    )


def _render_alpha_preview() -> None:
    st.markdown(
        '<div class="alpha-preview">'
        '<div class="alpha-preview-title">Solana Meme Alpha — Beta</div>'
        '<div class="alpha-preview-sub">'
        'Smart wallet tracking, early buyer discovery, paper trading simulation.'
        '</div>'
        '<div class="alpha-stat-row">'
        '<div class="alpha-stat"><span>Wallets tracked</span><b>12</b></div>'
        '<div class="alpha-stat"><span>Hot wallets now</span>'
        '<b style="color:#fbbf24">3</b></div>'
        '<div class="alpha-stat"><span>Early tokens found</span><b>47</b></div>'
        '<div class="alpha-stat"><span>Paper P/L</span>'
        '<b style="color:#4ade80">+$184</b></div>'
        '</div>'
        '</div>',
        unsafe_allow_html=True,
    )


# ── Main render function ───────────────────────────────────────────────────────

def render_pro_dashboard() -> None:
    """
    Render the full Pro Market Overview Dashboard.

    Attempts to fetch live ProSetupSignals from services/pro_market_scanner.
    Falls back to static demo data if scanner is unavailable or fails.
    Symbols in the heatmap and setup cards have "Open in Pro Terminal" buttons.
    """
    st.markdown(_CSS, unsafe_allow_html=True)

    # ── Try live scanner ──────────────────────────────────────────────────────
    _live_signals: list = []
    _scanner_error: str = ""
    _mode: str = "demo"

    if _SCANNER_AVAILABLE:
        try:
            _live_signals = _scan_markets() or []
            if _live_signals:
                _mode = "live"
        except Exception as exc:
            _scanner_error = str(exc)

    # ── Decide which setup cards to show ──────────────────────────────────────
    if _mode == "live" and _live_signals:
        _setup_cards = _signals_to_setup_cards(_live_signals[:3])
    else:
        _setup_cards = _TOP_SETUPS  # static demo

    # 1. Header
    _render_header()

    # 2. Market KPIs
    st.markdown('<div class="dash-section-label">Market KPIs</div>', unsafe_allow_html=True)
    render_market_kpi_cards(_KPI_CARDS)

    # 3. Heatmap + Terminal buttons
    st.markdown('<div class="dash-section-label">Market Heatmap</div>', unsafe_allow_html=True)
    _render_heatmap_with_buttons(_HEATMAP_ITEMS)

    # 4. Market Stats
    st.markdown('<div class="dash-section-label">Market Stats</div>', unsafe_allow_html=True)
    render_market_stat_cards(_MARKET_STATS)

    st.markdown('<div class="dash-divider"></div>', unsafe_allow_html=True)

    # 5. Top Pro Setups + Whale Alerts
    left_col, right_col = st.columns([0.62, 0.38])
    with left_col:
        _setup_label_col, _mode_col = st.columns([0.7, 0.3])
        with _setup_label_col:
            st.markdown('<div class="dash-section-label">Top Pro Setups</div>', unsafe_allow_html=True)
        with _mode_col:
            if _mode == "live":
                st.markdown(
                    '<div style="font-size:10px;color:#4ade80;font-weight:600;'
                    'padding-top:22px;text-align:right">Mode: Live scanner</div>',
                    unsafe_allow_html=True,
                )
            else:
                _fallback_reason = "scanner unavailable" if not _SCANNER_AVAILABLE else (
                    f"error: {_scanner_error[:40]}" if _scanner_error else "no signals returned"
                )
                st.markdown(
                    f'<div style="font-size:10px;color:#5a5b62;font-weight:600;'
                    f'padding-top:22px;text-align:right">'
                    f'Mode: Demo fallback<br>'
                    f'<span style="font-weight:400;color:#3a3b42">{_fallback_reason}</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
        _render_setup_cards(_setup_cards)

    with right_col:
        st.markdown('<div class="dash-section-label">Whale Alerts</div>', unsafe_allow_html=True)
        _render_whale_feed(_WHALE_ALERTS)

    st.markdown('<div class="dash-divider"></div>', unsafe_allow_html=True)

    # 6. Meme Alpha Beta preview
    st.markdown('<div class="dash-section-label">Meme Alpha Beta</div>', unsafe_allow_html=True)
    _render_alpha_preview()

    # 7. Footer
    _footer_note = (
        "Top Pro Setups are live-scored from Binance orderbook data."
        if _mode == "live"
        else "Top Pro Setups show static demo data — scanner unavailable or failed."
    )
    st.markdown(
        f'<div style="font-size:11px;color:#3a3b42;margin-top:18px;padding-bottom:8px">'
        f'{_footer_note} KPIs, heatmap and stats are static demo data.'
        f'</div>',
        unsafe_allow_html=True,
    )
