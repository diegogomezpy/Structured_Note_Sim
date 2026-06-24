# Streamlit App — Exhaustive Feature Catalog (port reference)

This is the authoritative checklist of every user-facing feature in the original
Streamlit app (`app/app.py`, ~3172 lines), produced to drive the FastAPI + React
port (`api/` + `web/`). Each item notes the Streamlit control and an `app.py:LINE`
reference. Use the "port status" markers to track what the React app already has.

Legend: ✅ done in React · 🟡 partial · ⬜ not yet ported.

---

## 1. Global / chrome
- ⬜ Page config wide layout (`app.py:62-66`).
- 🟡 Theme/CSS — IBM Plex + navy/blue; custom card/chip/step-header components from `app/style.css` (`app.py:68-74`). (React has its own design system.)
- ✅ Language toggle EN/ES (sidebar radio, `app.py:660-662`) — full rerun rebuilds figures; ES auto-translates Yahoo descriptions.
- 🟡 Navigation setup↔dashboard (`app.py:1502`, `1670-1674`). (React is single-page; no separate setup page yet.)
- ⬜ Sidebar (dashboard): note name, issuer favicon, summary line, **download config** button, **branding JSON uploader** (+clear), build-report panel, **Generate PDF** button, Reconfigure, Run (`app.py:1594-1675`).
- ⬜ Branding auto-load from `branding/branding_*.json` once per session (`app.py:419-431`).
- 🟡 Path ceiling `_MAX_PATHS` (15000 cloud / 250000 local) + `_MAX_UNDERLYINGS=5` (`app.py:27-35`).

## 2. Setup page (`app.py:777-1579`)
- ⬜ **JSON config upload** with inverted-ticker auto-correction + unknown→custom registration (`app.py:784-842`).
- 🟡 **Underlyings**: universe multiselect (max 5) from ~50+ labels (`app.py:876-882`); ✅ chips with logos (read-only in React). ⬜ add-custom-ticker flow w/ toasts (`app.py:885-917`), ⬜ custom logo upload per underlying (`app.py:934-958`), ⬜ per-underlying descriptions + **Prefill from Yahoo** (`app.py:964-994`).
- ⬜ **Note-type picker** radio (phoenix/reverse_conv/growth_autocall/bonus_cert/capital_protected/custom) — pre-fills defaults, NEVER hides fields (`app.py:999-1100`).
- 🟡 Schedule: maturity selectbox (off-grid preserved), frequency selectbox (`app.py:1103-1132`). React has maturity slider + freq select.
- 🟡 Coupon: ✅ coupon p.a., ✅ coupon barrier; ⬜ coupon basket rule, ✅ memory toggle (`app.py:1135-1170`).
- ⬜ Protection/barriers: ✅ knock-in barrier; ⬜ min_return, ⬜ capital protection toggle + guarantee% + cap upside, ⬜ One Star overlay toggle+level (`app.py:1173-1243`).
- 🟡 Autocall: ✅ barrier, ✅ start period, ⬜ basket rule, ⬜ step-down %, ⬜ floor %, ⬜ premium-at-call, ⬜ barrier-schedule preview (`app.py:1246-1306`).
- ⬜ **Metadata expander**: note name, issuer (+favicon), issuer description+Prefill, S&P/Moody's/Fitch ratings, custom issuer logo upload, **issue date** + live/future feedback (`app.py:1311-1428`).
- 🟡 **Engine expander**: ✅ paths, ⬜ seed, ⬜ live memory estimate/warn, ✅ engine numpy/cpp, ⬜ store-on-disk, ⬜ calibration window radio (1/2/3/5/10y) (`app.py:1431-1494`).
- 🟡 Confirm/build → builds full `NoteTerms` with ALL fields (`app.py:1499-1579`).

## 3. Note structure / term-sheet display (`app.py:1707-1777`)
- 🟡 Two-line header w/ issuer badge (React header has this).
- 🟡 ✅ **underlying breakdown cards** (`UnderlyingCards.tsx` via `/api/underlyings/metrics`: market cap, 3M IV/realized vol, last price, RSI, description, 1Y price chart — lazy-loaded, collapsible). ⬜ issuer row (logo + description + rating metrics) (`app.py:1709-1751`).
- 🟡 Terms grouped metrics (React timeline + footer covers some).
- ✅ **Observation schedule table** (Period / Time / Autocall eligible) — `ObservationSchedule.tsx`.
- ✅ NEW in React: live visual note timeline (no Streamlit equivalent).

## 4. Monte Carlo tab (`app.py:2027-2427`) — 5 sub-tabs
- 🟡 Pre-run market-ready prefetch + run caption (`app.py:2029-2045`). React has staged progress.
- ✅ **Summary**: expected IRR/total/coupon, P(autocall), P(KI), loss-given-KI (React hero metrics + waterfall), ✅ **autocall-by-period table** (`MCTables.tsx`). ⬜ One-Star rescue caption.
- ✅ **Payoff/IRR**: IRR distribution chart (React: in Summary sub-tab). ⬜ knock-in info caption.
- ✅ **Paths**: worst-of fan + per-asset fans (React: Distributions sub-tab).
- ✅ **Path explorer** — React has filter chips (all/autocalled/held/KI) + resample + zoom. ⬜ MISSING vs original: up to 3 comparison panels, rich per-observation legend, per-path metrics (principal/coupons/IRR), per-asset final-perf cards, single-path step (random/prev/next), coupon-paid-period filter (`app.py:2150-2345`).
- 🟡 **Correlations & calibration**: ✅ input + realized heatmaps, ✅ **difference heatmap** (`corr_diff`), ✅ **calibrated Heston parameters table** (S₀/μ/V₀/θ/κ/ξ/ρ/Feller — `MCTables.tsx`). ⬜ effective basket correlation + gap (`app.py:2347-2427`).

## 5. Historical backtest tab (`app.py:2433-2827`) — 3 sub-tabs
- ✅ **Outcomes**: mean IRR, autocall%, KI%, loss-given-KI, outcome bar w/ per-period gradient, issue table, ✅ worst-asset pie, ✅ **IRR scatter** (React `BacktestPanel.tsx`).
- ✅ **Prices**: weekly downsampled price history w/ issue-window markers (React Prices sub-tab).
- ⬜ **Explorer**: backtest path explorer (3 panels, filters incl. IRR band, historical worst-of path via `replay_note`) (`app.py:2667-2827`).
- ⬜ Date-range pickers (start/end + Apply) w/ context-fingerprint reset (`app.py:2487-2548`).

## 6. Current performance (live) tab (`app.py:2833-3083`) — ✅ ported
- `LivePanel.tsx` via `/api/live` (`engine.run_live_api`, replay via `core.note.replay_note`): lifecycle progress bar, worst-of today + vs-strike, worst asset, KI/autocall buffers, per-asset cards, **observation history table**, pending-memory/growth-premium info, coupon-IRR-to-date, live performance chart. Auto-disabled when no issue date.

## 7. PDF / report builder (`app.py:1642-3172` + `pdf_report.py`) — ✅ ported
- `ReportPanel.tsx` via `POST /api/report` (`engine.build_report_pdf`): section toggle cards (MC / Calibration / Backtest / Live, all default ON), runs only requested flows, downloads the branded PDF. Reuses `app/pdf_report.py`. ⬜ remaining: branding-JSON upload, custom logo overrides, issuer/underlying-description prefill.

## 8. Easy-to-miss behaviors
- ⬜ Note-type picker pre-fills but never hides fields.
- ⬜ Inverted-ticker auto-correction on JSON upload.
- ⬜ Off-grid maturity preserved (9M ≠ snapped to 1Y).
- ⬜ Barriers/coupon use number_input (sub-percent precision), not sliders.
- 🟡 Path-explorer slider extremes apply NO bound (avoid rounding-drop) — React MC sim had this; re-check explorer filters.
- ⬜ Up to 3 comparison panels in both explorers.
- ✅ Antithetic doubling (2×n_paths shown).
- ⬜ Live tab conditional (2 vs 3 tabs).
- ⬜ Generate-PDF can run the sim first.
- ⬜ Build-report master/sub tree.
- ✅ Memory guard / float16 storage (backend reused).
- ✅ Calibration on adj_close vs barriers/S0 on raw close (engine reused).
- ⬜ Custom logo / issuer-logo uploads as base64 overrides.
- ⬜ "Prefill from Yahoo" buttons (issuer + underlyings) w/ ES translation.
- ⬜ Backtest date-picker reset + Apply semantics; outcome color_map.

**Structural invariants to preserve:** `core/note.py:replay_note` is the single
source of truth for live/explorer per-observation status (never reimplement memory
/step-down/growth in the frontend); observation dates are calendar-snapped to the
trading grid everywhere (`obs_calendar_dates`).

Chart builders: `app/charts.py:246-972`. PDF gating: `app/pdf_report.py:2589-3021`.
Ticker universe: `app/underlyings.py`. UI strings: `app/translations.py`.
