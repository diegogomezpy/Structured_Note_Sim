"""Golden-value tests for the payoff core (core/note.py).

`price_note` is the SOLE payoff evaluator for both Monte Carlo and the backtest, so
these lock its behaviour on hand-built deterministic paths (no simulation, no
network) — any future payoff edit that changes a known outcome trips a test. Also
covers NoteTerms.from_dict migrations and the participation redemption formulas
(the Python side of the TS mirror in web/src/lib/participation.ts)."""
import json
from dataclasses import replace

import numpy as np
import pytest

from core.note import NoteTerms, price_note, _participation_redemption


def _phoenix(**over) -> NoteTerms:
    d = {"name": "T", "note_type": "phoenix", "maturity": 1.0, "payment_freq": "semi-annual",
         "coupon_pa": 0.10, "coupon_barrier": 0.7, "autocall_barrier": 1.0,
         "autocall_start_period": 1, "knock_in_barrier": 0.5, "memory": True,
         "tickers": {"^GSPC": "SPX"}}
    d.update(over)
    return NoteTerms.from_dict(d)


# ── NoteTerms: derived fields + round-trip ──────────────────────────────────────
def test_derived_fields():
    t = _phoenix()                       # semi-annual over 1y → 2 observations
    assert t.n_obs == 2
    assert t.coupon_rate == pytest.approx(0.05)     # 10% p.a. / 2 periods


def test_from_dict_to_dict_roundtrip():
    for t in (_phoenix(), _phoenix(name="Ünïcode — note", coupon_pa=0.135)):
        again = NoteTerms.from_dict(json.loads(json.dumps(t.to_dict())))
        assert again.name == t.name
        assert again.coupon_pa == pytest.approx(t.coupon_pa)
        assert again.n_obs == t.n_obs
        assert again.knock_in_barrier == pytest.approx(t.knock_in_barrier)


# ── legacy-config migrations (must keep loading old JSON) ────────────────────────
def test_legacy_capital_guarantee_becomes_participation():
    t = NoteTerms.from_dict({"name": "CP", "maturity": 1, "payment_freq": "annual",
                             "coupon_pa": 0, "coupon_barrier": 0, "autocall_barrier": 1,
                             "autocall_start_period": 1, "knock_in_barrier": 0,
                             "capital_guarantee": 0.9, "tickers": {"^GSPC": "x"}})
    assert t.note_type == "participation"
    assert t.protection_level == pytest.approx(0.9)


def test_legacy_knockout_rebate_becomes_payout():
    t = NoteTerms.from_dict({"name": "KO", "maturity": 1, "payment_freq": "annual",
                             "coupon_pa": 0, "coupon_barrier": 0, "autocall_barrier": 1,
                             "autocall_start_period": 1, "knock_in_barrier": 0,
                             "tickers": {"^GSPC": "x"}, "participation_upside": "shark_fin",
                             "knockout_level": 1.3, "knockout_rebate": 0.05})
    assert t.knockout_payout == pytest.approx(1.05)     # 1 + rebate


# ── price_note golden values (deterministic hand-built paths) ────────────────────
def test_price_note_phoenix_golden():
    t = _phoenix()
    # 2 paths, 1 asset, 5 time steps; observations at steps 2 and 4.
    perf = np.ones((2, 5, 1))
    perf[1, :, 0] = 0.3                  # path 1 crashes and stays below every barrier
    note = price_note(perf, t, obs_steps=[2, 4], obs_times=[0.5, 1.0])

    # Path 0 (flat at par): autocalls at P1 with one coupon → 1 + 0.05.
    # Path 1 (flat at 0.30): never autocalls, knocked in, capital returned at 0.30.
    assert note["nominal_payoffs"] == pytest.approx([1.05, 0.30])
    assert note["prob_autocall"] == pytest.approx(0.5)
    assert note["prob_knock_in_total"] == pytest.approx(0.5)
    assert note["prob_maturity"] == pytest.approx(0.5)
    assert note["expected_coupon"] == pytest.approx(0.025)          # mean(0.05, 0)
    assert note["expected_nominal_payout"] == pytest.approx(0.675)  # mean(1.05, 0.30)
    assert [round(float(x), 3) for x in note["prob_autocall_by_period"]] == [0.5, 0.0]


def test_price_note_all_autocall_hard_trigger():
    # Hard trigger (call_steepness None): worst-of exactly at the barrier autocalls
    # with probability exactly 1.0 regardless of seed.
    t = _phoenix()
    perf = np.ones((16, 5, 1))
    note = price_note(perf, t, obs_steps=[2, 4], obs_times=[0.5, 1.0])
    assert note["prob_autocall"] == 1.0
    assert note["prob_knock_in_total"] == 0.0
    assert note["expected_coupon"] == pytest.approx(0.05)


# ── participation redemption formulas (Python side of the TS mirror) ─────────────
def _part(**over) -> NoteTerms:
    d = {"name": "P", "note_type": "participation", "maturity": 1, "payment_freq": "annual",
         "coupon_pa": 0, "coupon_barrier": 0, "autocall_barrier": 2, "autocall_start_period": 99,
         "knock_in_barrier": 0, "tickers": {"^GSPC": "x"},
         "participation_strike": 1.0, "participation_rate": 1.0}
    d.update(over)
    return NoteTerms.from_dict(d)


@pytest.mark.parametrize("dn,up,extra,expect", [
    ("full",   "linear",  {},                       [1.2, 1.0, 1.0]),
    ("buffer", "linear",  {"protection_level": 0.8}, [1.2, 1.0, 0.8]),
    ("airbag", "linear",  {"protection_level": 0.6}, [1.2, 1.0, 1.0]),
    ("full",   "digital", {"digital_payout": 0.1},   [1.1, 1.0, 1.0]),
    ("bear",   "linear",  {"protection_level": 1.0}, [1.0, 1.1, 1.4]),
])
def test_participation_redemption_styles(dn, up, extra, expect):
    t = _part(participation_downside=dn, participation_upside=up, **extra)
    r = _participation_redemption(np.array([1.2, 0.9, 0.6]), t)
    assert r.tolist() == pytest.approx(expect)


def test_participation_shark_fin_null_payout_no_crash():
    """A shark-fin config that omits knockout_payout must fall back to par (matching
    the null-safe TS mirror `?? 1`), not crash on float(None)."""
    t = _part(participation_upside="shark_fin", knockout_level=1.3)
    object.__setattr__(t, "knockout_payout", None)          # simulate a null config
    r = _participation_redemption(np.array([0.9, 1.1, 1.4]), t)
    assert r[2] == pytest.approx(1.0)                        # above KO → par, no crash
