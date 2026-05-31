import streamlit as st
import pandas as pd
import requests
import json
from pathlib import Path
from openai import OpenAI
from streamlit_autorefresh import st_autorefresh
import time
import re
import traceback
import hashlib
from contextlib import contextmanager

st.set_page_config(
    page_title="Smart Wallet Finder",
    layout="wide",
    initial_sidebar_state="expanded"
)

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)


# -----------------------------
# Stability / UX foundation
# -----------------------------
APP_BUILD_NAME = "Stability UI Build"
APP_BUILD_VERSION = "2026-05-30"


def human_error_message(section_name, error):
    return (
        f"{section_name} could not be rendered safely. "
        "The app stayed open so you can switch sections, retry, or continue testing."
    )


def render_safe_error(section_name, error):
    st.markdown(
        """
        <style>
        .safe-error-card {
            border: 1px solid rgba(248, 113, 113, 0.35);
            background: linear-gradient(135deg, rgba(127, 29, 29, 0.30), rgba(15, 23, 42, 0.92));
            border-radius: 18px;
            padding: 18px 20px;
            margin: 14px 0;
            color: #fee2e2;
        }
        .safe-error-title {
            font-size: 18px;
            font-weight: 900;
            margin-bottom: 6px;
            color: #fecaca;
        }
        .safe-error-sub {
            font-size: 13px;
            color: #fca5a5;
            line-height: 1.45;
            margin-bottom: 10px;
        }
        .safe-error-next {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 8px;
            margin-top: 10px;
        }
        .safe-error-next div {
            border: 1px solid rgba(255,255,255,0.09);
            background: rgba(255,255,255,0.04);
            border-radius: 12px;
            padding: 10px 12px;
            color: #f8fafc;
            font-size: 12px;
        }
        @media (max-width: 900px) {
            .safe-error-next { grid-template-columns: 1fr; }
        }
        </style>
        """,
        unsafe_allow_html=True
    )
    st.markdown(
        f"""
        <div class="safe-error-card">
            <div class="safe-error-title">This section hit a safe error</div>
            <div class="safe-error-sub">{human_error_message(section_name, error)}</div>
            <div class="safe-error-next">
                <div><b>1. Stay calm</b><br>The whole app did not crash.</div>
                <div><b>2. Try again</b><br>Refresh or switch section.</div>
                <div><b>3. Send the trace</b><br>The technical error is below.</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )
    with st.expander("Technical details for debugging", expanded=False):
        st.code("".join(traceback.format_exception(type(error), error, error.__traceback__)))


@contextmanager
def safe_section(section_name):
    try:
        yield
    except Exception as error:
        render_safe_error(section_name, error)


def compact_address(value, front=6, back=4):
    text = str(value or "").strip()
    if len(text) <= front + back + 3:
        return text or "-"
    return f"{text[:front]}…{text[-back:]}"


def safe_dataframe(df, columns=None, empty_message="No data yet.", height=None):
    if df is None or not hasattr(df, "empty") or df.empty:
        st.info(empty_message)
        return
    show_df = df.copy()
    if columns:
        show_df = show_df[[col for col in columns if col in show_df.columns]]
    st.dataframe(show_df, width="stretch", hide_index=True, height=height)

WALLET_WATCHLIST_FILE = DATA_DIR / "watchlist_wallets.json"
WALLET_HISTORY_FILE = DATA_DIR / "wallet_history.json"
AUTO_WALLET_SETTINGS_FILE = DATA_DIR / "auto_wallet_settings.json"
TOKEN_WATCHLIST_FILE = DATA_DIR / "watchlist_tokens.json"
RECENT_TOKEN_MINTS_FILE = DATA_DIR / "recent_token_mints.json"
RECENT_WALLETS_FILE = DATA_DIR / "recent_wallets.json"
RECENT_AI_SEARCHES_FILE = DATA_DIR / "recent_ai_searches.json"
DEX_ALPHA_SEEN_FILE = DATA_DIR / "dex_alpha_seen_cache.json"
WALLET_LABELS_FILE = DATA_DIR / "wallet_labels.json"
MARKET_MONITOR_SETTINGS_FILE = DATA_DIR / "market_monitor_settings.json"
MARKET_SNAPSHOTS_FILE = DATA_DIR / "market_snapshots.json"
TOKEN_MEMORY_FILE = DATA_DIR / "token_memory.json"
WALLET_ALPHA_MEMORY_FILE = DATA_DIR / "wallet_alpha_memory.json"
DISCOVERY_RUNS_FILE = DATA_DIR / "discovery_runs.json"
WALLET_DOCUMENTATION_FILE = DATA_DIR / "wallet_documentation.json"
WALLET_JOURNAL_PINS_FILE = DATA_DIR / "wallet_journal_pins.json"
JOURNAL_REFRESH_SETTINGS_FILE = DATA_DIR / "journal_refresh_settings.json"
BETA_LOGIN_SESSION_FILE = DATA_DIR / "beta_login_session.json"
PAPER_SETTINGS_FILE = DATA_DIR / "paper_trading_settings.json"
PAPER_TRADES_FILE = DATA_DIR / "paper_trades.json"
PAPER_EVENTS_FILE = DATA_DIR / "paper_trading_events.json"
MY_WALLETS_FILE = DATA_DIR / "my_wallets.json"



# ─────────────────────────────────────────
# SUPABASE STORAGE LAYER (inline)
# ─────────────────────────────────────────
from datetime import datetime as _dt

@st.cache_resource
def _get_sb():
    try:
        from supabase import create_client
        url = st.secrets.get("SUPABASE_URL", "")
        key = st.secrets.get("SUPABASE_KEY", "")
        if url and key:
            return create_client(url, key)
    except Exception:
        pass
    return None

def _sb_now():
    return _dt.utcnow().isoformat()

def _sb_load(key):
    try:
        sb = _get_sb()
        if not sb:
            return None
        res = sb.table("app_state").select("value").eq("key", key).execute()
        if res.data:
            return json.loads(res.data[0]["value"])
    except Exception:
        pass
    return None

def _sb_save(key, value):
    try:
        sb = _get_sb()
        if not sb:
            return False
        sb.table("app_state").upsert({
            "key": key,
            "value": json.dumps(value, default=str),
            "updated_at": _sb_now()
        }).execute()
        return True
    except Exception:
        return False

def load_json_list(file_path):
    result = _sb_load(file_path.stem)
    if result is not None:
        return result if isinstance(result, list) else []
    try:
        if file_path.exists():
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        pass
    return []

def save_json_list(file_path, data):
    _sb_save(file_path.stem, data)
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
    except Exception:
        pass

def load_json_dict(file_path):
    result = _sb_load(file_path.stem)
    if result is not None:
        return result if isinstance(result, dict) else {}
    try:
        if file_path.exists():
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        pass
    return {}

def save_json_dict(file_path, data):
    _sb_save(file_path.stem, data)
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
    except Exception:
        pass

def log_event(event_type, data):
    try:
        sb = _get_sb()
        if sb:
            sb.table("events").insert({
                "event_type": event_type,
                "data": json.dumps(data, default=str),
                "created_at": _sb_now()
            }).execute()
    except Exception:
        pass

def storage_status():
    sb = _get_sb()
    if sb:
        try:
            sb.table("app_state").select("key").limit(1).execute()
            return {"connected": True, "mode": "Supabase"}
        except Exception:
            pass
    return {"connected": False, "mode": "Local JSON"}

# ─────────────────────────────────────────

# Early numeric helpers used during session-state boot.
# The full helpers are defined again later, but these keep startup safe.
def safe_float(value, default=0):
    try:
        if value is None or value == "-":
            return default
        return float(value)
    except Exception:
        return default


def safe_int(value, default=0):
    try:
        if value is None or value == "-":
            return default
        return int(float(value))
    except Exception:
        return default

if "watchlist_wallets" not in st.session_state:
    st.session_state.watchlist_wallets = load_json_list(WALLET_WATCHLIST_FILE)

if "watchlist_tokens" not in st.session_state:
    st.session_state.watchlist_tokens = load_json_list(TOKEN_WATCHLIST_FILE)

if "token_watchlist_message" not in st.session_state:
    st.session_state.token_watchlist_message = ""

if "watchlist_message" not in st.session_state:
    st.session_state.watchlist_message = ""

if "keep_wallet_scan" not in st.session_state:
    st.session_state.keep_wallet_scan = False

if "last_wallet_scan" not in st.session_state:
    st.session_state.last_wallet_scan = None

if "selected_token_mint" not in st.session_state:
    st.session_state.selected_token_mint = ""

if "section_override" not in st.session_state:
    st.session_state.section_override = None

if "last_auto_token_review" not in st.session_state:
    st.session_state.last_auto_token_review = pd.DataFrame()

if "recent_token_mints" not in st.session_state:
    st.session_state.recent_token_mints = load_json_list(RECENT_TOKEN_MINTS_FILE)

if "recent_wallets" not in st.session_state:
    st.session_state.recent_wallets = load_json_list(RECENT_WALLETS_FILE)

if "recent_ai_searches" not in st.session_state:
    st.session_state.recent_ai_searches = load_json_list(RECENT_AI_SEARCHES_FILE)

if "wallet_history" not in st.session_state:
    st.session_state.wallet_history = load_json_dict(WALLET_HISTORY_FILE)

if "last_auto_wallet_check_count" not in st.session_state:
    st.session_state.last_auto_wallet_check_count = 0

if "last_auto_wallet_failed_count" not in st.session_state:
    st.session_state.last_auto_wallet_failed_count = 0

if "auto_wallet_settings" not in st.session_state:
    saved_auto_settings = load_json_dict(AUTO_WALLET_SETTINGS_FILE)
    st.session_state.auto_wallet_settings = {
        "enabled": bool(saved_auto_settings.get("enabled", False)),
        "interval": int(saved_auto_settings.get("interval", 60)),
        "scope": saved_auto_settings.get("scope", "Pinned first, then all"),
        "last_saved": saved_auto_settings.get("last_saved", "")
    }

if "last_auto_wallet_saved_state" not in st.session_state:
    st.session_state.last_auto_wallet_saved_state = dict(st.session_state.auto_wallet_settings)

if "auto_discovered_tokens" not in st.session_state:
    st.session_state.auto_discovered_tokens = pd.DataFrame()

if "auto_discovered_wallets" not in st.session_state:
    st.session_state.auto_discovered_wallets = pd.DataFrame()

if "auto_discovery_message" not in st.session_state:
    st.session_state.auto_discovery_message = ""

if "auto_discovery_last_token" not in st.session_state:
    st.session_state.auto_discovery_last_token = ""

if "dex_alpha_seen_tokens" not in st.session_state or "dex_alpha_seen_wallets" not in st.session_state:
    saved_seen_cache = load_json_dict(DEX_ALPHA_SEEN_FILE)
    st.session_state.dex_alpha_seen_tokens = saved_seen_cache.get("tokens", []) if isinstance(saved_seen_cache.get("tokens", []), list) else []
    st.session_state.dex_alpha_seen_wallets = saved_seen_cache.get("wallets", []) if isinstance(saved_seen_cache.get("wallets", []), list) else []
    st.session_state.dex_alpha_seen_saved_at = saved_seen_cache.get("saved_at", "")



if "wallet_labels" not in st.session_state:
    saved_wallet_labels = load_json_dict(WALLET_LABELS_FILE)
    st.session_state.wallet_labels = saved_wallet_labels if isinstance(saved_wallet_labels, dict) else {}

if "market_monitor_settings" not in st.session_state:
    saved_market_monitor_settings = load_json_dict(MARKET_MONITOR_SETTINGS_FILE)
    st.session_state.market_monitor_settings = {
        "enabled": bool(saved_market_monitor_settings.get("enabled", False)),
        "interval_minutes": int(saved_market_monitor_settings.get("interval_minutes", 10)),
        "max_tokens": int(saved_market_monitor_settings.get("max_tokens", 5)),
        "min_score": int(saved_market_monitor_settings.get("min_score", 55)),
        "wallets_per_token": int(saved_market_monitor_settings.get("wallets_per_token", 8)),
        "strict_early": bool(saved_market_monitor_settings.get("strict_early", True)),
        "last_scan_ts": float(saved_market_monitor_settings.get("last_scan_ts", 0) or 0),
        "last_scan_label": saved_market_monitor_settings.get("last_scan_label", ""),
    }

if "market_snapshots" not in st.session_state:
    st.session_state.market_snapshots = load_json_list(MARKET_SNAPSHOTS_FILE)

if "token_memory" not in st.session_state:
    st.session_state.token_memory = load_json_dict(TOKEN_MEMORY_FILE)

if "wallet_alpha_memory" not in st.session_state:
    st.session_state.wallet_alpha_memory = load_json_dict(WALLET_ALPHA_MEMORY_FILE)

if "discovery_runs" not in st.session_state:
    st.session_state.discovery_runs = load_json_list(DISCOVERY_RUNS_FILE)

if "market_monitor_message" not in st.session_state:
    st.session_state.market_monitor_message = ""

if "wallet_documentation" not in st.session_state:
    st.session_state.wallet_documentation = load_json_dict(WALLET_DOCUMENTATION_FILE)

if "wallet_journal_pins" not in st.session_state:
    saved_journal_pins = load_json_list(WALLET_JOURNAL_PINS_FILE)
    st.session_state.wallet_journal_pins = sorted({str(value).strip() for value in saved_journal_pins if str(value).strip()})

if "journal_refresh_settings" not in st.session_state:
    saved_journal_refresh_settings = load_json_dict(JOURNAL_REFRESH_SETTINGS_FILE)
    st.session_state.journal_refresh_settings = {
        "enabled": bool(saved_journal_refresh_settings.get("enabled", False)),
        "interval_seconds": safe_int(saved_journal_refresh_settings.get("interval_seconds", 60), 60),
        "scope": saved_journal_refresh_settings.get("scope", "Journal pinned only"),
        "max_wallets": safe_int(saved_journal_refresh_settings.get("max_wallets", 5), 5),
        "min_trust": safe_int(saved_journal_refresh_settings.get("min_trust", 50), 50),
        "last_refresh_ts": safe_float(saved_journal_refresh_settings.get("last_refresh_ts", 0), 0),
        "last_refresh_label": saved_journal_refresh_settings.get("last_refresh_label", ""),
    }


# -----------------------------
# Paper trading / fake wallet state
# -----------------------------
if "paper_settings" not in st.session_state:
    saved_paper_settings = load_json_dict(PAPER_SETTINGS_FILE)
    st.session_state.paper_settings = {
        "enabled": bool(saved_paper_settings.get("enabled", False)),
        "auto_copy": bool(saved_paper_settings.get("auto_copy", False)),
        "source": saved_paper_settings.get("source", "Journal pinned only"),
        "fake_balance_start": safe_float(saved_paper_settings.get("fake_balance_start", 1000), 1000),
        "cash": safe_float(saved_paper_settings.get("cash", saved_paper_settings.get("fake_balance_start", 1000)), 1000),
        "trade_size": safe_float(saved_paper_settings.get("trade_size", 25), 25),
        "max_open_trades": safe_int(saved_paper_settings.get("max_open_trades", 5), 5),
        "stop_loss_pct": safe_float(saved_paper_settings.get("stop_loss_pct", -25), -25),
        "take_profit_pct": safe_float(saved_paper_settings.get("take_profit_pct", 50), 50),
        "max_trade_size_pct": safe_float(saved_paper_settings.get("max_trade_size_pct", 10), 10),
        "min_liquidity_usd": safe_float(saved_paper_settings.get("min_liquidity_usd", 1000), 1000),
        "confirm_lock_result": bool(saved_paper_settings.get("confirm_lock_result", False)),
        "copy_cooldown_minutes": safe_int(saved_paper_settings.get("copy_cooldown_minutes", 10), 10),
        "live_refresh_seconds": safe_int(saved_paper_settings.get("live_refresh_seconds", 1), 1),
        "selected_source_wallets": saved_paper_settings.get("selected_source_wallets", []) if isinstance(saved_paper_settings.get("selected_source_wallets", []), list) else [],
        "last_bot_ts": safe_float(saved_paper_settings.get("last_bot_ts", 0), 0),
        "last_saved": saved_paper_settings.get("last_saved", "")
    }

if "paper_trades" not in st.session_state:
    saved_paper_trades = load_json_list(PAPER_TRADES_FILE)
    st.session_state.paper_trades = saved_paper_trades if isinstance(saved_paper_trades, list) else []

if "paper_events" not in st.session_state:
    saved_paper_events = load_json_list(PAPER_EVENTS_FILE)
    st.session_state.paper_events = saved_paper_events if isinstance(saved_paper_events, list) else []

if "my_wallets" not in st.session_state:
    saved_my_wallets = load_json_list(MY_WALLETS_FILE)
    st.session_state.my_wallets = saved_my_wallets if isinstance(saved_my_wallets, list) else []

if "paper_message" not in st.session_state:
    st.session_state.paper_message = ""

if "paper_last_impact" not in st.session_state:
    st.session_state.paper_last_impact = {}

if "paper_action_locks" not in st.session_state:
    st.session_state.paper_action_locks = {}




def save_dex_alpha_seen_cache():
    tokens = sorted({str(value).strip() for value in st.session_state.get("dex_alpha_seen_tokens", []) if str(value).strip()})
    wallets = sorted({str(value).strip() for value in st.session_state.get("dex_alpha_seen_wallets", []) if str(value).strip()})
    st.session_state.dex_alpha_seen_tokens = tokens
    st.session_state.dex_alpha_seen_wallets = wallets
    st.session_state.dex_alpha_seen_saved_at = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    save_json_dict(DEX_ALPHA_SEEN_FILE, {
        "tokens": tokens,
        "wallets": wallets,
        "saved_at": st.session_state.dex_alpha_seen_saved_at
    })


def reset_dex_alpha_seen_cache():
    st.session_state.dex_alpha_seen_tokens = []
    st.session_state.dex_alpha_seen_wallets = []
    st.session_state.dex_alpha_seen_saved_at = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    save_json_dict(DEX_ALPHA_SEEN_FILE, {"tokens": [], "wallets": [], "saved_at": st.session_state.dex_alpha_seen_saved_at})


def dex_alpha_seen_counts():
    return len(st.session_state.get("dex_alpha_seen_tokens", [])), len(st.session_state.get("dex_alpha_seen_wallets", []))


# -----------------------------
# Human wallet names / labels
# -----------------------------
def save_wallet_labels():
    labels = st.session_state.get("wallet_labels", {})
    clean_labels = {}
    if isinstance(labels, dict):
        for wallet, value in labels.items():
            wallet_key = str(wallet or "").strip()
            if not wallet_key:
                continue
            if isinstance(value, dict):
                name = str(value.get("name", "")).strip()
                note = str(value.get("note", "")).strip()
            else:
                name = str(value or "").strip()
                note = ""
            if name or note:
                clean_labels[wallet_key] = {"name": name, "note": note}
    st.session_state.wallet_labels = clean_labels
    save_json_dict(WALLET_LABELS_FILE, clean_labels)


def wallet_label_record(wallet_address):
    wallet_key = str(wallet_address or "").strip()
    labels = st.session_state.get("wallet_labels", {})
    if not isinstance(labels, dict):
        return {}
    value = labels.get(wallet_key, {})
    if isinstance(value, dict):
        return value
    if value:
        return {"name": str(value), "note": ""}
    return {}


def wallet_row_dict(row=None):
    if row is None:
        return {}
    if isinstance(row, dict):
        return row
    if isinstance(row, pd.Series):
        return row.to_dict()
    if hasattr(row, "to_dict"):
        try:
            value = row.to_dict()
            return value if isinstance(value, dict) else {}
        except Exception:
            return {}
    if hasattr(row, "get"):
        return row
    return {}


def wallet_auto_name(wallet_address, row=None, prefix="Alpha Wallet"):
    wallet = str(wallet_address or "").strip()
    if not wallet:
        return prefix

    row_data = wallet_row_dict(row)
    score = safe_float(row_data.get("Alpha Wallet Score", row_data.get("Early Score", row_data.get("Score", 0))))
    early_tokens = safe_int(row_data.get("Early Tokens", 0))
    saved = str(row_data.get("Saved?", "New")).lower()

    if early_tokens >= 2 or score >= 82:
        role = "Alpha Scout"
    elif score >= 70:
        role = "Early Watcher"
    elif saved == "saved":
        role = "Saved Wallet"
    else:
        role = "Fresh Wallet"

    suffix = wallet[-4:].upper() if len(wallet) >= 4 else wallet.upper()
    return f"{role} {suffix}"


def wallet_display_name(wallet_address, fallback=None, row=None):
    wallet = str(wallet_address or "").strip()
    record = wallet_label_record(wallet)
    name = str(record.get("name", "")).strip()
    if name:
        return name

    fallback_text = str(fallback or "").strip()
    # If fallback looks like a raw or shortened address, make a human name instead.
    if fallback_text and not ("..." in fallback_text or len(fallback_text) >= 30):
        return fallback_text
    return wallet_auto_name(wallet, row=row)


def wallet_note(wallet_address):
    return str(wallet_label_record(wallet_address).get("note", "")).strip()


def set_wallet_label(wallet_address, name, note=""):
    wallet = str(wallet_address or "").strip()
    if not wallet:
        return
    if "wallet_labels" not in st.session_state or not isinstance(st.session_state.wallet_labels, dict):
        st.session_state.wallet_labels = {}
    st.session_state.wallet_labels[wallet] = {
        "name": str(name or "").strip(),
        "note": str(note or "").strip()
    }
    save_wallet_labels()


def wallet_identity_badge(row_or_item, wallet_address):
    if row_or_item is None:
        row_or_item = {}
    score = safe_float(row_or_item.get("Alpha Wallet Score", row_or_item.get("Score", row_or_item.get("Early Score", 0)))) if hasattr(row_or_item, "get") else 0
    early_tokens = safe_int(row_or_item.get("Early Tokens", 0)) if hasattr(row_or_item, "get") else 0
    pinned = bool(row_or_item.get("Pinned", False)) if hasattr(row_or_item, "get") else False
    saved = wallet_already_saved(wallet_address) if "wallet_already_saved" in globals() else False

    if pinned:
        return "Pinned"
    if early_tokens >= 2:
        return "Repeat early"
    if score >= 80:
        return "Priority"
    if score >= 65:
        return "Watch"
    if saved:
        return "Saved"
    return "New"


def wallet_watchlist_item_name(item):
    wallet_address = item.get("Full Wallet", item.get("Wallet", ""))
    return wallet_display_name(wallet_address, item.get("Wallet", ""), row=item)


def add_wallet_to_watchlist(watchlist_item):
    full_wallet = str(watchlist_item.get("Full Wallet", watchlist_item.get("Wallet", "")) or "").strip()
    if full_wallet:
        preferred_name = str(watchlist_item.get("Name", watchlist_item.get("Wallet Alias", "")) or "").strip()
        if not preferred_name:
            preferred_name = wallet_display_name(full_wallet, watchlist_item.get("Wallet", ""), row=watchlist_item)
        watchlist_item["Wallet"] = preferred_name
        watchlist_item["Wallet Alias"] = preferred_name
        watchlist_item["Name"] = preferred_name
        if not wallet_label_record(full_wallet).get("name"):
            set_wallet_label(full_wallet, preferred_name, watchlist_item.get("Label Note", ""))

    already_added = any(
        item["Full Wallet"] == watchlist_item["Full Wallet"]
        for item in st.session_state.watchlist_wallets
    )

    if already_added:
        st.session_state.watchlist_message = "Wallet is already in your watchlist."
    else:
        watchlist_item.setdefault("Pinned", False)
        watchlist_item.setdefault("Check Count", 1)
        watchlist_item.setdefault("Last Checked", pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"))
        st.session_state.watchlist_wallets.append(watchlist_item)
        save_json_list(WALLET_WATCHLIST_FILE, st.session_state.watchlist_wallets)
        st.session_state.watchlist_message = "Wallet added to watchlist."


def remove_wallet_from_watchlist(index):
    if 0 <= index < len(st.session_state.watchlist_wallets):
        st.session_state.watchlist_wallets.pop(index)
        save_json_list(WALLET_WATCHLIST_FILE, st.session_state.watchlist_wallets)
        st.session_state.watchlist_message = "Wallet removed from watchlist."



def save_auto_wallet_settings():
    if "auto_wallet_settings" not in st.session_state:
        return

    st.session_state.auto_wallet_settings["last_saved"] = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    save_json_dict(AUTO_WALLET_SETTINGS_FILE, st.session_state.auto_wallet_settings)


def set_auto_wallet_setting(key, value):
    if "auto_wallet_settings" not in st.session_state:
        st.session_state.auto_wallet_settings = {}

    if st.session_state.auto_wallet_settings.get(key) != value:
        st.session_state.auto_wallet_settings[key] = value
        save_auto_wallet_settings()


def toggle_wallet_pin(index):
    if 0 <= index < len(st.session_state.watchlist_wallets):
        current_value = bool(st.session_state.watchlist_wallets[index].get("Pinned", False))
        st.session_state.watchlist_wallets[index]["Pinned"] = not current_value
        save_json_list(WALLET_WATCHLIST_FILE, st.session_state.watchlist_wallets)

        wallet = st.session_state.watchlist_wallets[index].get("Wallet", "Wallet")
        st.session_state.watchlist_message = f"{wallet} {'pinned' if not current_value else 'unpinned'}."


def wallet_is_pinned(item):
    return bool(item.get("Pinned", False))


def wallet_check_indices(wallet_items, scope="Pinned first, then all"):
    pinned_indices = [index for index, item in enumerate(wallet_items) if wallet_is_pinned(item)]
    other_indices = [index for index, item in enumerate(wallet_items) if not wallet_is_pinned(item)]

    if scope == "Pinned only":
        return pinned_indices

    return pinned_indices + other_indices


def safe_float(value, default=0):
    try:
        if value is None or value == "-":
            return default
        return float(value)
    except Exception:
        return default


def safe_int(value, default=0):
    try:
        if value is None or value == "-":
            return default
        return int(float(value))
    except Exception:
        return default


def format_signed_number(value):
    value = safe_int(value, 0)

    if value > 0:
        return f"+{value}"

    return str(value)


def format_signed_usd(value):
    value = safe_float(value, 0)

    if value > 0:
        return f"+{format_usd(value)}"

    if value < 0:
        return f"-{format_usd(abs(value))}"

    return "$0.00"


def movement_class(value):
    value = safe_float(value, 0)

    if value > 0:
        return "movement-up"

    if value < 0:
        return "movement-down"

    return "movement-flat"


def short_change_summary(score_change, swap_change, transfer_change, volume_change, largest_change):
    parts = []

    if score_change != 0:
        parts.append(f"Score {format_signed_number(score_change)}")

    if swap_change != 0:
        parts.append(f"Swaps {format_signed_number(swap_change)}")

    if transfer_change != 0:
        parts.append(f"Transfers {format_signed_number(transfer_change)}")

    if abs(volume_change) >= 0.01:
        parts.append(f"Volume {format_signed_usd(volume_change)}")

    if abs(largest_change) >= 0.01:
        parts.append(f"Largest Tx {format_signed_usd(largest_change)}")

    return " / ".join(parts) if parts else "No movement"


def latest_wallet_activity_text(wallet_tx_data):
    if wallet_tx_data is None or wallet_tx_data.empty:
        return "-"

    latest = wallet_tx_data.iloc[0]

    timestamp = latest.get("Timestamp", "-")
    activity = latest.get("Activity", "-")
    trade_side = latest.get("Trade Side", "-")
    main_token = latest.get("Main Token", "-")
    trade_hint = latest.get("Trade Hint", "-")
    token_mints = latest.get("Token Mints", "-")
    token_amounts = latest.get("Token Amounts", "-")

    token_text = shorten_mints(token_mints) if token_mints and token_mints != "-" else "-"
    amount_text = str(token_amounts)[:70] if token_amounts and token_amounts != "-" else "-"

    if trade_side and trade_side != "-":
        return f"{timestamp} · {activity} · {trade_side} · {main_token} · {trade_hint}"

    return f"{timestamp} · {activity} · {token_text} · {amount_text}"

def extract_first_token_mint(value):
    text = str(value or "").strip()

    if not text or text == "-":
        return ""

    ignored_mints = {
        "11111111111111111111111111111111",
        "So11111111111111111111111111111111111111112",
        "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        "Es9vMFrzaCERmJfrF4H2FYD4KCoNkYhTZ8d5T6s2KZ5"
    }

    candidates = []
    for raw_part in text.replace("[", "").replace("]", "").replace("'", "").replace('"', "").split(","):
        mint = raw_part.strip()
        if len(mint) >= 32 and mint not in ignored_mints:
            candidates.append(mint)

    if candidates:
        return candidates[0]

    for raw_part in text.replace("[", "").replace("]", "").replace("'", "").replace('"', "").split(","):
        mint = raw_part.strip()
        if len(mint) >= 32:
            return mint

    return ""


def latest_wallet_token_mint(wallet_tx_data):
    if wallet_tx_data is None or wallet_tx_data.empty:
        return ""

    latest = wallet_tx_data.iloc[0]
    return extract_first_token_mint(latest.get("Token Mints", ""))


def wallet_history_key(wallet_address):
    return str(wallet_address or "").strip()


def wallet_trade_counts(wallet_tx_data):
    if wallet_tx_data is None or wallet_tx_data.empty or "Trade Side" not in wallet_tx_data.columns:
        return 0, 0, 0

    sides = wallet_tx_data["Trade Side"].astype(str).str.upper()
    buys = int((sides == "BUY").sum())
    sells = int((sides == "SELL").sum())
    rotates = int((sides == "ROTATE").sum())
    return buys, sells, rotates


def latest_trade_event_from_wallet_data(wallet_tx_data):
    if wallet_tx_data is None or wallet_tx_data.empty:
        return {}

    if "Trade Side" not in wallet_tx_data.columns:
        return {}

    for _, row in wallet_tx_data.iterrows():
        side = str(row.get("Trade Side", "-")).upper()
        if side in ["BUY", "SELL", "ROTATE", "SWAP"]:
            return {
                "Trade Side": side,
                "Trade Token": row.get("Main Token", "-"),
                "Trade Token Mint": row.get("Main Token Mint", ""),
                "Trade Amount": safe_float(row.get("Main Token Amount", 0)),
                "Trade Counter Token": row.get("Counter Token", "-"),
                "Trade Counter Amount": safe_float(row.get("Counter Token Amount", 0)),
                "Trade Hint": row.get("Trade Hint", "-")
            }

    return {}

def append_wallet_history_point(
    wallet_address,
    short_wallet,
    old_score,
    old_swaps,
    old_transfers,
    old_volume,
    old_largest,
    new_score,
    new_swaps,
    new_transfers,
    new_volume,
    new_largest,
    score_change,
    swap_change,
    transfer_change,
    volume_change,
    largest_change,
    old_buys=0,
    old_sells=0,
    old_rotates=0,
    new_buys=0,
    new_sells=0,
    new_rotates=0,
    latest_trade_event=None
):
    key = wallet_history_key(wallet_address)

    if not key:
        return

    if "wallet_history" not in st.session_state:
        st.session_state.wallet_history = load_json_dict(WALLET_HISTORY_FILE)

    history = st.session_state.wallet_history.get(key, [])
    now = pd.Timestamp.now()
    latest_trade_event = latest_trade_event or {}

    buy_change = safe_int(new_buys) - safe_int(old_buys)
    sell_change = safe_int(new_sells) - safe_int(old_sells)
    rotate_change = safe_int(new_rotates) - safe_int(old_rotates)

    if not history:
        previous_time = (now - pd.Timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S")
        history.append({
            "Timestamp": previous_time,
            "Wallet": short_wallet,
            "Score": safe_int(old_score),
            "Swaps": safe_int(old_swaps),
            "Transfers": safe_int(old_transfers),
            "Buys": safe_int(old_buys),
            "Sells": safe_int(old_sells),
            "Rotates": safe_int(old_rotates),
            "USD Volume": safe_float(old_volume),
            "Largest Tx": safe_float(old_largest),
            "Score Change": 0,
            "Swaps Change": 0,
            "Transfers Change": 0,
            "Buys Change": 0,
            "Sells Change": 0,
            "Rotates Change": 0,
            "USD Volume Change": 0,
            "Largest Tx Change": 0,
            "Trade Side": "-",
            "Trade Token": "-",
            "Trade Token Mint": "",
            "Trade Amount": 0,
            "Trade Counter Token": "-",
            "Trade Counter Amount": 0,
            "Trade Hint": "previous baseline",
            "Note": "previous baseline"
        })

    history.append({
        "Timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
        "Wallet": short_wallet,
        "Score": safe_int(new_score),
        "Swaps": safe_int(new_swaps),
        "Transfers": safe_int(new_transfers),
        "Buys": safe_int(new_buys),
        "Sells": safe_int(new_sells),
        "Rotates": safe_int(new_rotates),
        "USD Volume": safe_float(new_volume),
        "Largest Tx": safe_float(new_largest),
        "Score Change": safe_int(score_change),
        "Swaps Change": safe_int(swap_change),
        "Transfers Change": safe_int(transfer_change),
        "Buys Change": safe_int(buy_change),
        "Sells Change": safe_int(sell_change),
        "Rotates Change": safe_int(rotate_change),
        "USD Volume Change": safe_float(volume_change),
        "Largest Tx Change": safe_float(largest_change),
        "Trade Side": latest_trade_event.get("Trade Side", "-"),
        "Trade Token": latest_trade_event.get("Trade Token", "-"),
        "Trade Token Mint": latest_trade_event.get("Trade Token Mint", ""),
        "Trade Amount": safe_float(latest_trade_event.get("Trade Amount", 0)),
        "Trade Counter Token": latest_trade_event.get("Trade Counter Token", "-"),
        "Trade Counter Amount": safe_float(latest_trade_event.get("Trade Counter Amount", 0)),
        "Trade Hint": latest_trade_event.get("Trade Hint", "-"),
        "Note": "recheck"
    })

    st.session_state.wallet_history[key] = history[-120:]
    save_json_dict(WALLET_HISTORY_FILE, st.session_state.wallet_history)

def wallet_history_dataframe(wallet_address):
    key = wallet_history_key(wallet_address)
    history = st.session_state.get("wallet_history", {}).get(key, [])

    if not history:
        return pd.DataFrame()

    df = pd.DataFrame(history)

    if df.empty:
        return df

    df["Time"] = pd.to_datetime(df.get("Timestamp"), errors="coerce")
    df = df.dropna(subset=["Time"]).sort_values("Time")

    numeric_columns = [
        "Score", "Swaps", "Transfers", "Buys", "Sells", "Rotates", "USD Volume", "Largest Tx",
        "Score Change", "Swaps Change", "Transfers Change", "Buys Change", "Sells Change", "Rotates Change",
        "USD Volume Change", "Largest Tx Change", "Trade Amount", "Trade Counter Amount"
    ]

    for column in numeric_columns:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce").fillna(0)

    return df



def save_wallet_history_state(message="Wallet chart history updated."):
    if "wallet_history" not in st.session_state:
        st.session_state.wallet_history = {}
    save_json_dict(WALLET_HISTORY_FILE, st.session_state.wallet_history)
    st.session_state.watchlist_message = message


def clear_wallet_history_for_wallet(wallet_address):
    key = wallet_history_key(wallet_address)
    if not key:
        st.session_state.watchlist_message = "No wallet address found for chart reset."
        return

    if "wallet_history" not in st.session_state:
        st.session_state.wallet_history = load_json_dict(WALLET_HISTORY_FILE)

    if key in st.session_state.wallet_history:
        st.session_state.wallet_history.pop(key, None)
        save_wallet_history_state("Chart history cleared for this wallet. Run Check or Auto Scan to build a fresh chart.")
    else:
        st.session_state.watchlist_message = "This wallet has no chart history yet."


def clear_all_wallet_history():
    st.session_state.wallet_history = {}
    save_wallet_history_state("All wallet chart history cleared. Watchlist, pins and tokens were kept.")


def clear_unpinned_wallet_history():
    if "wallet_history" not in st.session_state:
        st.session_state.wallet_history = load_json_dict(WALLET_HISTORY_FILE)

    pinned_keys = {
        wallet_history_key(item.get("Full Wallet", item.get("Wallet", "")))
        for item in st.session_state.get("watchlist_wallets", [])
        if wallet_is_pinned(item)
    }
    pinned_keys = {key for key in pinned_keys if key}

    st.session_state.wallet_history = {
        key: value
        for key, value in st.session_state.get("wallet_history", {}).items()
        if key in pinned_keys
    }
    save_wallet_history_state("Unpinned wallet chart history cleared. Pinned wallet charts were kept.")


def clear_unclear_swap_history_points():
    if "wallet_history" not in st.session_state:
        st.session_state.wallet_history = load_json_dict(WALLET_HISTORY_FILE)

    cleaned_history = {}
    removed = 0

    for wallet_key, points in st.session_state.get("wallet_history", {}).items():
        kept_points = []
        for point in points:
            side = str(point.get("Trade Side", "-")).upper()
            note = str(point.get("Note", ""))
            is_baseline = note == "previous baseline"
            has_clear_action = side in ["BUY", "SELL", "ROTATE"]
            is_unclear_swap = side == "SWAP"

            if is_baseline or has_clear_action or not is_unclear_swap:
                kept_points.append(point)
            else:
                removed += 1

        if kept_points:
            cleaned_history[wallet_key] = kept_points[-120:]

    st.session_state.wallet_history = cleaned_history
    save_wallet_history_state(f"Removed {removed} unclear SWAP-only chart point(s). Clear BUY/SELL/ROTATE data was kept.")


def wallet_history_point_count(wallet_address=None):
    history = st.session_state.get("wallet_history", {})
    if wallet_address:
        return len(history.get(wallet_history_key(wallet_address), []))
    return sum(len(points) for points in history.values())


def wallet_story_from_history(history_df, item):
    if history_df is None or history_df.empty or len(history_df) < 2:
        return "Not enough history yet. Run Check or Auto Update a few times so the wallet can build a visible story."

    last = history_df.iloc[-1]
    previous = history_df.iloc[-2]
    volume_change = safe_float(last.get("USD Volume Change", safe_float(last.get("USD Volume", 0)) - safe_float(previous.get("USD Volume", 0))))
    swap_change = safe_int(last.get("Swaps Change", safe_int(last.get("Swaps", 0)) - safe_int(previous.get("Swaps", 0))))
    largest_change = safe_float(last.get("Largest Tx Change", safe_float(last.get("Largest Tx", 0)) - safe_float(previous.get("Largest Tx", 0))))
    buy_change = safe_int(last.get("Buys Change", 0))
    sell_change = safe_int(last.get("Sells Change", 0))
    trade_side = str(last.get("Trade Side", "-")).upper()
    trade_token = last.get("Trade Token", "-")
    trade_hint = last.get("Trade Hint", "-")

    strongest_volume = safe_float(history_df["USD Volume Change"].max()) if "USD Volume Change" in history_df else 0
    strongest_swap = safe_int(history_df["Swaps Change"].max()) if "Swaps Change" in history_df else 0
    total_buys = safe_int(history_df["Buys Change"].clip(lower=0).sum()) if "Buys Change" in history_df else 0
    total_sells = safe_int(history_df["Sells Change"].clip(lower=0).sum()) if "Sells Change" in history_df else 0

    if trade_side == "BUY" and volume_change >= 100:
        return f"Buy story: latest detected action looks like a BUY of {trade_token}. Volume also jumped by {format_signed_usd(volume_change)}. This is worth checking quickly."

    if trade_side == "SELL":
        return f"Sell story: latest detected action looks like a SELL of {trade_token}. Check whether it happened after a volume spike or near the local peak."

    if buy_change > 0 and sell_change > 0:
        return f"Trading story: both buys and sells appeared in the latest window. This wallet may be actively rotating, not just holding."

    if total_buys > 0 and total_sells == 0:
        return f"Accumulation story: buys have appeared but no clear sells yet. Watch whether volume keeps rising or starts cooling."

    if total_sells > 0 and total_buys > 0:
        return f"Exit behavior visible: this wallet has both buy and sell markers. Use the Trade Behavior chart to see whether sells follow spikes."

    if volume_change >= 250 and swap_change > 0:
        return f"Strong story: new swaps came together with a volume spike ({format_signed_usd(volume_change)}). This is worth opening first."

    if volume_change >= 100:
        return f"Volume story: the latest check added {format_signed_usd(volume_change)}. Compare it with buy/sell markers below."

    if swap_change > 0:
        return f"Activity story: swaps increased by {format_signed_number(swap_change)}. Use Analyze Token if a token is detected."

    if largest_change >= 100:
        return f"Single-transaction story: largest transaction jumped by {format_signed_usd(largest_change)}. Check if this was one meaningful move."

    if safe_float(item.get("USD Volume Change", 0)) < -25:
        return "Cooling story: current visible activity is lower than the previous snapshot. Lower priority unless it wakes up again."

    if strongest_volume >= 250 or strongest_swap > 0:
        return "History still matters: the latest check is calm, but earlier spikes are visible in the chart."

    return "Quiet story: no meaningful spike yet. Keep it collapsed until Auto Update finds new movement."

def wallet_chart_range_dataframe(history_df, range_label):
    if history_df is None or history_df.empty:
        return history_df

    df = history_df.copy().sort_values("Time")

    if range_label == "Last 6 checks":
        return df.tail(6)

    if range_label == "Last 12 checks":
        return df.tail(12)

    if range_label == "Last 24 checks":
        return df.tail(24)

    if range_label == "All":
        return df

    return df.tail(12)


def render_story_chart_block(chart_df, value_column, change_column, title, value_label, bar_label):
    if chart_df is None or chart_df.empty or value_column not in chart_df.columns:
        st.info("Not enough chart data yet.")
        return

    plot_df = chart_df.copy()
    plot_df["Time Label"] = plot_df["Time"].dt.strftime("%H:%M")
    plot_df["Value"] = pd.to_numeric(plot_df[value_column], errors="coerce").fillna(0)
    plot_df["Change"] = pd.to_numeric(plot_df.get(change_column, 0), errors="coerce").fillna(0)

    chart_data = plot_df[["Time Label", "Value", "Change"]].to_dict("records")

    chart_spec = {
        "background": "#202124",
        "height": 260,
        "data": {"values": chart_data},
        "layer": [
            {
                "mark": {"type": "bar", "cornerRadiusTopLeft": 4, "cornerRadiusTopRight": 4, "opacity": 0.55},
                "encoding": {
                    "x": {"field": "Time Label", "type": "ordinal", "axis": {"labelColor": "#9ca3af", "title": None, "labelAngle": 0}},
                    "y": {"field": "Change", "type": "quantitative", "axis": {"labelColor": "#9ca3af", "title": bar_label, "gridColor": "rgba(255,255,255,0.07)"}},
                    "color": {
                        "condition": [
                            {"test": "datum.Change > 0", "value": "#4ade80"},
                            {"test": "datum.Change < 0", "value": "#f87171"}
                        ],
                        "value": "#6b7280"
                    },
                    "tooltip": [
                        {"field": "Time Label", "title": "Time"},
                        {"field": "Change", "title": bar_label, "format": ",.2f"},
                        {"field": "Value", "title": value_label, "format": ",.2f"}
                    ]
                }
            },
            {
                "mark": {"type": "line", "strokeWidth": 3, "point": {"filled": True, "size": 55}},
                "encoding": {
                    "x": {"field": "Time Label", "type": "ordinal"},
                    "y": {"field": "Value", "type": "quantitative", "axis": {"labelColor": "#9ca3af", "title": value_label}},
                    "color": {"value": "#a78bfa"},
                    "tooltip": [
                        {"field": "Time Label", "title": "Time"},
                        {"field": "Value", "title": value_label, "format": ",.2f"},
                        {"field": "Change", "title": bar_label, "format": ",.2f"}
                    ]
                }
            }
        ],
        "resolve": {"scale": {"y": "independent"}},
        "config": {
            "view": {"stroke": "transparent"},
            "axis": {
                "domainColor": "rgba(255,255,255,0.08)",
                "tickColor": "rgba(255,255,255,0.08)",
                "labelFont": "Inter, system-ui, sans-serif",
                "titleFont": "Inter, system-ui, sans-serif",
                "titleColor": "#9ca3af"
            }
        }
    }

    st.markdown(f"**{title}**")
    st.vega_lite_chart(chart_spec, width='stretch')



def render_trade_behavior_chart(chart_df):
    if chart_df is None or chart_df.empty:
        st.info("Not enough trade behavior data yet.")
        return

    st.markdown(
        """
        <style>
        .trade-quick-help {
            background: linear-gradient(135deg, rgba(15, 118, 110, 0.20), rgba(34, 197, 94, 0.08));
            border: 1px solid rgba(45, 212, 191, 0.25);
            color: #d1fae5;
            border-radius: 16px;
            padding: 12px 15px;
            margin: 6px 0 12px 0;
            font-size: 13px;
            line-height: 1.45;
        }
        .trade-hero-grid {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 10px;
            margin: 10px 0 12px 0;
        }
        .trade-hero-card {
            background: rgba(255,255,255,0.035);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 15px;
            padding: 12px 14px;
            min-height: 72px;
        }
        .trade-hero-card span {
            display: block;
            color: #94a3b8;
            font-size: 11px;
            margin-bottom: 6px;
        }
        .trade-hero-card b {
            color: #f8fafc;
            font-size: 15px;
            line-height: 1.25;
        }
        .trade-hero-card b.buy { color: #4ade80; }
        .trade-hero-card b.sell { color: #f87171; }
        .trade-hero-card b.swap { color: #7dd3fc; }
        .trade-hero-card b.rotate { color: #fbbf24; }
        .simple-legend {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 8px;
            margin: 8px 0 12px 0;
        }
        .simple-legend div {
            border: 1px solid rgba(255,255,255,0.08);
            background: rgba(255,255,255,0.035);
            border-radius: 13px;
            padding: 9px 10px;
            font-size: 12px;
            color: #cbd5e1;
        }
        .simple-legend b { color: #f8fafc; }
        .legend-dot {
            width: 10px;
            height: 10px;
            border-radius: 50%;
            display: inline-block;
            margin-right: 6px;
            vertical-align: -1px;
        }
        .legend-buy { background: #22c55e; }
        .legend-sell { background: #ef4444; }
        .legend-swap { background: #38bdf8; }
        .legend-rotate { background: #f59e0b; border-radius: 3px; }
        .trade-section-title {
            font-size: 14px;
            font-weight: 850;
            color: #f8fafc;
            margin-top: 16px;
            margin-bottom: 6px;
        }
        .trade-event-strip {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-top: 8px;
            margin-bottom: 8px;
        }
        .trade-chip {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 8px 10px;
            border-radius: 999px;
            font-size: 12px;
            border: 1px solid rgba(255,255,255,0.08);
            background: rgba(255,255,255,0.04);
            color: #e5e7eb;
        }
        .trade-chip .dot {
            width: 9px;
            height: 9px;
            border-radius: 50%;
            display: inline-block;
        }
        .trade-chip-buy { border-color: rgba(34, 197, 94, 0.32); background: rgba(34, 197, 94, 0.11); }
        .trade-chip-buy .dot { background: #22c55e; }
        .trade-chip-sell { border-color: rgba(239, 68, 68, 0.32); background: rgba(239, 68, 68, 0.11); }
        .trade-chip-sell .dot { background: #ef4444; }
        .trade-chip-swap { border-color: rgba(56, 189, 248, 0.32); background: rgba(56, 189, 248, 0.11); }
        .trade-chip-swap .dot { background: #38bdf8; }
        .trade-chip-rotate { border-color: rgba(245, 158, 11, 0.32); background: rgba(245, 158, 11, 0.11); }
        .trade-chip-rotate .dot { background: #f59e0b; border-radius: 3px; }
        .pnl-note {
            color: #94a3b8;
            font-size: 12px;
            margin: 6px 0 8px 0;
            line-height: 1.45;
        }
        .pnl-good { color: #4ade80 !important; font-weight: 850; }
        .pnl-bad { color: #f87171 !important; font-weight: 850; }
        .pnl-neutral { color: #cbd5e1 !important; font-weight: 850; }
        .beginner-alert {
            border-radius: 14px;
            padding: 11px 13px;
            margin: 10px 0;
            background: rgba(56, 189, 248, 0.10);
            border: 1px solid rgba(56, 189, 248, 0.25);
            color: #bae6fd;
            font-size: 13px;
        }
        .beginner-alert.good {
            background: rgba(34, 197, 94, 0.10);
            border-color: rgba(34, 197, 94, 0.25);
            color: #bbf7d0;
        }
        .beginner-alert.warn {
            background: rgba(245, 158, 11, 0.10);
            border-color: rgba(245, 158, 11, 0.25);
            color: #fde68a;
        }
        @media (max-width: 900px) {
            .trade-hero-grid, .simple-legend { grid-template-columns: repeat(2, minmax(0, 1fr)); }
        }
        </style>
        """,
        unsafe_allow_html=True
    )

    plot_df = chart_df.copy().sort_values("Time")
    plot_df["Time Label"] = plot_df["Time"].dt.strftime("%H:%M")

    def ensure_numeric_column(df, column, default=0):
        if column not in df.columns:
            df[column] = default
        df[column] = pd.to_numeric(df[column], errors="coerce").fillna(default)

    def ensure_text_column(df, column, default="-"):
        if column not in df.columns:
            df[column] = default
        df[column] = df[column].fillna(default).astype(str)

    for column in [
        "USD Volume Change", "Largest Tx", "Swaps Change", "Buys Change", "Sells Change", "Rotates Change",
        "Trade Amount", "Trade Counter Amount"
    ]:
        ensure_numeric_column(plot_df, column, 0)

    for column in ["Trade Side", "Trade Token", "Trade Counter Token", "Trade Hint"]:
        ensure_text_column(plot_df, column, "-")

    plot_df["Trade Side"] = plot_df["Trade Side"].str.upper()
    plot_df["Volume Change"] = plot_df["USD Volume Change"]

    marker_rows = []
    for _, row in plot_df.iterrows():
        side = str(row.get("Trade Side", "-")).upper()
        swaps_change = safe_int(row.get("Swaps Change", 0))
        volume_change = safe_float(row.get("Volume Change", 0))
        token = str(row.get("Trade Token", "-") or "-")
        counter_token = str(row.get("Trade Counter Token", "-") or "-")
        hint = str(row.get("Trade Hint", "-") or "-")

        if side in ["BUY", "SELL", "ROTATE", "SWAP"]:
            action = side
        elif swaps_change > 0:
            action = "SWAP"
            hint = "Swap detected, direction not clear yet"
        else:
            continue

        if action == "BUY":
            lane = "BUY / SWAP IN"
            text_label = "BUY"
            read = "wallet likely swapped SOL/stable into this token"
            chart_size = 260
        elif action == "SELL":
            lane = "SELL / SWAP OUT"
            text_label = "SELL"
            read = "wallet likely swapped token back into SOL/stable"
            chart_size = 260
        elif action == "ROTATE":
            lane = "ROTATE"
            text_label = "ROT"
            read = "wallet likely rotated from one token into another"
            chart_size = 220
        else:
            lane = "SWAP"
            text_label = ""  # no label spam for unclear swaps
            read = "swap happened, but direction is still unclear"
            chart_size = 75

        if action in ["BUY", "SELL", "ROTATE"]:
            chart_size = min(max(abs(volume_change) / 2, chart_size), 760)

        marker_rows.append({
            "Time Label": row.get("Time Label", "-"),
            "Action": action,
            "Lane": lane,
            "Text Label": text_label,
            "Trade Token": token,
            "Counter Token": counter_token,
            "Trade Hint": hint,
            "Read": read,
            "Volume Change": volume_change,
            "Swaps Change": swaps_change,
            "Largest Tx": safe_float(row.get("Largest Tx", 0)),
            "Trade Amount": safe_float(row.get("Trade Amount", 0)),
            "Trade Counter Amount": safe_float(row.get("Trade Counter Amount", 0)),
            "Marker Size": chart_size
        })

    marker_df = pd.DataFrame(marker_rows)
    if not marker_df.empty:
        marker_df = marker_df.reset_index(drop=True)

    clear_marker_df = marker_df[marker_df["Action"].isin(["BUY", "SELL", "ROTATE"])] if not marker_df.empty else pd.DataFrame()
    swap_marker_df = marker_df[marker_df["Action"] == "SWAP"] if not marker_df.empty else pd.DataFrame()

    buy_markers = marker_df[marker_df["Action"] == "BUY"].copy() if not marker_df.empty else pd.DataFrame()
    sell_markers = marker_df[marker_df["Action"] == "SELL"].copy() if not marker_df.empty else pd.DataFrame()
    rotate_markers = marker_df[marker_df["Action"] == "ROTATE"].copy() if not marker_df.empty else pd.DataFrame()

    buy_count = len(buy_markers)
    sell_count = len(sell_markers)
    swap_count = len(swap_marker_df)
    rotate_count = len(rotate_markers)

    def latest_marker_summary(df):
        if df is None or df.empty:
            return "None yet"
        row = df.iloc[-1]
        token = str(row.get("Trade Token", "-") or "-")
        token = token if len(token) <= 13 else token[:6] + "…" + token[-4:]
        action = str(row.get("Action", "-")).upper()
        return f"{row.get('Time Label', '-')} · {action} · {token}"

    def strongest_marker(df):
        if df is None or df.empty or "Volume Change" not in df.columns:
            return "None yet"
        clean_df = df.copy().reset_index(drop=True)
        clean_df["Volume Change"] = pd.to_numeric(clean_df["Volume Change"], errors="coerce").fillna(0)
        if clean_df.empty:
            return "None yet"
        row = clean_df.loc[clean_df["Volume Change"].abs().idxmax()]
        token = str(row.get("Trade Token", "-") or "-")
        token = token if len(token) <= 10 else token[:6] + "…" + token[-4:]
        return f"{row.get('Time Label', '-')} · {token} · {format_signed_usd(row.get('Volume Change', 0))}"

    if buy_count and sell_count:
        quick_read = "Buy/Sell pattern visible"
        quick_class = "buy"
        alert_class = "good"
        alert_text = "This range has both buy and sell markers. Use the P/L table below to judge if exits happened after entries."
    elif buy_count:
        quick_read = "Accumulating / buying"
        quick_class = "buy"
        alert_class = "good"
        alert_text = "Buy markers appeared, but no clear sell yet. This can mean open positions or missing exit data."
    elif sell_count:
        quick_read = "Selling / exiting"
        quick_class = "sell"
        alert_class = "warn"
        alert_text = "Sell markers appeared without a matching buy in this selected range. Try a longer range to see the entry."
    elif rotate_count:
        quick_read = "Rotating tokens"
        quick_class = "rotate"
        alert_class = "warn"
        alert_text = "The wallet is rotating between tokens. This can be useful, but needs token-level follow-up."
    elif swap_count:
        quick_read = "Swaps visible, direction unclear"
        quick_class = "swap"
        alert_class = "warn"
        alert_text = "The wallet is active, but most events are still unclear swaps. New scans should classify more of them as swap-in or swap-out."
    else:
        quick_read = "No clear trade pattern yet"
        quick_class = ""
        alert_class = ""
        alert_text = "No useful trading events in this range yet. Keep Auto Scan on or choose a longer range."

    st.markdown("**Trade behavior story**")
    st.markdown(
        (
            '<div class="trade-quick-help">'
            '<b>Simple read:</b> this section translates Solana swaps into human behavior. '
            '<b>BUY</b> means the wallet swapped SOL/USDC/USDT into a memecoin. '
            '<b>SELL</b> means the wallet swapped the memecoin back into SOL/USDC/USDT. '
            '<b>ROTATE</b> means token A into token B. Blue SWAP means direction is still unclear.'
            '</div>'
        ),
        unsafe_allow_html=True
    )

    st.markdown(
        f"""
        <div class="trade-hero-grid">
            <div class="trade-hero-card"><span>Latest clear action</span><b>{latest_marker_summary(clear_marker_df)}</b></div>
            <div class="trade-hero-card"><span>Strongest buy / swap in</span><b class="buy">{strongest_marker(buy_markers)}</b></div>
            <div class="trade-hero-card"><span>Strongest sell / swap out</span><b class="sell">{strongest_marker(sell_markers)}</b></div>
            <div class="trade-hero-card"><span>Quick read</span><b class="{quick_class}">{quick_read}</b></div>
        </div>
        <div class="beginner-alert {alert_class}">{alert_text}</div>
        """,
        unsafe_allow_html=True
    )

    st.markdown(
        """
        <div class="simple-legend">
            <div><span class="legend-dot legend-buy"></span><b>BUY / SWAP IN</b><br>SOL or stable went out, memecoin came in</div>
            <div><span class="legend-dot legend-sell"></span><b>SELL / SWAP OUT</b><br>Memecoin went out, SOL or stable came in</div>
            <div><span class="legend-dot legend-swap"></span><b>SWAP unclear</b><br>Swap visible, direction not safe yet</div>
            <div><span class="legend-dot legend-rotate"></span><b>ROTATE</b><br>Wallet moved from one token into another</div>
        </div>
        """,
        unsafe_allow_html=True
    )

    # Less clutter: clear BUY/SELL/ROTATE events are large and labelled. Unclear SWAPs stay small and unlabeled.
    marker_values = marker_df.to_dict("records") if not marker_df.empty else []
    if marker_values:
        action_chart = {
            "background": "#202124",
            "height": 230,
            "data": {"values": marker_values},
            "layer": [
                {
                    "mark": {"type": "point", "filled": True, "stroke": "#020617", "strokeWidth": 2.1, "opacity": 0.92},
                    "encoding": {
                        "x": {"field": "Time Label", "type": "ordinal", "axis": {"labelColor": "#9ca3af", "title": None, "labelAngle": 0}},
                        "y": {
                            "field": "Lane",
                            "type": "nominal",
                            "sort": ["BUY / SWAP IN", "SWAP", "ROTATE", "SELL / SWAP OUT"],
                            "axis": {"labelColor": "#e5e7eb", "title": None}
                        },
                        "size": {"field": "Marker Size", "type": "quantitative", "legend": None},
                        "shape": {
                            "field": "Action",
                            "type": "nominal",
                            "scale": {"domain": ["BUY", "SELL", "SWAP", "ROTATE"], "range": ["circle", "circle", "circle", "diamond"]},
                            "legend": None
                        },
                        "color": {
                            "field": "Action",
                            "type": "nominal",
                            "scale": {"domain": ["BUY", "SELL", "SWAP", "ROTATE"], "range": ["#22c55e", "#ef4444", "#38bdf8", "#f59e0b"]},
                            "legend": {"labelColor": "#e5e7eb", "titleColor": "#9ca3af", "orient": "top-right", "title": "Action"}
                        },
                        "tooltip": [
                            {"field": "Time Label", "title": "Time"},
                            {"field": "Action", "title": "Action"},
                            {"field": "Trade Token", "title": "Token"},
                            {"field": "Counter Token", "title": "Counter token"},
                            {"field": "Volume Change", "title": "Volume change", "format": ",.2f"},
                            {"field": "Swaps Change", "title": "New swaps"},
                            {"field": "Read", "title": "Meaning"},
                            {"field": "Trade Hint", "title": "Hint"}
                        ]
                    }
                },
                {
                    "transform": [{"filter": "datum.Action != 'SWAP'"}],
                    "mark": {"type": "text", "dy": -18, "fontSize": 12, "fontWeight": "bold"},
                    "encoding": {
                        "x": {"field": "Time Label", "type": "ordinal"},
                        "y": {"field": "Lane", "type": "nominal", "sort": ["BUY / SWAP IN", "SWAP", "ROTATE", "SELL / SWAP OUT"]},
                        "text": {"field": "Text Label"},
                        "color": {
                            "field": "Action",
                            "type": "nominal",
                            "scale": {"domain": ["BUY", "SELL", "ROTATE"], "range": ["#bbf7d0", "#fecaca", "#fde68a"]},
                            "legend": None
                        }
                    }
                }
            ],
            "config": {
                "view": {"stroke": "transparent"},
                "axis": {
                    "domainColor": "rgba(255,255,255,0.08)",
                    "tickColor": "rgba(255,255,255,0.08)",
                    "gridColor": "rgba(255,255,255,0.05)",
                    "labelFont": "Inter, system-ui, sans-serif",
                    "titleFont": "Inter, system-ui, sans-serif"
                }
            }
        }
        st.vega_lite_chart(action_chart, width="stretch")
    else:
        st.info("No buy/sell/swap markers yet. Keep Auto Update running. The chart will become useful once swaps are detected.")

    # Timeline before volume chart: beginners read the chips faster than the chart.
    if not marker_df.empty:
        recent_marker_rows = marker_df.tail(12)
        chips = []
        for _, row in recent_marker_rows.iterrows():
            action = str(row.get("Action", "-")).upper()
            cls = "trade-chip-buy" if action == "BUY" else "trade-chip-sell" if action == "SELL" else "trade-chip-swap" if action == "SWAP" else "trade-chip-rotate"
            token = str(row.get("Trade Token", "-") or "-")
            token = token if len(token) <= 10 else token[:6] + "…" + token[-4:]
            chips.append(
                f'<span class="trade-chip {cls}"><span class="dot"></span><b>{row.get("Time Label", "-")}</b> {action} · {token} · {format_signed_usd(row.get("Volume Change", 0))}</span>'
            )
        st.markdown('<div class="trade-section-title">Readable action timeline</div>', unsafe_allow_html=True)
        st.markdown('<div class="trade-event-strip">' + ''.join(chips) + '</div>', unsafe_allow_html=True)

    st.markdown('<div class="trade-section-title">Estimated Profit / Loss by token</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="pnl-note"><b>How to read it:</b> P/L appears when the selected range contains clear BUY/SWAP IN or SELL/SWAP OUT events. Blue SWAP-only activity is shown as activity, but not trusted for P/L. This is an estimate from parsed USD movement, not accounting-grade PnL.</div>',
        unsafe_allow_html=True
    )

    pnl_rows = []
    if not marker_df.empty:
        pnl_source = marker_df[marker_df["Action"].isin(["BUY", "SELL"])].copy()
        if not pnl_source.empty:
            grouped = {}
            for _, row in pnl_source.iterrows():
                token = str(row.get("Trade Token", "-") or "-")
                if not token or token == "-":
                    token = "Unknown token"
                display_token = token[:6] + "..." + token[-6:] if len(token) > 18 else token

                if token not in grouped:
                    grouped[token] = {
                        "Token": display_token,
                        "Buys": 0,
                        "Sells": 0,
                        "Buy Value": 0.0,
                        "Sell Value": 0.0,
                        "First Buy": "-",
                        "Last Sell": "-"
                    }

                usd_value = abs(safe_float(row.get("Volume Change", 0)))
                if usd_value <= 0:
                    usd_value = abs(safe_float(row.get("Trade Counter Amount", 0)))
                if usd_value <= 0:
                    usd_value = abs(safe_float(row.get("Trade Amount", 0)))

                action = str(row.get("Action", "-")).upper()
                if action == "BUY":
                    grouped[token]["Buys"] += 1
                    grouped[token]["Buy Value"] += usd_value
                    if grouped[token]["First Buy"] == "-":
                        grouped[token]["First Buy"] = row.get("Time Label", "-")
                elif action == "SELL":
                    grouped[token]["Sells"] += 1
                    grouped[token]["Sell Value"] += usd_value
                    grouped[token]["Last Sell"] = row.get("Time Label", "-")

            for grouped_item in grouped.values():
                pnl_value = grouped_item["Sell Value"] - grouped_item["Buy Value"]
                open_value = max(grouped_item["Buy Value"] - grouped_item["Sell Value"], 0)
                if grouped_item["Buys"] > 0 and grouped_item["Sells"] == 0:
                    status = "Open / accumulating"
                    read = "buy seen, no sell in this range"
                elif grouped_item["Sells"] > 0 and grouped_item["Buys"] == 0:
                    status = "Exit only seen"
                    read = "sell seen, entry may be outside range"
                elif pnl_value > 0:
                    status = "Closed positive"
                    read = "sold more value than bought in this range"
                elif pnl_value < 0:
                    status = "Negative or still holding"
                    read = "buy value higher than sell value in this range"
                else:
                    status = "Flat"
                    read = "balanced in this range"

                pnl_rows.append({
                    "Token": grouped_item["Token"],
                    "Buys": grouped_item["Buys"],
                    "Sells": grouped_item["Sells"],
                    "Buy Value": format_usd(grouped_item["Buy Value"]),
                    "Sell Value": format_usd(grouped_item["Sell Value"]),
                    "Est. P/L": format_signed_usd(pnl_value),
                    "Open Value Est.": format_usd(open_value),
                    "First Buy": grouped_item["First Buy"],
                    "Last Sell": grouped_item["Last Sell"],
                    "Status": status,
                    "Read": read
                })

    if pnl_rows:
        pnl_df = pd.DataFrame(pnl_rows)
        st.dataframe(pnl_df, width="stretch", hide_index=True)
    else:
        unclear_count = len(swap_marker_df)
        if unclear_count > 0:
            st.info(f"No estimated P/L yet. This range has {unclear_count} blue SWAP marker(s), but no trusted BUY/SELL marker. Let new Auto Scans run or select a range with green BUY and red SELL markers.")
        else:
            st.info("No estimated P/L yet. You need at least one detected BUY/SWAP IN or SELL/SWAP OUT marker for a token.")

    st.markdown('<div class="trade-section-title">Volume around those actions</div>', unsafe_allow_html=True)
    volume_values = plot_df[["Time Label", "Volume Change", "Largest Tx", "Swaps Change"]].to_dict("records")
    volume_chart = {
        "background": "#202124",
        "height": 150,
        "data": {"values": volume_values},
        "layer": [
            {
                "mark": {"type": "bar", "cornerRadiusTopLeft": 4, "cornerRadiusTopRight": 4, "opacity": 0.70},
                "encoding": {
                    "x": {"field": "Time Label", "type": "ordinal", "axis": {"labelColor": "#9ca3af", "title": None, "labelAngle": 0}},
                    "y": {"field": "Volume Change", "type": "quantitative", "axis": {"labelColor": "#9ca3af", "title": "Volume change", "gridColor": "rgba(255,255,255,0.07)"}},
                    "color": {
                        "condition": [
                            {"test": "datum['Volume Change'] > 0", "value": "#22c55e"},
                            {"test": "datum['Volume Change'] < 0", "value": "#ef4444"}
                        ],
                        "value": "#64748b"
                    },
                    "tooltip": [
                        {"field": "Time Label", "title": "Time"},
                        {"field": "Volume Change", "title": "Volume change", "format": ",.2f"},
                        {"field": "Largest Tx", "title": "Largest tx", "format": ",.2f"},
                        {"field": "Swaps Change", "title": "New swaps"}
                    ]
                }
            }
        ],
        "config": {
            "view": {"stroke": "transparent"},
            "axis": {
                "domainColor": "rgba(255,255,255,0.08)",
                "tickColor": "rgba(255,255,255,0.08)",
                "labelFont": "Inter, system-ui, sans-serif",
                "titleFont": "Inter, system-ui, sans-serif",
                "titleColor": "#9ca3af"
            }
        }
    }
    st.vega_lite_chart(volume_chart, width="stretch")

    with st.expander("Advanced: largest transaction line", expanded=False):
        advanced_values = plot_df[["Time Label", "Largest Tx", "Volume Change", "Swaps Change"]].to_dict("records")
        advanced_chart = {
            "background": "#202124",
            "height": 180,
            "data": {"values": advanced_values},
            "layer": [
                {
                    "mark": {"type": "line", "strokeWidth": 2.5, "point": {"filled": True, "size": 45}, "color": "#a78bfa"},
                    "encoding": {
                        "x": {"field": "Time Label", "type": "ordinal", "axis": {"labelColor": "#9ca3af", "title": None, "labelAngle": 0}},
                        "y": {"field": "Largest Tx", "type": "quantitative", "axis": {"labelColor": "#9ca3af", "title": "Largest tx", "gridColor": "rgba(255,255,255,0.07)"}},
                        "tooltip": [
                            {"field": "Time Label", "title": "Time"},
                            {"field": "Largest Tx", "title": "Largest tx", "format": ",.2f"},
                            {"field": "Volume Change", "title": "Volume change", "format": ",.2f"},
                            {"field": "Swaps Change", "title": "New swaps"}
                        ]
                    }
                }
            ],
            "config": {"view": {"stroke": "transparent"}}
        }
        st.vega_lite_chart(advanced_chart, width="stretch")

def render_wallet_history_chart(wallet_address, item):
    history_df = wallet_history_dataframe(wallet_address)

    if history_df.empty or len(history_df) < 2:
        st.info("No chart yet. Pin this wallet and keep Auto Update on. The chart builds from saved checks.")
        return

    story = wallet_story_from_history(history_df, item)
    status, status_class, status_hint = wallet_movement_status(item)

    latest = history_df.iloc[-1]
    previous = history_df.iloc[-2]
    best_volume_spike = safe_float(history_df["USD Volume Change"].max()) if "USD Volume Change" in history_df else 0
    best_largest_spike = safe_float(history_df["Largest Tx Change"].max()) if "Largest Tx Change" in history_df else 0
    best_swap_spike = safe_int(history_df["Swaps Change"].max()) if "Swaps Change" in history_df else 0
    total_buys = int(history_df.get("Buys Change", pd.Series(dtype=float)).clip(lower=0).sum()) if "Buys Change" in history_df else 0
    total_sells = int(history_df.get("Sells Change", pd.Series(dtype=float)).clip(lower=0).sum()) if "Sells Change" in history_df else 0

    story_class = "story-good" if status in ["HOT", "VOLUME SPIKE", "NEW SWAPS"] else "story-warn" if status == "COOLING" else "story-neutral"
    st.markdown(
        f"""<div class="wallet-story-box {story_class}">
            <div class="wallet-story-title">Wallet story</div>
            <div class="wallet-story-text">{story}</div>
        </div>""",
        unsafe_allow_html=True
    )

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Checks", len(history_df))
    c2.metric("Current Volume", format_usd(latest.get("USD Volume", 0)))
    c3.metric("Biggest Spike", format_signed_usd(best_volume_spike))
    c4.metric("Buys / Sells", f"{total_buys} / {total_sells}")
    c5.metric("Biggest Swap Spike", format_signed_number(best_swap_spike))

    chart_range_col, chart_type_col = st.columns([0.28, 0.72])
    with chart_range_col:
        chart_range = st.selectbox(
            "Range",
            ["Last 6 checks", "Last 12 checks", "Last 24 checks", "All"],
            index=1,
            key=f"wallet_chart_range_{wallet_address}"
        )
    with chart_type_col:
        chart_type = st.radio(
            "Chart",
            ["Trade Behavior", "Volume", "Swaps", "Score", "Largest Tx"],
            horizontal=True,
            key=f"wallet_chart_type_{wallet_address}"
        )

    chart_df = wallet_chart_range_dataframe(history_df, chart_range)

    if chart_type == "Trade Behavior":
        render_trade_behavior_chart(chart_df)
    elif chart_type == "Volume":
        render_story_chart_block(chart_df, "USD Volume", "USD Volume Change", "Volume story", "Total USD volume", "Volume change")
    elif chart_type == "Swaps":
        render_story_chart_block(chart_df, "Swaps", "Swaps Change", "Swap activity story", "Total swaps", "New swaps")
    elif chart_type == "Score":
        render_story_chart_block(chart_df, "Score", "Score Change", "Score story", "Wallet score", "Score change")
    else:
        render_story_chart_block(chart_df, "Largest Tx", "Largest Tx Change", "Largest transaction story", "Largest tx", "Largest tx change")

    with st.expander("Show raw chart data", expanded=False):
        compact_history = chart_df.tail(12).copy()
        compact_history["Time"] = compact_history["Time"].dt.strftime("%Y-%m-%d %H:%M:%S")
        if "USD Volume" in compact_history:
            compact_history["USD Volume"] = compact_history["USD Volume"].apply(format_usd)
        if "Largest Tx" in compact_history:
            compact_history["Largest Tx"] = compact_history["Largest Tx"].apply(format_usd)
        if "USD Volume Change" in compact_history:
            compact_history["USD Volume Change"] = compact_history["USD Volume Change"].apply(format_signed_usd)
        if "Largest Tx Change" in compact_history:
            compact_history["Largest Tx Change"] = compact_history["Largest Tx Change"].apply(format_signed_usd)
        show_cols = [
            "Time", "Trade Side", "Trade Token", "Trade Hint",
            "Score", "Swaps", "Transfers", "Buys", "Sells",
            "USD Volume", "Largest Tx", "Score Change", "Swaps Change", "Transfers Change",
            "Buys Change", "Sells Change", "USD Volume Change", "Largest Tx Change"
        ]
        st.dataframe(compact_history[[col for col in show_cols if col in compact_history.columns]], width='stretch', hide_index=True)

def wallet_movement_values(item):
    score_change = safe_int(item.get("Score Change", 0))
    swaps_change = safe_int(item.get("Swaps Change", 0))
    transfers_change = safe_int(item.get("Transfers Change", 0))
    volume_change = safe_float(item.get("USD Volume Change", 0))
    largest_change = safe_float(item.get("Largest Tx Change", 0))

    return score_change, swaps_change, transfers_change, volume_change, largest_change


def wallet_movement_score(item):
    score_change, swaps_change, transfers_change, volume_change, largest_change = wallet_movement_values(item)

    priority = 0
    priority += max(score_change, 0) * 2
    priority += max(swaps_change, 0) * 12
    priority += max(transfers_change, 0) * 2
    priority += min(max(volume_change, 0) / 25, 80)
    priority += min(max(largest_change, 0) / 20, 50)

    if item.get("Signal") == "Monitor":
        priority += 20
    elif item.get("Signal") == "Watch":
        priority += 10

    return priority


def wallet_movement_status(item):
    score_change, swaps_change, transfers_change, volume_change, largest_change = wallet_movement_values(item)

    if swaps_change > 0 and volume_change >= 100:
        return "HOT", "movement-hot", "New swaps plus meaningful volume."

    if volume_change >= 250:
        return "VOLUME SPIKE", "movement-hot", "Large fresh dollar movement."

    if swaps_change > 0:
        return "NEW SWAPS", "movement-up-badge", "New swap activity detected."

    if transfers_change > 0:
        return "NEW TRANSFERS", "movement-up-badge", "New transfer activity detected."

    if score_change > 0:
        return "SCORE UP", "movement-up-badge", "Wallet score improved."

    if score_change < 0 or volume_change < -25 or swaps_change < 0:
        return "COOLING", "movement-down-badge", "Activity or volume moved lower."

    return "NO MOVEMENT", "movement-flat-badge", "No meaningful change since last check."


def build_watchlist_radar(wallet_items):
    total_wallets = len(wallet_items)
    moved_wallets = 0
    hot_wallets = 0
    positive_swaps = 0
    positive_transfers = 0
    net_volume_change = 0
    highest_volume_wallet = "-"
    highest_volume_change_wallet = "-"
    highest_volume = 0
    highest_volume_change = 0

    for item in wallet_items:
        score_change, swaps_change, transfers_change, volume_change, largest_change = wallet_movement_values(item)
        status, status_class, status_hint = wallet_movement_status(item)

        if any([
            score_change != 0,
            swaps_change != 0,
            transfers_change != 0,
            abs(volume_change) >= 0.01,
            abs(largest_change) >= 0.01
        ]):
            moved_wallets += 1

        if status in ["HOT", "VOLUME SPIKE", "NEW SWAPS"]:
            hot_wallets += 1

        positive_swaps += max(swaps_change, 0)
        positive_transfers += max(transfers_change, 0)
        net_volume_change += volume_change

        current_volume = safe_float(item.get("USD Volume", 0))
        if current_volume > highest_volume:
            highest_volume = current_volume
            highest_volume_wallet = item.get("Wallet", "-")

        if volume_change > highest_volume_change:
            highest_volume_change = volume_change
            highest_volume_change_wallet = item.get("Wallet", "-")

    if highest_volume_change <= 0:
        highest_volume_change_wallet = "-"

    return {
        "Total Wallets": total_wallets,
        "Moved Wallets": moved_wallets,
        "Hot Wallets": hot_wallets,
        "New Swaps": positive_swaps,
        "New Transfers": positive_transfers,
        "Net Volume Change": net_volume_change,
        "Highest Volume Wallet": highest_volume_wallet,
        "Highest Volume": highest_volume,
        "Highest Volume Change Wallet": highest_volume_change_wallet,
        "Highest Volume Change": highest_volume_change
    }


def build_pinned_wallet_radar(wallet_items):
    pinned_items = [item for item in wallet_items if wallet_is_pinned(item)]
    radar = build_watchlist_radar(pinned_items) if pinned_items else build_watchlist_radar([])

    active_pinned = 0
    for item in pinned_items:
        status, _, _ = wallet_movement_status(item)
        if status in ["HOT", "VOLUME SPIKE", "NEW SWAPS", "NEW TRANSFERS"]:
            active_pinned += 1

    radar["Pinned Wallets"] = len(pinned_items)
    radar["Active Pinned"] = active_pinned
    return radar


def render_pinned_wallet_radar(wallet_items):
    pinned_radar = build_pinned_wallet_radar(wallet_items)

    if pinned_radar["Pinned Wallets"] == 0:
        st.markdown(
            """<div class="pinned-radar">
                <div class="pinned-radar-title">No pinned wallets yet</div>
                <div class="pinned-radar-subtitle">Pin your strongest wallets. Pinned wallets are checked first and build the most useful charts.</div>
            </div>""",
            unsafe_allow_html=True
        )
        return

    subtitle = "Pinned wallets are your main alpha list. Keep Auto Scan on to build better spike charts."
    if pinned_radar["Active Pinned"] > 0:
        subtitle = "Pinned movement detected. Open the active pinned wallets first."

    st.markdown(
        f"""<div class="pinned-radar">
            <div class="pinned-radar-title">Pinned Wallet Radar</div>
            <div class="pinned-radar-subtitle">{subtitle}</div>
            <div class="pinned-grid">
                <div><span>Pinned</span><strong>{pinned_radar["Pinned Wallets"]}</strong></div>
                <div><span>Active now</span><strong>{pinned_radar["Active Pinned"]}</strong></div>
                <div><span>New swaps</span><strong class="{movement_class(pinned_radar["New Swaps"])}">{format_signed_number(pinned_radar["New Swaps"])}</strong></div>
                <div><span>Net volume</span><strong class="{movement_class(pinned_radar["Net Volume Change"])}">{format_signed_usd(pinned_radar["Net Volume Change"])}</strong></div>
                <div><span>Biggest pinned move</span><strong>{pinned_radar["Highest Volume Change Wallet"]} · {format_signed_usd(pinned_radar["Highest Volume Change"])}</strong></div>
            </div>
        </div>""",
        unsafe_allow_html=True
    )


def render_watchlist_radar(wallet_items):
    radar = build_watchlist_radar(wallet_items)

    if radar["Hot Wallets"] > 0:
        radar_state = "radar-hot"
        radar_title = "Radar active"
        radar_text = "Some wallets are moving. Check the hot cards first."
    elif radar["Moved Wallets"] > 0:
        radar_state = "radar-moving"
        radar_title = "Movement detected"
        radar_text = "There is movement, but no strong hot signal yet."
    else:
        radar_state = "radar-calm"
        radar_title = "Radar calm"
        radar_text = "No meaningful wallet movement since the last check."

    radar_html = (
        f'<div class="watchlist-radar {radar_state}">'
        f'<div class="watchlist-radar-top">'
        f'<div>'
        f'<div class="watchlist-radar-title">{radar_title}</div>'
        f'<div class="watchlist-radar-subtitle">{radar_text}</div>'
        f'</div>'
        f'<div class="watchlist-radar-live">LIVE WATCHLIST</div>'
        f'</div>'
        f'<div class="watchlist-radar-grid">'
        f'<div><span>Wallets</span><strong>{radar["Total Wallets"]}</strong></div>'
        f'<div><span>Moved</span><strong>{radar["Moved Wallets"]}</strong></div>'
        f'<div><span>Hot</span><strong>{radar["Hot Wallets"]}</strong></div>'
        f'<div><span>New Swaps</span><strong>{format_signed_number(radar["New Swaps"])}</strong></div>'
        f'<div><span>New Transfers</span><strong>{format_signed_number(radar["New Transfers"])}</strong></div>'
        f'<div><span>Net Volume</span><strong class="{movement_class(radar["Net Volume Change"])}">{format_signed_usd(radar["Net Volume Change"])}</strong></div>'
        f'<div><span>Highest Volume</span><strong>{radar["Highest Volume Wallet"]} · {format_usd(radar["Highest Volume"])}</strong></div>'
        f'<div><span>Biggest Move</span><strong>{radar["Highest Volume Change Wallet"]} · {format_signed_usd(radar["Highest Volume Change"])}</strong></div>'
        f'</div>'
        f'</div>'
    )

    st.markdown(radar_html, unsafe_allow_html=True)


def sorted_watchlist_pairs(wallet_items, sort_mode):
    pairs = list(enumerate(wallet_items))

    if sort_mode == "Pinned + movement":
        return sorted(
            pairs,
            key=lambda pair: (
                1 if wallet_is_pinned(pair[1]) else 0,
                wallet_movement_score(pair[1]),
                safe_float(pair[1].get("USD Volume Change", 0)),
                safe_int(pair[1].get("Swaps Change", 0)),
                safe_int(pair[1].get("Score", 0))
            ),
            reverse=True
        )

    if sort_mode == "Highest movement":
        return sorted(
            pairs,
            key=lambda pair: (
                wallet_movement_score(pair[1]),
                safe_float(pair[1].get("USD Volume Change", 0)),
                safe_int(pair[1].get("Swaps Change", 0)),
                safe_int(pair[1].get("Score", 0))
            ),
            reverse=True
        )

    if sort_mode == "Highest volume change":
        return sorted(pairs, key=lambda pair: safe_float(pair[1].get("USD Volume Change", 0)), reverse=True)

    if sort_mode == "New swaps":
        return sorted(pairs, key=lambda pair: safe_int(pair[1].get("Swaps Change", 0)), reverse=True)

    if sort_mode == "Best score":
        return sorted(pairs, key=lambda pair: safe_int(pair[1].get("Score", 0)), reverse=True)

    if sort_mode == "Last checked":
        return sorted(pairs, key=lambda pair: str(pair[1].get("Last Checked", "")), reverse=True)

    return pairs


def recheck_wallet_watchlist_item(index):
    if index < 0 or index >= len(st.session_state.watchlist_wallets):
        st.session_state.watchlist_message = "Wallet not found."
        return None

    item = st.session_state.watchlist_wallets[index]
    wallet_address = item.get("Full Wallet", item.get("Wallet", "")).strip()

    if not wallet_address:
        st.session_state.watchlist_message = "Wallet has no address."
        return None

    wallet_tx_data, wallet_error = fetch_wallet_transactions(wallet_address)

    if wallet_error or wallet_tx_data is None or wallet_tx_data.empty:
        st.session_state.watchlist_message = "Could not recheck wallet."
        return None

    total_tx, transfers, swaps, unknown, activity_level = summarize_wallet_activity(wallet_tx_data)

    wallet_signal, wallet_score, wallet_reason = get_wallet_signal(
        total_tx,
        transfers,
        swaps,
        unknown
    )

    usd_stats = estimate_wallet_usd_stats(wallet_tx_data)
    new_buys, new_sells, new_rotates = wallet_trade_counts(wallet_tx_data)
    latest_trade_event = latest_trade_event_from_wallet_data(wallet_tx_data)

    old_score = safe_int(item.get("Score", 0))
    old_swaps = safe_int(item.get("Swaps", 0))
    old_transfers = safe_int(item.get("Transfers", 0))
    old_buys = safe_int(item.get("Buys", 0))
    old_sells = safe_int(item.get("Sells", 0))
    old_rotates = safe_int(item.get("Rotates", 0))
    old_volume = safe_float(item.get("USD Volume", 0))
    old_largest = safe_float(item.get("Largest Tx", 0))

    new_score = safe_int(wallet_score)
    new_swaps = safe_int(swaps)
    new_transfers = safe_int(transfers)
    new_volume = safe_float(usd_stats.get("Total USD Volume", 0))
    new_largest = safe_float(usd_stats.get("Largest USD Tx", 0))

    score_change = new_score - old_score
    swap_change = new_swaps - old_swaps
    transfer_change = new_transfers - old_transfers
    volume_change = new_volume - old_volume
    largest_change = new_largest - old_largest

    change_text = short_change_summary(
        score_change,
        swap_change,
        transfer_change,
        volume_change,
        largest_change
    )

    latest_activity = latest_wallet_activity_text(wallet_tx_data)
    latest_token_mint = latest_wallet_token_mint(wallet_tx_data)

    short_wallet_for_history = item.get("Wallet", wallet_address[:6] + "..." + wallet_address[-6:])
    append_wallet_history_point(
        wallet_address,
        short_wallet_for_history,
        old_score,
        old_swaps,
        old_transfers,
        old_volume,
        old_largest,
        new_score,
        new_swaps,
        new_transfers,
        new_volume,
        new_largest,
        score_change,
        swap_change,
        transfer_change,
        volume_change,
        largest_change,
        old_buys,
        old_sells,
        old_rotates,
        new_buys,
        new_sells,
        new_rotates,
        latest_trade_event
    )

    st.session_state.watchlist_wallets[index]["Signal"] = wallet_signal
    st.session_state.watchlist_wallets[index]["Score"] = new_score
    st.session_state.watchlist_wallets[index]["Transfers"] = new_transfers
    st.session_state.watchlist_wallets[index]["Swaps"] = new_swaps
    st.session_state.watchlist_wallets[index]["Buys"] = new_buys
    st.session_state.watchlist_wallets[index]["Sells"] = new_sells
    st.session_state.watchlist_wallets[index]["Rotates"] = new_rotates
    st.session_state.watchlist_wallets[index]["USD Volume"] = new_volume
    st.session_state.watchlist_wallets[index]["Largest Tx"] = new_largest
    st.session_state.watchlist_wallets[index]["Last Checked"] = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")
    st.session_state.watchlist_wallets[index]["Check Count"] = safe_int(item.get("Check Count", 0)) + 1
    st.session_state.watchlist_wallets[index]["Reason"] = wallet_reason

    st.session_state.watchlist_wallets[index]["Previous Score"] = old_score
    st.session_state.watchlist_wallets[index]["Previous Swaps"] = old_swaps
    st.session_state.watchlist_wallets[index]["Previous Transfers"] = old_transfers
    st.session_state.watchlist_wallets[index]["Previous Buys"] = old_buys
    st.session_state.watchlist_wallets[index]["Previous Sells"] = old_sells
    st.session_state.watchlist_wallets[index]["Previous Rotates"] = old_rotates
    st.session_state.watchlist_wallets[index]["Previous USD Volume"] = old_volume
    st.session_state.watchlist_wallets[index]["Previous Largest Tx"] = old_largest

    st.session_state.watchlist_wallets[index]["Score Change"] = score_change
    st.session_state.watchlist_wallets[index]["Swaps Change"] = swap_change
    st.session_state.watchlist_wallets[index]["Transfers Change"] = transfer_change
    st.session_state.watchlist_wallets[index]["Buys Change"] = new_buys - old_buys
    st.session_state.watchlist_wallets[index]["Sells Change"] = new_sells - old_sells
    st.session_state.watchlist_wallets[index]["Rotates Change"] = new_rotates - old_rotates
    st.session_state.watchlist_wallets[index]["USD Volume Change"] = volume_change
    st.session_state.watchlist_wallets[index]["Largest Tx Change"] = largest_change
    st.session_state.watchlist_wallets[index]["Change"] = change_text
    st.session_state.watchlist_wallets[index]["Latest Activity"] = latest_activity
    st.session_state.watchlist_wallets[index]["Latest Token Mint"] = latest_token_mint
    st.session_state.watchlist_wallets[index]["Latest Trade Side"] = latest_trade_event.get("Trade Side", "-")
    st.session_state.watchlist_wallets[index]["Latest Trade Token"] = latest_trade_event.get("Trade Token", "-")
    st.session_state.watchlist_wallets[index]["Latest Trade Hint"] = latest_trade_event.get("Trade Hint", "-")

    save_json_list(WALLET_WATCHLIST_FILE, st.session_state.watchlist_wallets)

    # Keep the Journal alive too: every manual/auto wallet check adds evidence to the wallet opinion layer.
    try:
        update_wallet_documentation_from_watchlist_item(st.session_state.watchlist_wallets[index], source="watchlist_recheck")
    except Exception:
        pass

    short_wallet = item.get("Wallet", wallet_address[:6] + "..." + wallet_address[-6:])
    st.session_state.watchlist_message = f"{short_wallet}: {change_text}"

    return f"{short_wallet}: {change_text}"


def add_token_to_watchlist(token_item):
    already_added = any(
        item["Mint"] == token_item["Mint"]
        for item in st.session_state.watchlist_tokens
    )

    if already_added:
        st.session_state.token_watchlist_message = "Token is already in your watchlist."
    else:
        st.session_state.watchlist_tokens.append(token_item)
        save_json_list(TOKEN_WATCHLIST_FILE, st.session_state.watchlist_tokens)
        st.session_state.token_watchlist_message = "Token added to watchlist."


def remove_token_from_watchlist(index):
    if 0 <= index < len(st.session_state.watchlist_tokens):
        st.session_state.watchlist_tokens.pop(index)
        save_json_list(TOKEN_WATCHLIST_FILE, st.session_state.watchlist_tokens)
        st.session_state.token_watchlist_message = "Token removed from watchlist."

def recheck_token_watchlist_item(index):
    item = st.session_state.watchlist_tokens[index]
    mint = item.get("Mint", "")

    if not mint:
        st.session_state.token_watchlist_message = "Token has no mint address."
        return

    token_data, error = fetch_token_pairs("solana", mint)

    if error or token_data is None or token_data.empty:
        st.session_state.token_watchlist_message = "Could not refresh token data."
        return

    best_pair = token_data.iloc[0]

    liquidity_status, volume_status, activity_status, risk = evaluate_token_pair(best_pair)
    copy_risk, copy_risk_reasons = evaluate_copy_risk(best_pair)

    decision, decision_reason = get_watch_signal(
        liquidity_status,
        volume_status,
        activity_status,
        risk,
        copy_risk
    )

    st.session_state.watchlist_tokens[index]["Liquidity"] = liquidity_status
    st.session_state.watchlist_tokens[index]["Volume"] = volume_status
    st.session_state.watchlist_tokens[index]["Activity"] = activity_status
    st.session_state.watchlist_tokens[index]["Risk"] = risk
    st.session_state.watchlist_tokens[index]["Copy Risk"] = copy_risk
    st.session_state.watchlist_tokens[index]["Decision"] = decision
    st.session_state.watchlist_tokens[index]["Reason"] = decision_reason
    st.session_state.watchlist_tokens[index]["Last Checked"] = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")

    save_json_list(TOKEN_WATCHLIST_FILE, st.session_state.watchlist_tokens)

    st.session_state.token_watchlist_message = "Token rechecked successfully."

def recheck_all_token_watchlist_items():
    if not st.session_state.watchlist_tokens:
        st.session_state.token_watchlist_message = "No tokens to recheck."
        return

    checked_count = 0
    failed_count = 0

    for index in range(len(st.session_state.watchlist_tokens)):
        before_message = st.session_state.token_watchlist_message

        recheck_token_watchlist_item(index)

        if st.session_state.token_watchlist_message == "Token rechecked successfully.":
            checked_count += 1
        else:
            failed_count += 1
            st.session_state.token_watchlist_message = before_message

    save_json_list(TOKEN_WATCHLIST_FILE, st.session_state.watchlist_tokens)

    st.session_state.token_watchlist_message = (
        f"Rechecked {checked_count} tokens. Failed: {failed_count}."
    )

def add_recent_item(state_key, value, limit=8):
    value = str(value).strip()

    if not value:
        return

    if state_key not in st.session_state:
        st.session_state[state_key] = []

    current_items = [
        item for item in st.session_state[state_key]
        if item != value
    ]

    st.session_state[state_key] = [value] + current_items[:limit - 1]

    recent_files = {
        "recent_token_mints": RECENT_TOKEN_MINTS_FILE,
        "recent_wallets": RECENT_WALLETS_FILE,
        "recent_ai_searches": RECENT_AI_SEARCHES_FILE
    }

    if state_key in recent_files:
        save_json_list(recent_files[state_key], st.session_state[state_key])

    

def extract_amount_from_description(description):
    text = str(description)

    if not text or text == "-":
        return "-"

    if " transferred a total of " in text:
        amount_text = text.split(" transferred a total of ", 1)[1]
        return amount_text.split(" ", 1)[0]

    if " transferred " in text:
        amount_text = text.split(" transferred ", 1)[1]
        first_word = amount_text.split(" ", 1)[0]

        if first_word.lower() in ["a", "an", "the"]:
            return "-"

        return first_word

    return "-"

def is_probably_real_wallet(address):
    if not address:
        return False

    if not isinstance(address, str):
        return False

    if len(address) < 32:
        return False

    blocked_prefixes = [
        "Tokenk",
        "AToken",
        "Comput",
        "Sysvar",
        "Vote",
        "Memo",
        "Stake",
        "BPFLoader",
        "AddressLookup"
    ]

    for prefix in blocked_prefixes:
        if address.startswith(prefix):
            return False

    blocked_exact = {
        "11111111111111111111111111111111",
        "So11111111111111111111111111111111111111112",
        "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
        "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL",
        "ComputeBudget111111111111111111111111111111"
    }

    if address in blocked_exact:
        return False

    return True

@st.cache_data(ttl=30, show_spinner=False)
def fetch_helius_signatures_for_address(address, limit=40):
    try:
        api_key = str(st.secrets["HELIUS_API_KEY"]).strip()

        url = f"https://mainnet.helius-rpc.com/?api-key={api_key}"

        payload = {
            "jsonrpc": "2.0",
            "id": "wallet-discovery-signatures",
            "method": "getSignaturesForAddress",
            "params": [
                address,
                {
                    "limit": limit
                }
            ]
        }

        response = requests.post(url, json=payload, timeout=20)
        response.raise_for_status()

        result = response.json()

        signatures = result.get("result", [])

        if not signatures:
            return [], "No Helius signatures found for this token."

        return signatures, None

    except Exception as error:
        return [], f"Helius signature error: {error}"


def discover_wallets_from_token_helius(token_mint, max_wallets=10):
    signatures, signature_error = fetch_helius_signatures_for_address(token_mint, limit=40)

    if signature_error:
        return pd.DataFrame(), signature_error

    wallet_stats = {}

    ignored_addresses = {
        token_mint,
        "11111111111111111111111111111111",
        "So11111111111111111111111111111111111111112"
    }

    api_key = str(st.secrets["HELIUS_API_KEY"]).strip()
    url = f"https://api.helius.xyz/v0/transactions/?api-key={api_key}"

    signature_list = [
        item.get("signature")
        for item in signatures
        if item.get("signature")
    ]

    for start in range(0, min(len(signature_list), 40), 10):
        batch = signature_list[start:start + 10]

        try:
            response = requests.post(
                url,
                json={"transactions": batch},
                timeout=25
            )
            response.raise_for_status()

            transactions = response.json()

        except Exception:
            continue

        for tx in transactions:
            account_data = tx.get("accountData", [])

            for account in account_data:
                wallet = account.get("account")

                if wallet in ignored_addresses:
                    continue
       
                if not is_probably_real_wallet(wallet):
                    continue

                if wallet not in wallet_stats:
                    wallet_stats[wallet] = {
                        "Wallet": wallet,
                        "Hits": 0
                    }

                wallet_stats[wallet]["Hits"] += 1

    candidates = list(wallet_stats.values())

    candidates = sorted(
        candidates,
        key=lambda item: item["Hits"],
        reverse=True
    )

    if not candidates:
        return pd.DataFrame(), "No wallet candidates found from Helius transactions."

    discovered_rows = []

    for candidate in candidates[:max_wallets]:
        wallet = candidate["Wallet"]
        short_wallet = f"{wallet[:6]}...{wallet[-6:]}"

        wallet_tx_data, wallet_error = fetch_wallet_transactions(wallet)

        if wallet_error or wallet_tx_data is None or wallet_tx_data.empty:
            discovered_rows.append({
                "Wallet": short_wallet,
                "Full Wallet": wallet,
                "Score": 20,
                "Type": "Candidate",
                "Hits": candidate["Hits"],
                "Swaps": "-",
                "Reason": "Found in token transactions. Wallet scan failed or no recent Helius data.",
                "Source Token": shorten_mints(token_mint)
            })
            continue

        total_tx, transfers_count, swaps, unknown, activity_level = summarize_wallet_activity(wallet_tx_data)

        wallet_signal, wallet_score, wallet_reason = get_wallet_signal(
            total_tx,
            transfers_count,
            swaps,
            unknown
        )

        if wallet_score >= 80:
            wallet_type = "Strong Candidate"
        elif wallet_score >= 60:
            wallet_type = "Watch Candidate"
        elif swaps >= 2:
            wallet_type = "Active Trader"
        else:
            wallet_type = "Transfer Candidate"

        if wallet_score >= 85:
            wallet_reason = "High activity and strong swap behavior. Good wallet to monitor for early token discovery."
        elif wallet_score >= 70:
            wallet_reason = "Promising wallet activity. Worth watching, but not the strongest signal yet."

        discovered_rows.append({
            "Wallet": short_wallet,
            "Full Wallet": wallet,
            "Score": wallet_score,
            "Type": wallet_type,
            "Hits": candidate["Hits"],
            "Swaps": swaps,
            "Reason": wallet_reason,
            "Source Token": shorten_mints(token_mint)
        })

    discovered_df = pd.DataFrame(discovered_rows)

    discovered_df = discovered_df.sort_values(
        by=["Score", "Hits"],
        ascending=False
    )

    return discovered_df, None

@st.cache_data(ttl=30, show_spinner=False)
def fetch_solscan_token_transfers(token_mint, limit=50):
    try:
        api_key = str(st.secrets["SOLSCAN_API_KEY"]).strip()

        url = "https://pro-api.solscan.io/v2.0/token/transfer"

        headers = {
            "accept": "application/json",
            "token": api_key
}

        params = {
            "address": token_mint,
            "page": 1,
            "page_size": 50,
            "exclude_amount_zero": True,
            "sort_by": "block_time",
            "sort_order": "asc"
}

        response = requests.get(url, headers=headers, params=params, timeout=20)
        response.raise_for_status()

        result = response.json()
        data = result.get("data", [])

        if isinstance(data, dict):
            data = data.get("items", data.get("data", []))

        if not data:
            return [], "No Solscan transfers found for this token."

        return data, None

    except Exception as error:
        return [], f"Solscan transfer error: {error}"


def extract_wallet_candidates_from_transfers(transfers, token_mint):
    wallet_stats = {}

    ignored_addresses = {
        token_mint,
        "11111111111111111111111111111111",
        "So11111111111111111111111111111111111111112"
    }

    for transfer in transfers:
        from_wallet = (
            transfer.get("from_address")
            or transfer.get("from")
            or transfer.get("src")
            or transfer.get("source")
        )

        to_wallet = (
            transfer.get("to_address")
            or transfer.get("to")
            or transfer.get("dst")
            or transfer.get("destination")
        )

        amount = (
            transfer.get("amount")
            or transfer.get("token_amount")
            or transfer.get("value")
            or 0
        )

        for wallet in [from_wallet, to_wallet]:
            if wallet in ignored_addresses:
                continue

            if not is_probably_real_wallet(wallet):
                continue

            if wallet not in wallet_stats:
                wallet_stats[wallet] = {
                    "Wallet": wallet,
                    "Transfers": 0,
                    "Volume Seen": 0
                }

            wallet_stats[wallet]["Transfers"] += 1

            try:
                wallet_stats[wallet]["Volume Seen"] += float(amount)
            except Exception:
                pass

    candidates = list(wallet_stats.values())

    candidates = sorted(
        candidates,
        key=lambda item: (item["Transfers"], item["Volume Seen"]),
        reverse=True
    )

    return candidates


def discover_wallets_from_token_solscan(token_mint, max_wallets=15):
    """
    Solscan-first wallet discovery.
    Fetches earliest transfers (asc order) to find wallets that bought in early.
    Scores each wallet via Helius transaction analysis.
    Returns: (DataFrame, error_string_or_None)
    """
    transfers, transfer_error = fetch_solscan_token_transfers(token_mint, limit=50)

    if transfer_error:
        return pd.DataFrame(), transfer_error

    candidates = extract_wallet_candidates_from_transfers(transfers, token_mint)

    if not candidates:
        return pd.DataFrame(), "No wallet candidates found in Solscan transfers."

    discovered_rows = []

    for rank, candidate in enumerate(candidates[:max_wallets]):
        wallet = str(candidate.get("Wallet", "")).strip()
        if not wallet:
            continue
        short_wallet = f"{wallet[:6]}...{wallet[-6:]}"
        early_rank = rank + 1  # lower = earlier buyer

        wallet_tx_data, wallet_error = fetch_wallet_transactions(wallet)

        if wallet_error or wallet_tx_data is None or wallet_tx_data.empty:
            # Still add as candidate — early position is already a signal
            base_score = max(60 - (early_rank * 3), 20)
            discovered_rows.append({
                "Wallet": short_wallet,
                "Full Wallet": wallet,
                "Score": base_score,
                "Early Rank": early_rank,
                "Type": "Early Buyer",
                "Transfers": candidate.get("Transfers", 0),
                "Swaps": "-",
                "Verdict": "Watch first",
                "Reason": f"Early buyer (rank #{early_rank}). Wallet scan failed — may be inactive.",
                "Source Token": shorten_mints(token_mint),
                "Saved?": "New" if not wallet_already_saved(wallet) else "Saved"
            })
            continue

        total_tx, transfers_count, swaps, unknown, activity_level = summarize_wallet_activity(wallet_tx_data)
        wallet_signal, wallet_score, wallet_reason = get_wallet_signal(total_tx, transfers_count, swaps, unknown)

        # Boost score for early position
        early_bonus = max(15 - (early_rank * 1), 0)
        final_score = min(safe_int(wallet_score) + early_bonus, 100)

        if final_score >= 80:
            wallet_type, verdict = "Alpha Scout", "Copy candidate"
        elif final_score >= 65:
            wallet_type, verdict = "Strong Early", "Watch closely"
        elif swaps >= 3:
            wallet_type, verdict = "Active Trader", "Paper trade first"
        else:
            wallet_type, verdict = "Early Buyer", "Needs proof"

        discovered_rows.append({
            "Wallet": short_wallet,
            "Full Wallet": wallet,
            "Score": final_score,
            "Early Rank": early_rank,
            "Type": wallet_type,
            "Transfers": candidate.get("Transfers", 0),
            "Swaps": safe_int(swaps),
            "Verdict": verdict,
            "Reason": wallet_reason,
            "Source Token": shorten_mints(token_mint),
            "Saved?": "New" if not wallet_already_saved(wallet) else "Saved"
        })

    if not discovered_rows:
        return pd.DataFrame(), "No valid wallet candidates after analysis."

    discovered_df = pd.DataFrame(discovered_rows)
    discovered_df = discovered_df.sort_values(by=["Score", "Transfers"], ascending=False).reset_index(drop=True)
    return discovered_df, None

def shorten_mints(value):
    if not value or value == "-":
        return "-"

    parts = str(value).split(",")
    shortened = []

    for mint in parts[:3]:
        mint = mint.strip()
        if len(mint) > 18:
            shortened.append(f"{mint[:6]}...{mint[-6:]}")
        else:
            shortened.append(mint)

    if len(parts) > 3:
        shortened.append(f"+{len(parts) - 3} more")

    return ", ".join(shortened)

# -----------------------------
# Styling
# -----------------------------
st.markdown("""
<style>
            
            .discovery-card {
    background: linear-gradient(145deg, #25262a, #202126);
    border: 1px solid #3a3b40;
    border-radius: 18px;
    padding: 15px 17px;
    margin-top: 12px;
    margin-bottom: 8px;
    box-shadow: 0 12px 28px rgba(0, 0, 0, 0.18);
}

.discovery-card-top {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 12px;
    margin-bottom: 13px;
}

.discovery-wallet {
    color: #f5f5f7;
    font-size: 18px;
    font-weight: 850;
}

.discovery-subtitle {
    color: #8f9299;
    font-size: 12px;
    margin-top: 3px;
}

.discovery-rating {
    color: #9be7b0;
    border: 1px solid rgba(80, 220, 140, 0.35);
    background: rgba(80, 220, 140, 0.10);
    border-radius: 999px;
    padding: 7px 11px;
    font-size: 13px;
    font-weight: 850;
    white-space: nowrap;
}

.discovery-grid {
    display: grid;
    grid-template-columns: 1fr 1fr 2.4fr;
    gap: 10px;
}

.discovery-grid div {
    background: rgba(255,255,255,0.035);
    border: 1px solid #34363b;
    border-radius: 13px;
    padding: 10px 11px;
}

.discovery-grid span {
    display: block;
    color: #8f9299;
    font-size: 11px;
    margin-bottom: 5px;
}

.discovery-grid strong {
    display: block;
    color: #f5f5f7;
    font-size: 13px;
    line-height: 1.35;
}
            
.clean-table {
    width: 100%;
    table-layout: fixed;
    border-collapse: separate;
    border-spacing: 0;
    background: #0f1218;
    border: 1px solid rgba(255,255,255,0.10);
    border-radius: 14px;
    overflow: hidden;
    font-size: 13px;
    box-shadow: 0 18px 45px rgba(0,0,0,0.28);
}
            
.market-table {
    width: 100%;
    table-layout: auto;
    border-collapse: separate;
    border-spacing: 0;
    background: #0f1218;
    border: 1px solid rgba(255,255,255,0.10);
    border-radius: 14px;
    overflow: hidden;
    font-size: 13px;
    box-shadow: 0 18px 45px rgba(0,0,0,0.28);
}

.market-table th {
    text-align: left;
    padding: 11px 12px;
    background: #171b23;
    color: #9ca3af;
    font-weight: 700;
    border-bottom: 1px solid rgba(255,255,255,0.10);
    white-space: nowrap;
}

.market-table td {
    padding: 11px 12px;
    color: #f3f4f6;
    border-bottom: 1px solid rgba(255,255,255,0.06);
    white-space: nowrap;
}

.market-table tr:last-child td {
    border-bottom: none;
}

.market-table tr:hover td {
    background: rgba(255,255,255,0.035);
}

.clean-table th {
    text-align: left;
    padding: 11px 12px;
    background: #171b23;
    color: #9ca3af;
    font-weight: 700;
    border-bottom: 1px solid rgba(255,255,255,0.10);
    white-space: nowrap;
}

.clean-table td {
    padding: 11px 12px;
    color: #f3f4f6;
    border-bottom: 1px solid rgba(255,255,255,0.06);
    vertical-align: middle;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

.clean-table tr:last-child td {
    border-bottom: none;
}

.clean-table tr:hover td {
    background: rgba(255,255,255,0.035);
}

.clean-table th:nth-child(1),
.clean-table td:nth-child(1) {
    width: 120px;
}

.clean-table th:nth-child(2),
.clean-table td:nth-child(2) {
    width: 95px;
}

.clean-table th:nth-child(3),
.clean-table td:nth-child(3) {
    width: 95px;
}

.clean-table th:nth-child(4),
.clean-table td:nth-child(4) {
    width: 230px;
}

.clean-table th:nth-child(5),
.clean-table td:nth-child(5) {
    width: 420px;
}
/* Font */
html, body, [class*="css"] {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}

/* Main app background */
.stApp {
    background: #202124;
    color: #f5f5f7;
}

/* Top header */
header[data-testid="stHeader"] {
    background: #202124;
}

/* Main container */
.block-container {
    padding-top: 2.4rem;
    padding-left: 4rem;
    padding-right: 4rem;
    max-width: 1400px;
}

/* Titles */
h1 {
    font-size: 40px !important;
    font-weight: 700 !important;
    letter-spacing: -1px;
    color: #f5f5f7 !important;
}

h2, h3 {
    color: #f5f5f7 !important;
    letter-spacing: -0.4px;
}

/* Captions and muted text */
.stCaptionContainer {
    color: #a1a1a6 !important;
}

/* Section titles */
.section-title {
    font-size: 21px;
    font-weight: 650;
    margin-top: 28px;
    margin-bottom: 14px;
    color: #f5f5f7;
    letter-spacing: -0.4px;
}

/* Sidebar */
[data-testid="stSidebar"] {
    background: #242528;
    border-right: 1px solid #34363a;
}

[data-testid="stSidebar"] > div:first-child {
    padding-top: 2.4rem;
    padding-left: 1.35rem;
    padding-right: 1.35rem;
}

/* Sidebar text */
[data-testid="stSidebar"] * {
    color: #f5f5f7;
}

/* Sidebar title */
[data-testid="stSidebar"] h1 {
    font-size: 30px !important;
    line-height: 1.12 !important;
    font-weight: 700 !important;
    letter-spacing: -0.8px !important;
    margin-bottom: 1.4rem !important;
}

/* Navigation label */
[data-testid="stSidebar"] .stRadio > label {
    color: #a1a1a6 !important;
    font-size: 13px !important;
    font-weight: 600 !important;
    margin-bottom: 0.7rem !important;
}

/* Radio container */
[data-testid="stSidebar"] .stRadio {
    width: 100%;
}

[data-testid="stSidebar"] .stRadio > div {
    width: 100%;
}

/* Navigation list */
[data-testid="stSidebar"] div[role="radiogroup"] {
    display: flex;
    flex-direction: column;
    gap: 8px;
    width: 100%;
}

/* Hide radio dots */
[data-testid="stSidebar"] div[role="radiogroup"] input {
    display: none;
}

[data-testid="stSidebar"] div[role="radiogroup"] label > div:first-child {
    display: none;
}

/* Navigation item wrapper */
[data-testid="stSidebar"] div[role="radiogroup"] > label {
    width: 100% !important;
    max-width: 100% !important;
    padding: 0 !important;
    margin: 0 !important;
    cursor: pointer;
}

/* Navigation item */
[data-testid="stSidebar"] div[role="radiogroup"] label > div:last-child {
    width: 100% !important;
    min-height: 44px;
    padding: 0 14px;
    border-radius: 16px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: transparent;
    border: 1px solid transparent;
    transition: all 0.18s ease;
}

/* Navigation text */
[data-testid="stSidebar"] div[role="radiogroup"] label p {
    width: 100%;
    text-align: center;
    font-size: 14px !important;
    font-weight: 550 !important;
    color: #d8d8dc !important;
    margin: 0 !important;
}

/* Hover navigation */
[data-testid="stSidebar"] div[role="radiogroup"] label:hover > div:last-child {
    background: #303136;
    border-color: #3a3b40;
    transform: translateX(2px);
}

/* Active navigation */
[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) > div:last-child {
    background: #3a3b40;
    border: 1px solid #4a4c52;
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.05);
}

/* Active navigation text */
[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) p {
    color: #ffffff !important;
}

/* Sidebar divider */
[data-testid="stSidebar"] hr {
    border-color: #3a3b40;
    margin-top: 1.8rem;
    margin-bottom: 1.6rem;
}

/* Sidebar filter labels */
[data-testid="stSidebar"] .stSelectbox label,
[data-testid="stSidebar"] .stSlider label {
    color: #f5f5f7 !important;
    font-size: 13px !important;
    font-weight: 600 !important;
}

/* Sidebar selectboxes */
[data-testid="stSidebar"] div[data-baseweb="select"] > div {
    background: #2b2c30 !important;
    color: #f5f5f7 !important;
    border-radius: 16px !important;
    border: 1px solid #3a3b40 !important;
    min-height: 44px;
    transition: all 0.18s ease;
}

[data-testid="stSidebar"] div[data-baseweb="select"]:hover > div {
    background: #303136 !important;
    border-color: #4a4c52 !important;
}

[data-testid="stSidebar"] div[data-baseweb="select"] span {
    color: #f5f5f7 !important;
}

/* Sidebar slider */
[data-testid="stSidebar"] .stSlider {
    padding-top: 0.2rem;
}

/* Sidebar full width fix */
[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
    width: 100%;
}

[data-testid="stSidebar"] .element-container {
    width: 100%;
}


/* Text area */
.stTextArea textarea {
    background: #2b2c30 !important;
    color: #f5f5f7 !important;
    border: 1px solid #3a3b40 !important;
    border-radius: 18px !important;
    padding: 14px 16px !important;
    font-size: 15px !important;
    box-shadow: none !important;
}

/* Metric cards */
[data-testid="stMetric"] {
    background: #2b2c30;
    border: 1px solid #3a3b40;
    border-radius: 24px;
    padding: 22px 22px;
    box-shadow: 0 10px 28px rgba(0, 0, 0, 0.22);
    transition: all 0.22s ease;
}

[data-testid="stMetric"]:hover {
    transform: translateY(-2px) scale(1.01);
    box-shadow: 0 16px 36px rgba(0, 0, 0, 0.30);
    border-color: #4a4c52;
}

[data-testid="stMetricLabel"] {
    color: #a1a1a6 !important;
}

[data-testid="stMetricValue"] {
    color: #f5f5f7 !important;
    font-weight: 600 !important;
}

/* Buttons */
.stButton button {
    border-radius: 999px !important;
    border: 1px solid #4a4c52 !important;
    background: #f5f5f7 !important;
    color: #202124 !important;
    padding: 0.65rem 1.3rem !important;
    font-weight: 600 !important;
    transition: all 0.22s ease;
    box-shadow: 0 8px 22px rgba(0, 0, 0, 0.20);
}

.stButton button:hover {
    transform: translateY(-2px) scale(1.015);
    background: #ffffff !important;
    color: #111111 !important;
    border-color: #ffffff !important;
    box-shadow: 0 14px 32px rgba(0, 0, 0, 0.32);
}

/* Selectbox */
div[data-baseweb="select"] > div {
    background: #2b2c30 !important;
    color: #f5f5f7 !important;
    border-radius: 16px !important;
    border: 1px solid #3a3b40 !important;
}

div[data-baseweb="select"] span {
    color: #f5f5f7 !important;
}

/* Dataframes */
[data-testid="stDataFrame"] {
    border-radius: 22px;
    overflow: hidden;
    border: 1px solid #3a3b40;
    box-shadow: 0 10px 28px rgba(0, 0, 0, 0.22);
}

/* Alerts */
.stAlert {
    border-radius: 18px;
    border: 1px solid #3a3b40;
}

/* Divider */
hr {
    border-color: #34363a;
    margin-top: 2rem;
    margin-bottom: 2rem;
}

*:focus {
    outline: none !important;
}
            
            /* -----------------------------
   FINAL SIDEBAR FIX
----------------------------- */

/* Sidebar fixed clean width */
section[data-testid="stSidebar"] {
    width: 320px !important;
    min-width: 320px !important;
    max-width: 320px !important;
    background: #242528 !important;
    border-right: 1px solid #34363a !important;
}

/* Sidebar inside spacing */
section[data-testid="stSidebar"] > div {
    width: 320px !important;
    padding-left: 22px !important;
    padding-right: 22px !important;
}

/* Sidebar content position */
[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
    width: 100% !important;
}

/* Sidebar title */
[data-testid="stSidebar"] h1 {
    font-size: 30px !important;
    line-height: 1.12 !important;
    font-weight: 700 !important;
    letter-spacing: -0.8px !important;
    margin-bottom: 1.4rem !important;
}

/* Keep Streamlit sidebar button visible */
/* Sidebar open/close handle only */
[data-testid="collapsedControl"] {
    display: flex !important;
    visibility: visible !important;
    opacity: 1 !important;

    position: fixed !important;
    top: 50% !important;
    left: 10px !important;
    transform: translateY(-50%) !important;

    width: 28px !important;
    height: 120px !important;
    min-width: 28px !important;

    background: rgba(255, 255, 255, 0.08) !important;
    border: 1px solid #4a4c52 !important;
    border-radius: 999px !important;

    align-items: center !important;
    justify-content: center !important;

    box-shadow: 0 10px 28px rgba(0, 0, 0, 0.28) !important;
    backdrop-filter: blur(10px) !important;

    z-index: 999999 !important;
    transition: all 0.2s ease !important;
}

[data-testid="collapsedControl"]:hover {
    background: rgba(255, 255, 255, 0.14) !important;
    border-color: #6a6c73 !important;
    transform: translateY(-50%) scale(1.04) !important;
}

[data-testid="collapsedControl"] svg {
    color: #f5f5f7 !important;
    width: 18px !important;
    height: 18px !important;
}

/* Navigation container full width */
[data-testid="stSidebar"] .stRadio,
[data-testid="stSidebar"] .stRadio > div,
[data-testid="stSidebar"] div[role="radiogroup"] {
    width: 100% !important;
}

/* Navigation list */
[data-testid="stSidebar"] div[role="radiogroup"] {
    display: flex !important;
    flex-direction: column !important;
    gap: 8px !important;
}

/* Hide radio dots */
[data-testid="stSidebar"] div[role="radiogroup"] input {
    display: none !important;
}

[data-testid="stSidebar"] div[role="radiogroup"] label > div:first-child {
    display: none !important;
}

/* Navigation item outer */
[data-testid="stSidebar"] div[role="radiogroup"] > label {
    width: 100% !important;
    max-width: 100% !important;
    margin: 0 !important;
    padding: 0 !important;
    cursor: pointer !important;
}

/* Navigation item inner */
[data-testid="stSidebar"] div[role="radiogroup"] label > div:last-child {
    width: 100% !important;
    min-height: 44px !important;
    padding: 0 14px !important;
    border-radius: 16px !important;
    background: transparent !important;
    border: 1px solid transparent !important;

    display: flex !important;
    align-items: center !important;
    justify-content: center !important;

    transition: all 0.18s ease !important;
}

/* Navigation text centered */
[data-testid="stSidebar"] div[role="radiogroup"] label p {
    width: 100% !important;
    text-align: center !important;
    font-size: 14px !important;
    font-weight: 550 !important;
    color: #d8d8dc !important;
    margin: 0 !important;
}

/* Hover */
[data-testid="stSidebar"] div[role="radiogroup"] label:hover > div:last-child {
    background: #303136 !important;
    border-color: #3a3b40 !important;
}

/* Active item */
[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) > div:last-child {
    background: #3a3b40 !important;
    border: 1px solid #4a4c52 !important;
}

/* Active text */
[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) p {
    color: #ffffff !important;
}
            
            /* Sidebar final polish */
[data-testid="stSidebar"] > div:first-child {
    padding-top: 2rem !important;
    padding-left: 1.4rem !important;
    padding-right: 1.4rem !important;
}

/* Sidebar title cleaner */
[data-testid="stSidebar"] h1 {
    font-size: 28px !important;
    line-height: 1.1 !important;
    margin-bottom: 1.8rem !important;
}

/* Navigation tighter */
[data-testid="stSidebar"] div[role="radiogroup"] {
    gap: 4px !important;
}

/* Navigation item height */
[data-testid="stSidebar"] div[role="radiogroup"] label > div:last-child {
    min-height: 40px !important;
    border-radius: 14px !important;
}

/* Navigation text */
[data-testid="stSidebar"] div[role="radiogroup"] label p {
    font-size: 13.5px !important;
    font-weight: 550 !important;
}

/* Less empty space before filters */
[data-testid="stSidebar"] hr {
    margin-top: 1.4rem !important;
    margin-bottom: 1.4rem !important;
}

/* Make filter boxes cleaner */
[data-testid="stSidebar"] div[data-baseweb="select"] > div {
    min-height: 42px !important;
    border-radius: 14px !important;
}

/* Keep sidebar collapse button small and normal */
button[kind="header"] {
    width: 28px !important;
    height: 28px !important;
    border-radius: 999px !important;
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
}

button[kind="header"]:hover {
    background: #303136 !important;
}
            
            /* Sidebar compact polish */
section[data-testid="stSidebar"] {
    width: 300px !important;
    min-width: 300px !important;
    max-width: 300px !important;
}

section[data-testid="stSidebar"] > div {
    width: 300px !important;
}

[data-testid="stSidebar"] > div:first-child {
    padding-top: 2.1rem !important;
    padding-left: 1.25rem !important;
    padding-right: 1.25rem !important;
}

[data-testid="stSidebar"] h1 {
    font-size: 26px !important;
    margin-bottom: 1.5rem !important;
}

[data-testid="stSidebar"] div[role="radiogroup"] {
    gap: 2px !important;
}

[data-testid="stSidebar"] div[role="radiogroup"] label > div:last-child {
    min-height: 38px !important;
    border-radius: 13px !important;
}

[data-testid="stSidebar"] hr {
    margin-top: 1.25rem !important;
    margin-bottom: 1.25rem !important;
}

/* Give main content a little more breathing room */
.block-container {
    padding-left: 4.5rem !important;
    padding-right: 4rem !important;
}
            
            /* Main hero section */
.hero-card {
    background: linear-gradient(145deg, #26272b, #222326);
    border: 1px solid #3a3b40;
    border-radius: 28px;
    padding: 34px 36px;
    margin-bottom: 22px;
    box-shadow: 0 16px 42px rgba(0, 0, 0, 0.24);
}

.hero-kicker {
    color: #a1a1a6;
    font-size: 13px;
    font-weight: 600;
    margin-bottom: 10px;
    letter-spacing: 0.3px;
    text-transform: uppercase;
}

.hero-title {
    color: #f5f5f7;
    font-size: 42px;
    line-height: 1.05;
    font-weight: 750;
    letter-spacing: -1.2px;
    margin-bottom: 12px;
}

.hero-subtitle {
    color: #a1a1a6;
    font-size: 15px;
    max-width: 720px;
    line-height: 1.6;
}

.search-label {
    color: #f5f5f7;
    font-size: 14px;
    font-weight: 600;
    margin-bottom: 8px;
}
            
            /* Hero polish */
.hero-card {
    padding: 28px 34px !important;
    border-radius: 24px !important;
    margin-bottom: 20px !important;
    background: linear-gradient(145deg, #26272b, #222326) !important;
    border: 1px solid #3a3b40 !important;
}

.hero-kicker {
    font-size: 11px !important;
    letter-spacing: 1px !important;
    color: #8f9299 !important;
}

.hero-title {
    font-size: 36px !important;
    letter-spacing: -1px !important;
    margin-bottom: 10px !important;
}

.hero-subtitle {
    font-size: 14px !important;
    color: #a1a1a6 !important;
}

/* Search spacing */
.search-label {
    margin-top: 4px !important;
    margin-bottom: 8px !important;
}
            
            /* Top spacing fix */
.block-container {
    padding-top: 3.8rem !important;
}

/* Hero top breathing room */
.hero-card {
    margin-top: 0.8rem !important;
}
            
            /* KPI cards polish */
[data-testid="stMetric"] {
    min-height: 116px !important;
    display: flex !important;
    align-items: center !important;
}

[data-testid="stMetricLabel"] {
    font-size: 13px !important;
    font-weight: 500 !important;
    color: #a1a1a6 !important;
}

[data-testid="stMetricValue"] {
    font-size: 34px !important;
    font-weight: 650 !important;
    letter-spacing: -0.8px !important;
}

[data-testid="stMetric"]:hover {
    transform: translateY(-3px) scale(1.01) !important;
}
            
  /* AI answer card refined */
.ai-answer-card {
    background: linear-gradient(145deg, #2b2c30, #25262a);
    border: 1px solid #3a3b40;
    border-radius: 22px;
    padding: 18px 20px;
    margin-top: 14px;
    margin-bottom: 22px;
    box-shadow: 0 14px 34px rgba(0, 0, 0, 0.20);
}

.ai-answer-top {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 16px;
    margin-bottom: 16px;
}

.ai-answer-label {
    color: #f5f5f7;
    font-size: 13px;
    font-weight: 700;
    letter-spacing: 0.2px;
}

.ai-answer-meta {
    color: #8f9299;
    font-size: 12px;
    margin-top: 4px;
}

.ai-answer-pill {
    color: #d8d8dc;
    background: rgba(255, 255, 255, 0.045);
    border: 1px solid #4a4c52;
    border-radius: 999px;
    padding: 6px 11px;
    font-size: 12px;
    font-weight: 600;
}

.ai-answer-text {
    color: #f5f5f7;
    font-size: 15px;
    line-height: 1.65;
    max-width: 980px;
}
            
            /* Final clean AI search input */
.search-label {
    text-align: center !important;
    width: 100% !important;
    margin-top: 14px !important;
    margin-bottom: 14px !important;
    font-size: 14px !important;
    font-weight: 650 !important;
}

/* outer input container */
div[data-testid="stTextInput"] {
    width: 100% !important;
    max-width: none !important;
    padding: 0 0 24px 0 !important;
    margin: 0 !important;
    overflow: visible !important;
}

/* Streamlit/BaseWeb wrapper */
div[data-testid="stTextInput"] > div,
div[data-testid="stTextInput"] div[data-baseweb="input"] {
    height: 64px !important;
    min-height: 64px !important;
    border-radius: 20px !important;
    overflow: hidden !important;
    background: #2b2c30 !important;
    border: 1px solid #3a3b40 !important;
    box-shadow: none !important;
}

/* actual input */
div[data-testid="stTextInput"] input {
    height: 64px !important;
    min-height: 64px !important;
    line-height: 64px !important;

    background: transparent !important;
    border: none !important;
    border-radius: 20px !important;

    color: #f5f5f7 !important;
    font-size: 15px !important;
    padding: 0 24px !important;

    outline: none !important;
    box-shadow: none !important;
}

/* hover */
div[data-testid="stTextInput"]:hover > div,
div[data-testid="stTextInput"] div[data-baseweb="input"]:hover {
    background: #303136 !important;
    border-color: #4a4c52 !important;
}

/* focus */
div[data-testid="stTextInput"] div[data-baseweb="input"]:focus-within {
    background: #303136 !important;
    border-color: #5a5c63 !important;
    box-shadow: none !important;
}

/* placeholder */
div[data-testid="stTextInput"] input::placeholder {
    color: #8f9299 !important;
}
            
            /* Remove tiny scrollbar inside AI search input */
div[data-testid="stTextInput"],
div[data-testid="stTextInput"] > div,
div[data-testid="stTextInput"] div[data-baseweb="input"] {
    overflow: hidden !important;
    scrollbar-width: none !important;
}

div[data-testid="stTextInput"]::-webkit-scrollbar,
div[data-testid="stTextInput"] > div::-webkit-scrollbar,
div[data-testid="stTextInput"] div[data-baseweb="input"]::-webkit-scrollbar {
    display: none !important;
}

div[data-testid="stTextInput"] div[data-baseweb="input"] {
    height: 62px !important;
    min-height: 62px !important;
    max-height: 62px !important;
}

div[data-testid="stTextInput"] input {
    height: 62px !important;
    min-height: 62px !important;
    max-height: 62px !important;
    line-height: 62px !important;
}
            
            /* Fix caret/right edge artifact in AI search */
div[data-testid="stTextInput"] div[data-baseweb="input"] {
    height: 56px !important;
    min-height: 56px !important;
    max-height: 56px !important;
    overflow: hidden !important;
    border-radius: 18px !important;
}

div[data-testid="stTextInput"] input {
    height: 56px !important;
    min-height: 56px !important;
    max-height: 56px !important;
    line-height: normal !important;
    border-radius: 18px !important;
    padding: 0 22px !important;
    caret-color: #f5f5f7 !important;
}

/* Remove inner right visual line */
div[data-testid="stTextInput"] div[data-baseweb="input"] > div {
    height: 56px !important;
    overflow: hidden !important;
}
            
            /* Final fix: remove right inner line / caret artifact */
div[data-testid="stTextInput"] {
    overflow: visible !important;
}

div[data-testid="stTextInput"] > div {
    height: auto !important;
    min-height: 0 !important;
    max-height: none !important;
    overflow: visible !important;
    border-radius: 20px !important;
}

div[data-testid="stTextInput"] div[data-baseweb="input"] {
    height: 58px !important;
    min-height: 58px !important;
    max-height: 58px !important;
    overflow: hidden !important;
    border-radius: 20px !important;
    background: #2b2c30 !important;
    border: 1px solid #3a3b40 !important;
}

div[data-testid="stTextInput"] div[data-baseweb="input"] > div {
    height: 58px !important;
    min-height: 58px !important;
    max-height: 58px !important;
    overflow: hidden !important;
}

div[data-testid="stTextInput"] input {
    height: 58px !important;
    min-height: 58px !important;
    max-height: 58px !important;
    line-height: 58px !important;
    padding: 0 22px !important;
    border: none !important;
    background: transparent !important;
    box-shadow: none !important;
    outline: none !important;
}

div[data-testid="stTextInput"] div[data-baseweb="input"]:hover {
    background: #303136 !important;
    border-color: #4a4c52 !important;
}

div[data-testid="stTextInput"] div[data-baseweb="input"]:focus-within {
    background: #303136 !important;
    border-color: #5a5c63 !important;
    box-shadow: none !important;
}
            
            /* Hide Streamlit input helper tooltip */
div[data-testid="InputInstructions"],
div[data-testid="stTextInput"] [data-testid="InputInstructions"],
div[data-testid="stTextInput"] small {
    display: none !important;
    visibility: hidden !important;
    opacity: 0 !important;
    height: 0 !important;
}
            
            /* AI answer final polish */
.ai-answer-card {
    margin-top: 8px !important;
    margin-bottom: 24px !important;
    padding: 18px 22px !important;
}

.ai-answer-pill {
    opacity: 0.85;
    font-size: 11.5px !important;
    padding: 5px 10px !important;
}

.ai-answer-text {
    color: #f1f1f3 !important;
    font-weight: 500 !important;
}
            
            /* KPI custom cards */
.kpi-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 18px;
    margin-top: 6px;
    margin-bottom: 28px;
}

.kpi-card {
    background: #2b2c30;
    border: 1px solid #3a3b40;
    border-radius: 24px;
    padding: 20px 22px;
    min-height: 118px;
    box-shadow: 0 12px 30px rgba(0, 0, 0, 0.20);
    transition: background 0.18s ease, border-color 0.18s ease, transform 0.18s ease, box-shadow 0.18s ease;
}

.kpi-card:hover {
    background: #303136;
    border-color: #4a4c52;
    transform: translateY(-2px);
    box-shadow: 0 18px 38px rgba(0, 0, 0, 0.28);
}

.kpi-label {
    color: #a1a1a6;
    font-size: 13px;
    font-weight: 600;
    margin-bottom: 12px;
}

.kpi-value {
    color: #f5f5f7;
    font-size: 34px;
    font-weight: 700;
    letter-spacing: -0.8px;
    line-height: 1;
}

.kpi-subtext {
    color: #8f9299;
    font-size: 12px;
    margin-top: 12px;
}
            
            /* Metric cards final design */
[data-testid="stMetric"] {
    background: linear-gradient(145deg, #2b2c30, #26272b) !important;
    border: 1px solid #3a3b40 !important;
    border-radius: 24px !important;
    padding: 22px 24px !important;
    min-height: 118px !important;
    box-shadow: 0 14px 34px rgba(0, 0, 0, 0.22) !important;
    transition:
        background 0.18s ease,
        border-color 0.18s ease,
        transform 0.18s ease,
        box-shadow 0.18s ease !important;
}

[data-testid="stMetric"]:hover {
    background: #303136 !important;
    border-color: #4a4c52 !important;
    transform: translateY(-3px) !important;
    box-shadow: 0 20px 44px rgba(0, 0, 0, 0.30) !important;
}

[data-testid="stMetricLabel"] {
    color: #a1a1a6 !important;
    font-size: 13px !important;
    font-weight: 600 !important;
}

[data-testid="stMetricValue"] {
    color: #f5f5f7 !important;
    font-size: 34px !important;
    font-weight: 700 !important;
    letter-spacing: -0.8px !important;
}
            
            /* Table section polish */
.section-title {
    font-size: 20px !important;
    font-weight: 700 !important;
    margin-top: 30px !important;
    margin-bottom: 14px !important;
    color: #f5f5f7 !important;
}

/* Streamlit dataframe panel */
[data-testid="stDataFrame"] {
    border-radius: 20px !important;
    overflow: hidden !important;
    border: 1px solid #3a3b40 !important;
    box-shadow: 0 14px 34px rgba(0, 0, 0, 0.22) !important;
    background: #202124 !important;
}

/* Give dataframes breathing room */
[data-testid="stDataFrame"] > div {
    border-radius: 20px !important;
}
            
            /* Tables final polish */
.section-title {
    font-size: 19px !important;
    font-weight: 700 !important;
    margin-top: 34px !important;
    margin-bottom: 12px !important;
    color: #f5f5f7 !important;
}

[data-testid="stDataFrame"] {
    background: #202124 !important;
    border: 1px solid #3a3b40 !important;
    border-radius: 20px !important;
    overflow: hidden !important;
    box-shadow: 0 14px 34px rgba(0, 0, 0, 0.22) !important;
}

[data-testid="stDataFrame"] > div {
    border-radius: 20px !important;
}

/* Reduce harsh selected cell look */
[data-testid="stDataFrame"] [aria-selected="true"] {
    outline: none !important;
    box-shadow: none !important;
}
            
            /* Token analysis card */
.token-analysis-card {
    background: linear-gradient(145deg, #2b2c30, #26272b);
    border: 1px solid #3a3b40;
    border-radius: 22px;
    padding: 18px 20px;
    margin-top: 18px;
    margin-bottom: 24px;
    box-shadow: 0 14px 34px rgba(0, 0, 0, 0.22);
}

.token-analysis-title {
    color: #f5f5f7;
    font-size: 14px;
    font-weight: 700;
    margin-bottom: 14px;
}

.token-analysis-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 14px;
}

.token-analysis-grid div {
    background: #202124;
    border: 1px solid #34363a;
    border-radius: 16px;
    padding: 14px 16px;
}

.token-analysis-grid span {
    display: block;
    color: #8f9299;
    font-size: 12px;
    margin-bottom: 6px;
}

.token-analysis-grid strong {
    display: block;
    color: #f5f5f7;
    font-size: 16px;
    font-weight: 700;
}
            
            /* Token quality colors */
.quality-strong,
.quality-high,
.risk-low {
    color: #9be7b0 !important;
}

.quality-medium,
.risk-medium {
    color: #f5d36b !important;
}

.quality-weak,
.quality-low,
.risk-high {
    color: #ff8a8a !important;
}
            
            /* Token summary card */
.token-summary-card {
    background: linear-gradient(145deg, #2b2c30, #26272b);
    border: 1px solid #3a3b40;
    border-radius: 20px;
    padding: 18px 20px;
    margin-top: -4px;
    margin-bottom: 28px;
    box-shadow: 0 12px 30px rgba(0, 0, 0, 0.18);
}

.token-summary-title {
    color: #f5f5f7;
    font-size: 14px;
    font-weight: 700;
    margin-bottom: 8px;
}

.token-summary-text {
    color: #b4b6bd;
    font-size: 14px;
    line-height: 1.65;
    max-width: 980px;
}
            
            /* Smart Wallet score cards */
.score-grid {
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 14px;
    margin-top: 8px;
    margin-bottom: 28px;
}

.score-card {
    background: linear-gradient(145deg, #2b2c30, #26272b);
    border: 1px solid #3a3b40;
    border-radius: 20px;
    padding: 16px 18px;
    box-shadow: 0 12px 30px rgba(0, 0, 0, 0.20);
    transition: background 0.18s ease, border-color 0.18s ease, transform 0.18s ease;
}

.score-card:hover {
    background: #303136;
    border-color: #4a4c52;
    transform: translateY(-2px);
}

.score-wallet {
    color: #a1a1a6;
    font-size: 12px;
    font-weight: 650;
    margin-bottom: 10px;
}

.score-value {
    color: #f5f5f7;
    font-size: 34px;
    font-weight: 750;
    letter-spacing: -0.8px;
    margin-bottom: 12px;
}

.score-meta {
    display: flex;
    flex-direction: column;
    gap: 4px;
    color: #8f9299;
    font-size: 12px;
}
            
            /* Wallet preview card */
.wallet-preview-card {
    background: linear-gradient(145deg, #2b2c30, #26272b);
    border: 1px solid #3a3b40;
    border-radius: 22px;
    padding: 20px 22px;
    margin-top: 18px;
    margin-bottom: 28px;
    box-shadow: 0 14px 34px rgba(0, 0, 0, 0.22);
}

.wallet-preview-top {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 16px;
    margin-bottom: 18px;
}

.wallet-preview-title {
    color: #f5f5f7;
    font-size: 14px;
    font-weight: 700;
}

.wallet-preview-subtitle {
    color: #8f9299;
    font-size: 12px;
    margin-top: 4px;
}

.wallet-preview-pill {
    color: #d8d8dc;
    background: rgba(255, 255, 255, 0.045);
    border: 1px solid #4a4c52;
    border-radius: 999px;
    padding: 6px 11px;
    font-size: 12px;
    font-weight: 600;
}

.wallet-preview-address {
    color: #f5f5f7;
    font-size: 24px;
    font-weight: 750;
    letter-spacing: -0.5px;
    margin-bottom: 18px;
}

.wallet-preview-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 14px;
}

.wallet-preview-grid div {
    background: #202124;
    border: 1px solid #34363a;
    border-radius: 16px;
    padding: 14px 16px;
}

.wallet-preview-grid span {
    display: block;
    color: #8f9299;
    font-size: 12px;
    margin-bottom: 6px;
}

.wallet-preview-grid strong {
    color: #f5f5f7;
    font-size: 15px;
}
            
            /* Smart wallet lookup spacing */
div[data-testid="stButton"] {
    margin-top: 6px !important;
    margin-bottom: 10px !important;
}

.wallet-preview-card {
    margin-top: 14px !important;
    margin-bottom: 24px !important;
}
            
            /* Copy risk card */
.copy-risk-card {
    background: linear-gradient(145deg, #2b2c30, #26272b);
    border: 1px solid #3a3b40;
    border-radius: 20px;
    padding: 18px 20px;
    margin-top: -10px;
    margin-bottom: 28px;
    box-shadow: 0 12px 30px rgba(0, 0, 0, 0.18);
}

.copy-risk-top {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 16px;
    margin-bottom: 12px;
}

.copy-risk-title {
    color: #f5f5f7;
    font-size: 14px;
    font-weight: 700;
}

.copy-risk-subtitle {
    color: #8f9299;
    font-size: 12px;
    margin-top: 4px;
}

.copy-risk-pill {
    border-radius: 999px;
    padding: 6px 11px;
    font-size: 12px;
    font-weight: 700;
    border: 1px solid #4a4c52;
    background: rgba(255, 255, 255, 0.045);
}

.copy-risk-text {
    color: #b4b6bd;
    font-size: 14px;
    line-height: 1.6;
}
            
            /* Watch signal card */
.watch-signal-card {
    background: linear-gradient(145deg, #2b2c30, #26272b);
    border: 1px solid #3a3b40;
    border-radius: 20px;
    padding: 18px 20px;
    margin-top: -10px;
    margin-bottom: 30px;
    box-shadow: 0 12px 30px rgba(0, 0, 0, 0.18);
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 18px;
}

.watch-signal-title {
    color: #f5f5f7;
    font-size: 14px;
    font-weight: 700;
    margin-bottom: 6px;
}

.watch-signal-text {
    color: #b4b6bd;
    font-size: 14px;
    line-height: 1.6;
}

.watch-signal-pill {
    border-radius: 999px;
    padding: 8px 14px;
    font-size: 13px;
    font-weight: 750;
    border: 1px solid #4a4c52;
    background: rgba(255, 255, 255, 0.045);
}

.signal-watch {
    color: #9be7b0 !important;
}

.signal-wait {
    color: #f5d36b !important;
}

.signal-avoid {
    color: #ff8a8a !important;
}
            
            /* Decision engine metric polish */
[data-testid="stMetric"] {
    background: linear-gradient(145deg, #2b2c30, #242529) !important;
    border: 1px solid #3a3b40 !important;
    border-radius: 22px !important;
    padding: 20px 22px !important;
    box-shadow: 0 16px 36px rgba(0, 0, 0, 0.24) !important;
}

[data-testid="stMetric"]:hover {
    background: #303136 !important;
    border-color: #4a4c52 !important;
    transform: translateY(-2px) !important;
}

[data-testid="stCaptionContainer"] {
    color: #a8abb2 !important;
    font-size: 13px !important;
    line-height: 1.55 !important;
}

.section-title {
    margin-top: 34px !important;
}
            
            /* Compact dashboard mode */
.block-container {
    padding-top: 2.4rem !important;
    padding-left: 3.4rem !important;
    padding-right: 3.4rem !important;
    max-width: 1320px !important;
}

h1 {
    font-size: 34px !important;
}

.section-title {
    font-size: 17px !important;
    margin-top: 26px !important;
    margin-bottom: 10px !important;
}

[data-testid="stMetric"] {
    min-height: 92px !important;
    padding: 16px 18px !important;
    border-radius: 18px !important;
}

[data-testid="stMetricValue"] {
    font-size: 27px !important;
}

[data-testid="stMetricLabel"] {
    font-size: 12px !important;
}

.wallet-preview-card,
.token-analysis-card {
    padding: 16px 18px !important;
    border-radius: 18px !important;
    margin-bottom: 20px !important;
}

.wallet-preview-address {
    font-size: 20px !important;
    margin-bottom: 14px !important;
}

.wallet-preview-grid div,
.token-analysis-grid div {
    padding: 12px 14px !important;
    border-radius: 14px !important;
}

[data-testid="stDataFrame"] {
    border-radius: 16px !important;
}
            
            /* Compact final dashboard polish */
.block-container {
    padding-top: 2.2rem !important;
    padding-left: 3.2rem !important;
    padding-right: 3.2rem !important;
    max-width: 1280px !important;
}

h1 {
    font-size: 32px !important;
    margin-bottom: 0.4rem !important;
}

.stCaptionContainer {
    font-size: 13px !important;
}

.section-title {
    font-size: 16px !important;
    margin-top: 24px !important;
    margin-bottom: 9px !important;
}

.wallet-preview-card,
.token-analysis-card {
    padding: 14px 16px !important;
    border-radius: 17px !important;
    margin-top: 12px !important;
    margin-bottom: 18px !important;
}

.wallet-preview-address {
    font-size: 18px !important;
    margin-bottom: 12px !important;
}

.wallet-preview-grid {
    gap: 10px !important;
}

.wallet-preview-grid div,
.token-analysis-grid div {
    padding: 10px 12px !important;
    border-radius: 13px !important;
}

[data-testid="stMetric"] {
    min-height: 82px !important;
    padding: 13px 15px !important;
    border-radius: 16px !important;
}

[data-testid="stMetricValue"] {
    font-size: 24px !important;
    line-height: 1.1 !important;
}

[data-testid="stMetricLabel"] {
    font-size: 11.5px !important;
}

[data-testid="stCaptionContainer"] {
    font-size: 12px !important;
    line-height: 1.45 !important;
}

[data-testid="stDataFrame"] {
    border-radius: 14px !important;
}
            
            /* Wallet insight card */
.wallet-insight-card {
    background: linear-gradient(145deg, #25262a, #222326);
    border: 1px solid #3a3b40;
    border-radius: 16px;
    padding: 14px 16px;
    margin-top: 12px;
    margin-bottom: 22px;
    box-shadow: 0 10px 24px rgba(0, 0, 0, 0.18);
}

.wallet-insight-title {
    color: #f5f5f7;
    font-size: 13px;
    font-weight: 750;
    margin-bottom: 10px;
}

.wallet-insight-row {
    display: grid;
    grid-template-columns: 160px 1fr;
    gap: 12px;
    margin-top: 8px;
}

.wallet-insight-row span {
    color: #8f9299;
    font-size: 12px;
}

.wallet-insight-row strong {
    color: #d8d8dc;
    font-size: 13px;
    font-weight: 600;
    line-height: 1.45;
}
            
            /* Signal card */
.signal-card {
    background: linear-gradient(145deg, #242834, #1f2330);
    border: 1px solid #34384a;
    border-radius: 16px;
    padding: 13px 15px;
    min-height: 82px;
    box-shadow: 0 10px 24px rgba(0, 0, 0, 0.18);
}

.signal-label {
    color: #9aa3b2;
    font-size: 11.5px;
    margin-bottom: 6px;
}

.signal-value {
    font-size: 22px;
    font-weight: 800;
    line-height: 1.1;
    margin-bottom: 5px;
}

.signal-desc {
    color: #c9ced8;
    font-size: 11.5px;
    line-height: 1.35;
}

/* Signal colors */
.signal-monitor {
    border-color: rgba(255, 166, 77, 0.65);
    background: linear-gradient(145deg, rgba(255, 140, 60, 0.20), #1f2330);
}

.signal-monitor .signal-value {
    color: #ffb357;
}

.signal-watch {
    border-color: rgba(255, 214, 102, 0.50);
    background: linear-gradient(145deg, rgba(255, 214, 102, 0.13), #1f2330);
}

.signal-watch .signal-value {
    color: #ffd666;
}

.signal-needs {
    border-color: rgba(120, 160, 255, 0.40);
    background: linear-gradient(145deg, rgba(120, 160, 255, 0.11), #1f2330);
}

.signal-needs .signal-value {
    color: #a9c1ff;
}

.signal-ignore {
    border-color: rgba(255, 120, 120, 0.40);
    background: linear-gradient(145deg, rgba(255, 120, 120, 0.11), #1f2330);
}

.signal-ignore .signal-value {
    color: #ff9b9b;
}
            
            /* Watchlist cards */
.watchlist-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
    gap: 14px;
    margin-top: 18px;
}

.watchlist-card {
    background: linear-gradient(145deg, #25262a, #202126);
    border: 1px solid #3a3b40;
    border-radius: 18px;
    padding: 16px 18px;
    box-shadow: 0 12px 28px rgba(0, 0, 0, 0.18);
}

.watchlist-top {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 12px;
    margin-bottom: 14px;
}

.watchlist-wallet {
    color: #f5f5f7;
    font-size: 17px;
    font-weight: 800;
}

.watchlist-pill {
    padding: 6px 10px;
    border-radius: 999px;
    font-size: 12px;
    font-weight: 800;
}

.watchlist-monitor {
    color: #ffb357;
    border: 1px solid rgba(255, 166, 77, 0.55);
    background: rgba(255, 166, 77, 0.10);
}

.watchlist-watch {
    color: #ffd666;
    border: 1px solid rgba(255, 214, 102, 0.45);
    background: rgba(255, 214, 102, 0.10);
}

.watchlist-meta {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 10px;
    margin-top: 12px;
}

.watchlist-meta div {
    background: rgba(255,255,255,0.035);
    border: 1px solid #34363b;
    border-radius: 13px;
    padding: 10px 11px;
}

.watchlist-meta span {
    display: block;
    color: #8f9299;
    font-size: 11px;
    margin-bottom: 5px;
}

.watchlist-meta strong {
    color: #f5f5f7;
    font-size: 15px;
}

.watchlist-address {
    color: #9aa0aa;
    font-size: 12px;
    word-break: break-all;
    margin-top: 10px;
}
            
            .watchlist-added-card {
    background: linear-gradient(145deg, rgba(80, 220, 140, 0.14), #202126);
    border: 1px solid rgba(80, 220, 140, 0.35);
    border-radius: 16px;
    padding: 13px 16px;
    margin-top: 12px;
    margin-bottom: 16px;
}

.watchlist-added-card strong {
    display: block;
    color: #9bffbd;
    font-size: 14px;
    margin-bottom: 4px;
}

.watchlist-added-card span {
    color: #b9c0c8;
    font-size: 12px;
}
            
            /* Wallet verdict */
.wallet-verdict-card {
    background: linear-gradient(145deg, rgba(255, 166, 77, 0.10), #202126);
    border: 1px solid rgba(255, 166, 77, 0.35);
    border-radius: 18px;
    padding: 16px 18px;
    margin-top: 16px;
    margin-bottom: 18px;
    box-shadow: 0 14px 32px rgba(0, 0, 0, 0.20);
}

.wallet-verdict-top {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 16px;
    margin-bottom: 14px;
}

.wallet-verdict-title {
    color: #f5f5f7;
    font-size: 16px;
    font-weight: 850;
}

.wallet-verdict-subtitle {
    color: #9aa0aa;
    font-size: 12px;
    margin-top: 4px;
}

.wallet-verdict-badge {
    color: #ffb357;
    border: 1px solid rgba(255, 166, 77, 0.55);
    background: rgba(255, 166, 77, 0.12);
    padding: 7px 11px;
    border-radius: 999px;
    font-size: 12px;
    font-weight: 850;
    white-space: nowrap;
}

.wallet-verdict-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 12px;
}

.wallet-verdict-item {
    background: rgba(255,255,255,0.035);
    border: 1px solid #34363b;
    border-radius: 14px;
    padding: 12px 13px;
}

.wallet-verdict-item span {
    display: block;
    color: #8f9299;
    font-size: 11px;
    margin-bottom: 6px;
}

.wallet-verdict-item strong {
    display: block;
    color: #f5f5f7;
    font-size: 14px;
    line-height: 1.35;
}

.wallet-verdict-note {
    color: #c8ccd2;
    font-size: 12px;
    margin-top: 13px;
    line-height: 1.45;
}
            
            /* Best candidate card */
.best-candidate-card {
    background: linear-gradient(145deg, rgba(80, 160, 255, 0.12), #202126);
    border: 1px solid rgba(80, 160, 255, 0.35);
    border-radius: 18px;
    padding: 16px 18px;
    margin-top: 16px;
    margin-bottom: 18px;
    box-shadow: 0 14px 32px rgba(0, 0, 0, 0.22);
}

.best-candidate-card.avoid {
    background: linear-gradient(145deg, rgba(255, 110, 110, 0.13), #202126);
    border-color: rgba(255, 110, 110, 0.35);
}

.best-candidate-card.watch {
    background: linear-gradient(145deg, rgba(255, 166, 77, 0.13), #202126);
    border-color: rgba(255, 166, 77, 0.42);
}

.best-candidate-top {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 16px;
    margin-bottom: 14px;
}

.best-candidate-title {
    color: #f5f5f7;
    font-size: 16px;
    font-weight: 850;
}

.best-candidate-subtitle {
    color: #9aa0aa;
    font-size: 12px;
    margin-top: 4px;
}

.best-candidate-pill {
    border-radius: 999px;
    padding: 7px 12px;
    font-size: 12px;
    font-weight: 850;
    color: #9fc5ff;
    border: 1px solid rgba(80, 160, 255, 0.45);
    background: rgba(80, 160, 255, 0.10);
}

.best-candidate-card.avoid .best-candidate-pill {
    color: #ff9b9b;
    border-color: rgba(255, 110, 110, 0.45);
    background: rgba(255, 110, 110, 0.10);
}

.best-candidate-card.watch .best-candidate-pill {
    color: #ffb357;
    border-color: rgba(255, 166, 77, 0.55);
    background: rgba(255, 166, 77, 0.12);
}

.best-candidate-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 10px;
    margin-top: 12px;
}

.best-candidate-item {
    background: rgba(255,255,255,0.035);
    border: 1px solid #34363b;
    border-radius: 14px;
    padding: 11px 12px;
}

.best-candidate-item span {
    display: block;
    color: #8f9299;
    font-size: 11px;
    margin-bottom: 5px;
}

.best-candidate-item strong {
    display: block;
    color: #f5f5f7;
    font-size: 13px;
    line-height: 1.35;
}

.best-candidate-note {
    color: #c8ccd2;
    font-size: 12px;
    margin-top: 12px;
    line-height: 1.45;
}
            
            /* Token watchlist cards */
.token-watchlist-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(340px, 1fr));
    gap: 14px;
    margin-top: 18px;
    margin-bottom: 18px;
}

.token-watchlist-card {
    background: linear-gradient(145deg, #25262a, #202126);
    border: 1px solid #3a3b40;
    border-radius: 18px;
    padding: 16px 18px;
    box-shadow: 0 12px 28px rgba(0, 0, 0, 0.20);
}

.token-watchlist-card.avoid {
    border-color: rgba(255, 110, 110, 0.35);
    background: linear-gradient(145deg, rgba(255, 110, 110, 0.10), #202126);
}

.token-watchlist-card.watch {
    border-color: rgba(255, 166, 77, 0.42);
    background: linear-gradient(145deg, rgba(255, 166, 77, 0.12), #202126);
}

.token-watchlist-top {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 12px;
    margin-bottom: 14px;
}

.token-watchlist-symbol {
    color: #f5f5f7;
    font-size: 20px;
    font-weight: 850;
}

.token-watchlist-name {
    color: #9aa0aa;
    font-size: 12px;
    margin-top: 3px;
}

.token-watchlist-pill {
    border-radius: 999px;
    padding: 6px 10px;
    font-size: 12px;
    font-weight: 850;
    border: 1px solid #4a4c52;
    color: #d8d8dc;
    background: rgba(255,255,255,0.045);
}

.token-watchlist-card.avoid .token-watchlist-pill {
    color: #ff9b9b;
    border-color: rgba(255, 110, 110, 0.45);
    background: rgba(255, 110, 110, 0.10);
}

.token-watchlist-card.watch .token-watchlist-pill {
    color: #ffb357;
    border-color: rgba(255, 166, 77, 0.55);
    background: rgba(255, 166, 77, 0.12);
}

.token-watchlist-meta {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 10px;
    margin-bottom: 12px;
}

.token-watchlist-meta div {
    background: rgba(255,255,255,0.035);
    border: 1px solid #34363b;
    border-radius: 13px;
    padding: 10px 11px;
}

.token-watchlist-meta span {
    display: block;
    color: #8f9299;
    font-size: 11px;
    margin-bottom: 5px;
}

.token-watchlist-meta strong {
    color: #f5f5f7;
    font-size: 13px;
}

.token-watchlist-reason {
    color: #c8ccd2;
    font-size: 12px;
    line-height: 1.45;
    margin-top: 10px;
}

.token-watchlist-mint {
    color: #8f9299;
    font-size: 11px;
    word-break: break-all;
    margin-top: 10px;
}

.token-watchlist-source {
    color: #8f9299;
    font-size: 11px;
    margin-top: 8px;
}
            
            /* Swapped token cards */
.swapped-token-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
    gap: 14px;
    margin-top: 14px;
    margin-bottom: 18px;
}

.swapped-token-card {
    background: linear-gradient(145deg, #25262a, #202126);
    border: 1px solid #393b40;
    border-radius: 18px;
    padding: 15px 17px;
    box-shadow: 0 12px 26px rgba(0, 0, 0, 0.20);
}

.swapped-token-top {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 12px;
    margin-bottom: 12px;
}

.swapped-token-symbol {
    color: #f5f5f7;
    font-size: 19px;
    font-weight: 850;
}

.swapped-token-name {
    color: #9aa0aa;
    font-size: 12px;
    margin-top: 3px;
}

.swapped-token-pill {
    color: #ffb357;
    border: 1px solid rgba(255, 166, 77, 0.45);
    background: rgba(255, 166, 77, 0.10);
    border-radius: 999px;
    padding: 6px 10px;
    font-size: 11px;
    font-weight: 850;
}

.swapped-token-mint {
    color: #8f9299;
    font-size: 11px;
    word-break: break-all;
    background: rgba(255,255,255,0.035);
    border: 1px solid #34363b;
    border-radius: 12px;
    padding: 10px 11px;
}
            
            /* Auto review cards */
.auto-review-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
    gap: 14px;
    margin-top: 16px;
    margin-bottom: 18px;
}

.auto-review-card {
    background: linear-gradient(145deg, #25262a, #202126);
    border: 1px solid #3a3b40;
    border-radius: 18px;
    padding: 16px 18px;
    box-shadow: 0 12px 28px rgba(0,0,0,0.20);
}

.auto-review-card.avoid {
    border-color: rgba(255, 110, 110, 0.38);
    background: linear-gradient(145deg, rgba(255, 110, 110, 0.10), #202126);
}

.auto-review-card.watch {
    border-color: rgba(255, 166, 77, 0.45);
    background: linear-gradient(145deg, rgba(255, 166, 77, 0.12), #202126);
}

.auto-review-top {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 12px;
    margin-bottom: 13px;
}

.auto-review-token {
    color: #f5f5f7;
    font-size: 20px;
    font-weight: 850;
}

.auto-review-name {
    color: #9aa0aa;
    font-size: 12px;
    margin-top: 3px;
}

.auto-review-pill {
    border-radius: 999px;
    padding: 6px 10px;
    font-size: 12px;
    font-weight: 850;
    color: #d8d8dc;
    border: 1px solid #4a4c52;
    background: rgba(255,255,255,0.045);
}

.auto-review-card.avoid .auto-review-pill {
    color: #ff9b9b;
    border-color: rgba(255, 110, 110, 0.45);
    background: rgba(255, 110, 110, 0.10);
}

.auto-review-card.watch .auto-review-pill {
    color: #ffb357;
    border-color: rgba(255, 166, 77, 0.55);
    background: rgba(255, 166, 77, 0.12);
}

.auto-review-meta {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 10px;
    margin-bottom: 12px;
}

.auto-review-meta div {
    background: rgba(255,255,255,0.035);
    border: 1px solid #34363b;
    border-radius: 13px;
    padding: 10px 11px;
}

.auto-review-meta span {
    display: block;
    color: #8f9299;
    font-size: 11px;
    margin-bottom: 5px;
}

.auto-review-meta strong {
    color: #f5f5f7;
    font-size: 13px;
}

.auto-review-reason {
    color: #c8ccd2;
    font-size: 12px;
    line-height: 1.45;
}

.auto-review-mint {
    color: #8f9299;
    font-size: 11px;
    word-break: break-all;
    margin-top: 10px;
}

/* Live pair cards */
.pair-card-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
    gap: 14px;
    margin-top: 16px;
    margin-bottom: 18px;
}

.pair-card {
    background: linear-gradient(145deg, #25262a, #202126);
    border: 1px solid #3a3b40;
    border-radius: 18px;
    padding: 16px 18px;
    box-shadow: 0 12px 28px rgba(0,0,0,0.20);
}

.pair-card-top {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 12px;
    margin-bottom: 13px;
}

.pair-card-title {
    color: #f5f5f7;
    font-size: 20px;
    font-weight: 850;
}

.pair-card-subtitle {
    color: #9aa0aa;
    font-size: 12px;
    margin-top: 3px;
}

.pair-card-pill {
    color: #9fc5ff;
    border: 1px solid rgba(80,160,255,0.45);
    background: rgba(80,160,255,0.10);
    border-radius: 999px;
    padding: 6px 10px;
    font-size: 12px;
    font-weight: 850;
}

.pair-card-meta {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 10px;
}

.pair-card-meta div {
    background: rgba(255,255,255,0.035);
    border: 1px solid #34363b;
    border-radius: 13px;
    padding: 10px 11px;
}

.pair-card-meta span {
    display: block;
    color: #8f9299;
    font-size: 11px;
    margin-bottom: 5px;
}

.pair-card-meta strong {
    color: #f5f5f7;
    font-size: 13px;
}
            
.discovery-card + div[data-testid="stHorizontalBlock"] {
    margin-top: -8px !important;
    margin-bottom: 10px !important;
}
            



/* Watchlist movement details */
.watchlist-card {
    margin-bottom: 14px;
}

.watchlist-meta {
    grid-template-columns: repeat(4, 1fr) !important;
}

.watchlist-movement-title {
    color: #f5f5f7;
    font-size: 12px;
    font-weight: 800;
    margin-top: 14px;
    margin-bottom: 8px;
    letter-spacing: 0.2px;
}

.watchlist-movement-grid {
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 10px;
    margin-top: 8px;
}

.watchlist-movement-grid div {
    background: rgba(255,255,255,0.035);
    border: 1px solid #34363b;
    border-radius: 13px;
    padding: 10px 11px;
}

.watchlist-movement-grid span {
    display: block;
    color: #8f9299;
    font-size: 11px;
    margin-bottom: 5px;
}

.watchlist-movement-grid strong {
    display: block;
    color: #f5f5f7;
    font-size: 13px;
    line-height: 1.35;
}

.watchlist-movement-grid em {
    display: block;
    font-style: normal;
    font-size: 12px;
    margin-top: 4px;
    font-weight: 800;
}

.movement-up {
    color: #9be7b0 !important;
}

.movement-down {
    color: #ff8a8a !important;
}

.movement-flat {
    color: #a8abb2 !important;
}

.watchlist-latest {
    margin-top: 10px;
    background: rgba(255,255,255,0.035);
    border: 1px solid #34363b;
    border-radius: 13px;
    padding: 10px 11px;
}

.watchlist-latest span {
    display: block;
    color: #8f9299;
    font-size: 11px;
    margin-bottom: 5px;
}

.watchlist-latest strong {
    color: #f5f5f7;
    font-size: 12px;
    line-height: 1.45;
    word-break: break-word;
}

.watchlist-change-pill {
    color: #f5d36b;
    border: 1px solid rgba(245, 211, 107, 0.35);
    background: rgba(245, 211, 107, 0.09);
    border-radius: 999px;
    padding: 6px 10px;
    font-size: 12px;
    font-weight: 850;
    white-space: nowrap;
}


/* Watchlist radar and movement upgrade */
.watchlist-radar {
    border-radius: 22px;
    padding: 18px 20px;
    margin-top: 18px;
    margin-bottom: 18px;
    border: 1px solid #3a3b40;
    background: linear-gradient(145deg, #25262a, #202126);
    box-shadow: 0 16px 38px rgba(0, 0, 0, 0.24);
}

.watchlist-radar.radar-hot {
    border-color: rgba(255, 120, 80, 0.55);
    background: linear-gradient(145deg, rgba(255, 120, 80, 0.14), #202126);
}

.watchlist-radar.radar-moving {
    border-color: rgba(245, 211, 107, 0.45);
    background: linear-gradient(145deg, rgba(245, 211, 107, 0.11), #202126);
}

.watchlist-radar.radar-calm {
    border-color: rgba(90, 180, 255, 0.35);
    background: linear-gradient(145deg, rgba(90, 180, 255, 0.09), #202126);
}

.watchlist-radar-top {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 14px;
    margin-bottom: 14px;
}

.watchlist-radar-title {
    color: #f5f5f7;
    font-size: 18px;
    font-weight: 850;
}

.watchlist-radar-subtitle {
    color: #a8abb2;
    font-size: 12px;
    margin-top: 4px;
}

.watchlist-radar-live {
    color: #9be7b0;
    border: 1px solid rgba(80, 220, 140, 0.42);
    background: rgba(80, 220, 140, 0.10);
    padding: 7px 11px;
    border-radius: 999px;
    font-size: 11px;
    font-weight: 850;
    white-space: nowrap;
}

.watchlist-radar-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 10px;
}

.watchlist-radar-grid div {
    background: rgba(255,255,255,0.04);
    border: 1px solid #34363b;
    border-radius: 14px;
    padding: 11px 12px;
}

.watchlist-radar-grid span {
    display: block;
    color: #8f9299;
    font-size: 11px;
    margin-bottom: 6px;
}

.watchlist-radar-grid strong {
    display: block;
    color: #f5f5f7;
    font-size: 15px;
    font-weight: 850;
    line-height: 1.25;
}

.watchlist-card.hot-card {
    border-color: rgba(255, 120, 80, 0.55);
    background: linear-gradient(145deg, rgba(255, 120, 80, 0.10), #202126);
}

.watchlist-card.moving-card {
    border-color: rgba(245, 211, 107, 0.42);
    background: linear-gradient(145deg, rgba(245, 211, 107, 0.08), #202126);
}

.watchlist-alert-row {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    margin-top: 10px;
    margin-bottom: 10px;
}

.wallet-alert-pill {
    border-radius: 999px;
    padding: 6px 10px;
    font-size: 11px;
    font-weight: 850;
    white-space: nowrap;
}

.movement-hot {
    color: #ffb357 !important;
    border: 1px solid rgba(255, 120, 80, 0.60);
    background: rgba(255, 120, 80, 0.14);
}

.movement-up-badge {
    color: #9be7b0 !important;
    border: 1px solid rgba(80, 220, 140, 0.50);
    background: rgba(80, 220, 140, 0.11);
}

.movement-down-badge {
    color: #ff8a8a !important;
    border: 1px solid rgba(255, 120, 120, 0.50);
    background: rgba(255, 120, 120, 0.11);
}

.movement-flat-badge {
    color: #a8abb2 !important;
    border: 1px solid rgba(168, 171, 178, 0.35);
    background: rgba(168, 171, 178, 0.07);
}

.watchlist-explain {
    margin-top: 10px;
    color: #c8ccd2;
    font-size: 12px;
    line-height: 1.45;
    padding: 10px 12px;
    border-radius: 13px;
    border: 1px solid rgba(255,255,255,0.08);
    background: rgba(255,255,255,0.035);
}

.watchlist-value-pair {
    display: block;
    color: #8f9299;
    font-size: 11px;
    margin-top: 4px;
}


/* Compact interface pass */
.block-container {
    padding-top: 2.2rem !important;
    padding-left: 3.4rem !important;
    padding-right: 3.4rem !important;
    max-width: 1320px !important;
}

h1 {
    font-size: 32px !important;
    margin-bottom: 0.4rem !important;
}

.section-title {
    margin-top: 20px !important;
    margin-bottom: 9px !important;
    font-size: 17px !important;
}

.stCaptionContainer {
    font-size: 12px !important;
}

[data-testid="stMetric"] {
    min-height: 86px !important;
    padding: 14px 16px !important;
    border-radius: 18px !important;
}

[data-testid="stMetricValue"] {
    font-size: 25px !important;
}

[data-testid="stMetricLabel"] {
    font-size: 11px !important;
}

.stButton button {
    padding: 0.48rem 0.95rem !important;
    min-height: 36px !important;
    font-size: 12px !important;
}

div[data-baseweb="select"] > div,
.stTextArea textarea,
div[data-testid="stTextInput"] div[data-baseweb="input"] {
    min-height: 42px !important;
    border-radius: 14px !important;
}

.watchlist-radar {
    padding: 14px 16px !important;
    border-radius: 18px !important;
    margin-bottom: 14px !important;
}

.watchlist-radar-grid {
    gap: 9px !important;
}

.watchlist-radar-grid div {
    padding: 9px 10px !important;
    border-radius: 12px !important;
}

.watchlist-card {
    padding: 13px 15px !important;
    border-radius: 17px !important;
    margin-top: 10px !important;
}

.watchlist-meta,
.watchlist-movement-grid,
.watchlist-current-grid {
    gap: 8px !important;
}

.watchlist-meta div,
.watchlist-movement-grid div,
.watchlist-current-grid div {
    padding: 8px 9px !important;
    border-radius: 11px !important;
}

.movement-up,
.positive-number {
    color: #8dffb0 !important;
}

.movement-down,
.negative-number {
    color: #ff8f9b !important;
}

.movement-flat {
    color: #b7bbc3 !important;
}


/* -----------------------------
   HUMAN-FIRST COMPACT UI OVERRIDES
----------------------------- */
.block-container { max-width: 1320px !important; padding-top: 2.1rem !important; padding-left: 3.2rem !important; padding-right: 3.2rem !important; }
h1 { font-size: 30px !important; margin-bottom: 0.25rem !important; }
.stCaptionContainer, .stMarkdown p { line-height: 1.35 !important; }
.section-title { font-size: 16px !important; margin-top: 18px !important; margin-bottom: 9px !important; }
.stButton button { min-height: 34px !important; height: 34px !important; padding: 0.35rem 0.85rem !important; font-size: 12.5px !important; box-shadow: none !important; }
[data-testid="stMetric"] { min-height: 82px !important; padding: 13px 15px !important; border-radius: 16px !important; }
[data-testid="stMetricValue"] { font-size: 23px !important; }
[data-testid="stMetricLabel"] { font-size: 11.5px !important; }
div[data-baseweb="select"] > div, .stTextInput div[data-baseweb="input"] { min-height: 42px !important; border-radius: 13px !important; }
.human-topbar { background: linear-gradient(145deg, rgba(43,44,48,0.96), rgba(31,33,38,0.96)); border: 1px solid rgba(255,255,255,0.09); border-radius: 18px; padding: 13px 15px; margin: 8px 0 12px 0; box-shadow: 0 10px 26px rgba(0,0,0,0.18); }
.human-topbar-row { display:flex; justify-content:space-between; align-items:center; gap:12px; }
.human-title { color:#f5f5f7; font-size:16px; font-weight:850; letter-spacing:-0.2px; }
.human-subtitle { color:#9ca0a8; font-size:12px; margin-top:3px; }
.human-pill { border-radius:999px; padding:5px 9px; font-size:10.5px; font-weight:850; white-space:nowrap; border:1px solid rgba(255,255,255,0.16); color:#d8d8dc; background:rgba(255,255,255,0.06); }
.human-pill-green { color:#9be7b0; border-color:rgba(90,220,140,0.45); background:rgba(90,220,140,0.10); }
.human-pill-yellow { color:#ffd36e; border-color:rgba(255,210,90,0.45); background:rgba(255,210,90,0.10); }
.human-pill-red { color:#ff9b9b; border-color:rgba(255,110,110,0.45); background:rgba(255,110,110,0.10); }
.human-pill-blue { color:#9fc5ff; border-color:rgba(100,160,255,0.45); background:rgba(100,160,255,0.10); }
.human-summary-grid { display:grid; grid-template-columns: repeat(6, 1fr); gap:8px; margin-top:11px; }
.human-summary-grid div, .human-mini div, .human-deltas div { background:rgba(255,255,255,0.04); border:1px solid rgba(255,255,255,0.075); border-radius:12px; padding:8px 9px; }
.human-summary-grid span, .human-mini span, .human-deltas span { display:block; color:#8f9299; font-size:10.2px; margin-bottom:4px; }
.human-summary-grid strong, .human-mini strong, .human-deltas strong { display:block; color:#f5f5f7; font-size:12.8px; font-weight:850; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.human-card { background:linear-gradient(145deg, rgba(38,39,43,0.98), rgba(30,31,36,0.98)); border:1px solid rgba(255,255,255,0.09); border-radius:18px; padding:13px 15px; margin:10px 0 5px 0; box-shadow:0 10px 26px rgba(0,0,0,0.18); }
.human-card-hot { border-color:rgba(255,180,80,0.52); background:linear-gradient(145deg, rgba(255,160,70,0.13), rgba(30,31,36,0.98)); }
.human-card-up { border-color:rgba(100,220,140,0.34); background:linear-gradient(145deg, rgba(80,210,130,0.09), rgba(30,31,36,0.98)); }
.human-card-down { border-color:rgba(255,110,110,0.38); background:linear-gradient(145deg, rgba(255,90,100,0.09), rgba(30,31,36,0.98)); }
.human-card-top { display:flex; justify-content:space-between; align-items:flex-start; gap:12px; margin-bottom:9px; }
.human-wallet { color:#f5f5f7; font-size:15.5px; font-weight:850; }
.human-address, .human-meta-line { color:#8f9299; font-size:10.8px; margin-top:3px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; max-width:850px; }
.human-deltas { display:grid; grid-template-columns: repeat(5, 1fr); gap:8px; margin-bottom:8px; }
.human-mini { display:grid; grid-template-columns: repeat(4, 1fr); gap:8px; margin-bottom:8px; }
.human-latest { background:rgba(255,255,255,0.035); border:1px solid rgba(255,255,255,0.07); border-radius:12px; padding:8px 10px; color:#d8d8dc; font-size:11px; line-height:1.35; overflow-wrap:anywhere; }
.human-latest span { display:block; color:#8f9299; font-size:10.2px; margin-bottom:3px; }
.human-action-gap { height:0px; margin-top:-39px; margin-bottom:20px; }
.movement-up { color:#9be7b0 !important; }
.movement-down { color:#ff9b9b !important; }
.movement-flat { color:#a8abb2 !important; }
.watchlist-card, .token-watchlist-card, .recent-card { padding:13px 15px !important; margin-top:10px !important; border-radius:18px !important; }
.watchlist-meta, .watchlist-movement-grid, .token-watchlist-meta { gap:8px !important; }
.watchlist-meta div, .watchlist-movement-grid div, .token-watchlist-meta div { padding:8px 9px !important; border-radius:12px !important; }
@media (max-width: 1100px) { .human-summary-grid { grid-template-columns: repeat(3, 1fr); } .human-deltas { grid-template-columns: repeat(3, 1fr); } .human-mini { grid-template-columns: repeat(2, 1fr); } .block-container { padding-left:1.3rem !important; padding-right:1.3rem !important; } }

/* Story charts and final UX cleanup */
.story-callout { background: rgba(155,231,176,0.08); border: 1px solid rgba(155,231,176,0.18); border-radius: 14px; padding: 10px 12px; margin: 8px 0 12px 0; color: #e8f7ec; font-size: 12px; line-height: 1.45; }
.settings-grid { display:grid; grid-template-columns: repeat(3, 1fr); gap:10px; margin-top:10px; margin-bottom:14px; }
.settings-card { background: rgba(255,255,255,0.035); border:1px solid rgba(255,255,255,0.075); border-radius:14px; padding:12px 13px; }
.settings-card span { display:block; color:#8f9299; font-size:11px; margin-bottom:5px; }
.settings-card strong { color:#f5f5f7; font-size:14px; }
@media (max-width: 1100px) { .settings-grid { grid-template-columns: 1fr; } }


/* Pinned wallets + Solscan-style story charts */
.pin-badge {
    color: #fef3c7;
    background: rgba(245, 158, 11, 0.14);
    border: 1px solid rgba(245, 158, 11, 0.42);
    border-radius: 999px;
    padding: 4px 9px;
    font-size: 11px;
    font-weight: 800;
    margin-left: 8px;
}
.wallet-story-box {
    border-radius: 16px;
    padding: 13px 15px;
    margin: 8px 0 14px 0;
    border: 1px solid rgba(255,255,255,0.10);
}
.wallet-story-title {
    color: #f5f5f7;
    font-size: 13px;
    font-weight: 800;
    margin-bottom: 4px;
}
.wallet-story-text {
    color: #d1d5db;
    font-size: 13px;
    line-height: 1.45;
}
.story-good {
    background: linear-gradient(135deg, rgba(34,197,94,0.13), rgba(16,185,129,0.06));
    border-color: rgba(34,197,94,0.30);
}
.story-warn {
    background: linear-gradient(135deg, rgba(248,113,113,0.13), rgba(245,158,11,0.06));
    border-color: rgba(248,113,113,0.30);
}
.story-neutral {
    background: linear-gradient(135deg, rgba(167,139,250,0.12), rgba(75,85,99,0.06));
    border-color: rgba(167,139,250,0.24);
}
.pinned-radar {
    background: linear-gradient(145deg, rgba(245,158,11,0.12), rgba(38,39,43,0.92));
    border: 1px solid rgba(245,158,11,0.36);
    border-radius: 20px;
    padding: 14px 16px;
    margin: 12px 0 14px 0;
}
.pinned-radar-title {
    color: #fef3c7;
    font-size: 15px;
    font-weight: 850;
    margin-bottom: 4px;
}
.pinned-radar-subtitle {
    color: #c7c7cc;
    font-size: 12px;
    margin-bottom: 12px;
}
.pinned-grid {
    display: grid;
    grid-template-columns: repeat(5, minmax(0, 1fr));
    gap: 9px;
}
.pinned-grid div {
    background: rgba(255,255,255,0.045);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 13px;
    padding: 9px 10px;
}
.pinned-grid span {
    display: block;
    color: #9ca3af;
    font-size: 11px;
    margin-bottom: 5px;
}
.pinned-grid strong {
    display: block;
    color: #f5f5f7;
    font-size: 13px;
}


.trade-buy {
    color: #86efac !important;
    background: rgba(34, 197, 94, 0.12);
    border: 1px solid rgba(34, 197, 94, 0.35);
    border-radius: 999px;
    padding: 2px 8px;
    font-weight: 850;
}

.trade-sell {
    color: #fca5a5 !important;
    background: rgba(239, 68, 68, 0.12);
    border: 1px solid rgba(239, 68, 68, 0.35);
    border-radius: 999px;
    padding: 2px 8px;
    font-weight: 850;
}

.trade-rotate {
    color: #fbbf24 !important;
    background: rgba(245, 158, 11, 0.12);
    border: 1px solid rgba(245, 158, 11, 0.35);
    border-radius: 999px;
    padding: 2px 8px;
    font-weight: 850;
}

.trade-neutral {
    color: #d1d5db !important;
    background: rgba(156, 163, 175, 0.10);
    border: 1px solid rgba(156, 163, 175, 0.20);
    border-radius: 999px;
    padding: 2px 8px;
    font-weight: 750;
}

</style>
""", unsafe_allow_html=True)


# -----------------------------
# Helper functions for table colors
# -----------------------------
def color_score(value):
    if value >= 80:
        return "background-color: #d8f3dc; color: #1b4332;"
    if value >= 60:
        return "background-color: #fff3bf; color: #5f3f00;"
    return "background-color: #f8d7da; color: #842029;"


def color_pnl(value):
    if value > 0:
        return "color: #74c69d; font-weight: 600;"
    if value < 0:
        return "color: #ff6b6b; font-weight: 600;"
    return "color: #a1a1a6;"


# -----------------------------
# Example data
# -----------------------------
wallets = pd.DataFrame({
    "Wallet": ["7xK4...91aF", "A9p2...kL28", "3Fm8...88qP", "B2x7...7ZuR", "9Qw1...mN49"],
    "Early Entries": [12, 9, 7, 6, 5],
    "Win Rate": ["72%", "68%", "61%", "59%", "55%"],
    "Avg ROI": ["184%", "132%", "91%", "76%", "64%"],
    "Score": [91, 84, 77, 71, 66],
    "Last Activity": ["4 min ago", "19 min ago", "1 hour ago", "3 hours ago", "5 hours ago"]
})

trades = pd.DataFrame({
    "Time": ["10:42", "10:18", "09:55", "09:21", "08:44", "08:12", "07:50"],
    "Wallet": ["7xK4...91aF", "A9p2...kL28", "7xK4...91aF", "3Fm8...88qP", "B2x7...7ZuR", "9Qw1...mN49", "A9p2...kL28"],
    "Token": ["TOKEN-A", "TOKEN-B", "TOKEN-C", "TOKEN-D", "TOKEN-E", "TOKEN-F", "TOKEN-G"],
    "Action": ["Buy", "Buy", "Sell", "Buy", "Buy", "Sell", "Sell"],
    "Amount": ["3.2 SOL", "1.8 SOL", "5.1 SOL", "0.9 SOL", "2.4 SOL", "1.1 SOL", "0.7 SOL"],
    "PnL %": [34.5, -12.8, 91.2, 8.4, -24.6, 17.9, -5.3],
    "Risk": ["Medium", "High", "Low", "Medium", "High", "Low", "Medium"]
})


# -----------------------------
# Public beta login / beginner gate
# -----------------------------

def beta_session_token():
    try:
        import hashlib
        raw = f"{secret_value('APP_USER', 'tester')}::{secret_value('APP_PASSWORD', 'beta')}::smart-wallet-beta"
        return hashlib.sha256(raw.encode('utf-8')).hexdigest()
    except Exception:
        return ""


def load_beta_login_session():
    data = load_json_dict(BETA_LOGIN_SESSION_FILE)
    if not isinstance(data, dict):
        return False
    token = str(data.get("token", ""))
    expires_at = pd.to_datetime(data.get("expires_at", ""), errors="coerce")
    if not token or token != beta_session_token():
        return False
    if pd.isna(expires_at) or expires_at < pd.Timestamp.now():
        save_json_dict(BETA_LOGIN_SESSION_FILE, {})
        return False
    return True


def save_beta_login_session(days=14):
    save_json_dict(BETA_LOGIN_SESSION_FILE, {
        "token": beta_session_token(),
        "saved_at": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
        "expires_at": (pd.Timestamp.now() + pd.Timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S"),
    })


def clear_beta_login_session():
    save_json_dict(BETA_LOGIN_SESSION_FILE, {})

def secret_value(name, default=None):
    try:
        return st.secrets.get(name, default)
    except Exception:
        return default


def beta_login_enabled():
    value = str(secret_value("BETA_LOGIN_ENABLED", "true") or "true").strip().lower()
    return value not in ["0", "false", "no", "off"]


def require_beta_login():
    if not beta_login_enabled():
        return

    expected_password = str(secret_value("APP_PASSWORD", "beta") or "beta")
    expected_user = str(secret_value("APP_USER", "tester") or "tester")

    if st.session_state.get("beta_authenticated") or load_beta_login_session():
        st.session_state.beta_authenticated = True
        return

    st.markdown(
        """
        <style>
        .login-shell{max-width:760px;margin:8vh auto 0 auto;border:1px solid rgba(59,130,246,.25);background:linear-gradient(135deg,rgba(15,23,42,.98),rgba(30,41,59,.86));border-radius:26px;padding:28px 30px;box-shadow:0 22px 70px rgba(0,0,0,.35)}
        .login-kicker{color:#60a5fa;font-weight:900;font-size:12px;text-transform:uppercase;letter-spacing:.08em;margin-bottom:8px}.login-title{color:#f8fafc;font-size:31px;font-weight:950;margin-bottom:8px}.login-sub{color:#cbd5e1;font-size:14px;line-height:1.55;margin-bottom:18px}.login-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin:14px 0 2px}.login-grid div{border:1px solid rgba(255,255,255,.08);background:rgba(255,255,255,.04);border-radius:15px;padding:12px;color:#e5e7eb;font-size:12px}.login-grid b{display:block;color:#f8fafc;margin-bottom:4px}@media(max-width:800px){.login-grid{grid-template-columns:1fr}.login-shell{margin:3vh 10px}}
        </style>
        <div class="login-shell">
          <div class="login-kicker">Private beta</div>
          <div class="login-title">Smart Wallet Finder</div>
          <div class="login-sub">A beginner-friendly alpha wallet dashboard. Login first, then use the app like a guided workflow: Market finds ideas, Journal builds proof, Watchlist scans only the important wallets.</div>
          <div class="login-grid">
            <div><b>1. Market Radar</b>Finds possible early tokens and wallets.</div>
            <div><b>2. Journal</b>Turns raw wallets into simple theses.</div>
            <div><b>3. Watchlist</b>Live-scans the wallets worth watching.</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.form("beta_login_form"):
        username = st.text_input("User", value="tester", placeholder="tester")
        password = st.text_input("Password", type="password", placeholder="Enter beta password")
        remember_login = st.checkbox("Keep me logged in on this device", value=True)
        submitted = st.form_submit_button("Enter beta")

    if submitted:
        if username.strip() == expected_user and password == expected_password:
            st.session_state.beta_authenticated = True
            if remember_login:
                save_beta_login_session(days=14)
            st.rerun()
        else:
            st.error("Wrong login. Check the beta user/password.")

    st.caption("Local fallback login: user `tester`, password `beta`. For public testing set APP_USER and APP_PASSWORD in Streamlit secrets.")
    st.stop()


require_beta_login()


st.markdown("""
<style>
/* ── Global button base ── */
div.stButton > button {
    transition: background 0.15s ease, color 0.15s ease, border-color 0.15s ease !important;
    border-radius: 10px !important;
    font-weight: 500 !important;
}
div.stButton > button:hover {
    background: rgba(124,92,252,0.12) !important;
    border-color: rgba(124,92,252,0.5) !important;
    color: #c4b5fd !important;
}
/* ── Page fade-in ── */
section.main > div {
    animation: pageIn 0.18s ease both;
}
@keyframes pageIn {
    from { opacity:0; transform:translateY(5px); }
    to   { opacity:1; transform:translateY(0); }
}
/* ── Metric hover ── */
[data-testid="stMetric"] {
    transition: transform 0.15s ease, box-shadow 0.15s ease;
    border-radius: 12px;
}
[data-testid="stMetric"]:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 16px rgba(124,92,252,0.15);
}
/* ── Sidebar nav buttons ── */
section[data-testid="stSidebar"] div.stButton > button {
    background: transparent !important;
    border: none !important;
    text-align: left !important;
    color: #8a8b92 !important;
}
section[data-testid="stSidebar"] div.stButton > button:hover {
    background: rgba(124,92,252,0.10) !important;
    color: #d0d0d5 !important;
    border-color: transparent !important;
}
</style>
<script>
// JS button press effect — works even in Streamlit shadow DOM
(function(){
    function addPressEffect(btn) {
        btn.addEventListener('mousedown', function() {
            this.style.transform = 'scale(0.95)';
            this.style.transition = 'transform 0.08s cubic-bezier(.34,1.56,.64,1)';
        });
        btn.addEventListener('mouseup', function() {
            this.style.transform = 'scale(1)';
        });
        btn.addEventListener('mouseleave', function() {
            this.style.transform = 'scale(1)';
        });
    }
    function patchButtons() {
        document.querySelectorAll('button').forEach(function(btn) {
            if (!btn.dataset.pressed) {
                btn.dataset.pressed = '1';
                addPressEffect(btn);
            }
        });
    }
    // Run on load and re-run when Streamlit re-renders
    setInterval(patchButtons, 800);
    document.addEventListener('DOMContentLoaded', patchButtons);
})();
</script>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────
# SIDEBAR — Premium Navigation v2
# ─────────────────────────────────────────

_SECTION_REMAP = {
    "Overview": "Today",
    "Market Dashboard": "Today",
    "Token Scanner": "Token Finder",
    "Auto Discovery": "Token Finder",
    "Market Monitor": "Token Finder",
    "Wallet Discovery": "Smart Wallets",
    "Recent Trades": "Smart Wallets",
    "AI Search": "Smart Wallets",
}

_NAV_ITEMS = [
    ("Today",          "", "main"),
    ("Token Finder",   "", "main"),
    ("Smart Wallets",  "", "main"),
    ("Wallet Journal", "", "track"),
    ("Watchlist",      "", "track"),
    ("Paper Trading",  "", "track"),
    ("Settings",       "", "system"),
]

if "main_navigation" not in st.session_state:
    st.session_state.main_navigation = "Today"

if st.session_state.section_override:
    _mapped = _SECTION_REMAP.get(st.session_state.section_override, st.session_state.section_override)
    _valid = [n for n,_,_ in _NAV_ITEMS]
    if _mapped in _valid:
        st.session_state.main_navigation = _mapped
    st.session_state.section_override = None

with st.sidebar:
    st.markdown("""
    <style>
    section[data-testid="stSidebar"] {
        width: 240px !important;
        min-width: 240px !important;
        max-width: 240px !important;
        background: #18191c !important;
        border-right: 1px solid #2a2b30 !important;
    }
    section[data-testid="stSidebar"] > div {
        padding: 0 !important;
    }
    .nav-logo {
        padding: 28px 20px 20px 20px;
        border-bottom: 1px solid #2a2b30;
        margin-bottom: 8px;
    }
    .nav-logo-name {
        font-size: 14px;
        font-weight: 600;
        color: #f5f5f7;
        letter-spacing: -0.2px;
    }
    .nav-logo-sub {
        font-size: 11px;
        color: #4a4b52;
        margin-top: 2px;
        letter-spacing: 0.03em;
    }
    .nav-group {
        padding: 14px 12px 4px 20px;
        font-size: 10px;
        font-weight: 600;
        color: #3a3b42;
        letter-spacing: 0.1em;
        text-transform: uppercase;
    }
    .nav-btn {
        display: flex;
        align-items: center;
        gap: 10px;
        width: calc(100% - 16px);
        margin: 2px 8px;
        padding: 9px 12px;
        border-radius: 10px;
        font-size: 13px;
        font-weight: 500;
        color: #8a8b92;
        cursor: pointer;
        border: none;
        background: transparent;
        text-align: left;
        transition: all 0.15s ease;
    }
    .nav-btn:hover {
        background: #222328;
        color: #d0d0d5;
    }
    .nav-btn.active {
        background: #222328;
        color: #f5f5f7;
        font-weight: 600;
    }
    .nav-btn .nav-icon {
        font-size: 15px;
        width: 20px;
        text-align: center;
    }
    .nav-btn .nav-dot {
        width: 5px;
        height: 5px;
        border-radius: 50%;
        background: #7c5cfc;
        margin-left: auto;
    }
    .nav-footer {
        position: absolute;
        bottom: 20px;
        left: 0;
        right: 0;
        padding: 14px 20px;
        border-top: 1px solid #2a2b30;
        font-size: 11px;
        color: #3a3b42;
    }
    </style>

    <div class="nav-logo">
        <div class="nav-logo-name">Smart Wallet Finder</div>
        <div class="nav-logo-sub">PRIVATE BETA</div>
    </div>
    """, unsafe_allow_html=True)

    _current_group = None
    _group_labels = {"main": "DISCOVER", "track": "TRACK", "system": "SYSTEM"}

    for _name, _icon, _group in _NAV_ITEMS:
        if _group != _current_group:
            _current_group = _group
            st.markdown(f'<div class="nav-group">{_group_labels[_group]}</div>', unsafe_allow_html=True)
        _is_active = st.session_state.get("main_navigation") == _name
        _active_class = "active" if _is_active else ""
        _dot = '<span class="nav-dot"></span>' if _is_active else ""
        st.markdown(f"""
        <div class="nav-btn {_active_class}" id="navbtn_{_name}">
            <span class="nav-icon">{_icon}</span>
            <span>{_name}</span>
            {_dot}
        </div>
        """, unsafe_allow_html=True)
        if st.button(_name, key=f"_nav_{_name}", use_container_width=True):
            st.session_state.main_navigation = _name
            st.rerun()

    st.markdown("""
    <style>
    [data-testid="stSidebar"] .stButton button {
        opacity: 0 !important;
        position: absolute !important;
        height: 44px !important;
        width: 100% !important;
        top: 0 !important;
        left: 0 !important;
        cursor: pointer !important;
        border: none !important;
        background: transparent !important;
        box-shadow: none !important;
    }
    [data-testid="stSidebar"] .stButton {
        position: relative !important;
        margin-top: -44px !important;
        height: 44px !important;
    }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("---")
    if st.session_state.get("beta_authenticated"):
        if st.button("Logout", key="sidebar_logout_beta"):
            st.session_state.beta_authenticated = False
            clear_beta_login_session()
            st.rerun()
    st.markdown(f'<div style="font-size:10px;color:#3a3b42;padding:8px 0;">Solana · {APP_BUILD_VERSION}</div>', unsafe_allow_html=True)

section = st.session_state.get("main_navigation", "Today")
chain = "Solana"
timeframe = "24h"
min_score = 60

# Real AI response
# -----------------------------
def ai_answer(question):
    try:
        client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

        wallet_context = wallets.to_string(index=False)
        trades_context = trades.to_string(index=False)

        prompt = f"""
You are an AI analyst inside a crypto smart wallet dashboard.

The user is asking:
{question}

Current top wallets:
{wallet_context}

Recent trades:
{trades_context}

Answer clearly and professionally.
Do not give financial advice.
Do not tell the user to blindly copy trades.
Focus on:
- what the dashboard data suggests
- risks
- what should be checked next
Keep the answer short and useful.
"""

        response = client.responses.create(
            model="gpt-5.5",
            input=prompt
        )

        return response.output_text

    except Exception as error:
        return f"AI connection error: {error}"
    
# -----------------------------
# DEX Screener token scanner
# -----------------------------
@st.cache_data(ttl=30, show_spinner=False)
def fetch_token_pairs(chain_id, token_address):
    try:
        url = f"https://api.dexscreener.com/token-pairs/v1/{chain_id}/{token_address}"

        response = requests.get(url, timeout=10)
        response.raise_for_status()

        data = response.json()

        if not data:
            return None, "No pairs found for this token."

        pairs = data if isinstance(data, list) else data.get("pairs", [])

        if not pairs:
            return None, "No pairs found for this token."

        pairs = sorted(
            pairs,
            key=lambda pair: (pair.get("liquidity") or {}).get("usd") or 0,
            reverse=True
        )

        rows = []

        for pair in pairs[:10]:
            base_token = pair.get("baseToken") or {}
            quote_token = pair.get("quoteToken") or {}
            liquidity = pair.get("liquidity") or {}
            volume = pair.get("volume") or {}
            price_change = pair.get("priceChange") or {}
            txns = pair.get("txns") or {}

            rows.append({
                "DEX": pair.get("dexId", "-"),
                "Pair": f"{base_token.get('symbol', '-')}/{quote_token.get('symbol', '-')}",
                "Price USD": pair.get("priceUsd", "-"),
                "Liquidity USD": liquidity.get("usd", 0),
                "Volume 24h": volume.get("h24", 0),
                "Change 5m": price_change.get("m5", 0),
                "Change 1h": price_change.get("h1", 0),
                "Change 6h": price_change.get("h6", 0),
                "Change 24h": price_change.get("h24", 0),
                "Txns 24h": (txns.get("h24") or {}).get("buys", 0) + (txns.get("h24") or {}).get("sells", 0),
                "Market Cap": pair.get("marketCap", 0)
            })

        return pd.DataFrame(rows), None

    except Exception:
        return None, "DEX Screener error: Could not fetch token data."
    
    # -----------------------------
# Wallet activity classifier
# -----------------------------
BASE_TOKEN_MINTS = {
    "11111111111111111111111111111111",
    "So11111111111111111111111111111111111111112",
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkYhTZ8d5T6s2KZ5"
}

BASE_TOKEN_LABELS = {
    "11111111111111111111111111111111": "SOL",
    "So11111111111111111111111111111111111111112": "SOL",
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": "USDC",
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkYhTZ8d5T6s2KZ5": "USDT"
}


def token_label(mint):
    mint = str(mint or "").strip()
    if not mint or mint == "-":
        return "-"
    return BASE_TOKEN_LABELS.get(mint, f"{mint[:6]}...{mint[-6:]}" if len(mint) > 14 else mint)


def is_base_or_stable_mint(mint):
    return str(mint or "").strip() in BASE_TOKEN_MINTS


def parse_transfer_amount(value):
    try:
        if value is None or value == "-":
            return 0.0
        return abs(float(str(value).replace(",", "")))
    except Exception:
        return 0.0



def is_base_or_stable_label(label):
    label = str(label or "").upper().strip()
    return label in {"SOL", "WSOL", "USDC", "USDT", "USD"}


def clean_token_symbol(symbol):
    symbol = str(symbol or "").strip()
    if not symbol:
        return "-"
    symbol = symbol.replace("$", "").replace(",", "")
    symbol = symbol.strip(" .:;()[]{}")
    return symbol.upper() if len(symbol) <= 10 else symbol


def parse_swap_from_description(description):
    """Infer swap direction from Helius' human-readable description.

    On Solana almost everything is technically a swap. For humans we translate:
    SOL/USDC/USDT -> memecoin = BUY / SWAP IN
    memecoin -> SOL/USDC/USDT = SELL / SWAP OUT
    memecoin -> memecoin = ROTATE
    """
    text = str(description or "")
    if "swap" not in text.lower():
        return {}

    patterns = [
        r"swapped\s+([0-9,\.]+)\s+([^\s]+)\s+for\s+([0-9,\.]+)\s+([^\s]+)",
        r"swap\s+([0-9,\.]+)\s+([^\s]+)\s+for\s+([0-9,\.]+)\s+([^\s]+)",
        r"paid\s+([0-9,\.]+)\s+([^\s,]+).*received\s+([0-9,\.]+)\s+([^\s,]+)",
        r"sold\s+([0-9,\.]+)\s+([^\s,]+).*received\s+([0-9,\.]+)\s+([^\s,]+)",
    ]

    match = None
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            break

    if not match:
        return {}

    from_amount, from_symbol, to_amount, to_symbol = match.groups()
    from_symbol = clean_token_symbol(from_symbol)
    to_symbol = clean_token_symbol(to_symbol)
    from_is_base = is_base_or_stable_label(from_symbol)
    to_is_base = is_base_or_stable_label(to_symbol)

    try:
        from_amount = float(str(from_amount).replace(",", ""))
    except Exception:
        from_amount = 0

    try:
        to_amount = float(str(to_amount).replace(",", ""))
    except Exception:
        to_amount = 0

    if from_is_base and not to_is_base:
        side = "BUY"
        main_token = to_symbol
        main_amount = to_amount
        counter_token = from_symbol
        counter_amount = from_amount
        hint = f"Swap in: paid {from_symbol}, received {to_symbol}"
    elif not from_is_base and to_is_base:
        side = "SELL"
        main_token = from_symbol
        main_amount = from_amount
        counter_token = to_symbol
        counter_amount = to_amount
        hint = f"Swap out: sold {from_symbol}, received {to_symbol}"
    elif not from_is_base and not to_is_base:
        side = "ROTATE"
        main_token = to_symbol
        main_amount = to_amount
        counter_token = from_symbol
        counter_amount = from_amount
        hint = f"Rotate: swapped {from_symbol} into {to_symbol}"
    else:
        side = "SWAP"
        main_token = to_symbol
        main_amount = to_amount
        counter_token = from_symbol
        counter_amount = from_amount
        hint = f"Base swap: {from_symbol} into {to_symbol}"

    return {
        "Trade Side": side,
        "Main Token Mint": "",
        "Main Token": main_token,
        "Main Token Amount": main_amount,
        "Counter Token Mint": "",
        "Counter Token": counter_token,
        "Counter Token Amount": counter_amount,
        "Trade Hint": hint
    }


def summarize_trade_side(wallet_address, tx):
    """Translate Solana swaps into readable wallet behavior.

    Technical truth: most memecoin actions are swaps.
    Human-readable meaning:
    - base/stable -> memecoin = BUY / SWAP IN
    - memecoin -> base/stable = SELL / SWAP OUT
    - memecoin -> memecoin = ROTATE
    - unclear swap = SWAP
    """
    wallet_address = str(wallet_address or "").strip()
    description = tx.get("description", "-")
    raw_type = str(tx.get("type", "-")).upper()

    # Helius descriptions often contain the clearest user-readable swap direction.
    # Try it early so Jupiter/routing transactions are not left as blue unclear swaps.
    early_parsed_description = parse_swap_from_description(description)
    if early_parsed_description and early_parsed_description.get("Trade Side") in ["BUY", "SELL", "ROTATE"]:
        return early_parsed_description

    incoming = []
    outgoing = []

    for transfer in tx.get("tokenTransfers", []) or []:
        mint = transfer.get("mint") or "-"
        amount = (
            transfer.get("tokenAmount")
            or transfer.get("amount")
            or 0
        )
        amount = parse_transfer_amount(amount)

        from_user = str(transfer.get("fromUserAccount") or transfer.get("fromTokenAccount") or "")
        to_user = str(transfer.get("toUserAccount") or transfer.get("toTokenAccount") or "")

        item = {
            "mint": mint,
            "amount": amount,
            "label": token_label(mint),
            "is_base": is_base_or_stable_mint(mint)
        }

        if to_user == wallet_address:
            incoming.append(item)
        if from_user == wallet_address:
            outgoing.append(item)

    for transfer in tx.get("nativeTransfers", []) or []:
        try:
            lamports = float(transfer.get("amount") or 0)
        except Exception:
            lamports = 0

        sol_amount = abs(lamports) / 1_000_000_000
        if sol_amount <= 0:
            continue

        item = {
            "mint": "So11111111111111111111111111111111111111112",
            "amount": sol_amount,
            "label": "SOL",
            "is_base": True
        }

        from_user = str(transfer.get("fromUserAccount") or "")
        to_user = str(transfer.get("toUserAccount") or "")

        if to_user == wallet_address:
            incoming.append(item)
        if from_user == wallet_address:
            outgoing.append(item)

    incoming_risky = [item for item in incoming if not item["is_base"]]
    outgoing_risky = [item for item in outgoing if not item["is_base"]]
    incoming_base = [item for item in incoming if item["is_base"]]
    outgoing_base = [item for item in outgoing if item["is_base"]]

    main_in = max(incoming_risky, key=lambda item: item["amount"], default=None)
    main_out = max(outgoing_risky, key=lambda item: item["amount"], default=None)
    base_in = max(incoming_base, key=lambda item: item["amount"], default=None)
    base_out = max(outgoing_base, key=lambda item: item["amount"], default=None)

    if main_in and base_out:
        side = "BUY"
        main = main_in
        counter = base_out
        hint = f"Swap in: paid {counter['label']}, received {main['label']}"
    elif main_out and base_in:
        side = "SELL"
        main = main_out
        counter = base_in
        hint = f"Swap out: sold {main['label']}, received {counter['label']}"
    elif main_in and main_out:
        side = "ROTATE"
        main = main_in
        counter = main_out
        hint = f"Rotate: swapped {counter['label']} into {main['label']}"
    elif main_in and not main_out:
        side = "BUY"
        main = main_in
        counter = base_out
        hint = f"Swap in / token received: {main['label']}"
    elif main_out and not main_in:
        side = "SELL"
        main = main_out
        counter = base_in
        hint = f"Swap out / token sent: {main['label']}"
    else:
        parsed_description = parse_swap_from_description(description)
        if parsed_description:
            return parsed_description

        if raw_type == "SWAP" or "swap" in str(description).lower():
            side = "SWAP"
            main = None
            counter = None
            hint = "Swap detected, direction unclear"
        elif incoming_base and not outgoing_risky:
            side = "BASE IN"
            main = base_in
            counter = None
            hint = f"Wallet received {main['label']}"
        elif outgoing_base and not incoming_risky:
            side = "BASE OUT"
            main = base_out
            counter = None
            hint = f"Wallet sent {main['label']}"
        else:
            side = "-"
            main = None
            counter = None
            hint = "No clear swap direction detected"

    return {
        "Trade Side": side,
        "Main Token Mint": main["mint"] if main else "",
        "Main Token": main["label"] if main else "-",
        "Main Token Amount": main["amount"] if main else 0,
        "Counter Token Mint": counter["mint"] if counter else "",
        "Counter Token": counter["label"] if counter else "-",
        "Counter Token Amount": counter["amount"] if counter else 0,
        "Trade Hint": hint
    }

def trade_side_badge_class(side):
    side = str(side or "").upper()
    if side == "BUY":
        return "trade-buy"
    if side == "SELL":
        return "trade-sell"
    if side == "ROTATE":
        return "trade-rotate"
    return "trade-neutral"

def classify_wallet_activity(tx_type, description):
    text = description.lower()

    if tx_type == "SWAP" or "swapped" in text or "swap" in text:
        return "Swap"

    if tx_type == "TRANSFER":
        if "transferred" in text and " sol " in text:
            return "SOL Transfer"
        return "Transfer"

    if "token" in text or "mint" in text:
        return "Token Movement"

    if "transferred" in text:
        return "Small Transfer"

    return "Unknown"
    
    # -----------------------------
# Helius wallet transactions
# -----------------------------
@st.cache_data(ttl=30, show_spinner=False)
def fetch_wallet_transactions(wallet_address, limit=10):
    try:
        api_key = str(st.secrets["HELIUS_API_KEY"]).strip()

        url = f"https://api.helius.xyz/v0/addresses/{wallet_address}/transactions/?api-key={api_key}"

        params = {
            "limit": limit
        }

        response = requests.get(url, params=params, timeout=20)
        response.raise_for_status()

        transactions = response.json()

        if not transactions:
            return pd.DataFrame(), "No transactions found for this wallet."

        rows = []

        for tx in transactions:
            raw_type = tx.get("type", "-")
            description = tx.get("description", "-")

            activity = classify_wallet_activity(raw_type, description)
            trade_info = summarize_trade_side(wallet_address, tx)

            timestamp = tx.get("timestamp", "-")
            if timestamp != "-":
                timestamp = pd.to_datetime(timestamp, unit="s").strftime("%Y-%m-%d %H:%M")

            token_mints = []
            token_amounts = []

            for token_transfer in tx.get("tokenTransfers", []):
                mint = token_transfer.get("mint")

                amount = (
                    token_transfer.get("tokenAmount")
                    or token_transfer.get("amount")
                    or 0
                )

                if mint:
                    token_mints.append(mint)

                    try:
                        token_amounts.append(str(float(amount)))
                    except Exception:
                        token_amounts.append("0")

            rows.append({
                "Timestamp": timestamp,
                "Activity": activity,
                "Trade Side": trade_info.get("Trade Side", "-"),
                "Main Token": trade_info.get("Main Token", "-"),
                "Main Token Mint": trade_info.get("Main Token Mint", ""),
                "Main Token Amount": trade_info.get("Main Token Amount", 0),
                "Counter Token": trade_info.get("Counter Token", "-"),
                "Counter Token Mint": trade_info.get("Counter Token Mint", ""),
                "Counter Token Amount": trade_info.get("Counter Token Amount", 0),
                "Trade Hint": trade_info.get("Trade Hint", "-"),
                "Description": description,
                "Token Mints": ", ".join(token_mints[:4]) if token_mints else "-",
                "Token Amounts": ", ".join(token_amounts[:4]) if token_amounts else "-"
            })

        return pd.DataFrame(rows), None

    except Exception:
        return None, "Helius wallet error: Could not fetch wallet transactions."

def resolve_token_names(token_mints):
    try:
        if not token_mints:
            return {}

        clean_mints = []
        for mint in token_mints:
            if mint and mint != "-" and mint not in clean_mints:
                clean_mints.append(mint)

        if not clean_mints:
            return {}

        token_list = ",".join(clean_mints[:30])
        url = f"https://api.dexscreener.com/tokens/v1/solana/{token_list}"

        response = requests.get(url, timeout=10)
        response.raise_for_status()

        pairs = response.json()

        token_map = {}

        for pair in pairs:
            base = pair.get("baseToken") or {}
            quote = pair.get("quoteToken") or {}

            for token in [base, quote]:
                address = token.get("address")
                symbol = token.get("symbol")
                name = token.get("name")

                if address and address in clean_mints:
                    token_map[address] = {
                        "symbol": symbol or "Unknown",
                        "name": name or symbol or "Unknown"
                    }

        return token_map

    except Exception:
        return {}
    
    # -----------------------------
# Extract swapped token mints
# -----------------------------
def get_swapped_token_mints(wallet_tx_data):
    if "Token Mints" not in wallet_tx_data.columns:
        return []

    swap_rows = wallet_tx_data[wallet_tx_data["Activity"] == "Swap"]

    mints = []

    for value in swap_rows["Token Mints"].dropna():
        if value == "-":
            continue

        for mint in str(value).split(","):
            mint = mint.strip()

            if mint and mint != "-" and mint not in mints:
                mints.append(mint)

    return mints

def format_usd(value):
    try:
        value = float(value)
    except Exception:
        value = 0

    if value >= 1_000_000:
        return f"${value / 1_000_000:.2f}M"

    if value >= 1_000:
        return f"${value / 1_000:.2f}K"

    return f"${value:.2f}"


@st.cache_data(ttl=30, show_spinner=False)
def fetch_token_price_map_usd(token_mints):
    price_map = {}

    stable_prices = {
        "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": 1.0,
        "Es9vMFrzaCERmJfrF4H2FYD4KCoNkYhTZ8d5T6s2KZ5": 1.0
    }

    for mint, price in stable_prices.items():
        price_map[mint] = price

    sol_mint = "So11111111111111111111111111111111111111112"

    try:
        sol_url = f"https://api.dexscreener.com/tokens/v1/solana/{sol_mint}"
        sol_response = requests.get(sol_url, timeout=12)
        sol_response.raise_for_status()
        sol_pairs = sol_response.json()

        if sol_pairs:
            sol_price = sol_pairs[0].get("priceUsd")
            price_map[sol_mint] = float(sol_price)
        else:
            price_map[sol_mint] = 0

    except Exception:
        price_map[sol_mint] = 0

    clean_mints = []

    for mint in token_mints:
        if not mint:
            continue

        if mint == "-":
            continue

        if mint not in clean_mints:
            clean_mints.append(mint)

    if not clean_mints:
        return price_map

    try:
        token_list = ",".join(clean_mints[:30])
        url = f"https://api.dexscreener.com/tokens/v1/solana/{token_list}"

        response = requests.get(url, timeout=12)
        response.raise_for_status()

        pairs = response.json()

        for pair in pairs:
            price_usd = pair.get("priceUsd")

            try:
                price_usd = float(price_usd)
            except Exception:
                continue

            base_token = pair.get("baseToken") or {}
            quote_token = pair.get("quoteToken") or {}

            base_address = base_token.get("address")
            quote_address = quote_token.get("address")

            if base_address and base_address in clean_mints:
                price_map[base_address] = price_usd

            if quote_address and quote_address in stable_prices:
                price_map[quote_address] = stable_prices[quote_address]

    except Exception:
        pass

    return price_map


def estimate_wallet_usd_stats(wallet_tx_data):
    stats = {
        "Total USD Volume": 0,
        "Swap USD Volume": 0,
        "Transfer USD Volume": 0,
        "Largest USD Tx": 0,
        "Average USD Tx": 0,
        "Priced Tx Count": 0
    }

    if wallet_tx_data is None or wallet_tx_data.empty:
        return stats

    all_mints = []

    if "Token Mints" in wallet_tx_data.columns:
        for value in wallet_tx_data["Token Mints"].dropna():
            if value == "-":
                continue

            for mint in str(value).split(","):
                mint = mint.strip()

                if mint and mint not in all_mints:
                    all_mints.append(mint)

    price_map = fetch_token_price_map_usd(all_mints)

    usd_values = []

    for _, row in wallet_tx_data.iterrows():
        activity = row.get("Activity", "-")
        token_mints = row.get("Token Mints", "-")
        token_amounts = row.get("Token Amounts", "-")

        if not token_mints or token_mints == "-":
            continue

        if not token_amounts or token_amounts == "-":
            continue

        mints = [item.strip() for item in str(token_mints).split(",")]
        amounts = [item.strip() for item in str(token_amounts).split(",")]

        tx_parts_usd = []

        for mint, amount in zip(mints, amounts):
            if not mint or mint == "-":
                continue

            try:
                amount = abs(float(str(amount).replace(",", "")))
            except Exception:
                continue

            price = price_map.get(mint)

            if price is None or price <= 0:
                continue

            part_usd = amount * price

            if part_usd > 0:
                tx_parts_usd.append(part_usd)

        if not tx_parts_usd:
            continue

        if activity == "Swap":
            tx_usd_value = max(tx_parts_usd)
        else:
            tx_usd_value = sum(tx_parts_usd)

        if tx_usd_value <= 0:
            continue

        usd_values.append(tx_usd_value)

        stats["Total USD Volume"] += tx_usd_value
        stats["Largest USD Tx"] = max(stats["Largest USD Tx"], tx_usd_value)
        stats["Priced Tx Count"] += 1

        if activity == "Swap":
            stats["Swap USD Volume"] += tx_usd_value
        else:
            stats["Transfer USD Volume"] += tx_usd_value

    if usd_values:
        stats["Average USD Tx"] = sum(usd_values) / len(usd_values)

    return stats
    
    # -----------------------------
# Wallet activity summary
# -----------------------------
def summarize_wallet_activity(wallet_tx_data):
    total_tx = len(wallet_tx_data)

    transfers = int(wallet_tx_data["Activity"].isin([
        "Transfer",
        "SOL Transfer",
        "Small Transfer",
        "Token Movement"
    ]).sum())

    swaps = int((wallet_tx_data["Activity"] == "Swap").sum())
    unknown = int((wallet_tx_data["Activity"] == "Unknown").sum())

    if total_tx >= 10:
        activity_level = "High"
    elif total_tx >= 5:
        activity_level = "Medium"
    else:
        activity_level = "Low"

    return total_tx, transfers, swaps, unknown, activity_level

def calculate_wallet_score_100(total_tx, transfers, swaps, unknown):
    score = 0

    if total_tx >= 40:
        score += 20
    elif total_tx >= 20:
        score += 15
    elif total_tx >= 10:
        score += 10
    elif total_tx >= 5:
        score += 5

    if swaps >= 10:
        score += 45
    elif swaps >= 7:
        score += 38
    elif swaps >= 4:
        score += 30
    elif swaps >= 2:
        score += 18
    elif swaps >= 1:
        score += 10

    if transfers > 0 and swaps > 0:
        swap_ratio = swaps / max(total_tx, 1)

        if swap_ratio >= 0.45:
            score += 20
        elif swap_ratio >= 0.25:
            score += 14
        elif swap_ratio >= 0.10:
            score += 8

    if transfers >= 12 and swaps <= 1:
        score -= 20

    if unknown >= 10:
        score -= 10
    elif unknown >= 5:
        score -= 5

    score = max(0, min(100, score))

    return score

def calculate_discovery_score_100(base_score, hits, swaps):
    score = int(base_score)

    try:
        hits = int(hits)
    except Exception:
        hits = 0

    try:
        swaps = int(swaps)
    except Exception:
        swaps = 0

    if hits >= 40:
        score += 20
    elif hits >= 25:
        score += 15
    elif hits >= 10:
        score += 8

    if swaps >= 10:
        score += 15
    elif swaps >= 7:
        score += 10
    elif swaps >= 4:
        score += 6

    score = max(0, min(100, score))

    return score

def get_wallet_signal(total_tx, transfers, swaps, unknown):
    score = calculate_wallet_score_100(total_tx, transfers, swaps, unknown)

    if swaps == 0:
        signal = "Ignore"
        reason = "Recent activity is mostly transfers. No clear trading behavior detected."
    elif score >= 75:
        signal = "Monitor"
        reason = "This wallet shows strong swap activity and may be useful for token discovery."
    elif score >= 50:
        signal = "Watch"
        reason = "This wallet shows promising trading behavior, but needs more confirmation."
    elif score >= 25:
        signal = "Needs More Data"
        reason = "This wallet has some activity, but the signal is still weak."
    else:
        signal = "Ignore"
        reason = "This wallet does not show enough useful trading behavior yet."

    return signal, score, reason

# -----------------------------
# Wallet verdict text
# -----------------------------
def wallet_verdict_text(wallet_signal, transfers, swaps, unknown):
    if wallet_signal == "Monitor" and swaps >= 5:
        verdict_title = "Strong discovery wallet"
        verdict_badge = "Monitor"
        strength = "High swap activity"
        risk = "Low transfer noise"
        action = "Analyze swapped tokens"
        note = "This wallet is actively swapping tokens and may help identify fresh token opportunities."

    elif wallet_signal == "Watch":
        verdict_title = "Potential wallet"
        verdict_badge = "Watch"
        strength = "Some useful activity"
        risk = "Needs more confirmation"
        action = "Check again later"
        note = "This wallet shows some signal, but not enough to treat it as a strong discovery source yet."

    elif transfers > swaps:
        verdict_title = "Mostly transfer wallet"
        verdict_badge = "Weak"
        strength = "Low discovery value"
        risk = "Transfer-heavy activity"
        action = "Ignore for now"
        note = "This wallet mostly transfers funds and does not show enough swap behavior for token discovery."

    else:
        verdict_title = "Not enough signal"
        verdict_badge = "Needs Data"
        strength = "Limited evidence"
        risk = "Unclear behavior"
        action = "Scan more activity"
        note = "There is not enough useful activity yet to judge this wallet confidently."

    return verdict_title, verdict_badge, strength, risk, action, note

# -----------------------------
# Wallet insight text
# -----------------------------
def wallet_insight_text(activity_level, transfers, swaps, unknown, wallet_signal):
    if swaps == 0 and transfers > 0:
        behavior = "Mostly transfer activity. No clear swap behavior detected yet."
        next_check = "Check again later or test a wallet with known token buys."
    elif swaps > 0:
        behavior = "Swap activity detected. This wallet may be useful for token discovery."
        next_check = "Review swapped tokens and compare them with the Token Scanner."
    elif unknown >= transfers:
        behavior = "Many transactions are still unclear from the current API data."
        next_check = "Use this wallet as a watch candidate, but do not rely on it yet."
    else:
        behavior = "Wallet activity is present, but the signal is not specific enough yet."
        next_check = "Look for repeated swaps, early token entries or larger movements."

    return behavior, next_check
    
# -----------------------------
# Token quality evaluation
# -----------------------------
def evaluate_token_pair(best_pair):
    liquidity = float(best_pair["Liquidity USD"])
    volume = float(best_pair["Volume 24h"])
    txns = int(best_pair["Txns 24h"])

    if liquidity >= 1_000_000:
        liquidity_status = "Strong"
    elif liquidity >= 100_000:
        liquidity_status = "Medium"
    else:
        liquidity_status = "Weak"

    if volume >= 1_000_000:
        volume_status = "Strong"
    elif volume >= 100_000:
        volume_status = "Medium"
    else:
        volume_status = "Weak"

    if txns >= 10_000:
        activity_status = "High"
    elif txns >= 1_000:
        activity_status = "Medium"
    else:
        activity_status = "Low"

    risk_points = 0

    if liquidity_status == "Weak":
        risk_points += 2
    elif liquidity_status == "Medium":
        risk_points += 1

    if volume_status == "Weak":
        risk_points += 2
    elif volume_status == "Medium":
        risk_points += 1

    if activity_status == "Low":
        risk_points += 2
    elif activity_status == "Medium":
        risk_points += 1

    if risk_points <= 1:
        risk = "Low"
    elif risk_points <= 3:
        risk = "Medium"
    else:
        risk = "High"

    return liquidity_status, volume_status, activity_status, risk

# -----------------------------
# Pick best token candidate
# -----------------------------
def pick_best_token_candidate(auto_review_df):
    if auto_review_df is None or auto_review_df.empty:
        return None, "No reviewed tokens yet."

    priority = {
        "Monitor": 4,
        "Watch": 3,
        "Wait": 2,
        "Skip": 1,
        "Avoid": 0
    }

    risk_penalty = {
        "Low": 0,
        "Medium": 1,
        "High": 2,
        "Unknown": 2
    }

    scored_rows = []

    for _, row in auto_review_df.iterrows():
        decision = row.get("Decision", "Skip")
        risk = row.get("Risk", "Unknown")
        copy_risk = row.get("Copy Risk", "Unknown")
        liquidity = row.get("Liquidity", "-")
        volume = row.get("Volume", "-")
        activity = row.get("Activity", "-")

        score = priority.get(decision, 0)

        if liquidity == "Strong":
            score += 2
        elif liquidity == "Medium":
            score += 1
        elif liquidity == "Weak":
            score -= 2

        if volume == "Strong":
            score += 2
        elif volume == "Medium":
            score += 1

        if activity == "High":
            score += 1

        score -= risk_penalty.get(risk, 2)
        score -= risk_penalty.get(copy_risk, 2)

        scored_rows.append((score, row))

    scored_rows = sorted(scored_rows, key=lambda item: item[0], reverse=True)

    best_score, best_row = scored_rows[0]

    if best_score <= 0 or best_row.get("Decision") == "Avoid":
        return best_row, "No clean candidate. Best reviewed token still looks risky."

    return best_row, "Best available candidate based on liquidity, volume, activity and risk."

# -----------------------------
# Auto review swapped tokens
# -----------------------------
def auto_review_tokens(token_rows, chain_id="solana"):
    review_rows = []

    for token in token_rows[:5]:
        symbol = token.get("Token", "Unknown")
        name = token.get("Name", "Unknown")
        mint = token.get("Mint", "")

        if not mint:
            continue

        token_data, error = fetch_token_pairs(chain_id, mint)

        if error or token_data is None or token_data.empty:
            review_rows.append({
                "Token": symbol,
                "Name": name,
                "Liquidity": "-",
                "Volume": "-",
                "Activity": "-",
                "Risk": "Unknown",
                "Copy Risk": "Unknown",
                "Decision": "Skip",
                "Reason": "No reliable DEX data found yet.",
                "Mint": mint
            })
            continue

        best_pair = token_data.iloc[0]

        liquidity_status, volume_status, activity_status, risk = evaluate_token_pair(best_pair)

        copy_risk, copy_risk_reasons = evaluate_copy_risk(best_pair)

        decision, decision_reason = get_watch_signal(
            liquidity_status,
            volume_status,
            activity_status,
            risk,
            copy_risk
        )

        review_rows.append({
            "Token": symbol,
            "Name": name,
            "Liquidity": liquidity_status,
            "Volume": volume_status,
            "Activity": activity_status,
            "Risk": risk,
            "Copy Risk": copy_risk,
            "Decision": decision,
            "Reason": decision_reason,
            "Mint": mint
        })

    return pd.DataFrame(review_rows)

# -----------------------------
# Token summary text
# -----------------------------
def token_summary(liquidity_status, volume_status, activity_status, risk):
    if risk == "Low":
        risk_text = "Risk appears low based on current liquidity, volume and trading activity."
    elif risk == "Medium":
        risk_text = "Risk appears moderate. The token has some healthy signals, but not all metrics are strong."
    else:
        risk_text = "Risk appears high. Liquidity, volume or activity may be too weak for confident tracking."

    return (
        f"This token shows {liquidity_status.lower()} liquidity, "
        f"{volume_status.lower()} volume and {activity_status.lower()} trading activity. "
        f"{risk_text}"
    )

# -----------------------------
# Copy risk evaluation
# -----------------------------
def evaluate_copy_risk(best_pair):
    change_24h = float(best_pair["Change 24h"])
    liquidity = float(best_pair["Liquidity USD"])
    volume = float(best_pair["Volume 24h"])
    txns = int(best_pair["Txns 24h"])

    risk_points = 0
    reasons = []

    if change_24h >= 80:
        risk_points += 3
        reasons.append("24h price move is already very high")
    elif change_24h >= 30:
        risk_points += 2
        reasons.append("24h momentum is already elevated")
    elif change_24h >= 15:
        risk_points += 1
        reasons.append("token has already moved noticeably in 24h")

    if liquidity < 100_000:
        risk_points += 2
        reasons.append("liquidity is still weak")
    elif liquidity < 500_000:
        risk_points += 1
        reasons.append("liquidity is moderate")

    if volume > liquidity * 8:
        risk_points += 2
        reasons.append("volume is very high compared to liquidity")
    elif volume > liquidity * 4:
        risk_points += 1
        reasons.append("volume is high compared to liquidity")

    if txns > 50_000:
        risk_points += 1
        reasons.append("trading activity is already very crowded")

    if risk_points <= 1:
        copy_risk = "Low"
    elif risk_points <= 3:
        copy_risk = "Medium"
    else:
        copy_risk = "High"

    if not reasons:
        reasons.append("current momentum does not look overly extended")

    return copy_risk, reasons

# -----------------------------
# Watch signal
# -----------------------------
def get_watch_signal(liquidity_status, volume_status, activity_status, risk, copy_risk):
    if risk == "Low" and copy_risk == "Low" and liquidity_status == "Strong" and volume_status == "Strong":
        signal = "Watch"
        reason = "Strong liquidity, strong volume and low copy risk make this token worth monitoring."
    elif risk == "High" or copy_risk == "High" or liquidity_status == "Weak":
        signal = "Avoid"
        reason = "Risk is too high or liquidity is too weak for a clean setup."
    else:
        signal = "Wait"
        reason = "The token has some good signals, but the setup is not clean enough yet."

    return signal, reason

# -----------------------------
# Styled table versions
# -----------------------------
filtered_wallets = wallets[wallets["Score"] >= min_score]

styled_wallets = filtered_wallets.style.map(
    color_score,
    subset=["Score"]
)

styled_trades = trades.style.map(
    color_pnl,
    subset=["PnL %"]
).format({
    "PnL %": "{:+.1f}%"
})


# -----------------------------
# Auto Discovery helpers
# -----------------------------
def short_address(value, left=6, right=6):
    text = str(value or "").strip()
    if len(text) <= left + right + 3:
        return text or "-"
    return f"{text[:left]}...{text[-right:]}"


def token_already_saved(mint):
    mint = str(mint or "").strip()
    return any(str(item.get("Mint", "")).strip() == mint for item in st.session_state.get("watchlist_tokens", []))


def wallet_already_saved(wallet):
    wallet = str(wallet or "").strip()
    return any(str(item.get("Full Wallet", item.get("Wallet", ""))).strip() == wallet for item in st.session_state.get("watchlist_wallets", []))


def auto_token_candidate_score(row):
    score = 0
    score += safe_int(row.get("Buys", 0)) * 20
    score += safe_int(row.get("Rotates", 0)) * 12
    score += safe_int(row.get("Hits", 0)) * 8
    score += min(abs(safe_float(row.get("Volume Seen", 0))) / 50, 35)
    if str(row.get("Last Action", "")).upper() == "BUY":
        score += 15
    if token_already_saved(row.get("Mint", "")):
        score -= 25
    return round(score, 1)


def build_auto_token_candidates(source_scope="Pinned wallets", range_label="Last 24 checks"):
    wallet_items = st.session_state.get("watchlist_wallets", [])

    if source_scope == "Pinned wallets":
        wallet_items = [item for item in wallet_items if wallet_is_pinned(item)]

    candidates = {}

    for item in wallet_items:
        wallet_address = item.get("Full Wallet", item.get("Wallet", ""))
        wallet_label = item.get("Wallet", short_address(wallet_address))
        history_df = wallet_history_dataframe(wallet_address)

        if history_df is None or history_df.empty:
            # Fallback: use latest token if the wallet has movement but no rich history yet.
            latest_mint = str(item.get("Latest Token Mint", "") or "").strip()
            if latest_mint and latest_mint not in BASE_TOKEN_MINTS:
                key = latest_mint
                candidates.setdefault(key, {
                    "Token": short_address(latest_mint),
                    "Mint": latest_mint,
                    "Source Wallet": wallet_label,
                    "Source Wallet Full": wallet_address,
                    "Last Action": item.get("Latest Trade Side", "SWAP") or "SWAP",
                    "Hits": 0,
                    "Buys": 0,
                    "Sells": 0,
                    "Rotates": 0,
                    "Volume Seen": safe_float(item.get("USD Volume Change", 0)),
                    "Last Seen": item.get("Last Checked", "-"),
                    "Reason": "Latest token seen on a watched wallet."
                })
            continue

        history_df = wallet_chart_range_dataframe(history_df, range_label)
        if history_df is None or history_df.empty:
            continue

        for _, point in history_df.iterrows():
            side = str(point.get("Trade Side", "-")).upper()
            mint = str(point.get("Trade Token Mint", "") or "").strip()
            token = str(point.get("Trade Token", "-") or "-")

            if not mint or mint in BASE_TOKEN_MINTS:
                continue

            if side not in ["BUY", "ROTATE", "SELL", "SWAP"]:
                continue

            if mint not in candidates:
                candidates[mint] = {
                    "Token": token if token and token != "-" else short_address(mint),
                    "Mint": mint,
                    "Source Wallet": wallet_label,
                    "Source Wallet Full": wallet_address,
                    "Last Action": side,
                    "Hits": 0,
                    "Buys": 0,
                    "Sells": 0,
                    "Rotates": 0,
                    "Volume Seen": 0.0,
                    "Last Seen": "-",
                    "Reason": ""
                }

            candidate = candidates[mint]
            candidate["Hits"] += 1
            candidate["Volume Seen"] += abs(safe_float(point.get("USD Volume Change", 0)))
            candidate["Last Action"] = side
            candidate["Last Seen"] = point.get("Timestamp", point.get("Time", "-"))

            if side == "BUY":
                candidate["Buys"] += 1
            elif side == "SELL":
                candidate["Sells"] += 1
            elif side == "ROTATE":
                candidate["Rotates"] += 1

            if side == "BUY":
                candidate["Reason"] = "Pinned wallet swapped into this token. Best early-discovery signal."
            elif side == "ROTATE" and not candidate["Reason"]:
                candidate["Reason"] = "Wallet rotated into this token. Worth checking."
            elif not candidate["Reason"]:
                candidate["Reason"] = "Token appeared in wallet swap history."

    rows = list(candidates.values())
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["Score"] = df.apply(auto_token_candidate_score, axis=1)
    df["Saved?"] = df["Mint"].apply(lambda mint: "Already saved" if token_already_saved(mint) else "New")
    df["Volume Seen"] = pd.to_numeric(df["Volume Seen"], errors="coerce").fillna(0)
    df = df.sort_values(by=["Score", "Buys", "Hits", "Volume Seen"], ascending=False).reset_index(drop=True)
    return df


def review_auto_token_candidate(mint, token_label="Token"):
    token_data, error = fetch_token_pairs("solana", mint)
    if error or token_data is None or token_data.empty:
        return None, error or "No live token data found."

    best_pair = token_data.iloc[0]
    liquidity_status, volume_status, activity_status, risk = evaluate_token_pair(best_pair)
    copy_risk, copy_risk_reasons = evaluate_copy_risk(best_pair)
    decision, decision_reason = get_watch_signal(liquidity_status, volume_status, activity_status, risk, copy_risk)

    token_symbol = str(best_pair.get("Pair", token_label)).split("/", 1)[0].strip() or token_label

    review = {
        "Token": token_symbol,
        "Mint": mint,
        "Decision": decision,
        "Liquidity": liquidity_status,
        "Volume": volume_status,
        "Activity": activity_status,
        "Risk": risk,
        "Copy Risk": copy_risk,
        "Reason": decision_reason,
        "Liquidity USD": safe_float(best_pair.get("Liquidity USD", 0)),
        "Volume 24h": safe_float(best_pair.get("Volume 24h", 0)),
        "Txns 24h": safe_int(best_pair.get("Txns 24h", 0)),
        "Pair": best_pair.get("Pair", "-"),
        "Last Checked": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")
    }
    return review, None


def auto_token_watchlist_item(review, source_wallet="Auto Discovery"):
    return {
        "Token": review.get("Token", "Token"),
        "Name": "Auto discovered token",
        "Mint": review.get("Mint", ""),
        "Decision": review.get("Decision", "Wait"),
        "Liquidity": review.get("Liquidity", "-"),
        "Volume": review.get("Volume", "-"),
        "Activity": review.get("Activity", "-"),
        "Risk": review.get("Risk", "-"),
        "Copy Risk": review.get("Copy Risk", "-"),
        "Reason": review.get("Reason", "Auto discovered from pinned wallet swaps."),
        "Source Wallet": source_wallet,
        "Last Checked": review.get("Last Checked", pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"))
    }



# -----------------------------
# Auto Discovery alpha helpers
# -----------------------------
def discovery_safe_text(value, max_len=120):
    text = str(value or "-")
    text = text.replace("<", "").replace(">", "")
    if len(text) > max_len:
        return text[:max_len - 3] + "..."
    return text


def discovery_range_df(history_df, range_label):
    if history_df is None or history_df.empty:
        return pd.DataFrame()
    if range_label == "Fresh only":
        return history_df.tail(8)
    return wallet_chart_range_dataframe(history_df, range_label)


def discovery_time_bonus(ts):
    try:
        t = pd.to_datetime(ts, errors="coerce")
        if pd.isna(t):
            return 0
        age_min = (pd.Timestamp.now() - t).total_seconds() / 60
        if age_min <= 30:
            return 18
        if age_min <= 120:
            return 12
        if age_min <= 24 * 60:
            return 7
        return 2
    except Exception:
        return 0


def candidate_stage_and_read(row):
    score = safe_float(row.get("Alpha Score", 0))
    buys = safe_int(row.get("Swap Ins", 0))
    sells = safe_int(row.get("Swap Outs", 0))
    wallets = safe_int(row.get("Early Wallets", 0))
    saved = str(row.get("Saved?", "New"))

    if saved == "Already saved":
        return "SAVED", "Already in your token watchlist. Keep monitoring from Token Watchlist."
    if score >= 75 and buys > sells and wallets >= 2:
        return "STRONG EARLY", "Multiple watched wallets entered before many exits. Open this first."
    if score >= 60 and buys > sells:
        return "EARLY WATCH", "Looks early: swap-in activity is stronger than swap-out activity."
    if sells > buys and sells > 0:
        return "EXIT PRESSURE", "More selling than buying in this range. Be careful."
    if buys > 0:
        return "FIRST SIGNAL", "At least one watched wallet swapped into this token. Needs confirmation."
    return "UNCLEAR", "Activity exists, but not enough clear swap-in data yet."


def build_alpha_discovery_candidates(source_scope="Pinned wallets", range_label="Last 24 checks", include_unclear=False):
    wallet_items = st.session_state.get("watchlist_wallets", [])
    if source_scope == "Pinned wallets":
        wallet_items = [item for item in wallet_items if wallet_is_pinned(item)]

    candidates = {}
    early_wallets = {}

    for item in wallet_items:
        wallet_address = item.get("Full Wallet", item.get("Wallet", ""))
        if not wallet_address:
            continue
        wallet_label = item.get("Wallet", short_address(wallet_address))
        is_pinned = wallet_is_pinned(item)
        history_df = wallet_history_dataframe(wallet_address)

        if history_df is None or history_df.empty:
            latest_mint = str(item.get("Latest Token Mint", "") or "").strip()
            latest_side = str(item.get("Latest Trade Side", "SWAP") or "SWAP").upper()
            if latest_mint and latest_mint not in BASE_TOKEN_MINTS:
                history_df = pd.DataFrame([{
                    "Timestamp": item.get("Last Checked", pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")),
                    "Time": pd.Timestamp.now(),
                    "Trade Side": latest_side,
                    "Trade Token": item.get("Latest Trade Token", short_address(latest_mint)),
                    "Trade Token Mint": latest_mint,
                    "Trade Hint": item.get("Latest Trade Hint", "latest wallet token"),
                    "USD Volume Change": safe_float(item.get("USD Volume Change", 0)),
                    "Swaps Change": safe_int(item.get("Swaps Change", 0))
                }])
            else:
                continue

        use_df = discovery_range_df(history_df, range_label)
        if use_df is None or use_df.empty:
            continue

        for _, point in use_df.iterrows():
            side = str(point.get("Trade Side", "-")).upper()
            if side == "SWAP" and not include_unclear:
                continue
            if side not in ["BUY", "SELL", "ROTATE", "SWAP"]:
                continue

            mint = str(point.get("Trade Token Mint", "") or "").strip()
            token = str(point.get("Trade Token", "") or "").strip()
            if not mint or mint in BASE_TOKEN_MINTS:
                continue

            if mint not in candidates:
                candidates[mint] = {
                    "Token": token if token and token != "-" else short_address(mint),
                    "Mint": mint,
                    "Early Wallets Set": set(),
                    "Source Wallets List": [],
                    "Pinned Sources": 0,
                    "Hits": 0,
                    "Swap Ins": 0,
                    "Swap Outs": 0,
                    "Rotates": 0,
                    "Unclear Swaps": 0,
                    "Volume Seen": 0.0,
                    "Latest Seen Raw": None,
                    "Last Action": side,
                    "Last Hint": point.get("Trade Hint", "-"),
                    "Best Source Wallet": wallet_label,
                    "Best Source Wallet Full": wallet_address,
                    "Best Source Score": wallet_movement_score(item),
                }

            c = candidates[mint]
            c["Hits"] += 1
            c["Volume Seen"] += abs(safe_float(point.get("USD Volume Change", 0)))
            c["Last Action"] = side
            c["Last Hint"] = point.get("Trade Hint", "-")
            c["Early Wallets Set"].add(wallet_address)
            if wallet_label not in c["Source Wallets List"]:
                c["Source Wallets List"].append(wallet_label)
            if is_pinned:
                c["Pinned Sources"] += 1
            ts = point.get("Timestamp", point.get("Time", ""))
            if c["Latest Seen Raw"] is None or str(ts) > str(c["Latest Seen Raw"]):
                c["Latest Seen Raw"] = ts
            if wallet_movement_score(item) > safe_float(c.get("Best Source Score", 0)):
                c["Best SourceWallet"] = wallet_label
                c["Best Source Wallet Full"] = wallet_address
                c["Best Source Score"] = wallet_movement_score(item)

            if side == "BUY":
                c["Swap Ins"] += 1
            elif side == "SELL":
                c["Swap Outs"] += 1
            elif side == "ROTATE":
                c["Rotates"] += 1
            elif side == "SWAP":
                c["Unclear Swaps"] += 1

            ew = early_wallets.setdefault(wallet_address, {
                "Wallet": wallet_label,
                "Full Wallet": wallet_address,
                "Pinned": is_pinned,
                "Early Tokens": set(),
                "Swap Ins": 0,
                "Rotates": 0,
                "Swap Outs": 0,
                "Unclear": 0,
                "Last Token": "-",
                "Last Seen": "-",
                "Score": 0
            })
            if side in ["BUY", "ROTATE"]:
                ew["Early Tokens"].add(mint)
                ew["Last Token"] = token if token and token != "-" else short_address(mint)
                ew["Last Seen"] = ts
            if side == "BUY":
                ew["Swap Ins"] += 1
            elif side == "ROTATE":
                ew["Rotates"] += 1
            elif side == "SELL":
                ew["Swap Outs"] += 1
            elif side == "SWAP":
                ew["Unclear"] += 1

    rows = []
    for mint, c in candidates.items():
        wallet_count = len(c["Early Wallets Set"])
        buys = safe_int(c["Swap Ins"])
        sells = safe_int(c["Swap Outs"])
        rotates = safe_int(c["Rotates"])
        unclear = safe_int(c["Unclear Swaps"])
        hits = safe_int(c["Hits"])
        volume = safe_float(c["Volume Seen"])
        latest_seen = c.get("Latest Seen Raw", "-")

        score = 0
        score += min(wallet_count * 22, 38)
        score += min(buys * 20, 36)
        score += min(rotates * 12, 22)
        score += min(hits * 4, 18)
        score += min(c.get("Pinned Sources", 0) * 6, 18)
        score += discovery_time_bonus(latest_seen)
        if 25 <= volume <= 2500:
            score += 10
        elif volume > 8000:
            score -= 12
        if sells > buys:
            score -= min((sells - buys) * 14, 30)
        if unclear and not buys and not rotates:
            score -= 8
        if token_already_saved(mint):
            score -= 18
        score = max(0, min(100, round(score, 1)))

        source_wallets = ", ".join(c["Source Wallets List"][:3])
        if len(c["Source Wallets List"]) > 3:
            source_wallets += f" +{len(c['Source Wallets List']) - 3} more"

        row = {
            "Token": c["Token"],
            "Mint": mint,
            "Alpha Score": score,
            "Stage": "",
            "Read": "",
            "Early Wallets": wallet_count,
            "Source Wallets": source_wallets,
            "Best Source Wallet": c.get("Best SourceWallet", c.get("Best Source Wallet", "-")),
            "Best Source Wallet Full": c.get("Best Source Wallet Full", ""),
            "Swap Ins": buys,
            "Swap Outs": sells,
            "Rotates": rotates,
            "Unclear Swaps": unclear,
            "Hits": hits,
            "Volume Seen": volume,
            "Last Seen": latest_seen,
            "Last Action": c.get("Last Action", "-"),
            "Last Hint": c.get("Last Hint", "-"),
            "Saved?": "Already saved" if token_already_saved(mint) else "New"
        }
        stage, read = candidate_stage_and_read(row)
        row["Stage"] = stage
        row["Read"] = read
        rows.append(row)

    candidate_df = pd.DataFrame(rows)
    if not candidate_df.empty:
        candidate_df = candidate_df.sort_values(
            by=["Alpha Score", "Swap Ins", "Early Wallets", "Rotates", "Hits"],
            ascending=False
        ).reset_index(drop=True)

    wallet_rows = []
    for wallet, w in early_wallets.items():
        early_tokens = len(w["Early Tokens"])
        w_score = min(100, early_tokens * 24 + w["Swap Ins"] * 10 + w["Rotates"] * 8 - w["Swap Outs"] * 4 + (10 if w["Pinned"] else 0))
        wallet_rows.append({
            "Wallet": w["Wallet"],
            "Full Wallet": w["Full Wallet"],
            "Pinned": "Yes" if w["Pinned"] else "No",
            "Early Tokens": early_tokens,
            "Swap Ins": w["Swap Ins"],
            "Rotates": w["Rotates"],
            "Swap Outs": w["Swap Outs"],
            "Last Token": w["Last Token"],
            "Last Seen": w["Last Seen"],
            "Early Score": round(w_score, 1),
            "Read": "Repeated early entries" if early_tokens >= 2 else "One early signal" if early_tokens == 1 else "Needs more data"
        })
    wallet_df = pd.DataFrame(wallet_rows)
    if not wallet_df.empty:
        wallet_df = wallet_df.sort_values(by=["Early Score", "Early Tokens", "Swap Ins"], ascending=False).reset_index(drop=True)

    return candidate_df, wallet_df


def render_alpha_candidate_card(row, index):
    token = discovery_safe_text(row.get("Token", "Token"), 40)
    mint = str(row.get("Mint", ""))
    score = safe_float(row.get("Alpha Score", 0))
    stage = row.get("Stage", "-")
    read = discovery_safe_text(row.get("Read", "-"), 180)
    source_wallets = discovery_safe_text(row.get("Source Wallets", "-"), 120)
    last_hint = discovery_safe_text(row.get("Last Hint", "-"), 120)
    saved = row.get("Saved?", "New")

    stage_class = "candidate-hot" if score >= 75 else "candidate-watch" if score >= 55 else "candidate-neutral"
    st.markdown(
        f"""
        <div class="alpha-candidate-card {stage_class}">
            <div class="alpha-candidate-top">
                <div>
                    <div class="alpha-candidate-token">{token}</div>
                    <div class="alpha-candidate-sub">{short_address(mint)} · {source_wallets}</div>
                </div>
                <div class="alpha-score">{score:.0f}/100</div>
            </div>
            <div class="alpha-badges">
                <span>{stage}</span><span>{saved}</span><span>{safe_int(row.get('Swap Ins', 0))} swap-in</span><span>{safe_int(row.get('Early Wallets', 0))} early wallet(s)</span>
            </div>
            <div class="alpha-candidate-read">{read}</div>
            <div class="alpha-mini-grid">
                <div><span>Swap In</span><strong>{safe_int(row.get('Swap Ins', 0))}</strong></div>
                <div><span>Swap Out</span><strong>{safe_int(row.get('Swap Outs', 0))}</strong></div>
                <div><span>Rotates</span><strong>{safe_int(row.get('Rotates', 0))}</strong></div>
                <div><span>Seen Volume</span><strong>{format_usd(row.get('Volume Seen', 0))}</strong></div>
            </div>
            <div class="alpha-hint"><b>Why:</b> {last_hint}</div>
        </div>
        """,
        unsafe_allow_html=True
    )




# -----------------------------
# Paper trading / fake wallet helpers
# -----------------------------
def save_paper_settings():
    settings = st.session_state.get("paper_settings", {})
    settings["last_saved"] = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    st.session_state.paper_settings = settings
    save_json_dict(PAPER_SETTINGS_FILE, settings)


def save_paper_trades():
    trades = st.session_state.get("paper_trades", [])
    save_json_list(PAPER_TRADES_FILE, trades[-500:])


def save_paper_events():
    events = st.session_state.get("paper_events", [])
    save_json_list(PAPER_EVENTS_FILE, events[-1000:])


def save_my_wallets():
    wallets = st.session_state.get("my_wallets", [])
    clean = []
    seen = set()
    for item in wallets:
        if not isinstance(item, dict):
            continue
        address = str(item.get("Address", item.get("Wallet", "")) or "").strip()
        if not address or address in seen:
            continue
        seen.add(address)
        clean.append({
            "Name": str(item.get("Name", wallet_auto_name(address, prefix="My Wallet")) or "").strip(),
            "Address": address,
            "Note": str(item.get("Note", "") or "").strip(),
            "Added": str(item.get("Added", pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")) or "")
        })
    st.session_state.my_wallets = clean
    save_json_list(MY_WALLETS_FILE, clean)


def paper_log_event(kind, message, payload=None):
    event = {
        "Timestamp": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Type": str(kind or "info"),
        "Message": str(message or ""),
        "Payload": payload or {}
    }
    st.session_state.setdefault("paper_events", []).append(event)
    st.session_state.paper_events = st.session_state.paper_events[-1000:]
    save_paper_events()


def paper_set_impact(kind, title, message="", level="medium"):
    st.session_state.paper_last_impact = {
        "kind": str(kind or "info"),
        "title": str(title or "Action saved"),
        "message": str(message or ""),
        "level": str(level or "medium"),
        "ts": time.time(),
        "label": pd.Timestamp.now().strftime("%H:%M:%S"),
    }


def paper_action_allowed(action_key, cooldown_seconds=0.75):
    action_key = str(action_key or "paper_action")
    locks = st.session_state.setdefault("paper_action_locks", {})
    now = time.time()
    last = safe_float(locks.get(action_key, 0), 0)
    if now - last < safe_float(cooldown_seconds, 0.75):
        return False
    locks[action_key] = now
    st.session_state.paper_action_locks = locks
    return True


def render_paper_impact():
    impact = st.session_state.get("paper_last_impact", {})
    if not isinstance(impact, dict) or not impact.get("title"):
        return
    age = time.time() - safe_float(impact.get("ts", 0), 0)
    if age > 8:
        return
    level = str(impact.get("level", "medium")).lower()
    if level not in ["soft", "medium", "strong", "danger"]:
        level = "medium"
    html = f'''
        <div class="paper-impact paper-impact-{level}">
            <div><b>{impact.get("title", "Action saved")}</b><span>{impact.get("message", "")}</span></div>
            <em>{impact.get("label", "")}</em>
        </div>
        '''
    st.markdown(html, unsafe_allow_html=True)


def paper_trade_id(token_mint, source_wallet):
    seed = f"{token_mint}|{source_wallet}|{time.time()}".encode("utf-8")
    return hashlib.sha1(seed).hexdigest()[:14]


def paper_open_trades():
    return [t for t in st.session_state.get("paper_trades", []) if str(t.get("Status", "Open")).lower() == "open"]


def paper_closed_trades():
    return [t for t in st.session_state.get("paper_trades", []) if str(t.get("Status", "")).lower() == "closed"]


def paper_has_open_trade(token_mint, source_wallet=None):
    token_mint = str(token_mint or "").strip()
    source_wallet = str(source_wallet or "").strip()
    for trade in paper_open_trades():
        if str(trade.get("Token Mint", "")).strip() != token_mint:
            continue
        if not source_wallet or str(trade.get("Source Wallet", "")).strip() == source_wallet:
            return True
    return False


def dex_token_best_pair(token_mint):
    pairs, error = fetch_dexscreener_pairs_raw(token_mint)
    if error or not pairs:
        return None
    pairs = sorted(pairs, key=lambda p: safe_float((p.get("liquidity") or {}).get("usd", 0)), reverse=True)
    return pairs[0] if pairs else None


def dex_token_quote(token_mint):
    token_mint = str(token_mint or "").strip()
    if not token_mint:
        return None, "No token mint."
    pair = dex_token_best_pair(token_mint)
    if not pair:
        return None, "No live price found on DexScreener."
    base = pair.get("baseToken") or {}
    price = safe_float(pair.get("priceUsd", 0))
    if price <= 0:
        return None, "DexScreener has no usable price yet."
    quote = {
        "Token": str(base.get("symbol") or short_address(token_mint)),
        "Name": str(base.get("name") or base.get("symbol") or short_address(token_mint)),
        "Mint": token_mint,
        "Price": price,
        "URL": pair.get("url", ""),
        "Liquidity USD": safe_float((pair.get("liquidity") or {}).get("usd", 0)),
        "Volume 24h": safe_float((pair.get("volume") or {}).get("h24", 0)),
        "Change 5m": safe_float((pair.get("priceChange") or {}).get("m5", 0)),
        "Change 1h": safe_float((pair.get("priceChange") or {}).get("h1", 0)),
        "Change 24h": safe_float((pair.get("priceChange") or {}).get("h24", 0)),
    }
    return quote, None


def paper_recalc_trade(trade, live_quote=None):
    token_mint = str(trade.get("Token Mint", "")).strip()
    quote = live_quote
    if quote is None and token_mint:
        quote, _ = dex_token_quote(token_mint)
    if not quote:
        return trade
    price = safe_float(quote.get("Price", 0))
    units = safe_float(trade.get("Units", 0))
    entry_value = safe_float(trade.get("Entry Value", 0))
    current_value = units * price
    pnl = current_value - entry_value
    pnl_pct = (pnl / entry_value * 100) if entry_value > 0 else 0
    trade["Current Price"] = price
    trade["Current Value"] = current_value
    trade["P/L"] = pnl
    trade["P/L %"] = pnl_pct
    now_label = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    trade["Last Updated"] = now_label

    # Keep a small live P/L trail per fake trade so every open trade tells its own story.
    live_history = trade.get("Live PnL History", [])
    if not isinstance(live_history, list):
        live_history = []
    last_stamp = str(live_history[-1].get("Timestamp", "")) if live_history and isinstance(live_history[-1], dict) else ""
    if last_stamp != now_label:
        live_history.append({
            "Timestamp": now_label,
            "Price": price,
            "Value": current_value,
            "P/L": pnl,
            "P/L %": pnl_pct
        })
    trade["Live PnL History"] = live_history[-240:]

    trade["Token"] = trade.get("Token") or quote.get("Token", short_address(token_mint))
    trade["Token URL"] = quote.get("URL", trade.get("Token URL", ""))
    return trade


def paper_update_open_trades(apply_rules=True):
    settings = st.session_state.get("paper_settings", {})
    updated = 0
    closed = 0
    cash = safe_float(settings.get("cash", settings.get("fake_balance_start", 1000)), 1000)
    stop_loss = safe_float(settings.get("stop_loss_pct", -25), -25)
    take_profit = safe_float(settings.get("take_profit_pct", 50), 50)

    for trade in st.session_state.get("paper_trades", []):
        if str(trade.get("Status", "Open")).lower() != "open":
            continue
        before_status = trade.get("Status", "Open")
        paper_recalc_trade(trade)
        updated += 1
        pnl_pct = safe_float(trade.get("P/L %", 0))
        if apply_rules and (pnl_pct <= stop_loss or pnl_pct >= take_profit):
            trade["Status"] = "Closed"
            trade["Exit Reason"] = "Stop loss" if pnl_pct <= stop_loss else "Take profit"
            trade["Exit Time"] = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
            trade["Exit Price"] = safe_float(trade.get("Current Price", 0))
            trade["Exit Value"] = safe_float(trade.get("Current Value", 0))
            cash += safe_float(trade.get("Exit Value", 0))
            closed += 1
            paper_log_event("close", f"{trade.get('Exit Reason')} closed {trade.get('Token', 'token')} at {format_signed_usd(trade.get('P/L', 0))}.", {"Trade ID": trade.get("ID", "")})
        if before_status != trade.get("Status"):
            updated += 1

    settings["cash"] = cash
    st.session_state.paper_settings = settings
    save_paper_settings()
    save_paper_trades()
    return updated, closed


def paper_open_trade(token_mint, source_wallet="", source_name="", reason="", size=None, mode="Journal copy"):
    token_mint = str(token_mint or "").strip()
    if not token_mint or token_mint in BASE_TOKEN_MINTS or len(token_mint) < 32 or len(token_mint) > 60:
        return False, "No valid memecoin token mint found for paper trade."

    if not paper_action_allowed(f"open_{token_mint}_{source_wallet}", cooldown_seconds=1.25):
        return False, "Trade action already received. Wait a moment to prevent duplicate entries."

    settings = st.session_state.get("paper_settings", {})
    open_count = len(paper_open_trades())
    max_open = safe_int(settings.get("max_open_trades", 5), 5)
    if open_count >= max_open:
        return False, f"Max open paper trades reached ({max_open})."

    if paper_has_open_trade(token_mint, source_wallet):
        return False, "This token is already open for this source wallet."

    quote, error = dex_token_quote(token_mint)
    if error or not quote:
        return False, error or "No live quote found."

    min_liquidity = safe_float(settings.get("min_liquidity_usd", 1000), 1000)
    liquidity = safe_float(quote.get("Liquidity USD", 0), 0)
    if min_liquidity > 0 and liquidity > 0 and liquidity < min_liquidity:
        return False, f"Safety filter: liquidity is only {format_usd(liquidity)}. Minimum is {format_usd(min_liquidity)}."

    cash = safe_float(settings.get("cash", settings.get("fake_balance_start", 1000)), 1000)
    start_balance = max(safe_float(settings.get("fake_balance_start", 1000), 1000), 1)
    trade_size = safe_float(size if size is not None else settings.get("trade_size", 25), 25)
    if trade_size <= 0:
        return False, "Trade size must be above $0."
    max_trade_size = start_balance * max(safe_float(settings.get("max_trade_size_pct", 10), 10), 1) / 100
    if trade_size > max_trade_size:
        return False, f"Safety filter: this fake trade is too large. Max per trade is {format_usd(max_trade_size)} ({safe_float(settings.get('max_trade_size_pct', 10), 10):.0f}% of play money)."
    trade_size = min(trade_size, cash)
    if trade_size <= 0:
        return False, "Fake wallet has no available cash."

    price = safe_float(quote.get("Price", 0))
    units = trade_size / price if price > 0 else 0
    now = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    trade = {
        "ID": paper_trade_id(token_mint, source_wallet),
        "Status": "Open",
        "Mode": mode,
        "Token": quote.get("Token", short_address(token_mint)),
        "Token Mint": token_mint,
        "Token URL": quote.get("URL", ""),
        "Source Wallet": source_wallet,
        "Source Name": (source_name or wallet_display_name(source_wallet, row={})) if source_wallet else "Manual",
        "Reason": reason or "Paper trade opened from journal signal.",
        "Entry Time": now,
        "Entry Price": price,
        "Entry Value": trade_size,
        "Units": units,
        "Current Price": price,
        "Current Value": trade_size,
        "P/L": 0.0,
        "P/L %": 0.0,
        "Last Updated": now,
    }
    st.session_state.setdefault("paper_trades", []).append(trade)
    settings["cash"] = cash - trade_size
    st.session_state.paper_settings = settings
    save_paper_settings()
    save_paper_trades()
    paper_log_event("open", f"Opened fake trade {trade.get('Token')} for {format_usd(trade_size)}.", {"Token Mint": token_mint, "Source Wallet": source_wallet})
    return True, f"Opened fake trade for {trade.get('Token')} at {format_usd(price)}."


def paper_close_trade_by_id(trade_id, reason="Manual close"):
    trade_id = str(trade_id or "").strip()
    if not paper_action_allowed(f"close_{trade_id}", cooldown_seconds=1.0):
        return False, "Close action already received. Wait a moment to prevent duplicate closes."
    settings = st.session_state.get("paper_settings", {})
    cash = safe_float(settings.get("cash", settings.get("fake_balance_start", 1000)), 1000)
    for trade in st.session_state.get("paper_trades", []):
        if str(trade.get("ID", "")) != trade_id or str(trade.get("Status", "")).lower() != "open":
            continue
        paper_recalc_trade(trade)
        trade["Status"] = "Closed"
        trade["Exit Reason"] = reason
        trade["Exit Time"] = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
        trade["Exit Price"] = safe_float(trade.get("Current Price", 0))
        trade["Exit Value"] = safe_float(trade.get("Current Value", 0))
        cash += safe_float(trade.get("Exit Value", 0))
        settings["cash"] = cash
        st.session_state.paper_settings = settings
        save_paper_settings()
        save_paper_trades()
        paper_log_event("close", f"Closed fake trade {trade.get('Token')} at {format_signed_usd(trade.get('P/L', 0))}.", {"Trade ID": trade_id})
        return True, "Fake trade result locked."
    return False, "Open trade not found."


def latest_copyable_wallet_signal(wallet_address):
    history_df = wallet_history_dataframe(wallet_address)
    if history_df is None or history_df.empty:
        return {}
    df = history_df.copy().sort_values("Time")
    if "Trade Side" not in df.columns:
        return {}
    df["Trade Side"] = df["Trade Side"].fillna("-").astype(str).str.upper()
    useful = df[df["Trade Side"].isin(["BUY", "SELL", "ROTATE"])]
    if useful.empty:
        useful = df[df["Trade Side"].isin(["SWAP"])]
    if useful.empty:
        return {}
    row = useful.iloc[-1].to_dict()
    token_mint = str(row.get("Trade Token Mint", "") or "").strip()
    if not token_mint:
        token_mint = extract_first_token_mint(row.get("Trade Token", ""))
    row["Trade Token Mint"] = token_mint
    return row



def paper_candidate_source_wallets(source=None):
    settings = st.session_state.get("paper_settings", {})
    source = source or settings.get("source", "Journal pinned only")
    docs = st.session_state.get("wallet_documentation", {})
    pins = set(st.session_state.get("wallet_journal_pins", []))

    if source == "Journal pinned only":
        candidate_keys = pins
    elif source == "Strong thesis only":
        candidate_keys = {k for k, v in docs.items() if isinstance(v, dict) and str(v.get("Verdict", "")) == "Strong thesis"}
    elif source == "Strong + Promising":
        candidate_keys = {k for k, v in docs.items() if isinstance(v, dict) and str(v.get("Verdict", "")) in ["Strong thesis", "Promising"]}
    else:
        candidate_keys = pins

    wallets = []
    for wallet in candidate_keys:
        wallet = str(wallet or "").strip()
        if not wallet:
            continue
        record = docs.get(wallet, {}) if isinstance(docs, dict) else {}
        wallets.append({
            "Wallet": wallet,
            "Name": wallet_display_name(wallet, record.get("Wallet", ""), row=record if isinstance(record, dict) else {}),
            "Verdict": record.get("Verdict", "-") if isinstance(record, dict) else "-",
            "Trust": safe_float(record.get("Best Trust Score", 0)) if isinstance(record, dict) else 0,
            "Early Tokens": safe_int(record.get("Early Tokens", 0)) if isinstance(record, dict) else 0,
            "Seen": safe_int(record.get("Seen Count", record.get("Seen", 0))) if isinstance(record, dict) else 0,
        })

    wallets = sorted(wallets, key=lambda x: (safe_float(x.get("Trust", 0)), safe_int(x.get("Early Tokens", 0)), str(x.get("Name", ""))), reverse=True)
    return wallets


def paper_source_wallets():
    """Selected Journal wallets that the copier is allowed to follow.

    Empty selection means: copy all wallets from the chosen source group.
    """
    settings = st.session_state.get("paper_settings", {})
    wallets = paper_candidate_source_wallets(settings.get("source", "Journal pinned only"))
    selected = settings.get("selected_source_wallets", [])
    if isinstance(selected, str):
        selected = [selected]
    selected = {str(value).strip() for value in selected if str(value).strip()}
    if selected:
        wallets = [wallet for wallet in wallets if str(wallet.get("Wallet", "")).strip() in selected]
    return wallets


def paper_bot_scan_once():
    """Copy-tracking bot: opens/closes fake trades from journal wallet signals only."""
    settings = st.session_state.get("paper_settings", {})
    source_wallets = paper_source_wallets()
    opened = 0
    closed = 0
    skipped = 0

    paper_update_open_trades(apply_rules=True)

    for source in source_wallets:
        wallet = source.get("Wallet", "")
        signal = latest_copyable_wallet_signal(wallet)
        if not signal:
            skipped += 1
            continue

        side = str(signal.get("Trade Side", "-")).upper()
        token_mint = str(signal.get("Trade Token Mint", "") or "").strip()
        token = str(signal.get("Trade Token", "") or "")
        hint = str(signal.get("Trade Hint", "") or "")
        if not token_mint or token_mint in BASE_TOKEN_MINTS:
            skipped += 1
            continue

        if side == "BUY":
            ok, msg = paper_open_trade(
                token_mint=token_mint,
                source_wallet=wallet,
                source_name=source.get("Name", ""),
                reason=f"{source.get('Name', 'Wallet')} showed BUY/SWAP IN. {hint}",
                size=safe_float(settings.get("trade_size", 25), 25),
                mode="Journal copier"
            )
            opened += 1 if ok else 0
            skipped += 0 if ok else 1
        elif side == "SELL":
            # Close open trades for this source/token when the copied wallet exits.
            close_ids = [
                t.get("ID") for t in paper_open_trades()
                if str(t.get("Source Wallet", "")) == wallet and str(t.get("Token Mint", "")) == token_mint
            ]
            if close_ids:
                for trade_id in close_ids:
                    ok, _ = paper_close_trade_by_id(trade_id, reason="Copied wallet sell")
                    closed += 1 if ok else 0
            else:
                skipped += 1
        else:
            skipped += 1

    settings["last_bot_ts"] = time.time()
    st.session_state.paper_settings = settings
    save_paper_settings()
    if opened or closed:
        paper_log_event("bot", f"Journal copier scan: {opened} opened, {closed} closed, {skipped} skipped.")
    return opened, closed, skipped


def paper_wallet_summary():
    paper_update_open_trades(apply_rules=False)
    settings = st.session_state.get("paper_settings", {})
    start = safe_float(settings.get("fake_balance_start", 1000), 1000)
    cash = safe_float(settings.get("cash", start), start)
    open_value = sum(safe_float(t.get("Current Value", 0)) for t in paper_open_trades())
    closed_pnl = sum(safe_float(t.get("P/L", 0)) for t in paper_closed_trades())
    open_pnl = sum(safe_float(t.get("P/L", 0)) for t in paper_open_trades())
    equity = cash + open_value
    total_pnl = equity - start
    closed = paper_closed_trades()
    wins = len([t for t in closed if safe_float(t.get("P/L", 0)) > 0])
    win_rate = (wins / len(closed) * 100) if closed else 0
    return {
        "Start": start,
        "Cash": cash,
        "Open Value": open_value,
        "Equity": equity,
        "Total P/L": total_pnl,
        "Open P/L": open_pnl,
        "Closed P/L": closed_pnl,
        "Open Trades": len(paper_open_trades()),
        "Closed Trades": len(closed),
        "Win Rate": win_rate,
    }


def paper_trade_live_pnl_chart(trade, key_suffix=""):
    history = trade.get("Live PnL History", [])
    if not isinstance(history, list) or len(history) < 2:
        return
    rows = []
    for point in history[-80:]:
        if not isinstance(point, dict):
            continue
        rows.append({
            "Time": str(point.get("Timestamp", ""))[-8:-3] or str(point.get("Timestamp", "")),
            "P/L": safe_float(point.get("P/L", 0)),
            "P/L %": safe_float(point.get("P/L %", 0)),
            "Value": safe_float(point.get("Value", 0)),
        })
    if len(rows) < 2:
        return
    chart_spec = {
        "background": "#202124",
        "height": 135,
        "data": {"values": rows},
        "layer": [
            {
                "mark": {"type": "area", "opacity": 0.18},
                "encoding": {
                    "x": {"field": "Time", "type": "ordinal", "axis": {"labelColor": "#94a3b8", "title": None, "labelAngle": 0}},
                    "y": {"field": "P/L", "type": "quantitative", "axis": {"labelColor": "#94a3b8", "title": "Live P/L", "gridColor": "rgba(255,255,255,0.06)"}},
                    "color": {"condition": [{"test": "datum['P/L'] >= 0", "value": "#22c55e"}], "value": "#ef4444"},
                    "tooltip": [
                        {"field": "Time", "title": "Time"},
                        {"field": "P/L", "title": "P/L", "format": ",.2f"},
                        {"field": "P/L %", "title": "P/L %", "format": ",.1f"},
                        {"field": "Value", "title": "Value", "format": ",.2f"},
                    ]
                }
            },
            {
                "mark": {"type": "line", "strokeWidth": 2.5, "point": {"filled": True, "size": 38}},
                "encoding": {
                    "x": {"field": "Time", "type": "ordinal"},
                    "y": {"field": "P/L", "type": "quantitative"},
                    "color": {"condition": [{"test": "datum['P/L'] >= 0", "value": "#22c55e"}], "value": "#ef4444"},
                }
            }
        ],
        "config": {"view": {"stroke": "transparent"}}
    }
    st.vega_lite_chart(chart_spec, width="stretch")



def dex_token_market_snapshot(token_mint):
    # Beginner-friendly pool pressure snapshot for a token.
    # Most Solana memecoins do not have a classic order book.
    token_mint = str(token_mint or "").strip()
    pair = dex_token_best_pair(token_mint)
    if not pair:
        return {}, "No live market data found yet."

    txns = pair.get("txns") or {}
    volume = pair.get("volume") or {}
    liquidity = pair.get("liquidity") or {}
    price_change = pair.get("priceChange") or {}
    base = pair.get("baseToken") or {}
    price = safe_float(pair.get("priceUsd", 0))
    buys_5m = safe_int((txns.get("m5") or {}).get("buys", 0))
    sells_5m = safe_int((txns.get("m5") or {}).get("sells", 0))
    buys_1h = safe_int((txns.get("h1") or {}).get("buys", 0))
    sells_1h = safe_int((txns.get("h1") or {}).get("sells", 0))
    vol_5m = safe_float(volume.get("m5", 0))
    vol_1h = safe_float(volume.get("h1", 0))
    liq_usd = safe_float(liquidity.get("usd", 0))
    change_5m = safe_float(price_change.get("m5", 0))
    change_1h = safe_float(price_change.get("h1", 0))
    total_5m = buys_5m + sells_5m
    total_1h = buys_1h + sells_1h
    buy_pressure = (buys_5m / total_5m * 100) if total_5m else ((buys_1h / total_1h * 100) if total_1h else 50)
    sell_pressure = 100 - buy_pressure
    pressure_edge = buy_pressure - sell_pressure

    if pressure_edge >= 20 and change_5m >= -5:
        read = "Buy pressure is clearly stronger right now. Good for holding the paper trade, but still watch exits."
        mood = "Supportive"
    elif pressure_edge <= -20:
        read = "Sell pressure is stronger right now. This paper trade needs caution."
        mood = "Risky"
    elif abs(change_5m) >= 15:
        read = "Price is moving fast. Good for learning, but spikes can reverse quickly."
        mood = "Volatile"
    else:
        read = "Pressure is balanced. Wait for a clearer push before judging the signal."
        mood = "Balanced"

    snapshot = {
        "Token": str(base.get("symbol") or short_address(token_mint)),
        "Price": price,
        "URL": pair.get("url", ""),
        "Liquidity USD": liq_usd,
        "Volume 5m": vol_5m,
        "Volume 1h": vol_1h,
        "Buys 5m": buys_5m,
        "Sells 5m": sells_5m,
        "Buys 1h": buys_1h,
        "Sells 1h": sells_1h,
        "Buy Pressure": buy_pressure,
        "Sell Pressure": sell_pressure,
        "Pressure Edge": pressure_edge,
        "Change 5m": change_5m,
        "Change 1h": change_1h,
        "Mood": mood,
        "Read": read,
    }
    return snapshot, None


def build_market_depth_ladder(snapshot):
    price = safe_float(snapshot.get("Price", 0))
    if price <= 0:
        return []
    liq = max(safe_float(snapshot.get("Liquidity USD", 0)), 1)
    buy_pressure = safe_float(snapshot.get("Buy Pressure", 50), 50)
    sell_pressure = safe_float(snapshot.get("Sell Pressure", 50), 50)
    vol_5m = max(safe_float(snapshot.get("Volume 5m", 0)), 1)
    scale = max(min((liq * 0.018) + (vol_5m * 0.06), 25000), 25)
    rows = []
    levels = [0.02, 0.015, 0.01, 0.005]
    for i, step in enumerate(levels):
        rows.append({"Side": "Sell wall", "Level": f"+{step*100:.1f}%", "Price": price * (1 + step), "Pressure USD": scale * (sell_pressure / 100) * (1.2 - i * 0.14), "Color Side": "SELL", "Sort": i})
    rows.append({"Side": "Live price", "Level": "Now", "Price": price, "Pressure USD": scale * 0.25, "Color Side": "PRICE", "Sort": 4})
    for i, step in enumerate([0.005, 0.01, 0.015, 0.02]):
        rows.append({"Side": "Buy support", "Level": f"-{step*100:.1f}%", "Price": price * (1 - step), "Pressure USD": scale * (buy_pressure / 100) * (1.2 - i * 0.14), "Color Side": "BUY", "Sort": 5 + i})
    return rows


def paper_trade_pressure_tape(trade, snapshot):
    history = trade.get("Live PnL History", [])
    chips = []
    if isinstance(history, list) and len(history) >= 2:
        recent = history[-8:]
        last_price = None
        for point in recent:
            if not isinstance(point, dict):
                continue
            price = safe_float(point.get("Price", 0))
            pnl = safe_float(point.get("P/L", 0))
            ts = str(point.get("Timestamp", ""))[-8:-3] or "now"
            if last_price is None:
                last_price = price
                continue
            diff = price - last_price
            if diff > 0:
                cls = "good"; label = "uptick"
            elif diff < 0:
                cls = "bad"; label = "downtick"
            else:
                cls = "neutral"; label = "flat"
            chips.append(f'<span class="paper-tape-chip {cls}">{ts} · {label} · {format_signed_usd(pnl)}</span>')
            last_price = price
    if not chips:
        buy_pressure = safe_float(snapshot.get("Buy Pressure", 50), 50)
        cls = "good" if buy_pressure >= 55 else "bad" if buy_pressure <= 45 else "neutral"
        chips.append(f'<span class="paper-tape-chip {cls}">live pressure · buy {buy_pressure:.0f}%</span>')
        chips.append(f'<span class="paper-tape-chip neutral">5m volume · {format_usd(snapshot.get("Volume 5m", 0))}</span>')
    return '<div class="paper-tape">' + ''.join(chips[-10:]) + '</div>'


def render_paper_trade_market_depth(trade, key_suffix=""):
    token_mint = str(trade.get("Token Mint", "") or "").strip()
    snapshot, error = dex_token_market_snapshot(token_mint)
    if error or not snapshot:
        st.info(error or "No live market depth yet.")
        return
    buy_pressure = safe_float(snapshot.get("Buy Pressure", 50), 50)
    sell_pressure = safe_float(snapshot.get("Sell Pressure", 50), 50)
    pressure_cls = "good" if buy_pressure >= sell_pressure else "bad"
    mood = str(snapshot.get("Mood", "Balanced"))
    mood_cls = "good" if mood == "Supportive" else "bad" if mood == "Risky" else "watch"
    change_5m_cls = 'good' if safe_float(snapshot.get('Change 5m', 0)) >= 0 else 'bad'
    change_1h_cls = 'good' if safe_float(snapshot.get('Change 1h', 0)) >= 0 else 'bad'

    st.markdown(
        f'''
        <div class="paper-depth-wrap">
            <div class="paper-depth-title"><div>Live Market Depth</div><span>Pool pressure view, not a classic CEX order book</span></div>
            <div class="paper-depth-grid">
                <div><span>Market mood</span><b class="{mood_cls}">{mood}</b></div>
                <div><span>Buy pressure</span><b class="{pressure_cls}">{buy_pressure:.0f}%</b></div>
                <div><span>Sell pressure</span><b>{sell_pressure:.0f}%</b></div>
                <div><span>5m volume</span><b>{format_usd(snapshot.get("Volume 5m", 0))}</b></div>
                <div><span>Liquidity</span><b>{format_usd(snapshot.get("Liquidity USD", 0))}</b></div>
                <div><span>5m move</span><b class="{change_5m_cls}">{safe_float(snapshot.get('Change 5m', 0)):.1f}%</b></div>
                <div><span>1h move</span><b class="{change_1h_cls}">{safe_float(snapshot.get('Change 1h', 0)):.1f}%</b></div>
                <div><span>5m buys / sells</span><b>{safe_int(snapshot.get("Buys 5m", 0))} / {safe_int(snapshot.get("Sells 5m", 0))}</b></div>
            </div>
            <div class="paper-ladder-note"><b>Beginner read:</b> {snapshot.get("Read", "-")}</div>
        </div>
        ''',
        unsafe_allow_html=True
    )

    rows = build_market_depth_ladder(snapshot)
    if rows:
        chart = {
            "background": "#202124",
            "height": 215,
            "data": {"values": rows},
            "mark": {"type": "bar", "cornerRadiusEnd": 5, "opacity": 0.88},
            "encoding": {
                "y": {"field": "Level", "type": "ordinal", "sort": {"field": "Sort", "order": "ascending"}, "axis": {"labelColor": "#cbd5e1", "title": None}},
                "x": {"field": "Pressure USD", "type": "quantitative", "axis": {"labelColor": "#94a3b8", "title": "Estimated pressure", "gridColor": "rgba(255,255,255,0.06)"}},
                "color": {"field": "Color Side", "type": "nominal", "scale": {"domain": ["SELL", "PRICE", "BUY"], "range": ["#ef4444", "#38bdf8", "#22c55e"]}, "legend": None},
                "tooltip": [{"field": "Side", "title": "Zone"}, {"field": "Level", "title": "Level"}, {"field": "Price", "title": "Price", "format": ",.8f"}, {"field": "Pressure USD", "title": "Pressure", "format": ",.2f"}],
            },
            "config": {"view": {"stroke": "transparent"}}
        }
        st.vega_lite_chart(chart, width="stretch")

    st.markdown("**Live trade tape**")
    st.markdown(paper_trade_pressure_tape(trade, snapshot), unsafe_allow_html=True)
    st.caption("The tape uses live price ticks and DexScreener pool pressure. It helps you see whether the fake trade is being supported or pressured.")


def reset_paper_wallet(balance=1000):
    st.session_state.paper_trades = []
    st.session_state.paper_events = []
    st.session_state.paper_settings.update({
        "fake_balance_start": safe_float(balance, 1000),
        "cash": safe_float(balance, 1000),
        "last_bot_ts": 0,
    })
    save_paper_settings()
    save_paper_trades()
    save_paper_events()
    st.session_state.paper_message = "Fake wallet reset. New paper-trading history starts now."


# -----------------------------
# DexScreener market-wide auto discovery helpers
# -----------------------------
@st.cache_data(ttl=120, show_spinner=False)
def fetch_dexscreener_token_profiles():
    """Fetch broad DexScreener token sources and keep Solana tokens only.

    This is intentionally market-wide, not limited to your watchlist.
    """
    endpoints = [
        "https://api.dexscreener.com/token-boosts/top/v1",
        "https://api.dexscreener.com/token-boosts/latest/v1",
        "https://api.dexscreener.com/token-profiles/latest/v1",
    ]

    profiles = []
    seen = set()
    errors = []

    for url in endpoints:
        try:
            response = requests.get(url, timeout=15)
            response.raise_for_status()
            data = response.json()
            if isinstance(data, dict):
                data = data.get("pairs") or data.get("tokens") or data.get("data") or []
            if not isinstance(data, list):
                continue

            for item in data:
                if not isinstance(item, dict):
                    continue
                chain_id = str(item.get("chainId") or item.get("chain") or "").lower()
                token_address = str(item.get("tokenAddress") or item.get("address") or item.get("baseToken", {}).get("address", "")).strip()
                if chain_id != "solana" or not token_address:
                    continue
                if token_address in seen or token_address in BASE_TOKEN_MINTS:
                    continue
                seen.add(token_address)
                item["tokenAddress"] = token_address
                item["sourceEndpoint"] = url.rsplit('/', 2)[-2]
                profiles.append(item)
        except Exception as error:
            errors.append(str(error))

    if not profiles and errors:
        return [], "DexScreener profile sources failed. Check internet connection or try again later."
    return profiles, None


@st.cache_data(ttl=30, show_spinner=False)
def fetch_dexscreener_pairs_raw(token_mint):
    try:
        url = f"https://api.dexscreener.com/token-pairs/v1/solana/{token_mint}"
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        data = response.json()
        pairs = data if isinstance(data, list) else data.get("pairs", []) if isinstance(data, dict) else []
        if not pairs:
            return [], "No DexScreener pairs found."
        return pairs, None
    except Exception as error:
        return [], f"DexScreener pair error: {error}"


def pair_age_hours(pair):
    try:
        created = pair.get("pairCreatedAt")
        if not created:
            return None
        created = float(created)
        if created > 10_000_000_000:
            created = created / 1000
        age_hours = (time.time() - created) / 3600
        if age_hours < 0:
            return None
        return age_hours
    except Exception:
        return None


def market_token_stage(score, liq, vol, txns, ch1h, ch24h, age_hours):
    if score >= 78:
        return "STRONG EARLY", "Early market traction: good activity, not obviously overextended yet."
    if score >= 62:
        return "EARLY WATCH", "Interesting early signal. Needs wallet confirmation before trusting it."
    if score >= 48:
        return "FIRST SIGNAL", "Some market activity, but not enough confirmation yet."
    return "FILTERED", "Too weak, too illiquid, too old, or already too extended."


def score_dexscreener_pair(pair, profile=None):
    profile = profile or {}
    base = pair.get("baseToken") or {}
    quote = pair.get("quoteToken") or {}
    liquidity = pair.get("liquidity") or {}
    volume = pair.get("volume") or {}
    txns = pair.get("txns") or {}
    price_change = pair.get("priceChange") or {}

    mint = str(base.get("address") or profile.get("tokenAddress") or "").strip()
    symbol = str(base.get("symbol") or profile.get("symbol") or short_address(mint)).strip()
    name = str(base.get("name") or profile.get("name") or symbol).strip()
    quote_symbol = str(quote.get("symbol") or "-")

    liq = safe_float(liquidity.get("usd", 0))
    vol24 = safe_float(volume.get("h24", 0))
    vol6 = safe_float(volume.get("h6", 0))
    vol1 = safe_float(volume.get("h1", 0))
    buys24 = safe_int((txns.get("h24") or {}).get("buys", 0))
    sells24 = safe_int((txns.get("h24") or {}).get("sells", 0))
    buys1 = safe_int((txns.get("h1") or {}).get("buys", 0))
    sells1 = safe_int((txns.get("h1") or {}).get("sells", 0))
    txns24 = buys24 + sells24
    txns1 = buys1 + sells1
    ch5 = safe_float(price_change.get("m5", 0))
    ch1 = safe_float(price_change.get("h1", 0))
    ch6 = safe_float(price_change.get("h6", 0))
    ch24 = safe_float(price_change.get("h24", 0))
    market_cap = safe_float(pair.get("marketCap", 0))
    fdv = safe_float(pair.get("fdv", 0))
    age_h = pair_age_hours(pair)

    score = 0
    reasons = []

    if 8_000 <= liq <= 350_000:
        score += 22
        reasons.append("liquidity is tradable but still early")
    elif 3_000 <= liq < 8_000:
        score += 10
        reasons.append("very early liquidity")
    elif liq > 1_000_000:
        score -= 12
        reasons.append("liquidity already large")
    else:
        score -= 10
        reasons.append("liquidity weak")

    if vol24 >= 250_000:
        score += 24
        reasons.append("strong 24h volume")
    elif vol24 >= 50_000:
        score += 18
        reasons.append("useful 24h volume")
    elif vol24 >= 15_000:
        score += 10
        reasons.append("some volume")
    else:
        score -= 8
        reasons.append("volume still low")

    if txns24 >= 250:
        score += 20
        reasons.append("many 24h transactions")
    elif txns24 >= 80:
        score += 12
        reasons.append("enough transaction activity")
    elif txns24 >= 25:
        score += 5
    else:
        score -= 8
        reasons.append("low transaction count")

    buy_ratio = buys24 / max(txns24, 1)
    if txns24 >= 30 and 0.48 <= buy_ratio <= 0.72:
        score += 9
        reasons.append("buy/sell balance is healthy")
    elif txns24 >= 30 and buy_ratio < 0.38:
        score -= 10
        reasons.append("sell pressure is high")
    elif txns24 >= 30 and buy_ratio > 0.82:
        score -= 5
        reasons.append("buy pressure may be too one-sided")

    if 5 <= ch1 <= 180:
        score += 12
        reasons.append("1h momentum positive")
    elif ch1 > 350:
        score -= 14
        reasons.append("1h move may already be late")
    elif ch1 < -25:
        score -= 10
        reasons.append("1h trend negative")

    if 10 <= ch24 <= 450:
        score += 8
    elif ch24 > 900:
        score -= 18
        reasons.append("24h move may already be exploded")
    elif ch24 < -40:
        score -= 8

    if age_h is not None:
        if 0.1 <= age_h <= 18:
            score += 18
            reasons.append("fresh pair")
        elif age_h <= 72:
            score += 9
            reasons.append("still relatively fresh")
        elif age_h > 168:
            score -= 10
            reasons.append("older pair")

    if market_cap and market_cap < 2_000_000:
        score += 6
    elif market_cap and market_cap > 20_000_000:
        score -= 10
        reasons.append("market cap already high")

    if profile.get("amount") or profile.get("totalAmount"):
        score += 5
        reasons.append("boosted visibility")

    score = max(0, min(100, round(score, 1)))
    stage, read = market_token_stage(score, liq, vol24, txns24, ch1, ch24, age_h)

    return {
        "Token": symbol or short_address(mint),
        "Name": name,
        "Mint": mint,
        "Pair": f"{symbol}/{quote_symbol}",
        "DEX": pair.get("dexId", "-"),
        "URL": pair.get("url", ""),
        "Alpha Score": score,
        "Stage": stage,
        "Read": read,
        "Reason": ", ".join(reasons[:4]) if reasons else "Market activity detected.",
        "Liquidity USD": liq,
        "Volume 24h": vol24,
        "Volume 6h": vol6,
        "Volume 1h": vol1,
        "Txns 24h": txns24,
        "Txns 1h": txns1,
        "Buys 24h": buys24,
        "Sells 24h": sells24,
        "Buy Ratio": buy_ratio,
        "Change 5m": ch5,
        "Change 1h": ch1,
        "Change 6h": ch6,
        "Change 24h": ch24,
        "Market Cap": market_cap,
        "FDV": fdv,
        "Age Hours": age_h if age_h is not None else -1,
        "Saved?": "Already saved" if token_already_saved(mint) else "New",
        "Source": "DexScreener market scan"
    }


def build_dexscreener_market_candidates(max_results=5, min_score=45, strict_early=True):
    profiles, profile_error = fetch_dexscreener_token_profiles()
    if profile_error:
        return pd.DataFrame(), profile_error

    rows = []
    seen = set()
    for profile in profiles[:80]:
        mint = str(profile.get("tokenAddress", "")).strip()
        if not mint or mint in seen or mint in BASE_TOKEN_MINTS:
            continue
        seen.add(mint)
        pairs, pair_error = fetch_dexscreener_pairs_raw(mint)
        if pair_error or not pairs:
            continue
        best_pair = sorted(pairs, key=lambda p: safe_float((p.get("liquidity") or {}).get("usd", 0)), reverse=True)[0]
        row = score_dexscreener_pair(best_pair, profile)
        if strict_early:
            liq = safe_float(row.get("Liquidity USD", 0))
            ch24 = safe_float(row.get("Change 24h", 0))
            age_h = safe_float(row.get("Age Hours", -1))
            if liq < 3_000 or liq > 1_500_000:
                continue
            if ch24 > 1200:
                continue
            if age_h > 0 and age_h > 336:
                continue
        if safe_float(row.get("Alpha Score", 0)) >= min_score:
            rows.append(row)

    if not rows:
        return pd.DataFrame(), None

    df = pd.DataFrame(rows)
    df = df.sort_values(by=["Alpha Score", "Volume 24h", "Txns 24h"], ascending=False).head(max_results).reset_index(drop=True)
    return df, None


def discover_wallets_for_market_candidates(token_df, max_tokens=5, max_wallets_per_token=6):
    if token_df is None or token_df.empty:
        return pd.DataFrame()

    wallet_map = {}
    for _, token_row in token_df.head(max_tokens).iterrows():
        mint = str(token_row.get("Mint", "")).strip()
        if not mint:
            continue
        discovered_df, discovery_error = discover_wallets_from_token_solscan(mint, max_wallets=max_wallets_per_token)
        if discovery_error and "401" in str(discovery_error):
            discovered_df, discovery_error = discover_wallets_from_token_helius(mint, max_wallets=max_wallets_per_token)
        elif discovery_error or discovered_df is None or discovered_df.empty:
            # Helius can still work even when Solscan returns no usable data.
            fallback_df, fallback_error = discover_wallets_from_token_helius(mint, max_wallets=max_wallets_per_token)
            if fallback_df is not None and not fallback_df.empty:
                discovered_df = fallback_df

        if discovered_df is None or discovered_df.empty:
            continue

        for _, wallet_row in discovered_df.iterrows():
            full_wallet = str(wallet_row.get("Full Wallet", "")).strip()
            if not full_wallet:
                continue
            if full_wallet not in wallet_map:
                wallet_map[full_wallet] = {
                    "Wallet": wallet_row.get("Wallet", short_address(full_wallet)),
                    "Full Wallet": full_wallet,
                    "Tokens Seen": set(),
                    "Token Symbols": [],
                    "Hits": 0,
                    "Score Sum": 0,
                    "Best Score": 0,
                    "Swaps Sum": 0,
                    "Reason": wallet_row.get("Reason", "Found around DexScreener candidate.")
                }
            w = wallet_map[full_wallet]
            w["Tokens Seen"].add(mint)
            symbol = str(token_row.get("Token", short_address(mint)))
            if symbol not in w["Token Symbols"]:
                w["Token Symbols"].append(symbol)
            hits = safe_int(wallet_row.get("Hits", wallet_row.get("Transfers", 1)), 1)
            score = safe_int(wallet_row.get("Score", 0))
            swaps = safe_int(wallet_row.get("Swaps", 0))
            w["Hits"] += max(hits, 1)
            w["Score Sum"] += score
            w["Best Score"] = max(w["Best Score"], score)
            w["Swaps Sum"] += swaps

    rows = []
    for full_wallet, w in wallet_map.items():
        tokens_count = len(w["Tokens Seen"])
        early_score = min(100, tokens_count * 28 + min(w["Hits"] * 4, 24) + min(w["Best Score"] / 2, 38) + min(w["Swaps Sum"] * 3, 20))
        token_text = ", ".join(w["Token Symbols"][:3])
        if len(w["Token Symbols"]) > 3:
            token_text += f" +{len(w['Token Symbols']) - 3} more"
        rows.append({
            "Wallet": w["Wallet"],
            "Full Wallet": full_wallet,
            "Early Tokens": tokens_count,
            "Tokens": token_text,
            "Hits": w["Hits"],
            "Best Score": w["Best Score"],
            "Swaps": w["Swaps Sum"],
            "Alpha Wallet Score": round(early_score, 1),
            "Saved?": "Saved" if wallet_already_saved(full_wallet) else "New",
            "Read": "Appears across multiple early tokens" if tokens_count >= 2 else "Appeared near one filtered token",
            "Reason": discovery_safe_text(w["Reason"], 120)
        })

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(by=["Alpha Wallet Score", "Early Tokens", "Hits", "Best Score"], ascending=False).reset_index(drop=True)
    return df




def discovery_wallet_verdict(row):
    early_tokens = safe_int(row.get("Early Tokens", 0))
    score = safe_float(row.get("Alpha Wallet Score", row.get("Early Score", row.get("Score", 0))))
    swaps = safe_int(row.get("Swaps", row.get("Swap Ins", 0)))
    saved = str(row.get("Saved?", "New")).lower()

    if saved == "saved":
        return "Already saved", "saved", "Already in your watchlist. Use only if you want to pin or compare."
    if early_tokens >= 2 and score >= 75:
        return "Priority", "hot", "Appears near multiple early tokens. This is the best wallet signal."
    if early_tokens >= 2:
        return "Repeat early", "good", "Appears around more than one early token. Worth adding and checking."
    if score >= 70 and swaps >= 2:
        return "Active early", "good", "Strong activity around one early token. Watch, but needs confirmation."
    if score >= 50:
        return "Watch", "watch", "Some useful activity. Lower priority than repeated early wallets."
    return "Low proof", "neutral", "Found near a token, but not enough proof yet."


def filter_fresh_wallet_candidates(wallet_df, exclude_seen=True, include_saved=False):
    if wallet_df is None or wallet_df.empty:
        return pd.DataFrame()

    df = wallet_df.copy()
    if "Full Wallet" not in df.columns:
        return df

    if exclude_seen:
        seen_wallets = set(st.session_state.get("dex_alpha_seen_wallets", []))
        if seen_wallets:
            df = df[~df["Full Wallet"].astype(str).isin(seen_wallets)]

    if not include_saved and "Saved?" in df.columns:
        df = df[df["Saved?"].astype(str).str.lower() != "saved"]

    if not df.empty:
        sort_cols = [col for col in ["Alpha Wallet Score", "Early Tokens", "Hits", "Best Score", "Swaps"] if col in df.columns]
        if sort_cols:
            df = df.sort_values(by=sort_cols, ascending=False).reset_index(drop=True)

    return df


def remember_alpha_scan_results(token_df=None, wallet_df=None):
    if "dex_alpha_seen_tokens" not in st.session_state:
        st.session_state.dex_alpha_seen_tokens = []
    if "dex_alpha_seen_wallets" not in st.session_state:
        st.session_state.dex_alpha_seen_wallets = []

    seen_tokens = set(st.session_state.get("dex_alpha_seen_tokens", []))
    seen_wallets = set(st.session_state.get("dex_alpha_seen_wallets", []))

    if token_df is not None and not token_df.empty and "Mint" in token_df.columns:
        seen_tokens.update(str(value).strip() for value in token_df["Mint"].dropna().tolist() if str(value).strip())
    if wallet_df is not None and not wallet_df.empty and "Full Wallet" in wallet_df.columns:
        seen_wallets.update(str(value).strip() for value in wallet_df["Full Wallet"].dropna().tolist() if str(value).strip())

    st.session_state.dex_alpha_seen_tokens = sorted(seen_tokens)
    st.session_state.dex_alpha_seen_wallets = sorted(seen_wallets)
    save_dex_alpha_seen_cache()


def fresh_dex_alpha_scan(max_tokens=5, min_score=45, strict_early=True, exclude_seen=True, include_saved_wallets=False):
    # Fresh Scan should not keep showing the same old winners.
    # We scan a wider pool, remove seen tokens/wallets, then only return truly fresh candidates.
    attempts = [max(max_tokens * 5, 25), max(max_tokens * 8, 40), max(max_tokens * 12, 60)]
    last_token_df = pd.DataFrame()
    last_wallet_df = pd.DataFrame()

    for scan_pool in attempts:
        token_df, token_error = build_dexscreener_market_candidates(
            max_results=scan_pool,
            min_score=min_score,
            strict_early=strict_early
        )
        if token_error:
            return pd.DataFrame(), pd.DataFrame(), token_error

        if token_df is None:
            token_df = pd.DataFrame()

        if exclude_seen and not token_df.empty:
            seen_tokens = set(st.session_state.get("dex_alpha_seen_tokens", []))
            if seen_tokens and "Mint" in token_df.columns:
                token_df = token_df[~token_df["Mint"].astype(str).isin(seen_tokens)].reset_index(drop=True)

        # Prefer not-yet-saved tokens for real discovery.
        if not token_df.empty and "Saved?" in token_df.columns:
            new_token_df = token_df[token_df["Saved?"].astype(str).str.lower() == "new"]
            if len(new_token_df) >= min(max_tokens, len(token_df)):
                token_df = new_token_df.reset_index(drop=True)

        token_df = token_df.head(max_tokens).reset_index(drop=True)
        last_token_df = token_df
        if token_df.empty:
            continue

        wallet_df = discover_wallets_for_market_candidates(token_df, max_tokens=max_tokens, max_wallets_per_token=14)
        wallet_df = filter_fresh_wallet_candidates(wallet_df, exclude_seen=exclude_seen, include_saved=include_saved_wallets)
        last_wallet_df = wallet_df

        # If fresh mode is on, do not silently fall back to old wallets. Return only fresh ones.
        if not wallet_df.empty or not exclude_seen:
            return token_df, wallet_df, None

    return last_token_df, last_wallet_df, None



# -----------------------------
# Market Monitor / Alpha Memory helpers
# -----------------------------

# -----------------------------
# Wallet documentation / opinion memory
# -----------------------------
def save_wallet_journal_pins():
    pins = sorted({str(value).strip() for value in st.session_state.get("wallet_journal_pins", []) if str(value).strip()})
    st.session_state.wallet_journal_pins = pins
    save_json_list(WALLET_JOURNAL_PINS_FILE, pins)


def wallet_journal_is_pinned(wallet_address):
    return str(wallet_address or "").strip() in set(st.session_state.get("wallet_journal_pins", []))


def toggle_wallet_journal_pin(wallet_address):
    wallet = str(wallet_address or "").strip()
    if not wallet:
        return False
    pins = set(st.session_state.get("wallet_journal_pins", []))
    if wallet in pins:
        pins.remove(wallet)
        pinned = False
    else:
        pins.add(wallet)
        pinned = True
    st.session_state.wallet_journal_pins = sorted(pins)
    save_wallet_journal_pins()
    return pinned


def wallet_journal_pinned_count():
    return len(st.session_state.get("wallet_journal_pins", []))


def wallet_journal_history_summary(wallet_address):
    df = wallet_history_dataframe(wallet_address)
    if df is None or df.empty:
        return {
            "Checks": 0,
            "Buys": 0,
            "Sells": 0,
            "P/L": 0.0,
            "Open Value": 0.0,
            "Volume": 0.0,
            "Last Action": "No live history yet",
            "Story": "Add to Watchlist or keep Market Monitor running so this wallet can build a live story."
        }

    buys = 0
    sells = 0
    buy_value = 0.0
    sell_value = 0.0
    last_action = "No clear action yet"
    for _, row in df.iterrows():
        side = str(row.get("Trade Side", "-") or "-").upper()
        if side not in ["BUY", "SELL"]:
            continue
        value = abs(safe_float(row.get("USD Volume Change", 0)))
        if value <= 0:
            value = abs(safe_float(row.get("Trade Counter Amount", 0)))
        if value <= 0:
            value = abs(safe_float(row.get("Trade Amount", 0)))
        token = str(row.get("Trade Token", "-") or "-")
        time_label = row.get("Time", "")
        if hasattr(time_label, "strftime"):
            time_label = time_label.strftime("%H:%M")
        if side == "BUY":
            buys += 1
            buy_value += value
            last_action = f"{time_label} · BUY · {journal_clean_text(token, 18)}"
        elif side == "SELL":
            sells += 1
            sell_value += value
            last_action = f"{time_label} · SELL · {journal_clean_text(token, 18)}"

    pnl = sell_value - buy_value
    open_value = max(buy_value - sell_value, 0)
    latest_volume = safe_float(df.iloc[-1].get("USD Volume", 0)) if len(df) else 0
    if buys and sells:
        story = "Entry and exit evidence exists. Check if sells happen after spikes."
    elif buys and not sells:
        story = "Accumulation visible. No clear exit yet in saved checks."
    elif sells and not buys:
        story = "Exit seen, but entry may be outside the selected history."
    else:
        story = "No clear BUY/SELL yet. Journal still needs more evidence."
    return {
        "Checks": len(df),
        "Buys": buys,
        "Sells": sells,
        "P/L": pnl,
        "Open Value": open_value,
        "Volume": latest_volume,
        "Last Action": last_action,
        "Story": story,
    }


def wallet_journal_action_recommendation(record, history_summary):
    verdict = str(record.get("Verdict", "Low proof") or "Low proof")
    trust = safe_float(record.get("Best Trust Score", 0))
    checks = safe_int(history_summary.get("Checks", 0))
    buys = safe_int(history_summary.get("Buys", 0))
    sells = safe_int(history_summary.get("Sells", 0))
    if verdict == "Strong thesis" and checks >= 2:
        return "Keep in Journal + Watchlist. Review chart before copying anything."
    if verdict == "Strong thesis":
        return "Journal pin first, then collect live Watchlist checks."
    if verdict == "Promising" and buys > 0:
        return "Watch closely. It has early evidence plus live buy behavior."
    if verdict == "Promising":
        return "Journal pin and wait for more proof before Watchlist pin."
    if trust >= 50:
        return "Keep as proof candidate. Do not prioritize yet."
    if sells > buys:
        return "Likely exit/noisy behavior. Only keep if it repeats early."
    return "Low priority. Let Market Monitor collect more evidence."


def update_wallet_documentation_from_watchlist_item(item, source="watchlist_recheck"):
    full_wallet = str(item.get("Full Wallet", item.get("Wallet", "")) or "").strip()
    if not full_wallet:
        return
    if "wallet_documentation" not in st.session_state:
        st.session_state.wallet_documentation = load_json_dict(WALLET_DOCUMENTATION_FILE)

    existing = st.session_state.wallet_documentation.get(full_wallet, {})
    history = wallet_journal_history_summary(full_wallet)
    trust_seed = safe_float(existing.get("Best Trust Score", 0))
    live_score = safe_float(item.get("Score", 0))
    buy_bonus = min(safe_int(history.get("Buys", 0)) * 4, 12)
    proof_bonus = min(safe_int(history.get("Checks", 0)) * 1.5, 12)
    trust = max(trust_seed, min(100, live_score + buy_bonus + proof_bonus))
    token_name = str(item.get("Latest Trade Token", item.get("Latest Token Mint", "")) or "").strip()
    token_names = existing.get("Token Names", []) if isinstance(existing.get("Token Names", []), list) else []
    if token_name and token_name != "-":
        token_names = list(dict.fromkeys(token_names + [token_name]))[:30]

    pseudo_record = {
        "Full Wallet": full_wallet,
        "Wallet": wallet_display_name(full_wallet, item.get("Wallet", ""), row=item),
        "Trust Score": trust,
        "Best Alpha Wallet Score": max(safe_float(existing.get("Best Alpha Wallet Score", 0)), live_score),
        "Appearances": max(safe_int(existing.get("Appearances", 0)), safe_int(item.get("Check Count", 0)), 1),
        "Early Tokens": max(safe_int(existing.get("Early Tokens", 0)), 1 if token_names else 0),
        "Hits": max(safe_int(existing.get("Hits", 0)), safe_int(item.get("Transfers", 0))),
        "Swaps": max(safe_int(existing.get("Swaps", 0)), safe_int(item.get("Swaps", 0))),
        "Token Names": token_names,
        "Saved?": "Saved" if wallet_already_saved(full_wallet) else "New",
        "Note": wallet_note(full_wallet) or str(item.get("Label Note", "") or ""),
        "Last Seen": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    run_id = f"watchlist-{pd.Timestamp.now().strftime('%Y%m%d%H%M%S')}-{full_wallet[-6:]}"
    update_wallet_documentation_from_memory(pseudo_record, run_id, source=source)
    save_json_dict(WALLET_DOCUMENTATION_FILE, st.session_state.get("wallet_documentation", {}))


def wallet_documentation_verdict(doc_record):
    trust = safe_float(doc_record.get("Best Trust Score", doc_record.get("Last Trust Score", 0)))
    appearances = safe_int(doc_record.get("Appearances", 0))
    early_tokens = safe_int(doc_record.get("Early Tokens", 0))
    good_events = safe_int(doc_record.get("Good Signals", 0))
    bad_events = safe_int(doc_record.get("Bad Signals", 0))

    if trust >= 85 and appearances >= 2 and good_events >= 2:
        return "Strong thesis", "Keep pinned / watch first", "This wallet repeatedly appears early with strong evidence."
    if trust >= 70 or (appearances >= 2 and early_tokens >= 2):
        return "Promising", "Watch + collect more proof", "This wallet has repeat early behavior, but still needs more outcome history."
    if bad_events > good_events and appearances >= 2:
        return "Risky / noisy", "Do not trust yet", "This wallet appears, but the evidence is mixed or noisy."
    if trust >= 50:
        return "Needs proof", "Observe only", "Interesting enough to track, not strong enough to copy or pin blindly."
    return "Low proof", "Usually skip", "Not enough useful history yet."


def wallet_documentation_tags_from_record(record):
    tags = []
    trust = safe_float(record.get("Trust Score", record.get("Best Trust Score", 0)))
    appearances = safe_int(record.get("Appearances", 0))
    early_tokens = safe_int(record.get("Early Tokens", 0))
    swaps = safe_int(record.get("Swaps", 0))
    saved = str(record.get("Saved?", "")).lower() == "saved"

    if trust >= 85:
        tags.append("High trust")
    elif trust >= 70:
        tags.append("Repeat early")
    elif trust >= 50:
        tags.append("Watch candidate")
    else:
        tags.append("Low proof")

    if appearances >= 3:
        tags.append("Seen often")
    if early_tokens >= 2:
        tags.append("Multiple tokens")
    if swaps >= 10:
        tags.append("Active swapper")
    if saved:
        tags.append("Saved")
    return tags[:6]


def update_wallet_documentation_from_memory(record, run_id, source="market_monitor"):
    full_wallet = str(record.get("Full Wallet", "") or "").strip()
    if not full_wallet:
        return

    if "wallet_documentation" not in st.session_state:
        st.session_state.wallet_documentation = load_json_dict(WALLET_DOCUMENTATION_FILE)

    docs = st.session_state.wallet_documentation
    existing = docs.get(full_wallet, {})
    timeline = existing.get("Timeline", [])
    if not isinstance(timeline, list):
        timeline = []

    trust = safe_float(record.get("Trust Score", 0))
    label = str(record.get("Label", "Watch candidate") or "Watch candidate")
    token_names = record.get("Token Names", [])
    if not isinstance(token_names, list):
        token_names = [str(token_names)] if token_names else []

    # Avoid duplicate timeline point for the same run.
    already_logged = any(str(event.get("Run ID", "")) == str(run_id) for event in timeline)
    good_signal = 1 if trust >= 70 or safe_int(record.get("Early Tokens", 0)) >= 2 else 0
    bad_signal = 1 if trust < 40 and safe_int(record.get("Appearances", 0)) >= 2 else 0

    note = wallet_note(full_wallet) or str(record.get("Note", "") or "")
    name = wallet_display_name(full_wallet, record.get("Wallet", ""), row=record)

    doc_record = {
        "Wallet": name,
        "Full Wallet": full_wallet,
        "First Seen": existing.get("First Seen", record.get("First Seen", pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"))),
        "Last Seen": record.get("Last Seen", pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")),
        "Appearances": max(safe_int(existing.get("Appearances", 0)), safe_int(record.get("Appearances", 0))),
        "Early Tokens": max(safe_int(existing.get("Early Tokens", 0)), safe_int(record.get("Early Tokens", 0))),
        "Hits": max(safe_int(existing.get("Hits", 0)), safe_int(record.get("Hits", 0))),
        "Swaps": max(safe_int(existing.get("Swaps", 0)), safe_int(record.get("Swaps", 0))),
        "Best Trust Score": max(safe_float(existing.get("Best Trust Score", 0)), trust),
        "Last Trust Score": trust,
        "Best Alpha Wallet Score": max(safe_float(existing.get("Best Alpha Wallet Score", 0)), safe_float(record.get("Best Alpha Wallet Score", 0))),
        "Token Names": list(dict.fromkeys((existing.get("Token Names", []) if isinstance(existing.get("Token Names", []), list) else []) + token_names))[:30],
        "Saved?": "Saved" if wallet_already_saved(full_wallet) else record.get("Saved?", "New"),
        "User Note": note,
        "Journal Pinned": wallet_journal_is_pinned(full_wallet),
        "Tags": wallet_documentation_tags_from_record(record),
        "Good Signals": safe_int(existing.get("Good Signals", 0)) + (0 if already_logged else good_signal),
        "Bad Signals": safe_int(existing.get("Bad Signals", 0)) + (0 if already_logged else bad_signal),
        "Source": source,
    }

    verdict, next_action, reason = wallet_documentation_verdict(doc_record)
    doc_record["Verdict"] = verdict
    doc_record["Next Action"] = next_action
    doc_record["Reason"] = reason

    if not already_logged:
        timeline.append({
            "Timestamp": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Run ID": run_id,
            "Source": source,
            "Trust Score": trust,
            "Label": label,
            "Verdict": verdict,
            "Next Action": next_action,
            "Early Tokens": safe_int(record.get("Early Tokens", 0)),
            "Hits": safe_int(record.get("Hits", 0)),
            "Swaps": safe_int(record.get("Swaps", 0)),
            "Tokens": ", ".join(token_names[:6]),
            "Reason": reason,
        })

    doc_record["Timeline"] = timeline[-80:]
    docs[full_wallet] = doc_record
    st.session_state.wallet_documentation = docs


def wallet_documentation_dataframe():
    records = []
    for record in st.session_state.get("wallet_documentation", {}).values():
        row = {k: v for k, v in record.items() if k != "Timeline"}
        if isinstance(row.get("Token Names"), list):
            row["Tokens"] = ", ".join(row.get("Token Names", [])[:6])
        if isinstance(row.get("Tags"), list):
            row["Tags"] = ", ".join(row.get("Tags", [])[:6])
        records.append(row)
    df = pd.DataFrame(records)
    if df.empty:
        return df
    sort_cols = [col for col in ["Best Trust Score", "Appearances", "Early Tokens"] if col in df.columns]
    if sort_cols:
        df = df.sort_values(sort_cols, ascending=False).reset_index(drop=True)
    return df


def journal_clean_text(value, max_len=120):
    """Return safe, human-readable text for journal cards.
    This also cleans old accidental HTML fragments that may already be saved in JSON.
    """
    if isinstance(value, list):
        value = ", ".join([str(v) for v in value if str(v).strip()])
    text = str(value or "").strip()
    if not text or text.lower() in ["nan", "none", "null"]:
        return "-"

    # Some older saved records may contain escaped HTML such as &lt;div class=...&gt;.
    # Decode first, remove tags second, then remove leftover code-like fragments.
    text = text.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"class=[\"'][^\"']*[\"']", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"/?div|/?span|journal-chip|wallet-doc-tags|wallet-doc-tag", " ", text, flags=re.IGNORECASE)
    text = text.replace("{", " ").replace("}", " ").replace(";", " ")
    text = re.sub(r"\s+", " ", text).strip(" -·|<>\n\t")
    if not text:
        return "-"
    if len(text) > max_len:
        return text[: max_len - 1].rstrip() + "…"
    return text


def journal_button_key(prefix, row_idx, wallet_address, scope="main"):
    wallet = str(wallet_address or "")
    digest = hashlib.sha1(wallet.encode("utf-8", errors="ignore")).hexdigest()[:12]
    safe_scope = re.sub(r"[^a-zA-Z0-9_]+", "_", str(scope or "main"))[:30]
    return f"{prefix}_{safe_scope}_{row_idx}_{digest}"


def journal_token_list(value, max_items=4):
    if isinstance(value, list):
        raw_items = value
    else:
        raw_items = str(value or "").split(",")
    items = []
    for item in raw_items:
        clean = journal_clean_text(item, 28)
        if clean and clean != "-" and "class=" not in clean.lower() and clean not in items:
            items.append(clean)
    return items[:max_items]


def journal_verdict_style(verdict):
    verdict = str(verdict or "Low proof")
    if verdict == "Strong thesis":
        return "strong", "", "Pin first"
    if verdict == "Promising":
        return "promising", "", "Watch closely"
    if verdict == "Needs proof":
        return "proof", "", "Collect proof"
    if verdict == "Risky / noisy":
        return "risky", "", "Be careful"
    return "low", "", "Usually skip"




def wallet_journal_story_cards(row, history):
    """Turn wallet evidence into a beginner-friendly story, not just numbers."""
    appearances = safe_int(row.get("Appearances", 0)) if hasattr(row, "get") else 0
    early_tokens = safe_int(row.get("Early Tokens", 0)) if hasattr(row, "get") else 0
    good = safe_int(row.get("Good Signals", 0)) if hasattr(row, "get") else 0
    bad = safe_int(row.get("Bad Signals", 0)) if hasattr(row, "get") else 0
    trust = safe_float(row.get("Best Trust Score", 0)) if hasattr(row, "get") else 0
    checks = safe_int(history.get("Checks", 0)) if isinstance(history, dict) else 0
    pnl = safe_float(history.get("P/L", 0)) if isinstance(history, dict) else 0
    buys = safe_int(history.get("Buys", 0)) if isinstance(history, dict) else 0
    sells = safe_int(history.get("Sells", 0)) if isinstance(history, dict) else 0
    open_value = safe_float(history.get("Open Value", 0)) if isinstance(history, dict) else 0

    if early_tokens >= 5 and good > bad and trust >= 80:
        thesis = "Repeated early wallet. It keeps appearing before or around fresh token activity."
    elif early_tokens >= 2:
        thesis = "Early pattern detected. The wallet has more than one early-token appearance."
    elif appearances >= 2:
        thesis = "Seen more than once. It is not proven yet, but worth documenting."
    else:
        thesis = "Single idea for now. Keep it in the Journal until it proves itself."

    if checks >= 8 and buys > sells:
        behavior = "Live history leans accumulation: more swap-ins than exits in the tracked range."
    elif checks >= 8 and sells > buys:
        behavior = "Live history shows exit activity: review whether sells happened after spikes."
    elif checks > 0:
        behavior = "Live history exists, but the trade direction is still not fully clear."
    else:
        behavior = "No live history yet. Journal evidence is mostly from market discovery."

    if pnl > 25:
        outcome = f"Tracked range is positive by about {format_signed_usd(pnl)}. Treat this as a useful sign, not proof."
    elif pnl < -25 and open_value > abs(pnl) * 0.5:
        outcome = f"P/L looks negative ({format_signed_usd(pnl)}), but open value remains. It may still be an open position."
    elif pnl < -25:
        outcome = f"Tracked range is negative ({format_signed_usd(pnl)}). Do not promote this wallet without more proof."
    elif open_value > 50:
        outcome = f"Open value around {format_usd(open_value)} is still being tracked. Wait for exit behavior."
    else:
        outcome = "No meaningful outcome yet. The next scans should show if the idea becomes useful."

    if bad > good and bad >= 2:
        risk = "Risk: noisy or unreliable so far. Keep it unpinned unless new evidence improves."
    elif early_tokens >= 4 and checks < 3:
        risk = "Risk: strong discovery signal, but not enough live follow-up yet."
    elif buys > 0 and sells == 0:
        risk = "Risk: exits are not visible yet. A good wallet should also show good selling behavior."
    else:
        risk = "Risk: normal. Keep watching for repeated useful behavior."

    return thesis, behavior, outcome, risk


def wallet_journal_beginner_decision(row, history, is_journal_pinned=False, is_saved=False):
    appearances = safe_int(row.get("Appearances", 0)) if hasattr(row, "get") else 0
    early_tokens = safe_int(row.get("Early Tokens", 0)) if hasattr(row, "get") else 0
    good = safe_int(row.get("Good Signals", 0)) if hasattr(row, "get") else 0
    bad = safe_int(row.get("Bad Signals", 0)) if hasattr(row, "get") else 0
    trust = safe_float(row.get("Best Trust Score", 0)) if hasattr(row, "get") else 0
    checks = safe_int(history.get("Checks", 0)) if isinstance(history, dict) else 0
    pnl = safe_float(history.get("P/L", 0)) if isinstance(history, dict) else 0

    if trust >= 85 and early_tokens >= 3 and good >= bad:
        return "Action: keep in Journal and Live pin. This is one of the wallets to review first."
    if trust >= 70 and early_tokens >= 2 and not is_journal_pinned:
        return "Action: Journal pin it first. Let the story build before copying anything."
    if is_journal_pinned and not is_saved and checks == 0:
        return "Action: add to Watchlist when you want live charts and P/L evidence."
    if is_saved and checks < 5:
        return "Action: leave Auto Scan running. It needs more checks before the story is reliable."
    if pnl < -50 and bad > good:
        return "Action: downgrade or skip for now. The evidence is not good enough."
    if appearances <= 1:
        return "Action: do nothing yet. One appearance is not enough proof."
    return "Action: keep watching. Promote only if it repeats useful early behavior."




def paper_results_for_source_wallet(wallet_address):
    wallet = str(wallet_address or "").strip()
    trades = []
    for trade in st.session_state.get("paper_trades", []):
        if str(trade.get("Source Wallet", "")).strip() == wallet:
            trades.append(trade)
    closed = [t for t in trades if str(t.get("Status", "")).lower() == "closed"]
    open_items = [t for t in trades if str(t.get("Status", "")).lower() == "open"]
    total_pnl = sum(safe_float(t.get("P/L", 0)) for t in closed)
    wins = sum(1 for t in closed if safe_float(t.get("P/L", 0)) > 0)
    losses = sum(1 for t in closed if safe_float(t.get("P/L", 0)) < 0)
    win_rate = (wins / len(closed) * 100) if closed else 0
    open_pnl = sum(safe_float(t.get("P/L", 0)) for t in open_items)
    return {
        "Total": len(trades),
        "Closed": len(closed),
        "Open": len(open_items),
        "Wins": wins,
        "Losses": losses,
        "Win Rate": win_rate,
        "Closed P/L": total_pnl,
        "Open P/L": open_pnl,
    }


def beginner_wallet_verdict(row, history, wallet_address="", is_journal_pinned=False, is_saved=False):
    """A simple beginner-facing decision layer. Raw scores stay behind the scenes."""
    trust = safe_float(row.get("Best Trust Score", row.get("Last Trust Score", 0))) if hasattr(row, "get") else 0
    appearances = safe_int(row.get("Appearances", 0)) if hasattr(row, "get") else 0
    early_tokens = safe_int(row.get("Early Tokens", 0)) if hasattr(row, "get") else 0
    good = safe_int(row.get("Good Signals", 0)) if hasattr(row, "get") else 0
    bad = safe_int(row.get("Bad Signals", 0)) if hasattr(row, "get") else 0
    checks = safe_int(history.get("Checks", 0)) if isinstance(history, dict) else 0
    buys = safe_int(history.get("Buys", 0)) if isinstance(history, dict) else 0
    sells = safe_int(history.get("Sells", 0)) if isinstance(history, dict) else 0
    hist_pnl = safe_float(history.get("P/L", 0)) if isinstance(history, dict) else 0
    paper = paper_results_for_source_wallet(wallet_address)
    paper_closed = safe_int(paper.get("Closed", 0))
    paper_pnl = safe_float(paper.get("Closed P/L", 0))
    paper_win_rate = safe_float(paper.get("Win Rate", 0))

    proof_points = 0
    proof_points += min(early_tokens * 12, 30)
    proof_points += min(appearances * 7, 21)
    proof_points += min(good * 10, 20)
    proof_points += min(checks * 2, 12)
    if paper_closed >= 3 and paper_pnl > 0:
        proof_points += 12
    if bad > good and bad >= 2:
        proof_points -= 18
    if paper_closed >= 2 and paper_pnl < 0:
        proof_points -= 15
    confidence = max(0, min(100, (trust * 0.45) + proof_points))

    if paper_closed >= 3 and paper_pnl > 0 and trust >= 65:
        label = "Copy candidate"
        tone = "copy"
        next_step = "Keep paper-copying this wallet. Promote only after repeated positive fake results."
    elif trust >= 75 and early_tokens >= 2 and good >= bad:
        label = "Paper trade first"
        tone = "paper"
        next_step = "Use Paper Trading before trusting it with real money."
    elif appearances >= 2 or early_tokens >= 1 or is_journal_pinned:
        label = "Watch first"
        tone = "watch"
        next_step = "Keep it in the Journal and collect more live checks."
    elif bad > good and bad >= 2:
        label = "Too noisy"
        tone = "risk"
        next_step = "Do not copy yet. Wait for cleaner repeated behavior."
    else:
        label = "Needs proof"
        tone = "proof"
        next_step = "Do nothing yet. One weak signal is not enough."

    why_bits = []
    if early_tokens:
        why_bits.append(f"seen around {early_tokens} early token(s)")
    if appearances:
        why_bits.append(f"appeared {appearances} time(s)")
    if checks:
        why_bits.append(f"{checks} live check(s) collected")
    if paper_closed:
        why_bits.append(f"paper result {format_signed_usd(paper_pnl)} with {paper_win_rate:.0f}% win rate")
    why = ", ".join(why_bits) if why_bits else "not enough repeated evidence yet"

    risk_bits = []
    if bad > good:
        risk_bits.append("bad/noisy evidence is higher than good evidence")
    if buys > 0 and sells == 0:
        risk_bits.append("buy behavior is visible, but exits are not proven")
    if hist_pnl < -25:
        risk_bits.append(f"tracked wallet range is negative ({format_signed_usd(hist_pnl)})")
    if paper_closed == 0:
        risk_bits.append("no paper-trading proof yet")
    risk = "; ".join(risk_bits) if risk_bits else "normal risk: still needs repeated proof"

    return {
        "Label": label,
        "Tone": tone,
        "Confidence": confidence,
        "Why": why,
        "Risk": risk,
        "Next": next_step,
        "Paper Closed": paper_closed,
        "Paper P/L": paper_pnl,
        "Paper Win Rate": paper_win_rate,
    }

def save_journal_refresh_settings():
    settings = st.session_state.get("journal_refresh_settings", {})
    save_json_dict(JOURNAL_REFRESH_SETTINGS_FILE, settings if isinstance(settings, dict) else {})


def journal_refresh_candidate_wallets(scope="Journal pinned only", min_trust=50, max_wallets=5):
    docs = st.session_state.get("wallet_documentation", {})
    pins = set(st.session_state.get("wallet_journal_pins", []))
    rows = []
    if isinstance(docs, dict):
        for wallet, record in docs.items():
            wallet_key = str(wallet or "").strip()
            if not wallet_key or not isinstance(record, dict):
                continue
            verdict = str(record.get("Verdict", "") or "")
            trust = safe_float(record.get("Best Trust Score", record.get("Last Trust Score", 0)))
            is_pinned = wallet_key in pins
            is_live = wallet_already_saved(wallet_key)

            include = False
            if scope == "Journal pinned only":
                include = is_pinned
            elif scope == "Pinned + live watchlist":
                include = is_pinned or is_live
            elif scope == "Strong thesis only":
                include = verdict == "Strong thesis"
            elif scope == "Strong + Promising":
                include = verdict in ["Strong thesis", "Promising"]
            elif scope == "All above trust filter":
                include = trust >= safe_float(min_trust, 50)
            else:
                include = is_pinned

            if include and trust >= safe_float(min_trust, 0):
                rows.append({
                    "Wallet": wallet_key,
                    "Name": wallet_display_name(wallet_key, record.get("Wallet", ""), row=record),
                    "Trust": trust,
                    "Verdict": verdict or "Needs proof",
                    "Pinned": is_pinned,
                    "Live": is_live,
                    "Early Tokens": safe_int(record.get("Early Tokens", 0)),
                    "Seen": safe_int(record.get("Seen Count", record.get("Appearances", 0))),
                })

    for wallet in pins:
        wallet_key = str(wallet or "").strip()
        if wallet_key and not any(row.get("Wallet") == wallet_key for row in rows):
            rows.append({
                "Wallet": wallet_key,
                "Name": wallet_display_name(wallet_key),
                "Trust": 0,
                "Verdict": "Needs proof",
                "Pinned": True,
                "Live": wallet_already_saved(wallet_key),
                "Early Tokens": 0,
                "Seen": 0,
            })

    rows = sorted(rows, key=lambda r: (bool(r.get("Pinned")), safe_float(r.get("Trust", 0)), safe_int(r.get("Early Tokens", 0)), safe_int(r.get("Seen", 0))), reverse=True)
    return rows[:max(safe_int(max_wallets, 5), 1)]


def journal_refresh_wallet_once(wallet_address):
    wallet_address = str(wallet_address or "").strip()
    if not wallet_address:
        return False, "No wallet address."

    for index, item in enumerate(st.session_state.get("watchlist_wallets", [])):
        full_wallet = str(item.get("Full Wallet", item.get("Wallet", "")) or "").strip()
        if full_wallet == wallet_address:
            result = recheck_wallet_watchlist_item(index)
            return bool(result), result or "Wallet refresh failed."

    wallet_tx_data, wallet_error = fetch_wallet_transactions(wallet_address)
    if wallet_error or wallet_tx_data is None or wallet_tx_data.empty:
        return False, "No fresh wallet data from Helius."

    total_tx, transfers, swaps, unknown, activity_level = summarize_wallet_activity(wallet_tx_data)
    wallet_signal, wallet_score, wallet_reason = get_wallet_signal(total_tx, transfers, swaps, unknown)
    usd_stats = estimate_wallet_usd_stats(wallet_tx_data)
    new_buys, new_sells, new_rotates = wallet_trade_counts(wallet_tx_data)
    latest_trade_event = latest_trade_event_from_wallet_data(wallet_tx_data)

    history_df = wallet_history_dataframe(wallet_address)
    if history_df is not None and not history_df.empty:
        last = history_df.iloc[-1]
        old_score = safe_int(last.get("Score", 0))
        old_swaps = safe_int(last.get("Swaps", 0))
        old_transfers = safe_int(last.get("Transfers", 0))
        old_buys = safe_int(last.get("Buys", 0))
        old_sells = safe_int(last.get("Sells", 0))
        old_rotates = safe_int(last.get("Rotates", 0))
        old_volume = safe_float(last.get("USD Volume", 0))
        old_largest = safe_float(last.get("Largest Tx", 0))
    else:
        old_score = old_swaps = old_transfers = old_buys = old_sells = old_rotates = 0
        old_volume = old_largest = 0

    new_score = safe_int(wallet_score)
    new_volume = safe_float(usd_stats.get("Total USD Volume", 0))
    new_largest = safe_float(usd_stats.get("Largest USD Tx", 0))
    name = wallet_display_name(wallet_address)

    append_wallet_history_point(
        wallet_address,
        name,
        old_score,
        old_swaps,
        old_transfers,
        old_volume,
        old_largest,
        new_score,
        safe_int(swaps),
        safe_int(transfers),
        new_volume,
        new_largest,
        new_score - old_score,
        safe_int(swaps) - old_swaps,
        safe_int(transfers) - old_transfers,
        new_volume - old_volume,
        new_largest - old_largest,
        old_buys,
        old_sells,
        old_rotates,
        new_buys,
        new_sells,
        new_rotates,
        latest_trade_event,
    )

    temp_item = {
        "Full Wallet": wallet_address,
        "Wallet": name,
        "Name": name,
        "Signal": wallet_signal,
        "Score": new_score,
        "Transfers": safe_int(transfers),
        "Swaps": safe_int(swaps),
        "Buys": new_buys,
        "Sells": new_sells,
        "Rotates": new_rotates,
        "USD Volume": new_volume,
        "Largest Tx": new_largest,
        "Check Count": wallet_history_point_count(wallet_address),
        "Reason": wallet_reason,
        "Latest Activity": latest_wallet_activity_text(wallet_tx_data),
        "Latest Token Mint": latest_wallet_token_mint(wallet_tx_data),
        "Latest Trade Side": latest_trade_event.get("Trade Side", "-"),
        "Latest Trade Token": latest_trade_event.get("Trade Token", "-"),
        "Latest Trade Hint": latest_trade_event.get("Trade Hint", "-"),
        "Last Checked": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
    }
    update_wallet_documentation_from_watchlist_item(temp_item, source="journal_refresh")
    return True, f"{name}: Journal refreshed."


def journal_refresh_batch(scope=None, min_trust=None, max_wallets=None):
    settings = st.session_state.get("journal_refresh_settings", {})
    scope = scope or settings.get("scope", "Journal pinned only")
    min_trust = safe_int(min_trust if min_trust is not None else settings.get("min_trust", 50), 50)
    max_wallets = safe_int(max_wallets if max_wallets is not None else settings.get("max_wallets", 5), 5)
    candidates = journal_refresh_candidate_wallets(scope, min_trust, max_wallets)
    ok_count = 0
    fail_count = 0
    messages = []
    for row in candidates:
        ok, msg = journal_refresh_wallet_once(row.get("Wallet", ""))
        ok_count += 1 if ok else 0
        fail_count += 0 if ok else 1
        messages.append(msg)
    settings["last_refresh_ts"] = time.time()
    settings["last_refresh_label"] = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    st.session_state.journal_refresh_settings = settings
    save_journal_refresh_settings()
    return ok_count, fail_count, messages


def render_journal_refresh_controls():
    settings = st.session_state.get("journal_refresh_settings", {})
    st.markdown(
        """
        <style>
        .journal-refresh-panel{border:1px solid rgba(45,212,191,.22);background:linear-gradient(135deg,rgba(15,118,110,.13),rgba(15,23,42,.96));border-radius:18px;padding:13px 15px;margin:12px 0 16px}.journal-refresh-panel b{color:#f8fafc}.journal-refresh-panel p{color:#cbd5e1;font-size:13px;line-height:1.45;margin:4px 0 0}.journal-refresh-status{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px}.journal-refresh-status span{border:1px solid rgba(255,255,255,.09);background:rgba(255,255,255,.04);border-radius:999px;padding:5px 8px;color:#cbd5e1;font-size:11px;font-weight:800}
        </style>
        <div class="journal-refresh-panel"><b>Journal Refresh Engine</b><p>Refreshes selected Journal wallets with fresh Helius data, updates their story, history, proof, and paper-copy signals. Use this for your preference-based wallet list instead of refreshing every random wallet.</p></div>
        """,
        unsafe_allow_html=True,
    )
    c1, c2, c3, c4, c5 = st.columns([0.16, 0.24, 0.20, 0.16, 0.24])
    with c1:
        enabled = st.toggle("Auto refresh", value=bool(settings.get("enabled", False)), key="journal_refresh_enabled")
    with c2:
        scope_options = ["Journal pinned only", "Pinned + live watchlist", "Strong thesis only", "Strong + Promising", "All above trust filter"]
        current_scope = settings.get("scope", "Journal pinned only")
        scope = st.selectbox("Wallet group", scope_options, index=scope_options.index(current_scope) if current_scope in scope_options else 0, key="journal_refresh_scope")
    with c3:
        interval_options = [15, 30, 60, 120, 300]
        current_interval = safe_int(settings.get("interval_seconds", 60), 60)
        interval = st.selectbox("Interval", interval_options, index=interval_options.index(current_interval) if current_interval in interval_options else 2, format_func=lambda x: f"{x} sec", key="journal_refresh_interval")
    with c4:
        max_options = [3, 5, 8, 12]
        current_max = safe_int(settings.get("max_wallets", 5), 5)
        max_wallets = st.selectbox("Max wallets", max_options, index=max_options.index(current_max) if current_max in max_options else 1, key="journal_refresh_max")
    with c5:
        min_trust = st.slider("Min trust", 0, 100, safe_int(settings.get("min_trust", 50), 50), 5, key="journal_refresh_min_trust")

    st.session_state.journal_refresh_settings.update({
        "enabled": bool(enabled),
        "scope": scope,
        "interval_seconds": safe_int(interval, 60),
        "max_wallets": safe_int(max_wallets, 5),
        "min_trust": safe_int(min_trust, 50),
    })
    save_journal_refresh_settings()

    candidates = journal_refresh_candidate_wallets(scope, min_trust, max_wallets)
    candidate_text = ", ".join([journal_clean_text(row.get("Name", row.get("Wallet", "Wallet")), 24) for row in candidates[:5]]) or "No matching wallets yet"
    st.markdown(
        f'<div class="journal-refresh-status"><span>Next group: {discovery_safe_text(candidate_text, 180)}</span><span>Last refresh: {discovery_safe_text(settings.get("last_refresh_label", "never") or "never", 30)}</span></div>',
        unsafe_allow_html=True,
    )

    b1, b2 = st.columns([0.22, 0.78])
    with b1:
        if st.button("Refresh journal now", type="primary", key="journal_refresh_now"):
            with st.spinner("Refreshing selected Journal wallets..."):
                ok_count, fail_count, messages = journal_refresh_batch(scope, min_trust, max_wallets)
            st.success(f"Journal refreshed: {ok_count} updated, {fail_count} skipped.")
            if messages:
                with st.expander("Refresh details", expanded=False):
                    for msg in messages[:20]:
                        st.write(msg)
            st.rerun()
    with b2:
        st.caption("Tip: Start with Journal pinned only. Add Strong + Promising later when you want broader automatic learning.")

    if bool(enabled):
        st_autorefresh(interval=max(safe_int(interval, 60), 15) * 1000, key="wallet_journal_auto_refresh")
        last_ts = safe_float(settings.get("last_refresh_ts", 0), 0)
        if time.time() - last_ts >= max(safe_int(interval, 60), 15):
            journal_refresh_batch(scope, min_trust, max_wallets)
            st.rerun()

def render_wallet_documentation_cards(limit=10, only_pinned=False, compact=True, key_scope="journal"):
    df = wallet_documentation_dataframe()
    if df is None or df.empty:
        st.info("No wallet documentation yet. Run Market Monitor scans so the app can build wallet opinions over time.")
        return

    pins = set(st.session_state.get("wallet_journal_pins", []))
    if "Full Wallet" in df.columns:
        df["Journal Pinned"] = df["Full Wallet"].astype(str).isin(pins)
    if only_pinned:
        df = df[df.get("Journal Pinned", False) == True]
        if df.empty:
            st.info("No Journal-pinned wallets yet. Use Journal pin on wallets you want to follow without adding everything to Watchlist.")
            return

    verdict_rank = {"Strong thesis": 0, "Promising": 1, "Needs proof": 2, "Risky / noisy": 3, "Low proof": 4}
    if "Verdict" in df.columns:
        df["_verdict_rank"] = df["Verdict"].map(verdict_rank).fillna(9)
    else:
        df["_verdict_rank"] = 9
    df["_journal_pin_rank"] = df.get("Journal Pinned", False).astype(int) if "Journal Pinned" in df.columns else 0
    if "Best Trust Score" not in df.columns:
        df["Best Trust Score"] = 0
    df = df.sort_values(["_journal_pin_rank", "_verdict_rank", "Best Trust Score"], ascending=[False, True, False]).head(limit).reset_index(drop=True)

    st.markdown(
        """
        <style>
        .journal-help{border:1px solid rgba(45,212,191,.24);background:linear-gradient(135deg,rgba(20,184,166,.12),rgba(15,23,42,.95));border-radius:16px;padding:12px 14px;margin:8px 0 14px;color:#d1fae5;font-size:13px;line-height:1.45}
        .journal-card-native{border:1px solid rgba(255,255,255,.10);background:linear-gradient(145deg,rgba(15,23,42,.98),rgba(30,41,59,.72));border-radius:18px;padding:13px 14px;margin-bottom:8px;box-shadow:0 18px 38px rgba(0,0,0,.18)}
        .journal-card-native.strong{border-color:rgba(34,197,94,.48);background:linear-gradient(145deg,rgba(5,46,22,.38),rgba(15,23,42,.96))}.journal-card-native.promising{border-color:rgba(59,130,246,.45);background:linear-gradient(145deg,rgba(30,58,138,.30),rgba(15,23,42,.96))}.journal-card-native.proof{border-color:rgba(245,158,11,.44);background:linear-gradient(145deg,rgba(120,53,15,.24),rgba(15,23,42,.96))}.journal-card-native.risky{border-color:rgba(248,113,113,.45);background:linear-gradient(145deg,rgba(127,29,29,.25),rgba(15,23,42,.96))}
        .journal-card-top{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}.journal-card-name{color:#f8fafc;font-weight:950;font-size:15px}.journal-card-sub{color:#94a3b8;font-size:11px;margin-top:2px}.journal-pill{border-radius:999px;padding:5px 8px;font-size:10px;font-weight:900;white-space:nowrap}.journal-pill.strong{background:rgba(34,197,94,.18);border:1px solid rgba(34,197,94,.35);color:#bbf7d0}.journal-pill.promising{background:rgba(59,130,246,.17);border:1px solid rgba(59,130,246,.35);color:#bfdbfe}.journal-pill.proof{background:rgba(245,158,11,.18);border:1px solid rgba(245,158,11,.35);color:#fde68a}.journal-pill.risky{background:rgba(248,113,113,.17);border:1px solid rgba(248,113,113,.35);color:#fecaca}.journal-pill.low{background:rgba(148,163,184,.14);border:1px solid rgba(148,163,184,.25);color:#cbd5e1}
        .trustbar{height:7px;border-radius:999px;background:rgba(255,255,255,.08);overflow:hidden;margin:10px 0}.trustbar span{display:block;height:100%;border-radius:999px;background:linear-gradient(90deg,#38bdf8,#22c55e)}
        .journal-mini{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:7px;margin:9px 0}.journal-mini div{border:1px solid rgba(255,255,255,.07);background:rgba(255,255,255,.035);border-radius:12px;padding:8px 9px}.journal-mini span{display:block;color:#94a3b8;font-size:10px;text-transform:uppercase;letter-spacing:.04em}.journal-mini b{color:#f8fafc;font-size:13px}.journal-mini .good{color:#4ade80}.journal-mini .bad{color:#f87171}.journal-readbox{border:1px solid rgba(255,255,255,.07);background:rgba(255,255,255,.035);border-radius:12px;padding:8px 10px;margin-top:8px;color:#dbeafe;font-size:12px;line-height:1.45}.journal-readbox b{color:#f8fafc}.journal-chipline{display:flex;flex-wrap:wrap;gap:5px;margin-top:8px}.journal-chip{border:1px solid rgba(45,212,191,.25);background:rgba(45,212,191,.08);color:#ccfbf1;border-radius:999px;padding:4px 7px;font-size:10.5px;font-weight:800}.journal-chip.tag{border-color:rgba(96,165,250,.25);background:rgba(96,165,250,.08);color:#dbeafe}.journal-note{color:#fde68a;font-size:12px;margin-top:7px}.journal-action-caption{font-size:11px;color:#94a3b8;margin-top:-2px;margin-bottom:6px}.beginner-verdict{border:1px solid rgba(255,255,255,.08);border-radius:14px;padding:10px 11px;margin:9px 0;background:rgba(255,255,255,.035);font-size:12px;line-height:1.45;color:#dbeafe}.beginner-verdict b{color:#f8fafc}.beginner-verdict.copy{border-color:rgba(34,197,94,.34);background:rgba(34,197,94,.10);color:#bbf7d0}.beginner-verdict.paper{border-color:rgba(56,189,248,.34);background:rgba(56,189,248,.10);color:#bae6fd}.beginner-verdict.watch{border-color:rgba(245,158,11,.32);background:rgba(245,158,11,.10);color:#fde68a}.beginner-verdict.risk{border-color:rgba(248,113,113,.34);background:rgba(248,113,113,.10);color:#fecaca}.beginner-verdict.proof{border-color:rgba(148,163,184,.25);background:rgba(148,163,184,.08);color:#cbd5e1}@media(max-width:1000px){.journal-mini{grid-template-columns:repeat(2,minmax(0,1fr))}}
        </style>
        <div class="journal-help"><b>Beginner logic:</b> Journal pin saves an idea. Live pin scans it constantly. Use the Journal to build proof first, then only Live pin wallets that keep showing useful behavior.</div>
        """,
        unsafe_allow_html=True,
    )

    for idx in range(0, len(df), 2):
        cols = st.columns(2)
        for offset, col in enumerate(cols):
            row_idx = idx + offset
            if row_idx >= len(df):
                continue
            row = df.iloc[row_idx]
            full_wallet = str(row.get("Full Wallet", "") or "").strip()
            if not full_wallet:
                continue

            name = journal_clean_text(wallet_display_name(full_wallet, row.get("Wallet", ""), row=row), 44)
            verdict = journal_clean_text(row.get("Verdict", "Needs proof"), 24)
            cls, icon, _ = journal_verdict_style(verdict)
            trust = max(0, min(100, safe_float(row.get("Best Trust Score", 0))))
            appearances = safe_int(row.get("Appearances", 0))
            early_tokens = safe_int(row.get("Early Tokens", 0))
            good = safe_int(row.get("Good Signals", 0))
            bad = safe_int(row.get("Bad Signals", 0))
            reason = journal_clean_text(row.get("Reason", "-"), 135)
            history = wallet_journal_history_summary(full_wallet)
            is_journal_pinned = wallet_journal_is_pinned(full_wallet)
            is_saved = wallet_already_saved(full_wallet)
            thesis_story, behavior_story, outcome_story, risk_story = wallet_journal_story_cards(row, history)
            beginner_verdict = beginner_wallet_verdict(row, history, full_wallet, is_journal_pinned, is_saved)
            next_action = journal_clean_text(beginner_verdict.get("Next", wallet_journal_beginner_decision(row, history, is_journal_pinned, is_saved)), 150)
            tokens = journal_token_list(row.get("Tokens", row.get("Token Names", [])), 4)
            tags = journal_token_list(row.get("Tags", []), 4)
            note = journal_clean_text(row.get("User Note", ""), 120)
            pnl = safe_float(history.get("P/L", 0))
            pnl_class = "good" if pnl > 0 else "bad" if pnl < 0 else ""
            proof_text = "Good proof" if good > bad and good > 0 else "Needs proof" if good == 0 else "Mixed proof"
            status_line = f"{'Journal pinned' if is_journal_pinned else 'Idea candidate'} · {'Live Watchlist' if is_saved else 'Not live-scanned'}"
            chip_html = "".join([f'<span class="journal-chip">{discovery_safe_text(x, 24)}</span>' for x in tokens])
            chip_html += "".join([f'<span class="journal-chip tag">{discovery_safe_text(x, 24)}</span>' for x in tags])
            if not chip_html:
                chip_html = '<span class="journal-chip tag">No token proof yet</span>'

            with col:
                st.markdown(
                    f"""
                    <div class="journal-card-native {cls}">
                      <div class="journal-card-top">
                        <div><div class="journal-card-name">{discovery_safe_text(name, 44)}</div><div class="journal-card-sub">{short_address(full_wallet)} · {status_line}</div></div>
                        <div class="journal-pill {cls}">{discovery_safe_text(verdict, 22)}</div>
                      </div>
                      <div class="trustbar"><span style="width:{trust:.0f}%"></span></div>
                      <div class="journal-mini">
                        <div><span>Trust</span><b>{trust:.0f}/100</b></div>
                        <div><span>Seen</span><b>{appearances}x</b></div>
                        <div><span>Early tokens</span><b>{early_tokens}</b></div>
                        <div><span>Proof</span><b>{good}/{bad} · {proof_text}</b></div>
                        <div><span>Checks</span><b>{safe_int(history.get('Checks', 0))}</b></div>
                        <div><span>Swap in/out</span><b>{safe_int(history.get('Buys', 0))}/{safe_int(history.get('Sells', 0))}</b></div>
                        <div><span>Est. P/L</span><b class="{pnl_class}">{format_signed_usd(pnl)}</b></div>
                        <div><span>Open value</span><b>{format_usd(history.get('Open Value', 0))}</b></div>
                      </div>
                      <div class="beginner-verdict {beginner_verdict.get('Tone', 'proof')}"><b>Beginner verdict: {discovery_safe_text(beginner_verdict.get('Label', 'Needs proof'), 30)}</b> · Confidence {safe_float(beginner_verdict.get('Confidence', 0)):.0f}/100<br><b>Why:</b> {discovery_safe_text(beginner_verdict.get('Why', '-'), 155)}<br><b>Risk:</b> {discovery_safe_text(beginner_verdict.get('Risk', '-'), 155)}</div>
                      <div class="journal-readbox"><b>Thesis:</b> {discovery_safe_text(thesis_story, 150)}<br><b>Behavior:</b> {discovery_safe_text(behavior_story, 150)}<br><b>Outcome:</b> {discovery_safe_text(outcome_story, 150)}<br><b>Next:</b> {discovery_safe_text(next_action, 150)}</div>
                      {f'<div class="journal-note"><b>Note:</b> {discovery_safe_text(note, 120)}</div>' if note and note != '-' else ''}
                      <div class="journal-chipline">{chip_html}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                st.markdown('<div class="journal-action-caption">Actions for this wallet</div>', unsafe_allow_html=True)
                b1, b2, b3, b4 = st.columns([1, 1, 1, 1])
                with b1:
                    pin_label = "Unpin idea" if is_journal_pinned else "Journal pin"
                    if st.button(pin_label, key=journal_button_key("wallet_doc_journal_pin", row_idx, full_wallet, key_scope)):
                        pinned = toggle_wallet_journal_pin(full_wallet)
                        if full_wallet in st.session_state.get("wallet_documentation", {}):
                            st.session_state.wallet_documentation[full_wallet]["Journal Pinned"] = pinned
                            save_json_dict(WALLET_DOCUMENTATION_FILE, st.session_state.wallet_documentation)
                        st.rerun()
                with b2:
                    if st.button("Open", key=journal_button_key("wallet_doc_open", row_idx, full_wallet, key_scope)):
                        st.session_state.wallet_address_input = full_wallet
                        st.session_state._sw_auto_scan = True
                        add_recent_item("recent_wallets", full_wallet)
                        st.session_state.section_override = "Smart Wallets"
                        st.rerun()
                with b3:
                    if st.button("Watchlist", key=journal_button_key("wallet_doc_add", row_idx, full_wallet, key_scope), disabled=is_saved):
                        item = {
                            "Wallet": name, "Name": name, "Wallet Alias": name,
                            "Label Note": str(row.get("User Note", "")), "Full Wallet": full_wallet,
                            "Signal": "Monitor" if trust >= 70 else "Watch", "Score": safe_int(row.get("Best Alpha Wallet Score", trust)),
                            "Transfers": safe_int(row.get("Hits", 0)), "Swaps": safe_int(row.get("Swaps", 0)),
                            "USD Volume": 0, "Largest Tx": 0,
                            "Last Checked": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
                            "Check Count": 1, "Pinned": False, "Change": "Added from Journal Hub",
                        }
                        add_wallet_to_watchlist(item)
                        st.success(st.session_state.watchlist_message)
                with b4:
                    if st.button("Live pin", key=journal_button_key("wallet_doc_live_pin", row_idx, full_wallet, key_scope)):
                        if not wallet_already_saved(full_wallet):
                            item = {
                                "Wallet": name, "Name": name, "Wallet Alias": name,
                                "Label Note": str(row.get("User Note", "")), "Full Wallet": full_wallet,
                                "Signal": "Monitor", "Score": safe_int(row.get("Best Alpha Wallet Score", trust)),
                                "Transfers": safe_int(row.get("Hits", 0)), "Swaps": safe_int(row.get("Swaps", 0)),
                                "USD Volume": 0, "Largest Tx": 0,
                                "Last Checked": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
                                "Check Count": 1, "Pinned": True, "Change": "Live pinned from Journal Hub",
                            }
                            add_wallet_to_watchlist(item)
                        for saved_item in st.session_state.watchlist_wallets:
                            if str(saved_item.get("Full Wallet", "")).strip() == full_wallet:
                                saved_item["Pinned"] = True
                                saved_item["Wallet"] = name
                                saved_item["Name"] = name
                                saved_item["Wallet Alias"] = name
                        set_wallet_label(full_wallet, name, str(row.get("User Note", "")))
                        save_json_list(WALLET_WATCHLIST_FILE, st.session_state.watchlist_wallets)
                        if not wallet_journal_is_pinned(full_wallet):
                            toggle_wallet_journal_pin(full_wallet)
                        st.success("Wallet live-pinned and kept in Journal.")

def render_wallet_documentation_timeline(wallet_address=None, limit=30):
    docs = st.session_state.get("wallet_documentation", {})
    events = []
    for full_wallet, record in docs.items():
        if wallet_address and str(full_wallet).strip() != str(wallet_address).strip():
            continue
        for event in record.get("Timeline", []) if isinstance(record.get("Timeline", []), list) else []:
            event_row = dict(event)
            event_row["Wallet"] = wallet_display_name(full_wallet, record.get("Wallet", ""), row=record)
            event_row["Address"] = short_address(full_wallet)
            events.append(event_row)
    if not events:
        st.info("No wallet documentation timeline yet.")
        return
    df = pd.DataFrame(events).sort_values("Timestamp", ascending=False).head(limit)
    show_cols = ["Timestamp", "Wallet", "Address", "Verdict", "Trust Score", "Early Tokens", "Hits", "Swaps", "Tokens", "Next Action", "Reason"]
    st.dataframe(df[[col for col in show_cols if col in df.columns]], width="stretch", hide_index=True)



def save_market_monitor_settings():
    settings = st.session_state.get("market_monitor_settings", {})
    save_json_dict(MARKET_MONITOR_SETTINGS_FILE, settings)


def set_market_monitor_setting(key, value):
    if "market_monitor_settings" not in st.session_state:
        st.session_state.market_monitor_settings = {}
    if st.session_state.market_monitor_settings.get(key) != value:
        st.session_state.market_monitor_settings[key] = value
        save_market_monitor_settings()


def persist_market_memory():
    save_json_list(MARKET_SNAPSHOTS_FILE, st.session_state.get("market_snapshots", [])[-500:])
    save_json_dict(TOKEN_MEMORY_FILE, st.session_state.get("token_memory", {}))
    save_json_dict(WALLET_ALPHA_MEMORY_FILE, st.session_state.get("wallet_alpha_memory", {}))
    save_json_dict(WALLET_DOCUMENTATION_FILE, st.session_state.get("wallet_documentation", {}))
    save_json_list(DISCOVERY_RUNS_FILE, st.session_state.get("discovery_runs", [])[-120:])


def market_monitor_should_scan(settings):
    if not settings.get("enabled"):
        return False
    interval_seconds = max(int(settings.get("interval_minutes", 10)), 1) * 60
    last_ts = float(settings.get("last_scan_ts", 0) or 0)
    return (time.time() - last_ts) >= interval_seconds


def token_memory_quality(token_record):
    best_score = safe_float(token_record.get("Best Alpha Score", 0))
    seen = safe_int(token_record.get("Times Seen", 0))
    best_change = max(
        safe_float(token_record.get("Best 1h Change", 0)),
        safe_float(token_record.get("Best 6h Change", 0)),
        safe_float(token_record.get("Best 24h Change", 0)),
    )
    liq = safe_float(token_record.get("Last Liquidity", 0))
    penalty = 0
    if liq < 3000:
        penalty += 8
    if safe_float(token_record.get("Worst 1h Change", 0)) < -45:
        penalty += 10
    quality = min(100, max(0, best_score * 0.55 + min(best_change, 500) / 8 + min(seen * 6, 20) - penalty))
    return round(quality, 1)


def update_token_memory_from_scan(token_df, run_id):
    if "token_memory" not in st.session_state:
        st.session_state.token_memory = load_json_dict(TOKEN_MEMORY_FILE)

    now_label = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    updated = []
    if token_df is None or token_df.empty:
        return updated

    for _, row in token_df.iterrows():
        mint = str(row.get("Mint", "") or "").strip()
        if not mint:
            continue
        existing = st.session_state.token_memory.get(mint, {})
        times_seen = safe_int(existing.get("Times Seen", 0)) + 1
        first_seen = existing.get("First Seen", now_label)
        best_score = max(safe_float(existing.get("Best Alpha Score", 0)), safe_float(row.get("Alpha Score", 0)))
        best_1h = max(safe_float(existing.get("Best 1h Change", -9999)), safe_float(row.get("Change 1h", 0)))
        best_6h = max(safe_float(existing.get("Best 6h Change", -9999)), safe_float(row.get("Change 6h", 0)))
        best_24h = max(safe_float(existing.get("Best 24h Change", -9999)), safe_float(row.get("Change 24h", 0)))
        worst_1h = min(safe_float(existing.get("Worst 1h Change", 9999)), safe_float(row.get("Change 1h", 0)))

        record = {
            "Token": row.get("Token", short_address(mint)),
            "Name": row.get("Name", row.get("Token", short_address(mint))),
            "Mint": mint,
            "First Seen": first_seen,
            "Last Seen": now_label,
            "Times Seen": times_seen,
            "Best Alpha Score": round(best_score, 1),
            "Last Alpha Score": safe_float(row.get("Alpha Score", 0)),
            "Best 1h Change": round(best_1h, 2),
            "Best 6h Change": round(best_6h, 2),
            "Best 24h Change": round(best_24h, 2),
            "Worst 1h Change": round(worst_1h, 2),
            "Last Liquidity": safe_float(row.get("Liquidity USD", 0)),
            "Last Volume 24h": safe_float(row.get("Volume 24h", 0)),
            "Last Txns 24h": safe_int(row.get("Txns 24h", 0)),
            "Last Buy Ratio": safe_float(row.get("Buy Ratio", 0)),
            "Last Stage": row.get("Stage", "-"),
            "Last Run": run_id,
            "URL": row.get("URL", ""),
        }
        record["Token Quality"] = token_memory_quality(record)
        st.session_state.token_memory[mint] = record
        updated.append(record)
    return updated


def wallet_memory_trust(wallet_record):
    appearances = safe_int(wallet_record.get("Appearances", 0))
    early_tokens = len(wallet_record.get("Token Mints", [])) if isinstance(wallet_record.get("Token Mints", []), list) else safe_int(wallet_record.get("Early Tokens", 0))
    best_score = safe_float(wallet_record.get("Best Alpha Wallet Score", 0))
    avg_token_quality = safe_float(wallet_record.get("Avg Token Quality", 0))
    saved_bonus = 8 if wallet_already_saved(wallet_record.get("Full Wallet", "")) else 0
    trust = appearances * 7 + early_tokens * 18 + best_score * 0.38 + avg_token_quality * 0.28 + saved_bonus
    return round(min(100, max(0, trust)), 1)


def update_wallet_memory_from_scan(wallet_df, token_df, run_id):
    if "wallet_alpha_memory" not in st.session_state:
        st.session_state.wallet_alpha_memory = load_json_dict(WALLET_ALPHA_MEMORY_FILE)

    now_label = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    token_quality_map = {}
    if token_df is not None and not token_df.empty:
        for _, token_row in token_df.iterrows():
            token_quality_map[str(token_row.get("Token", ""))] = safe_float(token_row.get("Alpha Score", 0))

    updated = []
    if wallet_df is None or wallet_df.empty:
        return updated

    for _, row in wallet_df.iterrows():
        full_wallet = str(row.get("Full Wallet", "") or "").strip()
        if not full_wallet:
            continue
        existing = st.session_state.wallet_alpha_memory.get(full_wallet, {})
        token_symbols = [part.strip() for part in str(row.get("Tokens", "")).replace("+", ",").split(",") if part.strip()]
        token_mints = existing.get("Token Mints", []) if isinstance(existing.get("Token Mints", []), list) else []
        token_names = existing.get("Token Names", []) if isinstance(existing.get("Token Names", []), list) else []
        for symbol in token_symbols:
            if symbol not in token_names and len(symbol) <= 40:
                token_names.append(symbol)
        early_tokens = max(safe_int(row.get("Early Tokens", 0)), len(token_names), safe_int(existing.get("Early Tokens", 0)))
        appearances = safe_int(existing.get("Appearances", 0)) + 1
        best_score = max(safe_float(existing.get("Best Alpha Wallet Score", 0)), safe_float(row.get("Alpha Wallet Score", 0)))
        avg_token_quality = safe_float(existing.get("Avg Token Quality", 0))
        current_quality = safe_float(row.get("Alpha Wallet Score", 0))
        avg_token_quality = round(((avg_token_quality * max(appearances - 1, 0)) + current_quality) / max(appearances, 1), 1)

        name = wallet_display_name(full_wallet, row.get("Wallet", ""), row=row)
        record = {
            "Wallet": name,
            "Full Wallet": full_wallet,
            "First Seen": existing.get("First Seen", now_label),
            "Last Seen": now_label,
            "Appearances": appearances,
            "Early Tokens": early_tokens,
            "Token Names": token_names[:20],
            "Token Mints": token_mints[:50],
            "Hits": safe_int(existing.get("Hits", 0)) + safe_int(row.get("Hits", 0)),
            "Swaps": safe_int(existing.get("Swaps", 0)) + safe_int(row.get("Swaps", 0)),
            "Best Alpha Wallet Score": round(best_score, 1),
            "Last Alpha Wallet Score": safe_float(row.get("Alpha Wallet Score", 0)),
            "Avg Token Quality": avg_token_quality,
            "Saved?": "Saved" if wallet_already_saved(full_wallet) else "New",
            "Last Run": run_id,
            "Note": wallet_note(full_wallet),
        }
        record["Trust Score"] = wallet_memory_trust(record)
        if record["Trust Score"] >= 85:
            record["Label"] = "Core alpha wallet"
            record["Next Action"] = "Add + pin, then keep Auto Scan ON."
        elif record["Appearances"] >= 2 or record["Trust Score"] >= 70:
            record["Label"] = "Repeat early wallet"
            record["Next Action"] = "Add to watchlist. Pin after one more useful signal."
        elif record["Trust Score"] >= 50:
            record["Label"] = "Watch candidate"
            record["Next Action"] = "Watch, but do not trust yet."
        else:
            record["Label"] = "Low proof"
            record["Next Action"] = "Usually ignore unless the token is special."
        st.session_state.wallet_alpha_memory[full_wallet] = record
        update_wallet_documentation_from_memory(record, run_id, source="market_monitor")
        updated.append(record)
    return updated


def run_market_monitor_scan(max_tokens=None, min_score=None, wallets_per_token=None, strict_early=None, source="manual"):
    settings = st.session_state.get("market_monitor_settings", {})
    max_tokens = int(max_tokens if max_tokens is not None else settings.get("max_tokens", 5))
    min_score = int(min_score if min_score is not None else settings.get("min_score", 55))
    wallets_per_token = int(wallets_per_token if wallets_per_token is not None else settings.get("wallets_per_token", 8))
    strict_early = bool(strict_early if strict_early is not None else settings.get("strict_early", True))

    run_id = pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")
    started_label = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")

    token_df, token_error = build_dexscreener_market_candidates(max_results=max_tokens, min_score=min_score, strict_early=strict_early)
    if token_error:
        st.session_state.market_monitor_message = token_error
        return pd.DataFrame(), pd.DataFrame(), token_error
    if token_df is None:
        token_df = pd.DataFrame()

    wallet_df = discover_wallets_for_market_candidates(token_df, max_tokens=max_tokens, max_wallets_per_token=wallets_per_token) if not token_df.empty else pd.DataFrame()
    if wallet_df is None:
        wallet_df = pd.DataFrame()

    token_memory_updates = update_token_memory_from_scan(token_df, run_id)
    wallet_memory_updates = update_wallet_memory_from_scan(wallet_df, token_df, run_id)

    snapshot_rows = []
    if not token_df.empty:
        for _, row in token_df.iterrows():
            snapshot_rows.append({
                "Run ID": run_id,
                "Timestamp": started_label,
                "Token": row.get("Token", "-"),
                "Mint": row.get("Mint", ""),
                "Alpha Score": safe_float(row.get("Alpha Score", 0)),
                "Stage": row.get("Stage", "-"),
                "Liquidity USD": safe_float(row.get("Liquidity USD", 0)),
                "Volume 24h": safe_float(row.get("Volume 24h", 0)),
                "Txns 24h": safe_int(row.get("Txns 24h", 0)),
                "Change 1h": safe_float(row.get("Change 1h", 0)),
                "Change 24h": safe_float(row.get("Change 24h", 0)),
                "Wallets Found": 0 if wallet_df.empty else len(wallet_df),
                "Source": source,
            })

    st.session_state.market_snapshots = (st.session_state.get("market_snapshots", []) + snapshot_rows)[-500:]
    run_record = {
        "Run ID": run_id,
        "Timestamp": started_label,
        "Source": source,
        "Tokens": 0 if token_df.empty else len(token_df),
        "Wallets": 0 if wallet_df.empty else len(wallet_df),
        "Best Token Score": safe_float(token_df["Alpha Score"].max()) if not token_df.empty and "Alpha Score" in token_df.columns else 0,
        "Best Wallet Score": safe_float(wallet_df["Alpha Wallet Score"].max()) if not wallet_df.empty and "Alpha Wallet Score" in wallet_df.columns else 0,
        "Min Score": min_score,
        "Strict Early": strict_early,
    }
    st.session_state.discovery_runs = (st.session_state.get("discovery_runs", []) + [run_record])[-120:]
    st.session_state.market_monitor_settings["last_scan_ts"] = time.time()
    st.session_state.market_monitor_settings["last_scan_label"] = started_label
    save_market_monitor_settings()
    persist_market_memory()

    st.session_state.auto_discovered_tokens = token_df
    st.session_state.auto_discovered_wallets = wallet_df
    st.session_state.market_monitor_message = f"Market scan saved: {len(token_df)} token(s), {len(wallet_df)} wallet candidate(s)."
    return token_df, wallet_df, None


def market_monitor_memory_tables():
    token_records = list(st.session_state.get("token_memory", {}).values())
    wallet_records = list(st.session_state.get("wallet_alpha_memory", {}).values())
    token_df = pd.DataFrame(token_records)
    wallet_df = pd.DataFrame(wallet_records)
    if not token_df.empty:
        sort_cols = [col for col in ["Token Quality", "Best Alpha Score", "Times Seen"] if col in token_df.columns]
        if sort_cols:
            token_df = token_df.sort_values(sort_cols, ascending=False).reset_index(drop=True)
    if not wallet_df.empty:
        sort_cols = [col for col in ["Trust Score", "Appearances", "Early Tokens", "Best Alpha Wallet Score"] if col in wallet_df.columns]
        if sort_cols:
            wallet_df = wallet_df.sort_values(sort_cols, ascending=False).reset_index(drop=True)
    return token_df, wallet_df


def render_monitor_wallet_memory_cards(wallet_df, limit=8):
    if wallet_df is None or wallet_df.empty:
        st.info("No wallet memory yet. Run a Market Monitor scan first.")
        return
    show_df = wallet_df.head(limit).reset_index(drop=True)
    for idx in range(0, len(show_df), 2):
        cols = st.columns(2)
        for offset, col in enumerate(cols):
            row_idx = idx + offset
            if row_idx >= len(show_df):
                continue
            row = show_df.iloc[row_idx]
            full_wallet = str(row.get("Full Wallet", "") or "").strip()
            name = wallet_display_name(full_wallet, row.get("Wallet", ""), row=row)
            trust = safe_float(row.get("Trust Score", 0))
            label = row.get("Label", "Watch candidate")
            cls = "core" if trust >= 85 else "repeat" if trust >= 70 else "watch" if trust >= 50 else "low"
            token_names = row.get("Token Names", [])
            if isinstance(token_names, list):
                token_text = ", ".join(token_names[:4])
            else:
                token_text = str(token_names or "-")
            note = wallet_note(full_wallet) or str(row.get("Note", "") or "")
            with col:
                st.markdown(
                    f"""
                    <div class="memory-wallet-card {cls}">
                        <div class="memory-card-top">
                            <div>
                                <div class="memory-wallet-name">{discovery_safe_text(name, 44)}</div>
                                <div class="memory-wallet-address">{short_address(full_wallet)} · {row.get('Saved?', 'New')}</div>
                            </div>
                            <div class="memory-trust-pill {cls}">{trust:.0f}/100</div>
                        </div>
                        <div class="memory-label">{label}</div>
                        <div class="memory-grid">
                            <div><span>Seen</span><b>{safe_int(row.get('Appearances', 0))}x</b></div>
                            <div><span>Early tokens</span><b>{safe_int(row.get('Early Tokens', 0))}</b></div>
                            <div><span>Hits</span><b>{safe_int(row.get('Hits', 0))}</b></div>
                            <div><span>Swaps</span><b>{safe_int(row.get('Swaps', 0))}</b></div>
                        </div>
                        <div class="memory-note"><b>Tokens:</b> {discovery_safe_text(token_text, 90)}</div>
                        <div class="memory-note"><b>Next:</b> {discovery_safe_text(row.get('Next Action', '-'), 100)}</div>
                        {f'<div class="memory-user-note">Note: {discovery_safe_text(note, 100)}</div>' if note else ''}
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                b1, b2, b3 = st.columns([0.28, 0.34, 0.38])
                with b1:
                    if st.button("Add", key=f"monitor_mem_add_{row_idx}_{full_wallet}", disabled=wallet_already_saved(full_wallet)):
                        item = {
                            "Wallet": name,
                            "Name": name,
                            "Wallet Alias": name,
                            "Label Note": note,
                            "Full Wallet": full_wallet,
                            "Signal": "Monitor" if trust >= 70 else "Watch",
                            "Score": safe_int(row.get("Best Alpha Wallet Score", trust)),
                            "Transfers": safe_int(row.get("Hits", 0)),
                            "Swaps": safe_int(row.get("Swaps", 0)),
                            "USD Volume": 0,
                            "Largest Tx": 0,
                            "Last Checked": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
                            "Check Count": 1,
                            "Pinned": False,
                            "Change": "Added from Market Monitor memory",
                        }
                        set_wallet_label(full_wallet, name, note)
                        add_wallet_to_watchlist(item)
                        st.success(st.session_state.watchlist_message)
                with b2:
                    if st.button("Add + pin", key=f"monitor_mem_pin_{row_idx}_{full_wallet}"):
                        item = {
                            "Wallet": name,
                            "Name": name,
                            "Wallet Alias": name,
                            "Label Note": note,
                            "Full Wallet": full_wallet,
                            "Signal": "Monitor",
                            "Score": safe_int(row.get("Best Alpha Wallet Score", trust)),
                            "Transfers": safe_int(row.get("Hits", 0)),
                            "Swaps": safe_int(row.get("Swaps", 0)),
                            "USD Volume": 0,
                            "Largest Tx": 0,
                            "Last Checked": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
                            "Check Count": 1,
                            "Pinned": True,
                            "Change": "Pinned from Market Monitor memory",
                        }
                        set_wallet_label(full_wallet, name, note)
                        add_wallet_to_watchlist(item)
                        for saved_item in st.session_state.watchlist_wallets:
                            if str(saved_item.get("Full Wallet", "")).strip() == full_wallet:
                                saved_item["Pinned"] = True
                        save_json_list(WALLET_WATCHLIST_FILE, st.session_state.watchlist_wallets)
                        st.success("Wallet added and pinned.")
                with b3:
                    if st.button("Open wallet", key=f"monitor_mem_open_{row_idx}_{full_wallet}"):
                        st.session_state.wallet_address_input = full_wallet
                        st.session_state._sw_auto_scan = True
                        add_recent_item("recent_wallets", full_wallet)
                        st.session_state.section_override = "Smart Wallets"
                        st.rerun()


def render_monitor_token_memory_table(token_df, limit=12):
    if token_df is None or token_df.empty:
        st.info("No token memory yet. Run a Market Monitor scan first.")
        return
    show_cols = [
        "Token", "Token Quality", "Times Seen", "Best Alpha Score", "Last Alpha Score",
        "Best 1h Change", "Best 6h Change", "Best 24h Change", "Last Liquidity", "Last Volume 24h", "Last Stage", "Last Seen"
    ]
    view = token_df[[col for col in show_cols if col in token_df.columns]].head(limit).copy()
    for col in ["Last Liquidity", "Last Volume 24h"]:
        if col in view.columns:
            view[col] = view[col].apply(format_usd)
    for col in ["Best 1h Change", "Best 6h Change", "Best 24h Change"]:
        if col in view.columns:
            view[col] = view[col].apply(lambda v: f"{safe_float(v):+.1f}%")
    st.dataframe(view, width="stretch", hide_index=True)

def render_alpha_scan_dashboard(token_df, wallet_df, only_new_wallets=True):
    token_count = 0 if token_df is None or token_df.empty else len(token_df)
    wallet_count = 0 if wallet_df is None or wallet_df.empty else len(wallet_df)
    repeat_count = 0
    strong_count = 0
    avg_score = 0

    if wallet_df is not None and not wallet_df.empty:
        if "Early Tokens" in wallet_df.columns:
            repeat_count = int((pd.to_numeric(wallet_df["Early Tokens"], errors="coerce").fillna(0) >= 2).sum())
        if "Alpha Wallet Score" in wallet_df.columns:
            strong_count = int((pd.to_numeric(wallet_df["Alpha Wallet Score"], errors="coerce").fillna(0) >= 75).sum())
            avg_score = safe_float(pd.to_numeric(wallet_df["Alpha Wallet Score"], errors="coerce").fillna(0).mean())

    mode_text = "Fresh-only mode" if only_new_wallets else "May include older/saved wallets"
    st.markdown(
        f"""
        <div class="alpha-control-panel alpha-results-panel">
            <div class="alpha-panel-top">
                <div>
                    <div class="alpha-panel-title">Discovery result</div>
                    <div class="alpha-panel-sub">{mode_text}. Best signal: repeated early wallets across multiple filtered tokens.</div>
                </div>
                <div class="alpha-live-pill">LIVE RADAR</div>
            </div>
            <div class="alpha-stat-grid">
                <div><span>Tokens filtered</span><strong>{token_count}</strong></div>
                <div><span>Fresh wallets</span><strong>{wallet_count}</strong></div>
                <div><span>Repeated early</span><strong>{repeat_count}</strong></div>
                <div><span>Strong wallets</span><strong>{strong_count}</strong></div>
                <div><span>Avg wallet score</span><strong>{avg_score:.0f}/100</strong></div>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )


def wallet_group_label(row):
    verdict, verdict_class, verdict_hint = discovery_wallet_verdict(row)
    score = safe_float(row.get("Alpha Wallet Score", row.get("Early Score", 0)))
    early_tokens = safe_int(row.get("Early Tokens", 0))
    saved = str(row.get("Saved?", "New")).lower()

    if saved == "saved":
        return "Saved / already known"
    if early_tokens >= 2 or score >= 82:
        return "Priority"
    if score >= 65:
        return "Watch"
    return "Low proof"


def render_wallet_candidate_row(row, idx, key_prefix="auto_wallets"):
    full_wallet = str(row.get("Full Wallet", "") or "").strip()
    if not full_wallet:
        return

    auto_name = wallet_display_name(full_wallet, row.get("Wallet", ""), row=row)
    default_name = st.session_state.get(f"{key_prefix}_name_{idx}_{full_wallet}", auto_name)
    tokens = discovery_safe_text(row.get("Tokens", row.get("Last Token", "-")), 135)
    score = safe_float(row.get("Alpha Wallet Score", row.get("Early Score", row.get("Score", 0))))
    early_tokens = safe_int(row.get("Early Tokens", 0))
    hits = safe_int(row.get("Hits", 0))
    swaps = safe_int(row.get("Swaps", row.get("Swap Ins", 0)))
    saved = str(row.get("Saved?", "New"))
    read = discovery_safe_text(row.get("Read", "Appeared around an early token."), 180)
    verdict, verdict_class, verdict_hint = discovery_wallet_verdict(row)
    identity = wallet_identity_badge(row, full_wallet)
    note = wallet_note(full_wallet)

    if early_tokens >= 2:
        beginner_action = "Add + pin"
        action_read = "Repeated early wallet. Best candidate to monitor first."
        action_class = "good"
    elif score >= 70:
        beginner_action = "Add to watch"
        action_read = "Strong enough to track. Pin after it proves itself."
        action_class = "watch"
    elif saved.lower() == "saved":
        beginner_action = "Already saved"
        action_read = "Open only if you want to compare with your watchlist."
        action_class = "saved"
    else:
        beginner_action = "Usually skip"
        action_read = "Low proof. Keep only if the token itself looks special."
        action_class = "low"

    name_col, score_col, proof_col = st.columns([0.50, 0.18, 0.32])
    with st.container(border=True):
        st.markdown(
            f"""
            <div class="wallet-identity-card {action_class}">
                <div class="wallet-identity-top">
                    <div>
                        <div class="wallet-friendly-name">{discovery_safe_text(default_name, 42)}</div>
                        <div class="wallet-address-line">{short_address(full_wallet)} · {identity} · {saved}</div>
                    </div>
                    <div class="wallet-score-pill {action_class}">{score:.0f}/100</div>
                </div>
                <div class="wallet-proof-grid">
                    <div><span>Early tokens</span><b>{early_tokens}</b></div>
                    <div><span>Hits</span><b>{hits}</b></div>
                    <div><span>Swaps</span><b>{swaps}</b></div>
                    <div><span>Signal</span><b>{verdict}</b></div>
                </div>
                <div class="wallet-human-read"><b>{beginner_action}:</b> {action_read}<br><b>Why:</b> {discovery_safe_text(verdict_hint, 160)}</div>
                <div class="wallet-token-strip"><b>Seen around:</b> {tokens}</div>
            </div>
            """,
            unsafe_allow_html=True
        )

        edit_col, note_col = st.columns([0.38, 0.62])
        with edit_col:
            custom_name = st.text_input(
                "Name",
                value=default_name,
                key=f"{key_prefix}_name_{idx}_{full_wallet}",
                label_visibility="collapsed",
                help="Give this wallet a human name before saving it. You do not need to remember the address."
            )
        with note_col:
            custom_note = st.text_input(
                "Note",
                value=note,
                key=f"{key_prefix}_note_{idx}_{full_wallet}",
                label_visibility="collapsed",
                placeholder="optional note, e.g. early BONK wallet / strong exits",
                help="Optional note shown later in Settings."
            )

        friendly_name = str(custom_name or auto_name).strip() or auto_name
        watchlist_item = {
            "Wallet": friendly_name,
            "Name": friendly_name,
            "Wallet Alias": friendly_name,
            "Label Note": custom_note,
            "Full Wallet": full_wallet,
            "Signal": "Monitor" if score >= 75 or early_tokens >= 2 else "Watch",
            "Score": safe_int(row.get("Best Score", row.get("Alpha Wallet Score", row.get("Early Score", 0)))),
            "Transfers": safe_int(row.get("Hits", 0)),
            "Swaps": safe_int(row.get("Swaps", row.get("Swap Ins", 0))),
            "USD Volume": 0,
            "Largest Tx": 0,
            "Last Checked": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
            "Check Count": 1,
            "Previous Score": safe_int(row.get("Best Score", 0)),
            "Previous Swaps": safe_int(row.get("Swaps", row.get("Swap Ins", 0))),
            "Previous Transfers": safe_int(row.get("Hits", 0)),
            "Previous USD Volume": 0,
            "Previous Largest Tx": 0,
            "Score Change": 0,
            "Swaps Change": 0,
            "Transfers Change": 0,
            "USD Volume Change": 0,
            "Largest Tx Change": 0,
            "Latest Activity": f"Found around Auto Discovery tokens: {row.get('Tokens', row.get('Last Token', '-'))}",
            "Latest Token Mint": "",
            "Pinned": False,
            "Change": "New wallet from Auto Discovery"
        }

        b1, b2, b3, b4 = st.columns([0.18, 0.22, 0.18, 0.42])
        with b1:
            if st.button("Add", key=f"{key_prefix}_add_{idx}_{full_wallet}"):
                set_wallet_label(full_wallet, friendly_name, custom_note)
                add_wallet_to_watchlist(watchlist_item)
                st.success(st.session_state.watchlist_message)
        with b2:
            if st.button("Add + pin", key=f"{key_prefix}_pin_{idx}_{full_wallet}"):
                set_wallet_label(full_wallet, friendly_name, custom_note)
                watchlist_item["Pinned"] = True
                add_wallet_to_watchlist(watchlist_item)
                for saved_item in st.session_state.watchlist_wallets:
                    if str(saved_item.get("Full Wallet", saved_item.get("Wallet", ""))).strip() == full_wallet:
                        saved_item["Pinned"] = True
                        saved_item["Wallet"] = friendly_name
                        saved_item["Name"] = friendly_name
                        saved_item["Wallet Alias"] = friendly_name
                save_json_list(WALLET_WATCHLIST_FILE, st.session_state.watchlist_wallets)
                st.success("Wallet added and pinned." if "already" not in st.session_state.watchlist_message.lower() else "Wallet was already saved and is now pinned.")
        with b3:
            if st.button("Open", key=f"{key_prefix}_open_{idx}_{full_wallet}"):
                st.session_state.wallet_address_input = full_wallet
                add_recent_item("recent_wallets", full_wallet)
                st.session_state.section_override = "Smart Wallets"
                st.rerun()
        with b4:
            st.caption(read)

def render_discovered_wallet_candidates(wallet_df, title="Wallet candidates", caption="Wallets found around filtered early tokens.", key_prefix="auto_wallets", limit=12):
    if wallet_df is None or wallet_df.empty:
        st.info("No wallet candidates to show yet.")
        return

    df = wallet_df.copy().reset_index(drop=True)
    if "Alpha Wallet Score" in df.columns:
        df["Alpha Wallet Score"] = pd.to_numeric(df["Alpha Wallet Score"], errors="coerce").fillna(0)
    if "Early Tokens" in df.columns:
        df["Early Tokens"] = pd.to_numeric(df["Early Tokens"], errors="coerce").fillna(0)
    if "Hits" in df.columns:
        df["Hits"] = pd.to_numeric(df["Hits"], errors="coerce").fillna(0)

    df["Group"] = df.apply(wallet_group_label, axis=1)
    sort_cols = [col for col in ["Alpha Wallet Score", "Early Tokens", "Hits", "Swaps"] if col in df.columns]
    if sort_cols:
        df = df.sort_values(sort_cols, ascending=False).reset_index(drop=True)

    total_wallets = len(df)
    repeated = int((df.get("Early Tokens", pd.Series(dtype=float)) >= 2).sum()) if "Early Tokens" in df else 0
    new_wallets = int((df.get("Saved?", pd.Series(dtype=str)).astype(str).str.lower() == "new").sum()) if "Saved?" in df else 0
    high_score = int((df.get("Alpha Wallet Score", pd.Series(dtype=float)) >= 75).sum()) if "Alpha Wallet Score" in df else 0

    st.markdown(f"### {title}")
    st.caption(caption)
    st.markdown(
        f"""
        <div class="wallet-results-summary compact">
            <div><span>Total</span><strong>{total_wallets}</strong></div>
            <div><span>Repeated early</span><strong>{repeated}</strong></div>
            <div><span>New</span><strong>{new_wallets}</strong></div>
            <div><span>High score</span><strong>{high_score}</strong></div>
        </div>
        """,
        unsafe_allow_html=True
    )

    groups = [
        ("Priority", "Best signals. Add + pin these first."),
        ("Watch", "Useful but needs confirmation."),
        ("Low proof", "Usually skip unless the token itself looks special."),
        ("Saved / already known", "Already in your system."),
    ]

    rendered = 0
    for group_name, group_help in groups:
        group_df = df[df["Group"] == group_name].head(limit).reset_index(drop=True)
        if group_df.empty:
            continue
        expanded = group_name in ["Priority", "Watch"]
        with st.expander(f"{group_name} · {len(group_df)}", expanded=expanded):
            st.caption(group_help)
            for local_idx, (_, row) in enumerate(group_df.iterrows()):
                render_discovered_wallet_candidate_key = f"{key_prefix}_{group_name.replace(' ', '_').replace('/', '_')}_{local_idx}"
                render_wallet_candidate_row(row, local_idx, key_prefix=render_discovered_wallet_candidate_key)
                rendered += 1

    display_cols = ["Group", "Wallet", "Full Wallet", "Early Tokens", "Tokens", "Hits", "Best Score", "Swaps", "Alpha Wallet Score", "Saved?", "Read", "Reason"]
    display_cols = [col for col in display_cols if col in df.columns]
    with st.expander("Advanced: raw wallet table", expanded=False):
        if display_cols:
            st.dataframe(df[display_cols].head(50), width="stretch", hide_index=True)


def render_market_token_card(row, index):
    score = safe_float(row.get("Alpha Score", 0))
    token = discovery_safe_text(row.get("Token", "Token"), 40)
    mint = str(row.get("Mint", ""))
    reason = discovery_safe_text(row.get("Reason", "-"), 220)
    read = discovery_safe_text(row.get("Read", "-"), 220)
    age_h = safe_float(row.get("Age Hours", -1))
    age_text = "unknown" if age_h < 0 else f"{age_h:.1f}h"
    buy_ratio = safe_float(row.get("Buy Ratio", 0)) * 100
    stage = row.get("Stage", "-")
    liquidity = format_usd(row.get("Liquidity USD", 0))
    volume24 = format_usd(row.get("Volume 24h", 0))
    txns24 = safe_int(row.get("Txns 24h", 0))
    change1 = safe_float(row.get("Change 1h", 0))
    change24 = safe_float(row.get("Change 24h", 0))

    score_class = "hot" if score >= 75 else "good" if score >= 55 else "neutral"
    st.markdown(
        f"""
        <div class="alpha-token-row {score_class}">
            <div>
                <div class="alpha-token-title">{token} <span>{short_address(mint)}</span></div>
                <div class="alpha-token-sub">{row.get('Pair', '-')} · {row.get('DEX', '-')} · {stage}</div>
            </div>
            <div><span>Score</span><b>{score:.0f}/100</b></div>
            <div><span>Age</span><b>{age_text}</b></div>
            <div><span>Liq</span><b>{liquidity}</b></div>
            <div><span>Vol 24h</span><b>{volume24}</b></div>
            <div><span>Txns</span><b>{txns24}</b></div>
        </div>
        """,
        unsafe_allow_html=True
    )
    with st.expander(f"Why {token} is in the shortlist", expanded=False):
        st.markdown(f"**Simple read:** {read}")
        st.markdown(f"**Why:** {reason}")
        st.markdown(f"**Momentum:** 1h `{change1:.1f}%` · 24h `{change24:.1f}%` · Buy ratio `{buy_ratio:.0f}%`")



st.markdown(
    """
    <style>
    .wallet-identity-card {
        border-radius: 16px;
        padding: 13px 14px;
        background: rgba(255,255,255,0.025);
        border: 1px solid rgba(255,255,255,0.07);
        margin-bottom: 10px;
    }
    .wallet-identity-card.good { background: linear-gradient(135deg, rgba(34,197,94,.13), rgba(34,197,94,.035)); border-color: rgba(34,197,94,.22); }
    .wallet-identity-card.watch { background: linear-gradient(135deg, rgba(245,158,11,.13), rgba(245,158,11,.035)); border-color: rgba(245,158,11,.22); }
    .wallet-identity-card.low { background: rgba(148,163,184,.05); }
    .wallet-identity-card.saved { background: rgba(96,165,250,.08); border-color: rgba(96,165,250,.18); }
    .wallet-identity-top { display:flex; justify-content:space-between; gap:12px; align-items:flex-start; }
    .wallet-friendly-name { color:#f8fafc; font-size:18px; font-weight:850; letter-spacing:-.02em; }
    .wallet-address-line { color:#94a3b8; font-size:12px; margin-top:2px; }
    .wallet-score-pill { border-radius:999px; padding:7px 10px; font-weight:850; font-size:13px; border:1px solid rgba(255,255,255,.09); color:#e5e7eb; white-space:nowrap; }
    .wallet-score-pill.good { color:#bbf7d0; background:rgba(34,197,94,.14); border-color:rgba(34,197,94,.25); }
    .wallet-score-pill.watch { color:#fde68a; background:rgba(245,158,11,.14); border-color:rgba(245,158,11,.25); }
    .wallet-score-pill.low { color:#cbd5e1; background:rgba(148,163,184,.10); }
    .wallet-score-pill.saved { color:#bfdbfe; background:rgba(96,165,250,.12); border-color:rgba(96,165,250,.25); }
    .wallet-proof-grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:8px; margin:12px 0 9px; }
    .wallet-proof-grid div { border-radius:12px; background:rgba(2,6,23,.28); border:1px solid rgba(255,255,255,.06); padding:8px 9px; }
    .wallet-proof-grid span { display:block; color:#94a3b8; font-size:11px; margin-bottom:3px; }
    .wallet-proof-grid b { color:#f8fafc; font-size:13px; }
    .wallet-human-read { color:#dbeafe; font-size:13px; line-height:1.45; margin-top:7px; }
    .wallet-token-strip { color:#94a3b8; font-size:12px; line-height:1.45; margin-top:6px; }
    .name-manager-row { border:1px solid rgba(255,255,255,.08); border-radius:14px; padding:10px 12px; margin-bottom:8px; background:rgba(255,255,255,.025); }
    .name-manager-title { color:#f8fafc; font-weight:800; }
    .name-manager-sub { color:#94a3b8; font-size:12px; }
    @media (max-width: 900px) { .wallet-proof-grid { grid-template-columns:repeat(2,minmax(0,1fr)); } }
    </style>
    """,
    unsafe_allow_html=True
)

# -----------------------------
# Pages
# -----------------------------

# -----------------------------
# Pages
# -----------------------------

with safe_section(section):
    if section == "Today":
        # ── live data ──────────────────────────────────────────────
        wallet_count = len(st.session_state.watchlist_wallets)
        token_count  = len(st.session_state.watchlist_tokens)
        paper_trades = st.session_state.get("paper_trades", [])
        active_trades = [t for t in paper_trades if not t.get("closed")]
        pinned_count  = len([w for w in st.session_state.watchlist_wallets if wallet_is_pinned(w)])
        journal_docs  = st.session_state.get("wallet_documentation", {})
        strong_wallets = [k for k,v in journal_docs.items() if isinstance(v,dict) and v.get("verdict") in ["Strong thesis","Copy candidate","Promising"]]

        radar = build_watchlist_radar(st.session_state.watchlist_wallets) if wallet_count else {
            "Hot Wallets": 0, "Moved Wallets": 0,
            "Net Volume Change": 0, "New Swaps": 0
        }
        hot_count  = radar.get("Hot Wallets", 0)
        move_count = radar.get("Moved Wallets", 0)

        # paper P/L
        total_pl = 0.0
        risky_trades = []
        for _t in active_trades:
            try:
                _pl = safe_float(_t.get("live_pnl_pct", _t.get("pnl_pct", 0)))
                total_pl += _pl
                _sl = safe_float(_t.get("stop_loss_pct", -25))
                if _pl <= _sl * 0.8:
                    risky_trades.append(_t)
            except Exception:
                pass

        # ── CSS ────────────────────────────────────────────────────
        st.markdown("""
        <style>
        .today-hero {
            padding: 36px 0 28px 0;
            margin-bottom: 8px;
        }
        .today-hero-kicker {
            font-size: 12px;
            font-weight: 600;
            color: #7c5cfc;
            letter-spacing: 0.12em;
            text-transform: uppercase;
            margin-bottom: 8px;
        }
        .today-hero-title {
            font-size: 38px;
            font-weight: 700;
            color: #f5f5f7;
            letter-spacing: -1.2px;
            line-height: 1.08;
            margin-bottom: 6px;
        }
        .today-hero-sub {
            font-size: 14px;
            color: #5a5b62;
            letter-spacing: -0.1px;
        }
        .today-stats {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 12px;
            margin-bottom: 32px;
        }
        .today-stat {
            background: #1e1f23;
            border: 1px solid #2a2b30;
            border-radius: 18px;
            padding: 20px 20px 16px;
            transition: all 0.2s ease;
        }
        .today-stat:hover {
            border-color: #3a3b42;
            transform: translateY(-1px);
        }
        .today-stat-label {
            font-size: 11px;
            font-weight: 600;
            color: #4a4b52;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            margin-bottom: 10px;
        }
        .today-stat-value {
            font-size: 28px;
            font-weight: 700;
            color: #f5f5f7;
            letter-spacing: -1px;
            line-height: 1;
        }
        .today-stat-value.green { color: #34d399; }
        .today-stat-value.red   { color: #f87171; }
        .today-stat-value.purple { color: #a78bfa; }
        .today-stat-sub {
            font-size: 11px;
            color: #4a4b52;
            margin-top: 6px;
        }
        .today-section-label {
            font-size: 11px;
            font-weight: 600;
            color: #4a4b52;
            letter-spacing: 0.1em;
            text-transform: uppercase;
            margin-bottom: 14px;
        }
        .today-cards {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 14px;
            margin-bottom: 28px;
        }
        .today-card {
            background: #1e1f23;
            border: 1px solid #2a2b30;
            border-radius: 18px;
            padding: 22px 20px;
            transition: all 0.2s ease;
            cursor: default;
        }
        .today-card:hover {
            border-color: #3a3b42;
            transform: translateY(-2px);
        }
        .today-card-icon {
            font-size: 22px;
            margin-bottom: 14px;
        }
        .today-card-title {
            font-size: 14px;
            font-weight: 600;
            color: #f5f5f7;
            margin-bottom: 5px;
            letter-spacing: -0.2px;
        }
        .today-card-sub {
            font-size: 12px;
            color: #5a5b62;
            line-height: 1.5;
        }
        .today-card.highlight {
            border-color: #7c5cfc;
            background: #1a1825;
        }
        .today-card.warning {
            border-color: #f59e0b;
            background: #1c1a14;
        }
        .today-card.success {
            border-color: #34d399;
            background: #141c1a;
        }
        .today-alert {
            background: #1c1418;
            border: 1px solid #7f1d1d;
            border-left: 3px solid #f87171;
            border-radius: 14px;
            padding: 16px 20px;
            margin-bottom: 28px;
            display: flex;
            align-items: flex-start;
            gap: 12px;
        }
        .today-alert-icon { font-size: 18px; }
        .today-alert-text { font-size: 13px; color: #fca5a5; line-height: 1.5; }
        .today-alert-title { font-weight: 600; color: #fecaca; margin-bottom: 3px; }
        .today-action-row {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
            margin-bottom: 28px;
        }
        .today-action-btn {
            background: #222328;
            border: 1px solid #2a2b30;
            border-radius: 10px;
            padding: 9px 16px;
            font-size: 12px;
            font-weight: 600;
            color: #d0d0d5;
            cursor: pointer;
            transition: all 0.15s ease;
        }
        .today-action-btn:hover {
            background: #2a2b30;
            border-color: #3a3b42;
            color: #f5f5f7;
        }
        </style>
        """, unsafe_allow_html=True)

        # ── Hero ───────────────────────────────────────────────────
        import datetime as _datetime
        _day = _datetime.datetime.now().strftime("%A, %B %-d") if hasattr(_datetime.datetime.now(), 'strftime') else "Today"
        try:
            _day = _datetime.datetime.now().strftime("%A, %B %d").replace(" 0", " ")
        except Exception:
            _day = "Today"

        _greeting = "Good morning" if _datetime.datetime.now().hour < 12 else ("Good afternoon" if _datetime.datetime.now().hour < 18 else "Good evening")

        st.markdown(f"""
        <div class="today-hero">
            <div class="today-hero-kicker">Smart Wallet Finder · Private Beta</div>
            <div class="today-hero-title">{_greeting}.</div>
            <div class="today-hero-sub">{_day} · here's what matters right now</div>
        </div>
        """, unsafe_allow_html=True)

        # ── Stats row ──────────────────────────────────────────────
        _pl_class = "green" if total_pl >= 0 else "red"
        _pl_str   = f"+{total_pl:.0f}%" if total_pl >= 0 else f"{total_pl:.0f}%"
        _hot_class = "purple" if hot_count > 0 else ""

        st.markdown(f"""
        <div class="today-stats">
            <div class="today-stat">
                <div class="today-stat-label">Wallets watched</div>
                <div class="today-stat-value">{wallet_count}</div>
                <div class="today-stat-sub">{pinned_count} pinned · {len(strong_wallets)} strong thesis</div>
            </div>
            <div class="today-stat">
                <div class="today-stat-label">Paper P/L</div>
                <div class="today-stat-value {_pl_class}">{_pl_str if active_trades else "—"}</div>
                <div class="today-stat-sub">{len(active_trades)} active trade{"s" if len(active_trades) != 1 else ""}</div>
            </div>
            <div class="today-stat">
                <div class="today-stat-label">Hot wallets</div>
                <div class="today-stat-value {_hot_class}">{hot_count}</div>
                <div class="today-stat-sub">{move_count} moved · {token_count} tokens saved</div>
            </div>
            <div class="today-stat">
                <div class="today-stat-label">Risky trades</div>
                <div class="today-stat-value {"red" if risky_trades else ""}">{len(risky_trades)}</div>
                <div class="today-stat-sub">{"near stop loss" if risky_trades else "all trades safe"}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # ── Alert if risky trades ──────────────────────────────────
        if risky_trades:
            _rt = risky_trades[0]
            _rt_name = str(_rt.get("token", _rt.get("token_mint", "Unknown")))[:12]
            _rt_pl   = safe_float(_rt.get("live_pnl_pct", _rt.get("pnl_pct", 0)))
            st.markdown(f"""
            <div class="today-alert">
                <div class="today-alert-icon">⚠️</div>
                <div class="today-alert-text">
                    <div class="today-alert-title">Trade alert — {_rt_name}</div>
                    Position is at {_rt_pl:.1f}% and approaching your stop loss. Review it in Paper Trading.
                </div>
            </div>
            """, unsafe_allow_html=True)

        # ── What to do now ─────────────────────────────────────────
        st.markdown('<div class="today-section-label">What to do now</div>', unsafe_allow_html=True)

        # build dynamic cards
        _cards = []

        if hot_count > 0:
            _cards.append(("highlight", "!", f"{hot_count} hot wallet{'s' if hot_count!=1 else ''} right now", "Something just moved. Check Smart Wallets → Recent Trades first."))
        elif move_count > 0:
            _cards.append(("", "·", f"{move_count} wallet{'s' if move_count!=1 else ''} moved", "No urgent spike but activity detected. Worth a quick look."))
        else:
            _cards.append(("", "·", "No urgent wallet movement", "All quiet. Keep Auto Scan running to catch the next move early."))

        if token_count == 0:
            _cards.append(("", "·", "Find your first token", "Open Token Finder and run a scan. The engine looks for fresh, early Solana tokens."))
        else:
            _cards.append(("success", "·", f"{token_count} token{'s' if token_count!=1 else ''} on your list", "Token Finder is tracking these. Run a fresh scan to see what's moved."))

        if not active_trades:
            _cards.append(("", "·", "No paper trades active", "Set up a fake trade in Paper Trading to test a wallet before risking real money."))
        elif len(risky_trades) > 0:
            _cards.append(("warning", "·", f"{len(risky_trades)} trade near stop loss", "Review your Paper Trading positions. One is getting close to your limit."))
        else:
            _cards.append(("success", "·", f"{len(active_trades)} trade{'s' if len(active_trades)!=1 else ''} active", f"Paper P/L today: {_pl_str}. Things look {'good' if total_pl>=0 else 'rough'}."))

        _card_html = '<div class="today-cards">'
        for _cls, _icon, _title, _sub in _cards:
            _card_html += f"""
            <div class="today-card {_cls}">
                <div class="today-card-icon">{_icon}</div>
                <div class="today-card-title">{_title}</div>
                <div class="today-card-sub">{_sub}</div>
            </div>"""
        _card_html += "</div>"
        st.markdown(_card_html, unsafe_allow_html=True)

        # ── Quick navigation buttons ───────────────────────────────
        st.markdown('<div class="today-section-label">Quick jump</div>', unsafe_allow_html=True)
        _qc = st.columns(4)
        with _qc[0]:
            if st.button("Token Finder", key="today_go_token", use_container_width=True):
                st.session_state.main_navigation = "Token Finder"
                st.rerun()
        with _qc[1]:
            if st.button("Smart Wallets", key="today_go_wallets", use_container_width=True):
                st.session_state.main_navigation = "Smart Wallets"
                st.rerun()
        with _qc[2]:
            if st.button("Journal", key="today_go_journal", use_container_width=True):
                st.session_state.main_navigation = "Wallet Journal"
                st.rerun()
        with _qc[3]:
            if st.button("Paper Trading", key="today_go_paper", use_container_width=True):
                st.session_state.main_navigation = "Paper Trading"
                st.rerun()

        # ── Top attention wallets (if any) ─────────────────────────
        if st.session_state.watchlist_wallets:
            attention = []
            for _idx, _item in sorted_watchlist_pairs(st.session_state.watchlist_wallets, "Highest movement"):
                _status, _, _hint = wallet_movement_status(_item)
                _, _sc, _tc, _vc, _lc = wallet_movement_values(_item)
                if _status in ["HOT","VOLUME SPIKE","NEW SWAPS","NEW TRANSFERS","SCORE UP"] or abs(_vc) >= 25:
                    attention.append((_idx, _item, _status, _hint))

            if attention:
                st.markdown('<div class="today-section-label" style="margin-top:28px;">Top attention wallets</div>', unsafe_allow_html=True)
                for _idx, _item, _status, _hint in attention[:3]:
                    _fw  = _item.get("Full Wallet", "-")
                    _wn  = wallet_watchlist_item_name(_item)
                    _, _sc, _tc, _vc, _lc = wallet_movement_values(_item)
                    st.markdown(f"""
                    <div style="background:#1e1f23;border:1px solid #2a2b30;border-radius:16px;padding:18px 20px;margin-bottom:10px;display:flex;align-items:center;justify-content:space-between;">
                        <div>
                            <div style="font-size:14px;font-weight:600;color:#f5f5f7;margin-bottom:3px;">{_wn}</div>
                            <div style="font-size:12px;color:#5a5b62;">{_hint}</div>
                        </div>
                        <div style="text-align:right;">
                            <div style="font-size:11px;font-weight:700;color:#7c5cfc;letter-spacing:0.08em;">{_status}</div>
                            <div style="font-size:12px;color:#4a4b52;margin-top:3px;">Vol {format_signed_usd(_vc)}</div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)


    elif section == "Smart Wallets":
        st.markdown("""
        <style>
        .sw-page-title{font-size:24px;font-weight:600;color:#f5f5f7;padding:28px 0 4px}
        .sw-page-sub{font-size:14px;color:#5a5b62;margin-bottom:20px}
        .sw-result{background:#1e1f23;border:1px solid #2a2b30;border-radius:14px;padding:20px;margin-bottom:12px}
        .sw-result-name{font-size:15px;font-weight:600;color:#f5f5f7;margin-bottom:2px}
        .sw-result-addr{font-size:12px;color:#4a4b52;margin-bottom:10px;font-family:monospace}
        .sw-badge{display:inline-block;padding:4px 12px;border-radius:20px;font-size:11px;font-weight:700;letter-spacing:.04em;margin-bottom:12px}
        .sw-badge.alpha{background:rgba(124,92,252,.15);color:#a78bfa;border:1px solid rgba(124,92,252,.3)}
        .sw-badge.watch{background:rgba(34,197,94,.12);color:#4ade80;border:1px solid rgba(34,197,94,.25)}
        .sw-badge.paper{background:rgba(251,191,36,.12);color:#fbbf24;border:1px solid rgba(251,191,36,.25)}
        .sw-badge.risky{background:rgba(239,68,68,.12);color:#f87171;border:1px solid rgba(239,68,68,.25)}
        .sw-stats{display:flex;gap:16px;flex-wrap:wrap;margin-top:8px}
        .sw-stat{display:flex;flex-direction:column}
        .sw-stat span{font-size:11px;color:#4a4b52}
        .sw-stat b{font-size:14px;font-weight:600;color:#c0c0c8}
        .sw-label{font-size:11px;font-weight:600;color:#3a3b42;letter-spacing:.07em;text-transform:uppercase;margin:20px 0 8px}
        .sw-recent-item{display:flex;align-items:center;gap:12px;padding:10px 14px;border:1px solid #2a2b30;border-radius:10px;margin-bottom:6px}
        .sw-recent-name{font-size:13px;color:#c0c0c8;font-weight:500}
        .sw-recent-addr{font-size:11px;color:#4a4b52;font-family:monospace}
        </style>
        """, unsafe_allow_html=True)

        st.markdown('<div class="sw-page-title">Smart Wallets</div>', unsafe_allow_html=True)
        st.markdown('<div class="sw-page-sub">Scan any Solana wallet or discover early buyers from a token mint.</div>', unsafe_allow_html=True)

        _prefill = st.session_state.get("wallet_address_input", "")
        _auto = st.session_state.pop("_sw_auto_scan", False)

        tab_scan, tab_disc, tab_recent = st.tabs(["Scan wallet", "Discover from token", "Recent"])

        with tab_scan:
            c_in, c_btn = st.columns([0.8, 0.2])
            with c_in:
                _w_addr = st.text_input(
                    "addr", value=_prefill,
                    placeholder="Paste Solana wallet address...",
                    label_visibility="collapsed", key="sw_addr_input"
                )
            with c_btn:
                _do_scan = st.button("Scan", key="sw_scan_btn", use_container_width=True, type="primary")

            if (_do_scan or _auto) and _w_addr.strip():
                st.session_state.wallet_address_input = _w_addr.strip()
                add_recent_item("recent_wallets", _w_addr.strip())
                with st.spinner("Fetching from Helius..."):
                    _wtx, _werr = fetch_wallet_transactions(_w_addr.strip())
                if _werr or _wtx is None or _wtx.empty:
                    st.error("Could not fetch wallet. Check address or Helius API key.")
                else:
                    _ttx, _tfr, _tsw, _tun, _tlvl = summarize_wallet_activity(_wtx)
                    _wsig, _wscore, _wreason = get_wallet_signal(_ttx, _tfr, _tsw, _tun)
                    _usd = estimate_wallet_usd_stats(_wtx)
                    _nb, _ns, _nr = wallet_trade_counts(_wtx)
                    _sc = safe_int(_wscore)
                    if _sc >= 80: _vcls, _vtxt = "alpha", "Alpha Scout"
                    elif _sc >= 65: _vcls, _vtxt = "watch", "Worth watching"
                    elif _sc >= 45: _vcls, _vtxt = "paper", "Paper trade first"
                    else: _vcls, _vtxt = "risky", "Needs more proof"

                    _dn = wallet_display_name(_w_addr.strip())
                    _vol = safe_float(_usd.get("Total USD Volume", 0))
                    _lrg = safe_float(_usd.get("Largest USD Tx", 0))

                    st.markdown(f"""
                    <div class="sw-result">
                        <div class="sw-result-name">{_dn}</div>
                        <div class="sw-result-addr">{compact_address(_w_addr.strip(), 10, 6)}</div>
                        <div class="sw-badge {_vcls}">{_vtxt}</div>
                        <div class="sw-stats">
                            <div class="sw-stat"><span>Score</span><b>{_sc}/100</b></div>
                            <div class="sw-stat"><span>Signal</span><b>{_wsig}</b></div>
                            <div class="sw-stat"><span>Tx</span><b>{_ttx}</b></div>
                            <div class="sw-stat"><span>Swaps</span><b>{_tsw}</b></div>
                            <div class="sw-stat"><span>Volume</span><b>{format_usd(_vol)}</b></div>
                            <div class="sw-stat"><span>Largest</span><b>{format_usd(_lrg)}</b></div>
                            <div class="sw-stat"><span>Buys</span><b>{_nb}</b></div>
                            <div class="sw-stat"><span>Sells</span><b>{_ns}</b></div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                    with st.expander("Why this verdict?", expanded=True):
                        st.markdown(f"**Signal:** {_wsig}  \n**Reason:** {_wreason}  \n**Activity:** {_tlvl}")

                    _a1, _a2, _a3 = st.columns(3)
                    with _a1:
                        if st.button("Add to Watchlist", key="sw_add_wl", use_container_width=True):
                            add_wallet_to_watchlist({
                                "Wallet": _dn, "Name": _dn, "Wallet Alias": _dn,
                                "Full Wallet": _w_addr.strip(), "Signal": _wsig, "Score": _sc,
                                "Transfers": safe_int(_tfr), "Swaps": safe_int(_tsw),
                                "USD Volume": _vol, "Largest Tx": _lrg,
                                "Last Checked": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
                                "Check Count": 1, "Pinned": False,
                            })
                            st.success("Added to Watchlist.")
                    with _a2:
                        if st.button("Paper trade", key="sw_paper", use_container_width=True):
                            st.session_state.main_navigation = "Paper Trading"
                            st.rerun()
                    with _a3:
                        if st.button("View in Journal", key="sw_journal", use_container_width=True):
                            st.session_state.main_navigation = "Wallet Journal"
                            st.rerun()

            elif _prefill and not _do_scan and not _auto:
                st.caption(f"Pre-loaded: {compact_address(_prefill)} — click Scan to analyse.")

        with tab_disc:
            st.caption("Paste a token mint to find which wallets bought it early. Uses Solscan first, Helius as fallback.")
            _dc1, _dc2 = st.columns([0.8, 0.2])
            with _dc1:
                _mint = st.text_input("mint", placeholder="Paste token mint address...",
                                      label_visibility="collapsed", key="sw_mint_input")
            with _dc2:
                _do_disc = st.button("Discover", key="sw_disc_btn", use_container_width=True, type="primary")

            if _do_disc and _mint.strip():
                _ddf = None
                _derr = None
                with st.spinner("Scanning via Solscan (earliest buyers)..."):
                    _ddf, _derr = discover_wallets_from_token_solscan(_mint.strip(), max_wallets=15)
                if _derr or _ddf is None or (hasattr(_ddf, "empty") and _ddf.empty):
                    with st.spinner("Trying Helius fallback..."):
                        _ddf, _derr = discover_wallets_from_token_helius(_mint.strip(), max_wallets=15)
                if _derr or _ddf is None or (hasattr(_ddf, "empty") and _ddf.empty):
                    st.warning(f"No wallets found. {_derr or 'Try a different token mint.'}")
                else:
                    _dc = len(_ddf)
                    st.success(f"Found {_dc} early wallets.")
                    _show = [c for c in ["Wallet","Score","Early Rank","Type","Verdict","Transfers","Swaps","Saved?"] if c in _ddf.columns]
                    st.dataframe(_ddf[_show].head(15), use_container_width=True, hide_index=True)
                    st.markdown('<div class="sw-label">Quick actions</div>', unsafe_allow_html=True)
                    for _di, _dr in _ddf.head(6).iterrows():
                        _dfw = str(_dr.get("Full Wallet","")).strip()
                        _dwn = str(_dr.get("Wallet", _dfw[:12])).strip()
                        if not _dfw:
                            continue
                        _r1, _r2, _r3 = st.columns([0.5, 0.25, 0.25])
                        with _r1:
                            st.markdown(f"`{_dwn}` — Score **{safe_int(_dr.get('Score',0))}** · {_dr.get('Verdict','-')}")
                        with _r2:
                            if st.button("Scan", key=f"dsc_s_{_dfw[-8:]}", use_container_width=True):
                                st.session_state.wallet_address_input = _dfw
                                st.session_state._sw_auto_scan = True
                                st.session_state.main_navigation = "Smart Wallets"
                                st.rerun()
                        with _r3:
                            if st.button("Watchlist", key=f"dsc_w_{_dfw[-8:]}", use_container_width=True):
                                add_wallet_to_watchlist({
                                    "Wallet": _dwn, "Name": _dwn, "Wallet Alias": _dwn,
                                    "Full Wallet": _dfw, "Signal": str(_dr.get("Type","Watch")),
                                    "Score": safe_int(_dr.get("Score",30)),
                                    "Transfers": safe_int(_dr.get("Transfers",0)), "Swaps": 0,
                                    "USD Volume": 0, "Largest Tx": 0,
                                    "Last Checked": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
                                    "Check Count": 1, "Pinned": False,
                                })
                                st.success(f"Added.")

        with tab_recent:
            _rws = st.session_state.get("recent_wallets", [])
            if not _rws:
                st.info("No recently scanned wallets yet.")
            else:
                st.markdown('<div class="sw-label">Recently scanned</div>', unsafe_allow_html=True)
                for _rw in _rws[:10]:
                    _rs = str(_rw).strip()
                    _rn, _rb = st.columns([0.82, 0.18])
                    with _rn:
                        st.markdown(f"""<div class="sw-recent-item">
                            <div>
                                <div class="sw-recent-name">{wallet_display_name(_rs)}</div>
                                <div class="sw-recent-addr">{compact_address(_rs, 10, 6)}</div>
                            </div>
                        </div>""", unsafe_allow_html=True)
                    with _rb:
                        if st.button("Open", key=f"sw_r_{_rs[-8:]}", use_container_width=True):
                            st.session_state.wallet_address_input = _rs
                            st.session_state._sw_auto_scan = True
                            st.rerun()


    elif section == "Market Dashboard":
        st.title("Market Dashboard")
        st.caption("Live market overview for tokens saved in your watchlist.")

        if not st.session_state.watchlist_tokens:
            st.info("No tokens in your watchlist yet. Add tokens first.")
        else:
            dashboard_rows = []
            seen_dashboard_mints = set()

            for item in st.session_state.watchlist_tokens:
                token = item.get("Token", "Unknown")
                name = item.get("Name", "Unknown")
                mint = item.get("Mint", "")
                decision = item.get("Decision", "-")
                risk = item.get("Risk", "-")
                copy_risk = item.get("Copy Risk", "-")
                last_checked = item.get("Last Checked", "-")

                if not mint:
                    continue
            
                if mint in seen_dashboard_mints:
                    continue

                seen_dashboard_mints.add(mint)

                token_data, error = fetch_token_pairs("solana", mint)

                if error or token_data is None or token_data.empty:
                    dashboard_rows.append({
                        "Token": token,
                        "Name": name,
                        "Price": "-",
                        "5m %": "-",
                        "1h %": "-",
                        "6h %": "-",
                        "24h %": "-",
                        "Volume 24h": "-",
                        "Liquidity": "-",
                        "Txns 24h": "-",
                        "Risk": risk,
                        "Copy Risk": copy_risk,
                        "Decision": decision,
                        "Last Checked": last_checked
                    })
                    continue

                best_pair = token_data.iloc[0]

                dashboard_rows.append({
                    "Token": token,
                    "Name": name,
                    "Price": best_pair.get("Price USD", "-"),
                    "5m %": best_pair.get("Change 5m", 0),
                    "1h %": best_pair.get("Change 1h", 0),
                    "6h %": best_pair.get("Change 6h", 0),
                    "24h %": best_pair.get("Change 24h", 0),
                    "Volume 24h": best_pair.get("Volume 24h", 0),
                    "Liquidity": best_pair.get("Liquidity USD", 0),
                    "Txns 24h": best_pair.get("Txns 24h", 0),
                    "Risk": risk,
                    "Copy Risk": copy_risk,
                    "Decision": decision,
                    "Last Checked": last_checked
                })

            dashboard_df = pd.DataFrame(dashboard_rows)

            if not dashboard_df.empty:
                for percent_col in ["5m %", "1h %", "6h %", "24h %"]:
                    dashboard_df[percent_col] = pd.to_numeric(dashboard_df[percent_col], errors="coerce").fillna(0)

                dashboard_df["Volume 24h"] = pd.to_numeric(dashboard_df["Volume 24h"], errors="coerce").fillna(0)
                dashboard_df["Liquidity"] = pd.to_numeric(dashboard_df["Liquidity"], errors="coerce").fillna(0)
                dashboard_df["Txns 24h"] = pd.to_numeric(dashboard_df["Txns 24h"], errors="coerce").fillna(0)

                raw_dashboard_df = dashboard_df.copy()

                top_1h = raw_dashboard_df.sort_values("1h %", ascending=False).iloc[0]
                top_24h = raw_dashboard_df.sort_values("24h %", ascending=False).iloc[0]
                top_volume = raw_dashboard_df.sort_values("Volume 24h", ascending=False).iloc[0]
                top_txns = raw_dashboard_df.sort_values("Txns 24h", ascending=False).iloc[0]

                metric_col_1, metric_col_2, metric_col_3, metric_col_4 = st.columns(4)

                with metric_col_1:
                    st.metric(
                        "Biggest 1h Gainer",
                        top_1h["Token"],
                        f"{top_1h['1h %']:+.2f}%"
                    )

                with metric_col_2:
                    st.metric(
                        "Biggest 24h Gainer",
                        top_24h["Token"],
                        f"{top_24h['24h %']:+.2f}%"
                    )

                with metric_col_3:
                    st.metric(
                        "Highest Volume",
                        top_volume["Token"],
                        f"${top_volume['Volume 24h']:,.0f}"
                    )

                with metric_col_4:
                    st.metric(
                        "Highest Txns",
                        top_txns["Token"],
                        f"{top_txns['Txns 24h']:,.0f}"
                    )

                dashboard_df["5m %"] = dashboard_df["5m %"].map(lambda value: f"{value:+.2f}%")
                dashboard_df["1h %"] = dashboard_df["1h %"].map(lambda value: f"{value:+.2f}%")
                dashboard_df["6h %"] = dashboard_df["6h %"].map(lambda value: f"{value:+.2f}%")
                dashboard_df["24h %"] = dashboard_df["24h %"].map(lambda value: f"{value:+.2f}%")

                dashboard_df["Volume 24h"] = dashboard_df["Volume 24h"].map(lambda value: f"${value:,.0f}")
                dashboard_df["Liquidity"] = dashboard_df["Liquidity"].map(lambda value: f"${value:,.0f}")
                dashboard_df["Txns 24h"] = dashboard_df["Txns 24h"].map(lambda value: f"{value:,.0f}")

            if dashboard_df.empty:
                st.info("No valid token mints found in watchlist.")
            else:
                st.markdown('<div class="section-title">Watchlist Market Performance</div>', unsafe_allow_html=True)

                visible_dashboard_columns = [
                    "Token",
                    "Price",
                    "5m %",
                    "1h %",
                    "24h %",
                    "Volume 24h",
                    "Txns 24h",
                    "Risk",
                    "Decision"
                ]

                dashboard_df = dashboard_df[
                    [col for col in visible_dashboard_columns if col in dashboard_df.columns]
                ]

                st.markdown(
                    dashboard_df.to_html(
                        index=False,
                        escape=False,
                        classes="market-table"                ),
                    unsafe_allow_html=True
                )


    elif section == "Recent Trades":
        st.title("Recent Trades")
        st.caption("Für Menschen gebaut: Erst sehen was wichtig ist, dann Details nur bei Bedarf öffnen.")

        wallet_items = st.session_state.watchlist_wallets

        if not wallet_items:
            st.markdown(
                """<div class="human-topbar">
                    <div class="human-title">No activity yet</div>
                    <div class="human-subtitle">Add wallets first. Then this page becomes your live feed for HOT wallets, new swaps and volume spikes.</div>
                </div>""",
                unsafe_allow_html=True
            )
            c1, c2, _ = st.columns([0.18, 0.22, 0.60])
            with c1:
                if st.button("Go to Smart Wallets", key="empty_recent_go_wallets"):
                    st.session_state.section_override = "Smart Wallets"
                    st.rerun()
            with c2:
                if st.button("Go to Discovery", key="empty_recent_go_discovery"):
                    st.session_state.section_override = "Wallet Discovery"
                    st.rerun()
        else:
            radar = build_watchlist_radar(wallet_items)
            radar_state_class = "human-pill-green" if radar["Hot Wallets"] else "human-pill-yellow" if radar["Moved Wallets"] else ""
            radar_label = "ACTION NEEDED" if radar["Hot Wallets"] else "MOVEMENT" if radar["Moved Wallets"] else "CALM"

            if radar["Hot Wallets"] > 0:
                next_action_title = "Check HOT wallets first"
                next_action_text = "Start with wallets that show HOT, VOLUME SPIKE or NEW SWAPS. Use Analyze Token when a latest token is detected."
            elif radar["Moved Wallets"] > 0:
                next_action_title = "Movement found"
                next_action_text = "Open the biggest movers first. If no token is detected, open the wallet and inspect swapped tokens."
            else:
                next_action_title = "Nothing urgent"
                next_action_text = "Keep Auto Update running or refresh later. Quiet wallets are intentionally hidden in Actionable view."

            st.markdown(
                f"""<div class="human-topbar">
                    <div class="human-topbar-row">
                        <div>
                            <div class="human-title">{next_action_title}</div>
                            <div class="human-subtitle">{next_action_text}</div>
                        </div>
                        <div class="human-pill {radar_state_class}">{radar_label}</div>
                    </div>
                    <div class="human-summary-grid">
                        <div><span>Wallets</span><strong>{radar["Total Wallets"]}</strong></div>
                        <div><span>Moved</span><strong>{radar["Moved Wallets"]}</strong></div>
                        <div><span>Hot</span><strong>{radar["Hot Wallets"]}</strong></div>
                        <div><span>New Swaps</span><strong class="{movement_class(radar["New Swaps"])}">{format_signed_number(radar["New Swaps"])}</strong></div>
                        <div><span>Net Volume</span><strong class="{movement_class(radar["Net Volume Change"])}">{format_signed_usd(radar["Net Volume Change"])}</strong></div>
                        <div><span>Biggest Move</span><strong>{radar["Highest Volume Change Wallet"]} · {format_signed_usd(radar["Highest Volume Change"])}</strong></div>
                    </div>
                </div>""",
                unsafe_allow_html=True
            )

            with st.expander("How to use this feed", expanded=False):
                st.markdown(
                    """
                    **Simple workflow:**  
                    1. Keep the filter on **Actionable**.  
                    2. Check cards marked **HOT**, **VOLUME SPIKE** or **NEW SWAPS**.  
                    3. Click **Analyze Token** when available.  
                    4. If no token is detected, click **Open Wallet** and inspect swapped tokens.  
                    5. Quiet wallets can stay hidden until they move.
                    """
                )

            action_col, filter_col, view_col, mode_col = st.columns([0.16, 0.22, 0.20, 0.22])

            with action_col:
                if st.button("Refresh", key="recent_refresh_activity"):
                    results = []
                    for recheck_index in range(len(st.session_state.watchlist_wallets)):
                        result = recheck_wallet_watchlist_item(recheck_index)
                        if result:
                            results.append(result)

                    st.session_state.watchlist_message = (
                        f"Activity refreshed for {len(results)} wallets."
                        if results else
                        "Activity refresh finished. No wallet movement found."
                    )
                    st.rerun()

            with filter_col:
                recent_filter = st.selectbox(
                    "Filter",
                    ["Actionable", "All", "Hot only", "Moved only", "Cooling", "No movement"],
                    index=0,
                    key="recent_activity_filter"
                )

            with view_col:
                max_cards = st.selectbox(
                    "Show",
                    [5, 10, 20, 50],
                    index=0,
                    key="recent_activity_limit",
                    format_func=lambda value: f"Top {value}"
                )

            with mode_col:
                recent_mode = st.selectbox(
                    "Mode",
                    ["Simple", "Advanced"],
                    index=0,
                    key="recent_activity_mode"
                )

            sorted_pairs = sorted_watchlist_pairs(wallet_items, "Highest movement")
            visible_pairs = []
            for index, item in sorted_pairs:
                status, status_class, status_hint = wallet_movement_status(item)
                score_change, swaps_change, transfers_change, volume_change, largest_change = wallet_movement_values(item)
                moved = any([score_change != 0, swaps_change != 0, transfers_change != 0, abs(volume_change) >= 0.01, abs(largest_change) >= 0.01])
                actionable = status in ["HOT", "VOLUME SPIKE", "NEW SWAPS", "NEW TRANSFERS", "SCORE UP"] or abs(volume_change) >= 25
                if recent_filter == "Actionable" and not actionable:
                    continue
                if recent_filter == "Hot only" and status not in ["HOT", "VOLUME SPIKE", "NEW SWAPS"]:
                    continue
                if recent_filter == "Moved only" and not moved:
                    continue
                if recent_filter == "Cooling" and status != "COOLING":
                    continue
                if recent_filter == "No movement" and moved:
                    continue
                visible_pairs.append((index, item, status, status_hint, actionable))
            visible_pairs = visible_pairs[:max_cards]

            if st.session_state.watchlist_message:
                st.success(st.session_state.watchlist_message)
            if not visible_pairs:
                st.info("No wallet activity matches this filter yet. Switch Filter to All if you want everything.")

            attention_pairs = [pair for pair in visible_pairs if pair[4]]
            calm_pairs = [pair for pair in visible_pairs if not pair[4]]

            def render_recent_card(index, item, status, status_hint):
                full_wallet = item.get("Full Wallet", "-")
                wallet = wallet_watchlist_item_name(item)
                signal = item.get("Signal", "-")
                last_checked = item.get("Last Checked", "Not checked yet")
                latest_activity = item.get("Latest Activity", "-")
                latest_token_mint = item.get("Latest Token Mint", "") or extract_first_token_mint(latest_activity)
                if not latest_activity or latest_activity == "-":
                    latest_activity = "No latest activity stored yet. Click Refresh or Check Wallet."
                score = safe_int(item.get("Score", 0))
                swaps = safe_int(item.get("Swaps", 0))
                usd_volume = safe_float(item.get("USD Volume", 0))
                checks = safe_int(item.get("Check Count", 0))
                previous_score = safe_int(item.get("Previous Score", score))
                previous_swaps = safe_int(item.get("Previous Swaps", swaps))
                previous_volume = safe_float(item.get("Previous USD Volume", usd_volume))
                score_change, swaps_change, transfers_change, volume_change, largest_change = wallet_movement_values(item)

                if status in ["HOT", "VOLUME SPIKE"]:
                    card_class, pill_class, next_step = "human-card-hot", "human-pill-yellow", "Analyze latest token or open wallet."
                elif status in ["NEW SWAPS", "NEW TRANSFERS", "SCORE UP"]:
                    card_class, pill_class, next_step = "human-card-up", "human-pill-green", "Worth checking."
                elif status == "COOLING":
                    card_class, pill_class, next_step = "human-card-down", "human-pill-red", "Lower priority."
                else:
                    card_class, pill_class, next_step = "", "", "No action needed."

                token_hint = latest_token_mint[:6] + "..." + latest_token_mint[-6:] if latest_token_mint else "No token detected"

                st.markdown(
                    f"""<div class="human-card {card_class}">
                        <div class="human-card-top">
                            <div>
                                <div class="human-wallet">{wallet}</div>
                                <div class="human-meta-line">{signal} · checked {last_checked} · {checks} checks</div>
                            </div>
                            <div class="human-pill {pill_class}" title="{status_hint}">{status}</div>
                        </div>
                        <div class="human-deltas">
                            <div><span>Swaps</span><strong class="{movement_class(swaps_change)}">{format_signed_number(swaps_change)}</strong></div>
                            <div><span>Volume</span><strong class="{movement_class(volume_change)}">{format_signed_usd(volume_change)}</strong></div>
                            <div><span>Largest Tx</span><strong class="{movement_class(largest_change)}">{format_signed_usd(largest_change)}</strong></div>
                            <div><span>Token</span><strong>{token_hint}</strong></div>
                        </div>
                        <div class="human-latest"><span>Next best action</span>{next_step}</div>
                    </div>""",
                    unsafe_allow_html=True
                )

                st.markdown('<div class="human-action-gap"></div>', unsafe_allow_html=True)
                _, recent_check_col, recent_analyze_col, recent_open_col = st.columns([3.8, 0.85, 1.18, 0.75])
                with recent_check_col:
                    if st.button("Check", key=f"recent_check_wallet_{index}_{full_wallet}", type="secondary"):
                        recheck_wallet_watchlist_item(index); st.rerun()
                with recent_analyze_col:
                    analyze_disabled = not bool(latest_token_mint)
                    if st.button("Analyze Token", key=f"recent_analyze_token_{index}_{full_wallet}", type="secondary", disabled=analyze_disabled):
                        st.session_state.selected_token_mint = latest_token_mint
                        st.session_state.token_scanner_input = latest_token_mint
                        add_recent_item("recent_token_mints", latest_token_mint)
                        st.session_state.section_override = "Token Scanner"
                        st.rerun()
                with recent_open_col:
                    if st.button("Open", key=f"recent_open_wallet_{index}_{full_wallet}", type="secondary"):
                        st.session_state.wallet_address_input = full_wallet
                        st.session_state._sw_auto_scan = True
                        add_recent_item("recent_wallets", full_wallet)
                        st.session_state.section_override = "Smart Wallets"
                        st.rerun()

                if recent_mode == "Advanced":
                    with st.expander(f"Details for {wallet}", expanded=False):
                        st.markdown(
                            f"""
                            **Why this matters:** {status_hint}  
                            **Score:** {previous_score} → {score} ({format_signed_number(score_change)})  
                            **Swaps:** {previous_swaps} → {swaps} ({format_signed_number(swaps_change)})  
                            **Volume:** {format_usd(previous_volume)} → {format_usd(usd_volume)} ({format_signed_usd(volume_change)})  
                            **Latest activity:** {latest_activity}
                            """
                        )

            if attention_pairs:
                st.markdown('<div class="section-title">Needs attention</div>', unsafe_allow_html=True)
                for index, item, status, status_hint, actionable in attention_pairs:
                    render_recent_card(index, item, status, status_hint)

            if calm_pairs:
                with st.expander(f"Quiet / lower priority ({len(calm_pairs)})", expanded=False):
                    for index, item, status, status_hint, actionable in calm_pairs:
                        render_recent_card(index, item, status, status_hint)


    elif section == "Watchlist":
        st.markdown('<p style="font-size:24px;font-weight:600;color:#f5f5f7;padding:28px 0 4px;">Watchlist</p>', unsafe_allow_html=True)
        st.markdown('<p style="font-size:14px;color:#5a5b62;margin-bottom:16px;">Your radar — wallets worth watching, sorted by activity.</p>', unsafe_allow_html=True)

        with st.expander("Start here: How to use the Watchlist", expanded=False):
            st.markdown(
                """
                **Simple workflow:**  
                1. Add interesting wallets from **Smart Wallets** or **Wallet Discovery**.  
                2. Turn **Auto Update** on, or click **Check All**.  
                3. Look only at **Needs attention** first.  
                4. Click **Analyze Token** if a latest token is detected.  
                5. Keep quiet wallets collapsed until they move.
                """
            )

        watch_tab, token_tab = st.tabs(["Wallets", "Tokens"])

        with watch_tab:
            st.markdown('<div class="section-title">Wallet Radar</div>', unsafe_allow_html=True)

            if not st.session_state.watchlist_wallets:
                st.markdown(
                    """<div class="human-topbar">
                        <div class="human-title">No wallets yet</div>
                        <div class="human-subtitle">Start by scanning a wallet or discovering wallets from a token. Once added, this page will show HOT wallets, new swaps and volume spikes.</div>
                    </div>""",
                    unsafe_allow_html=True
                )
                c1, c2, _ = st.columns([0.18, 0.22, 0.60])
                with c1:
                    if st.button("Scan Wallet", key="empty_watch_go_smart"):
                        st.session_state.section_override = "Smart Wallets"
                        st.rerun()
                with c2:
                    if st.button("Discover Wallets", key="empty_watch_go_discovery"):
                        st.session_state.section_override = "Wallet Discovery"
                        st.rerun()
            else:
                radar = build_watchlist_radar(st.session_state.watchlist_wallets)

                if radar["Hot Wallets"] > 0:
                    next_action_title = "Action needed"
                    next_action_text = "HOT wallets found. Check Needs attention first, then analyze the latest token."
                    state_class = "human-pill-green"
                elif radar["Moved Wallets"] > 0:
                    next_action_title = "Movement detected"
                    next_action_text = "Some wallets moved. Open the biggest mover or inspect new swaps."
                    state_class = "human-pill-yellow"
                else:
                    next_action_title = "No urgent movement"
                    next_action_text = "Everything is quiet. Keep Auto Update on or recheck later."
                    state_class = ""

                st.markdown(
                    f"""<div class="human-topbar">
                        <div class="human-topbar-row">
                            <div>
                                <div class="human-title">{next_action_title}</div>
                                <div class="human-subtitle">{next_action_text}</div>
                            </div>
                            <div class="human-pill {state_class}">NEXT STEP</div>
                        </div>
                        <div class="human-summary-grid">
                            <div><span>Wallets</span><strong>{radar["Total Wallets"]}</strong></div>
                            <div><span>Moved</span><strong>{radar["Moved Wallets"]}</strong></div>
                            <div><span>Hot</span><strong>{radar["Hot Wallets"]}</strong></div>
                            <div><span>New Swaps</span><strong class="{movement_class(radar["New Swaps"])}">{format_signed_number(radar["New Swaps"])}</strong></div>
                            <div><span>Net Volume</span><strong class="{movement_class(radar["Net Volume Change"])}">{format_signed_usd(radar["Net Volume Change"])}</strong></div>
                            <div><span>Biggest Move</span><strong>{radar["Highest Volume Change Wallet"]} · {format_signed_usd(radar["Highest Volume Change"])}</strong></div>
                        </div>
                    </div>""",
                    unsafe_allow_html=True
                )

                render_pinned_wallet_radar(st.session_state.watchlist_wallets)

                saved_settings = st.session_state.get("auto_wallet_settings", {"enabled": False, "interval": 60, "scope": "Pinned first, then all"})
                interval_options = [30, 60, 120, 300]
                saved_interval = int(saved_settings.get("interval", 60)) if str(saved_settings.get("interval", 60)).isdigit() else 60
                if saved_interval not in interval_options:
                    saved_interval = 60

                control_auto, control_interval, control_scope, control_sort, control_show, control_mode = st.columns([0.16, 0.15, 0.20, 0.20, 0.17, 0.12])
                with control_auto:
                    auto_watchlist = st.toggle(
                        "Auto Scan",
                        value=bool(saved_settings.get("enabled", False)),
                        help="Saved setting. If enabled, this starts automatically again after app restart."
                    )
                    set_auto_wallet_setting("enabled", bool(auto_watchlist))
                with control_interval:
                    auto_interval_seconds = st.selectbox(
                        "Interval",
                        interval_options,
                        index=interval_options.index(saved_interval),
                        format_func=lambda x: f"{x}s",
                        key="auto_wallet_interval_select"
                    )
                    set_auto_wallet_setting("interval", int(auto_interval_seconds))
                with control_scope:
                    scope_options = ["Pinned first, then all", "Pinned only"]
                    saved_scope = saved_settings.get("scope", "Pinned first, then all")
                    if saved_scope not in scope_options:
                        saved_scope = "Pinned first, then all"
                    auto_scope = st.selectbox("Auto scope", scope_options, index=scope_options.index(saved_scope), key="auto_wallet_scope_select")
                    set_auto_wallet_setting("scope", auto_scope)
                with control_sort:
                    sort_mode = st.selectbox("Sort", ["Pinned + movement", "Highest movement", "Highest volume change", "New swaps", "Best score", "Last checked"], index=0)
                with control_show:
                    wallet_filter = st.selectbox("Show", ["Actionable", "All", "Pinned only", "Hot only", "Moved only", "No movement"], index=0, key="watchlist_wallet_filter")
                with control_mode:
                    watch_mode = st.selectbox("Mode", ["Simple", "Advanced"], index=0, key="watchlist_view_mode")

                if auto_watchlist:
                    st_autorefresh(interval=auto_interval_seconds * 1000, key="wallet_watchlist_auto_refresh")
                    now_ts = time.time()
                    last_auto_check = st.session_state.get("last_auto_wallet_watchlist_check", 0)
                    if now_ts - last_auto_check >= auto_interval_seconds:
                        auto_results = []
                        auto_indices = wallet_check_indices(st.session_state.watchlist_wallets, auto_scope)
                        total_auto_wallets = len(auto_indices)

                        for recheck_index in auto_indices:
                            result = recheck_wallet_watchlist_item(recheck_index)
                            if result:
                                auto_results.append(result)

                        st.session_state.last_auto_wallet_watchlist_check = now_ts
                        st.session_state.last_auto_wallet_check_count = len(auto_results)
                        st.session_state.last_auto_wallet_failed_count = max(total_auto_wallets - len(auto_results), 0)
                        st.session_state.watchlist_message = f"Auto scanned {len(auto_results)} wallets. Failed/skipped: {st.session_state.last_auto_wallet_failed_count}." if auto_results else "Auto scan completed. No wallet movement found."
                        save_auto_wallet_settings()
                        st.rerun()

                action_col, status_col, _ = st.columns([0.16, 0.42, 0.42])
                with action_col:
                    if st.button("Check All", key="check_all_wallets"):
                        check_results = []
                        total_check_wallets = len(st.session_state.watchlist_wallets)
                        for recheck_index in range(total_check_wallets):
                            result = recheck_wallet_watchlist_item(recheck_index)
                            if result:
                                check_results.append(result)
                        skipped_count = max(total_check_wallets - len(check_results), 0)
                        st.session_state.watchlist_message = f"Checked {len(check_results)} wallets. Failed/skipped: {skipped_count}." if check_results else "Checked all wallets. No movement found."
                        st.rerun()
                with status_col:
                    if auto_watchlist:
                        last_auto = st.session_state.get("last_auto_wallet_watchlist_check", 0)
                        last_auto_text = pd.to_datetime(last_auto, unit="s").strftime("%H:%M:%S") if last_auto else "waiting"
                        checked_count = st.session_state.get("last_auto_wallet_check_count", 0)
                        failed_count = st.session_state.get("last_auto_wallet_failed_count", 0)
                        next_text = "soon" if not last_auto else f"~{max(int(auto_interval_seconds - (time.time() - last_auto)), 0)}s"
                        pinned_count = len([item for item in st.session_state.watchlist_wallets if wallet_is_pinned(item)])
                        st.caption(f"Auto Scan ON · saved across restarts · scope: {auto_scope} · pinned {pinned_count} · every {auto_interval_seconds}s · last {last_auto_text} · checked {checked_count} · skipped {failed_count} · next {next_text}")
                    else:
                        st.caption(f"Auto Scan OFF · saved across restarts · {len(st.session_state.watchlist_wallets)} wallets saved · use Check All or Check per wallet")

                if st.session_state.watchlist_message:
                    st.success(st.session_state.watchlist_message)

                displayed_pairs = []
                pinned_pairs = []
                quiet_pairs = []
                cooling_pairs = []
                attention_pairs = []

                for index, item in sorted_watchlist_pairs(st.session_state.watchlist_wallets, sort_mode):
                    status, _, _ = wallet_movement_status(item)
                    score_change, swaps_change, transfers_change, volume_change, largest_change = wallet_movement_values(item)
                    moved = any([score_change != 0, swaps_change != 0, transfers_change != 0, abs(volume_change) >= 0.01, abs(largest_change) >= 0.01])
                    actionable = status in ["HOT", "VOLUME SPIKE", "NEW SWAPS", "NEW TRANSFERS", "SCORE UP"] or abs(volume_change) >= 25
                    if wallet_filter == "Actionable" and not actionable and not wallet_is_pinned(item): 
                        continue
                    if wallet_filter == "Pinned only" and not wallet_is_pinned(item):
                        continue
                    if wallet_filter == "Hot only" and status not in ["HOT", "VOLUME SPIKE", "NEW SWAPS"]: 
                        continue
                    if wallet_filter == "Moved only" and not moved: 
                        continue
                    if wallet_filter == "No movement" and moved: 
                        continue

                    pair = (index, item, status)
                    displayed_pairs.append(pair)
                    if wallet_is_pinned(item):
                        pinned_pairs.append(pair)
                    elif actionable:
                        attention_pairs.append(pair)
                    elif status == "COOLING":
                        cooling_pairs.append(pair)
                    else:
                        quiet_pairs.append(pair)

                if not displayed_pairs:
                    st.info("No wallets match this filter. Switch Show to All if you want everything.")

                def render_wallet_card(index, item, movement_status):
                    signal = item.get("Signal", "-")
                    full_wallet = item.get("Full Wallet", "-")
                    wallet = wallet_watchlist_item_name(item)
                    current_score = safe_int(item.get("Score", 0))
                    current_swaps = safe_int(item.get("Swaps", 0))
                    current_transfers = safe_int(item.get("Transfers", 0))
                    current_buys = safe_int(item.get("Buys", 0))
                    current_sells = safe_int(item.get("Sells", 0))
                    current_volume = safe_float(item.get("USD Volume", 0))
                    current_largest = safe_float(item.get("Largest Tx", 0))
                    previous_score = safe_int(item.get("Previous Score", current_score))
                    previous_swaps = safe_int(item.get("Previous Swaps", current_swaps))
                    previous_transfers = safe_int(item.get("Previous Transfers", current_transfers))
                    previous_buys = safe_int(item.get("Previous Buys", current_buys))
                    previous_sells = safe_int(item.get("Previous Sells", current_sells))
                    previous_volume = safe_float(item.get("Previous USD Volume", current_volume))
                    previous_largest = safe_float(item.get("Previous Largest Tx", current_largest))
                    score_change = safe_int(item.get("Score Change", current_score - previous_score))
                    swaps_change = safe_int(item.get("Swaps Change", current_swaps - previous_swaps))
                    transfers_change = safe_int(item.get("Transfers Change", current_transfers - previous_transfers))
                    buys_change = safe_int(item.get("Buys Change", current_buys - previous_buys))
                    sells_change = safe_int(item.get("Sells Change", current_sells - previous_sells))
                    volume_change = safe_float(item.get("USD Volume Change", current_volume - previous_volume))
                    largest_change = safe_float(item.get("Largest Tx Change", current_largest - previous_largest))
                    latest_activity = item.get("Latest Activity", "-")
                    latest_token_mint = item.get("Latest Token Mint", "") or extract_first_token_mint(latest_activity)
                    movement_status, movement_badge_class, movement_hint = wallet_movement_status(item)
                    checks = item.get("Check Count", 1)
                    last_checked = item.get("Last Checked", "-")
                    pinned = wallet_is_pinned(item)
                    pin_badge = '<span class="pin-badge">PINNED</span>' if pinned else ""

                    if movement_status in ["HOT", "VOLUME SPIKE"]: 
                        card_class, pill_class, next_step = "human-card-hot", "human-pill-yellow", "Analyze token or open wallet."
                    elif movement_status in ["NEW SWAPS", "NEW TRANSFERS", "SCORE UP"]: 
                        card_class, pill_class, next_step = "human-card-up", "human-pill-green", "Worth checking."
                    elif movement_status == "COOLING": 
                        card_class, pill_class, next_step = "human-card-down", "human-pill-red", "Lower priority."
                    else: 
                        card_class, pill_class, next_step = "", "", "No action needed."

                    token_hint = latest_token_mint[:6] + "..." + latest_token_mint[-6:] if latest_token_mint else "No token"
                    latest_trade_side = str(item.get("Latest Trade Side", "-") or "-").upper()
                    latest_trade_token = item.get("Latest Trade Token", "-") or "-"
                    latest_trade_hint = item.get("Latest Trade Hint", "-") or "-"
                    trade_badge_class = trade_side_badge_class(latest_trade_side)

                    st.markdown(f"""<div class="human-card {card_class}">
                        <div class="human-card-top">
                            <div>
                                <div class="human-wallet">{wallet}{pin_badge}</div>
                                <div class="human-meta-line">{short_address(full_wallet)} · {signal} · {checks} checks · last {last_checked}</div>
                            </div>
                            <div class="human-pill {pill_class}" title="{movement_hint}">{movement_status}</div>
                        </div>
                        <div class="human-deltas">
                            <div><span>Swaps</span><strong class="{movement_class(swaps_change)}">{format_signed_number(swaps_change)}</strong></div>
                            <div><span>Buys</span><strong class="{movement_class(buys_change)}">{format_signed_number(buys_change)}</strong></div>
                            <div><span>Sells</span><strong class="{movement_class(-sells_change) if sells_change else 'movement-flat'}">{format_signed_number(sells_change)}</strong></div>
                            <div><span>Volume</span><strong class="{movement_class(volume_change)}">{format_signed_usd(volume_change)}</strong></div>
                            <div><span>Largest Tx</span><strong class="{movement_class(largest_change)}">{format_signed_usd(largest_change)}</strong></div>
                            <div><span>Token</span><strong>{token_hint}</strong></div>
                        </div>
                        <div class="human-latest"><span>Latest action</span><b class="{trade_badge_class}">{latest_trade_side}</b> · {latest_trade_token} · {latest_trade_hint}</div>
                        <div class="human-latest"><span>Next best action</span>{next_step}</div>
                    </div>""", unsafe_allow_html=True)

                    st.markdown('<div class="human-action-gap"></div>', unsafe_allow_html=True)
                    _, col_pin, col_check, col_analyze, col_open, col_remove = st.columns([3.15, 0.55, 0.65, 1.05, 0.65, 0.35])
                    with col_pin:
                        pin_label = "Unpin" if pinned else "Pin"
                        if st.button(pin_label, key=f"wallet_pin_card_{index}_{full_wallet}", type="secondary"):
                            toggle_wallet_pin(index)
                            st.rerun()
                    with col_check:
                        if st.button("Check", key=f"wallet_check_card_{index}_{full_wallet}", type="secondary"):
                            recheck_wallet_watchlist_item(index); st.rerun()
                    with col_analyze:
                        analyze_disabled = not bool(latest_token_mint)
                        if st.button("Analyze Token", key=f"wallet_analyze_card_{index}_{full_wallet}", type="secondary", disabled=analyze_disabled):
                            st.session_state.selected_token_mint = latest_token_mint
                            st.session_state.token_scanner_input = latest_token_mint
                            add_recent_item("recent_token_mints", latest_token_mint)
                            st.session_state.section_override = "Token Scanner"
                            st.rerun()
                    with col_open:
                        if st.button("Open", key=f"wallet_open_card_{index}_{full_wallet}", type="secondary"):
                            st.session_state.wallet_address_input = full_wallet
                            add_recent_item("recent_wallets", full_wallet)
                            st.session_state.section_override = "Smart Wallets"
                            st.rerun()
                    with col_remove:
                        if st.button("", help=f"Remove {wallet}", key=f"wallet_remove_card_{index}_{full_wallet}", type="primary"):
                            remove_wallet_from_watchlist(index); st.rerun()

                    with st.expander(f"Chart / story for {wallet}", expanded=False):
                        history_points_for_wallet = wallet_history_point_count(full_wallet)
                        reset_col, reset_hint_col = st.columns([0.18, 0.82])
                        with reset_col:
                            if st.button("Reset chart", key=f"wallet_reset_chart_{index}_{full_wallet}", type="secondary", disabled=history_points_for_wallet == 0):
                                clear_wallet_history_for_wallet(full_wallet)
                                st.rerun()
                        with reset_hint_col:
                            st.caption(f"Chart points saved: {history_points_for_wallet}. Reset only clears this wallet chart, not the wallet itself.")
                        render_wallet_history_chart(full_wallet, item)

                    if watch_mode == "Advanced":
                        with st.expander(f"Details for {wallet}", expanded=False):
                            st.markdown(
                                f"""
                                **Why:** {movement_hint}  
                                **Address:** `{full_wallet}`  
                                **Score:** {previous_score} → {current_score} ({format_signed_number(score_change)})  
                                **Swaps:** {previous_swaps} → {current_swaps} ({format_signed_number(swaps_change)})  
                                **Transfers:** {previous_transfers} → {current_transfers} ({format_signed_number(transfers_change)})  
                                **Buys:** {previous_buys} → {current_buys} ({format_signed_number(buys_change)})  
                                **Sells:** {previous_sells} → {current_sells} ({format_signed_number(sells_change)})  
                                **Volume:** {format_usd(previous_volume)} → {format_usd(current_volume)} ({format_signed_usd(volume_change)})  
                                **Largest Tx:** {format_usd(previous_largest)} → {format_usd(current_largest)} ({format_signed_usd(largest_change)})  
                                **Latest activity:** {latest_activity}
                                """
                            )

                if pinned_pairs:
                    st.markdown('<div class="section-title">Pinned wallets</div>', unsafe_allow_html=True)
                    for index, item, status in pinned_pairs:
                        render_wallet_card(index, item, status)

                if attention_pairs:
                    st.markdown('<div class="section-title">Needs attention</div>', unsafe_allow_html=True)
                    for index, item, status in attention_pairs:
                        render_wallet_card(index, item, status)

                if cooling_pairs:
                    with st.expander(f"Cooling / lower priority ({len(cooling_pairs)})", expanded=False):
                        for index, item, status in cooling_pairs:
                            render_wallet_card(index, item, status)

                if quiet_pairs:
                    with st.expander(f"Quiet wallets ({len(quiet_pairs)})", expanded=False):
                        for index, item, status in quiet_pairs:
                            render_wallet_card(index, item, status)

        with token_tab:
            st.markdown('<div class="section-title">Token Watchlist</div>', unsafe_allow_html=True)

            with st.expander("How to use Token Watchlist", expanded=False):
                st.markdown(
                    """
                    **Simple workflow:**  
                    1. Add tokens from **Analyze Token** or **Token Scanner**.  
                    2. Click **Recheck Tokens**.  
                    3. Read **Decision**, **Risk** and **Copy Risk** first.  
                    4. Open only tokens marked Watch/Monitor or tokens with a clear reason.
                    """
                )

            token_action_col, token_status_col, _ = st.columns([0.16, 0.42, 0.42])
            with token_action_col:
                if st.button("Recheck Tokens", key="recheck_all_tokens"):
                    recheck_all_token_watchlist_items(); st.rerun()
            with token_status_col:
                st.caption(f"{len(st.session_state.watchlist_tokens)} tokens saved · Decision first, details on demand.")

            if st.session_state.token_watchlist_message:
                st.success(st.session_state.token_watchlist_message)

            if st.session_state.watchlist_tokens:
                priority_tokens = []
                other_tokens = []
                for index, item in enumerate(st.session_state.watchlist_tokens):
                    decision = item.get("Decision", "Skip")
                    if decision in ["Watch", "Monitor", "Wait"]:
                        priority_tokens.append((index, item))
                    else:
                        other_tokens.append((index, item))

                def render_token_card(index, item):
                    token = item.get("Token", "Unknown")
                    name = item.get("Name", "Unknown")
                    mint = item.get("Mint", "")
                    decision = item.get("Decision", "Skip")
                    liquidity = item.get("Liquidity", "-")
                    volume = item.get("Volume", "-")
                    risk = item.get("Risk", "-")
                    copy_risk = item.get("Copy Risk", "-")
                    reason = item.get("Reason", "-")
                    source_wallet = item.get("Source Wallet", "-")
                    last_checked = item.get("Last Checked", "Not checked yet")
                    decision_class = "human-pill-green" if decision in ["Watch", "Monitor"] else "human-pill-yellow" if decision == "Wait" else "human-pill-red" if decision == "Avoid" else ""

                    st.markdown(f"""<div class="human-card">
                        <div class="human-card-top">
                            <div><div class="human-wallet">{token}</div><div class="human-meta-line">{name} · last checked {last_checked}</div></div>
                            <div class="human-pill {decision_class}">{decision}</div>
                        </div>
                        <div class="human-mini">
                            <div><span>Liquidity</span><strong>{liquidity}</strong></div>
                            <div><span>Volume</span><strong>{volume}</strong></div>
                            <div><span>Risk</span><strong>{risk}</strong></div>
                            <div><span>Copy Risk</span><strong>{copy_risk}</strong></div>
                        </div>
                        <div class="human-latest"><span>Next best action</span>{"Open and review" if decision in ["Watch", "Monitor"] else "Keep watching" if decision == "Wait" else "Lower priority"}</div>
                    </div>""", unsafe_allow_html=True)

                    st.markdown('<div class="human-action-gap"></div>', unsafe_allow_html=True)
                    _, col_open, col_recheck, col_remove = st.columns([4.05, 0.65, 0.75, 0.35])
                    with col_open:
                        if st.button("Open", help=f"{token} in Token Scanner öffnen", key=f"watchlist_open_{index}_{mint}"):
                            st.session_state.selected_token_mint = mint
                            st.session_state.token_scanner_input = mint
                            st.session_state.section_override = "Token Scanner"
                            st.rerun()
                    with col_recheck:
                        if st.button("Recheck", help=f"{token} neu prüfen", key=f"watchlist_recheck_{index}_{mint}"):
                            recheck_token_watchlist_item(index)
                            st.rerun()
                    with col_remove:
                        if st.button("", help=f"Remove {token}", key=f"watchlist_remove_{index}_{mint}", type="primary"):
                            remove_token_from_watchlist(index)
                            st.rerun()

                    with st.expander(f"Details for {token}", expanded=False):
                        st.markdown(
                            f"""
                            **Reason:** {reason}  
                            **Source wallet:** {source_wallet}  
                            **Mint:** `{mint}`
                            """
                        )

                if priority_tokens:
                    st.markdown('<div class="section-title">Priority tokens</div>', unsafe_allow_html=True)
                    for index, item in priority_tokens:
                        render_token_card(index, item)

                if other_tokens:
                    with st.expander(f"Lower priority tokens ({len(other_tokens)})", expanded=False):
                        for index, item in other_tokens:
                            render_token_card(index, item)
            else:
                st.info("No tokens added yet. Analyze a token and add it to the watchlist first.")


    elif section == "Token Finder" or section == "Token Scanner" or section == "Auto Discovery" or section == "Market Monitor":
        st.markdown('<p style="font-size:24px;font-weight:600;color:#f5f5f7;padding:28px 0 4px;">Token Finder</p>', unsafe_allow_html=True)
        st.markdown('<p style="font-size:14px;color:#5a5b62;margin-bottom:16px;">DexScreener radar — find early tokens, trace which wallets bought first.</p>', unsafe_allow_html=True)

        st.markdown(
            """
            <style>
            .alpha-hero {
                border: 1px solid rgba(34, 197, 94, 0.26);
                background:
                    radial-gradient(circle at top left, rgba(34,197,94,.16), transparent 35%),
                    linear-gradient(135deg, rgba(15, 23, 42, .96), rgba(20, 83, 45, .24));
                border-radius: 24px;
                padding: 18px 20px;
                margin: 4px 0 16px 0;
                box-shadow: 0 18px 50px rgba(0,0,0,.26);
            }
            .alpha-hero-title { font-size: 24px; font-weight: 950; color: #f8fafc; margin-bottom: 6px; }
            .alpha-hero-sub { color: #cbd5e1; font-size: 13px; line-height: 1.55; max-width: 980px; }
            .alpha-flow { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin-top: 15px; }
            .alpha-flow div { background: rgba(255,255,255,0.045); border: 1px solid rgba(255,255,255,0.08); border-radius: 15px; padding: 12px; }
            .alpha-flow span { display:block; color:#94a3b8; font-size:11px; margin-bottom:6px; }
            .alpha-flow strong { color:#f8fafc; font-size:13px; }
            .alpha-control-panel {
                border: 1px solid rgba(255,255,255,.09);
                background: linear-gradient(145deg, rgba(30,41,59,.62), rgba(15,23,42,.55));
                border-radius: 20px;
                padding: 15px 16px;
                margin: 12px 0;
            }
            .alpha-results-panel { border-color: rgba(56,189,248,.22); background: linear-gradient(145deg, rgba(56,189,248,.09), rgba(15,23,42,.58)); }
            .alpha-panel-top { display:flex; justify-content:space-between; align-items:flex-start; gap:12px; margin-bottom:12px; }
            .alpha-panel-title { color:#f8fafc; font-size:16px; font-weight:900; }
            .alpha-panel-sub { color:#94a3b8; font-size:12px; margin-top:4px; line-height:1.45; }
            .alpha-live-pill { color:#86efac; border:1px solid rgba(34,197,94,.28); background:rgba(34,197,94,.10); border-radius:999px; padding:7px 10px; font-size:11px; font-weight:900; white-space:nowrap; }
            .alpha-stat-grid, .wallet-results-summary { display:grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap:9px; }
            .wallet-results-summary { grid-template-columns: repeat(4, minmax(0, 1fr)); margin: 8px 0 12px 0; }
            .alpha-stat-grid div, .wallet-results-summary div { background:rgba(255,255,255,.04); border:1px solid rgba(255,255,255,.075); border-radius:13px; padding:10px 11px; }
            .alpha-stat-grid span, .wallet-results-summary span { display:block; color:#94a3b8; font-size:11px; margin-bottom:6px; }
            .alpha-stat-grid strong, .wallet-results-summary strong { color:#f8fafc; font-size:17px; }
            .alpha-token-grid { display:grid; grid-template-columns: repeat(2, minmax(0,1fr)); gap:12px; margin:8px 0 14px 0; }
            .alpha-candidate-card { background: linear-gradient(145deg, rgba(36,37,42,.96), rgba(29,30,35,.96)); border: 1px solid rgba(255,255,255,0.08); border-radius: 18px; padding: 15px 17px; margin: 12px 0 8px 0; box-shadow: 0 14px 35px rgba(0,0,0,.22); }
            .alpha-candidate-card.candidate-hot { border-color: rgba(34,197,94,.42); background: linear-gradient(145deg, rgba(34,197,94,.10), rgba(29,30,35,.98)); }
            .alpha-candidate-card.candidate-watch { border-color: rgba(245,158,11,.42); background: linear-gradient(145deg, rgba(245,158,11,.10), rgba(29,30,35,.98)); }
            .alpha-candidate-card.candidate-neutral { border-color: rgba(148,163,184,.22); }
            .alpha-candidate-top { display:flex; align-items:flex-start; justify-content:space-between; gap:12px; margin-bottom:10px; }
            .alpha-candidate-token { color:#f8fafc; font-size:18px; font-weight:900; }
            .alpha-candidate-sub { color:#94a3b8; font-size:12px; margin-top:3px; }
            .alpha-score { color:#bbf7d0; border:1px solid rgba(34,197,94,.32); background:rgba(34,197,94,.10); border-radius:999px; padding:8px 11px; font-weight:900; white-space:nowrap; }
            .alpha-badges { display:flex; flex-wrap:wrap; gap:7px; margin:8px 0 10px 0; }
            .alpha-badges span { color:#fde68a; border:1px solid rgba(245,158,11,.25); background:rgba(245,158,11,.08); border-radius:999px; padding:6px 9px; font-size:11px; font-weight:800; }
            .alpha-candidate-read { color:#dbeafe; font-size:13px; line-height:1.45; margin-bottom:10px; }
            .alpha-mini-grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:9px; }
            .alpha-mini-grid div { background:rgba(255,255,255,.035); border:1px solid rgba(255,255,255,.075); border-radius:12px; padding:9px 10px; }
            .alpha-mini-grid span { display:block; color:#94a3b8; font-size:11px; margin-bottom:5px; }
            .alpha-mini-grid strong { color:#f8fafc; font-size:13px; }
            .alpha-hint { color:#cbd5e1; font-size:12px; margin-top:10px; }
            .alpha-wallet-card {
                background: linear-gradient(145deg, rgba(15,23,42,.92), rgba(30,41,59,.72));
                border:1px solid rgba(148,163,184,.18);
                border-radius:18px;
                padding:14px 15px;
                margin: 8px 0;
                min-height: 220px;
            }
            .alpha-wallet-card.hot { border-color:rgba(34,197,94,.52); background:linear-gradient(145deg, rgba(34,197,94,.12), rgba(15,23,42,.90)); }
            .alpha-wallet-card.good { border-color:rgba(56,189,248,.38); background:linear-gradient(145deg, rgba(56,189,248,.10), rgba(15,23,42,.90)); }
            .alpha-wallet-card.watch { border-color:rgba(245,158,11,.34); background:linear-gradient(145deg, rgba(245,158,11,.10), rgba(15,23,42,.90)); }
            .alpha-wallet-card.saved { border-color:rgba(148,163,184,.28); opacity:.82; }
            .alpha-wallet-top { display:flex; justify-content:space-between; align-items:flex-start; gap:10px; }
            .alpha-wallet-name { color:#f8fafc; font-size:16px; font-weight:950; }
            .alpha-wallet-address { color:#94a3b8; font-size:12px; margin-top:4px; }
            .alpha-wallet-score { border-radius:999px; padding:7px 10px; font-size:12px; font-weight:950; white-space:nowrap; }
            .alpha-wallet-score.score-hot { color:#bbf7d0; border:1px solid rgba(34,197,94,.35); background:rgba(34,197,94,.12); }
            .alpha-wallet-score.score-good { color:#bae6fd; border:1px solid rgba(56,189,248,.32); background:rgba(56,189,248,.12); }
            .alpha-wallet-score.score-neutral { color:#e5e7eb; border:1px solid rgba(148,163,184,.22); background:rgba(148,163,184,.08); }
            .alpha-wallet-badges { display:flex; flex-wrap:wrap; gap:6px; margin:11px 0; }
            .alpha-wallet-badges span { border-radius:999px; padding:5px 8px; font-size:10px; font-weight:900; color:#e5e7eb; background:rgba(255,255,255,.06); border:1px solid rgba(255,255,255,.08); }
            .alpha-wallet-badges span.hot { color:#bbf7d0; border-color:rgba(34,197,94,.26); background:rgba(34,197,94,.10); }
            .alpha-wallet-badges span.good { color:#bae6fd; border-color:rgba(56,189,248,.24); background:rgba(56,189,248,.10); }
            .alpha-wallet-badges span.watch { color:#fde68a; border-color:rgba(245,158,11,.24); background:rgba(245,158,11,.10); }
            .alpha-wallet-badges span.neutral { color:#cbd5e1; }
            .alpha-wallet-why { color:#e2e8f0; font-size:12px; line-height:1.45; margin-bottom:8px; }
            .alpha-wallet-text { color:#94a3b8; font-size:12px; line-height:1.4; margin-top:5px; }
            .alpha-step-note { background:rgba(56,189,248,.09); border:1px solid rgba(56,189,248,.22); color:#bae6fd; border-radius:15px; padding:11px 13px; margin:10px 0 14px 0; font-size:13px; line-height:1.45; }
            .alpha-danger-note { background:rgba(245,158,11,.09); border:1px solid rgba(245,158,11,.22); color:#fde68a; border-radius:15px; padding:11px 13px; margin:10px 0 14px 0; font-size:13px; line-height:1.45; }
            @media(max-width:1100px){ .alpha-token-grid{grid-template-columns:1fr;} }
            @media(max-width:900px){ .alpha-flow,.alpha-mini-grid,.alpha-stat-grid,.wallet-results-summary{grid-template-columns:repeat(2,minmax(0,1fr));} }
        
            .alpha-human-row { border-radius:14px; padding:10px 12px; margin:8px 0 10px 0; font-size:12px; line-height:1.45; border:1px solid rgba(255,255,255,.08); }
            .alpha-human-row.good { background:rgba(34,197,94,.10); border-color:rgba(34,197,94,.24); color:#bbf7d0; }
            .alpha-human-row.watch { background:rgba(56,189,248,.10); border-color:rgba(56,189,248,.24); color:#bae6fd; }
            .alpha-human-row.low { background:rgba(148,163,184,.08); border-color:rgba(148,163,184,.18); color:#cbd5e1; }
            .alpha-human-row.saved { background:rgba(245,158,11,.08); border-color:rgba(245,158,11,.20); color:#fde68a; }
            .wallet-results-summary.compact { margin-bottom: 12px; }
            .alpha-token-row { display:grid; grid-template-columns: minmax(220px, 1.8fr) repeat(5, minmax(90px, .65fr)); gap:10px; align-items:center; border-radius:16px; padding:12px 14px; margin:8px 0; border:1px solid rgba(255,255,255,.09); background:rgba(255,255,255,.035); }
            .alpha-token-row.hot { border-color:rgba(34,197,94,.28); background:linear-gradient(135deg, rgba(34,197,94,.10), rgba(255,255,255,.025)); }
            .alpha-token-row.good { border-color:rgba(56,189,248,.22); }
            .alpha-token-row.neutral { opacity:.86; }
            .alpha-token-title { color:#f8fafc; font-weight:950; font-size:15px; }
            .alpha-token-title span { color:#94a3b8; font-size:11px; font-weight:700; margin-left:6px; }
            .alpha-token-sub { color:#94a3b8; font-size:12px; margin-top:4px; }
            .alpha-token-row span { color:#94a3b8; font-size:10px; display:block; margin-bottom:4px; }
            .alpha-token-row b { color:#f8fafc; font-size:13px; }
            .alpha-mode-banner { border-radius:18px; padding:13px 15px; margin:12px 0; background:rgba(15,23,42,.76); border:1px solid rgba(56,189,248,.18); color:#cbd5e1; font-size:13px; line-height:1.5; }
            @media(max-width:1100px){ .alpha-token-row{grid-template-columns:1fr 1fr 1fr;} }
    </style>
            """,
            unsafe_allow_html=True
        )

        st.markdown(
            """
            <div class="alpha-hero">
                <div class="alpha-hero-title">Auto Alpha Discovery</div>
                <div class="alpha-hero-sub">
                    This page scans DexScreener market-wide, keeps only early-looking Solana tokens, then searches for fresh wallets around those tokens.
                    The edge is not one token. The edge is finding wallets that show up early again and again.
                </div>
                <div class="alpha-flow">
                    <div><span>1</span><strong>Find early tokens</strong></div>
                    <div><span>2</span><strong>Filter out late / weak setups</strong></div>
                    <div><span>3</span><strong>Extract fresh wallets</strong></div>
                    <div><span>4</span><strong>Add + pin only the best</strong></div>
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

        for key, default in {
            "dex_alpha_tokens": pd.DataFrame(),
            "dex_alpha_wallets": pd.DataFrame(),
            "alpha_review_result": {},
            "alpha_discovered_wallets": pd.DataFrame(),
            "dex_alpha_seen_tokens": [],
            "dex_alpha_seen_wallets": [],
            "dex_alpha_scan_round": 0,
            "dex_alpha_last_mode": ""
        }.items():
            if key not in st.session_state:
                st.session_state[key] = default

        st.markdown(
            '<div class="alpha-step-note"><b>Beginner mode:</b> Press <b>Fresh Scan</b>. First look at the wallet section, not the token section. Add + pin wallets marked <b>Priority</b> or <b>Repeat early</b>. Those are the wallets that may become useful long-term.</div>',
            unsafe_allow_html=True
        )

        with st.container(border=True):
            st.markdown("**Scan controls**")
            c1, c2, c3, c4 = st.columns([0.20, 0.22, 0.22, 0.36])
            with c1:
                max_tokens = st.selectbox("Top tokens", [5, 8, 10], index=0, help="How many filtered DexScreener tokens to keep.")
            with c2:
                market_min_score = st.slider("Min token score", 0, 100, 45, help="Higher = stricter, fewer candidates.")
            with c3:
                strict_early = st.toggle("Strict early filter", value=True, help="Removes weak, old, or already overextended tokens.")
            with c4:
                only_new_wallets = st.toggle("Fresh wallets only", value=True, help="Hide wallets already shown in previous discovery scans and hide saved wallets.")

            b1, b2, b3, b4 = st.columns([0.22, 0.25, 0.22, 0.31])
            with b1:
                scan_now = st.button("Fresh Scan", type="primary", key="scan_dex_alpha_fresh")
            with b2:
                rescan_same_pool = st.button("Rescan / include old", key="scan_dex_alpha_rescan")
            with b3:
                clear_seen = st.button("Reset seen cache", key="scan_dex_alpha_reset_seen")
            with b4:
                seen_t, seen_w = dex_alpha_seen_counts()
                st.caption(f"Fresh Scan hides already shown results. Seen cache: {seen_t} tokens / {seen_w} wallets.")

            auto_add_candidates = st.toggle(
                "Auto-add strong fresh wallets as Watch candidates",
                value=False,
                help="Only new wallets with Alpha score >= 82 or repeated early tokens are added. They are not pinned automatically."
            )

        if clear_seen:
            reset_dex_alpha_seen_cache()
            st.session_state.dex_alpha_scan_round = 0
            st.success("Seen cache cleared. Fresh Scan can show previously hidden wallets again.")

        run_scan = scan_now or rescan_same_pool
        exclude_seen = bool(scan_now and only_new_wallets)

        if run_scan:
            if scan_now:
                remember_alpha_scan_results(
                    st.session_state.get("dex_alpha_tokens", pd.DataFrame()),
                    st.session_state.get("dex_alpha_wallets", pd.DataFrame())
                )
            with st.spinner("Scanning DexScreener and filtering early Solana tokens..."):
                token_df, wallet_df, scan_error = fresh_dex_alpha_scan(
                    max_tokens=max_tokens,
                    min_score=market_min_score,
                    strict_early=strict_early,
                    exclude_seen=exclude_seen,
                    include_saved_wallets=not only_new_wallets
                )
            if scan_error:
                st.error(scan_error)
                st.session_state.dex_alpha_tokens = pd.DataFrame()
                st.session_state.dex_alpha_wallets = pd.DataFrame()
            else:
                st.session_state.dex_alpha_tokens = token_df
                st.session_state.dex_alpha_wallets = wallet_df
                st.session_state.dex_alpha_scan_round = safe_int(st.session_state.get("dex_alpha_scan_round", 0)) + 1
                st.session_state.dex_alpha_last_mode = "Fresh-only" if exclude_seen else "Rescan / include old"
                if token_df is None or token_df.empty:
                    st.warning("No token candidates passed the current filter. Lower Min token score or disable Strict early filter.")
                else:
                    auto_added = 0
                    if auto_add_candidates and wallet_df is not None and not wallet_df.empty:
                        strong_df = wallet_df.copy()
                        strong_df["Alpha Wallet Score"] = pd.to_numeric(strong_df.get("Alpha Wallet Score", 0), errors="coerce").fillna(0)
                        strong_df["Early Tokens"] = pd.to_numeric(strong_df.get("Early Tokens", 0), errors="coerce").fillna(0)
                        strong_df = strong_df[(strong_df["Alpha Wallet Score"] >= 82) | (strong_df["Early Tokens"] >= 2)].head(5)
                        for _, auto_row in strong_df.iterrows():
                            full_wallet = str(auto_row.get("Full Wallet", "")).strip()
                            if not full_wallet or wallet_already_saved(full_wallet):
                                continue
                            auto_item = {
                                "Wallet": auto_row.get("Wallet", short_address(full_wallet)),
                                "Full Wallet": full_wallet,
                                "Signal": "Watch",
                                "Score": safe_int(auto_row.get("Best Score", auto_row.get("Alpha Wallet Score", 0))),
                                "Transfers": safe_int(auto_row.get("Hits", 0)),
                                "Swaps": safe_int(auto_row.get("Swaps", 0)),
                                "USD Volume": 0,
                                "Largest Tx": 0,
                                "Last Checked": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
                                "Check Count": 1,
                                "Pinned": False,
                                "Latest Activity": f"Auto-added from Discovery tokens: {auto_row.get('Tokens', '-')}",
                                "Change": "Auto Discovery watch candidate"
                            }
                            add_wallet_to_watchlist(auto_item)
                            auto_added += 1
                    auto_text = f" · auto-added {auto_added} watch candidate(s)" if auto_added else ""
                    st.success(f"Scan #{st.session_state.dex_alpha_scan_round}: {len(token_df)} token(s), {0 if wallet_df is None else len(wallet_df)} fresh wallet candidate(s){auto_text}.")

        token_df = st.session_state.get("dex_alpha_tokens", pd.DataFrame())
        wallet_df = st.session_state.get("dex_alpha_wallets", pd.DataFrame())

        if token_df is None or token_df.empty:
            st.info("No discovery scan loaded yet. Click Fresh Scan.")
            st.markdown(
                """
                **What this will do:**
                1. Pull Solana token candidates from DexScreener.  
                2. Keep only early-looking setups.  
                3. Find wallets around those tokens.  
                4. Highlight fresh wallets that appear repeatedly.
                """
            )
        else:
            st.markdown(
                '<div class="alpha-mode-banner"><b>How to use this page:</b> First scan, then only care about wallets in Priority or Watch. Tokens are just the bait. The real goal is to find wallets that appear early repeatedly. Use Fresh Scan for new candidates and Rescan / include old only for comparison.</div>',
                unsafe_allow_html=True
            )
            render_alpha_scan_dashboard(token_df, wallet_df, only_new_wallets=only_new_wallets)

            if wallet_df is not None and not wallet_df.empty:
                render_discovered_wallet_candidates(
                    wallet_df,
                    title="Best fresh wallet candidates",
                    caption="These are the wallets found around the current filtered token set. Repeated early wallets are the highest priority.",
                    key_prefix="dex_global_wallet",
                    limit=12
                )
            else:
                st.markdown(
                    '<div class="alpha-danger-note"><b>No fresh wallets shown.</b> The tokens were found, but wallet filtering returned nothing new. Try Rescan / include old, lower Min token score, or Reset seen cache.</div>',
                    unsafe_allow_html=True
                )

            st.divider()
            st.markdown("### Token shortlist")
            st.caption("Use this section after the wallet section. Tokens are market-wide DexScreener candidates, not from your watchlist.")

            for idx, row in token_df.iterrows():
                render_market_token_card(row, idx)
                mint = str(row.get("Mint", ""))
                source_wallet = "DexScreener Auto Discovery"
                b1, b2, b3, b4, b5 = st.columns([0.12, 0.13, 0.13, 0.14, 0.48])
                with b1:
                    if st.button("Analyze", key=f"dex_alpha_analyze_{idx}_{mint}"):
                        st.session_state.selected_token_mint = mint
                        st.session_state.token_scanner_input = mint
                        add_recent_item("recent_token_mints", mint)
                        st.session_state.section_override = "Token Scanner"
                        st.rerun()
                with b2:
                    if st.button("Live review", key=f"dex_alpha_review_{idx}_{mint}"):
                        with st.spinner("Checking live DEX pair..."):
                            review, err = review_auto_token_candidate(mint, row.get("Token", "Token"))
                        if err:
                            st.session_state.alpha_review_result[mint] = {"error": err}
                        else:
                            st.session_state.alpha_review_result[mint] = review
                        st.rerun()
                with b3:
                    if st.button("Add token", key=f"dex_alpha_add_{idx}_{mint}"):
                        review = st.session_state.alpha_review_result.get(mint)
                        if not review or review.get("error"):
                            review = {
                                "Token": row.get("Token", "Token"),
                                "Mint": mint,
                                "Decision": row.get("Stage", "Watch"),
                                "Liquidity": format_usd(row.get("Liquidity USD", 0)),
                                "Volume": format_usd(row.get("Volume 24h", 0)),
                                "Activity": f"{safe_int(row.get('Txns 24h', 0))} txns 24h",
                                "Risk": "Market-wide candidate",
                                "Copy Risk": "Unknown",
                                "Reason": row.get("Read", "DexScreener auto discovered token."),
                                "Last Checked": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")
                            }
                        add_token_to_watchlist(auto_token_watchlist_item(review, source_wallet))
                        st.success(st.session_state.token_watchlist_message)
                with b4:
                    if st.button("Find wallets", key=f"dex_alpha_find_wallets_{idx}_{mint}"):
                        remember_alpha_scan_results(wallet_df=st.session_state.get("alpha_discovered_wallets", pd.DataFrame()))
                        with st.spinner("Finding fresh wallets around this token..."):
                            single_df = discover_wallets_for_market_candidates(pd.DataFrame([row]), max_tokens=1, max_wallets_per_token=16)
                            single_df = filter_fresh_wallet_candidates(single_df, exclude_seen=only_new_wallets, include_saved=not only_new_wallets)
                        st.session_state.alpha_discovered_wallets = single_df if single_df is not None else pd.DataFrame()
                        st.session_state.alpha_discovered_wallets_source_mint = mint
                        st.session_state.alpha_discovered_wallets_source_token = row.get("Token", "Token")
                        st.success(f"Found {0 if single_df is None else len(single_df)} fresh wallet candidate(s).")
                with b5:
                    review = st.session_state.alpha_review_result.get(mint)
                    if review:
                        if review.get("error"):
                            st.warning(review.get("error"))
                        else:
                            st.markdown(f"**Live:** {review.get('Decision', '-')} · Liquidity {review.get('Liquidity', '-')} · Volume {review.get('Volume', '-')} · Risk {review.get('Risk', '-')}")

                single_wallet_df = st.session_state.get("alpha_discovered_wallets", pd.DataFrame())
                single_source_mint = st.session_state.get("alpha_discovered_wallets_source_mint", "")
                if single_source_mint == mint and single_wallet_df is not None and not single_wallet_df.empty:
                    render_discovered_wallet_candidates(
                        single_wallet_df,
                        title=f"Fresh wallets around {row.get('Token', 'this token')}",
                        caption="Token-specific wallet candidates from the button above.",
                        key_prefix=f"dex_single_wallet_{idx}",
                        limit=12
                    )
                    st.divider()

        with st.expander("Optional: also use my watched-wallet history", expanded=False):
            source_scope = st.selectbox("Watched-wallet source", ["Pinned wallets", "All watched wallets"], index=0, key="watched_source_scope")
            range_label = st.selectbox("Watched-wallet range", ["Fresh only", "Last 6 checks", "Last 12 checks", "Last 24 checks", "All"], index=0, key="watched_range_label")
            include_unclear = st.toggle("Include unclear blue swaps", value=False, key="watched_include_unclear")
            if st.button("Find from watched wallets", key="find_from_watched_wallets"):
                watched_df, watched_wallet_df = build_alpha_discovery_candidates(source_scope, range_label, include_unclear)
                st.session_state.alpha_candidate_df = watched_df
                st.session_state.alpha_wallet_df = watched_wallet_df
                st.success(f"Found {len(watched_df)} watched-wallet token candidate(s).")
            watched_df = st.session_state.get("alpha_candidate_df", pd.DataFrame())
            if watched_df is not None and not watched_df.empty:
                for idx, row in watched_df.head(8).iterrows():
                    render_alpha_candidate_card(row, idx)



    elif section == "_market_monitor_disabled":
        st.title("Market Monitor")
        st.caption("Long-term alpha memory: scan the market repeatedly, remember tokens, and learn which wallets show up early more than once.")

        st.markdown(
            """
            <style>
            .monitor-hero {
                border:1px solid rgba(56,189,248,.24);
                background:linear-gradient(135deg, rgba(14,165,233,.14), rgba(15,23,42,.92) 50%, rgba(34,197,94,.10));
                border-radius:24px;
                padding:18px;
                margin:8px 0 18px 0;
                box-shadow:0 18px 48px rgba(0,0,0,.22);
            }
            .monitor-title { font-size:22px; font-weight:900; color:#f8fafc; margin-bottom:6px; }
            .monitor-sub { color:#cbd5e1; font-size:13px; line-height:1.45; max-width:980px; }
            .monitor-flow { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:10px; margin-top:16px; }
            .monitor-flow div { border:1px solid rgba(255,255,255,.08); background:rgba(255,255,255,.035); border-radius:16px; padding:11px 12px; }
            .monitor-flow span { color:#7dd3fc; font-size:11px; font-weight:850; text-transform:uppercase; letter-spacing:.03em; }
            .monitor-flow b { display:block; color:#f8fafc; margin-top:5px; font-size:13px; }
            .monitor-kpi-grid { display:grid; grid-template-columns:repeat(5,minmax(0,1fr)); gap:10px; margin: 10px 0 18px 0; }
            .monitor-kpi { border:1px solid rgba(148,163,184,.16); background:rgba(255,255,255,.035); border-radius:16px; padding:12px 14px; }
            .monitor-kpi span { color:#94a3b8; display:block; font-size:11px; margin-bottom:6px; }
            .monitor-kpi strong { color:#f8fafc; font-size:20px; }
            .monitor-panel { border:1px solid rgba(148,163,184,.16); background:rgba(15,23,42,.58); border-radius:20px; padding:16px; margin:12px 0; }
            .monitor-section-head { font-size:18px; font-weight:900; color:#f8fafc; margin:14px 0 4px; }
            .monitor-help { color:#94a3b8; font-size:13px; margin-bottom:10px; }
            .memory-wallet-card { min-height:245px; border-radius:20px; padding:15px; margin:8px 0; border:1px solid rgba(148,163,184,.18); background:linear-gradient(145deg, rgba(15,23,42,.92), rgba(30,41,59,.72)); }
            .memory-wallet-card.core { border-color:rgba(34,197,94,.58); background:linear-gradient(145deg, rgba(34,197,94,.13), rgba(15,23,42,.92)); }
            .memory-wallet-card.repeat { border-color:rgba(56,189,248,.46); background:linear-gradient(145deg, rgba(56,189,248,.12), rgba(15,23,42,.92)); }
            .memory-wallet-card.watch { border-color:rgba(245,158,11,.42); background:linear-gradient(145deg, rgba(245,158,11,.10), rgba(15,23,42,.92)); }
            .memory-card-top { display:flex; align-items:flex-start; justify-content:space-between; gap:12px; }
            .memory-wallet-name { color:#f8fafc; font-size:17px; font-weight:950; }
            .memory-wallet-address { color:#94a3b8; font-size:12px; margin-top:4px; }
            .memory-trust-pill { border-radius:999px; padding:8px 11px; font-weight:950; color:#dcfce7; background:rgba(34,197,94,.14); border:1px solid rgba(34,197,94,.35); }
            .memory-trust-pill.repeat { color:#bae6fd; background:rgba(56,189,248,.14); border-color:rgba(56,189,248,.35); }
            .memory-trust-pill.watch { color:#fde68a; background:rgba(245,158,11,.14); border-color:rgba(245,158,11,.35); }
            .memory-trust-pill.low { color:#cbd5e1; background:rgba(148,163,184,.10); border-color:rgba(148,163,184,.20); }
            .memory-label { margin:10px 0 10px; color:#e5e7eb; font-weight:800; }
            .memory-grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:8px; }
            .memory-grid div { background:rgba(255,255,255,.045); border:1px solid rgba(255,255,255,.075); border-radius:13px; padding:9px; }
            .memory-grid span { color:#94a3b8; display:block; font-size:11px; }
            .memory-grid b { color:#f8fafc; font-size:14px; }
            .memory-note { color:#cbd5e1; font-size:12px; margin-top:10px; line-height:1.4; }
            .memory-user-note { color:#fde68a; background:rgba(245,158,11,.09); border:1px solid rgba(245,158,11,.20); border-radius:12px; padding:8px; margin-top:9px; font-size:12px; }
            .monitor-warning { border:1px solid rgba(245,158,11,.26); background:rgba(245,158,11,.09); color:#fde68a; border-radius:16px; padding:12px 14px; font-size:13px; margin:10px 0; }
            @media (max-width: 1100px) { .monitor-flow, .monitor-kpi-grid { grid-template-columns:repeat(2,minmax(0,1fr)); } }
            </style>
            <div class="monitor-hero">
                <div class="monitor-title">Market Monitor: live search + long-term alpha memory</div>
                <div class="monitor-sub">This is the stronger engine. Live search finds what is hot right now. Market Monitor keeps snapshots over time, remembers which wallets appear early, and builds a trust score instead of forcing users to read raw addresses and random stats.</div>
                <div class="monitor-flow">
                    <div><span>Step 1</span><b>Scan DexScreener early tokens</b></div>
                    <div><span>Step 2</span><b>Find wallets around those tokens</b></div>
                    <div><span>Step 3</span><b>Save token + wallet memory</b></div>
                    <div><span>Step 4</span><b>Promote repeat early wallets</b></div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        settings = st.session_state.get("market_monitor_settings", {})
        c1, c2, c3, c4, c5 = st.columns([0.18, 0.19, 0.18, 0.18, 0.27])
        with c1:
            monitor_enabled = st.toggle("Auto monitor", value=bool(settings.get("enabled", False)), key="market_monitor_enabled_toggle")
            set_market_monitor_setting("enabled", monitor_enabled)
        with c2:
            interval_minutes = st.selectbox("Interval", [5, 10, 15, 30, 60], index=[5, 10, 15, 30, 60].index(int(settings.get("interval_minutes", 10))) if int(settings.get("interval_minutes", 10)) in [5, 10, 15, 30, 60] else 1, key="market_monitor_interval_select")
            set_market_monitor_setting("interval_minutes", interval_minutes)
        with c3:
            max_tokens = st.selectbox("Top tokens", [3, 5, 8, 10], index=1, key="market_monitor_max_tokens")
            set_market_monitor_setting("max_tokens", max_tokens)
        with c4:
            min_score = st.slider("Min token score", 35, 85, int(settings.get("min_score", 55)), key="market_monitor_min_score")
            set_market_monitor_setting("min_score", min_score)
        with c5:
            strict_early = st.toggle("Strict early filter", value=bool(settings.get("strict_early", True)), key="market_monitor_strict_toggle")
            set_market_monitor_setting("strict_early", strict_early)

        if monitor_enabled:
            st_autorefresh(interval=max(int(interval_minutes), 1) * 60 * 1000, key="market_monitor_auto_refresh")
            if market_monitor_should_scan(st.session_state.market_monitor_settings):
                with st.spinner("Auto Market Monitor scan running..."):
                    run_market_monitor_scan(source="auto")

        action_col1, action_col2, action_col3 = st.columns([0.22, 0.24, 0.54])
        with action_col1:
            if st.button("Run market scan now", type="primary", key="market_monitor_manual_scan"):
                with st.spinner("Scanning DexScreener, scoring tokens, and finding wallets..."):
                    run_market_monitor_scan(max_tokens=max_tokens, min_score=min_score, strict_early=strict_early, source="manual")
                st.success(st.session_state.market_monitor_message)
        with action_col2:
            if st.button("Reload memory", key="market_monitor_reload_memory"):
                st.session_state.market_snapshots = load_json_list(MARKET_SNAPSHOTS_FILE)
                st.session_state.token_memory = load_json_dict(TOKEN_MEMORY_FILE)
                st.session_state.wallet_alpha_memory = load_json_dict(WALLET_ALPHA_MEMORY_FILE)
                st.session_state.wallet_documentation = load_json_dict(WALLET_DOCUMENTATION_FILE)
                st.session_state.discovery_runs = load_json_list(DISCOVERY_RUNS_FILE)
                st.success("Market memory reloaded.")
        with action_col3:
            last_scan = st.session_state.market_monitor_settings.get("last_scan_label", "never") or "never"
            st.caption(f"Last scan: {last_scan}. Auto monitor runs while this Streamlit app/page is active.")

        if st.session_state.market_monitor_message:
            st.success(st.session_state.market_monitor_message)

        token_memory_df, wallet_memory_df = market_monitor_memory_tables()
        run_count = len(st.session_state.get("discovery_runs", []))
        snapshot_count = len(st.session_state.get("market_snapshots", []))
        token_count = 0 if token_memory_df is None or token_memory_df.empty else len(token_memory_df)
        wallet_count = 0 if wallet_memory_df is None or wallet_memory_df.empty else len(wallet_memory_df)
        wallet_doc_count = len(st.session_state.get("wallet_documentation", {}))
        strong_wallets = 0 if wallet_memory_df is None or wallet_memory_df.empty or "Trust Score" not in wallet_memory_df.columns else int((pd.to_numeric(wallet_memory_df["Trust Score"], errors="coerce").fillna(0) >= 70).sum())

        st.markdown(
            f"""
            <div class="monitor-kpi-grid">
                <div class="monitor-kpi"><span>Monitor runs</span><strong>{run_count}</strong></div>
                <div class="monitor-kpi"><span>Token snapshots</span><strong>{snapshot_count}</strong></div>
                <div class="monitor-kpi"><span>Tokens remembered</span><strong>{token_count}</strong></div>
                <div class="monitor-kpi"><span>Wallets remembered</span><strong>{wallet_count}</strong></div>
                <div class="monitor-kpi"><span>Wallet docs</span><strong>{wallet_doc_count}</strong></div>
                <div class="monitor-kpi"><span>Strong wallets</span><strong>{strong_wallets}</strong></div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        tab_wallets, tab_journal, tab_tokens, tab_runs, tab_settings = st.tabs(["Best wallets", "Wallet journal", "Token memory", "Scan history", "Memory controls"])

        with tab_wallets:
            st.markdown('<div class="monitor-section-head">Best remembered wallets</div>', unsafe_allow_html=True)
            st.markdown('<div class="monitor-help">Use this like your shortlist. The best signal is not one lucky hit; it is a wallet appearing early around multiple filtered tokens over time.</div>', unsafe_allow_html=True)
            render_monitor_wallet_memory_cards(wallet_memory_df, limit=10)

            with st.expander("Full wallet memory table", expanded=False):
                if wallet_memory_df is not None and not wallet_memory_df.empty:
                    table_cols = ["Wallet", "Trust Score", "Label", "Appearances", "Early Tokens", "Hits", "Swaps", "Best Alpha Wallet Score", "Saved?", "Last Seen", "Next Action"]
                    st.dataframe(wallet_memory_df[[col for col in table_cols if col in wallet_memory_df.columns]].head(50), width="stretch", hide_index=True)
                else:
                    st.info("No wallet memory yet.")

        with tab_journal:
            st.markdown('<div class="monitor-section-head">Wallet journal</div>', unsafe_allow_html=True)
            st.markdown('<div class="monitor-help">This is the opinion layer for wallets. It turns repeated appearances into a thesis: trust, reason, next action, and evidence history.</div>', unsafe_allow_html=True)
            render_wallet_documentation_cards(limit=10, key_scope="market_monitor_journal")
            with st.expander("Wallet journal timeline", expanded=False):
                render_wallet_documentation_timeline(limit=40)
            with st.expander("Full wallet documentation table", expanded=False):
                doc_df = wallet_documentation_dataframe()
                if doc_df is not None and not doc_df.empty:
                    cols = ["Wallet", "Verdict", "Best Trust Score", "Last Trust Score", "Appearances", "Early Tokens", "Good Signals", "Bad Signals", "Tags", "Tokens", "Next Action", "Reason", "Saved?", "Last Seen"]
                    st.dataframe(doc_df[[col for col in cols if col in doc_df.columns]].head(80), width="stretch", hide_index=True)
                else:
                    st.info("No wallet documentation yet.")

        with tab_tokens:
            st.markdown('<div class="monitor-section-head">Token memory</div>', unsafe_allow_html=True)
            st.markdown('<div class="monitor-help">This shows what the monitor has seen over time. Later we can use these outcomes to punish bad wallets and reward wallets that were early before strong moves.</div>', unsafe_allow_html=True)
            render_monitor_token_memory_table(token_memory_df, limit=20)

        with tab_runs:
            st.markdown('<div class="monitor-section-head">Scan history</div>', unsafe_allow_html=True)
            runs_df = pd.DataFrame(st.session_state.get("discovery_runs", []))
            if not runs_df.empty:
                st.dataframe(runs_df.sort_values("Timestamp", ascending=False).head(30), width="stretch", hide_index=True)
            else:
                st.info("No scan runs saved yet.")
            with st.expander("Recent token snapshots", expanded=False):
                snapshots_df = pd.DataFrame(st.session_state.get("market_snapshots", []))
                if not snapshots_df.empty:
                    st.dataframe(snapshots_df.sort_values("Timestamp", ascending=False).head(50), width="stretch", hide_index=True)
                else:
                    st.info("No snapshots saved yet.")

        with tab_settings:
            st.markdown('<div class="monitor-section-head">Memory controls</div>', unsafe_allow_html=True)
            st.markdown('<div class="monitor-warning">Reset only if you want to start learning from scratch. Your normal wallet watchlist and token watchlist are not touched.</div>', unsafe_allow_html=True)
            reset_col1, reset_col2, reset_col3, reset_col4 = st.columns(4)
            with reset_col1:
                if st.button("Clear token memory", key="clear_token_memory"):
                    st.session_state.token_memory = {}
                    persist_market_memory()
                    st.success("Token memory cleared.")
            with reset_col2:
                if st.button("Clear wallet memory", key="clear_wallet_memory"):
                    st.session_state.wallet_alpha_memory = {}
                    persist_market_memory()
                    st.success("Wallet memory cleared.")
            with reset_col3:
                if st.button("Clear wallet journal", key="clear_wallet_documentation"):
                    st.session_state.wallet_documentation = {}
                    persist_market_memory()
                    st.success("Wallet journal cleared.")
            with reset_col4:
                confirm_all = st.checkbox("Confirm full monitor reset", key="confirm_market_monitor_reset")
                if st.button("Clear monitor history", disabled=not confirm_all, key="clear_monitor_history"):
                    st.session_state.market_snapshots = []
                    st.session_state.token_memory = {}
                    st.session_state.wallet_alpha_memory = {}
                    st.session_state.wallet_documentation = {}
                    st.session_state.wallet_journal_pins = []
                    save_wallet_journal_pins()
                    st.session_state.discovery_runs = []
                    persist_market_memory()
                    st.success("Market monitor memory cleared.")

    elif section == "_ai_search_disabled":
        st.title("AI Search")
        st.caption("Ask questions about wallets, trades and risk patterns.")
        st.info("AI Search is paused for now. We will add this later when the API is ready.")


    elif section == "Paper Trading":
        with safe_section("Paper Trading"):
            st.markdown('<p style="font-size:24px;font-weight:600;color:#f5f5f7;padding:28px 0 4px;">Paper Trading</p>', unsafe_allow_html=True)
            st.markdown('<p style="font-size:14px;color:#5a5b62;margin-bottom:16px;">Fake money, real prices — test wallet ideas before risking anything real.</p>', unsafe_allow_html=True)

            st.markdown(
                """
                <style>
                .paper-hero{border:1px solid rgba(45,212,191,.24);background:linear-gradient(135deg,rgba(20,184,166,.14),rgba(15,23,42,.97) 55%,rgba(59,130,246,.10));border-radius:22px;padding:18px 20px;margin-bottom:14px}
                .paper-title{color:#f8fafc;font-size:23px;font-weight:950;margin-bottom:5px}.paper-sub{color:#cbd5e1;font-size:13px;line-height:1.45;max-width:980px}
                .paper-flow{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:9px;margin-top:13px}.paper-flow div{background:rgba(255,255,255,.045);border:1px solid rgba(255,255,255,.07);border-radius:13px;padding:10px;color:#e5e7eb;font-size:12px}.paper-flow span{display:block;color:#94a3b8;font-size:10px;text-transform:uppercase;letter-spacing:.05em;margin-bottom:3px}
                .paper-note{border:1px solid rgba(56,189,248,.22);background:rgba(56,189,248,.08);border-radius:15px;padding:10px 12px;color:#bae6fd;font-size:13px;line-height:1.45;margin:8px 0 14px}
                .paper-danger{border:1px solid rgba(248,113,113,.25);background:rgba(127,29,29,.16);border-radius:15px;padding:10px 12px;color:#fecaca;font-size:13px;line-height:1.45;margin:8px 0 14px}
                .paper-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin:10px 0 14px}.paper-card{border:1px solid rgba(255,255,255,.08);background:rgba(255,255,255,.035);border-radius:16px;padding:12px 14px}.paper-card span{display:block;color:#94a3b8;font-size:11px}.paper-card b{display:block;color:#f8fafc;font-size:19px;margin-top:4px}.paper-card b.good{color:#4ade80}.paper-card b.bad{color:#f87171}
                .paper-trade-card{border:1px solid rgba(255,255,255,.09);background:linear-gradient(145deg,rgba(15,23,42,.98),rgba(30,41,59,.72));border-radius:18px;padding:13px 14px;margin-bottom:10px}.paper-trade-top{display:flex;justify-content:space-between;gap:10px}.paper-trade-name{font-size:16px;font-weight:950;color:#f8fafc}.paper-trade-sub{font-size:11px;color:#94a3b8;margin-top:2px}.paper-pill{border-radius:999px;padding:5px 8px;font-size:10px;font-weight:900}.paper-pill.open{background:rgba(34,197,94,.16);border:1px solid rgba(34,197,94,.32);color:#bbf7d0}.paper-pill.closed{background:rgba(148,163,184,.14);border:1px solid rgba(148,163,184,.24);color:#cbd5e1}
                .paper-mini{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:7px;margin:10px 0}.paper-mini div{border:1px solid rgba(255,255,255,.07);background:rgba(255,255,255,.035);border-radius:12px;padding:8px 9px}.paper-mini span{display:block;color:#94a3b8;font-size:10px;text-transform:uppercase}.paper-mini b{font-size:13px;color:#f8fafc}.paper-mini .good{color:#4ade80}.paper-mini .bad{color:#f87171}
                .paper-status-strip{display:grid;grid-template-columns:1.15fr 1fr 1fr;gap:10px;margin:0 0 15px 0}.paper-status-strip>div{border:1px solid rgba(255,255,255,.08);background:linear-gradient(145deg,rgba(15,23,42,.92),rgba(30,41,59,.52));border-radius:17px;padding:13px 15px}.paper-status-strip span{display:block;color:#94a3b8;font-size:11px;text-transform:uppercase;letter-spacing:.04em;margin-bottom:5px}.paper-status-strip b{color:#f8fafc;font-size:15px}.paper-status-strip .good{color:#4ade80}.paper-status-strip .bad{color:#f87171}.paper-status-strip .watch{color:#fbbf24}
                .paper-progress{height:9px;border-radius:999px;background:rgba(255,255,255,.08);overflow:hidden;margin:9px 0 4px}.paper-progress-fill{height:100%;border-radius:999px;background:linear-gradient(90deg,#ef4444,#f59e0b,#22c55e);box-shadow:0 0 16px rgba(34,197,94,.20)}.paper-progress-label{display:flex;justify-content:space-between;color:#94a3b8;font-size:10px}
                .paper-setup-presets{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin:12px 0}.paper-preset-card{border:1px solid rgba(45,212,191,.18);background:linear-gradient(145deg,rgba(20,184,166,.10),rgba(15,23,42,.88));border-radius:16px;padding:12px}.paper-preset-card b{color:#f8fafc;font-size:14px}.paper-preset-card span{display:block;color:#94a3b8;font-size:12px;margin-top:4px;line-height:1.35}
                .paper-manual-zone{border:1px solid rgba(56,189,248,.22);background:linear-gradient(135deg,rgba(56,189,248,.10),rgba(15,23,42,.92));border-radius:18px;padding:14px;margin:16px 0 10px}.paper-manual-zone b{color:#e0f2fe}.paper-manual-zone span{color:#94a3b8;font-size:12px}.paper-glow-buy{border:1px solid rgba(34,197,94,.35)!important;background:linear-gradient(135deg,rgba(34,197,94,.18),rgba(15,23,42,.92))!important}.paper-glow-sell{border:1px solid rgba(248,113,113,.35)!important;background:linear-gradient(135deg,rgba(248,113,113,.16),rgba(15,23,42,.92))!important}
                .paper-depth-wrap{border:1px solid rgba(45,212,191,.18);background:linear-gradient(145deg,rgba(15,23,42,.94),rgba(2,6,23,.72));border-radius:17px;padding:13px;margin:9px 0 12px}.paper-depth-title{display:flex;justify-content:space-between;gap:10px;align-items:center;color:#f8fafc;font-weight:950;margin-bottom:7px}.paper-depth-title span{color:#94a3b8;font-size:11px;font-weight:700}.paper-depth-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin:8px 0}.paper-depth-grid div{border:1px solid rgba(255,255,255,.07);background:rgba(255,255,255,.035);border-radius:13px;padding:9px 10px}.paper-depth-grid span{display:block;color:#94a3b8;font-size:10px;text-transform:uppercase}.paper-depth-grid b{color:#f8fafc;font-size:14px}.paper-depth-grid .good{color:#4ade80}.paper-depth-grid .bad{color:#f87171}.paper-depth-grid .watch{color:#fbbf24}.paper-tape{display:flex;flex-wrap:wrap;gap:7px;margin:8px 0}.paper-tape-chip{border-radius:999px;padding:7px 9px;font-size:11px;border:1px solid rgba(255,255,255,.08);background:rgba(255,255,255,.04);color:#e5e7eb}.paper-tape-chip.good{border-color:rgba(34,197,94,.28);background:rgba(34,197,94,.10);color:#bbf7d0}.paper-tape-chip.bad{border-color:rgba(248,113,113,.28);background:rgba(248,113,113,.10);color:#fecaca}.paper-tape-chip.neutral{border-color:rgba(56,189,248,.28);background:rgba(56,189,248,.09);color:#bae6fd}.paper-action-row{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px}.paper-ladder-note{color:#94a3b8;font-size:12px;line-height:1.4;margin-top:6px}.paper-trade-card .paper-note{margin-top:9px}
                .paper-safety-panel{border:1px solid rgba(251,191,36,.26);background:linear-gradient(135deg,rgba(245,158,11,.10),rgba(15,23,42,.92));border-radius:17px;padding:13px 14px;margin:12px 0;color:#fde68a;font-size:13px;line-height:1.45}.paper-safety-panel b{color:#fef3c7}.paper-safety-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin-top:9px}.paper-safety-grid div{border:1px solid rgba(255,255,255,.08);background:rgba(255,255,255,.035);border-radius:12px;padding:9px 10px}.paper-safety-grid span{display:block;color:#94a3b8;font-size:10px;text-transform:uppercase}.paper-safety-grid strong{color:#f8fafc;font-size:13px}
                .paper-action-hint{border:1px solid rgba(34,197,94,.22);background:rgba(34,197,94,.08);color:#bbf7d0;border-radius:14px;padding:10px 12px;margin:8px 0 12px;font-size:12.5px;line-height:1.45}
                .paper-impact{display:flex;justify-content:space-between;align-items:center;gap:12px;border-radius:18px;padding:12px 14px;margin:10px 0 14px;animation:paperImpactPop .55s ease-out both;box-shadow:0 14px 38px rgba(0,0,0,.22)}.paper-impact b{display:block;color:#f8fafc;font-size:14px}.paper-impact span{display:block;color:#cbd5e1;font-size:12px;margin-top:2px}.paper-impact em{color:#94a3b8;font-size:11px;white-space:nowrap}.paper-impact-soft{border:1px solid rgba(56,189,248,.24);background:linear-gradient(135deg,rgba(56,189,248,.13),rgba(15,23,42,.94))}.paper-impact-medium{border:1px solid rgba(45,212,191,.30);background:linear-gradient(135deg,rgba(20,184,166,.16),rgba(15,23,42,.94))}.paper-impact-strong{border:1px solid rgba(34,197,94,.38);background:linear-gradient(135deg,rgba(34,197,94,.22),rgba(15,23,42,.94));box-shadow:0 0 26px rgba(34,197,94,.16),0 14px 38px rgba(0,0,0,.22)}.paper-impact-danger{border:1px solid rgba(248,113,113,.38);background:linear-gradient(135deg,rgba(248,113,113,.20),rgba(15,23,42,.94));box-shadow:0 0 26px rgba(248,113,113,.12),0 14px 38px rgba(0,0,0,.22)}@keyframes paperImpactPop{0%{opacity:0;transform:translateY(8px) scale(.985);filter:saturate(.8)}45%{opacity:1;transform:translateY(-2px) scale(1.01);filter:saturate(1.25)}100%{opacity:1;transform:translateY(0) scale(1);filter:saturate(1)}}
                div.stButton > button[kind="primary"]{border-radius:999px!important;font-weight:900!important;box-shadow:0 0 22px rgba(34,197,94,.16)!important}div.stButton > button{border-radius:999px!important;font-weight:800!important;transition:all .14s ease!important;position:relative!important;overflow:hidden!important} div.stButton > button:hover{transform:translateY(-1px) scale(1.015)!important;box-shadow:0 10px 26px rgba(15,23,42,.42)!important}div.stButton > button:active{transform:translateY(1px) scale(.985)!important;filter:brightness(1.22)!important} div.stButton > button:focus:not(:active){box-shadow:0 0 0 3px rgba(45,212,191,.20),0 0 24px rgba(45,212,191,.15)!important}
                
                @media(max-width:900px){.paper-flow,.paper-grid,.paper-mini{grid-template-columns:1fr 1fr}}
                </style>
                <div class="paper-hero">
                    <div class="paper-title">Paper Trading Machine</div>
                    <div class="paper-sub">Trade with fake money on live prices. Pick Journal wallets, let the copy machine simulate entries and exits, and learn which wallet signals actually work without risking real money.</div>
                    <div class="paper-flow">
                        <div><span>1</span><b>Pick wallets</b></div>
                        <div><span>2</span><b>Copy machine trades</b></div>
                        <div><span>3</span><b>Live P/L moves</b></div>
                        <div><span>4</span><b>Keep what works</b></div>
                    </div>
                </div>
                <div class="paper-danger"><b>Important:</b> no real wallet is connected, no private keys are used and no real trades are placed. This is a live-price simulator for learning and testing.</div>
                """,
                unsafe_allow_html=True
            )

            render_paper_impact()

            settings = st.session_state.get("paper_settings", {})
            if settings.get("enabled"):
                # P/L should feel live. Bot copying still respects its own cooldown below.
                refresh_ms = max(safe_int(settings.get("live_refresh_seconds", 1), 1), 1) * 1000
                st_autorefresh(interval=refresh_ms, key="paper_trading_autorefresh")

            if settings.get("enabled") and settings.get("auto_copy"):
                cooldown = max(safe_int(settings.get("copy_cooldown_minutes", 10), 10), 1) * 60
                last_ts = safe_float(settings.get("last_bot_ts", 0), 0)
                if time.time() - last_ts >= cooldown:
                    paper_bot_scan_once()

            summary = paper_wallet_summary()
            pnl_class = "good" if summary["Total P/L"] >= 0 else "bad"
            open_pnl_class = "good" if summary["Open P/L"] >= 0 else "bad"
            max_active_trades = max(safe_int(settings.get("max_open_trades", 5), 5), 1)
            active_trades = safe_int(summary.get("Open Trades", 0), 0)
            active_load_pct = min(max((active_trades / max_active_trades) * 100, 0), 100)
            total_profit_pct = (safe_float(summary.get("Total P/L", 0), 0) / max(safe_float(summary.get("Start", 1000), 1000), 1)) * 100
            if total_profit_pct > 3:
                account_mood = "Healthy test run"
                account_mood_class = "good"
            elif total_profit_pct < -3:
                account_mood = "Needs review"
                account_mood_class = "bad"
            else:
                account_mood = "Still learning"
                account_mood_class = "watch"
            copy_state = "Auto-copy is ON" if settings.get("auto_copy") else "Manual mode"
            refresh_read = f"prices every {safe_int(settings.get('live_refresh_seconds', 1), 1)} sec"

            st.markdown(
                f"""
                <div class="paper-grid">
                    <div class="paper-card"><span>Fake account value</span><b>{format_usd(summary["Equity"])}</b></div>
                    <div class="paper-card"><span>Total fake profit</span><b class="{pnl_class}">{format_signed_usd(summary["Total P/L"])}</b></div>
                    <div class="paper-card"><span>Live open profit</span><b class="{open_pnl_class}">{format_signed_usd(summary["Open P/L"])}</b></div>
                    <div class="paper-card"><span>Win rate</span><b>{summary["Win Rate"]:.0f}%</b></div>
                    <div class="paper-card"><span>Free play money</span><b>{format_usd(summary["Cash"])}</b></div>
                    <div class="paper-card"><span>Money in trades</span><b>{format_usd(summary["Open Value"])}</b></div>
                    <div class="paper-card"><span>Active trades</span><b>{summary["Open Trades"]}</b></div>
                    <div class="paper-card"><span>Finished trades</span><b>{summary["Closed Trades"]}</b></div>
                </div>
                """,
                unsafe_allow_html=True
            )

            st.markdown(
                f"""
                <div class="paper-status-strip">
                    <div><span>Account mood</span><b class="{account_mood_class}">{account_mood}</b><div class="paper-progress"><div class="paper-progress-fill" style="width:{min(max(total_profit_pct + 50, 0), 100):.0f}%"></div></div><div class="paper-progress-label"><em>drawdown</em><em>{total_profit_pct:+.1f}%</em><em>profit</em></div></div>
                    <div><span>Trade load</span><b>{active_trades}/{max_active_trades} active trades</b><div class="paper-progress"><div class="paper-progress-fill" style="width:{active_load_pct:.0f}%"></div></div><div class="paper-progress-label"><em>calm</em><em>busy</em></div></div>
                    <div><span>Mode</span><b>{copy_state}</b><br><small style="color:#94a3b8">Live P/L updates from {refresh_read}. Signal checks use your selected speed.</small></div>
                </div>
                """,
                unsafe_allow_html=True
            )

            if safe_int(settings.get("live_refresh_seconds", 1), 1) <= 1 and active_trades >= 5:
                st.warning("Turbo refresh is active with many fake trades. For smoother testing, use 2–5 sec refresh or reduce active trades.")

            if st.session_state.get("paper_message"):
                st.success(st.session_state.paper_message)
                st.session_state.paper_message = ""

            setup_tab, open_tab, closed_tab, bot_tab, own_tab, log_tab = st.tabs(["Control room", "Active fake trades", "Results", "Copy setup", "My wallets", "Trade diary"])

            with setup_tab:
                st.markdown('<div class="paper-note"><b>Simple setup:</b> start with $1,000 play money, small trade sizes, and only a few active trades. Let the copy machine follow your best Journal wallets first.</div>', unsafe_allow_html=True)
                st.markdown('<div class="paper-setup-presets"><div class="paper-preset-card"><b>Safe learner</b><span>Small buys, slower checks, best for first tests.</span></div><div class="paper-preset-card"><b>Balanced copy</b><span>Good default for testing selected Journal wallets.</span></div><div class="paper-preset-card"><b>Fast scalp test</b><span>Faster checks and tighter exits for active sessions.</span></div></div>', unsafe_allow_html=True)
                p1, p2, p3 = st.columns(3)
                with p1:
                    if st.button("Use safe learner", key="paper_preset_safe"):
                        st.session_state.paper_settings.update({"trade_size": 10, "max_open_trades": 3, "stop_loss_pct": -20, "take_profit_pct": 30, "copy_cooldown_minutes": 10, "live_refresh_seconds": 2, "auto_copy": False})
                        save_paper_settings()
                        st.rerun()
                with p2:
                    if st.button("Use balanced copy", type="primary", key="paper_preset_balanced"):
                        st.session_state.paper_settings.update({"trade_size": 25, "max_open_trades": 5, "stop_loss_pct": -25, "take_profit_pct": 50, "copy_cooldown_minutes": 5, "live_refresh_seconds": 1, "auto_copy": True})
                        save_paper_settings()
                        st.rerun()
                with p3:
                    if st.button("Use fast scalp test", key="paper_preset_fast"):
                        st.session_state.paper_settings.update({"trade_size": 15, "max_open_trades": 4, "stop_loss_pct": -15, "take_profit_pct": 25, "copy_cooldown_minutes": 2, "live_refresh_seconds": 1, "auto_copy": True})
                        save_paper_settings()
                        st.rerun()
                c1, c2, c3, c4, c5 = st.columns(5)
                with c1:
                    enabled = st.toggle("Turn simulator on", value=bool(settings.get("enabled", False)), key="paper_enabled_toggle")
                with c2:
                    auto_copy = st.toggle("Auto-copy signals", value=bool(settings.get("auto_copy", False)), key="paper_auto_copy_toggle")
                with c3:
                    source = st.selectbox("Wallet group", ["Journal pinned only", "Strong thesis only", "Strong + Promising"], index=["Journal pinned only", "Strong thesis only", "Strong + Promising"].index(settings.get("source", "Journal pinned only")) if settings.get("source", "Journal pinned only") in ["Journal pinned only", "Strong thesis only", "Strong + Promising"] else 0, key="paper_source_select")
                with c4:
                    cooldown = st.selectbox("Signal check speed", [2, 5, 10, 15, 30], index=[2,5,10,15,30].index(safe_int(settings.get("copy_cooldown_minutes", 10), 10)) if safe_int(settings.get("copy_cooldown_minutes", 10), 10) in [2,5,10,15,30] else 2, format_func=lambda x: f"Every {x} min", key="paper_cooldown_select")
                with c5:
                    live_refresh_options = [1, 2, 5, 10, 15, 30, 60]
                    current_live_refresh = safe_int(settings.get("live_refresh_seconds", 1), 1)
                    live_refresh = st.selectbox("Live P/L refresh", live_refresh_options, index=live_refresh_options.index(current_live_refresh) if current_live_refresh in live_refresh_options else 0, format_func=lambda x: f"Every {x} sec", key="paper_live_refresh_select")

                r1, r2, r3, r4 = st.columns(4)
                with r1:
                    fake_balance = st.number_input("Play money start", min_value=100.0, max_value=100000.0, value=float(settings.get("fake_balance_start", 1000)), step=100.0, key="paper_start_balance_input")
                with r2:
                    trade_size = st.number_input("Play money per copied trade", min_value=1.0, max_value=10000.0, value=float(settings.get("trade_size", 25)), step=5.0, key="paper_trade_size_input")
                with r3:
                    max_open = st.number_input("Max active trades", min_value=1, max_value=50, value=int(settings.get("max_open_trades", 5)), step=1, key="paper_max_open_input")
                with r4:
                    take_profit = st.number_input("Take Profit %", min_value=5.0, max_value=1000.0, value=float(settings.get("take_profit_pct", 50)), step=5.0, key="paper_tp_input")

                s1, s2, s3 = st.columns([0.25, 0.25, 0.50])
                with s1:
                    stop_loss = st.number_input("Stop Loss %", min_value=-95.0, max_value=-1.0, value=float(settings.get("stop_loss_pct", -25)), step=1.0, key="paper_sl_input")
                with s2:
                    max_trade_pct = st.number_input("Max trade size %", min_value=1.0, max_value=50.0, value=float(settings.get("max_trade_size_pct", 10)), step=1.0, key="paper_max_trade_pct_input")
                with s3:
                    min_liquidity = st.number_input("Min liquidity USD", min_value=0.0, max_value=1000000.0, value=float(settings.get("min_liquidity_usd", 1000)), step=500.0, key="paper_min_liquidity_input")

                st.markdown(
                    f"""
                    <div class="paper-safety-panel"><b>Safety rails:</b> Paper Trading stays fake, but these limits train safer habits before real money ever exists.
                      <div class="paper-safety-grid">
                        <div><span>Per-trade cap</span><strong>{max_trade_pct:.0f}% of play money</strong></div>
                        <div><span>Liquidity filter</span><strong>{format_usd(min_liquidity)} minimum</strong></div>
                        <div><span>Risk rules</span><strong>Stop Loss + Take Profit active</strong></div>
                      </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                save_col, hint_col = st.columns([0.25, 0.75])
                with save_col:
                    if st.button("Save trading setup", type="primary", key="paper_save_setup"):
                        first_time = not st.session_state.paper_settings.get("enabled")
                        st.session_state.paper_settings.update({
                            "enabled": bool(enabled),
                            "auto_copy": bool(auto_copy),
                            "source": source,
                            "fake_balance_start": safe_float(fake_balance, 1000),
                            "trade_size": safe_float(trade_size, 25),
                            "max_open_trades": safe_int(max_open, 5),
                            "stop_loss_pct": safe_float(stop_loss, -25),
                            "take_profit_pct": safe_float(take_profit, 50),
                            "max_trade_size_pct": safe_float(max_trade_pct, 10),
                            "min_liquidity_usd": safe_float(min_liquidity, 1000),
                            "copy_cooldown_minutes": safe_int(cooldown, 10),
                            "live_refresh_seconds": safe_int(live_refresh, 1),
                            "selected_source_wallets": settings.get("selected_source_wallets", []),
                        })
                        if first_time or safe_float(st.session_state.paper_settings.get("cash", 0)) <= 0 and not st.session_state.get("paper_trades"):
                            st.session_state.paper_settings["cash"] = safe_float(fake_balance, 1000)
                        save_paper_settings()
                        paper_set_impact("setup", "Trading setup saved", "Stop Loss, Take Profit and safety limits are now active.", level="soft")
                        st.success("Trading setup saved.")
                        st.rerun()
                with hint_col:
                    st.caption("Changing play money does not reset old trades. Use reset only when you want a clean new test. Keep trade size small while testing new wallets.")

                with st.expander("Reset practice account", expanded=False):
                    st.warning("Safety check: this clears fake trades and the trade diary. It does not touch real wallets because this app does not trade real funds.")
                    reset_balance = st.number_input("New play money balance", min_value=100.0, max_value=100000.0, value=float(settings.get("fake_balance_start", 1000)), step=100.0, key="paper_reset_balance")
                    confirm_reset = st.text_input("Type RESET to confirm", key="paper_reset_confirm_text")
                    if st.button("Reset practice account", key="paper_reset_wallet", disabled=(confirm_reset.strip().upper() != "RESET")):
                        reset_paper_wallet(reset_balance)
                        paper_set_impact("reset", "Practice account reset", f"New fake balance: {format_usd(reset_balance)}. Previous paper trades were cleared.", level="danger")
                        st.rerun()

                st.markdown('<div class="paper-manual-zone"><b>Place a fake trade</b><br><span>Paste a token address, choose your play-money buy size, then watch live P/L, pressure and the trade tape move.</span></div>', unsafe_allow_html=True)
                m1, m2, m3 = st.columns([0.55, 0.20, 0.25])
                with m1:
                    manual_mint = st.text_input("Token address", placeholder="Paste Solana token address", key="paper_manual_mint")
                with m2:
                    manual_size = st.number_input("Play-money buy size", min_value=1.0, max_value=10000.0, value=float(settings.get("trade_size", 25)), step=5.0, key="paper_manual_size")
                with m3:
                    st.write("")
                    if st.button("Place trade", type="primary", key="paper_manual_buy"):
                        ok, msg = paper_open_trade(manual_mint, reason="Manual paper trade", size=manual_size, mode="Manual")
                        paper_set_impact(
                            "place_trade" if ok else "place_trade_failed",
                            "Trade placed" if ok else "Trade not placed",
                            msg,
                            level="strong" if ok else "danger",
                        )
                        (st.success if ok else st.error)(msg)
                        st.rerun()

            with open_tab:
                updated, closed = paper_update_open_trades(apply_rules=True)
                open_trades = paper_open_trades()
                if not open_trades:
                    st.info("No live fake trades yet. Place a trade or let the copy machine follow selected Journal wallets.")
                for idx, trade in enumerate(open_trades):
                    pnl = safe_float(trade.get("P/L", 0))
                    pnl_pct = safe_float(trade.get("P/L %", 0))
                    pnl_cls = "good" if pnl >= 0 else "bad"
                    tp_pct = max(safe_float(settings.get("take_profit_pct", 50), 50), 1)
                    sl_pct = safe_float(settings.get("stop_loss_pct", -25), -25)
                    denom = max(tp_pct - sl_pct, 1)
                    progress_pct = min(max(((pnl_pct - sl_pct) / denom) * 100, 0), 100)
                    trade_read = "Moving well" if pnl_pct >= tp_pct * 0.5 else "Needs patience" if pnl_pct >= 0 else "Under water"
                    trade_card_extra_cls = "paper-glow-buy" if pnl >= 0 else "paper-glow-sell"
                    token = str(trade.get("Token", "Token"))
                    mint = str(trade.get("Token Mint", ""))
                    source_name = str(trade.get("Source Name", "Manual"))
                    st.markdown(
                        f"""
                        <div class="paper-trade-card {trade_card_extra_cls}">
                            <div class="paper-trade-top">
                                <div><div class="paper-trade-name">{token}</div><div class="paper-trade-sub">{short_address(mint)} · copied from {source_name}</div></div>
                                <div class="paper-pill open">OPEN</div>
                            </div>
                            <div class="paper-mini">
                                <div><span>Entry</span><b>{format_usd(trade.get("Entry Value", 0))}</b></div>
                                <div><span>Current</span><b>{format_usd(trade.get("Current Value", 0))}</b></div>
                                <div><span>Live P/L</span><b class="{pnl_cls}">{format_signed_usd(pnl)}</b></div>
                                <div><span>Live P/L %</span><b class="{pnl_cls}">{pnl_pct:.1f}%</b></div>
                                <div><span>Live price</span><b>{format_usd(trade.get("Current Price", 0))}</b></div>
                                <div><span>Updated</span><b>{str(trade.get("Last Updated", "-"))[-8:-3]}</b></div>
                            </div>
                            <div class="paper-progress"><div class="paper-progress-fill" style="width:{progress_pct:.0f}%"></div></div>
                            <div class="paper-progress-label"><em>Stop Loss {sl_pct:.0f}%</em><em>{trade_read}</em><em>Take Profit +{tp_pct:.0f}%</em></div>
                            <div class="paper-note"><b>Why opened:</b> {trade.get("Reason", "-")}<br><b>Beginner read:</b> Watch if the copied wallet exits. Green is not proof until the exit is visible.</div>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )
                    st.markdown('<div class="paper-action-hint"><b>Trade controls:</b> Lock result closes this fake trade at the current live price. Stop Loss and Take Profit can still close it automatically.</div>', unsafe_allow_html=True)
                    b1, b2 = st.columns([0.18, 0.82])
                    with b1:
                        if st.button("Lock result", key=f"paper_close_{trade.get('ID', idx)}"):
                            ok, msg = paper_close_trade_by_id(trade.get("ID", ""), reason="Manual paper close")
                            paper_set_impact(
                                "lock_result" if ok else "lock_failed",
                                "Result locked" if ok else "Result not locked",
                                msg,
                                level="medium" if ok else "danger",
                            )
                            (st.success if ok else st.error)(msg)
                            st.rerun()
                    with st.expander("Live P/L trail", expanded=False):
                        paper_trade_live_pnl_chart(trade, key_suffix=str(trade.get("ID", idx)))
                        st.caption("This updates from live DexScreener prices while the fake trade is open.")
                    with st.expander("Live Market Depth", expanded=False):
                        render_paper_trade_market_depth(trade, key_suffix=str(trade.get("ID", idx)))
                    with b2:
                        if trade.get("Token URL"):
                            st.caption(f"DexScreener: {trade.get('Token URL')}")

            with closed_tab:
                closed_trades = sorted(paper_closed_trades(), key=lambda t: str(t.get("Exit Time", t.get("Entry Time", ""))), reverse=True)
                if not closed_trades:
                    st.info("No finished trades yet. Results appear after a fake trade is closed. This is where you learn which copied wallets actually helped.")
                else:
                    rows = []
                    for trade in closed_trades:
                        rows.append({
                            "Token": trade.get("Token", "-"),
                            "Source": trade.get("Source Name", "-"),
                            "Entry": trade.get("Entry Time", "-"),
                            "Exit": trade.get("Exit Time", "-"),
                            "Entry Value": format_usd(trade.get("Entry Value", 0)),
                            "Exit Value": format_usd(trade.get("Exit Value", trade.get("Current Value", 0))),
                            "P/L": format_signed_usd(trade.get("P/L", 0)),
                            "P/L %": f"{safe_float(trade.get('P/L %', 0)):.1f}%",
                            "Reason": trade.get("Exit Reason", "-"),
                            "Lesson": "Good signal" if safe_float(trade.get("P/L", 0)) > 0 else "Needs review",
                        })
                    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

            with bot_tab:
                st.markdown('<div class="paper-note"><b>Copy machine:</b> choose the exact Journal wallets you want to test. The copy machine reads their latest buy/sell evidence, opens fake positions on buy signals, and closes on sell signals or your risk rules.</div>', unsafe_allow_html=True)
                all_candidate_wallets = paper_candidate_source_wallets(settings.get("source", "Journal pinned only"))
                option_labels = {
                    item.get("Wallet", ""): f"{item.get('Name', '-')} | {item.get('Verdict', '-')} | Trust {safe_float(item.get('Trust', 0)):.0f}/100"
                    for item in all_candidate_wallets
                    if item.get("Wallet")
                }
                current_selected = [w for w in settings.get("selected_source_wallets", []) if w in option_labels] if isinstance(settings.get("selected_source_wallets", []), list) else []
                selected_wallets = st.multiselect(
                    "Wallets to copy",
                    options=list(option_labels.keys()),
                    default=current_selected,
                    format_func=lambda wallet: option_labels.get(wallet, compact_address(wallet)),
                    help="Leave empty to copy every wallet from the selected source group.",
                    key="paper_selected_source_wallets"
                )
                if selected_wallets != current_selected:
                    settings["selected_source_wallets"] = selected_wallets
                    st.session_state.paper_settings = settings
                    save_paper_settings()

                source_wallets = paper_source_wallets()
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Available wallet ideas", len(all_candidate_wallets))
                c2.metric("Selected wallets", len(source_wallets))
                c3.metric("Journal pinned", wallet_journal_pinned_count())
                c4.metric("Active fake trades", len(paper_open_trades()))

                if st.button("Check copy signals now", type="primary", key="paper_run_copier_once"):
                    opened, closed, skipped = paper_bot_scan_once()
                    paper_set_impact("copy_check", "Copy signals checked", f"{opened} opened, {closed} closed, {skipped} skipped.", level="medium")
                    st.success(f"Copy check done: {opened} opened, {closed} closed, {skipped} skipped.")
                    st.rerun()

                if not source_wallets:
                    st.info("No wallets selected yet. Go to Wallet Journal and use Journal pin on wallets you want to test.")
                else:
                    st.markdown("**Wallets currently being copied**")
                    source_rows = []
                    for source in source_wallets:
                        signal = latest_copyable_wallet_signal(source.get("Wallet", ""))
                        source_rows.append({
                            "Wallet": source.get("Name", "-"),
                            "Verdict": source.get("Verdict", "-"),
                            "Trust": f"{safe_float(source.get('Trust', 0)):.0f}/100",
                            "Latest signal": signal.get("Trade Side", "-") if signal else "-",
                            "Token": token_label(signal.get("Trade Token Mint", "")) if signal else "-",
                            "Signal time": signal.get("Timestamp", "-") if signal else "-",
                        })
                    st.dataframe(pd.DataFrame(source_rows), width="stretch", hide_index=True)

            with own_tab:
                st.markdown('<div class="paper-note"><b>My wallets:</b> add your own public wallet addresses read-only. No private key, no seed phrase. Later we can compare your behavior against the fake bot and Journal wallets.</div>', unsafe_allow_html=True)
                w1, w2, w3 = st.columns([0.25, 0.45, 0.30])
                with w1:
                    my_name = st.text_input("Name", placeholder="My main wallet", key="my_wallet_name_input")
                with w2:
                    my_address = st.text_input("Public wallet address", placeholder="Paste public Solana wallet address", key="my_wallet_address_input")
                with w3:
                    my_note = st.text_input("Note", placeholder="optional", key="my_wallet_note_input")
                if st.button("Add read-only wallet", key="add_my_readonly_wallet"):
                    address = str(my_address or "").strip()
                    if not address or len(address) < 32:
                        st.error("Please paste a valid public wallet address.")
                    else:
                        st.session_state.my_wallets.append({
                            "Name": my_name.strip() or wallet_auto_name(address, prefix="My Wallet"),
                            "Address": address,
                            "Note": my_note.strip(),
                            "Added": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")
                        })
                        save_my_wallets()
                        st.success("Read-only wallet saved.")
                        st.rerun()

                wallets = st.session_state.get("my_wallets", [])
                if not wallets:
                    st.info("No read-only wallets saved yet.")
                else:
                    for idx, wallet in enumerate(wallets):
                        st.markdown(f"**{wallet.get('Name', 'My Wallet')}**  \n`{wallet.get('Address', '')}`  \n{wallet.get('Note', '')}")
                        c1, c2 = st.columns([0.18, 0.82])
                        with c1:
                            if st.button("Remove", key=f"remove_my_wallet_{idx}_{hashlib.sha1(str(wallet.get('Address','')).encode()).hexdigest()[:8]}"):
                                st.session_state.my_wallets.pop(idx)
                                save_my_wallets()
                                st.rerun()

            with log_tab:
                events = list(reversed(st.session_state.get("paper_events", [])[-100:]))
                if not events:
                    st.info("No learning log yet.")
                else:
                    st.dataframe(pd.DataFrame(events), width="stretch", hide_index=True)

    elif section == "Wallet Journal":
        with safe_section("Wallet Journal"):
            st.markdown('<p style="font-size:24px;font-weight:600;color:#f5f5f7;padding:28px 0 4px;">Wallet Journal</p>', unsafe_allow_html=True)
            st.markdown('<p style="font-size:14px;color:#5a5b62;margin-bottom:16px;">Your scouting book — wallets with evidence, verdicts and next steps.</p>', unsafe_allow_html=True)

            st.markdown(
                """
                <style>
                .journal-hero{border:1px solid rgba(99,102,241,.24);background:linear-gradient(135deg,rgba(99,102,241,.14),rgba(15,23,42,.96) 55%,rgba(34,197,94,.08));border-radius:22px;padding:18px 20px;margin-bottom:14px}.journal-title{color:#f8fafc;font-size:22px;font-weight:950;margin-bottom:5px}.journal-sub{color:#cbd5e1;font-size:13px;line-height:1.45;max-width:920px}.journal-steps{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:9px;margin-top:13px}.journal-steps div{background:rgba(255,255,255,.045);border:1px solid rgba(255,255,255,.07);border-radius:13px;padding:10px;color:#e5e7eb;font-size:12px}.journal-steps span{display:block;color:#94a3b8;font-size:10px;text-transform:uppercase;letter-spacing:.05em;margin-bottom:3px}.journal-mode-note{border:1px solid rgba(56,189,248,.22);background:rgba(56,189,248,.08);border-radius:15px;padding:10px 12px;color:#bae6fd;font-size:13px;line-height:1.45;margin:8px 0 14px}@media(max-width:900px){.journal-steps{grid-template-columns:1fr}}
                </style>
                <div class="journal-hero">
                    <div class="journal-title">Wallet Journal: turn wallet chaos into simple decisions</div>
                    <div class="journal-sub">This is the marketing-friendly beginner area: every wallet gets a simple opinion, proof status, history, estimated P/L and a next action. Users should not need to understand raw wallet addresses or random plus/minus movement.</div>
                    <div class="journal-steps">
                        <div><span>1</span><b>Market finds wallets</b></div>
                        <div><span>2</span><b>Journal saves evidence</b></div>
                        <div><span>3</span><b>History/P&L builds</b></div>
                        <div><span>4</span><b>You decide: watch or skip</b></div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )

            doc_df = wallet_documentation_dataframe()
            total_docs = 0 if doc_df is None or doc_df.empty else len(doc_df)
            strong_docs = 0 if doc_df is None or doc_df.empty or "Verdict" not in doc_df.columns else int((doc_df["Verdict"].astype(str) == "Strong thesis").sum())
            promising_docs = 0 if doc_df is None or doc_df.empty or "Verdict" not in doc_df.columns else int((doc_df["Verdict"].astype(str) == "Promising").sum())
            pinned_docs = wallet_journal_pinned_count()
            live_pinned = len([item for item in st.session_state.get("watchlist_wallets", []) if wallet_is_pinned(item)])

            k1, k2, k3, k4, k5 = st.columns(5)
            k1.metric("Journal wallets", total_docs)
            k2.metric("Journal pinned", pinned_docs)
            k3.metric("Strong thesis", strong_docs)
            k4.metric("Promising", promising_docs)
            k5.metric("Live pinned", live_pinned)

            render_journal_refresh_controls()

            tab_pinned, tab_best, tab_all, tab_timeline = st.tabs(["My ideas", "Best wallets", "All notes", "Evidence timeline"])

            with tab_pinned:
                st.markdown('<div class="journal-mode-note"><b>Use this as your main daily list.</b> Journal pin means: keep this wallet as an idea and let the Journal build proof over time.</div>', unsafe_allow_html=True)
                render_wallet_documentation_cards(limit=20, only_pinned=True, key_scope="journal_pinned")

            with tab_best:
                filter_col, limit_col = st.columns([0.6, 0.4])
                with filter_col:
                    verdict_filter = st.multiselect(
                        "Show verdicts",
                        ["Strong thesis", "Promising", "Needs proof", "Risky / noisy", "Low proof"],
                        default=["Strong thesis", "Promising", "Needs proof"],
                        key="wallet_journal_verdict_filter"
                    )
                with limit_col:
                    journal_limit = st.selectbox("Cards", [6, 10, 20, 40], index=1, key="wallet_journal_limit")
                if doc_df is not None and not doc_df.empty and verdict_filter:
                    keep_wallets = set(doc_df[doc_df["Verdict"].isin(verdict_filter)]["Full Wallet"].astype(str).tolist()) if "Full Wallet" in doc_df.columns else set()
                    original_docs = st.session_state.get("wallet_documentation", {})
                    filtered_docs = {k: v for k, v in original_docs.items() if str(k) in keep_wallets}
                    old_docs = st.session_state.wallet_documentation
                    st.session_state.wallet_documentation = filtered_docs
                    render_wallet_documentation_cards(limit=journal_limit, key_scope="journal_best_filtered")
                    st.session_state.wallet_documentation = old_docs
                else:
                    render_wallet_documentation_cards(limit=journal_limit, key_scope="journal_best_all")

            with tab_all:
                st.markdown('<div class="journal-mode-note">This is the full evidence board. Use it when you want to compare everything, not just the best ideas.</div>', unsafe_allow_html=True)
                render_wallet_documentation_cards(limit=40, key_scope="journal_all_notes")
                with st.expander("Full table", expanded=False):
                    doc_df = wallet_documentation_dataframe()
                    if doc_df is not None and not doc_df.empty:
                        pins = set(st.session_state.get("wallet_journal_pins", []))
                        if "Full Wallet" in doc_df.columns:
                            doc_df["Journal Pinned"] = doc_df["Full Wallet"].astype(str).isin(pins)
                        cols = ["Wallet", "Journal Pinned", "Verdict", "Best Trust Score", "Last Trust Score", "Appearances", "Early Tokens", "Good Signals", "Bad Signals", "Tags", "Tokens", "Next Action", "Reason", "Saved?", "First Seen", "Last Seen"]
                        st.dataframe(doc_df[[col for col in cols if col in doc_df.columns]], width="stretch", hide_index=True)
                    else:
                        st.info("No wallet documentation yet. Run Market Monitor scans first.")

            with tab_timeline:
                st.markdown('<div class="journal-mode-note"><b>Evidence timeline:</b> this shows why the opinion changed over time.</div>', unsafe_allow_html=True)
                render_wallet_documentation_timeline(limit=100)

    elif section == "Settings":
        st.title("Settings")
        st.caption("Use this page when something feels wrong: API keys, data files, watchlist size and app state are checked here.")

        def secret_status(secret_name):
            try:
                value = st.secrets.get(secret_name, "")
                return bool(str(value).strip())
            except Exception:
                return False

        helius_ok = secret_status("HELIUS_API_KEY")
        solscan_ok = secret_status("SOLSCAN_API_KEY")
        openai_ok = secret_status("OPENAI_API_KEY")

        wallet_history_points = sum(len(points) for points in st.session_state.get("wallet_history", {}).values())
        pinned_wallets_count = len([item for item in st.session_state.watchlist_wallets if wallet_is_pinned(item)])
        auto_settings = st.session_state.get("auto_wallet_settings", {})

        st.markdown(
            f"""<div class="settings-grid">
                <div class="settings-card"><span>Helius API</span><strong>{"Connected" if helius_ok else "Missing"}</strong></div>
                <div class="settings-card"><span>Solscan API</span><strong>{"Connected" if solscan_ok else "Missing"}</strong></div>
                <div class="settings-card"><span>OpenAI API</span><strong>{"Connected" if openai_ok else "Missing / optional"}</strong></div>
                <div class="settings-card"><span>Wallets saved</span><strong>{len(st.session_state.watchlist_wallets)}</strong></div>
                <div class="settings-card"><span>Pinned wallets</span><strong>{pinned_wallets_count}</strong></div>
                <div class="settings-card"><span>Tokens saved</span><strong>{len(st.session_state.watchlist_tokens)}</strong></div>
                <div class="settings-card"><span>Wallet chart points</span><strong>{wallet_history_points}</strong></div>
                <div class="settings-card"><span>Auto Scan</span><strong>{"ON" if auto_settings.get("enabled") else "OFF"}</strong></div>
                <div class="settings-card"><span>Auto interval</span><strong>{auto_settings.get("interval", 60)}s</strong></div>
            </div>""",
            unsafe_allow_html=True
        )

        with st.expander("What these settings mean", expanded=True):
            st.markdown(
                """
                - **Helius API** powers wallet transaction checks and wallet discovery.  
                - **Solscan API** is used for token transfer discovery.  
                - **OpenAI API** is optional while AI Search is paused.  
                - **Pinned wallets** are your high-priority wallets. They are checked first and build the most useful charts.  
                - **Auto Scan** is now saved in `data/auto_wallet_settings.json`, so it survives app restarts.  
                - **Wallet chart points** grow when you click Check, Check All or leave Auto Scan running.  
                - If charts look empty, pin wallets and let Auto Scan run for several checks.
                - If old blue SWAP markers make the charts confusing, use **Chart cleanup** below and start fresh.
                """
            )

        st.markdown('<div class="section-title">Data files</div>', unsafe_allow_html=True)
        st.code(
            f"""{WALLET_WATCHLIST_FILE}\n{TOKEN_WATCHLIST_FILE}\n{WALLET_HISTORY_FILE}\n{AUTO_WALLET_SETTINGS_FILE}\n{RECENT_TOKEN_MINTS_FILE}\n{RECENT_WALLETS_FILE}""",
            language="text"
        )

        c1, c2, c3 = st.columns([0.24, 0.24, 0.52])
        with c1:
            if st.button("Clear UI messages", key="settings_clear_messages"):
                st.session_state.watchlist_message = ""
                st.session_state.token_watchlist_message = ""
                st.success("Messages cleared.")
        with c2:
            if st.button("Reload saved data", key="settings_reload_data"):
                st.session_state.watchlist_wallets = load_json_list(WALLET_WATCHLIST_FILE)
                st.session_state.watchlist_tokens = load_json_list(TOKEN_WATCHLIST_FILE)
                st.session_state.wallet_history = load_json_dict(WALLET_HISTORY_FILE)
                st.session_state.auto_wallet_settings = load_json_dict(AUTO_WALLET_SETTINGS_FILE) or {"enabled": False, "interval": 60, "scope": "Pinned first, then all"}
                st.success("Saved data reloaded.")

        with st.expander("Chart cleanup", expanded=False):
            st.markdown(
                """
                Use this when old blue **SWAP unclear** points make the charts hard to read.  
                This does **not** remove wallets, pins or token watchlist entries. It only cleans saved chart history.
                """
            )

            cleanup_col1, cleanup_col2, cleanup_col3 = st.columns(3)

            with cleanup_col1:
                st.markdown("**Keep pinned charts only**")
                st.caption("Best when you only care about your priority wallets.")
                if st.button("Clear unpinned history", key="settings_clear_unpinned_history"):
                    clear_unpinned_wallet_history()
                    st.success(st.session_state.watchlist_message)

            with cleanup_col2:
                st.markdown("**Remove unclear SWAP spam**")
                st.caption("Keeps BUY / SELL / ROTATE points, removes old unclear SWAP points.")
                if st.button("Clean unclear SWAPs", key="settings_clear_unclear_swaps"):
                    clear_unclear_swap_history_points()
                    st.success(st.session_state.watchlist_message)

            with cleanup_col3:
                st.markdown("**Fresh chart start**")
                st.caption("Keeps watchlists, clears all wallet charts.")
                confirm_clear_all = st.checkbox("I want to clear all chart history", key="settings_confirm_clear_all_history")
                if st.button("Clear all chart history", key="settings_clear_all_wallet_history", disabled=not confirm_clear_all):
                    clear_all_wallet_history()
                    st.success(st.session_state.watchlist_message)

        with st.expander("Wallet names", expanded=False):
            st.markdown(
                """
                Rename wallets here so nobody has to remember addresses.  
                The address stays saved in the background; only the human label changes.
                """
            )
            if not st.session_state.watchlist_wallets:
                st.info("No saved wallets yet.")
            else:
                for idx, item in enumerate(st.session_state.watchlist_wallets):
                    full_wallet = str(item.get("Full Wallet", item.get("Wallet", "")) or "").strip()
                    if not full_wallet:
                        continue
                    current_name = wallet_watchlist_item_name(item)
                    current_note = wallet_note(full_wallet)
                    st.markdown(
                        f'<div class="name-manager-row"><div class="name-manager-title">{current_name}</div><div class="name-manager-sub">{short_address(full_wallet)} · {"Pinned" if wallet_is_pinned(item) else "Watchlist"}</div></div>',
                        unsafe_allow_html=True
                    )
                    ncol, note_col, save_col = st.columns([0.34, 0.46, 0.20])
                    with ncol:
                        new_name = st.text_input("Wallet name", value=current_name, key=f"settings_wallet_name_{idx}_{full_wallet}", label_visibility="collapsed")
                    with note_col:
                        new_note = st.text_input("Wallet note", value=current_note, key=f"settings_wallet_note_{idx}_{full_wallet}", label_visibility="collapsed", placeholder="optional note")
                    with save_col:
                        if st.button("Save name", key=f"settings_save_wallet_name_{idx}_{full_wallet}"):
                            set_wallet_label(full_wallet, new_name, new_note)
                            st.session_state.watchlist_wallets[idx]["Wallet"] = new_name
                            st.session_state.watchlist_wallets[idx]["Name"] = new_name
                            st.session_state.watchlist_wallets[idx]["Wallet Alias"] = new_name
                            save_json_list(WALLET_WATCHLIST_FILE, st.session_state.watchlist_wallets)
                            st.success("Wallet name saved.")

        with st.expander("Danger zone", expanded=False):
            st.warning("Full reset is intentionally not automatic. Use Chart cleanup above first. Full wallet/token reset can be added later with a stronger confirmation flow.")

