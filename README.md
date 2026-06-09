# Multi-Asset Heston Simulator & Structured Note Engine

A Python framework for calibrating, simulating, and pricing a **multi-asset Heston stochastic volatility model** against real market data, with a full structured product engine for **Phoenix Memory Autocallable notes** on any basket of equity underlyings.

Built as an internal tool at CADIEM Casa de Bolsa and deployed as an interactive dashboard.

---

## Overview

The project covers the full quantitative workflow:

1. **Calibration** — estimate Heston parameters and tail dependence from historical price data via method of moments
2. **Simulation** — simulate correlated multi-asset paths under the physical measure with Milstein discretisation, antithetic variates, and a Student-t copula
3. **Pricing** — evaluate Phoenix Memory Autocallable note payoffs across all simulated scenarios with full memory coupon support
4. **Backtesting** — replay the note on every historical issue date using realized prices
5. **Dashboard** — interactive bilingual (EN/ES) Streamlit app with a setup page and full results dashboard

---

## Project Structure

```
.
├── core/
│   ├── calibrator.py          # Historical Heston calibration pipeline
│   ├── simulator.py           # Multi-asset Heston Monte Carlo engine
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
│   ├── translations.py        # Bilingual string registry (EN/ES)
│   └── __init__.py
│
├── .streamlit/
│   └── config.toml            # Light theme + green palette
│
├── hsbc_xs3376563584.json     # Reference note config — HSBC 24M Monthly Phoenix
├── bbva_xs3378405743.json     # Reference note config — BBVA 18M Quarterly Phoenix
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

---

## Calibration Pipeline

All parameters are estimated from historical daily adjusted close prices.

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

The `NoteTerms` dataclass captures the full specification of a Phoenix Memory Autocallable note. All parameters are configurable and JSON-serialisable.

| Parameter | Description | Default |
|-----------|-------------|---------|
| `maturity` | Note tenor in years | 1.0 |
| `n_obs` | Number of observation periods | 4 |
| `coupon_rate` | Coupon per period (fraction) | 0.025 |
| `coupon_barrier` | Basket must be ≥ this for coupon | 0.55 |
| `autocall_barrier` | Basket must be ≥ this for autocall | 1.00 |
| `autocall_start_period` | First period eligible for autocall | 1 |
| `knock_in_barrier` | European KI checked at final valuation only | 0.55 |
| `principal_protection` | Floor on maturity redemption (no KI) | 1.00 |
| `memory` | Accumulate missed coupons (Phoenix mechanic) | True |
| `coupon_basket` | `worst_of` / `best_of` / `average` | `worst_of` |
| `autocall_basket` | `worst_of` / `best_of` / `average` | `worst_of` |
| `final_basket` | `worst_of` / `best_of` / `average` | `worst_of` |
| `tickers` | `{yf_symbol: display_name}` — stored in JSON config | `{}` |

### Payoff Logic

**At each observation period $j$:**

- **Coupon:** if `coupon_basket ≥ coupon_barrier`, pay `coupon_rate × (pending_periods + 1)` if memory, else `coupon_rate`
- **Autocall** (from `autocall_start_period`): if `autocall_basket ≥ autocall_barrier`, redeem at par

**At maturity (if not autocalled):**

- If `worst_of_final < knock_in_barrier` → cash-equivalent physical delivery: payout = worst-of final performance
- Else → `max(principal_protection, final_basket_final)`

**IRR:** simple annualisation — `total_return / t_held` — consistent with how structured note coupons are quoted.

### Reference Term Sheets

Two real term sheets are included as ready-to-use JSON configs:

| File | Issuer | Underlyings | Tenor | Coupon | KI |
|------|--------|-------------|-------|--------|-----|
| `hsbc_xs3376563584.json` | HSBC | GS / JPM / MS | 24M monthly | 10% p.a. | 55% European |
| `bbva_xs3378405743.json` | BBVA | NVDA / PLTR / TSLA | 18M quarterly | 15% p.a. | 50% European |

Both use memory coupons, 100% autocall barrier, and worst-of basket for coupons/autocall. The BBVA note uses best-of for the final redemption condition.

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
sim_results = sim.run()
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
    n_obs=4, coupon_rate=0.025, coupon_barrier=0.55,
    autocall_barrier=1.00, knock_in_barrier=0.55, memory=True,
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

On first load, a full-page setup form collects:
- **Underlying selection** from ~50 predefined tickers (equity indices, US large caps, European stocks, commodity ETFs) or any custom yfinance symbol
- **Note terms** — all 15 `NoteTerms` parameters across maturity, coupons, barriers, basket types
- **JSON upload** — drag and drop a config file to populate all fields including underlyings at once
- **Download** — export the current configuration as a JSON file

### Dashboard

After confirming setup the dashboard shows:

- **Summary metrics** — expected IRR, total return, expected coupon, P(autocalled), P(knock-in), autocall breakdown by period
- **IRR distribution** — histogram of annualised IRR split by autocalled vs maturity paths, with mean and coupon p.a. reference lines
- **Price path fan charts** — worst-of basket + individual asset fan charts (5/25/50/75/95th percentiles) with observation markers
- **Path explorer** — step through individual Monte Carlo paths; shows per-asset lines and worst-of line with observation markers
- **Correlation diagnostics** — input vs realised correlation heatmaps, Heston parameter table
- **Historical backtest** — outcome distribution bar chart, IRR scatter by issue date, historical path explorer (select any issue date to see the actual realized path with observation markers)
- **Bilingual** — full EN/ES interface

---

## Dependencies

```
numpy >= 1.26, < 3
pandas >= 2.0, < 4
scipy >= 1.11
matplotlib >= 3.7
plotly >= 5.18
yfinance >= 0.2
streamlit >= 1.30
```

---

## Known Limitations & Future Work

| Limitation | Impact | Potential fix |
|-----------|--------|--------------|
| P-measure calibration only | $\rho \approx 0$; no implied vol surface | Carr-Madan / characteristic function calibration from options |
| In-sample backtest | Calibration window overlaps backtest window | Expanding-window calibration |
| Euler price step | Minor bias with stochastic vol | Full Milstein for price process |
| Single $\nu$ across assets | Ignores per-asset tail structure | Per-asset copula or vine copula |
| No Greeks | Cannot hedge positions | Bump-and-reprice or adjoint AD |

**Planned extensions:** risk-neutral calibration, barrier and Asian options, variance swap pricing, GPU acceleration (CuPy), Sobol quasi-Monte Carlo, Greeks.

---

## Disclaimer

This project was developed for quantitative research and internal use. It is not investment advice and should not be used as the sole basis for investment decisions.
