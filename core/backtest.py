"""
core/backtest.py
----------------
Historical backtest: replay the note on every valid issue date using
actual realized index prices (no simulation).
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
    bt_start:         pd.Timestamp | None = None,
    bt_end:           pd.Timestamp | None = None,
) -> tuple[pd.DataFrame, dict]:
    """
    bt_start / bt_end : optional date range for issue dates.
        If provided, only issue dates within [bt_start, bt_end] are tested.
        The prices DataFrame must still cover the full maturity window around
        each issue date, so pass the full price history here.
    """

    rng = np.random.default_rng(seed)

    maturity_days   = round(terms.maturity * 252)
    obs_day_offsets = [round(t / terms.maturity * maturity_days) for t in terms.obs_times()]

    # Need at least 2 * maturity_days rows: one full maturity before the first
    # valid issue date and one full maturity after the last.
    if len(prices) < 2 * maturity_days + 1:
        raise ValueError(
            f"Price history too short for backtest: {len(prices)} trading days available "
            f"but at least {2 * maturity_days + 1} required "
            f"(2 × {maturity_days}-day maturity window). "
            f"Increase history_years or shorten the note maturity."
        )

    # Natural bounds: need maturity_days of history before and after each issue date
    first_valid = prices.index[maturity_days]
    last_valid  = prices.index[-maturity_days]

    # Apply optional user-specified date range on top of natural bounds
    if bt_start is not None:
        first_valid = max(first_valid, bt_start)
    if bt_end is not None:
        last_valid  = min(last_valid, bt_end)

    if first_valid > last_valid:
        return pd.DataFrame(), {}

    sampled     = pd.date_range(start=first_valid, end=last_valid,
                                freq=f"{issue_freq_weeks}W")

    asset_names = list(prices.columns)
    records     = []

    for issue_date in sampled:
        issue_idx = prices.index.searchsorted(issue_date)
        if issue_idx >= len(prices) - maturity_days:
            continue

        issue_date = prices.index[issue_idx]
        S0         = prices.iloc[issue_idx].values.astype(float)

        called               = False
        call_quarter         = 0
        t_held               = terms.maturity
        pending_coupons      = 0   # memory: periods missed since last payment
        total_coupons_paid   = 0.0 # running sum of ALL coupons paid across periods

        for q, offset in enumerate(obs_day_offsets):
            obs_idx = issue_idx + offset
            if obs_idx >= len(prices):
                break

            perf     = prices.iloc[obs_idx].values.astype(float) / S0
            perf_2d  = perf.reshape(1, -1)

            coupon_val   = float(_basket(perf_2d, terms.coupon_basket)[0])
            autocall_val = float(_basket(perf_2d, terms.autocall_basket)[0])

            # ── Coupon for this period ────────────────────────────────────
            if coupon_val >= terms.coupon_barrier:
                if terms.memory:
                    # Pay this period + all previously missed periods
                    period_coupon = terms.coupon_rate * (pending_coupons + 1)
                    pending_coupons = 0
                else:
                    period_coupon = terms.coupon_rate
            else:
                period_coupon = 0.0
                if terms.memory:
                    pending_coupons += 1

            total_coupons_paid += period_coupon

            # ── Autocall check ────────────────────────────────────────────
            if q + 1 >= terms.autocall_start_period:
                p_call = float(terms.autocall_prob(np.array([autocall_val]))[0])
                if rng.random() < p_call:
                    t_held       = terms.obs_times()[q]
                    call_quarter = q + 1
                    called       = True
                    break

        # ── Final payout ─────────────────────────────────────────────────
        mat_idx  = issue_idx + maturity_days
        perf_mat = prices.iloc[mat_idx].values.astype(float) / S0

        if called:
            # Principal always returned at autocall; maturity price not needed.
            principal = 1.0
        else:
            worst_final = float(perf_mat.min())
            knock_in    = worst_final < terms.knock_in_barrier
            # Note: no upside participation in either worst-of or best-of Phoenix notes.
            # BBVA best-of final basket: cases A and B both pay exactly 100% when no KI.
            if knock_in:
                principal = worst_final          # cash-equivalent physical delivery
            else:
                principal = terms.principal_protection   # no KI → return floor (100%)
            t_held = terms.maturity

        payout = principal + total_coupons_paid
        # Simple annualised IRR — consistent with price_note()
        irr    = (payout - 1.0) / t_held

        row: dict = {
            "Issue Date":       pd.Timestamp(issue_date),
            "Call Quarter":     call_quarter,
            "Principal":        principal,
            "Total Coupons":    total_coupons_paid,
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
        "prob_floor":    float(knock_in_mask.mean()),
        "prob_called":   float((bt["Call Quarter"] > 0).mean()),
        "prob_knock_in": float(knock_in_mask.mean()),
        "prob_maturity": float((bt["Call Quarter"] == 0).mean()),
        **{f"prob_q{i}": float((bt["Call Quarter"] == i).mean())
           for i in range(1, min(4, terms.n_obs + 1))},
    }

    return bt, summary