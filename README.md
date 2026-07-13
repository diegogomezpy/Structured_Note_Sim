# Multi-Asset Heston Simulator & Structured Note Engine

A Python framework for calibrating, simulating, and pricing a **multi-asset Heston stochastic volatility model** against real market data, with a full structured product engine for **autocallable and structured notes** — Phoenix Memory autocallables (memory coupons, a One Star best-of overlay, and an uncapped **Zenith** upside) and **Participation** notes — on any basket of equity underlyings (single-asset notes supported).

Built as an internal tool and deployed as a single-page **React** web app backed by a **FastAPI** service, with a branded, bilingual PDF report.

**▶️ Live app: [structured-note-sim-doemm2affa-tl.a.run.app](https://structured-note-sim-doemm2affa-tl.a.run.app/)**

---

## Overview

The project covers the full quantitative workflow:

1. **Calibration** — estimate Heston parameters and tail dependence from historical price data via method of moments
2. **Simulation** — simulate correlated multi-asset paths under the physical measure with Milstein discretisation, antithetic variates, and a Student-t copula
3. **Pricing** — evaluate the note payoff across every simulated scenario through one payoff engine covering two families: the **Phoenix** autocall waterfall (memory coupon, One-Star best-of overlay, uncapped **Zenith** upside on an in-the-money redemption) and the **Participation** note (composable downside × upside styles + a periodic cliquet mode)
4. **Backtesting** — replay the note on every historical issue date using realized prices, through the same payoff engine
5. **Web app** — interactive bilingual (EN/ES) React single-page app (FastAPI backend) that frames the note through six tabs — **Monte Carlo**, **Historical Backtest**, **Current Performance** (live), **Compare** (A/B two notes on shared paths), **Report** (branded one-click PDF), and **Batch** (many notes zipped) — with a setup page and live barrier tracking

---

## Project Structure

```
.
├── core/                      # Pure-quant library (no web / Plotly / file-I/O imports)
│   ├── calibrator.py          #   Historical Heston calibration pipeline
│   ├── simulator.py           #   Multi-asset Heston Monte Carlo engine (run(engine=...))
│   ├── simulator_cpp.py       #   Thin wrapper over the optional compiled C++ engine
│   ├── note.py                #   NoteTerms dataclass + vectorized payoff engine (Phoenix + Participation)
│   ├── note_description.py    #   Natural-language note summary generator
│   ├── backtest.py            #   Historical backtest using realized prices
│   └── __init__.py            #   Public API: HestonParams, NoteTerms, price_note, ...
│
├── data/
│   ├── loader.py              # load_prices() / load_dividends() — yfinance / CSV / DataFrame
│   └── __init__.py
│
├── api/                       # FastAPI backend — serves the JSON API *and* the built React bundle
│   ├── main.py                #   Routes (simulate, backtest, compare, report, batch, quotes, cover photos, ...)
│   ├── engine.py              #   Wires core/ + data/ → JSON for the UI; pluggable in-memory/Redis run store
│   ├── requirements.txt       #   fastapi + uvicorn (quant deps live in the root requirements.txt)
│   └── __init__.py
│
├── app/                       # Quant-only helpers shared by the API (no UI framework)
│   ├── charts.py              #   All Plotly figure builders as pure functions (→ JSON)
│   ├── pdf_report.py          #   Branded bilingual PDF generator (fpdf2 + kaleido)
│   ├── cover_photos.py        #   Sector → Pexels cover-photo taxonomy (data only; network calls stay in api/)
│   ├── translations.py        #   Bilingual string registry (EN/ES) — PDF + chart labels
│   ├── underlyings.py         #   Selectable ticker universe + logo maps
│   └── __init__.py
│
├── web/                       # React + TypeScript + Vite single-page front-end
│   ├── src/                   #   App.tsx, components/, lib/, i18n/, theme/, api/
│   │                          #     tab panels: MonteCarloPanel, BacktestPanel, LivePanel,
│   │                          #     ComparePanel, ReportPanel, BatchReportPanel (+ SectionTree)
│   │                          #     lib: participation, noteDescription, reportSections,
│   │                          #     batchReport, plotly (custom bundle), localFolder
│   ├── public/
│   ├── package.json
│   └── vite.config.ts         #   dev server proxies /api → http://localhost:8010
│
├── note_configs/             # 16 ready-to-use JSON term sheets (load in the app)
│                             #   HSBC ×2, BBVA, Citi, Santander ×3, Barclays, BNP Paribas,
│                             #   Julius Baer, 2 Participation (cliquet + growth),
│                             #   4 Silex thematic (consumer / services / One-Star / Zenith)
├── tests/                    # pytest quant-core suite (run by CI)
│   ├── conftest.py
│   └── test_note.py          #   payoff-engine coverage (Phoenix, One-Star, Zenith, Participation)
├── branding/                 # Firm branding JSON + bundled ticker logos
│   ├── branding_example.json #   documented template (all keys)
│   └── ticker_logos/         #   optional local PNG logos
├── fonts/                    # IBM Plex Sans (embedded in the PDF); fonts/brand/ for custom TTFs
├── cpp/                      # Optional compiled engine (pybind11 + block-SIMD + std::thread)
│   ├── heston_kernel.cpp     #   the kernel; validated against numpy by convergence
│   ├── CMakeLists.txt        #   build (scikit-build-core); `pip install ./cpp`
│   └── README.md             #   build / benchmark / wiring notes
├── scripts/
│   ├── verify_pdf.py         # Standalone PDF-render harness (needs PyMuPDF)
│   ├── compare_engines.py    # Validate + benchmark the C++ engine vs numpy
│   └── audit_tail.py         # Pretty-print the Cloud Run generation audit trail
│
├── design_lang/              # Design-system reference (Mercator tokens + page snapshots)
├── .github/workflows/        # CI gate (ci.yml: web build+lint, python syntax + pytest) + wheels.yml
├── Dockerfile                # Single-image build: Vite bundle + C++ wheel + Chrome-for-Testing + FastAPI runtime
├── requirements.txt          # Quant / runtime Python deps
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

It is block-SIMD (the per-step `exp`/`sqrt`/`sin`/`cos` vectorise across a contiguous block of paths via a vector libm) with a branch-free Box–Muller xoshiro256++ RNG, and parallelised across path-blocks with `std::thread` (no OpenMP/libomp dependency). It keeps full daily paths and is validated against numpy by **convergence of statistics**, not bit-equality (different RNG stream). The Docker image **builds and bundles this engine** (a portable wheel compiled in a dedicated stage), so `engine="cpp"` is available in production and the app falls back to numpy if it's ever absent. For local Python use, build it with `pip install ./cpp` into the same interpreter that runs the API; in the app, pick the engine in the run settings. See [`cpp/README.md`](cpp/README.md) for build, benchmarks, and the threads knob (`HESTON_NUM_THREADS`).

---

## Calibration Pipeline

All parameters are estimated from historical daily **adjusted** close prices (total-return dynamics). Barrier observation, the backtest, and live tracking use **raw** official closes — the levels term sheets actually fix against — and the simulator applies pre-programmed proportional dividend jumps at forecast ex-dates to convert total-return paths into price paths.

| Step | Parameter | Method |
|------|-----------|--------|
| 1 | Data loading | CSV / yfinance / DataFrame |
| 2 | Return construction | 1-day $r_1$ (RV, leverage); 2-day $r_2$ (correlation) |
| 3 | $\theta$ | Mean of the rolling RV series (long-run variance) |
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

The `NoteTerms` dataclass captures the full specification of a note. A single engine (`price_note()`) covers every variant below — the differences are entirely in the configured fields. All parameters are configurable and JSON-serialisable.

`note_type` (`phoenix` / `reverse_conv` / `growth_autocall` / `participation` / `custom`) is an **explicit stored field** that drives the setup menu, the payoff branch, the structure diagram and the prose. **Only two families are currently selectable in the UI: `phoenix` and `participation`.** `reverse_conv`, `growth_autocall` and `custom` are **parked** — kept in the `NoteType` union and still priced (so existing configs load), but removed from the picker until each is redesigned with its own menus. `from_dict` **infers** `note_type` for configs that predate the field, so legacy JSON still loads.

**Phoenix family** — all three ride the one Phoenix waterfall in `price_note()`; the type is a menu/label distinction, the behaviour is set by fields:

- **Phoenix Memory** — periodic coupon paid when the basket clears `coupon_barrier`; missed coupons accumulate (`memory=True`).
- **Reverse Convertible** *(parked in UI)* — guaranteed coupon: `coupon_barrier=0.0`, no memory, so it pays every period regardless of level.
- **Growth / Classic (step-down) Autocall** *(parked in UI)* — no periodic coupon; an accrued premium is paid only at autocall (`coupon_at_autocall_only`), and the autocall barrier steps down over time (`autocall_step_down`, `autocall_floor`).

**Participation note** (`note_type="participation"`, or legacy `capital_guarantee>0`) — a standalone **maturity-only** payoff that skips the entire coupon/autocall/knock-in waterfall (`_participation_payoff` → `_participation_redemption`). It composes **one downside style** with **one upside style** around `participation_strike`:

- downside (`participation_downside`): `full` (flat floor at `protection_level`, par when ≥1) · `buffer` (par down to `protection_level`, then 1:1 loss below) · `airbag` (par down to the barrier, then geared `B/protection_level` below) · `bear` (participate as the basket falls below the strike, floored above it — the upside style is ignored).
- upside (`participation_upside`): `linear` (`participation_rate·(B−strike)`, optional `upside_cap`) · `shark_fin` (participate up to `knockout_level`, else the flat `knockout_payout`; European/at-maturity KO) · `digital` (fixed `digital_payout` if `B ≥ strike`).

`participation_periodic=True` switches to a **cliquet / ratchet** mode: each observation is a self-contained one-period participation note (strike reset to par, `period_cap` as the cap), and the per-period P&L is summed with capital rolling at par.

**Zenith** (`zenith=True`) — an overlay on the Phoenix waterfall giving **worst-of upside participation on an in-the-money redemption**. Any redemption at or above the initial level (an autocall, or a non-loss maturity with worst-of ≥ 100%) pays `principal_protection + participation_rate·max(0, WoF−1)` on top of par + coupon, capped by `upside_cap` (`None` = uncapped, the "no CAP" case). The capital-loss branch and coupons/memory are unchanged.

**One Star overlay** (`one_star_level`) — a best-of OR-overlay orthogonal to the above. When set, its **final-redemption rescue is always active**: a single underlying ≥ `one_star_level` at maturity redeems capital at par even if the worst-of breached the knock-in (BBVA "Barrier and Knock-in"). The `one_star_coupon` / `one_star_autocall` flags (both default `False`) extend the same best-of overlay to the periodic coupon / autocall checks (BNP-style One Star). `null` = off, plain worst-of throughout.

| Parameter | Description | Default |
|-----------|-------------|---------|
| `note_type` | Structure family (`phoenix` / `participation` selectable; `reverse_conv` / `growth_autocall` / `custom` parked) | `phoenix` |
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
| `one_star_level` | Best-of OR-overlay level; one underlying ≥ this rescues final redemption; `null` = off | `None` |
| `one_star_coupon` | One Star best-of also satisfies the coupon barrier (periodic) | False |
| `one_star_autocall` | One Star best-of also forces the autocall trigger (periodic) | False |
| `autocall_step_down` | Per-period decrement of the autocall barrier (0 = constant) | 0.0 |
| `autocall_floor` | Minimum autocall barrier under step-down | `None` |
| `coupon_at_autocall_only` | No periodic coupon; accrued premium paid as a lump at autocall | False |
| `zenith` | Uncapped worst-of upside participation on an in-the-money redemption | False |
| `upside_cap` | Cap on redemption above par; also caps Zenith and participation linear/shark-fin upside (e.g. `0.15` = 1.15 cap) | `None` |
| `capital_guarantee` | **Legacy** CP guarantee — migrated to `protection_level` + `note_type="participation"` | `None` |
| `issuer` | Issuing bank, display only (e.g. `"BBVA"`) — shows a logo in the app | `""` |
| `issuer_description` / `issuer_rating_sp` / `_moody` / `_fitch` | Optional issuer profile for the PDF "Issuer Information" section | `""` |
| `tickers` | `{yf_symbol: display_name}` — stored in JSON config | `{}` |
| `issue_date` | `"YYYY-MM-DD"` — enables Current Performance tab when set | `None` |

**Participation-specific fields** (used only when `note_type="participation"`):

| Parameter | Description | Default |
|-----------|-------------|---------|
| `participation_downside` | `full` / `buffer` / `airbag` / `bear` | `full` |
| `participation_upside` | `linear` / `shark_fin` / `digital` | `linear` |
| `participation_basket` | Basket applied to the final level (`worst_of` / `best_of` / `average`) | `worst_of` |
| `protection_level` | Capital floor / buffer level / airbag barrier (fraction of initial) | 1.0 |
| `participation_rate` | Upside (or downside, for `bear`) multiplier; also the Zenith rate | 1.0 |
| `participation_strike` | Level from which participation is measured | 1.0 |
| `knockout_level` | Shark-fin: upside knocks out above this final level | `None` |
| `knockout_payout` | Shark-fin: flat redemption above the knock-out (1.0 = par) | 1.0 |
| `digital_payout` | Digital: fixed extra return if final ≥ strike (e.g. `0.10` = +10%) | 0.0 |
| `participation_periodic` | Cliquet mode — reset strike each period, sum per-period P&L | False |
| `period_cap` | Per-period cap in cliquet mode (`None` = uncapped) | `None` |

> **Derived fields** (never stored, always computed): `n_obs = maturity × periods_per_year`, `coupon_rate = coupon_pa / periods_per_year`.
>
> **Legacy fields** `final_basket` + `final_redemption_barrier` are auto-migrated to `one_star_level` by `NoteTerms.from_dict` (best-of → the barrier level; otherwise off); a positive `capital_guarantee` is migrated to `note_type="participation"` + `protection_level`.

### Payoff Logic

**At each observation period $j$:**

- **Coupon:** if `coupon_basket ≥ coupon_barrier`, pay `coupon_rate × (pending_periods + 1)` if memory, else `coupon_rate`. With `coupon_barrier = 0.0` this becomes a guaranteed coupon (Reverse Convertible). With `one_star_coupon`, a single underlying ≥ `one_star_level` also pays the coupon.
- **Autocall** (from `autocall_start_period`): if `autocall_basket ≥ autocall_barrier_schedule[j]`, redeem at par. The barrier is constant unless `autocall_step_down > 0`, in which case it declines each period (floored at `autocall_floor`). With `one_star_autocall`, a single underlying ≥ `one_star_level` also forces the call.

**Growth / Classic autocall** (`coupon_at_autocall_only = True`): no periodic coupon is paid. Instead an accrued premium of `coupon_rate × j` is paid as a lump **only** when the note autocalls at period $j$ (zero if held to maturity).

**At maturity (if not autocalled):**

- **One Star rescue:** if `one_star_level` is set and the best performer ≥ `one_star_level` → redeem at `principal_protection` (par) regardless of the KI.
- **Capital loss:** if `worst_of_final < knock_in_barrier` AND not rescued → cash-equivalent physical delivery: payout = worst-of final performance.
- **Par redemption:** otherwise → `principal_protection`.

**Zenith redemption** (`zenith = True`): any redemption at or above the initial level pays the worst-of upside on top of par — `principal_protection + participation_rate·max(0, WoF−1)`, capped by `upside_cap` (`None` = uncapped). This applies to an autocall (worst-of at the call date, which is ≥ `autocall_barrier`) **and** to a non-loss maturity (worst-of at final valuation; below par the upside term is zero, so it reduces to par). The capital-loss (1:1) branch and coupons/memory are unchanged.

**Participation note** (`note_type = "participation"`, or legacy `capital_guarantee > 0`): a standalone branch (`_participation_payoff`) that bypasses the coupon/autocall/KI waterfall entirely. The final basket level `B` (`participation_basket`) is run through `_participation_redemption`, composing one downside style (`full` / `buffer` / `airbag` / `bear`) with one upside style (`linear` / `shark_fin` / `digital`) around `participation_strike`; `upside_cap` caps the upside. `participation_periodic = True` switches to cliquet mode: each observation is a self-contained one-period participation note (strike reset to par, `period_cap` as the cap), and the per-period P&L is summed with capital rolling at par. `_participation_redemption` has a TS mirror in `web/src/lib/participation.ts` that feeds the payoff-profile diagram.

**IRR:** simple annualisation — `total_return / t_held` — consistent with how structured note coupons are quoted.

### Reference Term Sheets

Sixteen term sheets are included as ready-to-use JSON configs (load any of them on the setup page):

| File | Issuer | Type | Underlyings | Tenor | Coupon | KI |
|------|--------|------|-------------|-------|--------|-----|
| `hsbc_xs3376563584.json` | HSBC | Phoenix Memory | GS / JPM / MS | 24M monthly | 10% p.a. | 55% European |
| `bbva_xs3378405743.json` | BBVA | Phoenix One Star | NVDA / PLTR / TSLA | 18M quarterly | 15% p.a. | 50% European |
| `citi_xs3096699163.json` | Citi | Growth autocall (step-down) | GOOGL / AMZN / AAPL | 2Y quarterly | 12% p.a. premium | 53.7% European |
| `santander_xs3242406752.json` | Santander | Phoenix Memory | C / GLE.PA / MS | 2Y quarterly | 10.6% p.a. | 50% European |
| `santander_xs3242417106.json` | Santander | Phoenix Memory | C / GLE.PA / MS | 2Y quarterly | 10.6% p.a. | 50% European |
| `santander_C_GLE.PA_MS.json` | Santander | Phoenix Memory | C / GLE.PA / MS | 2Y quarterly | 12.35% p.a. | 50% European |
| `hsbc_xs3287776739.json` | HSBC | Phoenix Memory (single asset) | AMD | 18M quarterly | 18% p.a. | 55.5% European |
| `barclays_xs3305367727.json` | Barclays | Reverse Convertible | ORCL / ADBE | 1Y monthly | 15.25% p.a. guaranteed | 50% European |
| `bnp_paribas_pr00529720.json` | BNP Paribas | Phoenix One Star | DELL / IBM / MSFT | 1Y quarterly | 16% p.a. | 50% European |
| `julius_baer_pr00529635.json` | Julius Baer | Phoenix Memory | DELL / IBM / MSFT | 1Y quarterly | 28% p.a. | 50% European |
| `silex_autocall_consumo_wmt_mo_pm.json` | Silex (indic.) | Phoenix Memory | WMT / MO / PM | 2Y quarterly | 10.6% p.a. | 60% European |
| `silex_autocall_servicios_nee_vz_etr.json` | Silex (indic.) | Phoenix Memory | NEE / VZ / ETR | 2Y quarterly | 10.5% p.a. | 60% European |
| `silex_autocall_onestar_nflx_googl_meta.json` | Silex (indic.) | Phoenix One Star | NFLX / GOOGL / META | 2Y quarterly | 12.05% p.a. | 60% European |
| `silex_autocall_zenith_wmt_tgt_dg.json` | Silex (indic.) | Zenith Phoenix | WMT / TGT / DG | 2Y quarterly | 11.7% p.a. | 70% European |
| `participation_growth_spx_sx5e.json` | Generic Bank | Participation (full × linear) | SPX / SX5E | 3Y | — (130% up, +60% cap) | none |
| `participation_cliquet_sx5e.json` | Generic Bank | Participation (cliquet) | SX5E | 3Y annual | — (annual, 8% cap) | none |

The Citi note demonstrates the step-down barrier (100% declining 3%/period from obs 3, floored at 88%) with a 12% p.a. premium paid only at autocall. The Barclays note pays a guaranteed coupon every month (`coupon_barrier = 0.0`). The BNP One Star note lifts coupon, autocall **and** final redemption when any single underlying ≥ 100% (`one_star_coupon` / `one_star_autocall` both on), whereas the BBVA and Silex One Star notes apply the overlay to the final-redemption rescue only. The four `silex_*` notes are thematic indicative baskets — defensive consumer (WMT/MO/PM), utilities & telecom (NEE/VZ/ETR), big-tech with a One Star overlay (NFLX/GOOGL/META), and a **Zenith** consumer note (WMT/TGT/DG) where an in-the-money worst-of adds uncapped upside participation on redemption. The two `participation_*` notes exercise the maturity-only Participation family: capital-protected growth (par floor × 130% linear upside capped at +60%) and an annual cliquet (100% floor, 8% per-period cap).

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

## Web App

The front-end is a React + TypeScript (Vite) single-page app; the FastAPI backend
serves both the JSON API and the built bundle. For local development run the two
side by side — Vite proxies `/api` to the backend:

```bash
# Terminal 1 — backend (FastAPI on :8010)
pip install -r requirements.txt -r api/requirements.txt
uvicorn api.main:app --reload --port 8010

# Terminal 2 — front-end (Vite dev server on :5173, proxies /api → :8010)
cd web && npm install && npm run dev
```

Then open http://localhost:5173. To run the production single-image build locally,
see [Deployment](#deployment).

### Setup Page

The app opens on a **blank note** (nothing is auto-loaded) with a persistent
left-hand **setup rail** and, on the first ever visit, a guided tour that can be
reopened any time from "How it works". The rail holds the most-edited essentials;
the full option set lives in a **settings overlay** modal opened from the rail
(numbered groups: note type, underlyings, schedule/coupon, protection, autocall,
metadata, per-underlying details, simulation engine). Every control carries an
inline tooltip explaining what it does.

- **Note-type family** — a segmented toggle switches structure family and swaps the
  relevant fields. Two families are currently selectable: **Phoenix**
  (coupon/autocall/knock-in) and **Participation** (a maturity-level payoff that
  composes one downside style × one upside style, with an optional cliquet/periodic
  reset). Other families still load and price but aren't offered in the picker.
- **Underlying selection** — 53 predefined tickers (equity indices, US financials,
  US large-cap tech, and European blue chips) or any custom yfinance symbol; one or
  more underlyings, with single-asset notes supported.
- **Note terms** — maturity, coupons, barriers, basket types, memory, One Star /
  Zenith overlays, and issuer metadata, edited inline in the rail or in full in the
  settings overlay.
- **JSON config** — load a term-sheet config (upload a file, pick a bundled example,
  or connect a local folder of configs that are auto-detected) to populate every
  field at once, including underlyings. Advanced fields without a dedicated widget
  (step-down barrier, growth-autocall premium, …) are carried through from the
  loaded config.
- **Custom logos** — optionally upload your own company logos for the underlyings,
  used in the app cards and the PDF when a favicon is a poor fit.
- **Save / download** — export the current configuration as a JSON file, or (with a
  writable folder connected) save it straight back into that folder, renaming the
  file in place when the note is renamed.

### Results

After confirming setup, the results view frames the note through three **analysis
lenses** — the same note seen forward, backward, and live — plus tabs to compare
two variants and to export branded PDFs. Each analysis tab opens with a consistent
intro band stating the question it answers.

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

**Compare — _A/B, two variants on shared paths_**
- Seed a Variant B by duplicating the current note or loading a saved config, then edit it through the same settings overlay. The backend prices Monte Carlo for A and B on **one shared simulation** whenever they share underlyings + maturity, so the differences are pure term effects — a provenance banner states whether the run used shared or independent paths.
- A difference table (A / B / Δ, colour-signed), overlay IRR and outcome charts, and side-by-side structure diagrams. The historical backtest and current-performance comparisons are run on demand, each as side-by-side metric tables and charts.
- The comparison can be embedded in the PDF from the Report tab.

**Report — _branded bilingual PDF_**
- A dedicated tab builds a branded one-click export. Audience **presets** (Full, Client, Term sheet, Marketing, IC, Analyst, Quant, plus Custom) and a fine-grained **section tree** grouped by lens (Note details / Monte Carlo / Historical backtest / Current performance) pick exactly which sections and figures to include; a custom selection persists across sessions.
- The report can be generated **without running the simulation first** — a terms-only report needs no run, while analytical sections use the latest run. The PDF mirrors the three-lens structure with numbered part dividers and a grouped table of contents, and can carry through the A/B comparison when a Variant B exists. An in-app **tutorial** walks through the builder.
- The in-app builder renders **synchronously** in the request (Cloud Run only allocates CPU while a request is in flight); async start/poll endpoints (`/api/report/start`, `/api/report/status`, `/api/report/result`) also exist for always-on deployments.

**Batch — _many notes, one ZIP_**
- Generate reports for several notes in one pass without loading each on the dashboard. Add notes from the current note, the bundled configs, or a connected folder; tune each row independently — audience **preset**, exact **sections**, **language**, and **image mode** (auto sector-matched photos / choose photos / none).
- One global branding config applies across the batch (each report rendered in its own language). Rows can be duplicated to make variants of the same note, with bulk select / duplicate / remove.
- Every note renders to its own standalone PDF, zipped client-side into a single **ZIP**, with per-row status so a single failure doesn't sink the batch.

Report styling (shared by the Report and Batch tabs):

- **Branding** — per-firm colours, fonts, logos, cover/disclaimer text and selectable cover key-terms, driven by a `branding/branding_*.json` config (see `branding_example.json` for the full key set) or edited live in the Branding panel.
- **Report photos** — an optional [Pexels](https://www.pexels.com/)-backed photo library (suggested by sector), plus your own uploads or a connected local image folder. The chosen, drag-reorderable pool drives the cover, the back page and the filler bands. The library needs a `PEXELS_API_KEY` on the server; it degrades cleanly without one (uploads/folders still work).

**Bilingual** — full EN/ES interface throughout the app and the report.

---

## Deployment

The app ships as a **single Docker image** to **Google Cloud Run** at
[structured-note-sim-doemm2affa-tl.a.run.app](https://structured-note-sim-doemm2affa-tl.a.run.app/),
auto-deploying from `main` on every push (gated by CI — see
[API & runtime](#api--runtime)). The [`Dockerfile`](Dockerfile) is a
three-stage build:

1. **web-build** (`node`) — builds the React/Vite front-end (`web/` → `web/dist`)
2. **cpp-build** (`python` + Clang) — compiles the optional C++ Heston engine
   into a portable wheel (`HESTON_NATIVE=OFF` drops `-march=native` so the binary
   runs on any Cloud Run CPU)
3. **python runtime** — `uvicorn` serves the FastAPI API *and* the built bundle
   same-origin

**PDF figure rendering (kaleido → Chromium).** kaleido rasterises the Plotly
figures by driving a headless browser. Debian's apt `chromium` proved unusable —
its version drifts on every rebuild and one build (150.0.7871) crashed at launch
(SIGTRAP) on Cloud Run, silently breaking every PDF. The image instead bakes in
the **Chrome-for-Testing** build kaleido/choreographer is tested against, fetched
at build time by `choreo_get_chrome`, and points kaleido at it through a small
`--no-sandbox` wrapper (`BROWSER_PATH=/usr/local/bin/chromium-headless`). The apt
`chromium` package is still installed, but **only** to pull in the shared
libraries (fonts, nss, gbm, …) the browser needs — it is not the browser kaleido
launches. `--no-sandbox` is safe here because Chromium only rasterises the app's
own trusted Plotly JSON and runs as an unprivileged user.

Run the production image locally:

```bash
docker build -t structured-note-sim .
docker run -p 8080:8080 structured-note-sim   # http://localhost:8080
```

Notes on running it reliably long-term:

- **Dependencies are pinned** (`requirements.txt` + `api/requirements.txt`) with
  upper bounds so a future rebuild can't silently pull a breaking major release.
  Bump versions deliberately and re-pin.
- **`yfinance` is the single point of failure.** All live data flows through it,
  and Yahoo periodically changes its undocumented endpoints, breaking yfinance
  until it's patched. If the app starts failing to load prices, bump `yfinance`
  first (`pip install -U yfinance`) and re-pin. Data-load failures surface as a
  clean in-app message, not a traceback.
- **Memory scales with paths.** The engine keeps full daily paths, so Monte Carlo
  peak memory scales with `n_paths × n_steps × n_assets`. The API bounds the path
  count to **1,000–250,000** (default **10,000**); the retained per-path arrays
  are stored compactly (float16 performance + precomputed percentile fan bands;
  the worst-of is derived on demand). Size the Cloud Run instance memory for the
  path counts you intend to allow.
- **Cold starts:** an idle instance is scaled to zero; the first request after
  inactivity waits a few seconds for it to start. This is expected, not a failure.

### Environment variables

All optional — the app runs with none set.

- **`PEXELS_API_KEY`** — enables the report photo library (sector-suggested cover
  photos); degrades cleanly without it (uploads / connected folders still work).
- **`SNSIM_GEOIP`** — set to `off` to disable IP geolocation in the generation
  audit log (the line still logs the raw IP). See [Provenance, attribution &
  audit](#provenance-attribution--audit).
- **`REDIS_URL`** — opt-in **shared run store** for a multi-instance deploy. Unset
  (the default), each instance keeps runs in-memory; set it and runs persist in
  Redis so the path explorer / inspector / report survive load-balancing across
  instances. Best-effort: if it's unreachable the app falls back to in-memory (see
  [API & runtime](#api--runtime)).

The compiled C++ engine is built into the image, so `engine="cpp"` works in
production and falls back to numpy if ever absent.

---

## API & runtime

The React SPA is **stateless on the wire**: it POSTs JSON to `/api/simulate`,
`/api/backtest`, `/api/compare`, `/api/report`, … and gets JSON back — there is no
server session cookie or shared client state. Server-side state lives only in
`api/engine.py` (the run store + caches below).

- **Uniform error contract.** Every failure returns the same shape —
  `{"ok": false, "error": {"status": <int>, "message": <str>}}` — via app-wide
  exception handlers (`HTTPException`, request-validation, and unhandled `500`),
  instead of FastAPI's mix of `{detail: "…"}`, `{detail: [...]}` and bare 500s.
  Success payloads are **unenveloped** (returned as-is), so the client reads one
  error shape and raises a typed `ApiError` without per-endpoint churn.
- **PDF report — sync and async.** `POST /api/report` builds the PDF synchronously
  and streams it back; this is what the web client uses, because Cloud Run only
  allocates CPU while a request is in flight (a background job would starve). An
  async flow exists for always-allocated-CPU deploys: `POST /api/report/start`
  returns a `job_id`, `GET /api/report/status/{id}` polls it, and
  `GET /api/report/result/{id}` downloads the finished PDF. Jobs render in a small
  background pool and are in-memory with a TTL.
- **Pluggable run store (in-memory by default; Redis optional).** A `/api/simulate`
  stores the compact per-run arrays and returns a `run_id` the path explorer,
  inspector and report re-read without re-simulating. The default
  `_InMemoryRunStore` is an LRU-bounded, lock-guarded dict (cap 8 runs). When
  **`REDIS_URL` is set** (and only then) the store is `_RedisRunStore` — a shared
  cross-instance store keying each pickled run under a 1-hour TTL — needed so a
  follow-up call load-balanced to a different instance can still find its run.
  Redis is **opt-in and off by default**, and best-effort: if `REDIS_URL` is unset
  or unreachable the app transparently falls back to in-memory.
- **Caches.** `load_prices` results are cached (1-hour TTL, matching the live
  tab's refresh cadence), as are backtest results (keyed on tickers + terms),
  quotes, and translations — the API has no Streamlit `@st.cache_data` layer, so
  these stand in for it.
- **Generation audit log.** `/api/simulate` and `/api/report` each write one
  server-side line with a coarse best-effort geo (never embedded in the PDF);
  `SNSIM_GEOIP=off` disables the geolocation. See [Provenance, attribution &
  audit](#provenance-attribution--audit).

### Continuous integration

A GitHub Actions workflow ([`.github/workflows/ci.yml`](.github/workflows/ci.yml))
gates every push and PR on the same checks the deploy runs, catching a break here
rather than at Cloud Build (which would block the auto-deploy):

- **web** — `npm ci` → `npm run lint` (oxlint) → `npm run build` (`tsc -b`
  type-check + `vite build`), mirroring the Dockerfile's front-end build.
- **python** — `py_compile` on every module (catches the syntax / f-string-version
  breaks that would fail the image build without installing the heavy stack), then
  the golden-value **quant-core `pytest` suite** (`tests/`, no network; `scipy` is
  installed because importing `core.note` pulls in the calibrator).

---

## Provenance, attribution & audit

Every generated report carries lightweight provenance, every model run is logged,
and the author is credited in-app (header → **About**).

### PDF metadata

Each generated report embeds (invisible) document metadata:

- **Author / Creator / Producer / Keywords** — an author-attribution watermark.
  It is base64-obfuscated in the source and stamped from two call sites, so it
  isn't a one-line delete — but it is *deterrence, not DRM*: a source-available
  build can always strip it.
- **Title** — the note / report title.
- **Subject** — a readable, **non-PII** provenance line: `Generated <UTC time> ·
  <note> · <tickers> · Structured Note Simulator`.
- **CreationDate** — the UTC generation timestamp.

View it with macOS **Preview → Tools → Show Inspector** (⌘I), Acrobat **File →
Properties**, or the CLI: `pdfinfo report.pdf`, `exiftool report.pdf`, or
`python -c "import fitz; print(fitz.open('report.pdf').metadata)"`.

### Generation audit log

`/api/simulate` and `/api/report` each write one server-side log line, so you can
trace who is *using* the tool (and, for reports, who *exports* one):

```
[report] ts=<UTC> ip=<client IP> geo='<city, region, country · ISP · ASN>'
         note='…' tickers='…' sections=N n_paths=… lang=… engine=… ua='…'
```

- The **client IP is geotagged** (city/region/country + ISP/ASN), best-effort via
  ip-api.com, cached, with a 2 s timeout; private/blank IPs are skipped.
- It lives **only in the request log** (operator-visible) and is **never embedded
  in the PDF** — an IP is personal data and reports are white-label /
  redistributable.
- Read it on Cloud Run — **your service → Logs** (free-text search `[report]`),
  or the bundled helper **`python scripts/audit_tail.py`**, which wraps `gcloud
  logging read`, parses the lines and prints them with a summary (unique IPs, top
  networks / countries). Flags: `--tag report|simulate`, `--since 1d`, `-n 50`,
  `--json`; needs the gcloud CLI + `gcloud auth login`.
- **`SNSIM_GEOIP=off`** disables geolocation (the line still logs the raw IP).

> **Commercial / privacy note:** an IP address is personal data (GDPR/CCPA). For a
> commercial deploy, disclose the logging in a privacy policy and set a retention
> limit. ip-api.com's free tier is **non-commercial** only — swap in a licensed
> geolocation provider or a self-hosted MaxMind GeoLite2 database.

---

## Dependencies

**Python** — pinned in `requirements.txt` (quant/runtime) and `api/requirements.txt`
(the FastAPI layer) with upper bounds, so a future rebuild can't pull an
incompatible major release (see [Deployment](#deployment)):

```
numpy >= 2.4, < 3
pandas >= 3.0, < 4
scipy >= 1.17, < 2
matplotlib >= 3.7, < 4       # notebook-only; lazy-imported, never loaded by the app
plotly >= 6.8, < 7
yfinance >= 1.4, < 2         # most fragile dep — bump first if live data stops loading
deep-translator >= 1.11, < 2 # optional EN→ES machine translation of Yahoo descriptions
fpdf2 >= 2.8, < 3            # PDF report
kaleido >= 1.3, < 2          # Plotly figure export for the PDF
Pillow >= 12, < 13           # image handling in the PDF
redis >= 5, < 7              # optional shared run store; only used when REDIS_URL is set
fastapi >= 0.137, < 1        # api/requirements.txt
uvicorn[standard] >= 0.49, < 1
```

**Front-end** — React 19 + TypeScript + Vite + Plotly.js, with `jszip` for the
Batch tab's multi-report ZIP download (see `web/package.json`).

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

## License

Source-available under the **[PolyForm Noncommercial License 1.0.0](LICENSE.md)** — © 2026 Diego Sebastian Gomez Harika. Free to use, modify, and share for **noncommercial** purposes (personal use, research, education, evaluation); **any commercial use — by a company or otherwise — requires a separate license from the author**. For commercial licensing, contact **diegogomezzx@gmail.com**. See [`LICENSE.md`](LICENSE.md) for the exact terms.

Third-party components keep their own licenses (numpy/pandas/scipy BSD, plotly/FastAPI/React MIT, fpdf2 LGPL-3.0, IBM Plex Sans OFL-1.1, …). Note that some **data/content sources are not licensed for commercial use as configured** — Yahoo Finance data (via `yfinance`), Google Translate (via `deep-translator`), and third-party company logos — so a commercial deployment must swap in licensed equivalents.

---

## Disclaimer

This project was developed for quantitative research and internal use. It is not investment advice and should not be used as the sole basis for investment decisions.
