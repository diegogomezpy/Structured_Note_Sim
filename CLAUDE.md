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

### Secondary-market position (cost basis)

A note can be held as a **position bought after issue at a price away from par**, described by three `NoteTerms` fields: `settlement_date`, `purchase_price` (the CLEAN price as a fraction of nominal) and `accrued_at_purchase` (coupon settled on top). `cost_basis` = `purchase_price + accrued_at_purchase` (a `@property`, never stored) and `is_secondary` is the display switch. The defaults — no settlement date, price 1.0, accrued 0.0 — are a primary subscription at par, so **every existing config prices exactly as before**.

- **`core/note.py:_position_returns()` is the only place the cost basis enters the payoff.** It turns per-path `nominal_payoffs` into `(payoff − cost) / cost` and annualises that over the same `t_held`. All three payoff branches (Phoenix, participation, cliquet) call it, so the Monte Carlo and the backtest — which share `price_note` — can never disagree about a position. `price_note` also returns `cost_basis` and `prob_loss` (P(negative return **on cost**) — distinct from `prob_knock_in_total`, since coupons can carry a knocked-in path back into profit and a discount can rescue a below-par redemption).
- **Payoffs, barriers and probabilities are untouched** — the cost basis only re-bases the return denominator. `prob_above_par` / `prob_below_par` / the participation breakeven stay measured against par, because they describe the *note*, not the holder.
- **`settlement_date` only affects the live tab** (`api/engine.py:run_live_api` + `_participation_live_result` via `_settlement_ts` / `_position_summary`): coupons fixed at or before settlement went to the previous holder, so they are excluded from `income_since` and each observation row is tagged `held`. Holding time runs from settlement, and `irr_to_date` becomes income / cost / holding-years — which reduces exactly to the old formula for a par subscription. The band also reports `pull_to_par` and `return_on_cost`.
- The cost basis is orthogonal to **seasoning** (below): one says what you paid, the other says what gets simulated.

### Seasoning — pricing the remaining life

`NoteTerms.seasoned` (**default `False`**) switches the Monte Carlo from "a hypothetical note issued today for the full tenor" — the historical behaviour of every config, and still the default — to "what is left of *this* note". It needs a past `issue_date`; the toggle lives in the setup overlay's Position card.

**What changes when it's on** (`api/engine.py:_seasoning` resolves the state, `_simulate_full` applies it):

- The grid runs **today → the ORIGINAL maturity** (issue + tenor), not today + tenor.
- `perf_paths = sim_prices / S0_fix` where `S0_fix` is the **fixing at the issue anchor**, read from the full price history. So the paths open at today's level (e.g. 0.82) instead of 1.0 and the term sheet's barriers keep their meaning. This is the whole point — a knock-in at 60% must mean 60% of the original fixing.
- Only the observations still to come are priced, with **`price_note(..., periods_elapsed=k, pending_coupons=p, start_basket=b)`**. Inside, `k` shifts every per-period quantity onto **absolute** term-sheet periods: autocall eligibility (`abs_periods >= autocall_start_period`), the step-down rungs (`autocall_barrier_schedule()[k:]`), and the growth-autocall accrual (`coupon_rate * (autocall_period + k)`). Memory arrears carried in are released by the first coupon that pays inside the window. `start_basket` is the cliquet's last elapsed reset level.
- `replay_note(perf_obs, terms, start_period=…, pending=…)` replays a window the same way — it derives the arrears from realised prices, and the single-path inspector reuses it.
- Coupons already paid are **realised, not part of the forward payoff**; the summary reports them as `coupons_received` for context only.

**Indexing contract.** Every per-period array `price_note` returns (`coupon_amounts`, `prob_autocall_by_period`, `autocall_period`, …) is aligned to the *priced window*, all sharing width `len(obs_steps)`. The result carries `periods_elapsed`, and the run summary exposes it as **`period_offset`**: column *i* describes term-sheet period `period_offset + i + 1`. Display layers add the offset (`MCTables`, `OutcomeWaterfall`, `HeroMetrics`, `obs_pairs` labels, the inspector); `inspect_run` also shifts client-sent period filters back into window space.

**Refusals.** Seasoning is silently skipped — the run falls back to from-issue and reports `seasoning_reason` — when there is no issue date, the issue date is in the future, price history doesn't reach the fixing, the note has matured, or it **already autocalled on realised prices** (nothing left to simulate).

**A/B compare.** `_can_share_paths()` gates path sharing: seasoning changes both the grid and the performance scale, so B can only ride A's paths when both are seasoned off the same `issue_date`. Otherwise B is simulated independently.

**Not seasoned:** the historical backtest (each issue window is a full life by construction) and the live tab (which reads realised prices, not simulation).

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
  "issue_date": "YYYY-MM-DD",
  "settlement_date": null,
  "purchase_price": 1.0,
  "accrued_at_purchase": 0.0,
  "seasoned": false
}
```

`issue_date` is optional; when set and on/before today, the app shows a "Current Performance" tab. `call_steepness: null` means hard trigger. The position fields are optional and default to a primary subscription at par — see [Secondary-market position](#secondary-market-position-cost-basis); `seasoned` defaults to off — see [Seasoning](#seasoning--pricing-the-remaining-life).

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
- upside `participation_upside`: `linear` (`participation_rate`·min(B−strike, `upside_cap`)) · `shark_fin` (participate up to `knockout_level`, else a flat `knockout_rebate`; European/at-maturity KO) · `digital` (fixed `digital_payout` if `B ≥ strike`).

`upside_cap` caps the **underlying move** that participates (`min(B−strike, upside_cap)`), NOT the redemption — participation is applied after the cap, so the participating gain tops out at the same underlying level (strike + `upside_cap`) whatever the rate, and the max redemption is `1 + rate·upside_cap`. A digital ignores the move magnitude, so the cap doesn't enter. The displayed "upside cap" is the underlying cap **level** (`1 + upside_cap`), which is rate-independent; the payoff-diagram cap **line** sits at the redemption ceiling `1 + rate·upside_cap`. The cliquet `period_cap` is the same, per period.

Plus `participation_strike` and `participation_basket`. `_participation_redemption` has a TS mirror in `web/src/lib/participation.ts` that feeds the payoff-profile diagram, so the picture always matches the priced payoff — **keep the two in sync**. Airbag = `final/barrier` and shark-fin KO = at-maturity (European) are the intended conventions.

## A/B comparison — paired paths

`/api/compare` prices two notes and, wherever possible, prices them on **one shared simulation**. That is the feature, not an optimisation: index *i* is then the same simulated world for both notes, so the per-path difference is a real quantity rather than a difference of two independent averages.

The statistics live in **`core/compare.py`**, not the API layer — they are pure numpy over `price_note` payoff dicts, so they import without plotly/yfinance and stay testable in CI's light job (`api/engine.py` imports them under their old private names; it owns only the figures and serialisation).

- **`share_blockers(a, b)`** returns *why* the paths can't be shared — `underlyings` / `maturity` / `seasoning` / `issue_date` — so the UI names the term to change instead of only reporting that the comparison is noisier. `can_share_paths` is the boolean wrapper; both `run_compare` and `_compare_for_pdf` use it.
- **`paired_stats()`** (shared paths only, else `None`) is the head-to-head: win/tie/loss rate, mean and median edge on total return and IRR, the 5th–95th percentile edge, the paired standard error, an **outcome transition matrix** (`outcome_buckets` → called / at-par / knocked-in, or below/at/above par for participation) and conditional tails (*when A loses, what does B do?*). The win rate is the headline the summary means can't give: a +0.8% mean edge that wins on 51% of paths is a different product from one that wins on 88%.
- **Error bars.** Every `compare_diff` row carries `se`, the standard error **of the delta** — the paired SE when paths are shared (market risk cancels, so it is far tighter), otherwise the two independent errors in quadrature. `metric_samples` maps a summary key to its per-path array; quantiles and conditional means return `None` and the row shows no ±. The client greys any delta inside ±2 se and labels it noise.
- **Payload discipline.** The compare response deliberately carries **summaries only** — no per-side figure sets, no `run_id`s. It used to build the full 7-figure set for each side (fans, per-asset fans, correlations) that the panel never rendered, and store both runs in a store capped at `_MAX_RUNS`. Overlay histograms are also **pre-binned server-side** (`_bin_edges` / `_pct_bar` in `app/charts.py`): `go.Histogram` ships every raw path value, which at 20 000 antithetic paths was 426 KB for a picture with 60 bars. Net effect 802 KB → 150 KB *with six charts instead of two*. If you add a compare chart, bin it.
- **Front end.** `ComparePanel` renders the verdict band, the **term-sheet diff** (`termDiffRows` in `web/src/lib/terms.ts` — which fields actually differ, so the metric deltas are attributable), the metric table with noise marks + CSV export, the paired charts, and backtest/live head-to-heads. Note B loads from the user's **connected folder** (`useLocalFolder('note-configs')`) or an upload — *not* from `/api/configs`, which returns `[]` by design.
- **Win rate has a basis, and the two are different.** The Monte Carlo band measures it on **total return**; the backtest head-to-head measures it on **IRR** over paired issue dates. A note that calls sooner earns the same money in less time, so it can lose the first and win the second by a wide margin. Both tiles name their basis — an untagged "B wins" printed twice over different quantities reads as a contradiction.
- **The worst-of envelope is a property of the SIMULATION, not the note.** With shared paths A's and B's bands are the same array, so `build_wof_fan_compare(..., shared=True)` draws the market **once** and puts each note's knock-in / autocall lines across it — where the barriers sit against one distribution *is* the comparison. Two envelopes only when the notes ran different simulations.

Covered by `tests/test_compare.py` (hand-built payoff dicts, no simulation).

### Chart colour: one remap, three surfaces

Compare charts are built once, server-side, in the blue/amber source palette (`_CMP_A` / `_CMP_B` in `app/charts.py`) and recoloured per surface: `web/src/lib/plotlyTheme.ts:SERIES_REMAP` for the app (light and dark), `app/pdf_report.py:_rebrand_figure` for the PDF. Two consequences worth knowing before touching a compare chart:

- **Use literals that are IN the remap tables.** A colour that isn't a key survives untouched — which is how the edge-by-outcome bars shipped royal blue and orange inside a viridian app. `deepRecolor` now handles per-point `color` **arrays** and `colorscale` stop pairs, not just scalar strings, so a bar chart that colours its bars individually and a heatmap ramp both follow the theme. rgba literals carry their alpha through both remaps.
- **The tables are many-to-one.** Several distinct source colours collapse onto the same viridian in dark mode, so a chart that needs N visually distinct series cannot pick N arbitrary hexes and assume they stay distinct. Check the mapping, or use the A/B pair, which is guaranteed to differ.

`--cmp-a` / `--cmp-b` in `web/src/index.css` are the CSS side of the same pair and **must resolve to what the figures resolve to** in each mode, or the chip beside a chart disagrees with the series inside it.

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

## `reportkit` — the report engine, now a separate package

The themed-PDF engine lives in its **own repository** and is installed as a
dependency: [`report_maker`](https://github.com/diegogomezpy/report_maker),
pinned by tag in `requirements.txt` (`reportkit[charts] @ git+…@v0.5.0`). It has
no imports from `app/`, `core/` or `data/` and knows nothing about structured
notes — a different project can `pip install` it and build a report.

    reportkit.document   ReportDocument: covers, section heads, tables, metric
                         bands, figures, callouts, and the keep-together
                         pagination (heading never orphaned from its block).
    reportkit.theme      ReportTheme / SpecTheme, palette-derived tokens, the
                         shape + gradient primitives, the theme registry.
    reportkit.branding   resolve a brand config to a frozen `Brand`, and
                         `apply_brand` it — palette before token derivation,
                         brand fonts after the default family, watermark after
                         the image decode, filler pool after cover/back.
    reportkit.cover      full-bleed pages: `full_bleed()` opens the page
                         chrome-free, paints the themed background, draws the
                         photo and tints it. Plus the sigil / cover-logo
                         placement and the tall left photo column.
    reportkit.fonts      registration; ships IBM Plex Sans under the OFL.
    reportkit.text       PDF-safe string sanitisation (incl. the Latin-1 path).
    reportkit.images     load / sanitise / embed + path, URL-scheme and
                         decompression-bomb guards.
    reportkit.color      CSS colour parsing, brand palette remapping.
    reportkit.spec       describe a document as data; `render_spec(dict)`.
    reportkit.charts     [charts extra] Plotly figure → brand-coloured PNG.

`app/pdf_report.py` is the Structured-Note **adapter**: `_NotePDF(ReportDocument)`
plus the note-specific blocks (term sheets, structure diagram, participation
profile, glossary, the `_LABELS` vocabulary, `_build_pdf_report`'s assembly).
`generate_pdf_report()` is unchanged, so `api/engine.py` never noticed.

**Things that are load-bearing and easy to break:**

- **`pdf_report._FIG_HOOK` must stay an alias of the SAME ContextVar** as
  `reportkit.charts.FIG_HOOK`. `api/proof.py` and `tests/golden_fixture.py`
  `.set()`/`.reset()` through that attribute path; a second ContextVar disables
  the proof's placeholder mode and puts a real headless Chrome in CI.
- **`_fetch_image_bytes` and friends stay module globals** in the adapter,
  resolved at call time — `golden_fixture.py` rebinds `_fetch_image_bytes` to
  neutralise the network. Bind it early and the golden goes to the network while
  staying green.
- **The adapter injects, reportkit does not assume:** the font directory (this
  repo's `fonts/`, so the same bytes get embedded), the label table (`_t` wins
  over reportkit's nine chrome defaults), and `_rebrand_figure` (which knows
  *this* app's source chart palette).
- **`_NotePDF` must not re-declare inherited methods.** `tests/test_pdf_layout.py`
  `setattr`s 17 method names onto it to instrument pagination; a redefinition
  shadows the instrumented base method and blinds the orphan probe.
- **Bumping the tag is a production change.** Re-run
  `scripts/extraction_gate.sh` after any bump: the suite, `tests/golden/hashes.json`
  unchanged, and all 16 documents byte-identical. `scripts/pdf_baseline.py
  capture` re-baselines, deliberately by hand.

## PDF outline — one source for the chapter numbers

The report has exactly **seven possible numbered chapters**, in this order: Note Terms · Issuer · Underlying Breakdown · Monte Carlo · Historical Backtest · Current Performance · Comparison (`_CHAPTERS` in `app/pdf_report.py`). The first three head a page with `secondary_head`; the last four open an analytical lens with `section_divider`. Everything else — Payoff & Distribution, Price Paths, the glossary, the disclaimer — is a **sub-section and carries no number anywhere**.

`_plan_chapters({key: bool}) -> {key: "01"}` numbers whatever is present, in that order. It is the **only** place a chapter number is decided; the cover's "In this report" list and the body's heads both read the mapping (`pdf.chapter_nums` for `underlying_block`, which draws one page per underlying). Consequences:

- **Never write a number literal in a head call.** The old literals meant the body skipped a number whenever a chapter was toggled off (no issuer ⇒ 01 then 03), and the cover — which numbered every *leaf* — printed a different sequence entirely, so its "04 Price Paths" and the body's "04 · Monte Carlo" were different things.
- **The presence flags are hoisted above the cover** in `_build_pdf_report` (`_has_mc`, `_has_bt`, `_has_live`, `_has_cmp`), because the contents page is page 2 and the body it lists has not run yet. Each is the OR of exactly the conditions its block uses; adding an item to a lens means adding its condition to that OR. `_compare_tables()` exists for this reason — the comparison chapter only exists if one of its tables has rows, which has to be known before the cover is drawn.
- Adding a chapter: extend `_CHAPTERS`, add its flag to the `_plan_chapters` call, list it in `_cover_page`'s `toc_groups`, and pass `_chap[key]` to its head. `tests/test_pdf_layout.py` asserts the printed numbers and the contents list are the same gapless `01..N` sequence, over every theme.

**Cover pages and `_is_cover`.** `_is_cover` describes the page **about to be drawn** — every cover builder raises it *before* its `add_page()`. fpdf2 renders the closing page's footer from inside `add_page()`, so any "is the current page a cover?" test must use **`_cover_pages`** (keyed by page number), never the flag. Consulting the flag is what stripped the footer off the glossary and stopped its trailing void being decorated. `_is_cover` is load-bearing for **`header()` only**, which runs for the new page before it can be registered.

## PDF report themes (pluggable visual identity)

The report's *look* is a swappable **theme**, separate from its *content*. `reportkit/theme.py` owns the visual-identity layer; `app/pdf_report.py` owns the content (tables, metric bands, figures, glossary, cover copy, chart rebranding) and delegates every chrome surface to the active theme.

- **`ReportTheme`** is the interface. Each hook — `header` / `footer`, `eyebrow`, `section_title`, `secondary_head` (numbered reference heads), `section_divider` (analytical-lens chapter heads), `subsection`, `decorate_void` / `decorate_void_photo` (empty-space fillers), `cover_masthead`, `cover_left_void_fill` — receives the live `_NotePDF` instance (`pdf`) and draws through it. `_NotePDF.header()/footer()/section_title()/secondary_head()/…` are thin wrappers that call `self.theme.<hook>(self, …)`, so call sites never change when the theme changes. The theme reaches translations via `pdf.t(key)` and text sanitisation via `pdf._safe`; the photo-band hook uses `reportkit.images.cover_crop`. `app/pdf_report.py` imports the theme layer from `reportkit.theme` (and re-exports the chamfer primitives + neutral tokens under their original `_NAMES`).
- **Palette-driven tokens.** `build_tokens(primary, accent, section_rule, panel, sidebar_bar) -> ThemeTokens` derives `ink/lime/teal/amber/panel/sidebar_bar/…` from the resolved brand palette (single source for the derivation that `_NotePDF.__init__` used to inline). The brand-neutral constants (`AMBER`, `RULE_SOFT`, `TEXT`, …) and the chamfer-hexagon shape primitives also live here and are re-imported into `pdf_report.py` under their original `_NAMES`.
- **Themes.** `HexagonTheme` (`"hexagon"` / `"cadiem"`) is CADIEM's original chamfer-hexagon language, moved **verbatim**. `MercatorTheme` (`"mercator"`) is the website-inspired language (rounded number-chips, a light editorial chapter opener with a big ghosted numeral, thin accent keylines, airy voids — no chamfers/hexagons).
- **Selection.** `branding["report_theme"]` → `resolve_theme()` → registry; unknown/absent falls back to `DEFAULT_THEME`, which is **`"mercator"`** (so a generic un-themed brand gets the clean airy report). **CADIEM must set `"report_theme": "cadiem"` in its branding config** to keep the hexagon look — the deployed CADIEM config carries this key (it is otherwise gitignored). The web branding form exposes the picker (`brand_theme` in `ReportPanel.tsx`).
- **Byte-identity contract.** A change to a drawing routine must not move pixels it did not intend to. `tests/test_golden_pdf.py` proves it: a hermetic harness (no network, no Chrome — figures are stubbed *inside* `_fig_to_png` at the caller's exact pixel size so pagination is unchanged) that renders the full report under three brand fixtures — `mercator` (default), `hexagon` (resolves the built-in CADIEM theme) and `custom` (an inline SpecTheme with linear/radial gradients) — and diffs per-page SHA-256 digests against `tests/golden/hashes.json`.

```bash
python -m pytest tests/test_golden_pdf.py -q
```

  Inputs come from `tests/golden_fixture.py`: a seeded RNG builds a `results` dict shaped like the one `api/engine.py` stores, so the golden guards the *drawing* code and does not go red when the quant library legitimately changes a number. The analytics half lives in **`api/preview_fixture.py`** and is shared with the PDF Studio proof — `results()` + `figures()` for the Monte Carlo lens, and **`extras()`** for every section gated on something else (backtest, current performance, A/B comparison, underlying breakdown). Both callers splat `extras()`, so the golden guards the whole document and the proof previews it; a section with no fixture data is a section neither of them covers. The brand fixtures are synthetic — the real CADIEM config and its brand fonts are gitignored licensed assets and must never enter the repo — but they drive the same code paths. On failure the run writes both renders to a temp dir and prints the path; review image by image, then re-baseline with `GOLDEN_UPDATE=1`. Runs in CI (`golden-pdf` job) and skips cleanly wherever the PDF stack is absent.

## PDF attribution / provenance metadata

`app/pdf_report.py` stamps every generated PDF's document metadata (see `_stamp_attribution` + `_stamp_provenance`, called from the build tail):

- **`_stamp_attribution`** sets Author/Creator/Producer/Keywords to an author-attribution watermark. The string is base64 in `_A64` (assembled at runtime, not a grep-able literal) and stamped from **two** call sites (after doc build + before `output()`) so deleting one leaves the mark. It's deterrence, not DRM — a source-available build can strip it.
- **`_stamp_provenance`** sets Title (note/report title), Subject (`Generated <UTC> · <note> · <tickers> · Structured Note Simulator`), and the PDF CreationDate. Deliberately **non-PII** — no IP, since a report is white-label / redistributable.

## Generation audit log (server-side, IP stays out of the PDF)

`api/main.py` logs one provenance line per `/api/simulate` and `/api/report` via the shared `_audit(request, tag, **fields)` helper: `[tag] ts=<UTC> ip=<client IP> geo=… <fields> ua=…`. The client IP comes from `X-Forwarded-For` (first hop; falls back to `request.client.host`). `_geo(ip)` resolves a coarse location + ISP/ASN best-effort via ip-api.com (cached in `_GEO_CACHE`, 2s timeout, skips private IPs, `SNSIM_GEOIP=off` disables it). **Never embed the IP/geo in the PDF** — it's personal data and the doc is redistributable; the audit line is operator-only. ip-api.com's free tier is non-commercial — swap for a licensed provider / self-hosted GeoLite2 for a commercial deploy.
