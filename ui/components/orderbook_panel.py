"""
ui/components/orderbook_panel.py
---------------------------------
Reusable Streamlit component for rendering order book metrics.

Accepts an OrderBookSnapshot and OrderBookMetrics (both from core/models.py)
and renders a complete, readable panel — no business logic here.

Rules:
- Only Streamlit rendering calls and core/formatting helpers.
- No network calls.
- No direct imports from connectors/ or services/.
- Crashes safely: every render function guards against empty/None inputs.
"""

from __future__ import annotations

import streamlit as st

from core.constants import SIGNAL_COLORS, SIGNAL_DISPLAY, RISK_COLORS
from core.formatting import compact_address, format_pct, format_usd, safe_float
from core.models import OrderBookLevel, OrderBookMetrics, OrderBookSnapshot


# ── CSS (injected once per session, idempotent) ───────────────────────────────

_CSS = """
<style>
/* ── Orderbook panel ── */
.ob-panel { margin-bottom: 24px; }

.ob-signal-bar {
    display: flex; align-items: center; gap: 12px;
    background: #1a1b1f; border: 1px solid #2a2b30;
    border-radius: 14px; padding: 14px 18px; margin-bottom: 14px;
}
.ob-signal-pill {
    display: inline-block; padding: 5px 16px; border-radius: 20px;
    font-size: 12px; font-weight: 700; letter-spacing: .04em; flex-shrink: 0;
}
.ob-signal-reason {
    font-size: 13px; color: #9090a0; line-height: 1.45; flex: 1;
}

.ob-metrics {
    display: grid; grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 10px; margin-bottom: 14px;
}
.ob-metric {
    background: #1e1f23; border: 1px solid #2a2b30;
    border-radius: 12px; padding: 12px 14px;
}
.ob-metric span {
    display: block; font-size: 10px; color: #4a4b52;
    text-transform: uppercase; letter-spacing: .06em; margin-bottom: 5px;
}
.ob-metric b {
    display: block; font-size: 17px; font-weight: 600; color: #f5f5f7;
}
.ob-metric b.g { color: #4ade80; }
.ob-metric b.r { color: #f87171; }
.ob-metric b.y { color: #fbbf24; }

/* Depth bar */
.ob-depth-row {
    background: #1a1b1f; border: 1px solid #2a2b30;
    border-radius: 12px; padding: 12px 16px; margin-bottom: 10px;
}
.ob-depth-label {
    display: flex; justify-content: space-between;
    font-size: 11px; color: #5a5b62; margin-bottom: 8px;
}
.ob-depth-bar {
    height: 8px; border-radius: 4px; background: #23242a; overflow: hidden;
    display: flex;
}
.ob-depth-bar-bid {
    background: linear-gradient(90deg, #16a34a, #4ade80);
    border-radius: 4px 0 0 4px; transition: width .3s ease;
}
.ob-depth-bar-ask {
    background: linear-gradient(90deg, #f87171, #ef4444);
    border-radius: 0 4px 4px 0; transition: width .3s ease;
}

/* Walls */
.ob-walls {
    display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 14px;
}
.ob-wall-panel {
    background: #1e1f23; border: 1px solid #2a2b30; border-radius: 12px; padding: 12px 14px;
}
.ob-wall-title {
    font-size: 10px; font-weight: 600; color: #4a4b52;
    text-transform: uppercase; letter-spacing: .06em; margin-bottom: 8px;
}
.ob-wall-row {
    display: flex; justify-content: space-between; align-items: center;
    padding: 5px 0; border-bottom: 1px solid #23242a; font-size: 12px;
}
.ob-wall-row:last-child { border-bottom: none; }
.ob-wall-price { font-weight: 600; color: #f5f5f7; font-family: monospace; }
.ob-wall-size  { color: #9090a0; }
.ob-wall-usd   { font-weight: 600; }
.ob-wall-usd.g { color: #4ade80; }
.ob-wall-usd.r { color: #f87171; }

/* Book table */
.ob-book {
    display: grid; grid-template-columns: 1fr 1fr; gap: 10px;
}
.ob-book-side {
    background: #1e1f23; border: 1px solid #2a2b30; border-radius: 12px;
    overflow: hidden;
}
.ob-book-header {
    display: flex; justify-content: space-between;
    padding: 8px 12px; font-size: 10px; font-weight: 600; color: #4a4b52;
    text-transform: uppercase; letter-spacing: .05em;
    border-bottom: 1px solid #23242a;
}
.ob-book-row {
    display: flex; justify-content: space-between; align-items: center;
    padding: 5px 12px; font-size: 11px; border-bottom: 1px solid #1a1b1f;
    font-family: monospace;
}
.ob-book-row:last-child { border-bottom: none; }
.ob-book-price-bid { color: #4ade80; font-weight: 600; }
.ob-book-price-ask { color: #f87171; font-weight: 600; }
.ob-book-qty  { color: #9090a0; }
.ob-book-usd  { color: #5a5b62; }

.ob-thin-warning {
    background: rgba(239,68,68,.08); border: 1px solid rgba(239,68,68,.3);
    border-radius: 10px; padding: 10px 14px; font-size: 12px; color: #f87171;
    margin-bottom: 12px;
}
.ob-empty {
    background: #1a1b1f; border: 1px solid #2a2b30; border-radius: 14px;
    padding: 32px; text-align: center; color: #4a4b52; font-size: 14px;
}

@media (max-width: 768px) {
    .ob-metrics { grid-template-columns: repeat(2, 1fr); }
    .ob-walls { grid-template-columns: 1fr; }
    .ob-book { grid-template-columns: 1fr; }
}
</style>
"""

_css_injected = False


def _inject_css() -> None:
    global _css_injected
    if not _css_injected:
        st.markdown(_CSS, unsafe_allow_html=True)
        _css_injected = True


# ── Helpers ───────────────────────────────────────────────────────────────────

def _signal_color(signal: str) -> str:
    return SIGNAL_COLORS.get(signal, "#94a3b8")


def _signal_label(signal: str) -> str:
    return SIGNAL_DISPLAY.get(signal, signal.replace("_", " ").title())


def _imbalance_class(imbalance: float) -> str:
    if imbalance >= 0.2:
        return "g"
    if imbalance <= -0.2:
        return "r"
    return ""


def _score_class(score: float) -> str:
    if score >= 65:
        return "g"
    if score >= 35:
        return "y"
    return "r"


def _price_str(price: float) -> str:
    """Format a price with appropriate decimal places."""
    if price >= 1_000:
        return f"{price:,.2f}"
    if price >= 1:
        return f"{price:.4f}"
    if price >= 0.0001:
        return f"{price:.6f}"
    return f"{price:.10f}"


# ── Main render function ───────────────────────────────────────────────────────

def render_orderbook_panel(
    snapshot: OrderBookSnapshot | None,
    metrics: OrderBookMetrics | None,
    show_book_rows: int = 8,
) -> None:
    """
    Render a complete order book panel.

    Shows signal, key metrics, imbalance depth bar, biggest walls,
    and a live bid/ask table. Safe to call with None inputs.

    Args:
        snapshot:       OrderBookSnapshot from connectors/binance.py.
                        If None, renders an empty state.
        metrics:        OrderBookMetrics from services/orderbook_engine.py.
                        If None, renders an empty state.
        show_book_rows: Number of price levels to show in the bid/ask table.
                        Default 8.
    """
    _inject_css()

    if snapshot is None or metrics is None:
        st.markdown(
            '<div class="ob-empty">No orderbook data. Select a market and click Refresh.</div>',
            unsafe_allow_html=True,
        )
        return

    if snapshot.is_empty:
        st.markdown(
            f'<div class="ob-empty">Empty book for {snapshot.symbol}. '
            "Market may be unavailable or data is delayed.</div>",
            unsafe_allow_html=True,
        )
        return

    st.markdown('<div class="ob-panel">', unsafe_allow_html=True)

    # ── Thin book warning ─────────────────────────────────────────────────────
    if metrics.is_thin:
        st.markdown(
            '<div class="ob-thin-warning">'
            "⚠ Thin book — less than $5,000 depth on one side. "
            "Spreads and slippage estimates may be unreliable."
            "</div>",
            unsafe_allow_html=True,
        )

    # ── Signal bar ────────────────────────────────────────────────────────────
    _scol = _signal_color(metrics.signal)
    _slbl = _signal_label(metrics.signal)
    st.markdown(
        f"""<div class="ob-signal-bar">
  <div class="ob-signal-pill" style="background:rgba(0,0,0,.2);
       color:{_scol};border:1px solid {_scol}44">{_slbl}</div>
  <div class="ob-signal-reason">{metrics.signal_reason}</div>
  <div style="font-size:11px;color:#3a3b42;flex-shrink:0">
    {metrics.symbol} &nbsp;·&nbsp; {metrics.exchange}
  </div>
</div>""",
        unsafe_allow_html=True,
    )

    # ── Key metrics grid ──────────────────────────────────────────────────────
    _imb = metrics.imbalance
    _imb_cls = _imbalance_class(_imb)
    _imb_str = f"{_imb:+.3f}"
    _liq_cls = _score_class(metrics.liquidity_score)
    _mid_str = _price_str(metrics.mid_price)

    st.markdown(
        f"""<div class="ob-metrics">
  <div class="ob-metric">
    <span>Mid price</span><b>${_mid_str}</b>
  </div>
  <div class="ob-metric">
    <span>Spread</span>
    <b class="{'r' if metrics.spread_pct > 1.0 else 'y' if metrics.spread_pct > 0.1 else 'g'}">{metrics.spread_pct:.4f}%</b>
  </div>
  <div class="ob-metric">
    <span>Imbalance</span>
    <b class="{_imb_cls}">{_imb_str}</b>
  </div>
  <div class="ob-metric">
    <span>Liquidity score</span>
    <b class="{_liq_cls}">{metrics.liquidity_score:.0f}/100</b>
  </div>
  <div class="ob-metric">
    <span>Bid depth 0.5%</span>
    <b class="g">{format_usd(metrics.bid_depth_usd)}</b>
  </div>
  <div class="ob-metric">
    <span>Ask depth 0.5%</span>
    <b class="r">{format_usd(metrics.ask_depth_usd)}</b>
  </div>
  <div class="ob-metric">
    <span>Slip buy $1k</span>
    <b class="{'r' if metrics.slippage_buy_1k > 0.5 else 'y' if metrics.slippage_buy_1k > 0.1 else 'g'}">{metrics.slippage_buy_1k:.4f}%</b>
  </div>
  <div class="ob-metric">
    <span>Slip sell $1k</span>
    <b class="{'r' if metrics.slippage_sell_1k > 0.5 else 'y' if metrics.slippage_sell_1k > 0.1 else 'g'}">{metrics.slippage_sell_1k:.4f}%</b>
  </div>
</div>""",
        unsafe_allow_html=True,
    )

    # ── Imbalance depth bar ───────────────────────────────────────────────────
    _total_d = metrics.bid_depth_usd + metrics.ask_depth_usd
    _bid_pct = (metrics.bid_depth_usd / _total_d * 100) if _total_d > 0 else 50.0
    _ask_pct = 100.0 - _bid_pct
    _bias_label = (
        "Bid-heavy — buy pressure dominant"
        if _imb > 0.3
        else "Ask-heavy — sell pressure dominant"
        if _imb < -0.3
        else "Balanced book"
    )

    st.markdown(
        f"""<div class="ob-depth-row">
  <div class="ob-depth-label">
    <span>Bids {format_usd(metrics.bid_depth_usd)} ({_bid_pct:.1f}%)</span>
    <span style="color:#5a5b62">{_bias_label}</span>
    <span>Asks {format_usd(metrics.ask_depth_usd)} ({_ask_pct:.1f}%)</span>
  </div>
  <div class="ob-depth-bar">
    <div class="ob-depth-bar-bid" style="width:{_bid_pct:.1f}%"></div>
    <div class="ob-depth-bar-ask" style="width:{_ask_pct:.1f}%"></div>
  </div>
</div>""",
        unsafe_allow_html=True,
    )

    # ── Biggest walls ─────────────────────────────────────────────────────────
    def _wall_rows(walls: list[OrderBookLevel], side: str) -> str:
        if not walls:
            return '<div class="ob-wall-row"><span style="color:#3a3b42;font-size:12px">No walls</span></div>'
        cls = "g" if side == "bid" else "r"
        rows = ""
        for w in walls:
            usd = w.usd_size if w.usd_size > 0 else w.price * w.qty
            rows += (
                f'<div class="ob-wall-row">'
                f'<span class="ob-wall-price">{_price_str(w.price)}</span>'
                f'<span class="ob-wall-size">{w.qty:,.4f}</span>'
                f'<span class="ob-wall-usd {cls}">{format_usd(usd)}</span>'
                f"</div>"
            )
        return rows

    st.markdown(
        f"""<div class="ob-walls">
  <div class="ob-wall-panel">
    <div class="ob-wall-title" style="color:#4ade80">Bid walls (support)</div>
    {_wall_rows(metrics.bid_walls, 'bid')}
  </div>
  <div class="ob-wall-panel">
    <div class="ob-wall-title" style="color:#f87171">Ask walls (resistance)</div>
    {_wall_rows(metrics.ask_walls, 'ask')}
  </div>
</div>""",
        unsafe_allow_html=True,
    )

    # ── Bid / Ask book table ──────────────────────────────────────────────────
    n = max(1, show_book_rows)
    _bids = snapshot.bids[:n]
    _asks = snapshot.asks[:n]

    def _book_rows_bid(levels: list[OrderBookLevel]) -> str:
        if not levels:
            return '<div class="ob-book-row"><span style="color:#3a3b42">—</span></div>'
        rows = ""
        for lvl in levels:
            usd = lvl.usd_size if lvl.usd_size > 0 else lvl.price * lvl.qty
            rows += (
                f'<div class="ob-book-row">'
                f'<span class="ob-book-price-bid">{_price_str(lvl.price)}</span>'
                f'<span class="ob-book-qty">{lvl.qty:,.4f}</span>'
                f'<span class="ob-book-usd">{format_usd(usd)}</span>'
                f"</div>"
            )
        return rows

    def _book_rows_ask(levels: list[OrderBookLevel]) -> str:
        if not levels:
            return '<div class="ob-book-row"><span style="color:#3a3b42">—</span></div>'
        rows = ""
        for lvl in levels:
            usd = lvl.usd_size if lvl.usd_size > 0 else lvl.price * lvl.qty
            rows += (
                f'<div class="ob-book-row">'
                f'<span class="ob-book-price-ask">{_price_str(lvl.price)}</span>'
                f'<span class="ob-book-qty">{lvl.qty:,.4f}</span>'
                f'<span class="ob-book-usd">{format_usd(usd)}</span>'
                f"</div>"
            )
        return rows

    st.markdown(
        f"""<div class="ob-book">
  <div class="ob-book-side">
    <div class="ob-book-header">
      <span style="color:#4ade80">Bids</span>
      <span>Qty</span>
      <span>USD size</span>
    </div>
    {_book_rows_bid(_bids)}
  </div>
  <div class="ob-book-side">
    <div class="ob-book-header">
      <span style="color:#f87171">Asks</span>
      <span>Qty</span>
      <span>USD size</span>
    </div>
    {_book_rows_ask(_asks)}
  </div>
</div>""",
        unsafe_allow_html=True,
    )

    st.markdown("</div>", unsafe_allow_html=True)
