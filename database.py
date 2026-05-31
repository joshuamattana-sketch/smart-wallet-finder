import streamlit as st
import json
from datetime import datetime

# ─────────────────────────────────────────
# Supabase client (cached so it's created once)
# ─────────────────────────────────────────
@st.cache_resource
def get_supabase():
    try:
        from supabase import create_client
        url = st.secrets.get("SUPABASE_URL", "")
        key = st.secrets.get("SUPABASE_KEY", "")
        if not url or not key:
            return None
        return create_client(url, key)
    except Exception:
        return None


def db_available():
    return get_supabase() is not None


# ─────────────────────────────────────────
# Generic helpers
# ─────────────────────────────────────────
def _now():
    return datetime.utcnow().isoformat()


def _safe(fn, fallback):
    """Run fn(); return fallback on any error."""
    try:
        return fn()
    except Exception:
        return fallback


# ─────────────────────────────────────────
# WATCHLIST WALLETS
# ─────────────────────────────────────────
def load_watchlist_wallets():
    sb = get_supabase()
    if not sb:
        return []
    res = _safe(
        lambda: sb.table("watchlist_wallets").select("*").order("created_at").execute(),
        None
    )
    if res and res.data:
        return [row["data"] for row in res.data]
    return []


def save_watchlist_wallets(wallets: list):
    sb = get_supabase()
    if not sb:
        return
    # Upsert full list as a single JSON blob keyed by "wallets"
    _safe(
        lambda: sb.table("app_state").upsert({
            "key": "watchlist_wallets",
            "value": json.dumps(wallets),
            "updated_at": _now()
        }).execute(),
        None
    )


def load_watchlist_wallets_blob() -> list:
    sb = get_supabase()
    if not sb:
        return []
    res = _safe(
        lambda: sb.table("app_state").select("value").eq("key", "watchlist_wallets").execute(),
        None
    )
    if res and res.data:
        return json.loads(res.data[0]["value"])
    return []


# ─────────────────────────────────────────
# WATCHLIST TOKENS
# ─────────────────────────────────────────
def load_watchlist_tokens() -> list:
    sb = get_supabase()
    if not sb:
        return []
    res = _safe(
        lambda: sb.table("app_state").select("value").eq("key", "watchlist_tokens").execute(),
        None
    )
    if res and res.data:
        return json.loads(res.data[0]["value"])
    return []


def save_watchlist_tokens(tokens: list):
    sb = get_supabase()
    if not sb:
        return
    _safe(
        lambda: sb.table("app_state").upsert({
            "key": "watchlist_tokens",
            "value": json.dumps(tokens),
            "updated_at": _now()
        }).execute(),
        None
    )


# ─────────────────────────────────────────
# WALLET HISTORY
# ─────────────────────────────────────────
def load_wallet_history() -> dict:
    sb = get_supabase()
    if not sb:
        return {}
    res = _safe(
        lambda: sb.table("app_state").select("value").eq("key", "wallet_history").execute(),
        None
    )
    if res and res.data:
        return json.loads(res.data[0]["value"])
    return {}


def save_wallet_history(history: dict):
    sb = get_supabase()
    if not sb:
        return
    _safe(
        lambda: sb.table("app_state").upsert({
            "key": "wallet_history",
            "value": json.dumps(history),
            "updated_at": _now()
        }).execute(),
        None
    )


# ─────────────────────────────────────────
# WALLET LABELS
# ─────────────────────────────────────────
def load_wallet_labels() -> dict:
    sb = get_supabase()
    if not sb:
        return {}
    res = _safe(
        lambda: sb.table("app_state").select("value").eq("key", "wallet_labels").execute(),
        None
    )
    if res and res.data:
        return json.loads(res.data[0]["value"])
    return {}


def save_wallet_labels_db(labels: dict):
    sb = get_supabase()
    if not sb:
        return
    _safe(
        lambda: sb.table("app_state").upsert({
            "key": "wallet_labels",
            "value": json.dumps(labels),
            "updated_at": _now()
        }).execute(),
        None
    )


# ─────────────────────────────────────────
# WALLET DOCUMENTATION (Journal)
# ─────────────────────────────────────────
def load_wallet_documentation() -> dict:
    sb = get_supabase()
    if not sb:
        return {}
    res = _safe(
        lambda: sb.table("app_state").select("value").eq("key", "wallet_documentation").execute(),
        None
    )
    if res and res.data:
        return json.loads(res.data[0]["value"])
    return {}


def save_wallet_documentation(docs: dict):
    sb = get_supabase()
    if not sb:
        return
    _safe(
        lambda: sb.table("app_state").upsert({
            "key": "wallet_documentation",
            "value": json.dumps(docs),
            "updated_at": _now()
        }).execute(),
        None
    )


# ─────────────────────────────────────────
# PAPER TRADES
# ─────────────────────────────────────────
def load_paper_trades() -> list:
    sb = get_supabase()
    if not sb:
        return []
    res = _safe(
        lambda: sb.table("app_state").select("value").eq("key", "paper_trades").execute(),
        None
    )
    if res and res.data:
        return json.loads(res.data[0]["value"])
    return []


def save_paper_trades(trades: list):
    sb = get_supabase()
    if not sb:
        return
    _safe(
        lambda: sb.table("app_state").upsert({
            "key": "paper_trades",
            "value": json.dumps(trades),
            "updated_at": _now()
        }).execute(),
        None
    )


# ─────────────────────────────────────────
# MARKET SNAPSHOTS
# ─────────────────────────────────────────
def load_market_snapshots() -> list:
    sb = get_supabase()
    if not sb:
        return []
    res = _safe(
        lambda: sb.table("app_state").select("value").eq("key", "market_snapshots").execute(),
        None
    )
    if res and res.data:
        return json.loads(res.data[0]["value"])
    return []


def save_market_snapshots(snapshots: list):
    sb = get_supabase()
    if not sb:
        return
    _safe(
        lambda: sb.table("app_state").upsert({
            "key": "market_snapshots",
            "value": json.dumps(snapshots),
            "updated_at": _now()
        }).execute(),
        None
    )


# ─────────────────────────────────────────
# GENERIC KEY/VALUE (for any other settings)
# ─────────────────────────────────────────
def load_state(key: str, fallback=None):
    sb = get_supabase()
    if not sb:
        return fallback
    res = _safe(
        lambda: sb.table("app_state").select("value").eq("key", key).execute(),
        None
    )
    if res and res.data:
        try:
            return json.loads(res.data[0]["value"])
        except Exception:
            return res.data[0]["value"]
    return fallback


def save_state(key: str, value):
    sb = get_supabase()
    if not sb:
        return
    _safe(
        lambda: sb.table("app_state").upsert({
            "key": key,
            "value": json.dumps(value),
            "updated_at": _now()
        }).execute(),
        None
    )


# ─────────────────────────────────────────
# EVENT LOG (for learning engine later)
# ─────────────────────────────────────────
def log_event(event_type: str, data: dict):
    """
    Log any event for the pattern engine to learn from later.
    event_type examples: 'token_discovered', 'wallet_early', 'paper_trade_closed'
    """
    sb = get_supabase()
    if not sb:
        return
    _safe(
        lambda: sb.table("events").insert({
            "event_type": event_type,
            "data": json.dumps(data),
            "created_at": _now()
        }).execute(),
        None
    )