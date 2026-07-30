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

from core.note import NoteTerms, price_note, replay_note, _basket


def hold_gap(terms: NoteTerms) -> tuple[int, float] | None:
    """How far into the note's life this position was bought — ``(observations already
    fixed, years)`` — or None for a note held from issue (or not held at all).

    Both are read off the note's OWN calendar so the backtest replicates the real
    position: if you bought 14 months into a 3y quarterly note, four observations had
    fixed and belonged to the seller, and your holding period starts 14 months in.
    Everything after that is what the historical windows should measure.

    Clamped to leave at least one observation to price — a settlement date past the
    final observation is a matured note, not a position.
    """
    if not (terms.settlement_date and terms.issue_date):
        return None
    issue  = pd.Timestamp(terms.issue_date)
    settle = pd.Timestamp(terms.settlement_date)
    if settle <= issue:
        return None                                  # held from issue: nothing elapsed
    obs_cal = [pd.Timestamp(d) for d in terms.obs_calendar_dates(issue)]
    k = min(sum(1 for d in obs_cal if d <= settle), terms.n_obs - 1)
    return k, max(0.0, (settle - issue).days / 365.0)


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
    #
    # For a POSITION bought after issue, replicate the same gap in every historical
    # window: price only the observations after the purchase point, carry in whatever
    # arrears that window had reached, and measure the holding period from the
    # purchase — not from issue. Without this the earlier coupons counted as the
    # buyer's and the on-cost IRR was annualised over the whole note life.
    gap = hold_gap(terms)
    skipped_called = 0
    if gap is None:
        res = price_note(perf, terms, seed=seed)
    else:
        k_off, gap_years = gap
        # A note that had already autocalled by the purchase date could not have been
        # bought at all, so those windows leave the sample. This is a real selection
        # effect — you can only buy a note that is still alive — but it biases what
        # remains toward the windows that did NOT call early, so the count is reported.
        elapsed_perf = perf[:, 1:k_off + 1, :]                    # (n_issues, k_off, n_assets)
        alive        = np.ones(n_issues, dtype=bool)
        pending      = np.zeros(n_issues, dtype=int)
        opening      = np.ones(n_issues, dtype=float)
        is_part      = getattr(terms, "note_type", "") == "participation"
        for i in range(n_issues):
            if is_part:
                if getattr(terms, "participation_periodic", False) and k_off:
                    opening[i] = float(_basket(elapsed_perf[i, -1:, :],
                                               terms.participation_basket)[0])
                continue
            rep = replay_note(elapsed_perf[i], terms) if k_off else None
            if rep and rep["autocall_period"]:
                alive[i] = False
            elif rep:
                pending[i] = int(rep["pending_coupons"])
        skipped_called = int((~alive).sum())
        if not alive.any():
            # Nothing to measure, but WHY matters — say it rather than showing an
            # empty backtest that looks like missing data.
            return pd.DataFrame(), {"n_issues": 0, "skipped_called": skipped_called,
                                    "purchase_gap_periods": k_off,
                                    "purchase_gap_years": float(gap_years)}

        # Remaining observation times, measured from the PURCHASE date.
        rem_times = [t - gap_years for t in terms.obs_times()[k_off:]]
        res = price_note(perf[alive], terms, seed=seed,
                         obs_steps=list(range(k_off + 1, n_obs + 1)),
                         obs_times=rem_times,
                         periods_elapsed=k_off,
                         pending_coupons=pending[alive],
                         start_basket=opening[alive])
        # Every row below is built from `res`, so the frame must be the same subset.
        perf         = perf[alive]
        issue_dates  = [d for d, a in zip(issue_dates, alive) if a]
        n_issues     = int(alive.sum())

    perf_mat = perf[:, -1, :]                                     # (n_issues, n_assets)
    k_off    = gap[0] if gap else 0

    # `res`'s per-period arrays are aligned to the PRICED window, so an autocall at
    # window index 1 is term-sheet period k_off+1. The frame reports the TERM SHEET's
    # numbering (0 still means "reached maturity"), which is what every display layer
    # and the eligibility check downstream assume.
    called_abs = np.where(res["autocall_period"] > 0,
                          res["autocall_period"] + k_off, 0)

    bt = pd.DataFrame({
        "Issue Date":       pd.to_datetime(issue_dates),
        "Call Quarter":     called_abs,
        "Principal":        res["principal_payoffs"],
        "Knock-in":         res["knock_in_triggered"],
        "Total Coupons":    res["coupon_payoffs"],
        "Payout":           res["nominal_payoffs"],
        "IRR":              res["annualized_returns"],
        "Worst Asset":      [asset_names[j] for j in perf_mat.argmin(axis=1)],
        "Worst Final Perf": perf_mat.min(axis=1),
    })
    for j, name in enumerate(asset_names):
        bt[f"{name} Perf"] = perf_mat[:, j]

    knock_in_mask = bt["Knock-in"]

    # Mirror the full Monte Carlo metric set so the backtest reports the SAME
    # measures (app + PDF). `res` already holds them, computed by the shared
    # price_note engine over exactly these historical issue windows — so e.g.
    # res["expected_irr"] == mean_irr by construction. loss_given_knock_in is
    # the mean IRR over real (unrescued) knock-in paths; NaN when there are none.
    summary = {
        "n_issues":      len(bt),
        "mean_irr":      float(bt["IRR"].mean()),
        "median_irr":    float(bt["IRR"].median()),
        "prob_called":   float((bt["Call Quarter"] > 0).mean()),
        "prob_knock_in": float(knock_in_mask.mean()),
        "prob_maturity": float((bt["Call Quarter"] == 0).mean()),
        # Same metrics as the Monte Carlo summary, over the historical windows.
        "expected_total_return": float(res["expected_total_return"]),
        "expected_coupon":       float(res["expected_coupon"]),
        "expected_nominal_payout": float(res["expected_nominal_payout"]),
        "loss_given_knock_in":   float(res["loss_given_knock_in"]),
        "prob_knock_in_total":   float(res["prob_knock_in_total"]),
        # Position measures — the IRR column above is already on cost, so a
        # secondary-market purchase price is reflected across every issue window.
        "cost_basis":            float(res["cost_basis"]),
        "prob_loss":             float(res["prob_loss"]),
        # ── The position the windows replicate ──────────────────────────────
        # `period_offset` is the same contract as the Monte Carlo's: every
        # per-period array above describes term-sheet period offset+i+1.
        "period_offset":          k_off,
        "purchase_gap_periods":   k_off,
        "purchase_gap_years":     float(gap[1]) if gap else 0.0,
        # Every historical window assumes the SAME entry price you actually paid —
        # no valuation model is applied, so the windows are comparable to each other
        # but 82% was not necessarily a fair price in each of them. Stated here so a
        # display layer can say so rather than implying the price was derived.
        "entry_price":            float(terms.purchase_price or 1.0),
        # Windows dropped because the note had already autocalled by the purchase
        # date — you could not have bought it. A real selection effect, and one that
        # biases the survivors toward the windows that did NOT call early.
        "skipped_called":         skipped_called,
        # Average time (years) to early redemption over the historical windows that
        # autocalled — None when none did. Same shared-engine measure as the MC run.
        "avg_time_to_autocall":  res["avg_time_to_autocall"],
        # Per-issue × per-period coupon matrix, row-aligned with `bt` (bt is built
        # from `res` in this same order). Powers the path explorer's "coupon paid at
        # period t" filter. Width is the PRICED window, so with a purchase gap it is
        # (n_issues, n_obs − period_offset) and column i is period offset+i+1.
        "coupon_amounts":        res["coupon_amounts"],
        # Per-issue worst-of trajectory at each observation column (incl. the t=0
        # fixing), in note-relative time. Row-aligned with `bt`. Powers the backtest
        # path explorer's overlaid worst-of fan.
        #
        # Deliberately the FULL life, even with a purchase gap — the pre-purchase
        # stretch is exactly the "what had already happened" context the explorer
        # wants, and `obs_times_rel` stays years-since-issue to match. So these two
        # are full-width while `coupon_amounts` is window-width; `period_offset` is
        # what reconciles them.
        "wof_obs":               perf.min(axis=2),                 # (n_issues, n_obs+1)
        "obs_times_rel":         [0.0] + list(terms.obs_times()),  # years since issue
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
