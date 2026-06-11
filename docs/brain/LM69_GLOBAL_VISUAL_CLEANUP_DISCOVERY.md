# LM69 Global Visual Cleanup — Discovery

Status: discovery only (LM69A). No frontend code in this patch.
Scope: an art-directed cleanup plan for the Lumora app shell and all five app
pages, to be executed before more features land. Goal feeling: a **dark
market intelligence instrument** — sharp, premium, focused, live, calm under
pressure. Not a generated dashboard, not a casino, not dry enterprise.

The product substance is real now (live candles, heatmap, whale feed, reads).
The UI must stop competing with it.

---

## 1. Current UI problems (grounded in the actual code)

### 1.1 Everything is the same panel
Every page is a vertical stack of identical `Panel flush` boxes — same
border, same surface, same radius, same weight. On Liquidity Map a user sees,
top to bottom: controls panel, note banner, heatmap panel, depth panel,
preview section, 4 zone cards, 5 summary cards, API Status panel, Data Status
panel — **eleven near-identical bordered surfaces**. Nothing tells the eye
what matters. Border is currently free; it should be earned.

### 1.2 Badge soup and status duplication
- Liquidity Map shows connection state in at least four places: header badges
  (up to 3), the API Status panel (13 key/value pairs), the Data Status
  panel, and the canvas corner label. Terminal repeats Live/Stale in its
  header *and* KPI strip.
- Dashboard's Current Read header can show 4 chips at once (quality + status
  + stale + fallback); whale rows carry side chip + risk chip + conf + time.
- `DEMO` is styled as amber **warning** everywhere, so demo data screams the
  same color as actual risk. Amber is doing three unrelated jobs (stale,
  demo, medium risk).

### 1.3 Micro-typography inflation
Arbitrary per-file font sizes: 7.5, 8.5, 9, 10, 11, 11.5, 12, 12.5, 13, 15px
all coexist, plus three competing section-title treatments
(`lm-section-title`, `text-[11px] font-semibold uppercase`,
`text-xs font-semibold uppercase`). Spacing is similarly ad hoc (`gap-2/2.5/3/4`,
`p-2/2.5/3/3.5/4` mixed without a rule).

### 1.4 Debug UI shipped as product UI
API Status (Requested/Resolved/Cells/Walls/Generated/Demo/Auto/…), Data
Status, the heatmap `showDebug` overlay, and per-panel error strings are all
visible by default. This is operator telemetry, not trader intelligence —
it's the single biggest "assembled, not designed" signal.

### 1.5 Equal-weight information / duplicated content
- Dashboard: "Current Read" card and the "Primary market" card repeat
  bias/score/walls/price; the page says the same thing twice before the fold.
- Paper Trading: the positions table and the per-position setup cards list
  the same trades twice in two formats.
- Terminal: KPI strip, pressure banner, dominance panel and walls list all
  sit at the same visual level as the Intelligence Chart — the one strong,
  proprietary element on the page.

### 1.6 Leftover legacy
Liquidity Map still uses `lumora-*` tokens (`text-lumora-cyan`,
`lumora-purple-bright`, `focus:border-lumora-purple`) and gradient zone-card
rails with purple — off the LM design language. `lm-app-bg` dot grid behind
the app reads cheap next to the chart's flat plane.

---

## 2. Design principles (the interpretation of "premium")

1. **One instrument per page.** Every page has exactly one visual center —
   its instrument (chart, heatmap, tape, read, desk). The instrument gets the
   only strong frame on the page. Everything else is support.
2. **Border is earned.** Three surface levels, total. If everything has a
   border, nothing does.
3. **Status appears once.** One status cluster per surface, top-right, max
   two chips. System telemetry lives behind a disclosure, never inline.
4. **Color is a verdict.** Green/red = direction and bid/ask. Amber = risk
   and staleness only. Cyan = price/now/active. Purple = brand mark only.
   Demo/source labels are *gray*.
5. **Numbers speak, labels whisper.** Values in mono at readable sizes;
   labels in one micro style; explanatory prose appears on
   hover/expand/drill-down, not by default.
6. **Calm density.** Dense like a terminal, not busy like a template — fixed
   spacing scale, fewer sections, tighter rows, more whitespace *between*
   zones than *inside* them.
7. **Motion is state.** Live dot, number transitions, row hover, disclosure
   expand (≤160ms). Nothing else moves. (Landing page keeps its cinema; the
   app does not import it.)
8. **Personality through precision,** not decoration: the mono micro-labels,
   the read language, the field-style chart chrome ARE the personality.

Core UX rule: **more intelligence, less noise** — the most useful read first,
detail on demand.

---

## 3. Proposed design system (reusable primitives)

All in `components/ui/`, replacing ad-hoc per-page markup:

| Primitive | Replaces | Definition |
|---|---|---|
| **AppShell** | `(app)/layout.tsx` body | Flat `bg-lm-bg` (drop the `lm-app-bg` dot grid in-app), TopNav, `max-w-screen-2xl`, page padding. Global LIVE indicator stays in nav as the *only* always-on system status. |
| **PageHeader** | 5 hand-rolled headers | `title` + optional `context` line + right `status` slot (≤2 chips) + optional `toolbar` slot. One height, one type style. |
| **Surface** | `Panel` (evolves it) | `level="primary"` — the instrument frame: `bg-lm-surface`, 1px border, `lm-chart-frame` inset, the only level allowed an accent top stripe. `level="secondary"` — recessed: `bg-lm-surface-muted`, **no border**, rounded-md. `level="inline"` — no background; hairline dividers only. `Panel` stays as alias during migration. |
| **MetricStrip** | KPI strips on Terminal/Paper Trading/Whale Alerts | Divided cells: micro label + mono value + optional sub. One component, one density, horizontal scroll on mobile. |
| **ChartFrame** | IntelligenceChartPanel chrome (generalized) | header bar (title, scope, status cluster) + instrument body + optional bottom context bar + footer disclaimer line. Heatmap and whale tape adopt the same chrome so all instruments feel like one family. |
| **StatusChip** | `StatusBadge` (re-tokened) | Semantic axes, not raw colors — see §6. Max 2 per surface enforced by convention. |
| **SectionTitle** | 3 competing styles | `lm-section-title` becomes the single section lead; drop the other two. |
| **Disclosure** | API/Data Status panels, long reasons, debug | Collapsed-by-default row ("System", "Details") with chevron; also powers expandable feed rows. |
| **DataField** | ad-hoc label/value pairs | micro label + mono value, used inside strips, popovers, disclosures. |
| **Toolbar** | per-page select/segment rows | symbol select, segmented controls, toggle chips — one height (28px), one focus style. |

### Typography roles (exactly five)
| Role | Spec | Use |
|---|---|---|
| `display` | mono 700, 22–28px, tabular | hero prices, equity, verdicts |
| `value` | mono 600, 13px | table numbers, metric values |
| `body` | sans 12.5px / 1.4 | reasons, actions, prose |
| `caption` | sans 11px, dim | subtitles, footnotes, timestamps |
| `label` | mono 600, 10px, uppercase, +0.14em | the ONE micro-label style (9px and below retired for a11y) |

### Spacing scale
4 / 8 / 12 / 16 / 24. Page rhythm: sections `space-y-3` (12), instrument gets
16 above/below. Surface padding: primary 12, secondary 8–12, rows `py-1.5`.
Grid gaps: 12 everywhere (kill the 16s).

### Motion rules
Keep: `lm-live-dot`, `lm-page-enter` (160ms), row hover (120ms), number
transitions, disclosure expand. Remove: spinning RefreshCw as a permanent
"live" indicator (Terminal walls header — a spinner that never stops reads
as broken). All gated by the existing reduced-motion block.

---

## 4. Chart-centered IA — same family, different instruments

The pages stay distinct by **which instrument owns the top zone**, not by
layout novelty. Shared skeleton: PageHeader → (toolbar) → INSTRUMENT →
metric strip → support zone → disclosure footer.

| Page | Instrument (the one primary surface) | Feel |
|---|---|---|
| **Terminal** | Intelligence Chart, full width, taller (~480px) | the cockpit |
| **Liquidity Map** | Heatmap canvas + depth rail | the depth scanner |
| **Dashboard** | One merged "Current Read" command card (verdict + live price + key walls in a single surface) | the morning briefing |
| **Whale Alerts** | The tape (feed) itself, ChartFrame chrome | the wire |
| **Paper Trading** | Positions table | the desk blotter |

### Per-page direction

**Terminal** — the chart IS the page. Move Last/Bid/Ask/Spread into the
chart's bottom context bar (it already has one); demote the KPI strip;
pressure-banner text becomes one caption line under the chart header; Order
Flow Dominance + Walls become a two-up *secondary* (borderless) zone below;
remove the perpetual spinner. Net: 6 bordered panels → 1 primary + 1
secondary zone.

**Liquidity Map** — heatmap hero unchanged in function. Controls collapse
into one Toolbar row inside the instrument header. Key Zones become a compact
list in the depth rail (not 4 cards). The 5 summary cards merge into one
MetricStrip. API Status + Data Status + fallback notices collapse into a
single "System" Disclosure (all 13 fields preserved — just not ambient).
Source note banner only renders for non-supported markets. Purple gradient
rails and `lumora-*` tokens replaced with `lm-*`. `showDebug` off in product.

**Dashboard** — merge Current Read + primary market card into one command
surface: verdict (display type) + reason/action + live price + top bid/ask
rails, one status cluster. Secondary markets stay compact. Setups and Whale
Intel become secondary surfaces with `caption` headers; setup rows lose tag
chips by default (tags move into row expand). The dashboard answers "what's
the read?" in one glance.

**Whale Alerts** — feed gets ChartFrame chrome (title, count, one source
chip). Rows tighten to: time · side rail (color, no chip) · symbol · size ·
one risk chip; reason/action/conf move into the existing row expand. Filters
become Toolbar segments; summary becomes a MetricStrip above the tape.

**Paper Trading** — keep the strip + table; delete the duplicate
setup-context card list (setup text moves into an expandable table row);
journal rows keep the P&L rail but drop per-row icons-in-boxes. "Mock mode"
is one neutral chip in the PageHeader, not repeated per panel.

---

## 5. Reduce / hide / merge / disclose

| Action | Items |
|---|---|
| **Remove** | dot-grid app background; perpetual spinner; `showDebug` overlay; duplicate dashboard market card; duplicate paper-trading setup cards; decorative icon boxes in journal rows |
| **Merge** | Terminal KPI strip → chart context bar; LM summary cards → MetricStrip; Key Zones → depth rail; per-panel disclaimers → one page footer line |
| **Disclose** | API Status, Data Status, fallback diagnostics → "System" Disclosure; whale reason/action/confidence → row expand; setup tags → row expand; chart overlay legend → popover |
| **Keep visible** | verdicts, prices, risk chips, one status cluster per surface, the honesty line (one per page, footer) |

Text-density rule of thumb: a default viewport should show **≤1 sentence of
prose per surface**; everything longer lives one interaction away.

---

## 6. Standardization (chips, color, status)

`StatusChip` semantic axes (replacing raw StatusBadge variants):

| Axis | Tokens | Rendering |
|---|---|---|
| **Data state** | `live` / `stale` / `demo` / `error` | live = emerald dot + label; stale = amber; **demo = neutral gray** (no longer amber); error = red. One per surface, header right. |
| **Direction** | `long` / `short` / `neutral` | big verdicts = colored *text* (display role), no chip; dense rows = small chip. Same emerald/red/zinc everywhere (Dashboard, chart read, whale side, paper side). |
| **Risk** | `low` / `med` / `high` | emerald / amber / red chip — the only other amber user. |
| **Source** | `binance` / `supabase` / `journal` / `demo` | mono gray micro-text (`label` role), not a chip — e.g. `SRC BINANCE · WS`. |
| **Overlay toggles** | on/off | keep the LM68 chip toggles; standardize as Toolbar chips with `aria-pressed`. |

Rules: never two chips meaning the same thing on one surface; never amber for
non-risk/non-stale; `STALE` + `DEMO` cannot both show (demo implies the rest).

---

## 7. Responsive + accessibility

**Responsive:** instrument first on mobile, full-bleed (-mx page padding
acceptable); MetricStrip horizontal-scrolls (`lm-no-scrollbar`); toolbars
collapse to a single popover row; tables → the existing card-row fallback
pattern; touch targets ≥36px for toolbar controls.

**Accessibility:**
- *Contrast:* `lm-muted` (#71717a) passes on the dark surfaces for normal
  text but micro-uppercase at 9px does not pass readability — minimum label
  size becomes 10px; values stay ≥12px. No information encoded by color
  alone (side rails always pair with text/symbol).
- *Focus:* replace `focus:outline-none` selects with a visible
  `focus-visible` ring (1px cyan at 60%) on every Toolbar control, link, and
  row expander.
- *Keyboard:* segments/toggles stay real `<button>`s with `aria-pressed`;
  Disclosure uses `<button aria-expanded>`; feed-row expansion reachable by
  Tab + Enter.
- *Reduced motion:* already centralized in globals — new primitives must add
  their classes to that block, not ship their own loops.

---

## 8. Recommended patch sequence

| Patch | Scope |
|---|---|
| **LM69B — app shell + panel primitives** | AppShell (flat bg), PageHeader, Surface levels, SectionTitle, Disclosure, MetricStrip, Toolbar, focus styles, spacing tokens in globals. Pages keep working via the `Panel` alias; only layout.tsx + new primitives + globals touched. |
| **LM69C — terminal/chart layout cleanup** | Terminal page on the new skeleton: chart as sole primary, KPI merge into chart context bar, secondary dominance/walls zone, spinner removed. ChartFrame chrome extracted from IntelligenceChartPanel for reuse. |
| **LM69D — dashboard information architecture cleanup** | Merged command card, demoted setups/whale intel, row-expand for details, duplicate content removed. Liquidity Map's System Disclosure + MetricStrip merge ride along here (same IA pattern). |
| **LM69E — status/chip/typography standardization** | StatusChip semantic re-token (demo→gray app-wide), source micro-text, typography roles applied, legacy `lumora-*` tokens purged from Liquidity Map, Whale Alerts + Paper Trading row cleanup. |

Each patch: lint + build green, no Python/Supabase/worker changes, no new
dependencies, screenshots compared before/after per page.

---

## 9. What this is NOT

No new gradients, no new glow, no purple spread, no card multiplication, no
landing-page cinema inside the app, no hiding of honesty labels (demo/mock
stays visible — just calm and gray), no removal of data (telemetry moves
behind disclosures, never deleted).
