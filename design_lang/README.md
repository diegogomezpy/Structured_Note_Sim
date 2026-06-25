# Handoff: Mercator — Structured Products redesign

## Overview
Mercator is a new visual identity for the structured-note / autocallable Monte-Carlo
simulator (the existing React + Vite + TypeScript app in this repo). It replaces the
generic navy/blue, IBM-Plex, card-heavy "fintech dashboard" look with a calm,
**editorial / institutional** system: warm paper, ink, a deep viridian accent, serif
figures, and hairline rules instead of heavy cards and shadows. The goal is a tool that
reads like a term sheet a banker would put in front of a client — sober, precise, trustworthy.

**Functionality does not change.** This is a re-skin of the existing screens (header,
setup rail, note structure, Monte-Carlo / Backtest / Live / Report tabs). Keep all
current logic, data flow, and component structure; change look, type, color, and a few
component treatments.

## About the design files
The `references/*.dc.html` files in this bundle are **design references** — HTML
prototypes showing the intended look, not production code to copy. Recreate them in the
existing React/TS codebase using its established patterns (the app already uses CSS
variables keyed off `[data-theme]`, plain CSS in `src/index.css`, and small inline-styled
components — keep that approach). The `tokens/`, `assets/` files ARE drop-in ready.

To view a reference: open the `.dc.html` file in a browser (it loads `support.js` from the
same folder and fonts from Google Fonts). Each is a pannable canvas — scroll/zoom to see
all frames.

## Fidelity
**High-fidelity.** Colors, type, spacing, and component treatments are final. Match them
precisely using the tokens below. The one open product decision baked in: the brand name
is **Mercator** and the mark is the **meridian circle**.

---

## Design tokens

### Drop-in stylesheet
`tokens/mercator.css` is a **complete replacement for `src/index.css`**. It keeps every
existing CSS-variable NAME (`--bg`, `--surface`, `--text`, `--accent`, `--border`,
`--green`, `--red`, `--amber`, `--shadow`, `--header-bg`, …) so most components compile
unchanged. It adds `--font-serif`, `--font-sans`, `--hairline`, `.figure`, `.tag*`,
`.section-rule`, and `.btn--link`.

### Color — Light (primary)
| Token | Hex | Use |
|---|---|---|
| `--bg` | `#F7F5EF` | warm paper page background |
| `--surface` | `#FFFEFB` | cards, header, panels |
| `--surface-2` | `#F1EEE4` | inset / zebra rows |
| `--text` | `#1C241F` | ink, primary text |
| `--text-muted` | `#5C635B` | secondary text |
| `--text-faint` | `#8C9189` | captions, hints |
| `--border` | `#E6E1D5` | card & panel borders |
| `--border-strong` | `#D4CDBD` | inputs, stronger dividers |
| `--hairline` | `#ECE8DD` | faint in-card rules |
| `--accent` (viridian) | `#15694E` | brand, primary buttons, positive figures, active states |
| `--accent-hover` | `#114E3A` | hover |
| `--accent-weak` | `#E4EFE9` | accent tints / tags |
| `--red` (claret) | `#9C3B30` | losses / negatives (NOT bright red) |
| `--amber` (ochre) | `#9A6B1A` | "stale / inputs changed" notices |

Viridian alternates explored (lead is the deep `#15694E`): original `#18785A`,
forest `#114E3A`, pine-teal `#0E6E63`.

### Color — Dark (secondary)
`--bg #0E1310` · `--surface #161C17` · `--surface-2 #1E261F` · `--text #EEF1EA`
· `--border #2A332C` · `--accent #3FAE86` · `--red #D97A6E` · `--amber #D2A24E`.
(Full set in `tokens/mercator.css`.)

### Typography
- **Serif — Source Serif 4** (`--font-serif`): all headings (`h1/h2/h3`) and **all large
  figures** (metric values, table numbers). Use `font-variant-numeric: tabular-nums
  lining-nums` for figures (the `.figure` class does this). Italic is used for captions
  ("*Monte Carlo, 50,000 paths*").
- **Sans — Hanken Grotesk** (`--font-sans`): all UI, labels, body, buttons, table headers.
- **No monospace.** The previous `.mono` numeric treatment is removed — replace every
  `className="mono"` on a numeric value with `className="figure"` (serif) or `className="tnum"`
  (sans + tabular, for small in-line table values).
- Load fonts (add to `index.html` `<head>`):
  ```html
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Source+Serif+4:ital,opsz,wght@0,8..60,400;0,8..60,500;0,8..60,600;0,8..60,700;1,8..60,400&family=Hanken+Grotesk:wght@400;500;600;700&display=swap" rel="stylesheet">
  ```

### Type scale (used in mocks)
| Role | Font / weight | Size | Notes |
|---|---|---|---|
| Page / note title | Serif 600 | 30px | `letter-spacing:-0.01em` |
| Hero metric value | Serif 600 | 33px | tabular, `line-height:.9` |
| Section title | Serif 600 | 18–20px | |
| Caption (italic) | Serif italic 400 | 13–15px | muted |
| Section label | Sans 600 | 10.5px | `letter-spacing:0.14–0.16em`, uppercase |
| Body / UI | Sans 400–500 | 13–14.5px | `line-height:1.55` |
| Table value | Serif/Sans | 13–15px | tabular |

### Radius / shadow / lines
- Radius: cards `8px`, buttons & inputs `5px`, tags `4px` (squarer = more institutional).
- Shadow (light): `0 1px 2px rgba(40,35,20,.05), 0 12px 30px -20px rgba(40,35,20,.18)` — soft, sparing.
- **Prefer hairline rules + whitespace over boxes.** Metric groups are separated by 1px
  vertical `--border` rules, not individual cards.

---

## Assets
- `assets/favicon.svg` — drop-in replacement for `public/favicon.svg` (viridian tile, paper
  meridian mark, rounded 7px).
- `assets/BrandMark.tsx` — drop-in replacement for `src/components/BrandMark.tsx`. Same
  `{ size }` API and `currentColor` behavior as the old mark, so `Header.tsx` and the
  empty-state tile keep working; only the glyph changes (meridian circle + zenith node).
- App icon / header tile: viridian `#15694E` background, mark stroked in paper `#F7F5EF`.

---

## Screens / Views

### 1. App header (`src/components/Header.tsx`)
- **Layout:** unchanged — flex row, space-between, `padding: 15px clamp(14px,1.6vw,28px)`,
  `background: var(--header-bg)`, `border-bottom: 1px solid var(--border)`. Drop the heavy
  `box-shadow` (use none or the soft `--shadow`).
- **Brand lockup:** 34px viridian tile (radius 7) holding `<BrandMark size={22}>` in paper,
  then the wordmark **"Mercator" in Source Serif 4, 600, 19px, ink** (NOT uppercase tracked).
  Drop the small "STRUCTURED PRODUCTS" eyebrow or keep it tiny in sans 8.5px/0.18em uppercase muted.
- **Instrument readout:** vertical hairline divider, then issuer name (sans 13px 600) + tickers
  + "· SX5E / SPX / NKY · 3Y worst-of" in sans 12.5px `--text-muted`.
- **Right cluster:** "As of <date>" (sans 12px faint) · status `Priced` (viridian dot + label)
  · EN/ES + theme toggle as the segmented pill (see Components). **Remove the ticker/run
  "engine · paths" mono readout** — it's a terminal cue.

### 2. Setup rail (`src/components/SetupRail.tsx`, in `Panel`)
- Calm vertical form. Each term as a label/value row separated by a `--hairline` rule:
  label sans 12.5px `--text-muted` left, value serif 15px ink right (tabular). Inputs use the
  new 5px-radius style. Primary "Run simulation" = `.btn--primary` full-width.

### 3. Note structure / metrics (main column)
- **Section dividers:** use `.section-rule` — numbered small-caps label ("II · Risk & Returns")
  + hairline + italic serif caption.
- **HeroMetrics (`src/components/HeroMetrics.tsx`):** replace the 4 separate `.card` boxes with
  ONE row of 4 figures separated by vertical `--border` rules (a single bordered strip, or
  borderless with dividers). Each: label (sans 9.5px/0.1em uppercase muted) → value
  (**serif 33px 600 tabular**, color `--accent` for IRR-positive, `--red` claret for
  knock-in/negative, `--text` for neutral) → hint (sans 11.5px faint). No glow, no tone-colored boxes.
- **Tables (ObservationSchedule, MCTables):** hairline tables — header row sans 9.5px/0.06em
  uppercase muted on `--surface-2`, body rows serif 14px tabular with `1px var(--hairline)`
  row separators; right-align numerics; coupons in `--accent`, losses in `--red`.

### 4. Tabs (`src/components/Tabs.tsx`)
- Editorial underline tabs: active = ink/viridian text 13px 600 with a `2px solid var(--accent)`
  bottom border (`margin-bottom:-1px` over a `1px var(--border)` track); inactive = `--text-muted`,
  no border. Drop the chart icon on Report or keep it small.

### 5. States (Monte-Carlo panel area)
- **Empty:** centered 46px `--accent-weak` tile with the mark in viridian, serif 18px title
  "No simulation yet", sans 12.5px muted body, `.btn--primary` "Run simulation".
- **Running (`RunProgress`):** serif 17px "Pricing 50,000 paths…", a determinate **3px hairline
  bar** (`--border` track, `--accent` fill), sub-line sans 11px faint + `%`. No spinner.
- **Stale (`stale_banner`):** the ochre notice — `--amber-weak` bg, `1px #ECDFC4` border, radius 6,
  ochre dot, sans 13px ink message, `.btn--link` "Re-run" on the right.
- **Error:** `--red` claret text, same calm banner shell.

### 6. Supporting elements (see `references/Mercator — Elements.dc.html`)
Stepper (Terms → Simulate → Report, nodes on a meridian line, current node haloed with
`--accent-weak`); status **tags** (`.tag--accent/warn/neutral/outline`); **segmented control**
(viridian-filled active segment in a `--border-strong` pill) for Light/Dark & EN/ES; **outcome
distribution meter** (one horizontal stacked bar: autocall `--accent` / coupon `#7EB4A0` /
loss `--red`, with a sans+serif legend) — a calmer replacement for multiple charts; **inline
sparkline** (1.6px `--accent` polyline + end dot + hairline baseline) beside single figures;
**key-terms** definition list; **tooltip** (ink `#1C241F` card, serif title, paper text);
**footer** (mark + "Mercator" + version + fine print in sans 10.5px faint).

---

## Interactions & behavior
Unchanged from the current app. Notes:
- Theme toggle still flips `[data-theme]` on `<html>` (keep `ThemeProvider`); light is now the default.
- Transitions stay subtle: `background/color 0.12–0.2s ease`. No glows, no pulsing.
- Charts (Plotly, `src/lib/plotlyTheme.ts`): retheme to paper/ink — `paper_bgcolor` & `plot_bgcolor`
  transparent, gridlines `--hairline`, axis text `--text-muted` in Hanken, primary series `--accent`,
  negative/loss series `--red`, font family Hanken Grotesk. Remove dark-navy plot styling.

## State management
No new state. Reuse existing `terms`, `opts`, `result`, `status`, tab, and theme state.

## Files in this bundle
- `tokens/mercator.css` — drop-in replacement for `src/index.css`
- `assets/favicon.svg` — drop-in replacement for `public/favicon.svg`
- `assets/BrandMark.tsx` — drop-in replacement for `src/components/BrandMark.tsx`
- `references/Meridian — Editorial.dc.html` — style guide + composed full screen (open in browser)
- `references/Mercator — Elements.dc.html` — the 12 supporting elements (open in browser)
- `references/support.js` — runtime for the two reference files (don't ship; reference only)

## Implementation order (suggested)
1. Add the font `<link>` to `index.html`; replace `src/index.css` with `tokens/mercator.css`.
2. Swap `BrandMark.tsx` and `public/favicon.svg`; set the wordmark to "Mercator" (serif) in `Header.tsx`.
3. Convert `.mono` numerics → `.figure` / `.tnum`; let `h1/h2/h3` pick up the serif.
4. Rework `HeroMetrics` to the hairline metric strip; retheme tables.
5. Editorial tabs; the empty / running / stale states.
6. Retheme Plotly. Then layer in the supporting elements (stepper, tags, outcome meter, sparkline) where useful.
