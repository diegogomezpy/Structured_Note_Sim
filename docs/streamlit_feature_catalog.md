# Streamlit → React Feature Parity (audited)

Authoritative parity checklist between the original Streamlit app (`app/app.py`,
~3150 lines) and the FastAPI + React port (`api/` + `web/`). Re-audited against
the live React source — markers below reflect the **current** state, not the
original port snapshot.

Legend: ✅ ported · 🟡 partial / cosmetic difference · ⬜ not ported.

---

## 1. Global / chrome
- ✅ Two-column responsive layout (React design system; replaces Streamlit wide layout).
- ✅ Language toggle EN/ES — instant client re-theme; ES auto-translates Yahoo issuer + underlying descriptions (refetch on switch).
- ✅ Dark / light theme toggle (no Streamlit equivalent).
- ✅ Sidebar: note name + issuer favicon + summary line (header), download config, JSON upload, How-to-add-a-note tutorial, Run.
- ✅ Branding auto-load from `branding/branding_*.json` (preset dropdown in the report panel, via `/api/branding`).
- 🟡 Path ceiling presets (2k–250k) exposed in the engine group; no separate cloud/local `_MAX_PATHS` clamp surfaced (backend memory guard still applies).

## 2. Setup (rail + settings overlay)
- ✅ JSON config upload (normalised through `/api/config/parse`: legacy-field migration + inverted-ticker fix).
- ✅ Underlyings: universe picker (max 5) with logo chips, inline add/remove, **custom ticker** flow.
- ✅ Note-type presets (Phoenix / Reverse convertible / Growth autocall / Bonus cert / Capital protected / Custom) — `lib/noteType`, pre-fills defaults, never hides fields.
- ✅ Schedule + coupon: maturity, frequency, coupon p.a., coupon basket, coupon barrier, memory.
- ✅ Protection: knock-in barrier, capital-protection toggle + guarantee %, cap-upside toggle + %, One-Star overlay toggle + level.
- ✅ Autocall: barrier, start period, basket, step-down %, floor %, premium-at-call.
- ✅ Metadata: note name, issuer, issue date, S&P / Moody's / Fitch ratings.
- ✅ Per-underlying details: custom logo upload, editable descriptions, analyst buy/hold/sell %, Prefill-from-Yahoo.
- ✅ Engine: paths, seed, numpy/C++ engine, calibration window (1/2/3/5/10y).
- ✅ Rail quick-edit: maturity, frequency, coupon, the three barriers (sliders), plus a Mechanics group (autocall start, baskets, memory, One-Star) — no overlay trip needed for the common fields.
- ⬜ **store-on-disk** toggle (memory-map `perf_paths`) — backend helper exists; not surfaced in the engine group.
- 🟡 Live pre-run **memory estimate / warning** — backend memory guard aborts unsafe runs, but there's no pre-run RAM estimate shown.
- 🟡 Off-grid maturity (e.g. 1.4y) — slider is 0.25-grid; arbitrary values survive a config round-trip but snap on slider edit.

## 3. Note structure / term-sheet
- ✅ Header with issuer badge + summary line.
- ✅ Collapsible underlying-breakdown cards (market cap, IV/realized vol, last price, RSI, description, 1Y chart) — lazy-prefetched.
- ✅ Collapsible issuer card (logo + ratings + auto-loaded/translated description).
- ✅ Observation-schedule table (period / time / autocall eligible).
- ✅ Live note-structure diagram (hideable) — no Streamlit equivalent.

## 4. Monte Carlo
- ✅ Summary: expected IRR / total / coupon, P(autocall), P(KI), loss-given-KI, autocall-by-period table, hero metrics, outcome waterfall.
- ✅ IRR distribution, worst-of fan, per-asset fans.
- ✅ Path explorer: filter chips (all/autocalled/held/KI), coupon-period filter, resample, zoom, 1–3 comparison panels with naming, per-path metrics (principal/coupons/IRR), per-asset final-perf, single-path nav.
- ✅ Correlations: input + realized + **difference** heatmaps, calibrated Heston parameter table.
- ⬜ **Effective basket correlation** heatmap + gap metric (the heteroskedasticity-inflated correlation) — `app.py:2347-2362`; the API doesn't return `effective_corr` yet.

## 5. Historical backtest
- ✅ Outcomes: mean IRR, autocall %, KI %, loss-given-KI, outcome bar (per-period gradient), issue table, worst-asset pie, IRR scatter.
- ✅ Prices: weekly-downsampled history with issue-window markers.
- ✅ Backtest path explorer (3 panels, filters incl. IRR band, historical worst-of via `replay_note`).
- ✅ Date-range pickers (start/end + apply) with context reset.

## 6. Current performance (live) — ✅
- `LivePanel` via `/api/live` (`replay_note`): lifecycle bar, worst-of today + vs-strike, worst asset, KI/autocall buffers, per-asset cards, observation-history table, pending-memory/growth info, coupon-IRR-to-date, live chart (above the table). Auto-disabled when no issue date.

## 7. PDF / report builder — ✅
- `ReportPanel` via `POST /api/report`: fine-grained master/sub section tree (Note / MC / Calibration / Backtest / Live), runs only requested flows (can run the sim itself — no prior run needed), full branding form (firm, colours incl. secondary/rule/panel, website, contact, footer, disclaimer, logo) + preset loader, custom logo overrides, issuer/underlying prefill. Reuses `app/pdf_report.py`.

## 8. Remaining gaps (the only real ones)
1. ⬜ Effective basket correlation heatmap + gap (MC › Correlations). Needs `effective_corr` from the sim returned by `/api/simulate` + a 4th heatmap.
2. ⬜ `store_on_disk` engine toggle (memory-mapped paths).
3. 🟡 Pre-run memory estimate/warning; off-grid maturity on the slider.

**Umbrella:** the React app is feature-complete bar the three items above; it is
not yet the hosted app (Streamlit stays live on Cloud Run until switchover is
approved).

**Structural invariants:** `core/note.py:replay_note` is the single source of
truth for live/explorer per-observation status; observation dates are
calendar-snapped to the trading grid everywhere. Chart builders: `app/charts.py`.
PDF: `app/pdf_report.py`. Ticker universe: `app/underlyings.py`.
