"""Tests for the historical backtest (core/backtest.py).

The focus is the POSITION: a note bought some way into its life must be measured
from the purchase, not from issue. Before this, every historical window was priced
as a full life while the cost basis was applied anyway — so coupons the seller had
already collected counted as the buyer's, and the on-cost IRR was annualised over
the whole tenor instead of the holding period.

Prices here are synthetic and deterministic (no network, no RNG): a flat series
where every window behaves identically and the arithmetic is hand-checkable, plus a
sinusoid where windows genuinely differ.
"""
import numpy as np
import pandas as pd
import pytest

from core.backtest import hold_gap, run_backtest
from core.note import NoteTerms


ISSUE = "2020-01-02"


def _terms(**over) -> NoteTerms:
    """A 1y quarterly autocall that never calls (barrier at 150%) and always pays its
    coupon (barrier at 70%), so a flat price series gives 4 coupons and par back."""
    d = {"name": "T", "note_type": "autocall", "maturity": 1.0,
         "payment_freq": "quarterly", "coupon_pa": 0.08, "coupon_barrier": 0.70,
         "autocall_barrier": 1.50, "autocall_start_period": 1, "knock_in_barrier": 0.50,
         "memory": False, "tickers": {"X": "Xco"}, "issue_date": ISSUE}
    d.update(over)
    return NoteTerms.from_dict(d)


def _flat(years: float = 4.0, level: float = 100.0) -> pd.DataFrame:
    idx = pd.bdate_range("2019-01-01", periods=int(252 * years))
    return pd.DataFrame({"Xco": np.full(len(idx), level)}, index=idx)


def _wave(years: float = 6.0) -> pd.DataFrame:
    """A 12-month sinusoid: a window opening at a trough rises into its first
    observation (and autocalls at 100%), one opening at a peak does not."""
    idx = pd.bdate_range("2019-01-01", periods=int(252 * years))
    t = np.arange(len(idx)) / 252.0
    return pd.DataFrame({"Xco": 100.0 + 18.0 * np.sin(2 * np.pi * t)}, index=idx)


# ── the gap itself ─────────────────────────────────────────────────────────────
def test_hold_gap_is_none_without_a_position():
    assert hold_gap(_terms()) is None
    assert hold_gap(_terms(settlement_date=None)) is None


def test_hold_gap_is_none_when_held_from_issue():
    """Settling on the issue date is a subscription — nothing has elapsed."""
    assert hold_gap(_terms(settlement_date=ISSUE)) is None


@pytest.mark.parametrize("settle,periods", [
    ("2020-02-01", 0),   # before the first quarterly observation
    ("2020-04-05", 1),   # just past observation 1 (2020-04-02)
    ("2020-08-01", 2),   # past observations 1 and 2
])
def test_hold_gap_counts_observations_already_fixed(settle, periods):
    k, years = hold_gap(_terms(settlement_date=settle))
    assert k == periods
    assert years == pytest.approx((pd.Timestamp(settle) - pd.Timestamp(ISSUE)).days / 365.0)


def test_hold_gap_refuses_a_settlement_past_the_final_observation():
    """Settling after the last observation is a MATURED note, not a position.

    This case previously asserted the old `min(k, n_obs - 1)` clamp, which capped
    the observation count but left `gap_years` past maturity — so the first
    remaining observation time came out NEGATIVE (1.000 - 1.414 = -0.414 years for
    this fixture) and every historical window annualised a real payoff over a
    negative holding period. The test was encoding the bug; refusing is correct,
    and the caller falls back to full-life windows.
    """
    assert hold_gap(_terms(settlement_date="2021-06-01")) is None


# ── a subscription is unchanged ────────────────────────────────────────────────
def test_full_life_windows_measure_the_whole_tenor():
    bt, s = run_backtest(_flat(), _terms(), seed=1)
    assert len(bt) > 0
    assert s["period_offset"] == 0
    assert s["purchase_gap_periods"] == 0
    assert s["skipped_called"] == 0
    assert s["coupon_amounts"].shape[1] == 4              # all four observations
    # Flat prices: every coupon pays, nothing calls, par back. 8% over one year.
    assert bt["Total Coupons"].unique() == pytest.approx([0.08])
    assert (bt["Call Quarter"] == 0).all()
    assert bt["IRR"].unique() == pytest.approx([0.08])


# ── a position bought after issue ──────────────────────────────────────────────
def test_purchase_gap_drops_the_seller_s_coupons_and_shortens_the_window():
    """Bought two quarters in: only the last two coupons are the buyer's, and the
    holding period is six months, not a year."""
    t = _terms(settlement_date="2020-08-01")             # k = 2
    bt, s = run_backtest(_flat(), t, seed=1)
    assert s["purchase_gap_periods"] == 2
    assert s["period_offset"] == 2
    assert s["coupon_amounts"].shape[1] == 2             # P3 and P4 only
    assert bt["Total Coupons"].unique() == pytest.approx([0.04])   # 2 × 2%, not 4 × 2%


def test_on_cost_irr_annualises_over_the_holding_period_only():
    """The defect this exists for. Bought at 90% two quarters in, the position pays
    1.04 on a cost of 0.90 over ~0.58y held — NOT over the full year. Annualising
    over the tenor understated the IRR by a factor of the gap."""
    t = _terms(settlement_date="2020-08-01", purchase_price=0.90)
    bt, s = run_backtest(_flat(), t, seed=1)
    _, gap_years = hold_gap(t)
    total = (1.04 - 0.90) / 0.90
    # obs_times are evenly spaced from issue, so the remaining life is 1.0 − gap.
    held = 1.0 - gap_years
    assert bt["IRR"].unique() == pytest.approx([total / held], rel=1e-6)
    # And the same note held from issue is a materially different number.
    bt0, _ = run_backtest(_flat(), _terms(purchase_price=0.90), seed=1)
    assert bt0["IRR"].unique() == pytest.approx([(1.08 - 0.90) / 0.90])
    assert bt["IRR"].iloc[0] > bt0["IRR"].iloc[0]


def test_entry_price_assumption_is_reported_not_derived():
    """No valuation model is applied — every window assumes the price actually paid,
    which the summary states so a display layer can caveat it."""
    t = _terms(settlement_date="2020-08-01", purchase_price=0.82,
               accrued_at_purchase=0.01)
    _, s = run_backtest(_flat(), t, seed=1)
    assert s["entry_price"] == pytest.approx(0.82)       # the CLEAN price paid
    assert s["cost_basis"] == pytest.approx(0.83)        # clean + accrued


def test_windows_that_called_before_the_purchase_are_dropped_and_counted():
    """You cannot buy a note that has already redeemed. Those windows leave the
    sample — a real selection effect, so the count is surfaced."""
    t = _terms(autocall_barrier=1.0, settlement_date="2020-08-01")   # k = 2
    all_bt, _ = run_backtest(_wave(), _terms(autocall_barrier=1.0), seed=1)
    bt, s = run_backtest(_wave(), t, seed=1)
    assert s["skipped_called"] > 0
    assert len(bt) + s["skipped_called"] == len(all_bt)
    # Whatever survives either reached maturity or called at P3/P4 — never earlier,
    # because a call at P1/P2 is exactly what got the window dropped.
    called = bt["Call Quarter"][bt["Call Quarter"] > 0]
    assert called.empty or called.min() >= 3


def test_call_quarter_reports_term_sheet_periods_not_window_indices():
    """price_note's per-period arrays are window-relative; the frame must not be, or
    a call at absolute P3 would read as P1 and fail the eligibility check."""
    t = _terms(autocall_barrier=1.0, autocall_start_period=1,
               settlement_date="2020-08-01")
    bt, s = run_backtest(_wave(), t, seed=1)
    called = bt["Call Quarter"][bt["Call Quarter"] > 0]
    assert not called.empty
    assert called.min() > s["period_offset"]             # shifted past the elapsed ones
    assert called.max() <= t.n_obs


def test_participation_position_prices_the_remaining_window():
    """The participation branch has no coupons, but the gap still shortens the window
    and re-anchors the holding period."""
    t = _terms(note_type="participation", participation_downside="full",
               participation_upside="linear", protection_level=0.90,
               participation_rate=1.0, participation_strike=1.0,
               purchase_price=0.95, settlement_date="2020-08-01")
    bt, s = run_backtest(_flat(), t, seed=1)
    assert s["purchase_gap_periods"] == 2
    _, gap_years = hold_gap(t)
    # Flat prices → basket ends at par → redeems par on a cost of 0.95.
    total = (1.0 - 0.95) / 0.95
    assert bt["IRR"].unique() == pytest.approx([total / (1.0 - gap_years)], rel=1e-6)


def test_per_window_arrears_are_carried_in_independently():
    """Memory arrears differ per historical window, so `pending_coupons` has to be
    per-path. A scalar would apply one window's arrears to all of them."""
    t = _terms(memory=True, coupon_barrier=0.95, autocall_barrier=1.50,
               settlement_date="2020-08-01")
    bt, s = run_backtest(_wave(), t, seed=1)
    assert len(bt) > 1
    # The wave puts different windows above/below a 95% coupon barrier at different
    # observations, so the released-coupon totals must NOT all be equal.
    assert bt["Total Coupons"].nunique() > 1
