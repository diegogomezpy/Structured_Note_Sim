# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the app

```bash
streamlit run app/app.py
```

There are no tests and no linter configured. The project requires Python 3.12+ (f-strings use nested same-quote syntax introduced in 3.12).

## Deployment (Streamlit Community Cloud)

Live at **https://structurednotesim.streamlit.app/**, auto-redeploying from
`main` on every push. Three deploy-hardening conventions exist — keep them
intact when editing the relevant code:

- **`requirements.txt` is pinned with upper bounds** (`<next-major`) so a cloud
  rebuild can't silently pull a breaking release. Bump deliberately and re-pin.
  `PyMuPDF` is intentionally **not** listed — it's verify-only
  (`scripts/verify_pdf.py`); `matplotlib` is listed but notebook-only
  (lazy-imported inside `simulator.plot()`, never loaded by the app).
- **Path-count ceiling (`_MAX_PATHS` in `app/app.py`)**: MC peak memory scales
  with `n_paths × n_steps × n_assets`; the free tier (~1 GB) OOMs on a 50K-path
  multi-year note. `_MAX_PATHS` caps the "Monte Carlo paths" slider at **15,000
  on Streamlit Cloud** (detected via `os.getcwd().startswith("/mount/src")` or a
  `STREAMLIT_CLOUD` env var) and **50,000 locally**. The **`SNSIM_MAX_PATHS`**
  env var overrides it. The slider's session default is clamped with
  `min(..., _MAX_PATHS)` so a loaded config can't exceed the cap.
- **Graceful data-load failure (`_safe_load_prices` in `app/app.py`)**: yfinance
  is the single point of failure (Yahoo changes undocumented endpoints
  periodically). `load_prices` already raises a friendly `ValueError` on
  empty/rate-limited responses; `_safe_load_prices` wraps it to render
  `st.error(tr("data_load_error"))` + a retry hint and `st.stop()` instead of a
  traceback. The run-simulation block routes through it; the backtest, prefetch,
  and live/historical loads already have their own `try/except` guards. If you
  add a new interactive `_load_prices` call, route it through `_safe_load_prices`
  (or guard it).

## Architecture

The project is split into a pure-quant library (`core/`, `data/`) and a Streamlit front-end (`app/`). `core/` has no Streamlit, Plotly, or file I/O imports and can be used in notebooks independently.

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

The Streamlit app (`app/app.py`) wires these together. All Plotly figure builders live in `app/charts.py` as pure functions with no Streamlit calls—they take numpy/pandas arguments and return `go.Figure`.

### Raw vs adjusted closes — never mix them up

Two price series, two purposes, deliberately split:

- **Raw official closes** (`load_prices(field="close")`, the default): what term
  sheets observe for barrier / coupon / autocall / KI fixings. Used by the
  backtest, the Current Performance tab, and as the simulation's `S0`.
- **Adjusted closes** (`field="adj_close"`): total-return series. Used ONLY to
  calibrate drift/vol/correlations (ex-date jumps must not pollute the
  estimates). Never compare adjusted prices to barriers.

The MC simulates the **total-return process** (drift from adjusted closes) and
converts to price paths via pre-programmed proportional dividend jumps at
forecast ex-dates (see below). **Double-counting trap:** do NOT calibrate `mu`
on raw closes AND subtract discrete dividends — raw-close returns already
embed the drops; total-return calibration + explicit jumps is the consistent
pair. The calibrator's own yfinance branch keeps `auto_adjust=True` on purpose.

### Calendar-first observation scheduling

Observation dates are derived, never stored: obs k = anchor date +
`k × (12 / periods_per_year)` months (`NoteTerms.obs_calendar_dates(anchor)`),
snapped to the **next trading day** in the relevant price index via
`searchsorted`. Anchor = each sampled historical issue date (backtest), the
note's `issue_date` (live tab), or the last close (MC). No `obs_dates` field
exists in the JSON configs by design (config bloat); add one only if an
irregular schedule (long stub period) ever requires it. The old
`round(maturity*252)` row-offset scheduling is gone — do not reintroduce a
252-trading-days-per-year constant in scheduling (it survives only as the `dt`
convention inside calibration).

### Single payoff engine for MC and backtest

`core/note.py:price_note()` is the sole payoff evaluator. There is
deliberately no second payoff implementation in `backtest.py`. Any payoff
change must be made once, in `price_note()`, and it will apply to both.

- The **backtest** builds a compact `(n_issues, n_obs+1, n_assets)` perf array
  (initial fixing + one column per snapped observation date); with `N = n_obs`,
  `terms.obs_steps(n_obs)` resolves to `[1..n_obs]` and the engine evaluates it
  unchanged.
- The **MC** passes the full daily paths plus explicit `obs_steps=` /
  `obs_times=` kwargs (grid indices and year-fractions of the snapped
  observation dates). When `obs_times` is given, the maturity holding time for
  IRR is `obs_times[-1]`, and final valuation uses `obs_steps[-1]`.
- **Partially-elapsed (live) notes** use `core/note.py:replay_note(perf_obs,
  terms)` — the single source of truth for "what happened so far" (memory
  coupons, step-down schedule, `coupon_at_autocall_only`). The Current
  Performance tab and `build_live_performance_chart` only consume its output;
  never reimplement coupon/autocall logic in the app or chart layer.

### Monte Carlo trading-day grid and dividend jumps

`app/app.py`'s run block builds a real future trading-day calendar
(`pd.bdate_range` from the last close to maturity) and passes
`dt_grid` (per-step calendar gaps in year fractions — a Fri→Mon step diffuses
3/365 of variance) to `HestonMultiSimulator`. When `dt_grid` is given, `T`/`N`
are derived from it. `div_schedule` is an `(n_assets, N)` array of
proportional drops applied at the END of step t (`S[:,t+1] *= 1-d`), built by
`data/loader.py:build_dividend_schedule()` from trailing-12-month cash
dividends repeated on anniversary ex-dates (via `load_dividends()`;
proportional vs current spot). Price indices (SPX/SX5E/…) have empty dividend
series → no jumps: constituent dividends are already in a price index's drift.
Verified: a 4% modelled yield lowers mean log-growth by exactly ~0.04 vs an
identical no-dividend asset. The uniform `T`/`N` grid still works for
notebooks/tests (legacy path).

### NoteTerms design

`NoteTerms` stores human-readable fields (`maturity`, `payment_freq`, `coupon_pa`) and derives `n_obs`, `coupon_rate`, `periods_per_year` as `@property`. The JSON configs and UI sliders use the human-readable fields only. Derived values are never stored.

`from_dict` / `from_json` handle legacy configs that stored `n_obs` + `coupon_rate` directly — these are back-converted on load. Unknown keys in the input dict are **not** silently dropped: `from_dict` emits `warnings.warn` listing any unrecognised keys, so JSON typos surface immediately.

`autocall_start_period` is validated in `__post_init__`: values < 1 raise `ValueError`. (A value of 0 would silently resolve to Python's `[-1:]` slice and enable only the last period.)

### Autocall trigger

By default `call_steepness=None` → hard trigger: the per-observation comparison `autocall_basket >= autocall_barrier_schedule()[j]` returns exactly 0.0 or 1.0, so `call_draws < prob` is fully deterministic regardless of RNG seed. Soft sigmoid triggers exist but require steepness ≥ ~2000 to approximate a hard trigger — at 100 the trigger is NOT effectively hard (see docstring).

`price_note()` compares each observation against `terms.autocall_barrier_schedule()` (a per-period array), not a scalar. For constant-barrier notes the schedule is flat and this is identical to the old behaviour; for growth autocalls (`autocall_step_down > 0`) it declines each period from `autocall_start_period`, floored at `autocall_floor`. (The old standalone scalar `NoteTerms.autocall_prob()` method has been removed — the engine path uses the schedule directly.)

**Single-asset notes:** `np.corrcoef` collapses to a 0-d scalar for one asset, so `calibrator._corr_SS`/`_corr_VV` wrap it in `np.atleast_2d` (→ `[[1.0]]`). The setup form allows ≥ 1 underlying.

### Calibration → simulation parameter handoff

- `mu` is the **arithmetic** drift for `dS/S = mu*dt + ...`. The calibrator adds `0.5*theta` back to the mean log-return to avoid double-counting the volatility drag, because the log-Euler price step subtracts `V/2` again at each step.
- Correlation block: `corr_SV` is a diagonal matrix; diagonal = each asset's own `rho`. Off-diagonals are zero. The full `2n×2n` block matrix is validated for PSD on construction; if not PSD, Higham (2002) nearest-PSD projection is applied.
- Antithetic variates double the output paths: `n_paths` passed in → `2*n_paths` in all result arrays.

### Realized vs effective correlation diagnostic

`corr_SS` is the **instantaneous Brownian correlation** fed into the Cholesky,
but the calibrator *estimates* it as the Pearson correlation of historical 2-day
log-returns. The Correlation Diagnostics tab reports two realized matrices from
`simulator.run()`:

- **`realized_corr`** — pooled correlation of simulated daily returns **after
  standardizing each step by its own `sqrt(V_t)`**. Removing the stochastic-vol
  heteroskedasticity recovers the Brownian correlation, so this matches `corr_SS`
  to <0.3% and is the honest "did the engine reproduce the input" check. The
  "max off-diagonal error" success/warning banner is computed against this.
- **`effective_corr`** — pooled correlation of the **raw** daily returns (no
  standardization), shown in a separate expander labelled "effective basket
  correlation". This is the co-movement the payoff actually sees, and it runs
  **above** `corr_SS` by construction: pooling high- and low-vol days inflates
  the sample correlation (Forbes–Rigobon heteroskedasticity bias), most for
  high vol-of-vol underlyings. Do **not** flag the input-vs-effective gap as a
  calibration error — that gap is expected and was the source of the old
  "high off-diagonal error" false alarm. Both are measured on **base paths
  only** (antithetic reflections would make the check circular) and with the
  deterministic dividend jumps stripped out.

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
  "final_basket": "worst_of",
  "final_redemption_barrier": 1.0,
  "tickers": {"TICKER": "DisplayName", ...},
  "issue_date": "YYYY-MM-DD"
}
```

`issue_date` is optional; when set and on/before today, the app shows a "Current Performance" tab. `call_steepness: null` means hard trigger.

### Optional fields

- `coupon_barrier: 0.0` → **guaranteed coupon** (basket always ≥ 0): pays every active period regardless of underlying level. Used for Reverse Convertibles (e.g. Barclays XS3305367727).
- Single-underlying notes are supported: a `tickers` dict with one entry (e.g. HSBC XS3287776739 on AMD). `worst_of`/`best_of`/`average` of one asset reduces to that asset. The setup form allows ≥ 1 underlying.

### Growth / Classic Autocall (step-down barrier + step-up premium)

Three optional fields (all default to a no-op, so plain Phoenix notes are unaffected):

- `autocall_step_down` (float, default `0.0`): the autocall barrier declines by this amount each period from `autocall_start_period`. `NoteTerms.autocall_barrier_schedule()` returns the per-period levels; `price_note()` compares each observation against the schedule rather than a scalar.
- `autocall_floor` (float | null): minimum barrier under step-down.
- `coupon_at_autocall_only` (bool, default `false`): no periodic coupon — instead an accrued premium of `coupon_rate × observation_index` is paid as a lump **only** when the note autocalls (zero if held to maturity). `coupon_pa` carries the premium accrual rate.

Example: Citi XS3096699163 — barrier 100% stepping down 3%/period from obs 3 (floor 88%), 12% p.a. premium paid only at call. Config: `autocall_step_down: 0.03, autocall_floor: 0.88, coupon_at_autocall_only: true, coupon_pa: 0.12, autocall_start_period: 3`.

These fields are exposed by the **Growth Autocall** template in the setup form's
note-type picker (see below); they default to a no-op for the Phoenix family.

## Basket types and final redemption

The `final_basket` + `final_redemption_barrier` fields implement the BBVA-style "best-of rescue": if the best performer at maturity is ≥ `final_redemption_barrier`, the note redeems at par even if the knock-in was breached. With `final_basket="worst_of"` (standard), the rescue condition can never coincide with a barrier event and the logic reduces to standard worst-of.

## Streamlit session state

The app has two pages controlled by `st.session_state["page"]`: `"setup"` and `"dashboard"`. All heavy computation (calibration, simulation, backtest) is cached via `@st.cache_data`. Cache keys for the backtest use `tickers_tuple` (a `tuple` of `(sym, name)` pairs) and `terms.to_json()`. Simulation results are stored in `st.session_state["results"]` and are `None` until the user clicks "Run Simulation".

Because Streamlit ignores a keyed widget's `value=` once its key exists in `session_state`, fields that must be populated from a loaded JSON config (e.g. `setup_issuer`, `setup_issue_date`, `setup_note_type`) push the loaded value into `session_state` *before* the widget renders. Forgetting this is why a config field "doesn't load".

### Setup-form note-type picker

The setup page leads with a **note-type template picker** (`setup_note_type`
radio: `phoenix` / `reverse_conv` / `growth_autocall` / `bonus_cert` /
`capital_protected` / `custom`). The picker drives **progressive disclosure** —
`_show_*` booleans gate which sections render (Coupon, Protection/Barriers,
Autocall, the step-down growth sub-block, capital-protection/min-return inputs).
It does **not** change the `NoteTerms` build contract: every widget variable
(`coupon_pa_pct`, `coupon_bar_pct`, `autocall_bar_pct`, `min_return_pct`,
`capital_guarantee`, `upside_cap`, …) is first seeded from `base`, then a
per-template block forces the canonical values the structure hard-codes (e.g.
Bonus/Capital-Protected → `autocall_barrier=200%`, `coupon_pa=0`; Reverse
Convertible → `coupon_barrier=0`, `memory=False`; Growth → `coupon_at_autocall_only=True`),
so a field hidden by the template still builds correctly — even when switching
type from a Phoenix base. The confirm block reads those variables unchanged.

Two ordering rules the picker depends on:
- `setup_note_type` is pushed into `session_state` **only inside the JSON-upload
  block** (`_detect_note_type(_parsed)`), which runs once per new file — so a
  manual override on later reruns is never clobbered.
- `_detect_note_type()` (in `app/app.py`) infers the template from a loaded
  config; **it must stay in sync with the per-template forcing logic** and the
  payoff branches in `core/note.py`. Order matters: capital-protected and bonus
  are checked before the Phoenix tests because they set fields those tests match.

Metadata (name/issuer/issue-date) and engine settings (paths/seed/calibration
window) live in collapsed `st.expander`s; the session-state-before-widget pushes
for `setup_issuer`/`setup_issue_date` run inside the metadata expander body
(which always executes).

## PDF report

`app/pdf_report.py:generate_pdf_report()` builds the report with fpdf2; Plotly figures are rasterised to PNG via kaleido (`_fig_to_png`). The core Helvetica font is Latin-1 only, so `_NotePDF.cell`/`multi_cell` are overridden to run all text through `_safe()` (transliterates `—`, `→`, `≥`, curly quotes, etc.; drops anything else) — never write raw user text to the PDF without it. The sidebar **Generate PDF Report** button builds the doc *after* all tabs render; each tab caches its figures/data into `_pdf_*` session_state keys during its render pass (Streamlit runs every tab's code each rerun), and a `st.empty()` placeholder right under the button is where the download button is injected so it isn't buried at the bottom of the sidebar.

## Charts — barrier lines

`build_wof_fan` and `build_path_wof_chart` both accept an optional `autocall_barrier` kwarg and draw it as a grey dotted line. The KI barrier is drawn as a red dashed line labelled "Knock-in barrier". Pass both from the caller:

```python
build_wof_fan(wof_paths, t_grid, terms.knock_in_barrier, obs_pairs, tr,
              autocall_barrier=terms.autocall_barrier)
```

For step-down (growth) autocalls, also pass `autocall_schedule` — a list of `(x, level)` points where the level follows `terms.autocall_barrier_schedule()`. The shared `_add_autocall_barrier` helper then draws a stepped (`hv`) dotted line instead of the flat one; it falls back to the flat `add_hline` when the schedule is `None` or constant. The fan chart takes time-based x (`obs_times`), the path chart takes step-based x (`obs_steps`). `app.py` builds these only when `terms.autocall_step_down` is set.

`build_historical_wof_path` takes the SNAPPED observation dates (`obs_dates`, the same ones the engine evaluated — get them from `core.backtest.snapped_obs_dates()`), stops drawing markers at the autocall date (the note no longer exists afterwards), and accepts `autocall_schedule` + `coupon_at_autocall_only`. Its `coupon_barrier` parameter colours observation markers green (coupon paid) or red (missed); the shared `_add_coupon_barrier` helper draws the coupon barrier as its own orange dashed line when it differs from the KI barrier — never relabel the KI line as a coupon barrier.

`build_live_performance_chart` only draws: it takes `obs_markers` (dicts produced from `replay_note` output by app.py) and `future_obs` (label, calendar-date pairs). It contains no payoff logic by design.

## Improvement roadmap (2026-06-11 deep-dive)

### Quick wins — low effort, high value

- **QW1 Pre-allocate `Z_full`** (`core/simulator.py`): replace per-step `np.concatenate([Z, -Z], axis=0)` with a pre-allocated buffer filled in-place. Saves one large allocation per time step; measurable at ≥10K paths.
- **QW2 Vectorize basket extraction** (`core/note.py`): replace the `obs_steps` list comprehension in `price_note()` with advanced indexing `perf_paths[:, np.array(obs_steps), :]` + single axis reduction. Meaningful for 5Y monthly notes (60 obs).
- **QW3 Fix `corr_VV` bias** (`core/calibrator.py`): use `np.diff(rv, axis=0)` instead of RV levels for `corr_VV`. One line — removes the documented upward bias in variance-variance correlation.
- **QW4 ~~Fix/deprecate `autocall_prob()` scalar method~~ (DONE)**: the scalar `NoteTerms.autocall_prob()` method has been removed entirely — the engine path uses `autocall_barrier_schedule()` directly, so the step-down silent-wrong-probability risk is eliminated.
- **QW5 ~~IRR denominator guard~~ (DONE)**: `np.maximum(t_held_arr, 1/252)` now guards the division at `core/note.py` (and the capital-protected branch guards `t_maturity` likewise). Defends against a degenerate near-zero holding time.
- **QW6 Expose `t_dof` as UI slider** (`app/app.py`): already threaded through to simulator; a slider would let users stress-test copula tail sensitivity.
- **QW7 Replace `print()` with `logging`** (`core/simulator.py`): Feller output and summary table go to terminal only; `logging.getLogger(__name__)` allows Streamlit callers to suppress/redirect.
- **QW8 Unify RNG seed for soft-trigger backtest** (`core/backtest.py`): `run_backtest()` defaults `seed=42`; app passes `seed+1`. Document or unify — irrelevant for hard triggers but inconsistent for soft.

### Medium-effort improvements

- **QE (Quadratic-Exponential) scheme** (`core/simulator.py`): replace Milstein+full-truncation for the CIR variance process with Andersen (2007) QE scheme. Removes positive V=0 bias in knocked-in scenarios, allows larger dt steps, makes Feller condition irrelevant. ~50 lines replacing the inner Milstein step. Reference: Andersen 2007 "Efficient Simulation of the Heston Stochastic Volatility Model".
- **Quasi-Monte Carlo (Sobol sequences)** (`core/simulator.py`): replace `np.random.default_rng` draws with `scipy.stats.qmc.Sobol` + inverse-normal transform. Convergence O(log(N)^d/N) vs O(1/√N); same accuracy at ~4× fewer paths. ~20 lines replacing normal draws in `HestonMultiSimulator.run()`.
- **Periodic / American KI barrier** (`core/note.py`): some term sheets observe KI at each coupon date, not only at final fixing. Add `knock_in_monitoring: "european" | "periodic"` flag to `NoteTerms`; add loop in `price_note()` to set a `ki_breached` flag at each observation step.
- **Capital-protected / participation payoff** (`core/note.py`): new note type needed for Bonus Certificates and Capital Protected Participation Notes (see "New note types" section below). Requires `min_return` and `upside_cap` fields in `NoteTerms` and a new payoff branch in `price_note()`.

### High-effort, high-impact

- **Control variates** (`core/simulator.py`): geometric basket terminal value has closed-form distribution under lognormal dynamics; correlates 0.7–0.9 with worst-of payoff. Combined with existing antithetics: 50–80% further SE reduction.
- **Term-structure of vol calibration** (`core/calibrator.py`): calibrate theta to 2Y realized RV vs 21D spot vol to reproduce observed vol term structure. Meaningful for 2Y+ notes where current flat-vol assumption understates term structure steepness.
- **Pathwise / Likelihood-Ratio Greeks** (`core/note.py`): delta via bump-and-reprice on cached paths; LR method (Broadie-Glasserman 1996) for autocall barrier discontinuity. Enables delta/vega/KI-barrier sensitivities.
- **Compound IRR option** (`core/note.py`): add `compound_irr = (1 + total_return)^(1/t_held) - 1` as optional output. ~0.5–1% lower than simple IRR at 3Y. Two lines.
- **Risk-neutral mode** (`core/simulator.py`): `mu = r - q` + implied-vol calibration for fair-value comparable to dealer mid-markets. Requires options data feed and separate calibration module. Physical measure is deliberate default; this would be an optional switch.

### New note types needed

See "New note structures" section below for detailed implementation notes on Bonus Certificates and Capital Protected Participation Notes — both seen in PUENTE product shelf.

## Review status (2026-06-10)

A full-repo review was performed and all findings were FIXED in the same pass
(adjusted-vs-raw close split, calendar-first scheduling, trading-day MC grid
with dividend jumps, live-tab rewrite onto `replay_note`, float-precision
barrier inputs, cache TTLs, chart label/marker fixes, IRR histogram tail
clipping, PDF growth-autocall rows, dead code removal, missing
`fpdf2`/`kaleido` installed). Everything was verified numerically: the
vectorized engine matches naive per-path replays exactly (MC memory-coupon
logic on 4,000 random paths; calendar backtest on 119 synthetic issues;
`replay_note` vs `price_note` on 500 paths; the Citi step-down live replay on
real data), and dividend jumps reproduce the modelled yield to 4 decimal
places.

### Known remaining limitations (deliberate, not bugs)

- **Calibration proxies bias kappa/xi low**: kappa from AR(1) of an
  *overlapping* 21-day rolling RV series (overlap pushes phi → 1, kappa ↓) and
  xi from increments of the same smoothed series; `corr_VV` from levels of
  overlapping rolling RV is likewise inflated. Left unchanged on purpose — a
  numerics change of this size needs its own validation pass. Candidates:
  non-overlapping windows or bipower variation.
- **No discounting / risk-neutral mode**: results are physical-measure
  expected values; `expected_irr` is not a price. The simulator's unused `r`
  parameter was removed.
- **Backtest issue dates overlap** (monthly sampling of multi-year windows):
  summary stats are autocorrelated; documented in `run_backtest`.
- **Future trading calendar is `pd.bdate_range`** (weekdays only): future
  exchange holidays (~9/yr) are not modelled; the error is one grid day, vs
  weeks under the old 252-row convention. An exchange-calendar package would
  be exact but adds a dependency.
- **Dividend forecasts assume the trailing-12M pattern repeats** on
  anniversary ex-dates, proportional to the current spot. Good enough for
  regular payers; special dividends and cuts are not anticipated.
- **`.venv/bin/pip` has a broken shebang** (points at the old
  `Multiasset_Heston_Sim` path) — use `.venv/bin/python -m pip`.

## Note structures beyond Phoenix (implemented)

Both payoffs below are **implemented in `core/note.py:price_note()` and shipped as
configs** — this section documents the live behaviour, not a wishlist. The two
extra fields each is gated on default to a no-op so plain Phoenix notes are
unaffected.

To disable the Phoenix machinery these structures don't use, the shipped configs
set `coupon_pa: 0.0`, `coupon_barrier: 0.0` (guaranteed-but-zero, so no coupon
ever pays), and `autocall_barrier: 2.0` (200% — unreachable, so the note never
autocalls). `autocall_start_period` can stay `1`.

### Bonus Certificate / European Barrier Note with Floor Return

Shipped as `note_configs/puente_mayo_bonus_meli_orcl_meta.json` (PUENTE Mayo,
MELI/ORCL/META, 1Y, 29% floor, 60% European KI).

Payoff at maturity (no autocall, no periodic coupons):
- worst-of(T) ≥ `knock_in_barrier` (European, measured at maturity only): `max(worst-of performance, 1 + min_return)` — full upside with a guaranteed floor.
- worst-of(T) < `knock_in_barrier`: `worst-of performance` (1:1 loss below barrier).

Field: **`min_return`** (float, default `0.0` = no floor). In `price_note()` the
final-step redemption uses `protected_redemption = np.maximum(worst_final, 1.0 +
terms.min_return)` when `min_return > 0` and KI is not breached; capital-loss
paths take the standard 1:1 downside unchanged. There is no separate
participation field — upside participation is always 100%.

### Capital Protected Participation Note (capped upside, guaranteed floor)

Shipped as `note_configs/puente_junio_capital_garantizado_optionA.json`
(100% floor + 15% cap) and `…_optionB.json` (95% floor + 30% cap) — PUENTE Junio,
NU/MELI, 1.5Y.

Payoff at maturity (no KI, no autocall, no periodic coupons):
`np.clip(worst-of(T), capital_guarantee, 1 + upside_cap)`

Fields: **`capital_guarantee`** (float | null, default `null`) and **`upside_cap`**
(float | null, default `null`). `price_note()` has a dedicated early-return
branch gated on `terms.capital_guarantee is not None` that skips the entire
Phoenix waterfall (no autocall, coupon, or KI logic) and returns the clipped
worst-of payoff; `upside_cap = None` means an uncapped ceiling (`+inf`).

## Repo audit (2026-06-11): structure, branding contract, dead code, performance

Ranked within each group by impact.

**Resolution (2026-06-11, same-day fix pass):** all targeted fixes below were
applied and verified — branding contract **B1–B5**, performance **P1–P6**, dead
code **D1–D8**, and doc rot **S4–S5**. The large structural refactors **S1**
(unify the two i18n systems), **S2** (split the ~2000-line `pdf_report.py` /
~1830-line `app.py` into packages) and **S3** (shared logo module) were
deliberately **deferred** — they churn every file the fixes touch and the repo
has no test suite to catch a regression. They remain open below as the next
pass. Verification: `py_compile` across the tree, the engine smoke test, a
headless `AppTest` setup+dashboard run (confirming the P1 session-state shape and
float32 paths), the branding-rebrand unit checks, and the `scripts/verify_pdf.py`
en+es render. The findings below are kept verbatim as the record of what was
found; the deferred S1–S3 entries are the live backlog.

### Branding config — the contract is ad hoc, tuned for CADIEM

The branding JSON works for CADIEM because the PDF's chart-rebrand constants
happen to be tuned to a green palette; it is NOT a general contract:

- **B1 Hard-coded complementary palette** (`app/pdf_report.py`):
  `_BRAND_GOLD = (198,148,38)` and `_GREEN_RAMP_HUE = 150` are module
  constants. A firm with blue/red branding gets brand-colored series but a
  *gold* second category and a *green* hsl ramp on the backtest bar —
  inconsistent for any non-green palette. Fix: derive the ramp hue from the
  branding accent (RGB→HSL) and add an optional `chart_secondary_color` key
  (default gold) to the branding schema.
- **B2 No schema validation**: `app/app.py` just `json.loads` the upload and
  `_resolve_palette` indexes keys directly. A typo (`primary_colour`) is
  silently ignored; a malformed hex (`"green"`) raises deep inside PDF
  generation. Mirror `NoteTerms.from_dict`: warn on unknown keys, validate hex
  with fallback to defaults.
- **B3 Stale schema docs**: the `pdf_report.py` module docstring documents only
  `firm_name/primary_color/accent_color/logo_url` but the loader also supports
  `logo_file` (preferred) and `logo_base64`. `generate_pdf_report`'s docstring
  points to that stale docstring. There is no canonical schema doc; the closest
  is `branding/branding_example.json` (which references a nonexistent
  `branding/acme_logo.png`).
- **B4 Branding is PDF-only** (deliberate but undocumented): the Streamlit UI
  palette is hard-coded in `app/style.css` + `.streamlit/config.toml`. The
  sidebar uploader gives no hint that branding affects only the report.
- **B5 No content keys**: institutional reports carry firm contact/website and
  sometimes custom disclaimer text; the cover eyebrow "STRUCTURED NOTE
  ANALYTICS" and the legal block are hard-coded. Candidate optional keys:
  `report_title`, `website`, `contact`, `footer_note`.

### Performance — why the app feels slow (ranked)

- **P1 Session-state memory blow-up** (`app/app.py` run block): the stored
  `results` dict keeps `sim_results` whole — `S_paths` (a list duplicating
  `sim_prices`) AND `V_paths` — but the dashboard only ever reads
  `sim_results["realized_corr"]`. Measured footprint at the 10K-path default:
  ~630 MB held for a 1.5Y note, ~1.25 GB for 3Y, ~2.1 GB for 5Y; at the 50K
  slider max a 5Y note holds ~10 GB → swap pressure makes *everything* slow.
  Fix: store only `realized_corr` (and drop the write-only `grid_dates` /
  `div_schedule` keys, see D-list); optionally store paths as float32 (halves
  it again). Peak memory during the run is ~2× the stored figure because
  `perf_paths` and the `np.stack` copy coexist; having the simulator return a
  3-D array directly would remove one full copy.
- **P2 Every widget interaction reruns every tab**: clicking "Next path"
  rebuilds the backtest figures, the live tab, and the MC figures. The path
  explorer and the backtest issue-date selector are ideal candidates for
  `@st.fragment` (Streamlit ≥1.33) so navigation reruns only that fragment.
- **P3 MC figures built twice per rerun**: the MC tab builds
  `irr_dist`/`wof_fan`/`corr` once into `_pdf_mc_figures` (for the PDF) and
  then builds the SAME figures again for display. Each `build_wof_fan` call
  runs `np.percentile` over the full (2·n_paths × N) array; the per-asset
  `build_fan_chart` calls add one percentile pass per asset — all repeated on
  every rerun. Fix: build once per (run, lang) and reuse for both display and
  PDF, or cache the percentile bands in `results` at run time.
- **P4 Full-history chart re-serialized per rerun**: `build_historical_prices`
  plots max-history daily closes (decades × n_assets points) and re-sends the
  JSON to the browser on every rerun. Downsample to weekly for display
  (visually identical at that scale).
- **P5 PDF logo fetches are uncached and repeated**: `_load_ticker_logo` is
  called for the cover, the calibration table, and the performance table —
  3 resolutions (and up to 3 × 8s-timeout network fetches) per asset per
  report when no local file exists. Add a per-call memo (the calibration
  table already builds a local `logo_cache`; hoist that to one shared dict per
  `generate_pdf_report` call, or `functools.lru_cache`).
- **P6 matplotlib imported at module top of `core/simulator.py`** (~0.2s import
  + resident memory in the Streamlit process) though only the notebook-only
  `plot()` method uses it. Move the import inside `plot()`.
- (Already on the roadmap: QW1 `Z_full` preallocation, QW2 basket-extraction
  vectorization, QW7 print→logging.)

### Dead code inventory

- **D1 `data/loader.py` bundled-CSV default is broken**: `DEFAULT_CSV_FILES`
  points at `data/SPX.csv`/`SX5E.csv`/`SMI.csv` which do not exist in the repo
  — `load_prices(source="csv")` with defaults raises FileNotFoundError. Either
  drop the csv source's defaults or the dead constants.
- **D2 97 unused translation keys** in `app/translations.py` (389 total, 292
  used) — relics of the pre-rewrite single-page app (`decisiveness_*`,
  `floor_*`, `call_3m/6m/9m`, `tab_fan/payoff/explorer/corr`, `outcome_*`, …).
  Verified by AST scan against all `tr("…")` call sites.
- **D3 `app/app.py:227 _DISPLAY_TO_LABEL`** — built, never read.
- **D4 ~~`NoteTerms.autocall_prob()`~~ (DONE)** — removed; no call sites
  remained and it was wrong for step-down notes.
- **D5 Write-only results keys**: `results["grid_dates"]` and
  `results["div_schedule"]` are stored by the run block and never read.
- **D6 Unused engine outputs**: `price_note`'s `prob_floor` /
  `expected_nominal_payout` and the simulator's `S_terminal` /
  `log_returns_terminal` have no consumers outside internal print summaries
  (keep only if regarded as public API for notebooks).
- **D7 `charts.py:_plain_layout`** is a pure alias of `_apply_theme` (12 call
  sites); the `_GREEN_DARK/_GREEN_MID/_GREEN_LIGHT` aliases now hold navy/blue
  values — rename in one mechanical pass to stop the name/value mismatch.
- **D8 `simulator.plot()`** writes `heston_multi_diagnostics.png` to cwd —
  file I/O inside `core/`, violating the module's own "no file I/O" contract.
  Notebook-only; relocate to a scripts/ helper or guard it.
- NOT dead: the Inter TTC font fallback in pdf_report.py (`fonts/Inter.ttc`
  exists and is the fallback if IBM Plex files are removed).

### Structure & doc rot

- **S1 Two parallel i18n systems**: `app/translations.py` (Translator, UI) and
  `_LABELS` inside `app/pdf_report.py` (~80 keys, PDF). Same strings exist in
  both (e.g. "Análisis de Nota Estructurada"). Unify on Translator or document
  the split; today a wording fix must be made twice.
- **S2 `app/pdf_report.py` is ~2000 lines** mixing five concerns: label
  translations, font registration, logo fetching/conversion, chart color
  remapping, and page layout. Natural split: `app/pdf/` package with
  `labels.py`, `branding.py` (palette + remap + logos), `layout.py` (_NotePDF),
  `report.py` (page builders). Same for `app/app.py` (~1830 lines): the setup
  page and dashboard could be separate modules; the 4 near-identical inline
  logo+name HTML snippets belong in one helper.
- **S3 Logo-resolution logic is scattered**: URL building lives in `app/app.py`
  (`TICKER_LOGOS`, `_LOGO_BASE`, `get_issuer_logo_url`), local-file-first
  resolution in `app/pdf_report.py`. A shared `branding/logos.py` (or
  `app/logos.py`) would give the web UI local-file support for free.
- **S4 Stale docstrings**: `core/simulator.py` titles itself
  "heston_simulator.py", `core/calibrator.py` "heston_calibrator.py";
  `core/__init__.py` references the old project name "Multiasset_Heston_Sim";
  `scripts/verify_pdf.py`'s docstring claims it avoids `app/charts.py` but it
  now imports the real chart builders (intentionally); `HestonParams.mu`
  docstring says "Default 0.0 = risk-neutral" (misleading — there is no
  discounting anywhere; physical measure).
- **S5 CLAUDE.md "New note structures" section describes `min_return` /
  `capital_guarantee` / `upside_cap` as "fields needed"** — they are
  implemented in `core/note.py` and shipped in the PUENTE configs. The section
  should be rewritten as documentation of the implemented payoffs.
