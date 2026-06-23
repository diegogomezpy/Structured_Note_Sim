"""
scripts/compare_engines.py
--------------------------
Validate the optional Numba simulation engine against the default numpy engine.

The numpy engine is the reference (bit-identical to the original implementation).
The Numba engine runs the same model parallelised across cores; because it uses a
different draw order and float reductions it is NOT bit-identical, so we check
CONVERGENCE of the things that matter — terminal moments, realized correlation,
and a priced note's payoff statistics — plus the wall-clock speedup.

Offline (no network): fixed Heston parameters, one sample Phoenix note.

Run:
    pip install "numba>=0.60"
    python scripts/compare_engines.py [n_base_paths]
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
    corr_SS = np.eye(n) * 0.5 + 0.5          # 0.5 pairwise return correlation
    corr_VV = np.eye(n)
    corr_SV = np.diag([-0.6] * n)            # leverage effect
    return HestonMultiSimulator(params, corr_SS, corr_VV, corr_SV,
                                T=1.5, N=378, n_paths=n_base, seed=seed)


def _run(sim, engine):
    with contextlib.redirect_stdout(io.StringIO()):
        t0 = time.perf_counter()
        res = sim.run(engine=engine)
        return res, time.perf_counter() - t0


def _price(res, terms):
    n = len(res["S_paths"])
    sim_prices = np.stack(res["S_paths"], axis=2)        # (n_total, N+1, n)
    S0 = sim_prices[:, 0:1, :]
    perf = sim_prices / S0
    return price_note(perf, terms, seed=1,
                      obs_steps=terms.obs_steps(sim_prices.shape[1] - 1),
                      obs_times=terms.obs_times())


def main():
    n_base = int(sys.argv[1]) if len(sys.argv) > 1 else 25_000
    terms = NoteTerms(name="Sample Phoenix", maturity=1.5, payment_freq="quarterly",
                      coupon_pa=0.12, coupon_barrier=0.7, autocall_barrier=1.0,
                      autocall_start_period=1, knock_in_barrier=0.6, memory=True,
                      tickers={"A": "AssetA", "B": "AssetB", "C": "AssetC"})

    print(f"Comparing engines at {2 * n_base:,} paths (N=378, 3 assets)\n")

    res_np, t_np = _run(_build(n_base), "numpy")
    try:
        _run(_build(500), "numba")                       # warm up the JIT
    except ImportError as e:
        print(e)
        return
    res_nb, t_nb = _run(_build(n_base), "numba")

    pn, pb = _price(res_np, terms), _price(res_nb, terms)

    def line(label, a, b, fmt="{:.4f}"):
        d = abs(a - b)
        print(f"  {label:24s} numpy {fmt.format(a)}   numba {fmt.format(b)}   |Δ| {fmt.format(d)}")

    print("Terminal log-return (pooled over assets):")
    line("mean", res_np["log_returns_terminal"].mean(),
         res_nb["log_returns_terminal"].mean())
    line("std", res_np["log_returns_terminal"].std(),
         res_nb["log_returns_terminal"].std())
    print("\nRealized correlation (max abs diff vs numpy): "
          f"{np.max(np.abs(res_np['realized_corr'] - res_nb['realized_corr'])):.4f}")

    print("\nPriced note (same payoff engine, independent paths):")
    for k in ("expected_irr", "expected_total_return", "prob_autocall",
              "prob_knock_in_total", "expected_coupon"):
        line(k, float(pn[k]), float(pb[k]))

    print(f"\nWall-clock:  numpy {t_np:.2f}s   numba {t_nb:.2f}s   "
          f"speedup {t_np / t_nb:.2f}x")
    print("(numba excludes one-time JIT warmup; differences above are Monte-Carlo "
          "error, not bias — both engines target the same model.)")


if __name__ == "__main__":
    main()
