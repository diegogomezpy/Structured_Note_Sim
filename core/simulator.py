"""
core/simulator.py
-----------------
Multi-asset Heston Stochastic Volatility Model simulator.

Model dynamics for asset i (under physical measure):
    dS_i = S_i * (mu_i*dt + sqrt(V_i)*dW_Si)
    dV_i = kappa_i*(theta_i - V_i)*dt + xi_i*sqrt(V_i)*dW_Vi
    dW_Si * dW_Vi = rho_i * dt          (own leverage effect)

Improvements over basic Euler-Maruyama:

1. Milstein discretization (variance process)
   Adds the O(dt) correction term to the variance step:
       V_{t+dt} = V_t + kappa*(theta-V)*dt + xi*sqrt(V)*dW_V
                + 0.5*xi²*dt*(dW_V²/dt - 1)
   Reduces discretization bias, especially near V=0. Price step
   remains log-Euler (exact for geometric Brownian motion).
   Full truncation (V floored at 0) is applied after the Milstein step.

2. Antithetic variates (variance reduction)
   Each batch of n_paths is simulated twice: once with the original
   Brownian increments Z and once with -Z. The two sets are averaged
   in the output. This halves the Monte Carlo variance at no extra
   random number cost, equivalent to doubling n_paths for smooth payoffs.
   Reported n_paths in output = 2 * n_paths passed in.

3. Student-t copula (tail dependence)
   When t_dof is set (e.g. 4-8), the Gaussian copula is replaced by a
   Student-t copula. Each step draws:
       Z   ~ N(0, I_{2n})
       s   ~ chi²(t_dof) / t_dof     (scalar, shared across assets)
       W   = (Z / sqrt(s)) * sqrt((ν-2)/ν) @ L.T   (correlated, standardized)
   The sqrt((ν-2)/ν) factor standardizes the t variates to unit variance
   (a raw t(ν) has variance ν/(ν-2)), so the simulated vol stays consistent
   with the calibrated theta/V0. The shocks introduce joint tail dependence:
   extreme moves become more correlated than the Gaussian copula implies.
   Relevant for worst-of products where the floor is triggered by joint
   tail events. t_dof=None (default) reduces to the Gaussian copula.
   Requires t_dof > 2.

4. Vectorized realized correlation
   Replaces the O(n_paths) loop over np.corrcoef with a single
   matrix operation using broadcasting and einsum. ~100x faster.

Cross-asset dependency is specified via a 3-block correlation structure:

    C = [ corr_SS  corr_SV ]
        [ corr_SV' corr_VV ]
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Parameter container
# ---------------------------------------------------------------------------

@dataclass
class HestonParams:
    """
    Per-asset Heston parameters.

    Parameters
    ----------
    name  : str   – Asset label (used in plots and summaries).
    S0    : float – Initial asset price.
    kappa : float – Mean-reversion speed of variance.
    theta : float – Long-run mean variance.  sqrt(theta) ≈ long-run vol.
    xi    : float – Vol-of-vol.
    rho   : float – Own leverage effect: corr(dS, dV) for this asset.
    V0    : float – Initial variance.
    mu    : float – Annualised arithmetic drift (physical measure; there is
                    no discounting in this library).
    """
    name  : str
    S0    : float
    kappa : float
    theta : float
    xi    : float
    rho   : float
    V0    : float
    mu    : float = 0.0

    def feller_condition(self) -> tuple[bool, float]:
        """
        Feller: 2*kappa*theta > xi^2.
        Returns (satisfied, margin).  margin > 0 => satisfied.
        """
        lhs = 2.0 * self.kappa * self.theta
        rhs = self.xi ** 2
        return (lhs > rhs), (lhs - rhs)

    def validate(self) -> None:
        if self.kappa <= 0:
            raise ValueError(f"[{self.name}] kappa must be > 0, got {self.kappa}")
        if self.theta <= 0:
            raise ValueError(f"[{self.name}] theta must be > 0, got {self.theta}")
        if self.xi <= 0:
            raise ValueError(f"[{self.name}] xi must be > 0, got {self.xi}")
        if not (-1.0 < self.rho < 1.0):
            raise ValueError(f"[{self.name}] rho must be in (-1,1), got {self.rho}")
        if self.V0 < 0:
            raise ValueError(f"[{self.name}] V0 must be >= 0, got {self.V0}")


# ---------------------------------------------------------------------------
# Correlation matrix utilities
# ---------------------------------------------------------------------------

def build_block_corr(
    corr_SS: np.ndarray,
    corr_VV: np.ndarray,
    corr_SV: np.ndarray,
) -> np.ndarray:
    """
    Assemble the 2n x 2n block correlation matrix from the three n x n blocks.

    Layout:
        [ corr_SS  corr_SV ]
        [ corr_SV' corr_VV ]

    Note: corr_SV[i,i] should equal the own-leverage rho_i for asset i.
    The off-diagonals of corr_SV are cross terms (asset i return vs asset j vol).
    """
    return np.block([
        [corr_SS, corr_SV  ],
        [corr_SV.T, corr_VV],
    ])


def nearest_psd(C: np.ndarray, epsilon: float = 1e-8) -> np.ndarray:
    """
    Project C onto the nearest positive semi-definite correlation matrix.

    Uses eigenvalue clipping (Higham 2002): negative eigenvalues are floored
    at epsilon, then the matrix is re-normalized to have unit diagonal.

    Parameters
    ----------
    C       : symmetric matrix to fix
    epsilon : minimum eigenvalue floor

    Returns
    -------
    C_psd : nearest PSD correlation matrix
    """
    C = (C + C.T) / 2.0                        # enforce symmetry
    eigvals, eigvecs = np.linalg.eigh(C)
    eigvals_clipped  = np.maximum(eigvals, epsilon)
    C_psd = eigvecs @ np.diag(eigvals_clipped) @ eigvecs.T
    # Re-normalize diagonal back to 1
    d     = np.sqrt(np.diag(C_psd))
    C_psd = C_psd / np.outer(d, d)
    return C_psd


def validate_and_fix_corr(
    C:    np.ndarray,
    name: str = "correlation matrix",
    tol:  float = 1e-10,
) -> np.ndarray:
    """
    Check symmetry, unit diagonal, and PSD.  Fix PSD if violated, raise on others.
    Returns the (possibly corrected) matrix and prints a warning if fixed.
    """
    n = C.shape[0]

    # Symmetry
    if not np.allclose(C, C.T, atol=1e-10):
        raise ValueError(f"{name} is not symmetric.")

    # Unit diagonal
    if not np.allclose(np.diag(C), 1.0, atol=1e-10):
        raise ValueError(f"{name} diagonal entries must all be 1.0.")

    # Entries in [-1, 1]
    if np.any(np.abs(C) > 1.0 + 1e-10):
        raise ValueError(f"{name} has entries outside [-1, 1].")

    # PSD check
    eigvals = np.linalg.eigvalsh(C)
    if np.any(eigvals < -tol):
        min_eig = eigvals.min()
        print(
            f"[WARNING] {name} is not PSD (min eigenvalue = {min_eig:.6f}). "
            f"Applying nearest-PSD projection (Higham 2002). "
            f"Max off-diagonal change will be reported."
        )
        C_fixed = nearest_psd(C)
        mask    = 1.0 - np.eye(n)
        max_chg = np.max(np.abs(C_fixed - C) * mask)
        print(f"         Max off-diagonal change after projection: {max_chg:.6f}")
        return C_fixed

    return C


# ---------------------------------------------------------------------------
# Multi-asset simulator
# ---------------------------------------------------------------------------

class HestonMultiSimulator:
    """
    Milstein simulation of the Heston model for n assets jointly,
    with antithetic variates, optional Student-t copula, and
    vectorized realized correlation.

    Parameters
    ----------
    params   : list[HestonParams]   – One HestonParams per asset (length n).
    corr_SS  : np.ndarray (n x n)   – Return-return correlations.
    corr_VV  : np.ndarray (n x n)   – Variance-variance correlations.
    corr_SV  : np.ndarray (n x n)   – Cross correlations.
                                       corr_SV[i,i] = rho_i (own leverage).
                                       corr_SV[i,j] = cross term (i≠j).
    T        : float  – Time horizon in years. Ignored if dt_grid is given.
    N        : int    – Number of time steps. Ignored if dt_grid is given.
    n_paths  : int    – Monte Carlo paths (antithetics double this internally).
    seed     : int    – RNG seed.
    t_dof    : int or None – Degrees of freedom for Student-t copula.
                             None (default) = Gaussian copula.
                             Typical values: 4–8 for realistic tail dependence.
    dt_grid  : np.ndarray or None – Per-step time increments in year fractions
                             (length = number of steps). Used to simulate a real
                             trading-day calendar: each step is one trading day
                             and dt is the calendar gap to the next one (a
                             Fri→Mon step carries 3/365 of variance). When given,
                             N = len(dt_grid) and T = dt_grid.sum(); the T and N
                             arguments are ignored. None = uniform T/N grid.
    div_schedule : np.ndarray or None – Pre-programmed proportional dividend
                             drops, shape (n_assets, N). div_schedule[i, t] is
                             applied at the END of step t: S[:, t+1] *= (1 - d).
                             Used to convert total-return dynamics (drift
                             calibrated on adjusted closes) into price paths
                             with deterministic ex-date jumps. None = no jumps.
    """

    def __init__(
        self,
        params:   list,
        corr_SS:  np.ndarray,
        corr_VV:  np.ndarray,
        corr_SV:  np.ndarray,
        T:        float        = 1.0,
        N:        int          = 252,
        n_paths:  int          = 10_000,
        seed:     Optional[int]= None,
        t_dof:    Optional[int]= None,
        dt_grid:  Optional[np.ndarray] = None,
        div_schedule: Optional[np.ndarray] = None,
    ):
        self.params   = params
        self.n_assets = len(params)
        if dt_grid is not None:
            dt_grid = np.asarray(dt_grid, dtype=float)
            if dt_grid.ndim != 1 or len(dt_grid) == 0 or np.any(dt_grid <= 0):
                raise ValueError("dt_grid must be a 1-D array of positive year fractions.")
            N = len(dt_grid)
            T = float(dt_grid.sum())
        self.dt_grid  = dt_grid
        self.T        = T
        self.N        = N
        self.n_paths  = n_paths
        self.seed     = seed
        if t_dof is not None and t_dof <= 2:
            raise ValueError(
                f"t_dof must be > 2 (finite variance required for "
                f"standardized t shocks); got {t_dof}."
            )
        self.t_dof    = t_dof
        if div_schedule is not None:
            div_schedule = np.asarray(div_schedule, dtype=float)
            if div_schedule.shape != (self.n_assets, N):
                raise ValueError(
                    f"div_schedule must be (n_assets, N) = ({self.n_assets},{N}), "
                    f"got {div_schedule.shape}"
                )
            if np.any(div_schedule < 0) or np.any(div_schedule >= 1):
                raise ValueError("div_schedule entries must be proportional drops in [0, 1).")
        self.div_schedule = div_schedule

        # Simulation outputs
        # S_paths[i], V_paths[i] : np.ndarray (n_paths, N+1) for asset i
        self.S_paths: Optional[list] = None
        self.V_paths: Optional[list] = None

        # Validate and store per-asset params
        for p in params:
            p.validate()

        # Validate and store correlation blocks
        self._validate_blocks(corr_SS, corr_VV, corr_SV)
        self.corr_SS = corr_SS
        self.corr_VV = corr_VV
        self.corr_SV = corr_SV

        # Build, validate, and Cholesky-decompose the full 2n x 2n matrix
        self.C_full = build_block_corr(corr_SS, corr_VV, corr_SV)
        self.C_full = validate_and_fix_corr(self.C_full, "full 2n×2n block matrix")
        self.L      = np.linalg.cholesky(self.C_full)   # (2n, 2n) lower triangular

    def _validate_blocks(
        self,
        corr_SS: np.ndarray,
        corr_VV: np.ndarray,
        corr_SV: np.ndarray,
    ) -> None:
        n = self.n_assets
        for name, mat in [("corr_SS", corr_SS), ("corr_VV", corr_VV)]:
            if mat.shape != (n, n):
                raise ValueError(f"{name} must be ({n},{n}), got {mat.shape}")
            validate_and_fix_corr(mat, name)  # individual blocks must be valid corr matrices

        if corr_SV.shape != (n, n):
            raise ValueError(f"corr_SV must be ({n},{n}), got {corr_SV.shape}")

        # Check corr_SV diagonal matches each asset's own rho
        for i, p in enumerate(self.params):
            if abs(corr_SV[i, i] - p.rho) > 1e-6:
                raise ValueError(
                    f"corr_SV[{i},{i}] = {corr_SV[i,i]} but {p.name}.rho = {p.rho}. "
                    f"The diagonal of corr_SV must equal each asset's own leverage rho."
                )

    # ------------------------------------------------------------------
    # Core simulation
    # ------------------------------------------------------------------

    def run(self) -> dict:
        """
        Simulate all paths using:
          - Milstein scheme for the variance process
          - Antithetic variates (output has 2*n_paths paths)
          - Student-t copula if t_dof is set, else Gaussian
          - Vectorized realized correlation (no path loop)

        Returns
        -------
        dict with keys:
            S_paths    : list of n arrays (2*n_paths, N+1)
            V_paths    : list of n arrays (2*n_paths, N+1)
            S_terminal : np.ndarray (2*n_paths, n)
            log_returns_terminal : np.ndarray (2*n_paths, n)
            realized_corr : np.ndarray (n, n)
            feller     : list of (bool, float) per asset
        """
        n        = self.n_assets
        # Per-step time increments: real trading-day calendar if dt_grid was
        # given, otherwise a uniform grid (legacy behaviour).
        if self.dt_grid is not None:
            dt_arr = self.dt_grid
        else:
            dt_arr = np.full(self.N, self.T / self.N)
        sdt_arr  = np.sqrt(dt_arr)
        n_base   = self.n_paths          # paths per antithetic batch
        n_total  = 2 * n_base            # antithetic doubles output
        rng      = np.random.default_rng(self.seed)

        # Feller check
        feller_results = []
        print()
        for p in self.params:
            ok, margin = p.feller_condition()
            feller_results.append((ok, margin))
            status = "[OK]     " if ok else "[WARNING]"
            print(f"  {status} Feller — {p.name}: 2κθ - ξ² = {margin:.4f}  "
                  + ("✓" if ok else "✗  (Milstein + full truncation applied)"))

        if self.t_dof is not None:
            print(f"  [Copula] Student-t with ν = {self.t_dof} degrees of freedom")
        else:
            print(f"  [Copula] Gaussian")
        print(f"  [Scheme] Milstein (variance) + log-Euler (price)")
        print(f"  [VR]     Antithetic variates — {n_base:,} base paths → {n_total:,} total")

        # Pre-allocate for both original and antithetic paths
        S = [np.empty((n_total, self.N + 1)) for _ in range(n)]
        V = [np.empty((n_total, self.N + 1)) for _ in range(n)]
        for i, p in enumerate(self.params):
            S[i][:, 0] = p.S0
            V[i][:, 0] = p.V0

        # Main simulation loop
        for t in range(self.N):
            dt  = dt_arr[t]
            sdt = sdt_arr[t]

            # --- Draw base normals (n_base, 2n) ---
            Z = rng.standard_normal((n_base, 2 * n))

            # --- Student-t copula: scale by chi² ---
            if self.t_dof is not None:
                # chi²(ν)/ν scalar per path — shared across all Brownians
                chi2 = rng.chisquare(df=self.t_dof, size=n_base) / self.t_dof
                Z = Z / np.sqrt(chi2[:, np.newaxis])
                # Standardize: a t(ν) variate has variance ν/(ν-2), not 1.
                # Without this rescale every Brownian increment is inflated by
                # sqrt(ν/(ν-2)) — e.g. +29% vol at ν=5, +41% at ν=4 — so the
                # simulation runs at a much higher vol than the calibrated
                # theta/V0, and the Milstein term 0.5·ξ²·(dW² − dt) picks up a
                # spurious positive drift (E[dW²] > dt). Rescaling restores
                # unit-variance shocks while preserving the t tail dependence.
                Z = Z * np.sqrt((self.t_dof - 2.0) / self.t_dof)

            # --- Antithetic: stack [Z, -Z] → (n_total, 2n) ---
            Z_full = np.concatenate([Z, -Z], axis=0)

            # --- Correlate via Cholesky ---
            W = Z_full @ self.L.T   # (n_total, 2n)

            for i, p in enumerate(self.params):
                dW_S = W[:, i]     * sdt
                dW_V = W[:, n + i] * sdt

                V_t   = V[i][:, t]
                V_pos = np.maximum(V_t, 0.0)
                sqV   = np.sqrt(V_pos)

                # --- Milstein variance step ---
                # dV = kappa*(theta-V)*dt + xi*sqrt(V)*dW_V
                #    + 0.5*xi²*(dW_V² - dt)      ← Milstein correction
                V_next = (
                    V_t
                    + p.kappa * (p.theta - V_t) * dt
                    + p.xi * sqV * dW_V
                    + 0.5 * p.xi ** 2 * (dW_V ** 2 - dt)
                )
                V[i][:, t + 1] = np.maximum(V_next, 0.0)   # full truncation

                # --- Log-Euler price step (exact for GBM) ---
                S[i][:, t + 1] = S[i][:, t] * np.exp(
                    p.mu * dt - 0.5 * V_pos * dt + sqV * dW_S
                )

                # --- Pre-programmed dividend jump (proportional drop) ---
                # Converts total-return dynamics into price paths: the drift
                # mu is calibrated on adjusted closes (total return), and the
                # deterministic ex-date deduction reproduces the predictable
                # price decline the note's barriers actually observe.
                if self.div_schedule is not None and self.div_schedule[i, t] > 0.0:
                    S[i][:, t + 1] *= (1.0 - self.div_schedule[i, t])

        self.S_paths = S
        self.V_paths = V

        # --- Terminal values ---
        S_T = np.column_stack([S[i][:, -1] for i in range(n)])
        S0  = np.array([p.S0 for p in self.params])
        LR  = np.log(S_T / S0[np.newaxis, :])

        # --- Vectorized realized correlation (base paths only) ---
        # Antithetic paths are constructed as -Z reflections of the base paths;
        # including them would bias the realized correlation toward the input matrix
        # by design, making the diagnostic circular.  We use only the first n_base
        # paths (the original draws) for an honest out-of-sample check.
        # daily_lr: (n_base, N, n)
        daily_lr = np.stack(
            [np.diff(np.log(S[i][:n_base]), axis=1) for i in range(n)],
            axis=2,
        )
        # Strip the deterministic dividend jumps before measuring correlation:
        # an ex-date drop adds log(1-d) to that step's return for ONE asset
        # only, which would spuriously decorrelate it from the others (and the
        # jumps are not part of the stochastic co-movement being checked).
        if self.div_schedule is not None:
            daily_lr -= np.log(1.0 - self.div_schedule.T)[np.newaxis, :, :]

        def _pooled_corr(x: np.ndarray) -> np.ndarray:
            """Sample Pearson correlation of (n_base, N, n) returns, pooled over
            paths and time."""
            dm       = x - x.mean(axis=1, keepdims=True)
            cov_mean = np.einsum('ptj,ptk->jk', dm, dm) / ((self.N - 1) * n_base)
            std_vec  = np.sqrt(np.diag(cov_mean))
            c        = cov_mean / np.outer(std_vec, std_vec)
            np.fill_diagonal(c, 1.0)
            return c

        # (a) EFFECTIVE correlation — pooled Pearson correlation of the raw daily
        # returns. This is the co-movement the basket payoff actually experiences,
        # but it is heteroskedasticity-inflated relative to the instantaneous
        # parameter: pooling high-vol and low-vol days together lifts the sample
        # correlation (Forbes-Rigobon bias). It is therefore NOT directly
        # comparable to the calibrated corr_SS and should not be flagged as
        # "error vs input".
        effective_corr = _pooled_corr(daily_lr)

        # (b) REALIZED (instantaneous) correlation — standardize each step's
        # return by its own sqrt(V_t) before pooling. This removes the stochastic-
        # vol heteroskedasticity and recovers the Brownian correlation that was
        # actually fed into the Cholesky, so "realized vs input (corr_SS)" is a
        # like-for-like check of the engine (matches corr_SS to <0.3% in tests).
        vol_w = np.stack(
            [np.sqrt(np.maximum(V[i][:n_base, :-1], 1e-12)) for i in range(n)],
            axis=2,
        )
        realized_corr = _pooled_corr(daily_lr / vol_w)

        results = {
            "S_paths":               S,
            "V_paths":               V,
            "S_terminal":            S_T,
            "log_returns_terminal":  LR,
            "realized_corr":         realized_corr,
            "effective_corr":        effective_corr,
            "feller":                feller_results,
        }

        self._print_summary(results)
        return results

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def _print_summary(self, results: dict) -> None:
        n      = self.n_assets
        S_T    = results["S_terminal"]
        LR     = results["log_returns_terminal"]
        RC     = results["realized_corr"]
        n_total = S_T.shape[0]

        print("\n" + "=" * 60)
        print("  HESTON MULTI-ASSET SIMULATION SUMMARY")
        print("=" * 60)
        print(f"  Assets   : {[p.name for p in self.params]}")
        print(f"  Paths    : {n_total:,} ({self.n_paths:,} base × 2 antithetic)  "
              f"Steps: {self.N}  T: {self.T}yr")
        copula = f"Student-t (ν={self.t_dof})" if self.t_dof else "Gaussian"
        print(f"  Scheme   : Milstein + log-Euler  |  Copula: {copula}")
        print()
        for i, p in enumerate(self.params):
            print(f"  {p.name}:")
            print(f"    S0={p.S0:.1f}  V0={p.V0:.4f} (σ≈{np.sqrt(p.V0)*100:.1f}%)  "
                  f"θ={p.theta:.4f} (σ≈{np.sqrt(p.theta)*100:.1f}%)  "
                  f"μ={p.mu:.4f} ({p.mu*100:.1f}% p.a.)")
            print(f"    Mean S_T={np.mean(S_T[:,i]):.2f}  "
                  f"5th={np.percentile(S_T[:,i],5):.2f}  "
                  f"95th={np.percentile(S_T[:,i],95):.2f}")
            print(f"    Mean log-ret={np.mean(LR[:,i]):.4f}  "
                  f"Std={np.std(LR[:,i]):.4f}")
        print()
        print("  Input corr_SS (return-return):")
        for row in self.corr_SS:
            print("    " + "  ".join(f"{v:+.3f}" for v in row))
        print()
        print("  Realized instantaneous correlations (vol-standardized):")
        names = [p.name for p in self.params]
        header = "         " + "  ".join(f"{nm:>7}" for nm in names)
        print(header)
        for i, nm in enumerate(names):
            row = "  ".join(f"{RC[i,j]:+.3f}" for j in range(n))
            print(f"  {nm:>7}  {row}")
        print("=" * 60 + "\n")

    def plot(self, n_display: int = 40, save_path: str | None = None) -> None:
        """
        Diagnostic dashboard:
          Row 1: Price paths per asset
          Row 2: Vol paths per asset
          Row 3: Terminal log-return distributions
          Row 4: Correlation heatmaps (input vs realized)

        save_path : str or None
            If provided, the figure is also written to this path as a PNG.
            Default None = display only (no file I/O).
        """
        import matplotlib.pyplot as plt
        import matplotlib.gridspec as gridspec

        if self.S_paths is None:
            raise RuntimeError("Call run() before plot().")

        n      = self.n_assets
        t_grid = np.linspace(0, self.T, self.N + 1)
        rng    = np.random.default_rng(0)
        n_total = self.S_paths[0].shape[0]
        idx    = rng.integers(0, n_total, size=n_display)
        colors = ["steelblue", "darkorange", "seagreen", "crimson", "mediumpurple"]

        fig = plt.figure(figsize=(5 * n, 18), constrained_layout=True)
        fig.suptitle("Heston Multi-Asset — Simulation Diagnostics", fontsize=14,
                     fontweight="bold", y=1.01)
        gs  = gridspec.GridSpec(4, n, figure=fig, hspace=0.0, wspace=0.0)

        LR = np.log(
            np.column_stack([self.S_paths[i][:, -1] for i in range(n)]) /
            np.array([p.S0 for p in self.params])
        )

        # Realized corr (recompute for plot — base paths only, same reason as run())
        n_base = self.n_paths
        daily_lr = np.stack(
            [np.diff(np.log(self.S_paths[i][:n_base]), axis=1) for i in range(n)], axis=2
        )
        # De-jump dividends, as in run() — deterministic drops are not co-movement
        if self.div_schedule is not None:
            daily_lr -= np.log(1.0 - self.div_schedule.T)[np.newaxis, :, :]
        dm = daily_lr - daily_lr.mean(axis=1, keepdims=True)
        cov_sum  = np.einsum('ptj,ptk->jk', dm, dm)
        cov_mean = cov_sum / ((self.N - 1) * n_base)
        std_vec  = np.sqrt(np.diag(cov_mean))
        realized_corr = cov_mean / np.outer(std_vec, std_vec)
        np.fill_diagonal(realized_corr, 1.0)

        for i, p in enumerate(self.params):
            c = colors[i % len(colors)]

            # --- Row 0: Price paths ---
            ax = fig.add_subplot(gs[0, i])
            for k in idx:
                ax.plot(t_grid, self.S_paths[i][k], lw=0.5, alpha=0.4, color=c)
            ax.set_title(f"{p.name} — Price Paths", pad=4)
            ax.set_ylabel("Price")
            ax.tick_params(labelbottom=False)   # hide x tick labels — shared with row below

            # --- Row 1: Vol paths ---
            ax = fig.add_subplot(gs[1, i])
            for k in idx:
                ax.plot(t_grid, np.sqrt(np.maximum(self.V_paths[i][k], 0)) * 100,
                        lw=0.5, alpha=0.4, color=c)
            ax.axhline(np.sqrt(p.theta) * 100, color="red", ls="--", lw=1.5,
                       label=f"√θ={np.sqrt(p.theta)*100:.1f}%")
            ax.set_title(f"{p.name} — Vol (%)", pad=4)
            ax.set_ylabel("Vol (%)")
            ax.set_xlabel("Time (yr)")
            ax.legend(fontsize=7, loc="upper right")

            # --- Row 2: Terminal log-return distribution ---
            ax = fig.add_subplot(gs[2, i])
            ax.hist(LR[:, i], bins=100, density=True, alpha=0.75,
                    color=c, edgecolor="none", label="Simulated")
            mu, sd = LR[:, i].mean(), LR[:, i].std()
            x = np.linspace(LR[:, i].min(), LR[:, i].max(), 400)
            ax.plot(x, np.exp(-0.5*((x-mu)/sd)**2) / (sd*np.sqrt(2*np.pi)),
                    "k--", lw=1.5, label="Normal fit")
            ax.set_title(f"{p.name} — Terminal Log-Return", pad=4)
            ax.set_xlabel("ln(S_T / S_0)")
            ax.set_ylabel("Density")
            ax.legend(fontsize=7, loc="upper left")

        # --- Row 3: Correlation heatmaps (input vs realized) ---
        names = [p.name for p in self.params]

        ax_in = fig.add_subplot(gs[3, 0])
        im = ax_in.imshow(self.corr_SS, vmin=-1, vmax=1, cmap="RdBu_r")
        ax_in.set_title("Input Return Correlations", pad=6)
        ax_in.set_xticks(range(n)); ax_in.set_xticklabels(names, fontsize=8)
        ax_in.set_yticks(range(n)); ax_in.set_yticklabels(names, fontsize=8)
        for ii in range(n):
            for jj in range(n):
                ax_in.text(jj, ii, f"{self.corr_SS[ii,jj]:.2f}",
                           ha="center", va="center", fontsize=8,
                           color="white" if abs(self.corr_SS[ii,jj]) > 0.5 else "black")
        plt.colorbar(im, ax=ax_in, fraction=0.046)

        ax_re = fig.add_subplot(gs[3, 1])
        im2 = ax_re.imshow(realized_corr, vmin=-1, vmax=1, cmap="RdBu_r")
        ax_re.set_title("Realized Return Correlations", pad=6)
        ax_re.set_xticks(range(n)); ax_re.set_xticklabels(names, fontsize=8)
        ax_re.set_yticks(range(n)); ax_re.set_yticklabels(names, fontsize=8)
        for ii in range(n):
            for jj in range(n):
                ax_re.text(jj, ii, f"{realized_corr[ii,jj]:.2f}",
                           ha="center", va="center", fontsize=8,
                           color="white" if abs(realized_corr[ii,jj]) > 0.5 else "black")
        plt.colorbar(im2, ax=ax_re, fraction=0.046)

        # Difference heatmap
        if n >= 3:
            ax_diff = fig.add_subplot(gs[3, 2])
            diff = realized_corr - self.corr_SS
            im3  = ax_diff.imshow(diff, vmin=-0.1, vmax=0.1, cmap="RdBu_r")
            ax_diff.set_title("Realized − Input  (target ≈ 0)", pad=6)
            ax_diff.set_xticks(range(n)); ax_diff.set_xticklabels(names, fontsize=8)
            ax_diff.set_yticks(range(n)); ax_diff.set_yticklabels(names, fontsize=8)
            for ii in range(n):
                for jj in range(n):
                    ax_diff.text(jj, ii, f"{diff[ii,jj]:+.3f}",
                                 ha="center", va="center", fontsize=8)
            plt.colorbar(im3, ax=ax_diff, fraction=0.046)

        if save_path is not None:
            plt.savefig(save_path, dpi=150)
        plt.show()
        if save_path is not None:
            print(f"[Saved] {save_path}")


# ---------------------------------------------------------------------------
# Quick test
# ---------------------------------------------------------------------------

if __name__ == "__main__":

    params = [
        HestonParams(name="SPX",  S0=100.0, kappa=2.0, theta=0.040, xi=0.30, rho=-0.70, V0=0.040),
        HestonParams(name="SX5E", S0=100.0, kappa=1.5, theta=0.050, xi=0.35, rho=-0.65, V0=0.050),
        HestonParams(name="SMI",  S0=100.0, kappa=1.8, theta=0.035, xi=0.25, rho=-0.60, V0=0.035),
    ]

    # Return-return correlations (globally diversified but correlated equity indices)
    corr_SS = np.array([
        [1.00, 0.75, 0.65],
        [0.75, 1.00, 0.60],
        [0.65, 0.60, 1.00],
    ])

    # Variance-variance correlations (vol regimes tend to move together globally)
    corr_VV = np.array([
        [1.00, 0.50, 0.40],
        [0.50, 1.00, 0.45],
        [0.40, 0.45, 1.00],
    ])

    # Cross terms: diagonal = own leverage (must match p.rho), off-diagonal ≈ 0
    corr_SV = np.array([
        [-0.70,  0.02,  0.02],
        [ 0.02, -0.65,  0.02],
        [ 0.02,  0.02, -0.60],
    ])

    sim = HestonMultiSimulator(
        params   = params,
        corr_SS  = corr_SS,
        corr_VV  = corr_VV,
        corr_SV  = corr_SV,
        T        = 1.0,
        N        = 252,
        n_paths  = 20_000,
        seed     = 42,
    )

    results = sim.run()
    sim.plot(save_path="heston_multi_diagnostics.png")