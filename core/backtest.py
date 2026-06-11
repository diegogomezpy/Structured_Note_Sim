"""
core/backtest.py
----------------
Historical backtest: replay the note on every valid issue date using
actual realized index prices (no simulation).

Each historical issue date is treated as ONE 'path' and evaluated by the SAME
vectorized payoff engine (core.note.price_note) used for the Monte Carlo.
There is deliberately no second implementation of the payoff here — keeping a
single engine means term-sheet fixes (memory coupons, hard trigger, best-of
final-redemption rescue, ...) apply to simulation and backtest identically and
cannot drift apart.

Scheduling is calendar-first: observation k for an issue date is
``issue + k × (12 / periods_per_year) months``, snapped to the next available
trading day in the aligned price index (this is how term sheets define
observation dates). The performance array passed to the engine is compact —
one column per observation date plus the initial fixing, shape
``(n_issues, n_obs + 1, n_assets)`` — so ``terms.obs_steps(n_obs)`` resolves to
``[1..n_obs]`` and price_note evaluates it unchanged.

The prices DataFrame must be RAW (unadjusted) closes — that is what real
notes observe; realized prices already contain actual ex-date dividend drops.

This is exact because the autocall trigger is deterministic by default
(call_steepness=None): the payoff of a realized path does not depend on any
RNG. If a soft trigger is explicitly configured, the seed controls the
Bernoulli call draws, as in price_note.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from core.note import NoteTerms, price_note


def run_backtest(
    prices:     pd.DataFrame,
    terms:      NoteTerms,
    issue_freq: str = "MS",   # pandas offset alias; "MS" = monthly (month start)
    seed:       int = 42,
    bt_start:   pd.Timestamp | None = None,
    bt_end:     pd.Timestamp | None = None,
) -> tuple[pd.DataFrame, dict]:
    """
    bt_start / bt_end : optional date range for issue dates.
        If provided, only issue dates within [bt_start, bt_end] are tested.
        The prices DataFrame must still cover the full maturity window after
        each issue date, so pass the full price history here.
    """
    n_obs      = terms.n_obs
    mat_months = round(terms.maturity * 12)
    last_date  = prices.index[-1]

    # Need at least one issue date whose final observation (issue + maturity,
    # calendar months) falls within the available history.
    if prices.index[0] + pd.DateOffset(months=mat_months) > last_date:
        req_years = mat_months / 12.0
        raise ValueError(
            f"Price history too short for backtest: it spans "
            f"{prices.index[0].date()} → {last_date.date()} but a "
            f"{terms.maturity:g}Y note needs at least {req_years:g} calendar years "
            f"of realized prices after the first issue date. "
            f"Shorten the note maturity or check the underlyings' history."
        )

    # Natural bounds: issues valid from the start of history up to one full
    # (calendar) maturity window before the end of history.
    first_valid = prices.index[0]
    last_valid  = last_date - pd.DateOffset(months=mat_months)

    # Apply optional user-specified date range on top of natural bounds
    if bt_start is not None:
        first_valid = max(first_valid, bt_start)
    if bt_end is not None:
        last_valid  = min(last_valid, bt_end)

    if first_valid > last_valid:
        return pd.DataFrame(), {}

    # Monthly issue dates ("MS" = first of each month; each is snapped to the
    # next trading day via searchsorted below). Monthly sampling reduces the
    # overlap between consecutive issues vs a finer grid, so the summary
    # stats are a little less autocorrelated.
    sampled = pd.date_range(start=first_valid, end=last_valid, freq=issue_freq)

    # ── Resolve issue + observation dates to trading-day indices ───────────
    price_arr   = prices.values.astype(float)
    asset_names = list(prices.columns)
    n_assets    = len(asset_names)

    issue_idxs:  list[int]          = []
    issue_dates: list[pd.Timestamp] = []
    obs_idx_mat: list[np.ndarray]   = []
    for d in sampled:
        i0 = int(prices.index.searchsorted(d))      # next trading day >= d
        if i0 >= len(prices):
            continue
        anchor = prices.index[i0]
        # Calendar observation dates, snapped to the next trading day each.
        obs_dates = terms.obs_calendar_dates(anchor)
        obs_idx   = prices.index.searchsorted(obs_dates)
        if obs_idx[-1] >= len(prices):
            continue                                # maturity beyond history
        issue_idxs.append(i0)
        issue_dates.append(anchor)
        obs_idx_mat.append(np.asarray(obs_idx, dtype=int))

    if not issue_idxs:
        return pd.DataFrame(), {}

    n_issues = len(issue_idxs)

    # ── Build the compact performance array: one column per observation ────
    # perf[i, 0, k] = 1.0 (initial fixing); perf[i, j, k] = price of asset k
    # at the j-th snapped observation date of issue i, / S0.
    row_idx = np.column_stack([np.asarray(issue_idxs), np.vstack(obs_idx_mat)])  # (n_issues, n_obs+1)
    windows = price_arr[row_idx]                                                  # (n_issues, n_obs+1, n_assets)
    S0      = windows[:, 0:1, :]                                                  # (n_issues, 1, n_assets)
    perf    = windows / S0

    # ── Evaluate with the shared payoff engine ─────────────────────────────
    # With N = n_obs, terms.obs_steps(n_obs) == [1..n_obs]: every column after
    # the fixing is an observation, the last one is final valuation.
    res = price_note(perf, terms, seed=seed)

    perf_mat = perf[:, -1, :]                                     # (n_issues, n_assets)

    bt = pd.DataFrame({
        "Issue Date":       pd.to_datetime(issue_dates),
        "Call Quarter":     res["autocall_period"],
        "Principal":        res["principal_payoffs"],
        "Knock-in":         res["knock_in_triggered"],
        "Total Coupons":    res["coupon_payoffs"],
        "Payout":           res["nominal_payoffs"],
        "IRR":              res["annualized_returns"],
        "Worst Asset":      [asset_names[j] for j in perf_mat.argmin(axis=1)],
        "Worst Final Perf": perf_mat.min(axis=1),
    })
    for k, name in enumerate(asset_names):
        bt[f"{name} Perf"] = perf_mat[:, k]

    knock_in_mask = bt["Knock-in"]

    summary = {
        "n_issues":      len(bt),
        "mean_irr":      float(bt["IRR"].mean()),
        "median_irr":    float(bt["IRR"].median()),
        "prob_called":   float((bt["Call Quarter"] > 0).mean()),
        "prob_knock_in": float(knock_in_mask.mean()),
        "prob_maturity": float((bt["Call Quarter"] == 0).mean()),
    }

    return bt, summary


def snapped_obs_dates(
    prices: pd.DataFrame,
    terms:  NoteTerms,
    issue_date: pd.Timestamp,
) -> tuple[pd.Timestamp, list[pd.Timestamp]]:
    """
    Resolve (snapped issue date, snapped observation dates) for one issue date
    against a price index — the same calendar-first rule run_backtest uses.
    Observation dates beyond the available history are omitted.
    """
    i0 = int(prices.index.searchsorted(issue_date))
    if i0 >= len(prices):
        raise ValueError(f"Issue date {issue_date} is beyond the available history.")
    anchor   = prices.index[i0]
    obs_idx  = prices.index.searchsorted(terms.obs_calendar_dates(anchor))
    obs_idx  = [int(j) for j in obs_idx if j < len(prices)]
    return anchor, [prices.index[j] for j in obs_idx]
