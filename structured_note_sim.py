import numpy as np
import pandas as pd
from heston_calibrator import HestonCalibrator
from heston_simulator import HestonMultiSimulator

# ==============================================================================
# 1. PHYSICAL CALIBRATION FROM CSV FILES
# ==============================================================================
print("Starting historical calibration from CSV downloads...")
cal = HestonCalibrator(
    csv_files = {
        "SPX.csv":  "SPX",
        "SX5E.csv": "SX5E",
        "SMI.csv":  "SMI",
    },
    rv_window  = 21,
    mle_refine = False,
)
result = cal.calibrate()
print("Calibration complete.")

# ==============================================================================
# 2. CONFIGURING THE PHYSICAL FORECASTING SIMULATION
# ==============================================================================
# The simulation utilizes the true historical drifts (mu) extracted 
# by your calibrator from your data files.

T = 1.0          # 12 Months maturity
N = 252          # Trading days
n_paths = 50000  # Number of paths for statistical forecasting
seed = 42

print(f"\nRunning physical multi-asset Heston simulation ({n_paths} paths)...")
sim = HestonMultiSimulator(
    params   = result.params,
    corr_SS  = result.corr_SS,
    corr_VV  = result.corr_VV,
    corr_SV  = result.corr_SV,
    T        = T,
    N        = N,
    n_paths  = n_paths,
    seed     = seed,
)
sim_results = sim.run()

# ==============================================================================
# 3. STRUCTURED NOTE OPERATIONAL ENGINE (ANNUALIZED RETURNS)
# ==============================================================================
print("\nEvaluating structured note contract rules over simulated paths...")

asset_names = [p.name for p in result.params]
n_assets = len(asset_names)

# Combine the list of paths into a single 3D numpy array of shape (n_paths, N+1, n_assets)
sim_prices = np.stack(sim_results["S_paths"], axis=2)

# Normalize paths to find relative performance (S_t / S_0)
S0_vector = np.array([p.S0 for p in result.params]).reshape(1, 1, n_assets)
perf_paths = sim_prices / S0_vector

# Vectorized tracking of the worst performing underlying asset across all steps
worst_of_paths = np.min(perf_paths, axis=2)

# Set precise daily steps matching 3M, 6M, and 9M milestones
steps_per_quarter = N // 4
obs_steps = [steps_per_quarter, steps_per_quarter * 2, steps_per_quarter * 3]

# Allocation arrays to collect empirical outcomes
nominal_payoffs = np.zeros(n_paths)
annualized_returns = np.zeros(n_paths)
autocall_events = np.zeros(n_paths)  # Tracks the exact quarter of automatic execution (0 if never)

for idx in range(n_paths):
    autocalled_early = False
    
    # Evaluate programmatic contractual execution on specific observation steps
    for q, step in enumerate(obs_steps):
        t_years = (q + 1) * 0.25
        worst_of_perf = worst_of_paths[idx, step]
        
        # AUTOMATIC CALL RULE: Triggered if worst-of asset performance >= 95%
        if worst_of_perf >= 0.95:
            # Note terminates automatically. Returns 100% principal + 10% p.a. prorated coupon
            payout = 1.0 + (0.10 * t_years)
            nominal_payoffs[idx] = payout
            
            # Annualize based on the exact fraction of the year held before being called
            annualized_returns[idx] = (payout ** (1.0 / t_years)) - 1.0
            
            autocall_events[idx] = q + 1
            autocalled_early = True
            break  # Subsequent observations are void once the note is called
            
    # If the note survives all quarters without triggering, evaluate final Maturity (T = 1.0)
    if not autocalled_early:
        t_years = 1.0
        worst_of_final = worst_of_paths[idx, N]
        
        if worst_of_final >= 0.95:
            # Scenario A: Worst-of index finishes above 95% -> Full upside payout
            payout = 0.95 + 1.00 * (worst_of_final - 0.95)
        else:
            # Scenario B: Worst-of index is below 95% -> Hard capital floor applies
            payout = 0.95
            
        nominal_payoffs[idx] = payout
        # At T=1.0, the annualized return is identical to the nominal return rate
        annualized_returns[idx] = (payout ** (1.0 / t_years)) - 1.0

# ==============================================================================
# 4. PERFORMANCE ANALYSIS & STATS OUTPUT
# ==============================================================================
mean_nominal_return = np.mean(nominal_payoffs)
mean_annualized_return = np.mean(annualized_returns)

prob_q1 = np.mean(autocall_events == 1)
prob_q2 = np.mean(autocall_events == 2)
prob_q3 = np.mean(autocall_events == 3)
prob_mat = np.mean(autocall_events == 0)
prob_floor = np.mean((autocall_events == 0) & (worst_of_paths[:, N] < 0.95))

print("\n" + "="*60)
print("       REAL-WORLD PROFILE PERFORMANCE FORECAST (P-MEASURE)     ")
print("="*60)
print(f"Underlyings Basket                       : {', '.join(asset_names)}")
print(f"Expected Nominal Payout at Termination   : ${mean_nominal_return:.4f} (per $1.00 invested)")
print(f"Expected Absolute Total Return           : {(mean_nominal_return - 1.0) * 100:.2f}%")
print(f"Expected Annualized Rate of Return (IRR) : {mean_annualized_return * 100:.2f}%")
print("-"*60)
print(f"Probability of Automatic Call at 3M (Q1) : {prob_q1 * 100:.2f}%")
print(f"Probability of Automatic Call at 6M (Q2) : {prob_q2 * 100:.2f}%")
print(f"Probability of Automatic Call at 9M (Q3) : {prob_q3 * 100:.2f}%")
print(f"Probability of Surviving to Maturity     : {prob_mat * 100:.2f}%")
print(f"Probability of Ending in Capital Floor   : {prob_floor * 100:.2f}%")
print("="*60)

# Run structural diagnostic plots
sim.plot()