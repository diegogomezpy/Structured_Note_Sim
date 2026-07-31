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

from core.note import NoteTerms, price_note, replay_note, _participation_redemption


def _autocall(**over) -> NoteTerms:
    d = {"name": "T", "note_type": "autocall", "maturity": 1.0, "payment_freq": "semi-annual",
         "coupon_pa": 0.10, "coupon_barrier": 0.7, "autocall_barrier": 1.0,
         "autocall_start_period": 1, "knock_in_barrier": 0.5, "memory": True,
         "tickers": {"^GSPC": "SPX"}}
    d.update(over)
    return NoteTerms.from_dict(d)


# ── NoteTerms: derived fields + round-trip ──────────────────────────────────────
def test_derived_fields():
    t = _autocall()                       # semi-annual over 1y → 2 observations
    assert t.n_obs == 2
    assert t.coupon_rate == pytest.approx(0.05)     # 10% p.a. / 2 periods


def test_from_dict_to_dict_roundtrip():
    for t in (_autocall(), _autocall(name="Ünïcode — note", coupon_pa=0.135)):
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
def test_price_note_autocall_golden():
    t = _autocall()
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
    t = _autocall()
    perf = np.ones((16, 5, 1))
    note = price_note(perf, t, obs_steps=[2, 4], obs_times=[0.5, 1.0])
    assert note["prob_autocall"] == 1.0
    assert note["prob_knock_in_total"] == 0.0
    assert note["expected_coupon"] == pytest.approx(0.05)


def test_price_note_zenith_upside_participation():
    # Zenith: an in-the-money redemption pays the worst-of upside on top of
    # par + coupon; below-par at maturity is unchanged (1:1 loss).
    t = _autocall(zenith=True)            # 2 obs, coupon 0.05/period, coupon barrier 0.7, KI 0.5
    perf = np.ones((3, 5, 1))
    perf[0, :, 0] = 1.20                                  # autocalls P1 at 1.20
    perf[1, 2, 0] = 0.80; perf[1, 4, 0] = 0.80           # maturity 0.80 (70%..100%): par + 2 coupons
    perf[2, 2, 0] = 0.80; perf[2, 4, 0] = 0.40           # maturity 0.40 (< KI): 1:1 loss + P1 coupon
    note = price_note(perf, t, obs_steps=[2, 4], obs_times=[0.5, 1.0])
    # 0: 1.20 + 0.05 · 1: 1.00 + 0.10 · 2: 0.40 + 0.05
    assert note["nominal_payoffs"] == pytest.approx([1.25, 1.10, 0.45])
    # Same paths, Zenith OFF: the autocall redeems at par (1.05), no upside.
    off = price_note(perf, replace(t, zenith=False), obs_steps=[2, 4], obs_times=[0.5, 1.0])
    assert off["nominal_payoffs"] == pytest.approx([1.05, 1.10, 0.45])


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


# ── secondary-market position: returns measured on cost, not par ────────────────
def test_cost_basis_defaults_to_par():
    t = _autocall()
    assert t.cost_basis == pytest.approx(1.0)
    assert t.is_secondary is False


@pytest.mark.parametrize("over,cost,secondary", [
    ({"purchase_price": 0.95},                              0.95,  True),
    ({"purchase_price": 0.95, "accrued_at_purchase": 0.02}, 0.97,  True),
    ({"settlement_date": "2025-06-01"},                     1.0,   True),   # at par, but bought later
    ({"purchase_price": 1.03},                              1.03,  True),   # bought at a premium
])
def test_cost_basis_and_is_secondary(over, cost, secondary):
    t = _autocall(**over)
    assert t.cost_basis == pytest.approx(cost)
    assert t.is_secondary is secondary


def test_purchase_price_rebases_returns():
    """Same payoffs, different cost: the paths are untouched and only the return
    denominator moves. Buying at 95 turns a par redemption into a +5.26% gain."""
    perf = np.ones((2, 5, 1))
    perf[1, :, 0] = 0.3                                   # crashes, knocked in
    kw = dict(obs_steps=[2, 4], obs_times=[0.5, 1.0])
    par = price_note(perf, _autocall(), **kw)
    sec = price_note(perf, _autocall(purchase_price=0.95), **kw)

    # The note itself is unchanged — same payoff, same call, same knock-in.
    assert sec["nominal_payoffs"] == pytest.approx(par["nominal_payoffs"])
    assert sec["prob_autocall"] == pytest.approx(par["prob_autocall"])
    assert sec["prob_knock_in_total"] == pytest.approx(par["prob_knock_in_total"])
    # Returns are on cost: (payoff − 0.95) / 0.95, annualised over the same t_held.
    assert sec["cost_basis"] == pytest.approx(0.95)
    assert sec["total_returns"] == pytest.approx([(1.05 - .95) / .95, (0.30 - .95) / .95])
    assert sec["annualized_returns"] == pytest.approx([(1.05 - .95) / .95 / 0.5,
                                                       (0.30 - .95) / .95 / 1.0])
    assert par["cost_basis"] == pytest.approx(1.0)
    assert par["total_returns"] == pytest.approx([0.05, -0.70])


def test_prob_loss_is_not_the_knock_in_rate():
    """P(loss) is about the POSITION, so a coupon can rescue a knocked-in path and a
    discount can rescue a below-par redemption — neither shows up in P(knock-in)."""
    t = _autocall(coupon_pa=0.60, coupon_barrier=0.0)      # 30%/period, always paid
    perf = np.ones((2, 5, 1))
    perf[0, :, 0] = 0.90                                  # matures at 0.90, no knock-in
    perf[1, 2, 0] = 0.90; perf[1, 4, 0] = 0.45            # knocks in, redeems at 0.45 + 0.60 coupons
    at_par = price_note(perf, t, obs_steps=[2, 4], obs_times=[0.5, 1.0])
    assert at_par["prob_knock_in_total"] == pytest.approx(0.5)
    assert at_par["prob_loss"] == pytest.approx(0.0)      # 1.05 and 1.60 — both above par

    # Bought at 1.20 (a premium): the same 1.05 path is now a loss on cost.
    rich = price_note(perf, replace(t, purchase_price=1.20), obs_steps=[2, 4], obs_times=[0.5, 1.0])
    assert rich["prob_knock_in_total"] == pytest.approx(0.5)   # unchanged — a note property
    assert rich["prob_loss"] == pytest.approx(0.5)


def test_participation_returns_on_cost():
    t = _part(purchase_price=0.90)
    perf = np.ones((2, 2, 1))
    perf[0, 1, 0] = 1.20                                  # redeems at 1.20
    perf[1, 1, 0] = 0.70                                  # full protection → par
    note = price_note(perf, t, obs_steps=[1], obs_times=[1.0])
    assert note["nominal_payoffs"] == pytest.approx([1.20, 1.00])
    assert note["cost_basis"] == pytest.approx(0.90)
    assert note["total_returns"] == pytest.approx([(1.2 - .9) / .9, (1.0 - .9) / .9])


def test_position_fields_roundtrip():
    t = _autocall(settlement_date="2025-06-01", purchase_price=0.955,
                 accrued_at_purchase=0.0125)
    again = NoteTerms.from_dict(json.loads(json.dumps(t.to_dict())))
    assert again.settlement_date == "2025-06-01"
    assert again.purchase_price == pytest.approx(0.955)
    assert again.accrued_at_purchase == pytest.approx(0.0125)
    assert again.cost_basis == pytest.approx(0.9675)


def test_zero_cost_basis_rejected():
    with pytest.raises(ValueError, match="purchase_price"):
        _autocall(purchase_price=0.0)


# ── held notes: pricing only the remaining window of a partially-elapsed note ────
def _held_kw(k, **over):
    """price_note args for the last `4 - k` observations of a 4-period note."""
    return {"obs_steps": list(range(k + 1, 5)),
            "obs_times": [(j + 1) / 4 for j in range(k, 4)],
            "periods_elapsed": k, **over}


def _q(**over) -> NoteTerms:
    """A 1y quarterly autocall — 4 observations, so a window is easy to reason about."""
    return _autocall(payment_freq="quarterly", coupon_pa=0.08, **over)


def test_held_window_prices_only_the_remaining_window():
    t = _q()
    perf = np.ones((1, 5, 1)) * 0.8              # flat at 80%: coupons pay, no autocall
    full = price_note(perf, t, obs_steps=[1, 2, 3, 4], obs_times=[.25, .5, .75, 1.0])
    tail = price_note(perf, t, **_held_kw(3))    # only P4 left
    assert full["coupon_amounts"].shape[1] == 4
    assert tail["coupon_amounts"].shape[1] == 1
    assert tail["periods_elapsed"] == 3
    # 4 coupons over the whole life vs the single one still to come.
    assert full["coupon_payoffs"] == pytest.approx([0.08])
    assert tail["coupon_payoffs"] == pytest.approx([0.02])


def test_held_window_counts_autocall_lockout_in_absolute_periods():
    """A note locked out until P3 is callable at EVERY remaining observation once
    the window opens at P3 — the lock-out is a term-sheet period, not an offset."""
    t = _q(autocall_start_period=3, autocall_barrier=1.0)
    perf = np.ones((1, 5, 1))                    # at the barrier throughout
    fresh = price_note(perf, t, obs_steps=[1, 2, 3, 4], obs_times=[.25, .5, .75, 1.0])
    assert fresh["autocall_period"] == pytest.approx([3])       # first callable period
    tail = price_note(perf, t, **_held_kw(2))              # window opens at P3
    assert tail["autocall_period"] == pytest.approx([1])        # = absolute P3
    # Opening at P1 of the window must NOT re-apply the lock-out from the window.
    assert tail["prob_autocall"] == 1.0


def test_held_window_carries_memory_arrears():
    """Arrears accrued before the window are released by the first coupon in it."""
    t = _q(memory=True, coupon_barrier=0.7)
    perf = np.ones((1, 5, 1)) * 0.8              # above the coupon barrier
    clean = price_note(perf, t, **_held_kw(2))
    owed2 = price_note(perf, t, **_held_kw(2, pending_coupons=2))
    # P3 pays 1 coupon clean, 3 with two quarters of arrears; P4 pays 1 either way.
    assert clean["coupon_amounts"][0].tolist() == pytest.approx([0.02, 0.02])
    assert owed2["coupon_amounts"][0].tolist() == pytest.approx([0.06, 0.02])


def test_held_window_growth_premium_accrues_from_issue():
    """coupon_at_autocall_only pays for every period SINCE ISSUE, so a held
    note called at its next observation still collects the full accrual."""
    t = _q(coupon_at_autocall_only=True, autocall_barrier=1.0)
    perf = np.ones((1, 5, 1))
    tail = price_note(perf, t, **_held_kw(2))   # calls at the window's P1 = absolute P3
    assert tail["autocall_period"] == pytest.approx([1])
    assert tail["coupon_payoffs"] == pytest.approx([0.06])      # 3 × 2%, not 1 × 2%


def test_held_window_uses_the_remaining_step_down_rungs():
    t = _q(autocall_barrier=1.0, autocall_step_down=0.05, autocall_start_period=1)
    perf = np.ones((1, 5, 1)) * 0.92             # below P1/P2 rungs, above P3's 0.90
    fresh = price_note(perf, t, obs_steps=[1, 2, 3, 4], obs_times=[.25, .5, .75, 1.0])
    assert fresh["autocall_period"] == pytest.approx([3])
    tail = price_note(perf, t, **_held_kw(2))   # window starts on the 0.90 rung
    assert tail["autocall_period"] == pytest.approx([1])


def test_held_window_rejects_a_matured_note():
    with pytest.raises(ValueError, match="already reached maturity"):
        price_note(np.ones((1, 5, 1)), _q(), **_held_kw(4))


# ── the position's return: settlement → redemption, on what was paid ─────────────
def test_realised_income_enters_the_return_but_not_the_payoff():
    """Coupons banked between settlement and today are the holder's money, but only
    the remaining life is simulated — so they have to be added back. Without this the
    reported 'return on cost' silently drops income the holder actually received."""
    t = _q()
    perf = np.ones((1, 5, 1)) * 0.8                      # coupons pay, never calls
    bare = price_note(perf, t, **_held_kw(2))
    with_income = price_note(perf, t, **_held_kw(2, realised_income=0.04))
    # The PAYOFF is untouched — realised income is not a future cash flow.
    assert with_income["nominal_payoffs"] == pytest.approx(bare["nominal_payoffs"])
    assert with_income["coupon_payoffs"] == pytest.approx(bare["coupon_payoffs"])
    # The RETURN moves by exactly the banked income, divided by the cost basis.
    assert (with_income["total_returns"] - bare["total_returns"]) == pytest.approx([0.04])
    assert with_income["realised_income"] == pytest.approx(0.04)


def test_realised_income_is_measured_on_cost_not_on_par():
    """The banked income divides by what was PAID, like every other return here."""
    t = _q(purchase_price=0.80)                          # cost basis 0.80
    perf = np.ones((1, 5, 1)) * 0.8
    bare = price_note(perf, t, **_held_kw(2))
    banked = price_note(perf, t, **_held_kw(2, realised_income=0.04))
    assert (banked["total_returns"] - bare["total_returns"]) == pytest.approx([0.04 / 0.80])


def test_elapsed_years_annualises_over_the_whole_holding_period():
    """A forward-only denominator overstates the annualised figure: 6 months left of a
    position held 18 months is a 2-year investment, not a 6-month one.

    `obs_times` here are measured from TODAY, which is what a held run passes (the
    engine builds them off a grid that starts at the anchor, see _snap_obs). The
    _held_kw helper above keeps them anchored at issue instead, so it is deliberately
    not used — the two anchors are the easy thing to conflate."""
    t = _q()
    perf = np.ones((1, 5, 1)) * 0.8
    win = {"obs_steps": [3, 4], "obs_times": [0.25, 0.5], "periods_elapsed": 2}
    fwd = price_note(perf, t, **win)                              # 0.5y still to run
    held = price_note(perf, t, **win, elapsed_years=1.5)          # + 1.5y already held
    # Same total return, spread over 4× the time (0.5y → 2.0y) → a quarter of the IRR.
    assert held["total_returns"] == pytest.approx(fwd["total_returns"])
    assert held["annualized_returns"] == pytest.approx(fwd["annualized_returns"] / 4.0)
    assert held["elapsed_years"] == pytest.approx(1.5)


def test_position_args_default_to_a_no_op():
    """Every note priced from issue must be byte-identical to before these existed."""
    t = _q()
    perf = np.ones((1, 5, 1)) * 0.9
    kw = {"obs_steps": [1, 2, 3, 4], "obs_times": [.25, .5, .75, 1.0]}
    plain = price_note(perf, t, **kw)
    zeroed = price_note(perf, t, realised_income=0.0, elapsed_years=0.0, **kw)
    assert zeroed["total_returns"] == pytest.approx(plain["total_returns"])
    assert zeroed["annualized_returns"] == pytest.approx(plain["annualized_returns"])


def test_participation_position_return_includes_banked_income():
    """The participation branch runs through the same _position_returns, so a held
    participation note must pick both anchors up too (its own payoff has no coupons —
    a cliquet's locked-in per-period income is what `realised_income` carries)."""
    t = _autocall(note_type="participation", participation_downside="full",
                  participation_upside="linear", protection_level=0.9,
                  participation_rate=1.0, participation_strike=1.0)
    perf = np.ones((1, 3, 1)) * 1.10
    kw = {"obs_steps": [1, 2], "obs_times": [0.5, 1.0]}
    bare = price_note(perf, t, **kw)
    held = price_note(perf, t, realised_income=0.05, elapsed_years=1.0, **kw)
    assert held["nominal_payoffs"] == pytest.approx(bare["nominal_payoffs"])
    assert (held["total_returns"] - bare["total_returns"]) == pytest.approx([0.05])
    assert held["annualized_returns"] == pytest.approx(
        held["total_returns"] / 2.0)                      # 1y remaining + 1y held


def test_replay_note_window_uses_absolute_periods():
    t = _q(autocall_start_period=3, autocall_barrier=1.0, memory=True, coupon_barrier=0.7)
    perf_obs = np.ones((2, 1)) * 0.8             # two observations, coupon-paying
    r = replay_note(perf_obs, t, start_period=3, pending=1)
    assert [row["period"] for row in r["rows"]] == [3, 4]
    assert r["rows"][0]["coupon_amount"] == pytest.approx(0.04)   # 1 arrear + 1 current
    assert r["autocall_period"] == 0                              # 80% never hits 100%


# ── participation: the protection floor ──────────────────────────────────────

def _prot_note(prot, downside="full", strike=1.0, rate=1.0, cap=0.30):
    from core.note import NoteTerms
    return NoteTerms.from_dict({
        "name": "P", "maturity": 3.0, "payment_freq": "annual", "coupon_pa": 0.0,
        "coupon_barrier": 0.0, "autocall_barrier": 0.0, "autocall_start_period": 1,
        "knock_in_barrier": 0.0, "memory": False, "coupon_basket": "worst_of",
        "autocall_basket": "worst_of", "note_type": "participation",
        "participation_downside": downside, "participation_upside": "linear",
        "participation_rate": rate, "participation_strike": strike,
        "protection_level": prot, "upside_cap": cap, "tickers": {"A": "A"},
    })


def test_full_protection_is_a_floor_not_a_flat_payout():
    """"Protected at 90%" means never LESS than 90% — not always exactly 90%.

    The redemption used to be a flat `protection_level` for every basket level
    below the strike, so a basket that finished at 95% paid 90% and the holder
    lost 5 points they had actually earned.
    """
    import numpy as np
    from core.note import _participation_redemption
    t = _prot_note(0.90)
    B = np.array([0.70, 0.85, 0.90, 0.95, 0.99])
    R = _participation_redemption(B, t)
    assert list(np.round(R, 6)) == [0.90, 0.90, 0.90, 0.95, 0.99]


def test_the_protection_floor_has_no_step_at_the_strike():
    """The defect the flat floor produced: a 10-point jump between a basket at
    99.9% and one at 100%. A term sheet describes no such cliff."""
    import numpy as np
    from core.note import _participation_redemption
    t = _prot_note(0.90)
    just_under, at_strike = _participation_redemption(np.array([0.9999, 1.0]), t)
    assert abs(at_strike - just_under) < 1e-3, (
        f"discontinuity at the strike: {just_under:.4f} -> {at_strike:.4f}")


def test_full_capital_protection_is_unchanged():
    """prot >= 1 is the common case and must price exactly as it always did:
    flat par below the strike."""
    import numpy as np
    from core.note import _participation_redemption
    R = _participation_redemption(np.array([0.4, 0.7, 0.95, 1.0]), _prot_note(1.0))
    assert list(np.round(R, 6)) == [1.0, 1.0, 1.0, 1.0]


def test_buffer_and_airbag_are_untouched_by_the_floor_fix():
    """They have their own shapes; only `full` changed."""
    import numpy as np
    from core.note import _participation_redemption
    B = np.array([0.95, 0.85])
    buf = _participation_redemption(B, _prot_note(0.90, downside="buffer"))
    air = _participation_redemption(B, _prot_note(0.90, downside="airbag"))
    assert list(np.round(buf, 6)) == [1.0, 0.95]          # par in the buffer, then 1:1
    assert list(np.round(air, 6)) == [1.0, round(0.85 / 0.90, 6)]   # geared below


def test_the_floor_does_not_become_an_uncapped_upside_above_a_high_strike():
    """A strike ABOVE par puts the band [par, strike) in the DOWNSIDE branch. The
    floor `max(B, prot)` paid that gain 1:1 there — ignoring participation_rate and
    upside_cap entirely — and then dropped back to par AT the strike, a cliff
    exactly where the note is supposed to start participating.

    Mutation-verified: drop the `min(..., 1.0)` and the 1.09 assertion goes to
    1.0899… and the continuity assertion to a 9-point step."""
    import numpy as np
    from core.note import _participation_redemption
    t = _prot_note(0.90, strike=1.10, rate=2.0)
    # Below the strike but above par: par, not the basket's gain.
    assert _participation_redemption(np.array([1.05, 1.09]), t).tolist() == [1.0, 1.0]
    # ...and no step at the strike itself.
    under, at = _participation_redemption(np.array([1.0999, 1.10]), t)
    assert abs(at - under) < 1e-3, f"cliff at the strike: {under:.4f} -> {at:.4f}"
    # The floor still floors, and the rate still applies above the strike.
    assert _participation_redemption(np.array([0.70]), t).tolist() == [0.90]
    assert _participation_redemption(np.array([1.20]), t)[0] == pytest.approx(1.20)


def test_breakeven_reports_the_lower_loss_region_not_the_grid_bound():
    """A shark fin whose knock-out rebate sits BELOW par loses money in two
    disjoint regions — deep down, and again above the knock-out. Taking the last
    losing grid point reported the top of the scan (300%) as "redeems below par
    below X", on a note that is back at par by 80%."""
    from core.note import NoteTerms, _participation_breakeven
    t = NoteTerms.from_dict({
        "name": "SF", "maturity": 2.0, "payment_freq": "annual", "coupon_pa": 0.0,
        "coupon_barrier": 0.0, "autocall_barrier": 0.0, "autocall_start_period": 1,
        "knock_in_barrier": 0.0, "memory": False, "coupon_basket": "worst_of",
        "autocall_basket": "worst_of", "note_type": "participation",
        "participation_downside": "buffer", "participation_upside": "shark_fin",
        "participation_rate": 1.0, "participation_strike": 1.0,
        "protection_level": 0.80, "knockout_level": 1.40, "knockout_payout": 0.95,
        "tickers": {"A": "A"},
    })
    be = _participation_breakeven(t)
    assert be is not None and 0.79 <= be <= 0.81, (
        f"breakeven {be} — the loss region above the knock-out leaked into it")


# ── One Star overlays ─────────────────────────────────────────────────────────
def _one_star(level=1.0, coupon=False, autocall=False):
    """Two underlyings, a 100% One Star level, and barriers the WORST-OF cannot
    clear on its own — so anything that pays here came from the overlay."""
    from core.note import NoteTerms
    return NoteTerms.from_dict({
        "name": "OS", "maturity": 1.0, "payment_freq": "annual", "coupon_pa": 0.10,
        "coupon_barrier": 0.90, "autocall_barrier": 0.95, "autocall_start_period": 1,
        "knock_in_barrier": 0.80, "memory": False, "coupon_basket": "worst_of",
        "autocall_basket": "worst_of", "note_type": "autocall",
        "one_star_level": level, "one_star_coupon": coupon, "one_star_autocall": autocall,
        "tickers": {"A": "A", "B": "B"},
    })


def _split_path():
    """One asset at 130%, the other at 60%: the worst-of misses every barrier and
    breaches the knock-in, while the best-of clears the One Star level."""
    import numpy as np
    return np.array([[[1.0, 1.0], [1.30, 0.60]]])       # (1 path, 2 steps, 2 assets)


def test_one_star_rescues_final_redemption_by_default():
    """The safe default (both flags off): the overlay applies to the FINAL
    REDEMPTION only. A worst-of at 60% is through a knock-in at 80%, and capital
    still comes back at par because one underlying finished at/above 100%."""
    from core.note import price_note
    r = price_note(_split_path(), _one_star(), seed=1, obs_steps=[1], obs_times=[1.0])
    # `knock_in_triggered` means "breached AND NOT rescued", so a working rescue
    # makes it FALSE. The breach itself is `prob_barrier_event`; the two together
    # are what says the overlay fired rather than the barrier never being hit.
    assert r["prob_barrier_event"] == pytest.approx(1.0), "the worst-of must have breached"
    assert r["prob_rescued"] == pytest.approx(1.0), "One Star must have rescued it"
    assert not bool(r["knock_in_triggered"][0]), "a rescued path is not a knock-in"
    assert r["principal_payoffs"][0] == pytest.approx(1.0), "capital back at par"
    # ...and it did NOT reach into the periodic checks.
    assert r["coupon_payoffs"][0] == pytest.approx(0.0), "coupon overlay is off by default"
    assert int(r["autocall_period"][0]) == 0, "autocall overlay is off by default"


def test_one_star_coupon_flag_pays_a_coupon_the_worst_of_missed():
    """`one_star_coupon` extends the same best-of overlay to the coupon check."""
    from core.note import price_note
    r = price_note(_split_path(), _one_star(coupon=True), seed=1,
                   obs_steps=[1], obs_times=[1.0])
    assert r["coupon_payoffs"][0] > 0.0, "a single underlying at 130% must pay"
    assert int(r["autocall_period"][0]) == 0, "the autocall flag was NOT set"


def test_one_star_autocall_flag_calls_a_note_the_worst_of_could_not():
    """`one_star_autocall` forces the call deterministically, regardless of the
    worst-of and of the RNG (the trigger is hard by default)."""
    from core.note import price_note
    r = price_note(_split_path(), _one_star(autocall=True), seed=1,
                   obs_steps=[1], obs_times=[1.0])
    assert int(r["autocall_period"][0]) == 1, "one underlying >= 100% must call it"


def test_one_star_level_none_disables_the_overlay_whatever_the_flags():
    """`one_star_level = None` is a plain worst-of note. The flags must not be
    able to resurrect an overlay that has no level to test against."""
    from core.note import price_note
    r = price_note(_split_path(), _one_star(level=None, coupon=True, autocall=True),
                   seed=1, obs_steps=[1], obs_times=[1.0])
    assert int(r["autocall_period"][0]) == 0
    assert r["coupon_payoffs"][0] == pytest.approx(0.0)
    assert r["principal_payoffs"][0] < 1.0, "no rescue: capital follows the worst-of"


# ── schedule consistency ──────────────────────────────────────────────────────
@pytest.mark.parametrize("maturity,freq,drift", [
    (1.5, "quarterly", 0.00),   # 6 whole quarters — fits
    (2.0, "quarterly", 0.00),
    (1.0, "annual",    0.00),
    (1.3, "quarterly", 0.05),   # n_obs rounds to 5 => 15 months, not 15.6
    (0.9, "quarterly", 0.10),   # n_obs rounds to 4 => 12 months, not 10.8
])
def test_schedule_drift_reports_a_tenor_that_does_not_fit_whole_periods(maturity, freq, drift):
    """`n_obs` ROUNDS maturity x periods-per-year while the calendar steps in whole
    months, so a tenor that is not a whole number of periods gives two different
    schedules — and the app prices on BOTH: the Monte Carlo on `obs_times` (evenly
    spaced over the stated maturity), the backtest and live tab on the calendar.

    A 0.9-year quarterly note is priced to 0.900y in one and 1.000y in the other.
    That is a different note, and nothing said so. The property makes it visible;
    the run summary carries it as a warning."""
    from core.note import NoteTerms
    t = NoteTerms.from_dict({
        "name": "S", "maturity": maturity, "payment_freq": freq, "coupon_pa": 0.10,
        "coupon_barrier": 0.70, "autocall_barrier": 1.0, "autocall_start_period": 1,
        "knock_in_barrier": 0.50, "tickers": {"A": "A"}})
    assert t.schedule_drift_years == pytest.approx(drift, abs=5e-3)
