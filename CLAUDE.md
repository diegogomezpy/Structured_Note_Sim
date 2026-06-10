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

### Single payoff engine for MC and backtest

`core/note.py:price_note()` is the sole payoff evaluator. Both the Monte Carlo path and the historical backtest construct a `perf_paths: (n_paths, N+1, n_assets)` array (performance relative to S0) and pass it directly to `price_note()`. There is deliberately no second payoff implementation in `backtest.py`. Any payoff change must be made once, in `price_note()`, and it will apply to both.

### NoteTerms design

`NoteTerms` stores human-readable fields (`maturity`, `payment_freq`, `coupon_pa`) and derives `n_obs`, `coupon_rate`, `periods_per_year` as `@property`. The JSON configs and UI sliders use the human-readable fields only. Derived values are never stored.

`from_dict` / `from_json` handle legacy configs that stored `n_obs` + `coupon_rate` directly — these are back-converted on load. Unknown keys in the input dict are **not** silently dropped: `from_dict` emits `warnings.warn` listing any unrecognised keys, so JSON typos surface immediately.

`autocall_start_period` is validated in `__post_init__`: values < 1 raise `ValueError`. (A value of 0 would silently resolve to Python's `[-1:]` slice and enable only the last period.)

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

## Charts — barrier lines

`build_wof_fan` and `build_path_wof_chart` both accept an optional `autocall_barrier` kwarg and draw it as a grey dotted line. The KI barrier is drawn as a red dashed line labelled "Knock-in barrier". Pass both from the caller:

```python
build_wof_fan(wof_paths, t_grid, terms.knock_in_barrier, obs_pairs, tr,
              autocall_barrier=terms.autocall_barrier)
```

`build_historical_wof_path` requires a `coupon_barrier` parameter (separate from `knock_in_barrier`) — it is used to colour observation markers green (coupon paid) or red (missed). Do not conflate with the KI barrier.
