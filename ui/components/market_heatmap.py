"""
ui/components/market_heatmap.py
--------------------------------
Market heatmap component for the Pro Dashboard.

render_market_heatmap(items)

Items show symbol, price, change_pct and setup_score as colored tiles.
Color is driven by change_pct. Setup score is shown as a badge.
No external charts, no API calls.
"""

from __future__ import annotations

import streamlit as st

# ── CSS ───────────────────────────────────────────────────────────────────────

_HEATMAP_CSS = """<style>
.hm-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
    gap: 10px;
    margin: 8px 0 16px;
}
.hm-tile {
    border-radius: 12px;
    padding: 14px 16px;
    border: 1px solid transparent;
    cursor: default;
    transition: transform .1s ease, box-shadow .1s ease;
}
.hm-tile:hover {
    transform: translateY(-2px);
    box-shadow: 0 6px 20px rgba(0,0,0,.3);
}
.hm-tile.pos-strong {
    background: rgba(34,197,94,.18);
    border-color: rgba(34,197,94,.35);
}
.hm-tile.pos-mild {
    background: rgba(34,197,94,.09);
    border-color: rgba(34,197,94,.20);
}
.hm-tile.neutral {
    background: #1e1f23;
    border-color: #2a2b30;
}
.hm-tile.neg-mild {
    background: rgba(239,68,68,.09);
    border-color: rgba(239,68,68,.20);
}
.hm-tile.neg-strong {
    background: rgba(239,68,68,.18);
    border-color: rgba(239,68,68,.35);
}
.hm-sym {
    font-size: 13px;
    font-weight: 700;
    color: #f5f5f7;
    margin-bottom: 4px;
    letter-spacing: .01em;
}
.hm-price {
    font-size: 16px;
    font-weight: 600;
    color: #f5f5f7;
    margin-bottom: 3px;
    font-family: monospace;
}
.hm-chg {
    font-size: 12px;
    font-weight: 700;
    margin-bottom: 6px;
}
.hm-chg.pos { color: #4ade80; }
.hm-chg.neg { color: #f87171; }
.hm-chg.flat { color: #5a5b62; }
.hm-score-row {
    display: flex;
    align-items: center;
    gap: 6px;
}
.hm-score-badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 8px;
    font-size: 10px;
    font-weight: 700;
}
.hm-score-badge.high {
    background: rgba(124,92,252,.20);
    color: #a78bfa;
    border: 1px solid rgba(124,92,252,.35);
}
.hm-score-badge.mid {
    background: rgba(251,191,36,.12);
    color: #fbbf24;
    border: 1px solid rgba(251,191,36,.28);
}
.hm-score-badge.low {
    background: rgba(100,116,139,.12);
    color: #64748b;
    border: 1px solid rgba(100,116,139,.22);
}
.hm-score-lbl {
    font-size: 10px;
    color: #4a4b52;
}
</style>"""

def _inject_heatmap_css() -> None:
    st.markdown(_HEATMAP_CSS, unsafe_allow_html=True)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _tile_class(change_pct: float) -> str:
    if change_pct >= 3.0:
        return "pos-strong"
    if change_pct >= 0.5:
        return "pos-mild"
    if change_pct <= -3.0:
        return "neg-strong"
    if change_pct <= -0.5:
        return "neg-mild"
    return "neutral"


def _chg_class(change_pct: float) -> str:
    if change_pct > 0.1:
        return "pos"
    if change_pct < -0.1:
        return "neg"
    return "flat"


def _score_badge_class(score: float) -> str:
    if score >= 70:
        return "high"
    if score >= 45:
        return "mid"
    return "low"


def _fmt_price(price: float) -> str:
    if price >= 1_000:
        return f"${price:,.2f}"
    if price >= 1:
        return f"${price:.3f}"
    if price >= 0.001:
        return f"${price:.5f}"
    return f"${price:.8f}"


# ── Public API ────────────────────────────────────────────────────────────────

def render_market_heatmap(items: list[dict]) -> None:
    """
    Render a grid of colored market tiles.

    Each item dict may contain:
        symbol      (str)   — e.g. "BTC", "ETH"
        price       (float) — current price in USD
        change_pct  (float) — 24h change, e.g. 1.5 for +1.5%
        setup_score (float) — 0–100 pro setup score
        market_type (str)   — optional "spot" / "perp"

    Color logic:
        >= +3%   → strong green tile
        +0.5–3%  → mild green tile
        ±0.5%    → neutral grey tile
        -0.5–3%  → mild red tile
        <= -3%   → strong red tile

    Score badge:
        >= 70 → purple  (high setup probability)
        45–69 → yellow  (watch)
        < 45  → grey    (low)

    Args:
        items: List of market dicts.

    Example:
        render_market_heatmap([
            {"symbol": "BTC", "price": 67420.0,
             "change_pct": 1.4, "setup_score": 78},
        ])
    """
    _inject_heatmap_css()

    if not items:
        st.caption("No market data.")
        return

    # Build entire grid as one self-contained HTML block
    tiles_html = ""
    for item in items:
        sym    = str(item.get("symbol", "?"))
        price  = float(item.get("price", 0))
        chg    = float(item.get("change_pct", 0))
        score  = float(item.get("setup_score", 0))
        mtype  = str(item.get("market_type", "spot"))

        tile_cls  = _tile_class(chg)
        chg_cls   = _chg_class(chg)
        score_cls = _score_badge_class(score)
        chg_sign  = "+" if chg > 0 else ""
        mtype_lbl = "PERP" if mtype == "perp" else "SPOT"

        tiles_html += (
            f'<div class="hm-tile {tile_cls}">'
            f'<div class="hm-sym">{sym} <span style="font-size:9px;color:#3a3b42;'
            f'font-weight:500">{mtype_lbl}</span></div>'
            f'<div class="hm-price">{_fmt_price(price)}</div>'
            f'<div class="hm-chg {chg_cls}">{chg_sign}{chg:.2f}%</div>'
            f'<div class="hm-score-row">'
            f'<span class="hm-score-badge {score_cls}">{score:.0f}</span>'
            f'<span class="hm-score-lbl">setup score</span>'
            f'</div>'
            f'</div>'
        )

    # One self-contained st.markdown call — grid open + all tiles + grid close
    st.markdown(
        f'<div class="hm-grid">{tiles_html}</div>',
        unsafe_allow_html=True,
    )
