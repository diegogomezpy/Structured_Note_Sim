# Data Schema — CADIEM Structured-Note Report

The report is generated from two inputs: a **brand config** (constant across notes) and **per-note data** (the analytics). In the prototype these are merged in `report-content.js` as `window.RPT = { shared, en, es }`. Below is the production-shaped model.

---

## 1. Brand config — `branding_cadiem.json` (client-provided, constant)
```jsonc
{
  "firm_name": "CADIEM Casa de Bolsa",
  "primary_color": "#007953",
  "accent_color": "#2E7E8C",
  "chart_secondary_color": "#1C5566",
  "section_rule_color": "#D0D52E",     // lime (we use #CBD61E in design)
  "panel_color": "#ECF1F6",
  "logo_base64": "…",                   // green logo (light bg)
  "cover_logo_base64": "…",             // white logo (dark bg)
  "cover_image_base64": "…",            // cover photo (jpg)
  "cover_sigil_base64": "…",            // arcs motif
  "title_font": "Neulis Alt",
  "title_font_files": { "Bold": "…ttf base64" },
  "body_font": "Gantari",
  "body_font_files": { "Regular": "…", "Bold": "…", "Italic": "…", "BoldItalic": "…" },
  "cover_overlay_color": "#007953",
  "cover_overlay_opacity": 0.75,
  "report_title": { "es": "Nota Estructurada", "en": "Structured Note" },
  "website": "www.cadiem.com.py",
  "footer_note": { "es": "Solo a título informativo…", "en": "For informational purposes only…" },
  "disclaimer_body": { "es": "El presente documento…", "en": "This document is strictly…" }
}
```
> The disclaimer also has a bold second paragraph ("This document is a commercial communication…" / "Este documento constituye una comunicación comercial…"). Keep both paragraphs.

---

## 2. Per-note data
```jsonc
{
  "language": "en",                      // "en" | "es" — or generate both
  "sections": {                          // modularity toggles
    "noteTerms": true, "issuer": true, "underlyings": true,
    "monteCarlo": true, "backtest": true, "currentPerf": true
    // cover, summary, glossary, disclaimer are always rendered
  },

  "product_name": "BNP Paribas PR00529720",
  "product_long": "12M Quarterly Phoenix One Star (DELL / IBM / MSFT)",
  "date_label": "26 Jun 2026",
  "issue_date": "2026-06-17",
  "issuer": { "name": "BNP Paribas", "blurb_en": "…", "blurb_es": "…",
              "ratings": [["S&P","A+"],["Moody's","A1"],["Fitch","AA-"]] },

  "terms": {
    "maturity": "1Y quarterly", "coupon_pa": "16.00%",
    "coupon_barrier": "50.0%", "memory_coupon": true,
    "autocall_barrier": "100%", "first_autocall_obs": "P1",
    "knockin_barrier": "50.0%", "coupon_rule": "worst-of",
    "autocall_rule": "worst-of", "one_star_level": "100%"
  },
  "observation_schedule": [["P1","0.25","100%"],["P2","0.50","100%"],["P3","0.75","100%"],["P4","1.00","100%"]],
  "note_description_en": "This Investment (the Note)…",   // long paragraph, EN + ES
  "model_methodology_en": "Multi-asset Heston…",           // EN + ES

  "underlyings": [
    { "name": "Dell Technologies Inc.", "ticker": "DELL", "color": "#007953",
      "sector": "Equity · Technology", "market_cap": "$264.6B", "vol_3m": "89.5%",
      "last_price": "409.45", "rsi": "60", "desc_en": "…", "desc_es": "…",
      "price_series": [ /* trailing-12m closes for the line chart */ ] },
    { "name": "International Business Machines", "ticker": "IBM", "color": "#2E7E8C", "...": "…" },
    { "name": "Microsoft Corporation", "ticker": "MSFT", "color": "#9AA80F", "...": "…" }
  ],

  "monte_carlo": {
    "paths": 20000,
    "metrics": { "expected_irr": "15.27%", "total_return": "4.35%",
                 "p_autocall": "97.7%", "p_knockin": "0.83%",
                 "loss_given_knockin": "-58.54%" },
    "outcome_breakdown": [   // Figure 1 (stacked bar) — share of paths, must sum to 100
      {"label":"Autocalled P1","value":86.03},{"label":"Autocalled P2","value":7.56},
      {"label":"Autocalled P3","value":2.73},{"label":"Autocalled P4","value":1.34},
      {"label":"Redeemed at par","value":1.51},{"label":"Knocked in","value":0.83}
    ],
    "outcome_summary": [     // Figure 2 (dual panel) — probability + mean return by outcome
      {"outcome":"Autocalled","prob":97.7,"total_return":4.7,"irr":15.9},
      {"outcome":"Held to maturity","prob":1.5,"total_return":16.0,"irr":16.0},
      {"outcome":"Capital loss","prob":0.8,"total_return":-58.5,"irr":-58.5}
    ],
    "autocall_by_period": [["P1","0.25","86.03%"],["P2","0.50","7.56%"],["P3","0.75","2.73%"],["P4","1.00","1.34%"]]
  },

  "backtest": {
    "issue_dates_tested": 106,
    "metrics": { "mean_irr": "16.00%", "total_return": "4.42%",
                 "autocall_rate": "100.0%", "knockin_rate": "0.0%", "irr_if_knockin": "—" },
    "outcomes_by_count": [   // Figure 3 (vertical count bars) — counts sum to issue_dates_tested
      {"label":"Autocalled P1","count":97},{"label":"Autocalled P2","count":7},{"label":"Autocalled P3","count":2}
    ]
  },

  "current": {
    "metrics": { "worst_of_today": "93.1%", "worst_asset": "Microsoft Corp",
                 "coupon_irr_to_date": "0.00%", "elapsed_years": "0.02" },
    "asset_performance": [["Dell Technologies Inc","97.65%"],
                          ["International Business Machines","98.44%"],
                          ["Microsoft Corp","93.12%"]],
    "observation_history": [["P1","2026-09-17","Upcoming"],["P2","2026-12-17","Upcoming"],
                            ["P3","2027-03-17","Upcoming"],["P4","2027-06-17","Upcoming"]],
    "perf_since_issue": { /* per-asset short series + worst-of for Figure 4 */ }
  },

  "glossary": [ ["Autocallable note","A structured note that…"], /* ~18 term/definition pairs, EN + ES */ ]
}
```

## Summary-page derived values
The first-page KPI strip and Payoff Scenarios panel are **derived** from the above:
- KPIs: `monte_carlo.metrics.expected_irr`, `monte_carlo.metrics.p_autocall`, `monte_carlo.metrics.p_knockin`, `backtest.metrics.mean_irr`.
- Payoff Scenarios rows = `monte_carlo.outcome_summary` (label, prob, irr) color-mapped green/teal/amber.
- Executive Summary = 3–4 generated bullets (see sample copy in `report-content.js` → `en.execBullets` / `es.execBullets`).

## Bilingual rule
Every human-readable string exists in both `en` and `es`. Section headings, table headers, captions, glossary, disclaimer, footnote — all localized. Numbers/tickers are language-neutral (note ES uses comma decimals in prose, e.g. "15,3%").
