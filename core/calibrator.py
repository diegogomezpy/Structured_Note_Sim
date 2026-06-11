"""
heston_calibrator.py
--------------------
Calibrates Heston model parameters for one or more assets from historical
daily closing price data.

Pipeline per asset
------------------
Step 1  — Data acquisition
          Pull via yfinance, or accept a pre-loaded DataFrame.

Step 2  — Return computation
          Universal 2-day overlapping log-returns:
              r_t(2d) = ln(S_t / S_{t-2})
          Used for all assets and all correlation estimates.
          Reason: eliminates the artificial decorrelation caused by the
          ~6-hour gap between US (SPX) and European (SX5E, SMI) closes.

Step 3  — Rolling Realized Variance proxy
          RV_t = rolling(window).var(r_1d) * 252
          where r_1d are 1-day returns (used only for RV; 2-day used for corr).
          Window is user-configurable (default 21 days).

Step 4  — Method of Moments (MoM) calibration per asset
          Estimates all 5 Heston parameters analytically:
            theta : sample variance of 1-day returns / dt
            V0    : most recent rolling RV value
            kappa : -log(phi) / dt  where phi = AR(1) coefficient of RV series
            xi    : std(diff(RV)) / sqrt(theta * dt)
            rho   : corr(1d returns, diff(RV))   [leverage effect]
          Parameters are clamped to physically reasonable bounds.

Step 5  — MLE refinement (optional, off by default)
          Uses MoM estimates as starting values.
          Maximizes the approximate conditional log-likelihood:
              r_t | V_{t-1} ~ N(-0.5*V*dt, V*dt*(1-rho^2))
          where V is proxied by rolling RV.
          Optimizer: Nelder-Mead with 3000 iterations.

Step 6  — Correlation block estimation
          corr_SS : Pearson correlation of 2-day returns across all assets
          corr_VV : Pearson correlation of RV series across all assets
          corr_SV : diagonal matrix with each asset's own rho on diagonal,
                    zeros off-diagonal (cross leverage terms set to zero;
                    see module docstring for justification)

Output
------
Returns a CalibrationResult with:
  - params       : list[HestonParams]  ready for HestonMultiSimulator
  - corr_SS      : np.ndarray (n, n)
  - corr_VV      : np.ndarray (n, n)
  - corr_SV      : np.ndarray (n, n)  diagonal only
  - diagnostics  : dict of intermediate series for inspection

Usage
-----
    from heston_calibrator import HestonCalibrator

    cal = HestonCalibrator(
        tickers   = {"^GSPC": "SPX", "^STOXX50E": "SX5E", "^SSMI": "SMI"},
        years     = 5,
        rv_window = 21,
        mle_refine = False,
    )
    result = cal.calibrate()

    # Feed directly into simulator
    from heston_simulator import HestonMultiSimulator
    sim = HestonMultiSimulator(
        params  = result.params,
        corr_SS = result.corr_SS,
        corr_VV = result.corr_VV,
        corr_SV = result.corr_SV,
        T=1.0, N=252, n_paths=20_000,
    )
"""

import warnings
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Optional, Union
from scipy.optimize import minimize
from scipy import stats

# HestonParams lives in heston_simulator — import it
from core.simulator import HestonParams


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass
class CalibrationResult:
    """
    Output of HestonCalibrator.calibrate().

    Attributes
    ----------
    params      : list[HestonParams]  – one per asset, ready for simulator
    corr_SS     : np.ndarray (n, n)   – return-return correlations
    corr_VV     : np.ndarray (n, n)   – variance-variance correlations
    corr_SV     : np.ndarray (n, n)   – diagonal leverage matrix
    t_dof       : int                 – degrees of freedom for Student-t copula
    diagnostics : dict                – intermediate series for inspection
    """
    params:      list
    corr_SS:     np.ndarray
    corr_VV:     np.ndarray
    corr_SV:     np.ndarray
    t_dof:       int = 5
    diagnostics: dict = field(default_factory=dict)

    def summary(self) -> None:
        """Print a clean calibration summary."""
        n = len(self.params)
        print("\n" + "=" * 65)
        print("  HESTON CALIBRATION RESULTS")
        print("=" * 65)
        for p in self.params:
            ok, margin = p.feller_condition()
            feller_str = f"✓ (margin {margin:.4f})" if ok else f"✗ VIOLATED (margin {margin:.4f})"
            print(f"\n  {p.name}")
            print(f"    S0    = {p.S0:.2f}")
            print(f"    mu    = {p.mu:.4f}   ({p.mu*100:.1f}% p.a.)")
            print(f"    V0    = {p.V0:.5f}   (σ ≈ {np.sqrt(p.V0)*100:.1f}%)")
            print(f"    theta = {p.theta:.5f}   (σ ≈ {np.sqrt(p.theta)*100:.1f}%)")
            print(f"    kappa = {p.kappa:.4f}")
            print(f"    xi    = {p.xi:.4f}")
            print(f"    rho   = {p.rho:.4f}")
            print(f"    Feller: {feller_str}")

        names = [p.name for p in self.params]
        print(f"\n  corr_SS (return-return, 2-day overlapping):")
        _print_matrix(self.corr_SS, names)
        print(f"\n  corr_VV (variance-variance, rolling RV):")
        _print_matrix(self.corr_VV, names)
        print(f"\n  corr_SV (diagonal leverage, cross terms = 0):")
        _print_matrix(self.corr_SV, names)
        print(f"\n  Student-t copula: ν = {self.t_dof} "
              f"(fitted from return tail behaviour)")
        print("=" * 65 + "\n")


def _print_matrix(M: np.ndarray, names: list) -> None:
    header = "          " + "  ".join(f"{nm:>8}" for nm in names)
    print(header)
    for i, nm in enumerate(names):
        row = "  ".join(f"{M[i,j]:+.4f}" for j in range(len(names)))
        print(f"  {nm:>8}  {row}")


# ---------------------------------------------------------------------------
# Parameter bounds — physically reasonable ranges
# ---------------------------------------------------------------------------

PARAM_BOUNDS = {
    "kappa": (0.10,  20.0),
    "theta": (0.001,  0.50),
    "xi":    (0.05,   2.00),
    "rho":   (-0.98,  0.98),
}


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


# ---------------------------------------------------------------------------
# Calibrator
# ---------------------------------------------------------------------------

class HestonCalibrator:
    """
    Calibrates Heston parameters from historical daily closing prices.

    Parameters
    ----------
    tickers    : dict[str, str]
                 Mapping from yfinance ticker symbol to display name.
                 e.g. {"^GSPC": "SPX", "^STOXX50E": "SX5E", "^SSMI": "SMI"}
                 Ignored if prices_df is provided directly.
    years      : float
                 How many years of history to use.  Default 5.
    rv_window  : int
                 Rolling window (trading days) for realized variance proxy.
                 Default 21 (≈ 1 calendar month).
    mle_refine : bool
                 If True, refine MoM estimates with MLE.  Default False.
    prices_df  : pd.DataFrame or None
                 Pre-loaded price DataFrame with asset names as columns.
                 If provided, tickers and years are ignored for data fetching.
    end_date   : str or None
                 End date for data pull (YYYY-MM-DD).  Defaults to today.
    ssl_verify : bool
                 Set to False if you are behind a corporate proxy that injects
                 its own SSL certificate (common in brokerage/bank networks).
                 Default True.
    csv_files  : dict[str, str] or None
                 Mapping from raw Yahoo Finance CSV path to display name.
                 e.g. {"GSPC.csv": "SPX", "STOXX50E.csv": "SX5E", "SSMI.csv": "SMI"}
                 Each CSV must be a raw Yahoo Finance download with an
                 'Adj Close' column and a 'Date' index column.
                 If provided, tickers, years, and prices_df are all ignored.
    """

    def __init__(
        self,
        tickers:     dict                    = None,
        years:       float                   = 5.0,
        rv_window:   int                     = 21,
        mle_refine:  bool                    = False,
        prices_df:   Optional[pd.DataFrame]  = None,
        end_date:    Optional[str]           = None,
        ssl_verify:  bool                    = True,
        csv_files:   Optional[dict]          = None,
        calib_years: Optional[float]         = None,
    ):
        self.tickers     = tickers if tickers is not None else {}
        self.years       = years
        self.rv_window   = rv_window
        self.mle_refine  = mle_refine
        self.prices_df   = prices_df
        self.end_date    = end_date
        self.ssl_verify  = ssl_verify
        self.csv_files   = csv_files
        self.calib_years = calib_years

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def calibrate(self) -> CalibrationResult:
        """
        Run the full calibration pipeline.

        Returns
        -------
        CalibrationResult
        """
        # Step 1: Get prices
        prices = self._get_prices()
        names  = list(prices.columns)
        n      = len(names)

        # Optional: slice to recent calib_years for parameter estimation.
        # Useful when prices_df covers a long history (e.g. 20 years for backtesting)
        # but you want Heston params calibrated on recent market conditions only.
        calib_prices = prices
        if self.calib_years is not None:
            cutoff = prices.index[-1] - pd.DateOffset(years=self.calib_years)
            calib_prices = prices[prices.index >= cutoff]
            if len(calib_prices) < 60:
                print(f"[Calibrator] WARNING: calib_years={self.calib_years} gives only "
                      f"{len(calib_prices)} obs after slicing — using full history instead.")
                calib_prices = prices

        print(f"\n[Calibrator] Assets     : {names}")
        print(f"[Calibrator] Full data  : {prices.index[0].date()} → {prices.index[-1].date()} ({len(prices)} days)")
        if calib_prices is not prices:
            print(f"[Calibrator] Calib window: {calib_prices.index[0].date()} → {calib_prices.index[-1].date()} ({len(calib_prices)} days, last {self.calib_years}Y)")

        # Step 2: Compute returns (on calibration window only)
        lr1, lr2 = self._compute_returns(calib_prices)
        # lr1: 1-day log returns  (n_obs-1, n)  — used for RV and rho
        # lr2: 2-day log returns  (n_obs-2, n)  — used for corr_SS

        # Step 3: Rolling realized variance per asset
        rv_df = self._rolling_rv(lr1)

        # Step 4: MoM calibration per asset
        params_list = []
        for i, name in enumerate(names):
            S0  = float(prices[name].iloc[-1])   # always latest price from full history
            p   = self._mom_calibrate(
                name   = name,
                S0     = S0,
                lr1    = lr1[:, i],
                rv     = rv_df[:, i],
            )
            # Step 5: Optional MLE refinement
            if self.mle_refine:
                p = self._mle_refine(p, lr1[:, i], rv_df[:, i])
            params_list.append(p)

        # Step 6: Correlation blocks
        corr_SS = self._corr_SS(lr2)
        corr_VV = self._corr_VV(rv_df)
        corr_SV = self._corr_SV(params_list)

        # Step 7: Estimate Student-t copula degrees of freedom
        # Fit a univariate t-distribution to each asset's daily log-returns via MLE,
        # then take the median across assets. Clamped to [3, 30].
        # ν → 3: very heavy tails. ν → 30: near-Gaussian.
        dof_estimates = []
        for i in range(len(names)):
            try:
                nu, _, _ = stats.t.fit(lr1[:, i], floc=0)
                dof_estimates.append(nu)
            except Exception:
                dof_estimates.append(5.0)
        t_dof = int(round(float(np.clip(np.median(dof_estimates), 3, 30))))
        print(f"[Calibrator] Student-t copula ν = {t_dof} "
              f"(per-asset fits: {[f'{v:.1f}' for v in dof_estimates]})")

        diagnostics = {
            "prices":       prices,        # full history
            "calib_prices": calib_prices,  # calibration window (may equal prices)
            "lr1":          pd.DataFrame(lr1, columns=names),
            "lr2":          pd.DataFrame(lr2, columns=names),
            "rv":           pd.DataFrame(rv_df, columns=names),
        }

        result = CalibrationResult(
            params      = params_list,
            corr_SS     = corr_SS,
            corr_VV     = corr_VV,
            corr_SV     = corr_SV,
            t_dof       = t_dof,
            diagnostics = diagnostics,
        )
        result.summary()
        return result

    # ------------------------------------------------------------------
    # Step 1: Data
    # ------------------------------------------------------------------

    def _get_prices(self) -> pd.DataFrame:
        """Return a clean DataFrame of adjusted closing prices."""

        # --- Branch 1: raw Yahoo Finance CSV files ---
        if self.csv_files is not None:
            return self._load_from_csv_files()

        # --- Branch 2: pre-loaded DataFrame ---
        if self.prices_df is not None:
            df = self.prices_df.copy().dropna()
            print("[Calibrator] Using pre-loaded price DataFrame.")
            return df

        # Otherwise pull from yfinance
        try:
            import yfinance as yf
        except ImportError:
            raise ImportError(
                "yfinance not installed.  Run: pip install yfinance\n"
                "Or pass a pre-loaded DataFrame via prices_df=."
            )

        import datetime
        end   = pd.Timestamp(self.end_date) if self.end_date else pd.Timestamp.today()
        start = end - pd.DateOffset(years=self.years)

        ticker_symbols = list(self.tickers.keys())
        print(f"[Calibrator] Pulling {ticker_symbols} from yfinance …")

        # Corporate proxies often inject self-signed SSL certs that yfinance
        # rejects. Pass ssl_verify=False to bypass when behind such a network.
        session = None
        if not self.ssl_verify:
            import requests
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            session = requests.Session()
            session.verify = False
            print("[Calibrator] SSL verification disabled (ssl_verify=False).")

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            download_kwargs = dict(
                start       = start.strftime("%Y-%m-%d"),
                end         = end.strftime("%Y-%m-%d"),
                # Deliberately adjusted: calibration estimates TOTAL-RETURN
                # dynamics (drift/vol/corr) — ex-date dividend jumps must not
                # pollute the estimates. Barrier observation uses raw closes
                # (data/loader.py field="close"), never this series.
                auto_adjust = True,
                progress    = False,
            )
            if session is not None:
                download_kwargs["session"] = session
            raw = yf.download(ticker_symbols, **download_kwargs)

        # Handle single vs multi-ticker yfinance output
        if isinstance(raw.columns, pd.MultiIndex):
            prices = raw["Close"][ticker_symbols]
        else:
            prices = raw[["Close"]].rename(columns={"Close": ticker_symbols[0]})

        # Rename columns to display names
        prices = prices.rename(columns=self.tickers)

        # Drop rows where ANY asset has a missing price
        # (holidays differ across exchanges — we only keep days all traded)
        n_before = len(prices)
        prices   = prices.dropna()
        n_after  = len(prices)
        if n_before - n_after > 0:
            print(f"[Calibrator] Dropped {n_before - n_after} rows with missing prices "
                  f"(non-overlapping holidays).")

        if len(prices) < 60:
            raise ValueError(
                f"Only {len(prices)} clean observations after alignment. "
                f"Increase years or check ticker symbols."
            )

        return prices

    def _load_from_csv_files(self) -> pd.DataFrame:
        """
        Load and align prices from raw Yahoo Finance CSV files.

        Each CSV is a standard Yahoo Finance download containing columns:
            Date, Open, High, Low, Close, Adj Close, Volume

        We extract 'Adj Close' from each file, rename to the display name,
        align on the common date index, and drop non-overlapping holidays.
        """
        series = {}
        for path, name in self.csv_files.items():
            df = pd.read_csv(path, index_col="Date", parse_dates=True)

            # Yahoo Finance CSVs sometimes have a header row and a metadata row
            # at the top. Drop any rows where the index is not a valid date.
            df = df[pd.to_datetime(df.index, errors="coerce").notna()]
            df.index = pd.to_datetime(df.index)

            if "Adj Close" not in df.columns:
                raise ValueError(
                    f"File '{path}' has no 'Adj Close' column. "
                    f"Columns found: {list(df.columns)}. "
                    f"Make sure you are using a raw Yahoo Finance CSV download."
                )

            adj = pd.to_numeric(df["Adj Close"], errors="coerce")
            series[name] = adj
            print(f"[Calibrator] Loaded {name} from '{path}'  "
                  f"({len(adj)} rows, {adj.index[0].date()} → {adj.index[-1].date()})")

        prices = pd.DataFrame(series)

        # Align: keep only dates where all assets have a price
        n_before = len(prices)
        prices   = prices.dropna()
        n_after  = len(prices)
        if n_before - n_after > 0:
            print(f"[Calibrator] Dropped {n_before - n_after} rows with missing prices "
                  f"(non-overlapping holidays).")

        if len(prices) < 60:
            raise ValueError(
                f"Only {len(prices)} clean observations after alignment. "
                f"Check that your CSV files cover an overlapping date range."
            )

        print(f"[Calibrator] Aligned date range: "
              f"{prices.index[0].date()} → {prices.index[-1].date()}  "
              f"({len(prices)} common trading days)")
        return prices

    # ------------------------------------------------------------------
    # Step 2: Returns
    # ------------------------------------------------------------------

    def _compute_returns(
        self,
        prices: pd.DataFrame,
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        Compute 1-day and 2-day overlapping log returns.

        1-day: r1_t = ln(S_t / S_{t-1})   shape (T-1, n)
        2-day: r2_t = ln(S_t / S_{t-2})   shape (T-2, n)

        The 2-day returns are used for all correlation estimates to
        correct for the US/Europe asynchronous close problem.
        """
        p   = prices.values.astype(float)
        lr1 = np.log(p[1:,  :] / p[:-1, :])   # (T-1, n)
        lr2 = np.log(p[2:,  :] / p[:-2, :])   # (T-2, n)
        return lr1, lr2

    # ------------------------------------------------------------------
    # Step 3: Rolling Realized Variance
    # ------------------------------------------------------------------

    def _rolling_rv(self, lr1: np.ndarray) -> np.ndarray:
        """
        Compute rolling realized variance from 1-day returns.

        RV_t = rolling(window).var(r1) * 252

        Returns array of shape (T-1, n), with the first (window-1)
        rows back-filled from the first valid window to avoid NaNs.
        """
        w   = self.rv_window
        df  = pd.DataFrame(lr1)
        rv  = df.rolling(w).var().bfill() * 252
        return rv.values.astype(float)

    # ------------------------------------------------------------------
    # Step 4: Method of Moments
    # ------------------------------------------------------------------

    def _mom_calibrate(
        self,
        name: str,
        S0:   float,
        lr1:  np.ndarray,
        rv:   np.ndarray,
    ) -> HestonParams:
        """
        Estimate Heston parameters for one asset via Method of Moments.

        Parameter map
        -------------
        theta : E[V] ≈ sample variance of 1-day returns / dt
        V0    : most recent rolling RV value (current variance)
        kappa : mean-reversion speed from AR(1) of RV series
                phi = corr(RV_t, RV_{t+1})  =>  kappa = -log(phi) / dt
        xi    : vol-of-vol from std of RV increments
                xi ≈ std(dRV) / sqrt(theta * dt)
        rho   : leverage effect from corr(r_t, dRV_t)
        """
        dt  = 1.0 / 252.0
        eps = 1e-8

        # theta: long-run variance estimated as the mean of the rolling RV series.
        # Using mean(RV) rather than var(lr1)/dt keeps theta consistent with the
        # other RV-derived parameters (kappa, xi, V0) and avoids the mismatch
        # between the unconditional return variance and the mean-reversion target
        # when V0 is anchored to the most recent RV window.
        rv_clean = rv[~np.isnan(rv)]
        theta = float(np.mean(rv_clean))

        # mu: annualised ARITHMETIC drift (the model's price-equation drift).
        #
        # The model is dS/S = mu*dt + sqrt(V)*dW, so log-returns satisfy
        #     d ln S = (mu - V/2)*dt + sqrt(V)*dW
        # and the mean realized log-return estimates (mu - theta/2), NOT mu —
        # the volatility drag is already embedded in historical log-returns.
        # The simulator's log-Euler step then subtracts V/2 again, so feeding it
        # mean(lr)/dt directly double-counts the drag: simulated geometric
        # growth would be (realized growth - theta/2). For a 60-vol name like
        # TSLA that's an ~18%/yr downward bias — enough to flatten the median
        # path entirely. Adding theta/2 back recovers the arithmetic drift, and
        # the simulator's -V/2 cancels it so simulated log-growth matches the
        # realized geometric growth over the calibration window.
        mu = float(np.mean(lr1) / dt) + 0.5 * theta

        # V0: current variance (last window value)
        V0 = float(rv_clean[-1])

        # kappa: AR(1) mean reversion of RV
        if len(rv_clean) > 2:
            phi   = float(np.corrcoef(rv_clean[:-1], rv_clean[1:])[0, 1])
            phi   = _clamp(phi, eps, 1.0 - eps)
            kappa = float(-np.log(phi) / dt)
        else:
            kappa = 2.0  # fallback

        # xi: vol-of-vol from daily RV increments.
        # From the discrete Milstein step: dV ≈ xi * sqrt(V) * dW_V * sqrt(dt)
        # so xi ≈ std(dRV) / (sqrt(mean_V) * sqrt(dt)).
        # rv is already annualised (×252); d_rv increments are in annualised variance
        # units per calendar day. We use sqrt(theta) as the proxy for sqrt(V).
        d_rv  = np.diff(rv_clean)
        xi    = float(np.std(d_rv) / (np.sqrt(max(theta, eps)) * np.sqrt(dt)))

        # rho: leverage — correlation between 1-day returns and same-day RV changes.
        # d_rv[t] = rv_clean[t+1] - rv_clean[t], so d_rv[t] corresponds to the
        # return lr1[t] (both reference the same day-to-day transition).
        # We therefore align lr1[:-1] with d_rv (both length len(rv_clean)-1).
        min_len = min(len(lr1) - 1, len(d_rv))
        if min_len > 10:
            rho = float(np.corrcoef(lr1[:min_len], d_rv[:min_len])[0, 1])
        else:
            rho = -0.5  # fallback

        # Clamp all parameters to physical bounds
        kappa = _clamp(kappa, *PARAM_BOUNDS["kappa"])
        theta = _clamp(theta, *PARAM_BOUNDS["theta"])
        xi    = _clamp(xi,    *PARAM_BOUNDS["xi"])
        rho   = _clamp(rho,   *PARAM_BOUNDS["rho"])
        V0    = _clamp(V0,    PARAM_BOUNDS["theta"][0], PARAM_BOUNDS["theta"][1])

        # Enforce Feller by nudging kappa up if needed
        feller_margin = 2.0 * kappa * theta - xi ** 2
        if feller_margin < 0.01:
            kappa = (xi ** 2 + 0.01) / (2.0 * theta)
            kappa = _clamp(kappa, *PARAM_BOUNDS["kappa"])
            print(f"  [{name}] Feller enforced: kappa nudged to {kappa:.4f}")

        print(f"  [MoM] {name}: kappa={kappa:.3f}  theta={theta:.5f}  "
              f"xi={xi:.3f}  rho={rho:.3f}  V0={V0:.5f}  mu={mu:.4f} ({mu*100:.1f}% p.a.)")

        return HestonParams(
            name  = name,
            S0    = S0,
            kappa = kappa,
            theta = theta,
            xi    = xi,
            rho   = rho,
            V0    = V0,
            mu    = mu,
        )

    # ------------------------------------------------------------------
    # Step 5: MLE Refinement (optional)
    # ------------------------------------------------------------------

    def _mle_refine(
        self,
        p0:  HestonParams,
        lr1: np.ndarray,
        rv:  np.ndarray,
    ) -> HestonParams:
        """
        Refine MoM estimates via approximate MLE.

        Approximate likelihood:
            r_t | V_{t-1} ~ N(-0.5 * V_{t-1} * dt,  V_{t-1} * dt * (1 - rho^2))

        where V is proxied by rolling RV.  Optimizer: Nelder-Mead.
        """
        dt = 1.0 / 252.0

        def neg_ll(params: np.ndarray) -> float:
            kappa, theta, xi, rho = params
            if (kappa <= 0 or theta <= 0 or xi <= 0
                    or not (-1 < rho < 1)
                    or 2 * kappa * theta < xi ** 2):
                return 1e10
            V_t  = np.maximum(rv[:-1], 1e-8)
            mu_v = -0.5 * V_t * dt
            sig2 = V_t * dt * (1.0 - rho ** 2) + 1e-10
            ll   = float((-0.5 * (np.log(2 * np.pi * sig2)
                                  + (lr1[1:] - mu_v) ** 2 / sig2)).sum())
            return -ll / len(lr1)

        x0      = [p0.kappa, p0.theta, p0.xi, p0.rho]
        result  = minimize(
            neg_ll, x0=x0, method="Nelder-Mead",
            options={"maxiter": 3000, "xatol": 1e-5, "fatol": 1e-5},
        )

        if not result.success:
            print(f"  [MLE] {p0.name}: optimizer did not converge — keeping MoM estimates.")
            return p0

        kappa, theta, xi, rho = result.x
        kappa = _clamp(kappa, *PARAM_BOUNDS["kappa"])
        theta = _clamp(theta, *PARAM_BOUNDS["theta"])
        xi    = _clamp(xi,    *PARAM_BOUNDS["xi"])
        rho   = _clamp(rho,   *PARAM_BOUNDS["rho"])

        print(f"  [MLE] {p0.name}: kappa={kappa:.3f}  theta={theta:.5f}  "
              f"xi={xi:.3f}  rho={rho:.3f}")

        return HestonParams(
            name=p0.name, S0=p0.S0,
            kappa=kappa, theta=theta, xi=xi, rho=rho, V0=p0.V0,
            mu=p0.mu,  # drift unchanged by MLE (estimated separately from mean return)
        )

    # ------------------------------------------------------------------
    # Step 6: Correlation blocks
    # ------------------------------------------------------------------

    def _corr_SS(self, lr2: np.ndarray) -> np.ndarray:
        """
        Return-return correlation from 2-day overlapping log returns.
        Shape: (n, n)
        """
        # np.corrcoef collapses to a 0-d scalar for a single asset; force 2-d.
        C = np.atleast_2d(np.corrcoef(lr2.T))
        np.fill_diagonal(C, 1.0)
        return C

    def _corr_VV(self, rv: np.ndarray) -> np.ndarray:
        """
        Variance-variance correlation from rolling RV series.
        Shape: (n, n)
        """
        # np.corrcoef collapses to a 0-d scalar for a single asset; force 2-d.
        C = np.atleast_2d(np.corrcoef(rv.T))
        np.fill_diagonal(C, 1.0)
        return C

    def _corr_SV(self, params: list) -> np.ndarray:
        """
        Build the corr_SV matrix.
        Diagonal = each asset's own rho (leverage effect).
        Off-diagonal = 0 (cross leverage terms are small and destabilize PSD).
        Shape: (n, n)
        """
        n = len(params)
        C = np.zeros((n, n))
        for i, p in enumerate(params):
            C[i, i] = p.rho
        return C


# ---------------------------------------------------------------------------
# Quick test with synthetic data (runs when executed directly)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import datetime

    # --- Generate synthetic price data that mimics real index behavior ---
    np.random.seed(42)
    n_days = 1260  # 5 years

    # Correlated GARCH-like returns to give realistic vol clustering
    # True params: kappa~3, theta~0.04, xi~0.4, rho~-0.7 for SPX
    dates = pd.bdate_range(
        end    = datetime.date.today(),
        periods = n_days,
    )

    # Simulate with some vol clustering manually
    def sim_garch_prices(S0, omega, alpha, beta, n, seed):
        rng = np.random.default_rng(seed)
        h   = np.zeros(n)
        r   = np.zeros(n)
        h[0] = omega / (1 - alpha - beta)
        for t in range(1, n):
            h[t] = omega + alpha * r[t-1]**2 + beta * h[t-1]
            r[t] = np.sqrt(h[t]) * rng.standard_normal()
        return S0 * np.exp(np.cumsum(r))

    prices = pd.DataFrame({
        "SPX":  sim_garch_prices(4500, 0.00001, 0.08, 0.91, n_days, seed=1),
        "SX5E": sim_garch_prices(4300, 0.00002, 0.10, 0.89, n_days, seed=2),
        "SMI":  sim_garch_prices(11000, 0.000008, 0.07, 0.92, n_days, seed=3),
    }, index=dates)

    # --- Run calibrator with synthetic data ---
    cal = HestonCalibrator(
        tickers    = {},           # ignored when prices_df is provided
        years      = 5,
        rv_window  = 21,
        mle_refine = False,
        prices_df  = prices,
    )

    result = cal.calibrate()

    print("\n--- Ready to feed into simulator ---")
    print(f"params[0]: {result.params[0]}")
    print(f"corr_SS:\n{np.round(result.corr_SS, 3)}")

    # --- Demonstrate MLE refinement ---
    print("\n--- Re-running with MLE refinement ---")
    cal_mle = HestonCalibrator(
        tickers    = {},
        years      = 5,
        rv_window  = 21,
        mle_refine = True,
        prices_df  = prices,
    )
    result_mle = cal_mle.calibrate()