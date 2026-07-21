# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the app

The product is a React (Vite) single-page app served by a FastAPI backend. For local dev, run both:

```bash
# backend — FastAPI on :8010
pip install -r requirements.txt -r api/requirements.txt
uvicorn api.main:app --reload --port 8010

# front-end — Vite on :5173 (proxies /api → :8010)
cd web && npm install && npm run dev
```

Production is a single Docker image (`Dockerfile`): Vite build + compiled C++ wheel + uvicorn serving the API and the built bundle. The Python side has no tests/linter; the front-end lints with `oxlint` (`npm run lint`) and type-checks with `tsc -b` (part of `npm run build`). Python 3.12+ required (f-strings use nested same-quote syntax introduced in 3.12).

## Architecture

The project is split into a pure-quant library (`core/`, `data/`), quant-only helpers shared with the API (`app/charts.py`, `app/pdf_report.py`, `app/translations.py`, `app/underlyings.py`), a FastAPI backend (`api/`), and a React front-end (`web/`). `core/` has no web, Plotly, or file I/O imports and can be used in notebooks independently. (The legacy Streamlit UI was removed — the `app/` package now holds only those framework-free helpers.)

### Data flow

```
data/loader.py  →  core/calibrator.py  →  core/simulator.py  →  core/note.py / core/backtest.py
     ↓                                                                ↓
load_prices()       HestonCalibrator          HestonMultiSimulator     price_note()
                    → CalibrationResult       → S_paths, V_paths       run_backtest()
                      .params
                      .corr_SS/VV/SV
                      .t_dof
```

`api/engine.py` wires these together and serialises everything to JSON for the React UI (and shapes the PDF inputs); `api/main.py` exposes the routes. All Plotly figure builders live in `app/charts.py` as pure functions—they take numpy/pandas arguments and return `go.Figure` (serialised to JSON for the front-end, or exported to PNG by kaleido for the PDF).

### Simulation engines (numpy default, optional C++)

`HestonMultiSimulator.run(engine="numpy"|"cpp")`. **numpy is the default and the reference**; the app calls `run()` with no argument. The optional C++ engine (`cpp/heston_kernel.cpp`, pybind11, wrapped by `core/simulator_cpp.py`) runs the same model — block-SIMD with a branch-free xoshiro256++/Box–Muller RNG, parallelised across path-blocks with `std::thread` (no OpenMP/libomp). It is **not** bit-identical to numpy (different RNG stream); it is validated by convergence of statistics (`scripts/compare_engines.py`), not bit-equality. `run()` returns the same results dict either way (`_finalize` is the shared tail), so everything downstream is unchanged. The Docker image builds + installs the `heston_cpp` wheel so `engine="cpp"` works in production; for local Python use build with `pip install ./cpp` **into the same interpreter that runs uvicorn** (common gotcha: building into `.venv` but launching the API from system Python). If `"cpp"` is selected but unbuilt, the simulator catches `ImportError` and falls back to numpy.

### Single payoff engine for MC and backtest

`core/note.py:price_note()` is the sole payoff evaluator. Both the Monte Carlo path and the historical backtest construct a `perf_paths: (n_paths, N+1, n_assets)` array (performance relative to S0) and pass it directly to `price_note()`. There is deliberately no second payoff implementation in `backtest.py`. Any payoff change must be made once, in `price_note()`, and it will apply to both.

### NoteTerms design

`NoteTerms` stores human-readable fields (`maturity`, `payment_freq`, `coupon_pa`) and derives `n_obs`, `coupon_rate`, `periods_per_year` as `@property`. The JSON configs and UI sliders use the human-readable fields only. Derived values are never stored.

`from_dict` / `from_json` handle legacy configs that stored `n_obs` + `coupon_rate` directly — these are back-converted on load.

### Autocall trigger

By default `call_steepness=None` → hard trigger: `autocall_prob()` returns exactly 0.0 or 1.0. The `call_draws < prob` comparison is then fully deterministic regardless of RNG seed. Soft sigmoid triggers exist but require steepness ≥ ~2000 to approximate a hard trigger — at 100 the trigger is NOT effectively hard (see docstring).

### Calibration → simulation parameter handoff

- `mu` is the **arithmetic** drift for `dS/S = mu*dt + ...`. The calibrator adds `0.5*theta` back to the mean log-return to avoid double-counting the volatility drag, because the log-Euler price step subtracts `V/2` again at each step.
- Correlation block: `corr_SV` is a diagonal matrix; diagonal = each asset's own `rho`. Off-diagonals are zero. The full `2n×2n` block matrix is validated for PSD on construction; if not PSD, Higham (2002) nearest-PSD projection is applied.
- Antithetic variates double the output paths: `n_paths` passed in → `2*n_paths` in all result arrays.

### IRR convention

Simple annualisation: `total_return / t_held`. **Not** compound. This matches how structured note coupons are quoted as simple p.a. rates. Expected IRR ≠ ratio of expected total return to expected time held (it's the mean of per-path ratios).

## Note JSON config format

Configs live in `note_configs/`. Required fields for `NoteTerms.from_dict`:

```json
{
  "name": "...",
  "maturity": 1.5,
  "payment_freq": "quarterly",
  "coupon_pa": 0.15,
  "coupon_barrier": 0.50,
  "autocall_barrier": 1.0,
  "autocall_start_period": 1,
  "knock_in_barrier": 0.50,
  "memory": true,
  "coupon_basket": "worst_of",
  "autocall_basket": "worst_of",
  "one_star_level": null,
  "tickers": {"TICKER": "DisplayName", ...},
  "issue_date": "YYYY-MM-DD"
}
```

`issue_date` is optional; when set and on/before today, the app shows a "Current Performance" tab. `call_steepness: null` means hard trigger.

## Basket types and the One Star feature

`one_star_level` (a fraction like `1.0`, or `null` = off) implements the "One Star" best-of overlay. **By default it applies to the FINAL REDEMPTION check only**: a single underlying at or above `one_star_level` at maturity redeems capital at par even when the worst-of breached the knock-in barrier. This is the BBVA XS3378405743 "Barrier and Knock-in" rescue and the safe default — it does NOT touch the coupon or autocall observations.

Two opt-in flags extend the same best-of overlay to the periodic checks, **both `False` by default**:
- `one_star_coupon` — a single underlying ≥ `one_star_level` also pays that period's coupon (even if the worst-of is below the coupon barrier).
- `one_star_autocall` — a single underlying ≥ `one_star_level` also forces the autocall.

Set both `True` for a BNP-style "One Star" note (see `note_configs/bnp_paribas_pr00529720.json`), where the overlay lifts coupon, autocall AND final redemption. In `price_note()` the final-redemption rescue always uses `one_star_met` (via `protection_cond`); the coupon/autocall overlays use the flag-gated `one_star_coupon_met` / `one_star_autocall_met`. When `one_star_level` is `null` the note is plain worst-of throughout regardless of the flags.

Legacy configs that used `final_basket="best_of"` + `final_redemption_barrier` are migrated by `NoteTerms.from_dict` to `one_star_level` (best-of → the barrier value; worst-of/average → `null`), with both overlay flags off — exactly reproducing the old final-redemption-only rescue.

## Note types (structure families)

`NoteTerms.note_type` (`phoenix | reverse_conv | growth_autocall | participation | custom`) is an **explicit stored field** that drives the dedicated setup menus (`SettingsOverlay` expanded / `SetupRail` sidebar both branch on it), the payoff branch, the structure diagram (`NoteTimeline` → `ParticipationProfile` for participation) and the prose. `from_dict` **infers** it for configs that predate the field (legacy `capital_guarantee>0` → `participation`), so old JSON still loads. The phoenix / reverse-conv / growth-autocall family all share the one Phoenix waterfall in `price_note()` — for them `note_type` is a menu/label distinction only. Only `participation` has its own payoff branch. The plan is to give each family its own good payoff + menus one at a time; participation is the first.

**Currently exposed: only `phoenix` and `participation`.** `reverse_conv`, `growth_autocall` and `custom` are **parked** — removed from the pickable `web/src/lib/noteType.ts:NOTE_TYPES` until each is redesigned with its own trusted payoff + menus. They stay in the `NoteType` union and `applyPreset`, and `from_dict` still infers/prices them, so existing configs of those types load and price via the Phoenix waterfall — they just aren't selectable in the UI (`detectNoteType` collapses any non-participation type to `phoenix` for the picker). Reintroduce one at a time; intended behaviour is noted in the `noteType.ts` header (reverse convertible = guaranteed coupon/no barrier/no memory; growth autocall = no periodic coupon, premium accrues and pays as a lump at autocall, often step-down barrier; custom = leave every field as-is).

### Participation Note

A single **maturity-level** payoff (no coupons/autocall/knock-in) — `price_note()` routes `note_type=="participation"` (or legacy `capital_guarantee>0`) to `_participation_payoff()`, which evaluates `_participation_redemption(B, terms)` on the final basket level `B`. It composes **one downside style** with **one upside style**:

- downside `participation_downside`: `full` (flat floor at `protection_level`, par when ≥1) · `buffer` (par down to `protection_level`, then 1:1 below) · `airbag` (par down to the barrier, then geared `B/barrier` below) · `bear` (participate as `B` falls below the strike, floored above it — the upside style is ignored).
- upside `participation_upside`: `linear` (`participation_rate`·(B−strike), optional `upside_cap`) · `shark_fin` (participate up to `knockout_level`, else a flat `knockout_rebate`; European/at-maturity KO) · `digital` (fixed `digital_payout` if `B ≥ strike`).

Plus `participation_strike` and `participation_basket`. `_participation_redemption` has a TS mirror in `web/src/lib/participation.ts` that feeds the payoff-profile diagram, so the picture always matches the priced payoff — **keep the two in sync**. Airbag = `final/barrier` and shark-fin KO = at-maturity (European) are the intended conventions.

## API run/session model

The React SPA is stateless on the wire: it POSTs `/api/simulate` (and `/api/backtest`, `/api/report`, …) and gets JSON back. The server keeps state in `api/engine.py`:

- **`_RUNS`** — an in-memory `OrderedDict[run_id → payload]` capped at `_MAX_RUNS` (8). A `/api/simulate` stores the full run and returns a `run_id`; the path explorer (`/api/runs/{id}/paths`), inspector (`/api/runs/{id}/inspect`) and report re-read that run without re-simulating. Oldest runs are evicted FIFO.
- **Price cache** (TTL) — `load_prices` results, since the API has no `@st.cache_data` layer. Backtest results (`_BT_CACHE`, keyed on tickers + terms) and translations (`_TR_CACHE`) are cached too.

### Results storage schema (memory-sensitive — read before touching it)

The engine keeps full daily paths, so **RAM, not CPU, is the ceiling**. A stored run deliberately does NOT keep the full float64 cubes. It stores:

- `perf_paths` — per-asset performance (price/S0) as **float16** (bounded ~[0, 20] so it never overflows like raw prices could; the ~5e-4 rounding is display-only). This is the path explorer's only big array.
- `wof_bands` (7, N+1) and `asset_bands` (n, 7, N+1) — the `[1,5,25,50,75,95,99]` percentile fan envelopes, **precomputed once** so the charts never rescan the full arrays.
- **No `worst_of_paths`** — derived from `perf_paths[pn].min(axis=2)` on demand.
- payoff stats from `price_note` (float64-exact; the float16 is display-only, so coupon/IRR/KI totals are unaffected).

Discipline to preserve: don't retain the float64 working set (raw S/V paths, stacked/perf cubes) past building the compact copies; `_RUNS` is capped so memory can't grow unbounded across runs. The band-aware chart builders (`build_wof_fan`, `build_fan_chart`) take a `bands=` arg and skip the percentile scan when given. The API bounds `n_paths` to 1000–250000 (default 10000); size the deploy's memory for the cap you allow.

## PDF report themes (pluggable visual identity)

The report's *look* is a swappable **theme**, separate from its *content*. `app/pdf_theme.py` owns the visual-identity layer; `app/pdf_report.py` owns the content (tables, metric bands, figures, glossary, cover copy, chart rebranding) and delegates every chrome surface to the active theme.

- **`ReportTheme`** is the interface. Each hook — `header` / `footer`, `eyebrow`, `section_title`, `secondary_head` (numbered reference heads), `section_divider` (analytical-lens chapter heads), `subsection`, `decorate_void` / `decorate_void_photo` (empty-space fillers), `cover_masthead`, `cover_left_void_fill` — receives the live `_NotePDF` instance (`pdf`) and draws through it. `_NotePDF.header()/footer()/section_title()/secondary_head()/…` are thin wrappers that call `self.theme.<hook>(self, …)`, so call sites never change when the theme changes. The theme reaches translations via `pdf.t(key)` and text sanitisation via `pdf._safe`; `_cover_crop` is a deferred `from pdf_report import` inside the photo-band hook (the only cross-module edge — `pdf_report` imports `pdf_theme` at top level).
- **Palette-driven tokens.** `build_tokens(primary, accent, section_rule, panel, sidebar_bar) -> ThemeTokens` derives `ink/lime/teal/amber/panel/sidebar_bar/…` from the resolved brand palette (single source for the derivation that `_NotePDF.__init__` used to inline). The brand-neutral constants (`AMBER`, `RULE_SOFT`, `TEXT`, …) and the chamfer-hexagon shape primitives also live here and are re-imported into `pdf_report.py` under their original `_NAMES`.
- **Themes.** `HexagonTheme` (`"hexagon"` / `"cadiem"`) is CADIEM's original chamfer-hexagon language, moved **verbatim**. `MercatorTheme` (`"mercator"`) is the website-inspired language (rounded number-chips, a light editorial chapter opener with a big ghosted numeral, thin accent keylines, airy voids — no chamfers/hexagons).
- **Selection.** `branding["report_theme"]` → `resolve_theme()` → registry; unknown/absent falls back to `DEFAULT_THEME`, which is **`"mercator"`** (so a generic un-themed brand gets the clean airy report). **CADIEM must set `"report_theme": "cadiem"` in its branding config** to keep the hexagon look — the deployed CADIEM config carries this key (it is otherwise gitignored). The web branding form exposes the picker (`brand_theme` in `ReportPanel.tsx`).
- **Byte-identity contract.** `HexagonTheme` must reproduce the pre-refactor CADIEM output pixel-for-pixel. `scratchpad/golden.py` is a hermetic (no Chrome, figures stubbed) golden pixel-diff harness used to prove it — regenerate a baseline and `check` after any change to a hexagon-theme drawing routine.

## PDF attribution / provenance metadata

`app/pdf_report.py` stamps every generated PDF's document metadata (see `_stamp_attribution` + `_stamp_provenance`, called from the build tail):

- **`_stamp_attribution`** sets Author/Creator/Producer/Keywords to an author-attribution watermark. The string is base64 in `_A64` (assembled at runtime, not a grep-able literal) and stamped from **two** call sites (after doc build + before `output()`) so deleting one leaves the mark. It's deterrence, not DRM — a source-available build can strip it.
- **`_stamp_provenance`** sets Title (note/report title), Subject (`Generated <UTC> · <note> · <tickers> · Structured Note Simulator`), and the PDF CreationDate. Deliberately **non-PII** — no IP, since a report is white-label / redistributable.

## Generation audit log (server-side, IP stays out of the PDF)

`api/main.py` logs one provenance line per `/api/simulate` and `/api/report` via the shared `_audit(request, tag, **fields)` helper: `[tag] ts=<UTC> ip=<client IP> geo=… <fields> ua=…`. The client IP comes from `X-Forwarded-For` (first hop; falls back to `request.client.host`). `_geo(ip)` resolves a coarse location + ISP/ASN best-effort via ip-api.com (cached in `_GEO_CACHE`, 2s timeout, skips private IPs, `SNSIM_GEOIP=off` disables it). **Never embed the IP/geo in the PDF** — it's personal data and the doc is redistributable; the audit line is operator-only. ip-api.com's free tier is non-commercial — swap for a licensed provider / self-hosted GeoLite2 for a commercial deploy.
