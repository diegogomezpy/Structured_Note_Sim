# Handoff: CADIEM Structured-Note Report (Aesthetic Redesign)

## Overview
This is an **aesthetic redesign of CADIEM Casa de Bolsa's automated structured-note PDF report** (e.g. "12M Quarterly Phoenix One Star — DELL / IBM / MSFT"). The report is generated per-note and presents a quantitative analysis: note terms, issuer, underlying breakdown, a Monte-Carlo simulation, a historical backtest, current performance, a glossary and a disclaimer.

The redesign keeps **all original information and chart types** — only the visual design changed. The goal of this handoff is to let you reproduce the look of these reference files inside CADIEM's existing report generator.

## About the Design Files
The files in `source/` are a **design reference built as an HTML "Design Component"** (a prototype showing the intended look), **not production code to ship directly**. **To view the complete sample report**, open `source/CADIEM Structured Note Report.dc.html` in a browser — keep it next to its sibling files (`support.js`, `report-content.js`, `report-charts.js`, `assets/`), which are all included in `source/`. It renders the full report (all sections, charts, both languages). Use the EN/ES toggle and the section toggles in the top control bar (that bar is screen-only and is hidden when printing/exporting to PDF).

Your task is to **recreate this design in CADIEM's existing report-generation stack**. The original reports appear to be produced by a Python pipeline (matplotlib charts embedded as PNGs, page text laid out and rendered to PDF). The most faithful path is an **HTML-template → PDF** approach (e.g. Jinja2 + WeasyPrint/Playwright/Puppeteer), because the layout relies on CSS the design already expresses. If you keep matplotlib for charts, restyle them to the palette in this doc; if you move charts to HTML/SVG, the specs in `CHARTS.md` describe each one exactly.

## Fidelity
**High-fidelity.** Final colors, typography, spacing, shapes and layouts. Reproduce pixel-closely. Exact tokens are in the Design Tokens section.

---

## Page Format
- **A4 portrait**, 794 × 1123 px at 96dpi (= 210 × 297 mm). Print CSS uses `@page { size: A4; margin: 0 }`.
- Each page = one `<section class="rpt-page">`, `padding: 52px 56px 64px`, white background, with a footer pinned to the bottom.
- A page break is forced after every page (`break-after: page`).
- Page numbering: cover is page 1; every following page shows `Page N / total` bottom-right. (In the prototype these are filled by JS at runtime; in a server generator, compute them from the active section set — see Modularity.)

## Report Structure (page order)
1. **Cover** — full-bleed photo + green overlay (immersive).
2. **Summary / At-a-glance** (always on).
3. **Note Terms** — Description + structure diagram (toggleable group, 2 pages).
4. **Issuer Information** (toggleable, 1 page).
5. **Underlying Breakdown** — one page per underlying (toggleable, N pages).
6. **Monte Carlo** — Payoff & Distribution (toggleable, 2 pages).
7. **Historical Backtest** — Outcomes & Summary (toggleable, 1 page).
8. **Current Performance** (toggleable, 1 page).
9. **Glossary of Terms** (always on).
10. **Disclaimer** — immersive green page (always on).

## Modularity (important)
The report is **modular**: the client picks which sections appear. Always-on: Cover, Summary, Glossary, Disclaimer. Toggleable groups: Note Terms, Issuer, Underlyings, Monte Carlo, Backtest, Current Performance. The layout must reflow and re-number pages for any on/off combination. Section **numbers** (01–06) are fixed identifiers on the section heads; page numbers are dynamic.

In the prototype, toggles live in `Component` state (`state.show`) and language in `state.lang`; in a generator these become build parameters.

---

## Two-Tier Section-Head System
There are two deliberate header treatments — this hierarchy is intentional:

**A. Primary section head (analytical sections: Monte Carlo, Backtest, Current Performance)** — a bold full-width **dark-green hexagon banner**:
- Shape: rectangular chamfer (cut top-right + bottom-left corners, **rounded**). 682 × 118 px. CSS `clip-path: path('M 12 0 L 649 0 Q 656 0 660.95 4.95 L 677.05 21.05 Q 682 26 682 33 L 682 106 Q 682 118 670 118 L 33 118 Q 26 118 21.05 113.05 L 4.95 96.95 Q 0 92 0 85 L 0 12 Q 0 0 12 0 Z')`
- Background `#0B3D2E`. Contains: big section number in `#CBD61E` Neulis 46px, a 1px white-22%-opacity divider, a lime kicker (uppercase, .22em tracking), and a white Neulis 32px heading. A faint white hexagon-cluster watermark (opacity .18) sits top-right inside.

**B. Secondary section head (reference sections: Note Terms, Issuer, Underlyings)** — a light, smaller header:
- A 46 × 46 px **lime chamfer chip** (rounded hexagon, `clip-path: path('M 9 0 L 30 0 Q 34 0 36.83 2.83 L 43.17 9.17 Q 46 12 46 16 L 46 37 Q 46 46 37 46 L 16 46 Q 12 46 9.17 43.17 L 2.83 36.83 Q 0 34 0 30 L 0 9 Q 0 0 9 0 Z')`, background `#CBD61E`) holding the section number in `#0B3D2E` Neulis 20px.
- Next to it: a green uppercase kicker (`#007953`, .18em tracking) over a dark-green Neulis 23px title.
- Sits on a thin rule (`1px solid #C9D2CC`).

**Section heading copy** (institutional, not questions):
| Section | EN | ES |
|---|---|---|
| Monte Carlo | Projected Outcomes | Resultados Proyectados |
| Backtest | Realised Outcomes | Resultados Históricos |
| Current Performance | Position to Date | Posición a la Fecha |

---

## The CADIEM "Hexagon" Shape
The brand's signature shape is a **rectangular chamfer** — a rectangle with the top-right and bottom-left corners cut at 45°, and **all corners rounded** (NOT a regular 6-sided hexagon). Source assets: `assets/` (the originals were `element3.png` light, `element5.png` dark green). It is used for: section-head banners, number chips, and decorative watermarks.

**Decorations:** faint clusters of varied-size chamfer-hexagons fill genuinely empty page regions (Issuer lower area, Backtest below the chart). Rules: they must sit **behind** content (`z-index:-1` with `isolation:isolate` on the page) and must **never overlap any text or the footnotes** — only blank space, bleeding off a page edge. Use varied sizes/arrangements page-to-page (three cluster variants exist: `hexGreenA/B/C` in `report-charts.js`).

---

## Cover & Disclaimer (immersive green pages)
Both use the same treatment: full-bleed `assets/cover.jpg`, a `#007953` overlay at **0.75–0.80 opacity**, a dark-green gradient for legibility, the **white** logo (`assets/cover-logo.png`), a lime rule, and a faint white arcs/hex motif. The disclaimer body sits in a `rgba(8,46,34,.78)` rounded panel with white justified text (second paragraph bold). Footer: lime website + grey copyright.

---

## The First Page (Summary) — layout detail
This is the most designed page; reproduce carefully.
1. **Header**: green logo left, `Structured Note · 26 Jun 2026` right, `2px solid #007953` rule.
2. **Masthead**: a dark-green (`#0B3D2E`) hexagon panel (`clip-path: path()`, 682 × 232 px) containing a lime kicker, white Neulis 34px product title, a `#9fc4b3` sub-line, and a 4-column **KPI strip** divided by a top hairline — each KPI has a `2px solid #CBD61E` left keyline, an uppercase `#9fc4b3` label and a white Neulis 25px value. A faint white hex cluster (opacity .18) decorates the top-right.
   - KPIs: Expected IRR p.a. `15.27%` · P(autocall) `97.7%` · P(knock-in) `0.83%` · Mean historical IRR `16.00%`.
3. **Two columns**: left = **Executive Summary** (lime rule + bullet list); right = a **panel rail** (`#ECF1F6`, `border-top:4px solid #007953`, radius 10) listing the three underlyings (colored ticker chips + names), a divider, then the key-terms list.
4. **Two columns (lower)**: left = **About This Report** caption + a **Payoff Scenarios** panel (`#ECF1F6`, green top rule) — three rows (Autocalled 97.7% +15.9%, Held to maturity 1.5% +16.0%, Capital loss 0.8% −58.5%) color-coded green/teal/amber, with `Probability` / `IRR p.a.` column headers; right = **In This Report** numbered contents list.

---

## Design Tokens

### Colors
| Token | Hex | Use |
|---|---|---|
| Ink / darkest green | `#0B3D2E` | Masthead, banners, headings |
| Primary green | `#007953` | Rules, primary accents, brand |
| Emerald | `#2BC275` | Secondary chart/series |
| Teal | `#2E7E8C` | Tertiary accent / IBM series |
| Olive | `#9AA80F` / `#CBD61E` lime | Highlight, keylines, chips, MSFT series |
| Amber (downside) | `#C9772D` / `#9A7B12` | Knock-in / capital-loss (brand has no red) |
| Panel | `#ECF1F6` | Card / tile backgrounds |
| Panel green tint | `#EEF4EF` | Alt panel |
| Body text | `#243B33` / `#42514a` | Paragraphs |
| Muted | `#8B97A0` / `#A6B0B8` | Labels, captions, footnotes |
| Hairline | `#E3E8EC` / `#DDE5EA` / `#C9D2CC` | Rules, borders |
| Chart grid | `#E6EBE8` | Gridlines |

### Asset (underlying) series colors
DELL `#007953` · IBM `#2E7E8C` · MSFT `#9AA80F`.

### Typography
- **Headings/display:** **Neulis Alt** (700). Files: `assets/NeulisAlt-Bold.ttf`. Used for titles, numbers, stat values.
- **Body/UI:** **Gantari** (400/700, italic). Files: `assets/Gantari-*.ttf`. Used for all body, labels, captions.
- Cover title ~38–52px; section-head heading 32px; page titles 23–26px; KPI values 25–26px; body 12–12.5px; captions/labels 10–11px (uppercase, .12–.22em tracking); footnotes 8.5px.

### Other
- Radius: cards `10px`, small chips/figures `4–6px`, masthead/banners use chamfer clip-path (corner radius ~12–16 baked into the path).
- Footnote (every interior page, bottom): the bilingual disclaimer micro-text left, page number right, above a `1px #E3E8EC` rule.

## Assets (in `source/assets/`)
- `logo.png` — green CADIEM logo (light backgrounds).
- `cover-logo.png` — white CADIEM logo (dark/photo backgrounds).
- `cover.jpg` — skyscraper cover photo (cover + disclaimer).
- `cover-sigil.png` — concentric-arcs motif (used faintly; the hexagon clusters are generated, see CHARTS.md).
- `NeulisAlt-Bold.ttf`, `Gantari-Regular/Bold/Italic.ttf` — embedded brand fonts.
All of these are also delivered base64-encoded inside the client's `branding_cadiem.json` (see DATA_SCHEMA.md).

## Charts / Figures
All figure types match the originals 1:1 (restyled to the green palette). Full per-figure specs (type, axes, encodings, data, exact colors) are in **`CHARTS.md`**.

## Data Model
The report is data-driven. The full input schema — brand config + per-note data that feeds every page — is in **`DATA_SCHEMA.md`**. In the prototype this data lives in `source/report-content.js` (`window.RPT` = shared data + `en`/`es` text) and `source/report-charts.js` (pre-rendered chart SVGs).

## Files in this bundle
- `source/CADIEM Structured Note Report.dc.html` — **the sample report + design template** (markup + a `Component` logic class at the bottom). Open in a browser to view the full rendered sample.
- `source/report-content.js` — bilingual copy + per-note data (`window.RPT`).
- `source/report-charts.js` — all figure SVGs + hexagon decorations (`window.REPORT_CHARTS`).
- `source/support.js` — the prototype's runtime (reference only; not needed in production).
- `source/assets/` — logos, fonts, cover photo, sigil.
- `DATA_SCHEMA.md` — input data model.
- `CHARTS.md` — figure-by-figure chart specifications.

## Implementation notes
- Reproduce the bilingual (EN/ES) capability: every string has both; the disclaimer/footnote ES copy is authoritative in `branding_cadiem.json`.
- The top control bar in the prototype is a **screen-only authoring aid** — do not ship it; expose language + section selection as generation parameters instead.
- Keep amber (not red) for downside elements to stay on-brand.
- Numbers in the sample (IRRs, probabilities, prices) are the real values from the reference note; wire them to the generator's computed outputs.
