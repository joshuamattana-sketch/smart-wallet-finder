"""
ui/components/market_cards.py
------------------------------
Reusable card components for the Pro Dashboard.

render_market_kpi_cards(cards)   — top-level KPI strip
render_market_stat_cards(stats)  — secondary stats row

All rendering is Streamlit-native.
No API calls. No external dependencies.
"""

from __future__ import annotations

import streamlit as st

# ── Shared CSS ────────────────────────────────────────────────────────────────

_CARDS_CSS = """<style>
.kpi-card {
    background: #1a1b1f;
    border: 1px solid #2a2b30;
    border-radius: 14px;
    padding: 16px 18px;
}
.kpi-label {
    font-size: 10px;
    font-weight: 600;
    color: #4a4b52;
    text-transform: uppercase;
    letter-spacing: .07em;
    margin-bottom: 6px;
}
.kpi-value {
    font-size: 22px;
    font-weight: 700;
    color: #f5f5f7;
    line-height: 1.1;
    margin-bottom: 4px;
}
.kpi-value.g { color: #4ade80; }
.kpi-value.r { color: #f87171; }
.kpi-value.y { color: #fbbf24; }
.kpi-sub {
    font-size: 11px;
    color: #5a5b62;
}
.kpi-sub .g { color: #4ade80; font-weight: 600; }
.kpi-sub .r { color: #f87171; font-weight: 600; }
.stat-card {
    background: #18191c;
    border: 1px solid #23242a;
    border-radius: 10px;
    padding: 12px 14px;
    display: flex;
    justify-content: space-between;
    align-items: center;
}
.stat-label { font-size: 12px; color: #5a5b62; }
.stat-value { font-size: 14px; font-weight: 600; color: #c0c0c8; }
.stat-value.g { color: #4ade80; }
.stat-value.r { color: #f87171; }
.stat-value.y { color: #fbbf24; }
</style>"""

_cards_css_done = False


def _inject_cards_css() -> None:
    global _cards_css_done
    if not _cards_css_done:
        st.markdown(_CARDS_CSS, unsafe_allow_html=True)
        _cards_css_done = True


# ── Helpers ───────────────────────────────────────────────────────────────────

def _color_class(value: float, *, invert: bool = False) -> str:
    """Return 'g', 'r', or '' based on sign. Invert for metrics where higher is worse."""
    if value > 0:
        return "r" if invert else "g"
    if value < 0:
        return "g" if invert else "r"
    return ""


# ── Public API ────────────────────────────────────────────────────────────────

def render_market_kpi_cards(cards: list[dict]) -> None:
    """
    Render a horizontal strip of large KPI cards.

    Each card dict may contain:
        label      (str)   — card title
        value      (str)   — primary display value (pre-formatted)
        color      (str)   — 'g' (green), 'r' (red), 'y' (yellow), '' (white)
        sub        (str)   — optional secondary line (plain text)
        sub_color  (str)   — color class for sub ('g', 'r', '')
        icon       (str)   — optional emoji prefix shown before label

    Args:
        cards: List of card dicts. Up to 4 shown cleanly in one row.

    Example:
        render_market_kpi_cards([
            {"label": "BTC Price", "value": "$67,420", "color": "g",
             "sub": "+1.4% today", "sub_color": "g"},
        ])
    """
    _inject_cards_css()

    if not cards:
        st.caption("No KPI data.")
        return

    cols = st.columns(len(cards))
    for col, card in zip(cols, cards):
        with col:
            _label    = str(card.get("label", ""))
            _value    = str(card.get("value", "—"))
            _color    = str(card.get("color", ""))
            _sub      = str(card.get("sub", ""))
            _sub_col  = str(card.get("sub_color", ""))
            _icon     = str(card.get("icon", ""))
            _label_display = f"{_icon} {_label}".strip() if _icon else _label

            _sub_html = ""
            if _sub:
                if _sub_col:
                    _sub_html = f'<div class="kpi-sub"><span class="{_sub_col}">{_sub}</span></div>'
                else:
                    _sub_html = f'<div class="kpi-sub">{_sub}</div>'

            st.markdown(
                f'<div class="kpi-card">'
                f'<div class="kpi-label">{_label_display}</div>'
                f'<div class="kpi-value {_color}">{_value}</div>'
                f'{_sub_html}'
                f'</div>',
                unsafe_allow_html=True,
            )


def render_market_stat_cards(stats: list[dict]) -> None:
    """
    Render a row of compact horizontal stat cards.

    Each stat dict may contain:
        label  (str)  — left side label
        value  (str)  — right side value (pre-formatted)
        color  (str)  — 'g', 'r', 'y', or ''

    Args:
        stats: List of stat dicts. Best with 2–4 columns of 2–3 rows each.

    Example:
        render_market_stat_cards([
            {"label": "24h Volume",   "value": "$48.2B", "color": ""},
            {"label": "BTC Dominance","value": "52.4%",  "color": "y"},
        ])
    """
    _inject_cards_css()

    if not stats:
        return

    # Two columns of stats
    mid   = (len(stats) + 1) // 2
    left  = stats[:mid]
    right = stats[mid:]

    col1, col2 = st.columns(2)
    for col, group in ((col1, left), (col2, right)):
        with col:
            for s in group:
                _lbl = str(s.get("label", ""))
                _val = str(s.get("value", "—"))
                _cls = str(s.get("color", ""))
                st.markdown(
                    f'<div class="stat-card">'
                    f'<span class="stat-label">{_lbl}</span>'
                    f'<span class="stat-value {_cls}">{_val}</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
