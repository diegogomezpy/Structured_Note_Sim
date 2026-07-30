"""Tests for the A/B comparison statistics (core/compare.py).

These lock the arithmetic that makes a comparison *paired*: index i is the same
simulated world for both notes, so the per-path difference is a real quantity
and its standard error is far tighter than either side's own. Everything here
runs on hand-built payoff dicts — no simulation, no network."""
import numpy as np
import pytest

from core.compare import outcome_buckets, paired_stats, share_blockers, compare_diff
from core.note import NoteTerms


def _terms(**over) -> NoteTerms:
    d = {"name": "T", "note_type": "autocall", "maturity": 1.0, "payment_freq": "quarterly",
         "coupon_pa": 0.10, "coupon_barrier": 0.7, "autocall_barrier": 1.0,
         "autocall_start_period": 1, "knock_in_barrier": 0.5,
         "tickers": {"^GSPC": "SPX"}}
    d.update(over)
    return NoteTerms.from_dict(d)


def _note(total, *, called=None, ki=None, payoff=None):
    """A minimal price_note-shaped dict — only the keys the paired stats read."""
    total = np.asarray(total, dtype=float)
    n = total.size
    return {
        "total_returns": total,
        "annualized_returns": total,                       # 1y note → IRR == total
        "nominal_payoffs": np.asarray(payoff if payoff is not None else 1.0 + total, dtype=float),
        "autocall_period": np.asarray(called if called is not None else [0] * n, dtype=int),
        "knock_in_triggered": np.asarray(ki if ki is not None else [False] * n, dtype=bool),
        "coupon_payoffs": np.zeros(n),
    }


# ── shareability ───────────────────────────────────────────────────────────────
def test_identical_notes_can_share_paths():
    assert share_blockers(_terms(), _terms()) == []


@pytest.mark.parametrize("over,blocker", [
    ({"tickers": {"AAPL": "Apple"}},                      "underlyings"),
    ({"maturity": 2.0},                                   "maturity"),
    ({"settlement_date": "2024-01-15", "issue_date": "2024-01-15"}, "held"),
])
def test_share_blockers_name_the_offending_term(over, blocker):
    assert share_blockers(_terms(), _terms(**over)) == [blocker]


def test_reordered_underlyings_still_share_paths():
    """A basket is a SET. The same two underlyings listed in a different order is
    the same note — worst-of / best-of / average all reduce across assets — so it
    must not block a shared simulation."""
    a = _terms(tickers={"SBUX": "Starbucks", "GE": "General Electric"})
    b = _terms(tickers={"GE": "General Electric", "SBUX": "Starbucks"})
    assert share_blockers(a, b) == []


def test_held_notes_need_the_same_issue_date():
    a = _terms(settlement_date="2024-01-15", issue_date="2024-01-15")
    b = _terms(settlement_date="2024-06-15", issue_date="2024-06-15")
    # Both held, so the grid and the fixings differ only through the issue date.
    assert share_blockers(a, b) == ["issue_date"]
    assert share_blockers(a, _terms(settlement_date="2024-01-15",
                                    issue_date="2024-01-15")) == []


def test_legacy_seasoned_flag_migrates_to_a_position():
    """`seasoned` was a stored flag; it is now derived from settlement_date. A legacy
    config must keep modelling the remaining life — as a note held since issue at par,
    which is what it always meant — and must NOT become a secondary purchase."""
    t = _terms(seasoned=True, issue_date="2024-01-15")
    assert t.settlement_date == "2024-01-15"
    assert t.is_held is True
    assert t.is_secondary is False          # held since issue at par is a subscription
    assert t.cost_basis == 1.0
    assert "seasoned" not in t.to_dict()    # the flag is gone from the schema


# ── paired statistics ──────────────────────────────────────────────────────────
def test_win_rate_counts_paths_not_averages():
    """B loses big on one path and wins slightly on nine: the mean edge favours A
    while the win rate favours B. Reporting only the mean hides that entirely."""
    a = _note([0.0] * 10)
    b = _note([-1.0] + [0.01] * 9)
    p = paired_stats(a, b, _terms(), _terms())
    assert p["win_rate"] == pytest.approx(0.9)
    assert p["loss_rate"] == pytest.approx(0.1)
    assert p["mean_edge"] < 0            # mean says A
    assert p["median_edge"] > 0          # median and win rate say B


def test_ties_are_not_counted_as_wins():
    p = paired_stats(_note([0.05] * 4), _note([0.05] * 4), _terms(), _terms())
    assert (p["win_rate"], p["tie_rate"], p["loss_rate"]) == (0.0, 1.0, 0.0)
    assert p["mean_edge"] == pytest.approx(0.0)
    assert p["se_edge"] == pytest.approx(0.0)


def test_edge_percentiles_and_paired_standard_error():
    d = np.linspace(-0.10, 0.10, 101)               # symmetric edge distribution
    p = paired_stats(_note(np.zeros(101)), _note(d), _terms(), _terms())
    assert p["mean_edge"] == pytest.approx(0.0, abs=1e-12)
    assert p["edge_p5"] == pytest.approx(-0.09, abs=1e-9)
    assert p["edge_p95"] == pytest.approx(0.09, abs=1e-9)
    # SE of the paired difference = std / sqrt(n)
    assert p["se_edge"] == pytest.approx(d.std(ddof=1) / np.sqrt(101))


def test_transition_matrix_rows_are_a_outcomes():
    """Two paths: one A calls / B calls, one A knocks in / B redeems at par. The
    off-diagonal cell is the whole point — it answers "when A knocked in, what
    did B do?"."""
    a = _note([0.05, -0.4], called=[1, 0], ki=[False, True])
    b = _note([0.05, 0.02], called=[1, 0], ki=[False, False])
    p = paired_stats(a, b, _terms(), _terms())
    assert p["labels"] == ["out_called", "out_par", "out_ki"]
    m = p["transition"]
    assert m[0][0] == pytest.approx(0.5)      # called under both
    assert m[2][1] == pytest.approx(0.5)      # A knocked in, B redeemed at par
    assert sum(sum(row) for row in m) == pytest.approx(1.0)


def test_conditional_tails_look_at_a_s_bad_paths():
    a = _note([-0.30, 0.05, 0.05, 0.05])
    b = _note([0.10, 0.05, 0.05, 0.05])       # B rescues the one path A loses on
    p = paired_stats(a, b, _terms(), _terms())["conditional"]
    assert p["a_loss_rate"] == pytest.approx(0.25)
    assert p["b_loss_rate"] == pytest.approx(0.0)
    assert p["b_loses_given_a"] == pytest.approx(0.0)
    assert p["edge_on_a_losses"] == pytest.approx(0.40)


def test_participation_buckets_split_on_the_redemption():
    t = _terms(note_type="participation", protection_level=1.0, autocall_start_period=99)
    note = _note([0.2, 0.0, -0.2], payoff=[1.2, 1.0, 0.8])
    code, labels = outcome_buckets(note, t)
    assert labels == ["part_loss", "part_par", "part_gain"]
    assert code.tolist() == [2, 1, 0]


# ── diff-table error bars ──────────────────────────────────────────────────────
def test_paired_standard_error_is_tighter_than_independent():
    """The whole reason for sharing paths: common market risk cancels in the
    difference, so the same data yields a far smaller error bar on the delta."""
    rng = np.random.default_rng(0)
    market = rng.normal(0, 0.30, 4000)          # shared shock, dwarfs the term effect
    a = _note(market)
    b = _note(market + 0.01)                    # B is +1% on EVERY path
    paired = compare_diff({"expected_total_return": float(market.mean())},
                           {"expected_total_return": float((market + 0.01).mean())},
                           _terms(), _terms(), a, b, True)
    indep = compare_diff({"expected_total_return": float(market.mean())},
                          {"expected_total_return": float((market + 0.01).mean())},
                          _terms(), _terms(), a, b, False)
    se_paired = next(r["se"] for r in paired["rows"] if r["key"] == "expected_total_return")
    se_indep = next(r["se"] for r in indep["rows"] if r["key"] == "expected_total_return")
    assert se_paired == pytest.approx(0.0, abs=1e-9)   # the difference is constant
    assert se_indep > 100 * max(se_paired, 1e-12)      # independent can't see it


def test_diff_adds_a_cost_basis_row_only_when_the_sides_differ():
    keys = lambda d: [r["key"] for r in d["rows"]]     # noqa: E731
    same = compare_diff({}, {}, _terms(), _terms())
    assert "cost_basis" not in keys(same)
    bought = compare_diff({}, {}, _terms(), _terms(purchase_price=0.95))
    assert "cost_basis" in keys(bought)
    row = next(r for r in bought["rows"] if r["key"] == "cost_basis")
    assert (row["a"], row["b"]) == (1.0, pytest.approx(0.95))
