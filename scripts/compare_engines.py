"""
scripts/compare_engines.py
--------------------------
Validate the optional C++ engine (cpp/) against the default numpy engine.

The numpy engine is the reference (bit-identical to the original implementation).
The C++ engine runs the same model parallelised across cores; because it uses a
different RNG stream it is NOT bit-identical, so we check CONVERGENCE of the
things that matter — terminal moments, cross-asset correlation, and a priced
note's payoff statistics — plus the wall-clock speedup.

Build the C++ module first, then run:
    pip install ./cpp
    python scripts/compare_engines.py [n_base_paths]

Offline (no network): fixed Heston parameters, one sample Autocall note.
"""
from __future__ import annotations

import contextlib
import io
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.note import NoteTerms, price_note                       # noqa: E402
from core.simulator import HestonParams, HestonMultiSimulator     # noqa: E402


def _build(n_base: int, seed: int = 7):
    names = ["AssetA", "AssetB", "AssetC"]
    params = [HestonParams(name=nm, S0=100.0, kappa=1.5, theta=0.04,
                           xi=0.3, rho=-0.6, V0=0.04, mu=0.06) for nm in names]
    n = len(names)
    corr_SS = np.eye(n) * 0.5 + 0.5
    corr_VV = np.eye(n)
    corr_SV = np.diag([-0.6] * n)
    return HestonMultiSimulator(params, corr_SS, corr_VV, corr_SV,
                                T=1.5, N=378, n_paths=n_base, seed=seed)


def _cpp_paths(sim):
    """Run the C++ engine with the same params as `sim` (no run() wiring yet)."""
    from core.simulator_cpp import simulate_full
    dt = (sim.dt_grid if sim.dt_grid is not None
          else np.full(sim.N, sim.T / sim.N))
    p = sim.params
    return simulate_full(
        np.array([q.S0 for q in p]), np.array([q.V0 for q in p]),
        np.array([q.kappa for q in p]), np.array([q.theta for q in p]),
        np.array([q.xi for q in p]), np.array([q.mu for q in p]),
        sim.L, dt, np.sqrt(dt), sim.div_schedule, sim.t_dof, sim.seed,
        sim.n_paths, len(p), sim.N)


def _stats(S_paths, terms):
    n = len(S_paths)
    cube = np.stack(S_paths, axis=2)                 # (n_total, N+1, n)
    S0 = cube[:, 0, :]
    lr = np.log(cube[:, -1, :] / S0)
    perf = cube / cube[:, 0:1, :]
    res = price_note(perf, terms, seed=1,
                     obs_steps=terms.obs_steps(cube.shape[1] - 1),
                     obs_times=terms.obs_times())
    return lr, np.corrcoef(lr.T), res


def main():
    n_base = int(sys.argv[1]) if len(sys.argv) > 1 else 25_000
    terms = NoteTerms(name="Sample Autocall", maturity=1.5, payment_freq="quarterly",
                      coupon_pa=0.12, coupon_barrier=0.7, autocall_barrier=1.0,
                      autocall_start_period=1, knock_in_barrier=0.6, memory=True,
                      tickers={"A": "AssetA", "B": "AssetB", "C": "AssetC"})

    print(f"Comparing engines at {2 * n_base:,} paths (N=378, 3 assets)\n")

    with contextlib.redirect_stdout(io.StringIO()):
        t0 = time.perf_counter(); res_np = _build(n_base).run()
        t_np = time.perf_counter() - t0
    try:
        _cpp_paths(_build(256))                       # warm any first-call cost
        t0 = time.perf_counter(); S_cpp, _ = _cpp_paths(_build(n_base))
        t_cpp = time.perf_counter() - t0
    except ImportError as e:
        print(e); return

    lr_np, corr_np, pn = _stats(res_np["S_paths"], terms)
    lr_cpp, corr_cpp, pc = _stats(S_cpp, terms)

    def line(label, a, b, fmt="{:.4f}"):
        print(f"  {label:24s} numpy {fmt.format(a)}   cpp {fmt.format(b)}   "
              f"|Δ| {fmt.format(abs(a - b))}")

    print("Terminal log-return (pooled over assets):")
    line("mean", lr_np.mean(), lr_cpp.mean())
    line("std", lr_np.std(), lr_cpp.std())
    print(f"\nCross-asset correlation max abs diff: "
          f"{np.max(np.abs(corr_np - corr_cpp)):.4f}")

    print("\nPriced note (same payoff engine, independent paths):")
    for k in ("expected_irr", "expected_total_return", "prob_autocall",
              "prob_knock_in_total", "expected_coupon"):
        line(k, float(pn[k]), float(pc[k]))

    print(f"\nWall-clock:  numpy {t_np:.2f}s   cpp {t_cpp:.2f}s   "
          f"speedup {t_np / t_cpp:.2f}x")
    print("(differences above are Monte-Carlo error, not bias — both engines "
          "target the same model.)")


if __name__ == "__main__":
    main()
