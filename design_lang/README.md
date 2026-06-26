# Handoff: Mercator — Structured Products design system

## Overview
Mercator is the design language for the structured-note / autocallable Monte-Carlo
simulator (the existing **React + Vite + TypeScript** app in this repo). It replaces the
generic navy/blue "fintech dashboard" look with a calm, **institutional** system: warm
paper, ink, a deep viridian accent, and a strict **figure register** set on a faint
graph-paper ground. The goal is a tool that reads like an instrument / term sheet a banker
puts in front of a client — sober, precise, trustworthy.

**Functionality does not change.** This is a re-skin of the existing screens (header,
setup rail, note structure, Monte-Carlo / Backtest / Live / Report tabs). Keep all current
logic, data flow, and component structure; change look, type, colour, and a few component
treatments.

## About the design files
The `references/*.dc.html` files are **design references** — HTML prototypes showing the
intended look, not production code to copy. Recreate them in the existing React/TS codebase
using its established patterns (the app uses CSS variables keyed off `[data-theme]`, plain
CSS in `src/index.css`, and small inline-styled components — keep that approach). The
`tokens/` and `assets/` files ARE drop-in ready.

To view a reference: open the `.dc.html` in a browser (it loads `support.js` from the same
folder + fonts from Google Fonts). Most are a **pannable canvas** — scroll/zoom to see all
frames. **Start with `references/Mercator - System.dc.html`** — it's the index, with a card
linking to every other document.

## Fidelity
**High-fidelity.** Colours, type, spacing, and treatments are final — match them precisely
using the tokens below. Brand name is **Mercator**; the mark is the **meridian circle**.

---

## THE REGISTER (read this first)
The single rule that defines Mercator. Every **number, ticker, code, unit, and eyebrow
label** is set in **IBM Plex Mono, tabular**. Serif is for titles only; sans is for body and
controls. Specifically:

1. **Mono numerals** — all figures in IBM Plex Mono with `font-variant-numeric: tabular-nums`
   so columns align on the decimal. Never serif, never proportional.
2. **Signed P&L** — direction is always signed and coloured: **viridian `#15694E` up**,
   **rust `#9C3B30` down**, with `▲ / ▼` glyphs (`.delta-pos` / `.delta-neg`).
3. **Split units** — the unit (`%`, `bps`, `y`, `€`) sits smaller and muted beside the
   figure, so the number reads first (`.fig` + `.fig-unit`).
4. **Ledger tables** — heavy header rule (`1.5px` ink) + hairline row rules + vertical
   hairline rules, numerics right-aligned (`.ledger`).
5. **Mono eyebrows** — overlines and caption labels are mono uppercase, ~`0.08em` tracking
   (`.eyebrow`), NOT sans.
6. **Graph-paper ground** — the app shell sits on a faint grid; opaque panels float above it
   (`.ground`).

> NOTE: an earlier iteration of this handoff used *serif* figures and "no monospace." That is
> superseded — the final system is the **mono register** described here.

---

## Design tokens

### Drop-in stylesheet
`tokens/mercator.css` is a **complete replacement for `src/index.css`**. It keeps every
existing CSS-variable NAME (`--bg`, `--surface`, `--text`, `--accent`, `--border`, `--green`,
`--red`, `--amber`, `--shadow`, `--header-bg`, …) so most components compile unchanged. It
adds `--font-serif`, `--font-sans`, `--font-mono`, the grid tokens, and the helper classes
`.fig` `.fig-unit` `.delta-pos` `.delta-neg` `.eyebrow` `.ledger` `.ground` `.tag*` `.btn--*`.
`className="mono"` (already used across the app) now maps to IBM Plex Mono — so existing
numeric cells become correct automatically.

### Colour — Light (primary)
| Token | Hex | Use |
|---|---|---|
| `--bg` | `#F7F5EF` | warm paper page background |
| `--bg-elev` / `--surface-2` | `#F1EEE4` | app ground base / inset rows |
| `--surface` | `#FFFEFB` | cards, header, panels (opaque, float over the ground) |
| `--surface-hover` | `#EFECE3` | muted fill / hover |
| `--text` | `#1C241F` | ink, primary text + heavy table rule |
| `--text-muted` | `#5C635B` | secondary text |
| `--text-faint` | `#8C9189` | captions, eyebrows, units |
| `--border` | `#E6E1D5` | card & panel borders (1px hairline) |
| `--border-strong` | `#D4CDBD` | inputs, stronger dividers |
| `--hairline` | `#ECE8DD` | faint in-card / ledger row rules |
| `--accent` (viridian) | `#15694E` | brand, primary buttons, positive figures, active states |
| `--accent-hover` | `#114E3A` | hover |
| `--accent-weak` | `#E4EFE9` | accent tints / tags / focus ring fill |
| `--red` (rust) | `#9C3B30` | losses / negatives / down (NOT bright red) |
| `--amber` (ochre) | `#9A6B1A` | "stale / inputs changed" + the worst-of underlying |
| chart 2nd / 3rd | `#3F8A6F` / `#7EB4A0` | secondary viridian series |
| grid minor / major | `#E7E0CF` / `#DDD4BF` | graph-paper ground lines |

Dark theme (secondary) full set is in `tokens/mercator.css` (`--bg #0E1310`,
`--accent #3FAE86`, `--red #D97A6E`, `--amber #D2A24E`, …).

### Typography — three voices
- **Source Serif 4** (`--font-serif`) — titles & section headings ONLY (`h1/h2/h3`, panel
  titles, the "Mercator" wordmark). Weights 400/600. Italic for captions
  (“*Monte Carlo, 50,000 paths*”). **Never** used for figures.
- **Hanken Grotesk** (`--font-sans`) — body, labels, buttons, table descriptions. 400–700.
- **IBM Plex Mono** (`--font-mono`) — **all figures, tickers, codes, units, eyebrows.** 400–600.
- Load fonts (add to `index.html` `<head>`):
  ```html
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Source+Serif+4:ital,opsz,wght@0,8..60,400;0,8..60,500;0,8..60,600;0,8..60,700;1,8..60,400&family=Hanken+Grotesk:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
  ```

### Type scale (used in mocks)
| Role | Font / weight | Size | Notes |
|---|---|---|---|
| Page / note title | Serif 600 | 30px | `letter-spacing:-0.01em` |
| Hero metric value | **Mono 600** | 33px | tabular, `line-height:.95`; split unit at ~16px |
| Section title | Serif 600 | 14.5–21px | |
| Caption (italic) | Serif italic 400 | 12.5–15px | muted |
| Eyebrow / overline | **Mono 500** | 9.5–10px | `letter-spacing:0.08em`, uppercase, faint |
| Body / UI | Sans 400–500 | 12.5–14px | `line-height:1.55` |
| Table value | **Mono** | 12.5–13px | tabular, right-aligned |
| Big numeric (IRR, quote) | **Mono 600** | 24–38px | split unit |

### Radius / shadow / lines
- Radius: cards `8–9px`, buttons & inputs `6px`, tags `4px`, modals `12px`, pills `999px`.
- Shadow (light, sparing): card `0 1px 2px rgba(40,35,20,.05)`; card-hover
  `0 6px 20px -10px rgba(40,35,20,.28)`; modal `0 24px 60px -16px rgba(15,22,17,.55)`;
  toast `0 6px 18px -10px rgba(40,35,20,.3)`.
- **Focus ring** (every focusable control): `box-shadow: 0 0 0 3px var(--ring)` (viridian-tint
  halo) + `border-color: var(--accent)`. **Error:** `border:1px solid var(--red)` +
  `box-shadow:0 0 0 3px #F0D9D4` halo, with a mono rust message below.
- **Prefer hairline rules + whitespace over heavy boxes.**

---

## Screens / Views
Each maps to a reference doc and to existing components.

### 0. System index — `references/Mercator - System.dc.html`
The design-system home: masthead + linked cards. Not an app screen; your map to everything else.

### 1. Foundations — `references/Mercator - Foundations.dc.html`
Type specimen (serif / sans / mono), the colour & token swatches (with hexes), and the four
register rules spelled out. Source of truth for the tokens above.

### 2. App header — `src/components/Header.tsx`
Flex row, space-between, `height ~62px`, `background var(--header-bg)`, `border-bottom 1px
var(--border)`, no heavy shadow. Left: 30px viridian tile (radius 7) with the meridian mark in
paper, then **"Mercator" in Source Serif 4 600 ~19px**; vertical hairline; note name (serif
15px) + ISIN/tickers in **mono 10.5px** muted. Right: run-meta chip
(`numpy · 50,000 paths · seed 42` in **mono**), a `Priced` status tag (viridian dot), and an
`Export report` secondary button.

### 3. Pricer (the full app in situ) — `references/Mercator - Pricer.dc.html`
- Shell uses `.ground` (graph paper). Layout: `grid-template-columns: 340px 1fr; gap 20px`.
- **Setup rail (`SetupRail.tsx`)** in a `Panel`: template select, underlying basket rows
  (mono ticker tile + name + signed day move), quick-edit **sliders** (label sans left, value
  **mono** right; track `--border`, fill `--accent`, 14px knob; KI-barrier slider uses `--red`),
  segmented frequency, primary "Re-run simulation".
- **Note structure**: the autocall **ladder** (nodes on a hairline line, AC level **mono** above,
  cumulative coupon below, current node haloed `--accent-weak`) + an issuer/credit strip + a
  notional/memory/capital readout.
- **Tabs**: underline tabs — active = viridian 13px 600 with `2px solid var(--accent)` bottom.
- **HeroMetrics (`HeroMetrics.tsx`)**: two groups (Return / Risk) of cards; each = eyebrow
  (mono uppercase) → value (**mono 33px 600**, split unit; `--accent` for IRR-positive / low KI,
  `--red` for loss) → hint (mono 11px faint).
- **MC result**: return-distribution **histogram** (bars; loss bins `--red`, body `--accent`,
  barrier marker line) + **outcome** stacked bar with a `.ledger`-style legend.

### 4. Backtest & Live — `references/Mercator - Backtest & Live.dc.html`
Same shell. Backtest: window control, 4 mono metric cards, realised-IRR **scatter** (dots;
losses `--red`), outcome split bar + legend. Live: worst-of level / distance-to-barrier (signed
`.delta-pos`) / accrued coupon / next-obs metrics, a per-asset **ledger** table, a worst-of line
chart with the barrier dashed in `--red`.

### 5. Report (output PDF) — `references/Mercator - Report.dc.html`
Letter-width (816px) institutional document: masthead with the desk identity + a `2.5px`
viridian rule, headline term figures on a faint graph ground, ruled **note-terms** and
**observation-schedule** ledgers, an MC section (mono metrics + histogram + autocall-by-period
bars + outcome bar), issuer/credit strip, disclaimer footer. Maps to `ReportPanel.tsx` output.

### 6. Controls — `references/Mercator - Controls.dc.html`
Every control across Default / Hover / Focus / Error / Disabled: text & number inputs
(mono values), select (with open dropdown), segmented control, sliders (default / grabbed-halo
/ disabled), toggle, checkbox, radio, and buttons (Primary / Secondary / Ghost / Danger). Maps
to `fields.tsx`. Use these for the exact border/halo/disabled treatments.

### 7. Charts — `references/Mercator - Charts.dc.html`
The data-viz vocabulary + palette: worst-of **fan chart** (percentile bands of `--accent` at
0.12/0.20 opacity + median line + `--red` dashed barrier), **IRR distribution** histogram,
**IRR scatter**, **correlation matrix** heatmap (cells tinted `rgba(21,105,78,α)` where α=ρ,
mono values), worst-asset **allocation donut**, multi-line **price history**. Retheme Plotly
(`src/lib/plotlyTheme.ts`) to match: transparent bg, `--hairline` gridlines, axis text Hanken
`--text-muted`, primary series `--accent`, loss `--red`, third series `#9A6B1A`.

### 8. Overlays — `references/Mercator - Overlays.dc.html`
Scrim `rgba(20,28,23,0.46)`; modal = paper card, radius 12, modal shadow. Settings overlay
(`SettingsOverlay.tsx`): header (serif title + mono sub) → fields → footer (Cancel + primary).
Confirmation dialog (rust icon tile, serif title, Keep/Discard). **Toasts** rise with a 3px
`border-left` in the state colour + one signed icon (success `--accent` check, error `--red` x,
caution `--amber` info, ink info reversed).

### 9. States — `references/Mercator - States.dc.html`
- **Empty:** centered `--accent-weak` tile + meridian mark, serif title "No simulation yet",
  primary "Run simulation".
- **Running (`RunProgress`):** serif "Pricing 50,000 paths…", a determinate **3px hairline bar**
  (`--border` track, `--accent` fill), mono telemetry line. **No spinner.**
- **Skeleton:** `.skeleton` shimmer blocks in the panel's own shapes.
- **Error:** rust tile + x, serif title, mono error string in a `--red` tinted box, Retry primary.

### 10. Iconography — `references/Mercator - Iconography.dc.html`
The mark lockups (primary / mark-only / on-ink / mono) + clear-space (½ mark height) + min-size
(drop the equator line < 20px; never < 16px), and the **12-icon set** (sun, moon, play, refresh,
chart, spinner, x, plus, info, check, upload, download) — 24×24 grid, 1.9 stroke, round
cap/join, `stroke = currentColor`, only `play` filled. Maps to `Icon.tsx` (unchanged paths).

### 11. Mobile — `references/Mercator - Mobile.dc.html`
The pricer at 390px: result reads first (metrics 2-up, ladder scrolls), the setup rail collapses
into a **bottom sheet** (grab handle, sliders, Apply & run) reached from a sticky bottom action bar.

### Texture study — `references/Mercator - Texture Options.dc.html`
The four grounds explored (graph / dot / diagonal / ledger). **Graph paper is canon** (`.ground`);
included only for context.

---

## Interactions & behavior
Unchanged from the current app. Notes:
- Theme toggle still flips `[data-theme]` on `<html>` (keep `ThemeProvider`); light is default.
- Transitions stay subtle: `background/color/border 0.12–0.2s ease`. No glows, no pulsing.
- Charts: retheme per §7. Keep Plotly interaction behaviour.
- Focus is keyboard+click identical (the shared 3px halo).

## State management
No new state. Reuse existing `terms`, `opts`, `result`, `status`, tab, and theme state.

## Assets
- `assets/favicon.svg` — drop-in replacement for `public/favicon.svg` (viridian tile, paper
  meridian mark).
- `assets/BrandMark.tsx` — drop-in replacement for `src/components/BrandMark.tsx`; same
  `{ size }` + `currentColor` API (meridian circle glyph). Header tile: viridian `#15694E` bg,
  mark stroked in paper `#F7F5EF`.

## Files in this bundle
- `tokens/mercator.css` — drop-in replacement for `src/index.css` (palette + register helpers +
  `.ground` + `.ledger` + focus ring).
- `assets/favicon.svg`, `assets/BrandMark.tsx` — drop-in brand assets.
- `references/Mercator - System.dc.html` — **start here**, links to all below.
- `references/Mercator - Foundations.dc.html` — type, colour, register rules.
- `references/Mercator - Elements.dc.html` — supporting elements + financial components.
- `references/Mercator - Controls.dc.html` — control states.
- `references/Mercator - Iconography.dc.html` — mark + icon set.
- `references/Mercator - Charts.dc.html` — data-viz vocabulary.
- `references/Mercator - Overlays.dc.html` — modal / dialog / toasts.
- `references/Mercator - States.dc.html` — empty / loading / skeleton / error.
- `references/Mercator - Pricer.dc.html` — the full app in situ.
- `references/Mercator - Backtest & Live.dc.html` — the other two tabs.
- `references/Mercator - Report.dc.html` — the output document.
- `references/Mercator - Mobile.dc.html` — responsive pricer.
- `references/Mercator - Texture Options.dc.html` — ground study (graph = canon).
- `references/support.js` — runtime for the reference files (don't ship; reference only).

## Implementation order (suggested)
1. Add the font `<link>` to `index.html`; replace `src/index.css` with `tokens/mercator.css`.
2. Swap `BrandMark.tsx` + `public/favicon.svg`; set the wordmark to "Mercator" (serif) in `Header.tsx`.
3. Add `.ground` to the app shell behind the panels.
4. `className="mono"` numerics now render correct automatically; add split units (`.fig-unit`)
   and signed `.delta-*` on deltas; convert tables to `.ledger`.
5. Rework `HeroMetrics` to mono values; convert eyebrows/overlines to `.eyebrow` (mono).
6. Editorial underline tabs; the empty / running / skeleton / error states.
7. Retheme Plotly to the chart palette (§7). Then the overlays, toasts, and supporting elements.
