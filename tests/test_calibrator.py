"""
tests/test_calibrator.py
------------------------
`core/calibrator.py` had no tests. The bug that prompted these: `mu` was computed
as `mean(log-return)/dt + 0.5*theta` using the RAW theta, but theta is then clamped
to PARAM_BOUNDS max 0.50 (~71% vol) and the simulator mean-reverts to the CLAMPED
value. The half-theta added back is supposed to cancel the log-Euler step's -V/2;
when the two thetas differ, it doesn't, and the difference is pure invented drift.

Measured on a 92%-vol series before the fix: +15.4% per year of upward drift that
is not in the data — which on a knock-in product understates barrier risk, the one
direction you never want to be wrong in.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from core.calibrator import PARAM_BOUNDS, HestonCalibrator
from core.simulator import HestonMultiSimulator


def _series(vol: float, *, n: int = 1300, seed: int = 5) -> pd.DataFrame:
    """A GBM series with a known annualised mean log-return of -0.5*vol**2."""
    rng = np.random.default_rng(seed)
    dt = 1 / 252
    lr = rng.normal(-0.5 * vol ** 2 * dt, vol * np.sqrt(dt), n)
    return (pd.DataFrame({"HI": 100 * np.exp(np.cumsum(lr))},
                         index=pd.bdate_range("2019-01-01", periods=n)),
            float(lr.mean() / dt))


def _simulated_log_growth(cal, *, n_paths: int = 20_000, seed: int = 3) -> float:
    p = cal.params[0]
    sim = HestonMultiSimulator(
        params=cal.params, corr_SS=np.eye(1), corr_VV=np.eye(1),
        corr_SV=np.eye(1) * p.rho, n_paths=n_paths, seed=seed,
        dt_grid=np.full(252, 1 / 252), t_dof=cal.t_dof)
    S = sim.run(engine="numpy")["S_paths"][0]
    return float(np.log(S[:, -1] / S[:, 0]).mean())


@pytest.mark.parametrize("vol,clamps", [(0.35, False), (0.92, True)])
def test_simulated_growth_matches_the_calibration_window(vol, clamps):
    """The invariant `mu`'s derivation claims: simulated log-growth reproduces the
    realised log-growth of the calibration window.

    The high-vol case is the one that matters — it is the only one where theta hits
    its bound, and the only one the bug affected. Reverting `mu` to use the raw
    theta puts the error at ~+0.154/yr, so the 0.05 bound turns red — mutation-
    verified, not assumed.
    """
    df, realised = _series(vol)
    cal = HestonCalibrator(prices_df=df, calib_years=5).calibrate()
    assert (cal.params[0].theta >= PARAM_BOUNDS["theta"][1] - 1e-9) is clamps, (
        f"fixture must {'' if clamps else 'not '}hit the theta bound")
    err = _simulated_log_growth(cal) - realised
    assert abs(err) < 0.05, (
        f"simulated log-growth is {err:+.4f}/yr away from realised — mu and the "
        "theta the simulator uses have drifted apart")


def test_calibrated_parameters_are_inside_their_bounds():
    """Every parameter the simulator receives must be inside PARAM_BOUNDS: it
    validates them and raises, so an out-of-bounds estimate is a hard failure at
    run time rather than a bad number."""
    df, _ = _series(0.92)
    cal = HestonCalibrator(prices_df=df, calib_years=5).calibrate()
    for p in cal.params:
        for field in ("kappa", "theta", "xi", "rho"):
            lo, hi = PARAM_BOUNDS[field]
            assert lo <= getattr(p, field) <= hi, f"{p.name}.{field} out of bounds"
        assert p.V0 > 0 and np.isfinite(p.mu)
        p.validate()


def test_feller_is_enforced_after_clamping():
    """The nudge must leave 2*kappa*theta > xi**2. The simulator only warns, so a
    violated Feller condition silently degrades the variance path near zero."""
    df, _ = _series(0.92)
    cal = HestonCalibrator(prices_df=df, calib_years=5).calibrate()
    for p in cal.params:
        ok, margin = p.feller_condition()
        assert ok, f"{p.name}: Feller violated after calibration (margin {margin:.4f})"
