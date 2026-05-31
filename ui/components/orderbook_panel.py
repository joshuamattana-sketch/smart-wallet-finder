"""
ui/components/orderbook_panel.py
---------------------------------
Reusable Streamlit component for rendering order book metrics.

Stability contract:
- Zero module-level mutable state (no _css_injected flag).
  CSS is injected on every render call — Streamlit deduplicates it.
- unsafe_allow_html is used for exactly ONE purpose: the <style> block.
  Every other element uses st.container / st.columns / st.metric /
  st.dataframe / st.caption / st.markdown (plain text only).
- No HTML that spans multiple st.* calls.
- No dynamic f-string HTML for data values.
- Renders identically on first load, symbol change, and manual refresh.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from core.constants import SIGNAL_COLORS, SIGNAL_DISPLAY
from core.formatting import format_usd, safe_float
from core.models import OrderBookLevel, OrderBookMetrics, OrderBookSnapshot

# ── One-time CSS — injected on every call, Streamlit deduplicates ─────────────
_STYLE = """<style>
.ob-verdict-row {
    display: flex; align-items: center; gap: 12px;
    background: #1a1b1f; border: 1px solid #2a2b30;
    border-radius: 12px; padding: 12px 16px; margin-bottom: 12px;
}
.ob-verdict-pill {
    padding: 4px 14px; border-radius: 18px;
    font-size: 11px; font-weight: 700; letter-spacing: .04em;
    white-space: nowrap; flex-shrink: 0;
}
.ob-verdict-reason { font-size: 12px; color: #9090a0; line-height: 1.4; }
.ob-bar-wrap {
    background: #1a1b1f; border: 1px solid #2a2b30;
    border-radius: 10px; padding: 10px 14px; margin: 8px 0;
}
.ob-bar-labels {
    display: flex; justify-content: space-between;
    font-size: 11px; margin-bottom: 6px;
}
.ob-bar-track {
    height: 7px; border-radius: 4px;
    background: #23242a; overflow: hidden; display: flex;
}
.ob-bar-bid {
    background: linear-gradient(90deg,#16a34a,#4ade80);
    border-radius: 4px 0 0 4px;
}
.ob-bar-ask {
    background: linear-gradient(90deg,#f87171,#ef4444);
    border-radius: 0 4px 4px 0;
}
</style>"""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fmt_price(price: float) -> str:
    """Format a price with auto-precision based on magnitude."""
    if price >= 1_000:
        return f"{price:,.2f}"
    if price >= 1:
        return f"{price:.4f}"
    if price >= 0.0001:
        return f"{price:.6f}"
    return f"{price:.10f}"


def _level_usd(lvl: OrderBookLevel) -> float:
    """USD size of a level — falls back to price * qty if usd_size is 0."""
    return lvl.usd_size if lvl.usd_size > 0 else (lvl.price * lvl.qty)


def _walls_df(walls: list[OrderBookLevel]) -> pd.DataFrame:
    """Convert a list of OrderBookLevel walls to a display DataFrame."""
    if not walls:
        return pd.DataFrame(columns=["Price", "Qty", "USD size"])
    return pd.DataFrame([
        {
            "Price":    _fmt_price(w.price),
            "Qty":      f"{w.qty:,.4f}",
            "USD size": format_usd(_level_usd(w)),
        }
        for w in walls
    ])


def _levels_df(levels: list[OrderBookLevel], n: int) -> pd.DataFrame:
    """Convert top-n OrderBookLevels to a display DataFrame."""
    rows = levels[:max(1, n)]
    if not rows:
        return pd.DataFrame(columns=["Price", "Qty", "USD size"])
    return pd.DataFrame([
        {
            "Price":    _fmt_price(lvl.price),
            "Qty":      f"{lvl.qty:,.4f}",
            "USD size": format_usd(_level_usd(lvl)),
        }
        for lvl in rows
    ])


# ── Main render function ───────────────────────────────────────────────────────

def render_orderbook_panel(
    snapshot: OrderBookSnapshot | None,
    metrics: OrderBookMetrics | None,
    show_book_rows: int = 8,
) -> None:
    """
    Render a complete, stable order book panel.

    Args:
        snapshot:       OrderBookSnapshot. None renders empty state.
        metrics:        OrderBookMetrics. None renders empty state.
        show_book_rows: Rows shown in bid/ask level tables. Default 8.
    """
    # CSS injected on every call — Streamlit skips duplicates automatically
    st.markdown(_STYLE, unsafe_allow_html=True)

    # ── Guard: no data ────────────────────────────────────────────────────────
    if snapshot is None or metrics is None:
        st.info("No orderbook data. Select a market and click Refresh.")
        return

    if snapshot.is_empty:
        st.warning(
            f"Empty book received for **{snapshot.symbol}**. "
            "The market may be unavailable or the symbol is invalid."
        )
        return

    # ── Thin book notice ──────────────────────────────────────────────────────
    if metrics.is_thin:
        st.warning(
            "Thin book — less than $5,000 depth on one side. "
            "Slippage and depth estimates may be unreliable."
        )

    # ── Verdict / signal header ───────────────────────────────────────────────
    _sig_color = SIGNAL_COLORS.get(metrics.signal, "#94a3b8")
    _sig_label = SIGNAL_DISPLAY.get(
        metrics.signal,
        metrics.signal.replace("_", " ").title(),
    )
    # Build a fully self-contained HTML block: open and close in one call
    st.markdown(
        f'<div class="ob-verdict-row">'
        f'<span class="ob-verdict-pill" style="'
        f'color:{_sig_color};border:1px solid {_sig_color}55;'
        f'background:rgba(0,0,0,.28)">'
        f'{_sig_label}'
        f'</span>'
        f'<span class="ob-verdict-reason">{metrics.signal_reason}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── Metric grid — row 1 ───────────────────────────────────────────────────
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Mid price",      f"${_fmt_price(metrics.mid_price)}")
    col2.metric("Spread",         f"{metrics.spread_pct:.4f}%")
    col3.metric("Imbalance",      f"{metrics.imbalance:+.3f}")
    col4.metric("Liquidity",      f"{metrics.liquidity_score:.0f} / 100")

    # ── Metric grid — row 2 ───────────────────────────────────────────────────
    col5, col6, col7, col8 = st.columns(4)
    col5.metric("Bid depth 0.5%", format_usd(metrics.bid_depth_usd))
    col6.metric("Ask depth 0.5%", format_usd(metrics.ask_depth_usd))
    col7.metric("Slip buy $1k",   f"{metrics.slippage_buy_1k:.4f}%")
    col8.metric("Slip sell $1k",  f"{metrics.slippage_sell_1k:.4f}%")

    # ── Balance bar ───────────────────────────────────────────────────────────
    _total = metrics.bid_depth_usd + metrics.ask_depth_usd
    _bid_w = (metrics.bid_depth_usd / _total * 100) if _total > 0 else 50.0
    _ask_w = 100.0 - _bid_w
    _imb   = metrics.imbalance
    _bias  = (
        "Bid-heavy"  if _imb >  0.3 else
        "Ask-heavy"  if _imb < -0.3 else
        "Balanced"
    )
    # Fully self-contained block — open and close in one st.markdown call
    st.markdown(
        f'<div class="ob-bar-wrap">'
        f'<div class="ob-bar-labels">'
        f'<span style="color:#4ade80">Bids {format_usd(metrics.bid_depth_usd)}'
        f' ({_bid_w:.1f}%)</span>'
        f'<span style="color:#5a5b62">{_bias}</span>'
        f'<span style="color:#f87171">Asks {format_usd(metrics.ask_depth_usd)}'
        f' ({_ask_w:.1f}%)</span>'
        f'</div>'
        f'<div class="ob-bar-track">'
        f'<div class="ob-bar-bid" style="width:{_bid_w:.1f}%"></div>'
        f'<div class="ob-bar-ask" style="width:{_ask_w:.1f}%"></div>'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── Walls — native dataframes in two columns ──────────────────────────────
    st.caption("Biggest walls")
    wcol1, wcol2 = st.columns(2)

    with wcol1:
        st.caption("Bid walls (support)")
        _bw_df = _walls_df(metrics.bid_walls)
        if _bw_df.empty:
            st.caption("No significant bid walls detected.")
        else:
            st.dataframe(_bw_df, use_container_width=True, hide_index=True)

    with wcol2:
        st.caption("Ask walls (resistance)")
        _aw_df = _walls_df(metrics.ask_walls)
        if _aw_df.empty:
            st.caption("No significant ask walls detected.")
        else:
            st.dataframe(_aw_df, use_container_width=True, hide_index=True)

    # ── Book levels — native dataframes in two columns ────────────────────────
    st.caption("Order book levels")
    lcol1, lcol2 = st.columns(2)
    _n = max(1, show_book_rows)

    with lcol1:
        st.caption("Bids")
        _bid_df = _levels_df(snapshot.bids, _n)
        if _bid_df.empty:
            st.caption("No bid levels.")
        else:
            st.dataframe(_bid_df, use_container_width=True, hide_index=True)

    with lcol2:
        st.caption("Asks")
        _ask_df = _levels_df(snapshot.asks, _n)
        if _ask_df.empty:
            st.caption("No ask levels.")
        else:
            st.dataframe(_ask_df, use_container_width=True, hide_index=True)
