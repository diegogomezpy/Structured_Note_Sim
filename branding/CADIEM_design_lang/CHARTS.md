# Charts & Figures — Specifications

All figures keep the **same type and encoding as the original generator**; only the palette/style changed (green-forward CADIEM palette). In the prototype each is a pre-rendered SVG string in `report-charts.js` (`window.REPORT_CHARTS`). Reproduce them in your stack (HTML/SVG or restyled matplotlib). Shared style: font **Gantari**; gridlines `#E6EBE8`; axis text `#8B97A0` ~9–10px; downside uses amber `#C9772D`/`#9A7B12` (never red).

## Palette for series
- Primary green `#007953`, deep `#0B3D2E`, emerald `#2BC275`, teal `#2E7E8C`, olive `#9AA80F`, lime `#CBD61E`.
- Underlying series: DELL `#007953`, IBM `#2E7E8C`, MSFT `#9AA80F`.
- Band fills (fans/areas): light green tints `#D5EBDE`, `#9BD8B4`.

---

### Trailing 12-month price (one per underlying — pages in Underlying Breakdown)
- **Type:** single-series line + soft area fill (gradient of the series color, 0.22→0 alpha).
- **Axes:** x = months (Jul…May, 6 ticks); y = price (4 gridlines, auto-scaled to series ±1.5%).
- **Data:** `underlyings[i].price_series` (trailing-12m daily/we­ekly closes). Last point gets a filled dot.
- **Color:** the underlying's series color.

### Figure 1 — Outcome breakdown (Monte Carlo, page 1)
- **Type:** single **100%-stacked horizontal bar** ("Share of paths").
- **Segments (in order):** Autocalled P1 `#0B3D2E`, P2 `#0F5E3C`, P3 `#007953`, P4 `#2BC275`, Redeemed at par `#CBD61E`, Knocked in `#C9772D`. White 1px separators. % labels shown on segments ≥5%.
- **Legend:** below, 3-per-row swatch + label. X axis 0–100%.
- **Data:** `monte_carlo.outcome_breakdown` (values sum to 100).

### Figure 2 — Outcome detail (Monte Carlo, page 2)  *(caption: "Distribution of simple annualised IRR…")*
- **Type:** **dual panel**.
  - Left "Probability": vertical bars for Autocalled / Held to maturity / Capital loss (emerald / forest / amber), value labels on top, y 0–100%.
  - Right "Mean return by outcome": grouped bars, two series per outcome — **Total return** `#0B3D2E` and **IRR p.a.** `#2E7E8C` — with a 0% baseline (bars go negative for Capital loss), value labels.
- **Legend:** Total return / IRR p.a. centered below.
- **Data:** `monte_carlo.outcome_summary`.

### Figure 3 — Historical outcomes by issue date (Backtest)
- **Type:** **vertical count bar chart**. y = "Count", x = "Outcome".
- **Bars:** Autocalled P1/P2/P3 with a green gradient (`#2BC275` → `#007953` → `#0B3D2E`); count label on/above each bar; counts sum to `backtest.issue_dates_tested`.
- **Data:** `backtest.outcomes_by_count`.

### Figure 4 — Underlying performance since issue (Current Performance)
- **Type:** **multi-line** "Performance vs Issue Date".
- **Series:** Dell / IBM / MSFT as thin **dashed** lines in their series colors; **Worst-of** as a thick solid `#0B3D2E` line.
- **Reference lines:** Autocall barrier 100% (grey dotted, labeled) and Knock-in barrier 50% (amber dashed, labeled). Vertical dotted markers P1–P4 at the future observation dates; a solid "Today" vertical near the left (window is short — most of the canvas is future).
- **Axes:** y 45–107%; x Jul 2026 … May 2027. Legend below.
- **Data:** `current.perf_since_issue` + barriers from `terms`.

### Structure Diagram (Note Terms, page 1)
- **Type:** schematic timeline, issue → maturity (1 year), 4 quarterly observation points.
- **Elements:** horizontal level bands — capital-at-risk tint below 50%, protected tint 50–100%; dashed level lines at **100%** (Autocall / One-Star, green) and **50%** (Coupon / Knock-in, amber) with right-side labels; an illustrative teal "worst-of level" path; an upward **+4.00% coupon arrow** at each of P1–P4 (emerald); a lime "Autocall window" marker spanning P1→maturity; endpoint labels "Issue · Jun 2026" and "Maturity · Jun 2027".
- **Data:** derived from `terms` + `observation_schedule` (coupon per period = coupon_pa / periods).

### Summary mini "Payoff Scenarios" (first page — NOT a chart)
- A small **text panel**, not a figure: three rows (Autocalled / Held to maturity / Capital loss) each with a color dot, label, probability, and IRR p.a., color-mapped green / teal / amber. Data = `monte_carlo.outcome_summary`.

---

## Hexagon decorations (not data — brand graphic)
Generated in `report-charts.js` as `hexGreenA/B/C` (green clusters for light pages) and `hexWhite` (for the dark masthead). Each is an SVG of **2–3 rectangular-chamfer hexagons** (rounded; cut top-right + bottom-left) at varied sizes — outlines plus one filled lime shape. Placement rules: behind content (`z-index:-1`, page has `isolation:isolate`), only in empty space, bleeding off a page edge, never over text or the footnote. Vary the cluster per page.

Generator for the chamfer path (W×H, chamfer `c`, round `q`, corner radius `r`):
```js
function hexPath(W,H,c,q,r){ const s=q*0.7071; return [
  `M ${r} 0`,`L ${W-c-q} 0`,`Q ${W-c} 0 ${W-c+s} ${s}`,`L ${W-s} ${c-s}`,`Q ${W} ${c} ${W} ${c+q}`,
  `L ${W} ${H-r}`,`Q ${W} ${H} ${W-r} ${H}`,`L ${c+q} ${H}`,`Q ${c} ${H} ${c-s} ${H-s}`,
  `L ${s} ${H-c+s}`,`Q 0 ${H-c} 0 ${H-c-q}`,`L 0 ${r}`,`Q 0 0 ${r} 0`,`Z` ].join(' '); }
```
Use it for `clip-path: path('…')` on solid panels (banners, chips, masthead) and as `<path d="…">` for outline decorations.
