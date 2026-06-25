# Streamlit App — Feature Catalog & Port Status

Authoritative checklist of every user-facing feature in the original Streamlit app
(`app/app.py`), tracking what the FastAPI + React port (`api/` + `web/`) has.

Legend: ✅ done in React · 🟡 intentional difference · ⬜ genuinely missing.

**Audited 2026-06-24.** The port is essentially feature-complete; what was a long
⬜ list is now almost entirely ✅. The genuine remaining gaps are collected here:

## Remaining gaps (act before the hosting switchover)
1. ⬜ **Run memory guard + path cap (API).** Streamlit refused a run whose projected
   peak RAM exceeded physical RAM (`app.py:_sim_peak_gb`) and capped paths at 15 000
   on Cloud (`_MAX_PATHS`). The FastAPI backend enforces **neither** — a 250 000-path
   request could OOM the Cloud Run instance once React is the hosted app. Highest
   priority for the switchover.
2. ⬜ **`store_on_disk` toggle.** Streamlit could memory-map the retained path arrays
   to lower RAM (`app.py:360`). Not ported — purely a memory/perf option.
3. ⬜ **Live RAM estimate / warning in the UI.** Streamlit showed projected peak RAM
   before a run. The React engine panel has paths/seed/engine/calib but no estimate.
4. ⬜ **`principal_protection` edit control.** Loads from JSON, is in the blank-note
   default and the add-note tutorial, but has no slider in `SettingsOverlay` (rarely
   changed; default 1.0). Add to the Protection group if desired.
5. 🟡 **Off-grid maturity precision.** React maturity is a 0.25y-step slider; configs
   with arbitrary tenors load fine but snap if the slider is touched. Streamlit kept
   exact off-grid values. Switch to a number input if exact tenors must be editable.

Everything below is ✅ unless marked otherwise.

---

## 1. Global / chrome
- 🟡 Single living page (no separate setup↔dashboard navigation) — by design.
- ✅ Language toggle EN/ES; ES auto-translates Yahoo issuer + underlying descriptions.
- ✅ Sidebar: note name/issuer header, download-config, build-report panel, Generate
  PDF, Run. Branding is loaded via a preset dropdown in the report panel.
- 🟡 Branding: manual preset dropdown (auto-discovers `branding/*.json`) instead of
  Streamlit's auto-load-once-per-session — explicit by choice.
- ✅ `_MAX_UNDERLYINGS = 5` enforced (`UnderlyingPicker`). ⬜ `_MAX_PATHS` cap — see gap #1.

## 2. Setup (React `SettingsOverlay` + `SetupRail`)
- ✅ JSON term-sheet upload (`/api/config/parse`) with inverted-ticker fix + unknown→custom.
- ✅ Underlyings: universe picker (max 5), inline custom-ticker add, per-underlying
  custom logo upload, editable descriptions + **Prefill from Yahoo**, analyst buy/hold/sell.
- ✅ Note-type picker (`lib/noteType`): pre-fills defaults, never hides fields.
- ✅ Schedule: maturity slider + frequency. (🟡 off-grid precision — gap #5.)
- ✅ Coupon: coupon p.a., coupon barrier, **coupon basket**, memory toggle.
- ✅ Protection: knock-in barrier, capital-protection toggle + guarantee% + upside cap,
  One-Star overlay toggle + level. ⬜ `principal_protection` control — gap #4.
- ✅ Autocall: barrier, start period, **autocall basket**, step-down %, floor %,
  premium-at-call. Step-down hurdle is drawn in the note diagram.
- ✅ Metadata: name, issuer, S&P/Moody's/Fitch ratings, issue date, issuer logo.
- ✅ Engine: paths, seed, numpy/cpp, calibration window (1/2/3/5/10y). ⬜ store-on-disk,
  ⬜ live memory estimate — gaps #2/#3.

## 3. Note structure / term-sheet display
- ✅ Two-line header with issuer badge.
- ✅ Collapsible underlying breakdown cards (market cap, IV/realized vol, last price,
  RSI, description, 1Y chart; lazy-prefetched) + downloadable as a report-styled PNG.
- ✅ Collapsible issuer card (logo, ratings, auto-loaded + translated description).
- ✅ Observation schedule table.
- ✅ Level-ladder note diagram (value axis, barriers as gridlines, callable markers,
  step-down hurdle) — no Streamlit equivalent.

## 4. Monte Carlo tab
- ✅ Summary (expected IRR/total/coupon, P(autocall), P(KI), loss-given-KI, hero metrics
  + waterfall), autocall-by-period table.
- ✅ IRR distribution, worst-of fan + per-asset fans.
- ✅ Path explorer: filter chips, resample, zoom, **comparison panels**, **rich
  per-observation legend**, per-path metrics (principal/coupons/IRR), per-asset
  final-perf, single-path step (random/prev/next), coupon-period filter.
- ✅ Correlation input/realized/difference heatmaps + calibrated Heston parameter table.
  ⬜ minor: effective basket correlation + gap line.

## 5. Historical backtest tab
- ✅ Outcomes: mean IRR, autocall%, KI%, loss-given-KI, outcome bar, issue table,
  worst-asset pie, IRR scatter.
- ✅ Prices: weekly history with issue-window markers.
- ✅ Backtest path explorer (panels, filters incl. IRR band, historical worst-of via
  `replay_note`).
- ✅ Issue-date range filter (start/end + Apply) with context reset.

## 6. Current performance (live) tab — ✅ ported
- `LivePanel` via `/api/live`: lifecycle bar, worst-of today/vs-strike, worst asset,
  KI/autocall buffers, per-asset cards, observation history, pending-memory/growth info,
  coupon-IRR-to-date, live chart. Auto-disabled when no issue date.

## 7. PDF / report builder — ✅ ported
- `ReportPanel` via `/api/report`: master/sub section tree (Note/MC/Backtest/Live),
  runs only requested flows, branded PDF. ✅ branding presets + all branding fields
  (colours, logo, website, contact, disclaimer), custom logo overrides,
  issuer/underlying-description prefill. Generate works without running the sim first.

## 8. Structural invariants (unchanged)
- `core/note.py:price_note` is the single payoff engine; `replay_note` the single source
  of truth for live/explorer per-observation status. Observation dates calendar-snapped.
- Memory: float16 path storage + precomputed bands (engine reused). The **run-time
  memory guard itself is not in the API** — gap #1.

Source refs: chart builders `app/charts.py`; PDF `app/pdf_report.py`; ticker universe
`app/underlyings.py`; UI strings `app/translations.py` + `web/src/i18n/strings.ts`.
