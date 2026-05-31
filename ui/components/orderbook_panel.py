"""
ui/components/orderbook_panel.py
---------------------------------
Reusable Streamlit component for rendering order book metrics.

Accepts an OrderBookSnapshot and OrderBookMetrics (from core/models.py)
and renders a stable, readable panel on every refresh/symbol-change.

Stability rules:
- CSS is injected once as a single self-contained <style> block.
- All data is displayed via st.metric, st.columns, st.dataframe, st.caption.
- unsafe_allow_html is only used for:
    1. The CSS block (one call, no open tags).
    2. Fully self-contained card HTML strings (open + close in same call).
- No <div> that opens in one st.markdown and closes in another.
"""

from __future__ import annotations

import streamlit as st
import pandas as pd

from core.constants import SIGNAL_COLORS, SIGNAL_DISPLAY
from core.formatting import format_usd, format_pct, safe_float
from core.models import OrderBookLevel, OrderBookMetrics, OrderBookSnapshot


# ── CSS — injected once, fully self-contained ─────────────────────────────────

_CSS = """<style>
.ob-signal-card {
    background: #1a1b1f;
    border: 1px solid #2a2b30;
    border-radius: 14px;
    padding: 14px 18px;
    margin-bottom: 16px;
    display: flex;
    align-items: center;
    gap: 14px;
}
.ob-signal-pill {
    display: inline-block;
    padding: 5px 16px;
    border-radius: 20px;
    font-size: 12px;
    font-weight: 700;
    letter-spacing: .04em;
    flex-shrink: 0;
    white-space: nowrap;
}
.ob-signal-reason {
    font-size: 13px;
    color: #9090a0;
    line-height: 1.45;
}
.ob-depth-card {
    background: #1a1b1f;
    border: 1px solid #2a2b30;
    border-radius: 12px;
    padding: 12px 16px;
    margin: 4px 0 12px;
}
.ob-depth-labels {
    display: flex;
    justify-content: space-between;
    font-size: 11px;
    color: #5a5b62;
    margin-bottom: 7px;
}
.ob-depth-track {
    height: 8px;
    border-radius: 4px;
    background: #23242a;
    overflow: hidden;
    display: flex;
}
.ob-depth-bid  { background: linear-gradient(90deg, #16a34a, #4ade80); border-radius: 4px 0 0 4px; }
.ob-depth-ask  { background: linear-gradient(90deg, #f87171, #ef4444); border-radius: 0 4px 4px 0; }
.ob-wall-card {
    background: #1e1f23;
    border: 1px solid #2a2b30;
    border-radius: 12px;
    padding: 12px 14px;
    height: 100%;
}
.ob-wall-title {
    font-size: 10px;
    font-weight: 600;
    letter-spacing: .06em;
    text-transform: uppercase;
    margin-bottom: 8px;
}
.ob-wall-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 5px 0;
    border-bottom: 1px solid #23242a;
    font-size: 12px;
    font-family: monospace;
}
.ob-wall-row:last-child { border-bottom: none; }
.ob-wall-price { font-weight: 600; color: #f5f5f7; }
.ob-wall-qty   { color: #5a5b62; }
.ob-wall-usd   { font-weight: 600; }
.ob-thin-warn {
    background: rgba(239,68,68,.08);
    border: 1px solid rgba(239,68,68,.3);
    border-radius: 10px;
    padding: 10px 14px;
    font-size: 12px;
    color: #f87171;
    margin-bottom: 12px;
}
</style>"""

_css_injected = False


def _ensure_css() -> None:
    global _css_injected
    if not _css_injected:
        st.markdown(_CSS, unsafe_allow_html=True)
        _css_injected = True


# ── Price formatter ────────────────────────────────────────────────────────────

def _fmt_price(price: float) -> str:
    if price >= 1_000:
        return f"{price:,.2f}"
    if price >= 1:
        return f"{price:.4f}"
    if price >= 0.0001:
        return f"{price:.6f}"
    return f"{price:.10f}"


def _usd_size(lvl: OrderBookLevel) -> float:
    return lvl.usd_size if lvl.usd_size > 0 else (lvl.price * lvl.qty)


# ── Wall card builder (self-contained HTML) ───────────────────────────────────

def _wall_card_html(walls: list[OrderBookLevel], side: str) -> str:
    """Return a fully self-contained HTML card for bid or ask walls."""
    if side == "bid":
        title_color = "#4ade80"
        title_text  = "Bid walls (support)"
        usd_color   = "#4ade80"
    else:
        title_color = "#f87171"
        title_text  = "Ask walls (resistance)"
        usd_color   = "#f87171"

    if not walls:
        rows_html = (
            '<div class="ob-wall-row">'
            '<span style="color:#3a3b42">No walls detected</span>'
            '</div>'
        )
    else:
        rows_html = ""
        for w in walls:
            usd = _usd_size(w)
            rows_html += (
                f'<div class="ob-wall-row">'
                f'<span class="ob-wall-price">{_fmt_price(w.price)}</span>'
                f'<span class="ob-wall-qty">{w.qty:,.4f}</span>'
                f'<span class="ob-wall-usd" style="color:{usd_color}">'
                f'{format_usd(usd)}</span>'
                f'</div>'
            )

    return (
        f'<div class="ob-wall-card">'
        f'<div class="ob-wall-title" style="color:{title_color}">{title_text}</div>'
        f'{rows_html}'
        f'</div>'
    )


# ── Main render function ───────────────────────────────────────────────────────

def render_orderbook_panel(
    snapshot: OrderBookSnapshot | None,
    metrics: OrderBookMetrics | None,
    show_book_rows: int = 8,
) -> None:
    """
    Render a complete, stable order book panel.

    Uses st.metric / st.columns / st.dataframe for all data.
    unsafe_allow_html only for CSS injection and fully closed card HTML.

    Args:
        snapshot:       OrderBookSnapshot from connectors/binance.py.
        metrics:        OrderBookMetrics from services/orderbook_engine.py.
        show_book_rows: Rows to show in the bid/ask table. Default 8.
    """
    _ensure_css()

    # ── Empty / None guard ────────────────────────────────────────────────────
    if snapshot is None or metrics is None:
        st.info("No orderbook data. Select a market and click Refresh.")
        return

    if snapshot.is_empty:
        st.warning(f"Empty book for {snapshot.symbol}. Market may be unavailable.")
        return

    # ── Thin book warning (native) ────────────────────────────────────────────
    if metrics.is_thin:
        st.markdown(
            '<div class="ob-thin-warn">'
            "Thin book — less than $5,000 depth on one side. "
            "Estimates may be unreliable."
            "</div>",
            unsafe_allow_html=True,
        )

    # ── Signal card (self-contained) ──────────────────────────────────────────
    _sig_color = SIGNAL_COLORS.get(metrics.signal, "#94a3b8")
    _sig_label = SIGNAL_DISPLAY.get(
        metrics.signal, metrics.signal.replace("_", " ").title()
    )
    st.markdown(
        f'<div class="ob-signal-card">'
        f'<span class="ob-signal-pill" style="'
        f'color:{_sig_color};'
        f'border:1px solid {_sig_color}44;'
        f'background:rgba(0,0,0,.25)">'
        f'{_sig_label}</span>'
        f'<span class="ob-signal-reason">{metrics.signal_reason}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── Key metrics — st.metric grid ─────────────────────────────────────────
    _c1, _c2, _c3, _c4 = st.columns(4)
    _c1.metric("Mid price",      f"${_fmt_price(metrics.mid_price)}")
    _c2.metric("Spread",         f"{metrics.spread_pct:.4f}%")
    _c3.metric("Imbalance",      f"{metrics.imbalance:+.3f}")
    _c4.metric("Liquidity",      f"{metrics.liquidity_score:.0f}/100")

    _c5, _c6, _c7, _c8 = st.columns(4)
    _c5.metric("Bid depth 0.5%", format_usd(metrics.bid_depth_usd))
    _c6.metric("Ask depth 0.5%", format_usd(metrics.ask_depth_usd))
    _c7.metric("Slip buy $1k",   f"{metrics.slippage_buy_1k:.4f}%")
    _c8.metric("Slip sell $1k",  f"{metrics.slippage_sell_1k:.4f}%")

    # ── Imbalance depth bar (self-contained) ──────────────────────────────────
    _total = metrics.bid_depth_usd + metrics.ask_depth_usd
    _bid_pct = (metrics.bid_depth_usd / _total * 100) if _total > 0 else 50.0
    _ask_pct = 100.0 - _bid_pct
    _imb = metrics.imbalance
    _bias = (
        "Bid-heavy — buy pressure"  if _imb >  0.3 else
        "Ask-heavy — sell pressure" if _imb < -0.3 else
        "Balanced book"
    )
    st.markdown(
        f'<div class="ob-depth-card">'
        f'<div class="ob-depth-labels">'
        f'<span style="color:#4ade80">Bids {format_usd(metrics.bid_depth_usd)} ({_bid_pct:.1f}%)</span>'
        f'<span>{_bias}</span>'
        f'<span style="color:#f87171">Asks {format_usd(metrics.ask_depth_usd)} ({_ask_pct:.1f}%)</span>'
        f'</div>'
        f'<div class="ob-depth-track">'
        f'<div class="ob-depth-bid" style="width:{_bid_pct:.1f}%"></div>'
        f'<div class="ob-depth-ask" style="width:{_ask_pct:.1f}%"></div>'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── Walls — two columns, each a self-contained card ───────────────────────
    _wc1, _wc2 = st.columns(2)
    with _wc1:
        st.markdown(_wall_card_html(metrics.bid_walls, "bid"), unsafe_allow_html=True)
    with _wc2:
        st.markdown(_wall_card_html(metrics.ask_walls, "ask"), unsafe_allow_html=True)

    # ── Bid / Ask table — st.dataframe (fully native, never corrupts) ─────────
    n = max(1, show_book_rows)
    _bids = snapshot.bids[:n]
    _asks = snapshot.asks[:n]

    _tc1, _tc2 = st.columns(2)

    with _tc1:
        st.caption("Bids")
        if _bids:
            _bid_df = pd.DataFrame([
                {
                    "Price":    _fmt_price(lvl.price),
                    "Qty":      f"{lvl.qty:,.4f}",
                    "USD size": format_usd(_usd_size(lvl)),
                }
                for lvl in _bids
            ])
            st.dataframe(
                _bid_df,
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.caption("No bid data.")

    with _tc2:
        st.caption("Asks")
        if _asks:
            _ask_df = pd.DataFrame([
                {
                    "Price":    _fmt_price(lvl.price),
                    "Qty":      f"{lvl.qty:,.4f}",
                    "USD size": format_usd(_usd_size(lvl)),
                }
                for lvl in _asks
            ])
            st.dataframe(
                _ask_df,
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.caption("No ask data.")
