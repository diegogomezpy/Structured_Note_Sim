# Multi-Asset Heston Simulator & Structured Note Engine

A Python framework for calibrating, simulating, and pricing a **multi-asset Heston stochastic volatility model** against real market data, with a full structured product engine for **autocallable and structured notes** — Phoenix Memory, Reverse Convertible, Growth/Classic (step-down) autocalls, Bonus Certificates, and Capital-Protected notes, with an optional One Star best-of overlay — on any basket of equity underlyings (single-asset notes supported).

Built as an internal tool and deployed as an interactive dashboard with a branded, bilingual PDF report.

**▶️ Live app: [structurednotesim.streamlit.app](https://structurednotesim.streamlit.app/)**

---

## Overview

The project covers the full quantitative workflow:

1. **Calibration** — estimate Heston parameters and tail dependence from historical price data via method of moments
2. **Simulation** — simulate correlated multi-asset paths under the physical measure with Milstein discretisation, antithetic variates, and a Student-t copula
3. **Pricing** — evaluate autocallable note payoffs across all simulated scenarios with full memory coupon, guaranteed coupon, and growth-autocall premium support
4. **Backtesting** — replay the note on every historical issue date using realized prices
5. **Dashboard** — interactive bilingual (EN/ES) Streamlit app that frames the note through three lenses (simulate → backtest → live), with a setup page, live "Current Performance" tracking, and a branded one-click PDF report

---

## Project Structure

```
.
├── core/
│   ├── calibrator.py          # Historical Heston calibration pipeline
│   ├── simulator.py           # Multi-asset Heston Monte Carlo engine (run(engine=...))
│   ├── simulator_cpp.py       # Thin wrapper over the optional compiled C++ engine
│   ├── note.py                # NoteTerms dataclass + vectorized payoff engine
│   ├── backtest.py            # Historical backtest using realized prices
│   └── __init__.py            # Public API: HestonParams, NoteTerms, price_note, ...
│
├── data/
│   ├── loader.py              # load_prices() — yfinance / CSV / DataFrame backends
│   └── __init__.py
│
├── app/
│   ├── app.py                 # Streamlit dashboard (setup page + results dashboard)
│   ├── charts.py              # All Plotly figure builders as pure functions
│   ├── pdf_report.py          # Branded PDF report generator (fpdf2 + kaleido)
│   ├── translations.py        # Bilingual string registry (EN/ES)
│   ├── underlyings.py         # Selectable ticker universe + logo maps
│   ├── style.css              # Streamlit theme (matches the PDF)
│   └── __init__.py
│
├── note_configs/             # 13 ready-to-use JSON term sheets (upload in the app)
│                             #   HSBC ×2, BBVA, Citi, Santander ×3, Barclays,
│                             #   BNP Paribas, Julius Baer, PUENTE ×3
├── branding/                 # Firm branding JSON + bundled ticker logos
│   ├── branding_example.json #   documented template (all keys)
│   └── ticker_logos/         #   optional local PNG logos
├── fonts/                    # IBM Plex Sans (embedded in the PDF)
├── cpp/                      # Optional compiled engine (pybind11 + block-SIMD + std::thread)
│   ├── heston_kernel.cpp     #   the kernel; validated against numpy by convergence
│   ├── CMakeLists.txt        #   build (scikit-build-core); `pip install ./cpp`
│   └── README.md             #   build / benchmark / wiring notes
├── scripts/
│   ├── verify_pdf.py         # Standalone PDF-render harness (needs PyMuPDF)
│   └── compare_engines.py    # Validate + benchmark the C++ engine vs numpy
│
├── .streamlit/
│   └── config.toml           # Light theme + navy/blue palette
│
├── packages.txt              # apt packages for Streamlit Cloud (chromium → PDF export)
├── requirements.txt
└── README.md
```

---

## Model

### Price Process (Physical Measure)

For each asset $i$:

$$dS_i = S_i \left( \mu_i \, dt + \sqrt{V_i} \, dW_{S_i} \right)$$

$$dV_i = \kappa_i(\theta_i - V_i)\,dt + \xi_i\sqrt{V_i}\,dW_{V_i}$$

$$\text{Corr}(dW_{S_i}, dW_{V_i}) = \rho_i$$

### Correlation Structure

Cross-asset dependence is captured through a full $2n \times 2n$ block correlation matrix:

$$C = \begin{pmatrix} \Sigma_{SS} & \Sigma_{SV} \\ \Sigma_{SV}^\top & \Sigma_{VV} \end{pmatrix}$$

- $\Sigma_{SS}$: return-return correlations (2-day overlapping to correct for timezone gaps between US and European closes)
- $\Sigma_{VV}$: variance-variance correlations
- $\Sigma_{SV}$: diagonal matrix of per-asset leverage effects $\rho_i$

If the assembled matrix is not PSD, a nearest-PSD projection (Higham 2002) is applied automatically.

---

## Simulation Engine

### Discretisation — Milstein Scheme

The variance process uses Milstein rather than Euler-Maruyama, reducing discretisation bias near $V = 0$:

$$V_{t+dt} = V_t + \kappa(\theta - V_t)\,dt + \xi\sqrt{V_t}\,dW_V + \tfrac{1}{2}\xi^2\left(dW_V^2 - dt\right)$$

Full truncation ($V$ floored at 0) after each step. Price step uses log-Euler:

$$S_{t+dt} = S_t \exp\!\left(\mu\,dt - \tfrac{1}{2}V_t\,dt + \sqrt{V_t}\,dW_S\right)$$

### Variance Reduction — Antithetic Variates

For every batch of $n$ base paths, an antithetic batch is generated using $-Z$, doubling effective path count at zero additional cost.

### Tail Dependence — Student-t Copula

At each time step the Gaussian increments are scaled by $\sqrt{\chi^2(\nu)/\nu}$ to produce joint heavy tails:

$$W = \frac{Z}{\sqrt{s}} \cdot L^\top, \quad s \sim \chi^2(\nu)/\nu$$

$\nu$ is calibrated automatically from historical returns via per-asset MLE, with the median taken across assets. Typical values are $\nu \approx 4$–$5$ for equity indices.

### Optional Compiled Engine (C++)

`HestonMultiSimulator.run()` defaults to the vectorised **numpy** engine (always available, no build step — the reference implementation). An optional **compiled C++ engine** runs the identical model faster:

```python
sim.run()                 # numpy reference (default) — what the app uses
sim.run(engine="cpp")     # compiled engine; raises ImportError if not built
```

It is block-SIMD (the per-step `exp`/`sqrt`/`sin`/`cos` vectorise across a contiguous block of paths via a vector libm) with a branch-free Box–Muller xoshiro256++ RNG, and parallelised across path-blocks with `std::thread` (no OpenMP/libomp dependency). It keeps full daily paths and is validated against numpy by **convergence of statistics**, not bit-equality (different RNG stream). Build it with `pip install ./cpp`; in the app, pick the engine in *Simulation engine settings*. See [`cpp/README.md`](cpp/README.md) for build, benchmarks, and the threads knob (`HESTON_NUM_THREADS`).

---

## Calibration Pipeline

All parameters are estimated from historical daily **adjusted** close prices (total-return dynamics). Barrier observation, the backtest, and live tracking use **raw** official closes — the levels term sheets actually fix against — and the simulator applies pre-programmed proportional dividend jumps at forecast ex-dates to convert total-return paths into price paths.

| Step | Parameter | Method |
|------|-----------|--------|
| 1 | Data loading | CSV / yfinance / DataFrame |
| 2 | Return construction | 1-day $r_1$ (RV, leverage); 2-day $r_2$ (correlation) |
| 3 | $\theta$ | Sample variance of $r_1$, annualised |
| 4 | $V_0$ | Most recent 21-day rolling realised variance |
| 5 | $\kappa$ | AR(1) of RV series: $\kappa = -\log(\hat\phi)/dt$ |
| 6 | $\xi$ | Std of RV increments normalised by $\sqrt{\theta \cdot dt}$ |
| 7 | $\rho$ | $\text{Corr}(r_t, \Delta\text{RV}_t)$ |
| 8 | $\mu$ | Sample mean log-return, annualised |
| 9 | $\nu$ | MLE $t$-fit per asset, median across assets |
| 10 | $\Sigma_{SS}, \Sigma_{VV}$ | Pearson correlation of 2-day returns / RV series |
| 11 | Feller condition | Enforced by nudging $\kappa$ if $2\kappa\theta < \xi^2$ |

**Note on $\rho$:** The 2021–2026 calibration window is dominated by a sustained bull market. Calibrated $\rho$ values are near zero rather than the textbook $-0.65$ for SPX — this is what the data shows under the physical measure. A risk-neutral calibration from the options surface would recover the expected negative $\rho$.

**Note on $\nu$:** MLE gives $\nu \approx 4$ for this dataset (SPX: 3.9, SX5E: 4.1, SMI: 4.7), indicating heavy tails consistent with the volatility events in the sample period.

---

## Structured Note Engine

### Supported Note Types

The `NoteTerms` dataclass captures the full specification of an autocallable note. A single engine (`price_note()`) covers all variants below — the differences are entirely in the configured fields. All parameters are configurable and JSON-serialisable.

- **Phoenix Memory** — periodic coupon paid when the basket clears `coupon_barrier`, missed coupons accumulate (`memory=True`).
- **Reverse Convertible** — guaranteed coupon: set `coupon_barrier=0.0` so it pays every period regardless of level.
- **Growth / Classic (step-down) Autocall** — no periodic coupon; an accrued premium is paid only at autocall, and the autocall barrier steps down over time (`autocall_step_down`, `autocall_floor`, `coupon_at_autocall_only`).
- **Bonus Certificate** — full upside participation with a guaranteed floor return when the KI is not breached (`min_return`); 1:1 downside if it is.
- **Capital Protected** — a standalone payoff that skips the entire autocall/coupon/KI waterfall: redemption is `clip(worst-of, capital_guarantee, 1 + upside_cap)`.
- **One Star overlay** — orthogonal to the above: a single underlying at or above `one_star_level` satisfies the coupon, autocall, **and** final-redemption conditions on its own (BNP-style; also models the BBVA "Barrier and Knock-in" rescue).

| Parameter | Description | Default |
|-----------|-------------|---------|
| `maturity` | Note tenor in years | 1.0 |
| `payment_freq` | Observation frequency (`monthly`/`quarterly`/`semi-annual`/`annual`) | `quarterly` |
| `coupon_pa` | Annualised coupon rate (e.g. `0.10` = 10% p.a.) | 0.10 |
| `coupon_barrier` | Basket must be ≥ this for coupon (`0.0` = guaranteed) | 0.55 |
| `autocall_barrier` | Basket must be ≥ this for autocall | 1.00 |
| `autocall_start_period` | First period eligible for autocall (1-indexed, ≥ 1) | 1 |
| `knock_in_barrier` | European KI — checked only at final valuation date | 0.55 |
| `principal_protection` | Maturity redemption when no capital loss | 1.00 |
| `memory` | Accumulate missed coupons (Phoenix mechanic) | True |
| `coupon_basket` | `worst_of` / `best_of` / `average` | `worst_of` |
| `autocall_basket` | `worst_of` / `best_of` / `average` | `worst_of` |
| `one_star_level` | Best-of OR-overlay level — one underlying ≥ this satisfies coupon / autocall / redemption; `null` = off | `None` |
| `autocall_step_down` | Per-period decrement of the autocall barrier (0 = constant) | 0.0 |
| `autocall_floor` | Minimum autocall barrier under step-down | `None` |
| `coupon_at_autocall_only` | No periodic coupon; accrued premium paid as a lump at autocall | False |
| `min_return` | Bonus Certificate floor return when KI not breached (e.g. `0.29` = +29%) | 0.0 |
| `capital_guarantee` | Capital-Protected guaranteed redemption (e.g. `1.00`); activates the standalone CP payoff | `None` |
| `upside_cap` | Maximum redemption above par under CP (e.g. `0.15` = 1.15 cap) | `None` |
| `issuer` | Issuing bank, display only (e.g. `"BBVA"`) — shows a logo in the app | `""` |
| `issuer_description` / `issuer_rating_sp` / `_moody` / `_fitch` | Optional issuer profile for the PDF "Issuer Information" section | `""` |
| `tickers` | `{yf_symbol: display_name}` — stored in JSON config | `{}` |
| `issue_date` | `"YYYY-MM-DD"` — enables Current Performance tab when set | `None` |

> **Derived fields** (never stored, always computed): `n_obs = maturity × periods_per_year`, `coupon_rate = coupon_pa / periods_per_year`.
>
> **Legacy fields** `final_basket` + `final_redemption_barrier` are auto-migrated to `one_star_level` by `NoteTerms.from_dict` (best-of → the barrier level; otherwise off).

### Payoff Logic

**At each observation period $j$:**

- **Coupon:** if `coupon_basket ≥ coupon_barrier`, pay `coupon_rate × (pending_periods + 1)` if memory, else `coupon_rate`. With `coupon_barrier = 0.0` this becomes a guaranteed coupon (Reverse Convertible).
- **Autocall** (from `autocall_start_period`): if `autocall_basket ≥ autocall_barrier_schedule[j]`, redeem at par. The barrier is constant unless `autocall_step_down > 0`, in which case it declines each period (floored at `autocall_floor`).

**Growth / Classic autocall** (`coupon_at_autocall_only = True`): no periodic coupon is paid. Instead an accrued premium of `coupon_rate × j` is paid as a lump **only** when the note autocalls at period $j$ (zero if held to maturity).

**At maturity (if not autocalled):**

- **One Star rescue:** if `one_star_level` is set and the best performer ≥ `one_star_level` → redeem at `principal_protection` (par) regardless of the KI
- **Capital loss:** if `worst_of_final < knock_in_barrier` AND not rescued → cash-equivalent physical delivery: payout = worst-of final performance
- **Bonus floor:** if KI not breached and `min_return > 0` → redeem at `max(worst_of_final, 1 + min_return)`
- **Par redemption:** otherwise → `principal_protection`

**Capital-Protected note** (`capital_guarantee` set): a standalone branch that bypasses the waterfall entirely — redemption is `clip(worst_of_final, capital_guarantee, 1 + upside_cap)`, no autocall, coupons, or KI.

**IRR:** simple annualisation — `total_return / t_held` — consistent with how structured note coupons are quoted.

### Reference Term Sheets

Thirteen real term sheets are included as ready-to-use JSON configs (upload any of them on the setup page):

| File | Issuer | Type | Underlyings | Tenor | Coupon | KI |
|------|--------|------|-------------|-------|--------|-----|
| `hsbc_xs3376563584.json` | HSBC | Phoenix Memory | GS / JPM / MS | 24M monthly | 10% p.a. | 55% European |
| `bbva_xs3378405743.json` | BBVA | Phoenix (One Star rescue) | NVDA / PLTR / TSLA | 18M quarterly | 15% p.a. | 50% European |
| `citi_xs3096699163.json` | Citi | Growth autocall (step-down) | GOOGL / AMZN / AAPL | 2Y quarterly | 12% p.a. premium | 53.7% European |
| `santander_xs3242406752.json` | Santander | Phoenix Memory | C / GLE.PA / MS | 2Y quarterly | 10.6% p.a. | 50% European |
| `santander_xs3242417106.json` | Santander | Phoenix Memory | C / GLE.PA / MS | 2Y quarterly | 10.6% p.a. | 50% European |
| `santander_C_GLE.PA_MS.json` | Santander | Phoenix Memory | C / GLE.PA / MS | 2Y quarterly | 12.35% p.a. | 50% European |
| `hsbc_xs3287776739.json` | HSBC | Phoenix (single asset) | AMD | 18M quarterly | 18% p.a. | 55.5% European |
| `barclays_xs3305367727.json` | Barclays | Reverse Convertible | ORCL / ADBE | 1Y monthly | 15.25% p.a. guaranteed | 50% European |
| `bnp_paribas_pr00529720.json` | BNP Paribas | Phoenix One Star | DELL / IBM / MSFT | 1Y quarterly | 16% p.a. | 50% European |
| `julius_baer_pr00529635.json` | Julius Baer | Phoenix Memory | DELL / IBM / MSFT | 1Y quarterly | 28% p.a. | 50% European |
| `puente_mayo_bonus_meli_orcl_meta.json` | PUENTE | Bonus Certificate | MELI / ORCL / META | 1Y | +29% floor | 60% European |
| `puente_junio_..._optionA.json` | PUENTE | Capital Protected | NU / MELI | 18M | 100% floor, 15% cap | — |
| `puente_junio_..._optionB.json` | PUENTE | Capital Protected | NU / MELI | 18M | 95% floor, 30% cap | — |

The Citi note demonstrates the step-down barrier (100% declining 3%/period from obs 3, floored at 88%) with a 12% p.a. premium paid only at autocall. The Barclays note pays a guaranteed coupon every month (`coupon_barrier = 0.0`). The BNP One Star note redeems at par if any single underlying ≥ 100% at maturity even when the worst-of breached the KI. The PUENTE Bonus and Capital-Protected configs exercise the `min_return` and `capital_guarantee` payoff branches.

---

## Data Loading

```python
from data.loader import load_prices

# Pull live from yfinance (default, 5-year window)
prices = load_prices()

# Custom tickers
prices = load_prices(
    source="yfinance",
    tickers={"GS": "GS", "JPM": "JPM", "MS": "MS"},
    years=3,
)

# Pre-loaded DataFrame
prices = load_prices(source="df", df=my_df)
```

---

## Usage

### Calibration

```python
from data.loader import load_prices
from core.calibrator import HestonCalibrator

prices = load_prices(tickers={"^GSPC": "SPX", "^STOXX50E": "SX5E", "^SSMI": "SMI"})
cal    = HestonCalibrator(prices_df=prices)
result = cal.calibrate()
# result.params  — list of HestonParams
# result.corr_SS — (n, n) return correlations
# result.t_dof   — calibrated Student-t degrees of freedom
```

### Simulation

```python
from core.simulator import HestonMultiSimulator

sim = HestonMultiSimulator(
    params=result.params, corr_SS=result.corr_SS,
    corr_VV=result.corr_VV, corr_SV=result.corr_SV,
    T=1.0, N=252, n_paths=10_000, seed=42, t_dof=result.t_dof,
)
sim_results = sim.run()              # or sim.run(engine="cpp") once `pip install ./cpp` is built
```

### Note Pricing

```python
import numpy as np
from core.note import NoteTerms, price_note

# Build perf_paths: (n_paths, N+1, n_assets)
sim_prices = np.stack(sim_results["S_paths"], axis=2)
S0_vec     = np.array([p.S0 for p in result.params]).reshape(1, 1, -1)
perf_paths = sim_prices / S0_vec

terms = NoteTerms(
    maturity=1.0, payment_freq="quarterly", coupon_pa=0.10,
    coupon_barrier=0.55, autocall_barrier=1.00,
    knock_in_barrier=0.55, memory=True,
)
output = price_note(perf_paths, terms, seed=43)
print(f"Expected IRR:  {output['expected_irr']:.2%}")
print(f"P(autocalled): {output['prob_autocall']:.2%}")
print(f"P(knock-in):   {output['prob_knock_in_total']:.2%}")
```

### Load a note from JSON

```python
terms = NoteTerms.from_json(open("hsbc_xs3376563584.json").read())
```

### Historical Backtest

```python
from core.backtest import run_backtest

bt, summary = run_backtest(prices, terms)
print(f"Mean IRR:    {summary['mean_irr']:.2%}")
print(f"Autocalled:  {summary['prob_called']:.1%}")
print(f"Knock-in:    {summary['prob_knock_in']:.1%}")
```

---

## Dashboard

```bash
pip install -r requirements.txt
streamlit run app/app.py
```

### Setup Page

On first load, a stepped full-page setup form collects:
- **Underlying selection** from ~75 predefined tickers (equity indices, US large caps, European stocks, commodity ETFs) or any custom yfinance symbol — one or more underlyings (single-asset notes are supported)
- **Note terms** — maturity, coupons, barriers, basket types, and issuer
- **JSON upload** — drag and drop a config file to populate all fields including underlyings at once. Advanced fields without a UI widget (step-down barrier, growth-autocall premium) are carried through from the loaded config.
- **Custom logos** — optionally upload your own company logos for the underlyings, used in the app cards and the PDF when a favicon is a poor fit
- **Download** — export the current configuration as a JSON file

### Dashboard

After confirming setup, the dashboard frames the note through three **analysis lenses** — the same note seen forward, backward, and live. Each tab opens with a consistent intro band stating the question it answers:

**Monte Carlo — _"what could happen?"_**
- Summary metrics — expected IRR, total return, expected coupon, P(autocalled), P(knock-in), and the autocall breakdown by period
- IRR distribution — a discrete two-panel chart (expected total return and mean IRR p.a. per scenario: each autocall period vs held-to-maturity). Structured-note IRRs cluster on a few discrete outcomes, so a continuous histogram collapses to spikes — the discrete view is the default for all notes
- Price-path fan charts — worst-of basket + per-asset fans (1/5/25/50/75/95/99th percentile bands, precomputed once per run) with observation markers
- Path explorer — query and step through individual simulated paths (filter by outcome, autocall period, knock-in, total-return band, or "coupon paid at period t"), with side-by-side comparison panels and per-observation note-mechanic legends
- Correlation diagnostics — input vs realised correlation heatmaps + the Heston parameter table

**Historical Backtest — _"what would have happened?"_**
- Replays the note on every valid historical issue date using realized prices: outcome-distribution bar chart, IRR scatter by issue date, and a path explorer (pick any issue date to see the actual realized path with observation markers)

**Current Performance — _"what is happening now?"_** (notes with a past `issue_date`)
- Live worst-of level vs. barriers, per-asset performance with logos, coupons paid to date, and progress through the note's life

Across all three:

- **PDF report** — a branded, bilingual one-click export (sidebar). A **build-report panel** picks exactly which sections and figures to include, and the report can be generated **without running the simulation first** (it still carries the Monte Carlo section). The PDF mirrors the three-lens structure with numbered part dividers and a grouped table of contents. Per-firm **branding** — colours, logo, report title, disclaimer — is driven by a `branding/branding_*.json` file (see `branding_example.json` for the full key set).
- **Bilingual** — full EN/ES interface throughout the app and the report

---

## Deployment

The app is hosted on **Streamlit Community Cloud** at
[structurednotesim.streamlit.app](https://structurednotesim.streamlit.app/),
auto-redeploying from `main` on every push. Notes on running it reliably
long-term:

- **`requirements.txt` is pinned** with upper bounds so a future rebuild on the
  cloud can't silently pull a breaking major release. Bump versions
  deliberately and re-pin.
- **`yfinance` is the single point of failure.** All live data flows through it,
  and Yahoo periodically changes its undocumented endpoints, breaking yfinance
  until it's patched. If the app starts failing to load prices, bump `yfinance`
  first (`pip install -U yfinance`) and re-pin. Data-load failures surface as a
  clean in-app message (with a retry hint), not a traceback.
- **Path-count ceiling for memory.** The engine keeps full daily paths, so MC
  peak memory scales with `n_paths × n_steps × n_assets`. The "Monte Carlo paths"
  slider is capped at **15,000 on Streamlit Cloud** (auto-detected, ~1 GB tier)
  and **250,000 locally**; override with the **`SNSIM_MAX_PATHS`** environment
  variable. Two safeguards back this up: a **live memory estimate** next to the
  slider warns before you commit, and a **pre-run guard** stops a run whose
  estimated peak exceeds physical RAM (it would only swap and hang) with a
  recommended path count instead. The retained per-path arrays are stored
  compactly (float16 performance + precomputed fan bands; the worst-of is derived
  on demand), and an optional **"Store paths on disk"** toggle memory-maps them so
  they live in evictable OS cache rather than process RAM on a tight machine.
- **Cold starts:** the Community Cloud instance sleeps after inactivity; the
  first visitor waits ~30 s for it to wake. This is expected, not a failure.

```bash
# local run
pip install -r requirements.txt
streamlit run app/app.py

# local run with a tighter path cap (e.g. on a low-memory machine)
SNSIM_MAX_PATHS=8000 streamlit run app/app.py
```

---

## Dependencies

Pinned in `requirements.txt` with upper bounds, so a future rebuild can't pull
an incompatible major release (see [Deployment](#deployment)):

```
numpy >= 2.4, < 3
pandas >= 3.0, < 4
scipy >= 1.17, < 2
matplotlib >= 3.7, < 4   # notebook-only; lazy-imported, never loaded by the app
plotly >= 6.8, < 7
yfinance >= 1.4, < 2     # most fragile dep — bump first if live data stops loading
streamlit >= 1.58, < 2
fpdf2 >= 2.8, < 3        # PDF report
kaleido >= 1.3, < 2      # Plotly figure export for the PDF
Pillow >= 12, < 13       # logo handling in the PDF
```

`PyMuPDF` is **not** a runtime dependency — it is only used by
`scripts/verify_pdf.py` to rasterise PDFs for eyeballing. Install it ad hoc.

---

## Scope, Limitations & Future Work

**What this is:** a forward-scenario, backtesting, and visualization tool for structured notes. It calibrates Heston to historical data under the **physical (P) measure**, simulates plausible real-world paths, evaluates the note's payoff across them, replays it on actual history, and tracks it live — answering _"what could happen / what would have happened / what's happening now"_ for a given note.

**What it is not:** a risk-neutral derivatives-pricing or hedging engine. It does not produce an arbitrage-free fair value, calibrate to an implied-volatility surface, or compute Greeks — that is a different (Q-measure) tool, and deliberately out of scope here.

| Limitation | Impact | Note |
|-----------|--------|------|
| Physical-measure (P) calibration — *by design* | Calibrated $\rho \approx 0$ on the recent bull-market sample (not the textbook $-0.65$); paths reflect likely *real-world* outcomes, not arbitrage-free prices | Intentional for scenario analysis; a longer / regime-mixed calibration window shifts $\rho$ |
| In-sample backtest | The calibration window overlaps the backtest window | Expanding-window / walk-forward calibration would remove the overlap |
| Log-Euler price step | Minor discretisation bias under stochastic vol | Full Milstein for the price process |
| Single $\nu$ across assets | Ignores per-asset tail structure | Per-asset or vine copula |

**Planned extensions** — all in service of better/faster *scenarios*, not pricing: GPU acceleration (CuPy) stacking on the C++ engine, Sobol quasi-Monte Carlo for faster convergence, expanding-window calibration, and additional structured-note payoff variants.

---

## Disclaimer

This project was developed for quantitative research and internal use. It is not investment advice and should not be used as the sole basis for investment decisions.
