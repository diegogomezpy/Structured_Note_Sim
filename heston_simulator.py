"""
heston_simulator.py
-------------------
Multi-asset Heston Stochastic Volatility Model simulator.

Model dynamics for asset i (under risk-neutral measure):
    dS_i = S_i * sqrt(V_i) * dW_Si
    dV_i = kappa_i*(theta_i - V_i)*dt + xi_i*sqrt(V_i)*dW_Vi
    dW_Si * dW_Vi = rho_i * dt          (own leverage effect)

Cross-asset dependency is specified via a 3-block correlation structure
that assembles into a full 2n x 2n matrix:

    C = [ corr_SS  corr_SV ]
        [ corr_SV' corr_VV ]

where:
    corr_SS[i,j] = correlation between asset i and j returns
    corr_VV[i,j] = correlation between asset i and j variance shocks
    corr_SV[i,j] = correlation between asset i return and asset j variance shock
                   diagonal of corr_SV = each asset's own rho (leverage effect)

The 2n x 2n matrix is Cholesky-decomposed to generate correlated Brownian
increments at each step. If the user-supplied blocks produce a non-PSD matrix,
a nearest-PSD projection (Higham 2002) is applied automatically.

Discretization: Euler-Maruyama with full truncation (variance floored at 0).

Usage
-----
    from heston_simulator import HestonParams, HestonMultiSimulator

    params = [
        HestonParams(name="SPX",   S0=100, kappa=2.0, theta=0.04, xi=0.30, rho=-0.70, V0=0.04),
        HestonParams(name="SX5E",  S0=100, kappa=1.5, theta=0.05, xi=0.35, rho=-0.65, V0=0.05),
        HestonParams(name="SMI",   S0=100, kappa=1.8, theta=0.035,xi=0.25, rho=-0.60, V0=0.035),
    ]

    corr_SS = np.array([[1.0, 0.75, 0.65],
                        [0.75,1.0,  0.60],
                        [0.65,0.60, 1.0 ]])

    corr_VV = np.array([[1.0, 0.50, 0.40],
                        [0.50,1.0,  0.45],
                        [0.40,0.45, 1.0 ]])

    # Diagonal = own rho; off-diagonal = cross asset-vol terms (typically ~0)
    corr_SV = np.array([[-0.70, 0.02, 0.02],
                        [ 0.02,-0.65, 0.02],
                        [ 0.02, 0.02,-0.60]])

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
    sim.plot()
"""

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
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
    """
    name  : str
    S0    : float
    kappa : float
    theta : float
    xi    : float
    rho   : float
    V0    : float

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
    Euler-Maruyama simulation of the Heston model for n assets jointly.

    The 2n Brownian motions (n price + n variance) are correlated via a
    full 2n x 2n block correlation matrix assembled from three n x n blocks.

    Parameters
    ----------
    params   : list[HestonParams]   – One HestonParams per asset (length n).
    corr_SS  : np.ndarray (n x n)   – Return-return correlations.
    corr_VV  : np.ndarray (n x n)   – Variance-variance correlations.
    corr_SV  : np.ndarray (n x n)   – Cross correlations.
                                       corr_SV[i,i] = rho_i (own leverage).
                                       corr_SV[i,j] = cross term (i≠j).
    T        : float  – Time horizon in years.
    N        : int    – Number of time steps.
    n_paths  : int    – Monte Carlo paths.
    seed     : int    – RNG seed.
    r        : float  – Risk-free rate for discounting. Default 0.
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
        r:        float        = 0.0,
    ):
        self.params   = params
        self.n_assets = len(params)
        self.T        = T
        self.N        = N
        self.n_paths  = n_paths
        self.seed     = seed
        self.r        = r

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
        Simulate all paths for all assets simultaneously.

        At each time step t:
          1. Draw 2n independent N(0,1) shocks:  Z ~ (n_paths, 2n)
          2. Correlate via Cholesky:              W = Z @ L.T  => correlated shocks
          3. Split W into price shocks W_S[:,i] and variance shocks W_V[:,i]
          4. Advance each asset's S and V with Euler-Maruyama

        Returns
        -------
        dict with keys:
            S_paths    : list of n arrays (n_paths, N+1) – price paths per asset
            V_paths    : list of n arrays (n_paths, N+1) – variance paths per asset
            S_terminal : np.ndarray (n_paths, n)          – terminal prices
            log_returns_terminal : np.ndarray (n_paths, n)
            realized_corr : np.ndarray (n, n) – realized return correlations
            feller     : list of (bool, float) per asset
        """
        n   = self.n_assets
        dt  = self.T / self.N
        sdt = np.sqrt(dt)
        rng = np.random.default_rng(self.seed)

        # Feller check for each asset
        feller_results = []
        print()
        for p in self.params:
            ok, margin = p.feller_condition()
            feller_results.append((ok, margin))
            status = "[OK]     " if ok else "[WARNING]"
            print(f"  {status} Feller — {p.name}: 2κθ - ξ² = {margin:.4f}  "
                  + ("✓" if ok else "✗  (full truncation applied)"))

        # Pre-allocate: store as list of arrays for clean per-asset access
        S = [np.empty((self.n_paths, self.N + 1)) for _ in range(n)]
        V = [np.empty((self.n_paths, self.N + 1)) for _ in range(n)]
        for i, p in enumerate(self.params):
            S[i][:, 0] = p.S0
            V[i][:, 0] = p.V0

        # Main simulation loop
        for t in range(self.N):
            # Draw (n_paths, 2n) independent standard normals
            Z = rng.standard_normal((self.n_paths, 2 * n))

            # Correlate: multiply by Cholesky factor
            # W[path, k] is the correlated shock for Brownian k
            # Layout: W[:, 0..n-1] = price shocks, W[:, n..2n-1] = variance shocks
            W = Z @ self.L.T   # (n_paths, 2n)

            for i, p in enumerate(self.params):
                dW_S = W[:, i]     * sdt   # price shock for asset i
                dW_V = W[:, n + i] * sdt   # variance shock for asset i

                V_t   = V[i][:, t]
                V_pos = np.maximum(V_t, 0.0)
                sqV   = np.sqrt(V_pos)

                # Variance step with full truncation
                V_next = V_t + p.kappa * (p.theta - V_t) * dt + p.xi * sqV * dW_V
                V[i][:, t + 1] = np.maximum(V_next, 0.0)

                # Price step (log-Euler)
                S[i][:, t + 1] = S[i][:, t] * np.exp(-0.5 * V_pos * dt + sqV * dW_S)

        self.S_paths = S
        self.V_paths = V

        # Build output arrays
        S_T = np.column_stack([S[i][:, -1] for i in range(n)])          # (n_paths, n)
        S0  = np.array([p.S0 for p in self.params])
        LR  = np.log(S_T / S0[np.newaxis, :])                           # (n_paths, n)

        # Realized pairwise return correlations (from daily log-returns)
        daily_lr = np.stack(
            [np.diff(np.log(S[i]), axis=1) for i in range(n)],
            axis=2
        )  # (n_paths, N, n)
        # Average correlation across paths
        realized_corr = np.mean(
            [np.corrcoef(daily_lr[path].T) for path in range(self.n_paths)],
            axis=0
        )

        results = {
            "S_paths":               S,
            "V_paths":               V,
            "S_terminal":            S_T,
            "log_returns_terminal":  LR,
            "realized_corr":         realized_corr,
            "feller":                feller_results,
        }

        self._print_summary(results)
        return results

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def _print_summary(self, results: dict) -> None:
        n   = self.n_assets
        S_T = results["S_terminal"]
        LR  = results["log_returns_terminal"]
        RC  = results["realized_corr"]

        print("\n" + "=" * 60)
        print("  HESTON MULTI-ASSET SIMULATION SUMMARY")
        print("=" * 60)
        print(f"  Assets   : {[p.name for p in self.params]}")
        print(f"  Paths    : {self.n_paths:,}    Steps: {self.N}    T: {self.T}yr")
        print()
        for i, p in enumerate(self.params):
            print(f"  {p.name}:")
            print(f"    S0={p.S0:.1f}  V0={p.V0:.4f} (σ≈{np.sqrt(p.V0)*100:.1f}%)  "
                  f"θ={p.theta:.4f} (σ≈{np.sqrt(p.theta)*100:.1f}%)")
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
        print("  Realized return correlations:")
        names = [p.name for p in self.params]
        header = "         " + "  ".join(f"{nm:>7}" for nm in names)
        print(header)
        for i, nm in enumerate(names):
            row = "  ".join(f"{RC[i,j]:+.3f}" for j in range(n))
            print(f"  {nm:>7}  {row}")
        print("=" * 60 + "\n")

    def plot(self, n_display: int = 40) -> None:
        """
        Diagnostic dashboard:
          Row 1: Price paths per asset
          Row 2: Vol paths per asset
          Row 3: Terminal log-return distributions
          Row 4: Correlation heatmaps (input vs realized)
        """
        if self.S_paths is None:
            raise RuntimeError("Call run() before plot().")

        n      = self.n_assets
        t_grid = np.linspace(0, self.T, self.N + 1)
        rng    = np.random.default_rng(0)
        idx    = rng.integers(0, self.n_paths, size=n_display)
        colors = ["steelblue", "darkorange", "seagreen", "crimson", "mediumpurple"]

        fig = plt.figure(figsize=(5 * n, 18), constrained_layout=True)
        fig.suptitle("Heston Multi-Asset — Simulation Diagnostics", fontsize=14,
                     fontweight="bold", y=1.01)
        gs  = gridspec.GridSpec(4, n, figure=fig, hspace=0.0, wspace=0.0)

        LR = np.log(
            np.column_stack([self.S_paths[i][:, -1] for i in range(n)]) /
            np.array([p.S0 for p in self.params])
        )

        # Realized corr (recompute for plot)
        daily_lr = np.stack(
            [np.diff(np.log(self.S_paths[i]), axis=1) for i in range(n)], axis=2
        )
        realized_corr = np.mean(
            [np.corrcoef(daily_lr[path].T) for path in range(self.n_paths)], axis=0
        )

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

        plt.savefig("heston_multi_diagnostics.png", dpi=150)
        plt.show()
        print("[Saved] heston_multi_diagnostics.png")


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
        r        = 0.0,
    )

    results = sim.run()
    sim.plot()