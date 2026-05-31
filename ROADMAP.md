# ROADMAP
_Smart Wallet Finder / Pro Trading Terminal_

---

## Phase 1 — Foundation (Current)
**Goal:** Stable base. Rules, structure, safety. Zero regressions.

- [x] PROJECT_RULES.md — architecture + security + vibe rules
- [x] AI_CONTEXT.md — product vision + AI session guidelines
- [x] ROADMAP.md — this file
- [x] CHANGELOG.md — version history
- [x] .env.example — secrets template
- [x] core/constants.py — all shared constants
- [x] core/formatting.py — number + address formatters
- [x] core/validators.py — input validation
- [x] core/security.py — HTML escape + secret masking
- [ ] storage/supabase_client.py — extract Supabase logic from app.py
- [ ] storage/local_storage.py — extract JSON file logic from app.py
- [ ] auth/session.py — extract login logic from app.py
- [ ] Fix: Smart Wallets section persistent in app.py (stop losing on re-upload)
- [ ] Fix: Copy button reliable across all sections

---

## Phase 2 — Pro Models + Data Connectors
**Goal:** Clean service layer. Real data from exchanges.

- [ ] connectors/helius.py — extract Helius calls from app.py
- [ ] connectors/solscan.py — extract Solscan calls from app.py
- [ ] connectors/dexscreener.py — extract DexScreener calls from app.py
- [ ] connectors/binance.py — Binance REST + WebSocket orderbook
- [ ] connectors/bybit.py — Bybit REST + WebSocket orderbook
- [ ] services/wallet_scorer.py — extract wallet scoring logic
- [ ] services/token_analyzer.py — DexScreener momentum scoring
- [ ] services/pro/orderbook.py — bid/ask depth, imbalance ratio, absorption detection
- [ ] services/pro/market_structure.py — HH/HL/LH/LL, BOS, order block detection
- [ ] All connectors return `(data, error)` tuple, never raise to caller

---

## Phase 3 — Live Terminal UI
**Goal:** Pro terminal that traders actually want to use.

- [ ] ui/components/wallet_card.py — standalone wallet card component
- [ ] ui/components/chart.py — smart chart component (score + BUY/SELL markers)
- [ ] ui/components/copy_button.py — global copy button with toast
- [ ] ui/smart_wallets.py — Smart Wallets page extracted from app.py
- [ ] ui/watchlist.py — Watchlist page extracted from app.py
- [ ] ui/token_finder.py — Token Finder page extracted from app.py
- [ ] ui/paper_trading.py — Paper Trading page extracted from app.py
- [ ] ui/today.py — Today page: live watchlist alerts + action cards
- [ ] Pro Terminal view: live orderbook depth chart (Vega-Lite)
- [ ] Pro Terminal view: market structure overlay on price chart
- [ ] Pro Terminal view: Setup Score panel with confluence breakdown

---

## Phase 4 — Pro Setup Score + Command Center
**Goal:** The core Pro product. Actionable signals with full reasoning.

- [ ] services/pro/setup_score.py — confluence scorer (structure + momentum + volume + orderbook)
- [ ] Setup Score card: Signal / Score / Reason / Risk / Action
- [ ] Command Center: live feed of top setup scores across DEFAULT_PRO_MARKETS
- [ ] One-click: place paper trade from any signal card
- [ ] Alert system: Supabase-backed signal history + Telegram push
- [ ] auth/access.py — plan gating (Free / Pro / Alpha)
- [ ] FEATURE_FLAGS runtime toggle without redeploy

---

## Phase 5 — Meme Alpha Beta Integration
**Goal:** Clean separation of Pro and Alpha. Both work independently.

- [ ] Alpha section clearly marked as "BETA / Experimental"
- [ ] Pattern Engine: accumulate DexScreener snapshots, early rank tracking
- [ ] Wallet confirmation signal: wallet buys + token momentum = alert
- [ ] Token risk scoring: liquidity depth, age, holder concentration
- [ ] Journal improvements: copy buttons, modernized card design
- [ ] Multi-user isolation: per-user Supabase namespace

---

## Phase 6 — Beta Access + Demo Mode
**Goal:** Friends and early users can safely access the product.

- [ ] Demo mode: read-only, fake data, no API keys needed
- [ ] Public beta: Streamlit Sharing set to Public with login wall
- [ ] Rate limiting: per-user scan limits (Supabase tracked)
- [ ] Admin panel: usage overview, rate limit control, user feedback
- [ ] Feedback button on every page → Supabase events table
- [ ] Basic onboarding flow: first-time user sees 3-step guide

---

## Backlog (No Phase Assigned)
- Telegram alerts when pinned wallet becomes active
- Birdeye / Pump.fun as social signal proxy
- P/L tracking per wallet over time (needs token price history)
- Mobile-optimized layout
- Export to CSV: watchlist, trade history, signals
