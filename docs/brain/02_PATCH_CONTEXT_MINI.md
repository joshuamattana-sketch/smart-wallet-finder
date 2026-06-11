# Patch Context Mini

## Current architecture

- `app.py` should stay thin and should not be edited unless explicitly requested.
- UI files should only be edited in UI-specific patches.
- API routes should only be edited in API-specific patches.
- `services/` contains pure Python engines and business logic.
- `tests/` contains deterministic local tests.
- `docs/brain/` contains project context and terminal commands.
- Supabase SQL lives in `supabase/`.
- Discord logic is split into formatter, sender, and filter services.
- Signal flow: heatmap history -> wall events -> persistence features -> setup classifier -> signal builder -> signal journal -> alerts.
- Whale flow starts with whale event detection, then formatter/filter/sender later.
- Whale live pipeline: Binance aggTrade WS -> normalize -> detect_whale_events -> filter -> (Discord | JSONL journal | Supabase whale_events).
- Whale read path: website /api/whale-alerts reads Supabase -> local JSONL journal -> mock alerts (server-side, 3-tier fallback).
- Futures/leverage context (LM64 series, planned): Binance futures aggTrade + funding/OI poller + force-order stream feed `MarketContext` (funding_rate, oi_change_pct, derived leverage_heat) into existing whale events without claiming individual-account leverage. See `docs/brain/LM64_FUTURES_WHALE_SOURCE_DISCOVERY.md`.
- Landing page redesign (LM67 series, planned): signature hero "The Lumora Field" — a 2.5D SVG/CSS market pressure visualization (price path, liquidity bands, whale pulses, futures drift, sweep zones, Current Read badge) replacing the generic hero; new sections on Panel/lm-* design language. See `docs/brain/LM67_LANDING_PAGE_DISCOVERY.md`.

## Completed patches

- LM45 heatmap history
- LM46 wall events
- LM47 wall persistence features
- LM48 setup classifier
- LM49 signal builder
- LM50 signal journal
- LM51A discord formatter
- LM51B discord webhook sender
- LM51C discord alert filter
- LM52A whale alert engine
- LM63A whale source discovery (recommendation only)
- LM63B Binance aggTrade collector
- LM63C whale live smoke + Discord pipeline
- LM63D per-symbol whale thresholds
- LM63E local JSONL whale event journal
- LM63F whale feed API + website fallback to mock
- LM63G Supabase whale_events schema (+ unique constraint fix)
- LM63H Supabase writer + smoke --target wiring
- LM63I website Supabase tier (Supabase -> journal -> mock)
- LM63J whale worker mode (--forever, --heartbeat-interval, env config)
- LM63K whale worker deployment docs
- LM64A futures whale source discovery (recommendation only)
- LM64B Binance Futures aggTrade connector (--market spot|futures; no schema change)
- LM67A landing page discovery — The Lumora Field (plan only, no frontend code)

## Rules

- No UI unless requested.
- No API route changes unless requested.
- No secrets.
- No commit/push.
- Tests must be local and deterministic.
- No network in tests.
- Keep patches small.
- Edit only listed files.

## Standard test commands

```bash
python -m pytest <target_test>
python -m compileall services tests