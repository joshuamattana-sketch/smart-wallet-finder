# AI CONTEXT
_Read this first before touching any file._

---

## Product Vision

**Smart Wallet Finder** is evolving into a two-tier intelligence terminal for crypto traders:

### Tier 1 — Pro Trading Terminal (Main Product)
A professional-grade terminal for liquid markets (BTC, ETH, SOL, HYPE and others).

Core loop: **Raw Data → Analysis → Signal → Reason / Risk / Action**

Features:
- Live orderbook metrics (bid/ask depth, imbalance, absorption)
- Market structure analysis (HH/HL/LH/LL, break of structure, order blocks)
- Pro Setup Scores (confluence of structure + momentum + volume)
- Command Center: live alerts, one-click paper trade from signal
- Multi-exchange: Binance, Bybit, OKX as data sources

### Tier 2 — Solana Meme Alpha (Beta / Experimental)
The existing Solana smart wallet and token discovery system. Remains fully functional as a beta feature set.

Features:
- Smart Wallet scanning and scoring via Helius + Solscan
- Token Finder: early buyer discovery, DexScreener momentum
- Wallet Journal, Watchlist, Paper Trading simulation
- Copy button system, discovery cards, wallet detail pages

---

## Current State (as of Foundation Pack)

The app is a single-file Streamlit app (`app.py`, ~13k lines). It works but has no module separation. The Foundation Pack introduces:
- Project rules and architecture documentation
- Core helper modules (formatting, validation, security, constants)
- A clear roadmap for phased refactoring

**Nothing is broken. We are adding structure around the working app.**

---

## Target Folder Structure

```
app.py                        (routing only — current monolith being phased out)
PROJECT_RULES.md
AI_CONTEXT.md
ROADMAP.md
CHANGELOG.md
.env.example

core/
  constants.py                ✅ done
  formatting.py               ✅ done
  validators.py               ✅ done
  security.py                 ✅ done

ui/                           (Phase 3)
  watchlist.py
  smart_wallets.py
  paper_trading.py
  token_finder.py
  today.py
  components/
    wallet_card.py
    chart.py
    copy_button.py

services/                     (Phase 2)
  wallet_scorer.py
  signal_engine.py
  token_analyzer.py
  paper_engine.py
  pattern_engine.py
  pro/
    orderbook.py
    market_structure.py
    setup_score.py

connectors/                   (Phase 2)
  helius.py
  solscan.py
  dexscreener.py
  binance.py
  bybit.py

storage/                      (Phase 1 → 2)
  supabase_client.py
  local_storage.py

auth/                         (Phase 4)
  access.py
  session.py
```

---

## Signal Philosophy

Every signal must have:
1. **Signal level** — what to do (STRONG_BUY / BUY / WATCH / AVOID / STRONG_SELL)
2. **Reason** — why in plain English (max 2 sentences)
3. **Risk level** — how dangerous this is (LOW / MEDIUM / HIGH / EXTREME)
4. **Confidence** — 0–100 score based on data quality
5. **Action hint** — the single clearest next step for the user

No signal without a reason. No reason without data.

---

## Key Rules for AI Sessions

- Always check if `elif section == "Smart Wallets"` exists before patching `app.py`.
- Always run `ast.parse()` before writing output.
- The Smart Wallets section must be inserted **before** `elif section == "Market Dashboard"`.
- Use `main_navigation` not `section_override` for navigation.
- Copy buttons use `copy_btn_html()` from the top of `app.py`.
- Chart function is `render_smart_wallet_chart()` — verify it exists before calling.
- Never use `·` (U+00B7) inside Python f-strings — causes SyntaxError.
- Never use emoji inside HTML strings rendered by Streamlit.
- Always use triple-single-quote f-strings for HTML blocks: `f'''...'''`
