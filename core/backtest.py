"""
core/backtest.py
----------------
Historical backtest: replay the note on every valid issue date using
actual realized index prices (no simulation).

Each historical issue date is treated as ONE 'path': a (n_issues, N+1,
n_assets) performance array is built from realized prices and evaluated by
the SAME vectorized payoff engine (core.note.price_note) used for the Monte
Carlo. There is deliberately no second implementation of the payoff here —
keeping a single engine means term-sheet fixes (memory coupons, hard
trigger, best-of final-redemption rescue, ...) apply to simulation and
backtest identically and cannot drift apart.

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
    maturity_days = round(terms.maturity * 252)

    # Need maturity_days + 1 rows: at least one issue date with a full
    # maturity window of realized prices after it. (No history is required
    # BEFORE an issue date — replaying a note only needs data from issue
    # to maturity, so issues are valid from the first day of aligned history.)
    if len(prices) < maturity_days + 1:
        raise ValueError(
            f"Price history too short for backtest: {len(prices)} trading days available "
            f"but at least {maturity_days + 1} required "
            f"(one full {maturity_days}-day maturity window after the first issue date). "
            f"Shorten the note maturity or check the underlyings' history."
        )

    # Natural bounds: issues valid from the start of history up to one full
    # maturity window before the end of history.
    first_valid = prices.index[0]
    last_valid  = prices.index[-maturity_days]

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

    # ── Resolve issue dates to trading-day indices ─────────────────────────
    price_arr   = prices.values.astype(float)
    asset_names = list(prices.columns)
    n_assets    = len(asset_names)

    issue_idxs:  list[int]          = []
    issue_dates: list[pd.Timestamp] = []
    for d in sampled:
        idx = prices.index.searchsorted(d)
        if idx >= len(prices) - maturity_days:
            continue
        issue_idxs.append(int(idx))
        issue_dates.append(prices.index[idx])

    if not issue_idxs:
        return pd.DataFrame(), {}

    n_issues = len(issue_idxs)

    # ── Build the performance array: each issue date is one 'path' ────────
    # perf[i, t, k] = price of asset k, t trading days after issue i, / S0.
    # Window slicing via broadcast indexing: (n_issues, N+1) row indices.
    offsets  = np.arange(maturity_days + 1)                       # (N+1,)
    row_idx  = np.asarray(issue_idxs)[:, None] + offsets[None, :] # (n_issues, N+1)
    windows  = price_arr[row_idx]                                 # (n_issues, N+1, n_assets)
    S0       = windows[:, 0:1, :]                                 # (n_issues, 1, n_assets)
    perf     = windows / S0

    # ── Evaluate with the shared payoff engine ─────────────────────────────
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
        "prob_floor":    float(knock_in_mask.mean()),
        "prob_called":   float((bt["Call Quarter"] > 0).mean()),
        "prob_knock_in": float(knock_in_mask.mean()),
        "prob_maturity": float((bt["Call Quarter"] == 0).mean()),
        **{f"prob_q{i}": float((bt["Call Quarter"] == i).mean())
           for i in range(1, min(4, terms.n_obs + 1))},
    }

    return bt, summary