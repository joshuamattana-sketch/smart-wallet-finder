"""
ui/components/liquidity_heatmap_panel.py
-----------------------------------------
Liquidity Wall Map panel for the Pro Trading Terminal.

Renders a Bookmap-inspired liquidity heatmap from a list of HeatmapCells.
Bids are green, asks are red/orange. Intensity drives background colour.
Hot zones are listed separately below the map.

Rules:
- No API calls.
- No external dependencies.
- unsafe_allow_html only for CSS block and fully self-contained cell rows.
- Streamlit-native (st.caption, st.columns, st.metric) for surrounding UI.
"""

from __future__ import annotations

import streamlit as st

from services.heatmap_engine import SIDE_ASK, SIDE_BID, HeatmapCell, detect_hot_zones

# ── CSS ───────────────────────────────────────────────────────────────────────

_CSS = """<style>
.hm-panel { margin-bottom: 8px; }

/* Grid of cells */
.hm-grid {
    display: grid;
    grid-template-columns: 90px 1fr 80px;
    gap: 2px;
    margin: 4px 0;
}
.hm-grid-header {
    display: grid;
    grid-template-columns: 90px 1fr 80px;
    gap: 2px;
    margin-bottom: 3px;
    padding: 0 2px;
}
.hm-hdr {
    font-size: 9px; font-weight: 600; color: #3a3b42;
    text-transform: uppercase; letter-spacing: .07em;
}
.hm-hdr.center { text-align: center; }
.hm-hdr.right  { text-align: right; }

/* Individual cell rows */
.hm-row {
    display: contents;
}
.hm-price {
    font-size: 11px; font-weight: 600; font-family: monospace;
    padding: 3px 6px;
    border-radius: 4px 0 0 4px;
    white-space: nowrap;
}
.hm-bar-wrap {
    position: relative;
    height: 100%;
    min-height: 20px;
    background: #18191c;
    overflow: hidden;
}
.hm-bar-fill {
    position: absolute;
    top: 0; bottom: 0;
    transition: width .2s ease;
}
.hm-bar-fill.bid {
    left: 0;
    background: linear-gradient(90deg, rgba(22,163,74,.15), rgba(34,197,94,.60));
    border-right: 1px solid rgba(34,197,94,.20);
}
.hm-bar-fill.ask {
    left: 0;
    background: linear-gradient(90deg, rgba(220,38,38,.15), rgba(239,68,68,.60));
    border-right: 1px solid rgba(239,68,68,.20);
}
/* Hot zones: brighter fill */
.hm-bar-fill.bid.hot  {
    background: linear-gradient(90deg, rgba(22,163,74,.25), rgba(74,222,128,.90));
    border-right: 2px solid rgba(74,222,128,.70);
}
.hm-bar-fill.ask.hot  {
    background: linear-gradient(90deg, rgba(220,38,38,.25), rgba(248,113,113,.90));
    border-right: 2px solid rgba(248,113,113,.70);
}
.hm-bar-label {
    position: absolute;
    right: 6px; top: 50%;
    transform: translateY(-50%);
    font-size: 9px; font-weight: 700;
    letter-spacing: .03em;
    white-space: nowrap;
}
.hm-bar-label.bid { color: rgba(74,222,128,.90); }
.hm-bar-label.ask { color: rgba(248,113,113,.90); }
.hm-size {
    font-size: 10px; font-family: monospace; color: #5a5b62;
    padding: 3px 6px;
    text-align: right;
    white-space: nowrap;
    border-radius: 0 4px 4px 0;
    background: #16171a;
    display: flex; align-items: center; justify-content: flex-end;
}

/* Hot zone list */
.hm-hot-list {
    display: flex; flex-direction: column; gap: 4px; margin-top: 8px;
}
.hm-hot-row {
    display: flex; align-items: center; gap: 8px;
    background: #1a1b1f; border-radius: 8px; padding: 6px 10px;
}
.hm-hot-side {
    font-size: 9px; font-weight: 700; padding: 2px 7px;
    border-radius: 5px; white-space: nowrap;
}
.hm-hot-side.bid {
    background: rgba(34,197,94,.12); color: #4ade80;
    border: 1px solid rgba(34,197,94,.22);
}
.hm-hot-side.ask {
    background: rgba(239,68,68,.12); color: #f87171;
    border: 1px solid rgba(239,68,68,.22);
}
.hm-hot-price { font-size: 12px; font-weight: 600; color: #f5f5f7; font-family: monospace; flex: 1; }
.hm-hot-size  { font-size: 11px; color: #9090a0; }
.hm-hot-int   { font-size: 11px; font-weight: 700; color: #a78bfa; }
.hm-hot-label { font-size: 10px; font-weight: 700; letter-spacing: .05em; }
.hm-hot-label.wall { color: #fbbf24; }
.hm-hot-label.hot  { color: #f97316; }

.hm-divider { height: 1px; background: #23242a; margin: 6px 0; }
.hm-empty {
    background: #1a1b1f; border: 1px solid #2a2b30;
    border-radius: 10px; padding: 20px; text-align: center;
    font-size: 13px; color: #3a3b42;
}
.hm-mid-line {
    display: grid; grid-template-columns: 90px 1fr 80px; gap: 2px;
    padding: 2px 0;
}
.hm-mid-price {
    font-size: 13px; font-weight: 700; color: #f5f5f7;
    font-family: monospace; padding: 4px 6px;
    background: #23242a; border-radius: 4px;
    text-align: center;
}
.hm-mid-label {
    font-size: 9px; color: #3a3b42; padding: 6px 6px;
    font-weight: 600; text-transform: uppercase; letter-spacing: .07em;
}
</style>"""

_css_injected = False


def _inject_css() -> None:
    global _css_injected
    if not _css_injected:
        st.markdown(_CSS, unsafe_allow_html=True)
        _css_injected = True


# ── Helpers ───────────────────────────────────────────────────────────────────

def _price_str(price: float) -> str:
    if price >= 1_000:
        return f"{price:,.2f}"
    if price >= 1:
        return f"{price:.4f}"
    return f"{price:.6f}"


def _fmt_size(size_usd: float) -> str:
    if size_usd >= 1_000_000:
        return f"${size_usd / 1_000_000:.1f}M"
    if size_usd >= 1_000:
        return f"${size_usd / 1_000:.0f}K"
    return f"${size_usd:.0f}"


def _row_html(cell: HeatmapCell) -> str:
    """Build one fully self-contained heatmap row (3-column grid item set)."""
    hot_cls   = "hot" if cell.is_hot else ""
    side_cls  = cell.side
    price_col = "rgba(34,197,94,.08)" if cell.is_bid else "rgba(239,68,68,.08)"

    bar_pct   = max(cell.intensity, 2)  # minimum 2% so very thin bars are visible
    label_html = (
        f'<span class="hm-bar-label {side_cls}">{cell.label}</span>'
        if cell.label else ""
    )

    price_str = _price_str(cell.price)
    size_str  = _fmt_size(cell.size_usd)

    return (
        # Column 1: price
        f'<div class="hm-price" style="background:{price_col};color:{"#86efac" if cell.is_bid else "#fca5a5"}">'
        f'{price_str}</div>'
        # Column 2: intensity bar
        f'<div class="hm-bar-wrap">'
        f'<div class="hm-bar-fill {side_cls} {hot_cls}" style="width:{bar_pct}%"></div>'
        f'{label_html}'
        f'</div>'
        # Column 3: size
        f'<div class="hm-size">{size_str}</div>'
    )


def _hot_zone_row(cell: HeatmapCell) -> str:
    """Build a hot-zone summary row HTML."""
    label_cls  = "wall" if cell.is_wall else "hot"
    label_text = "WALL" if cell.is_wall else "HOT"
    return (
        f'<div class="hm-hot-row">'
        f'<span class="hm-hot-side {cell.side}">{cell.side.upper()}</span>'
        f'<span class="hm-hot-price">{_price_str(cell.price)}</span>'
        f'<span class="hm-hot-size">{_fmt_size(cell.size_usd)}</span>'
        f'<span class="hm-hot-int">{cell.intensity}</span>'
        f'<span class="hm-hot-label {label_cls}">{label_text}</span>'
        f'</div>'
    )


# ── Main render function ───────────────────────────────────────────────────────

def render_liquidity_heatmap(
    cells: list[HeatmapCell],
    title: str = "Liquidity Wall Map",
    hot_zone_threshold: int = 70,
    show_hot_zones: bool = True,
    max_rows: int = 20,
) -> None:
    """
    Render a Bookmap-style liquidity heatmap panel.

    Bids are green (descending price, best bid at top).
    Asks are red/orange (ascending price, best ask below mid line).
    Bar width reflects intensity. Hot zones are highlighted.
    A separate hot-zone list shows key walls and support/resistance.

    Args:
        cells:              List of HeatmapCell from heatmap_engine.
        title:              Panel title. Default "Liquidity Wall Map".
        hot_zone_threshold: Intensity to qualify as hot. Default 70.
        show_hot_zones:     Whether to show the hot-zone list. Default True.
        max_rows:           Maximum rows per side to render. Default 20.

    Note:
        Renders an empty-state card if cells is empty or None.
    """
    _inject_css()

    if not cells:
        st.markdown(
            '<div class="hm-empty">No heatmap data. Refresh orderbook to generate map.</div>',
            unsafe_allow_html=True,
        )
        return

    # Separate and trim sides
    bids = [c for c in cells if c.is_bid][:max_rows]
    asks = [c for c in cells if c.is_ask][:max_rows]

    # Mid price (between best bid and best ask)
    mid_str = ""
    if bids and asks:
        mid = (bids[0].price + asks[0].price) / 2
        mid_str = _price_str(mid)

    # ── Title + summary metrics ─────────────────────────────────────────────
    st.caption(title)
    if bids or asks:
        m1, m2, m3 = st.columns(3)
        m1.metric("Bid levels", len(bids))
        m2.metric("Ask levels", len(asks))
        hot_count = sum(1 for c in cells if c.intensity >= hot_zone_threshold)
        m3.metric("Hot zones", hot_count)

    # ── Heatmap grid ─────────────────────────────────────────────────────────
    # Header
    header_html = (
        '<div class="hm-grid-header">'
        '<div class="hm-hdr">Price</div>'
        '<div class="hm-hdr center">Depth</div>'
        '<div class="hm-hdr right">Size</div>'
        '</div>'
    )
    st.markdown(header_html, unsafe_allow_html=True)

    # Bids (best bid first = highest price)
    if bids:
        bid_rows = "".join(_row_html(c) for c in bids)
        st.markdown(
            f'<div class="hm-grid">{bid_rows}</div>',
            unsafe_allow_html=True,
        )

    # Mid-price separator
    if mid_str:
        st.markdown(
            f'<div class="hm-mid-line">'
            f'<div class="hm-mid-price">{mid_str}</div>'
            f'<div class="hm-mid-label">mid price</div>'
            f'<div></div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # Asks (best ask first = lowest price)
    if asks:
        ask_rows = "".join(_row_html(c) for c in asks)
        st.markdown(
            f'<div class="hm-grid">{ask_rows}</div>',
            unsafe_allow_html=True,
        )

    # ── Hot zones list ────────────────────────────────────────────────────────
    if show_hot_zones:
        st.markdown('<div class="hm-divider"></div>', unsafe_allow_html=True)
        st.caption("Key walls & hot zones")
        hot = detect_hot_zones(cells, min_intensity=hot_zone_threshold)
        if hot:
            rows_html = "".join(_hot_zone_row(c) for c in hot[:8])
            st.markdown(
                f'<div class="hm-hot-list">{rows_html}</div>',
                unsafe_allow_html=True,
            )
        else:
            st.caption("No hot zones detected at current threshold.")
