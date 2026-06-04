# Multi-Asset Heston Simulator & Structured Note Engine

A Python framework for calibrating, simulating, and pricing a **multi-asset Heston stochastic volatility model** against real market data, with a full structured product engine applied to a **worst-of callable note** on SPX / SX5E / SMI.

**Live demo:** [worst-of-note-dashboard.streamlit.app](https://worst-of-note-dashboard.streamlit.app)

---

## Overview

The project covers the full quantitative workflow:

1. **Calibration** — estimate Heston parameters and tail dependence from historical price data
2. **Simulation** — simulate correlated multi-asset paths under the physical measure
3. **Pricing** — evaluate structured note payoffs across all simulated scenarios
4. **Backtesting** — replay the note on every historical issue date using realized prices
5. **Dashboard** — interactive bilingual (EN/ES) Streamlit app with green/white theme

---

## Project Structure

```
.
├── heston_calibrator.py       # Historical calibration pipeline
├── heston_simulator.py        # Multi-asset Heston Monte Carlo engine
├── structured_note_sim.py     # Note payoff engine + historical backtest
├── app.py                     # Streamlit dashboard
├── SPX.csv                    # S&P 500 adjusted closes (Yahoo Finance)
├── SX5E.csv                   # Euro Stoxx 50 adjusted closes
└── SMI.csv                    # Swiss Market Index adjusted closes
```

---

## Model

### Price Process (Physical Measure)

For each asset $i$:

$$dS_i = S_i \left( \mu_i \, dt + \sqrt{V_i} \, dW_{S_i} \right)$$

$$dV_i = \kappa_i(\theta_i - V_i)\,dt + \xi_i\sqrt{V_i}\,dW_{V_i}$$

$$\text{Corr}(dW_{S_i}, dW_{V_i}) = \rho_i$$

where $\mu_i$ is the annualised drift estimated from historical returns under the physical (P) measure.

### Correlation Structure

Cross-asset dependence is captured through a full $2n \times 2n$ block correlation matrix:

$$C = \begin{pmatrix} \Sigma_{SS} & \Sigma_{SV} \\ \Sigma_{SV}^\top & \Sigma_{VV} \end{pmatrix}$$

- $\Sigma_{SS}$: return-return correlations
- $\Sigma_{VV}$: variance-variance correlations  
- $\Sigma_{SV}$: diagonal matrix of per-asset leverage effects $\rho_i$

If the assembled matrix is not PSD, a nearest-PSD projection (Higham 2002) is applied automatically.

---

## Simulation Engine

### Discretization — Milstein Scheme

The variance process uses the Milstein scheme rather than Euler-Maruyama, reducing discretization bias especially near $V = 0$:

$$V_{t+dt} = V_t + \kappa(\theta - V_t)\,dt + \xi\sqrt{V_t}\,dW_V + \tfrac{1}{2}\xi^2\left(dW_V^2 - dt\right)$$

Full truncation ($V$ floored at 0) is applied after each step. The price step uses log-Euler (exact for geometric Brownian motion):

$$S_{t+dt} = S_t \exp\!\left(\mu\,dt - \tfrac{1}{2}V_t\,dt + \sqrt{V_t}\,dW_S\right)$$

### Variance Reduction — Antithetic Variates

For every batch of $n$ paths, an antithetic batch is generated using $-Z$, doubling the effective path count at no additional random number cost. Reported output contains $2n$ paths.

### Tail Dependence — Student-t Copula

The Gaussian copula is replaced with a Student-t copula to capture joint tail dependence — the empirically observed tendency for equity indices to crash together more often than the Gaussian model implies. At each time step:

$$Z \sim \mathcal{N}(0, I_{2n}), \quad s \sim \chi^2(\nu)/\nu, \quad W = \frac{Z}{\sqrt{s}} \cdot L^\top$$

The degrees of freedom $\nu$ are **calibrated automatically** from the historical return data using MLE of a univariate $t$-distribution fit to each asset, with the median taken across assets. Typical values are $\nu \approx 4$–$5$ for equity indices.

### Vectorized Realized Correlation

Realized correlations are computed via a single `einsum` over all paths simultaneously rather than a per-path `np.corrcoef` loop, giving approximately 100× speedup.

---

## Calibration Pipeline

All parameters are estimated from historical daily adjusted close prices.

| Step | What | Method |
|------|------|--------|
| 1 | Data loading | CSV / yfinance / DataFrame |
| 2 | Return construction | 1-day $r_1$ (RV, leverage); 2-day $r_2$ (correlation) |
| 3 | Realized variance | Rolling 21-day window, annualized |
| 4 | $\theta$ | Sample variance of $r_1$ |
| 5 | $V_0$ | Most recent rolling RV |
| 6 | $\kappa$ | AR(1) of RV series: $\kappa = -\log(\phi)/dt$ |
| 7 | $\xi$ | Std of RV increments normalized by $\sqrt{\theta \cdot dt}$ |
| 8 | $\rho$ | $\text{Corr}(r_t, \Delta\text{RV}_t)$ |
| 9 | $\mu$ | Sample mean log-return, annualized |
| 10 | $\nu$ | MLE $t$-fit per asset, median across assets |
| 11 | $\Sigma_{SS}, \Sigma_{VV}$ | Pearson correlation of 2-day returns / RV series |
| 12 | Feller condition | Enforced by nudging $\kappa$ if $2\kappa\theta < \xi^2$ |

**Note on $\rho$:** The 2021–2026 calibration window is dominated by a sustained bull market where returns and volatility were largely uncorrelated. The calibrated $\rho$ values are near zero or slightly positive rather than the textbook $-0.65$ for SPX. This is what the data shows, not a model error. A risk-neutral calibration from the options surface would recover the expected negative $\rho$.

**Note on $\nu$:** The MLE fit gives $\nu \approx 4$ for this dataset (SPX: 3.9, SX5E: 4.1, SMI: 4.7), indicating heavy tails consistent with the volatility events in the sample period.

Optional MLE refinement of the variance parameters ($\kappa, \theta, \xi, \rho$) is available via `mle_refine=True`.

---

## Structured Note

The engine prices a **12-month worst-of callable note** on SPX / SX5E / SMI, matching the structure of a real product currently offered by SILEX Partners.

### Terms

| Parameter | Value |
|-----------|-------|
| Underlyings | SPX, SX5E, SMI (worst-of) |
| Maturity | 12 months |
| Capital Floor | 95% (configurable) |
| Call Strike | 95% of worst-of |
| Issuer Call Dates | 3M, 6M, 9M |
| Coupon if Called | 10% p.a. pro-rata (configurable) |
| Upside at Maturity | 100% participation above floor, no cap |

### Payoff

**If issuer calls at date $t$:**
$$\text{Payout} = 100\% + \text{Coupon} \times t$$

**At maturity:**
$$\text{Payout} = 95\% + \max(0,\ \text{Worst-of Final} - 95\%)$$

### Issuer Call Model

The call is modelled as **discretionary**, not automatic. The issuer exercises with probability:

$$p_{\text{call}} = \sigma\!\left(\alpha \cdot (\text{worst-of} - \text{strike})\right), \quad \text{worst-of} \geq \text{strike}$$

where $\alpha$ (call decisiveness) is configurable. At $\alpha = 50$ the model approaches an automatic trigger; at $\alpha = 5$ the issuer exercises significant discretion around the strike.

---

## Historical Backtest

The backtest evaluates the note on every valid issue date between June 2022 and June 2025 using **actual realized index prices** — no simulation. The same probabilistic call model is applied to the historical paths.

For each issue date:
- $S_0$ is set to the actual index levels on that date
- Worst-of performance is checked at 3M, 6M, 9M using realized prices
- Maturity payoff uses the actual 12-month return

This gives a distribution of historical outcomes across market regimes.

**Limitation:** The calibration window overlaps with the backtest window, so there is in-sample leakage — the model has already seen the 2022 drawdown when estimating $\theta$. A proper out-of-sample backtest would use expanding-window calibration.

---

## Usage

### Calibration

```python
from heston_calibrator import HestonCalibrator

cal = HestonCalibrator(
    csv_files={
        "SPX.csv": "SPX",
        "SX5E.csv": "SX5E",
        "SMI.csv": "SMI",
    },
    rv_window=21,
    mle_refine=False,
)

result = cal.calibrate()
# result.params    — list of HestonParams (includes mu, t_dof)
# result.corr_SS   — return-return correlations
# result.corr_VV   — variance-variance correlations
# result.corr_SV   — leverage diagonal
# result.t_dof     — calibrated degrees of freedom
```

### Simulation

```python
from heston_simulator import HestonMultiSimulator

sim = HestonMultiSimulator(
    params=result.params,
    corr_SS=result.corr_SS,
    corr_VV=result.corr_VV,
    corr_SV=result.corr_SV,
    T=1.0,
    N=252,
    n_paths=10_000,   # antithetics double this to 20,000
    seed=42,
    t_dof=result.t_dof,
)

results = sim.run()
```

### Note Pricing

```python
from structured_note_sim import run_structured_note

output = run_structured_note(
    coupon_rate=0.10,
    floor_level=0.95,
    n_paths=10_000,
    call_steepness=20.0,
)

print(f"Expected IRR:       {output['expected_irr']:.2%}")
print(f"P(floor triggered): {output['prob_floor']:.2%}")
```

### Historical Backtest

```python
from structured_note_sim import run_backtest

bt, summary = run_backtest(
    coupon_rate=0.10,
    floor_level=0.95,
    call_steepness=20.0,
)

print(f"Mean IRR:     {summary['mean_irr']:.2%}")
print(f"Called early: {summary['prob_called']:.1%}")
print(f"Floor hit:    {summary['prob_floor']:.1%}")
```

---

## Dashboard

Run locally:

```bash
pip install -r requirements.txt
streamlit run app.py
```

**Live:** [worst-of-note-dashboard.streamlit.app](https://worst-of-note-dashboard.streamlit.app)

Features:
- Forward simulation with fan charts (5th/25th/50th/75th/95th percentiles)
- Payoff profile overlaid on simulated terminal distribution
- Single path explorer with annotated observation dates
- Correlation diagnostics (input vs. realized, Heston parameter table)
- Historical backtest with price paths and rolling worst-of chart
- Bilingual interface (English / Español)

---

## Dependencies

```bash
pip install numpy pandas scipy matplotlib yfinance streamlit plotly
```

---

## Known Limitations & Future Work

| Limitation | Impact | Potential fix |
|-----------|--------|--------------|
| P-measure calibration only | $\rho$ near zero; no implied vol surface | Carr-Madan / characteristic function calibration from options |
| In-sample backtest | Leakage from 2022 drawdown into $\theta$ | Expanding-window calibration |
| Python payoff loop | Slow for large $n$ | Vectorize with NumPy |
| Euler price step (exact only for GBM) | Minor bias with stochastic vol | Full Milstein for price process |
| Single $\nu$ across assets | Ignores per-asset tail structure | Per-asset copula or vine copula |

**Future extensions:** risk-neutral calibration, barrier options, Asian options, variance swap pricing, GPU acceleration (CuPy), Sobol quasi-Monte Carlo.

---

## Disclaimer

This project was developed for educational and quantitative research purposes. It is not investment advice and should not be used as the sole basis for investment decisions.
