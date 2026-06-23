"""
core/simulator_numba.py
-----------------------
Optional Numba JIT engine for HestonMultiSimulator.run(engine="numba").

This is a *validated reference* alternative to the default numpy engine, not a
replacement: the numpy path stays the source of truth (it is bit-identical to the
original implementation), and this one is checked against it by CONVERGENCE of
statistics, never bit-equality. The two cannot match bit-for-bit because the draw
order and float reductions differ — so compare expected IRR / payoff distribution
/ realized correlation, which agree to Monte-Carlo error.

Why it can be faster: the time loop is sequential per path, but paths are
independent, so the kernel parallelizes ACROSS base paths with `prange`
(each iteration also produces that path's antithetic twin). numpy runs this loop
single-threaded; here it uses every core.

Randomness is generated UP FRONT with numpy's Generator and passed in, not drawn
inside the kernel. Calling np.random.seed()/draws inside a numba `prange` is not
parallel-safe (the seed and the draws interleave across threads, which produced
occasional variance blow-ups); pre-generating makes the engine deterministic and
race-free. The cost is an (n_base, N, 2n) shock array — fine at the path counts
this visualization tool uses; it keeps full daily paths (the fans + explorer need
them), so it does not drop columns.

Numba is an OPTIONAL dependency. Importing this module raises ImportError with a
clear message if numba is missing; the default numpy engine never imports it.
"""

from __future__ import annotations

import numpy as np

try:
    from numba import njit, prange
except ImportError as e:  # pragma: no cover - exercised only without numba
    raise ImportError(
        "The 'numba' engine requires the numba package. Install it with "
        "`pip install numba`, or use the default engine='numpy'."
    ) from e


@njit(parallel=True, fastmath=True, cache=True)
def _heston_kernel(out_S, out_V, S0v, V0v, kappa, theta, xi, xi2, mu,
                   L, dt_arr, sdt_arr, div, Z, chi2, t_scale, n_base):
    """Fill out_S/out_V (shape (n_total, N+1, n), path-first) in place.

    Z      : (n_base, N, 2n) pre-drawn standard normals (one block per base path).
    chi2   : (n_base, N) pre-drawn chi²(ν)/ν for the Student-t copula, or a (1,1)
             dummy when t_scale == 0.
    t_scale: sqrt((ν-2)/ν) for the Student-t variance correction, or 0 for Gaussian.

    Mirrors the numpy model exactly: Milstein variance + full truncation, log-Euler
    price, deterministic dividend drops. The antithetic twin of base path b is
    written to row b + n_base using -dW for the linear terms (the Milstein dW² term
    and the dividend factor are sign-independent) — the [Z, -Z] pairing.
    """
    n   = S0v.shape[0]
    N   = dt_arr.shape[0]
    two = 2 * n
    for b in prange(n_base):
        Sb = S0v.copy(); Vb = V0v.copy()    # base path state
        Sa = S0v.copy(); Va = V0v.copy()    # antithetic path state
        for a in range(n):
            out_S[b, 0, a] = Sb[a]; out_V[b, 0, a] = Vb[a]
            out_S[b + n_base, 0, a] = Sa[a]; out_V[b + n_base, 0, a] = Va[a]

        w = np.empty(two)
        z = np.empty(two)
        for t in range(N):
            dt  = dt_arr[t]
            sdt = sdt_arr[t]
            for k in range(two):
                z[k] = Z[b, t, k]
            if t_scale > 0.0:                       # Student-t copula
                sc = t_scale / np.sqrt(chi2[b, t])
                for k in range(two):
                    z[k] *= sc
            # Correlate via Cholesky: w = L @ z  (2n×2n, explicit — no alloc).
            for r in range(two):
                acc = 0.0
                for cc in range(two):
                    acc += L[r, cc] * z[cc]
                w[r] = acc

            for a in range(n):
                dW_S = w[a]     * sdt
                dW_V = w[n + a] * sdt
                milstein = 0.5 * xi2[a] * (dW_V * dW_V - dt)   # sign-independent
                drop = 1.0 - div[a, t]
                # base path (+dW)
                Vp = Vb[a] if Vb[a] > 0.0 else 0.0
                sq = np.sqrt(Vp)
                Vn = Vb[a] + kappa[a] * (theta[a] - Vb[a]) * dt + xi[a] * sq * dW_V + milstein
                if Vn < 0.0:
                    Vn = 0.0
                Sn = Sb[a] * np.exp(mu[a] * dt - 0.5 * Vp * dt + sq * dW_S) * drop
                Vb[a] = Vn; Sb[a] = Sn
                out_S[b, t + 1, a] = Sn; out_V[b, t + 1, a] = Vn
                # antithetic path (-dW)
                Vpa = Va[a] if Va[a] > 0.0 else 0.0
                sqa = np.sqrt(Vpa)
                Vna = Va[a] + kappa[a] * (theta[a] - Va[a]) * dt - xi[a] * sqa * dW_V + milstein
                if Vna < 0.0:
                    Vna = 0.0
                Sna = Sa[a] * np.exp(mu[a] * dt - 0.5 * Vpa * dt - sqa * dW_S) * drop
                Va[a] = Vna; Sa[a] = Sna
                out_S[b + n_base, t + 1, a] = Sna; out_V[b + n_base, t + 1, a] = Vna


def simulate_full(S0v, V0v, kappa, theta, xi, mu, L, dt_arr, sdt_arr,
                  div, t_dof, seed, n_base, n_assets, N):
    """Run the Numba kernel and return (S_paths, V_paths) as lists of n arrays
    shaped (n_total, N+1) — the same contract the numpy engine returns.

    Randoms are drawn here with numpy's Generator (seeded) and passed into the
    kernel. div may be None (→ all-zero, no-op ×1). t_dof None → Gaussian.
    """
    twoN    = 2 * n_assets
    n_total = 2 * n_base
    rng = np.random.default_rng(seed)
    Z = rng.standard_normal((n_base, N, twoN))
    if t_dof is not None:
        chi2 = rng.chisquare(float(t_dof), size=(n_base, N)) / float(t_dof)
        t_scale = float(np.sqrt((t_dof - 2.0) / t_dof))
    else:
        chi2 = np.ones((1, 1))
        t_scale = 0.0

    div_arr = (np.ascontiguousarray(div, dtype=np.float64)
               if div is not None else np.zeros((n_assets, N)))
    out_S = np.empty((n_total, N + 1, n_assets))
    out_V = np.empty((n_total, N + 1, n_assets))
    _heston_kernel(
        out_S, out_V,
        np.ascontiguousarray(S0v, dtype=np.float64),
        np.ascontiguousarray(V0v, dtype=np.float64),
        np.ascontiguousarray(kappa, dtype=np.float64),
        np.ascontiguousarray(theta, dtype=np.float64),
        np.ascontiguousarray(xi, dtype=np.float64),
        np.ascontiguousarray(xi, dtype=np.float64) ** 2,
        np.ascontiguousarray(mu, dtype=np.float64),
        np.ascontiguousarray(L, dtype=np.float64),
        np.ascontiguousarray(dt_arr, dtype=np.float64),
        np.ascontiguousarray(sdt_arr, dtype=np.float64),
        div_arr, Z, chi2, t_scale, int(n_base),
    )
    S = [np.ascontiguousarray(out_S[:, :, i]) for i in range(n_assets)]
    V = [np.ascontiguousarray(out_V[:, :, i]) for i in range(n_assets)]
    return S, V
