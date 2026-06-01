"""
ui/pro_terminal.py
------------------
Pro Trading Terminal — main Streamlit page.

Fetches live Binance orderbook data, runs analysis via orderbook_engine,
and renders the result via the orderbook panel component.

Rules:
- No business logic here — only Streamlit orchestration.
- All errors surface as user-visible warnings, never uncaught exceptions.
- No WebSockets. Manual Refresh button only — no autorefresh.
- Reads st.session_state["pro_selected_symbol"] set by Pro Dashboard.
"""

from __future__ import annotations

import datetime
import time

import streamlit as st

from connectors.binance import (
    ConnectorError,
    InvalidSymbolError,
    RateLimitError,
    RestrictedLocationError,
    fetch_orderbook,
    normalize_symbol,
)
from core.constants import DEFAULT_PRO_MARKETS
from core.formatting import format_usd, safe_float
from services.orderbook_engine import analyze_orderbook
from ui.components.orderbook_panel import render_orderbook_panel

# Heatmap — guarded so terminal works even if engine not deployed
try:
    from services.heatmap_engine import (
        build_heatmap_from_orderbook as _build_heatmap,
        demo_heatmap_cells as _demo_heatmap_cells,
    )
    from ui.components.liquidity_heatmap_panel import (
        render_liquidity_heatmap as _render_liquidity_heatmap,
    )
    _HEATMAP_AVAILABLE = True
except Exception:
    _HEATMAP_AVAILABLE = False
    def _build_heatmap(snapshot, **kw): return []
    def _demo_heatmap_cells(): return []
    def _render_liquidity_heatmap(cells, **kw): pass


# ── Constants ─────────────────────────────────────────────────────────────────

# Live Binance-supported symbols shown in the selector
_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

# HYPE is listed on Hyperliquid, not Binance — shown with a note if selected
_BINANCE_SYMBOLS = set(_SYMBOLS)
_HYPE_NOTE = "HYPEUSDT is traded on Hyperliquid, not Binance. Showing BTCUSDT instead."

_DEPTH_LIMIT       = 20
_STATE_KEY_SNAP    = "_pro_ob_snapshot"
_STATE_KEY_METRICS = "_pro_ob_metrics"
_STATE_KEY_ERROR   = "_pro_ob_error"
_STATE_KEY_TS      = "_pro_ob_fetched_at"
_STATE_KEY_SYMBOL  = "_pro_ob_symbol"
_STATE_KEY_DEMO    = "_pro_ob_demo_mode"

_CSS = """
<style>
.pt-page-title {
    font-size: 26px; font-weight: 700; color: #f5f5f7;
    padding: 24px 0 2px; letter-spacing: -.01em;
}
.pt-page-sub { font-size: 14px; color: #5a5b62; margin-bottom: 20px; }
.pt-last-updated { font-size: 11px; color: #3a3b42; padding: 4px 0; }
.pt-error {
    background: rgba(239,68,68,.08); border: 1px solid rgba(239,68,68,.3);
    border-radius: 12px; padding: 12px 16px;
    font-size: 13px; color: #f87171; margin-bottom: 16px;
}
.pt-error b { color: #fca5a5; }
.pt-rate-limit {
    background: rgba(251,191,36,.08); border: 1px solid rgba(251,191,36,.3);
    border-radius: 12px; padding: 12px 16px;
    font-size: 13px; color: #fbbf24; margin-bottom: 16px;
}
.pt-rate-limit b { color: #fde68a; }
.pt-loading {
    background: #1a1b1f; border: 1px solid #2a2b30;
    border-radius: 14px; padding: 28px; text-align: center;
    font-size: 14px; color: #4a4b52;
}
.pt-summary-bar { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 16px; }
.pt-summary-chip {
    background: #1e1f23; border: 1px solid #2a2b30;
    border-radius: 8px; padding: 6px 12px;
    font-size: 12px; color: #9090a0; white-space: nowrap;
}
.pt-summary-chip b { color: #f5f5f7; }
.pt-section-label {
    font-size: 11px; font-weight: 600; color: #3a3b42;
    letter-spacing: .08em; text-transform: uppercase;
    margin: 20px 0 10px;
}
.pt-hype-note {
    background: rgba(124,92,252,.08); border: 1px solid rgba(124,92,252,.30);
    border-radius: 10px; padding: 9px 14px;
    font-size: 12px; color: #a78bfa; margin-bottom: 12px;
}
</style>
"""


# ── Session state helpers ──────────────────────────────────────────────────────

def _init_state() -> None:
    defaults = {
        _STATE_KEY_SNAP:    None,
        _STATE_KEY_METRICS: None,
        _STATE_KEY_ERROR:   None,
        _STATE_KEY_TS:      None,
        _STATE_KEY_SYMBOL:  _SYMBOLS[0],
        _STATE_KEY_DEMO:    False,
    }
    for key, default in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default

    # Initialise cross-page symbol key if missing
    if "pro_selected_symbol" not in st.session_state:
        st.session_state["pro_selected_symbol"] = ""


def _resolve_incoming_symbol() -> str:
    """
    Return the symbol to pre-select in the dropdown.

    Priority:
      1. st.session_state["pro_selected_symbol"] set by Pro Dashboard
         (consumed once — cleared after reading)
      2. Last used symbol stored in _STATE_KEY_SYMBOL
      3. Default: BTCUSDT
    """
    incoming = str(st.session_state.get("pro_selected_symbol", "")).strip().upper()
    if incoming:
        # Consume — don't keep re-triggering on every rerun
        st.session_state["pro_selected_symbol"] = ""
        # If it's HYPE or another non-Binance symbol, fall back to BTCUSDT
        if incoming not in _BINANCE_SYMBOLS:
            st.session_state[_STATE_KEY_SYMBOL] = _SYMBOLS[0]
            return _SYMBOLS[0]
        st.session_state[_STATE_KEY_SYMBOL] = incoming
        return incoming

    saved = str(st.session_state.get(_STATE_KEY_SYMBOL, _SYMBOLS[0]))
    return saved if saved in _BINANCE_SYMBOLS else _SYMBOLS[0]


# ── Demo snapshot builder ─────────────────────────────────────────────────────

def _build_demo_snapshot(symbol: str) -> "OrderBookSnapshot":  # type: ignore[name-defined]
    """Static demo OrderBookSnapshot for when Binance is region-blocked."""
    from core.models import OrderBookLevel, OrderBookSnapshot
    _mids = {"BTCUSDT": 67_500.0, "ETHUSDT": 3_500.0, "SOLUSDT": 175.0}
    mid = _mids.get(symbol, 100.0)
    bids = [
        OrderBookLevel(price=round(mid - (i + 1) * mid * 0.0002, 2),
                       qty=round(0.5 + i * 0.3, 4), usd_size=0.0)
        for i in range(10)
    ]
    asks = [
        OrderBookLevel(price=round(mid + (i + 1) * mid * 0.0002, 2),
                       qty=round(0.4 + i * 0.25, 4), usd_size=0.0)
        for i in range(10)
    ]
    for lvl in bids + asks:
        object.__setattr__(lvl, "usd_size", round(lvl.price * lvl.qty, 2))
    return OrderBookSnapshot(
        symbol=symbol, exchange="binance-demo",
        timestamp_ms=int(time.time() * 1000),
        bids=bids, asks=asks, mid_price=mid,
    )


# ── Fetch ─────────────────────────────────────────────────────────────────────

def _do_fetch(symbol: str) -> None:
    """Fetch orderbook and run analysis. Stores to session state. Never raises."""
    st.session_state[_STATE_KEY_ERROR]   = None
    st.session_state[_STATE_KEY_SNAP]    = None
    st.session_state[_STATE_KEY_METRICS] = None

    try:
        sym = normalize_symbol(symbol)
    except InvalidSymbolError as exc:
        st.session_state[_STATE_KEY_ERROR] = ("invalid", str(exc))
        return

    try:
        snapshot = fetch_orderbook(sym, limit=_DEPTH_LIMIT)
        st.session_state[_STATE_KEY_DEMO] = False
    except RestrictedLocationError:
        st.session_state[_STATE_KEY_DEMO]    = True
        st.session_state[_STATE_KEY_ERROR]   = None
        snap = _build_demo_snapshot(sym)
        st.session_state[_STATE_KEY_SNAP]    = snap
        st.session_state[_STATE_KEY_SYMBOL]  = sym
        st.session_state[_STATE_KEY_TS]      = None
        st.session_state[_STATE_KEY_METRICS] = analyze_orderbook(snap)
        return
    except RateLimitError as exc:
        st.session_state[_STATE_KEY_ERROR] = ("ratelimit", str(exc))
        return
    except ConnectorError as exc:
        st.session_state[_STATE_KEY_ERROR] = ("connector", str(exc))
        return
    except Exception as exc:
        st.session_state[_STATE_KEY_ERROR] = ("unexpected", f"Unexpected error: {exc}")
        return

    try:
        metrics = analyze_orderbook(snapshot)
    except Exception as exc:
        st.session_state[_STATE_KEY_ERROR] = (
            "analysis", f"Analysis failed: {exc}. Raw data was fetched."
        )
        st.session_state[_STATE_KEY_SNAP] = snapshot
        return

    st.session_state[_STATE_KEY_SNAP]    = snapshot
    st.session_state[_STATE_KEY_METRICS] = metrics
    st.session_state[_STATE_KEY_TS]      = time.time()
    st.session_state[_STATE_KEY_SYMBOL]  = sym


# ── Error renderer ────────────────────────────────────────────────────────────

def _render_error(error: tuple[str, str] | None) -> None:
    if error is None:
        return
    kind, msg = error
    if kind == "ratelimit":
        st.markdown(
            f'<div class="pt-rate-limit">'
            f"<b>Rate limit hit.</b> Wait 30-60s before refreshing.<br>"
            f"<span style='font-size:11px;color:#a16207'>{msg}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )
    elif kind == "connector":
        st.markdown(
            f'<div class="pt-error">'
            f"<b>Connection error.</b> Could not fetch orderbook from Binance.<br>"
            f"<span style='font-size:11px;opacity:.7'>{msg}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )
    elif kind == "invalid":
        st.markdown(
            f'<div class="pt-error"><b>Invalid symbol.</b> {msg}</div>',
            unsafe_allow_html=True,
        )
    elif kind == "analysis":
        st.markdown(
            f'<div class="pt-error"><b>Analysis error.</b> {msg}</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<div class="pt-error"><b>Error:</b> {msg}</div>',
            unsafe_allow_html=True,
        )


# ── Summary bar ───────────────────────────────────────────────────────────────

def _render_summary_bar(metrics, snapshot) -> None:
    if metrics is None:
        return
    _ts  = st.session_state.get(_STATE_KEY_TS)
    _ts_str = datetime.datetime.fromtimestamp(_ts).strftime("%H:%M:%S") if _ts else "-"
    _lvl = f"{len(snapshot.bids)}x{len(snapshot.asks)}" if snapshot else "-"

    def _pfmt(p: float) -> str:
        return f"{p:,.2f}" if p >= 1_000 else f"{p:.4f}" if p >= 1 else f"{p:.6f}"

    st.markdown(
        f"""<div class="pt-summary-bar">
  <div class="pt-summary-chip">Mid <b>${_pfmt(metrics.mid_price)}</b></div>
  <div class="pt-summary-chip">Spread <b>{metrics.spread_pct:.3f}%</b></div>
  <div class="pt-summary-chip">Levels <b>{_lvl}</b></div>
  <div class="pt-summary-chip">Liquidity <b>{metrics.liquidity_score:.0f}/100</b></div>
  <div class="pt-summary-chip">Last fetch <b>{_ts_str}</b></div>
</div>""",
        unsafe_allow_html=True,
    )


# ── Main render function ───────────────────────────────────────────────────────

def render_pro_terminal() -> None:
    """
    Render the full Pro Trading Terminal page.

    Reads st.session_state["pro_selected_symbol"] if set by Pro Dashboard,
    pre-selects it in the symbol dropdown, then clears it.
    Manual Refresh only.
    """
    _init_state()
    st.markdown(_CSS, unsafe_allow_html=True)

    st.markdown('<div class="pt-page-title">Pro Terminal</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="pt-page-sub">Live Binance orderbook — depth, imbalance, walls, slippage.</div>',
        unsafe_allow_html=True,
    )

    # ── Resolve symbol (may come from Pro Dashboard) ──────────────────────────
    _initial_sym = _resolve_incoming_symbol()

    # Show HYPE note if it was requested but not available on Binance
    _raw_incoming = str(st.session_state.get("pro_selected_symbol", "")).strip().upper()
    # Note: already cleared by _resolve_incoming_symbol, so check the stored symbol
    # We detect the HYPE case by checking if the stored key was HYPEUSDT before fallback
    # Simpler: just check if user's last session symbol was HYPE
    if st.session_state.get("_pt_showed_hype_note"):
        st.markdown(
            f'<div class="pt-hype-note">{_HYPE_NOTE}</div>',
            unsafe_allow_html=True,
        )
        st.session_state["_pt_showed_hype_note"] = False

    # ── Toolbar ───────────────────────────────────────────────────────────────
    _sym_idx = _SYMBOLS.index(_initial_sym) if _initial_sym in _SYMBOLS else 0

    _tb_sym, _tb_btn, _tb_depth, _tb_spacer = st.columns([0.25, 0.15, 0.25, 0.35])

    with _tb_sym:
        _selected = st.selectbox(
            "Market",
            options=_SYMBOLS,
            index=_sym_idx,
            key="_pt_symbol_select",
            label_visibility="collapsed",
        )

    with _tb_depth:
        _depth_choice = st.selectbox(
            "Book depth",
            options=[20, 50, 100],
            index=0,
            format_func=lambda x: f"Top {x} levels",
            key="_pt_depth_select",
            label_visibility="collapsed",
        )

    with _tb_btn:
        _refresh_clicked = st.button(
            "Refresh",
            key="_pt_refresh_btn",
            use_container_width=True,
            type="primary",
        )

    # ── Fetch trigger ─────────────────────────────────────────────────────────
    _last_sym     = st.session_state.get(_STATE_KEY_SYMBOL)
    _first_load   = (
        st.session_state.get(_STATE_KEY_SNAP) is None
        and st.session_state.get(_STATE_KEY_ERROR) is None
    )
    _symbol_changed = _last_sym != _selected

    if _refresh_clicked or _first_load or _symbol_changed:
        with st.spinner(f"Fetching {_selected} orderbook from Binance..."):
            _do_fetch(_selected)

    # ── Demo mode banner ──────────────────────────────────────────────────────
    if st.session_state.get(_STATE_KEY_DEMO):
        st.warning(
            "**Demo mode** — Binance is blocked from this hosted region (HTTP 451). "
            "Data shown is static sample data. Run the app locally for live data.",
            icon="⚠️",
        )

    # ── Error ─────────────────────────────────────────────────────────────────
    _render_error(st.session_state.get(_STATE_KEY_ERROR))

    # ── Summary bar ───────────────────────────────────────────────────────────
    _metrics  = st.session_state.get(_STATE_KEY_METRICS)
    _snapshot = st.session_state.get(_STATE_KEY_SNAP)
    _render_summary_bar(_metrics, _snapshot)

    # ── Orderbook panel ───────────────────────────────────────────────────────
    if _snapshot is not None or _metrics is not None:
        st.markdown(
            '<div class="pt-section-label">Order book</div>',
            unsafe_allow_html=True,
        )
        render_orderbook_panel(
            snapshot=_snapshot,
            metrics=_metrics,
            show_book_rows=_depth_choice // 2,
        )
    elif st.session_state.get(_STATE_KEY_ERROR) is None:
        st.markdown(
            '<div class="pt-loading">Select a market and click Refresh to load live data.</div>',
            unsafe_allow_html=True,
        )

    # ── Liquidity heatmap ──────────────────────────────────────────────────────
    if _HEATMAP_AVAILABLE and (_snapshot is not None or _metrics is not None):
        st.markdown(
            '<div class="pt-section-label">Liquidity Wall Map</div>',
            unsafe_allow_html=True,
        )
        _heatmap_mode = "demo"
        try:
            if _snapshot is not None and not _snapshot.is_empty:
                _hm_cells = _build_heatmap(_snapshot, levels=20)
                if _hm_cells:
                    _heatmap_mode = "snapshot"
                else:
                    _hm_cells = _demo_heatmap_cells()
            else:
                _hm_cells = _demo_heatmap_cells()
        except Exception:
            _hm_cells = _demo_heatmap_cells()

        _hm_title = (
            "Liquidity Wall Map — Live"
            if _heatmap_mode == "snapshot"
            else "Liquidity Wall Map — Demo"
        )
        _render_liquidity_heatmap(_hm_cells, title=_hm_title)
        st.markdown(
            f'<div class="pt-last-updated">'
            f'Heatmap mode: <b>{"Snapshot" if _heatmap_mode == "snapshot" else "Demo fallback"}</b>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # ── Footer ────────────────────────────────────────────────────────────────
    _ts      = st.session_state.get(_STATE_KEY_TS)
    _is_demo = st.session_state.get(_STATE_KEY_DEMO, False)
    if _is_demo:
        st.markdown(
            '<div class="pt-last-updated">'
            "Mode: <b>Demo fallback</b> &nbsp;&middot;&nbsp; "
            "Binance unavailable from this region"
            "</div>",
            unsafe_allow_html=True,
        )
    elif _ts:
        _age    = int(time.time() - _ts)
        _ts_fmt = datetime.datetime.fromtimestamp(_ts).strftime("%Y-%m-%d %H:%M:%S")
        st.markdown(
            f'<div class="pt-last-updated">'
            f"Data fetched at {_ts_fmt} ({_age}s ago) "
            f"&nbsp;&middot;&nbsp; "
            f"Source: Binance REST API (public, no key required)"
            f"</div>",
            unsafe_allow_html=True,
        )
