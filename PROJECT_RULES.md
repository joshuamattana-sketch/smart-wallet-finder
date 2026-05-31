# PROJECT RULES
_Smart Wallet Finder / Pro Trading Terminal_
_Version: 1.0 — Foundation Pack_

---

## 1. Architecture Rules

### Module Responsibilities

| Module | Responsibility | May import from |
|--------|---------------|-----------------|
| `app.py` | Routing only. Section dispatch. No business logic. | ui, services, core, auth |
| `ui/` | Rendering only. Streamlit calls. No API calls. | core, services |
| `services/` | Analysis, scoring, signal generation. Pure Python. | core, connectors |
| `connectors/` | External data fetching only. One source per file. | core |
| `core/` | Shared helpers, models, constants. Zero dependencies. | nothing |
| `storage/` | Read/write persistence. Supabase + local JSON. | core |
| `auth/` | Access control, session management. | core |

### Hard Rules

- `app.py` contains **no** business logic. It routes. Period.
- `ui/` files call **no** external APIs directly.
- `connectors/` files contain **no** UI code.
- `services/` files contain **no** Streamlit imports.
- `core/` files contain **no** Streamlit imports and **no** network calls.
- Cross-layer imports go downward only: `app → ui → services → connectors → core`.

---

## 2. Security Rules

- No real API keys in any committed file. Use `.env` or Streamlit Secrets only.
- All user input must pass through `core/security.py` before rendering as HTML.
- All wallet addresses must be validated via `core/validators.py` before API calls.
- No `eval()`, no `exec()`, no `__import__()` with dynamic strings.
- HTML rendered via `unsafe_allow_html=True` must use `html_escape()` on all user-controlled values.
- Secrets must be masked in logs via `mask_secret()`.
- No silent `except pass` anywhere. Log or re-raise.
- Rate-limit all external API calls in connectors. Never call in a tight loop.

---

## 3. Vibe-Coding Rules

- **Build small, test early.** A 50-line file that works beats a 500-line file that almost works.
- **Name things like a human.** `score_wallet()` not `process_data_v2()`.
- **Every function has one job.** If the docstring needs "and", split the function.
- **No dead code.** Remove commented-out blocks before committing.
- **No magic numbers.** Use `core/constants.py`. `SIGNAL_LEVELS["priority"]` not `75`.
- **No print() in production paths.** Use proper logging or Streamlit notifications.
- **Patch scripts are temporary.** Once a patch is applied, clean it up into proper structure.
- **Every PR/commit has a CHANGELOG entry.**
- **UI state lives in `st.session_state` only.** Never pass it through function arguments as a side effect.

---

## 4. Module Separation Reference

```
app.py                    → section router only
ui/
  watchlist.py            → Watchlist page render
  smart_wallets.py        → Smart Wallets page render
  paper_trading.py        → Paper Trading page render
  token_finder.py         → Token Finder page render
  today.py                → Today page render
  components/
    wallet_card.py        → reusable wallet card
    chart.py              → reusable chart components
    copy_button.py        → clipboard copy button
services/
  wallet_scorer.py        → wallet scoring logic
  signal_engine.py        → buy/sell signal generation
  token_analyzer.py       → token momentum + risk analysis
  paper_engine.py         → paper trading simulation
  pattern_engine.py       → early buyer pattern detection
connectors/
  helius.py               → Helius API only
  solscan.py              → Solscan API only
  dexscreener.py          → DexScreener API only
  binance.py              → Binance API only (Pro)
  bybit.py                → Bybit API only (Pro)
core/
  constants.py            → all shared constants
  formatting.py           → number/address formatters
  validators.py           → input validation
  security.py             → sanitization + masking
storage/
  supabase_client.py      → Supabase connection
  local_storage.py        → JSON file read/write
auth/
  access.py               → plan/feature gating
  session.py              → login, session state
```

---

## 5. Error Handling Rules

- Never: `except Exception: pass`
- Never: `except Exception: return None` without logging
- Always: log the exception context (function name, input summary)
- Prefer: return typed Result objects `{"ok": False, "error": "reason"}`
- UI layer: catch errors from services and show user-friendly messages
- Connector layer: always return `(data, error)` tuple

---

## 6. Commit Rules

- Every commit touches **one concern**. Not "misc fixes".
- Format: `type(scope): short description`
  - `feat(wallet): add copy button to candidate cards`
  - `fix(paper): route to correct section after trade`
  - `refactor(core): extract formatting helpers`
  - `docs: update ROADMAP phase 2`
- Update `CHANGELOG.md` with every commit that affects behavior.
