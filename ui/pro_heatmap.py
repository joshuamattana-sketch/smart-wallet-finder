"""
ui/pro_heatmap.py
------------------
Pro Liquidity Wall Map page for the Pro Trading Terminal.

Renders a Bookmap-style liquidity heatmap using demo snapshot data.
WebSocket-driven live orderbook history is planned for a future patch.

Rules:
- No API calls.
- No WebSockets (planned for later).
- No Streamlit-incompatible external libraries.
- Falls back gracefully if heatmap engine is unavailable.
"""

from __future__ import annotations

import streamlit as st

# ── Guarded imports ───────────────────────────────────────────────────────────
try:
    from services.heatmap_engine import (
        demo_heatmap_cells,
        detect_hot_zones,
    )
    from ui.components.liquidity_heatmap_panel import render_liquidity_heatmap
    _ENGINE_AVAILABLE = True
except Exception:
    _ENGINE_AVAILABLE = False
    def demo_heatmap_cells(): return []          # type: ignore[misc]
    def detect_hot_zones(c, **kw): return []     # type: ignore[misc]
    def render_liquidity_heatmap(c, **kw): pass  # type: ignore[misc]

_CSS = """<style>
.ph-title { font-size:26px; font-weight:700; color:#f5f5f7; padding:24px 0 2px; letter-spacing:-.01em; }
.ph-sub   { font-size:14px; color:#5a5b62; margin-bottom:20px; }
.ph-info  { background:#1a1b1f; border:1px solid #2a2b30; border-radius:12px;
            padding:12px 16px; font-size:12px; color:#5a5b62; margin-top:16px; }
.ph-info b { color:#a78bfa; }
.ph-badge { display:inline-block; padding:3px 10px; border-radius:8px; font-size:11px;
            font-weight:700; background:rgba(251,191,36,.10); color:#fbbf24;
            border:1px solid rgba(251,191,36,.25); margin-right:8px; }
</style>"""


def render_pro_heatmap() -> None:
    """
    Render the Pro Liquidity Wall Map page.

    Uses demo_heatmap_cells() as the data source until live WebSocket
    orderbook history is available. Symbol selector and refresh button
    are present as placeholders for future live connectivity.
    """
    st.markdown(_CSS, unsafe_allow_html=True)
    st.markdown('<div class="ph-title">Liquidity Wall Map</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="ph-sub">'
        'Order-book wall heatmap — bid support and ask resistance at a glance.'
        '</div>',
        unsafe_allow_html=True,
    )

    if not _ENGINE_AVAILABLE:
        st.warning(
            "Heatmap engine not available. "
            "Make sure services/heatmap_engine.py and "
            "ui/components/liquidity_heatmap_panel.py are deployed.",
            icon="⚠️",
        )
        return

    # ── Toolbar (placeholder for future live symbol selector) ─────────────────
    _col_sym, _col_ref, _col_mode, _col_spacer = st.columns([0.22, 0.13, 0.30, 0.35])

    with _col_sym:
        _symbol = st.selectbox(
            "Symbol",
            options=["BTCUSDT", "ETHUSDT", "SOLUSDT"],
            index=0,
            key="_ph_symbol",
            label_visibility="collapsed",
        )

    with _col_ref:
        _refresh = st.button(
            "Refresh",
            key="_ph_refresh",
            use_container_width=True,
            type="primary",
        )

    with _col_mode:
        st.markdown(
            '<div style="padding-top:6px">'
            '<span class="ph-badge">DEMO</span>'
            '<span style="font-size:11px;color:#3a3b42">Live WebSocket — coming soon</span>'
            '</div>',
            unsafe_allow_html=True,
        )

    # ── Heatmap ───────────────────────────────────────────────────────────────
    try:
        cells = demo_heatmap_cells()
    except Exception as exc:
        st.error(f"Could not generate heatmap data: {exc}")
        return

    if not cells:
        st.info("No heatmap data available.")
        return

    render_liquidity_heatmap(
        cells,
        title=f"Liquidity Wall Map — {_symbol} (Demo)",
        hot_zone_threshold=70,
        show_hot_zones=True,
        max_rows=20,
    )

    # ── Info footer ───────────────────────────────────────────────────────────
    hot_count  = sum(1 for c in cells if c.intensity >= 70)
    wall_count = sum(1 for c in cells if c.intensity >= 85)
    bid_depth  = sum(c.size_usd for c in cells if c.is_bid)
    ask_depth  = sum(c.size_usd for c in cells if c.is_ask)

    st.markdown(
        f'<div class="ph-info">'
        f'<b>Mode: Demo heatmap</b> &nbsp;&middot;&nbsp; '
        f'{len(cells)} price levels &nbsp;&middot;&nbsp; '
        f'{hot_count} hot zones &nbsp;&middot;&nbsp; '
        f'{wall_count} walls detected<br>'
        f'Bid depth: <b>${bid_depth/1e6:.1f}M</b> &nbsp;|&nbsp; '
        f'Ask depth: <b>${ask_depth/1e6:.1f}M</b><br>'
        f'<span style="color:#3a3b42;font-size:11px">'
        f'Future: live WebSocket orderbook history with time-axis replay.'
        f'</span>'
        f'</div>',
        unsafe_allow_html=True,
    )
