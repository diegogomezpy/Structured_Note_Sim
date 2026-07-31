"""
tests/test_simulator.py
-----------------------
The simulator had NO tests until a review found the Milstein variance correction
shipped at xi²/2 — exactly twice the correct xi²/4 — in both the numpy reference
and the C++ kernel. Nothing caught it because the term has zero mean, so it never
moved a headline average; it inflated the VARIANCE of the variance process, and
no assertion was looking there.

Everything here drives the REAL `HestonMultiSimulator`. An earlier draft of this
file reimplemented the variance step locally with the coefficient injected, which
read fine and guarded nothing: mutating core/simulator.py left every test's
verdict unchanged. A test helper that duplicates production logic is the same
mistake this codebase forbids in the payoff engine.

The yardstick is the CIR distribution's exact conditional moments, which is the
only thing a doubled correction term visibly violates.
"""
from __future__ import annotations

import importlib.util

import numpy as np
import pytest

from core.simulator import HestonMultiSimulator, HestonParams, nearest_psd


def cir_moments(V0: float, k: float, th: float, xi: float, T: float) -> tuple[float, float]:
    """Exact CIR conditional moments:
       E[V_T | V_0]   = theta + (V_0 - theta) e^{-kT}
       Var[V_T | V_0] = V_0 (xi²/k)(e^{-kT} - e^{-2kT}) + (theta xi²/2k)(1 - e^{-kT})²
    """
    m = th + (V0 - th) * np.exp(-k * T)
    v = (V0 * (xi ** 2 / k) * (np.exp(-k * T) - np.exp(-2 * k * T))
         + (th * xi ** 2 / (2 * k)) * (1 - np.exp(-k * T)) ** 2)
    return m, v


# The regime this app actually calibrates to: xi pinned at its 2.0 bound with
# kappa nudged to a Feller margin of ~0.01. A real observed calibration, and the
# only regime where an xi² error is bigger than Monte Carlo noise — at xi=0.2 the
# doubled and correct coefficients land within 0.2pp of each other, which is why
# the discriminating test below uses these numbers and not a gentler set.
HARD = dict(V0=0.08393, k=14.8491, th=0.13503, xi=2.0, T=1.4685)
MILD = dict(V0=0.04, k=2.0, th=0.04, xi=0.20, T=1.0)


def _run(params: dict, *, n_paths=30_000, seed=13, n_steps=370, n_assets=1, **over):
    """One run of the production simulator on a uniform grid."""
    p = [HestonParams(name=f"A{i}", S0=100.0, kappa=params["k"], theta=params["th"],
                      xi=params["xi"], rho=-0.6, V0=params["V0"], mu=0.05)
         for i in range(n_assets)]
    eye = np.eye(n_assets)
    ss = np.full((n_assets, n_assets), 0.35)
    np.fill_diagonal(ss, 1.0)
    sim = HestonMultiSimulator(
        params=p, corr_SS=ss, corr_VV=eye, corr_SV=eye * -0.6,
        n_paths=n_paths, seed=seed,
        dt_grid=np.full(n_steps, params["T"] / n_steps), **over)
    return sim.run(engine="numpy")


@pytest.mark.parametrize("params,label", [(MILD, "mild"), (HARD, "calibrated")])
def test_variance_process_matches_exact_cir_moments(params, label):
    """The discretised variance must reproduce the exact CIR mean and variance.

    THIS is the assertion that catches a doubled Milstein term. Measured through
    the real simulator at the calibrated regime: xi²/4 lands at +4.7% variance
    error, xi²/2 at +9.2%. The 7% bound sits between them, so reverting
    core/simulator.py's 0.25 to 0.5 turns this red — mutation-verified, not
    assumed. Full truncation biases the variance slightly high, which is why the
    bound is one-sided-ish and not tighter.
    """
    exact_m, exact_v = cir_moments(**params)
    V = _run(params)["V_paths"][0][:, -1]
    assert V.mean() == pytest.approx(exact_m, rel=0.03), f"{label}: E[V_T] off"
    assert abs(V.var() / exact_v - 1.0) < 0.07, (
        f"{label}: Var[V_T] is {V.var() / exact_v - 1.0:+.2%} vs exact CIR — "
        "a doubled Milstein correction looks like this")


def test_variance_never_negative_and_prices_positive():
    """Full truncation keeps sqrt(V) real; log-Euler keeps S positive. If either
    fails, perf_paths goes NaN or negative and every barrier test downstream is
    meaningless rather than merely wrong."""
    res = _run(HARD, n_paths=8000)
    V = res["V_paths"][0]
    S = np.stack(res["S_paths"], axis=2)
    assert np.all(V >= 0.0) and np.all(np.isfinite(V))
    assert np.all(S > 0.0) and np.all(np.isfinite(S))


def test_antithetic_doubles_paths_and_pairs_are_mirrored():
    """n_paths in => 2*n_paths out, with the second half the antithetic twin of
    the first. A broken pairing silently halves the effective sample size while
    still reporting the doubled count."""
    res = _run(MILD, n_paths=500)
    S = np.stack(res["S_paths"], axis=2)
    assert S.shape[0] == 1000, "antithetic must double the path count"
    lg = np.log(S[:, -1, 0] / S[0, 0, 0])
    base, twin = lg[:500], lg[500:]
    assert abs(base.mean() + twin.mean() - 2 * lg.mean()) < 1e-9


def test_seed_is_deterministic_and_different_seeds_differ():
    a = np.stack(_run(MILD, n_paths=400, seed=7)["S_paths"], axis=2)
    b = np.stack(_run(MILD, n_paths=400, seed=7)["S_paths"], axis=2)
    c = np.stack(_run(MILD, n_paths=400, seed=8)["S_paths"], axis=2)
    assert np.array_equal(a, b), "same seed must reproduce exactly"
    assert not np.array_equal(a, c), "different seeds must differ"


def test_t_copula_shocks_are_standardised():
    """A raw t(v) has variance v/(v-2), so without the sqrt((v-2)/v) rescale every
    Brownian increment is inflated — +41% at v=4 — and the simulation runs far
    hotter than the calibrated theta. Compare terminal dispersion against the
    Gaussian copula on the same seed."""
    g = np.stack(_run(MILD, n_paths=6000, seed=5)["S_paths"], axis=2)
    t = np.stack(_run(MILD, n_paths=6000, seed=5, t_dof=4)["S_paths"], axis=2)
    sd_g = np.log(g[:, -1, 0] / g[0, 0, 0]).std()
    sd_t = np.log(t[:, -1, 0] / t[0, 0, 0]).std()
    assert sd_t / sd_g < 1.25, (
        f"t-copula dispersion {sd_t / sd_g:.3f}x Gaussian — shocks unstandardised?")


def test_nearest_psd_projects_and_keeps_unit_diagonal():
    bad = np.array([[1.0, 0.95, -0.95], [0.95, 1.0, 0.95], [-0.95, 0.95, 1.0]])
    assert np.linalg.eigvalsh(bad).min() < 0, "fixture must actually be non-PSD"
    fixed = nearest_psd(bad)
    assert np.linalg.eigvalsh(fixed).min() >= -1e-10, "projection must be PSD"
    assert np.allclose(np.diag(fixed), 1.0), "must remain a correlation matrix"
    assert np.allclose(fixed, fixed.T)


# ── the C++ kernel, in the configuration production actually uses ────────────
# `engine="cpp"` is the default on /api/simulate, /api/compare and /api/report and
# the Docker image installs the wheel, but nothing exercised it: every test here
# hard-codes engine="numpy", and scripts/compare_engines.py builds its comparison
# with t_dof=None and div_schedule=None — the two defaults production NEVER takes
# (the calibrator always returns an int t_dof, and the engine always passes a
# dividend schedule). So the Student-t block and the dividend drop in the kernel
# were compared to the reference by nothing, manual or automated.
#
# The contract is convergence of statistics, not bit-equality: the kernel uses its
# own xoshiro256++ stream, so the two engines are deliberately not comparable path
# by path. Tolerances are sized for that.
# A module-level importorskip would skip this WHOLE file when the wheel is absent,
# silently taking the numpy tests with it — and CI does not install heston_cpp, so
# that is precisely where the coverage would disappear. Mark only the cpp tests.
_HAS_CPP = importlib.util.find_spec("heston_cpp") is not None
requires_cpp = pytest.mark.skipif(
    not _HAS_CPP,
    reason="heston_cpp not built — `pip install ./cpp` into this interpreter")


def _both_engines(*, n_paths=20_000, seed=21, n_steps=252, t_dof=None, divs=False):
    """Run the SAME configuration through both engines and return (numpy, cpp)."""
    T = 1.0
    p = [HestonParams(name="A", S0=100.0, kappa=2.0, theta=0.04, xi=0.30,
                      rho=-0.6, V0=0.04, mu=0.05)]
    div = None
    if divs:
        # Four 1% ex-date drops, as build_dividend_schedule produces: (n_assets, N).
        div = np.zeros((1, n_steps))
        div[0, [40, 100, 160, 220]] = 0.01
    out = []
    for eng in ("numpy", "cpp"):
        sim = HestonMultiSimulator(
            params=p, corr_SS=np.eye(1), corr_VV=np.eye(1), corr_SV=np.eye(1) * -0.6,
            n_paths=n_paths, seed=seed, t_dof=t_dof,
            dt_grid=np.full(n_steps, T / n_steps), div_schedule=div)
        out.append(sim.run(engine=eng))
    return out


@requires_cpp
@pytest.mark.parametrize("t_dof,divs,label", [
    (None, False, "gaussian, no dividends"),
    (4,    False, "student-t copula"),
    (None, True,  "dividend drops"),
    (4,    True,  "PRODUCTION: t-copula + dividends"),
])
def test_cpp_engine_matches_numpy_statistically(t_dof, divs, label):
    """Both engines must agree on the distribution they produce. The last case is
    the one every real run takes and the one nothing covered."""
    npy, cp = _both_engines(t_dof=t_dof, divs=divs)
    for key, tol in (("S_paths", 0.02), ("V_paths", 0.05)):
        a = npy[key][0][:, -1]
        b = cp[key][0][:, -1]
        assert b.mean() == pytest.approx(a.mean(), rel=tol), f"{label}: {key} mean"
        assert b.std() == pytest.approx(a.std(), rel=3 * tol), f"{label}: {key} std"
    assert np.all(np.isfinite(cp["S_paths"][0])) and np.all(cp["S_paths"][0] > 0)


@requires_cpp
def test_cpp_applies_the_dividend_drops():
    """The kernel's dividend multiply is a branch `compare_engines.py` never took.
    Four 1% ex-date drops must pull the terminal mean down by ~(1-0.01)^4 relative
    to the same seed with no dividends — in BOTH engines, by the same factor."""
    expected = 0.99 ** 4
    for eng_pair, tag in ((0, "numpy"), (1, "cpp")):
        with_d = _both_engines(divs=True)[eng_pair]["S_paths"][0][:, -1].mean()
        no_d = _both_engines(divs=False)[eng_pair]["S_paths"][0][:, -1].mean()
        assert with_d / no_d == pytest.approx(expected, rel=0.02), (
            f"{tag}: dividend drop factor {with_d / no_d:.4f}, expected ~{expected:.4f}")


@requires_cpp
def test_cpp_standardises_the_t_copula_like_numpy():
    """An unstandardised t(4) inflates every shock by ~41%. If the kernel skipped
    the sqrt((v-2)/v) rescale the numpy engine applies, its terminal dispersion
    would blow out relative to the Gaussian case while numpy's stayed put."""
    g_np, g_cp = _both_engines(t_dof=None)
    t_np, t_cp = _both_engines(t_dof=4)
    ratio_np = t_np["S_paths"][0][:, -1].std() / g_np["S_paths"][0][:, -1].std()
    ratio_cp = t_cp["S_paths"][0][:, -1].std() / g_cp["S_paths"][0][:, -1].std()
    assert ratio_cp == pytest.approx(ratio_np, rel=0.10), (
        f"t-copula dispersion ratio numpy={ratio_np:.3f} vs cpp={ratio_cp:.3f}")
    assert ratio_cp < 1.30, f"cpp t(4) shocks look unstandardised ({ratio_cp:.3f}x)"


# ── the correlation a worst-of actually gets ─────────────────────────────────
def _corr_roundtrip(target, *, xi=0.5, kappa=3.2, vv=0.0, seeds=3):
    """Ask for a RETURN correlation; measure what the returns actually do."""
    p = [HestonParams(name=f"A{i}", S0=100.0, kappa=kappa, theta=0.04, xi=xi,
                      rho=-0.5, V0=0.04, mu=0.05) for i in range(2)]
    ss = np.full((2, 2), target); np.fill_diagonal(ss, 1.0)
    vvm = np.full((2, 2), vv);   np.fill_diagonal(vvm, 1.0)
    out = []
    for sd in range(seeds):
        sim = HestonMultiSimulator(params=p, corr_SS=ss, corr_VV=vvm,
                                   corr_SV=np.eye(2) * -0.5, n_paths=1, seed=sd,
                                   dt_grid=np.full(3000, 1 / 252))
        res = sim.run(engine="numpy")
        lr = np.diff(np.log(np.column_stack([res["S_paths"][i][0] for i in range(2)])), axis=0)
        out.append(float(np.corrcoef(lr.T)[0, 1]))
    return float(np.mean(out)), sim


@pytest.mark.parametrize("target", [0.30, 0.60])
def test_simulated_returns_hit_the_requested_correlation(target):
    """`corr_SS` is a TARGET RETURN correlation and the simulator must deliver it.

    It did not: a return is sqrt(V)·dW and the variance processes are independent,
    so the random scaling diluted the driver correlation by k_i·k_j — the
    simulator returned 72-78% of what it was given, right across the calibrated
    regime. Since the calibrator MEASURES corr_SS from realised return
    correlation, the round trip lost a quarter of the co-movement: underlyings
    moving together at 0.85 were simulated at ~0.61. On a worst-of that is more
    dispersion, a worse basket, and a knock-in reported higher than the
    underlyings imply.

    The drivers are now inflated by 1/(k_i k_j), with k measured off the variance
    process itself (`variance_scale_factors`). Mutation-verified: passing
    match_return_corr=False puts 0.60 back at ~0.47.
    """
    got, _ = _corr_roundtrip(target)
    assert abs(got - target) < 0.04, f"asked {target}, got {got:+.3f}"


def test_a_correlation_too_high_to_reach_is_reported_not_hidden():
    """Compensation has a ceiling: at a high target the driver would need to
    exceed 1, and the 2n x 2n block cannot stay PSD with leverage on the diagonal.
    Those runs keep the closest achievable co-movement and set the flag, so the
    shortfall is visible instead of silent. Correlating the variance processes —
    which the calibrator does estimate from realised RV — recovers much of it."""
    got_lo, sim = _corr_roundtrip(0.85, vv=0.0)
    assert sim.corr_uplift_capped, "0.85 needs more than the drivers can carry"
    got_hi, _ = _corr_roundtrip(0.85, vv=0.85)
    assert got_hi > got_lo, "correlated variance must recover some of the shortfall"
    # Still better than the uncompensated 0.63 this replaced.
    assert got_lo > 0.65, f"capped case {got_lo:+.3f} is no better than before"


def test_opting_out_gives_the_raw_driver_behaviour():
    """`match_return_corr=False` keeps corr_SS as a literal driver correlation —
    the old contract, for a caller that wants it."""
    p = [HestonParams(name=f"A{i}", S0=100.0, kappa=3.2, theta=0.04, xi=0.5,
                      rho=-0.5, V0=0.04, mu=0.05) for i in range(2)]
    ss = np.full((2, 2), 0.60); np.fill_diagonal(ss, 1.0)
    sim = HestonMultiSimulator(params=p, corr_SS=ss, corr_VV=np.eye(2),
                               corr_SV=np.eye(2) * -0.5, n_paths=1, seed=0,
                               dt_grid=np.full(3000, 1 / 252), match_return_corr=False)
    res = sim.run(engine="numpy")
    lr = np.diff(np.log(np.column_stack([res["S_paths"][i][0] for i in range(2)])), axis=0)
    assert float(np.corrcoef(lr.T)[0, 1]) < 0.55, "opting out must NOT compensate"
