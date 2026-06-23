"""
core/simulator_cpp.py
---------------------
Thin Python wrapper over the optional `heston_cpp` C++ engine (cpp/). Mirrors the
numpy engine's contract so it can be validated against it and, once validated,
wired into HestonMultiSimulator.run(engine="cpp").

The compiled module is OPTIONAL — it must be built first (see cpp/README.md):
    pip install ./cpp
Importing this module raises ImportError with that hint if it isn't built; the
default numpy engine never imports it, so the app runs with no build step.
"""

from __future__ import annotations

import numpy as np

try:
    import heston_cpp  # built from cpp/heston_kernel.cpp
except ImportError as e:  # pragma: no cover - exercised only when unbuilt
    raise ImportError(
        "The 'cpp' engine requires the compiled heston_cpp module. Build it with "
        "`pip install ./cpp` (needs a C++17 compiler; see cpp/README.md), or use "
        "the default engine='numpy'."
    ) from e


def simulate_full(S0v, V0v, kappa, theta, xi, mu, L, dt_arr, sdt_arr,
                  div, t_dof, seed, n_base, n_assets, N, nthreads=0):
    """Run the C++ kernel and return (S_paths, V_paths) as lists of n arrays
    shaped (n_total, N+1) — the same contract HestonMultiSimulator.run() returns.

    `div` may be None (→ all-zero, no-op ×1). `t_dof` None → Gaussian.
    `nthreads`: 0 (default) = auto (all cores, or HESTON_NUM_THREADS/OMP_NUM_THREADS);
    a positive value pins the worker count. Output is identical for any thread
    count (per-block seeding), so this is purely a performance knob.
    """
    div_arr = (np.ascontiguousarray(div, dtype=np.float64)
               if div is not None else np.zeros((n_assets, N)))
    S_cube, V_cube = heston_cpp.simulate(            # (n_total, N+1, n) each
        np.ascontiguousarray(S0v, dtype=np.float64),
        np.ascontiguousarray(V0v, dtype=np.float64),
        np.ascontiguousarray(kappa, dtype=np.float64),
        np.ascontiguousarray(theta, dtype=np.float64),
        np.ascontiguousarray(xi, dtype=np.float64),
        np.ascontiguousarray(mu, dtype=np.float64),
        np.ascontiguousarray(L, dtype=np.float64),
        np.ascontiguousarray(dt_arr, dtype=np.float64),
        np.ascontiguousarray(sdt_arr, dtype=np.float64),
        div_arr,
        float(t_dof or 0.0), int(seed or 0), int(n_base),
        int(nthreads or 0),
    )
    S = [np.ascontiguousarray(S_cube[:, :, i]) for i in range(n_assets)]
    V = [np.ascontiguousarray(V_cube[:, :, i]) for i in range(n_assets)]
    return S, V
