import pandas as pd
from heston_calibrator import HestonCalibrator
from heston_simulator import HestonMultiSimulator

# Calibrate directly from raw Yahoo Finance CSV downloads
cal = HestonCalibrator(
    csv_files = {
        "SPX.csv":     "SPX",
        "SX5E.csv": "SX5E",
        "SMI.csv":     "SMI",
    },
    rv_window  = 21,
    mle_refine = False,
)
result = cal.calibrate()

# Simulate
sim = HestonMultiSimulator(
    params   = result.params,
    corr_SS  = result.corr_SS,
    corr_VV  = result.corr_VV,
    corr_SV  = result.corr_SV,
    T        = 1.0,
    N        = 252,
    n_paths  = 20_000,
    seed     = 42,
)
sim_results = sim.run()
sim.plot()