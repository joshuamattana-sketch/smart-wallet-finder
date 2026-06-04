# Lumora Design Direction

Institutional terminal meets boutique intelligence.

## Design Principles

1. **Data density over decoration.** Every pixel serves a read. No decorative gradients or glow that don't convey information.
2. **Hierarchy through typography, not color.** Use font weight, size, and opacity for hierarchy. Reserve color for semantic meaning.
3. **Monochrome base, semantic color.** Default state is near-monochrome. Color appears only when it means something.
4. **Flat panels, not glass.** Subtle 1px borders on flat dark surfaces. No frosted glass, no gradient overlays.
5. **Numbers are first-class.** JetBrains Mono, tabular-nums, right-aligned in tables, consistent sizing.
6. **Status is earned.** Badges only for machine state (Live/Stale/Error) and data labels (BID/ASK). Not decorative.
7. **Reduce, don't add.** Group related info. Collapse secondary panels behind toggles.
8. **Responsive density.** Desktop = dense terminal. Mobile = monitoring view (price + status + top walls).
9. **Motion is functional.** Only: status pulse dots, loading spinners, number transitions. No page transitions or hover glow.
10. **No marketing in the app.** Landing page is marketing. App views are austere data.

## Color Logic

### Token System (`lm-*` prefix)

| Token | Hex | Purpose |
|---|---|---|
| `lm-bg` | `#0c0c0e` | Page background (neutral dark) |
| `lm-surface` | `#141416` | Panel/card background |
| `lm-surface-muted` | `#111113` | Nested panel background |
| `lm-border` | `#1e1e22` | Panel borders (neutral gray) |
| `lm-text` | `#e0e0e4` | Primary text |
| `lm-text-dim` | `#a1a1a6` | Secondary text |
| `lm-muted` | `#71717a` | Labels, captions |
| `lm-purple` | `#8b5cf6` | Brand accent (nav/logo only) |
| `lm-cyan` | `#22d3ee` | Current price, active selection |
| `lm-live` | `#22c55e` | Live status, bid/support |
| `lm-error` | `#ef4444` | Errors, ask/resistance |
| `lm-warning` | `#f59e0b` | Stale data, medium risk |
| `lm-bid` | `#22c55e` | Bid side |
| `lm-ask` | `#ef4444` | Ask side |

### Semantic Color Rules

- **Green:** Bids, support, positive signals, "Live" status
- **Red:** Asks, resistance, negative signals, errors
- **Amber:** Warnings, stale data, medium risk
- **Cyan:** Current price marker, active data emphasis
- **Purple:** Brand accent in nav/logo only
- **Zinc grays:** Everything else

## Panel System

### `<Panel>`
- Flat `bg-lm-surface`, 1px `border-lm-border`, `rounded-lg`
- No gradient, no glow, no backdrop-blur
- Optional `compact` prop for tighter padding
- Optional `hover` prop for interactive panels (border lightens on hover)

### `<InlinePanel>`
- No border, `bg-lm-surface-muted`, `rounded-md`
- For nested sections within a Panel

### Migration
- Old `<GlassCard>` remains for existing pages during transition
- New pages use `<Panel>` and `<InlinePanel>` exclusively
- After all pages are migrated, remove GlassCard

## Badge System (`<StatusBadge>`)

| Variant | Use For |
|---|---|
| `live` | Connection is live and fresh |
| `stale` | Data exists but is old |
| `error` | Connection failed |
| `warning` | Caution states |
| `bid` | Bid/buy side labels |
| `ask` | Ask/sell side labels |
| `neutral` | Non-status metadata (exchange, timeframe) |

### Rules
- Optional `dot` prop shows a colored status dot (pulsing for `live`)
- Old `<Badge>` remains for existing pages
- Max 2-3 badges visible per card/row

## What to Avoid

- Gradient overlays on cards (`from-[rgba(...)]`)
- Neon glow shadows (`shadow-neon-purple`, `shadow-neon-cyan`)
- Glass morphism (`backdrop-blur`, `.glass`)
- More than 2 semantic colors in a single panel
- `rounded-xl` on data panels (use `rounded-lg`)
- Page transition animations (`fadeIn`)
- Hover glow effects (`glass-hover`)
- Marketing copy inside app views
- Decorative badges ("Beta", "Q3 2026")
- Purple-tinted backgrounds and borders

## Redesign Sequence

1. Liquidity Map (reference implementation)
2. Dashboard
3. Whale Alerts
4. Terminal
5. Market Bubbles / Intelligence Map (new page, last)
