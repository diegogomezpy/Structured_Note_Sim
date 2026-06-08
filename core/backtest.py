"""
core/backtest.py
----------------
Historical backtest: replay the note on every valid issue date using
actual realized index prices (no simulation).

Accepts a pre-loaded price DataFrame — use data.loader.load_prices() to
produce it.

Usage
-----
from data.loader import load_prices
from core.backtest import run_backtest
from core.note import NoteTerms

prices = load_prices()
terms  = NoteTerms(n_obs=4, coupon_rate=0.025, coupon_barrier=0.55)
bt, summary = run_backtest(prices, terms, seed=42)
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from core.note import NoteTerms, _basket


def run_backtest(
    prices:           pd.DataFrame,
    terms:            NoteTerms,
    issue_freq_weeks: int = 2,
    seed:             int = 42,
) -> tuple[pd.DataFrame, dict]:
    """
    Evaluate the note on every valid issue date in the price history
    using actual realized index prices.

    Parameters
    ----------
    prices           : pd.DataFrame
        Aligned daily closing prices (one column per asset, sorted by date).
    terms            : NoteTerms
        Product specification.
    issue_freq_weeks : int
        Spacing between sampled issue dates in weeks.
    seed             : int
        RNG seed for autocall probability draws.

    Returns
    -------
    bt      : pd.DataFrame  — one row per issue date
    summary : dict          — aggregate statistics
    """
    rng = np.random.default_rng(seed)

    maturity_days   = round(terms.maturity * 252)
    obs_day_offsets = [round(t / terms.maturity * maturity_days) for t in terms.obs_times()]

    first_valid = prices.index[maturity_days]
    last_valid  = prices.index[-(maturity_days + 1)]
    sampled     = pd.date_range(
        start=first_valid, end=last_valid, freq=f"{issue_freq_weeks}W"
    )

    asset_names = list(prices.columns)
    n_assets    = len(asset_names)
    records     = []

    for issue_date in sampled:
        issue_idx = prices.index.searchsorted(issue_date)
        if issue_idx >= len(prices) - maturity_days:
            continue

        issue_date = prices.index[issue_idx]
        S0         = prices.iloc[issue_idx].values.astype(float)

        called        = False
        call_quarter  = 0
        payout        = None
        t_held        = terms.maturity
        pending_coupons = 0  # memory coupon accumulator

        for q, offset in enumerate(obs_day_offsets):
            obs_idx = issue_idx + offset
            if obs_idx >= len(prices):
                break

            perf         = prices.iloc[obs_idx].values.astype(float) / S0  # (n_assets,)
            perf_2d      = perf.reshape(1, -1)

            coupon_val   = float(_basket(perf_2d, terms.coupon_basket)[0])
            autocall_val = float(_basket(perf_2d, terms.autocall_basket)[0])

            # Coupon payment (with memory if enabled)
            coupon_paid = 0.0
            if coupon_val >= terms.coupon_barrier:
                if terms.memory:
                    coupon_paid = terms.coupon_rate * (pending_coupons + 1)
                    pending_coupons = 0
                else:
                    coupon_paid = terms.coupon_rate
            else:
                if terms.memory:
                    pending_coupons += 1

            # Autocall check (only from autocall_start_period onward)
            if q + 1 >= terms.autocall_start_period:
                p_call = float(terms.autocall_prob(np.array([autocall_val]))[0])
                if rng.random() < p_call:
                    t_held       = terms.obs_times()[q]
                    payout       = 1.0 + coupon_paid   # principal + coupon(s) at call
                    call_quarter = q + 1
                    called       = True
                    break

        # Maturity redemption
        mat_idx  = issue_idx + maturity_days
        perf_mat = prices.iloc[mat_idx].values.astype(float) / S0
        perf_mat_2d = perf_mat.reshape(1, -1)

        if not called:
            worst_final = float(perf_mat.min())
            final_val   = float(_basket(perf_mat_2d, terms.final_basket)[0])

            knock_in = worst_final < terms.knock_in_barrier
            if knock_in:
                payout = worst_final  # cash-equivalent physical delivery
            else:
                payout = max(terms.principal_protection, final_val)

            # Add any remaining memory coupons that weren't triggered
            # (no barrier hit at maturity = no coupon, memory lost)
            call_quarter = 0
            t_held       = terms.maturity

        irr = (1.0 + (payout - 1.0)) ** (1.0 / t_held) - 1.0

        row: dict = {
            "Issue Date":       issue_date.date(),
            "Call Quarter":     call_quarter,
            "Payout":           payout,
            "IRR":              irr,
            "Worst Asset":      asset_names[int(perf_mat.argmin())],
            "Worst Final Perf": float(perf_mat.min()),
        }
        for i, name in enumerate(asset_names):
            row[f"{name} Perf"] = float(perf_mat[i])

        records.append(row)

    bt = pd.DataFrame(records)
    if bt.empty:
        return bt, {}

    knock_in_mask = (bt["Call Quarter"] == 0) & (bt["Worst Final Perf"] < terms.knock_in_barrier)

    summary = {
        "n_issues":      len(bt),
        "mean_irr":      float(bt["IRR"].mean()),
        "median_irr":    float(bt["IRR"].median()),
        "prob_floor":    float(knock_in_mask.mean()),      # legacy key used by app
        "prob_called":   float((bt["Call Quarter"] > 0).mean()),
        "prob_knock_in": float(knock_in_mask.mean()),
        "prob_maturity": float((bt["Call Quarter"] == 0).mean()),
        **{f"prob_q{i}": float((bt["Call Quarter"] == i).mean())
           for i in range(1, min(4, terms.n_obs + 1))},
    }

    return bt, summary