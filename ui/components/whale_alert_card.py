"""
ui/components/whale_alert_card.py
-----------------------------------
Whale alert card components for the Pro Dashboard.

render_whale_alert_card(alert)   — single alert card
render_whale_alerts(alerts)      — list of alert cards

Shows: symbol, alert type, side, size, leverage, risk,
       confidence, importance, reasons, warnings, action.

Rules:
- No API calls.
- No external dependencies.
- unsafe_allow_html only for fully self-contained card HTML.
- Streamlit-native (st.metric, st.caption) for data inside cards.
"""

from __future__ import annotations

import streamlit as st

from services.whale_alert_engine import VALID_ALERT_TYPES, WhaleAlert

# ── CSS — injected once, idempotent ───────────────────────────────────────────

_CSS = """<style>
.wa-card {
    background: #1a1b1f;
    border: 1px solid #2a2b30;
    border-radius: 14px;
    padding: 14px 16px;
    margin-bottom: 10px;
}
.wa-card.extreme { border-color: rgba(239,68,68,.50); }
.wa-card.high    { border-color: rgba(251,191,36,.40); }
.wa-card.medium  { border-color: rgba(99,102,241,.35); }
.wa-card.low     { border-color: #2a2b30; }

.wa-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 8px;
}
.wa-sym {
    font-size: 16px;
    font-weight: 700;
    color: #f5f5f7;
}
.wa-venue {
    font-size: 10px;
    color: #4a4b52;
    margin-top: 2px;
}
.wa-scores {
    text-align: right;
    line-height: 1;
}
.wa-importance {
    font-size: 22px;
    font-weight: 700;
    color: #a78bfa;
}
.wa-imp-lbl {
    font-size: 10px;
    color: #4a4b52;
}
.wa-badges {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
    margin-bottom: 8px;
}
.wa-badge {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 10px;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: .04em;
}
.wa-badge.type-long     { background:rgba(34,197,94,.14);  color:#4ade80;  border:1px solid rgba(34,197,94,.28); }
.wa-badge.type-short    { background:rgba(239,68,68,.14);  color:#f87171;  border:1px solid rgba(239,68,68,.28); }
.wa-badge.type-exit     { background:rgba(100,116,139,.14);color:#94a3b8;  border:1px solid rgba(100,116,139,.28); }
.wa-badge.type-neutral  { background:rgba(148,163,184,.12);color:#94a3b8;  border:1px solid rgba(148,163,184,.22); }
.wa-badge.risk-extreme  { background:rgba(239,68,68,.18);  color:#fca5a5;  border:1px solid rgba(239,68,68,.40); }
.wa-badge.risk-high     { background:rgba(251,191,36,.14);  color:#fde68a;  border:1px solid rgba(251,191,36,.30); }
.wa-badge.risk-medium   { background:rgba(99,102,241,.14);  color:#c4b5fd;  border:1px solid rgba(99,102,241,.28); }
.wa-badge.risk-low      { background:rgba(34,197,94,.10);  color:#86efac;  border:1px solid rgba(34,197,94,.20); }
.wa-badge.lev           { background:rgba(251,191,36,.10);  color:#fbbf24;  border:1px solid rgba(251,191,36,.22); }
.wa-badge.type-tag      { background:rgba(148,163,184,.08);color:#64748b;  border:1px solid rgba(148,163,184,.16); }
.wa-message {
    font-size: 12px;
    color: #c0c0c8;
    line-height: 1.45;
    margin-bottom: 8px;
}
.wa-action {
    font-size: 11px;
    font-weight: 600;
    color: #a78bfa;
    margin-bottom: 6px;
    padding: 5px 10px;
    background: rgba(124,92,252,.10);
    border-radius: 7px;
    border: 1px solid rgba(124,92,252,.20);
    display: inline-block;
}
.wa-context {
    font-size: 10px;
    color: #3a3b42;
    margin-bottom: 6px;
    font-family: monospace;
}
.wa-section-lbl {
    font-size: 9px;
    font-weight: 700;
    color: #3a3b42;
    text-transform: uppercase;
    letter-spacing: .07em;
    margin: 8px 0 4px;
}
.wa-reason {
    font-size: 11px;
    color: #6a6b72;
    padding: 3px 0;
    padding-left: 8px;
    border-left: 2px solid #2a2b30;
    margin-bottom: 3px;
}
.wa-warning {
    font-size: 11px;
    color: #b45309;
    padding: 3px 0;
    padding-left: 8px;
    border-left: 2px solid rgba(251,191,36,.40);
    margin-bottom: 3px;
}
.wa-empty {
    background: #1a1b1f;
    border: 1px solid #2a2b30;
    border-radius: 12px;
    padding: 24px;
    text-align: center;
    font-size: 13px;
    color: #3a3b42;
}
.wa-confidence-row {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-top: 8px;
}
.wa-conf-bar-track {
    flex: 1;
    height: 4px;
    background: #23242a;
    border-radius: 2px;
    overflow: hidden;
}
.wa-conf-bar-fill {
    height: 100%;
    border-radius: 2px;
    background: linear-gradient(90deg, #4a4b52, #a78bfa);
}
.wa-conf-lbl {
    font-size: 10px;
    color: #4a4b52;
    white-space: nowrap;
}
</style>"""

_css_injected = False


def _inject_css() -> None:
    global _css_injected
    if not _css_injected:
        st.markdown(_CSS, unsafe_allow_html=True)
        _css_injected = True


# ── Helpers ───────────────────────────────────────────────────────────────────

def _side_badge_class(side: str) -> str:
    return {"long": "type-long", "short": "type-short",
            "exit": "type-exit"}.get(side, "type-neutral")


def _risk_badge_class(risk: str) -> str:
    return f"risk-{risk}"


def _type_display(alert_type: str) -> str:
    return alert_type.replace("_", " ").title()


# ── Card builders ─────────────────────────────────────────────────────────────

def render_whale_alert_card(alert: WhaleAlert) -> None:
    """
    Render a single whale alert as a dark card.

    Displays symbol, venue, alert type, side, size, leverage, risk,
    confidence bar, importance score, reasons, warnings, and action.

    Args:
        alert: WhaleAlert dataclass instance.
    """
    _inject_css()

    risk   = alert.risk   # "low" / "medium" / "high" / "extreme"
    side   = alert.side   # "long" / "short" / "exit" / "none"

    # ── Side badge ───────────────────────────────────────────────────────────
    side_display = side.upper() if side != "none" else "—"
    side_cls     = _side_badge_class(side)

    # ── Risk badge ───────────────────────────────────────────────────────────
    risk_cls     = _risk_badge_class(risk)
    risk_display = f"{risk.upper()} RISK"

    # ── Leverage badge ────────────────────────────────────────────────────────
    lev_badge = (
        f'<span class="wa-badge lev">{alert.leverage_str}</span>'
        if alert.leverage else ""
    )

    # ── Alert type badge ──────────────────────────────────────────────────────
    type_display = _type_display(alert.alert_type)

    # ── Reasons HTML ─────────────────────────────────────────────────────────
    reasons_html = ""
    if alert.reasons:
        reasons_html = (
            '<div class="wa-section-lbl">Reasons</div>'
            + "".join(
                f'<div class="wa-reason">{r}</div>'
                for r in alert.reasons[:4]  # cap at 4 for compact display
            )
        )

    # ── Warnings HTML ─────────────────────────────────────────────────────────
    warnings_html = ""
    if alert.warnings:
        warnings_html = (
            '<div class="wa-section-lbl">Warnings</div>'
            + "".join(
                f'<div class="wa-warning">{w}</div>'
                for w in alert.warnings[:3]
            )
        )

    # ── Context line ──────────────────────────────────────────────────────────
    ctx_html = (
        f'<div class="wa-context">{alert.context}</div>'
        if alert.context else ""
    )

    # ── Confidence bar ────────────────────────────────────────────────────────
    conf_pct = max(0, min(100, alert.confidence))
    conf_html = (
        f'<div class="wa-confidence-row">'
        f'<span class="wa-conf-lbl">Confidence</span>'
        f'<div class="wa-conf-bar-track">'
        f'<div class="wa-conf-bar-fill" style="width:{conf_pct:.0f}%"></div>'
        f'</div>'
        f'<span class="wa-conf-lbl">{conf_pct:.0f}%</span>'
        f'</div>'
    )

    # ── Full self-contained card ───────────────────────────────────────────────
    st.markdown(
        f'<div class="wa-card {risk}">'

        # Header: symbol + venue | importance score
        f'<div class="wa-header">'
        f'<div>'
        f'<div class="wa-sym">{alert.symbol}</div>'
        f'<div class="wa-venue">{alert.venue}</div>'
        f'</div>'
        f'<div class="wa-scores">'
        f'<div class="wa-importance">{alert.importance_score:.0f}</div>'
        f'<div class="wa-imp-lbl">importance</div>'
        f'</div>'
        f'</div>'

        # Badges
        f'<div class="wa-badges">'
        f'<span class="wa-badge {side_cls}">{side_display}</span>'
        f'<span class="wa-badge {risk_cls}">{risk_display}</span>'
        f'<span class="wa-badge type-tag">{type_display}</span>'
        f'{lev_badge}'
        f'<span class="wa-badge type-tag">{alert.size_str}</span>'
        f'</div>'

        # Message
        f'<div class="wa-message">{alert.message}</div>'

        # Context
        f'{ctx_html}'

        # Action
        f'<div class="wa-action">{alert.action}</div>'

        # Reasons & warnings
        f'{reasons_html}'
        f'{warnings_html}'

        # Confidence bar
        f'{conf_html}'

        f'</div>',
        unsafe_allow_html=True,
    )


def render_whale_alerts(
    alerts: list[WhaleAlert],
    max_shown: int = 10,
    show_header: bool = True,
) -> None:
    """
    Render a list of whale alerts as stacked cards.

    Args:
        alerts:      List of WhaleAlert instances.
        max_shown:   Maximum number of cards to render. Default 10.
        show_header: If True, shows a count header. Default True.
    """
    _inject_css()

    if not alerts:
        st.markdown(
            '<div class="wa-empty">No whale alerts detected.</div>',
            unsafe_allow_html=True,
        )
        return

    shown = alerts[:max_shown]

    if show_header:
        st.caption(
            f"{len(shown)} whale alert{'s' if len(shown) != 1 else ''}"
            + (f" (of {len(alerts)} total)" if len(alerts) > max_shown else "")
        )

    for alert in shown:
        render_whale_alert_card(alert)
