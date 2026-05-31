# CHANGELOG
_Smart Wallet Finder / Pro Trading Terminal_

Format: `[version] YYYY-MM-DD — description`

---

## [0.9.0] 2026-05-31 — Foundation Pack

### Added
- `PROJECT_RULES.md` — architecture rules, security rules, vibe-coding rules, module separation reference
- `AI_CONTEXT.md` — product vision, current state, target structure, AI session guidelines
- `ROADMAP.md` — 6-phase roadmap from Foundation to Beta Access
- `CHANGELOG.md` — this file
- `.env.example` — secrets template with all required keys, no real values
- `core/constants.py` — SUPPORTED_CHAINS, MARKET_TYPES, DEFAULT_PRO_MARKETS, FEATURE_FLAGS, PLAN_IDS, SIGNAL_LEVELS, RISK_LEVELS
- `core/formatting.py` — safe_float, safe_int, compact_address, format_usd, format_pct, format_number
- `core/validators.py` — is_valid_solana_address, is_valid_evm_address, normalize_chain, normalize_symbol, validate_market_type, sanitize_user_note
- `core/security.py` — html_escape, safe_text, safe_label, mask_secret

### Changed
- Nothing. No existing files modified.

### Fixed
- Nothing. Foundation-only release.

### Notes
- This pack establishes the project structure without touching the working app.
- All core helpers are pure Python with no external dependencies.
- Next milestone: Phase 1 storage extraction (supabase_client.py, local_storage.py).

---

## [0.8.x] 2026-05-31 — Paper Trading Redesign

### Changed
- Paper Trading section completely rewritten: 4 tabs (Active / Closed / Place trade / Settings)
- Active trade cards: profit glow animation, near-SL pulse animation, P/L flash every 3s
- Place trade tab: live DexScreener price fetch, balloons on trade placement
- Settings tab: minimal — balance, size, stop/target, max trades
- Copy staging area when arriving from wallet "Paper trade" button

### Fixed
- Wallet candidate "Open" button now routes correctly to Smart Wallets detail view
- Copy button now copies full address (not truncated)
- Analyze Token now navigates to Token Finder with token banner

---

## [0.7.x] 2026-05-31 — Smart Wallets + Chart Engine

### Added
- `render_smart_wallet_chart()` — Vega-Lite chart: score line + volume bars + BUY/SELL markers + plain-English timeline
- Smart Wallets section: Scan / Discover / Recent tabs
- Wallet Detail page: score stats, buys/sells, verdict, chart, collapsible transactions, actions
- `copy_btn_html()` global helper — copy button with toast notification

### Fixed
- `render_wallet_history_chart()` replaced by smart chart wrapper
- Token Finder auto-load from Analyze Token button
- Open wallet routing from Journal, Watchlist, and discovery cards

---

## [0.6.x] 2026-05-31 — Watchlist Card Redesign

### Changed
- Watchlist wallet cards: full outer card wrapping header + deltas + hint + buttons + chart
- Status badges: HOT / UP / DOWN / FLAT with colored borders
- Chart expander moved into card footer

---

## [0.5.x] 2026-05-30 — Copy Button System

### Added
- Global `window._copyAddr` JavaScript — clipboard copy with toast notification
- Copy buttons on wallet addresses, token mints, discovery cards, transaction list

---

## [0.4.x] 2026-05-30 — Discovery Engine

### Changed
- Solscan discovery: sort order `asc` (earliest buyers first)
- Early rank bonus scoring: earlier buyers get score boost
- Discovery cards: grid layout with score, rank, verdict badge, copy button

---

## [0.1.0 — 0.3.x] 2026-05-28 to 2026-05-29 — Initial Build

### Added
- Streamlit app with sidebar navigation (Today, Token Finder, Smart Wallets, Wallet Journal, Watchlist, Paper Trading, Settings)
- Supabase integration for persistent state
- Helius API integration for wallet transaction history
- Solscan API integration for token transfers
- DexScreener integration for token prices and momentum
- Wallet scoring engine (get_wallet_signal, summarize_wallet_activity)
- Paper Trading simulation with fake money
- Wallet Journal with notes and verdicts
- Auto Scan for watchlist wallets
- GitHub + Streamlit Cloud auto-deploy pipeline
