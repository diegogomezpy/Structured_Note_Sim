"""
tests/test_position_state.py
----------------------------
`api/engine.py:_position_state` decides whether a held note gets the
remaining-life treatment at all. It can REFUSE for four reasons — the issue date
is in the future, price history doesn't reach the fixing, the note has matured,
or it already autocalled on realised prices — and a refusal silently falls the
whole run back to pricing from issue.

None of the four had a test. That matters more than an ordinary coverage gap:
the refusals are the branch where the app quietly prices something OTHER than
what the user asked for, and the report used to assert the held treatment on
`terms.is_held` alone, so a refusal printed a position band over a from-issue
run. That reader is told nothing.

Every test here monkeypatches `_prices` with a synthetic frame — the real one
goes to Yahoo, and a refusal test that depends on the network tests the network.

A module-level importorskip is right in this file (unlike tests/test_simulator.py,
where it would have taken the numpy tests with it): every test here is about
api.engine, so there is nothing left to run without it.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("plotly", reason="plotly not installed — API stack absent")

import api.engine as engine            # noqa: E402
from core.note import NoteTerms        # noqa: E402

ANCHOR = pd.Timestamp("2026-07-01")


def _terms(**over) -> NoteTerms:
    d = {"name": "P", "maturity": 2.0, "payment_freq": "quarterly", "coupon_pa": 0.10,
         "coupon_barrier": 0.70, "autocall_barrier": 1.00, "autocall_start_period": 1,
         "knock_in_barrier": 0.50, "memory": True, "coupon_basket": "worst_of",
         "autocall_basket": "worst_of", "note_type": "autocall",
         "tickers": {"AAA": "Alpha"},
         "issue_date": "2025-07-01", "settlement_date": "2025-10-01"}
    d.update(over)
    return NoteTerms.from_dict(d)


def _frame(start="2024-01-01", end="2026-07-01", level=100.0, drift=-0.0002) -> pd.DataFrame:
    """One asset on business days. `drift` is a per-day multiplier on the level, so
    a test can walk the price above or below a barrier deliberately.

    The default drifts gently DOWN: a perfectly flat series sits exactly at a 100%
    autocall barrier (perf == 1.0 meets `>=`), so "flat" is a called note, not a
    live one."""
    idx = pd.bdate_range(start, end)
    return pd.DataFrame({"Alpha": level * (1.0 + drift) ** np.arange(len(idx))}, index=idx)


@pytest.fixture
def prices(monkeypatch):
    """Install a synthetic price frame; the test can swap it per case."""
    box = {"df": _frame()}
    monkeypatch.setattr(engine, "_prices", lambda *a, **k: box["df"])
    return box


def _reason(terms, anchor=ANCHOR):
    return (engine._position_state(terms, anchor) or {}).get("reason")


# ── the happy path, so the refusals below are refusals and not "always None" ──
def test_a_live_position_resolves(prices):
    """Held for three quarters of a two-year note: four of eight observations have
    fixed, so the window is the remaining four."""
    st = engine._position_state(_terms(), ANCHOR)
    assert st is not None and st.get("ok") is not False, st
    assert st["periods_elapsed"] == 4, st["periods_elapsed"]
    assert st["elapsed_years"] > 0.0


def test_a_note_with_no_settlement_is_not_a_position(prices):
    """No settlement date => not held => None, and the run prices from issue with
    no reason to report. Distinct from a refusal, which HAS a reason."""
    assert engine._position_state(_terms(settlement_date=None), ANCHOR) is None


# ── the four refusals ────────────────────────────────────────────────────────
def test_refuses_a_note_issued_in_the_future(prices):
    """You cannot hold what has not been issued. Priced from issue instead."""
    assert _reason(_terms(issue_date="2027-01-01", settlement_date="2027-01-01")) == "not_issued"


def test_refuses_when_history_does_not_reach_the_fixing(prices):
    """The whole remaining-life treatment rests on the ORIGINAL fixing — barriers
    are fractions of it. Without it there is nothing to measure against, so the
    run must fall back rather than invent a level."""
    prices["df"] = _frame(start="2026-01-01")          # begins 6 months after issue
    assert _reason(_terms()) == "no_fixing"


def test_refuses_a_matured_note(prices):
    """Every observation has fixed: there is no remaining life to model.

    History has to start before the issue date, or this trips `no_fixing` first
    and proves nothing — the order of the guards is itself part of the contract."""
    prices["df"] = _frame(start="2022-06-01")
    assert _reason(_terms(issue_date="2022-07-01", settlement_date="2022-07-01")) == "matured"


def test_refuses_a_note_that_already_autocalled(prices):
    """Realised prices called it away, so the position no longer exists. This is
    the only refusal that depends on the PRICES rather than the dates — it replays
    the elapsed observations through the real payoff engine."""
    # Rising 0.05%/day clears the 100% autocall barrier well before the first
    # observation, so replay_note reports a call.
    prices["df"] = _frame(drift=0.0005)
    assert _reason(_terms()) == "called"


def test_a_flat_note_below_the_barrier_is_not_called(prices):
    """The mirror of the test above — proof that `called` tracks the prices and is
    not just what this fixture always returns."""
    prices["df"] = _frame(drift=-0.0005)               # drifts down, never calls
    st = engine._position_state(_terms(), ANCHOR)
    assert st.get("ok") is not False, st
