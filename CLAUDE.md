# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the app

```bash
streamlit run app/app.py
```

There are no tests and no linter configured. The project requires Python 3.12+ (f-strings use nested same-quote syntax introduced in 3.12).

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

`price_note()` compares each observation against `terms.autocall_barrier_schedule()` (a per-period array), not a scalar. For constant-barrier notes the schedule is flat and this is identical to the old behaviour; for growth autocalls (`autocall_step_down > 0`) it declines each period from `autocall_start_period`, floored at `autocall_floor`. The standalone `NoteTerms.autocall_prob()` method still exists (scalar barrier) for soft/hard dispatch but the engine path uses the schedule directly.

**Single-asset notes:** `np.corrcoef` collapses to a 0-d scalar for one asset, so `calibrator._corr_SS`/`_corr_VV` wrap it in `np.atleast_2d` (→ `[[1.0]]`). The setup form allows ≥ 1 underlying.

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

These fields are **not** exposed as setup-form widgets; they are preserved from the loaded JSON config across a setup round-trip via `getattr(base, ...)` in `app/app.py`.

## Basket types and final redemption

The `final_basket` + `final_redemption_barrier` fields implement the BBVA-style "best-of rescue": if the best performer at maturity is ≥ `final_redemption_barrier`, the note redeems at par even if the knock-in was breached. With `final_basket="worst_of"` (standard), the rescue condition can never coincide with a barrier event and the logic reduces to standard worst-of.

## Streamlit session state

The app has two pages controlled by `st.session_state["page"]`: `"setup"` and `"dashboard"`. All heavy computation (calibration, simulation, backtest) is cached via `@st.cache_data`. Cache keys for the backtest use `tickers_tuple` (a `tuple` of `(sym, name)` pairs) and `terms.to_json()`. Simulation results are stored in `st.session_state["results"]` and are `None` until the user clicks "Run Simulation".

Because Streamlit ignores a keyed widget's `value=` once its key exists in `session_state`, fields that must be populated from a loaded JSON config (e.g. `setup_issuer`, `setup_issue_date`) push the loaded value into `session_state` *before* the widget renders. Forgetting this is why a config field "doesn't load".

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
- **QW4 Fix/deprecate `autocall_prob()` scalar method** (`core/note.py:333`): compares against `self.autocall_barrier` (scalar) rather than the per-period schedule. Silent wrong probabilities for step-down notes. Remove or add `period_idx` parameter.
- **QW5 IRR denominator guard** (`core/note.py`): `np.maximum(t_held_arr, 1/252)` before division. Defensive guard against any floating-point near-zero edge case.
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

## New note structures

### Bonus Certificate / European Barrier Note with Floor Return

Seen in PUENTE product shelf (e.g. MELI/ORCL/META, 12M, 29% floor, 40% KI protection).

Payoff at maturity:
- If worst-of(T) ≥ knock_in_barrier (European, measured at maturity only):  `max(worst-of performance, 1 + min_return)`
- If worst-of(T) < knock_in_barrier: `worst-of performance` (1:1 loss below barrier)

No autocall, no periodic coupons. New `NoteTerms` fields needed:
- `min_return` (float, e.g. `0.29`): guaranteed minimum return above barrier. Default `0.0` = no floor (standard Phoenix behaviour unaffected).
- `upside_participation` (float, default `1.0`): fraction of worst-of upside above min_return. Always 100% in observed structures.

`price_note()` change: in the final-step redemption block, replace `pay_par` (1.0) with `max(basket_final, 1 + terms.min_return)` when `min_return > 0` and KI not breached. Single `if` branch; no other payoff logic changes.

JSON config example:
```json
{
  "name": "PUENTE Mayo Bonus MELI/ORCL/META",
  "maturity": 1.0,
  "payment_freq": "annual",
  "coupon_pa": 0.0,
  "coupon_barrier": 1.1,
  "autocall_barrier": 99.0,
  "autocall_start_period": 99,
  "knock_in_barrier": 0.60,
  "memory": false,
  "coupon_basket": "worst_of",
  "autocall_basket": "worst_of",
  "final_basket": "worst_of",
  "final_redemption_barrier": 1.0,
  "min_return": 0.29,
  "tickers": {"MELI": "MELI", "ORCL": "ORCL", "META": "META"}
}
```
(Set `coupon_barrier` and `autocall_barrier` impossibly high to disable periodic coupons and autocall effectively; `min_return: 0.29` triggers the floor logic.)

### Capital Protected Participation Note (capped upside, guaranteed floor)

Seen in PUENTE product shelf (e.g. NU/MELI, 18M, 100%/95% capital guarantee + 15%/30% CAP).

Payoff at maturity (no KI, no autocall, no periodic coupons):
`max(capital_guarantee, min(1 + worst-of return, 1 + upside_cap))`

New `NoteTerms` fields needed:
- `capital_guarantee` (float, e.g. `1.0` or `0.95`): floor on redemption. Default `null` = not a capital-protected note.
- `upside_cap` (float, e.g. `0.15` or `0.30`): ceiling on participation return. Default `null` = no cap.
- `min_return` (float): reuse from Bonus Certificate above; set `= capital_guarantee - 1` for unified logic.

`price_note()` change: add a new payoff branch triggered by `terms.capital_guarantee is not None`. In this branch skip all autocall/coupon logic entirely; final payoff = `np.clip(basket_final, terms.capital_guarantee, 1 + terms.upside_cap)`.

JSON config example (Option A: 100% floor + 15% CAP):
```json
{
  "name": "PUENTE Junio Capital Garantizado NU/MELI - Opcion A",
  "maturity": 1.5,
  "payment_freq": "annual",
  "coupon_pa": 0.0,
  "coupon_barrier": 1.1,
  "autocall_barrier": 99.0,
  "autocall_start_period": 99,
  "knock_in_barrier": 1.1,
  "memory": false,
  "coupon_basket": "worst_of",
  "autocall_basket": "worst_of",
  "final_basket": "worst_of",
  "final_redemption_barrier": 1.0,
  "capital_guarantee": 1.0,
  "upside_cap": 0.15,
  "tickers": {"NU": "NU", "MELI": "MELI"}
}
```
