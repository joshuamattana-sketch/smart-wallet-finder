# LM67 Landing Page Discovery — The Lumora Field

Status: discovery only (LM67A). No frontend code in this patch.
Scope: plan a premium, memorable Lumora landing page around a signature hero
concept called **The Lumora Field** — a 2.5D market pressure visualization —
instead of a generic AI orb/blob or fake dashboard screenshot.

---

## 1. Current landing page analysis

File: `lumora-web/app/page.tsx` (route `/`, outside the `(app)` group).

Current structure, top to bottom:

| # | Section | Notes |
|---|---|---|
| 1 | Sticky nav | Logo + "Private Beta" badge + "Open App" button |
| 2 | Hero | Centered text, `bg-hero-glow` gradient, generic headline "Market Intelligence for Serious Crypto Traders", two CTAs (Open App / Join Discord with placeholder `#` href) |
| 3 | "Context not noise" strip | Single GlassCard with positioning copy |
| 4 | Feature cards | 6 GlassCards (Terminal, Liquidity Maps, Whale Alerts, AI Market Bias, Smart Alerts, Paper Trading) with Live/Beta/Q3/Q4 badges |
| 5 | Beta CTA | GlassCard with purple glow, "Request Beta Access" button (no action wired) |
| 6 | Roadmap | 4 GlassCards from `roadmapItems` mock data |
| 7 | Footer | Logo + "Not financial advice" disclaimer |

Problems:

- **No visual proof.** The hero is pure text + a gradient glow. Nothing shows
  what Lumora actually *sees*. A liquidity intelligence product with no
  liquidity visual on the landing page undersells the core differentiator.
- **Old design language.** Uses `GlassCard`, `lumora-*` tokens, neon glow
  (`shadow-neon-purple`, `text-neon-purple`), `rounded-xl` — all explicitly on
  the "What to Avoid" list in `lumora-web/docs/DESIGN_DIRECTION.md`. The app
  pages (dashboard, liquidity map, whale alerts) have migrated to `Panel` /
  `StatusBadge` / `lm-*` tokens; the landing page has not.
- **Generic claims.** "Everything you need. Nothing you don't." could be any
  SaaS. Nothing communicates the unique reads Lumora produces (Current Read,
  sweep zones, whale impact, futures pressure).
- **Decorative badges** ("Q3 2026", "Q4 2026") that DESIGN_DIRECTION bans.
- **Dead CTAs.** Discord links are `#`, Request Beta Access does nothing.
- **Tone drift.** "Serious Crypto Traders" in neon purple reads hypey, not
  institutional.

What's worth keeping: the section *skeleton* (hero → positioning → features →
CTA → roadmap → footer) is sound; the demo-data honesty line is good and should
survive; the footer disclaimer is correct.

---

## 2. The Lumora Field — signature hero concept

### What it is

A 2.5D **market pressure visualization** rendered behind/beside the hero copy.
Not a decorative object — a stylized, labeled read of a market the way Lumora
sees it. Think **market MRI / liquidity radar / pressure scanner**: a slightly
tilted plane (subtle perspective, ~8–12° skew, no real 3D camera) on which the
market's hidden structure is drawn in the app's own visual language.

### Anatomy (layers, back to front)

1. **Field plane** — near-black surface (`lm-bg` → `lm-surface` gradient at
   ~3% delta), faint horizontal price-grid lines in `lm-border`. The tilt is
   what makes it "2.5D": the plane recedes slightly toward the top-right.
2. **Liquidity bands** — soft horizontal bands above price (ask side, red
   `lm-ask` at low opacity) and below price (bid side, green `lm-bid`).
   Band thickness/opacity = resting size. 2–3 bands per side, one clearly
   dominant per side. These echo the Liquidity Map heatmap without cloning it.
3. **Sweep risk zones** — one or two hatched/dashed amber (`lm-warning`)
   horizontal strips below the bid bands, labeled `SWEEP RISK`. Matches the
   SWP zone concept already in the liquidity map page.
4. **Price path** — a single cyan (`lm-cyan`) polyline traversing the field
   left → right, the brightest element. It interacts with the bands: stalls
   under the ask band, bounces off the bid band, dips toward the sweep zone.
   A small cyan dot marks "now" at the right edge.
5. **Whale impact pulses** — at 2–3 points on the price path, a brief
   expanding ring (one ring, ~1.2s, then gone — radar ping, not fireworks)
   with a micro-label like `WHALE BUY · $4.2M`. Green ring for buy, red for
   sell.
6. **Futures pressure drift** — a sparse field of small directional ticks or
   short streaks (`lm-muted` → semantic color at the extremes) drifting slowly
   above the plane, indicating which way leverage is leaning. This is the
   "atmosphere" of the field — barely-there motion, never confetti.
7. **Current Read badge** — a small `Panel`-styled card pinned to the top-right
   of the field: `READ: LONG · SCORE 72 · RISK MEDIUM`, mirroring the real
   Current Read card on the dashboard. This is the punchline: the field is
   what Lumora sees, the badge is what Lumora says.

### Optional: 30-second market replay

The field can run a scripted ~30s loop ("market replay") with 4–5 captioned
beats. A thin timeline strip under the field shows progress and the current
caption, e.g.:

1. `0:00 — Price approaches a $38M ask wall.` (price drifts up toward red band)
2. `0:07 — Whale sell hits: $4.2M market order.` (red pulse, price rejects)
3. `0:14 — Bids absorb. Wall at 67,350 holds twice.` (green band brightens)
4. `0:21 — Futures pressure flips long. Sweep risk fades.` (drift reverses, amber zone dims)
5. `0:28 — Read updates: LONG · score 72.` (Current Read badge ticks over, loop restarts)

Replay can ship in a later patch; the static-but-breathing field is the MVP.

### Feel targets / anti-targets

| Should feel like | Must NOT feel like |
|---|---|
| Market MRI | Generic AI orb |
| Liquidity radar | Random 3D blob |
| Pressure scanner | Crypto casino animation |
| Trading desk intelligence layer | Playful game UI |
| Calm, institutional, high-trust | Fake TradingView clone |

Design-language rules (from DESIGN_DIRECTION.md, applied to the field):

- Monochrome base; color only where it means something (bid/ask/warning/price).
- No glow shadows, no glass, no gradient overlays on cards.
- Motion is functional: pulses mark events, drift marks pressure. Nothing
  moves just to be pretty. At rest the field should look like an instrument,
  not a screensaver.
- Labels in JetBrains Mono, uppercase, tracking-wide — same micro-label style
  as the app (`text-[9px] uppercase tracking-widest`).

---

## 3. Landing page message

Primary message: **See the pressure behind the price.**

Supporting message: **Lumora makes hidden liquidity, whale flow, and futures
pressure readable** — one terminal that turns raw market structure into a
plain-language read.

Tone: institutional, calm, sharp, high-trust. No rocket emojis, no "10x",
no countdown timers, no neon hype.

---

## 4. Proposed landing page structure

1. **Hero — The Lumora Field.** Headline + subheadline left (or above on
   mobile), the Field filling the right ~55% / full-bleed behind on desktop.
   Two CTAs. One honest status badge (`Private Beta`). Demo-data note kept.
2. **30-second Market Replay strip.** Directly under the hero: the replay
   timeline with captions (or, in MVP, a static 5-step annotated strip of the
   same beats — "what just happened in the field, in words").
3. **What Lumora reads.** Three columns mapping field layers to product
   capability: Liquidity (bands/walls), Whale flow (pulses), Futures pressure
   (drift). Each links the visual metaphor to the real app feature.
4. **Market Read examples.** 2–3 real-looking Current Read cards (reusing the
   app's actual `Panel` + `StatusBadge` components) showing bias, score, risk,
   reason, action — proof that the output is a sentence, not a dashboard dump.
5. **Whale / Futures / Liquidity intelligence.** Deeper feature trio with
   small real-component previews (whale alert row, funding/OI context line,
   heatmap thumbnail). Only claim what exists or is clearly labeled as
   planned — no decorative quarter badges.
6. **Alerts that explain risk.** One section showing a Discord/webhook alert
   that includes the *why* (reason + risk + invalidation), contrasted with a
   bare "BTC moved" notification.
7. **Roadmap / early access.** Compact, honest roadmap (shipped / in progress
   / planned — status words, not quarters) + beta access form or Discord.
8. **Final CTA + footer.** "Open the terminal" / "Request beta access" +
   disclaimer footer.

Design system: build all new sections with `Panel` / `StatusBadge` / `lm-*`
tokens. This patch series should also be the moment the landing page leaves
GlassCard behind (per the migration note in DESIGN_DIRECTION.md).

---

## 5. Implementation options compared

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **CSS/SVG 2.5D** (SVG layers + CSS transforms/keyframes, inline in a client component) | Zero dependencies, ~0 bundle cost, SSR-renderable so hero paints instantly, trivially themeable with `lm-*` CSS vars, `prefers-reduced-motion` is one media query, crisp at any DPI | Complex particle effects awkward; everything must be authored as declarative layers | ✅ **Recommended MVP** |
| **Canvas 2D** (custom rAF loop) | Smooth particle drift and many pulses cheap; full control | Client-only (blank until JS hydrates), needs devicePixelRatio + resize handling, harder to keep on-brand, more code to maintain | Good **later upgrade** for the drift layer + replay only |
| **Three.js / R3F** | True 3D depth, impressive | 150–600 KB+ to the critical route, GPU cost on laptops/mobile, biggest "generic 3D blob" trap, fights the flat institutional aesthetic | ❌ Rejected |
| **Animated terminal replay** (typewriter log of events) | Very cheap, on-brand for a terminal product | Not visual enough to be the signature; doesn't show *spatial* pressure | Use as the **reduced-motion / mobile-fallback text track**, not the hero |

### Recommended MVP

**SVG + CSS, hybrid-ready.** One client component `LumoraField.tsx`:

- SVG `<svg viewBox>` with grouped layers (plane, bands, sweep zones, price
  path, pulse rings, drift ticks); the 2.5D tilt is a single CSS
  `transform: perspective(...) rotateX(...)` on a wrapper (with a
  non-transformed fallback).
- Price path draws once via `stroke-dashoffset` keyframes; pulses are scaled
  circles on a staggered `animation-delay` loop; drift is 10–15 ticks on slow
  `translate` keyframes. All pausable by class toggle.
- Current Read badge is plain HTML positioned over the SVG — real `Panel` +
  `StatusBadge` components, so it is pixel-identical to the app.
- The data behind the field is a small hardcoded "scene" object (band prices,
  pulse times, path points) — making a later Canvas/replay upgrade a renderer
  swap, not a redesign.
- Replay (LM67C+) adds a scene timeline that retimes the same layers; only
  then consider Canvas for the drift layer if SVG perf isn't enough.

This is the safest option that still reads as unique: nobody else's hero is a
labeled liquidity field in the product's own design language.

### Performance rules

- **No heavy initial bundle.** No three.js, no animation libs (no framer-motion
  for the field; CSS keyframes only). The field component should add ≲10 KB.
- **`prefers-reduced-motion`:** all keyframes gated behind
  `@media (prefers-reduced-motion: no-preference)`. Reduced-motion users get
  the full static field (bands, path, labels, badge) — it must look complete
  frozen, with the terminal-style caption strip carrying the narrative.
- **Mobile fallback:** below `sm`, drop the tilt (flat SVG), reduce drift
  ticks to ~5, stack hero copy above the field, cap field height (~320px).
  Optionally swap the replay strip for the static 5-line text version.
- **Graceful degradation:** the SVG renders server-side; with JS disabled the
  hero still shows the full static field. No layout shift: the field has a
  fixed aspect-ratio box.
- Pause all animation when the hero scrolls out of view
  (`IntersectionObserver`) and on `visibilitychange`.

---

## 6. Copy suggestions

### Headline (pick one)

1. **See the pressure behind the price.** ← primary recommendation
2. The market has structure. Lumora makes it readable.
3. Hidden liquidity, whale flow, futures pressure — on one screen.

### Subheadline

> Lumora is a liquidity intelligence terminal. It reads order-book walls,
> whale flow and futures positioning in real time — and turns them into a
> plain-language market read you can act on.

Honesty line (keep, restyled): `Demo data shown — live integrations rolling out in beta.`

### CTA labels

- Primary: **Open the terminal** (→ `/dashboard`)
- Secondary: **Request beta access**
- Tertiary (community): **Join the Discord**
- Avoid: "Start winning", "Get the edge", "Don't miss out".

### Feature cards (section 3 — What Lumora reads)

- **Liquidity structure** — "Where size is actually resting. Walls, gaps and
  demand zones mapped over time — before price gets there."
- **Whale flow** — "Large prints as they hit the tape, with side, size and
  market impact — filtered so only meaningful flow gets through."
- **Futures pressure** — "Funding, open interest and forced liquidations as
  context: which way is leverage leaning, and how crowded is it."

### Lumora Field micro-labels (on the visualization)

`ASK WALL $38M` · `BID SUPPORT $26M` · `SWEEP RISK` · `WHALE BUY · $4.2M` ·
`WHALE SELL · $7.1M` · `FUTURES PRESSURE → LONG` · `LIQUIDITY GAP` ·
`READ: LONG · SCORE 72 · RISK MEDIUM` · `NOW`

### 30-second replay text track

See §2 "Optional: 30-second market replay" — the five captions there are the
canonical copy. Style: timestamped, factual, one clause of consequence each.

### Section 6 (Alerts) example alert copy

> **LUMORA ALERT · BTCUSDT · HIGH RISK**
> Whale sell $7.1M into thinning bids. Major support 67,000 within 0.6%.
> Sweep risk elevated — invalidation below 66,800.

---

## 7. What not to claim

- **No guaranteed profits / performance.** Never "win", "profit", "edge that
  pays", win-rates, or implied returns. Lumora describes market structure;
  it does not promise outcomes.
- **No exact leverage claims.** We infer aggregate pressure (funding, OI,
  liquidations) — never claim to know any account's leverage or position
  (consistent with the LM64 futures-context constraint).
- **No financial advice.** Keep the footer disclaimer; add it near the beta
  CTA too. All reads are informational context, not recommendations — even
  though the UI uses words like LONG/SHORT, the marketing copy must frame
  them as "reads", not "calls to trade".
- **No fake liveness.** Anything mock/demo is labeled. No fabricated user
  counts, testimonials, or "$X billion tracked" stats we can't back.
- **No exchange partnership implications.** "Data from Binance, Bybit, OKX"
  (sources), never "partnered with".

---

## 8. Recommended next patch

**LM67B_LANDING_PAGE_THE_LUMORA_FIELD** — implement the hero:

- New `lumora-web/components/landing/LumoraField.tsx` (SVG/CSS field, scene
  data object, reduced-motion + mobile + visibility handling).
- Rewrite the hero section of `lumora-web/app/page.tsx` to the new copy and
  layout, on `Panel`/`lm-*` design language.
- No replay yet; static-but-breathing field + Current Read badge.

Likely follow-ups: LM67C (30s replay strip + timeline), LM67D (remaining
sections migrated off GlassCard: reads/features/alerts/roadmap/CTA),
LM67E (beta access form wiring + real Discord link).
