# VESDIO Design System — Technical Documentation

This document describes VESDIO's design token system: what exists, where it
lives, and how to use it. It is the reference for anyone touching styling in
this codebase — **before adding a new color, spacing value, or shadow,
check whether a token already covers it.**

## Why a design system

Prior to this work, the app mixed a third-party CodePen skeleton stylesheet
with pervasive inline `style={}` dicts and literal hex colors scattered
across `app.py` and `src/plotting.py` (e.g. `#f0f0f0`, `#ddd`, `#ccc`, `#888`,
`#f9f9f9`). Colors and spacing were re-typed at every call site, so nothing
guaranteed consistency and nothing supported a dark theme.

The fix: **one set of tokens, defined once, consumed from two places**:

| Source of truth | Consumers |
|---|---|
| `assets/design-system.css` — CSS custom properties on `:root` | Dash component `className`/`style` usage, future component-library theming (WS1) |
| `src/design_tokens.py` — the same values as Python dicts | `src/config.py` (`COLOR_PALETTE`), Plotly figure builders in `src/plotting.py`, any Python code that needs a token value |

Both files must stay in sync. If you change a value, change it in both
places and re-check the "Token reference" tables below.

> **Note on scope:** this workstream (WS0) only establishes the tokens and
> wires `COLOR_PALETTE` through them. The CodePen stylesheet in `app.py`,
> the inline `style={}` dicts in `app.py`, and the overall UI restructuring
> are addressed in a later workstream (UI modernization) — they are not yet
> removed or refactored.

## Color tokens

### Brand palette (Okabe-Ito, colorblind-safe)

The six brand colors are the [Okabe-Ito](https://jfly.uni-koeln.de/color/)
palette, chosen because it stays distinguishable under the common forms of
color vision deficiency. **These hex values are deliberately fixed — do not
change them without re-validating colorblind-safety.**

| Token (CSS) | Token (Python, `COLORS['brand']`) | Hex | Used for |
|---|---|---|---|
| `--color-blue` | `blue` | `#0072B2` | Neutral/base series, "before" state |
| `--color-red` | `red` | `#D55E00` | Impact/negative, "after" state |
| `--color-amber` | `amber` | `#E69F00` | Highlight / mid-scale |
| `--color-beige` | `beige` | `#F0E442` | Secondary highlight / scale low end |
| `--color-green` | `green` | `#009E73` | Positive change |
| `--color-grey` | `grey` | `#999999` | "Others" / de-emphasized category |

### Semantic aliases

Prefer semantic tokens over brand-color names in new code — they document
*intent*, and the underlying hex can be re-pointed later without touching
call sites.

| Semantic token (CSS) | Python (`COLORS['semantic']`) | Aliases | Hex |
|---|---|---|---|
| `--color-accent` | `accent` | blue | `#0072B2` |
| `--color-negative` | `negative` | red (vermillion) | `#D55E00` |
| `--color-positive` | `positive` | green (bluish-green) | `#009E73` |
| `--color-warning` | `warning` | amber | `#E69F00` |
| `--color-highlight` | `highlight` | beige | `#F0E442` |
| `--color-neutral` | `neutral` | grey | `#999999` |

`src/config.py`'s `COLOR_PALETTE` dict is kept as the existing public
interface for chart code (`src/plotting.py`) — its keys (`blue`, `red`,
`amber`, `beige`, `green`, `grey`) and values are unchanged, but the values
now come from `src/design_tokens.py` instead of being re-declared.

### Neutral ramp (9 steps)

Replaces the ad-hoc greys previously hardcoded in `app.py`
(`#f0f0f0`, `#ddd`, `#ccc`, `#888`, `#f9f9f9`).

| Token | Hex | Typical use |
|---|---|---|
| `--color-grey-100` | `#F7F7F7` | Page/section subtle background |
| `--color-grey-200` | `#EEEEEE` | Card/panel background |
| `--color-grey-300` | `#E0E0E0` | Default border |
| `--color-grey-400` | `#CCCCCC` | Strong border, disabled fill |
| `--color-grey-500` | `#999999` | Mid-tone text/icon (matches brand grey) |
| `--color-grey-600` | `#757575` | Secondary/muted text |
| `--color-grey-700` | `#555555` | Body text on light surfaces (dark-mode muted text) |
| `--color-grey-800` | `#333333` | Headings |
| `--color-grey-900` | `#1A1A1A` | Primary text (dark-mode page background) |

### Theme surfaces (light/dark)

`--color-bg`, `--color-bg-subtle`, `--color-surface`, `--color-surface-raised`,
`--color-border`, `--color-border-strong`, `--color-text`, `--color-text-muted`,
`--color-text-on-accent` resolve differently per theme. Light values are the
`:root` defaults; dark values apply automatically via
`@media (prefers-color-scheme: dark)`, and can be forced with
`<html data-theme="dark">` / `data-theme="light"` (the explicit attribute
always wins over the OS preference).

Brand/semantic colors (the Okabe-Ito set) are **not** re-themed — they stay
identical in light and dark mode so chart colors never disagree with the
page chrome, and so Plotly figures (which always render on a fixed light
canvas today) match on-page swatches.

## Spacing scale

4px base unit. Use these instead of arbitrary pixel paddings/margins.

| Token | Value |
|---|---|
| `--space-1` | 4px |
| `--space-2` | 8px |
| `--space-3` | 12px |
| `--space-4` | 16px |
| `--space-5` | 20px |
| `--space-6` | 24px |
| `--space-8` | 32px |
| `--space-10` | 40px |
| `--space-12` | 48px |
| `--space-16` | 64px |

Python equivalent: `SPACING` dict in `src/design_tokens.py`, keyed by the
same numeric step (`SPACING[4] == "16px"`).

## Type scale

| Token | Value |
|---|---|
| `--font-size-xs` | 0.75rem (12px) |
| `--font-size-sm` | 0.875rem (14px) |
| `--font-size-base` | 1rem (16px) |
| `--font-size-md` | 1.125rem (18px) |
| `--font-size-lg` | 1.25rem (20px) |
| `--font-size-xl` | 1.5rem (24px) |
| `--font-size-2xl` | 1.875rem (30px) |
| `--font-size-3xl` | 2.25rem (36px) |

Weights: `--font-weight-normal` (400), `--font-weight-medium` (500),
`--font-weight-bold` (700).
Line heights: `--line-height-tight` (1.2), `--line-height-normal` (1.5),
`--line-height-relaxed` (1.75).
Font families: `--font-family-base` (system UI stack), `--font-family-mono`
(system monospace stack).

Python equivalent: `TYPE` dict in `src/design_tokens.py`
(`TYPE["font_size"]["md"]`, etc.).

## Radii

| Token | Value |
|---|---|
| `--radius-sm` | 2px |
| `--radius-md` | 4px |
| `--radius-lg` | 8px |
| `--radius-xl` | 16px |
| `--radius-full` | 9999px (pill/circle) |

Python equivalent: `RADII` dict in `src/design_tokens.py`.

## Elevation / shadow

| Token | Light-mode value |
|---|---|
| `--shadow-sm` | `0 1px 2px rgba(26,26,26,0.08)` |
| `--shadow-md` | `0 2px 8px rgba(26,26,26,0.12)` |
| `--shadow-lg` | `0 8px 24px rgba(26,26,26,0.16)` |
| `--shadow-xl` | `0 16px 48px rgba(26,26,26,0.20)` |

Dark-mode values use a darker, higher-opacity shadow color; see
`assets/design-system.css`. Python equivalent: `SHADOWS` dict in
`src/design_tokens.py` (light-mode values only, for reference — shadows are
a CSS-only concern in the current UI).

## Z-index scale

| Token | Value | Layer |
|---|---|---|
| `--z-base` | 0 | Normal flow |
| `--z-dropdown` | 1000 | Dropdown menus |
| `--z-sticky` | 1100 | Sticky headers |
| `--z-modal-backdrop` | 1200 | Modal backdrop |
| `--z-modal` | 1300 | Modal content |
| `--z-popover` | 1400 | Popovers |
| `--z-tooltip` | 1500 | Tooltips |
| `--z-toast` | 1600 | Toast/notifications |

Python equivalent: `ZINDEX` dict in `src/design_tokens.py`.

## Usage rules

1. **Before touching styling, use tokens.** Never hardcode a new hex color,
   pixel spacing value, border-radius, shadow, or z-index — reference the
   matching CSS custom property (in `style={}`/`className` CSS) or Python
   dict (in chart/config code).
2. **Charts (`src/plotting.py`) read `COLOR_PALETTE`** (from
   `src/config.py`), not `design_tokens.py` directly, to keep one import
   surface for chart code. `COLOR_PALETTE`'s values are themselves sourced
   from `design_tokens.COLORS['brand']`.
3. **New semantic meaning → new semantic token**, not a new brand color.
   E.g. if a future chart needs a "warning" state, use
   `COLORS['semantic']['warning']` / `--color-warning` rather than
   re-declaring `#E69F00`.
4. **Do not alter the six Okabe-Ito brand hexes.** They are colorblind-safe
   by construction; if a new color is genuinely needed, it must be chosen
   and validated for colorblind-safety separately, not blended into the
   existing set.
5. **Dark mode is opt-in via tokens, not per-component CSS.** Components
   should use the theme-aware surface tokens (`--color-bg`, `--color-text`,
   etc.) so they automatically adapt; don't branch component logic on
   `prefers-color-scheme` directly.
6. **Keep `assets/design-system.css` and `src/design_tokens.py` numerically
   identical.** A value should never exist in one and not the other.

## Component inventory (current state)

This is a snapshot of what exists today, to orient future styling work. It
is not a target UI spec (that is a later workstream).

| Component | Location | Notes |
|---|---|---|
| App shell / header | `app.py` (top-level `layout`) | Uses the external CodePen stylesheet + fixed `100vh`; not yet migrated to tokens |
| Control column (position, shock, magnitude, run) | `app.py` | Dense single column, inline `style={}` throughout |
| Scenario Builder modal | `app.py` (`~line 281`) | Hand-rolled `html.Div` modal, no focus trap |
| Instructions modal | `app.py` (`~line 366`) | Hand-rolled `html.Div` modal, no focus trap |
| Results tabs (Summary / Geographic / Supply Chain / Global / Historical / Portfolio) | `app.py` | `dcc.Tabs`; Portfolio tab shows a placeholder outside portfolio mode |
| Historical production line chart | `src/plotting.py: create_historical_production_plot` | Uses `COLOR_PALETTE['blue']`/`['red']` |
| Before/after bar chart | `src/plotting.py: create_before_after_barchart` | Uses `COLOR_PALETTE['blue']`/`['red']` |
| Attribution waterfall | `src/plotting.py: create_waterfall_plot` | Uses `COLOR_PALETTE` |
| Choropleth map | `src/plotting.py: create_choropleth_map` | Custom colorscale from `beige`→`amber`→`red` |
| Supply-chain Sankey (single & portfolio) | `src/plotting.py: create_sankey_diagram`, `create_portfolio_sankey_diagram` | Node colors from `COLOR_PALETTE` |
| Portfolio breakdown table | `src/plotting.py: create_portfolio_breakdown_display` | `DataTable` styled with `COLOR_PALETTE['grey']`/`['red']`/`['green']` |
| Top impacts table | `src/plotting.py: create_top_impacts_table` | Same pattern |
| `assets/custom.css` | `assets/custom.css` | Small `dcc.Dropdown` option-padding override; unrelated to the token system, left as-is |
| `assets/design-system.css` | `assets/design-system.css` | New — the token definitions themselves |

## Files

- `assets/design-system.css` — CSS custom properties (this document's CSS
  reference above).
- `src/design_tokens.py` — the same values as Python dicts: `COLORS`,
  `SPACING`, `RADII`, `TYPE`, `SHADOWS`, `ZINDEX`.
- `src/config.py` — `COLOR_PALETTE`, derived from `design_tokens.COLORS`;
  the stable interface chart code imports from.
